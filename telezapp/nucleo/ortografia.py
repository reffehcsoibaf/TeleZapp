"""Corretor ortografico: usa o verificador do proprio Windows (ISpellChecker,
Windows 8 em diante), por ctypes, sem dependencia nova. Os dicionarios sao os
dos idiomas instalados no Windows e "Adicionar ao dicionario" grava no
dicionario pessoal do Windows, o mesmo dos outros programas."""
import ctypes
import logging
import sys
from ctypes import POINTER, byref, c_int, c_uint32, c_void_p, c_wchar_p
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

IDIOMAS = (("pt-BR", "Português do Brasil"), ("pt-PT", "Português de Portugal"),
           ("en-US", "Inglês dos Estados Unidos"), ("es-ES", "Espanhol"))

ACAO_SUGERIR, ACAO_SUBSTITUIR, ACAO_REMOVER = 1, 2, 3


@dataclass
class Erro:
    inicio: int          # posicao em caracteres do texto original
    tamanho: int
    palavra: str
    acao: int = 0
    troca: str = ""      # substituicao automatica (ACAO_SUBSTITUIR)
    sugestoes: list = field(default_factory=list)


class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16),
                ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]

    def __init__(self, texto):
        import uuid
        u = uuid.UUID(texto)
        super().__init__(u.time_low, u.time_mid, u.time_hi_version,
                         (ctypes.c_ubyte * 8)(*u.bytes[8:]))


CLSID_FABRICA = "7AB36653-1796-484B-BDFA-E74F1DB7C1DC"
IID_FABRICA = "8E018A9D-2415-4677-BF08-794EA61F94BB"


def _chamar(ptr, indice, restipo, *tipos):
    """Metodo numero `indice` da tabela virtual de um objeto COM."""
    tabela = ctypes.cast(ctypes.cast(ptr, POINTER(c_void_p))[0],
                         POINTER(c_void_p))
    return ctypes.WINFUNCTYPE(restipo, c_void_p, *tipos)(tabela[indice])


def _soltar(ptr):
    if ptr and ptr.value:
        _chamar(ptr, 2, c_uint32)(ptr)


def _cadeia_com(ptr):
    """Le e libera um LPWSTR (c_void_p) devolvido pelo COM."""
    texto = ctypes.wstring_at(ptr.value)
    ctypes.windll.ole32.CoTaskMemFree(ptr)
    return texto


class Corretor:
    """Um verificador de um idioma. `disponivel` e False onde o Windows nao
    oferece o servico ou o idioma; nesse caso nada e marcado como erro."""

    def __init__(self, idioma="pt-BR"):
        self.idioma = idioma
        self._fab = c_void_p()
        self._ver = c_void_p()
        self.disponivel = False
        if sys.platform != "win32":
            return
        try:
            self._iniciar(idioma)
        except Exception:
            log.exception("Verificador ortografico indisponivel")
            self.disponivel = False

    def _iniciar(self, idioma):
        # so nosso: em windll, os argtypes abaixo valeriam para o programa todo
        ole = ctypes.WinDLL("ole32")
        ole.CoInitializeEx(None, 2)       # ja pode estar iniciado: tudo bem
        clsid, iid = _GUID(CLSID_FABRICA), _GUID(IID_FABRICA)
        ole.CoCreateInstance.argtypes = [POINTER(_GUID), c_void_p, c_uint32,
                                         POINTER(_GUID), POINTER(c_void_p)]
        if ole.CoCreateInstance(byref(clsid), None, 1, byref(iid),
                                byref(self._fab)) != 0:
            return
        aceito = c_int(0)
        _chamar(self._fab, 4, ctypes.c_long, c_wchar_p, POINTER(c_int))(
            self._fab, idioma, byref(aceito))
        if not aceito.value:
            return
        if _chamar(self._fab, 5, ctypes.c_long, c_wchar_p, POINTER(c_void_p))(
                self._fab, idioma, byref(self._ver)) != 0:
            return
        self.disponivel = True

    def __del__(self):
        try:
            _soltar(self._ver)
            _soltar(self._fab)
        except Exception:
            pass

    # ------------------------------------------------------------- consulta
    def verificar(self, texto):
        """Lista de Erro, na ordem do texto."""
        if not self.disponivel or not texto.strip():
            return []
        # o Windows conta em unidades UTF-16; emojis ocupam duas
        pos16 = []
        for i, ch in enumerate(texto):
            pos16.extend([i] * (2 if ord(ch) > 0xFFFF else 1))
        pos16.append(len(texto))
        enum = c_void_p()
        if _chamar(self._ver, 4, ctypes.c_long, c_wchar_p, POINTER(c_void_p))(
                self._ver, texto, byref(enum)) != 0 or not enum.value:
            return []
        erros = []
        try:
            while True:
                err = c_void_p()
                if _chamar(enum, 3, ctypes.c_long, POINTER(c_void_p))(
                        enum, byref(err)) != 0 or not err.value:
                    break
                try:
                    ini, tam, acao = c_uint32(), c_uint32(), c_int()
                    _chamar(err, 3, ctypes.c_long, POINTER(c_uint32))(
                        err, byref(ini))
                    _chamar(err, 4, ctypes.c_long, POINTER(c_uint32))(
                        err, byref(tam))
                    _chamar(err, 5, ctypes.c_long, POINTER(c_int))(
                        err, byref(acao))
                    a = pos16[min(ini.value, len(pos16) - 1)]
                    b = pos16[min(ini.value + tam.value, len(pos16) - 1)]
                    e = Erro(a, b - a, texto[a:b], acao.value)
                    if acao.value == ACAO_SUBSTITUIR:
                        r = c_void_p()
                        _chamar(err, 6, ctypes.c_long, POINTER(c_void_p))(
                            err, byref(r))
                        e.troca = _cadeia_com(r)
                    erros.append(e)
                finally:
                    _soltar(err)
        finally:
            _soltar(enum)
        return erros

    def sugerir(self, palavra, maximo=8):
        if not self.disponivel:
            return []
        enum = c_void_p()
        if _chamar(self._ver, 5, ctypes.c_long, c_wchar_p, POINTER(c_void_p))(
                self._ver, palavra, byref(enum)) != 0 or not enum.value:
            return []
        achadas = []
        try:
            while len(achadas) < maximo:
                s, n = c_void_p(), c_uint32()
                if _chamar(enum, 3, ctypes.c_long, c_uint32, POINTER(c_void_p),
                           POINTER(c_uint32))(enum, 1, byref(s),
                                              byref(n)) != 0 or not n.value:
                    break
                achadas.append(_cadeia_com(s))
        finally:
            _soltar(enum)
        return achadas

    # ------------------------------------------------------------- dicionario
    def adicionar(self, palavra):
        """Grava a palavra no dicionario pessoal do Windows."""
        if self.disponivel:
            _chamar(self._ver, 6, ctypes.c_long, c_wchar_p)(self._ver, palavra)

    def ignorar(self, palavra):
        """Deixa de marcar a palavra enquanto o programa estiver aberto."""
        if self.disponivel:
            _chamar(self._ver, 7, ctypes.c_long, c_wchar_p)(self._ver, palavra)


def aplicar(texto, erro, nova):
    """O texto com `nova` no lugar da palavra errada."""
    return texto[:erro.inicio] + nova + texto[erro.inicio + erro.tamanho:]


class Revisao:
    """Percorre os erros de um texto, um de cada vez. O texto e verificado de
    novo depois de cada troca, entao as posicoes nunca ficam velhas."""

    def __init__(self, corretor, texto):
        self.corretor = corretor
        self.texto = texto
        self.posicao = 0          # so olha erros daqui para a frente
        self.erro = None
        self.trocas = 0
        self.avancar()

    def avancar(self):
        """Poe em `erro` o proximo erro (ou None, quando acabou)."""
        self.erro = None
        for e in self.corretor.verificar(self.texto):
            if e.inicio >= self.posicao:
                e.sugestoes = self.corretor.sugerir(e.palavra) \
                    if e.acao != ACAO_REMOVER else []
                if e.acao == ACAO_SUBSTITUIR and e.troca and \
                        e.troca not in e.sugestoes:
                    e.sugestoes.insert(0, e.troca)
                self.erro = e
                return

    def substituir(self, nova, todas=False):
        e = self.erro
        if todas:
            iguais = [x for x in self.corretor.verificar(self.texto)
                      if x.palavra == e.palavra]
            for x in reversed(iguais):
                self.texto = aplicar(self.texto, x, nova)
                self.trocas += 1
            self.posicao = e.inicio + len(nova)
        else:
            self.texto = aplicar(self.texto, e, nova)
            self.trocas += 1
            self.posicao = e.inicio + len(nova)
        self.avancar()

    def ignorar(self, sempre=False):
        if sempre:
            self.corretor.ignorar(self.erro.palavra)
        self.posicao = self.erro.inicio + self.erro.tamanho
        self.avancar()

    def adicionar(self):
        self.corretor.adicionar(self.erro.palavra)
        self.posicao = self.erro.inicio + self.erro.tamanho
        self.avancar()

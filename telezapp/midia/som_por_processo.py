# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Captura do som do computador SEM o som do próprio TeleZapp (loopback por
processo do WASAPI, Windows 10 build 20348 em diante).

Numa chamada, a voz da outra pessoa é tocada pelo TeleZapp. O loopback
comum capta tudo o que toca na saída, inclusive essa voz, e ela voltaria para
quem fala. O loopback por processo (`ActivateAudioInterfaceAsync` com
`AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK`, modo "excluir a árvore do
processo") entrega o som de todos os outros programas e deixa de fora o do
processo alvo: aqui, o do TeleZapp. Assim a voz do outro lado nunca entra, sem
nenhum cancelamento de eco, e os sons do próprio TeleZapp (avisos, fala) também
não vão para a chamada.

Só ctypes: a interface COM é chamada pelas tabelas de métodos. O formato que
sai é o da chamada: PCM de 16 bits, 16 kHz, mono. Qualquer falha levanta
`ErroPorProcesso`, e quem chama usa o loopback comum.
"""
import ctypes
import logging
import os
import sys
import threading
import time
import uuid
from ctypes import (POINTER, Structure, WINFUNCTYPE, byref, c_int, c_int64,
                    c_long, c_uint32, c_uint64, c_ulong, c_void_p, wintypes)

import numpy as np

log = logging.getLogger("telezapp.som_por_processo")

TAXA = 16000
AMOSTRAS = 960                          # 60 ms
BYTES_POR_QUADRO = AMOSTRAS * 2

_VAD_PROCESS_LOOPBACK = "VAD\\Process_Loopback"
_ACTIVATION_PROCESS_LOOPBACK = 1
_EXCLUIR_ARVORE = 1
_VT_BLOB = 65
_FLAG_LOOPBACK = 0x00020000
_FLAG_AUTOCONVERTPCM = 0x80000000
_FLAG_SRC_QUALIDADE = 0x08000000
_BUFFERFLAGS_SILENT = 0x2
_TEMPO_PARA_ATIVAR_S = 6.0


class ErroPorProcesso(Exception):
    """O loopback por processo não está disponível (Windows antigo, sem
    saída de som, falha de COM...)."""


class _GUID(Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


def _guid(texto):
    u = uuid.UUID(texto)
    g = _GUID()
    g.Data1, g.Data2, g.Data3 = u.time_low, u.time_mid, u.time_hi_version
    for i, b in enumerate(bytes([u.clock_seq_hi_variant, u.clock_seq_low])
                          + u.node.to_bytes(6, "big")):
        g.Data4[i] = b
    return g


def _mesmo_guid(a, b):
    return (a.Data1, a.Data2, a.Data3, bytes(a.Data4)) == \
        (b.Data1, b.Data2, b.Data3, bytes(b.Data4))


IID_UNKNOWN = _guid("00000000-0000-0000-C000-000000000046")
IID_AGILE = _guid("94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90")
IID_HANDLER = _guid("41D949AB-9862-444A-80F6-C261334DA5EB")
IID_AUDIOCLIENT = _guid("1CB9AD4C-DBFA-4C32-B178-C2F568A703B2")
IID_CAPTURECLIENT = _guid("C8ADBD64-E71E-48A0-A4DE-185C395CD317")


class _WAVEFORMATEX(Structure):
    _fields_ = [("wFormatTag", wintypes.WORD), ("nChannels", wintypes.WORD),
                ("nSamplesPerSec", wintypes.DWORD),
                ("nAvgBytesPerSec", wintypes.DWORD),
                ("nBlockAlign", wintypes.WORD),
                ("wBitsPerSample", wintypes.WORD), ("cbSize", wintypes.WORD)]


class _ProcessLoopback(Structure):
    _fields_ = [("TargetProcessId", wintypes.DWORD),
                ("ProcessLoopbackMode", c_int)]


class _ActivationParams(Structure):
    _fields_ = [("ActivationType", c_int),
                ("ProcessLoopbackParams", _ProcessLoopback)]


class _Blob(Structure):
    _fields_ = [("cbSize", c_ulong), ("pBlobData", c_void_p)]


class _PropVariant(Structure):
    _fields_ = [("vt", wintypes.WORD), ("r1", wintypes.WORD),
                ("r2", wintypes.WORD), ("r3", wintypes.WORD),
                ("blob", _Blob)]


def _metodo(objeto, indice, restype, *argtipos):
    """O método `indice` da tabela de métodos do objeto COM `objeto`."""
    tabela = c_void_p.from_address(objeto).value
    endereco = c_void_p.from_address(tabela + 8 * indice).value
    return WINFUNCTYPE(restype, c_void_p, *argtipos)(endereco)


def _liberar(objeto):
    if objeto:
        try:
            _metodo(objeto, 2, c_ulong)(objeto)         # IUnknown::Release
        except Exception:
            pass


def _checar(hr, o_que):
    if hr < 0:
        raise ErroPorProcesso("%s falhou (0x%08X)" % (o_que, hr & 0xFFFFFFFF))


# --------------------------------------------------- o objeto de retorno
_QI_T = WINFUNCTYPE(c_long, c_void_p, POINTER(_GUID), POINTER(c_void_p))
_REF_T = WINFUNCTYPE(c_ulong, c_void_p)
_COMPLETA_T = WINFUNCTYPE(c_long, c_void_p, c_void_p)


class _Tabela(Structure):
    _fields_ = [("qi", _QI_T), ("addref", _REF_T), ("release", _REF_T),
                ("completou", _COMPLETA_T)]


class _Objeto(Structure):
    _fields_ = [("tabela", POINTER(_Tabela))]


class _Ativacao:
    """O IActivateAudioInterfaceCompletionHandler (agil: serve a qualquer
    thread) que espera o Windows entregar o cliente de audio."""

    def __init__(self):
        self.pronto = threading.Event()
        self.hr = -1
        self.cliente = None
        self._contagem = 1
        self._tabela = _Tabela(_QI_T(self._qi), _REF_T(self._ref_mais),
                               _REF_T(self._ref_menos),
                               _COMPLETA_T(self._completou))
        self._objeto = _Objeto(ctypes.pointer(self._tabela))
        self.ponteiro = ctypes.addressof(self._objeto)

    def _qi(self, this, riid, saida):
        pedida = riid.contents
        if any(_mesmo_guid(pedida, g)
               for g in (IID_UNKNOWN, IID_AGILE, IID_HANDLER)):
            saida[0] = self.ponteiro
            self._contagem += 1
            return 0
        saida[0] = None
        return -2147467262                  # E_NOINTERFACE

    def _ref_mais(self, this):
        self._contagem += 1
        return self._contagem

    def _ref_menos(self, this):
        self._contagem -= 1
        return self._contagem

    def _completou(self, this, operacao):
        try:
            hr = c_long()
            unk = c_void_p()
            _metodo(operacao, 3, c_long, POINTER(c_long),
                    POINTER(c_void_p))(operacao, byref(hr), byref(unk))
            self.hr, self.cliente = hr.value, unk.value
        except Exception:
            log.exception("erro ao receber o cliente de áudio")
            self.hr = -1
        self.pronto.set()
        return 0


def disponivel():
    """O Windows tem a ativação por processo? (Windows 10 build 20348 em
    diante; a função nasce com o Windows 8, então só uma tentativa mostra.)"""
    if sys.platform != "win32":
        return False
    try:
        return sys.getwindowsversion().build >= 20348
    except Exception:
        return False


class CapturaPorProcesso:
    """O som de todos os programas menos o do processo `pid` (o TeleZapp),
    em quadros de 60 ms (PCM s16le, 16 kHz, mono). Tem `nome`, `exato`,
    `ler()` e `fechar()`, como as fontes de som do TeleZapp. Tudo roda na
    thread que a abre (ela precisa ter o COM iniciado: `abrir` faz isso)."""

    nome = "Todo o som do computador, menos o do TeleZapp"
    exato = True

    def __init__(self, pid=None):
        if not disponivel():
            raise ErroPorProcesso("O Windows desta máquina não tem o "
                                  "loopback por processo.")
        self._pid = pid or os.getpid()
        self._cliente = self._captura = None
        self._com = False
        self._canais = 1
        self._taxa = TAXA
        self._bytes_por_amostra = 2
        self._acumulado = np.empty(0, dtype="float32")
        self._abrir()

    # ---------------------------------------------------------- abrir
    def _abrir(self):
        ole32 = ctypes.windll.ole32
        hr = ole32.CoInitializeEx(None, 0)          # COINIT_MULTITHREADED
        if hr in (0, 1):                            # S_OK, S_FALSE
            self._com = True
        elif hr != -2147417850:                     # RPC_E_CHANGED_MODE: ja ha
            _checar(hr, "CoInitializeEx")
        try:
            self._ativar()
            self._iniciar()
        except BaseException:
            self.fechar()
            raise

    def _ativar(self):
        params = _ActivationParams(
            _ACTIVATION_PROCESS_LOOPBACK,
            _ProcessLoopback(self._pid, _EXCLUIR_ARVORE))
        variante = _PropVariant()
        variante.vt = _VT_BLOB
        variante.blob.cbSize = ctypes.sizeof(params)
        variante.blob.pBlobData = ctypes.cast(byref(params), c_void_p)
        ativacao = _Ativacao()
        operacao = c_void_p()
        f = ctypes.WinDLL("Mmdevapi").ActivateAudioInterfaceAsync
        f.restype = c_long
        f.argtypes = [ctypes.c_wchar_p, POINTER(_GUID),
                      POINTER(_PropVariant), c_void_p, POINTER(c_void_p)]
        _checar(f(_VAD_PROCESS_LOOPBACK, byref(IID_AUDIOCLIENT),
                  byref(variante), ativacao.ponteiro, byref(operacao)),
                "ActivateAudioInterfaceAsync")
        try:
            if not ativacao.pronto.wait(_TEMPO_PARA_ATIVAR_S):
                raise ErroPorProcesso("O Windows não respondeu à ativação.")
            _checar(ativacao.hr, "ativar o áudio do computador")
            if not ativacao.cliente:
                raise ErroPorProcesso("Sem cliente de áudio.")
            self._cliente = self._consultar(ativacao.cliente,
                                            IID_AUDIOCLIENT)
        finally:
            _liberar(ativacao.cliente)
            _liberar(operacao.value)

    @staticmethod
    def _consultar(objeto, iid):
        saida = c_void_p()
        _checar(_metodo(objeto, 0, c_long, POINTER(_GUID),
                        POINTER(c_void_p))(objeto, byref(iid), byref(saida)),
                "QueryInterface")
        return saida.value

    def _iniciar(self):
        c = self._cliente
        formato = self._inicializar()
        saida = c_void_p()
        _checar(_metodo(c, 14, c_long, POINTER(_GUID), POINTER(c_void_p))(
            c, byref(IID_CAPTURECLIENT), byref(saida)), "GetService")
        self._captura = saida.value
        _checar(_metodo(c, 10, c_long)(c), "Start")
        log.info("som do computador sem o do TeleZapp (%d Hz, %d canal(is))",
                 formato.nSamplesPerSec, formato.nChannels)

    def _inicializar(self):
        """Pede 16 kHz mono ao Windows; se ele recusar, 44,1 kHz estéreo
        (que o Windows sempre dá) e a conversão fica por nossa conta."""
        c = self._cliente
        ultimo = 0
        for taxa, canais, extra in ((TAXA, 1, _FLAG_AUTOCONVERTPCM
                                     | _FLAG_SRC_QUALIDADE),
                                    (44100, 2, 0)):
            formato = _WAVEFORMATEX(1, canais, taxa, taxa * canais * 2,
                                    canais * 2, 16, 0)
            ultimo = _metodo(c, 3, c_long, c_int, c_uint32, c_int64, c_int64,
                             POINTER(_WAVEFORMATEX), c_void_p)(
                c, 0, _FLAG_LOOPBACK | extra, 2_000_000, 0, byref(formato),
                None)
            if ultimo >= 0:
                self._taxa, self._canais = taxa, canais
                return formato
            log.info("formato %d Hz, %d canal(is) recusado (0x%08X)", taxa,
                     canais, ultimo & 0xFFFFFFFF)
            # um cliente que recusou o formato nao serve para outra tentativa
            self._recomecar_cliente()
            c = self._cliente
        _checar(ultimo, "Initialize")

    def _recomecar_cliente(self):
        _liberar(self._cliente)
        self._cliente = None
        self._ativar()

    # ------------------------------------------------------------ ler
    def _puxar(self):
        """Traz para dentro tudo o que o Windows já tem (float32 mono 16 kHz)."""
        cap = self._captura
        novos = []
        pacote = c_uint32()
        while True:
            _checar(_metodo(cap, 5, c_long, POINTER(c_uint32))(
                cap, byref(pacote)), "GetNextPacketSize")
            if not pacote.value:
                break
            dados = c_void_p()
            quadros = c_uint32()
            flags = wintypes.DWORD()
            pos, qpc = c_uint64(), c_uint64()
            _checar(_metodo(cap, 3, c_long, POINTER(c_void_p),
                            POINTER(c_uint32), POINTER(wintypes.DWORD),
                            POINTER(c_uint64), POINTER(c_uint64))(
                cap, byref(dados), byref(quadros), byref(flags), byref(pos),
                byref(qpc)), "GetBuffer")
            n = quadros.value * self._canais
            if flags.value & _BUFFERFLAGS_SILENT or not dados.value:
                amostras = np.zeros(n, dtype="float32")
            else:
                amostras = np.frombuffer(
                    ctypes.string_at(dados.value, n * 2),
                    dtype="<i2").astype("float32") / 32768.0
            _checar(_metodo(cap, 4, c_long, c_uint32)(cap, quadros.value),
                    "ReleaseBuffer")
            novos.append(amostras)
        if not novos:
            return
        junto = np.concatenate(novos)
        if self._canais == 2:
            junto = junto.reshape(-1, 2).mean(axis=1)
        if self._taxa != TAXA:
            junto = _para_16k(junto, self._taxa)
        self._acumulado = np.concatenate((self._acumulado, junto))

    def ler(self):
        """Um quadro de 60 ms em bytes; sem som disponível por 100 ms, devolve
        o que há completado com silêncio (o loopback não entrega nada
        enquanto nada toca)."""
        limite = time.monotonic() + 0.1
        while self._acumulado.size < AMOSTRAS:
            self._puxar()
            if self._acumulado.size >= AMOSTRAS or time.monotonic() >= limite:
                break
            time.sleep(0.005)
        bloco = self._acumulado[:AMOSTRAS]
        self._acumulado = self._acumulado[AMOSTRAS:]
        if bloco.size < AMOSTRAS:
            bloco = np.concatenate(
                (bloco, np.zeros(AMOSTRAS - bloco.size, dtype="float32")))
        return (np.clip(bloco, -1.0, 1.0) * 32767).astype("<i2").tobytes()

    def fechar(self):
        c, self._cliente = self._cliente, None
        cap, self._captura = self._captura, None
        if c:
            try:
                _metodo(c, 11, c_long)(c)                   # Stop
            except Exception:
                pass
        _liberar(cap)
        _liberar(c)
        if self._com:
            self._com = False
            try:
                ctypes.windll.ole32.CoUninitialize()
            except Exception:
                pass


def _para_16k(mono, taxa):
    """Reamostra para 16 kHz (media de blocos e interpolacao: serve a voz e a
    musica da chamada, que o Opus limita de qualquer jeito)."""
    if taxa == TAXA or mono.size == 0:
        return mono
    n = int(mono.size * TAXA / taxa)
    alvo = np.linspace(0, mono.size - 1, n)
    suave = np.convolve(mono, np.ones(3) / 3, mode="same")
    return np.interp(alvo, np.arange(mono.size), suave).astype("float32")


def abrir(pid=None):
    """Abre a captura por processo ou levanta ErroPorProcesso."""
    try:
        return CapturaPorProcesso(pid)
    except ErroPorProcesso:
        raise
    except Exception as e:
        raise ErroPorProcesso("%s: %s" % (type(e).__name__, e))

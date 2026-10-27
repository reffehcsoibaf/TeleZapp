# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Teclas de atalho: o texto de cada combinacao ("Ctrl+Shift+E"), o registro
das funcoes que aceitam atalho e a deteccao de conflitos. Sem wx, para testar
em qualquer sistema.

Uma combinacao e escrita sempre na forma canonica: modificadores na ordem
Ctrl, Alt, Shift e depois a tecla ("Ctrl+Alt+Shift+F5")."""
import re
from dataclasses import dataclass

MODIFICADORES = ("Ctrl", "Alt", "Shift")

TECLAS_NOMEADAS = ("Up", "Down", "Left", "Right", "Home", "End", "PgUp",
                   "PgDn", "Insert", "Delete", "Space", "Enter", "Esc", "Tab",
                   "Backspace")
SIMBOLOS = ",.;/\\'[]-=`"
TECLAS_F = tuple("F%d" % n for n in range(1, 13))

_APELIDOS = {"control": "Ctrl", "ctrl": "Ctrl", "alt": "Alt",
             "shift": "Shift", "pageup": "PgUp", "pgup": "PgUp",
             "pagedown": "PgDn", "pgdn": "PgDn", "del": "Delete",
             "ins": "Insert", "return": "Enter", "escape": "Esc",
             "esc": "Esc", "bksp": "Backspace", "back": "Backspace",
             "space": "Space", "tab": "Tab", "enter": "Enter"}

# o que o proprio programa ou o Windows ja usam: nao pode ser atalho
_RESERVADAS = {
    "Enter": "Enter envia a mensagem e abre os itens",
    "Esc": "Esc volta e fecha",
    "Tab": "Tab navega entre os controles",
    "Space": "Espaço marca e aperta botões",
    "Shift+Enter": "Shift Enter quebra a linha",
    "Alt+Enter": "Alt Enter mostra os detalhes da mensagem",
    "Alt+F4": "Alt F4 fecha janelas no Windows",
    "Alt+Tab": "Alt Tab troca de programa no Windows",
    "F10": "F10 abre o menu",
    "Shift+F10": "Shift F10 abre o menu de contexto",
    "Ctrl+A": "Control A seleciona tudo no texto",
    "Ctrl+C": "Control C copia",
    "Ctrl+V": "Control V cola",
    "Ctrl+X": "Control X recorta",
    "Ctrl+Z": "Control Z desfaz",
    "Ctrl+Y": "Control Y refaz",
    "Ctrl+Alt+Delete": "Control Alt Delete é do Windows",
    "Ctrl+Esc": "Control Esc abre o menu Iniciar",
    "Alt+Esc": "Alt Esc troca de programa no Windows",
    "Alt+Space": "Alt Espaço abre o menu da janela",
    "Delete": "Delete apaga",
    "Backspace": "Backspace apaga",
}


def normalizar(texto):
    """A combinacao na forma canonica, ou None se nao for uma combinacao."""
    if not isinstance(texto, str) or not texto.strip():
        return None
    partes = [p.strip() for p in re.split(r"\s*\+\s*", texto.strip())]
    mods, tecla = set(), None
    for p in partes:
        if not p:
            return None
        nome = _APELIDOS.get(p.lower(), p)
        if nome in MODIFICADORES:
            mods.add(nome)
            continue
        if tecla is not None:
            return None
        tecla = nome
    if tecla is None:
        return None
    if len(tecla) == 1 and tecla.isalpha():
        tecla = tecla.upper()
    elif len(tecla) == 1 and (tecla.isdigit() or tecla in SIMBOLOS):
        pass
    elif tecla.upper() in TECLAS_F:
        tecla = tecla.upper()
    else:
        achada = next((t for t in TECLAS_NOMEADAS
                       if t.lower() == tecla.lower()), None)
        if achada is None:
            return None
        tecla = achada
    return "+".join([m for m in MODIFICADORES if m in mods] + [tecla])


def partes(canon):
    """(ctrl, alt, shift, tecla) de uma combinacao canonica."""
    p = canon.split("+")
    tecla = p[-1]
    return "Ctrl" in p[:-1], "Alt" in p[:-1], "Shift" in p[:-1], tecla


def montar(ctrl, alt, shift, tecla):
    """A combinacao canonica de modificadores e uma tecla ja nomeada."""
    return normalizar("+".join(
        [m for m, a in (("Ctrl", ctrl), ("Alt", alt), ("Shift", shift))
         if a] + [tecla]))


def problema(canon):
    """Por que a combinacao nao serve de atalho, ou "" se serve."""
    if canon is None:
        return "Essa combinação de teclas não é válida."
    if canon in _RESERVADAS:
        return "%s." % _RESERVADAS[canon]
    ctrl, alt, shift, tecla = partes(canon)
    if tecla in TECLAS_F:
        return ""
    if not (ctrl or alt):
        return ("Use Control ou Alt junto com a tecla (ou uma tecla de F1 a "
                "F12), para não atrapalhar quem digita.")
    return ""


@dataclass
class Acao:
    chave: str
    rotulo: str
    categoria: str
    padrao: str = ""        # combinacao canonica, "" = sem atalho


def limpar_rotulo(rotulo):
    """O rotulo do menu sem a letra de acesso (&) e sem o atalho."""
    return rotulo.split("\t")[0].replace("&&", "\0").replace("&", "").replace(
        "\0", "&").strip()


class Registro:
    """As funcoes que aceitam atalho, os padroes e o que a pessoa mudou.
    `personalizados` guarda so o que difere do padrao: {chave: combinacao},
    com "" para uma funcao que ficou sem atalho."""

    def __init__(self, personalizados=None):
        self.acoes = {}
        self.personalizados = {}
        self.definir_personalizados(personalizados or {})

    def definir_personalizados(self, dados):
        self.personalizados = {}
        for chave, valor in dict(dados).items():
            canon = "" if valor == "" else normalizar(valor)
            if canon is not None:
                self.personalizados[chave] = canon

    def registrar(self, chave, rotulo, categoria, padrao=""):
        self.acoes[chave] = Acao(chave, limpar_rotulo(rotulo), categoria,
                                 normalizar(padrao) or "")

    # ------------------------------------------------------------ consulta
    def efetivo(self, chave, personalizados=None):
        """A combinacao em uso (""= sem atalho)."""
        pers = self.personalizados if personalizados is None \
            else personalizados
        if chave in pers:
            return pers[chave]
        return self.acoes[chave].padrao if chave in self.acoes else ""

    def todos(self, personalizados=None):
        """[(Acao, combinacao em uso)] na ordem do registro."""
        return [(a, self.efetivo(a.chave, personalizados))
                for a in self.acoes.values()]

    def dono(self, canon, ignorar=None, personalizados=None):
        """A Acao que ja usa a combinacao, ou None."""
        if not canon:
            return None
        for a, em_uso in self.todos(personalizados):
            if a.chave != ignorar and em_uso == canon:
                return a
        return None

    # ---------------------------------------------------------- alteracoes
    def com_atalho(self, chave, canon, personalizados=None):
        """Copia dos personalizados com `chave` usando `canon` (""= sem
        atalho). Voltar ao padrao tira a entrada."""
        pers = dict(self.personalizados if personalizados is None
                    else personalizados)
        if canon == self.acoes[chave].padrao:
            pers.pop(chave, None)
        else:
            pers[chave] = canon
        return pers

    def trocando(self, chave, canon, personalizados=None):
        """Como `com_atalho`, mas tirando a combinacao de quem a usava."""
        pers = dict(self.personalizados if personalizados is None
                    else personalizados)
        outro = self.dono(canon, ignorar=chave, personalizados=pers)
        if outro is not None:
            pers = self.com_atalho(outro.chave, "", pers)
        return self.com_atalho(chave, canon, pers)

    def buscar(self, texto, personalizados=None):
        """Funcoes cujo nome, categoria ou atalho tem todas as palavras."""
        palavras = _sem_acento(texto).split()
        achadas = []
        for a, canon in self.todos(personalizados):
            alvo = _sem_acento(" ".join((a.rotulo, a.categoria, canon,
                                         canon.replace("+", " "))))
            if all(p in alvo for p in palavras):
                achadas.append((a, canon))
        return achadas


def _sem_acento(texto):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


# como cada tecla aparece e e falada em portugues (a combinacao guardada e a
# forma canonica, em ingles, que o wx entende)
NOMES_DAS_TECLAS = {
    "Up": "Seta para cima", "Down": "Seta para baixo",
    "Left": "Seta para a esquerda", "Right": "Seta para a direita",
    "PgUp": "Page Up", "PgDn": "Page Down", "Space": "Espaço",
    "Esc": "Esc", "Backspace": "Backspace", "Delete": "Delete",
    "Insert": "Insert", ",": "vírgula", ".": "ponto", ";": "ponto e vírgula",
    "/": "barra", "\\": "barra invertida", "-": "menos", "=": "igual",
    "`": "crase", "'": "apóstrofo", "[": "abre colchete",
    "]": "fecha colchete"}
SIMBOLOS_NA_TELA = {",": ",", ".": ".", ";": ";", "/": "/", "\\": "\\",
                    "-": "-", "=": "=", "`": "`", "'": "'", "[": "[",
                    "]": "]"}


def exibir(canon):
    """A combinacao como aparece na tela: "Ctrl+Shift+Seta para a esquerda".
    Simbolos ficam como sao ("Ctrl+,")."""
    if not canon:
        return ""
    partes_ = canon.split("+")
    return "+".join(
        SIMBOLOS_NA_TELA.get(p, NOMES_DAS_TECLAS.get(p, p))
        for p in partes_)


# teclas cujo nome em portugues o wx nao entende depois do Tab do menu: o
# nome vai entre parenteses, no fim do texto do item
NOMES_FORA_DO_ACELERADOR = ("Up", "Down", "Left", "Right", "Space")


def no_fim_do_texto(canon):
    """True se o nome da combinacao nao pode ir depois do Tab do menu."""
    return bool(canon) and canon.split("+")[-1] in NOMES_FORA_DO_ACELERADOR


# teclas cujo nome em portugues o wx nao entende depois do Tab do menu: o
# nome vai entre parenteses, no fim do texto do item
NOMES_FORA_DO_ACELERADOR = ("Up", "Down", "Left", "Right", "Space")


def no_fim_do_texto(canon):
    """True se o nome da combinacao nao pode ir depois do Tab do menu."""
    return bool(canon) and canon.split("+")[-1] in NOMES_FORA_DO_ACELERADOR


# teclas cujo nome em portugues o wx nao entende depois do Tab do menu: o
# nome vai entre parenteses, no fim do texto do item
NOMES_FORA_DO_ACELERADOR = ("Up", "Down", "Left", "Right", "Space")


def no_fim_do_texto(canon):
    """True se o nome da combinacao nao pode ir depois do Tab do menu."""
    return bool(canon) and canon.split("+")[-1] in NOMES_FORA_DO_ACELERADOR


def texto_falado(canon):
    """Como o leitor de tela deve dizer a combinacao."""
    if not canon:
        return "sem atalho"
    nomes = dict(NOMES_DAS_TECLAS, Ctrl="Control")
    return " ".join(nomes.get(p, p) for p in canon.split("+"))

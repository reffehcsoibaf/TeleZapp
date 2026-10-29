# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Emojis para reagir e para escrever: a lista completa, com nomes em
portugues, e a busca por palavras. Os dados vem do pacote `emoji`; o resto
do programa so enxerga `Emoji`.

A lista traz uma linha por emoji, sem as variantes de tom de pele; cada emoji
que tem variantes forma uma "familia" (o sem tom, depois do claro ao escuro)
pela qual as setas da janela passam (`passo_de_tom`).

A busca acha pelo nome, por apelidos, por sinonimos escritos a mao
(SINONIMOS) e pelas palavras-chave em portugues do CLDR do Unicode
(emojis_cldr_pt.py, gerado por ferramentas/gerar_emojis_cldr.py): quem digita
"gargalhada", "kkk" ou "aniversario" acha o emoji mesmo que o nome nao diga
isso. O que casa com o nome vem antes do que casa so pelas palavras-chave."""
import unicodedata
from dataclasses import dataclass

# Os mais usados para reagir, na ordem do WhatsApp
RAPIDOS = ("👍", "❤️", "😂", "😮", "😢", "🙏")

# Palavras que as pessoas digitam e que nao estao nos nomes oficiais
SINONIMOS = {
    "👍": "joinha curtir curti gostei ok positivo",
    "👎": "negativo nao gostei",
    "❤️": "amor curti gostei",
    "😂": "rindo risada rir kkk haha engracado",
    "🤣": "rindo risada gargalhada kkk",
    "😢": "chorando triste",
    "😭": "chorando choro",
    "🙏": "obrigado obrigada por favor orando reza agradecer",
    "😮": "surpreso surpresa uau",
    "😡": "bravo raiva irritado",
    "🎉": "parabens festa comemorar",
    "🔥": "fogo incrivel",
    "👏": "aplausos palmas parabens",
    "😍": "apaixonado amei",
    "🥰": "apaixonado carinho",
    "😊": "feliz sorrindo sorriso",
    "👋": "tchau oi ola",
    "🤝": "acordo aperto de mao",
    "🥹": "emocionado saudade",
    "😔": "saudade desanimado",
    "🫂": "abraco saudade consolo",
    "🥺": "implorando fofo pidao",
    "🤗": "abraco carinho",
    "💪": "forca academia musculo",
    "🎂": "aniversario bolo parabens",
}


@dataclass(frozen=True)
class Emoji:
    simbolo: str
    nome: str          # em portugues, para ler e para a busca
    busca: str         # tudo o que acha este emoji, sem acento
    palavras: tuple = ()           # as palavras de `busca`, sem repetir
    palavras_nome: tuple = ()      # so as do nome em portugues
    palavras_base: tuple = ()      # nome, ingles, apelidos e sinonimos a mao


_lista = None
_cldr = None
_familias = {}      # emoji sem tom (e sem variacao) -> (o emoji, claro ... escuro)
_TONS = tuple(chr(c) for c in range(0x1F3FB, 0x1F400))


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


def _nome(codigo):
    return (codigo or "").strip(":").replace("_", " ")


def _palavras_do_cldr(simbolo):
    """As palavras-chave do CLDR para o emoji (vazio se o arquivo gerado nao
    estiver ou nao o conhece)."""
    global _cldr
    if _cldr is None:
        try:
            from telezapp.nucleo import emojis_cldr_pt
            _cldr = emojis_cldr_pt.PALAVRAS
        except ImportError:
            _cldr = {}
    return _cldr.get(simbolo.replace(chr(0xFE0F), ""), "")


def _tom_de_pele(simbolo):
    return any(c in _TONS for c in simbolo)


def _chave_da_familia(simbolo):
    """O emoji sem os tons de pele e sem o seletor de variacao: junta o
    emoji e as suas variantes numa familia so."""
    return "".join(c for c in simbolo if c not in _TONS and c != chr(0xFE0F))


def _posto_do_tom(simbolo):
    return tuple(_TONS.index(c) for c in simbolo if c in _TONS)


def todos():
    """Todos os emojis completos, sem as variantes de tom de pele, na ordem
    do Unicode (que agrupa por assunto)."""
    global _lista
    if _lista is None:
        import emoji
        emoji.demojize("😂", language="pt")        # carrega os nomes
        lista = []
        variantes = {}
        for simbolo, dados in emoji.EMOJI_DATA.items():
            if dados.get("status") != emoji.STATUS["fully_qualified"]:
                continue
            nome = _nome(dados.get("pt")) or _nome(dados.get("en"))
            if _tom_de_pele(simbolo):
                variantes.setdefault(_chave_da_familia(simbolo), []).append(
                    (_posto_do_tom(simbolo), Emoji(simbolo, nome, "")))
                continue
            ingles = _nome(dados.get("en"))
            apelidos = " ".join(_nome(a) for a in dados.get("alias", []))
            base = _sem_acento(" ".join((
                nome, ingles, apelidos, SINONIMOS.get(simbolo, ""))))
            busca = _sem_acento(" ".join((
                base, _palavras_do_cldr(simbolo))))
            lista.append(Emoji(
                simbolo, nome, busca,
                tuple(dict.fromkeys(busca.split())),
                tuple(dict.fromkeys(_sem_acento(nome).split())),
                tuple(dict.fromkeys(base.split()))))
        for e in lista:
            chave = _chave_da_familia(e.simbolo)
            outros = sorted(variantes.get(chave, []),
                            key=lambda par: (par[0], par[1].simbolo))
            if outros:
                _familias[chave] = (e,) + tuple(v for _, v in outros)
        _lista = lista
    return _lista


def passo_de_tom(simbolo, delta):
    """O proximo (delta 1) ou o anterior (-1) tom de pele do emoji, dando a
    volta pela familia (o emoji sem tom, depois do claro ao escuro); None se
    ele nao tem variantes. Devolve um `Emoji` (com o nome)."""
    todos()
    familia = _familias.get(_chave_da_familia(simbolo))
    if not familia:
        return None
    for i, e in enumerate(familia):
        if e.simbolo == simbolo:
            return familia[(i + delta) % len(familia)]
    return None


def nome_de(simbolo):
    """O nome em portugues, para falar ("polegar para cima"); o proprio
    emoji se nao o conhecemos."""
    sem_variacao = simbolo.replace("️", "")
    for e in todos():
        if e.simbolo == simbolo or e.simbolo.replace("️", "") == \
                sem_variacao:
            return e.nome
    for e in _familias.get(_chave_da_familia(simbolo)) or ():
        if e.simbolo == simbolo:
            return e.nome      # uma variante de tom de pele
    return simbolo


def _abre(palavra, digitada):
    """A palavra do emoji comeca pelo que foi digitado (ou pelo singular dele:
    "risadas" acha "risada")."""
    return palavra.startswith(digitada) or (
        len(digitada) > 3 and digitada.endswith("s")
        and palavra.startswith(digitada[:-1]))


def _casa(palavras_do_emoji, digitadas):
    # cada palavra digitada abre alguma palavra do emoji ("bolo" nao acha
    # "simbolo")
    return all(any(_abre(w, p) for w in palavras_do_emoji)
               for p in digitadas)


def buscar(texto, limite=300):
    """Os emojis cujo nome, apelido, sinonimo ou palavra-chave tem todas as
    palavras digitadas (sem diferenca de acento ou maiusculas). Sem texto,
    todos. Primeiro vem quem tem as palavras digitadas inteiras (uma busca
    por "oi" acha antes o "oi" que o "oito"); depois, quem casa com o nome,
    com apelidos e sinonimos e, por ultimo, so com as palavras-chave do CLDR;
    dentro de cada grupo, a ordem do Unicode."""
    digitadas = _sem_acento(texto or "").split()
    if not digitadas:
        return todos()[:limite] if limite else todos()
    inteiras = set(digitadas)
    achados = [((0 if inteiras <= set(e.palavras) else 1,
                 0 if _casa(e.palavras_nome, digitadas)
                 else 1 if _casa(e.palavras_base, digitadas) else 2), e)
               for e in todos() if _casa(e.palavras, digitadas)]
    achados.sort(key=lambda par: par[0])        # estavel: mantem a ordem
    achados = [e for _, e in achados]
    return achados[:limite] if limite else achados

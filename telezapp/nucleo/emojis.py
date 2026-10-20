# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Emojis para reagir e para escrever: a lista completa, com nomes em
portugues, e a busca por palavras. Os dados vem do pacote `emoji`; o resto
do programa so enxerga `Emoji`."""
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
}


@dataclass(frozen=True)
class Emoji:
    simbolo: str
    nome: str          # em portugues, para ler e para a busca
    busca: str         # tudo o que acha este emoji, sem acento
    palavras: tuple = ()


_lista = None


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


def _nome(codigo):
    return (codigo or "").strip(":").replace("_", " ")


def _tom_de_pele(simbolo):
    return any("\U0001F3FB" <= c <= "\U0001F3FF" for c in simbolo)


def todos():
    """Todos os emojis completos, sem as variantes de tom de pele, na ordem
    do Unicode (que agrupa por assunto)."""
    global _lista
    if _lista is None:
        import emoji
        emoji.demojize("😂", language="pt")        # carrega os nomes
        lista = []
        for simbolo, dados in emoji.EMOJI_DATA.items():
            if dados.get("status") != emoji.STATUS["fully_qualified"] \
                    or _tom_de_pele(simbolo):
                continue
            nome = _nome(dados.get("pt")) or _nome(dados.get("en"))
            ingles = _nome(dados.get("en"))
            apelidos = " ".join(_nome(a) for a in dados.get("alias", []))
            busca = _sem_acento(" ".join((
                nome, ingles, apelidos, SINONIMOS.get(simbolo, ""))))
            lista.append(Emoji(simbolo, nome, busca,
                               tuple(dict.fromkeys(busca.split()))))
        _lista = lista
    return _lista


def nome_de(simbolo):
    """O nome em portugues, para falar ("polegar para cima"); o proprio
    emoji se nao o conhecemos."""
    sem_variacao = simbolo.replace("️", "")
    for e in todos():
        if e.simbolo == simbolo or e.simbolo.replace("️", "") == \
                sem_variacao:
            return e.nome
    return simbolo


def buscar(texto, limite=300):
    """Os emojis cujo nome, apelido ou sinonimo tem todas as palavras
    digitadas (sem diferenca de acento ou maiusculas). Sem texto, todos."""
    palavras = _sem_acento(texto or "").split()
    if not palavras:
        return todos()[:limite] if limite else todos()
    # cada palavra digitada abre alguma palavra do nome ("bolo" nao acha
    # "simbolo")
    achados = [e for e in todos() if all(
        any(w.startswith(p) for w in e.palavras) for p in palavras)]
    # quem comeca pela palavra vem antes
    primeira = palavras[0]
    achados.sort(key=lambda e: not e.busca.startswith(primeira))
    return achados[:limite] if limite else achados

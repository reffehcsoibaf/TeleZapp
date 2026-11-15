# SPDX-License-Identifier: GPL-3.0-or-later
"""Tira da resposta de um bot tradutor a linha de cabecalho dos idiomas
("Welsh → Portugues"), que vem antes da traducao e nao faz parte dela."""
import re

_SETA = r"(?:→|➡️?|➜|⇒|->|=>)"
_IDIOMA = r"[^\n.,;:!?()\[\]→➡➜⇒<>=-]{1,24}"
_CABECALHO = re.compile(
    r"\A[ \t]*" + _IDIOMA + r"[ \t]*" + _SETA + r"[ \t]*" + _IDIOMA +
    r"[ \t]*\r?\n+")


def sem_cabecalho_de_idiomas(texto):
    """O texto sem a primeira linha, se ela so diz "idioma → idioma" e
    sobra traducao depois; senao, o texto como veio."""
    if not texto:
        return texto
    resto = _CABECALHO.sub("", texto, count=1)
    return resto if resto.strip() else texto

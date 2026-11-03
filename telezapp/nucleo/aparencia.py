# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Aparencia da janela: o modo de exibicao e o tamanho da letra.

O modo "para leitor de tela" e a janela de sempre, feita para ser ouvida. O
modo "visual" e para quem le na tela. No automatico, vale o que o Windows
diz ao abrir: com um leitor de tela ligado, o modo para leitor de tela.
"""
import ctypes
import logging

log = logging.getLogger("telezapp.aparencia")

AUTOMATICO = "automatico"
LEITOR = "leitor"
VISUAL = "visual"

LETRA_NORMAL = 100
SPI_GETSCREENREADER = 0x0046


def leitor_de_tela_ligado():
    """O Windows avisa que ha um leitor de tela em uso? (O NVDA, o JAWS e o
    Narrador ligam esse aviso.) Fora do Windows ou com erro: False."""
    try:
        valor = ctypes.c_int(0)
        if not ctypes.windll.user32.SystemParametersInfoW(
                SPI_GETSCREENREADER, 0, ctypes.byref(valor), 0):
            return False
        return bool(valor.value)
    except Exception:
        return False


def modo(escolha, leitor_ligado=None):
    """O modo que vale: LEITOR ou VISUAL. `escolha` e a opcao guardada; no
    automatico (ou valor desconhecido), conta se ha leitor de tela ligado."""
    if escolha in (LEITOR, VISUAL):
        return escolha
    if leitor_ligado is None:
        leitor_ligado = leitor_de_tela_ligado()
    return LEITOR if leitor_ligado else VISUAL


def rotulo_do_dia(ts, agora=None):
    """"Hoje", "Ontem" ou "02/11/2026": o separador de dia da lista visual."""
    import time
    if not ts:
        return ""
    agora = time.time() if agora is None else agora
    try:
        dia = time.localtime(ts)
    except (OSError, OverflowError, ValueError):
        return ""
    hoje = time.localtime(agora)
    ontem = time.localtime(agora - 86400)
    if (dia.tm_year, dia.tm_yday) == (hoje.tm_year, hoje.tm_yday):
        return "Hoje"
    if (dia.tm_year, dia.tm_yday) == (ontem.tm_year, ontem.tm_yday):
        return "Ontem"
    return time.strftime("%d/%m/%Y", dia)


def quebrar_linhas(texto, largura, medir):
    """Divide o texto em linhas que cabem em `largura`, medida por
    `medir(trecho) -> pixels`. Quebra entre palavras; palavra maior que a
    linha (um link longo) e cortada onde couber. Sempre ao menos uma linha."""
    linhas = []
    for paragrafo in (texto or "").split("\n"):
        atual = ""
        for palavra in paragrafo.split(" "):
            tentativa = palavra if not atual else atual + " " + palavra
            if medir(tentativa) <= largura:
                atual = tentativa
                continue
            if atual:
                linhas.append(atual)
            atual = palavra
            while len(atual) > 1 and medir(atual) > largura:
                corte = len(atual) - 1
                while corte > 1 and medir(atual[:corte]) > largura:
                    corte -= 1
                linhas.append(atual[:corte])
                atual = atual[corte:]
        linhas.append(atual)
    return linhas or [""]


def tamanho_da_letra(base, porcento):
    """Tamanho em pontos da letra para `porcento` do tamanho `base`."""
    try:
        porcento = int(porcento)
    except (TypeError, ValueError):
        porcento = LETRA_NORMAL
    porcento = max(LETRA_NORMAL, min(porcento, 300))
    return round(float(base) * porcento / LETRA_NORMAL, 1)

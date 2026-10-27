# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Dispositivos de som: a saida (onde tocam os audios e a chamada) e o
microfone (onde se grava a voz e se fala na chamada) que a pessoa escolheu.

Vazio quer dizer "o padrao do Windows". A lista vem do sounddevice, na API de
som padrao do Windows (a mesma das chamadas do WhatsApp), sem repetir. O
Windows corta os nomes dessa API em 31 letras, entao um nome vale tambem como
inicio do nome completo que outras bibliotecas (a soundcard, o NTgCalls)
mostram."""
import logging
import threading

log = logging.getLogger("telezapp.dispositivos")

PADRAO = ""                  # "o padrao do Windows"
_IGNORADOS = ("Mapeador de som",)     # o mapeador e o proprio padrao

_trava = threading.Lock()
_escolha = {"microfone": PADRAO, "saida": PADRAO, "notificacao": PADRAO}


def definir(microfone=PADRAO, saida=PADRAO, notificacao=None):
    """Guarda a escolha para quem abre o som depois (reprodutor, gravador).
    `notificacao` e a saida dos sons de aviso do TeleZapp; None deixa como
    esta."""
    with _trava:
        _escolha["microfone"] = microfone or PADRAO
        _escolha["saida"] = saida or PADRAO
        if notificacao is not None:
            _escolha["notificacao"] = notificacao or PADRAO


def notificacao():
    """A saida dos sons de aviso (vazio = o padrao do Windows)."""
    with _trava:
        return _escolha["notificacao"]


def microfone():
    with _trava:
        return _escolha["microfone"]


def saida():
    with _trava:
        return _escolha["saida"]


def parecem_o_mesmo(escolhido, completo):
    """True se `escolhido` (que pode estar cortado) e `completo` sao o mesmo
    dispositivo."""
    if not escolhido or not completo:
        return False
    return completo == escolhido or completo.startswith(escolhido) or \
        escolhido.startswith(completo)


def listar():
    """([microfones], [saidas]) do Windows, sem repetir nem listar o
    mapeador."""
    mics, saidas = [], []
    try:
        import sounddevice as sd
        api = sd.query_hostapis(sd.default.hostapi)
        for i in api["devices"]:
            d = sd.query_devices(i)
            nome = d["name"]
            if nome.startswith(_IGNORADOS):
                continue
            if d["max_input_channels"] > 0 and nome not in mics:
                mics.append(nome)
            if d["max_output_channels"] > 0 and nome not in saidas:
                saidas.append(nome)
    except Exception:
        log.exception("erro ao listar dispositivos de som")
    return mics, saidas


def indice(nome, entrada):
    """O numero do dispositivo no sounddevice, ou None (= o padrao)."""
    if not nome:
        return None
    try:
        import sounddevice as sd
        api = sd.query_hostapis(sd.default.hostapi)
        for i in api["devices"]:
            d = sd.query_devices(i)
            canais = d["max_input_channels" if entrada
                       else "max_output_channels"]
            if canais > 0 and parecem_o_mesmo(nome, d["name"]):
                return i
    except Exception:
        log.exception("erro ao achar o dispositivo de som")
    return None


def indice_do_microfone():
    return indice(microfone(), True)


def indice_da_saida():
    return indice(saida(), False)


def indice_da_notificacao():
    return indice(notificacao(), False)


def opcoes(nomes, atual):
    """(itens, posicao): "Padrão do Windows" primeiro e depois os nomes, com a
    posicao do escolhido (0 se for o padrao ou se sumiu da lista). Para a
    janela; pura."""
    itens = ["Padrão do Windows"] + list(nomes)
    for n, nome in enumerate(nomes, 1):
        if parecem_o_mesmo(atual, nome):
            return itens, n
    return itens, 0


def nome_escolhido(itens, posicao):
    """O nome a guardar para a posicao escolhida na lista de `opcoes`."""
    return PADRAO if posicao <= 0 or posicao >= len(itens) else itens[posicao]

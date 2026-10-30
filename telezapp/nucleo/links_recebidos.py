# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Links que o Windows entregou ao TeleZapp (--link).

Quem foi aberto so para entregar o link o grava aqui e avisa a abertura que ja
esta rodando (nucleo.instancia), que os retira. Sem wx.
"""
import logging
import os

from telezapp import config

log = logging.getLogger("telezapp.links")

LIMITE = 4096
MAXIMO = 20


def _arquivo():
    return os.path.join(config.pasta("links"), "pendentes.txt")


def guardar(url):
    url = (url or "").strip()
    if not url or len(url) > LIMITE or "\n" in url or "\r" in url:
        return False
    try:
        with open(_arquivo(), "a", encoding="utf-8") as f:
            f.write(url + "\n")
        return True
    except OSError:
        log.warning("não consegui guardar o link recebido")
        return False


def retirar():
    """Os links guardados, que saem do arquivo."""
    caminho = _arquivo()
    try:
        with open(caminho, encoding="utf-8") as f:
            linhas = [l.strip() for l in f if l.strip()]
        os.remove(caminho)
    except OSError:
        return []
    return linhas[-MAXIMO:]

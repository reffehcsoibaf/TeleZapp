# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Conserto do libmagic (reconhece o tipo dos arquivos que o neonize envia).

O libmagic abre o banco `magic.mgc` com o caminho em ANSI: se o programa
estiver numa pasta com letra acentuada (como "Aribé" no nome do usuário), nao acha
o banco e todo envio de voz, documento ou midia falha com "could not find any
valid magic files". Aqui o caminho passa a ser um sem acento: o curto (8.3)
do Windows ou, se nao houver, uma copia do banco numa pasta publica."""
import ctypes
import logging
import os
import shutil

log = logging.getLogger("telezapp.midia")


def _caminho_curto(caminho):
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = ctypes.windll.kernel32.GetShortPathNameW(caminho, buf, 1024)
        return buf.value if 0 < n < 1024 else ""
    except (AttributeError, OSError):
        return ""


def _copia_sem_acento(caminho):
    for base in (os.environ.get("PUBLIC"), os.environ.get("ProgramData")):
        if not base or not base.isascii():
            continue
        pasta = os.path.join(base, "TeleZapp")
        destino = os.path.join(pasta, "magic.mgc")
        try:
            os.makedirs(pasta, exist_ok=True)
            if not os.path.isfile(destino) or \
                    os.path.getsize(destino) != os.path.getsize(caminho):
                shutil.copyfile(caminho, destino)
            return destino
        except OSError:
            continue
    return ""


def consertar_caminho_do_magic():
    """True se o caminho do banco foi trocado por um sem acento."""
    try:
        from magic import magic as mg
    except Exception:
        return False
    caminho = getattr(mg, "default_magic_file", None)
    if not caminho or caminho.isascii() or not os.path.isfile(caminho):
        return False
    novo = _caminho_curto(caminho)
    if not novo.isascii() or not novo:
        novo = _copia_sem_acento(caminho)
    if not novo:
        log.warning("o banco do libmagic está num caminho com acento e não "
                    "achei como contornar")
        return False
    mg.default_magic_file = novo
    getattr(mg, "_instances", {}).clear()
    log.info("libmagic: banco de tipos de arquivo em caminho sem acento")
    return True

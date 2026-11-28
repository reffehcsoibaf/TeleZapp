# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Os navegadores instalados no Windows, para escolher por onde abrir um link.

A lista vem do registro (a mesma de Aplicativos padrao do Windows):
HKLM e HKCU, SOFTWARE\\Clients\\StartMenuInternet."""
import logging
import os
import subprocess

log = logging.getLogger(__name__)

CHAVE = r"SOFTWARE\Clients\StartMenuInternet"


def _exe_do_comando(comando):
    """Caminho do programa dentro de um comando do registro, com ou sem
    aspas e com ou sem argumentos."""
    comando = (comando or "").strip()
    if comando.startswith('"'):
        fim = comando.find('"', 1)
        return comando[1:fim] if fim > 0 else comando[1:]
    pos = comando.lower().find(".exe")
    return comando[:pos + 4] if pos >= 0 else comando


def listar():
    """[(nome, caminho do programa)], sem repetir, em ordem alfabetica."""
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    achados = {}
    for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            base = winreg.OpenKey(raiz, CHAVE)
        except OSError:
            continue
        with base:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(base, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(base, sub) as k:
                        nome = winreg.QueryValueEx(k, "")[0] or sub
                    with winreg.OpenKey(
                            base, sub + r"\shell\open\command") as k:
                        comando = winreg.QueryValueEx(k, "")[0]
                except OSError:
                    continue
                exe = _exe_do_comando(comando)
                if exe and os.path.isfile(exe):
                    achados.setdefault(os.path.normcase(exe), (nome, exe))
    return sorted(achados.values(), key=lambda x: x[0].lower())


def abrir(exe, url):
    """Abre o endereco no navegador `exe`. True se o programa foi iniciado."""
    try:
        subprocess.Popen([exe, url], close_fds=True)
        return True
    except Exception:
        log.exception("não consegui abrir o link em %s", exe)
        return False

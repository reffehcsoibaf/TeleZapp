# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""O que muda de um sistema para outro: abrir arquivos e pastas, pasta de
dados e o nome do sistema para as mensagens. O resto do programa pergunta
aqui em vez de olhar `os.name` ou `sys.platform` por conta propria."""
import os
import subprocess
import sys

WINDOWS = sys.platform == "win32"
MAC = sys.platform == "darwin"


def nome_do_sistema():
    """Como o programa chama o sistema nas frases ("no Windows")."""
    return "Mac" if MAC else "Windows"


def abrir(caminho):
    """Abre um arquivo ou um endereco com o programa padrao do sistema.
    Levanta OSError se nao houver como."""
    if WINDOWS:
        os.startfile(caminho)
        return
    if MAC:
        subprocess.Popen(["open", caminho])
        return
    subprocess.Popen(["xdg-open", caminho])


def mostrar_na_pasta(caminho):
    """Abre a pasta do arquivo, com ele selecionado quando o sistema sabe."""
    if WINDOWS:
        subprocess.Popen(["explorer", "/select,", os.path.normpath(caminho)])
    elif MAC:
        subprocess.Popen(["open", "-R", caminho])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(caminho) or "."])


def abrir_pasta(pasta):
    """Abre a pasta no Explorador (Windows) ou no Finder (Mac)."""
    if WINDOWS:
        subprocess.Popen(["explorer", pasta])
    elif MAC:
        subprocess.Popen(["open", pasta])
    else:
        subprocess.Popen(["xdg-open", pasta])


def pasta_base_dos_dados():
    """A pasta onde fica a pasta de dados do programa."""
    if MAC:
        return os.path.join(os.path.expanduser("~"), "Library",
                            "Application Support")
    return os.environ.get("APPDATA") or os.path.expanduser("~")


def nome_do_usuario():
    """O nome do usuario do sistema, para nomes de travas e sinais."""
    return (os.environ.get("USERNAME") or os.environ.get("USER") or "")

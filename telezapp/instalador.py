# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Instalador de um arquivo so (TeleZapp.exe das Releases): abre a tela de
boas-vindas com Instalar, Criar copia portatil, Guia de uso e Fechar. O
programa vem dentro dele, como TeleZapp.zip; instalar ou criar a copia
portatil extrai esse zip e usa a mesma logica do programa. Ao terminar, o
instalador nao deixa nada para tras.

Gerado por ferramentas/empacotar.py. Pela linha de comando, `--pacote
<zip>` usa outro zip (testes)."""
import os
import shutil
import sys
import tempfile
import traceback

ARQUIVO = "TeleZapp.zip"


def caminho_do_pacote(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--pacote" in argv and argv.index("--pacote") + 1 < len(argv):
        return argv[argv.index("--pacote") + 1]
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(
        os.path.abspath(__file__))
    return os.path.join(base, ARQUIVO)


def main():
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    try:
        import wx
        from telezapp.interface.instalacao import mostrar_boas_vindas
        from telezapp.nucleo import instalacao as ins
        app = wx.App(False)
        pacote = caminho_do_pacote()
        if not os.path.isfile(pacote):
            wx.MessageBox("Este instalador está incompleto: o pacote do "
                          "programa não foi encontrado. Baixe de novo.",
                          "TeleZapp", wx.OK | wx.ICON_ERROR)
            return 1
        guia = tempfile.mkdtemp(prefix="telezapp-guia-")
        try:
            mostrar_boas_vindas(
                lambda progresso=None: ins.extrair_pacote(pacote, progresso),
                guia)
        finally:
            shutil.rmtree(guia, ignore_errors=True)
        del app
        return 0
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, "Erro no instalador do TeleZapp:\n" +
                traceback.format_exc(), "TeleZapp", 0x10)
        except Exception:
            pass
        return 1

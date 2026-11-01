# -*- mode: python ; coding: utf-8 -*-
# O instalador de um arquivo so (TeleZapp.exe das Releases), com o
# TeleZapp.zip dentro. Gerado por ferramentas/empacotar.py, que passa o zip
# em TELEZAPP_PACOTE.
import os

RAIZ = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
PACOTE = os.environ["TELEZAPP_PACOTE"]

a = Analysis(
    [os.path.join(SPECPATH, "instalar.py")],
    pathex=[RAIZ], binaries=[],
    datas=[(PACOTE, "."),
           (os.path.join(RAIZ, "telezapp", "ajuda"), "telezapp/ajuda"),
           (os.path.join(RAIZ, "telezapp", "imagens"), "telezapp/imagens")],
    hiddenimports=["telezapp.instalador", "telezapp.interface.instalacao",
                   "telezapp.interface.backup", "telezapp.interface.guia",
                   "telezapp.nucleo.instalacao",
                   "telezapp.nucleo.atualizador", "telezapp.nucleo.paginas",
                   "telezapp.nucleo.copia_oficial",
                   "telezapp.nucleo.backup", "pyzipper"],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["telethon", "neonize", "cv2", "numpy", "soundfile", "sounddevice",
              "PIL", "emoji", "tkinter"],
    noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="TeleZapp",
          debug=False, bootloader_ignore_signals=False, strip=False,
          upx=False, runtime_tmpdir=None, console=False,
          disable_windowed_traceback=False,
          icon=os.path.join(RAIZ, "telezapp", "imagens", "telezapp.ico"),
          version=os.environ.get("TELEZAPP_VERSAO"))

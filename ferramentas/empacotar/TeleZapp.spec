# -*- mode: python ; coding: utf-8 -*-
# O programa (pasta com TeleZapp.exe). Gerado por ferramentas/empacotar.py.
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

RAIZ = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

datas = [(os.path.join(RAIZ, "telezapp", "ajuda"), "telezapp/ajuda"),
         (os.path.join(RAIZ, "telezapp", "sons"), "telezapp/sons")]
binaries = []
hiddenimports = []
hiddenimports += collect_submodules("telethon")
hiddenimports += collect_submodules("hachoir")
hiddenimports += collect_submodules("telezapp")
for pacote in ("neonize", "magic", "pyzipper", "accessible_output2", "cv2",
               "emoji", "av"):
    d, b, h = collect_all(pacote)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += collect_submodules(
    "Cryptodome", filter=lambda n: "SelfTest" not in n)

a = Analysis(
    [os.path.join(SPECPATH, "iniciar.py")],
    pathex=[RAIZ], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports, hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TeleZapp",
          debug=False, bootloader_ignore_signals=False, strip=False,
          upx=False, console=False, disable_windowed_traceback=False,
          version=os.environ.get("TELEZAPP_VERSAO"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               upx_exclude=[], name="TeleZapp")

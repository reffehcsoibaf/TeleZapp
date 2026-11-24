# -*- mode: python ; coding: utf-8 -*-
# O TeleZapp.app do Mac. Gerado pelo GitHub Actions (testes-macos.yml).
# Sem assinatura da Apple: o app leva so a assinatura "ad hoc" que o Mac
# exige para abrir; na primeira vez a pessoa abre com o botao direito.
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

RAIZ = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
VERSAO = os.environ.get("TELEZAPP_VERSAO", "0.0.0")

datas = [(os.path.join(RAIZ, "telezapp", "ajuda"), "telezapp/ajuda"),
         (os.path.join(RAIZ, "telezapp", "sons"), "telezapp/sons"),
         (os.path.join(RAIZ, "telezapp", "imagens"), "telezapp/imagens")]
ICONE = os.path.join(RAIZ, "build-mac", "telezapp.icns")
if not os.path.isfile(ICONE):
    ICONE = None
binaries = []
hiddenimports = []
hiddenimports += collect_submodules("telethon")
hiddenimports += collect_submodules("hachoir")
hiddenimports += collect_submodules("telezapp")
for pacote in ("neonize", "magic", "pyzipper", "cv2", "emoji", "av",
               "livekit", "truststore", "keyring"):
    d, b, h = collect_all(pacote)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += collect_submodules(
    "Cryptodome", filter=lambda n: "SelfTest" not in n)
# VoiceOver (anuncios), Chaveiro e janela de robos (WKWebView)
hiddenimports += ["AppKit", "Foundation", "objc", "PyObjCTools.AppHelper",
                  "keyring.backends.macOS", "wx.html2"]

a = Analysis(
    [os.path.join(SPECPATH, "iniciar.py")],
    pathex=[RAIZ], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports, hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TeleZapp",
          debug=False, bootloader_ignore_signals=False, strip=False,
          upx=False, console=False, disable_windowed_traceback=False,
          argv_emulation=False, target_arch=None, codesign_identity="-",
          entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               upx_exclude=[], name="TeleZapp")
app = BUNDLE(
    coll, name="TeleZapp.app", icon=ICONE,
    bundle_identifier="com.fabioscheffer.telezapp",
    version=VERSAO,
    info_plist={
        "CFBundleName": "TeleZapp",
        "CFBundleDisplayName": "TeleZapp",
        "CFBundleShortVersionString": VERSAO,
        "CFBundleVersion": VERSAO,
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription":
            "O TeleZapp usa o microfone para gravar mensagens de voz e "
            "para as chamadas.",
        "NSCameraUsageDescription":
            "O TeleZapp usa a câmera para fotos, vídeos e chamadas de vídeo.",
        "NSContactsUsageDescription":
            "O TeleZapp pode mostrar os nomes dos seus contatos.",
        "NSAppleEventsUsageDescription":
            "O TeleZapp precisa mostrar avisos do sistema.",
        "CFBundleURLTypes": [
            {"CFBundleURLName": "Link do Telegram",
             "CFBundleURLSchemes": ["tg"]},
            {"CFBundleURLName": "Link do WhatsApp",
             "CFBundleURLSchemes": ["whatsapp"]},
        ],
    })

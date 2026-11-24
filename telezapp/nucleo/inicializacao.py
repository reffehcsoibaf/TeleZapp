# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Abrir o TeleZapp ao entrar no Windows: um valor na chave Run do usuario
(HKCU), sem precisar de administrador. O programa aberto assim recebe
--segundo-plano e, se a opcao de continuar em segundo plano estiver ligada,
fica na bandeja em vez de abrir a janela."""
import os
import subprocess
import sys

from telezapp.nucleo import instalacao

CHAVE = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALOR = "TeleZapp"
ARGUMENTO = "--segundo-plano"


def comando():
    """A linha que o Windows executa ao entrar na conta."""
    programa = instalacao.pasta_do_programa()
    if programa:
        exe = os.path.join(programa, instalacao.EXE)
        return subprocess.list2cmdline([exe, ARGUMENTO])
    # pelo codigo-fonte: o iniciar-telezapp.bat cuida do ambiente, e o
    # Windows abre o login fora da pasta do projeto
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    bat = os.path.join(raiz, "iniciar-telezapp.bat")
    return 'cmd.exe /c "cd /d "%s" && "%s" %s"' % (raiz, bat, ARGUMENTO)


def _winreg():
    if sys.platform != "win32":
        return None
    import winreg
    return winreg


ROTULO_MAC = "com.telezapp.abrir-ao-entrar"


def _plist_mac():
    return os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents",
                        ROTULO_MAC + ".plist")


def _argumentos_mac():
    """O que o Mac executa ao entrar: o proprio aplicativo (ou o Python com
    o codigo, fora do pacote .app)."""
    if getattr(sys, "frozen", False):
        return [os.path.abspath(sys.executable), ARGUMENTO]
    return [sys.executable, "-m", "telezapp", ARGUMENTO]


def _gravar_plist_mac():
    import plistlib
    destino = _plist_mac()
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "wb") as f:
        plistlib.dump({"Label": ROTULO_MAC,
                       "ProgramArguments": _argumentos_mac(),
                       "RunAtLoad": True}, f)


def ativado(chave=CHAVE):
    """True se ha uma entrada do TeleZapp na inicializacao."""
    if sys.platform == "darwin":
        return os.path.isfile(_plist_mac())
    reg = _winreg()
    if reg is None:
        return False
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, chave) as k:
            reg.QueryValueEx(k, VALOR)
            return True
    except OSError:
        return False


def definir(ligado, chave=CHAVE, linha=None):
    """Liga ou desliga. Devolve False se o sistema recusou."""
    if sys.platform == "darwin":
        try:
            if ligado:
                _gravar_plist_mac()
            else:
                try:
                    os.remove(_plist_mac())
                except FileNotFoundError:
                    pass
            return True
        except OSError:
            return False
    reg = _winreg()
    if reg is None:
        return False
    try:
        if ligado:
            with reg.CreateKeyEx(reg.HKEY_CURRENT_USER, chave, 0,
                                 reg.KEY_SET_VALUE) as k:
                reg.SetValueEx(k, VALOR, 0, reg.REG_SZ, linha or comando())
        else:
            try:
                with reg.OpenKey(reg.HKEY_CURRENT_USER, chave, 0,
                                 reg.KEY_SET_VALUE) as k:
                    reg.DeleteValue(k, VALOR)
            except FileNotFoundError:
                pass
        return True
    except OSError:
        return False


def linha_atual(chave=CHAVE):
    if sys.platform == "darwin":
        if not ativado():
            return ""
        return subprocess.list2cmdline(_argumentos_mac())
    reg = _winreg()
    if reg is None:
        return ""
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, chave) as k:
            return reg.QueryValueEx(k, VALOR)[0]
    except OSError:
        return ""

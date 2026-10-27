# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Uma segunda abertura do programa avisa a primeira, que pode estar
escondida na bandeja, para mostrar a janela. O aviso e um evento nomeado do
Windows (por usuario); sem Windows, nada acontece."""
import ctypes
import os
import sys

SINCRONIZAR = 0x00100000
EVENT_MODIFY_STATE = 0x0002
ESPERA_OK = 0


def _nome(sufixo=""):
    return "TeleZapp-mostrar-%s%s" % (os.environ.get("USERNAME", ""), sufixo)


def _k32():
    k = ctypes.windll.kernel32
    k.CreateEventW.restype = ctypes.c_void_p
    k.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                               ctypes.c_wchar_p]
    k.OpenEventW.restype = ctypes.c_void_p
    k.OpenEventW.argtypes = [ctypes.c_uint32, ctypes.c_int,
                             ctypes.c_wchar_p]
    k.SetEvent.argtypes = [ctypes.c_void_p]
    k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    return k


def criar_sinal(sufixo=""):
    """O evento que a primeira abertura espera (None fora do Windows)."""
    if sys.platform != "win32":
        return None
    return _k32().CreateEventW(None, 0, 0, _nome(sufixo)) or None


def esperar(sinal, milissegundos=500):
    """True se alguem acionou o sinal nesse tempo."""
    if not sinal:
        return False
    return _k32().WaitForSingleObject(sinal, milissegundos) == ESPERA_OK


def acionar(sufixo=""):
    """Avisa a abertura que ja esta rodando; False se nao houver nenhuma."""
    if sys.platform != "win32":
        return False
    k = _k32()
    h = k.OpenEventW(SINCRONIZAR | EVENT_MODIFY_STATE, 0, _nome(sufixo))
    if not h:
        return False
    try:
        return bool(k.SetEvent(h))
    finally:
        k.CloseHandle(h)


def fechar(sinal):
    if sinal:
        _k32().CloseHandle(sinal)

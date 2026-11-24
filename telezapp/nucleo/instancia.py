# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Uma segunda abertura do programa avisa a primeira, que pode estar
escondida na bandeja, para mostrar a janela. O aviso e um evento nomeado do
Windows (por usuario). No Mac o aviso e um arquivo pequeno na pasta de dados
que a primeira abertura vigia."""
import ctypes
import os
import sys
import time

SINCRONIZAR = 0x00100000
EVENT_MODIFY_STATE = 0x0002
ESPERA_OK = 0


def _nome(sufixo=""):
    from telezapp.nucleo import plataforma
    return "TeleZapp-mostrar-%s%s" % (plataforma.nome_do_usuario(), sufixo)


def _arquivo_do_sinal(sufixo=""):
    from telezapp import config
    return os.path.join(config.pasta(), "mostrar%s.sinal" % sufixo)


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
    if sys.platform == "darwin":
        caminho = _arquivo_do_sinal(sufixo)
        try:
            os.remove(caminho)          # sobra de uma abertura anterior
        except OSError:
            pass
        return caminho
    if sys.platform != "win32":
        return None
    return _k32().CreateEventW(None, 0, 0, _nome(sufixo)) or None


def esperar(sinal, milissegundos=500):
    """True se alguem acionou o sinal nesse tempo."""
    if not sinal:
        return False
    if isinstance(sinal, str):          # Mac: arquivo-sinal
        fim = time.monotonic() + milissegundos / 1000.0
        while True:
            if os.path.exists(sinal):
                try:
                    os.remove(sinal)
                except OSError:
                    pass
                return True
            if time.monotonic() >= fim:
                return False
            time.sleep(0.1)
    return _k32().WaitForSingleObject(sinal, milissegundos) == ESPERA_OK


def acionar(sufixo=""):
    """Avisa a abertura que ja esta rodando; False se nao houver nenhuma."""
    if sys.platform == "darwin":
        try:
            with open(_arquivo_do_sinal(sufixo), "w") as f:
                f.write(str(os.getpid()))
            return True
        except OSError:
            return False
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
    if isinstance(sinal, str):
        return
    if sinal:
        _k32().CloseHandle(sinal)

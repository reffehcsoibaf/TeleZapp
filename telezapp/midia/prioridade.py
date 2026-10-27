# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Mantem o som da chamada correndo com o TeleZapp em segundo plano.

Com a janela minimizada, escondida ou em outro programa em primeiro plano, o
Windows trata o processo como "de fundo": pode jogar as threads no modo de
eficiencia (EcoQoS), ignorar o relogio de alta resolucao e ate suspender o
computador por inatividade. Para a chamada isso quer dizer quadros de som
atrasados ou perdidos, e as pessoas deixam de se ouvir. Durante a chamada:

- `chamada_em_curso(True)` desliga o modo de eficiencia do processo, pede o
  relogio de 1 ms e impede o Windows de suspender o computador;
- `thread_de_audio()` poe a thread que lê ou toca o som no grupo "Audio" do
  Windows (MMCSS), que o sistema atende antes das outras.

Tudo e melhor esforco: se uma chamada ao Windows falhar, so fica no log. Fora
do Windows nao faz nada.
"""
import ctypes
import logging
import sys
import threading

log = logging.getLogger("telezapp.prioridade")

_WINDOWS = sys.platform == "win32"

# SetProcessInformation(ProcessPowerThrottling)
_PROCESSO_POWER_THROTTLING = 4
_VERSAO_POWER_THROTTLING = 1
_EXECUCAO_RAPIDA = 0x1
_IGNORAR_RESOLUCAO_DO_RELOGIO = 0x4
# SetThreadExecutionState
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001

_trava = threading.Lock()
_ativa = [False]


class _EstadoDeEnergia(ctypes.Structure):
    _fields_ = [("Version", ctypes.c_ulong), ("ControlMask", ctypes.c_ulong),
                ("StateMask", ctypes.c_ulong)]


def _energia_do_processo(sem_economia):
    """True: o processo nao entra no modo de eficiencia nem perde o relogio
    fino. False: volta a deixar o Windows decidir."""
    estado = _EstadoDeEnergia(
        _VERSAO_POWER_THROTTLING,
        (_EXECUCAO_RAPIDA | _IGNORAR_RESOLUCAO_DO_RELOGIO)
        if sem_economia else 0, 0)
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    k32.SetProcessInformation.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong]
    ok = k32.SetProcessInformation(
        k32.GetCurrentProcess(), _PROCESSO_POWER_THROTTLING,
        ctypes.byref(estado), ctypes.sizeof(estado))
    if not ok:
        log.info("o Windows não aceitou mudar o modo de energia (%d)",
                 ctypes.get_last_error() or ctypes.GetLastError())


def chamada_em_curso(ligado):
    """Liga ou desliga o modo "chamada": vale para o processo todo. Pode ser
    chamada varias vezes seguidas com o mesmo valor."""
    if not _WINDOWS:
        return
    with _trava:
        if _ativa[0] == bool(ligado):
            return
        _ativa[0] = bool(ligado)
    try:
        _energia_do_processo(bool(ligado))
        winmm = ctypes.windll.winmm
        (winmm.timeBeginPeriod if ligado else winmm.timeEndPeriod)(1)
        ctypes.windll.kernel32.SetThreadExecutionState(
            (_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED) if ligado
            else _ES_CONTINUOUS)
        log.info("modo chamada %s", "ligado" if ligado else "desligado")
    except Exception:
        log.exception("erro ao ajustar a energia para a chamada")


def esta_ativa():
    return _ativa[0]


def thread_de_audio():
    """Chamada de dentro da thread de som: pede ao Windows para atende-la
    como som em tempo real. Devolve o identificador a passar a
    `soltar_thread` ao terminar (0 se nao deu)."""
    if not _WINDOWS:
        return 0
    try:
        av = ctypes.windll.avrt
        av.AvSetMmThreadCharacteristicsW.restype = ctypes.c_void_p
        indice = ctypes.c_ulong(0)
        ident = av.AvSetMmThreadCharacteristicsW("Audio",
                                                 ctypes.byref(indice))
        return ident or 0
    except Exception:
        log.info("não foi possível pôr a thread de som em tempo real")
        return 0


def soltar_thread(ident):
    if not _WINDOWS or not ident:
        return
    try:
        ctypes.windll.avrt.AvRevertMmThreadCharacteristics(
            ctypes.c_void_p(ident))
    except Exception:
        pass

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela em segundo plano que fica na barra de tarefas mas some do Alt+Tab.

No Windows, o Alt+Tab e o botao da barra de tarefas usam o mesmo criterio
(janela comum, sem o estilo de janela de ferramenta). Aqui a janela ganha o
estilo de ferramenta, que a tira do Alt+Tab, e o botao da barra de tarefas e
pedido a parte (ITaskbarList.AddTab). Se algo falhar, a janela volta ao
normal: melhor aparecer no Alt+Tab do que sumir da barra de tarefas.
"""
import ctypes
import logging
import sys

log = logging.getLogger("telezapp.segundo_plano")

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SW_HIDE = 0
SW_SHOWMINNOACTIVE = 7
CLSID_TASKBARLIST = "56FDF344-FD6D-11D0-958A-006097C9A090"
IID_ITASKBARLIST = "56FDF342-FD6D-11D0-958A-006097C9A090"


def estilo_fora_do_alttab(estilo):
    """O estilo estendido sem APPWINDOW e com TOOLWINDOW."""
    return (estilo | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW


def estilo_normal(estilo):
    """Tira o TOOLWINDOW (volta a aparecer no Alt+Tab)."""
    return estilo & ~WS_EX_TOOLWINDOW


def _guid(texto):
    import uuid
    return (ctypes.c_byte * 16)(*uuid.UUID(texto).bytes_le)


def _adicionar_botao(hwnd):
    """Pede ao shell o botao da barra de tarefas para a janela. True se o
    shell aceitou."""
    ole = ctypes.windll.ole32
    ole.CoInitialize(None)
    objeto = ctypes.c_void_p()
    hr = ole.CoCreateInstance(_guid(CLSID_TASKBARLIST), None, 1,
                              _guid(IID_ITASKBARLIST), ctypes.byref(objeto))
    if hr != 0 or not objeto:
        return False
    tabela = ctypes.cast(ctypes.cast(objeto, ctypes.POINTER(ctypes.c_void_p))[0],
                         ctypes.POINTER(ctypes.c_void_p))
    hr_init = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(tabela[3])
    add_tab = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                                 ctypes.c_void_p)(tabela[4])
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(tabela[2])
    try:
        return hr_init(objeto) == 0 and add_tab(objeto, hwnd) == 0
    finally:
        release(objeto)


def _mudar_estilo(hwnd, funcao):
    """Troca o estilo estendido com a janela escondida e a mostra de novo
    minimizada e sem ativar, para o shell reler o estilo."""
    u = ctypes.windll.user32
    u.ShowWindow(hwnd, SW_HIDE)
    u.SetWindowLongW(hwnd, GWL_EXSTYLE, funcao(u.GetWindowLongW(
        hwnd, GWL_EXSTYLE)))
    u.ShowWindow(hwnd, SW_SHOWMINNOACTIVE)


def tirar_do_alttab(hwnd):
    """Minimiza a janela, tira-a do Alt+Tab e mantem o botao da barra de
    tarefas. False (e nada muda) se nao for Windows ou se o shell recusar."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        _mudar_estilo(hwnd, estilo_fora_do_alttab)
        if _adicionar_botao(hwnd):
            return True
        log.warning("o shell nao aceitou o botao da barra de tarefas")
    except Exception:
        log.exception("tirar a janela do Alt+Tab")
    try:
        _mudar_estilo(hwnd, estilo_normal)
    except Exception:
        log.exception("desfazer o estilo da janela")
    return False


def voltar_ao_alttab(hwnd):
    """Desfaz tirar_do_alttab: a janela volta a aparecer no Alt+Tab."""
    if sys.platform != "win32" or not hwnd:
        return
    try:
        u = ctypes.windll.user32
        u.SetWindowLongW(hwnd, GWL_EXSTYLE, estilo_normal(
            u.GetWindowLongW(hwnd, GWL_EXSTYLE)))
    except Exception:
        log.exception("devolver a janela ao Alt+Tab")

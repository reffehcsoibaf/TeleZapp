# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Som de limite de lista: seta para cima no primeiro item ou seta para
baixo no ultimo, em qualquer lista do programa (janela principal e todas as
janelas de dialogo). Um filtro de eventos do wx olha as teclas antes de
chegarem ao controle, entao nenhuma janela precisa cuidar disso; a tecla
segue o caminho normal."""
import logging

import wx

from telezapp.acessibilidade import fala

log = logging.getLogger("telezapp.limite_de_lista")
_filtro = None


def posicao(ctrl):
    """(quantos itens, indice do item atual) se `ctrl` e uma lista (ListBox,
    CheckListBox, ListCtrl, lista visual, Choice, RadioBox); senao None."""
    if hasattr(ctrl, "GetCount") and hasattr(ctrl, "GetSelection"):
        n, i = ctrl.GetCount(), ctrl.GetSelection()
    elif hasattr(ctrl, "GetItemCount") and hasattr(ctrl, "GetFocusedItem"):
        n, i = ctrl.GetItemCount(), ctrl.GetFocusedItem()
    else:
        return None
    if not isinstance(n, int) or not isinstance(i, int):
        return None          # arvores e afins devolvem outra coisa
    return n, i


def no_limite(ctrl, tecla, shift=False, ctrl_ou_alt=False):
    """A tecla (cima ou baixo) bate no comeco ou no fim da lista?"""
    if tecla not in (wx.WXK_UP, wx.WXK_DOWN) or shift or ctrl_ou_alt:
        return False
    p = posicao(ctrl)
    if p is None or p[0] == 0:
        return False
    n, i = p
    return (tecla == wx.WXK_UP and i == 0) or \
        (tecla == wx.WXK_DOWN and i == n - 1)


def tocar_se_no_limite(evt):
    """Para o EVT_KEY_DOWN de qualquer controle; nunca consome a tecla."""
    try:
        if no_limite(evt.GetEventObject(), evt.GetKeyCode(),
                     evt.ShiftDown(), evt.ControlDown() or evt.AltDown()):
            fala.bipe("limite_da_lista")
    except Exception:
        log.debug("som de limite de lista falhou", exc_info=True)


def instalar():
    """Liga o som em todas as janelas do programa (uma vez, depois de criar
    o wx.App)."""
    global _filtro
    if _filtro is not None:
        return _filtro

    class Filtro(wx.EventFilter):
        def __init__(self):
            super().__init__()
            wx.EvtHandler.AddFilter(self)

        def FilterEvent(self, evt):
            if evt.GetEventType() == wx.wxEVT_KEY_DOWN:
                tocar_se_no_limite(evt)
            return wx.EventFilter.Event_Skip
    _filtro = Filtro()
    return _filtro

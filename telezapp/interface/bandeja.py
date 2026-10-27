# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Icone do TeleZapp na area de notificacao do Windows: com a janela
escondida o programa segue conectado e dando os avisos. Clique no icone
mostra a janela; o menu do icone tem Abrir e Sair."""
import wx

try:
    import wx.adv as _adv
except Exception:                      # sem wx.adv: sem bandeja
    _adv = None

NOME_DO_ICONE = "TeleZapp"


def _icone():
    """Um quadrado verde com um T branco, desenhado na hora (o programa nao
    traz arquivo de icone)."""
    bmp = wx.Bitmap(32, 32)
    dc = wx.MemoryDC(bmp)
    dc.SetBackground(wx.Brush(wx.Colour(37, 160, 90)))
    dc.Clear()
    dc.SetPen(wx.Pen(wx.WHITE, 4))
    dc.DrawLine(8, 9, 24, 9)
    dc.DrawLine(16, 9, 16, 25)
    dc.SelectObject(wx.NullBitmap)
    icone = wx.Icon()
    icone.CopyFromBitmap(bmp)
    return icone


if _adv is not None:
    class Bandeja(_adv.TaskBarIcon):
        def __init__(self, janela):
            super().__init__()
            self.janela = janela
            self.SetIcon(_icone(), NOME_DO_ICONE)
            self.Bind(_adv.EVT_TASKBAR_LEFT_DCLICK,
                      lambda e: self.janela._mostrar_da_bandeja())
            self.Bind(_adv.EVT_TASKBAR_LEFT_UP,
                      lambda e: self.janela._mostrar_da_bandeja())

        def CreatePopupMenu(self):
            menu = wx.Menu()
            abrir = menu.Append(wx.ID_ANY, "&Abrir o TeleZapp")
            sair = menu.Append(wx.ID_ANY, "&Sair")
            menu.Bind(wx.EVT_MENU,
                      lambda e: self.janela._mostrar_da_bandeja(), abrir)
            menu.Bind(wx.EVT_MENU, lambda e: self.janela._sair(), sair)
            return menu


def criar(janela):
    """O icone da bandeja, ou None se o wx nao tiver como criar."""
    if _adv is None:
        return None
    try:
        return Bandeja(janela)
    except Exception:
        return None

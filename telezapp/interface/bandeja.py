# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Icone do TeleZapp na area de notificacao do Windows: com a janela
escondida o programa segue conectado e dando os avisos. Clique no icone
mostra a janela; o menu do icone tem Abrir e Sair."""
import os

import wx

try:
    import wx.adv as _adv
except Exception:                      # sem wx.adv: sem bandeja
    _adv = None

NOME_DO_ICONE = "TeleZapp"


ARQUIVO_DO_ICONE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "imagens", "telezapp.ico")


def icone_do_app():
    """O icone do TeleZapp (um teclado com fone de ouvido), do arquivo
    telezapp.ico; sem o arquivo, o quadrado verde com um T."""
    try:
        icone = wx.Icon(ARQUIVO_DO_ICONE, wx.BITMAP_TYPE_ICO)
        if icone.IsOk():
            return icone
    except Exception:
        pass
    return _icone()


def _icone():
    """Um quadrado verde com um T branco, desenhado na hora, para quando o
    arquivo de icone nao esta la."""
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
            self.SetIcon(icone_do_app(), NOME_DO_ICONE)
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

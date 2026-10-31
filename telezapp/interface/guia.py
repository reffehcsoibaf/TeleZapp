# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Guia de uso numa janela do programa, sem navegador: a lista de assuntos e o
texto do assunto escolhido."""
import wx

from telezapp import NOME
from telezapp.nucleo import paginas


class DialogoGuia(wx.Dialog):
    def __init__(self, pai):
        super().__init__(pai, title="Guia de uso do %s" % NOME,
                         size=(820, 560),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.assuntos = paginas.ler_assuntos()
        self.lista = wx.ListBox(self, name="Assuntos",
                                choices=[t for t, _ in self.assuntos])
        self.texto = wx.TextCtrl(self, name="Texto",
                                 style=wx.TE_MULTILINE | wx.TE_READONLY)
        fechar = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        lado_a = wx.BoxSizer(wx.VERTICAL)
        lado_a.Add(wx.StaticText(self, label="Assuntos"), 0, wx.BOTTOM, 4)
        lado_a.Add(self.lista, 1, wx.EXPAND)
        lado_b = wx.BoxSizer(wx.VERTICAL)
        lado_b.Add(wx.StaticText(self, label="Texto"), 0, wx.BOTTOM, 4)
        lado_b.Add(self.texto, 1, wx.EXPAND)
        meio = wx.BoxSizer(wx.HORIZONTAL)
        meio.Add(lado_a, 1, wx.EXPAND | wx.RIGHT, 8)
        meio.Add(lado_b, 2, wx.EXPAND)
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(meio, 1, wx.EXPAND | wx.ALL, 8)
        lay.Add(fechar, 0, wx.ALL | wx.ALIGN_RIGHT, 8)
        self.SetSizer(lay)
        self.Layout()
        self.lista.Bind(wx.EVT_LISTBOX, lambda e: self._mostrar())
        # Enter no assunto leva direto ao texto dele
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.texto.SetFocus())
        self.lista.Bind(wx.EVT_KEY_DOWN, self._tecla)
        if self.assuntos:
            self.lista.SetSelection(0)
            self._mostrar()
        self.lista.SetFocus()
        self.CentreOnParent()

    def _tecla(self, evt):
        if evt.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.texto.SetFocus()
        else:
            evt.Skip()

    def _mostrar(self):
        n = self.lista.GetSelection()
        if 0 <= n < len(self.assuntos):
            self.texto.SetValue(self.assuntos[n][1])
            self.texto.SetInsertionPoint(0)


def mostrar_guia(pai):
    dlg = DialogoGuia(pai)
    try:
        dlg.ShowModal()
    finally:
        dlg.Destroy()

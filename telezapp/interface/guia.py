# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Guia de uso numa janela do programa, sem navegador: a caixa de pesquisa, a
lista de assuntos e o texto do assunto escolhido."""
import wx

from telezapp import NOME
from telezapp.nucleo import paginas


class DialogoGuia(wx.Dialog):
    def __init__(self, pai):
        super().__init__(pai, title="Guia de uso do %s" % NOME,
                         size=(820, 560),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.assuntos = paginas.ler_assuntos()
        self.mostrados = list(range(len(self.assuntos)))   # posicoes na lista
        # o rotulo vem ANTES do campo (a ordem que o leitor de tela segue)
        rot_busca = wx.StaticText(self, label="&Pesquisar no guia:")
        self.busca = wx.TextCtrl(self, name="Pesquisar no guia",
                                 style=wx.TE_PROCESS_ENTER)
        self.rot_lista = wx.StaticText(self, label="Assuntos")
        self.lista = wx.ListBox(self, name="Assuntos")
        self.texto = wx.TextCtrl(self, name="Texto",
                                 style=wx.TE_MULTILINE | wx.TE_READONLY)
        fechar = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        lado_a = wx.BoxSizer(wx.VERTICAL)
        lado_a.Add(self.rot_lista, 0, wx.BOTTOM, 4)
        lado_a.Add(self.lista, 1, wx.EXPAND)
        lado_b = wx.BoxSizer(wx.VERTICAL)
        lado_b.Add(wx.StaticText(self, label="Texto"), 0, wx.BOTTOM, 4)
        lado_b.Add(self.texto, 1, wx.EXPAND)
        meio = wx.BoxSizer(wx.HORIZONTAL)
        meio.Add(lado_a, 1, wx.EXPAND | wx.RIGHT, 8)
        meio.Add(lado_b, 2, wx.EXPAND)
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(rot_busca, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        lay.Add(self.busca, 0, wx.ALL | wx.EXPAND, 8)
        lay.Add(meio, 1, wx.EXPAND | wx.ALL, 8)
        lay.Add(fechar, 0, wx.ALL | wx.ALIGN_RIGHT, 8)
        self.SetSizer(lay)
        self.Layout()
        self.busca.Bind(wx.EVT_TEXT, lambda e: self._pesquisar())
        # Enter ou seta para baixo na pesquisa levam ao resultado
        self.busca.Bind(wx.EVT_TEXT_ENTER, lambda e: self._ir_ao_resultado())
        self.busca.Bind(wx.EVT_KEY_DOWN, self._tecla_da_busca)
        self.lista.Bind(wx.EVT_LISTBOX, lambda e: self._mostrar())
        # Enter no assunto leva direto ao texto dele
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.texto.SetFocus())
        self.lista.Bind(wx.EVT_KEY_DOWN, self._tecla)
        self._preencher()
        self.lista.SetFocus()
        self.CentreOnParent()

    # ------------------------------------------------------------ pesquisa
    def _pesquisar(self):
        """Mostra so os assuntos que tem todas as palavras da caixa."""
        antes = self._assunto_escolhido()
        self.mostrados = paginas.pesquisar(self.assuntos, self.busca.GetValue())
        self._preencher(manter=antes)

    def _preencher(self, manter=None):
        self.lista.Set([self.assuntos[n][0] for n in self.mostrados])
        total = len(self.assuntos)
        if len(self.mostrados) == total:
            self.rot_lista.SetLabel("Assuntos")
        elif self.mostrados:
            self.rot_lista.SetLabel("Assuntos (%d de %d)" % (
                len(self.mostrados), total))
        else:
            self.rot_lista.SetLabel("Assuntos (nenhum encontrado)")
        if self.mostrados:
            self.lista.SetSelection(
                self.mostrados.index(manter) if manter in self.mostrados
                else 0)
        self._mostrar()

    def _ir_ao_resultado(self):
        if self.mostrados:
            self.lista.SetFocus()

    def _tecla_da_busca(self, evt):
        if evt.GetKeyCode() == wx.WXK_DOWN and self.mostrados:
            self.lista.SetFocus()
        else:
            evt.Skip()

    # --------------------------------------------------------------- lista
    def _assunto_escolhido(self):
        n = self.lista.GetSelection()
        return self.mostrados[n] if 0 <= n < len(self.mostrados) else None

    def _tecla(self, evt):
        if evt.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.texto.SetFocus()
        else:
            evt.Skip()

    def _mostrar(self):
        n = self._assunto_escolhido()
        if n is None:
            self.texto.SetValue("")
            return
        texto = self.assuntos[n][1]
        self.texto.SetValue(texto)
        trecho = paginas.primeiro_trecho(texto, self.busca.GetValue())
        if trecho:
            # o cursor vai ao primeiro trecho achado, e o leitor de tela le
            # dali quando o foco chega ao texto
            self.texto.SetInsertionPoint(trecho[0])
            self.texto.ShowPosition(trecho[0])
        else:
            self.texto.SetInsertionPoint(0)


def mostrar_guia(pai):
    dlg = DialogoGuia(pai)
    try:
        dlg.ShowModal()
    finally:
        dlg.Destroy()

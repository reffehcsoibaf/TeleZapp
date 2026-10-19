# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Janela para escolher para quais conversas encaminhar."""
import wx

from telezapp.nucleo import encaminhar as enc


class DialogoEncaminhar(wx.Dialog):
    """Busca por nome e lista de conversas com caixa de marcar. As marcas
    sobrevivem a uma nova busca."""

    def __init__(self, pai, destinos, rotulo_de, resumo):
        """destinos: ver nucleo.encaminhar.destinos; rotulo_de(destino) ->
        texto da linha; resumo: o que esta sendo encaminhado."""
        super().__init__(pai, title="Encaminhar",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.todos, self.rotulo_de = destinos, rotulo_de
        self.marcados = set()               # (conta_id, conversa_id)
        self._mostrados = []
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(self, label="Encaminhar %s. Digite para buscar "
                                          "e marque com Espaço as conversas "
                                          "que vão receber." % resumo),
                0, wx.ALL, 10)
        lay.Add(wx.StaticText(self, label="Buscar conversa ou contato"), 0,
                wx.LEFT | wx.RIGHT, 10)
        self.busca = wx.TextCtrl(self, name="Buscar conversa ou contato")
        lay.Add(self.busca, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        lay.Add(wx.StaticText(self, label="Conversas (Espaço marca)"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.lista = wx.CheckListBox(self, name="Conversas",
                                     size=(460, 260))
        lay.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.contagem = wx.StaticText(self, label="Nenhuma marcada")
        lay.Add(self.contagem, 0, wx.ALL, 10)
        botoes = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        self.ok = self.FindWindowById(wx.ID_OK)
        self.ok.SetLabel("&Encaminhar")
        lay.Add(botoes, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.busca.Bind(wx.EVT_TEXT, lambda e: self._preencher())
        self.lista.Bind(wx.EVT_CHECKLISTBOX, self._ao_marcar)
        self.Bind(wx.EVT_BUTTON, self._ok, id=wx.ID_OK)
        self._preencher()
        self.CentreOnParent()
        self.busca.SetFocus()

    def _preencher(self):
        self._mostrados = enc.filtrar(self.todos, self.busca.GetValue())
        self.lista.Set([self.rotulo_de(d) for d in self._mostrados])
        for i, d in enumerate(self._mostrados):
            self.lista.Check(i, (d[0], d[1]) in self.marcados)
        if self._mostrados:
            self.lista.SetSelection(0)

    def _ao_marcar(self, evt):
        i = evt.GetInt()
        chave = (self._mostrados[i][0], self._mostrados[i][1])
        if self.lista.IsChecked(i):
            self.marcados.add(chave)
        else:
            self.marcados.discard(chave)
        n = len(self.marcados)
        self.contagem.SetLabel("Nenhuma marcada" if not n else
                               "1 marcada" if n == 1 else "%d marcadas" % n)

    def _ok(self, evt):
        if not self.marcados:
            wx.MessageBox("Marque pelo menos uma conversa.", "Encaminhar",
                          wx.OK | wx.ICON_WARNING, self)
            return
        evt.Skip()

    def escolhidos(self):
        """[(conta_id, conversa_id, nome, tipo)] marcados."""
        return [d for d in self.todos if (d[0], d[1]) in self.marcados]

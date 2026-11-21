# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela para pôr e tirar uma conversa das pastas do Telegram ou das listas
do WhatsApp: uma lista de caixas de marcar (marcada = a conversa está nela),
com o rótulo antes. Enter aplica, Esc cancela."""
import wx


class DialogoPastas(wx.Dialog):
    def __init__(self, pai, nome_da_conversa, itens, lista=False):
        """itens: [(id, nome, esta_na_pasta)]."""
        palavra = "listas" if lista else "pastas"
        super().__init__(pai, title="%s de %s" % (palavra.capitalize(),
                                                  nome_da_conversa),
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.itens = list(itens)
        rotulo = "Em quais %s a conversa fica (Espaço marca)" % palavra
        self.rotulo = wx.StaticText(self, label=rotulo + ":")
        self.lista = wx.CheckListBox(
            self, choices=[n or "Sem nome" for _i, n, _t in self.itens],
            name=rotulo, size=(380, 220))
        for k, (_i, _n, tem) in enumerate(self.itens):
            self.lista.Check(k, bool(tem))
        self.b_ok = wx.Button(self, wx.ID_OK, "&Aplicar")
        self.b_cancelar = wx.Button(self, wx.ID_CANCEL, "Cance&lar")
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(self.rotulo, 0, wx.ALL, 12)
        lay.Add(self.lista, 1, wx.LEFT | wx.RIGHT | wx.EXPAND, 12)
        linha = wx.BoxSizer(wx.HORIZONTAL)
        linha.Add(self.b_ok, 0, wx.RIGHT, 6)
        linha.Add(self.b_cancelar, 0)
        lay.Add(linha, 0, wx.ALL, 12)
        self.SetSizerAndFit(lay)
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        if self.itens:
            self.lista.SetSelection(0)
        self.lista.SetFocus()

    def mudancas(self):
        """[(id, nome, incluir)] só do que mudou em relação a antes."""
        marcadas = set(self.lista.GetCheckedItems())
        return [(i, n, k in marcadas)
                for k, (i, n, tem) in enumerate(self.itens)
                if (k in marcadas) != bool(tem)]

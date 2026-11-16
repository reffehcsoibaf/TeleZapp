# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Escolher quem convidar para a chamada em andamento (recurso experimental).

Uma lista de caixas de marcar, com o rotulo antes dela (a ordem real das
janelas do Windows, que o leitor de tela e o Tab seguem). Enter convida,
Esc cancela. Nao e modal para o resto do programa: e a janela da chamada ou
a principal que a abre.
"""
import wx


class DialogoConvidar(wx.Dialog):
    def __init__(self, pai, candidatos, quem_chama="a chamada"):
        """candidatos: [(endereco, nome)]."""
        super().__init__(pai, title="Adicionar participantes",
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.candidatos = list(candidatos)
        self.rotulo = wx.StaticText(
            self, label="Quem convidar para %s (Espaço marca):" % quem_chama)
        self.lista = wx.CheckListBox(
            self, choices=[n or "Participante" for _a, n in self.candidatos],
            name="Quem convidar")
        self.b_ok = wx.Button(self, wx.ID_OK, "&Convidar")
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
        if self.candidatos:
            self.lista.SetSelection(0)
        self.lista.SetFocus()

    def escolhidos(self):
        """[(endereco, nome)] das caixas marcadas."""
        return [self.candidatos[i] for i in self.lista.GetCheckedItems()]

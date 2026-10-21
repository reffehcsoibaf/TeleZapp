# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Janela de Gerenciar contas: uma lista em que cada conta tem uma caixa de
marcar (marcada = ativada, desmarcada = desativada), e, com a conta em foco,
os botões Excluir e Renomear (Tab). Quem muda as contas é a Janela; aqui só
fica a tela."""
import wx


class DialogoContas(wx.Dialog):
    """`itens()`: [(conta_id, rotulo, ativa)]. `ao_marcar(conta_id, ativa)`,
    `ao_excluir(conta_id)` e `ao_renomear(conta_id)` devolvem True se mudou
    algo (a lista é refeita)."""

    def __init__(self, pai, itens, ao_marcar, ao_excluir, ao_renomear):
        super().__init__(pai, title="Gerenciar contas",
                         style=wx.DEFAULT_DIALOG_STYLE)
        self._itens, self._ao_marcar = itens, ao_marcar
        self._ao_excluir, self._ao_renomear = ao_excluir, ao_renomear
        self._ids = []
        lay = wx.BoxSizer(wx.VERTICAL)
        rotulo = ("Contas. Espaço marca ou desmarca: marcada fica "
                  "conectada, desmarcada não conecta (as conversas "
                  "guardadas continuam na tela). Tab leva a Excluir e "
                  "Renomear.")
        explicacao = wx.StaticText(self, label=rotulo)
        explicacao.Wrap(440)
        lay.Add(explicacao, 0, wx.ALL, 10)
        self.lista = wx.CheckListBox(self, choices=[], name="Contas",
                                     size=(440, 160))
        lay.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        linha = wx.BoxSizer(wx.HORIZONTAL)
        self.excluir = wx.Button(self, label="&Excluir...")
        self.renomear = wx.Button(self, label="&Renomear...")
        fechar = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        for b in (self.excluir, self.renomear, fechar):
            linha.Add(b, 0, wx.RIGHT, 8)
        lay.Add(linha, 0, wx.ALL, 10)
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.Bind(wx.EVT_CHECKLISTBOX, self._marcou, self.lista)
        self.Bind(wx.EVT_BUTTON, self._clicou_excluir, self.excluir)
        self.Bind(wx.EVT_BUTTON, self._clicou_renomear, self.renomear)
        self._preencher(0)
        self.CentreOnParent()
        self.lista.SetFocus()

    def _preencher(self, selecionar):
        itens = self._itens()
        self._ids = [i[0] for i in itens]
        self.lista.Set([i[1] for i in itens])
        for n, (_, _, ativa) in enumerate(itens):
            self.lista.Check(n, bool(ativa))
        if itens:
            self.lista.SetSelection(max(0, min(selecionar, len(itens) - 1)))
        for b in (self.excluir, self.renomear):
            b.Enable(bool(itens))

    def _atual(self):
        n = self.lista.GetSelection()
        return (self._ids[n], n) if 0 <= n < len(self._ids) else (None, 0)

    def _marcou(self, evt):
        n = evt.GetInt()
        if 0 <= n < len(self._ids):
            self._ao_marcar(self._ids[n], self.lista.IsChecked(n))
            self._preencher(n)

    def _clicou_excluir(self, evt):
        conta_id, n = self._atual()
        if conta_id and self._ao_excluir(conta_id):
            self._preencher(n)
            if not self._ids:
                self.EndModal(wx.ID_CANCEL)

    def _clicou_renomear(self, evt):
        conta_id, n = self._atual()
        if conta_id and self._ao_renomear(conta_id):
            self._preencher(n)

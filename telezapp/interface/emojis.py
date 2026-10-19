# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Janelas de emoji: a busca completa (para escrever e para reagir) e a
lista curta de reacoes.

Nas duas, o foco vai direto para a lista ou para a busca, Enter escolhe e
Esc fecha. Cada item e "emoji nome", que o leitor de tela le por inteiro."""
import wx

from telezapp.nucleo import emojis

OUTRO = "outro"
TIRAR = "tirar"


class DialogoEmoji(wx.Dialog):
    """Digite parte do nome (joinha, coração, bolo...) e use as setas; Enter
    escolhe."""

    def __init__(self, pai, titulo="Inserir emoji"):
        super().__init__(pai, title=titulo,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.escolhido = ""
        self._achados = []
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(self, label="&Buscar emoji pelo nome"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.busca = wx.TextCtrl(self, name="Buscar emoji pelo nome",
                                 size=(380, -1))
        lay.Add(self.busca, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        lay.Add(wx.StaticText(self, label="&Emojis"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.lista = wx.ListBox(self, name="Emojis", size=(380, 260))
        lay.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        botoes = wx.BoxSizer(wx.HORIZONTAL)
        ok = wx.Button(self, wx.ID_OK, "OK")
        cancelar = wx.Button(self, wx.ID_CANCEL, "Cancelar")
        ok.SetDefault()
        for b in (ok, cancelar):
            botoes.Add(b, 0, wx.LEFT, 8)
        lay.Add(botoes, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.busca.Bind(wx.EVT_TEXT, lambda e: self._preencher())
        self.busca.Bind(wx.EVT_KEY_DOWN, self._tecla_busca)
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._escolher())
        ok.Bind(wx.EVT_BUTTON, lambda e: self._escolher())
        self.CentreOnParent()
        self._preencher()
        self.busca.SetFocus()

    def _preencher(self):
        self._achados = emojis.buscar(self.busca.GetValue(), 400)
        self.lista.Set(["%s %s" % (e.simbolo, e.nome)
                        for e in self._achados] or ["Nenhum emoji achado."])
        if self._achados:
            self.lista.SetSelection(0)

    def _tecla_busca(self, evento):
        """Seta para baixo na busca leva ao primeiro emoji achado."""
        if evento.GetKeyCode() == wx.WXK_DOWN and self._achados:
            self.lista.SetFocus()
            return
        evento.Skip()

    def _escolher(self):
        i = self.lista.GetSelection()
        if not (0 <= i < len(self._achados)):
            return
        self.escolhido = self._achados[i].simbolo
        self.EndModal(wx.ID_OK)


def escolher_emoji(pai, titulo="Inserir emoji"):
    """O emoji escolhido na busca completa, ou "" se a pessoa desistiu."""
    dlg = DialogoEmoji(pai, titulo)
    try:
        return dlg.escolhido if dlg.ShowModal() == wx.ID_OK else ""
    finally:
        dlg.Destroy()


def escolher_reacao(pai, atual=""):
    """A reacao a uma mensagem: um dos emojis rapidos, OUTRO (abrir a busca
    completa) ou TIRAR (so aparece se ja ha uma reacao sua). "" se desistiu."""
    itens = [(e, "%s %s" % (e, emojis.nome_de(e))) for e in emojis.RAPIDOS]
    itens.append((OUTRO, "Outro emoji..."))
    if atual:
        itens.append((TIRAR, "Tirar a minha reação (%s)" % atual))
    dlg = wx.SingleChoiceDialog(
        pai, "Escolha a reação à mensagem.", "Reagir", [r for _, r in itens])
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return ""
        return itens[dlg.GetSelection()][0]
    finally:
        dlg.Destroy()

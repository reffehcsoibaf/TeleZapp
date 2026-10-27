# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela "Dispositivos de som": a saida (onde tocam os audios e a chamada) e o
microfone (onde se grava a voz e se fala na chamada). A primeira opcao de cada
lista e "Padrão do Windows"."""
import wx

from telezapp.midia import dispositivos


class DialogoDispositivos(wx.Dialog):
    def __init__(self, pai, microfones, saidas, microfone="", saida=""):
        super().__init__(pai, title="Dispositivos de som",
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.itens_mic, pos_mic = dispositivos.opcoes(microfones, microfone)
        self.itens_saida, pos_saida = dispositivos.opcoes(saidas, saida)
        self.escolha_saida = wx.Choice(self, choices=self.itens_saida,
                                       name="Saída de som")
        self.escolha_mic = wx.Choice(self, choices=self.itens_mic,
                                     name="Microfone")
        self.escolha_saida.SetSelection(pos_saida)
        self.escolha_mic.SetSelection(pos_mic)

        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(
            self, label="Vale para tocar áudios, gravar e chamadas."),
            0, wx.ALL, 12)
        for rotulo, escolha in (
                (wx.StaticText(self, label="Saída de &som (alto-falantes ou "
                                           "fone):"), self.escolha_saida),
                (wx.StaticText(self, label="&Microfone:"), self.escolha_mic)):
            lay.Add(rotulo, 0, wx.LEFT | wx.RIGHT, 12)
            lay.Add(escolha, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        botoes = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        if botoes is not None:
            lay.Add(botoes, 0, wx.EXPAND | wx.ALL, 12)
        self.SetSizerAndFit(lay)
        self.escolha_saida.SetFocus()

    def escolhidos(self):
        """(microfone, saida): o nome, ou vazio para o padrão do Windows."""
        return (dispositivos.nome_escolhido(
                    self.itens_mic, self.escolha_mic.GetSelection()),
                dispositivos.nome_escolhido(
                    self.itens_saida, self.escolha_saida.GetSelection()))


def escolher(pai, microfone="", saida=""):
    """Abre a janela com os dispositivos do Windows. Devolve (microfone,
    saida) ou None se a pessoa cancelar."""
    microfones, saidas = dispositivos.listar()
    dlg = DialogoDispositivos(pai, microfones, saidas, microfone, saida)
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return None
        return dlg.escolhidos()
    finally:
        dlg.Destroy()

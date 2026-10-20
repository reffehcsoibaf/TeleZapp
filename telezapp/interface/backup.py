# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Janelas de backup e de restauracao: o que incluir (ou restaurar) e a
senha. Quem grava e restaura e `nucleo.backup`."""
import wx

from telezapp.nucleo import backup as bk


class DialogoBackup(wx.Dialog):
    """Escolhe as partes e a senha (opcional) do backup."""

    def __init__(self, pai):
        super().__init__(pai, title="Fazer backup",
                         style=wx.DEFAULT_DIALOG_STYLE)
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(
            self, label="Escolha o que vai no backup. O arquivo é um zip "
                        "que o 7-Zip também abre."), 0, wx.ALL, 10)
        self.caixas = {}
        for parte, rotulo in bk.PARTES:
            c = wx.CheckBox(self, label=rotulo)
            c.SetValue(parte == "configuracoes")
            lay.Add(c, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
            self.caixas[parte] = c
        lay.Add(wx.StaticText(
            self, label="Com senha, o arquivo é cifrado (AES-256) e as "
                        "chaves dos provedores de IA vão junto, se a parte "
                        "de configurações estiver marcada. Sem senha, as "
                        "chaves ficam de fora."), 0, wx.LEFT | wx.RIGHT |
            wx.TOP, 10)
        lay.Add(wx.StaticText(self, label="Senha do backup (deixe em branco "
                                          "para não usar senha)"),
                0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.senha = wx.TextCtrl(self, style=wx.TE_PASSWORD,
                                 name="Senha do backup")
        lay.Add(self.senha, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        lay.Add(wx.StaticText(self, label="Repita a senha"),
                0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.repita = wx.TextCtrl(self, style=wx.TE_PASSWORD,
                                  name="Repita a senha")
        lay.Add(self.repita, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        lay.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0,
                wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.Bind(wx.EVT_BUTTON, self._ok, id=wx.ID_OK)
        self.CentreOnParent()

    def _ok(self, evt):
        if not self.partes():
            wx.MessageBox("Marque pelo menos uma parte.", "Fazer backup",
                          wx.OK | wx.ICON_WARNING, self)
            return
        if self.senha.GetValue() != self.repita.GetValue():
            wx.MessageBox("As duas senhas não são iguais.", "Fazer backup",
                          wx.OK | wx.ICON_WARNING, self)
            return
        if self.caixas["contas"].GetValue() and not self.senha.GetValue():
            r = wx.MessageBox(
                "O backup vai levar as sessões das suas contas, que dão "
                "acesso a elas, e está sem senha. Quem tiver o arquivo "
                "poderá usar as suas contas. Continuar sem senha?",
                "Fazer backup", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
                self)
            if r != wx.YES:
                return
        evt.Skip()

    def partes(self):
        return [p for p, c in self.caixas.items() if c.GetValue()]


class DialogoRestaurar(wx.Dialog):
    """Escolhe o que restaurar, entre as partes que o backup tem."""

    def __init__(self, pai, manifesto):
        super().__init__(pai, title="Restaurar backup",
                         style=wx.DEFAULT_DIALOG_STYLE)
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(
            self, label="Este backup foi feito pelo TeleZapp %s. Marque o "
                        "que restaurar. As configurações valem na hora; o "
                        "resto troca o que há agora na próxima vez que o "
                        "TeleZapp abrir, e o que havia fica guardado na "
                        "pasta antes-da-restauracao." % (
                            manifesto.versao or "(versão desconhecida)")),
            0, wx.ALL, 10)
        self.caixas = {}
        for parte in manifesto.partes:
            c = wx.CheckBox(self, label=bk.NOMES_PARTES[parte])
            c.SetValue(True)
            lay.Add(c, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
            self.caixas[parte] = c
        lay.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0,
                wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.CentreOnParent()

    def partes(self):
        return [p for p, c in self.caixas.items() if c.GetValue()]

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janelas de backup e de restauracao: o que incluir (ou restaurar) e a
senha. Quem grava e restaura e `nucleo.backup`."""
import wx

from telezapp.nucleo import backup as bk


def _caixas_de_contas(janela, lay, contas, titulo):
    """Uma caixa por conta (com um rotulo antes): so aparece quando ha mais
    de uma conta. Devolve {conta_id: caixa}."""
    caixas = {}
    if len(contas) < 2:
        return caixas
    lay.Add(wx.StaticText(janela, label=titulo), 0,
            wx.LEFT | wx.RIGHT | wx.TOP, 10)
    for conta_id, rotulo in contas:
        c = wx.CheckBox(janela, label=rotulo)
        c.SetValue(True)
        lay.Add(c, 0, wx.LEFT | wx.RIGHT, 20)
        caixas[conta_id] = c
    return caixas


def _contas_marcadas(caixas):
    """None quando todas estao marcadas (ou ha uma so); senao, os ids."""
    marcadas = [i for i, c in caixas.items() if c.GetValue()]
    return None if len(marcadas) == len(caixas) else marcadas


class DialogoBackup(wx.Dialog):
    """Escolhe as partes, as contas e a senha (opcional) do backup.
    `contas`: [(conta_id, rotulo)] das contas que existem."""

    def __init__(self, pai, contas=()):
        super().__init__(pai, title="Fazer backup",
                         style=wx.DEFAULT_DIALOG_STYLE)
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(
            self, label="Escolha o que vai no backup. O arquivo é um zip "
                        "que o 7-Zip também abre."), 0, wx.ALL, 10)
        self.caixas = {}
        for parte, rotulo in bk.PARTES:
            c = wx.CheckBox(self, label=rotulo)
            c.SetValue(parte in ("configuracoes", "atalhos", "sons"))
            lay.Add(c, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
            self.caixas[parte] = c
        self.caixas_de_contas = _caixas_de_contas(
            self, lay, contas, "Contas que vão no backup (valem para as "
                               "sessões, as conversas e as mídias):")
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
        if self.caixas_de_contas and self.contas() == []:
            wx.MessageBox("Marque pelo menos uma conta.", "Fazer backup",
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
        if self.caixas["conversas"].GetValue() and (
                not self.caixas["contas"].GetValue()):
            r = wx.MessageBox(
                bk.AVISO_CONVERSAS_SEM_CONTAS + " Marque também Contas e "
                "sessões para levá-las a outra instalação. Fazer o backup "
                "sem as contas?", "Fazer backup",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self)
            if r != wx.YES:
                return
        evt.Skip()

    def partes(self):
        return [p for p, c in self.caixas.items() if c.GetValue()]

    def contas(self):
        """None: todas as contas; senao, os ids das marcadas."""
        return _contas_marcadas(self.caixas_de_contas)


class DialogoRestaurar(wx.Dialog):
    """Escolhe o que restaurar, entre as partes que o backup tem.
    `contas`: [(conta_id, nome)] das contas que o backup tem."""

    def __init__(self, pai, manifesto, contas=()):
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
            rotulo = bk.NOMES_PARTES[parte]
            if parte == "configuracoes" and manifesto.formato < 2:
                rotulo = ("Configurações do TeleZapp, com os atalhos e os "
                          "sons (as opções da janela de Configurações)")
            c = wx.CheckBox(self, label=rotulo)
            c.SetValue(True)
            lay.Add(c, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
            self.caixas[parte] = c
        self.caixas_de_contas = _caixas_de_contas(
            self, lay, contas if set(manifesto.partes) & {
                "contas", "conversas", "midias"} else (),
            "Contas a restaurar (só os dados delas são trocados; as outras "
            "contas ficam como estão):")
        lay.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0,
                wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.CentreOnParent()

    def partes(self):
        return [p for p, c in self.caixas.items() if c.GetValue()]

    def contas(self):
        """None: todas as contas do backup; senao, os ids das marcadas."""
        return _contas_marcadas(self.caixas_de_contas)

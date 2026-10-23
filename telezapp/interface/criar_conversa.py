# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Janela de Novo grupo, Novo canal e Nova comunidade: conta, nome,
descricao e, nos grupos, participantes (e topicos, onde o servico tem)."""
import wx

from telezapp.nucleo import criar_conversa as cc


class DialogoCriarConversa(wx.Dialog):
    def __init__(self, pai, tipo, contas):
        """contas: [(conta_id, rotulo, servico)] das contas conectadas que
        criam este tipo."""
        super().__init__(pai, title=cc.NOMES[tipo][2],
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.tipo, self.contas = tipo, contas
        lay = wx.BoxSizer(wx.VERTICAL)

        def campo(rotulo, criar, expandir=0):
            # o rotulo nasce ANTES do controle: o leitor de tela usa o texto
            # que vem logo antes do controle como o nome dele
            lay.Add(wx.StaticText(self, label=rotulo), 0,
                    wx.LEFT | wx.RIGHT | wx.TOP, 10)
            ctrl = criar()
            lay.Add(ctrl, expandir, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
            return ctrl
        self.conta = None
        if len(contas) > 1:
            self.conta = campo("Criar pela conta", lambda: wx.Choice(
                self, choices=[r for _, r, _ in contas],
                name="Criar pela conta"))
            self.conta.SetSelection(0)
            self.conta.Bind(wx.EVT_CHOICE, lambda e: self._atualizar())
        self.nome = campo("Nome", lambda: wx.TextCtrl(
            self, name="Nome", size=(420, -1)))
        self.descricao = campo("Descrição (opcional)", lambda: wx.TextCtrl(
            self, name="Descrição", size=(420, 80), style=wx.TE_MULTILINE))
        self.participantes = None
        if tipo == cc.GRUPO:
            self.participantes = campo(
                "Participantes (opcional): telefones no formato internacional, "
                "como +55 51 99999 8888, ou @usuários, "
                "separados por vírgula",
                lambda: wx.TextCtrl(self, name="Participantes",
                                    size=(420, -1)))
        self.topicos = None
        if tipo == cc.GRUPO:
            self.topicos = wx.CheckBox(
                self, label="Dividir o grupo em &tópicos",
                name="Dividir o grupo em tópicos")
            lay.Add(self.topicos, 0, wx.ALL, 10)
        lay.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0,
                wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.Bind(wx.EVT_BUTTON, self._ao_ok, id=wx.ID_OK)
        self.CentreOnParent()
        self._atualizar()
        self.nome.SetFocus()

    def _servico(self):
        i = max(self.conta.GetSelection(), 0) if self.conta else 0
        return self.contas[i][2]

    def _atualizar(self):
        """Topicos so existem no Telegram."""
        if self.topicos is not None:
            telegram = self._servico() == "telegram"
            self.topicos.Show(telegram)
            if not telegram:
                self.topicos.SetValue(False)
            self.Layout()
            self.Fit()

    def _ao_ok(self, evento):
        _, _, erro = cc.validar(self._servico(), self.tipo,
                                self.nome.GetValue(),
                                self.descricao.GetValue())
        if erro:
            wx.MessageBox(erro, self.GetTitle(), wx.OK | wx.ICON_WARNING,
                          self)
            self.nome.SetFocus()
            return
        evento.Skip()

    def escolhido(self):
        """(conta_id, nome, descricao, [participantes], topicos)."""
        i = max(self.conta.GetSelection(), 0) if self.conta else 0
        nome, descricao, _ = cc.validar(
            self._servico(), self.tipo, self.nome.GetValue(),
            self.descricao.GetValue())
        gente = cc.separar_participantes(
            self.participantes.GetValue() if self.participantes else "")
        return (self.contas[i][0], nome, descricao, gente,
                bool(self.topicos and self.topicos.GetValue()))

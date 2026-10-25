# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Janela de limpeza de midias baixadas e de mensagens: filtros, total e
confirmacao.

So desenha e pergunta; quem escolhe e apaga e `nucleo.limpeza`. O que foi
limpo fica registrado e so volta com um novo pareamento da conta.
"""
import wx

from telezapp.nucleo import limpeza
from telezapp.nucleo import modelos as m

TIPOS = (("", ()),) + limpeza.GRUPOS_TIPOS
TODOS = "Todos"


class DialogoLimpeza(wx.Dialog):
    def __init__(self, pai, banco, contas, conversas, falar, ao_limpar,
                 so_a_conversa=None):
        """contas: [(conta_id, rotulo)]; conversas: [(conta_id, conversa_id,
        nome)] de todas as conversas. so_a_conversa: (conta_id, conversa_id,
        nome) para limpar so uma conversa; a janela nao mostra conta nem
        conversa e as demais opcoes seguem iguais."""
        titulo = "Limpar mídias e mensagens"
        if so_a_conversa:
            titulo = "Limpar a conversa: %s" % so_a_conversa[2]
        super().__init__(pai, title=titulo, style=wx.DEFAULT_DIALOG_STYLE)
        self.banco, self.falar, self.ao_limpar = banco, falar, ao_limpar
        self.so_a_conversa = so_a_conversa
        self.contas = [("", "Todas as contas")] + list(contas)
        self.todas_conversas = list(conversas)
        self._conversas = []
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(
            self, label="Apaga neste computador, não na conta. O que for "
                        "limpo não volta, nem por histórico nem por download, "
                        "até a conta ser pareada de novo. O total aparece "
                        "antes de confirmar."),
                0, wx.ALL, 10)

        def campo(rotulo, criar):
            # o rotulo nasce ANTES do controle: o leitor de tela usa o texto
            # que vem logo antes do controle como o nome dele
            lay.Add(wx.StaticText(self, label=rotulo), 0,
                    wx.LEFT | wx.RIGHT | wx.TOP, 10)
            ctrl = criar()
            lay.Add(ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
            return ctrl
        self.o_que = campo("O que limpar", lambda: wx.Choice(
            self, choices=["Só as mídias baixadas (as mensagens ficam)",
                           "Mensagens, com as mídias delas"],
            name="O que limpar"))
        self.o_que.SetSelection(0)
        if not so_a_conversa:
            self.conta = campo("Conta", lambda: wx.Choice(
                self, choices=[r for _, r in self.contas], name="Conta"))
            self.conversa = campo("Conversa", lambda: wx.Choice(
                self, name="Conversa"))
        self.tipo = campo("Tipo de mídia", lambda: wx.Choice(
            self, choices=[TODOS] + [r for r, _ in TIPOS[1:]],
            name="Tipo de mídia"))
        self.dias = campo(
            "Só as baixadas há mais de quantos dias (0 = todas)",
            lambda: wx.SpinCtrl(self, min=0, max=36500, initial=0,
                                name="Dias"))
        self.mb = campo(
            "Só as maiores que quantos MB (0 = qualquer tamanho)",
            lambda: wx.SpinCtrl(self, min=0, max=100000, initial=0,
                                name="Tamanho mínimo em MB"))
        self.favoritas = wx.CheckBox(
            self, label="Manter as mensagens &favoritas")
        self.favoritas.SetValue(True)
        lay.Add(self.favoritas, 0, wx.ALL, 10)
        self.tipo.SetSelection(0)
        if not so_a_conversa:
            self.conta.SetSelection(0)
            self.conta.Bind(wx.EVT_CHOICE,
                            lambda e: self._montar_conversas())
            self._montar_conversas()
        linha = wx.BoxSizer(wx.HORIZONTAL)
        apagar = wx.Button(self, label="&Apagar...")
        linha.Add(apagar, 0, wx.RIGHT, 6)
        linha.Add(wx.Button(self, wx.ID_CANCEL, "&Fechar"), 0)
        lay.Add(linha, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        apagar.Bind(wx.EVT_BUTTON, lambda e: self._apagar())
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.CentreOnParent()
        (self.o_que if so_a_conversa else self.conta).SetFocus()

    def _montar_conversas(self):
        conta = self.contas[max(self.conta.GetSelection(), 0)][0]
        self._conversas = [("", "", "Todas as conversas")] + [
            c for c in self.todas_conversas if not conta or c[0] == conta]
        self.conversa.Set([c[2] for c in self._conversas])
        self.conversa.SetSelection(0)

    def filtros(self):
        if self.so_a_conversa:
            conta, conv = self.so_a_conversa[0], self.so_a_conversa
        else:
            conta = self.contas[max(self.conta.GetSelection(), 0)][0]
            conv = self._conversas[max(self.conversa.GetSelection(), 0)]
        i = max(self.tipo.GetSelection(), 0)
        return limpeza.Filtros(
            o_que=(limpeza.MENSAGENS if self.o_que.GetSelection() == 1
                   else limpeza.MIDIAS),
            conta_id=conta, conversa_id=conv[1], tipos=TIPOS[i][1],
            dias=self.dias.GetValue(), mb=self.mb.GetValue(),
            manter_favoritas=self.favoritas.GetValue())

    def _apagar(self):
        sel = limpeza.selecionar(self.banco, self.filtros())
        msgs = sel.o_que == limpeza.MENSAGENS
        if not sel.quantidade:
            texto = "Nada passa pelos filtros."
            self.falar(texto)
            wx.MessageBox(texto, "Limpar mídias e mensagens",
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        n = sel.quantidade
        nome = ("mensagem" if n == 1 else "mensagens") if msgs else             ("arquivo" if n == 1 else "arquivos")
        pergunta = "Apagar %d %s" % (n, nome)
        if sel.bytes:
            pergunta += ", liberando %s" % m.tamanho_legivel(sel.bytes)
        pergunta += ". O que for apagado não volta até a conta ser pareada "             "de novo. Continuar?"
        r = wx.MessageBox(pergunta, "Limpar mídias e mensagens",
                          wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
        if r != wx.YES:
            return
        feitos, liberados, falhas = limpeza.apagar(self.banco, sel)
        if msgs:
            texto = "%d %s" % (feitos, "mensagem apagada" if feitos == 1
                               else "mensagens apagadas")
        else:
            texto = "%d %s" % (feitos, "arquivo apagado" if feitos == 1
                               else "arquivos apagados")
        if liberados:
            texto += ", %s liberados" % m.tamanho_legivel(liberados)
        texto += "."
        if falhas:
            texto += " %d não puderam ser apagados (talvez em uso)." % falhas
        self.ao_limpar(sel)
        self.falar(texto)
        wx.MessageBox(texto, "Limpar mídias e mensagens",
                      wx.OK | wx.ICON_INFORMATION, self)
        self.EndModal(wx.ID_OK)

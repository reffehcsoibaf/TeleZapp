# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela de publicar um status (WhatsApp) ou uma historia (Telegram)."""
import os

import wx

from telezapp.interface.emojis import escolher_emoji
from telezapp.interface.teclas import combinacao_do_evento
from telezapp.nucleo import emojis, publicar_status as ps


class DialogoPublicarStatus(wx.Dialog):
    """contas: [(id, rotulo, servico)]. Depois de ShowModal() == wx.ID_OK,
    `resultado` tem conta_id, texto, anexo e publico. atalho_emoji: a mesma
    tecla de inserir emoji da janela principal, que aqui nao chega.
    gravar_voz(pai) -> caminho da gravacao ou None (so no WhatsApp).
    escolher_mencoes(pai, conta_id, atuais) -> [(id, nome)] ou None."""

    def __init__(self, pai, contas, escolher_arquivo, atalho_emoji="",
                 fala=None, gravar_voz=None, escolher_mencoes=None):
        super().__init__(pai, title="Novo status",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.contas = list(contas)
        self.escolher_arquivo = escolher_arquivo
        self.atalho_emoji = atalho_emoji
        self.fala = fala
        self.gravar_voz = gravar_voz
        self.voz = False                # o arquivo e uma gravacao daqui
        self.escolher_mencoes = escolher_mencoes
        self.mencoes = []               # [(id, nome)]
        self.resultado = None
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(self, label="&Conta"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.cx_conta = wx.Choice(self, choices=[r for _, r, _ in contas],
                                  name="Conta")
        self.cx_conta.SetSelection(0)
        lay.Add(self.cx_conta, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        lay.Add(wx.StaticText(self, label="&Texto (no Telegram, a legenda)"),
                0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.texto = wx.TextCtrl(self, style=wx.TE_MULTILINE,
                                 name="Texto do status", size=(420, 110))
        lay.Add(self.texto, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.btn_emoji = wx.Button(self, label="Inserir &emoji...")
        lay.Add(self.btn_emoji, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        lay.Add(wx.StaticText(self, label="Foto ou &vídeo (opcional no "
                                          "WhatsApp, obrigatório no "
                                          "Telegram)"),
                0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        linha = wx.BoxSizer(wx.HORIZONTAL)
        self.arquivo = wx.TextCtrl(self, style=wx.TE_READONLY,
                                   name="Foto ou vídeo escolhido")
        self.btn_procurar = wx.Button(self, label="Procurar arquivo...")
        self.btn_limpar = wx.Button(self, label="Tirar o arquivo")
        linha.Add(self.arquivo, 1, wx.RIGHT, 8)
        linha.Add(self.btn_procurar, 0, wx.RIGHT, 8)
        linha.Add(self.btn_limpar, 0)
        lay.Add(linha, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.btn_gravar = wx.Button(self, label="&Gravar mensagem de voz...")
        lay.Add(self.btn_gravar, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.btn_mencoes = wx.Button(self, label="&Mencionar pessoas...")
        lay.Add(self.btn_mencoes, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.rot_publico = wx.StaticText(self, label="Quem pode &ver "
                                                     "(Telegram)")
        lay.Add(self.rot_publico, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.cx_publico = wx.Choice(self, choices=[r for _, r in ps.PUBLICOS],
                                    name="Quem pode ver")
        self.cx_publico.SetSelection(0)
        lay.Add(self.cx_publico, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        botoes = wx.BoxSizer(wx.HORIZONTAL)
        self.ok = wx.Button(self, wx.ID_OK, "&Publicar")
        cancelar = wx.Button(self, wx.ID_CANCEL, "Cancelar")
        self.ok.SetDefault()
        botoes.Add(self.ok, 0, wx.RIGHT, 8)
        botoes.Add(cancelar, 0)
        lay.Add(botoes, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.caminho = ""
        self.Bind(wx.EVT_CHAR_HOOK, self._ao_apertar)
        self.btn_emoji.Bind(wx.EVT_BUTTON, lambda e: self._inserir_emoji())
        self.cx_conta.Bind(wx.EVT_CHOICE, lambda e: self._ao_trocar_conta())
        self.btn_procurar.Bind(wx.EVT_BUTTON, lambda e: self._procurar())
        self.btn_limpar.Bind(wx.EVT_BUTTON, lambda e: self._limpar())
        self.btn_gravar.Bind(wx.EVT_BUTTON, lambda e: self._gravar())
        self.btn_mencoes.Bind(wx.EVT_BUTTON, lambda e: self._mencionar())
        self.ok.Bind(wx.EVT_BUTTON, lambda e: self._publicar())
        self._ao_trocar_conta()
        self.CentreOnParent()
        self.texto.SetFocus()

    def _ao_apertar(self, evt):
        if self.atalho_emoji and \
                combinacao_do_evento(evt) == self.atalho_emoji:
            self._inserir_emoji()
            return
        evt.Skip()

    def _inserir_emoji(self):
        simbolo = escolher_emoji(self, fala=self.fala)
        self.texto.SetFocus()
        if not simbolo:
            return
        self.texto.WriteText(simbolo)
        if self.fala is not None:
            self.fala.falar("Emoji inserido: %s." % emojis.nome_de(simbolo),
                            interromper=True)

    def _servico(self):
        return self.contas[max(self.cx_conta.GetSelection(), 0)][2]

    def _ao_trocar_conta(self):
        telegram = self._servico() == "telegram"
        self.rot_publico.Show(telegram)
        self.cx_publico.Show(telegram)
        self.btn_gravar.Show(not telegram and self.gravar_voz is not None)
        self.btn_mencoes.Show(not telegram and
                              self.escolher_mencoes is not None)
        self.mencoes = []               # a escolha era de outra conta
        self.btn_mencoes.SetLabel("&Mencionar pessoas...")
        self.Layout()

    def _procurar(self):
        caminho = self.escolher_arquivo(self)
        if caminho:
            self._limpar()
            self.caminho = caminho
            self.arquivo.SetValue(caminho)

    def _mencionar(self):
        conta_id = self.contas[max(self.cx_conta.GetSelection(), 0)][0]
        escolha = self.escolher_mencoes(self, conta_id, self.mencoes)
        if escolha is None:
            return
        self.mencoes = escolha
        self.btn_mencoes.SetLabel(
            "&Mencionar pessoas: " + ", ".join(n for _, n in escolha)
            if escolha else "&Mencionar pessoas...")
        self.Layout()

    def _gravar(self):
        caminho = self.gravar_voz(self)
        if not caminho:
            return
        self._limpar()
        self.caminho, self.voz = caminho, True
        self.arquivo.SetValue("Mensagem de voz gravada")
        self.ok.SetFocus()

    def _limpar(self):
        if self.voz:                    # a gravacao so existe para este envio
            try:
                os.remove(self.caminho)
            except OSError:
                pass
        self.caminho, self.voz = "", False
        self.arquivo.SetValue("")

    def _publicar(self):
        conta_id, _, servico = self.contas[max(self.cx_conta.GetSelection(),
                                               0)]
        anexo, texto, erro = ps.validar(servico, self.texto.GetValue(),
                                        self.caminho, self.voz)
        if erro:
            wx.MessageBox(erro, "Novo status", wx.OK | wx.ICON_WARNING,
                          self)
            return
        publico = ps.PUBLICOS[max(self.cx_publico.GetSelection(), 0)][0]
        self.resultado = {"conta_id": conta_id, "texto": texto,
                          "anexo": anexo, "publico": publico,
                          "mencoes": [c for c, _ in self.mencoes]}
        self.EndModal(wx.ID_OK)

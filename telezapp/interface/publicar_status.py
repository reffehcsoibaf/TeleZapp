# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela de publicar um status (WhatsApp) ou uma historia (Telegram)."""
import wx

from telezapp.interface.emojis import escolher_emoji
from telezapp.interface.teclas import combinacao_do_evento
from telezapp.nucleo import emojis, publicar_status as ps


class DialogoPublicarStatus(wx.Dialog):
    """contas: [(id, rotulo, servico)]. Depois de ShowModal() == wx.ID_OK,
    `resultado` tem conta_id, texto, anexo e publico. atalho_emoji: a mesma
    tecla de inserir emoji da janela principal, que aqui nao chega."""

    def __init__(self, pai, contas, escolher_arquivo, atalho_emoji="",
                 fala=None):
        super().__init__(pai, title="Novo status",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.contas = list(contas)
        self.escolher_arquivo = escolher_arquivo
        self.atalho_emoji = atalho_emoji
        self.fala = fala
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
        self.Layout()

    def _procurar(self):
        caminho = self.escolher_arquivo(self)
        if caminho:
            self.caminho = caminho
            self.arquivo.SetValue(caminho)

    def _limpar(self):
        self.caminho = ""
        self.arquivo.SetValue("")

    def _publicar(self):
        conta_id, _, servico = self.contas[max(self.cx_conta.GetSelection(),
                                               0)]
        anexo, texto, erro = ps.validar(servico, self.texto.GetValue(),
                                        self.caminho)
        if erro:
            wx.MessageBox(erro, "Novo status", wx.OK | wx.ICON_WARNING,
                          self)
            return
        publico = ps.PUBLICOS[max(self.cx_publico.GetSelection(), 0)][0]
        self.resultado = {"conta_id": conta_id, "texto": texto,
                          "anexo": anexo, "publico": publico}
        self.EndModal(wx.ID_OK)

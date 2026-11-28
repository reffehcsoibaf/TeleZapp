# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela "Colaborar financeiramente": mostra a chave Pix do projeto, com um
botao para copiar. So texto e botoes nativos, sem link externo, para o leitor
de tela ler tudo em ordem."""
import wx

from telezapp import NOME

# A chave e publica por natureza (quem paga precisa dela).
PIX_CHAVE = "51989404175"
PIX_TIPO = "celular"
PIX_NOME = "Fabio Scheffer Moraes"
PIX_BANCO = "Caixa Econômica Federal"

ROTULO_BOTAO = "&Colaborar financeiramente..."


def texto_do_pix():
    """O que a janela mostra. Pura, para poder ser testada."""
    return "\n".join([
        "O %s é gratuito, sem anúncios, e é feito por uma pessoa só. Se ele "
        "te ajuda e você quiser colaborar financeiramente, qualquer valor é "
        "bem-vindo, por Pix. Colaborar é totalmente opcional e não muda nada "
        "no programa." % NOME,
        "",
        "Chave Pix (%s): %s" % (PIX_TIPO, PIX_CHAVE),
        "Nome: %s" % PIX_NOME,
        "Banco: %s" % PIX_BANCO,
        "",
        "Para pagar: no aplicativo do seu banco, escolha Pix, pagar com "
        "chave, e cole a chave com o botão Copiar a chave Pix. Confira que "
        "o nome que o banco mostra é o acima antes de confirmar.",
    ])


def copiar_para_a_area(texto):
    """Copia para a area de transferencia. True se deu certo."""
    if not wx.TheClipboard.Open():
        return False
    try:
        wx.TheClipboard.SetData(wx.TextDataObject(texto))
        wx.TheClipboard.Flush()
        return True
    finally:
        wx.TheClipboard.Close()


class DialogoColaborar(wx.Dialog):
    def __init__(self, pai, fala=None):
        super().__init__(pai, title="Colaborar financeiramente",
                         size=(560, 420),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.fala = fala
        rotulo = "Como colaborar com o %s" % NOME
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(self, label=rotulo), 0, wx.ALL, 8)
        self.texto = wx.TextCtrl(self, value=texto_do_pix(), name=rotulo,
                                 style=wx.TE_MULTILINE | wx.TE_READONLY)
        lay.Add(self.texto, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        linha = wx.BoxSizer(wx.HORIZONTAL)
        self.copiar = wx.Button(self, label="Copiar a chave &Pix")
        self.fechar = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        self.copiar.Bind(wx.EVT_BUTTON, self._copiar)
        linha.Add(self.copiar, 0, wx.RIGHT, 8)
        linha.Add(self.fechar)
        lay.Add(linha, 0, wx.ALL | wx.ALIGN_RIGHT, 8)
        self.SetSizer(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.texto.SetInsertionPoint(0)
        self.texto.SetFocus()
        self.CentreOnParent()

    def _copiar(self, evt):
        ok = copiar_para_a_area(PIX_CHAVE)
        aviso = ("Chave Pix copiada: %s" % PIX_CHAVE if ok
                 else "Não foi possível copiar. A chave é %s" % PIX_CHAVE)
        if self.fala is not None:
            self.fala.falar(aviso, interromper=True)


def mostrar(pai, fala=None):
    dlg = DialogoColaborar(pai, fala)
    try:
        dlg.ShowModal()
    finally:
        dlg.Destroy()

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Janelas de login e de texto, com controles nativos lidos pelo NVDA.

Cada campo tem um rotulo (StaticText antes do controle, que o NVDA le ao
focar) e o mesmo texto como nome do controle. Erros aparecem numa caixa de
mensagem do Windows antes de pedir de novo, que o NVDA le sozinho.
"""
import wx

from telezapp.provedores.base import PEDIR_CODIGO, PEDIR_SENHA, PEDIR_TELEFONE

TEXTOS_LOGIN = {
    PEDIR_TELEFONE: (
        "Conta do {servico}: número de telefone",
        "Digite o número da conta do {servico}, com DDD. Exemplo: 51 99999 "
        "8888. Para número de outro país, comece com o sinal de mais e o "
        "código do país.",
        "Número de telefone com DDD", False),
    PEDIR_CODIGO: (
        "Conta do {servico}: código de login",
        "O {servico} enviou um código de login para o aplicativo dele no seu "
        "celular (ou por SMS). Digite o código aqui.",
        "Código recebido", False),
    PEDIR_SENHA: (
        "Conta do {servico}: senha de duas etapas",
        "Esta conta tem verificação em duas etapas. Digite a senha que você "
        "criou para ela no {servico}.",
        "Senha de duas etapas", True),
}


class DialogoCampos(wx.Dialog):
    """Explicacao, um ou mais campos rotulados, OK e Cancelar."""

    def __init__(self, pai, titulo, explicacao, campos):
        """campos: lista de (rotulo, valor_inicial, senha)."""
        super().__init__(pai, title=titulo,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        lay = wx.BoxSizer(wx.VERTICAL)
        texto = wx.StaticText(self, label=explicacao)
        texto.Wrap(460)
        lay.Add(texto, 0, wx.ALL, 10)
        self.controles = []
        for rotulo, valor, senha in campos:
            lay.Add(wx.StaticText(self, label=rotulo), 0,
                    wx.LEFT | wx.RIGHT | wx.TOP, 10)
            estilo = wx.TE_PASSWORD if senha else 0
            ctrl = wx.TextCtrl(self, value=valor or "", name=rotulo,
                               style=estilo, size=(460, -1))
            lay.Add(ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
            self.controles.append(ctrl)
        botoes = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        lay.Add(botoes, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.CentreOnParent()
        if self.controles:
            self.controles[0].SetFocus()

    def valores(self):
        return [c.GetValue().strip() for c in self.controles]


def pedir_login(pai, servico, etapa, erro="", valor=""):
    """Mostra o pedido de login; devolve o texto ou None se cancelar."""
    titulo, explicacao, rotulo, senha = TEXTOS_LOGIN[etapa]
    titulo = titulo.format(servico=servico)
    explicacao = explicacao.format(servico=servico)
    if erro:
        wx.MessageBox(erro, titulo, wx.OK | wx.ICON_WARNING, pai)
    while True:
        dlg = DialogoCampos(pai, titulo, explicacao, [(rotulo, valor, senha)])
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return None
            texto = dlg.valores()[0]
        finally:
            dlg.Destroy()
        if texto:
            return texto
        wx.MessageBox("O campo %s está vazio." % rotulo, titulo,
                      wx.OK | wx.ICON_WARNING, pai)


def pedir_credenciais_telegram(pai, validar):
    """Pede api id e api hash do Telegram; (id, hash) ou None."""
    titulo = "Credenciais do aplicativo no Telegram"
    explicacao = (
        "Nesta fase de testes, o TeleZapp ainda não tem as credenciais "
        "próprias no Telegram. Informe o api id e o api hash criados em "
        "my.telegram.org, na opção API development tools. Eles identificam "
        "o aplicativo, não a sua conta, e ficam só neste computador.")
    valores = ["", ""]
    while True:
        dlg = DialogoCampos(pai, titulo, explicacao, [
            ("api id (só números)", valores[0], False),
            ("api hash", valores[1], False)])
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return None
            valores = dlg.valores()
        finally:
            dlg.Destroy()
        if validar(*valores):
            return int(valores[0]), valores[1]
        wx.MessageBox("O api id deve ter só números e o api hash pelo menos "
                      "16 caracteres. Confira e tente de novo.", titulo,
                      wx.OK | wx.ICON_WARNING, pai)


def mostrar_texto(pai, titulo, texto, rotulo):
    """Texto longo somente leitura, navegavel pelas setas."""
    dlg = wx.Dialog(pai, title=titulo, size=(620, 460),
                    style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    rot = wx.StaticText(dlg, label=rotulo)
    caixa = wx.TextCtrl(dlg, value=texto, name=rotulo,
                        style=wx.TE_MULTILINE | wx.TE_READONLY)
    ok = wx.Button(dlg, wx.ID_OK, "&Fechar")
    ok.SetDefault()
    lay = wx.BoxSizer(wx.VERTICAL)
    lay.Add(rot, 0, wx.ALL, 8)
    lay.Add(caixa, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
    lay.Add(ok, 0, wx.ALL | wx.ALIGN_RIGHT, 8)
    dlg.SetSizer(lay)
    dlg.SetEscapeId(wx.ID_OK)
    caixa.SetFocus()
    dlg.ShowModal()
    dlg.Destroy()

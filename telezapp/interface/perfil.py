# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Janela para editar o proprio perfil: nome, recado e foto.

So desenha e prepara a foto; ler o perfil e gravar nos servicos e com quem
chama (a janela principal, em segundo plano).
"""
import os

import wx

from telezapp.nucleo import perfil as np_

FILTRO_DE_IMAGENS = ("Imagens (*.jpg;*.jpeg;*.png;*.bmp;*.webp)|"
                     "*.jpg;*.jpeg;*.png;*.bmp;*.webp|Todos os arquivos|*.*")


class DialogoPerfil(wx.Dialog):
    """Nome, (sobrenome,) recado e a escolha de uma foto nova."""

    def __init__(self, pai, titulo, servico, valores, com_sobrenome=False,
                 foto=None, nome_da_foto=""):
        """valores: {'nome', 'sobrenome', 'recado'} de agora; foto: bytes JPEG
        ja escolhidos (ao reabrir a janela depois de um erro)."""
        super().__init__(pai, title=titulo, style=wx.DEFAULT_DIALOG_STYLE)
        self.foto, self.nome_da_foto = foto, nome_da_foto
        self.com_sobrenome = com_sobrenome
        lim = np_.limites(servico)
        lay = wx.BoxSizer(wx.VERTICAL)

        def campo(rotulo, criar):
            # o rotulo nasce ANTES do controle: o leitor de tela usa o texto
            # que vem logo antes do controle como o nome dele
            lay.Add(wx.StaticText(self, label=rotulo), 0,
                    wx.LEFT | wx.RIGHT | wx.TOP, 10)
            ctrl = criar()
            lay.Add(ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
            return ctrl

        def texto(chave, rotulo, maximo):
            c = campo(rotulo, lambda: wx.TextCtrl(
                self, value=valores.get(chave, ""), name=rotulo,
                size=(380, -1)))
            if maximo:
                c.SetMaxLength(maximo)
            return c
        self.nome = texto("nome", "Nome (até %d caracteres)" % lim["nome"],
                          lim["nome"])
        self.sobrenome = None
        if com_sobrenome:
            self.sobrenome = texto("sobrenome", "Sobrenome (opcional)",
                                   lim["sobrenome"])
        self.recado = texto(
            "recado", "Recado (%s)" % np_.DICA_DO_RECADO.get(servico, ""),
            lim["recado"])
        self.estado_foto = wx.StaticText(self, label=self._texto_da_foto())
        lay.Add(self.estado_foto, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.botao_foto = wx.Button(self, label="Escolher &foto nova...")
        lay.Add(self.botao_foto, 0, wx.ALL, 10)
        self.botao_foto.Bind(wx.EVT_BUTTON, lambda e: self._escolher_foto())
        lay.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0,
                wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.CentreOnParent()
        self.nome.SetFocus()

    def _texto_da_foto(self):
        if self.foto:
            return "Foto nova escolhida: %s." % (self.nome_da_foto or "imagem")
        return "A foto atual não muda, a menos que você escolha uma nova."

    def _escolher_foto(self):
        dlg = wx.FileDialog(self, "Escolher a foto do perfil",
                            wildcard=FILTRO_DE_IMAGENS,
                            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            caminho = dlg.GetPath()
        finally:
            dlg.Destroy()
        try:
            self.foto = np_.preparar_foto(caminho)
        except ValueError as e:
            wx.MessageBox(str(e), "Foto do perfil",
                          wx.OK | wx.ICON_WARNING, self)
            return
        self.nome_da_foto = os.path.basename(caminho)
        self.estado_foto.SetLabel(self._texto_da_foto())

    def valores(self):
        """{'nome', 'sobrenome', 'recado'} digitados (sem 'sobrenome' nos
        servicos que nao tem)."""
        v = {"nome": self.nome.GetValue(),
             "recado": self.recado.GetValue()}
        if self.sobrenome is not None:
            v["sobrenome"] = self.sobrenome.GetValue()
        return v

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Janelas das ferramentas de grupo: pedidos de entrada (aprovar e recusar) e
link de convite com QR Code. Controles nativos do wx, para o leitor de tela;
as chamadas ao servico rodam fora da thread da interface."""
import logging
import threading

import wx

from telezapp.nucleo import grupo as ng

log = logging.getLogger("telezapp.grupo")


class DialogoPedidos(wx.Dialog):
    """Quem pediu para entrar no grupo: aprovar ou recusar os escolhidos."""

    def __init__(self, pai, prov, conversa_id, nome, fala):
        super().__init__(pai, title="Pedidos de entrada em %s" % nome,
                         size=(600, 460),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.prov, self.cid, self.fala = prov, conversa_id, fala
        self.pedidos = []
        self.ocupado = False
        lay = wx.BoxSizer(wx.VERTICAL)
        self.resumo = wx.StaticText(self, label="Carregando os pedidos...")
        lay.Add(self.resumo, 0, wx.ALL, 10)
        rotulo = "Pedidos (Ctrl ou Shift marcam mais de um)"
        lay.Add(wx.StaticText(self, label=rotulo), 0, wx.LEFT | wx.RIGHT, 10)
        self.lista = wx.ListBox(self, style=wx.LB_EXTENDED | wx.LB_HSCROLL,
                                name=rotulo)
        lay.Add(self.lista, 1, wx.EXPAND | wx.ALL, 10)
        linha = wx.WrapSizer(wx.HORIZONTAL)
        for rotulo, funcao in (("&Aprovar", lambda: self.responder(True)),
                               ("&Recusar", lambda: self.responder(False)),
                               ("A&tualizar", self.carregar)):
            b = wx.Button(self, label=rotulo)
            b.Bind(wx.EVT_BUTTON, lambda e, f=funcao: f())
            linha.Add(b, 0, wx.RIGHT, 6)
        linha.Add(wx.Button(self, wx.ID_CANCEL, "&Fechar"), 0)
        lay.Add(linha, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.SetSizer(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.CentreOnParent()
        self.carregar()

    def carregar(self):
        if self.ocupado:
            return
        self.ocupado = True
        self.fala.falar("Lendo os pedidos...", interromper=True)

        def trabalho():
            try:
                ok, dado = self.prov.pedidos_de_entrada(self.cid)
            except Exception:
                log.exception("pedidos de entrada")
                ok, dado = False, "Não consegui ler os pedidos."
            wx.CallAfter(self._chegaram, ok, dado)
        threading.Thread(target=trabalho, daemon=True,
                         name="pedidos-de-entrada").start()

    def _chegaram(self, ok, dado):
        self.ocupado = False
        if not self:
            return
        if not ok:
            self.pedidos = []
            self.lista.Set(["Nenhum pedido."])
            self.resumo.SetLabel(dado)
            self.fala.falar(dado, interromper=True)
            return
        self.pedidos = dado
        self.lista.Set([ng.rotulo_do_pedido(p) for p in dado]
                       or ["Nenhum pedido."])
        texto = ng.resumo_dos_pedidos(len(dado))
        self.resumo.SetLabel(texto)
        self.fala.falar(texto, interromper=True)
        if dado:
            self.lista.SetSelection(0)
            self.lista.SetFocus()

    def escolhidos(self):
        if hasattr(self.lista, "GetSelections"):
            marcados = list(self.lista.GetSelections())
        else:
            marcados = [self.lista.GetSelection()]
        return [self.pedidos[i] for i in marcados
                if 0 <= i < len(self.pedidos)]

    def responder(self, aprovar):
        if self.ocupado:
            return
        alvos = self.escolhidos()
        if not alvos:
            self.fala.falar("Escolha um pedido na lista.", interromper=True)
            return
        if not aprovar:
            r = wx.MessageBox("Recusar %d pedido%s?" % (
                len(alvos), "" if len(alvos) == 1 else "s"),
                "Recusar pedidos",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
            if r != wx.YES:
                return
        self.ocupado = True
        self.fala.falar("Enviando ao serviço...", interromper=True)

        def trabalho():
            try:
                ok, texto = self.prov.responder_pedidos(
                    self.cid, [p["id"] for p in alvos], aprovar)
            except Exception:
                log.exception("responder pedidos")
                ok, texto = False, "Não consegui responder aos pedidos."
            wx.CallAfter(self._respondido, ok, texto)
        threading.Thread(target=trabalho, daemon=True,
                         name="responder-pedidos").start()

    def _respondido(self, ok, texto):
        self.ocupado = False
        if not self:
            return
        self.fala.falar(texto, interromper=True)
        if not ok:
            wx.MessageBox(texto, "Pedidos de entrada",
                          wx.OK | wx.ICON_WARNING, self)
            return
        self.carregar()


class DialogoConvite(wx.Dialog):
    """Link de convite do grupo, com QR Code, copiar, salvar e trocar."""

    def __init__(self, pai, link, copiar, revogar, fala):
        """copiar(texto); revogar() -> (ok, novo link ou texto), chamado
        fora da thread da interface."""
        super().__init__(pai, title="Link de convite do grupo",
                         size=(560, 640),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.link, self._copiar, self._revogar, self.fala = (
            link, copiar, revogar, fala)
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(self, label="Link de convite"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.campo = wx.TextCtrl(self, value=link, style=wx.TE_READONLY,
                                 name="Link de convite")
        lay.Add(self.campo, 0, wx.EXPAND | wx.ALL, 10)
        self.qr = wx.StaticBitmap(self)
        self.qr.SetName("QR Code do convite")
        lay.Add(self.qr, 1, wx.ALIGN_CENTER | wx.ALL, 10)
        linha = wx.WrapSizer(wx.HORIZONTAL)
        for rotulo, funcao in (
                ("&Copiar o link", self.copiar),
                ("&Salvar o QR Code...", self.salvar_qr),
                ("&Trocar por um link novo", self.trocar)):
            b = wx.Button(self, label=rotulo)
            b.Bind(wx.EVT_BUTTON, lambda e, f=funcao: f())
            linha.Add(b, 0, wx.RIGHT | wx.BOTTOM, 6)
        linha.Add(wx.Button(self, wx.ID_CANCEL, "&Fechar"), 0)
        lay.Add(linha, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.SetSizer(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.CentreOnParent()
        self._mostrar_qr()

    def _mostrar_qr(self):
        try:
            from telezapp.interface.dialogos import imagem_qr
            self.qr.SetBitmap(imagem_qr(self.link, 6))
        except Exception:
            log.exception("QR do convite")

    def copiar(self):
        self._copiar(self.link)

    def salvar_qr(self):
        dlg = wx.FileDialog(self, "Salvar o QR Code do convite",
                            defaultFile="convite-do-grupo.png",
                            wildcard="Imagem PNG (*.png)|*.png",
                            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            caminho = dlg.GetPath()
        finally:
            dlg.Destroy()
        try:
            with open(caminho, "wb") as f:
                f.write(ng.png_do_qr(self.link))
        except Exception:
            log.exception("salvar o QR do convite")
            self.fala.falar("Não consegui salvar o QR Code.",
                            interromper=True)
            return
        self.fala.falar("QR Code salvo.", interromper=True)

    def trocar(self):
        r = wx.MessageBox(
            "Trocar o link? O link atual deixa de valer, e quem o tem não "
            "consegue mais entrar por ele.", "Trocar o link de convite",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
        if r != wx.YES:
            return
        self.fala.falar("Trocando o link...", interromper=True)

        def trabalho():
            try:
                ok, dado = self._revogar()
            except Exception:
                log.exception("revogar o link")
                ok, dado = False, "Não consegui trocar o link."
            wx.CallAfter(self._trocado, ok, dado)
        threading.Thread(target=trabalho, daemon=True,
                         name="revogar-link").start()

    def _trocado(self, ok, dado):
        if not self:
            return
        if not ok:
            self.fala.falar(dado, interromper=True)
            wx.MessageBox(dado, "Link de convite", wx.OK | wx.ICON_WARNING,
                          self)
            return
        self.link = dado
        self.campo.SetValue(dado)
        self._mostrar_qr()
        self._copiar(dado)
        self.fala.falar("Link trocado e copiado.", interromper=True)

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Janela para escolher a combinacao de teclas de uma funcao: a pessoa aperta
a combinacao e o programa a escreve e a fala. Os controles tem rotulos para
o leitor de tela e nada depende da tela."""
import wx

from telezapp.interface import teclas
from telezapp.nucleo import atalhos as at

REMOVER = "remover"


class DialogoAtalho(wx.Dialog):
    """Foco no campo "Combinação": aperte as teclas. Tab sai do campo. OK
    guarda, Remover deixa a funcao sem atalho e Cancelar nao muda nada."""

    def __init__(self, pai, funcao, atual, falar=None):
        super().__init__(pai, title="Atalho de %s" % funcao,
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.falar = falar
        self.escolhida = atual or ""
        self.resultado = None            # combinacao, "" ou REMOVER
        lay = wx.BoxSizer(wx.VERTICAL)
        texto = wx.StaticText(
            self, label="Com o foco no campo, aperte a combinação de teclas "
            "que você quer usar para %s. Tab sai do campo." % funcao)
        texto.Wrap(420)
        lay.Add(texto, 0, wx.ALL, 10)
        lay.Add(wx.StaticText(self, label="&Combinação"), 0,
                wx.LEFT | wx.RIGHT, 10)
        self.campo = wx.TextCtrl(self, value=self.escolhida,
                                 style=wx.TE_READONLY, name="Combinação",
                                 size=(420, -1))
        lay.Add(self.campo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.aviso = wx.StaticText(self, label="", name="Aviso")
        lay.Add(self.aviso, 0, wx.ALL, 10)
        botoes = wx.BoxSizer(wx.HORIZONTAL)
        self.ok = wx.Button(self, wx.ID_OK, "OK")
        self.remover = wx.Button(self, wx.ID_ANY, "&Remover o atalho")
        cancelar = wx.Button(self, wx.ID_CANCEL, "Cancelar")
        self.ok.SetDefault()
        for b in (self.ok, self.remover, cancelar):
            botoes.Add(b, 0, wx.LEFT, 8)
        lay.Add(botoes, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.campo.Bind(wx.EVT_KEY_DOWN, self._ao_tecla)
        self.campo.Bind(wx.EVT_CHAR, lambda e: None)    # nada e digitado
        self.ok.Bind(wx.EVT_BUTTON, self._ao_ok)
        self.remover.Bind(wx.EVT_BUTTON, self._ao_remover)
        self.CentreOnParent()
        self.campo.SetFocus()
        self._atualizar_ok()

    def _dizer(self, texto):
        if self.falar is not None:
            self.falar(texto, interromper=True)

    def _atualizar_ok(self):
        self.ok.Enable(bool(self.escolhida))

    def _ao_tecla(self, evt):
        tab = evt.GetKeyCode() == wx.WXK_TAB
        sem_mod = not (evt.ControlDown() or evt.AltDown() or evt.ShiftDown())
        if tab or (sem_mod and evt.GetKeyCode() in (
                wx.WXK_RETURN, wx.WXK_ESCAPE, wx.WXK_NUMPAD_ENTER)):
            evt.Skip()               # navegar, confirmar e cancelar
            return
        canon = teclas.combinacao_do_evento(evt)
        if canon is None:
            return                   # so um modificador apertado
        motivo = at.problema(canon)
        if motivo:
            self.aviso.SetLabel(motivo)
            self._dizer("%s não serve. %s" % (at.texto_falado(canon), motivo))
            return
        self.escolhida = canon
        self.campo.SetValue(canon)
        self.aviso.SetLabel("")
        self._atualizar_ok()
        self._dizer(at.texto_falado(canon))

    def _ao_ok(self, evt):
        if self.escolhida:
            self.resultado = self.escolhida
            self.EndModal(wx.ID_OK)

    def _ao_remover(self, evt):
        self.resultado = REMOVER
        self.EndModal(wx.ID_OK)


def escolher_atalho(pai, funcao, atual, falar=None):
    """A combinacao escolhida, REMOVER para tirar o atalho ou None se a
    pessoa cancelou."""
    dlg = DialogoAtalho(pai, funcao, atual, falar)
    try:
        return dlg.resultado if dlg.ShowModal() == wx.ID_OK else None
    finally:
        dlg.Destroy()

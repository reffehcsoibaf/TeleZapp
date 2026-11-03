# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela de acompanhar uma localizacao em tempo real do Telegram: o texto se
atualiza sozinho e o movimento e falado."""
import wx

from telezapp.interface import dialogos
from telezapp.nucleo import localizacao as nucleo

CONFERIR_FIM_MS = 30000


class DialogoLocalizacao(wx.Dialog):
    def __init__(self, pai, quem, acao, falar):
        super().__init__(pai, title="Localização em tempo real de %s" % quem,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.falar = falar
        self.acompanhamento = nucleo.Acompanhamento(quem, acao)
        lay = wx.BoxSizer(wx.VERTICAL)
        rotulo = "Situação"
        lay.Add(wx.StaticText(self, label=rotulo), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.texto = wx.TextCtrl(
            self, name=rotulo, size=(460, 150),
            style=wx.TE_MULTILINE | wx.TE_READONLY)
        lay.Add(self.texto, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.falar_movimento = wx.CheckBox(self, label="&Falar o movimento")
        self.falar_movimento.SetValue(True)
        lay.Add(self.falar_movimento, 0, wx.ALL, 10)
        botoes = wx.BoxSizer(wx.HORIZONTAL)
        self.b_mapa = wx.Button(self, label="Abrir no &mapa")
        self.b_mapa.Bind(wx.EVT_BUTTON, self._abrir_mapa)
        botoes.Add(self.b_mapa, 0, wx.RIGHT, 10)
        botoes.Add(wx.Button(self, wx.ID_CANCEL, "&Fechar"))
        lay.Add(botoes, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.CentreOnParent()
        self._mostrar()
        self.texto.SetFocus()
        self.relogio = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._conferir_fim, self.relogio)
        self.relogio.Start(CONFERIR_FIM_MS)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._ao_destruir)

    def _ao_destruir(self, evt):
        if evt.GetEventObject() is self:
            self.relogio.Stop()
        evt.Skip()

    def _mostrar(self):
        """Sem mudar o ponto em que o leitor de tela esta no texto."""
        pos = self.texto.GetInsertionPoint()
        self.texto.ChangeValue(self.acompanhamento.texto())
        self.texto.SetInsertionPoint(min(pos, self.texto.GetLastPosition()))
        self.b_mapa.Enable(bool(self.acompanhamento.link()))

    def atualizar(self, acao):
        frase = self.acompanhamento.atualizar(acao)
        self._mostrar()
        self._dizer(frase)

    def _conferir_fim(self, _evt):
        frase = self.acompanhamento.conferir_fim()
        if frase:
            self._mostrar()
            self.falar(frase)

    def _dizer(self, frase):
        if frase and (self.falar_movimento.GetValue()
                      or self.acompanhamento.terminou):
            self.falar(frase)

    def _abrir_mapa(self, _evt):
        link = self.acompanhamento.link()
        if link:
            dialogos.abrir_link(link)

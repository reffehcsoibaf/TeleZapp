# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Janela com uma barra de progresso de verdade (wx.Gauge).

Para quem usa leitor de tela a barra diz mais do que a fala: o NVDA toca bipes
que sobem do grave ao agudo conforme ela avança, e isso só acontece com uma
barra de progresso na janela em primeiro plano. Por isso os avanços longos
(atualização, instalar, backup, download pedido, envio grande) abrem esta
janela em vez de só falar "20 por cento".
"""
import wx


class JanelaDeProgresso(wx.Dialog):
    """Janela sem modal: quem a abriu continua rodando e chama `atualizar`.

    `ao_cancelar`: se vier, a janela tem o botão Cancelar (e Esc também
    cancela) e a função é chamada uma vez. Sem ela, Esc só fecha a janela.
    Sem Enter padrão: um Enter perdido de quem digita não cancela nada."""

    def __init__(self, pai, titulo, texto="", ao_cancelar=None):
        super().__init__(pai, title=titulo, style=wx.CAPTION | wx.SYSTEM_MENU)
        self._ao_cancelar = ao_cancelar
        self._cancelada = False
        self._fechada = False
        lay = wx.BoxSizer(wx.VERTICAL)
        self.rotulo = wx.StaticText(self, label=texto or titulo,
                                    size=(380, -1))
        lay.Add(self.rotulo, 0, wx.ALL | wx.EXPAND, 10)
        self.barra = wx.Gauge(self, range=100, size=(380, 24), name=titulo)
        lay.Add(self.barra, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 10)
        self.botao = None
        if ao_cancelar is not None:
            self.botao = wx.Button(self, wx.ID_CANCEL, "&Cancelar")
            self.botao.Bind(wx.EVT_BUTTON, lambda e: self.cancelar())
            lay.Add(self.botao, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        else:
            lay.AddSpacer(10)
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.Bind(wx.EVT_CLOSE, self._ao_fechar)
        self.CentreOnParent()

    @property
    def cancelada(self):
        return self._cancelada

    @property
    def aberta(self):
        return not self._fechada

    def mostrar(self):
        """Abre a janela em primeiro plano (o NVDA só toca os bipes da barra
        da janela ativa), sem pegar o Enter de quem estava digitando."""
        self.Show()
        self.Raise()

    def atualizar(self, percentual=None, texto=None):
        """`percentual` de 0 a 100; sem ele (None), a barra só anda (não se
        sabe quanto falta)."""
        if self._fechada:
            return
        if texto is not None:
            self.rotulo.SetLabel(texto)
        if percentual is None:
            self.barra.Pulse()
        else:
            self.barra.SetValue(max(0, min(100, int(percentual))))

    def cancelar(self):
        if self._cancelada or self._ao_cancelar is None:
            return
        self._cancelada = True
        if self.botao is not None:
            self.botao.Enable(False)
        self.rotulo.SetLabel("Cancelando...")
        self._ao_cancelar()

    def _ao_fechar(self, evt):
        # o X ou Esc: com cancelamento possivel, cancela; senao so esconde
        if self._ao_cancelar is not None and not self._cancelada:
            self.cancelar()
            return
        evt.Skip()

    def fechar(self):
        """Fecha de vez (o trabalho terminou)."""
        if self._fechada:
            return
        self._fechada = True
        try:
            self.Destroy()
        except RuntimeError:
            pass

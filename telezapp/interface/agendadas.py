# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Mensagens agendadas: a janela para agendar (texto, data e hora) e a lista
das agendadas de uma conversa, com mudar o horário e cancelar. A conta e o
servidor ficam em `janela.py` e no provedor; a data e a hora são lidas em
`nucleo.agendamento`.

O servidor guarda a mensagem e a envia na hora marcada, mesmo com o TeleZapp
fechado. Sem modais que prendem o foco além das janelas simples de diálogo."""
import threading
from datetime import datetime

import wx

from telezapp.nucleo import agendamento as ag


class DialogoAgendar(wx.Dialog):
    """Texto (quando for novo), data e hora. `escolhido()` devolve
    (texto, datetime) depois do OK."""

    def __init__(self, pai, destino, texto="", editar_texto=True,
                 titulo="Agendar mensagem", agora=None, quando=None,
                 local=False):
        super().__init__(pai, title=titulo,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._agora = agora or datetime.now
        self._resultado = None
        data, hora = ag.sugestao(self._agora())
        if quando is not None:
            data, hora = quando.strftime("%d/%m/%Y"), quando.strftime("%H:%M")
        lay = wx.BoxSizer(wx.VERTICAL)
        if local:
            aviso = ("Agendar para %s. O WhatsApp não guarda mensagens "
                     "agendadas: o TeleZapp envia na hora marcada, e por isso "
                     "precisa estar aberto e conectado nessa hora. Se estiver "
                     "fechado, ao abrir ele pergunta o que fazer." % destino)
        else:
            aviso = ("Agendar para %s. O Telegram guarda a mensagem e a "
                     "envia na hora marcada, mesmo com o TeleZapp fechado."
                     % destino)
        texto_aviso = wx.StaticText(self, label=aviso)
        texto_aviso.Wrap(460)
        lay.Add(texto_aviso, 0, wx.ALL, 10)
        lay.Add(wx.StaticText(self, label="&Mensagem:"), 0,
                wx.LEFT | wx.RIGHT, 10)
        self.caixa = wx.TextCtrl(self, value=texto, name="Mensagem",
                                 style=wx.TE_MULTILINE | wx.TE_READONLY
                                 if not editar_texto else wx.TE_MULTILINE,
                                 size=(460, 110))
        lay.Add(self.caixa, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        lay.Add(wx.StaticText(self, label=(
            "&Data (hoje, amanhã ou dia/mês/ano):")), 0,
            wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.data = wx.TextCtrl(self, value=data, name="Data")
        lay.Add(self.data, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        lay.Add(wx.StaticText(self, label="&Hora (por exemplo 14:30):"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.hora = wx.TextCtrl(self, value=hora, name="Hora")
        lay.Add(self.hora, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        botoes = wx.BoxSizer(wx.HORIZONTAL)
        self.b_ok = wx.Button(self, wx.ID_OK, "&Agendar")
        self.b_ok.SetDefault()
        botoes.Add(self.b_ok, 0, wx.RIGHT, 6)
        botoes.Add(wx.Button(self, wx.ID_CANCEL, "&Cancelar"), 0)
        lay.Add(botoes, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.Bind(wx.EVT_BUTTON, self._ok, id=wx.ID_OK)
        self.CentreOnParent()
        (self.caixa if editar_texto and not texto else self.data).SetFocus()

    def _ok(self, evt):
        texto = self.caixa.GetValue().strip()
        if not texto:
            wx.MessageBox("Escreva a mensagem.", "Agendar mensagem",
                          wx.OK | wx.ICON_WARNING, self)
            self.caixa.SetFocus()
            return
        quando, erro = ag.montar(self.data.GetValue(), self.hora.GetValue(),
                                 self._agora())
        if quando is None:
            wx.MessageBox(erro, "Agendar mensagem", wx.OK | wx.ICON_WARNING,
                          self)
            self.data.SetFocus()
            return
        self._resultado = (texto, quando)
        self.EndModal(wx.ID_OK)

    def escolhido(self):
        return self._resultado


class DialogoAgendadas(wx.Dialog):
    """As mensagens agendadas da conversa. `carregar()` -> lista de
    {"id", "quando", "texto"}; `mudar(item, quando)` e `cancelar(item)` ->
    (ok, motivo); os três bloqueiam e rodam fora da janela."""

    def __init__(self, pai, destino, carregar, mudar, cancelar, falar=None,
                 agora=None, local=False):
        super().__init__(pai, title="Mensagens agendadas",
                         size=(640, 460),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.destino = destino
        self.local = local
        self.carregar_fn, self.mudar_fn, self.cancelar_fn = (
            carregar, mudar, cancelar)
        self.falar = falar or (lambda texto: None)
        self._agora = agora or datetime.now
        self.itens = []
        self.ocupada = False
        lay = wx.BoxSizer(wx.VERTICAL)
        self.rotulo = wx.StaticText(self, label=(
            "Mensagens agendadas para %s. Carregando..." % destino))
        lay.Add(self.rotulo, 0, wx.ALL, 10)
        self.lista = wx.ListBox(self, name="Mensagens agendadas")
        lay.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        # os botoes vem depois da lista: da lista, o Tab chega a eles
        botoes = wx.BoxSizer(wx.HORIZONTAL)
        self.b_mudar = wx.Button(self, wx.ID_ANY, "&Mudar o horário")
        self.b_cancelar = wx.Button(self, wx.ID_ANY, "&Cancelar o envio")
        self.b_fechar = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        for b in (self.b_mudar, self.b_cancelar, self.b_fechar):
            botoes.Add(b, 0, wx.RIGHT, 6)
        lay.Add(botoes, 0, wx.ALL, 10)
        self.SetSizer(lay)
        self.b_mudar.Bind(wx.EVT_BUTTON, lambda e: self._mudar())
        self.b_cancelar.Bind(wx.EVT_BUTTON, lambda e: self._cancelar())
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._mudar())
        self.lista.Bind(wx.EVT_LISTBOX, lambda e: self._ajustar())
        self.b_mudar.Enable(False)
        self.b_cancelar.Enable(False)
        self.CentreOnParent()
        self.lista.SetFocus()
        self.recarregar(avisar=True)

    # ----------------------------------------------------------- lista
    def _atual(self):
        i = self.lista.GetSelection()
        return self.itens[i] if 0 <= i < len(self.itens) else None

    def _ajustar(self):
        tem = self._atual() is not None and not self.ocupada
        self.b_mudar.Enable(tem)
        self.b_cancelar.Enable(tem)

    def recarregar(self, avisar=False, manter=None):
        self.ocupada = True
        self._ajustar()

        def trabalho():
            try:
                itens, erro = list(self.carregar_fn()), ""
            except Exception as e:
                itens, erro = [], str(e) or "Não consegui carregar."
            wx.CallAfter(self._mostrar, itens, erro, avisar, manter)
        threading.Thread(target=trabalho, daemon=True,
                         name="agendadas").start()

    def _mostrar(self, itens, erro, avisar, manter):
        if not self:
            return
        self.ocupada = False
        self.itens = itens
        agora = self._agora()
        self.lista.Set([ag.linha(x["texto"], x["quando"], agora,
                                 atrasada=x.get("atrasada", False))
                        for x in itens])
        if erro:
            frase = erro
        elif not itens:
            frase = "Nenhuma mensagem agendada para %s." % self.destino
        elif len(itens) == 1:
            frase = "1 mensagem agendada para %s." % self.destino
        else:
            frase = "%d mensagens agendadas para %s." % (len(itens),
                                                          self.destino)
        self.rotulo.SetLabel(frase)
        if itens:
            ids = [x["id"] for x in itens]
            i = ids.index(manter) if manter in ids else 0
            self.lista.SetSelection(i)
        if avisar or erro:
            self.falar(frase)
        self._ajustar()

    # ----------------------------------------------------------- acoes
    def _mudar(self):
        x = self._atual()
        if x is None:
            self.falar("Escolha uma mensagem.")
            return
        if self.ocupada:
            self.falar("Espere terminar.")
            return
        dlg = DialogoAgendar(self, self.destino, x["texto"],
                             editar_texto=False, local=self.local,
                             titulo="Mudar o horário da mensagem",
                             agora=self._agora, quando=x["quando"])
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            _, quando = dlg.escolhido()
        finally:
            dlg.Destroy()
        self._rodar("Mudando o horário.", lambda: self.mudar_fn(x, quando),
                    "Horário mudado para %s." % ag.descricao(
                        quando, self._agora()), x["id"])

    def _cancelar(self):
        x = self._atual()
        if x is None:
            self.falar("Escolha uma mensagem.")
            return
        if self.ocupada:
            self.falar("Espere terminar.")
            return
        r = wx.MessageBox(
            "Cancelar o envio desta mensagem? Ela não será enviada.",
            "Cancelar o envio", wx.YES_NO | wx.NO_DEFAULT
            | wx.ICON_QUESTION, self)
        if r != wx.YES:
            return
        self._rodar("Cancelando.", lambda: self.cancelar_fn(x),
                    "Envio cancelado.", None)

    def _rodar(self, aviso, acao, pronto, manter):
        self.ocupada = True
        self._ajustar()
        self.falar(aviso)

        def trabalho():
            try:
                ok, motivo = acao()
            except Exception:
                ok, motivo = False, "algo deu errado"
            wx.CallAfter(self._acabou, ok, motivo, pronto, manter)
        threading.Thread(target=trabalho, daemon=True,
                         name="agendada-acao").start()

    def _acabou(self, ok, motivo, pronto, manter):
        if not self:
            return
        if ok:
            self.falar(pronto)
            self.recarregar(manter=manter)
        else:
            self.ocupada = False
            self._ajustar()
            self.falar("Não consegui: %s." % motivo)

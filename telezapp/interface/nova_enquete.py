# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Janela para criar uma enquete: a pergunta, as opcoes (digite e aperte
Enter para acrescentar; Remover tira a selecionada), se aceita varias
respostas e, no Telegram, se os votos sao anonimos."""
import wx

from telezapp.nucleo import modelos as m


class DialogoNovaEnquete(wx.Dialog):
    def __init__(self, pai, servico, fala):
        super().__init__(pai, title="Nova enquete",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.servico, self.fala = servico, fala
        self.minimo, self.maximo = m.LIMITE_OPCOES_ENQUETE.get(
            servico, (2, 10))
        self.opcoes = []
        self.resultado = None       # (pergunta, opcoes, multipla, anonima)
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(self, label="&Pergunta"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.pergunta = wx.TextCtrl(self, name="Pergunta", size=(460, -1))
        lay.Add(self.pergunta, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        lay.Add(wx.StaticText(self, label="&Nova opção (Enter acrescenta)"),
                0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        linha = wx.BoxSizer(wx.HORIZONTAL)
        self.campo = wx.TextCtrl(self, name="Nova opção",
                                 style=wx.TE_PROCESS_ENTER, size=(340, -1))
        self.b_adicionar = wx.Button(self, wx.ID_ANY, "&Acrescentar")
        linha.Add(self.campo, 1, wx.RIGHT, 6)
        linha.Add(self.b_adicionar, 0)
        lay.Add(linha, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.rot_lista = wx.StaticText(self, label="&Opções")
        lay.Add(self.rot_lista, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.lista = wx.ListBox(self, name="Opções", size=(460, 140))
        lay.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        edicao = wx.BoxSizer(wx.HORIZONTAL)
        self.b_remover = wx.Button(self, wx.ID_ANY, "&Remover a opção")
        self.b_subir = wx.Button(self, wx.ID_ANY, "Mover para &cima")
        self.b_descer = wx.Button(self, wx.ID_ANY, "Mover para &baixo")
        for b in (self.b_remover, self.b_subir, self.b_descer):
            edicao.Add(b, 0, wx.RIGHT, 6)
        lay.Add(edicao, 0, wx.ALL, 10)
        self.multipla = wx.CheckBox(self, label="Permitir &várias respostas",
                                    name="Permitir várias respostas")
        lay.Add(self.multipla, 0, wx.LEFT | wx.RIGHT, 10)
        self.anonima = wx.CheckBox(self, label="Votos a&nônimos",
                                   name="Votos anônimos")
        self.anonima.SetValue(True)
        self.anonima.Show(servico == "telegram")
        lay.Add(self.anonima, 0, wx.ALL, 10)
        self.aviso = wx.StaticText(self, label="", name="Situação")
        lay.Add(self.aviso, 0, wx.LEFT | wx.RIGHT, 10)
        botoes = wx.BoxSizer(wx.HORIZONTAL)
        self.ok = wx.Button(self, wx.ID_OK, "C&riar")
        cancelar = wx.Button(self, wx.ID_CANCEL, "Cancelar")
        self.ok.SetDefault()
        for b in (self.ok, cancelar):
            botoes.Add(b, 0, wx.LEFT, 8)
        lay.Add(botoes, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.campo.Bind(wx.EVT_TEXT_ENTER, lambda e: self._acrescentar())
        self.b_adicionar.Bind(wx.EVT_BUTTON, lambda e: self._acrescentar())
        self.b_remover.Bind(wx.EVT_BUTTON, lambda e: self._remover())
        self.b_subir.Bind(wx.EVT_BUTTON, lambda e: self._mover(-1))
        self.b_descer.Bind(wx.EVT_BUTTON, lambda e: self._mover(1))
        self.pergunta.Bind(wx.EVT_TEXT, lambda e: self._atualizar())
        self.ok.Bind(wx.EVT_BUTTON, self._ao_ok)
        self.CentreOnParent()
        self._atualizar()
        self.pergunta.SetFocus()

    def _dizer(self, texto):
        self.fala.falar(texto, interromper=True)

    def _atualizar(self):
        self.lista.Set(self.opcoes)
        self.rot_lista.SetLabel("&Opções (%d de %d a %d)" % (
            len(self.opcoes), self.minimo, self.maximo))
        tem = bool(self.opcoes)
        self.b_remover.Enable(tem)
        self.b_subir.Enable(len(self.opcoes) > 1)
        self.b_descer.Enable(len(self.opcoes) > 1)
        erro = m.erro_da_enquete(self.servico, self.pergunta.GetValue(),
                                 self.opcoes)
        self.aviso.SetLabel(erro)
        self.ok.Enable(not erro)

    def _acrescentar(self):
        texto = self.campo.GetValue().strip()
        if not texto:
            return
        if len(self.opcoes) >= self.maximo:
            self._dizer("O limite é de %d opções." % self.maximo)
            return
        if len(texto) > m.MAX_OPCAO_ENQUETE:
            self._dizer("Cada opção pode ter até %d letras." %
                        m.MAX_OPCAO_ENQUETE)
            return
        if texto.lower() in [o.lower() for o in self.opcoes]:
            self._dizer("Essa opção já está na lista.")
            return
        self.opcoes.append(texto)
        self.campo.Clear()
        self._atualizar()
        self.lista.SetSelection(len(self.opcoes) - 1)
        self._dizer("Opção %d acrescentada." % len(self.opcoes))
        self.campo.SetFocus()

    def _remover(self):
        i = self.lista.GetSelection()
        if 0 <= i < len(self.opcoes):
            nome = self.opcoes.pop(i)
            self._atualizar()
            if self.opcoes:
                self.lista.SetSelection(min(i, len(self.opcoes) - 1))
            self._dizer("Opção removida: %s." % nome)

    def _mover(self, passo):
        i = self.lista.GetSelection()
        j = i + passo
        if 0 <= i < len(self.opcoes) and 0 <= j < len(self.opcoes):
            self.opcoes[i], self.opcoes[j] = self.opcoes[j], self.opcoes[i]
            self._atualizar()
            self.lista.SetSelection(j)
            self._dizer("Opção %d." % (j + 1))

    def _ao_ok(self, evt):
        # a opcao que ficou digitada e nao foi acrescentada entra tambem
        if self.campo.GetValue().strip():
            self._acrescentar()
        erro = m.erro_da_enquete(self.servico, self.pergunta.GetValue(),
                                 self.opcoes)
        if erro:
            self._dizer(erro)
            return
        self.resultado = (self.pergunta.GetValue().strip(),
                          list(self.opcoes), self.multipla.GetValue(),
                          self.anonima.GetValue())
        self.EndModal(wx.ID_OK)


def pedir_enquete(pai, servico, fala):
    """(pergunta, opcoes, multipla, anonima) ou None se cancelou."""
    dlg = DialogoNovaEnquete(pai, servico, fala)
    try:
        return dlg.resultado if dlg.ShowModal() == wx.ID_OK else None
    finally:
        dlg.Destroy()

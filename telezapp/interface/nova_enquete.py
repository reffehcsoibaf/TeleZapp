# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela para criar uma enquete: a pergunta, as opcoes (digite e aperte
Enter para acrescentar; Remover tira a selecionada), se aceita varias
respostas e, no Telegram, se os votos sao anonimos."""
import time

import wx

from telezapp.nucleo import modelos as m

# Prazos para encerrar a enquete: (texto, segundos; 0 = sem prazo)
PRAZOS = (("Sem prazo", 0), ("Em 1 hora", 3600), ("Em 8 horas", 8 * 3600),
          ("Em 24 horas", 24 * 3600), ("Em 3 dias", 3 * 24 * 3600),
          ("Em 7 dias", 7 * 24 * 3600))


class DialogoNovaEnquete(wx.Dialog):
    def __init__(self, pai, servico, fala, avancada=False):
        super().__init__(pai, title="Nova enquete",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.servico, self.fala, self.avancada = servico, fala, avancada
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
        if avancada:
            self._montar_avancadas(lay)
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
        if avancada:
            self.quiz.Bind(wx.EVT_CHECKBOX, lambda e: self._atualizar())
        self.ok.Bind(wx.EVT_BUTTON, self._ao_ok)
        self.CentreOnParent()
        self._atualizar()
        self.pergunta.SetFocus()

    def _montar_avancadas(self, lay):
        """Recursos experimentais do WhatsApp: quiz, ocultar quem votou,
        opcoes novas dos participantes e prazo."""
        self.quiz = wx.CheckBox(
            self, label="É um &quiz (uma resposta certa)", name="Quiz")
        lay.Add(self.quiz, 0, wx.LEFT | wx.RIGHT, 10)
        self.rot_certa = wx.StaticText(self, label="Resposta &certa")
        lay.Add(self.rot_certa, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.certa = wx.Choice(self, choices=[], name="Resposta certa")
        lay.Add(self.certa, 0, wx.LEFT | wx.RIGHT, 10)
        self.oculta = wx.CheckBox(
            self, label="&Ocultar quem votou", name="Ocultar quem votou")
        lay.Add(self.oculta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.adicionar = wx.CheckBox(
            self, label="Permitir que os participantes acrescentem &opções "
            "novas", name="Permitir acrescentar opções")
        lay.Add(self.adicionar, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        lay.Add(wx.StaticText(self, label="&Encerrar a enquete"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.prazo = wx.Choice(
            self, choices=[nome for nome, _s in PRAZOS],
            name="Encerrar a enquete")
        self.prazo.SetSelection(0)
        lay.Add(self.prazo, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

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
        if self.avancada:
            quiz = self.quiz.GetValue()
            antes = self.certa.GetSelection()
            self.certa.Set(list(self.opcoes))
            if 0 <= antes < len(self.opcoes):
                self.certa.SetSelection(antes)
            elif self.opcoes:
                self.certa.SetSelection(0)
            self.certa.Enable(quiz and bool(self.opcoes))
            self.rot_certa.Enable(quiz and bool(self.opcoes))
            if quiz:
                self.multipla.SetValue(False)
            self.multipla.Enable(not quiz)

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

    def _avancadas(self):
        """So o que foi escolhido (vazio numa enquete comum)."""
        extras = {}
        if self.quiz.GetValue() and self.certa.GetSelection() >= 0:
            extras["quiz"] = self.certa.GetSelection()
        if self.oculta.GetValue():
            extras["oculta"] = True
        if self.adicionar.GetValue():
            extras["permite_adicionar"] = True
        segundos = PRAZOS[max(0, self.prazo.GetSelection())][1]
        if segundos:
            extras["encerra_em"] = int(time.time()) + segundos
        return extras

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
        if self.avancada:
            self.resultado += (self._avancadas(),)
        self.EndModal(wx.ID_OK)


def pedir_enquete(pai, servico, fala, avancada=False):
    """(pergunta, opcoes, multipla, anonima) ou None se cancelou. Com
    `avancada`, vem um quinto item: o dicionario do quiz, de ocultar quem
    votou, de opcoes novas e do prazo (so as caracteristicas escolhidas)."""
    dlg = DialogoNovaEnquete(pai, servico, fala, avancada)
    try:
        return dlg.resultado if dlg.ShowModal() == wx.ID_OK else None
    finally:
        dlg.Destroy()

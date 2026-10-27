# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela da enquete: a pergunta, as opcoes com a contagem de cada uma (marca
com Espaco; numa enquete de uma resposta so, marcar uma desmarca a outra),
Votar, Tirar meu voto, Atualizar e Ver quem votou."""
import wx

from telezapp.nucleo import modelos as m

DEMORA_ATUALIZAR_MS = 1500     # o voto vai e volta pelo servico


class DialogoEnquete(wx.Dialog):
    def __init__(self, pai, obter, pode_votar, votar, atualizar, fala):
        """obter() devolve a mensagem atual; votar(escolhas) e atualizar()
        pedem ao servico (o resultado chega depois e obter() o traz)."""
        super().__init__(pai, title="Enquete",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.obter, self.votar, self.atualizar_servico = obter, votar, \
            atualizar
        self.pode_votar, self.fala = pode_votar, fala
        self.enq = m.enquete_de(obter())
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(self, label="&Pergunta"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.pergunta = wx.TextCtrl(
            self, value=self.enq["pergunta"], name="Pergunta",
            style=wx.TE_MULTILINE | wx.TE_READONLY, size=(460, 60))
        lay.Add(self.pergunta, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.rot_lista = wx.StaticText(self, label="&Opções")
        lay.Add(self.rot_lista, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.lista = wx.CheckListBox(self, choices=[], name="Opções",
                                     size=(460, 200))
        lay.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.aviso = wx.StaticText(self, label="", name="Situação")
        lay.Add(self.aviso, 0, wx.ALL, 10)
        botoes = wx.WrapSizer(wx.HORIZONTAL)
        self.b_votar = wx.Button(self, wx.ID_ANY, "&Votar")
        self.b_tirar = wx.Button(self, wx.ID_ANY, "&Tirar meu voto")
        self.b_atualizar = wx.Button(self, wx.ID_ANY, "&Atualizar")
        self.b_quem = wx.Button(self, wx.ID_ANY, "Ver &quem votou")
        fechar = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        for b in (self.b_votar, self.b_tirar, self.b_atualizar, self.b_quem,
                  fechar):
            botoes.Add(b, 0, wx.RIGHT | wx.BOTTOM, 6)
        lay.Add(botoes, 0, wx.ALL, 10)
        self.b_votar.SetDefault()
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.lista.Bind(wx.EVT_CHECKLISTBOX, self._marcou)
        self.b_votar.Bind(wx.EVT_BUTTON, lambda e: self._votar())
        self.b_tirar.Bind(wx.EVT_BUTTON, lambda e: self._tirar())
        self.b_atualizar.Bind(wx.EVT_BUTTON, lambda e: self._atualizar())
        self.b_quem.Bind(wx.EVT_BUTTON, lambda e: self._quem())
        self.CentreOnParent()
        self._preencher(marcar=self.enq["meus"])
        self.lista.SetFocus()

    def _dizer(self, texto):
        self.fala.falar(texto, interromper=True)

    def _preencher(self, marcar):
        """Poe as opcoes (com a contagem) e marca as dadas."""
        self.enq = m.enquete_de(self.obter())
        linhas = m.linhas_da_enquete(self.enq)
        self.lista.Set(linhas)
        for i in marcar:
            if 0 <= i < len(linhas):
                self.lista.Check(i, True)
        if self.lista.GetCount():
            self.lista.SetSelection(0)
        self.rot_lista.SetLabel(
            "&Opções (%s)" % ("só uma resposta" if self.enq["maximo"] == 1
                              else "até %d respostas" % self.enq["maximo"]))
        votantes = m.votantes_da_enquete(self.enq)
        situacao = "%s." % ("Enquete encerrada" if self.enq["encerrada"]
                            else "Enquete aberta")
        situacao += " %s." % ("Nenhum voto" if votantes == 0 else
                              "1 voto" if votantes == 1 else
                              "%d votos" % votantes)
        if not self.pode_votar and not self.enq["encerrada"]:
            situacao += " Sem conexão ou sem suporte a voto: só leitura."
        self.aviso.SetLabel(situacao)
        aberta = self.pode_votar and not self.enq["encerrada"]
        self.b_votar.Enable(aberta)
        self.b_tirar.Enable(aberta and bool(self.enq["meus"]))
        self.b_quem.Enable(not self.enq["anonima"] and bool(
            self.enq["votos"]))
        self.Layout()

    def _marcou(self, evt):
        i = evt.GetInt()
        if not self.lista.IsChecked(i):
            return
        marcadas = list(self.lista.GetCheckedItems())
        if self.enq["maximo"] == 1:
            for j in marcadas:
                if j != i:
                    self.lista.Check(j, False)
        elif len(marcadas) > self.enq["maximo"]:
            self.lista.Check(i, False)
            self._dizer("Só dá para marcar %d opções." % self.enq["maximo"])

    def _votar(self):
        escolhas = sorted(self.lista.GetCheckedItems())
        if not escolhas:
            self._dizer("Marque uma opção com Espaço, ou use Tirar meu voto.")
            return
        self.votar(escolhas)
        self._dizer("Voto enviado.")
        self._atualizar_depois(escolhas)

    def _tirar(self):
        self.votar([])
        self._dizer("Pedido para tirar o seu voto enviado.")
        self._atualizar_depois([])

    def _atualizar(self):
        self.atualizar_servico()
        self._atualizar_depois(None)

    def _atualizar_depois(self, marcar):
        def refazer():
            if self:
                marcadas = self.enq["meus"] if marcar is None else marcar
                self._preencher(marcar=m.enquete_de(self.obter())["meus"]
                                or marcadas)
                self._dizer("Enquete atualizada.")
        wx.CallLater(DEMORA_ATUALIZAR_MS, refazer)

    def _quem(self):
        linhas = []
        for i, opcao in enumerate(self.enq["opcoes"]):
            nomes = m.quem_votou_em(self.enq, i)
            if nomes:
                linhas.append("%s (%d): %s" % (opcao, len(nomes),
                                               ", ".join(nomes)))
        texto = "\n".join(linhas) or "Ninguém votou ainda."
        dlg = wx.MessageDialog(self, texto, "Quem votou", wx.OK)
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()


def abrir(pai, obter, pode_votar, votar, atualizar, fala):
    dlg = DialogoEnquete(pai, obter, pode_votar, votar, atualizar, fala)
    try:
        dlg.ShowModal()
    finally:
        dlg.Destroy()

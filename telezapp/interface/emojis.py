# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janelas de emoji: a busca completa (para escrever e para reagir) e a
lista curta de reacoes.

Nas duas, o foco vai direto para a lista ou para a busca, Enter escolhe e
Esc fecha. Cada item e "emoji nome", que o leitor de tela le por inteiro. Num
emoji que tem tons de pele, as setas para a esquerda e para a direita trocam o
item pelo tom anterior ou pelo proximo (o sem tom, depois do claro ao escuro),
e a fala diz qual ficou.

Na busca completa para escrever, Control Espaco marca varios emojis (Espaco
marca e desmarca, Control A marca todos, Esc desfaz) e Enter insere todos os
marcados, na ordem em que foram marcados."""
import wx

from telezapp.interface.marcas import Marcas

from telezapp.nucleo import emojis

OUTRO = "outro"
TIRAR = "tirar"


class DialogoEmoji(wx.Dialog):
    """Digite parte do nome (joinha, coração, bolo...) e use as setas; Enter
    escolhe."""

    def __init__(self, pai, titulo="Inserir emoji", fala=None, varios=False):
        super().__init__(pai, title=titulo,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.escolhido = ""
        self.marcas = None
        self._achados = []
        self.fala = fala
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(self, label="&Buscar emoji pelo nome"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.busca = wx.TextCtrl(self, name="Buscar emoji pelo nome",
                                 size=(380, -1))
        lay.Add(self.busca, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        lay.Add(wx.StaticText(self, label="&Categoria"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self._categorias = [(None, "Todas")] + emojis.categorias()
        self.categoria = wx.Choice(self, name="Categoria",
                                   choices=[n for _, n in self._categorias])
        self.categoria.SetSelection(0)
        lay.Add(self.categoria, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        lay.Add(wx.StaticText(self, label="&Emojis"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.lista = wx.ListBox(self, name="Emojis" + (
            " (Control Espaço marca vários)" if varios else ""),
            size=(380, 260))
        lay.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        if varios:
            self.marcas = Marcas(
                self.lista,
                (lambda t: fala.falar(t, interromper=True)) if fala
                else None, chave=lambda e: e.simbolo, dono=self)
            self.Bind(wx.EVT_CHAR_HOOK, self._hook)
        botoes = wx.BoxSizer(wx.HORIZONTAL)
        ok = wx.Button(self, wx.ID_OK, "OK")
        cancelar = wx.Button(self, wx.ID_CANCEL, "Cancelar")
        ok.SetDefault()
        for b in (ok, cancelar):
            botoes.Add(b, 0, wx.LEFT, 8)
        lay.Add(botoes, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.busca.Bind(wx.EVT_TEXT, lambda e: self._preencher())
        self.categoria.Bind(wx.EVT_CHOICE, self._ao_trocar_categoria)
        self.busca.Bind(wx.EVT_KEY_DOWN, self._tecla_busca)
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._escolher())
        self.lista.Bind(wx.EVT_KEY_DOWN, self._tecla_lista)
        ok.Bind(wx.EVT_BUTTON, lambda e: self._escolher())
        self.CentreOnParent()
        self._preencher()
        self.busca.SetFocus()

    def _chave_da_categoria(self):
        i = self.categoria.GetSelection()
        return self._categorias[i][0] if 0 <= i < len(
            self._categorias) else None

    def _ao_trocar_categoria(self, _evento=None):
        self._preencher()
        if self.fala is not None:
            n = len(self._achados)
            self.fala.falar("%s, %s." % (
                self._categorias[self.categoria.GetSelection()][1],
                "nenhum emoji" if not n else "1 emoji" if n == 1
                else "%d emojis" % n), interromper=True)

    def _preencher(self):
        # sem texto numa categoria, todos os dela (sem o corte da busca)
        categoria = self._chave_da_categoria()
        self._achados = emojis.buscar(
            self.busca.GetValue(), 0 if categoria else 400, categoria)
        textos = ["%s %s" % (e.simbolo, e.nome) for e in self._achados]
        if self.marcas is not None:
            textos = self.marcas.rotulos(textos, self._achados)
        self.lista.Set(textos or ["Nenhum emoji achado."])
        if self._achados:
            self.lista.SetSelection(0)

    def _hook(self, evento):
        """As teclas da selecao multipla, antes de o dialogo tratar o Esc."""
        if self.marcas is not None and self.marcas.tecla(evento):
            return
        evento.Skip()

    def _tecla_busca(self, evento):
        """Seta para baixo na busca leva ao primeiro emoji achado."""
        if evento.GetKeyCode() == wx.WXK_DOWN and self._achados:
            self.lista.SetFocus()
            return
        evento.Skip()

    def _tecla_lista(self, evento):
        """Esquerda e direita passam pelos tons de pele do emoji em foco."""
        if evento.GetKeyCode() in (wx.WXK_LEFT, wx.WXK_RIGHT) and not (
                evento.ControlDown() or evento.AltDown()
                or evento.ShiftDown()):
            delta = 1 if evento.GetKeyCode() == wx.WXK_RIGHT else -1
            if self.passo_de_tom(delta):
                return
        evento.Skip()

    def passo_de_tom(self, delta):
        """Troca o emoji selecionado pelo tom seguinte (delta 1) ou anterior
        (-1) e fala qual ficou; False se ele nao tem tons."""
        i = self.lista.GetSelection()
        if not (0 <= i < len(self._achados)):
            return False
        novo = emojis.passo_de_tom(self._achados[i].simbolo, delta)
        if novo is None:
            return False
        self._achados[i] = novo
        texto = "%s %s" % (novo.simbolo, novo.nome)
        if self.marcas is not None:
            self.marcas.substituir(i, novo, texto)
        else:
            self.lista.SetString(i, texto)
        self.lista.SetSelection(i)
        if self.fala is not None:
            self.fala.falar(texto, interromper=True)
        return True

    def _escolher(self):
        if self.marcas is not None and self.marcas.marcados:
            # todos os marcados, na ordem em que foram marcados
            self.escolhido = "".join(
                e.simbolo for e in self.marcas.marcados.values())
            self.EndModal(wx.ID_OK)
            return
        i = self.lista.GetSelection()
        if not (0 <= i < len(self._achados)):
            return
        self.escolhido = self._achados[i].simbolo
        self.EndModal(wx.ID_OK)


def escolher_emoji(pai, titulo="Inserir emoji", fala=None, varios=False):
    """O emoji escolhido na busca completa, ou "" se a pessoa desistiu.
    `fala`, se houver, diz o tom de pele escolhido com as setas. `varios`:
    deixa marcar varios (Control Espaco); o resultado e a juncao deles."""
    dlg = DialogoEmoji(pai, titulo, fala, varios)
    try:
        return dlg.escolhido if dlg.ShowModal() == wx.ID_OK else ""
    finally:
        dlg.Destroy()


class DialogoReacao(wx.Dialog):
    """A lista curta de reacoes: os emojis rapidos, "Outro emoji..." e, se ja
    ha uma reacao sua, "Tirar a minha reacao". Enter escolhe; esquerda e
    direita passam pelos tons de pele do emoji rapido em foco."""

    def __init__(self, pai, atual="", fala=None):
        super().__init__(pai, title="Reagir", style=wx.DEFAULT_DIALOG_STYLE)
        self.fala = fala
        self.escolhido = ""
        # (valor, texto): o valor e o emoji, OUTRO ou TIRAR
        self.itens = [(e, "%s %s" % (e, emojis.nome_de(e)))
                      for e in emojis.RAPIDOS]
        self.itens.append((OUTRO, "Outro emoji..."))
        if atual:
            self.itens.append((TIRAR, "Tirar a minha reação (%s)" % atual))
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(self, label="Escolha a &reação à mensagem."),
                0, wx.ALL, 10)
        self.lista = wx.ListBox(self, name="Reações", size=(340, 190))
        self.lista.Set([t for _, t in self.itens])
        lay.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        botoes = wx.BoxSizer(wx.HORIZONTAL)
        ok = wx.Button(self, wx.ID_OK, "OK")
        cancelar = wx.Button(self, wx.ID_CANCEL, "Cancelar")
        ok.SetDefault()
        for b in (ok, cancelar):
            botoes.Add(b, 0, wx.LEFT, 8)
        lay.Add(botoes, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.lista.SetSelection(0)
        self.lista.Bind(wx.EVT_KEY_DOWN, self._tecla)
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._escolher())
        ok.Bind(wx.EVT_BUTTON, lambda e: self._escolher())
        self.CentreOnParent()
        self.lista.SetFocus()

    def _tecla(self, evento):
        if evento.GetKeyCode() in (wx.WXK_LEFT, wx.WXK_RIGHT) and not (
                evento.ControlDown() or evento.AltDown()
                or evento.ShiftDown()):
            delta = 1 if evento.GetKeyCode() == wx.WXK_RIGHT else -1
            if self.passo_de_tom(delta):
                return
        evento.Skip()

    def passo_de_tom(self, delta):
        """Troca o emoji em foco pelo tom seguinte ou anterior e fala qual
        ficou; False se a linha nao e um emoji ou ele nao tem tons."""
        i = self.lista.GetSelection()
        if not (0 <= i < len(self.itens)) or self.itens[i][0] in (OUTRO,
                                                                  TIRAR):
            return False
        novo = emojis.passo_de_tom(self.itens[i][0], delta)
        if novo is None:
            return False
        texto = "%s %s" % (novo.simbolo, novo.nome)
        self.itens[i] = (novo.simbolo, texto)
        self.lista.SetString(i, texto)
        self.lista.SetSelection(i)
        if self.fala is not None:
            self.fala.falar(texto, interromper=True)
        return True

    def _escolher(self):
        i = self.lista.GetSelection()
        if not (0 <= i < len(self.itens)):
            return
        self.escolhido = self.itens[i][0]
        self.EndModal(wx.ID_OK)


def escolher_reacao(pai, atual="", fala=None):
    """A reacao a uma mensagem: um dos emojis rapidos (com o tom de pele que
    as setas escolherem), OUTRO (abrir a busca completa) ou TIRAR (so aparece
    se ja ha uma reacao sua). "" se desistiu."""
    dlg = DialogoReacao(pai, atual, fala)
    try:
        return dlg.escolhido if dlg.ShowModal() == wx.ID_OK else ""
    finally:
        dlg.Destroy()

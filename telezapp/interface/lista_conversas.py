# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Janela do que a lista de conversas mostra: ativar e desativar cada
informacao e escolher a ordem em que aparecem.

Serve a janela de configuracoes (onde as mudancas ficam pendentes ate OK ou
Aplicar) e o menu Exibir (onde valem na hora): quem chama diz como ler e como
guardar o valor.
"""
import wx

from telezapp.nucleo import lista_conversas as lc


class DialogoListaConversas(wx.Dialog):
    """Lista de quatro informacoes, na ordem em que aparecem na lista de
    conversas; Enter ou Espaco ativa e desativa, e dois botoes mudam a ordem."""

    def __init__(self, pai, ler, gravar, fala=None):
        """ler() -> valor atual; gravar(valor) guarda o novo; fala, se houver,
        diz o que mudou."""
        super().__init__(pai, title="Lista de conversas",
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.ler, self.gravar, self.fala = ler, gravar, fala
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(
            self, label="O que cada conversa mostra na lista, na ordem em que "
                        "aparece. Pelo menos um item fica ativado."), 0,
                wx.ALL, 10)
        lay.Add(wx.StaticText(
            self, label="&Informações (Enter ou Espaço ativa e desativa):"),
            0, wx.LEFT | wx.RIGHT, 10)
        self.lista = wx.ListBox(self, name="Informações", size=(420, 120))
        lay.Add(self.lista, 1, wx.EXPAND | wx.ALL, 10)
        linha = wx.WrapSizer(wx.HORIZONTAL)
        self.botoes = {}
        for chave, rotulo in (("cima", "Mover para &cima"),
                              ("baixo", "Mover para &baixo"),
                              ("padrao", "&Restaurar o padrão")):
            b = wx.Button(self, label=rotulo)
            self.botoes[chave] = b
            linha.Add(b, 0, wx.RIGHT | wx.BOTTOM, 8)
        lay.Add(linha, 0, wx.LEFT | wx.RIGHT, 10)
        lay.Add(wx.Button(self, wx.ID_OK, "&Fechar"), 0,
                wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetEscapeId(wx.ID_OK)
        self.SetSizerAndFit(lay)
        self.CentreOnParent()
        self.lista.Bind(wx.EVT_KEY_DOWN, self._tecla)
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.alternar())
        self.botoes["cima"].Bind(wx.EVT_BUTTON, lambda e: self.mover(-1))
        self.botoes["baixo"].Bind(wx.EVT_BUTTON, lambda e: self.mover(1))
        self.botoes["padrao"].Bind(wx.EVT_BUTTON, lambda e: self.restaurar())
        self.preencher(0)
        self.lista.SetFocus()

    # -------------------------------------------------------------- lista
    def preencher(self, selecionar=0):
        lay = lc.normalizar(self.ler())
        self.lista.Set([lc.texto_do_item(lay, c) for c in lay["ordem"]])
        self.lista.SetSelection(min(max(selecionar, 0),
                                    len(lay["ordem"]) - 1))
        self.botoes["padrao"].Enable(not lc.eh_padrao(lay))

    def chave(self):
        """A informacao selecionada, ou None."""
        ordem = lc.normalizar(self.ler())["ordem"]
        i = self.lista.GetSelection()
        return ordem[i] if 0 <= i < len(ordem) else None

    def _dizer(self, texto):
        if self.fala is not None:
            self.fala.falar(texto, interromper=True)

    def _tecla(self, evt):
        sem_mod = not (evt.ControlDown() or evt.AltDown() or evt.ShiftDown())
        if sem_mod and evt.GetKeyCode() in (
                wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE):
            self.alternar()
            return
        evt.Skip()

    # ------------------------------------------------------------- acoes
    def alternar(self):
        chave = self.chave()
        if chave is None:
            return
        novo, ativado = lc.alternar(self.ler(), chave)
        if ativado is None:
            self._dizer(lc.MENSAGEM_DO_MINIMO)
            return
        self.gravar(novo)
        i = self.lista.GetSelection()
        self.preencher(i)
        self._dizer("ativado" if ativado else "desativado")

    def mover(self, delta):
        chave = self.chave()
        if chave is None:
            return
        novo, posicao = lc.mover(self.ler(), chave, delta)
        if posicao == self.lista.GetSelection():
            self._dizer("Já é o primeiro item." if delta < 0
                        else "Já é o último item.")
            return
        self.gravar(novo)
        self.preencher(posicao)
        self._dizer("%s, posição %d de %d." % (
            lc.ROTULOS[chave], posicao + 1, len(lc.CHAVES)))
        self.lista.SetFocus()

    def restaurar(self):
        self.gravar(lc.padrao())
        self.preencher(0)
        self._dizer("Lista de conversas no padrão.")
        self.lista.SetFocus()

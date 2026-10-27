# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela do corretor ortografico: mostra a palavra com erro, as sugestoes e
os botoes para trocar, ignorar ou guardar no dicionario. A palavra e a frase
em volta ficam num campo de texto, que o leitor de tela le inteiro."""
import wx


def contexto(texto, erro, raio=40):
    """A palavra com um pedaco do texto antes e depois."""
    ini = max(0, erro.inicio - raio)
    fim = min(len(texto), erro.inicio + erro.tamanho + raio)
    return ("..." if ini else "") + texto[ini:fim].replace("\n", " ") + \
        ("..." if fim < len(texto) else "")


class DialogoOrtografia(wx.Dialog):
    def __init__(self, pai, revisao, falar):
        super().__init__(pai, title="Verificar ortografia",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.rev = revisao
        self.falar = falar
        lay = wx.BoxSizer(wx.VERTICAL)
        self.rot_palavra = wx.StaticText(self, label="&Palavra não encontrada")
        lay.Add(self.rot_palavra, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.palavra = wx.TextCtrl(self, style=wx.TE_READONLY,
                                   name="Palavra não encontrada",
                                   size=(420, -1))
        lay.Add(self.palavra, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        lay.Add(wx.StaticText(self, label="&No texto"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.frase = wx.TextCtrl(self, style=wx.TE_READONLY | wx.TE_MULTILINE,
                                 name="No texto", size=(420, 60))
        lay.Add(self.frase, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        lay.Add(wx.StaticText(self, label="&Trocar por"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.troca = wx.TextCtrl(self, name="Trocar por", size=(420, -1))
        lay.Add(self.troca, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        lay.Add(wx.StaticText(self, label="&Sugestões"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.lista = wx.ListBox(self, name="Sugestões", size=(420, 130))
        lay.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        grade = wx.WrapSizer(wx.HORIZONTAL)
        self.botoes = {}
        for chave, rotulo in (("trocar", "&Trocar"),
                              ("trocar_todas", "Trocar t&odas"),
                              ("ignorar", "&Ignorar"),
                              ("ignorar_todas", "Ig&norar todas"),
                              ("adicionar", "&Adicionar ao dicionário")):
            b = wx.Button(self, label=rotulo)
            b.Bind(wx.EVT_BUTTON, lambda e, k=chave: self._acao(k))
            self.botoes[chave] = b
            grade.Add(b, 0, wx.RIGHT | wx.TOP, 6)
        fechar = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        grade.Add(fechar, 0, wx.RIGHT | wx.TOP, 6)
        lay.Add(grade, 0, wx.ALL, 10)
        self.botoes["trocar"].SetDefault()
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.lista.Bind(wx.EVT_LISTBOX,
                        lambda e: self._sugestao_escolhida())
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._acao("trocar"))
        self.CentreOnParent()
        self._mostrar()

    def _sugestao_escolhida(self):
        i = self.lista.GetSelection()
        if i != wx.NOT_FOUND and self.rev.erro.sugestoes:
            self.troca.SetValue(self.rev.erro.sugestoes[i])

    def _mostrar(self):
        e = self.rev.erro
        if e is None:
            self.EndModal(wx.ID_OK)
            return
        self.palavra.SetValue(e.palavra)
        self.frase.SetValue(contexto(self.rev.texto, e))
        self.lista.Set(e.sugestoes or ["Nenhuma sugestão."])
        if e.sugestoes:
            self.lista.SetSelection(0)
        self.troca.SetValue(e.sugestoes[0] if e.sugestoes else "")
        self.botoes["trocar"].Enable(True)
        self.botoes["trocar_todas"].Enable(True)
        self.palavra.SetFocus()
        self.falar("%s. %s." % (e.palavra, "%d sugestões" % len(e.sugestoes)
                                if e.sugestoes else "Sem sugestões"),
                   interromper=True)

    def _acao(self, chave):
        r, e = self.rev, self.rev.erro
        if e is None:
            return
        if chave in ("trocar", "trocar_todas"):
            nova = self.troca.GetValue()
            if not nova.strip():
                self.falar("Digite a palavra certa no campo Trocar por.",
                           interromper=True)
                self.troca.SetFocus()
                return
            r.substituir(nova, todas=chave == "trocar_todas")
        elif chave == "ignorar":
            r.ignorar()
        elif chave == "ignorar_todas":
            r.ignorar(sempre=True)
        else:
            r.adicionar()
        self._mostrar()


def revisar(pai, corretor, texto, falar):
    """(texto_corrigido, houve_troca, terminou) depois da janela.
    `terminou` e False se a pessoa fechou antes do fim."""
    from telezapp.nucleo.ortografia import Revisao
    rev = Revisao(corretor, texto)
    if rev.erro is None:
        return texto, False, True
    dlg = DialogoOrtografia(pai, rev, falar)
    try:
        fim = dlg.ShowModal() == wx.ID_OK
    finally:
        dlg.Destroy()
    return rev.texto, rev.trocas > 0, fim

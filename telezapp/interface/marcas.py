# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Selecao multipla numa lista simples (wx.ListBox), igual a das listas de
conversas e de mensagens: Control Espaco liga o modo de selecao e marca o
item em foco; no modo, Espaco marca e desmarca; Control A marca todos (ou
desmarca, se ja estao); Esc desfaz. O item marcado comeca com "Marcado:".

Quem usa chama `tecla(evt)` no EVT_CHAR_HOOK (devolve True se tratou),
`rotulos(textos, dados)` ao preencher a lista e `escolhidos(dados, i)` nas
acoes: os marcados, ou so o item em foco se nada estiver marcado."""
import wx


def contagem(n):
    return "nenhum marcado" if n == 0 else \
        "1 marcado" if n == 1 else "%d marcados" % n


class Marcas:
    def __init__(self, lista, falar=None, chave=id, dono=None):
        """`chave(dado)`: o que identifica o item mesmo quando a lista e
        refeita (padrao: o proprio objeto). `dono`: a janela da lista (para
        saber onde esta o foco)."""
        self.lista = lista
        self.dono = dono or lista
        self.falar = falar or (lambda texto: None)
        self.chave = chave
        self.modo = False
        self.marcados = {}              # chave -> dado
        self._dados = []
        self._textos = []

    # ---------------------------------------------------------- consulta
    def marcado(self, dado):
        return self.chave(dado) in self.marcados

    def rotulos(self, textos, dados):
        """Os textos da lista com "Marcado: " nos marcados (e guarda os
        dados para as teclas)."""
        self._textos, self._dados = list(textos), list(dados)
        return [("Marcado: " + t) if self.marcado(d) else t
                for t, d in zip(self._textos, self._dados)]

    def lista_de_marcados(self):
        """Os marcados, na ordem da lista (os que nao aparecem agora, como
        os de outra busca, no fim)."""
        na_lista = [d for d in self._dados if self.marcado(d)]
        vistas = {self.chave(d) for d in na_lista}
        return na_lista + [d for k, d in self.marcados.items()
                           if k not in vistas]

    def escolhidos(self):
        """Os marcados ou, sem marcas, o item em foco (lista vazia se nada)."""
        if self.marcados:
            return self.lista_de_marcados()
        i = self.lista.GetSelection()
        return [self._dados[i]] if 0 <= i < len(self._dados) else []

    # ---------------------------------------------------------- mudancas
    def _redesenhar(self, i):
        if 0 <= i < len(self._dados):
            t, d = self._textos[i], self._dados[i]
            self.lista.SetString(i, ("Marcado: " + t) if self.marcado(d)
                                 else t)

    def alternar(self):
        i = self.lista.GetSelection()
        if not 0 <= i < len(self._dados):
            return
        d = self._dados[i]
        self.modo = True
        if self.marcado(d):
            self.marcados.pop(self.chave(d), None)
            marcou = False
        else:
            self.marcados[self.chave(d)] = d
            marcou = True
        self._redesenhar(i)
        self.falar("%s, %s." % ("Marcado" if marcou else "Desmarcado",
                                contagem(len(self.marcados))))

    def marcar_todos(self):
        if not self._dados:
            return
        self.modo = True
        todos = {self.chave(d): d for d in self._dados}
        if set(todos) <= set(self.marcados):
            for k in todos:
                self.marcados.pop(k, None)
        else:
            self.marcados.update(todos)
        for i in range(len(self._dados)):
            self._redesenhar(i)
        self.falar(contagem(len(self.marcados)).capitalize() + ".")

    def substituir(self, i, dado, texto):
        """O item `i` virou outro (o emoji trocou de tom): a marca, se havia,
        passa para o novo."""
        velho = self._dados[i]
        estava = self.marcado(velho)
        if estava:
            self.marcados.pop(self.chave(velho), None)
            self.marcados[self.chave(dado)] = dado
        self._dados[i], self._textos[i] = dado, texto
        self._redesenhar(i)

    def esquecer(self, dados):
        """Tira das marcas o que saiu da lista (removido, apagado)."""
        for d in dados:
            self.marcados.pop(self.chave(d), None)
        if not self.marcados:
            self.modo = False

    def desfazer(self, falar=True):
        self.modo = False
        self.marcados = {}
        for i in range(len(self._dados)):
            self._redesenhar(i)
        if falar:
            self.falar("Seleção desfeita.")

    # ------------------------------------------------------------ teclado
    def tecla(self, evt):
        """True se a tecla era da selecao (e ja foi tratada)."""
        k = evt.GetKeyCode()
        ctrl = evt.ControlDown()
        outros = evt.AltDown() or evt.ShiftDown()
        na_lista = self.dono.FindFocus() is self.lista
        if na_lista and k == wx.WXK_SPACE and not outros and \
                (ctrl or self.modo):
            self.alternar()
            return True
        if na_lista and k == ord("A") and ctrl and not outros:
            self.marcar_todos()
            return True
        if k == wx.WXK_ESCAPE and not (ctrl or outros) and self.modo:
            self.desfazer()
            return True
        return False

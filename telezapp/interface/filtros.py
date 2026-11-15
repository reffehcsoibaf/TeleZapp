# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janelas dos filtros personalizados (Configurações, Interface, Filtros):
ativar, criar, renomear e excluir filtros que juntam serviço ou conta e tipo
de conversa. Quem guarda e aplica é a janela de configurações; aqui só fica a
tela. Sem janela modal dentro de outra além do formulário de um filtro."""
import wx

from telezapp.nucleo import filtros_personalizados as fp


class DialogoNovoFiltro(wx.Dialog):
    """Duas listas de caixas (serviço ou conta; tipo de conversa), o nome do
    filtro e o botão Salvar filtro. O nome é sugerido com o que está marcado,
    e deixa de mudar sozinho quando a pessoa o escreve."""

    def __init__(self, pai, contas, filtros, tipos=fp.TIPOS):
        """`contas`: [(valor, rotulo)] como no filtro de conta; `filtros`: os
        que já existem (para não repetir o nome)."""
        super().__init__(pai, title="Novo filtro",
                         style=wx.DEFAULT_DIALOG_STYLE)
        self._contas, self._tipos = list(contas), list(tipos)
        self._filtros = filtros
        self._nome_editado = False
        self._atualizando = False
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(
            self, label="Marque o que o filtro mostra. Dentro de cada lista "
                        "basta uma das opções marcadas; entre as duas listas, "
                        "as duas valem. Uma lista sem nada marcado não "
                        "restringe."), 0, wx.ALL, 10)
        lay.Add(wx.StaticText(self, label="&Contas e serviços:"), 0,
                wx.LEFT | wx.RIGHT, 10)
        self.lista_contas = wx.CheckListBox(
            self, choices=[r for _, r in self._contas],
            name="Contas e serviços", size=(420, 110))
        lay.Add(self.lista_contas, 0, wx.EXPAND | wx.ALL, 10)
        lay.Add(wx.StaticText(self, label="&Tipos de conversa:"), 0,
                wx.LEFT | wx.RIGHT, 10)
        self.lista_tipos = wx.CheckListBox(
            self, choices=[r for _, r in self._tipos],
            name="Tipos de conversa", size=(420, 150))
        lay.Add(self.lista_tipos, 0, wx.EXPAND | wx.ALL, 10)
        lay.Add(wx.StaticText(self, label="&Nome do filtro:"), 0,
                wx.LEFT | wx.RIGHT, 10)
        self.nome = wx.TextCtrl(self, name="Nome do filtro", size=(420, -1))
        lay.Add(self.nome, 0, wx.EXPAND | wx.ALL, 10)
        linha = wx.BoxSizer(wx.HORIZONTAL)
        self.salvar = wx.Button(self, wx.ID_OK, "&Salvar filtro")
        cancelar = wx.Button(self, wx.ID_CANCEL, "&Cancelar")
        linha.Add(self.salvar, 0, wx.RIGHT, 8)
        linha.Add(cancelar, 0)
        lay.Add(linha, 0, wx.ALL, 10)
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.lista_contas.Bind(wx.EVT_CHECKLISTBOX, self._marcou)
        self.lista_tipos.Bind(wx.EVT_CHECKLISTBOX, self._marcou)
        self.nome.Bind(wx.EVT_TEXT, self._digitou)
        self.Bind(wx.EVT_BUTTON, self._salvar, id=wx.ID_OK)
        self._sugerir()
        self.CentreOnParent()
        self.lista_contas.SetFocus()

    # ------------------------------------------------------------ valores
    def contas_marcadas(self):
        return [v for i, (v, _) in enumerate(self._contas)
                if self.lista_contas.IsChecked(i)]

    def tipos_marcados(self):
        return [v for i, (v, _) in enumerate(self._tipos)
                if self.lista_tipos.IsChecked(i)]

    def _sugerir(self):
        """Poe no campo o nome sugerido (enquanto a pessoa não o mudou)."""
        if self._nome_editado:
            return
        self._atualizando = True
        try:
            self.nome.SetValue(fp.nome_sugerido(
                self.contas_marcadas(), self.tipos_marcados(),
                self._contas))
        finally:
            self._atualizando = False

    def _marcou(self, evt):
        self._sugerir()

    def _digitou(self, evt):
        if not self._atualizando:
            self._nome_editado = True

    def resultado(self):
        """O filtro pronto: {"id", "nome", "contas", "tipos"}."""
        nome = self.nome.GetValue().strip()
        return {"id": fp.novo_id(self._filtros),
                "nome": fp.nome_livre(nome, self._filtros),
                "contas": self.contas_marcadas(),
                "tipos": self.tipos_marcados()}

    def _salvar(self, evt):
        if not self.contas_marcadas() and not self.tipos_marcados():
            wx.MessageBox("Marque pelo menos um item em uma das listas.",
                          "Novo filtro", wx.OK | wx.ICON_WARNING, self)
            return
        if not self.nome.GetValue().strip():
            wx.MessageBox("Escreva um nome para o filtro.", "Novo filtro",
                          wx.OK | wx.ICON_WARNING, self)
            self.nome.SetFocus()
            return
        evt.Skip()


class DialogoFiltros(wx.Dialog):
    """A caixa de ativar os filtros personalizados e, ativada, a lista deles
    com os botões Novo filtro, Renomear filtro e Excluir filtro."""

    def __init__(self, pai, ler, gravar, contas, fala=None):
        """ler() -> {"ativo", "lista"}; gravar(valor) guarda o novo valor;
        contas() -> [(valor, rotulo)] do filtro de conta; fala, se houver,
        diz o que mudou."""
        super().__init__(pai, title="Filtros", style=wx.DEFAULT_DIALOG_STYLE)
        self.ler, self.gravar, self.contas, self.fala = (
            ler, gravar, contas, fala)
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(
            self, label="Filtros personalizados juntam, em um só, o serviço "
                        "ou a conta e o tipo de conversa. Ativados, eles "
                        "tomam o lugar das caixas de serviço, conta e tipo "
                        "de conversa na tela principal."), 0, wx.ALL, 10)
        self.ativar = wx.CheckBox(self, label="&Ativar filtros "
                                              "personalizados")
        self.ativar.SetValue(bool(self.ler()["ativo"]))
        lay.Add(self.ativar, 0, wx.LEFT | wx.RIGHT, 10)
        self.rotulo_lista = wx.StaticText(self, label="&Filtros "
                                                      "personalizados:")
        lay.Add(self.rotulo_lista, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.lista = wx.ListBox(self, name="Filtros personalizados",
                                size=(420, 140))
        lay.Add(self.lista, 1, wx.EXPAND | wx.ALL, 10)
        linha = wx.BoxSizer(wx.HORIZONTAL)
        self.novo = wx.Button(self, label="&Novo filtro...")
        self.renomear = wx.Button(self, label="&Renomear filtro...")
        self.excluir = wx.Button(self, label="&Excluir filtro...")
        self.botoes = (self.novo, self.renomear, self.excluir)
        for b in self.botoes:
            linha.Add(b, 0, wx.RIGHT, 8)
        lay.Add(linha, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        fechar = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        lay.Add(fechar, 0, wx.ALL, 10)
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.ativar.Bind(wx.EVT_CHECKBOX, self._ativou)
        self.novo.Bind(wx.EVT_BUTTON, lambda e: self.novo_filtro())
        self.renomear.Bind(wx.EVT_BUTTON, lambda e: self.renomear_filtro())
        self.excluir.Bind(wx.EVT_BUTTON, lambda e: self.excluir_filtro())
        self._preencher(0)
        self._mostrar()
        self.CentreOnParent()
        self.ativar.SetFocus()

    # -------------------------------------------------------------- estado
    def _valor(self):
        return self.ler()

    def _guardar(self, ativo=None, lista=None):
        atual = self._valor()
        self.gravar({"ativo": atual["ativo"] if ativo is None else ativo,
                     "lista": atual["lista"] if lista is None else lista})

    def _preencher(self, selecionar):
        lista = self._valor()["lista"]
        self.lista.Set([f["nome"] for f in lista])
        if lista:
            self.lista.SetSelection(min(max(selecionar, 0), len(lista) - 1))
        self.renomear.Enable(bool(lista))
        self.excluir.Enable(bool(lista))

    def _mostrar(self):
        """A lista e os botões só aparecem com a caixa marcada."""
        visivel = self.ativar.GetValue()
        for parte in (self.rotulo_lista, self.lista, *self.botoes):
            parte.Show(visivel)
        self.Layout()
        self.Fit()

    def _atual(self):
        i = self.lista.GetSelection()
        lista = self._valor()["lista"]
        return (lista[i], i) if 0 <= i < len(lista) else (None, -1)

    def _dizer(self, texto):
        if self.fala:
            self.fala.falar(texto, interromper=True)

    # ------------------------------------------------------------- acoes
    def _ativou(self, evt):
        self._guardar(ativo=self.ativar.GetValue())
        self._mostrar()
        if self.ativar.GetValue():
            n = len(self._valor()["lista"])
            self._dizer("Filtros personalizados ativados." + (
                "" if n else " Crie o primeiro filtro em Novo filtro."))
            if n:
                self.lista.SetFocus()
            else:
                self.novo.SetFocus()
        else:
            self._dizer("Filtros personalizados desativados.")

    def novo_filtro(self):
        lista = self._valor()["lista"]
        dlg = DialogoNovoFiltro(self, self.contas(), lista)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return False
            filtro = dlg.resultado()
        finally:
            dlg.Destroy()
        lista = lista + [filtro]
        self._guardar(lista=lista)
        self._preencher(len(lista) - 1)
        self._dizer("Filtro %s criado." % filtro["nome"])
        self.lista.SetFocus()
        return True

    def renomear_filtro(self):
        filtro, i = self._atual()
        if filtro is None:
            return False
        dlg = wx.TextEntryDialog(self, "Novo nome do filtro:",
                                 "Renomear filtro", filtro["nome"])
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return False
            nome = dlg.GetValue().strip()
        finally:
            dlg.Destroy()
        lista = self._valor()["lista"]
        if not nome or nome == filtro["nome"]:
            return False
        nome = fp.nome_livre(nome, lista, filtro["id"])
        lista = [dict(f, nome=nome) if f["id"] == filtro["id"] else f
                 for f in lista]
        self._guardar(lista=lista)
        self._preencher(i)
        self._dizer("Filtro renomeado para %s." % nome)
        self.lista.SetFocus()
        return True

    def excluir_filtro(self):
        filtro, i = self._atual()
        if filtro is None:
            return False
        r = wx.MessageBox("Excluir o filtro %s?" % filtro["nome"], "Filtros",
                          wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
        if r != wx.YES:
            return False
        lista = [f for f in self._valor()["lista"] if f["id"] != filtro["id"]]
        self._guardar(lista=lista)
        self._preencher(i)
        self._dizer("Filtro %s excluído." % filtro["nome"])
        (self.lista if lista else self.novo).SetFocus()
        return True

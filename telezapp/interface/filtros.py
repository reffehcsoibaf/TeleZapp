# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janelas dos filtros personalizados (Configurações, Interface, Filtros):
ativar, criar, editar, renomear e excluir filtros que juntam serviço ou conta
e tipo de conversa, com o que o filtro contém e o que não contém. Quem guarda
e aplica é a janela de configurações; aqui só fica a tela. Sem janela modal
dentro de outra além do formulário de um filtro e, a partir dele, a das
listas de Contém e de Não contém."""
import wx

from telezapp.nucleo import filtros_personalizados as fp
from telezapp.nucleo import modelos as m

AJUDA_CONTEM = ("Marque o que o filtro mostra. Dentro de cada lista basta "
                "uma das opções marcadas; entre as duas listas, as duas "
                "valem. Uma lista sem nada marcado não restringe.")
AJUDA_NAO_CONTEM = ("Marque o que o filtro tira da lista. A conversa que "
                    "casar com qualquer opção marcada aqui não aparece, "
                    "mesmo que case com o que o filtro contém.")


class DialogoCondicoes(wx.Dialog):
    """As duas listas de caixas de um lado do filtro: o que ele contém (o que
    mostra) ou o que não contém (o que tira). Contas e serviços; tipos de
    conversa. Ao confirmar, quem abriu lê as marcas."""

    def __init__(self, pai, titulo, ajuda, contas, tipos, marcadas_contas=(),
                 marcadas_tipos=()):
        """`contas` e `tipos`: [(valor, rotulo)]; `marcadas_*`: valores que
        já estão marcados."""
        super().__init__(pai, title=titulo, style=wx.DEFAULT_DIALOG_STYLE)
        self._contas, self._tipos = list(contas), list(tipos)
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(self, label=ajuda), 0, wx.ALL, 10)
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
        linha = wx.BoxSizer(wx.HORIZONTAL)
        linha.Add(wx.Button(self, wx.ID_OK, "&OK"), 0, wx.RIGHT, 8)
        linha.Add(wx.Button(self, wx.ID_CANCEL, "&Cancelar"), 0)
        lay.Add(linha, 0, wx.ALL, 10)
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        for i, (v, _) in enumerate(self._contas):
            if v in marcadas_contas:
                self.lista_contas.Check(i)
        for i, (v, _) in enumerate(self._tipos):
            if v in marcadas_tipos:
                self.lista_tipos.Check(i)
        self.CentreOnParent()
        self.lista_contas.SetFocus()

    def contas_marcadas(self):
        return [v for i, (v, _) in enumerate(self._contas)
                if self.lista_contas.IsChecked(i)]

    def tipos_marcados(self):
        return [v for i, (v, _) in enumerate(self._tipos)
                if self.lista_tipos.IsChecked(i)]


class DialogoNovoFiltro(wx.Dialog):
    """Cria ou edita um filtro: o nome e dois botões, Contém e Não contém, que
    abrem cada um a janela com as listas de caixas. O nome é sugerido com o
    que está marcado (só no filtro novo) e deixa de mudar sozinho quando a
    pessoa o escreve."""

    def __init__(self, pai, contas, filtros, tipos=fp.TIPOS, filtro=None):
        """`contas`: [(valor, rotulo)] como no filtro de conta; `filtros`: os
        que já existem (para não repetir o nome); `filtro`: o que está sendo
        editado (None para um novo)."""
        super().__init__(pai, title="Editar filtro" if filtro else
                         "Novo filtro", style=wx.DEFAULT_DIALOG_STYLE)
        self._contas, self._tipos = list(contas), list(tipos)
        self._filtros = filtros
        self._editando = filtro
        filtro = filtro or {}
        self._contem = (list(filtro.get("contas") or ()),
                        list(filtro.get("tipos") or ()))
        self._nao_contem = (list(filtro.get("nao_contas") or ()),
                            list(filtro.get("nao_tipos") or ()))
        self._nome_editado = bool(filtro)
        self._atualizando = False
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(
            self, label="Use Contém para o que o filtro mostra e Não contém "
                        "para o que ele tira da lista."), 0, wx.ALL, 10)
        lay.Add(wx.StaticText(self, label="&Nome do filtro:"), 0,
                wx.LEFT | wx.RIGHT, 10)
        self.nome = wx.TextCtrl(self, name="Nome do filtro", size=(420, -1))
        lay.Add(self.nome, 0, wx.EXPAND | wx.ALL, 10)
        self.btn_contem = wx.Button(self, label="C&ontém...")
        lay.Add(self.btn_contem, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.resumo_contem = wx.StaticText(self, label="")
        lay.Add(self.resumo_contem, 0, wx.ALL, 10)
        self.btn_nao_contem = wx.Button(self, label="&Não contém...")
        lay.Add(self.btn_nao_contem, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.resumo_nao_contem = wx.StaticText(self, label="")
        lay.Add(self.resumo_nao_contem, 0, wx.ALL, 10)
        linha = wx.BoxSizer(wx.HORIZONTAL)
        self.salvar = wx.Button(self, wx.ID_OK, "&Salvar filtro")
        cancelar = wx.Button(self, wx.ID_CANCEL, "&Cancelar")
        linha.Add(self.salvar, 0, wx.RIGHT, 8)
        linha.Add(cancelar, 0)
        lay.Add(linha, 0, wx.ALL, 10)
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.btn_contem.Bind(wx.EVT_BUTTON, lambda e: self.abrir_contem())
        self.btn_nao_contem.Bind(wx.EVT_BUTTON,
                                 lambda e: self.abrir_nao_contem())
        self.nome.Bind(wx.EVT_TEXT, self._digitou)
        self.Bind(wx.EVT_BUTTON, self._salvar, id=wx.ID_OK)
        if self._editando:
            self._atualizando = True
            try:
                self.nome.SetValue(self._editando.get("nome", ""))
            finally:
                self._atualizando = False
        self._atualizar()
        self.CentreOnParent()
        self.nome.SetFocus()

    # ------------------------------------------------------------ valores
    def contas_marcadas(self):
        return list(self._contem[0])

    def tipos_marcados(self):
        return list(self._contem[1])

    def nao_contas_marcadas(self):
        return list(self._nao_contem[0])

    def nao_tipos_marcados(self):
        return list(self._nao_contem[1])

    def _texto_do_resumo(self, prefixo, contas, tipos, vazio):
        rot = dict(self._contas)
        rot.update(self._tipos)
        itens = [rot[v] for v in list(contas) + list(tipos) if v in rot]
        return "%s: %s" % (prefixo, ", ".join(itens) if itens else vazio)

    def _atualizar(self):
        """Refaz os resumos e, enquanto a pessoa não escreveu o nome, o
        nome sugerido."""
        self.resumo_contem.SetLabel(self._texto_do_resumo(
            "Contém", *self._contem, "nada marcado, não restringe"))
        self.resumo_nao_contem.SetLabel(self._texto_do_resumo(
            "Não contém", *self._nao_contem, "nada marcado"))
        if self._nome_editado:
            return
        self._atualizando = True
        try:
            self.nome.SetValue(fp.nome_sugerido(
                self.contas_marcadas(), self.tipos_marcados(),
                self._contas, self.nao_contas_marcadas(),
                self.nao_tipos_marcados()))
        finally:
            self._atualizando = False

    def _digitou(self, evt):
        if not self._atualizando:
            self._nome_editado = True

    # ------------------------------------------------------------- acoes
    def _abrir(self, titulo, ajuda, atuais, excluir):
        contas, tipos = self._contas, self._tipos
        if excluir:      # "todas" nao serve para tirar: tiraria tudo
            contas = [c for c in contas if c[0] != m.CONTA_TODAS]
            tipos = [t for t in tipos if t[0] != "todas"]
        dlg = DialogoCondicoes(self, titulo, ajuda, contas, tipos, *atuais)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return None
            return dlg.contas_marcadas(), dlg.tipos_marcados()
        finally:
            dlg.Destroy()

    def abrir_contem(self):
        novo = self._abrir("Contém", AJUDA_CONTEM, self._contem, False)
        if novo is not None:
            self._contem = novo
            self._atualizar()
        self.btn_contem.SetFocus()

    def abrir_nao_contem(self):
        novo = self._abrir("Não contém", AJUDA_NAO_CONTEM, self._nao_contem,
                           True)
        if novo is not None:
            self._nao_contem = novo
            self._atualizar()
        self.btn_nao_contem.SetFocus()

    def resultado(self):
        """O filtro pronto: {"id", "nome", "contas", "tipos"} e, se houver,
        "nao_contas" e "nao_tipos"."""
        nome = self.nome.GetValue().strip()
        id_ = (self._editando["id"] if self._editando
               else fp.novo_id(self._filtros))
        filtro = {"id": id_,
                  "nome": fp.nome_livre(nome, self._filtros, id_),
                  "contas": self.contas_marcadas(),
                  "tipos": self.tipos_marcados()}
        if self.nao_contas_marcadas():
            filtro["nao_contas"] = self.nao_contas_marcadas()
        if self.nao_tipos_marcados():
            filtro["nao_tipos"] = self.nao_tipos_marcados()
        return filtro

    def _salvar(self, evt):
        titulo = self.GetTitle()
        if not (self.contas_marcadas() or self.tipos_marcados()
                or self.nao_contas_marcadas() or self.nao_tipos_marcados()):
            wx.MessageBox("Marque pelo menos um item em Contém ou em Não "
                          "contém.", titulo, wx.OK | wx.ICON_WARNING, self)
            self.btn_contem.SetFocus()
            return
        repetidos = ((set(self.contas_marcadas())
                      & set(self.nao_contas_marcadas()))
                     | (set(self.tipos_marcados())
                        & set(self.nao_tipos_marcados())))
        if repetidos:
            wx.MessageBox("O mesmo item está em Contém e em Não contém. "
                          "Tire de um dos dois.", titulo,
                          wx.OK | wx.ICON_WARNING, self)
            self.btn_contem.SetFocus()
            return
        if not self.nome.GetValue().strip():
            wx.MessageBox("Escreva um nome para o filtro.", titulo,
                          wx.OK | wx.ICON_WARNING, self)
            self.nome.SetFocus()
            return
        evt.Skip()


class DialogoFiltros(wx.Dialog):
    """A caixa de ativar os filtros personalizados e, ativada, a lista deles
    com os botões Novo filtro, Editar filtro, Renomear filtro e Excluir
    filtro."""

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
        self.editar = wx.Button(self, label="&Editar filtro...")
        self.renomear = wx.Button(self, label="&Renomear filtro...")
        self.excluir = wx.Button(self, label="E&xcluir filtro...")
        self.botoes = (self.novo, self.editar, self.renomear, self.excluir)
        for b in self.botoes:
            linha.Add(b, 0, wx.RIGHT, 8)
        lay.Add(linha, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        fechar = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        lay.Add(fechar, 0, wx.ALL, 10)
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.ativar.Bind(wx.EVT_CHECKBOX, self._ativou)
        self.novo.Bind(wx.EVT_BUTTON, lambda e: self.novo_filtro())
        self.editar.Bind(wx.EVT_BUTTON, lambda e: self.editar_filtro())
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
        self.editar.Enable(bool(lista))
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

    def editar_filtro(self):
        filtro, i = self._atual()
        if filtro is None:
            return False
        lista = self._valor()["lista"]
        dlg = DialogoNovoFiltro(self, self.contas(), lista, filtro=filtro)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return False
            novo = dlg.resultado()
        finally:
            dlg.Destroy()
        lista = [novo if f["id"] == filtro["id"] else f for f in lista]
        self._guardar(lista=lista)
        self._preencher(i)
        self._dizer("Filtro %s alterado." % novo["nome"])
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

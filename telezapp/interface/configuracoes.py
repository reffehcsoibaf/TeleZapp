# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela de configuracoes no estilo do NVDA: busca no alto, categorias numa
lista vertical e, ao lado, as opcoes da categoria como controles nativos.

Tab vai da busca para as categorias, depois para as opcoes e para os botoes
OK, Cancelar e Aplicar. A descricao de cada opcao e falada pelo programa
logo depois do foco (F1 repete); nao e um texto da janela, porque o NVDA le
todos os textos fixos de uma janela ao abri-la.
"""
import os
import threading

import wx

from telezapp import config
from telezapp.acessibilidade.fala import bipe

from telezapp.nucleo import atalhos as nucleo_atalhos
from telezapp.nucleo import pacotes_de_som
from telezapp.nucleo.configuracoes import (CATEGORIA_BUSCA,
                                           ModeloConfiguracoes)


class DialogoConfiguracoes(wx.Dialog):
    def __init__(self, pai, cfg, aplicador, categoria_inicial=None,
                 fala=None, privacidade=None, ia=None, atalhos=None):
        """aplicador(chave, valor) executa uma mudanca (efeitos incluidos)."""
        super().__init__(pai, title="Configurações do TeleZapp",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.modelo = ModeloConfiguracoes(cfg)
        self.modelo.registro = atalhos   # funcoes que aceitam atalho
        self.lista_atalhos = None        # lista de funcoes, se aberta
        self.aplicador = aplicador
        self.fala = fala
        # contas do WhatsApp e leitura da privacidade delas (ver janela)
        self.privacidade = privacidade
        self.ia = ia                 # chaves e testes dos provedores de IA
        self.lista_sons = None       # lista de eventos de som, se aberta
        self._espera = None          # fala da descricao agendada
        self._opcao_em_foco = None
        self.Bind(wx.EVT_CHAR_HOOK, self._ao_tecla)
        self.categorias = []
        self.controles = {}          # chave -> controle
        self._montar()
        self._preencher_categorias(categoria_inicial)

    # ------------------------------------------------------------- layout
    def _montar(self):
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(self, label="&Buscar nas configurações"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.busca = wx.TextCtrl(self, name="Buscar nas configurações",
                                 size=(520, -1))
        self.busca.Bind(wx.EVT_TEXT, self._ao_buscar)
        lay.Add(self.busca, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        corpo = wx.BoxSizer(wx.HORIZONTAL)
        col = wx.BoxSizer(wx.VERTICAL)
        # Sem rotulo nem nome: o NVDA fala "lista" e o item (Avisos, 1 de 4),
        # sem repetir "categorias" antes do item.
        # ListCtrl de uma coluna, como nas configuracoes do NVDA: o ListBox
        # fazia o NVDA falar a categoria duas vezes ao chegar nele com Tab.
        self.lista = wx.ListCtrl(
            self, size=(180, 300),
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_NO_HEADER)
        self.lista.InsertColumn(0, "Categoria", width=160)
        self._trocando = False
        self.lista.Bind(wx.EVT_LIST_ITEM_SELECTED,
                        self._ao_escolher_categoria)
        col.Add(self.lista, 1, wx.EXPAND)
        corpo.Add(col, 0, wx.EXPAND | wx.ALL, 10)

        self.painel = wx.ScrolledWindow(self, size=(460, 300))
        self.painel.SetScrollRate(0, 10)
        self.lay_painel = wx.BoxSizer(wx.VERTICAL)
        self.painel.SetSizer(self.lay_painel)
        corpo.Add(self.painel, 1, wx.EXPAND | wx.TOP | wx.RIGHT | wx.BOTTOM,
                  10)
        lay.Add(corpo, 1, wx.EXPAND)


        botoes = wx.BoxSizer(wx.HORIZONTAL)
        ok = wx.Button(self, wx.ID_OK, "OK")
        cancelar = wx.Button(self, wx.ID_CANCEL, "Cancelar")
        self.btn_aplicar = wx.Button(self, wx.ID_APPLY, "&Aplicar")
        ok.SetDefault()
        for b in (ok, cancelar, self.btn_aplicar):
            botoes.Add(b, 0, wx.LEFT, 8)
        lay.Add(botoes, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        ok.Bind(wx.EVT_BUTTON, self._ao_ok)
        self.btn_aplicar.Bind(wx.EVT_BUTTON, lambda e: self._aplicar())
        self.SetSizerAndFit(lay)
        self.SetMinSize(self.GetSize())

    # --------------------------------------------------------- categorias
    def _categoria_escolhida(self):
        i = self.lista.GetFirstSelected()
        return i if 0 <= i < len(self.categorias) else -1

    def _preencher_categorias(self, escolher=None):
        atual = escolher
        i = self._categoria_escolhida()
        if atual is None and i >= 0:
            atual = self.categorias[i]
        self.categorias = self.modelo.lista_de_categorias()
        if self.modelo.busca.strip():
            atual = CATEGORIA_BUSCA
        i = self.categorias.index(atual) if atual in self.categorias else 0
        self._trocando = True
        try:
            self.lista.DeleteAllItems()
            for nome in self.categorias:
                self.lista.InsertItem(self.lista.GetItemCount(), nome)
            self.lista.Select(i)
            self.lista.Focus(i)
        finally:
            self._trocando = False
        self._mostrar_opcoes(self.categorias[i])

    def _ao_escolher_categoria(self, evento):
        if self._trocando:
            return
        i = evento.GetIndex() if evento is not None else             self._categoria_escolhida()
        if 0 <= i < len(self.categorias):
            self._mostrar_opcoes(self.categorias[i])

    def _ao_buscar(self, evento):
        self.modelo.busca = self.busca.GetValue()
        self._preencher_categorias()

    # ------------------------------------------------------------- opcoes
    def _mostrar_opcoes(self, categoria):
        self.lay_painel.Clear(delete_windows=True)
        self.controles = {}
        self.lista_sons = None
        if categoria == "Sons" and not self.modelo.busca.strip():
            self._criar_sons()          # tela propria, sem opcoes comuns
            self.painel.Layout()
            self.painel.FitInside()
            return
        self.lista_atalhos = None
        if categoria == "Atalhos" and not self.modelo.busca.strip() \
                and self.modelo.registro is not None:
            self._criar_atalhos()
            self.painel.Layout()
            self.painel.FitInside()
            return
        opcoes = self.modelo.opcoes(categoria)
        if not opcoes:
            self.lay_painel.Add(
                wx.StaticText(self.painel,
                              label="Nenhuma configuração encontrada."),
                0, wx.ALL, 8)
        for o in opcoes:
            self._criar_opcao(o)
        if categoria != CATEGORIA_BUSCA:
            for grupo in self.modelo.grupos(categoria):
                self._criar_botao_grupo(categoria, grupo)
        if categoria == "Interface" and not self.modelo.busca.strip():
            self._criar_botao_lista_conversas()
        if categoria == "Mensagens" and not self.modelo.busca.strip():
            self._criar_botao_lista_mensagens()
        if categoria == "Privacidade" and self.privacidade is not None \
                and not self.modelo.busca.strip():
            self._criar_privacidade_conta()
        if categoria == "Inteligência artificial" and self.ia is not None \
                and not self.modelo.busca.strip():
            self._criar_ia()
        self.painel.Layout()
        self.painel.FitInside()

    # ------------------------------------------------------------ atalhos
    def _criar_atalhos(self):
        """Busca, lista de funcoes com a tecla de cada uma (Enter ou duplo
        clique altera) e os botoes Alterar, Remover e Restaurar."""
        p, lay = self.painel, self.lay_painel
        for o in self.modelo.opcoes("Atalhos"):
            self._criar_opcao(o)         # Mostrar as teclas nos controles
        lay.Add(wx.StaticText(p, label="Buscar função ou atalho:"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.busca_atalhos = wx.TextCtrl(p, name="Buscar função ou atalho")
        lay.Add(self.busca_atalhos, 0, wx.EXPAND | wx.ALL, 8)
        lay.Add(wx.StaticText(p, label="Funções (Enter altera o atalho):"),
                0, wx.LEFT | wx.RIGHT, 8)
        self.lista_atalhos = wx.ListBox(p, name="Funções", size=(-1, 230))
        lay.Add(self.lista_atalhos, 1, wx.EXPAND | wx.ALL, 8)
        linha = wx.WrapSizer(wx.HORIZONTAL)
        self.btn_atalho_alterar = wx.Button(p, label="Alterar atalho...")
        self.btn_atalho_remover = wx.Button(p, label="Remover atalho")
        self.btn_atalho_padrao = wx.Button(p, label="Restaurar o padrão")
        self.btn_atalho_todos = wx.Button(p, label="Restaurar todos os padrões")
        for b in (self.btn_atalho_alterar, self.btn_atalho_remover,
                  self.btn_atalho_padrao, self.btn_atalho_todos):
            linha.Add(b, 0, wx.RIGHT | wx.BOTTOM, 8)
        lay.Add(linha, 0, wx.LEFT | wx.RIGHT, 8)
        self._atalhos_itens = []
        self.busca_atalhos.Bind(wx.EVT_TEXT,
                                lambda e: self._atalhos_preencher())
        self.lista_atalhos.Bind(wx.EVT_LISTBOX_DCLICK,
                                lambda e: self._atalhos_alterar())
        self.lista_atalhos.Bind(wx.EVT_KEY_DOWN, self._atalhos_tecla)
        self.btn_atalho_alterar.Bind(wx.EVT_BUTTON,
                                     lambda e: self._atalhos_alterar())
        self.btn_atalho_remover.Bind(wx.EVT_BUTTON,
                                     lambda e: self._atalhos_remover())
        self.btn_atalho_padrao.Bind(wx.EVT_BUTTON,
                                    lambda e: self._atalhos_padrao())
        self.btn_atalho_todos.Bind(wx.EVT_BUTTON,
                                   lambda e: self._atalhos_todos())
        self._atalhos_preencher()

    def _atalhos_texto(self, acao, canon):
        return "%s, %s: %s" % (acao.rotulo, acao.categoria,
                               nucleo_atalhos.exibir(canon) or "sem atalho")

    def _atalhos_preencher(self, manter=None):
        """Mostra as funcoes que casam com a busca; `manter` e a chave da
        funcao que continua selecionada."""
        if manter is None:
            manter = self._atalhos_chave()
        self._atalhos_itens = self.modelo.atalhos_lista(
            self.busca_atalhos.GetValue())
        itens = [self._atalhos_texto(a, c) for a, c in self._atalhos_itens] \
            or ["Nenhuma função encontrada."]
        self.lista_atalhos.Set(itens)
        chaves = [a.chave for a, _ in self._atalhos_itens]
        if chaves:
            self.lista_atalhos.SetSelection(
                chaves.index(manter) if manter in chaves else 0)
        for b in (self.btn_atalho_alterar, self.btn_atalho_remover,
                  self.btn_atalho_padrao):
            b.Enable(bool(chaves))

    def _atalhos_chave(self):
        i = self.lista_atalhos.GetSelection()
        if 0 <= i < len(self._atalhos_itens):
            return self._atalhos_itens[i][0].chave
        return None

    def _atalhos_tecla(self, evt):
        if evt.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and \
                not (evt.ControlDown() or evt.AltDown() or evt.ShiftDown()):
            self._atalhos_alterar()
            return
        evt.Skip()

    def _atalhos_dizer(self, texto):
        if self.fala is not None:
            self.fala.falar(texto, interromper=True)

    def _atalhos_alterar(self):
        from telezapp.interface import atalhos as ui_atalhos
        chave = self._atalhos_chave()
        if chave is None:
            return
        acao = self.modelo.registro.acoes[chave]
        escolha = ui_atalhos.escolher_atalho(
            self, acao.rotulo, self.modelo.atalho_de(chave),
            lambda texto, interromper=True: self._atalhos_dizer(texto))
        if escolha is None:
            return
        canon = "" if escolha == ui_atalhos.REMOVER else escolha
        self._atalhos_definir(chave, canon)

    def _atalhos_definir(self, chave, canon):
        """Poe a combinacao na funcao; se outra a usa, avisa e pergunta se
        substitui."""
        outro = self.modelo.atalho_definir(chave, canon)
        if outro is not None:
            r = wx.MessageBox(
                "O atalho %s já é usado por \"%s\" (%s). Substituir? \"%s\" "
                "ficará sem atalho." % (nucleo_atalhos.exibir(canon),
                                       outro.rotulo, outro.categoria,
                                       outro.rotulo),
                "Atalho em uso", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
                self)
            if r != wx.YES:
                self._atalhos_dizer("Atalho não alterado.")
                return
            self.modelo.atalho_definir(chave, canon, substituir=True)
        self._atalhos_preencher(chave)
        self._atalhos_dizer("Atalho %s. Aplique para valer." % (
            nucleo_atalhos.texto_falado(canon) if canon else "removido"))

    def _atalhos_remover(self):
        chave = self._atalhos_chave()
        if chave is not None:
            self._atalhos_definir(chave, "")

    def _atalhos_padrao(self):
        chave = self._atalhos_chave()
        if chave is None:
            return
        padrao = self.modelo.registro.acoes[chave].padrao
        self._atalhos_definir(chave, padrao)

    def _atalhos_todos(self):
        r = wx.MessageBox("Voltar todos os atalhos ao padrão?",
                          "Restaurar atalhos",
                          wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
        if r != wx.YES:
            return
        self.modelo.atalhos_restaurar_todos()
        self._atalhos_preencher()
        self._atalhos_dizer("Todos os atalhos voltaram ao padrão. Aplique "
                            "para valer.")

    # ----------------------------------------------- pacotes de sons
    def _criar_sons(self):
        """Caixa de pacotes, lista de eventos (Enter ou Espaco ativa e
        desativa) e, no evento, Ouvir som e, nos pacotes personalizados,
        Procurar som. Os pacotes Padrao e TeleZapp nao se editam."""
        p, lay = self.painel, self.lay_painel
        lay.Add(wx.StaticText(p, label="Pacote de sons:"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.cx_pacote = wx.Choice(p, name="Pacote de sons")
        lay.Add(self.cx_pacote, 0, wx.EXPAND | wx.ALL, 8)
        linha = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_novo_pacote = wx.Button(p, label="Novo pacote personalizado...")
        self.btn_excluir_pacote = wx.Button(p, label="Excluir este pacote")
        linha.Add(self.btn_novo_pacote, 0, wx.RIGHT, 8)
        linha.Add(self.btn_excluir_pacote, 0)
        lay.Add(linha, 0, wx.LEFT | wx.RIGHT, 8)
        lay.Add(wx.StaticText(p, label="Eventos (Enter ou Espaço ativa e "
                                       "desativa):"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.lista_sons = wx.ListBox(p, name="Eventos", size=(-1, 230))
        lay.Add(self.lista_sons, 1, wx.EXPAND | wx.ALL, 8)
        linha2 = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_ouvir_som = wx.Button(p, label="Ouvir som")
        self.btn_procurar_som = wx.Button(p, label="Procurar som...")
        linha2.Add(self.btn_ouvir_som, 0, wx.RIGHT, 8)
        linha2.Add(self.btn_procurar_som, 0)
        lay.Add(linha2, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.cx_pacote.Bind(wx.EVT_CHOICE, lambda e: self._sons_escolher_pacote())
        self.btn_novo_pacote.Bind(wx.EVT_BUTTON, lambda e: self._sons_novo())
        self.btn_excluir_pacote.Bind(wx.EVT_BUTTON,
                                     lambda e: self._sons_excluir())
        self.btn_ouvir_som.Bind(wx.EVT_BUTTON, lambda e: self._sons_ouvir())
        self.btn_procurar_som.Bind(wx.EVT_BUTTON,
                                   lambda e: self._sons_procurar())
        self._sons_preencher_pacotes()
        self._sons_preencher_eventos()

    def _sons_preencher_pacotes(self):
        est = self.modelo.sons
        self._ids_pacotes = [i for i, _ in est.pacotes()]
        self.cx_pacote.Set([n for _, n in est.pacotes()])
        if est.ativo in self._ids_pacotes:
            self.cx_pacote.SetSelection(self._ids_pacotes.index(est.ativo))

    def _sons_preencher_eventos(self, manter=0):
        est = self.modelo.sons
        itens = [est.texto_do_evento(est.ativo, e, r)
                 for e, r in pacotes_de_som.eventos()]
        self.lista_sons.Set(itens)
        self.lista_sons.SetSelection(min(max(manter, 0), len(itens) - 1))
        custom = pacotes_de_som.editavel(est.ativo)
        self.btn_procurar_som.Show(custom)       # so nos personalizados
        self.btn_excluir_pacote.Enable(custom)
        self.painel.Layout()

    def _sons_evento(self):
        i = self.lista_sons.GetSelection()
        todos = pacotes_de_som.eventos()
        return (todos[i][0], i) if 0 <= i < len(todos) else (None, -1)

    def _sons_atualizar_item(self, evento, i):
        est = self.modelo.sons
        rotulo = dict(pacotes_de_som.eventos())[evento]
        self.lista_sons.SetString(i, est.texto_do_evento(est.ativo, evento,
                                                         rotulo))

    def _sons_escolher_pacote(self):
        i = self.cx_pacote.GetSelection()
        if 0 <= i < len(self._ids_pacotes):
            self.modelo.sons.selecionar(self._ids_pacotes[i])
            self._sons_preencher_eventos()

    def _sons_alternar(self):
        evento, i = self._sons_evento()
        if evento is None:
            return
        ativado = self.modelo.sons.alternar(self.modelo.sons.ativo, evento)
        self._sons_atualizar_item(evento, i)
        if self.fala is not None:
            self.fala.falar("ativado" if ativado else "desativado",
                            interromper=True)

    def _sons_ouvir(self):
        evento, _ = self._sons_evento()
        if evento is not None:
            est = self.modelo.sons
            bipe(evento, est.valor_para_ouvir(est.ativo, evento))

    def _sons_procurar(self):
        evento, i = self._sons_evento()
        est = self.modelo.sons
        if evento is None or not pacotes_de_som.editavel(est.ativo):
            return
        dlg = wx.FileDialog(
            self, "Escolha o som para este evento",
            wildcard="Sons|*.wav;*.ogg;*.opus;*.mp3;*.flac|"
                     "Todos os arquivos|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            origem = dlg.GetPath()
        finally:
            dlg.Destroy()
        est.escolher(est.ativo, evento, origem)
        self._sons_atualizar_item(evento, i)
        if self.fala is not None:
            self.fala.falar("Som escolhido: %s. Aplique para importar para "
                            "o pacote." % os.path.basename(origem),
                            interromper=True)

    def _sons_novo(self):
        est = self.modelo.sons
        dlg = wx.TextEntryDialog(self, "Nome do novo pacote de sons:",
                                 "Novo pacote personalizado")
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            nome = dlg.GetValue()
        finally:
            dlg.Destroy()
        pacote_id, erro = est.criar(nome)
        if erro:
            wx.MessageBox(erro, "Novo pacote", wx.OK | wx.ICON_WARNING, self)
            return
        est.selecionar(pacote_id)
        self._sons_preencher_pacotes()
        self._sons_preencher_eventos()
        self.cx_pacote.SetFocus()

    def _sons_excluir(self):
        est = self.modelo.sons
        if not pacotes_de_som.editavel(est.ativo):
            return
        nome = pacotes_de_som.nome_do_pacote(est.ativo)
        r = wx.MessageBox("Excluir o pacote %s e os sons dele? Isso vale "
                          "quando você aplicar." % nome, "Excluir pacote",
                          wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
        if r != wx.YES:
            return
        est.excluir(est.ativo)
        self._sons_preencher_pacotes()
        self._sons_preencher_eventos()
        self.cx_pacote.SetFocus()

    def _criar_opcao(self, o):
        p = self.painel
        if o.numero:
            self.lay_painel.Add(wx.StaticText(p, label=o.rotulo + ":"), 0,
                                wx.LEFT | wx.RIGHT | wx.TOP, 8)
            c = wx.SpinCtrl(p, min=o.numero[0], max=o.numero[1],
                            initial=int(self.modelo.valor(o.chave)),
                            name=o.rotulo)
            c.Bind(wx.EVT_SPINCTRL, lambda e, o=o, c=c:
                   self.modelo.definir(o.chave, c.GetValue()))
            c.Bind(wx.EVT_TEXT, lambda e, o=o, c=c:
                   self.modelo.definir(o.chave, c.GetValue()))
        elif o.escolhas:
            escolhas = self.modelo.escolhas(o)
            self.lay_painel.Add(wx.StaticText(p, label=o.rotulo + ":"), 0,
                                wx.LEFT | wx.RIGHT | wx.TOP, 8)
            c = wx.Choice(p, choices=[r for _, r in escolhas],
                          name=o.rotulo)
            c.SetSelection(self.modelo.indice_da_escolha(o))
            c.Bind(wx.EVT_CHOICE, lambda e, o=o, c=c, esc=escolhas:
                   self._ao_escolher(o, esc[c.GetSelection()][0]))
        else:
            c = wx.CheckBox(p, label=o.rotulo, name=o.rotulo)
            c.SetValue(bool(self.modelo.valor(o.chave)))
            c.Bind(wx.EVT_CHECKBOX, lambda e, o=o, c=c:
                   self._ao_marcar(o, c.GetValue()))
        # A descricao nao e um texto da janela (o NVDA leria todos ao abrir):
        # e falada pelo programa pouco depois do foco, e F1 repete.
        c.Bind(wx.EVT_SET_FOCUS, lambda e, o=o: self._ao_focar(e, o))
        self.lay_painel.Add(c, 0, wx.ALL, 8)
        self.controles[o.chave] = c
        if o.chave == "trancadas_exigir_codigo":
            self._criar_campos_codigo()

    def _criar_botao_grupo(self, categoria, grupo):
        """Um botao que abre, numa janela, as opcoes que ficam juntas."""
        b = wx.Button(self.painel, label=grupo)
        b.Bind(wx.EVT_BUTTON, lambda e: self._abrir_grupo(categoria, grupo))
        self.lay_painel.Add(b, 0, wx.ALL, 8)
        self.controles["grupo:" + grupo] = b

    def _criar_botao_lista_conversas(self):
        """Botao que abre o que a lista de conversas mostra e a ordem."""
        b = wx.Button(self.painel, label="Lista de conversas")
        b.Bind(wx.EVT_BUTTON, lambda e: self._abrir_lista_conversas())
        self.lay_painel.Add(b, 0, wx.ALL, 8)
        self.controles["lista_conversas"] = b

    def _criar_botao_lista_mensagens(self):
        """Botao que abre o que a lista de mensagens mostra e a ordem."""
        b = wx.Button(self.painel, label="Lista de mensagens")
        b.Bind(wx.EVT_BUTTON, lambda e: self._abrir_lista_mensagens())
        self.lay_painel.Add(b, 0, wx.ALL, 8)
        self.controles["lista_mensagens"] = b

    def _abrir_lista_mensagens(self):
        from telezapp.interface.lista_conversas import DialogoListaConversas
        from telezapp.nucleo import lista_mensagens as lm
        dlg = DialogoListaConversas(
            self, self.modelo.lista_msg_em_uso, self.modelo.lista_msg_definir,
            self.fala, nucleo=lm, titulo="Lista de mensagens",
            explicacao="O que cada mensagem mostra na lista de uma conversa "
                       "e em que ordem. Pelo menos um item fica ativado.")
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()
        b = self.controles.get("lista_mensagens")
        if b:
            b.SetFocus()

    def _abrir_lista_conversas(self):
        from telezapp.interface.lista_conversas import DialogoListaConversas
        dlg = DialogoListaConversas(self, self.modelo.lista_em_uso,
                                    self.modelo.lista_definir, self.fala)
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()
        b = self.controles.get("lista_conversas")
        if b:
            b.SetFocus()

    def _abrir_grupo(self, categoria, grupo):
        dlg = DialogoGrupoOpcoes(
            self, grupo, self.modelo.opcoes_do_grupo(categoria, grupo))
        dlg.ShowModal()
        dlg.Destroy()
        b = self.controles.get("grupo:" + grupo)
        if b:
            b.SetFocus()

    # ------------------------------------ provedores de IA
    def _criar_ia(self):
        """Ordem dos provedores de cada tarefa e, depois, um botao por
        provedor que abre a janela dele (chave, modelo e testes)."""
        from telezapp.nucleo.ia import catalogo
        p = self.painel
        self._ia_listas = {}
        self._ia_botoes = {}
        self.lay_painel.Add(wx.StaticText(
            p, label="Provedores de cada tarefa: marque os que podem "
                     "receber os arquivos e ponha na ordem em que devem ser "
                     "tentados. Se um falhar, o TeleZapp passa para o "
                     "próximo. Sem nenhum marcado, a tarefa fica desligada."),
            0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        for tarefa in catalogo.TAREFAS:
            nome = catalogo.NOMES_DE_TAREFA[tarefa]
            capazes = catalogo.provedores_da_tarefa(tarefa)
            nomes = dict(capazes)
            ligados = [c for c in self.modelo.ia_ordem(tarefa) if c in nomes]
            chaves = ligados + [c for c, _ in capazes if c not in ligados]
            self.lay_painel.Add(wx.StaticText(p, label=nome + ":"), 0,
                                wx.LEFT | wx.RIGHT | wx.TOP, 8)
            lista = wx.CheckListBox(p, choices=[nomes[c] for c in chaves],
                                    size=(380, -1), name=nome)
            for k, c in enumerate(chaves):
                lista.Check(k, c in ligados)
            if chaves:
                lista.SetSelection(0)
            self._ia_listas[tarefa] = (lista, chaves)
            lista.Bind(wx.EVT_CHECKLISTBOX, lambda e, t=tarefa:
                       self._ia_ordem_mudou(t))
            linha = wx.BoxSizer(wx.HORIZONTAL)
            linha.Add(lista, 0, wx.RIGHT, 8)
            for rotulo, passo in (("Subir", -1), ("Descer", 1)):
                b = wx.Button(p, label="%s na ordem: %s" % (rotulo, nome))
                b.Bind(wx.EVT_BUTTON, lambda e, t=tarefa, d=passo:
                       self._ia_mover(t, d))
                linha.Add(b, 0, wx.RIGHT | wx.ALIGN_BOTTOM, 6)
            self.lay_painel.Add(linha, 0, wx.LEFT | wx.RIGHT, 8)
        self.lay_painel.Add(wx.StaticText(
            p, label="Provedores (chave e modelo de cada um):"), 0,
            wx.LEFT | wx.RIGHT | wx.TOP, 12)
        for prov in catalogo.PROVEDORES.values():
            b = wx.Button(p, label=self._rotulo_provedor_ia(prov.chave))
            b.Bind(wx.EVT_BUTTON, lambda e, k=prov.chave:
                   self._configurar_provedor_ia(k))
            self._ia_botoes[prov.chave] = b
            self.lay_painel.Add(b, 0, wx.ALL, 6)

    def _rotulo_provedor_ia(self, provedor):
        """"Google Gemini: chave guardada, modelo automático..." """
        from telezapp.nucleo.ia import catalogo
        pendentes = self.modelo.ia_chaves
        if provedor in pendentes:
            chave = ("chave será apagada ao aplicar"
                     if pendentes[provedor] == "" else
                     "chave nova, será guardada ao aplicar")
        else:
            chave = "chave guardada" if self.ia.tem(provedor) else "sem chave"
        escolhido = self.modelo.ia_modelos.get(
            provedor, self.ia.modelo(provedor))
        return "%s: %s, modelo %s. Configurar..." % (
            catalogo.PROVEDORES[provedor].nome, chave,
            escolhido or "automático")

    def _atualizar_botoes_ia(self):
        for provedor, botao in getattr(self, "_ia_botoes", {}).items():
            try:
                botao.SetLabel(self._rotulo_provedor_ia(provedor))
            except RuntimeError:
                pass         # a categoria foi trocada e os botoes sumiram

    def _configurar_provedor_ia(self, provedor):
        dlg = DialogoProvedorIA(self, provedor, self.ia, self.fala,
                                self.modelo.ia_modelos.get(
                                    provedor, self.ia.modelo(provedor)),
                                provedor in self.modelo.ia_chaves and
                                self.modelo.ia_chaves[provedor] == "")
        try:
            if dlg.ShowModal() == wx.ID_OK:
                if dlg.apagar:
                    self.modelo.ia_apagar_chave(provedor)
                else:
                    self.modelo.ia_definir_chave(provedor, dlg.chave)
                self.modelo.ia_definir_modelo(provedor, dlg.modelo)
        finally:
            dlg.Destroy()
        self._atualizar_botoes_ia()
        botao = self._ia_botoes.get(provedor)
        if botao is not None:
            botao.SetFocus()

    def _depois_de_aplicar_ia(self):
        """Aplicado: as chaves digitadas ja estao guardadas; os botoes leem a
        situacao de novo."""
        self._atualizar_botoes_ia()

    def _ia_ordem_mudou(self, tarefa):
        lista, chaves = self._ia_listas[tarefa]
        self.modelo.ia_definir_ordem(tarefa, [
            c for k, c in enumerate(chaves) if lista.IsChecked(k)])

    def _ia_mover(self, tarefa, passo):
        lista, chaves = self._ia_listas[tarefa]
        i = lista.GetSelection()
        j = i + passo
        if i < 0 or not 0 <= j < len(chaves):
            if self.fala is not None:
                self.fala.falar("Não dá para mover mais nessa direção.",
                                interromper=True)
            return
        marcas = [lista.IsChecked(k) for k in range(len(chaves))]
        nomes = [lista.GetString(k) for k in range(len(chaves))]
        chaves[i], chaves[j] = chaves[j], chaves[i]
        marcas[i], marcas[j] = marcas[j], marcas[i]
        nomes[i], nomes[j] = nomes[j], nomes[i]
        for k in range(len(chaves)):
            lista.SetString(k, nomes[k])
            lista.Check(k, marcas[k])
        lista.SetSelection(j)
        self._ia_ordem_mudou(tarefa)
        if self.fala is not None:
            self.fala.falar("%s, posição %d de %d." % (
                nomes[j], j + 1, len(chaves)), interromper=True)

    # ------------------------------------ privacidade das contas
    def _criar_privacidade_conta(self):
        """Escolhas de privacidade da conta (ficam no servico, nao no
        TeleZapp), lidas ao abrir a categoria. Com mais de uma conta, uma
        caixa escolhe qual; cada servico mostra os campos que tem."""
        from telezapp.nucleo import privacidade_conta as pw
        p = self.painel
        contas = self.privacidade.contas()
        self.lay_painel.Add(wx.StaticText(
            p, label="Privacidade das contas (WhatsApp e Telegram)"), 0,
            wx.LEFT | wx.RIGHT | wx.TOP, 8)
        if not contas:
            self.lay_painel.Add(wx.StaticText(
                p, label="Conecte uma conta do WhatsApp ou do Telegram para "
                         "ver e mudar estas opções."), 0, wx.ALL, 8)
            return
        self._priv_contas = contas
        self._priv_conta = contas[0][0]
        if len(contas) > 1:
            self.lay_painel.Add(wx.StaticText(p, label="Conta:"), 0,
                                wx.LEFT | wx.RIGHT | wx.TOP, 8)
            sel = wx.Choice(p, choices=[r for _, r, _ in contas],
                            name="Conta")
            sel.SetSelection(0)
            sel.Bind(wx.EVT_CHOICE, lambda e, s=sel: self._trocar_conta_priv(
                self._priv_contas[s.GetSelection()][0]))
            self.lay_painel.Add(sel, 0, wx.ALL, 8)
        self._priv_caixas = {}
        for campo in pw.CAMPOS:
            rot = wx.StaticText(p, label=campo.rotulo + ":")
            c = wx.Choice(p, choices=[r for _, r in campo.opcoes],
                          name=campo.rotulo)
            c.Bind(wx.EVT_CHOICE, lambda e, k=campo.nome, c=c:
                   self.modelo.priv_definir(self._priv_conta, k,
                                            c.GetSelection()))
            self.lay_painel.Add(rot, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
            self.lay_painel.Add(c, 0, wx.ALL, 8)
            self._priv_caixas[campo.nome] = (rot, c)
        self._priv_rot_status = wx.StaticText(
            p, label="Quem pode ver meu status (só leitura; para mudar, "
                     "use o celular):")
        self._priv_status = wx.TextCtrl(
            p, name="Quem pode ver meu status", style=wx.TE_READONLY,
            size=(300, -1))
        self.lay_painel.Add(self._priv_rot_status, 0,
                            wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.lay_painel.Add(self._priv_status, 0, wx.ALL, 8)
        self._trocar_conta_priv(self._priv_conta)

    def _trocar_conta_priv(self, conta_id):
        """Mostra nas caixas o que a conta tem. A leitura vai ao servico e
        pode demorar, entao roda fora da janela: enquanto isso as caixas
        ficam apagadas e a categoria abre e responde na hora."""
        self._priv_conta = conta_id
        cache = getattr(self, "_priv_cache", None)
        if cache is None:
            cache = self._priv_cache = {}
        self._priv_ficha = getattr(self, "_priv_ficha", 0) + 1
        ficha = self._priv_ficha
        if conta_id in cache:
            self._priv_aplicar(conta_id, cache[conta_id])
            return
        for rot, c in self._priv_caixas.values():
            c.Enable(False)
        self._priv_rot_status.Show(True)
        self._priv_status.Show(True)
        self._priv_status.SetValue("Lendo a privacidade da conta...")
        self.painel.Layout()

        def ler():
            try:
                lido = self.privacidade.ler(conta_id) or {}
            except Exception:
                lido = {}
            wx.CallAfter(self._priv_lido, ficha, conta_id, lido)
        threading.Thread(target=ler, daemon=True, name="privacidade").start()

    def _priv_lido(self, ficha, conta_id, lido):
        if not self or ficha != self._priv_ficha:
            return      # a janela fechou ou a pessoa trocou de conta
        self._priv_cache[conta_id] = lido
        self._priv_aplicar(conta_id, lido)
        if self.fala is not None:
            self.fala.falar("Privacidade da conta carregada.")

    def _priv_aplicar(self, conta_id, lido):
        from telezapp.nucleo import privacidade_conta as pw
        valores = lido.get("valores")
        campos = {c.nome: c for c in pw.campos_do(lido.get("servico"))}
        for nome, (rot, caixa) in self._priv_caixas.items():
            visivel = nome in campos
            rot.Show(visivel)
            caixa.Show(visivel)
            if visivel:
                rot.SetLabel(campos[nome].rotulo + ":")
        tem_status = bool(lido.get("status"))
        self._priv_rot_status.Show(tem_status)
        self._priv_status.Show(tem_status)
        if pw.ilegivel(valores):
            for rot, c in self._priv_caixas.values():
                c.Enable(False)
            self._priv_rot_status.Show(True)
            self._priv_status.Show(True)
            self._priv_status.SetValue("Não consegui ler a privacidade desta "
                                       "conta agora.")
            self.painel.Layout()
            return
        self.modelo.priv_carregado[conta_id] = valores
        escolhido = self.modelo.priv_escolhido.get(conta_id, {})
        for nome, campo in campos.items():
            caixa = self._priv_caixas[nome][1]
            caixa.Enable(True)
            i = escolhido.get(nome, pw.indice(campo, valores.get(nome)))
            if i >= 0:
                caixa.SetSelection(i)
        self._priv_status.SetValue(lido.get("status") or "")
        self.painel.Layout()
        self.painel.FitInside()

    # ------------------------------------------- codigo das trancadas
    def _criar_campos_codigo(self):
        """Campos do codigo secreto, logo depois da caixa: o codigo atual
        (se ja existe) e o novo, duas vezes. Os novos so aparecem com a
        caixa marcada."""
        p = self.painel
        guardado = bool(self.modelo.cfg.get("codigo_trancadas"))
        self.campos_codigo = {}
        for campo, rotulo, existe in (
                ("atual", "Código atual", guardado),
                ("novo", "Novo código (4 a 12 números)", True),
                ("repita", "Repita o novo código", True)):
            rot = wx.StaticText(p, label=rotulo + ":")
            ctrl = wx.TextCtrl(p, name=rotulo, style=wx.TE_PASSWORD,
                               size=(240, -1))
            ctrl.SetValue(self.modelo.codigo[campo])
            ctrl.Bind(wx.EVT_TEXT, lambda e, k=campo, c=ctrl:
                      self.modelo.definir_codigo(k, c.GetValue()))
            self.lay_painel.Add(rot, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
            self.lay_painel.Add(ctrl, 0, wx.ALL, 8)
            self.campos_codigo[campo] = (rot, ctrl, existe)
        self._mostrar_campos_codigo()

    def _mostrar_campos_codigo(self):
        marcada = bool(self.modelo.valor("trancadas_exigir_codigo"))
        for campo, (rot, ctrl, existe) in self.campos_codigo.items():
            # o atual aparece sempre que ha codigo (ele e pedido tambem para
            # desligar); os novos, so com a exigencia marcada
            visivel = existe if campo == "atual" else marcada
            rot.Show(visivel)
            ctrl.Show(visivel)
        self.painel.Layout()
        self.painel.FitInside()

    def _ao_marcar(self, opcao, valor):
        self.modelo.definir(opcao.chave, valor)
        if opcao.chave == "trancadas_exigir_codigo":
            self._mostrar_campos_codigo()

    def _ao_focar(self, evento, opcao):
        evento.Skip()
        self._opcao_em_foco = opcao
        if self._espera is not None:
            self._espera.Stop()
        if self.fala is not None and self.modelo.valor("falar_descricoes"):
            self._espera = wx.CallLater(400, self.fala.falar,
                                        opcao.descricao)

    def _ao_tecla(self, evento):
        if (evento.GetKeyCode() == wx.WXK_F1 and self.fala is not None
                and self._opcao_em_foco is not None
                and self.FindFocus() in self.controles.values()):
            self.fala.falar(self._opcao_em_foco.descricao, interromper=True)
            return
        if evento.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER,
                                   wx.WXK_SPACE) and \
                not evento.HasModifiers() and \
                getattr(self, "lista_sons", None) is not None and \
                self.FindFocus() is self.lista_sons:
            self._sons_alternar()          # Enter ativa e desativa o evento
            return
        if (evento.GetKeyCode() == wx.WXK_DOWN and not evento.HasModifiers()
                and self.FindFocus() is self.busca):
            # Seta para baixo na busca leva ao primeiro resultado; sem
            # resultado, as categorias.
            alvo = next(iter(self.controles.values()), None) \
                if self.modelo.busca.strip() else None
            (alvo or self.lista).SetFocus()
            return
        evento.Skip()

    def _ao_escolher(self, opcao, valor):
        self.modelo.definir(opcao.chave, valor)
        if opcao.chave == "audio_passo_velocidade":
            # a lista de velocidades depende do passo: refaz as opcoes
            i = self._categoria_escolhida()
            if i >= 0:
                self._mostrar_opcoes(self.categorias[i])
                c = self.controles.get(opcao.chave)
                if c is not None:
                    c.SetFocus()

    # ------------------------------------------------------------ botoes
    def _aplicar(self):
        """False (e nada aplicado) se o codigo secreto esta errado."""
        erro = self.modelo.erro_codigo()
        if erro:
            if self.fala is not None:
                self.fala.falar(erro, interromper=True)
            else:
                wx.MessageBox(erro, "Configurações", wx.OK | wx.ICON_WARNING,
                              self)
            campos = getattr(self, "campos_codigo", {})
            alvo = campos.get("atual" if "atual" in erro else "novo")
            if alvo is not None:
                alvo[1].SetFocus()
            return False
        self.modelo.aplicar(self.aplicador)
        self._depois_de_aplicar_ia()
        return True

    def _ao_ok(self, evento):
        if self._aplicar():
            self.EndModal(wx.ID_OK)


class DialogoGrupoOpcoes(wx.Dialog):
    """As opcoes de um grupo (caixas de marcar), numa janela propria. O que
    for marcado vale como pendente na janela de configuracoes: so entra ao
    apertar OK ou Aplicar la."""

    def __init__(self, pai, titulo, opcoes):
        super().__init__(pai, title=titulo, style=wx.DEFAULT_DIALOG_STYLE)
        self.pai = pai
        self._em_foco = None
        self.caixas = {}
        lay = wx.BoxSizer(wx.VERTICAL)
        for o in opcoes:
            c = wx.CheckBox(self, label=o.rotulo, name=o.rotulo)
            c.SetValue(bool(pai.modelo.valor(o.chave)))
            c.Bind(wx.EVT_CHECKBOX, lambda e, o=o, c=c:
                   pai.modelo.definir(o.chave, c.GetValue()))
            c.Bind(wx.EVT_SET_FOCUS, lambda e, o=o: self._ao_focar(e, o))
            lay.Add(c, 0, wx.ALL, 8)
            self.caixas[o.chave] = c
        fechar = wx.Button(self, wx.ID_OK, "Fechar")
        fechar.SetDefault()
        lay.Add(fechar, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetEscapeId(wx.ID_OK)
        self.SetSizerAndFit(lay)
        self.Bind(wx.EVT_CHAR_HOOK, self._ao_tecla)
        self.CentreOnParent()

    def _ao_focar(self, evento, opcao):
        evento.Skip()
        self._em_foco = opcao
        pai = self.pai
        if pai._espera is not None:
            pai._espera.Stop()
        if pai.fala is not None and pai.modelo.valor("falar_descricoes"):
            pai._espera = wx.CallLater(400, pai.fala.falar, opcao.descricao)

    def _ao_tecla(self, evento):
        if evento.GetKeyCode() == wx.WXK_F1 and self.pai.fala is not None \
                and self._em_foco is not None:
            self.pai.fala.falar(self._em_foco.descricao, interromper=True)
            return
        evento.Skip()


class DialogoProvedorIA(wx.Dialog):
    """Chave e modelo de um provedor de IA, com Obter modelos e Testar. As
    mudancas so entram nas configuracoes ao apertar OK aqui e, depois, OK ou
    Aplicar nas configuracoes."""

    AUTOMATICO = "(Automático)"

    def __init__(self, pai, provedor, ia, fala, modelo_atual, apagar_antes):
        from telezapp.nucleo.ia import catalogo
        prov = catalogo.PROVEDORES[provedor]
        super().__init__(pai, title="Configurar " + prov.nome,
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.prov, self.ia, self.fala = prov, ia, fala
        self.chave, self.apagar = "", bool(apagar_antes)
        self.modelo = ""
        lay = wx.BoxSizer(wx.VERTICAL)
        self.situacao = wx.StaticText(self, label="")
        lay.Add(self.situacao, 0, wx.ALL, 10)
        lay.Add(wx.StaticText(
            self, label="Chave (vazio mantém a atual; ela fica cifrada "
                        "neste computador e não vai no backup):"), 0,
            wx.LEFT | wx.RIGHT, 10)
        self.campo = wx.TextCtrl(self, style=wx.TE_PASSWORD, size=(420, -1),
                                 name="Chave")
        self.campo.Bind(wx.EVT_TEXT, lambda e: self._atualizar())
        lay.Add(self.campo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        lay.Add(wx.StaticText(self, label="Modelo:"), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.combo = wx.ComboBox(
            self, choices=[self.AUTOMATICO] + ia.lista_de_modelos(provedor),
            style=wx.CB_DROPDOWN, size=(420, -1), name="Modelo")
        self.combo.SetValue(modelo_atual or self.AUTOMATICO)
        lay.Add(self.combo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        lay.Add(wx.StaticText(
            self, label="Automático: " + ", depois ".join(
                (prov.modelo,) + prov.alternativos)), 0,
            wx.LEFT | wx.RIGHT | wx.TOP, 10)
        linha = wx.WrapSizer(wx.HORIZONTAL)
        for rotulo, funcao in (
                ("&Obter modelos", self._obter_modelos),
                ("&Testar", self._testar),
                ("&Apagar a chave", self._apagar),
                ("&Onde conseguir a chave", lambda: ia.abrir(prov.url_chave)),
                ("Política de &privacidade",
                 lambda: ia.abrir(prov.url_privacidade))):
            b = wx.Button(self, label=rotulo)
            b.Bind(wx.EVT_BUTTON, lambda e, f=funcao: f())
            linha.Add(b, 0, wx.RIGHT | wx.TOP, 6)
        lay.Add(linha, 0, wx.ALL, 10)
        lay.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0,
                wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.Bind(wx.EVT_BUTTON, self._ok, id=wx.ID_OK)
        self.CentreOnParent()
        self._atualizar()
        self.campo.SetFocus()

    def _atualizar(self):
        if self.apagar and not self.campo.GetValue().strip():
            texto = "a chave guardada será apagada ao aplicar"
        elif self.campo.GetValue().strip():
            texto = "chave digitada, será guardada ao aplicar"
            self.apagar = False
        else:
            texto = ("chave guardada" if self.ia.tem(self.prov.chave)
                     else "sem chave")
        self.situacao.SetLabel("%s: %s" % (self.prov.nome, texto))

    def _modelo_do_combo(self):
        valor = self.combo.GetValue().strip()
        return "" if valor == self.AUTOMATICO else valor

    def _ok(self, evt):
        self.chave = self.campo.GetValue().strip()
        self.modelo = self._modelo_do_combo()
        evt.Skip()

    def _apagar(self):
        self.apagar = True
        self.campo.ChangeValue("")
        self._atualizar()
        if self.fala is not None:
            self.fala.falar("A chave será apagada quando você aplicar.",
                            interromper=True)

    def _falar(self, texto):
        if self.fala is not None:
            self.fala.falar(texto, interromper=True)

    def _testar(self):
        self._falar("Testando a conexão...")
        chave, modelo = self.campo.GetValue(), self._modelo_do_combo()

        def trabalho():
            ok, texto = self.ia.testar(self.prov.chave, chave, modelo)
            wx.CallAfter(self._mostrar, "Testar", ok, texto)
        threading.Thread(target=trabalho, daemon=True,
                         name="testar-ia").start()

    def _obter_modelos(self):
        self._falar("Obtendo a lista de modelos...")
        chave = self.campo.GetValue()

        def trabalho():
            ok, resultado = self.ia.obter_modelos(self.prov.chave, chave)
            wx.CallAfter(self._modelos_obtidos, ok, resultado)
        threading.Thread(target=trabalho, daemon=True,
                         name="obter-modelos").start()

    def _modelos_obtidos(self, ok, resultado):
        if not self:
            return
        if not ok:
            self._mostrar("Obter modelos", False, resultado)
            return
        atual = self.combo.GetValue()
        self.combo.Set([self.AUTOMATICO] + resultado)
        self.combo.SetValue(atual)
        self._falar("%d modelos encontrados. Abra a caixa e escolha um, ou "
                    "deixe em automático." % len(resultado))
        self.combo.SetFocus()

    def _mostrar(self, titulo, ok, texto):
        if not self:
            return
        self._falar(texto)
        wx.MessageBox(texto, titulo, wx.OK | (
            wx.ICON_INFORMATION if ok else wx.ICON_WARNING), self)

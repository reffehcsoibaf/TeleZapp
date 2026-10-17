# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Janela de configuracoes no estilo do NVDA: busca no alto, categorias numa
lista vertical e, ao lado, as opcoes da categoria como controles nativos.

Tab vai da busca para as categorias, depois para as opcoes e para os botoes
OK, Cancelar e Aplicar. A descricao de cada opcao e falada pelo programa
logo depois do foco (F1 repete); nao e um texto da janela, porque o NVDA le
todos os textos fixos de uma janela ao abri-la.
"""
import threading

import wx

from telezapp.nucleo.configuracoes import (CATEGORIA_BUSCA,
                                           ModeloConfiguracoes)


class DialogoConfiguracoes(wx.Dialog):
    def __init__(self, pai, cfg, aplicador, categoria_inicial=None,
                 fala=None, privacidade=None):
        """aplicador(chave, valor) executa uma mudanca (efeitos incluidos)."""
        super().__init__(pai, title="Configurações do TeleZapp",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.modelo = ModeloConfiguracoes(cfg)
        self.aplicador = aplicador
        self.fala = fala
        # contas do WhatsApp e leitura da privacidade delas (ver janela)
        self.privacidade = privacidade
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
        opcoes = self.modelo.opcoes(categoria)
        if not opcoes:
            self.lay_painel.Add(
                wx.StaticText(self.painel,
                              label="Nenhuma configuração encontrada."),
                0, wx.ALL, 8)
        for o in opcoes:
            self._criar_opcao(o)
        if categoria == "Privacidade" and self.privacidade is not None \
                and not self.modelo.busca.strip():
            self._criar_privacidade_conta()
        self.painel.Layout()
        self.painel.FitInside()

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
        return True

    def _ao_ok(self, evento):
        if self._aplicar():
            self.EndModal(wx.ID_OK)

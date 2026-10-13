# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Janela principal: conversas, mensagens e caixa de digitacao.

So conversa com o resto do app pelo gerenciador de contas (pedidos) e pelos
eventos (respostas). O registro grava acoes e focos, nunca o texto das
mensagens.
"""
import logging
import os
import subprocess
import threading
import time
import traceback

import wx

from telezapp import NOME, VERSAO, config
from telezapp.acessibilidade.fala import Fala, bipe
from telezapp.interface import dialogos
from telezapp.nucleo import eventos as ev
from telezapp.nucleo import modelos as m

log = logging.getLogger("telezapp.janela")

MARCADOR = "marcador"
TEXTO_SEM_CONVERSA = "Nenhuma conversa aberta. Aperte Enter numa conversa."
TEXTO_SEM_MENSAGENS = "Esta conversa ainda não tem mensagens."
TEXTO_CARREGANDO = "Carregando mensagens..."
TEXTO_SEM_CONTAS = "Nenhuma conversa ainda. Use o menu Arquivo para " \
                   "adicionar uma conta do Telegram ou do WhatsApp."
LIMITE_CACHE = 100        # mensagens lidas do banco ao abrir a conversa
LIMITE_MEMORIA = 1200     # mensagens mantidas na memoria por conversa

AJUDA = """\
ESTRUTURA DA JANELA
A janela tem três áreas, nesta ordem de Tab: Conversas, Mensagens e a caixa
Digite sua mensagem, seguida do botão Enviar.

ATALHOS
Control 1: ir para a lista de conversas
Control 2: ir para a lista de mensagens
Control 3: ir para a caixa de digitação
Control U: ir para a próxima conversa com mensagens não lidas
Control R: ouvir a última mensagem da conversa aberta
F5: atualizar a lista de conversas
Control Shift R: responder à mensagem selecionada
Control Shift C: copiar o texto da mensagem selecionada
Alt Enter: ver os detalhes e o texto completo da mensagem selecionada
Tecla Aplicativos ou Shift F10: menu da mensagem selecionada

NA LISTA DE CONVERSAS
Setas: percorrem as conversas (cada uma é lida com o número de não lidas).
Enter: abre a conversa e leva o foco para as mensagens: para o item "Início
das mensagens não lidas", se houver não lidas, ou para a última mensagem.

NA LISTA DE MENSAGENS
Esc: volta para a lista de conversas (também funciona na caixa de digitação).
Enter: mostra os detalhes e o texto completo da mensagem.

NA CAIXA DE DIGITAÇÃO
Enter: envia. Shift Enter: nova linha. Esc: cancela a resposta, se houver,
ou volta para a lista de conversas.

MENU EXIBIÇÃO
Escolha como cada mensagem é lida (autor e hora primeiro, conteúdo primeiro
ou autor só quando muda) e ligue ou desligue o som e a fala das mensagens
novas.
"""


def seguro(funcao):
    """Registra qualquer erro de um tratador, sem derrubar a janela."""
    def interno(*args, **kwargs):
        try:
            return funcao(*args, **kwargs)
        except Exception:
            log.error("erro em %s:\n%s", funcao.__name__,
                      traceback.format_exc())
    interno.__name__ = funcao.__name__
    return interno


class Janela(wx.Frame):
    def __init__(self, cfg, banco, barramento):
        super().__init__(None, title=NOME, size=(1000, 700))
        self.cfg = cfg
        self.banco = banco
        self.contas = None            # definido por quem cria a janela
        self.fala = Fala()
        self.conversas = []           # ordenadas pela ultima mensagem
        self._chaves_conv = []        # chave de cada item da lista
        self.indice = {}              # chave -> Conversa
        self.cache = {}               # chave da conversa -> [Mensagem]
        self.atual = None             # chave da conversa aberta
        self.marcador_n = 0           # nao lidas ao abrir a conversa
        self.marcador_id = None       # id da 1a nao lida (quando conhecido)
        self.esperando_servidor = False
        self.selecao_automatica = True
        self.mapa = [None]            # por item da lista: msg id, MARCADOR...
        self.resposta_a = None
        self.locais = 0               # contador de mensagens "enviando"
        self.estados = {}             # conta_id -> estado
        self.pareamentos = {}         # conta_id -> DialogoPareamento
        self.pareamento_recusado = set()
        self.estilo = cfg.get("estilo")
        self._criar_menus()
        self._criar_controles()
        self.CreateStatusBar()
        self.Bind(wx.EVT_CLOSE, self._ao_fechar)
        self.Bind(wx.EVT_CHAR_HOOK, self._char_hook)
        barramento.ouvir(self._ao_evento)
        self.lista_msgs.Set([TEXTO_SEM_CONVERSA])
        self.Centre()

    # ============================================================ montagem
    def _criar_menus(self):
        barra = wx.MenuBar()
        self.itens = {}

        def item(menu, chave, rotulo, tipo="normal"):
            if tipo == "check":
                it = menu.AppendCheckItem(wx.ID_ANY, rotulo)
            elif tipo == "radio":
                it = menu.AppendRadioItem(wx.ID_ANY, rotulo)
            else:
                it = menu.Append(wx.ID_ANY, rotulo)
            self.itens[chave] = it
            return it

        m_arq = wx.Menu()
        item(m_arq, "add_tg", "Adicionar conta do &Telegram...")
        item(m_arq, "add_wa", "Adicionar conta do &WhatsApp...")
        item(m_arq, "reconectar", "&Conectar as contas de novo")
        item(m_arq, "remover", "&Remover uma conta...")
        m_arq.AppendSeparator()
        item(m_arq, "logs", "Abrir a pasta de &logs")
        m_arq.AppendSeparator()
        item(m_arq, "sair", "&Sair\tCtrl+Q")
        barra.Append(m_arq, "&Arquivo")

        m_conv = wx.Menu()
        item(m_conv, "ir_conv", "Ir para a lista de &conversas\tCtrl+1")
        item(m_conv, "ir_msgs", "Ir para a lista de &mensagens\tCtrl+2")
        item(m_conv, "ir_caixa", "Ir para a caixa de &digitação\tCtrl+3")
        m_conv.AppendSeparator()
        item(m_conv, "abrir_conv", "&Abrir a conversa selecionada")
        item(m_conv, "proxima", "Próxima conversa &não lida\tCtrl+U")
        item(m_conv, "ler_ultima", "&Ouvir a última mensagem\tCtrl+R")
        item(m_conv, "atualizar", "A&tualizar a lista de conversas\tF5")
        barra.Append(m_conv, "&Conversa")

        m_msg = wx.Menu()
        item(m_msg, "responder", "&Responder\tCtrl+Shift+R")
        item(m_msg, "copiar", "&Copiar texto\tCtrl+Shift+C")
        item(m_msg, "detalhes", "&Detalhes\tAlt+Enter")
        barra.Append(m_msg, "&Mensagem")

        m_exib = wx.Menu()
        for est, nome in m.NOMES_ESTILOS.items():
            it = item(m_exib, "estilo%d" % est, nome, "radio")
            self.Bind(wx.EVT_MENU,
                      lambda e, est=est: self._mudar_estilo(est), it)
        m_exib.AppendSeparator()
        item(m_exib, "som", "&Som ao receber mensagem", "check")
        item(m_exib, "falar_novas", "&Falar mensagens novas", "check")
        item(m_exib, "confirmar_envio", "Confirmar envio por &voz", "check")
        barra.Append(m_exib, "&Exibição")

        m_aj = wx.Menu()
        item(m_aj, "ajuda", "&Teclas de atalho\tF1")
        item(m_aj, "sobre", "&Sobre o %s" % NOME)
        barra.Append(m_aj, "A&juda")
        self.SetMenuBar(barra)

        ligacoes = {
            "add_tg": lambda e: self.adicionar_conta("telegram"),
            "add_wa": lambda e: self.adicionar_conta("whatsapp"),
            "reconectar": lambda e: self._reconectar(),
            "remover": lambda e: self._remover_conta(),
            "logs": lambda e: self._abrir_logs(),
            "sair": lambda e: self.Close(),
            "ir_conv": lambda e: self._ir_para(self.lista_conv, "conversas"),
            "ir_msgs": lambda e: self._ir_para(self.lista_msgs, "mensagens"),
            "ir_caixa": lambda e: self._ir_para(self.caixa, "caixa"),
            "abrir_conv": lambda e: self._abrir_selecionada_na_lista(),
            "proxima": lambda e: self._proxima_nao_lida(),
            "ler_ultima": lambda e: self._ler_ultima(),
            "atualizar": lambda e: self._atualizar_conversas(),
            "responder": lambda e: self._responder(),
            "copiar": lambda e: self._copiar(),
            "detalhes": lambda e: self._detalhes(),
            "ajuda": lambda e: dialogos.mostrar_texto(
                self, "Teclas de atalho", AJUDA, "Teclas de atalho"),
            "sobre": lambda e: self._sobre(),
        }
        for chave, tratador in ligacoes.items():
            self.Bind(wx.EVT_MENU, seguro(tratador), self.itens[chave])
        for chave in ("som", "falar_novas", "confirmar_envio"):
            self.itens[chave].Check(bool(self.cfg.get(chave)))
            self.Bind(wx.EVT_MENU,
                      lambda e, k=chave: self._opcao(k, e.IsChecked()),
                      self.itens[chave])
        self.itens["estilo%d" % self.estilo].Check(True)

    def _criar_controles(self):
        painel = wx.Panel(self)
        rot_conv = wx.StaticText(painel, label="Conversas")
        self.lista_conv = wx.ListBox(painel, style=wx.LB_SINGLE | wx.LB_HSCROLL,
                                     name="Conversas")
        self.rot_msgs = wx.StaticText(painel, label="Mensagens")
        self.lista_msgs = wx.ListBox(painel, style=wx.LB_SINGLE | wx.LB_HSCROLL,
                                     name="Mensagens")
        self.rot_caixa = wx.StaticText(painel, label="Digite sua mensagem")
        self.caixa = wx.TextCtrl(painel, style=wx.TE_MULTILINE,
                                 name="Digite sua mensagem")
        self.botao_enviar = wx.Button(painel, label="&Enviar")

        esq = wx.BoxSizer(wx.VERTICAL)
        esq.Add(rot_conv, 0, wx.BOTTOM, 4)
        esq.Add(self.lista_conv, 1, wx.EXPAND)
        dir_ = wx.BoxSizer(wx.VERTICAL)
        dir_.Add(self.rot_msgs, 0, wx.BOTTOM, 4)
        dir_.Add(self.lista_msgs, 3, wx.EXPAND)
        dir_.Add(self.rot_caixa, 0, wx.TOP | wx.BOTTOM, 4)
        dir_.Add(self.caixa, 1, wx.EXPAND)
        dir_.Add(self.botao_enviar, 0, wx.TOP, 6)
        raiz = wx.BoxSizer(wx.HORIZONTAL)
        raiz.Add(esq, 1, wx.EXPAND | wx.ALL, 8)
        raiz.Add(dir_, 2, wx.EXPAND | wx.ALL, 8)
        painel.SetSizer(raiz)

        self.lista_conv.Bind(wx.EVT_LISTBOX_DCLICK,
                             seguro(lambda e: self._abrir_selecionada_na_lista()))
        self.lista_msgs.Bind(wx.EVT_CONTEXT_MENU, seguro(self._menu_mensagem))
        self.lista_msgs.Bind(wx.EVT_KEY_DOWN, self._tecla_mensagens)
        self.botao_enviar.Bind(wx.EVT_BUTTON,
                               seguro(lambda e: self._enviar_texto()))

    # ============================================================== inicio
    def comecar(self):
        """Mostra as conversas guardadas e liga as contas."""
        for dados in self.cfg.contas():
            self._juntar_conversas(dados["id"], self.banco.conversas(
                dados["id"]))
        self._preencher_conversas()
        self.contas.iniciar_salvas()
        if not self.cfg.contas():
            self.lista_conv.Set([TEXTO_SEM_CONTAS])
            wx.CallLater(400, self._oferecer_primeira_conta)
        self.lista_conv.SetFocus()
        if self.lista_conv.GetCount():
            self.lista_conv.SetSelection(0)
        log.info("fala direta pelo NVDA: %s", self.fala.ativa())

    @seguro
    def _oferecer_primeira_conta(self):
        r = wx.MessageBox(
            "Bem-vindo ao %s. Ainda não há nenhuma conta. Quer adicionar uma "
            "conta do Telegram agora? Para o WhatsApp, use o menu Arquivo."
            % NOME, NOME, wx.YES_NO | wx.ICON_QUESTION, self)
        if r == wx.YES:
            self.adicionar_conta("telegram")

    @seguro
    def adicionar_conta(self, servico):
        sugestao = self._telefone_sugerido()
        historico = "recentes"
        if servico == "whatsapp":
            historico = self._escolher_historico()
            if historico is None:
                return
        antes = set(self.contas.provedores)
        if not self.contas.adicionar(servico, sugestao, historico):
            wx.MessageBox("Não foi possível adicionar a conta. Sem as "
                          "credenciais do aplicativo, o Telegram não deixa "
                          "conectar.", NOME, wx.OK | wx.ICON_WARNING, self)
            return
        self.SetStatusText("Conectando ao %s..." % m.SERVICOS[servico])
        if servico == "whatsapp":
            for conta_id in set(self.contas.provedores) - antes:
                self._abrir_pareamento(conta_id, sugestao)

    def _telefone_sugerido(self):
        """O numero da conta ja usada (Telegram) ou o dos testes."""
        for dados in self.cfg.contas():
            if dados.get("telefone"):
                return dados["telefone"]
        return config.telefone_dos_testes()

    def _escolher_historico(self):
        from telezapp.provedores.whatsapp import OPCOES_HISTORICO
        return dialogos.escolher_historico(self, OPCOES_HISTORICO)

    @seguro
    def _parear_whatsapp_de_novo(self, conta_id):
        historico = self._escolher_historico()
        if historico is None:
            return
        self.pareamento_recusado.discard(conta_id)
        if self.contas.parear_de_novo(conta_id, historico):
            self._abrir_pareamento(conta_id, self._telefone_sugerido())

    @seguro
    def _remover_conta(self):
        contas = self.cfg.contas()
        if not contas:
            self.fala.falar("Não há contas para remover.")
            return
        nomes = ["%s, %s" % (c.get("nome") or c.get("telefone") or c["id"],
                             m.SERVICOS.get(c.get("servico"), "")) for c in contas]
        dlg = wx.SingleChoiceDialog(self, "Escolha a conta que vai sair do "
                                    "TeleZapp.", "Remover uma conta", nomes)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            escolhida = contas[dlg.GetSelection()]
            nome = nomes[dlg.GetSelection()]
        finally:
            dlg.Destroy()
        r = wx.MessageBox(
            "Remover a conta %s? As conversas e mensagens guardadas dela neste "
            "computador serão apagadas. A conta continua existindo no celular."
            % nome, "Remover uma conta", wx.YES_NO | wx.ICON_QUESTION, self)
        if r != wx.YES:
            return
        conta_id = escolhida["id"]
        self.contas.remover(conta_id)
        for chave in [k for k in self.indice if k[0] == conta_id]:
            del self.indice[chave]
            self.cache.pop(chave, None)
        if self.atual and self.atual[0] == conta_id:
            self.atual = None
            self.lista_msgs.Set([TEXTO_SEM_CONVERSA])
        self.estados.pop(conta_id, None)
        self._ordenar()
        if self.conversas:
            self._preencher_conversas()
        else:
            self._chaves_conv = []
            self.lista_conv.Set([TEXTO_SEM_CONTAS])
        self.fala.falar("Conta removida.")

    # --------------------------------------------------- pareamento WhatsApp
    def _abrir_pareamento(self, conta_id, telefone=""):
        dlg = self.pareamentos.get(conta_id)
        if dlg:
            return dlg

        def gerar(telefone):
            p = self.contas.provedor(conta_id)
            if p is not None:
                p.pedir_codigo_pareamento(telefone)
        dlg = dialogos.DialogoPareamento(
            self, self.fala.falar, gerar,
            lambda: self._pareamento_cancelado(conta_id), telefone, bipe)
        self.pareamentos[conta_id] = dlg
        dlg.Show()
        dlg.Raise()
        log.info("janela de pareamento aberta")
        return dlg

    def _pareamento_cancelado(self, conta_id):
        self.pareamentos.pop(conta_id, None)
        if self.contas.cancelar_nova(conta_id):
            self.fala.falar("Conexão do WhatsApp cancelada.")
        else:
            # conta salva desconectada: nao reabrir sozinho
            self.pareamento_recusado.add(conta_id)
        log.info("pareamento fechado sem concluir")

    def _ev_qr(self, e):
        if e.conta_id in self.pareamento_recusado:
            return
        self._abrir_pareamento(e.conta_id).mostrar_qr(e.codigo)

    def _ev_codigo(self, e):
        dlg = self.pareamentos.get(e.conta_id)
        if dlg:
            dlg.mostrar_codigo(e.codigo, e.erro)

    def obter_credenciais_telegram(self):
        """Usada pelo gerenciador de contas (na thread da janela)."""
        cred = config.credenciais_telegram(self.cfg)
        if cred is not None:
            return cred
        cred = dialogos.pedir_credenciais_telegram(
            self, config.credenciais_validas)
        if cred is not None:
            self.cfg.dados["telegram_api_id"] = cred[0]
            self.cfg.dados["telegram_api_hash"] = cred[1]
            self.cfg.salvar()
        return cred

    def pedir(self, conta, etapa, erro):
        """Chamada na thread do provedor: mostra o pedido de login na janela
        e espera a resposta."""
        resultado = {}
        pronto = threading.Event()

        def mostrar():
            try:
                self.Raise()
                valor = conta.telefone if etapa == "telefone" else ""
                resultado["v"] = dialogos.pedir_login(
                    self, m.SERVICOS.get(conta.servico, conta.servico),
                    etapa, erro, valor)
            except Exception:
                log.exception("erro no pedido de login")
            finally:
                pronto.set()
        wx.CallAfter(mostrar)
        pronto.wait()
        log.info("pedido de login (%s): %s", etapa,
                 "cancelado" if resultado.get("v") is None else "respondido")
        return resultado.get("v")

    # ============================================================= eventos
    def _ao_evento(self, e):
        tratador = {
            ev.EstadoConta: self._ev_estado,
            ev.ContaPronta: self._ev_conta_pronta,
            ev.ConversasAtualizadas: self._ev_conversas,
            ev.MensagensCarregadas: self._ev_mensagens,
            ev.MensagemNova: self._ev_nova,
            ev.EnvioFalhou: self._ev_falha,
            ev.LeituraConfirmada: self._ev_leitura,
            ev.Aviso: self._ev_aviso,
            ev.EstadosMensagens: self._ev_estados_mensagens,
            ev.QrPareamento: self._ev_qr,
            ev.CodigoPareamento: self._ev_codigo,
            ev.SincronizacaoConcluida: self._ev_sincronia,
        }.get(type(e))
        if tratador is not None and self:
            tratador(e)

    def _ev_estado(self, e):
        antes = self.estados.get(e.conta_id)
        self.estados[e.conta_id] = e.estado
        nome = self.contas.nome(e.conta_id) if self.contas else e.conta_id
        self.SetStatusText("%s: %s" % (nome, e.estado))
        servico = m.SERVICOS.get(self.contas.servico(e.conta_id), "") \
            if self.contas else ""
        if e.estado == ev.CONECTADA and antes != ev.CONECTADA:
            self.fala.falar("%s conectado." % servico)
        elif e.estado == ev.PRECISA_LOGIN:
            self.fala.falar("%s: %s." % (servico, e.detalhe or e.estado))
            if e.detalhe == "desconectada pelo celular":
                wx.CallAfter(self._oferecer_parear_de_novo, e.conta_id)

    @seguro
    def _oferecer_parear_de_novo(self, conta_id):
        r = wx.MessageBox(
            "O WhatsApp desconectou a conta %s: ela foi removida dos "
            "aparelhos conectados do celular, ou ficou muito tempo sem uso. "
            "Quer conectar de novo agora? As conversas guardadas continuam."
            % self.contas.nome(conta_id), NOME,
            wx.YES_NO | wx.ICON_QUESTION, self)
        if r == wx.YES:
            self._parear_whatsapp_de_novo(conta_id)

    def _ev_conta_pronta(self, e):
        self.SetStatusText("Conta pronta: %s" % e.nome)
        self.pareamento_recusado.discard(e.conta_id)
        dlg = self.pareamentos.pop(e.conta_id, None)
        if dlg:
            dlg.concluir()
            bipe("conectado")
            self.fala.falar("WhatsApp conectado. As conversas antigas "
                            "chegam em alguns segundos.", interromper=True)
            self.lista_conv.SetFocus()

    def _ev_conversas(self, e):
        self._juntar_conversas(e.conta_id, e.conversas)
        self._preencher_conversas()

    def _juntar_conversas(self, conta_id, conversas):
        aberta = self.atual
        for c in conversas:
            if c.chave == aberta:
                c.nao_lidas = 0   # a pessoa esta lendo esta conversa
            self.indice[c.chave] = c
        novas = {c.chave for c in conversas}
        for chave in [k for k in self.indice
                      if k[0] == conta_id and k not in novas and k != aberta]:
            del self.indice[chave]
        self._ordenar()

    def _ordenar(self):
        self.conversas = sorted(self.indice.values(), key=lambda c: -c.data)

    def _preencher_conversas(self):
        """Refaz a lista mantendo a conversa selecionada (por chave)."""
        if not self.conversas:
            return
        i = self.lista_conv.GetSelection()
        antes = None
        if 0 <= i < len(self._chaves_conv):
            antes = self._chaves_conv[i]
        self._chaves_conv = [c.chave for c in self.conversas]
        self.lista_conv.Set([m.rotulo_conversa(c) for c in self.conversas])
        if antes in self._chaves_conv:
            self.lista_conv.SetSelection(self._chaves_conv.index(antes))
        elif self._chaves_conv:
            self.lista_conv.SetSelection(0)

    def _ev_mensagens(self, e):
        chave = (e.conta_id, e.conversa_id)
        lista = self._mesclar(chave, e.mensagens)
        if chave != self.atual:
            return
        if self.esperando_servidor:
            self.esperando_servidor = False
            if self.marcador_n > 0:
                recebidas = [x for x in lista if not x.minha]
                n = min(self.marcador_n, len(recebidas))
                self.marcador_id = recebidas[-n].id if n else None
        destino = None
        if self.selecao_automatica:
            destino = MARCADOR if self.marcador_id else "ultima"
        self._preencher_mensagens(destino)

    def _mesclar(self, chave, novas):
        """Junta mensagens ao cache da conversa, sem repetir, em ordem."""
        atuais = {x.id: x for x in self.cache.get(chave, [])}
        for x in novas:
            atuais[x.id] = x
        lista = sorted(atuais.values(), key=_ordem)
        self.cache[chave] = lista[-LIMITE_MEMORIA:]
        return self.cache[chave]

    def _ev_nova(self, e):
        msg = e.mensagem
        chave = (msg.conta_id, msg.conversa_id)
        conv = e.conversa or self.indice.get(chave)
        if conv is None:
            conv = m.Conversa(msg.conta_id, msg.conversa_id, "Conversa nova",
                              data=msg.data)
        aberta = chave == self.atual
        if aberta:
            conv.nao_lidas = 0
        self.indice[chave] = conv
        self._ordenar()
        self._preencher_conversas()
        if e.enviada_daqui:
            self._tirar_local(chave, msg.texto)
        self._mesclar(chave, [msg])
        if aberta:
            no_fim = self._selecionado_no_fim()
            self._preencher_mensagens("ultima" if no_fim and
                                      self.FindFocus() is not self.lista_msgs
                                      else None)
            if not msg.minha and self.IsActive():
                p = self.contas.provedor(msg.conta_id)
                if p is not None:
                    p.marcar_como_lida(msg.conversa_id)
        if msg.minha or e.silenciosa:
            return  # minha, ou chegou na sincronia inicial: sem aviso
        log.info("mensagem nova (tipo %s, conversa aberta=%s)", msg.tipo,
                 aberta)
        resumo = m.formatar(msg, m.ESTILO_AUTOR_PRIMEIRO)
        aviso = ("Nova mensagem. " + resumo) if aberta else \
            "Nova mensagem em %s. %s" % (conv.nome, resumo)
        if self.cfg.get("som"):
            bipe("nova")
        if self.cfg.get("falar_novas"):
            self.fala.falar(aviso)
        self.SetStatusText(aviso[:150])

    def _ev_sincronia(self, e):
        if not e.quantas:
            return
        texto = ("1 mensagem nova chegou" if e.quantas == 1 else
                 "%d mensagens novas chegaram" % e.quantas) + \
            " no WhatsApp enquanto o TeleZapp estava fechado."
        log.info("sincronia: %d mensagens novas", e.quantas)
        if self.cfg.get("som"):
            bipe("nova")
        if self.cfg.get("falar_novas"):
            self.fala.falar(texto)
        self.SetStatusText(texto)

    def _ev_falha(self, e):
        chave = (e.conta_id, e.conversa_id)
        for x in self.cache.get(chave, []):
            if x.id.startswith("local-") and x.texto == e.texto and \
                    x.estado == m.ENVIANDO:
                x.estado = m.FALHOU
                break
        if chave == self.atual:
            self._preencher_mensagens()
            if not self.caixa.GetValue():
                self.caixa.SetValue(e.texto)
        bipe("erro")
        texto = "Não foi possível enviar: %s." % e.motivo
        self.fala.falar(texto, interromper=True)
        self.SetStatusText(texto)
        log.info("envio falhou (%s)", e.motivo)

    def _ev_leitura(self, e):
        chave = (e.conta_id, e.conversa_id)
        conv = self.indice.get(chave)
        if conv is not None:
            conv.lidas_ate = max(conv.lidas_ate, e.ate_id)
        mudou = False
        for x in self.cache.get(chave, []):
            if x.minha and x.estado == m.ENVIADA and x.id.isdigit() and \
                    int(x.id) <= e.ate_id:
                x.estado = m.LIDA
                mudou = True
        if mudou and chave == self.atual:
            self._preencher_mensagens()

    def _ev_estados_mensagens(self, e):
        chave = (e.conta_id, e.conversa_id)
        ids = set(e.ids)
        nivel = m.ORDEM_ESTADOS.get(e.estado, 0)
        mudou = False
        for x in self.cache.get(chave, []):
            if x.minha and x.id in ids and \
                    m.ORDEM_ESTADOS.get(x.estado, 0) < nivel:
                x.estado = e.estado
                mudou = True
        if mudou and chave == self.atual:
            self._preencher_mensagens()

    def _ev_aviso(self, e):
        self.SetStatusText(e.texto)
        self.fala.falar(e.texto)
        if e.grave:
            wx.MessageBox(e.texto, NOME, wx.OK | wx.ICON_WARNING, self)

    # ============================================================ teclado
    def _char_hook(self, evt):
        """Enter e Esc tratados na janela: o ListBox nao entrega o Enter."""
        try:
            k = evt.GetKeyCode()
            foco = self.FindFocus()
            sem_mod = not (evt.AltDown() or evt.ControlDown()
                           or evt.ShiftDown())
            if k == wx.WXK_ESCAPE and sem_mod:
                if foco is self.caixa and self.resposta_a is not None:
                    self._cancelar_resposta()
                    return
                if foco in (self.lista_msgs, self.caixa, self.botao_enviar):
                    self._voltar_para_conversas()
                    return
            if k in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and sem_mod:
                if foco is self.lista_conv:
                    self._abrir_selecionada_na_lista()
                    return
                if foco is self.lista_msgs:
                    self._detalhes_ou_marcador()
                    return
                if foco is self.caixa:
                    self._enviar_texto()
                    return
        except Exception:
            log.error("erro no teclado:\n%s", traceback.format_exc())
            return
        evt.Skip()

    def _tecla_mensagens(self, evt):
        # a pessoa mexeu na lista: nao mover a selecao sozinho
        if evt.GetKeyCode() in (wx.WXK_UP, wx.WXK_DOWN, wx.WXK_HOME,
                                wx.WXK_END, wx.WXK_PAGEUP, wx.WXK_PAGEDOWN):
            self.selecao_automatica = False
        evt.Skip()

    # =========================================================== conversas
    def _conversa_selecionada(self):
        i = self.lista_conv.GetSelection()
        if 0 <= i < len(self._chaves_conv):
            return self.indice.get(self._chaves_conv[i])
        return None

    @seguro
    def _abrir_selecionada_na_lista(self):
        conv = self._conversa_selecionada()
        if conv is None:
            self.fala.falar("Nenhuma conversa selecionada.")
            return
        self._abrir_conversa(conv)

    def _abrir_conversa(self, conv):
        self.atual = conv.chave
        self.resposta_a = None
        self.marcador_n = conv.nao_lidas
        self.marcador_id = None
        self.selecao_automatica = True
        guardadas = self.banco.mensagens(conv.conta_id, conv.id, LIMITE_CACHE)
        lista = self._mesclar(conv.chave, guardadas)
        if self.marcador_n > 0 or not lista:
            # o banco pode nao ter as mensagens mais novas: o marcador so e
            # posto quando o servidor responder
            self.esperando_servidor = True
        self.rot_msgs.SetLabel("Mensagens de " + conv.nome)
        self.rot_caixa.SetLabel("Digite sua mensagem")
        self.SetTitle("%s: %s" % (NOME, conv.nome))
        p = self.contas.provedor(conv.conta_id)
        if p is not None:
            # no WhatsApp o historico e local e rapido: carrega todas as nao
            # lidas para o marcador ficar no lugar certo
            teto = 1000 if self.contas.servico(conv.conta_id) == \
                "whatsapp" else 200
            p.carregar_mensagens(conv.id, min(teto, max(50, conv.nao_lidas
                                                        + 10)))
            if conv.nao_lidas:
                p.marcar_como_lida(conv.id)
        conv.nao_lidas = 0
        self._preencher_conversas()
        self._preencher_mensagens("ultima")
        log.info("conversa aberta (%d no cache, %d não lidas)", len(lista),
                 self.marcador_n)
        self.lista_msgs.SetFocus()

    def _voltar_para_conversas(self):
        if self.atual in self._chaves_conv:
            self.lista_conv.SetSelection(self._chaves_conv.index(self.atual))
        if self.marcador_id is not None:
            self.marcador_id = None
            self.marcador_n = 0
            if self.atual is not None:
                self._preencher_mensagens()
        self.lista_conv.SetFocus()

    def _proxima_nao_lida(self):
        n = len(self._chaves_conv)
        inicio = self.lista_conv.GetSelection() + 1
        for k in range(n):
            i = (inicio + k) % n
            conv = self.indice.get(self._chaves_conv[i])
            if conv is not None and conv.nao_lidas > 0:
                self.lista_conv.SetSelection(i)
                self.lista_conv.SetFocus()
                return
        bipe("erro")
        self.fala.falar("Nenhuma conversa com mensagens não lidas.")

    def _atualizar_conversas(self):
        for conta_id in list(self.estados):
            p = self.contas.provedor(conta_id)
            if p is not None and self.estados[conta_id] == ev.CONECTADA:
                p.atualizar_conversas()
        self.fala.falar("Atualizando as conversas.")

    def _reconectar(self):
        self.pareamento_recusado.clear()
        for dados in self.cfg.contas():
            if self.estados.get(dados["id"]) != ev.CONECTADA:
                self.contas.reconectar(dados["id"])

    # ============================================================ mensagens
    def _mensagens_atuais(self):
        return self.cache.get(self.atual, []) if self.atual else []

    def _preencher_mensagens(self, destino=None):
        """Refaz a lista. destino: MARCADOR, "ultima" ou None (mantem)."""
        if self.atual is None:
            return
        msgs = self._mensagens_atuais()
        antes = self._chave_selecionada()
        nomes = {x.id: ("Você" if x.minha else x.autor) for x in msgs}
        itens, mapa = [], []
        anterior = None
        for x in msgs:
            if self.marcador_id is not None and x.id == self.marcador_id:
                itens.append(m.texto_marcador(self.marcador_n))
                mapa.append(MARCADOR)
            itens.append(m.formatar(x, self.estilo, anterior,
                                    respondida=nomes.get(x.resposta_a)))
            mapa.append(x.id)
            anterior = x
        if not itens:
            itens = [TEXTO_CARREGANDO if self.esperando_servidor
                     else TEXTO_SEM_MENSAGENS]
            mapa = [None]
        self.mapa = mapa
        self.lista_msgs.Set(itens)
        sel = len(itens) - 1
        if destino == MARCADOR and MARCADOR in mapa:
            sel = mapa.index(MARCADOR)
        elif destino is None and antes in mapa:
            sel = mapa.index(antes)
        self.lista_msgs.SetSelection(sel)

    def _chave_selecionada(self):
        i = self.lista_msgs.GetSelection()
        return self.mapa[i] if 0 <= i < len(self.mapa) else None

    def _selecionado_no_fim(self):
        return self.lista_msgs.GetSelection() >= self.lista_msgs.GetCount() - 1

    def _mensagem_selecionada(self):
        chave = self._chave_selecionada()
        for x in self._mensagens_atuais():
            if x.id == chave:
                return x
        return None

    def _detalhes_ou_marcador(self):
        if self._chave_selecionada() == MARCADOR:
            self.fala.falar("Marcador. As mensagens não lidas começam na "
                            "próxima.")
            return
        self._detalhes()

    def _detalhes(self):
        x = self._mensagem_selecionada()
        if x is None:
            return
        conv = self.indice.get(self.atual)
        dialogos.mostrar_texto(self, "Detalhes da mensagem",
                               m.detalhes(x, conv.nome if conv else ""),
                               "Detalhes e texto completo")

    def _responder(self):
        x = self._mensagem_selecionada()
        if x is None or x.id.startswith("local-"):
            return
        self.resposta_a = x
        autor = "você" if x.minha else (x.autor or "mensagem")
        self.rot_caixa.SetLabel("Respondendo a %s. Digite sua resposta"
                                % autor)
        self.fala.falar("Respondendo a %s. Esc cancela a resposta." % autor)
        self.caixa.SetFocus()

    def _cancelar_resposta(self):
        self.resposta_a = None
        self.rot_caixa.SetLabel("Digite sua mensagem")
        self.fala.falar("Resposta cancelada.")

    def _copiar(self):
        x = self._mensagem_selecionada()
        if x is None:
            return
        texto = x.texto or m.conteudo(x)
        if wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(wx.TextDataObject(texto))
            finally:
                wx.TheClipboard.Close()
        self.fala.falar("Texto copiado.")

    def _ler_ultima(self):
        msgs = self._mensagens_atuais()
        if not msgs:
            self.fala.falar(TEXTO_SEM_CONVERSA if self.atual is None
                            else TEXTO_SEM_MENSAGENS)
            return
        self.fala.falar(m.formatar(msgs[-1], m.ESTILO_AUTOR_PRIMEIRO),
                        interromper=True)

    def _menu_mensagem(self, evt):
        if self._mensagem_selecionada() is None:
            return
        menu = wx.Menu()
        for rotulo, tratador in (("Responder", self._responder),
                                 ("Copiar texto", self._copiar),
                                 ("Detalhes", self._detalhes)):
            it = menu.Append(wx.ID_ANY, rotulo)
            self.Bind(wx.EVT_MENU, seguro(lambda e, t=tratador: t()), it)
        pos = evt.GetPosition()
        if pos == wx.DefaultPosition:
            self.lista_msgs.PopupMenu(menu, wx.Point(20, 20))
        else:
            self.lista_msgs.PopupMenu(menu,
                                      self.lista_msgs.ScreenToClient(pos))
        menu.Destroy()

    # ================================================================ envio
    def _enviar_texto(self):
        if self.atual is None:
            bipe("erro")
            self.fala.falar(TEXTO_SEM_CONVERSA)
            return
        texto = self.caixa.GetValue().strip()
        if not texto:
            bipe("erro")
            return
        conta_id, conversa_id = self.atual
        p = self.contas.provedor(conta_id)
        if p is None or self.estados.get(conta_id) != ev.CONECTADA:
            bipe("erro")
            self.fala.falar("A conta não está conectada. A mensagem não foi "
                            "enviada.", interromper=True)
            return
        resposta = self.resposta_a.id if self.resposta_a else ""
        self.locais += 1
        # sempre no fim, mesmo se o relogio do PC estiver atras do servidor
        ultima = max((x.data for x in self._mensagens_atuais()), default=0)
        local = m.Mensagem(conta_id, conversa_id, "local-%d" % self.locais,
                           minha=True, data=max(time.time(), ultima + 0.001),
                           texto=texto,
                           estado=m.ENVIANDO, resposta_a=resposta)
        self._mesclar(self.atual, [local])
        self.caixa.Clear()
        if self.resposta_a is not None:
            self.resposta_a = None
            self.rot_caixa.SetLabel("Digite sua mensagem")
        self._preencher_mensagens("ultima")
        p.enviar_texto(conversa_id, texto, resposta)
        log.info("texto enviado para a fila (%d caracteres)", len(texto))

    def _tirar_local(self, chave, texto):
        """Troca a mensagem 'enviando' pela confirmada pelo servico."""
        lista = self.cache.get(chave, [])
        for i, x in enumerate(lista):
            if x.id.startswith("local-") and x.texto == texto and \
                    x.estado == m.ENVIANDO:
                del lista[i]
                break
        bipe("enviada")
        if self.cfg.get("confirmar_envio"):
            self.fala.falar("Enviada.")

    # ============================================================== opcoes
    def _mudar_estilo(self, estilo):
        self.estilo = estilo
        self.cfg.set("estilo", estilo)
        if self.atual is not None:
            self._preencher_mensagens()
        self.fala.falar("Estilo: " + m.NOMES_ESTILOS[estilo])

    def _opcao(self, chave, valor):
        self.cfg.set(chave, bool(valor))
        log.info("opção %s = %s", chave, valor)

    def _ir_para(self, controle, nome):
        controle.SetFocus()

    def _abrir_logs(self):
        pasta = config.pasta("logs")
        if os.name == "nt":
            subprocess.Popen(["explorer", pasta])
        else:
            self.fala.falar(pasta)

    def _sobre(self):
        wx.MessageBox(
            "%s %s\nCliente de WhatsApp e Telegram feito para leitores de "
            "tela.\nSoftware livre sob a licença GPL versão 3 ou "
            "posterior.\nDados guardados em: %s" % (
                NOME, VERSAO, config.pasta_dados()),
            "Sobre o %s" % NOME, wx.OK | wx.ICON_INFORMATION, self)

    # ================================================================ saida
    def _ao_fechar(self, evt):
        log.info("fechando a janela")
        self.Hide()
        try:
            if self.contas is not None:
                self.contas.parar_todos()
        finally:
            self.Destroy()


def _ordem(x):
    """Ordena por data; ids numericos desempatam."""
    return (x.data, int(x.id) if x.id.isdigit() else 0)

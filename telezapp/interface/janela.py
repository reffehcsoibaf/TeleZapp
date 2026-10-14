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
from telezapp.interface import dialogos, visualizadores
from telezapp.midia import armazem
from telezapp.midia.reprodutor import FormatoNaoSuportado, Reprodutor
from telezapp.nucleo import eventos as ev
from telezapp.nucleo import modelos as m
from telezapp.nucleo import paginas

log = logging.getLogger("telezapp.janela")

MARCADOR = "marcador"
TEXTO_SEM_CONVERSA = "Nenhuma conversa aberta. Aperte Enter numa conversa."
TEXTO_SEM_MENSAGENS = "Esta conversa ainda não tem mensagens."
TEXTO_CARREGANDO = "Carregando mensagens..."
TEXTO_SEM_CONTAS = "Nenhuma conversa ainda. Aperte Alt e use Contas, no " \
                   "menu, para adicionar uma conta do Telegram ou do WhatsApp."
LIMITE_CACHE = 100        # mensagens lidas do banco ao abrir a conversa
LIMITE_MEMORIA = 1200     # mensagens mantidas na memoria por conversa

AJUDA = """\
ESTRUTURA DA JANELA
Sem conversa aberta, só a lista de Conversas aparece. Enter abre a conversa e
leva você à lista de Mensagens; Esc fecha a conversa. Com a conversa aberta, a caixa
para escrever fica logo abaixo das mensagens.

ATALHOS
Control 1: ir para a lista de conversas
Control 2: ir para a lista de mensagens
Control E: ir para a caixa de digitação
Control U: ir para a próxima conversa com mensagens não lidas
Control R: ouvir a última mensagem da conversa aberta
F5: atualizar a lista de conversas
Control Shift R: responder à mensagem selecionada
Control Shift C: copiar o texto da mensagem selecionada
Alt Enter: ver os detalhes e o texto completo da mensagem selecionada
Control O: abrir a mídia da mensagem (baixa antes, se preciso)
Control B: baixar a mídia sem abrir
Tecla Aplicativos ou Shift F10: menu da mensagem selecionada

NA LISTA DE CONVERSAS
Setas: percorrem as conversas (cada uma é lida com o número de não lidas).
Enter: abre a conversa e leva o foco para as mensagens: para o item "Início
das mensagens não lidas", se houver não lidas, ou para a última mensagem.

NA LISTA DE MENSAGENS
Esc: fecha a conversa e volta para a lista de conversas.
Enter: mostra os detalhes e o texto completo da mensagem. Numa mensagem com
foto, vídeo, áudio, voz ou documento, abre a mídia. Esc cancela um download.

NO LEITOR DE ÁUDIO E VÍDEO
Espaço: tocar ou pausar. Seta para a direita e para a esquerda: avançar e
voltar 5 segundos (com Shift, 30). Home: voltar ao início. Esc: fechar.

NA CAIXA DE DIGITAÇÃO
Enter: envia e esconde a caixa. Shift Enter: nova linha. Esc: cancela a
resposta, se houver, esconde a caixa e volta para as mensagens.

MENU
Aperte Alt para abrir o Menu. Ele tem submenus (Contas, Conversa, Mensagem,
Exibição e Ajuda): use a seta para a direita para entrar e a seta para a
esquerda para voltar. F1 abre o guia de uso completo.

EXIBIÇÃO
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
        self.midias = None            # gerente de downloads (idem)
        self.fala = Fala()
        self.conversas = []           # ordenadas pela ultima mensagem
        self._chaves_conv = []        # chave de cada item da lista
        self._rotulos_conv = []       # texto de cada item da lista
        self.rascunhos = {}           # texto nao enviado de cada conversa
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
        self.sincronia = {}           # conta_id -> (percentual, quando)
        self.audio = None             # (chave, Reprodutor) tocando sem janela
        self.interrompidas = {}       # conta_id -> % em que a sincronia parou
        self.progresso_midias = {}    # chave da midia -> percentual
        self.abrindo = None           # chave da midia que abre ao baixar
        self.abrindo_abrir = True     # False: so baixar, sem abrir
        self.progresso_falado = 0
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

        # Menu vertical (como no telezapp migration): uma unica entrada na
        # barra, aberta pelo Alt, com as secoes como submenus (seta para a
        # direita). E um menu nativo: o NVDA le como qualquer outro.
        raiz = wx.Menu()

        m_contas = wx.Menu()
        item(m_contas, "add_tg", "Adicionar conta do &Telegram...")
        item(m_contas, "add_wa", "Adicionar conta do &WhatsApp...")
        item(m_contas, "reconectar", "&Conectar as contas de novo")
        item(m_contas, "remover", "&Remover uma conta...")

        m_conv = wx.Menu()
        item(m_conv, "ir_conv", "Ir para a lista de &conversas\tCtrl+1")
        item(m_conv, "ir_msgs", "Ir para a lista de &mensagens\tCtrl+2")
        item(m_conv, "ir_caixa", "&Escrever mensagem\tCtrl+E")
        m_conv.AppendSeparator()
        item(m_conv, "abrir_conv", "&Abrir a conversa selecionada")
        item(m_conv, "proxima", "Próxima conversa &não lida\tCtrl+U")
        item(m_conv, "ler_ultima", "&Ouvir a última mensagem\tCtrl+R")
        item(m_conv, "atualizar", "A&tualizar a lista de conversas\tF5")

        m_msg = wx.Menu()
        item(m_msg, "responder", "&Responder\tCtrl+Shift+R")
        item(m_msg, "copiar", "&Copiar texto\tCtrl+Shift+C")
        item(m_msg, "detalhes", "&Detalhes\tAlt+Enter")
        m_msg.AppendSeparator()
        item(m_msg, "abrir_midia", "&Abrir mídia\tCtrl+O")
        item(m_msg, "baixar_midia", "&Baixar mídia sem abrir\tCtrl+B")
        item(m_msg, "salvar_midia", "Salvar c&ópia da mídia...")

        m_mid = wx.Menu()
        for valor, nome in next(o for o in config.OPCOES
                                if o.chave == "midias_baixar").escolhas:
            it = item(m_mid, "baixar_" + valor, nome, "radio")
            self.Bind(wx.EVT_MENU,
                      lambda e, v=valor: self._mudar_baixar(v), it)
        m_mid.AppendSeparator()
        item(m_mid, "audio_janela", "&Enter em áudio...")
        item(m_mid, "midias_limite", "&Limite do download automático...")
        item(m_mid, "midias_confirmar", "&Confirmar downloads grandes...")
        item(m_mid, "midias_espaco", "&Espaço usado pelas mídias")

        m_exib = wx.Menu()
        for est, nome in m.NOMES_ESTILOS.items():
            it = item(m_exib, "estilo%d" % est, nome, "radio")
            self.Bind(wx.EVT_MENU,
                      lambda e, est=est: self._mudar_estilo(est), it)
        m_exib.AppendSeparator()
        rotulos = {o.chave: o.rotulo for o in config.OPCOES}
        for chave in ("som", "falar_novas", "confirmar_envio"):
            item(m_exib, chave, rotulos[chave], "check")

        m_aj = wx.Menu()
        item(m_aj, "guia", "&Guia de uso\tF1")
        item(m_aj, "ajuda", "&Teclas de atalho\tShift+F1")
        item(m_aj, "novidades", "&Novidades desta versão")
        item(m_aj, "logs", "Abrir a pasta de &logs")
        item(m_aj, "sobre", "&Sobre o %s" % NOME)

        for submenu, rotulo in ((m_contas, "&Contas"), (m_conv, "C&onversa"),
                                (m_msg, "&Mensagem"), (m_mid, "Mí&dias"),
                                (m_exib, "&Exibição"),
                                (m_aj, "A&juda")):
            raiz.AppendSubMenu(submenu, rotulo)
        raiz.AppendSeparator()
        item(raiz, "sair", "&Sair\tCtrl+Q")
        barra.Append(raiz, "&Menu")
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
            "ir_caixa": lambda e: self._mostrar_caixa(),
            "abrir_conv": lambda e: self._abrir_selecionada_na_lista(),
            "proxima": lambda e: self._proxima_nao_lida(),
            "ler_ultima": lambda e: self._ler_ultima(),
            "atualizar": lambda e: self._atualizar_conversas(),
            "responder": lambda e: self._responder(),
            "copiar": lambda e: self._copiar(),
            "detalhes": lambda e: self._detalhes(),
            "ajuda": lambda e: dialogos.mostrar_texto(
                self, "Teclas de atalho", AJUDA, "Teclas de atalho"),
            "abrir_midia": lambda e: self._abrir_midia(),
            "baixar_midia": lambda e: self._abrir_midia(abrir=False),
            "salvar_midia": lambda e: self._salvar_midia(),
            "audio_janela": lambda e: self._escolher_opcao("audio_janela"),
            "midias_limite": lambda e: self._escolher_opcao(
                "midias_limite_auto_mb"),
            "midias_confirmar": lambda e: self._escolher_opcao(
                "midias_confirmar_mb"),
            "midias_espaco": lambda e: self._espaco_midias(),
            "guia": lambda e: self._abrir_pagina("guia.html"),
            "novidades": lambda e: self._abrir_pagina("novidades.html"),
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
        self.itens.get("baixar_" + str(self.cfg.get("midias_baixar")),
                       self.itens["baixar_demanda"]).Check(True)

    def _criar_controles(self):
        painel = wx.Panel(self)
        self.painel = painel
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
        self._mostrar_conversa(False, False)

    def _mostrar_conversa(self, mensagens, escrever):
        """Sem conversa aberta so a lista de conversas aparece; com a
        conversa aberta aparecem as mensagens e a caixa de digitar."""
        for w in (self.rot_msgs, self.lista_msgs):
            w.Show(mensagens)
        for w in (self.rot_caixa, self.caixa, self.botao_enviar):
            w.Show(escrever)
        self.painel.Layout()

    def _atualizar_titulo(self):
        """Titulo da janela: conversa aberta e o que esta em andamento
        (sincronia do historico, downloads de midia)."""
        base = NOME
        conv = self.indice.get(self.atual) if self.atual else None
        if conv is not None:
            base = "%s: %s" % (NOME, conv.nome)
        extras = []
        agora = time.time()
        for cid, (pct, quando) in list(self.sincronia.items()):
            if agora - quando > 90:      # o celular parou de mandar
                del self.sincronia[cid]
                continue
            servico = m.SERVICOS.get(self.contas.servico(cid), "") \
                if self.contas else ""
            extras.append("%s sincronizando %d%%" % (servico, pct))
        for cid, pct in self.interrompidas.items():
            servico = m.SERVICOS.get(self.contas.servico(cid), "") \
                if self.contas else ""
            extras.append("%s sincronia interrompida em %d%%" % (servico,
                                                                  pct))
        n = len(self.progresso_midias)
        if n == 1:
            pct = next(iter(self.progresso_midias.values()))
            extras.append("baixando mídia %d%%" % pct if pct > 0
                          else "baixando mídia")
        elif n > 1:
            extras.append("baixando %d mídias" % n)
        self.SetTitle(base + (" - " + ", ".join(extras) if extras else ""))

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
        servicos = ["telegram", "whatsapp"]
        dlg = wx.SingleChoiceDialog(
            self, "Bem-vindo ao %s. Ainda não há nenhuma conta. Escolha qual "
            "adicionar agora, ou cancele para fazer isso depois pelo menu "
            "(tecla Alt), em Contas." % NOME, NOME,
            [m.SERVICOS[s] for s in servicos])
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            servico = servicos[dlg.GetSelection()]
        finally:
            dlg.Destroy()
        self.adicionar_conta(servico)

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
            self._mostrar_conversa(False, False)
            self._atualizar_titulo()
        self.estados.pop(conta_id, None)
        self._ordenar()
        if self.conversas:
            self._preencher_conversas()
        else:
            self._chaves_conv = []
            self._rotulos_conv = []
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
            ev.ProgressoSincronia: self._ev_progresso_sincronia,
            ev.ProgressoMidia: self._ev_progresso_midia,
            ev.MidiaBaixada: self._ev_midia_baixada,
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
            if self.interrompidas.pop(e.conta_id, None) is not None:
                self._atualizar_titulo()
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
        chaves = [c.chave for c in self.conversas]
        rotulos = [m.rotulo_conversa(c) for c in self.conversas]
        if chaves == self._chaves_conv and \
                rotulos == self._rotulos_conv:
            return      # nada mudou: mexer na lista faz o NVDA repetir o foco
        if chaves == self._chaves_conv and \
                len(rotulos) == self.lista_conv.GetCount():
            # mesma ordem: troca so os textos que mudaram
            for k, (velho, novo) in enumerate(zip(self._rotulos_conv,
                                                  rotulos)):
                if velho != novo:
                    self.lista_conv.SetString(k, novo)
            self._rotulos_conv = rotulos
            return
        self._chaves_conv = chaves
        self._rotulos_conv = rotulos
        self.lista_conv.Set(rotulos)
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
            # mensagem minha nunca tira a pessoa de onde ela esta
            self._preencher_mensagens(
                "ultima" if no_fim and not msg.minha and
                self.FindFocus() is not self.lista_msgs else None)
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
        if chave == self.atual:
            texto += " O texto voltou para a caixa de digitação."
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
                if foco in (self.caixa, self.botao_enviar):
                    self._sair_da_caixa()
                    return
                if foco is self.lista_msgs:
                    if not self._cancelar_download() and \
                            not self._parar_audio():
                        self._fechar_conversa()
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
        self.caixa.SetValue(self.rascunhos.get(conv.chave, ""))
        self._mostrar_conversa(True, True)
        self._atualizar_titulo()
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

    def _fechar_conversa(self):
        """Esc na lista de mensagens: fecha a conversa e volta para a lista
        de conversas. Mensagens que chegarem depois contam como novas."""
        if self.atual in self._chaves_conv:
            self.lista_conv.SetSelection(self._chaves_conv.index(self.atual))
        if self.resposta_a is not None:
            self._cancelar_resposta()
        texto = self.caixa.GetValue()
        if texto.strip():
            self.rascunhos[self.atual] = texto
        else:
            self.rascunhos.pop(self.atual, None)
        self.caixa.Clear()
        self.marcador_id = None
        self.marcador_n = 0
        self.atual = None
        self.mapa = [None]
        self.rot_msgs.SetLabel("Mensagens")
        self.lista_msgs.Set([TEXTO_SEM_CONVERSA])
        self._mostrar_conversa(False, False)
        self._atualizar_titulo()
        self.lista_conv.SetFocus()

    def _mostrar_caixa(self):
        if self.atual is None:
            self.fala.falar(TEXTO_SEM_CONVERSA)
            return
        self.caixa.SetFocus()

    def _sair_da_caixa(self):
        """Esc na caixa: primeiro cancela a resposta em andamento; sem
        resposta, fecha a conversa (o rascunho fica guardado)."""
        if self.resposta_a is not None:
            self._cancelar_resposta()
            return
        self._fechar_conversa()

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
        x = self._mensagem_selecionada()
        if x is not None and x.tipo in armazem.BAIXAVEIS and \
                not x.id.startswith("local-"):
            self._abrir_midia()
            return
        self._detalhes()

    def _detalhes(self):
        x = self._mensagem_selecionada()
        if x is None:
            return
        conv = self.indice.get(self.atual)
        recibos = []
        if x.minha and self.banco is not None and not x.id.startswith("local-"):
            recibos = self.banco.recibos(x.conta_id, x.conversa_id, x.id)
        midia = None
        if x.tipo in armazem.BAIXAVEIS and self.midias is not None:
            midia = "baixada" if self.midias.caminho(x) else "não baixada"
        dialogos.mostrar_texto(self, "Detalhes da mensagem",
                               m.detalhes(x, conv.nome if conv else "",
                                          recibos=recibos, midia=midia),
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
        self._mostrar_caixa()

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
        # a selecao fica na mensagem em que a pessoa estava
        self._preencher_mensagens()
        self.caixa.SetFocus()
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

    # =============================================================== midias
    def _abrir_midia(self, abrir=True):
        x = self._mensagem_selecionada()
        if x is None or self.midias is None:
            return
        if x.tipo not in armazem.BAIXAVEIS:
            self.fala.falar("Esta mensagem não tem mídia.")
            return
        if x.id.startswith("local-"):
            return
        caminho = self.midias.caminho(x)
        if caminho:
            if abrir:
                self._mostrar_midia(x, caminho)
            else:
                self.fala.falar("Esta mídia já está baixada.")
            return
        limite = int(self.cfg.get("midias_confirmar_mb") or 0) * 1048576
        if x.tamanho and x.tamanho > limite:
            r = wx.MessageBox(
                "Esta mídia tem %s. Baixar mesmo?" % m.tamanho_legivel(
                    x.tamanho), NOME, wx.YES_NO | wx.ICON_QUESTION, self)
            if r != wx.YES:
                return
        self.abrindo = x.chave
        self.progresso_midias[x.chave] = 0
        self._atualizar_titulo()
        self.abrindo_abrir = abrir
        self.progresso_falado = 0
        self.midias.baixar(x)
        tam = (", " + m.tamanho_legivel(x.tamanho)) if x.tamanho else ""
        self.fala.falar("Baixando %s%s. Esc cancela." % (
            m.NOMES_TIPOS.get(x.tipo, "mídia"), tam), interromper=True)

    def _cancelar_download(self):
        if self.abrindo is not None and self.midias is not None and \
                self.midias.baixando(self.abrindo):
            self.midias.cancelar(self.abrindo)
            self.fala.falar("Cancelando o download.", interromper=True)
            return True
        return False

    def _tocar_sem_janela(self, x, caminho):
        """Enter em audio sem janela: toca ao fundo. Enter de novo na mesma
        mensagem pausa e continua; Esc para. False se o formato exige a
        janela (que usa o player do Windows)."""
        if self.audio is not None and self.audio[0] == x.chave and \
                not self.audio[1].terminou:
            motor = self.audio[1]
            motor.alternar()
            self.fala.falar("Tocando" if motor.tocando else "Pausado",
                            interromper=True)
            return True
        self._parar_audio(falar=False)
        try:
            motor = Reprodutor(caminho)
        except FormatoNaoSuportado:
            return False
        motor.tocar()
        self.audio = (x.chave, motor)
        self.fala.falar("Tocando", interromper=True)
        wx.CallLater(500, self._vigiar_audio, motor)
        return True

    def _vigiar_audio(self, motor):
        """Libera o dispositivo de som quando o audio acaba."""
        if self.audio is None or self.audio[1] is not motor:
            return
        if motor.terminou:
            self._parar_audio(falar=False)
            return
        wx.CallLater(500, self._vigiar_audio, motor)

    def _parar_audio(self, falar=True):
        if self.audio is None:
            return False
        motor = self.audio[1]
        self.audio = None
        try:
            motor.fechar()
        except Exception:
            log.exception("erro ao parar o áudio")
        if falar:
            self.fala.falar("Áudio parado.", interromper=True)
        return True

    def _mostrar_midia(self, x, caminho):
        if visualizadores.escolher(x.tipo, caminho) == visualizadores.AUDIO \
                and self.cfg.get("audio_janela") == "sem" and \
                self._tocar_sem_janela(x, caminho):
            return
        conv = self.indice.get((x.conta_id, x.conversa_id))
        visualizadores.abrir(self, x, caminho, self.fala,
                             conv.nome if conv else "")

    def _salvar_midia(self):
        x = self._mensagem_selecionada()
        if x is None or self.midias is None or \
                x.tipo not in armazem.BAIXAVEIS:
            return
        caminho = self.midias.caminho(x)
        if not caminho:
            self.fala.falar("Baixe a mídia antes, com Control B.")
            return
        visualizadores.salvar_copia(self, x, caminho, self.fala)

    def _mudar_baixar(self, valor):
        self.cfg.set("midias_baixar", valor)
        nomes = dict(next(o for o in config.OPCOES
                          if o.chave == "midias_baixar").escolhas)
        self.fala.falar("Mídias: " + nomes[valor])

    def _escolher_opcao(self, chave):
        o = next(o for o in config.OPCOES if o.chave == chave)
        atual = self.cfg.get(chave)
        dlg = wx.SingleChoiceDialog(self, o.descricao, o.rotulo,
                                    [r for _, r in o.escolhas])
        try:
            dlg.SetSelection([v for v, _ in o.escolhas].index(atual))
        except ValueError:
            pass
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            valor = o.escolhas[dlg.GetSelection()][0]
        finally:
            dlg.Destroy()
        self.cfg.set(chave, valor)
        self.fala.falar("%s: %s" % (o.rotulo, o.escolhas[
            [v for v, _ in o.escolhas].index(valor)][1]))

    def _espaco_midias(self):
        self.fala.falar("As mídias baixadas ocupam %s." % m.tamanho_legivel(
            armazem.tamanho_da_pasta()))

    def _ev_progresso_sincronia(self, e):
        if e.interrompida:
            self.sincronia.pop(e.conta_id, None)
            self.interrompidas[e.conta_id] = e.percentual
            servico = m.SERVICOS.get(self.contas.servico(e.conta_id), "") \
                if self.contas else ""
            texto = ("%s: a sincronia do histórico foi interrompida em %d%%. "
                     "O TeleZapp está tentando reconectar." %
                     (servico, e.percentual))
            self.SetStatusText(texto)
            self.fala.falar(texto, interromper=True)
            self._atualizar_titulo()
            wx.CallAfter(self._oferecer_historico_de_novo, e.conta_id,
                         e.percentual)
            return
        self.interrompidas.pop(e.conta_id, None)
        if e.percentual >= 100:
            self.sincronia.pop(e.conta_id, None)
        else:
            self.sincronia[e.conta_id] = (e.percentual, time.time())
            wx.CallLater(91000, self._atualizar_titulo)
        self._atualizar_titulo()

    @seguro
    def _oferecer_historico_de_novo(self, conta_id, percentual):
        if self.contas is None or self.contas.provedor(conta_id) is None:
            return
        r = wx.MessageBox(
            "A sincronia do histórico da conta %s parou em %d%% porque a "
            "conexão caiu. O WhatsApp só envia o histórico uma vez, logo "
            "depois do pareamento. Para receber o resto, é preciso "
            "conectar a conta de novo (as conversas já guardadas "
            "continuam). Quer conectar de novo agora?"
            % (self.contas.nome(conta_id), percentual), NOME,
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
        if r == wx.YES:
            self._parear_whatsapp_de_novo(conta_id)

    def _ev_progresso_midia(self, e):
        chave = (e.conta_id, e.conversa_id, e.mensagem_id)
        if self.progresso_midias.get(chave) != e.percentual:
            self.progresso_midias[chave] = e.percentual
            self._atualizar_titulo()
        if chave != self.abrindo:
            return
        marco = e.percentual // 25 * 25
        if 0 < marco < 100 and marco > self.progresso_falado:
            self.progresso_falado = marco
            self.fala.falar("%d por cento" % marco)
        self.SetStatusText("Baixando mídia: %d%%" % e.percentual)

    def _ev_midia_baixada(self, e):
        chave = (e.conta_id, e.conversa_id, e.mensagem_id)
        if self.progresso_midias.pop(chave, None) is not None:
            self._atualizar_titulo()
        pedida = chave == self.abrindo
        if pedida:
            self.abrindo = None
        if e.cancelada:
            if pedida:
                self.fala.falar("Download cancelado.", interromper=True)
            return
        if e.erro:
            if pedida or not e.automatica:
                bipe("erro")
                self.fala.falar(e.erro, interromper=True)
                wx.MessageBox(e.erro, NOME, wx.OK | wx.ICON_WARNING, self)
            return
        self.SetStatusText("Mídia baixada.")
        if not pedida:
            return
        if not self.abrindo_abrir:
            self.fala.falar("Mídia baixada.", interromper=True)
            return
        lista = self.cache.get((e.conta_id, e.conversa_id)) or \
            self.banco.mensagens(e.conta_id, e.conversa_id, LIMITE_MEMORIA)
        for x in lista:
            if x.id == e.mensagem_id:
                self._mostrar_midia(x, e.caminho)
                return

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
        if self.atual is None and controle is self.lista_msgs:
            self.fala.falar(TEXTO_SEM_CONVERSA)
            return
        controle.SetFocus()

    def _abrir_pagina(self, nome):
        """Guia de uso ou novidades, no navegador padrao."""
        caminho = paginas.gerar(nome, config.pasta_temporaria())
        if caminho is None:
            wx.MessageBox("O arquivo %s não foi encontrado." % nome, NOME,
                          wx.OK | wx.ICON_WARNING, self)
            return
        if os.name == "nt":
            os.startfile(caminho)
        else:
            self.fala.falar(caminho)

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
        self._parar_audio(falar=False)
        try:
            if self.contas is not None:
                self.contas.parar_todos()
        finally:
            self.Destroy()


def _ordem(x):
    """Ordena por data; ids numericos desempatam."""
    return (x.data, int(x.id) if x.id.isdigit() else 0)

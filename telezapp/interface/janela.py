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
from telezapp.interface.chamada import DialogoChamada
from telezapp.midia import armazem
from telezapp.midia import envio
from telezapp.midia import velocidade as vel
from telezapp.midia.gravador import MICROFONE, SOM_INTERNO, Gravador
from telezapp.midia.reprodutor import FormatoNaoSuportado, Reprodutor
from telezapp.nucleo import chamadas as ch
from telezapp.provedores.base import ErroPrivacidade
from telezapp.nucleo import codigo_secreto
from telezapp.nucleo import depuracao
from telezapp.nucleo import eventos as ev
from telezapp.nucleo import modelos as m
from telezapp.nucleo import paginas
from telezapp.nucleo.midias import TEXTO_LIMPA

log = logging.getLogger("telezapp.janela")

MARCADOR = "marcador"
TEXTO_SEM_CONVERSA = "Nenhuma conversa aberta. Aperte Enter numa conversa."
TEXTO_SEM_MENSAGENS = "Esta conversa ainda não tem mensagens."
TEXTO_CARREGANDO = "Carregando mensagens..."
TEXTO_FILTRO_VAZIO = "Nenhuma conversa neste filtro."
TEXTO_SEM_CONTAS ="Nenhuma conversa ainda. Aperte Alt e use Contas, no " \
                   "menu, para adicionar uma conta do Telegram ou do WhatsApp."
MAX_BOTOES_ACAO = 12     # botoes de resposta que cabem na ordem de Tab
MAX_BOTOES_LINK = 12     # links e botoes de endereco, tambem na ordem de Tab
LIMITE_ROTULO_LINK = 80  # caracteres do rotulo de um botao de link
LIMITE_CACHE = 100        # mensagens lidas do banco ao abrir a conversa
LIMITE_MEMORIA = 1200     # padrao de mensagens na memoria por conversa

AJUDA = """\
ESTRUTURA DA JANELA
Sem conversa aberta, só a lista de Conversas aparece. Enter abre a conversa e
leva você à lista de Mensagens; Esc fecha a conversa. Com a conversa aberta, a caixa
para escrever fica logo abaixo das mensagens.

ATALHOS
Alt 1: ir para a lista de conversas
Alt 2: na lista de conversas, a próxima conversa com mensagens não lidas;
dentro da conversa, o marcador de mensagens não lidas
Alt 3: ir para a lista de mensagens
End: ir para o fim da lista (Home: para o início)
Control E: ir para a caixa de digitação
Control R: ouvir a última mensagem da conversa aberta
F5: atualizar a lista de conversas
Control N: nova mensagem (escolhe a conta, se houver mais de uma, o destinatário e
o texto)
Control F: buscar conversa pelo nome (digitar o código secreto aqui libera as
conversas trancadas no celular)
Control Shift T: esconder de novo as conversas trancadas
Alt 4: filtro de serviço ou conta da lista de conversas
Alt 5: filtro de tipo de conversa (todas, não lidas, pessoais, grupos,
canais, arquivadas, trancadas)
Control Shift R: responder à mensagem selecionada
Control Shift C: copiar o texto da mensagem selecionada
Alt Enter: ver os detalhes e o texto completo da mensagem selecionada
Control Shift D: depurar a mensagem selecionada (menu Depurar)
Control O: abrir a mídia da mensagem (baixa antes, se preciso), mesmo
quando a legenda tem link
Control B: baixar a mídia sem abrir
Tab (na mensagem): vai aos botões de resposta e depois aos links, botões
de endereço e pessoas mencionadas; Espaço ou Enter abre
Control Shift A: anexar e enviar um arquivo (foto, vídeo, áudio, documento)
Control Shift M: gravar uma nota de voz pelo microfone
Control Shift S: gravar o som do computador e enviar como nota de voz
Control Shift Seta para cima e para baixo: áudio mais rápido e mais lento
(0,25x a 3x); Control Shift 0: velocidade normal
Control vírgula: abrir as configurações (busca, categorias e opções)
Control Shift L: ligar para a conversa (Telegram, conversa com uma pessoa)
Control Shift J: voltar à janela da chamada
Control Shift K: silenciar ou ativar o microfone na chamada
Control Shift H: desligar a chamada
Tecla Aplicativos ou Shift F10: menu da mensagem selecionada

NA LISTA DE CONVERSAS
Setas: percorrem as conversas (cada uma é lida com o número de não lidas).
Enter: abre a conversa e leva o foco para as mensagens: para o item "Início
das mensagens não lidas", se houver não lidas, ou para a última mensagem.

NA LISTA DE MENSAGENS
Esc: fecha a conversa e volta para a lista de conversas.
Enter: numa mensagem com foto, vídeo, áudio, voz ou documento, abre a mídia
(toca o áudio e o vídeo), mesmo com link na legenda. Numa mensagem só de
texto, abre o texto numa caixa somente leitura, com os botões Copiar texto e
Fechar (Esc também fecha). Alt Enter mostra os detalhes de qualquer mensagem.
Esc cancela um download.

NO LEITOR DE ÁUDIO E VÍDEO
Espaço: tocar ou pausar. Seta para a direita e para a esquerda: avançar e
voltar 5 segundos (com Shift, 30). Home: voltar ao início. + e -: mais
rápido e mais lento. Esc: fechar.

NA CAIXA DE DIGITAÇÃO
Enter: envia e esconde a caixa. Shift Enter: nova linha. Esc: cancela a
resposta, se houver, esconde a caixa e volta para as mensagens.
Depois do botão Enviar há três botões: Anexar arquivo, Gravar do microfone
e Gravar som do computador. O texto da caixa vai como legenda do arquivo.

MENU
Aperte Alt para abrir o Menu. Ele tem submenus (Contas, Contatos, Conversa,
Mensagem, Exibição e Ajuda): use a seta para a direita para entrar e a seta para a
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


class _ContasParaContatos:
    """O que o gerenciador de contatos precisa saber das contas."""

    def __init__(self, janela):
        self.j = janela

    def lista(self):
        return [(d["id"], d["servico"], d.get("nome") or d["id"])
                for d in self.j.cfg.contas()]

    def provedor(self, conta_id):
        return self.j.contas.provedores.get(conta_id)


class _PrivacidadeParaConfig:
    """O que a janela de configuracoes precisa para mostrar a privacidade
    da conta do WhatsApp."""

    def __init__(self, janela):
        self.j = janela

    def contas(self):
        """[(conta_id, rotulo, servico)] das contas conectadas."""
        achadas = []
        for d in self.j.cfg.contas():
            p = self.j.contas.provedores.get(d["id"])
            if d.get("servico") in ("whatsapp", "telegram") and \
                    p is not None and \
                    self.j.estados.get(d["id"]) == ev.CONECTADA:
                servico = m.SERVICOS.get(d["servico"], "")
                achadas.append((d["id"], "%s, %s" % (
                    d.get("nome") or d.get("telefone") or d["id"], servico),
                    d["servico"]))
        return achadas

    def ler(self, conta_id):
        from telezapp.nucleo import privacidade_conta as pw
        p = self.j.contas.provedores.get(conta_id)
        if p is None:
            return None
        valores = p.privacidade()
        status = p.privacidade_status()
        return {"valores": valores,
                "servico": self.j.contas.servico(conta_id),
                "status": pw.texto_status(*status) if status else ""}


class Janela(wx.Frame):
    def __init__(self, cfg, banco, barramento):
        super().__init__(None, title=NOME, size=(1000, 700))
        self.cfg = cfg
        self.banco = banco
        self.contas = None            # definido por quem cria a janela
        self.midias = None            # gerente de downloads (idem)
        self.fala = Fala()
        self.conversas = []           # as do filtro, pela ultima mensagem
        self.busca = ""               # texto do campo de busca de conversas
        self.trancadas_liberadas = False   # codigo secreto digitado agora
        self._tipos_atuais = m.tipos_visiveis(False)
        self._buscando = False        # evita tratar a limpeza do campo
        self.filtro_tipo = self._filtro_tipo_salvo(cfg)
        self.filtro_conta = cfg.get("filtro_conta") or m.CONTA_TODAS
        self._opcoes_conta = []       # (valor, rotulo) da caixa de contas
        self._chaves_conv = []        # chave de cada item da lista
        self._rotulos_conv = []       # texto de cada item da lista
        self._acoes_enviadas = []     # respostas de botao esperando resultado
        self.rascunhos = {}           # texto nao enviado de cada conversa
        self.indice = {}              # chave -> Conversa
        self.cache = {}               # chave da conversa -> [Mensagem]
        self.atual = None             # chave da conversa aberta
        self.marcador_n = 0           # nao lidas ao abrir a conversa
        self.marcador_id = None       # id da 1a nao lida (quando conhecido)
        self.esperando_servidor = False
        self.selecao_automatica = True
        self._itens_msgs = []         # texto de cada item da lista
        self.alvo_inicial = None      # ponto guardado da conversa aberta
        self.volta_para = []          # ids de onde a pessoa pulou (Esc volta)
        self.carga_inicial = False
        self.aguardando_foco = False  # esperando o servico para dar o foco
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
        self._proximo_chave = None    # audio que toca em sequencia
        self._seq_tocados = 0         # audios da sequencia atual, apos o 1o
        self.chamada = None           # nucleo.chamadas.Chamada em curso
        self.dlg_chamada = None       # DialogoChamada aberto
        self._criar_menus()
        self._criar_controles()
        self.CreateStatusBar()
        self.Bind(wx.EVT_CLOSE, self._ao_fechar)
        if hasattr(wx, "EVT_ICONIZE"):      # minimizar esconde as trancadas
            self.Bind(wx.EVT_ICONIZE, self._ao_minimizar)
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
        item(m_contas, "ativar_contas", "&Ativar ou desativar contas...")
        item(m_contas, "reconectar", "&Conectar as contas de novo")
        item(m_contas, "remover", "&Remover uma conta...")

        m_ctt = wx.Menu()
        item(m_ctt, "contatos", "&Gerenciar contatos...")
        item(m_ctt, "salvar_pessoa",
             "&Salvar a pessoa desta conversa como contato...")

        m_conv = wx.Menu()
        item(m_conv, "ir_conv", "Ir para a lista de &conversas\tAlt+1")
        item(m_conv, "nao_lidas", "Mensagens &não lidas (marcador ou próxima "
                                  "conversa)\tAlt+2")
        item(m_conv, "ir_msgs", "Ir para a lista de &mensagens\tAlt+3")
        item(m_conv, "ir_caixa", "&Escrever mensagem\tCtrl+E")
        m_conv.AppendSeparator()
        item(m_conv, "nova_msg", "&Nova mensagem...\tCtrl+N")
        item(m_conv, "abrir_conv", "&Abrir a conversa selecionada")
        item(m_conv, "arquivar", "Ar&quivar ou desarquivar a conversa")
        item(m_conv, "trancar", "Tra&ncar ou destrancar a conversa")
        item(m_conv, "fixar", "&Fixar ou desafixar a conversa")
        item(m_conv, "silenciar", "Sile&nciar ou reativar o som da conversa")
        item(m_conv, "ler_ultima", "&Ouvir a última mensagem\tCtrl+R")
        item(m_conv, "atualizar", "A&tualizar a lista de conversas\tF5")
        item(m_conv, "ir_filtro_conta",
             "Filtro de &serviço ou conta\tAlt+4")
        item(m_conv, "ir_filtro_tipo",
             "F&iltro de tipo de conversa\tAlt+5")
        item(m_conv, "buscar_conv", "Bus&car conversa\tCtrl+F")
        item(m_conv, "esconder_trancadas",
             "Esconder as conversas tr&ancadas\tCtrl+Shift+T")

        m_msg = wx.Menu()
        item(m_msg, "responder", "&Responder\tCtrl+Shift+R")
        item(m_msg, "copiar", "&Copiar texto\tCtrl+Shift+C")
        item(m_msg, "detalhes", "&Detalhes\tAlt+Enter")
        item(m_msg, "ir_respondida", "Ir para a mensagem respondi&da")
        m_msg.AppendSeparator()
        item(m_msg, "abrir_midia", "&Abrir mídia\tCtrl+O")
        item(m_msg, "baixar_midia", "&Baixar mídia sem abrir\tCtrl+B")
        item(m_msg, "salvar_midia", "Salvar c&ópia da mídia...")

        m_cham = wx.Menu()
        item(m_cham, "ligar", "&Ligar para esta conversa\tCtrl+Shift+L")
        item(m_cham, "chamada_janela",
             "Mostrar a &janela da chamada\tCtrl+Shift+J")
        item(m_cham, "chamada_mudo",
             "&Silenciar ou ativar o microfone\tCtrl+Shift+K")
        item(m_cham, "chamada_tempo", "&Tempo de chamada")
        item(m_cham, "chamada_desligar", "&Desligar\tCtrl+Shift+H")

        m_mid = wx.Menu()
        for valor, nome in next(o for o in config.OPCOES
                                if o.chave == "midias_baixar").escolhas:
            it = item(m_mid, "baixar_" + valor, nome, "radio")
            self.Bind(wx.EVT_MENU,
                      lambda e, v=valor: self._mudar_baixar(v), it)
        m_mid.AppendSeparator()
        item(m_mid, "anexar", "&Anexar arquivo...	Ctrl+Shift+A")
        item(m_mid, "gravar_mic", "Gravar do &microfone...	Ctrl+Shift+M")
        item(m_mid, "gravar_som",
             "Gravar o &som do computador...	Ctrl+Shift+S")
        m_mid.AppendSeparator()
        item(m_mid, "audio_janela", "&Enter em áudio...")
        item(m_mid, "audio_sequencia", "Áudios em &sequência...")
        item(m_mid, "vel_mais", "Áudio mais &rápido\tCtrl+Shift+Up")
        item(m_mid, "vel_menos", "Áudio mais le&nto\tCtrl+Shift+Down")
        item(m_mid, "vel_normal", "&Velocidade normal do áudio\tCtrl+Shift+0")
        item(m_mid, "vel_escolher", "Velocidade do áu&dio...")
        item(m_mid, "vel_passo", "&Passo da velocidade do áudio...")
        item(m_mid, "midias_limite", "&Limite do download automático...")
        item(m_mid, "midias_confirmar", "&Confirmar downloads grandes...")
        item(m_mid, "midias_espaco", "&Espaço usado pelas mídias")
        item(m_mid, "midias_limpar", "L&impar mídias baixadas...")

        m_exib = wx.Menu()
        for est, nome in m.NOMES_ESTILOS.items():
            it = item(m_exib, "estilo%d" % est, nome, "radio")
            self.Bind(wx.EVT_MENU,
                      lambda e, est=est: self._mudar_estilo(est), it)
        m_exib.AppendSeparator()
        rotulos = {o.chave: o.rotulo for o in config.OPCOES}
        for chave in ("som", "falar_novas", "confirmar_envio", "falar_quem_toca",
                      "falar_reacoes"):
            item(m_exib, chave, rotulos[chave], "check")

        m_dep = wx.Menu()
        item(m_dep, "dep_msg", "Depurar esta &mensagem\tCtrl+Shift+D")
        item(m_dep, "dep_conv", "Depurar esta &conversa")
        m_dep.AppendSeparator()
        item(m_dep, "depuracao", "&Modo de depuração (guardar a estrutura "
                                 "das mensagens novas)", "check")
        item(m_dep, "log_detalhado", "&Registro técnico detalhado do "
                                     "WhatsApp (vale na próxima abertura)",
             "check")

        m_aj = wx.Menu()
        item(m_aj, "guia", "&Guia de uso\tF1")
        item(m_aj, "ajuda", "&Teclas de atalho\tShift+F1")
        item(m_aj, "novidades", "&Novidades desta versão")
        item(m_aj, "logs", "Abrir a pasta de &logs")
        item(m_aj, "sobre", "&Sobre o %s" % NOME)

        for submenu, rotulo in ((m_contas, "&Contas"), (m_ctt, "Conta&tos"),
                                (m_conv, "C&onversa"),
                                (m_msg, "&Mensagem"),
                                (m_cham, "C&hamada"), (m_mid, "Mí&dias"),
                                (m_exib, "&Exibição"),
                                (m_dep, "&Depurar"),
                                (m_aj, "A&juda")):
            raiz.AppendSubMenu(submenu, rotulo)
        raiz.AppendSeparator()
        item(raiz, "configuracoes", "C&onfigurações...	Ctrl+,")
        item(raiz, "sair", "&Sair\tCtrl+Q")
        barra.Append(raiz, "&Menu")
        self.SetMenuBar(barra)

        ligacoes = {
            "add_tg": lambda e: self.adicionar_conta("telegram"),
            "add_wa": lambda e: self.adicionar_conta("whatsapp"),
            "ativar_contas": lambda e: self._ativar_contas(),
            "reconectar": lambda e: self._reconectar(),
            "remover": lambda e: self._remover_conta(),
            "ir_filtro_conta": lambda e: self._ir_para(self.cx_conta, ""),
            "ir_filtro_tipo": lambda e: self._ir_para(self.cx_tipo, ""),
            "buscar_conv": lambda e: self._ir_para(self.campo_busca, ""),
            "esconder_trancadas": lambda e: self._esconder_trancadas(),
            "contatos": lambda e: self._gerenciar_contatos(),
            "salvar_pessoa": lambda e: self._salvar_pessoa(),
            "logs": lambda e: self._abrir_logs(),
            "sair": lambda e: self.Close(),
            "configuracoes": lambda e: self._configuracoes(),
            "ir_conv": lambda e: self._ir_para(self.lista_conv, "conversas"),
            "ir_msgs": lambda e: self._ir_para(self.lista_msgs, "mensagens"),
            "ir_caixa": lambda e: self._mostrar_caixa(),
            "nova_msg": lambda e: self._nova_mensagem(),
            "abrir_conv": lambda e: self._abrir_selecionada_na_lista(),
            "arquivar": lambda e: self._arquivar_conversa(),
            "trancar": lambda e: self._trancar_conversa(),
            "fixar": lambda e: self._fixar_conversa(),
            "silenciar": lambda e: self._silenciar_conversa(),
            "nao_lidas": lambda e: self._ir_nao_lidas(),
            "ler_ultima": lambda e: self._ler_ultima(),
            "atualizar": lambda e: self._atualizar_conversas(),
            "responder": lambda e: self._responder(),
            "copiar": lambda e: self._copiar(),
            "ir_respondida": lambda e: self._ir_para_respondida(),
            "detalhes": lambda e: self._detalhes(),
            "dep_msg": lambda e: self._depurar_mensagem(),
            "dep_conv": lambda e: self._depurar_conversa(),
            "ajuda": lambda e: dialogos.mostrar_texto(
                self, "Teclas de atalho", AJUDA, "Teclas de atalho"),
            "anexar": lambda e: self._anexar_arquivo(),
            "gravar_mic": lambda e: self._gravar(MICROFONE),
            "gravar_som": lambda e: self._gravar(SOM_INTERNO),
            "ligar": lambda e: self._ligar(),
            "chamada_janela": lambda e: self._mostrar_chamada(),
            "chamada_mudo": lambda e: self._alternar_mudo(),
            "chamada_tempo": lambda e: self._falar_tempo_da_chamada(),
            "chamada_desligar": lambda e: self._desligar_chamada(),
            "abrir_midia": lambda e: self._abrir_midia(),
            "baixar_midia": lambda e: self._abrir_midia(abrir=False),
            "salvar_midia": lambda e: self._salvar_midia(),
            "audio_janela": lambda e: self._escolher_opcao("audio_janela"),
            "audio_sequencia": lambda e: self._escolher_opcao(
                "audio_sequencia"),
            "vel_mais": lambda e: self._mudar_velocidade(+1),
            "vel_menos": lambda e: self._mudar_velocidade(-1),
            "vel_normal": lambda e: self._aplicar_velocidade(1.0),
            "vel_escolher": lambda e: self._escolher_velocidade(),
            "vel_passo": lambda e: self._escolher_passo(),
            "midias_limite": lambda e: self._escolher_opcao(
                "midias_limite_auto_mb"),
            "midias_confirmar": lambda e: self._escolher_opcao(
                "midias_confirmar_mb"),
            "midias_espaco": lambda e: self._espaco_midias(),
            "midias_limpar": lambda e: self._limpar_midias(),
            "guia": lambda e: self._abrir_pagina("guia.html"),
            "novidades": lambda e: self._abrir_pagina("novidades.html"),
            "sobre": lambda e: self._sobre(),
        }
        for chave, tratador in ligacoes.items():
            self.Bind(wx.EVT_MENU, seguro(tratador), self.itens[chave])
        self.banco.depuracao = bool(self.cfg.get("depuracao"))
        self.itens["depuracao"].Check(self.banco.depuracao)
        self.Bind(wx.EVT_MENU,
                  lambda e: self._modo_depuracao(e.IsChecked()),
                  self.itens["depuracao"])
        self.itens["log_detalhado"].Check(
            bool(self.cfg.get("log_detalhado_whatsapp")))
        self.Bind(wx.EVT_MENU,
                  lambda e: self._log_detalhado(e.IsChecked()),
                  self.itens["log_detalhado"])
        for chave in ("som", "falar_novas", "confirmar_envio", "falar_quem_toca",
                      "falar_reacoes"):
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
        rot_cx_conta = wx.StaticText(painel, label="Serviço ou conta")
        self.cx_conta = wx.Choice(painel, name="Serviço ou conta")
        rot_cx_tipo = wx.StaticText(painel, label="Tipo de conversa")
        self.cx_tipo = wx.Choice(
            painel, choices=[r for _, r in self._tipos_atuais],
            name="Tipo de conversa")
        self.cx_tipo.SetSelection(self._indice_tipo())
        rot_busca = wx.StaticText(painel, label="Buscar conversa")
        self.campo_busca = wx.TextCtrl(painel, name="Buscar conversa",
                                       style=wx.TE_PROCESS_ENTER)
        self.campo_busca.Bind(wx.EVT_TEXT, seguro(self._ao_busca))
        self.campo_busca.Bind(
            wx.EVT_TEXT_ENTER,
            seguro(lambda e: self._busca_pronta()))
        self.cx_conta.Bind(wx.EVT_CHOICE, seguro(self._ao_filtro_conta))
        self.cx_tipo.Bind(wx.EVT_CHOICE, seguro(self._ao_filtro_tipo))
        rot_conv = wx.StaticText(painel, label="Conversas")
        self.lista_conv = wx.ListBox(painel, style=wx.LB_SINGLE | wx.LB_HSCROLL,
                                     name="Conversas")
        self.rot_msgs = wx.StaticText(painel, label="Mensagens")
        self.lista_msgs = wx.ListBox(painel, style=wx.LB_SINGLE | wx.LB_HSCROLL,
                                     name="Mensagens")
        # botoes de resposta da mensagem selecionada: controles de verdade,
        # criados aqui para ficarem na ordem de Tab logo depois da lista
        # (so aparecem quando a mensagem selecionada tem botoes ou opcoes)
        self.botoes_acao, self._acoes_atuais = [], []
        self._msg_das_acoes, self._botoes_chave = None, None
        for i in range(MAX_BOTOES_ACAO):
            b = wx.Button(painel, label="Botão")
            b.Show(False)
            b.Bind(wx.EVT_BUTTON, seguro(lambda e, k=i: self._tocar_botao(k)))
            self.botoes_acao.append(b)
        # links do texto ou da legenda e botoes de endereco: mesma ideia,
        # logo depois dos botoes de resposta
        self.botoes_link, self._links_atuais = [], []
        for i in range(MAX_BOTOES_LINK):
            b = wx.Button(painel, label="Link")
            b.Show(False)
            b.Bind(wx.EVT_BUTTON,
                   seguro(lambda e, k=i: self._abrir_botao_link(k)))
            self.botoes_link.append(b)
        # pessoas mencionadas: um botao cada, depois dos links; Enter abre a
        # conversa com a pessoa
        self.botoes_mencao, self._mencoes_atuais = [], []
        for i in range(MAX_BOTOES_LINK):
            b = wx.Button(painel, label="Pessoa")
            b.Show(False)
            b.Bind(wx.EVT_BUTTON,
                   seguro(lambda e, k=i: self._abrir_botao_mencao(k)))
            self.botoes_mencao.append(b)
        self.rot_caixa =wx.StaticText(painel, label="Digite sua mensagem")
        self.caixa = wx.TextCtrl(painel, style=wx.TE_MULTILINE,
                                 name="Digite sua mensagem")
        self.botao_enviar = wx.Button(painel, label="&Enviar")
        # sem tecla de acesso: Alt abre o Menu e as letras ja estao em uso
        self.botao_anexar = wx.Button(painel, label="Anexar arquivo")
        self.botao_mic = wx.Button(painel, label="Gravar do microfone")
        self.botao_som = wx.Button(painel, label="Gravar som do computador")
        self.botoes_envio = (self.botao_enviar, self.botao_anexar,
                             self.botao_mic, self.botao_som)

        esq = wx.BoxSizer(wx.VERTICAL)
        esq.Add(rot_cx_conta, 0, wx.BOTTOM, 2)
        esq.Add(self.cx_conta, 0, wx.EXPAND | wx.BOTTOM, 6)
        esq.Add(rot_cx_tipo, 0, wx.BOTTOM, 2)
        esq.Add(self.cx_tipo, 0, wx.EXPAND | wx.BOTTOM, 6)
        esq.Add(rot_busca, 0, wx.BOTTOM, 2)
        esq.Add(self.campo_busca, 0, wx.EXPAND | wx.BOTTOM, 6)
        esq.Add(rot_conv, 0, wx.BOTTOM, 4)
        esq.Add(self.lista_conv, 1, wx.EXPAND)
        dir_ = wx.BoxSizer(wx.VERTICAL)
        dir_.Add(self.rot_msgs, 0, wx.BOTTOM, 4)
        dir_.Add(self.lista_msgs, 3, wx.EXPAND)
        linha_acoes = wx.WrapSizer(wx.HORIZONTAL)
        for b in self.botoes_acao:
            linha_acoes.Add(b, 0, wx.RIGHT, 6)
        dir_.Add(linha_acoes, 0, wx.TOP, 4)
        linha_links = wx.WrapSizer(wx.HORIZONTAL)
        for b in self.botoes_link:
            linha_links.Add(b, 0, wx.RIGHT, 6)
        dir_.Add(linha_links, 0, wx.TOP, 4)
        linha_mencoes = wx.WrapSizer(wx.HORIZONTAL)
        for b in self.botoes_mencao:
            linha_mencoes.Add(b, 0, wx.RIGHT, 6)
        dir_.Add(linha_mencoes, 0, wx.TOP, 4)
        dir_.Add(self.rot_caixa, 0, wx.TOP | wx.BOTTOM, 4)
        dir_.Add(self.caixa, 1, wx.EXPAND)
        linha_envio = wx.WrapSizer(wx.HORIZONTAL)
        for b in self.botoes_envio:
            linha_envio.Add(b, 0, wx.RIGHT, 6)
        dir_.Add(linha_envio, 0, wx.TOP, 6)
        raiz = wx.BoxSizer(wx.HORIZONTAL)
        raiz.Add(esq, 1, wx.EXPAND | wx.ALL, 8)
        raiz.Add(dir_, 2, wx.EXPAND | wx.ALL, 8)
        painel.SetSizer(raiz)

        self.lista_conv.Bind(wx.EVT_LISTBOX_DCLICK,
                             seguro(lambda e: self._abrir_selecionada_na_lista()))
        self.lista_conv.Bind(wx.EVT_CONTEXT_MENU, seguro(self._menu_conversa))
        self.lista_msgs.Bind(wx.EVT_CONTEXT_MENU, seguro(self._menu_mensagem))
        self.lista_msgs.Bind(wx.EVT_KEY_DOWN, self._tecla_mensagens)
        self.lista_msgs.Bind(wx.EVT_LISTBOX,
                             seguro(lambda e: self._atualizar_botoes()))
        self.botao_enviar.Bind(wx.EVT_BUTTON,
                               seguro(lambda e: self._enviar_texto()))
        self.botao_anexar.Bind(wx.EVT_BUTTON,
                               seguro(lambda e: self._anexar_arquivo()))
        self.botao_mic.Bind(wx.EVT_BUTTON,
                            seguro(lambda e: self._gravar(MICROFONE)))
        self.botao_som.Bind(wx.EVT_BUTTON,
                            seguro(lambda e: self._gravar(SOM_INTERNO)))
        self._mostrar_conversa(False, False)

    def _mostrar_conversa(self, mensagens, escrever):
        """Sem conversa aberta so a lista de conversas aparece; com a
        conversa aberta aparecem as mensagens e a caixa de digitar."""
        for w in (self.rot_msgs, self.lista_msgs):
            w.Show(mensagens)
        for w in (self.rot_caixa, self.caixa) + self.botoes_envio:
            w.Show(escrever)
        if not mensagens:
            self._botoes_chave = None
            for b in (self.botoes_acao + self.botoes_link
                      + self.botoes_mencao):
                b.Show(False)
        self.painel.Layout()

    def _atualizar_botoes(self):
        """Mostra, logo depois da lista, um botao para cada botao/opcao da
        mensagem selecionada (Tab vai de um ao outro). Nao mexe no foco, a
        nao ser que o botao focado deixe de existir."""
        x = self._mensagem_selecionada() if self.atual else None
        acoes = m.extras_de(x)["acoes"][:MAX_BOTOES_ACAO] if x else []
        links = m.itens_de_link(x)[:MAX_BOTOES_LINK] if x else []
        mencoes = [dict(p) for p in m.extras_de(x)["mencoes"]
                   ][:MAX_BOTOES_LINK] if x else []
        rotulos_mencao = [dialogos.rotulo_mencao(p) for p in mencoes]
        chave = (x.id if x else None,
                 tuple(a.get("rotulo", "") for a in acoes),
                 tuple(links), tuple(rotulos_mencao))
        if chave == self._botoes_chave:
            return
        self._botoes_chave = chave
        self._acoes_atuais, self._msg_das_acoes = acoes, x
        self._links_atuais = links
        self._mencoes_atuais = mencoes
        perdeu_foco = False
        for i, b in enumerate(self.botoes_acao):
            if i < len(acoes):
                b.SetLabel((acoes[i].get("rotulo") or "Botão")
                           .replace("&", "&&"))
                b.Show(True)
            else:
                perdeu_foco = perdeu_foco or b.HasFocus()
                b.Show(False)
        for i, b in enumerate(self.botoes_link):
            if i < len(links):
                rotulo = links[i][0]
                if len(rotulo) > LIMITE_ROTULO_LINK:
                    rotulo = rotulo[:LIMITE_ROTULO_LINK - 1] + "…"
                b.SetLabel(rotulo.replace("&", "&&"))
                b.Show(True)
            else:
                perdeu_foco = perdeu_foco or b.HasFocus()
                b.Show(False)
        for i, b in enumerate(self.botoes_mencao):
            if i < len(mencoes):
                b.SetLabel(("Pessoa: " + rotulos_mencao[i])
                           .replace("&", "&&"))
                b.Show(True)
            else:
                perdeu_foco = perdeu_foco or b.HasFocus()
                b.Show(False)
        if perdeu_foco:
            self.lista_msgs.SetFocus()
        self.painel.Layout()

    @seguro
    def _abrir_botao_mencao(self, i):
        if 0 <= i < len(self._mencoes_atuais) and self._msg_das_acoes:
            self._abrir_conversa_da_mencao(self._msg_das_acoes,
                                           self._mencoes_atuais[i])

    @seguro
    def _abrir_botao_link(self, i):
        if 0 <= i < len(self._links_atuais):
            url = self._links_atuais[i][1]
            if dialogos.abrir_link(url):
                self.fala.falar("Abrindo no navegador.", interromper=True)
            else:
                self.fala.falar("Não consegui abrir o link.",
                                interromper=True)

    @seguro
    def _tocar_botao(self, i):
        if 0 <= i < len(self._acoes_atuais) and self._msg_das_acoes:
            self._tocar_acao(self._msg_das_acoes, self._acoes_atuais[i])

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
        self.cx_conta.SetFocus()
        if self.lista_conv.GetCount():
            ultima = self.cfg.get("ultima_conversa")
            chave = tuple(ultima) if isinstance(ultima, list) else None
            self.lista_conv.SetSelection(
                self._chaves_conv.index(chave)
                if chave in self._chaves_conv else 0)
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
                self._limpar_codigo_trancadas()
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
            self._limpar_codigo_trancadas()
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
            ev.ConversaApagadaNoCelular: self._ev_conversa_apagada,
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
            ev.EstadoChamada: self._ev_chamada,
            ev.MensagemAtualizada: self._ev_atualizada,
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
        conv = self.indice.get(self.atual) if self.atual else None
        if conv is not None and e.conta_id == conv.conta_id and \
                self.rot_msgs.GetLabel() != "Mensagens de " + conv.nome:
            # a conversa aberta mudou de nome (ex.: grupo renomeado)
            self.rot_msgs.SetLabel("Mensagens de " + conv.nome)
            self._atualizar_titulo()

    def _juntar_conversas(self, conta_id, conversas):
        aberta = self.atual
        # listas de transmissao nao aceitam envio: nao entram na lista
        conversas = [c for c in conversas
                     if not c.id.endswith("@broadcast")
                     and not self.banco.conversa_apagada(c)]
        for c in conversas:
            if c.tipo == "privada":
                c.nome = self.banco.nome_de_contato(
                    c.conta_id, c.id) or c.nome
            if c.chave == aberta:
                c.nao_lidas = 0   # a pessoa esta lendo esta conversa
            if list(c.chave) in (self.cfg.get("trancadas_locais") or []):
                c.trancada = True     # trancada pelo TeleZapp
            self.indice[c.chave] = c
        novas = {c.chave for c in conversas}
        for chave in [k for k in self.indice
                      if k[0] == conta_id and k not in novas and k != aberta]:
            del self.indice[chave]
        self._ordenar()

    def _ordenar(self):
        self._atualizar_caixa_conta()
        self.conversas = sorted(
            (c for c in self.indice.values()
             if c.chave == self.atual or m.passa_filtro(
                 c, self.filtro_tipo, self.filtro_conta, self.busca)),
            key=lambda c: (not c.fixada, -c.data))

    def _preencher_conversas(self):
        """Refaz a lista mantendo a conversa selecionada (por chave)."""
        if not self.conversas:
            if self.indice and self._chaves_conv != []:
                # ha conversas, mas nenhuma passa no filtro
                self._chaves_conv, self._rotulos_conv = [], []
                self.lista_conv.Set([TEXTO_FILTRO_VAZIO])
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
        # Atualiza a lista no lugar, sem limpar e refazer tudo: o NVDA repete
        # o nome da conversa em foco sempre que a lista e recriada ou a
        # selecao e reposta.
        lista = self.lista_conv
        if lista.GetCount() != len(self._rotulos_conv):
            lista.Set(rotulos)          # lista com texto de aviso
            self._chaves_conv, self._rotulos_conv = chaves, rotulos
            lista.SetSelection(chaves.index(antes)
                               if antes in chaves else 0)
            return
        while lista.GetCount() > len(rotulos):
            lista.Delete(lista.GetCount() - 1)
        for k, novo in enumerate(rotulos):
            if k >= lista.GetCount():
                lista.Append(novo)
            elif (k >= len(self._rotulos_conv)
                    or self._rotulos_conv[k] != novo):
                lista.SetString(k, novo)
        self._chaves_conv, self._rotulos_conv = chaves, rotulos
        alvo = (chaves.index(antes) if antes in chaves
                else min(max(i, 0), len(chaves) - 1))
        if lista.GetSelection() != alvo:
            lista.SetSelection(alvo)

    def _ev_mensagens(self, e):
        chave = (e.conta_id, e.conversa_id)
        lista = self._mesclar(chave, e.mensagens)
        if chave != self.atual:
            return
        primeira = self.esperando_servidor
        if self.esperando_servidor:
            self.esperando_servidor = False
            if self.marcador_n > 0:
                recebidas = [x for x in lista if not x.minha]
                n = min(self.marcador_n, len(recebidas))
                self.marcador_id = recebidas[-n].id if n else None
        inicial = primeira or self.carga_inicial or self.mapa == [None]
        self.carga_inicial = False
        destino = None
        if self.selecao_automatica and inicial:
            # so na primeira carga da conversa recem-aberta
            destino = self._destino_inicial()
        self._preencher_mensagens(destino)
        if primeira and self.alvo_inicial and \
                self.alvo_inicial not in self.mapa:
            self.fala.falar("Não achei o ponto em que você parou; abri no "
                            "%s." % ("marcador de não lidas"
                                     if self.marcador_id else "fim"))
        if primeira:
            self._dar_foco_as_mensagens()

    @staticmethod
    def _filtro_tipo_salvo(cfg):
        valor = cfg.get("filtro_conversas")
        if valor == "trancadas" and cfg.get("trancadas_exigir_codigo"):
            return "todas"        # so com o codigo, a cada abertura
        return valor if valor in dict(m.FILTROS_TIPO) else "todas"

    def _trancadas_visiveis(self):
        return self.trancadas_liberadas or \
            not self.cfg.get("trancadas_exigir_codigo")

    def _indice_tipo(self):
        return [v for v, _ in self._tipos_atuais].index(self.filtro_tipo)

    def _montar_tipos(self):
        """Refaz a caixa de tipos: Trancadas so entra no fim quando
        liberada (codigo digitado) ou quando a opcao permite."""
        tipos = m.tipos_visiveis(self._trancadas_visiveis())
        if tipos == self._tipos_atuais:
            return
        self._tipos_atuais = tipos
        if self.filtro_tipo not in dict(tipos):
            self.filtro_tipo = "todas"
        self.cx_tipo.Set([r for _, r in tipos])
        self.cx_tipo.SetSelection(self._indice_tipo())

    def _conversa_em_foco(self):
        conv = self.indice.get(self.atual) if self.atual else None
        if conv is None:
            i = self.lista_conv.GetSelection()
            if 0 <= i < len(self._chaves_conv):
                conv = self.indice.get(self._chaves_conv[i])
        return conv

    def _arquivar_conversa(self, conv=None):
        """Arquiva a conversa em foco, ou a tira dos arquivados. No Telegram
        a conta tambem e avisada; no WhatsApp a biblioteca nao deixa, entao
        vale so no TeleZapp."""
        conv = conv or self._conversa_em_foco()
        if conv is None:
            self.fala.falar("Nenhuma conversa selecionada.")
            return
        arquivar = not conv.arquivada
        prov = self.contas.provedor(conv.conta_id)
        na_conta = False
        try:
            na_conta = bool(prov and prov.arquivar_conversa(conv.id, arquivar))
        except Exception:
            log.exception("erro ao arquivar na conta")
        conv.arquivada = arquivar
        self.banco.salvar_conversas([conv])
        if self.atual == conv.chave:
            self._fechar_conversa()
        self._ordenar()
        self._preencher_conversas()
        self.fala.falar("%s%s." % (
            "Conversa arquivada" if arquivar else "Conversa desarquivada",
            "" if na_conta else ", só no TeleZapp"), interromper=True)

    def _trancar_conversa(self, conv=None):
        """Tranca a conversa em foco, ou a destranca. Vale so no TeleZapp: o
        WhatsApp nao deixa a biblioteca trancar no celular. A conversa trancada
        some das listas e so aparece no tipo Trancadas."""
        conv = conv or self._conversa_em_foco()
        if conv is None:
            self.fala.falar("Nenhuma conversa selecionada.")
            return
        trancar = not conv.trancada
        locais = [k for k in (self.cfg.get("trancadas_locais") or [])
                  if tuple(k) != conv.chave]
        if trancar:
            locais.append(list(conv.chave))
        self.cfg.set("trancadas_locais", locais)
        conv.trancada = trancar
        self.banco.salvar_conversas([conv])
        if self.atual == conv.chave:
            self._fechar_conversa()
        self._montar_tipos()
        self._ordenar()
        self._preencher_conversas()
        if not trancar:
            texto = "Conversa destrancada, só no TeleZapp."
        elif self.cfg.get("trancadas_exigir_codigo") and                 not self.cfg.get("codigo_trancadas"):
            texto = ("Conversa trancada, só no TeleZapp. Ela fica escondida "
                     "até você definir um código secreto em Configurações.")
        else:
            texto = "Conversa trancada, só no TeleZapp. Veja no tipo Trancadas."
        self.fala.falar(texto, interromper=True)

    def _depois_de_mudar_conversa(self, conv):
        self.banco.salvar_conversas([conv])
        self._ordenar()
        self._preencher_conversas()

    def _avisar_conta(self, conv, acao, texto_falha):
        """Conta o que mudou ao servico sem travar a janela; se ele nao
        aceitar, diz que a mudanca ficou so no TeleZapp."""
        prov = self.contas.provedor(conv.conta_id)
        if prov is None:
            return

        def avisar():
            try:
                ok = bool(acao(prov))
            except Exception:
                log.exception("erro ao avisar a conta")
                ok = False
            if not ok:
                wx.CallAfter(lambda: self.fala.falar(texto_falha))
        threading.Thread(target=avisar, daemon=True,
                         name="avisar-conta").start()

    def _fixar_conversa(self, conv=None):
        """Fixa a conversa no topo da lista, ou a desafixa; o servico e
        avisado."""
        conv = conv or self._conversa_em_foco()
        if conv is None:
            self.fala.falar("Nenhuma conversa selecionada.")
            return
        fixar = not conv.fixada
        conv.fixada = fixar
        self._depois_de_mudar_conversa(conv)
        self._avisar_conta(
            conv, lambda p: p.fixar_conversa(conv.id, fixar),
            "O serviço não aceitou. A mudança ficou só no TeleZapp.")
        self.fala.falar("Conversa fixada." if fixar
                        else "Conversa desafixada.", interromper=True)

    DURACOES_SILENCIO = (("8 horas", 8 * 3600), ("1 semana", 7 * 86400),
                         ("Sempre", 0))

    def _silenciar_conversa(self, conv=None):
        """Silencia a conversa (8 horas, 1 semana ou sempre) ou reativa o
        som. Conversa silenciada nao avisa mensagens novas."""
        conv = conv or self._conversa_em_foco()
        if conv is None:
            self.fala.falar("Nenhuma conversa selecionada.")
            return
        segundos = 0
        silenciar = not conv.silenciada()
        if silenciar:
            dlg = wx.SingleChoiceDialog(
                self, "Silenciar a conversa com %s por quanto tempo?" %
                conv.nome, "Silenciar",
                [r for r, _ in self.DURACOES_SILENCIO])
            try:
                if dlg.ShowModal() != wx.ID_OK:
                    return
                segundos = self.DURACOES_SILENCIO[dlg.GetSelection()][1]
            finally:
                dlg.Destroy()
        conv.silenciada_ate = (time.time() + segundos if segundos else -1.0) \
            if silenciar else 0.0
        self._depois_de_mudar_conversa(conv)
        self._avisar_conta(
            conv, lambda p: p.silenciar_conversa(conv.id, silenciar, segundos),
            "O serviço não aceitou. A mudança ficou só no TeleZapp.")
        self.fala.falar("Conversa silenciada." if silenciar
                        else "Som da conversa reativado.", interromper=True)

    def _apagar_conversa(self, conv=None):
        """Apaga a conversa e tudo dela neste computador. Fica registrada
        como apagada: so volta com mensagem nova, ou com novo pareamento."""
        conv = conv or self._conversa_em_foco()
        if conv is None:
            self.fala.falar("Nenhuma conversa selecionada.")
            return
        prov = self.contas.provedor(conv.conta_id)
        no_celular = bool(prov and prov.APAGA_NA_CONTA and
                          self.estados.get(conv.conta_id) == ev.CONECTADA)
        texto = ("Apagar a conversa com %s? As mensagens e as mídias dela "
                 "serão apagadas deste computador. Ela só volta se chegar "
                 "uma mensagem nova." % conv.nome)
        if no_celular:
            dlg = wx.MessageDialog(
                self, texto + " Quer apagar também no celular?",
                "Apagar conversa",
                wx.YES_NO | wx.CANCEL | wx.CANCEL_DEFAULT | wx.ICON_QUESTION)
            dlg.SetYesNoCancelLabels("Apagar aqui e no celular",
                                     "Apagar só aqui", "Cancelar")
            try:
                r = dlg.ShowModal()
            finally:
                dlg.Destroy()
            if r == wx.ID_CANCEL:
                return
            no_celular = r == wx.ID_YES
        else:
            r = wx.MessageBox(
                texto + " A conta não é afetada.", "Apagar conversa",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
            if r != wx.YES:
                return
        ultima = None
        if no_celular:
            guardadas = self.banco.mensagens(conv.conta_id, conv.id, 1)
            ultima = guardadas[-1] if guardadas else None
        self._remover_conversa_local(conv)
        if no_celular:
            self.fala.falar("Conversa apagada aqui. Apagando no celular...",
                            interromper=True)
            threading.Thread(
                target=self._apagar_no_celular, args=(prov, conv, ultima),
                daemon=True, name="apagar-no-celular").start()
        else:
            self.fala.falar("Conversa apagada. Ela só volta com uma "
                            "mensagem nova.", interromper=True)

    def _apagar_no_celular(self, prov, conv, ultima):
        ok = prov.apagar_conversa(conv.id, ultima)
        wx.CallAfter(lambda: self.fala.falar(
            "Conversa apagada também no celular." if ok else
            "Não consegui apagar a conversa no celular. Ela foi apagada só "
            "aqui.", interromper=True))

    def _ev_conversa_apagada(self, e):
        """Conversa apagada no celular: apaga aqui tambem, a menos que ja
        tenha mensagem mais nova que o aviso (ela voltou a ser usada)."""
        conv = self.indice.get((e.conta_id, e.conversa_id))
        if conv is None or (e.data and conv.data > e.data + 5):
            return
        self._remover_conversa_local(conv)
        self.fala.falar("A conversa com %s foi apagada no celular e também "
                        "aqui." % conv.nome, interromper=True)

    def _remover_conversa_local(self, conv):
        chave = conv.chave
        if self.atual == chave:
            self._fechar_conversa()
        for linha in self.banco.todas_midias():
            if (linha[0], linha[1]) == chave:
                try:
                    os.remove(linha[4])
                except OSError:
                    pass
        armazem.apagar_conversa(*chave)
        self.banco.apagar_conversa(chave[0], chave[1], conv.data)
        self.indice.pop(chave, None)
        self.cache.pop(chave, None)
        self.rascunhos.pop(chave, None)
        locais = [k for k in (self.cfg.get("trancadas_locais") or [])
                  if tuple(k) != chave]
        self.cfg.set("trancadas_locais", locais)
        self._montar_tipos()
        self._ordenar()
        self._preencher_conversas()

    def _atualizar_caixa_conta(self):
        """Mantem a caixa de contas em dia: todas, cada servico que tem
        conta e, onde um servico tem mais de uma, cada conta."""
        opcoes = m.opcoes_de_conta(
            [(d["id"], d["servico"], (d.get("nome") or d["id"]) + (
                " (desativada)" if d.get("ativa", True) is False else ""))
             for d in self.cfg.contas()])
        if opcoes == self._opcoes_conta:
            return
        self._opcoes_conta = opcoes
        valores = [v for v, _ in opcoes]
        if self.filtro_conta not in valores:
            self.filtro_conta = m.CONTA_TODAS
        self.cx_conta.Set([r for _, r in opcoes])
        self.cx_conta.SetSelection(valores.index(self.filtro_conta))

    def _resumo_filtro(self):
        n = len(self._chaves_conv)
        return "%s. %s" % (
            dict(self._opcoes_conta).get(self.filtro_conta, ""),
            "Nenhuma conversa" if n == 0 else
            "1 conversa" if n == 1 else "%d conversas" % n)

    def _aplicar_filtros(self, falar=True):
        self._ordenar()
        self._preencher_conversas()
        if falar:
            self.fala.falar("%s, %s" % (
                dict(m.FILTROS_TIPO)[self.filtro_tipo],
                self._resumo_filtro()), interromper=True)

    def _ao_filtro_conta(self, evento=None):
        i = self.cx_conta.GetSelection()
        if 0 <= i < len(self._opcoes_conta):
            self.filtro_conta = self._opcoes_conta[i][0]
            self.cfg.set("filtro_conta", self.filtro_conta)
            self._aplicar_filtros()

    def _ao_filtro_tipo(self, evento=None):
        i = self.cx_tipo.GetSelection()
        if 0 <= i < len(self._tipos_atuais):
            self.filtro_tipo = self._tipos_atuais[i][0]
            self._guardar_filtro_tipo()
            self._esconder_se_saiu_das_trancadas()
            self._aplicar_filtros()

    def _esconder_se_saiu_das_trancadas(self):
        """Saiu do tipo Trancadas: elas somem de novo e so voltam quando o
        codigo for digitado outra vez na busca."""
        if self.trancadas_liberadas and self.filtro_tipo != "trancadas":
            self._esconder_trancadas(falar=False)

    def _guardar_filtro_tipo(self):
        # Trancadas nunca e lembrado: a cada abertura pede o codigo de novo
        if not (self.filtro_tipo == "trancadas"
                and self.cfg.get("trancadas_exigir_codigo")):
            self.cfg.set("filtro_conversas", self.filtro_tipo)

    # ------------------------------------------------- busca e trancadas
    def _ao_busca(self, evento=None):
        if self._buscando:
            return
        texto = self.campo_busca.GetValue().strip()
        dados = self.cfg.get("codigo_trancadas")
        if (self.cfg.get("trancadas_exigir_codigo")
                and not self.trancadas_liberadas
                and codigo_secreto.pode_ser_codigo(texto)
                and codigo_secreto.confere(texto, dados)):
            self._liberar_trancadas()
            return
        self.busca = texto
        self._aplicar_filtros(falar=False)

    def _ao_minimizar(self, evento):
        evento.Skip()
        if evento.IsIconized():
            self._esconder_trancadas(falar=False)

    def _busca_pronta(self):
        """Enter no campo de busca: fala o resultado e vai para a lista."""
        self.fala.falar(self._resumo_filtro(), interromper=True)
        if self._chaves_conv:
            self.lista_conv.SetFocus()

    def _liberar_trancadas(self):
        """Codigo certo: o campo volta a ficar vazio (o codigo nao fica na
        tela), Trancadas entra no fim da caixa de tipos e e escolhida."""
        self._buscando = True
        try:
            self.campo_busca.SetValue("")
        finally:
            self._buscando = False
        self.busca = ""
        self.trancadas_liberadas = True
        self._montar_tipos()
        self.filtro_tipo = "trancadas"
        self.cx_tipo.SetSelection(self._indice_tipo())
        self._aplicar_filtros(falar=False)
        self.fala.falar("Conversas trancadas liberadas. %s" %
                        self._resumo_filtro(), interromper=True)

    def _esconder_trancadas(self, falar=True):
        """Volta a esconder as trancadas (precisa do codigo de novo)."""
        if not self.trancadas_liberadas:
            if falar:
                self.fala.falar("As conversas trancadas já estão escondidas.")
            return
        self.trancadas_liberadas = False
        conv = self.indice.get(self.atual) if self.atual else None
        if conv is not None and conv.trancada and \
                self.cfg.get("trancadas_exigir_codigo"):
            self._fechar_conversa()
        self._montar_tipos()
        self._aplicar_filtros(falar=False)
        if falar:
            self.fala.falar("Conversas trancadas escondidas.",
                            interromper=True)

    def _limpar_codigo_trancadas(self):
        """Novo pareamento do WhatsApp apaga o codigo secreto: e o unico
        jeito de recomecar se ele for esquecido. As trancadas continuam
        escondidas ate um codigo novo ser definido em Configuracoes."""
        if not self.cfg.get("codigo_trancadas"):
            return
        self.cfg.set("codigo_trancadas", None)
        self._esconder_trancadas(falar=False)
        self.fala.falar("O código secreto das conversas trancadas foi "
                        "apagado. Defina um novo em Configurações, "
                        "Privacidade.")

    def _limite_memoria(self):
        """Mensagens mantidas por conversa (opcao da pessoa)."""
        try:
            return max(1, int(self.cfg.get("mensagens_por_conversa")
                              or LIMITE_MEMORIA))
        except (TypeError, ValueError):
            return LIMITE_MEMORIA

    def _mesclar(self, chave, novas):
        """Junta mensagens ao cache da conversa, sem repetir, em ordem."""
        atuais = {x.id: x for x in self.cache.get(chave, [])}
        for x in novas:
            if self.banco.foi_limpa(x.conta_id, x.conversa_id,
                                    x.id) == "mensagem" or \
                    x.data <= (self.banco.apagada_ate(
                        x.conta_id, x.conversa_id) or -1):
                continue      # limpa, ou de conversa apagada: so volta com
                              # mensagem nova ou novo pareamento
            atuais[x.id] = x
        lista = sorted(atuais.values(), key=_ordem)
        self.cache[chave] = lista[-self._limite_memoria():]
        return self.cache[chave]

    def _ev_nova(self, e):
        msg = e.mensagem
        if self.banco.foi_limpa(msg.conta_id, msg.conversa_id,
                                msg.id) == "mensagem" or \
                msg.data <= (self.banco.apagada_ate(
                    msg.conta_id, msg.conversa_id) or -1):
            return
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
            if self._acao_concluida(chave, msg.texto, True):
                self.fala.falar("Enviado: " + msg.texto, interromper=True)
            else:
                self._tirar_local(chave, msg.texto, msg.tipo)
        self._mesclar(chave, [msg])
        if aberta:
            # nada tira a pessoa de onde ela esta por conta propria
            self._preencher_mensagens()
            if not msg.minha and self.IsActive():
                p = self.contas.provedor(msg.conta_id)
                if p is not None:
                    p.marcar_como_lida(msg.conversa_id)
        if msg.minha or e.silenciosa:
            return  # minha, ou chegou na sincronia inicial: sem aviso
        log.info("mensagem nova (tipo %s, conversa aberta=%s)", msg.tipo,
                 aberta)
        if self._conversa_muda(conv, aberta):
            return        # arquivada ou trancada: sem som, fala nem aviso
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
        self._acao_concluida(chave, e.texto, False)
        achada = self._local_enviando(self.cache.get(chave, []), e.texto,
                                      getattr(e, "tipo", m.TEXTO))
        if achada is not None:
            achada.estado = m.FALHOU
        if chave == self.atual:
            self._preencher_mensagens()
            if e.devolver_texto and not self.caixa.GetValue():
                self.caixa.SetValue(e.texto)
        bipe("erro")
        texto = "Não foi possível enviar: %s." % e.motivo
        if chave == self.atual and e.devolver_texto:
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

    @staticmethod
    def _conversa_muda(conv, aberta):
        """Conversa arquivada, trancada ou silenciada (e fechada): nao avisa
        nada."""
        return conv is not None and not aberta and \
            bool(conv.arquivada or conv.trancada or conv.silenciada())

    def _ev_atualizada(self, e):
        """Reacao, edicao ou mensagem apagada pelo autor."""
        chave = (e.conta_id, e.conversa_id)
        for i, x in enumerate(self.cache.get(chave, [])):
            if x.id == e.mensagem.id:
                self.cache[chave][i] = e.mensagem
                break
        aberta = chave == self.atual
        if aberta:
            self._preencher_mensagens()
        conv = self.indice.get(chave)
        if self._conversa_muda(conv, aberta):
            return
        onde = conv.nome if conv else ""
        autor = "Você" if e.mensagem.minha else (e.mensagem.autor or "alguém")
        if e.motivo == "reacao":
            if e.mensagem.minha and e.emoji and self.cfg.get("falar_reacoes"):
                self.fala.falar("%s reagiu com %s à sua mensagem: %s" % (
                    e.quem, e.emoji, m.citacao(e.mensagem)))
                self.SetStatusText("%s reagiu com %s" % (e.quem, e.emoji))
        elif aberta and e.motivo == "editada":
            self.fala.falar("%s editou uma mensagem." % autor)
        elif aberta and e.motivo == "apagada":
            self.fala.falar("%s apagou uma mensagem." % autor)
        elif e.motivo in ("editada", "apagada") and onde:
            self.SetStatusText("%s %s uma mensagem em %s" % (
                autor, "editou" if e.motivo == "editada" else "apagou",
                onde))

    # ========================================================== chamadas
    def _provedor_de_chamada(self, conta_id):
        p = self.contas.provedor(conta_id) if self.contas else None
        if p is not None and getattr(p, "suporta_chamadas", False):
            return p
        return None

    def _dispositivos_da_chamada(self):
        return (self.cfg.get("chamada_microfone") or "",
                self.cfg.get("chamada_saida") or "")

    @seguro
    def _ligar(self):
        if self.chamada is not None and self.chamada.ativa:
            self.fala.falar("Já há uma chamada em andamento.",
                            interromper=True)
            self._mostrar_chamada()
            return
        conv = self.indice.get(self.atual) if self.atual is not None \
            else self._conversa_selecionada()
        if conv is None:
            bipe("erro")
            self.fala.falar("Abra ou selecione uma conversa para ligar.",
                            interromper=True)
            return
        if conv.tipo != "privada":
            bipe("erro")
            self.fala.falar("Só dá para ligar para uma conversa com uma "
                            "pessoa, não para grupos nem canais.",
                            interromper=True)
            return
        p = self._provedor_de_chamada(conv.conta_id)
        if p is None:
            bipe("erro")
            self.fala.falar("Esta conta ainda não faz chamadas de voz.",
                            interromper=True)
            return
        if self.estados.get(conv.conta_id) != ev.CONECTADA:
            bipe("erro")
            self.fala.falar("A conta não está conectada. Nada foi ligado.",
                            interromper=True)
            return
        mic, saida = self._dispositivos_da_chamada()
        log.info("ligando (%s)", conv.conta_id)
        p.ligar(conv.id, mic, saida)

    def _ev_chamada(self, e):
        c = self.chamada
        mesma = c is not None and c.ativa and \
            (c.conta_id, c.conversa_id) == (e.conta_id, e.conversa_id)
        if not mesma:
            if e.estado == ch.ENCERRADA:
                return          # fim de uma chamada que nao conhecemos
            if self.dlg_chamada is not None:
                self.dlg_chamada.fechar()
            c = self.chamada = ch.Chamada(
                e.conta_id, e.conversa_id, e.nome, e.entrante, e.estado)
            mudou = True
        else:
            if e.nome and not c.nome:
                c.nome = e.nome
            mudou = c.aplicar(e.estado, e.motivo, e.erro)
        if not mudou:
            return
        log.info("chamada: %s %s", c.estado, c.motivo)
        a = ch.apresentar(c)
        self.SetStatusText(a.situacao)
        self.fala.falar(a.fala, interromper=True)
        toque = a.som in ("toque", "chamando")
        if a.som and (not toque or self.cfg.get("toque_chamada")):
            bipe(a.som)
            if toque:
                self._repetir_toque(c, c.estado, a.som)
        self._atualizar_dialogo_chamada(c)
        if c.estado == ch.ENCERRADA:
            self.chamada = None

    def _repetir_toque(self, c, estado, som):
        """Repete o som enquanto a chamada continua no mesmo estado."""
        def de_novo():
            if self.chamada is c and c.estado == estado and \
                    self.cfg.get("toque_chamada"):
                bipe(som)
                self._repetir_toque(c, estado, som)
        wx.CallLater(3000, de_novo)

    def _atualizar_dialogo_chamada(self, c):
        if self.dlg_chamada is not None and self.dlg_chamada.chamada is c:
            self.dlg_chamada.mostrar()
            return
        p = self._provedor_de_chamada(c.conta_id)
        mics, saidas = p.dispositivos_de_audio() if p is not None \
            else ([], [])
        mic, saida = self._dispositivos_da_chamada()
        acoes = {
            "atender": self._atender_chamada,
            "recusar": self._desligar_chamada,
            "desligar": self._desligar_chamada,
            "silenciar": self._silenciar_chamada,
            "tempo": self._falar_tempo_da_chamada,
            "trocar": self._trocar_dispositivos,
        }
        self.dlg_chamada = DialogoChamada(
            self, c, acoes, lambda t: self.fala.falar(t, interromper=True),
            mics, saidas, mic, saida, ao_fechar=self._chamada_fechada)
        self.dlg_chamada.Show()
        if hasattr(self.dlg_chamada, "Raise"):
            self.dlg_chamada.Raise()

    def _chamada_fechada(self):
        self.dlg_chamada = None

    def _chamada_em_curso(self):
        if self.chamada is None or not self.chamada.ativa:
            self.fala.falar("Nenhuma chamada em andamento.",
                            interromper=True)
            return None
        return self.chamada

    @seguro
    def _mostrar_chamada(self):
        c = self._chamada_em_curso()
        if c is not None:
            self._atualizar_dialogo_chamada(c)

    @seguro
    def _atender_chamada(self):
        c = self.chamada
        p = self._provedor_de_chamada(c.conta_id) if c else None
        if c is None or p is None:
            return
        mic, saida = self._dispositivos_da_chamada()
        p.atender_chamada(c.conversa_id, mic, saida)

    @seguro
    def _desligar_chamada(self):
        c = self._chamada_em_curso()
        p = self._provedor_de_chamada(c.conta_id) if c else None
        if p is not None:
            p.encerrar_chamada(c.conversa_id)

    @seguro
    def _silenciar_chamada(self, silenciar):
        c = self.chamada
        p = self._provedor_de_chamada(c.conta_id) if c else None
        if c is None or p is None or c.estado != ch.EM_CHAMADA:
            return
        p.silenciar_chamada(c.conversa_id, silenciar)
        c.mudo = bool(silenciar)
        self.fala.falar(ch.fala_mudo(c.mudo), interromper=True)
        self._atualizar_dialogo_chamada(c)

    @seguro
    def _alternar_mudo(self):
        c = self._chamada_em_curso()
        if c is None:
            return
        if c.estado != ch.EM_CHAMADA:
            self.fala.falar("O microfone só pode ser silenciado durante "
                            "a conversa.", interromper=True)
            return
        self._silenciar_chamada(not c.mudo)

    @seguro
    def _falar_tempo_da_chamada(self):
        c = self._chamada_em_curso()
        if c is None:
            return
        if c.estado != ch.EM_CHAMADA:
            self.fala.falar("A chamada ainda não começou.",
                            interromper=True)
            return
        self.fala.falar("Em chamada há %s." % ch.falar_duracao(c.segundos()),
                        interromper=True)

    @seguro
    def _trocar_dispositivos(self, microfone, saida):
        if microfone:
            self.cfg.set("chamada_microfone", microfone)
        if saida:
            self.cfg.set("chamada_saida", saida)
        c = self.chamada
        p = self._provedor_de_chamada(c.conta_id) if c else None
        if p is not None and c.estado == ch.EM_CHAMADA:
            p.trocar_dispositivos(c.conversa_id, microfone, saida)
            self.fala.falar("Dispositivo trocado.", interromper=True)

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
                if foco is self.caixa or foco in self.botoes_envio:
                    self._sair_da_caixa()
                    return
                if foco is self.lista_msgs:
                    if not self._cancelar_download() and \
                            not self._parar_audio() and \
                            not self._voltar_da_respondida():
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
        self.alvo_inicial = self.banco.posicao(conv.conta_id, conv.id)
        self.carga_inicial = True     # a 1a resposta do servico ainda e a abertura
        guardadas = self.banco.mensagens(
            conv.conta_id, conv.id, min(LIMITE_CACHE, self._limite_memoria()))
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
            p.carregar_mensagens(conv.id, min(
                teto, self._limite_memoria(), max(50, conv.nao_lidas + 10)))
            if conv.nao_lidas:
                p.marcar_como_lida(conv.id)
        conv.nao_lidas = 0
        self._preencher_conversas()
        self._preencher_mensagens(self._destino_inicial())
        log.info("conversa aberta (%d no cache, %d não lidas)", len(lista),
                 self.marcador_n)
        if self.marcador_n > 0:
            # o foco espera o servico responder: assim o leitor de tela fala
            # uma vez so, no marcador de nao lidas
            self.aguardando_foco = True
            wx.CallLater(3000, self._dar_foco_as_mensagens, conv.chave)
        else:
            self.lista_msgs.SetFocus()

    def _dar_foco_as_mensagens(self, chave=None):
        """Leva o foco para as mensagens depois que a selecao esta no lugar
        certo (assim o leitor de tela fala uma vez so)."""
        if not self.aguardando_foco or self.atual is None or \
                (chave is not None and chave != self.atual):
            return
        self.aguardando_foco = False
        if self.FindFocus() in (self.lista_conv, None):
            self.lista_msgs.SetFocus()

    def _fechar_conversa(self):
        """Esc na lista de mensagens: fecha a conversa e volta para a lista
        de conversas. Mensagens que chegarem depois contam como novas."""
        if self.atual in self._chaves_conv:
            self.lista_conv.SetSelection(self._chaves_conv.index(self.atual))
        if self.resposta_a is not None:
            self._cancelar_resposta()
        self._guardar_posicao()
        self._guardar_lista()
        self.volta_para = []
        texto = self.caixa.GetValue()
        if texto.strip():
            self.rascunhos[self.atual] = texto
        else:
            self.rascunhos.pop(self.atual, None)
        self.caixa.Clear()
        self.marcador_id = None
        self.marcador_n = 0
        self.atual = None
        self._ordenar()               # com filtro, a conversa pode sair
        self._preencher_conversas()
        self.mapa = [None]
        self._itens_msgs = []
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

    def _atualizar_conversas(self, avisar=True):
        for conta_id in list(self.estados):
            p = self.contas.provedor(conta_id)
            if p is not None and self.estados[conta_id] == ev.CONECTADA:
                p.atualizar_conversas()
        if avisar:
            self.fala.falar("Atualizando as conversas.")

    def _reconectar(self):
        self.pareamento_recusado.clear()
        for dados in self.cfg.contas():
            if dados.get("ativa", True) is not False and \
                    self.estados.get(dados["id"]) != ev.CONECTADA:
                self.contas.reconectar(dados["id"])

    @seguro
    def _ativar_contas(self):
        """Marca quais contas ficam ligadas. Todas desmarcadas = navegar so
        no que ja esta guardado, sem conexao."""
        contas = self.cfg.contas()
        if not contas:
            self.fala.falar("Não há contas.")
            return
        nomes = ["%s, %s" % (c.get("nome") or c.get("telefone") or c["id"],
                             m.SERVICOS.get(c.get("servico"), ""))
                 for c in contas]
        dlg = wx.MultiChoiceDialog(
            self, "Marque as contas que devem ficar conectadas. Contas "
            "desmarcadas não conectam; as conversas guardadas continuam na "
            "tela. Sem nenhuma marcada, o TeleZapp funciona sem conexão.",
            "Ativar ou desativar contas", nomes)
        dlg.SetSelections([i for i, c in enumerate(contas)
                           if c.get("ativa", True) is not False])
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            marcadas = set(dlg.GetSelections())
        finally:
            dlg.Destroy()
        ligadas = desligadas = 0
        for i, c in enumerate(contas):
            antes = c.get("ativa", True) is not False
            if (i in marcadas) == antes:
                continue
            if i in marcadas:
                ligadas += self.contas.ativar(c["id"])
            else:
                desligadas += self.contas.desativar(c["id"])
        self._atualizar_caixa_conta()
        partes = []
        if ligadas:
            partes.append("%d conectando" % ligadas)
        if desligadas:
            partes.append("%d desativada%s" % (desligadas,
                                               "s" if desligadas > 1 else ""))
        self.fala.falar("Contas: " + (", ".join(partes) if partes
                                      else "nada mudou") + ".",
                        interromper=True)

    # ============================================================ mensagens
    def _mensagens_atuais(self):
        return self.cache.get(self.atual, []) if self.atual else []

    def _preencher_mensagens(self, destino=None):
        """Refaz a lista. destino: MARCADOR, "ultima" ou None (mantem)."""
        if self.atual is None:
            return
        msgs = self._mensagens_atuais()
        antes = self._chave_selecionada()
        porid = {x.id: x for x in msgs}
        itens, mapa = [], []
        anterior = None
        for x in msgs:
            if self.marcador_id is not None and x.id == self.marcador_id:
                itens.append(m.texto_marcador(self.marcador_n))
                mapa.append(MARCADOR)
            itens.append(m.formatar(x, self.estilo, anterior,
                                    respondida=self._original(x, porid)))
            mapa.append(x.id)
            anterior = x
        if not itens:
            itens = [TEXTO_CARREGANDO if self.esperando_servidor
                     else TEXTO_SEM_MENSAGENS]
            mapa = [None]
        velho_mapa, velhos = self.mapa, self._itens_msgs
        self.mapa = mapa
        self._itens_msgs = itens
        if destino is None and mapa[:len(velho_mapa)] == velho_mapa \
                and velho_mapa != [None] and \
                self.lista_msgs.GetCount() == len(velho_mapa):
            # so mudou o fim ou o texto de algum item: mexe so no que mudou
            # e nao toca na selecao (o leitor de tela nao anuncia nada)
            for k, (a, b) in enumerate(zip(velhos, itens)):
                if a != b:
                    self.lista_msgs.SetString(k, b)
            for texto in itens[len(velho_mapa):]:
                self.lista_msgs.Append(texto)
            self._atualizar_botoes()
            return
        i_antes = self.lista_msgs.GetSelection()
        self.lista_msgs.Set(itens)
        sel = len(itens) - 1
        if destino == MARCADOR:
            if MARCADOR in mapa:
                sel = mapa.index(MARCADOR)
        elif destino not in (None, "ultima"):
            if destino in mapa:
                sel = mapa.index(destino)
            elif MARCADOR in mapa:
                sel = mapa.index(MARCADOR)
        elif destino is None:
            if antes in mapa:
                sel = mapa.index(antes)
            elif i_antes >= 0:
                sel = min(i_antes, len(itens) - 1)   # perto de onde estava
        self.lista_msgs.SetSelection(sel)
        self._atualizar_botoes()

    def _destino_inicial(self):
        """Onde a selecao cai ao abrir a conversa: no marcador, se ha nao
        lidas; senao no ponto em que a pessoa parou (ou no fim)."""
        alvo = self.alvo_inicial
        if self.marcador_n > 0:
            return MARCADOR      # com nao lidas, abre sempre no marcador
        if alvo == "":
            return "ultima"
        if alvo:
            return alvo      # se nao estiver na lista, cai no marcador/fim
        return MARCADOR if self.marcador_id else "ultima"

    def _guardar_posicao(self):
        """Grava onde a selecao esta (no fim da lista: ''), para reabrir a
        conversa no mesmo ponto."""
        if self.atual is None or self.mapa == [None]:
            return
        i = self.lista_msgs.GetSelection()
        if i < 0:
            return
        if i >= len(self.mapa) - 1:
            alvo = ""
        else:
            alvo = self.mapa[i]
            if alvo == MARCADOR:
                alvo = self.mapa[i + 1]
        try:
            self.banco.salvar_posicao(self.atual[0], self.atual[1], alvo or "")
        except Exception:
            log.exception("erro ao guardar a posição da conversa")

    def _guardar_lista(self):
        i = self.lista_conv.GetSelection()
        if 0 <= i < len(self._chaves_conv):
            self.cfg.set("ultima_conversa", list(self._chaves_conv[i]))

    def _ir_nao_lidas(self):
        """Alt 2: na lista de conversas, a proxima conversa com nao lidas;
        dentro da conversa, o marcador de mensagens nao lidas."""
        if self.FindFocus() is self.lista_conv or self.atual is None:
            self._proxima_nao_lida()
            return
        if MARCADOR in self.mapa:
            self.lista_msgs.SetSelection(self.mapa.index(MARCADOR))
            self.selecao_automatica = False
            self.lista_msgs.SetFocus()
            return
        self.lista_msgs.SetFocus()
        bipe("erro")
        self.fala.falar("Nenhuma mensagem não lida nesta conversa.",
                        interromper=True)

    def _original(self, x, porid):
        """A mensagem que `x` responde: da lista ou, se ficou fora dela, do
        banco de dados."""
        if not x.resposta_a:
            return None
        o = porid.get(x.resposta_a)
        if o is None and self.banco is not None:
            o = self.banco.mensagem(x.conta_id, x.conversa_id, x.resposta_a)
            if o is not None:
                porid[o.id] = o
        return o

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
        if x is not None and not x.id.startswith("local-"):
            if x.tipo in armazem.BAIXAVEIS:
                # mesmo com link na legenda: os links sao botoes (Tab)
                self._abrir_midia()
                return
            self._mostrar_texto(x)
            return
        self._detalhes()

    def _mostrar_texto(self, x):
        """Enter numa mensagem so de texto: o texto numa caixa somente
        leitura, com Copiar texto e Fechar (Esc fecha). Os detalhes seguem em
        Alt Enter."""
        autor = "você" if x.minha else (x.autor or "mensagem")
        dialogos.mostrar_mensagem(
            self, "Mensagem de %s" % autor, x.texto or m.conteudo(x),
            self._copiar_texto)

    def _copiar_texto(self, texto):
        if wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(wx.TextDataObject(texto))
            finally:
                wx.TheClipboard.Close()
        self.fala.falar("Texto copiado.")

    def _detalhes(self):
        x = self._mensagem_selecionada()
        if x is None:
            return
        conv = self.indice.get(self.atual)
        recibos = []
        if x.minha and self.banco is not None and not x.id.startswith("local-"):
            recibos = self.banco.recibos(x.conta_id, x.conversa_id, x.id)
        nomes = {}
        prov = self.contas.provedores.get(x.conta_id) if recibos else None
        for quem in {r[0] for r in recibos}:
            try:
                nome = prov.nome_de_participante(quem) if prov else ""
            except Exception:
                nome = ""
            if nome:
                nomes[quem] = nome
        midia = None
        if x.tipo in armazem.BAIXAVEIS and self.midias is not None:
            midia = "baixada" if self.midias.caminho(x) else "não baixada"
        extras = m.extras_de(x)
        links = [tuple(l) for l in extras["links"]]
        vistos = {u for u, _ in links}
        links += [l for l in m.extrair_links(x.texto) if l[0] not in vistos]
        pessoa = dialogos.mostrar_texto(
            self, "Detalhes da mensagem",
            m.detalhes(x, conv.nome if conv else "", recibos=recibos,
                       nomes=nomes, midia=midia),
            "Detalhes e texto completo", links=links,
            botoes=[tuple(b) for b in extras["botoes"]],
            mencoes=extras["mencoes"],
            acoes=[(a.get("rotulo", ""), a.get("tipo") == "lista")
                   for a in extras["acoes"]])
        if pessoa is not None and "_acao" in pessoa:
            wx.CallAfter(self._tocar_acao, x, extras["acoes"][pessoa["_acao"]])
        elif pessoa is not None:
            wx.CallAfter(self._abrir_conversa_da_mencao, x, pessoa)

    @seguro
    def _tocar_acao(self, x, acao):
        """Envia a resposta de um botao/opcao de uma mensagem, direto, sem
        confirmar. O resultado e falado quando chega: "Enviado" (a resposta
        aparece na conversa) ou o aviso de falha."""
        prov = self.contas.provedores.get(x.conta_id)
        if prov is None:
            bipe("erro")
            self.fala.falar("Esta conta não está disponível agora.")
            return
        rotulo = acao.get("rotulo", "")
        self._acoes_enviadas.append((x.conta_id, x.conversa_id, rotulo))
        try:
            prov.responder_acao(x, acao)
        except NotImplementedError:
            self._acoes_enviadas.pop()
            bipe("erro")
            self.fala.falar("Este serviço ainda não responde a botões.")

    def _acao_concluida(self, chave, texto, sucesso):
        """Tira da lista de respostas de botao esperando resultado; True se
        era uma delas."""
        item = (chave[0], chave[1], texto)
        if item in self._acoes_enviadas:
            self._acoes_enviadas.remove(item)
            return True
        return False

    @seguro
    def _abrir_conversa_da_mencao(self, x, pessoa):
        """Abre (ou cria, vazia) a conversa com quem foi mencionado, no
        mesmo servico e na mesma conta da mensagem."""
        cid = pessoa.get("id")
        if not cid:
            bipe("erro")
            self.fala.falar("Não consegui localizar esta pessoa.",
                            interromper=True)
            return
        chave = (x.conta_id, cid)
        conv = self.indice.get(chave)
        if conv is None:
            nome = pessoa.get("nome") or (
                "@" + pessoa["usuario"] if pessoa.get("usuario") else "") \
                or pessoa.get("telefone") or "Contato"
            conv = m.Conversa(x.conta_id, cid, nome,
                              self.contas.servico(x.conta_id), "privada",
                              data=time.time())
            self.indice[chave] = conv
            self._ordenar()
            self._preencher_conversas()
        if self.atual is not None:
            self._fechar_conversa()
        self._abrir_conversa(conv)
        self.fala.falar("Conversa com %s." % conv.nome, interromper=True)

    @seguro
    def _nova_mensagem(self):
        """Escreve para alguem sem abrir uma conversa antes: escolhe a conta
        (so se houver mais de uma conectada), o destinatario e o texto."""
        from telezapp.interface import contatos
        from telezapp.nucleo import nova_mensagem as nm
        contas = [(d["id"], "%s, %s" % (
            d.get("nome") or d.get("telefone") or d["id"],
            m.SERVICOS.get(d.get("servico"), "")))
            for d in self.cfg.contas()
            if self.estados.get(d["id"]) == ev.CONECTADA
            and self.contas.provedor(d["id"]) is not None]
        if not contas:
            bipe("erro")
            self.fala.falar("Nenhuma conta conectada para enviar.",
                            interromper=True)
            return
        def buscar(conta_id, texto):
            return nm.candidatos(
                texto, self.banco.contatos(conta_id),
                [c for c in self.indice.values()
                 if c.conta_id == conta_id])
        escolha = contatos.dialogo_nova_mensagem(self, contas, buscar)
        if escolha is None:
            return
        conta_id, destino, texto, pessoa = escolha
        achado = pessoa or self._resolver_destino(conta_id, destino, nm)
        if achado is None:
            bipe("erro")
            self.fala.falar("Não encontrei %s. Use o nome de um contato ou "
                            "conversa, um número com DDD ou um @usuário."
                            % destino, interromper=True)
            return
        conversa_id, nome = achado
        chave = (conta_id, conversa_id)
        conv = self.indice.get(chave)
        if conv is None:
            conv = m.Conversa(conta_id, conversa_id, nome,
                              self.contas.servico(conta_id), "privada",
                              data=time.time())
            self.indice[chave] = conv
            self._ordenar()
            self._preencher_conversas()
        if self.atual is not None and self.atual != chave:
            self._fechar_conversa()
        self._abrir_conversa(conv)
        self.caixa.SetValue(texto)
        self._enviar_texto()

    def _resolver_destino(self, conta_id, destino, nm):
        """(conversa_id, nome) do destino digitado, pela agenda e pelas
        conversas da conta ou, para telefone e @usuario, pelo servico."""
        tipo = nm.tipo_de_destino(destino)
        prov = self.contas.provedor(conta_id)
        if tipo == nm.NOME:
            achados = nm.candidatos(
                destino, self.banco.contatos(conta_id),
                [c for c in self.indice.values() if c.conta_id == conta_id])
            if len(achados) > 1:
                dlg = wx.SingleChoiceDialog(
                    self, "Há mais de uma pessoa com esse nome.",
                    "Para quem enviar",
                    [nm.rotulo(n, t) for _, n, t in achados])
                try:
                    if dlg.ShowModal() != wx.ID_OK:
                        return None
                    return achados[dlg.GetSelection()][:2]
                finally:
                    dlg.Destroy()
            return achados[0][:2] if achados else None
        if tipo == nm.TELEFONE:
            tel = m.normalizar_telefone(destino)
            conhecido = nm.candidatos(
                tel, self.banco.contatos(conta_id),
                [c for c in self.indice.values() if c.conta_id == conta_id])
            if conhecido:
                return conhecido[0][:2]
            id_ = prov.id_do_telefone(tel) if prov else ""
            if id_:
                return id_, tel
        return prov.resolver_destinatario(destino) if prov else None

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
        self._copiar_texto(x.texto or m.conteudo(x))

    # ------------------------------------------------------------ depurar
    def _modo_depuracao(self, ligado):
        self.cfg.set("depuracao", bool(ligado))
        self.banco.depuracao = bool(ligado)
        if ligado:
            self.fala.falar("Modo de depuração ligado. As mensagens novas do "
                            "WhatsApp passam a ter a estrutura guardada.")
        else:
            self.banco.limpar_depuracao()
            self.fala.falar("Modo de depuração desligado. As estruturas "
                            "guardadas foram apagadas.")

    def _log_detalhado(self, ligado):
        self.cfg.set("log_detalhado_whatsapp", bool(ligado))
        self.fala.falar(
            "Registro técnico detalhado do WhatsApp %s. Vale na próxima "
            "abertura do TeleZapp; feche e abra o programa." % (
                "ligado" if ligado else "desligado"))

    def _area_de_transferencia(self, texto):
        if wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(wx.TextDataObject(texto))
            finally:
                wx.TheClipboard.Close()
        self.fala.falar("Texto de depuração copiado.")

    def _salvar_depuracao(self, texto):
        nome = time.strftime("telezapp_depuracao_%Y%m%d_%H%M%S.txt")
        try:
            caminho = os.path.join(config.pasta_depuracao(), nome)
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(texto)
        except OSError:
            bipe("erro")
            self.fala.falar("Não consegui salvar o arquivo.")
            return
        self.fala.falar("Salvo em " + caminho)

    def _depurar_mensagem(self):
        x = self._mensagem_selecionada()
        if x is None:
            self.fala.falar("Nenhuma mensagem selecionada.")
            return
        conv = self.indice.get((x.conta_id, x.conversa_id))
        recibos = self.banco.recibos(x.conta_id, x.conversa_id, x.id)
        texto = depuracao.texto_mensagem(
            x, conv, self.banco.depuracao_de(x.conta_id, x.conversa_id, x.id),
            recibos, VERSAO, bool(self.cfg.get("depuracao")))
        dialogos.mostrar_depuracao(
            self, "Depurar mensagem", texto, self._area_de_transferencia,
            self._salvar_depuracao)

    # ============================================================ contatos
    def _gerenciar_contatos(self):
        from telezapp.interface import contatos
        dlg = contatos.GerenciadorContatos(
            self, self.banco, _ContasParaContatos(self),
            self._renomear_pelos_contatos,
            lambda t: self.fala.falar(t, interromper=True))
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()

    def _conversa_privada_em_foco(self):
        conv = self.indice.get(self.atual) if self.atual else None
        if conv is None:
            i = self.lista_conv.GetSelection()
            if 0 <= i < len(self._chaves_conv):
                conv = self.indice.get(self._chaves_conv[i])
        return conv if conv is not None and conv.tipo == "privada" else None

    def _salvar_pessoa(self, conv=None):
        from telezapp.interface import contatos
        if conv is None:
            conv = self._conversa_privada_em_foco()
        if conv is None or conv.tipo != "privada":
            self.fala.falar("Selecione uma conversa com uma pessoa.")
            return
        base = ("+" + conv.id.split("@")[0])             if conv.id.endswith("@s.whatsapp.net") else ""
        servico = m.SERVICOS.get(self.contas.servico(conv.conta_id), "")
        escolha = contatos.dialogo_salvar_pessoa(
            self, [(conv.conta_id, servico)], conv.nome, base)
        if escolha is None:
            return
        nome, telefone = escolha
        self.banco.salvar_contato(conv.conta_id, conv.id, nome,
                                  telefone or base)
        self._renomear_pelos_contatos()
        self.fala.falar("Contato %s salvo." % nome, interromper=True)

    def _renomear_pelos_contatos(self):
        """Poe nas conversas com pessoas o nome da agenda e, onde a pessoa
        removeu o contato, pede os nomes de novo ao servico."""
        mudou = []
        for c in self.indice.values():
            if c.tipo != "privada":
                continue
            nome = self.banco.nome_de_contato(c.conta_id, c.id)
            if nome and nome != c.nome:
                c.nome = nome
                mudou.append(c)
        if mudou:
            self.banco.salvar_conversas(mudou)
        self._ordenar()
        self._preencher_conversas()
        if self.atual in self.indice:
            self.rot_msgs.SetLabel("Mensagens de " + self.indice[self.atual].nome)
            self._atualizar_titulo()
        self._atualizar_conversas(avisar=False)

    def _depurar_conversa(self, conv=None):
        if conv is None:
            conv = self.indice.get(self.atual) if self.atual else None
        if conv is None:
            i = self.lista_conv.GetSelection()
            if 0 <= i < len(self._chaves_conv):
                conv = self.indice.get(self._chaves_conv[i])
        if conv is None:
            self.fala.falar("Nenhuma conversa selecionada.")
            return
        prov = self.contas.provedores.get(conv.conta_id)
        try:
            dados = prov.depurar_conversa(conv.id) if prov else {}
        except Exception:
            dados = {"erro": "o serviço não conseguiu informar"}
        msgs = self.banco.mensagens(conv.conta_id, conv.id, 500)
        texto = depuracao.texto_conversa(conv, msgs, dados, VERSAO)
        dialogos.mostrar_depuracao(
            self, "Depurar conversa", texto, self._area_de_transferencia,
            self._salvar_depuracao)

    def _ler_ultima(self):
        msgs = self._mensagens_atuais()
        if not msgs:
            self.fala.falar(TEXTO_SEM_CONVERSA if self.atual is None
                            else TEXTO_SEM_MENSAGENS)
            return
        self.fala.falar(m.formatar(msgs[-1], m.ESTILO_AUTOR_PRIMEIRO),
                        interromper=True)

    def _ir_para_respondida(self):
        """Leva a selecao para a mensagem a que a selecionada responde."""
        x = self._mensagem_selecionada()
        if x is None:
            return
        if not x.resposta_a:
            self.fala.falar("Esta mensagem não é uma resposta.")
            return
        if x.resposta_a not in self.mapa:
            # fora da lista aberta: tenta trazer do banco de dados
            o = self.banco.mensagem(x.conta_id, x.conversa_id, x.resposta_a)
            if o is None:
                bipe("erro")
                self.fala.falar("A mensagem original não está guardada no "
                                "TeleZapp.")
                return
            self._mesclar(self.atual, [o])
            self._preencher_mensagens(x.id)
        self.selecao_automatica = False
        self.volta_para.append(x.id)
        self.lista_msgs.SetSelection(self.mapa.index(x.resposta_a))
        self.lista_msgs.SetFocus()

    def _voltar_da_respondida(self):
        """Esc depois de ir para a mensagem respondida: volta para a resposta
        de onde a pessoa saiu. False se nao ha para onde voltar."""
        while self.volta_para:
            id_ = self.volta_para.pop()
            if id_ in self.mapa:
                self.lista_msgs.SetSelection(self.mapa.index(id_))
                return True
        return False

    def _menu_conversa(self, evt):
        """Menu de contexto da lista de conversas (botao direito ou tecla
        Menu): age sobre a conversa selecionada, nao sobre a aberta."""
        lista = self.lista_conv
        pos = evt.GetPosition()
        if pos != wx.DefaultPosition:
            k = lista.HitTest(lista.ScreenToClient(pos))
            if k != wx.NOT_FOUND and k != lista.GetSelection():
                lista.SetSelection(k)
        conv = self._conversa_selecionada()
        if conv is None:
            return
        opcoes = [("Abrir", lambda: self._abrir_conversa(conv)),
                  ("Desarquivar" if conv.arquivada else "Arquivar",
                   lambda: self._arquivar_conversa(conv))]
        opcoes.append(("Desafixar" if conv.fixada else "Fixar",
                       lambda: self._fixar_conversa(conv)))
        opcoes.append(("Reativar o som" if conv.silenciada() else "Silenciar",
                       lambda: self._silenciar_conversa(conv)))
        opcoes.append(("Destrancar" if conv.trancada else "Trancar",
                       lambda: self._trancar_conversa(conv)))
        opcoes.append(("Apagar conversa...",
                       lambda: self._apagar_conversa(conv)))
        if conv.tipo == "privada":
            opcoes.append(("Salvar como contato...",
                           lambda: self._salvar_pessoa(conv)))
        if self.cfg.get("depuracao"):
            opcoes.append(("Depurar conversa",
                           lambda: self._depurar_conversa(conv)))
        menu = wx.Menu()
        for rotulo, tratador in opcoes:
            it = menu.Append(wx.ID_ANY, rotulo)
            self.Bind(wx.EVT_MENU, seguro(lambda e, t=tratador: t()), it)
        if pos == wx.DefaultPosition:
            lista.PopupMenu(menu, wx.Point(20, 20))
        else:
            lista.PopupMenu(menu, lista.ScreenToClient(pos))
        menu.Destroy()

    def _menu_mensagem(self, evt):
        if self._mensagem_selecionada() is None:
            return
        menu = wx.Menu()
        opcoes = [("Responder", self._responder),
                  ("Copiar texto", self._copiar),
                  ("Detalhes", self._detalhes)]
        if self._mensagem_selecionada().resposta_a:
            opcoes.insert(1, ("Ir para a mensagem respondida",
                              self._ir_para_respondida))
        for rotulo, tratador in opcoes:
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
            desativada = hasattr(self.contas, "esta_ativa") and \
                not self.contas.esta_ativa(conta_id)
            self.fala.falar(
                "A conta está desativada. A mensagem não foi enviada. Ative "
                "a conta em Menu, Contas." if desativada else
                "A conta não está conectada. A mensagem não foi enviada.",
                interromper=True)
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

    def _tirar_local(self, chave, texto, tipo=m.TEXTO):
        """Troca a mensagem 'enviando' pela confirmada pelo servico."""
        lista = self.cache.get(chave, [])
        achada = self._local_enviando(lista, texto, tipo)
        if achada is not None:
            lista.remove(achada)
        bipe("enviada")
        if self.cfg.get("confirmar_envio"):
            self.fala.falar("Enviada.")

    @staticmethod
    def _local_enviando(lista, texto, tipo):
        """A mensagem local 'enviando' que o servico acabou de confirmar (ou
        que falhou): do mesmo tipo; numa midia, serve outro tipo de midia,
        porque o servico pode classificar de outro jeito."""
        locais = [x for x in lista if x.id.startswith("local-") and
                  x.estado == m.ENVIANDO and x.texto == texto]
        for x in locais:
            if x.tipo == tipo:
                return x
        if tipo != m.TEXTO:
            for x in locais:
                if x.tipo != m.TEXTO:
                    return x
        return None

    # ====================================================== anexos e voz
    def _destino_do_envio(self):
        """(conta_id, conversa_id, provedor) se da para enviar agora; senao
        avisa a pessoa e devolve None."""
        if self.atual is None:
            bipe("erro")
            self.fala.falar(TEXTO_SEM_CONVERSA)
            return None
        conta_id, conversa_id = self.atual
        p = self.contas.provedor(conta_id)
        if p is None or self.estados.get(conta_id) != ev.CONECTADA:
            bipe("erro")
            self.fala.falar("A conta não está conectada. Nada foi enviado.",
                            interromper=True)
            return None
        return conta_id, conversa_id, p

    def _anexar_arquivo(self):
        if self._destino_do_envio() is None:
            return
        caminho = dialogos.escolher_arquivo(
            self, self.cfg.get("pasta_anexos") or "")
        if not caminho:
            return
        self.cfg.set("pasta_anexos", os.path.dirname(caminho))
        self._enviar_arquivo(caminho)

    def _gravar(self, origem):
        if self._destino_do_envio() is None:
            return
        pasta = config.pasta_temporaria()
        if origem == MICROFONE:
            titulo = "Gravar nota de voz do microfone"
            instrucao = ("Fale perto do microfone. A gravação já começou. "
                         "Aperte Enter para parar; depois você pode ouvir, "
                         "gravar de novo ou enviar. Esc descarta.")
        else:
            titulo = "Gravar o som do computador"
            instrucao = ("Vai ser gravado tudo o que o computador tocar, "
                         "inclusive a voz do leitor de tela, se ele falar. "
                         "A gravação já começou. Aperte Enter para parar; "
                         "depois você pode ouvir, gravar de novo ou enviar. "
                         "Esc descarta.")
        gravacao = dialogos.gravar_voz(
            self, lambda: Gravador(pasta, origem, maximo_segundos=3600),
            titulo, instrucao, self.fala)
        if gravacao is None:
            return
        log.info("gravação (%s) de %.0fs pronta para enviar", origem,
                 gravacao.segundos)
        self._enviar_arquivo(gravacao.caminho, voz=True, temporario=True)

    def _enviar_arquivo(self, caminho, voz=False, temporario=False):
        destino = self._destino_do_envio()
        if destino is None:
            return
        conta_id, conversa_id, p = destino
        try:
            anexo = envio.preparar(caminho, voz=voz, temporario=temporario)
        except envio.ErroEnvio as e:
            bipe("erro")
            self.fala.falar(str(e), interromper=True)
            return
        legenda = "" if anexo.tipo in (m.VOZ, m.AUDIO) else \
            self.caixa.GetValue().strip()
        self.locais += 1
        ultima = max((x.data for x in self._mensagens_atuais()), default=0)
        local = m.Mensagem(conta_id, conversa_id, "local-%d" % self.locais,
                           minha=True, data=max(time.time(), ultima + 0.001),
                           texto=legenda, tipo=anexo.tipo,
                           segundos=anexo.segundos, nome_arquivo=anexo.nome,
                           tamanho=anexo.tamanho, estado=m.ENVIANDO)
        self._mesclar(self.atual, [local])
        if legenda:
            self.caixa.Clear()
        self._preencher_mensagens()
        texto = "Enviando %s, %s." % (m.NOMES_TIPOS[anexo.tipo],
                                      m.tamanho_legivel(anexo.tamanho))
        if anexo.aviso:
            texto += " " + anexo.aviso
        if self.resposta_a is not None:
            texto += " A mídia vai sem citar a mensagem respondida."
        self.fala.falar(texto, interromper=True)
        p.enviar_arquivo(conversa_id, anexo, legenda)
        log.info("arquivo (%s, %d bytes) enviado para a fila", anexo.tipo,
                 anexo.tamanho)

    # =============================================================== midias
    def _abrir_midia(self, abrir=True, x=None):
        if x is None:
            x = self._mensagem_selecionada()
        if x is None or self.midias is None:
            return
        if x.tipo not in armazem.BAIXAVEIS:
            self.fala.falar("Esta mensagem não tem mídia.")
            return
        if x.id.startswith("local-"):
            return
        if self.banco.foi_limpa(x.conta_id, x.conversa_id, x.id):
            bipe("erro")
            self.fala.falar(TEXTO_LIMPA, interromper=True)
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
        motor.velocidade = self._velocidade()
        motor.tocar()
        self.audio = (x.chave, motor)
        self._marcar_ouvida(x)
        proximo = self._proximo_chave == x.chave
        self._proximo_chave = None
        self._seq_tocados = self._seq_tocados + 1 if proximo else 0
        rotulo_vel = "" if motor.velocidade == 1.0 else vel.rotulo(
            motor.velocidade)
        if proximo:
            # dentro da sequencia vale o que a pessoa escolheu falar
            texto = m.anuncio_sequencia(
                x, rotulo_vel,
                proximo=bool(self.cfg.get("seq_falar_proximo")),
                tipo=bool(self.cfg.get("seq_falar_tipo")),
                quem=bool(self.cfg.get("seq_falar_quem")),
                duracao=bool(self.cfg.get("seq_falar_duracao")),
                mostrar_velocidade=bool(self.cfg.get("seq_falar_velocidade")))
        else:
            texto = m.anuncio_reproducao(
                x, rotulo_vel, False,
                detalhado=bool(self.cfg.get("falar_quem_toca")))
        if texto:
            self.fala.falar(texto, interromper=True)
        wx.CallLater(500, self._vigiar_audio, motor)
        return True

    def _marcar_ouvida(self, x):
        """Guarda que esta voz ou audio recebido ja foi tocado: a linha da
        mensagem passa a dizer 'ouvida' ao andar pela lista."""
        if x.minha or x.tipo not in (m.VOZ, m.AUDIO) or \
                m.extras_de(x)["ouvida"]:
            return
        m.atualizar_extras(x, ouvida=True)
        try:
            self.banco.salvar_mensagens([x])
        except Exception:
            log.exception("erro ao guardar que o áudio foi ouvido")
        if (x.conta_id, x.conversa_id) == self.atual:
            self._preencher_mensagens()

    def _vigiar_audio(self, motor):
        """Libera o dispositivo de som quando o audio acaba."""
        if self.audio is None or self.audio[1] is not motor:
            return
        if motor.terminou:
            chave = self.audio[0]
            self._parar_audio(falar=False)
            modo = self.cfg.get("audio_sequencia")
            if modo in ("sim", "bloco"):
                if not self._tocar_proximo_audio(
                        chave, so_seguidos=modo == "bloco"):
                    self._fim_da_sequencia()
            return
        wx.CallLater(500, self._vigiar_audio, motor)

    def _tocar_proximo_audio(self, chave, so_seguidos=False):
        """Acabou um audio: segue para o proximo audio ou voz da conversa
        (baixando antes, se preciso). Nao mexe na selecao da lista.
        so_seguidos: para na primeira mensagem que nao for audio, em vez de
        pular ate o proximo audio. Devolve False se nao havia proximo."""
        lista = self.cache.get((chave[0], chave[1]), [])
        achou = False
        for x in lista:
            if achou and so_seguidos and (
                    x.tipo not in (m.VOZ, m.AUDIO)
                    or x.id.startswith("local-")):
                return False
            if achou and x.tipo in (m.VOZ, m.AUDIO) and \
                    not x.id.startswith("local-"):
                # o "Próximo áudio" vai junto do anuncio de quem fala, em
                # _tocar_sem_janela: falar os dois separados cortava o
                # primeiro (cada fala interrompe a anterior)
                self._proximo_chave = x.chave
                self._abrir_midia(x=x)
                return True
            if x.chave == chave:
                achou = True
        return False

    def _fim_da_sequencia(self):
        """O ultimo audio acabou e nao ha outro: avisa, se a pessoa quer e
        se a sequencia teve mais de um audio."""
        tocados, self._seq_tocados = self._seq_tocados, 0
        if tocados and self.cfg.get("seq_falar_fim"):
            self.fala.falar("Fim da sequência.", interromper=True)

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
        if x.tipo in (m.VOZ, m.AUDIO):
            self._marcar_ouvida(x)
        conv = self.indice.get((x.conta_id, x.conversa_id))
        visualizadores.abrir(self, x, caminho, self.fala,
                             conv.nome if conv else "", cfg=self.cfg)

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

    # ------------------------------------------------ velocidade do audio
    def _passo_velocidade(self):
        return vel.passo_valido(self.cfg.get("audio_passo_velocidade"))

    def _velocidade(self):
        return vel.ajustar(self.cfg.get("audio_velocidade"),
                           self._passo_velocidade())

    def _aplicar_velocidade(self, valor):
        self.cfg.set("audio_velocidade", valor)
        if self.audio is not None:
            self.audio[1].velocidade = valor
        self.fala.falar("Velocidade %s" % vel.rotulo(valor),
                        interromper=True)

    def _mudar_velocidade(self, direcao):
        self._aplicar_velocidade(vel.proxima(
            self._velocidade(), self._passo_velocidade(), direcao))

    def _escolher_velocidade(self):
        valores = vel.valores(self._passo_velocidade())
        dlg = wx.SingleChoiceDialog(
            self, "Velocidade de reprodução dos áudios e mensagens de voz.",
            "Velocidade do áudio", [vel.rotulo(v) for v in valores])
        try:
            dlg.SetSelection(valores.index(self._velocidade()))
        except ValueError:
            pass
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            escolhida = valores[dlg.GetSelection()]
        finally:
            dlg.Destroy()
        self._aplicar_velocidade(escolhida)

    def _escolher_passo(self):
        """Muda o passo e leva a velocidade ao valor mais proximo que ele
        permite (de 0,25 em 0,25, de 0,5 em 0,5 ou de 1 em 1)."""
        antes = self._passo_velocidade()
        self._escolher_opcao("audio_passo_velocidade")
        depois = self._passo_velocidade()
        if depois == antes:
            return
        atual = self._velocidade()
        if atual != self.cfg.get("audio_velocidade"):
            self._aplicar_velocidade(atual)

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

    def _limpar_midias(self):
        from telezapp.interface import limpeza
        contas = [(d["id"], d.get("nome") or d["id"])
                  for d in self.cfg.contas()]
        conversas = sorted(((c.conta_id, c.id, c.nome)
                            for c in self.indice.values()),
                           key=lambda c: c[2].lower())
        dlg = limpeza.DialogoLimpeza(
            self, self.banco, contas, conversas,
            lambda t: self.fala.falar(t, interromper=True),
            self._ao_limpar)
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()

    def _ao_limpar(self, selecao):
        """Depois de limpar mensagens: tira da memoria o que saiu do banco."""
        if selecao.o_que != "mensagens":
            return
        tiradas = {(c, v, i) for c, v, i, *_ in selecao.itens}
        for chave, lista in list(self.cache.items()):
            self.cache[chave] = [x for x in lista if (
                x.conta_id, x.conversa_id, x.id) not in tiradas]
        if self.atual:
            self._preencher_mensagens()

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
            self.banco.mensagens(e.conta_id, e.conversa_id,
                                 self._limite_memoria())
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

    def _configuracoes(self):
        from telezapp.interface.configuracoes import DialogoConfiguracoes
        dlg = DialogoConfiguracoes(self, self.cfg, self._aplicar_opcao,
                                   fala=self.fala,
                                   privacidade=_PrivacidadeParaConfig(self))
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()

    def _aplicar_opcao(self, chave, valor):
        """Aplica uma opcao vinda da janela de configuracoes, com os mesmos
        efeitos e avisos dos menus, e mantem os itens de menu em dia."""
        if chave == "depuracao":
            self._modo_depuracao(valor)
            self.itens["depuracao"].Check(bool(valor))
        elif chave == "log_detalhado_whatsapp":
            self._log_detalhado(valor)
            self.itens["log_detalhado"].Check(bool(valor))
        elif chave == "estilo":
            self._mudar_estilo(valor)
            self.itens["estilo%d" % valor].Check(True)
        elif chave == "midias_baixar":
            self._mudar_baixar(valor)
            self.itens["baixar_" + str(valor)].Check(True)
        elif chave == "audio_velocidade":
            self._aplicar_velocidade(vel.ajustar(valor,
                                                 self._passo_velocidade()))
        elif chave == "audio_passo_velocidade":
            self.cfg.set(chave, valor)
            atual = self._velocidade()
            if atual != self.cfg.get("audio_velocidade"):
                self._aplicar_velocidade(atual)
        elif chave == "trancadas_exigir_codigo":
            self.cfg.set(chave, valor)
            self.trancadas_liberadas = False
            self._montar_tipos()
            self._aplicar_filtros(falar=False)
        elif chave == "privacidade_conta":
            self._aplicar_privacidade_conta(valor)
        elif chave == "codigo_trancadas":
            self.cfg.set(chave, codigo_secreto.criar(valor) if valor
                         else None)
            self.fala.falar("Código secreto salvo." if valor else
                            "Código secreto removido.")
        elif chave == "mensagens_por_conversa":
            self.cfg.set(chave, valor)
            limite = self._limite_memoria()
            for k in self.cache:
                self.cache[k] = self.cache[k][-limite:]
            self._preencher_mensagens()
        elif chave in ("som", "falar_novas", "confirmar_envio", "falar_quem_toca",
                      "falar_reacoes"):
            self._opcao(chave, valor)
            self.itens[chave].Check(bool(valor))
        else:
            self.cfg.set(chave, valor)

    def _aplicar_privacidade_conta(self, mudancas):
        """Grava na conta as escolhas de privacidade e confere, lendo de
        novo, se o WhatsApp as aceitou. Fala um resumo so."""
        from telezapp.nucleo import privacidade_conta as pw
        falhas, aplicadas, motivos = [], 0, []
        for conta_id in dict.fromkeys(c for c, _, _ in mudancas):
            p = self.contas.provedores.get(conta_id)
            pedidas = [(campo, valor) for c, campo, valor in mudancas
                       if c == conta_id]
            if p is None:
                falhas += [campo for campo, _ in pedidas]
                continue
            for campo, valor in pedidas:
                try:
                    p.definir_privacidade(campo, valor)
                except Exception as e:
                    log.exception("erro ao mudar a privacidade")
                    if isinstance(e, ErroPrivacidade):
                        motivos.append(str(e))
            nao = pw.nao_confirmadas(pedidas, p.privacidade())
            falhas += nao
            aplicadas += len(pedidas) - len(nao)
        if falhas:
            bipe("erro")
            self.fala.falar(
                "%s não confirmou: %s.%s" % (
                    "O serviço", ", ".join(
                        pw.rotulo_do_campo(c).lower() for c in falhas),
                    (" " + " ".join(dict.fromkeys(motivos)))
                    if motivos else ""), interromper=True)
        else:
            self.fala.falar("Privacidade: %d mudança%s salva%s." % (
                aplicadas, "" if aplicadas == 1 else "s",
                "" if aplicadas == 1 else "s"), interromper=True)

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
        if self.chamada is not None and self.chamada.ativa:
            r = wx.MessageBox(
                "Há uma chamada em andamento. Fechar o TeleZapp encerra a "
                "chamada. Fechar mesmo?", NOME,
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
            if r != wx.YES:
                if hasattr(evt, "Veto"):
                    evt.Veto()
                return
        log.info("fechando a janela")
        self.Hide()
        self._guardar_posicao()
        self._guardar_lista()
        self._parar_audio(falar=False)
        try:
            if self.contas is not None:
                self.contas.parar_todos()
        finally:
            self.Destroy()


def _ordem(x):
    """Ordena por data; ids numericos desempatam."""
    return (x.data, int(x.id) if x.id.isdigit() else 0)

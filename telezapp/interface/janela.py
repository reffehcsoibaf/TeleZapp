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
import sys
import threading
import time
import traceback

import wx

from telezapp import NOME, VERSAO, config
from telezapp.acessibilidade.fala import Fala, bipe, definir_sons
from telezapp.interface import colagem, dialogos, visualizadores
from telezapp.interface import emojis as ui_emojis
from telezapp.interface import enquete as ui_enquete
from telezapp.interface import nova_enquete as ui_nova_enquete
from telezapp.interface import ortografia as ui_ortografia
from telezapp.interface import teclas as ui_teclas
from telezapp.interface.progresso import JanelaDeProgresso
from telezapp.interface.publicar_status import DialogoPublicarStatus
from telezapp.interface.detalhes import ControleDetalhes, ControleRecibos
from telezapp.interface.chamada import DialogoChamada
from telezapp.midia import armazem
from telezapp.midia import envio
from telezapp.midia import velocidade as vel
from telezapp.midia.gravador import (MICROFONE, SOM_INTERNO, ErroGravacao,
                                     Gravador)
from telezapp.midia.reprodutor import (FormatoNaoSuportado, Reprodutor,
                                       formatar_tempo)
from telezapp.nucleo import chamadas as ch
from telezapp.provedores.base import ErroPerfil, ErroPrivacidade
from telezapp.nucleo import atualizacao
from telezapp.nucleo import atualizador
from telezapp.nucleo import inicializacao
from telezapp.nucleo import atalhos as nucleo_atalhos
from telezapp.nucleo.ia import catalogo as cat_ia
from telezapp.nucleo.ia import cofre as cofre_ia
from telezapp.nucleo.ia import servico as servico_ia
from telezapp.nucleo.ia.provedores import ErroIA
from telezapp.nucleo import backup
from telezapp.nucleo import codigo_secreto
from telezapp.nucleo import depuracao
from telezapp.nucleo import encaminhar as enc
from telezapp.nucleo import eventos as ev
from telezapp.nucleo import exportar
from telezapp.nucleo import instalacao
from telezapp.nucleo import limpeza
from telezapp.nucleo import modelos as m
from telezapp.nucleo import ortografia
from telezapp.nucleo import pacotes_de_som
from telezapp.nucleo import previa_links
from telezapp.nucleo import paginas
from telezapp.nucleo.midias import TEXTO_LIMPA

log = logging.getLogger("telezapp.janela")

MARCADOR = "marcador"
TEXTO_SEM_CONVERSA = "Nenhuma conversa aberta. Aperte Enter numa conversa."
TEXTO_SEM_MENSAGENS = "Esta conversa ainda não tem mensagens."
TEXTO_SOMENTE_LEITURA = ("Esta conversa é somente leitura: você não pode "
                         "escrever nela.")
TEXTO_CARREGANDO = "Carregando mensagens..."
TEXTO_FILTRO_VAZIO = "Nenhuma conversa neste filtro."
TEXTO_SEM_CONTAS ="Nenhuma conversa ainda. Aperte Alt e use Novo, Nova conta, no " \
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
Control Espaço (nas listas de conversas e de mensagens): ligar o modo de
seleção e marcar o item em foco; depois, Espaço marca ou desmarca os outros,
a tecla Menu mostra as ações para todos os marcados e Esc desfaz tudo
Delete: apagar a conversa (na lista de conversas) ou a mensagem (na lista de
mensagens) selecionada, com confirmação
Control I: detalhes da conversa selecionada (dados, mídias, membros, grupos em
comum, administração)
F2: editar a mensagem de texto selecionada (se for sua e estiver no prazo)
Control Shift E: encaminhar a mensagem selecionada (ou as marcadas) para as
conversas que você escolher
Control Shift C: copiar o texto da mensagem selecionada (o menu de contexto
tem um item de cópia para cada tipo de conteúdo)
Control V na caixa de digitar: colar arquivos ou imagens copiados, que
são enviados com o Enter; o texto da caixa vira a legenda
Alt Enter: ver os detalhes e o texto completo da mensagem selecionada
Control Shift D: depurar a mensagem selecionada (menu Depurar)
Control O: abrir a mídia da mensagem (baixa antes, se preciso), mesmo
quando a legenda tem link
Control B: baixar a mídia sem abrir
Tab (na mensagem): vai aos botões de resposta e depois aos links, botões
de endereço e pessoas mencionadas; Espaço ou Enter abre
F7: verificar a ortografia do texto da caixa de digitar (palavra, sugestões
e botões para trocar, ignorar ou adicionar ao dicionário do Windows)
Control Shift A: anexar e enviar um arquivo (foto, vídeo, áudio, documento)
Control Shift M: começar a gravar uma nota de voz pelo microfone; apertar de
novo para e envia (Esc descarta). Os botões de gravar abrem uma janela
Control Shift S: o mesmo, gravando o som do computador
Todos os atalhos do menu podem ser mudados em Configurações, Atalhos
Control Shift Seta para cima e para baixo: áudio mais rápido e mais lento
(0,25x a 3x); Control Shift 0: velocidade normal
Control Shift Seta para a esquerda e para a direita: voltar e avançar 5
segundos no áudio que toca (Control Shift Page Up e Page Down: 30
segundos)
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
Enter e Control Enter: enviam (a tecla de enviar muda em Configurações,
Atalhos; em Mensagens dá para o Enter só quebrar a linha). Shift Enter: nova
linha. Esc: cancela a
resposta, se houver, esconde a caixa e volta para as mensagens.
Depois do botão Enviar há três botões: Anexar e enviar arquivo, Gravar do
microfone e Gravar som do computador. O texto da caixa vai como legenda do arquivo.

MENU
Aperte Alt para abrir o Menu. Ele tem submenus (Novo, Ir para, Mensagens,
Conversas, Contatos, Chamadas, Mídias, Exibir, Ferramentas e Ajuda): use a seta
para a direita para entrar e a seta para a esquerda para voltar. F1 abre o guia de uso completo.

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


def emoji_falado(simbolo):
    """"polegar para cima" no lugar do emoji, para o leitor de tela."""
    from telezapp.nucleo import emojis
    return emojis.nome_de(simbolo)


class ListaDeTextos(wx.ListCtrl):
    """Lista de uma coluna com a mesma interface de um wx.ListBox.

    O ListBox faz o NVDA falar o item em foco duas vezes ao chegar nele;
    o ListCtrl de uma coluna, como nas configuracoes, fala uma so vez."""

    def __init__(self, pai, name=""):
        super().__init__(pai, name=name, style=wx.LC_REPORT
                         | wx.LC_SINGLE_SEL | wx.LC_NO_HEADER)
        self.InsertColumn(0, "", width=300)
        self.Bind(wx.EVT_SIZE, self._ao_redimensionar)

    def _ao_redimensionar(self, evt):
        self.SetColumnWidth(0, max(self.GetClientSize().width - 4, 100))
        evt.Skip()

    def GetCount(self):
        return self.GetItemCount()

    def GetString(self, i):
        return self.GetItemText(i)

    def SetString(self, i, texto):
        self.SetItemText(i, texto)

    def Append(self, texto):
        self.InsertItem(self.GetItemCount(), texto)

    def Delete(self, i):
        self.DeleteItem(i)

    def Set(self, textos):
        self.DeleteAllItems()
        for t in textos:
            self.InsertItem(self.GetItemCount(), t)

    def GetSelection(self):
        return self.GetFirstSelected()

    def SetSelection(self, i):
        antes = self.GetFirstSelected()
        if 0 <= antes < self.GetItemCount() and antes != i:
            self.Select(antes, False)
        self.Select(i)
        self.Focus(i)
        self.EnsureVisible(i)

    def HitTest(self, ponto):
        return super().HitTest(ponto)[0]


class _ContasParaContatos:
    """O que o gerenciador de contatos precisa saber das contas."""

    def __init__(self, janela):
        self.j = janela

    def lista(self):
        return [(d["id"], d["servico"], d.get("nome") or d["id"])
                for d in self.j.cfg.contas()]

    def provedor(self, conta_id):
        return self.j.contas.provedores.get(conta_id)


class _IaParaConfig:
    """O que a janela de configuracoes precisa dos provedores de IA."""

    def __init__(self, janela):
        self.j = janela

    def tem(self, provedor):
        return self.j.cofre_ia.tem(provedor)

    def modelo(self, provedor):
        return (self.j.cfg.get("ia_modelos") or {}).get(provedor, "")

    def abrir(self, url):
        dialogos.abrir_link(url)

    def lista_de_modelos(self, provedor):
        """Os modelos que o provedor ofereceu da ultima vez que foram
        pedidos."""
        return list((self.j.cfg.get("ia_lista_modelos") or {}).get(
            provedor, []))

    def obter_modelos(self, provedor, chave):
        """(True, [modelos]) ou (False, texto do erro); guarda a lista."""
        chave = chave.strip() or self.j.cofre_ia.obter(provedor)
        try:
            lista = servico_ia.listar_modelos(provedor, chave)
        except ErroIA as e:
            return False, e.texto
        except Exception:
            log.exception("lista de modelos")
            return False, "Não consegui obter a lista de modelos."
        listas = dict(self.j.cfg.get("ia_lista_modelos") or {})
        listas[provedor] = lista
        self.j.cfg.set("ia_lista_modelos", listas)
        return True, lista

    def testar(self, provedor, chave, modelo):
        """(ok, texto) de um pedido minimo; usa a chave digitada ou, se o
        campo esta vazio, a guardada."""
        chave = chave.strip() or self.j.cofre_ia.obter(provedor)
        if not chave:
            return False, "Digite uma chave para testar."
        modelo = modelo.strip() or cat_ia.PROVEDORES[provedor].modelo
        try:
            servico_ia.testar(provedor, chave, modelo)
        except ErroIA as e:
            return False, e.texto
        except Exception:
            log.exception("teste do provedor de IA")
            return False, "O teste falhou."
        return True, "%s respondeu: a chave e o modelo funcionam." % \
            cat_ia.PROVEDORES[provedor].nome


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
        pacotes_de_som.migrar_antigos(cfg)
        pacotes_de_som.migrar_liga_desliga(cfg)
        self._carregar_sons()
        self._carregar_limites_ia()
        m.definir_modo_previa(cfg.get("previa_links"))
        self._carregar_previa_de_links()
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
        self.mencoes = []             # quem foi mencionado (@) na caixa
        self._membros_grupo = {}      # chave da conversa -> lista de membros
        self._carregando_membros = None
        self.cofre_ia = cofre_ia.Cofre(
            os.path.join(config.pasta_dados(), "ia_chaves.json"))
        self._ia_pendentes = {}   # chave da mensagem -> esperando o download
        self._ia_ocupadas = set()  # mensagens que a IA esta processando
        self._ia_vagas = threading.Semaphore(2)    # pedidos automaticos
        self.avisos_de_chamada = {}   # (conta, chamada) -> janela de aviso
        self.presenca = None      # ev.Presenca (online / visto) da aberta
        self.digitando = None     # (ev.Presenca, expira) da conversa aberta
        self.editando = None      # mensagem minha que esta sendo editada
        self._rascunho_da_edicao = ""
        self._escrita_liberada = True   # a conversa aberta aceita mensagens
        self._caiu = set()        # contas que cairam (som de reconectada)
        self._quem_cache = {}     # quem enviou, p/ mensagens sem autor
        # modo de selecao (Control Espaco): marcas em varias conversas ou
        # mensagens para agir de uma vez pelo menu de contexto
        self.modo_conv, self.marc_conv = False, set()    # chaves de conversa
        self.modo_msg, self.marc_msg = False, set()      # ids de mensagem
        self.anexos = []          # midias coladas na caixa, a enviar com o Enter
        self.locais = 0               # contador de mensagens "enviando"
        self.sincronia = {}           # conta_id -> (percentual, quando)
        self.audio = None             # (chave, Reprodutor) tocando sem janela
        self.interrompidas = {}       # conta_id -> % em que a sincronia parou
        self.progresso_midias = {}    # chave da midia -> percentual
        self.abrindo = None           # chave da midia que abre ao baixar
        self.abrindo_abrir = True     # False: so baixar, sem abrir
        self.progresso_falado = 0
        self._barras = {}             # chave -> JanelaDeProgresso aberta
        self._inicio_progresso = {}   # chave -> quando o avanco comecou
        self.progresso_envios = {}    # (conta, conversa) -> % do envio
        self._envio_falado = {}       # idem: ultimo marco falado
        self.estados = {}             # conta_id -> estado
        self.pareamentos = {}         # conta_id -> DialogoPareamento
        self.pareamento_recusado = set()
        self.estilo = cfg.get("estilo")
        self._proximo_chave = None    # audio que toca em sequencia
        self._seq_tocados = 0         # audios da sequencia atual, apos o 1o
        self.chamada = None           # nucleo.chamadas.Chamada em curso
        self.dlg_chamada = None       # DialogoChamada aberto
        self._gravacao_rapida = None  # {"gravador", "origem"} gravando por atalho
        self._bandeja = None          # icone da area de notificacao
        self._saindo = False          # True: fechar e sair de verdade
        self._id_global = (wx.NewIdRef().GetId() if hasattr(wx, "NewIdRef")
                           else 9001)
        # funcoes que aceitam atalho (os itens de menu e outras) e o que a
        # pessoa mudou; os rotulos sem atalho de cada item ficam em
        # _base_menu e o atalho entra na hora (ver _atualizar_atalhos)
        self.atalhos = nucleo_atalhos.Registro(cfg.get("atalhos") or {})
        self._base_menu = {}
        self._menu_do_item = {}
        self._criar_menus()
        self._criar_controles()
        self._rotular_controles()
        self.CreateStatusBar()
        self.Bind(wx.EVT_CLOSE, self._ao_fechar)
        if hasattr(wx, "EVT_HOTKEY"):
            self.Bind(wx.EVT_HOTKEY,
                      lambda e: self._mostrar_da_bandeja())
        self._atualizar_bandeja()
        self._registrar_atalho_global()
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
            # o atalho do rotulo e o padrao; o que vale (e aparece) e posto
            # por _atualizar_atalhos, que le o que a pessoa escolheu
            base, _, padrao = rotulo.partition("\t")
            if tipo == "check":
                it = menu.AppendCheckItem(wx.ID_ANY, base)
            elif tipo == "radio":
                it = menu.AppendRadioItem(wx.ID_ANY, base)
            else:
                it = menu.Append(wx.ID_ANY, base)
            self.itens[chave] = it
            self._base_menu[chave] = base
            self._menu_do_item[chave] = menu
            self._padrao_menu[chave] = padrao
            return it

        self._padrao_menu = {}

        # Menu vertical: uma unica entrada na barra, aberta pelo Alt, com as
        # secoes como submenus (seta para a direita), na ordem: Novo, Ir para,
        # Mensagens, Conversas, Contatos, Chamadas, Midias, Exibir,
        # Ferramentas e Ajuda. E um menu nativo: o NVDA le como qualquer outro.
        raiz = wx.Menu()

        m_novo = wx.Menu()
        item(m_novo, "nova_msg", "Nova &mensagem...\tCtrl+N")
        item(m_novo, "nova_chamada", "Nova &chamada...")
        item(m_novo, "nova_enquete", "Nova &enquete...")
        item(m_novo, "novo_contato", "Novo c&ontato...")
        item(m_novo, "postar_status", "Novo &status ou história...\t"
                                      "Ctrl+Shift+U")
        item(m_novo, "adicionar_conta", "Nova co&nta...")
        item(m_novo, "novo_grupo", "Novo &grupo...")
        item(m_novo, "novo_canal", "Novo c&anal...")
        item(m_novo, "nova_comunidade", "Nova comuni&dade...")

        m_ir = wx.Menu()
        item(m_ir, "ir_conv", "Ir para a lista de &conversas\tAlt+1")
        item(m_ir, "ir_msgs", "Ir para a lista de &mensagens\tAlt+3")
        item(m_ir, "ir_caixa", "Ir para o campo &editável\tCtrl+E")
        item(m_ir, "ir_filtro_conta",
             "Ir para o filtro de &serviço ou conta\tAlt+4")
        item(m_ir, "ir_filtro_tipo",
             "Ir para o f&iltro de tipo de conversa\tAlt+5")
        item(m_ir, "ir_respondida", "Ir para a mensagem respondi&da")

        m_ctt = wx.Menu()
        item(m_ctt, "contatos", "&Gerenciar contatos...")
        item(m_ctt, "salvar_pessoa",
             "&Salvar a pessoa desta conversa como contato...")
        item(m_ctt, "salvar_autor",
             "Salvar quem enviou a &mensagem como contato...")
        m_ctt.AppendSeparator()
        item(m_ctt, "bloqueados", "Contatos &bloqueados...")
        item(m_ctt, "bloquear_pessoa",
             "Bloquear ou &desbloquear a pessoa desta conversa...")

        m_conv = wx.Menu()
        item(m_conv, "nao_lidas", "Mensagens &não lidas (marcador ou próxima "
                                  "conversa)\tAlt+2")
        m_conv.AppendSeparator()
        item(m_conv, "abrir_conv", "&Abrir a conversa selecionada")
        item(m_conv, "arquivar", "Ar&quivar ou desarquivar a conversa")
        item(m_conv, "salvar_conv", "Sal&var o conteúdo da conversa...")
        item(m_conv, "detalhes_conv", "Detalhes da con&versa..." + chr(9) +
             "Ctrl+I")
        item(m_conv, "trancar", "Tra&ncar ou destrancar a conversa")
        item(m_conv, "fixar", "&Fixar ou desafixar a conversa")
        item(m_conv, "silenciar", "Sile&nciar ou reativar o som da conversa")
        item(m_conv, "ler_ultima", "&Ouvir a última mensagem\tCtrl+R")
        item(m_conv, "atualizar", "A&tualizar a lista de conversas\tF5")
        item(m_conv, "buscar_conv", "Bus&car conversa\tCtrl+F")
        item(m_conv, "esconder_trancadas",
             "Esconder as conversas tr&ancadas\tCtrl+Shift+T")

        m_msg = wx.Menu()
        item(m_msg, "ver_enquete", "Ver e votar na enquete...")
        item(m_msg, "enviar_msg", "Enviar a mensagem digitada\tCtrl+Enter")
        m_msg.AppendSeparator()
        item(m_msg, "responder_particular", "Responder em &particular")
        item(m_msg, "responder", "&Responder\tCtrl+Shift+R")
        item(m_msg, "copiar", "&Copiar texto\tCtrl+Shift+C")
        item(m_msg, "detalhes", "&Detalhes\tAlt+Enter")
        item(m_msg, "editar_msg", "Edi&tar mensagem	F2")
        item(m_msg, "reagir", "Re&agir à mensagem...\tCtrl+Shift+G")
        item(m_msg, "inserir_emoji", "Inserir e&moji...\tCtrl+.")
        item(m_msg, "ortografia", "&Verificar ortografia da mensagem\tF7")
        item(m_msg, "encaminhar", "&Encaminhar...	Ctrl+Shift+E")
        item(m_msg, "favoritar_msg",
             "&Favoritar ou desfavoritar a mensagem\tCtrl+Shift+F")
        item(m_msg, "apagar_msg", "&Apagar mensagem...")
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
        item(m_cham, "chamada_tempo", "&Falar há quanto tempo a chamada dura")
        item(m_cham, "chamada_desligar", "&Desligar\tCtrl+Shift+H")

        m_mid = wx.Menu()
        m_baixar = wx.Menu()
        for valor, nome in next(o for o in config.OPCOES
                                if o.chave == "midias_baixar").escolhas:
            it = item(m_baixar, "baixar_" + valor, nome, "radio")
            self.Bind(wx.EVT_MENU,
                      lambda e, v=valor: self._mudar_baixar(v), it)
        m_mid.AppendSubMenu(m_baixar, "&Quando baixar as mídias")
        m_mid.AppendSeparator()
        item(m_mid, "anexar", "&Anexar e enviar arquivo como "
                              "documento...\tCtrl+Shift+A")
        item(m_mid, "gravar_mic", "Gravar nota de voz (começa; apertar de "
                                  "novo envia)\tCtrl+Shift+M")
        item(m_mid, "gravar_som", "Gravar o &som do computador (começa; "
                                  "apertar de novo envia)\tCtrl+Shift+S")
        item(m_mid, "gravar_pausa",
             "Pausar ou continuar a gravação por atalho")
        item(m_mid, "gravar_descartar",
             "Descartar a gravação por atalho (sem enviar)")
        item(m_mid, "gravar_mic_janela",
             "Gravar nota de voz em uma &janela...")
        item(m_mid, "gravar_som_janela",
             "Gravar o som do computador em uma ja&nela...")
        m_mid.AppendSeparator()
        item(m_mid, "audio_janela",
             "Ao tocar um áudio: só tocar ou abrir o &player...")
        item(m_mid, "audio_sequencia",
             "&Sequência de áudios...")
        item(m_mid, "audio_voltar", "Voltar &5 segundos no áudio\t"
                                    "Ctrl+Shift+Left")
        item(m_mid, "audio_avancar", "Avançar 5 s&egundos no áudio\t"
                                     "Ctrl+Shift+Right")
        item(m_mid, "audio_voltar_mais", "Voltar 30 segundos no áudio\t"
                                         "Ctrl+Shift+PgUp")
        item(m_mid, "audio_avancar_mais", "Avançar 30 segundos no áudio\t"
                                          "Ctrl+Shift+PgDn")
        item(m_mid, "vel_mais", "Áudio mais &rápido\tCtrl+Shift+Up")
        item(m_mid, "vel_menos", "Áudio mais le&nto\tCtrl+Shift+Down")
        item(m_mid, "vel_normal", "&Velocidade normal do áudio\tCtrl+Shift+0")
        item(m_mid, "vel_escolher", "&Escolher a velocidade do áudio...")
        item(m_mid, "vel_passo",
             "Quanto a velocidade muda a cada &vez...")
        item(m_mid, "midias_limite",
             "&Tamanho máximo do download automático...")
        item(m_mid, "midias_confirmar",
             "Perguntar antes de baixar arquivos &grandes...")
        item(m_mid, "midias_espaco", "Ver quanto &espaço as mídias ocupam")
        item(m_mid, "midias_limpar",
             "Apagar as mídias já bai&xadas do computador...")

        m_exib = wx.Menu()
        m_estilo = wx.Menu()
        for est, nome in m.NOMES_ESTILOS.items():
            it = item(m_estilo, "estilo%d" % est, nome, "radio")
            self.Bind(wx.EVT_MENU,
                      lambda e, est=est: self._mudar_estilo(est), it)
        m_exib.AppendSubMenu(m_estilo, "Como cada &mensagem é lida")
        m_exib.AppendSeparator()
        rotulos = {o.chave: o.rotulo for o in config.OPCOES}
        for chave in ("falar_novas", "falar_novas_outras_conversas",
                      "falar_novas_fora_do_telezapp", "confirmar_envio",
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
        item(m_aj, "atualizacoes", "&Verificar atualizações...")
        item(m_aj, "logs", "Abrir a pasta de &logs")
        item(m_aj, "pasta_sons", "Abrir a pasta de s&ons")
        m_aj.AppendSubMenu(m_dep, "&Depurar")
        item(m_aj, "sobre", "&Sobre o %s" % NOME)

        m_fer = wx.Menu()
        item(m_fer, "gerenciar_contas", "&Gerenciar contas...")
        item(m_fer, "reconectar", "Reco&nectar as contas")
        item(m_fer, "editar_perfil", "Editar o &meu perfil...")
        m_fer.AppendSeparator()
        item(m_fer, "backup", "Fazer &backup...")
        item(m_fer, "restaurar_backup", "&Restaurar backup...")
        item(m_fer, "configuracoes", "C&onfigurações...\tCtrl+,")
        m_fer.AppendSeparator()
        item(m_fer, "instalar", "&Instalar o %s neste computador..." % NOME)
        item(m_fer, "criar_portatil", "Criar cópia &portátil...")
        item(m_fer, "desinstalar", "&Desinstalar o %s..." % NOME)
        m_fer.AppendSeparator()
        item(m_fer, "abrir_atalhos", "Personalizar os &atalhos...")
        item(m_fer, "esconder_janela",
             "&Esconder a janela e continuar em segundo plano")
        item(m_fer, "sair", "&Sair\tCtrl+Q")

        for submenu, rotulo in ((m_novo, "&Novo"), (m_ir, "&Ir para"),
                                (m_msg, "&Mensagens"), (m_conv, "C&onversas"),
                                (m_ctt, "Conta&tos"), (m_cham, "C&hamadas"),
                                (m_mid, "Mí&dias"), (m_exib, "&Exibir"),
                                (m_fer, "&Ferramentas"), (m_aj, "A&juda")):
            raiz.AppendSubMenu(submenu, rotulo)
        barra.Append(raiz, "Menu")        # Alt sozinho ja abre; Alt M fica livre
        self.SetMenuBar(barra)
        categorias = {m_novo: "Novo", m_ir: "Ir para",
                      m_msg: "Mensagens", m_conv: "Conversas",
                      m_ctt: "Contatos", m_cham: "Chamadas",
                      m_mid: "Mídias", m_exib: "Exibir",
                      m_fer: "Ferramentas", m_aj: "Ajuda", m_dep: "Ajuda",
                      m_baixar: "Mídias", m_estilo: "Exibir"}
        # nos grupos de opcoes o nome do item sozinho nao diz do que se trata
        grupos = {m_baixar: "Quando baixar as mídias",
                  m_estilo: "Como cada mensagem é lida"}
        for chave, it in self.itens.items():
            grupo = grupos.get(self._menu_do_item[chave])
            self.atalhos.registrar(
                chave, (grupo + ": " if grupo else "") + self._base_menu[chave],
                categorias.get(self._menu_do_item[chave], "Menu"),
                self._padrao_menu[chave])
        self.atalhos.registrar(
            "mostrar_janela", "Chamar o TeleZapp quando ele está em segundo "
            "plano (atalho global)", "Geral", "")
        self._atualizar_atalhos()

        ligacoes = {
            "adicionar_conta": lambda e: self._adicionar_conta_pelo_menu(),
            "gerenciar_contas": lambda e: self._gerenciar_contas(),
            "editar_perfil": lambda e: self._editar_perfil(),
            "reconectar": lambda e: self._reconectar(),
            "ir_filtro_conta": lambda e: self._ir_para(self.cx_conta, ""),
            "ir_filtro_tipo": lambda e: self._ir_para(self.cx_tipo, ""),
            "buscar_conv": lambda e: self._ir_para(self.campo_busca, ""),
            "esconder_trancadas": lambda e: self._esconder_trancadas(),
            "contatos": lambda e: self._gerenciar_contatos(),
            "salvar_pessoa": lambda e: self._salvar_pessoa(),
            "salvar_conv": lambda e: self._salvar_conversa(),
            "detalhes_conv": lambda e: self._detalhes_da_conversa(),
            "salvar_autor": lambda e: self._salvar_autor(),
            "bloqueados": lambda e: self._contatos_bloqueados(),
            "bloquear_pessoa": lambda e: self._bloquear_pessoa(),
            "logs": lambda e: self._abrir_logs(),
            "pasta_sons": lambda e: self._abrir_pasta("sons"),
            "sair": lambda e: self._sair(),
            "esconder_janela": lambda e: self._esconder_na_bandeja(),
            "configuracoes": lambda e: self._configuracoes(),
            "backup": lambda e: self._fazer_backup(),
            "restaurar_backup": lambda e: self._restaurar_backup(),
            "ir_conv": lambda e: self._ir_para(self.lista_conv, "conversas"),
            "ir_msgs": lambda e: self._ir_para(self.lista_msgs, "mensagens"),
            "ir_caixa": lambda e: self._mostrar_caixa(),
            "enviar_msg": lambda e: self._enviar_texto(),
            "nova_msg": lambda e: self._nova_mensagem(),
            "nova_chamada": lambda e: self._nova_chamada(),
            "novo_contato": lambda e: self._novo_contato(),
            "novo_grupo": lambda e: self._nova_conversa("grupo"),
            "novo_canal": lambda e: self._nova_conversa("canal"),
            "nova_comunidade": lambda e: self._nova_conversa("comunidade"),
            "ver_enquete": lambda e: self._abrir_enquete(),
            "nova_enquete": lambda e: self._nova_enquete(),
            "abrir_conv": lambda e: self._abrir_selecionada_na_lista(),
            "arquivar": lambda e: self._arquivar_conversa(),
            "trancar": lambda e: self._trancar_conversa(),
            "fixar": lambda e: self._fixar_conversa(),
            "silenciar": lambda e: self._silenciar_conversa(),
            "nao_lidas": lambda e: self._ir_nao_lidas(),
            "ler_ultima": lambda e: self._ler_ultima(),
            "atualizar": lambda e: self._atualizar_conversas(),
            "responder": lambda e: self._responder(),
            "responder_particular": lambda e: self._responder_em_particular(),
            "copiar": lambda e: self._copiar(),
            "encaminhar": lambda e: self._encaminhar(),
            "editar_msg": lambda e: self._editar_mensagem(),
            "reagir": lambda e: self._reagir(),
            "postar_status": lambda e: self._postar_status(),
            "inserir_emoji": lambda e: self._inserir_emoji(),
            "ortografia": lambda e: self._verificar_ortografia(),
            "ir_respondida": lambda e: self._ir_para_respondida(),
            "detalhes": lambda e: self._detalhes(),
            "apagar_msg": lambda e: self._apagar_mensagem(),
            "favoritar_msg": lambda e: self._favoritar_mensagem(),
            "dep_msg": lambda e: self._depurar_mensagem(),
            "dep_conv": lambda e: self._depurar_conversa(),
            "ajuda": lambda e: dialogos.mostrar_texto(
                self, "Teclas de atalho", AJUDA, "Teclas de atalho"),
            "anexar": lambda e: self._anexar_arquivo(),
            "gravar_mic": lambda e: self._gravar_rapido(MICROFONE),
            "gravar_som": lambda e: self._gravar_rapido(SOM_INTERNO),
            "gravar_pausa": lambda e: self._pausar_gravacao_rapida(),
            "gravar_descartar": lambda e: self._descartar_gravacao_rapida(),
            "abrir_atalhos": lambda e: self._configuracoes("Atalhos"),
            "gravar_mic_janela": lambda e: self._gravar(MICROFONE),
            "gravar_som_janela": lambda e: self._gravar(SOM_INTERNO),
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
            "audio_voltar": lambda e: self._pular_audio(-5),
            "audio_avancar": lambda e: self._pular_audio(5),
            "audio_voltar_mais": lambda e: self._pular_audio(-30),
            "audio_avancar_mais": lambda e: self._pular_audio(30),
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
            "atualizacoes": lambda e: self._verificar_atualizacoes(),
            "instalar": lambda e: self._instalar(),
            "criar_portatil": lambda e: self._criar_portatil(),
            "desinstalar": lambda e: self._desinstalar(),
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
        for chave in ("falar_novas", "falar_novas_outras_conversas",
                      "falar_novas_fora_do_telezapp", "confirmar_envio",
                      "falar_reacoes"):
            self.itens[chave].Check(bool(self.cfg.get(chave)))
            self.Bind(wx.EVT_MENU,
                      lambda e, k=chave: self._opcao(k, e.IsChecked()),
                      self.itens[chave])
        self.itens["estilo%d" % self.estilo].Check(True)
        self.itens.get("baixar_" + str(self.cfg.get("midias_baixar")),
                       self.itens["baixar_demanda"]).Check(True)

    # --------------------------------------------------- atalhos na tela
    def _mostrar_atalhos(self):
        return bool(self.cfg.get("mostrar_atalhos"))

    def _atualizar_atalhos(self):
        """Poe em cada item de menu o atalho que vale. Os atalhos sempre valem
        por uma tabela de aceleracao da janela; com a opcao de mostrar ligada
        o nome do atalho, em portugues, tambem vai no nome do item."""
        mostrar = self._mostrar_atalhos()
        entradas = []
        for chave, it in self.itens.items():
            canon = self.atalhos.efetivo(chave)
            base = self._base_menu[chave]
            nome = nucleo_atalhos.exibir(canon)
            if not (mostrar and canon):
                sufixo = ""
            elif nucleo_atalhos.no_fim_do_texto(canon):
                sufixo = " (%s)" % nome      # o wx nao entende "Seta para..."
            else:
                sufixo = "\t" + nome
            it.SetItemLabel(base + sufixo)
            if canon and hasattr(wx, "AcceleratorEntry"):
                entradas.append(ui_teclas.entrada_de_aceleracao(
                    canon, it.GetId()))
        if hasattr(wx, "AcceleratorTable"):
            self.SetAcceleratorTable(wx.AcceleratorTable(entradas))

    def _rotular_controles(self):
        """Escreve o atalho no nome dos botoes e rotulos que tem uma funcao
        com atalho (se a opcao estiver ligada)."""
        mostrar = self._mostrar_atalhos()
        for controle, base, chave, fixo in self._controles_atalho:
            canon = fixo or self.atalhos.efetivo(chave) if chave or fixo \
                else ""
            if chave == "enviar_msg" and self.cfg.get("enter_envia"):
                canon = "Enter"
            controle.SetLabel(base + (
                " (%s)" % nucleo_atalhos.exibir(canon) if mostrar and canon
                else ""))

    def _aplicar_atalhos(self, personalizados):
        """Guarda o que a pessoa escolheu e poe nos menus e nos controles."""
        self.cfg.set("atalhos", dict(personalizados))
        self.atalhos.definir_personalizados(personalizados)
        self._atualizar_atalhos()
        self._rotular_controles()
        self._registrar_atalho_global()

    def _registrar_atalho_global(self):
        """(Re)liga o atalho que chama o TeleZapp de qualquer lugar."""
        if not hasattr(self, "RegisterHotKey"):
            return
        try:
            self.UnregisterHotKey(self._id_global)
        except Exception:
            pass
        canon = self.atalhos.efetivo("mostrar_janela")
        if not canon:
            return
        par = ui_teclas.para_atalho_global(canon)
        if par is None or not self.RegisterHotKey(self._id_global, *par):
            log.warning("atalho global %s nao registrado", canon)
            bipe("erro")
            self.fala.falar(
                "Não consegui reservar o atalho %s para chamar o TeleZapp: "
                "outro programa já o usa. Escolha outro em Configurações, "
                "Atalhos." % nucleo_atalhos.texto_falado(canon),
                interromper=True)

    def _atualizar_bandeja(self):
        """Cria ou tira o icone da area de notificacao conforme a opcao de
        continuar em segundo plano."""
        quer = bool(self.cfg.get("segundo_plano"))
        if quer and self._bandeja is None:
            from telezapp.interface import bandeja
            self._bandeja = bandeja.criar(self)
        elif not quer and self._bandeja is not None and self.IsShown():
            self._tirar_bandeja()

    def _tirar_bandeja(self):
        b, self._bandeja = self._bandeja, None
        if b is not None:
            try:
                b.RemoveIcon()
                b.Destroy()
            except Exception:
                pass

    def _esconder_na_bandeja(self):
        """Esconde a janela; o programa segue rodando. Cria o icone se for
        preciso, para sempre haver um jeito de voltar."""
        if self._bandeja is None:
            from telezapp.interface import bandeja
            self._bandeja = bandeja.criar(self)
        if self._bandeja is None:
            self.fala.falar("Este Windows não tem a área de notificação "
                            "para esconder a janela.", interromper=True)
            return
        atalho = self.atalhos.efetivo("mostrar_janela")
        bipe("escondido")
        self.Hide()
        self.fala.falar(
            "O TeleZapp continua em segundo plano. Para voltar, %s." % (
                "aperte %s" % nucleo_atalhos.texto_falado(atalho) if atalho
                else "use o ícone da área de notificação"),
            interromper=True)

    def _mostrar_da_bandeja(self):
        """Traz a janela de volta, de onde ela estiver (escondida,
        minimizada ou atras de outras)."""
        if not self.IsShown():
            self.Show()
        if self.IsIconized():
            self.Iconize(False)
        self.Raise()
        bipe("voltou")
        self.fala.falar("TeleZapp", interromper=True)

    def _sair(self):
        """Encerra de verdade, mesmo com a opcao de segundo plano ligada."""
        self._saindo = True
        self.Close()

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
        # Sair logo depois da busca (e antes da lista, na ordem de Tab), como
        # na maioria dos programas; sem tecla de acesso, porque Alt abre o
        # Menu. O item Sair de Ferramentas e Control Q continuam valendo.
        self.botao_sair = wx.Button(painel, label="Sair")
        self.botao_sair.Bind(wx.EVT_BUTTON, seguro(lambda e: self._sair()))
        self.cx_conta.Bind(wx.EVT_CHOICE, seguro(self._ao_filtro_conta))
        self.cx_tipo.Bind(wx.EVT_CHOICE, seguro(self._ao_filtro_tipo))
        rot_conv = wx.StaticText(painel, label="Conversas")
        self.lista_conv = ListaDeTextos(painel, name="Conversas")
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
        # TE_PROCESS_ENTER: o Enter chega ao controle (o leitor de tela o ve e
        # fecha a palavra digitada) e o envio sai do EVT_TEXT_ENTER
        self.caixa = wx.TextCtrl(painel,
                                 style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER,
                                 name="Digite sua mensagem")
        self.botao_enviar = wx.Button(painel, label="&Enviar")
        # sem tecla de acesso: Alt abre o Menu e as letras ja estao em uso
        self.botao_anexar = wx.Button(painel, label="Anexar e enviar arquivo")
        self.botao_mic = wx.Button(painel, label="Gravar do microfone")
        self.botao_som = wx.Button(painel, label="Gravar som do computador")
        self.botoes_envio = (self.botao_enviar, self.botao_anexar,
                             self.botao_mic, self.botao_som)
        # (controle, nome sem atalho, funcao, atalho fixo)
        self._controles_atalho = [
            (rot_cx_conta, "Serviço ou conta", "ir_filtro_conta", ""),
            (rot_cx_tipo, "Tipo de conversa", "ir_filtro_tipo", ""),
            (rot_busca, "Buscar conversa", "buscar_conv", ""),
            (self.botao_sair, "Sair", "sair", ""),
            (rot_conv, "Conversas", "ir_conv", ""),
            (self.botao_enviar, "&Enviar", "enviar_msg", ""),
            (self.botao_anexar, "Anexar e enviar arquivo", "anexar", ""),
            (self.botao_mic, "Gravar do microfone", "gravar_mic", ""),
            (self.botao_som, "Gravar som do computador", "gravar_som", ""),
        ]

        esq = wx.BoxSizer(wx.VERTICAL)
        esq.Add(rot_cx_conta, 0, wx.BOTTOM, 2)
        esq.Add(self.cx_conta, 0, wx.EXPAND | wx.BOTTOM, 6)
        esq.Add(rot_cx_tipo, 0, wx.BOTTOM, 2)
        esq.Add(self.cx_tipo, 0, wx.EXPAND | wx.BOTTOM, 6)
        esq.Add(rot_busca, 0, wx.BOTTOM, 2)
        esq.Add(self.campo_busca, 0, wx.EXPAND | wx.BOTTOM, 6)
        esq.Add(self.botao_sair, 0, wx.BOTTOM, 6)
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

        self.lista_conv.Bind(wx.EVT_LIST_ITEM_ACTIVATED,
                             seguro(lambda e: self._abrir_selecionada_na_lista()))
        self.lista_conv.Bind(wx.EVT_CONTEXT_MENU, seguro(self._menu_conversa))
        self.lista_msgs.Bind(wx.EVT_CONTEXT_MENU, seguro(self._menu_mensagem))
        self.lista_msgs.Bind(wx.EVT_KEY_DOWN, self._tecla_mensagens)
        self.lista_msgs.Bind(wx.EVT_LISTBOX,
                             seguro(lambda e: self._atualizar_botoes()))
        self.caixa.Bind(wx.EVT_TEXT_PASTE, self._ao_colar)
        self.caixa.Bind(wx.EVT_TEXT_ENTER,
                        seguro(lambda e: self._enter_na_caixa()))
        self.caixa.Bind(wx.EVT_KEY_DOWN, self._tecla_caixa)
        self.caixa.Bind(wx.EVT_CHAR, self._char_caixa)
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
                # sem id nem @usuario nao ha conversa a abrir (contato que
                # nao esta no servico): so a informacao
                abre = mencoes[i].get("id") or mencoes[i].get("usuario")
                b.SetLabel((("Iniciar conversa com " if abre else
                             "Contato sem conversa possível: ")
                            + rotulos_mencao[i]).replace("&", "&&"))
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

    def _status_da_conversa(self):
        """"digitando", "online" ou "visto por último ..." da conversa
        aberta; "" se desligado ou se o servico nao informou."""
        if not self.cfg.get("status_no_titulo"):
            return ""
        if self.digitando is not None:
            p, expira = self.digitando
            if time.time() < expira:
                return m.texto_presenca(p.estado, quem=p.quem)
            self.digitando = None
        p = self.presenca
        if p is None:
            return ""
        try:
            return m.texto_presenca(p.estado, p.quando, p.aprox)
        except Exception:
            # o titulo nunca pode derrubar o que a pessoa pediu (tocar,
            # baixar, transcrever): sem status, so o nome
            log.exception("não consegui montar o status da conversa")
            return ""

    def _ev_presenca(self, e):
        if (e.conta_id, e.conversa_id) != self.atual or \
                not self.cfg.get("status_no_titulo"):
            return
        if e.estado in ("digitando", "gravando", "enviando"):
            # o servico so avisa quando comeca e quando para: se o "parou"
            # se perder, o aviso some sozinho
            self.digitando = (e, time.time() + 10)
            wx.CallLater(10500, self._atualizar_titulo)
        elif e.estado == "parou":
            self.digitando = None
        else:
            self.presenca = e
        self._atualizar_titulo()

    def _atualizar_titulo(self):
        """Titulo da janela: conversa aberta e o que esta em andamento
        (sincronia do historico, downloads de midia)."""
        base = NOME
        conv = self.indice.get(self.atual) if self.atual else None
        if conv is not None:
            base = "%s: %s" % (NOME, conv.nome)
            status = self._status_da_conversa()
            if getattr(conv, "temporaria_s", 0):
                status = ", ".join(x for x in (status, "mensagens "
                                   "temporárias: %s" % m.texto_periodo(
                                       conv.temporaria_s, conv.servico)) if x)
            if status:
                base += " (%s)" % status
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
        envios = list(self.progresso_envios.values())
        if len(envios) == 1:
            extras.append("enviando mídia %d%%" % envios[0])
        elif len(envios) > 1:
            extras.append("enviando %d mídias" % len(envios))
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
        # a lista de conversas sempre abre no topo, com o foco nela; onde a
        # pessoa parou fica guardado dentro de cada conversa (posicao)
        self.lista_conv.SetFocus()
        if self.lista_conv.GetCount():
            self.lista_conv.SetSelection(0)
        log.info("fala direta pelo NVDA: %s", self.fala.ativa())
        self._apagar_expiradas()
        if self.cfg.get("verificar_atualizacoes"):
            wx.CallLater(8000, lambda: self._verificar_atualizacoes(False))

    @seguro
    def _oferecer_primeira_conta(self):
        self._escolher_servico_e_adicionar(
            "Bem-vindo ao %s. Ainda não há nenhuma conta. Escolha qual "
            "adicionar agora, ou cancele para fazer isso depois pelo menu "
            "(tecla Alt), em Novo, Nova conta." % NOME)

    @seguro
    def _adicionar_conta_pelo_menu(self):
        self._escolher_servico_e_adicionar(
            "Escolha o serviço da conta que quer adicionar.")

    def _escolher_servico_e_adicionar(self, texto):
        """Janela para escolher o servico; depois, a tela de dados dele."""
        servicos = ["telegram", "whatsapp"]
        dlg = wx.SingleChoiceDialog(self, texto, "Adicionar conta",
                                    [m.SERVICOS[x] for x in servicos])
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

    def _nome_da_conta(self, dados):
        return dados.get("nome") or dados.get("telefone") or dados["id"]

    def _itens_de_contas(self):
        """[(id, rotulo, ativa)] das contas, para Gerenciar contas."""
        return [(c["id"], "%s, %s" % (self._nome_da_conta(c),
                                      m.SERVICOS.get(c.get("servico"), "")),
                 c.get("ativa", True) is not False)
                for c in self.cfg.contas()]

    @seguro
    def _gerenciar_contas(self):
        """Lista de contas com caixa de marcar (ativada ou desativada) e,
        com a conta em foco, os botoes Excluir e Renomear."""
        if not self.cfg.contas():
            self.fala.falar("Não há contas. Use Novo, Nova conta.")
            return
        from telezapp.interface.gerenciar_contas import DialogoContas
        dlg = DialogoContas(self, self._itens_de_contas, self._marcar_conta,
                            self._excluir_conta_id, self._renomear_conta_id)
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()

    def _marcar_conta(self, conta_id, ativa):
        """Liga ou desliga uma conta e diz o que aconteceu."""
        dados = next((c for c in self.cfg.contas() if c["id"] == conta_id),
                     None)
        if dados is None:
            return False
        nome = self._nome_da_conta(dados)
        if ativa:
            mudou = self.contas.ativar(conta_id)
            texto = "%s ativada, conectando." % nome
        else:
            mudou = self.contas.desativar(conta_id)
            texto = "%s desativada." % nome
        self._atualizar_caixa_conta()
        self.fala.falar(texto if mudou else "Não consegui mudar %s." % nome,
                        interromper=True)
        return bool(mudou)

    def _renomear_conta_id(self, conta_id, nome=None):
        """Pede um nome para a conta (se `nome` nao vier) e o grava. True se
        mudou."""
        dados = next((c for c in self.cfg.contas() if c["id"] == conta_id),
                     None)
        if dados is None:
            return False
        if nome is None:
            dlg = dialogos.DialogoCampos(
                self, "Renomear a conta", "Escolha o nome que esta conta "
                "terá no TeleZapp. Deixe em branco para voltar ao nome do "
                "serviço.", [("Nome da conta", self._nome_da_conta(dados),
                              False)])
            try:
                if dlg.ShowModal() != wx.ID_OK:
                    return False
                nome = dlg.valores()[0]
            finally:
                dlg.Destroy()
        if not self.contas.renomear(conta_id, nome):
            return False
        self._atualizar_caixa_conta()
        novo_nome = self.contas.nome(conta_id)
        self.fala.falar("Conta renomeada para %s." % novo_nome,
                        interromper=True)
        return True

    @seguro
    def _excluir_conta_id(self, conta_id):
        """Pergunta e remove a conta do TeleZapp (as conversas e mensagens
        guardadas dela neste computador). True se removeu."""
        dados = next((c for c in self.cfg.contas() if c["id"] == conta_id),
                     None)
        if dados is None:
            return False
        nome = "%s, %s" % (self._nome_da_conta(dados),
                           m.SERVICOS.get(dados.get("servico"), ""))
        r = wx.MessageBox(
            "Excluir a conta %s? As conversas e mensagens guardadas dela "
            "neste computador serão apagadas. A conta continua existindo no "
            "celular." % nome, "Excluir uma conta",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
        if r != wx.YES:
            return False
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
        self._atualizar_caixa_conta()
        self.fala.falar("Conta excluída.", interromper=True)
        return True

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
            lambda: self._pareamento_cancelado(conta_id), telefone, bipe,
            lambda: self._reiniciar_pareamento(conta_id))
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

    def _reiniciar_pareamento(self, conta_id):
        """Recomeca a conexao do WhatsApp que esta pareando (fora da janela,
        porque parar a anterior pode levar alguns segundos)."""
        dlg = self.pareamentos.get(conta_id)
        if dlg:
            dlg.reiniciou()

        def trabalho():
            self.contas.reiniciar_pareamento(conta_id)
        threading.Thread(target=trabalho, daemon=True,
                         name="reiniciar-pareamento").start()

    def _ev_pareamento_falhou(self, e):
        dlg = self.pareamentos.get(e.conta_id)
        if dlg is None:
            return
        dlg.falhas += 1
        bipe("erro")
        if dlg.falhas > 3:
            self.fala.falar("O WhatsApp recusou o pareamento de novo. Feche "
                            "esta janela e tente mais tarde.",
                            interromper=True)
            return
        if e.metodo == "codigo":
            dlg.avisar("O celular não aceitou o código. Estou refazendo a "
                       "conexão: confira o número, gere um código novo e "
                       "digite-o no celular assim que aparecer.")
        else:
            dlg.avisar("O WhatsApp recusou o QR Code. Estou refazendo a "
                       "conexão: um QR Code novo chega em alguns segundos.")
        self._reiniciar_pareamento(e.conta_id)

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
            ev.AutoresAtualizados: self._ev_autores_atualizados,
            ev.MensagemApagadaNoCelular: self._ev_mensagem_apagada,
            ev.MensagensCarregadas: self._ev_mensagens,
            ev.MensagemNova: self._ev_nova,
            ev.EnvioFalhou: self._ev_falha,
            ev.LeituraConfirmada: self._ev_leitura,
            ev.Aviso: self._ev_aviso,
            ev.EstadosMensagens: self._ev_estados_mensagens,
            ev.QrPareamento: self._ev_qr,
            ev.CodigoPareamento: self._ev_codigo,
            ev.PareamentoFalhou: self._ev_pareamento_falhou,
            ev.Presenca: self._ev_presenca,
            ev.ChamadaWhatsApp: self._ev_chamada_whatsapp,
            ev.SincronizacaoConcluida: self._ev_sincronia,
            ev.ProgressoSincronia: self._ev_progresso_sincronia,
            ev.ProgressoMidia: self._ev_progresso_midia,
            ev.ProgressoEnvio: self._ev_progresso_envio,
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
        if antes == ev.CONECTADA and e.estado != ev.CONECTADA and \
                e.estado != ev.PRECISA_LOGIN:
            self._caiu.add(e.conta_id)
            bipe("desconectada")
        if e.estado == ev.CONECTADA and antes != ev.CONECTADA:
            if e.conta_id in self._caiu:
                self._caiu.discard(e.conta_id)
                bipe("reconectada")
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
        if conv is not None and e.conta_id == conv.conta_id and                 self._escrita_liberada != (not conv.somente_leitura):
            # o servico mudou quem pode escrever na conversa aberta
            self._escrita_liberada = not conv.somente_leitura
            foco_na_caixa = self.FindFocus() is self.caixa
            self._mostrar_conversa(True, self._escrita_liberada)
            if foco_na_caixa and not self._escrita_liberada:
                self.lista_msgs.SetFocus()
            self.fala.falar("Agora você pode escrever nesta conversa."
                            if self._escrita_liberada else
                            TEXTO_SOMENTE_LEITURA, interromper=True)

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

    def _topicos_de(self, conv):
        """Conversas dos topicos de um grupo com topicos (Telegram), as
        fixadas e mais recentes primeiro; vazio nas outras conversas."""
        prefixo = conv.id + "#"
        return sorted((c for c in self.indice.values()
                       if c.conta_id == conv.conta_id
                       and c.id.startswith(prefixo)),
                      key=lambda c: (not c.fixada, -c.data))

    def _escolher_topico(self, conv):
        """Grupo com topicos: pergunta qual abrir e devolve a conversa dele
        (None se a pessoa desistir). As demais voltam como estao."""
        topicos = self._topicos_de(conv)
        if not topicos:
            return conv
        rotulos = [t.nome.split(" › ", 1)[-1] + (
            ", %d não lidas" % t.nao_lidas if t.nao_lidas > 1 else
            ", 1 não lida" if t.nao_lidas == 1 else "") for t in topicos]
        dlg = wx.SingleChoiceDialog(
            self, "Escolha o tópico de %s." % conv.nome, "Tópicos", rotulos)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return None
            return topicos[dlg.GetSelection()]
        finally:
            dlg.Destroy()

    def _ordenar(self):
        self._atualizar_caixa_conta()
        for c in self.indice.values():
            if "#" not in c.id:
                filhos = self._topicos_de(c)
                if filhos:       # o grupo mostra os nao lidas de todos
                    c.nao_lidas = sum(f.nao_lidas for f in filhos)
        self.conversas = sorted(
            (c for c in self.indice.values()
             if "#" not in c.id and (c.chave == self.atual or m.passa_filtro(
                 c, self.filtro_tipo, self.filtro_conta, self.busca))),
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
        rotulos = [self._com_marca(m.rotulo_conversa(c),
                                   c.chave in self.marc_conv)
                   for c in self.conversas]
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

    # ===================================================== modo de selecao
    @staticmethod
    def _com_marca(texto, marcada):
        return ("Marcada: " + texto) if marcada else texto

    def _marcadas_conv(self):
        """Conversas marcadas que aparecem na lista, na ordem dela."""
        return [self.indice[k] for k in self._chaves_conv
                if k in self.marc_conv and k in self.indice]

    def _marcadas_msg(self):
        return [x for x in self._mensagens_atuais()
                if x.id in self.marc_msg and not x.id.startswith("local-")]

    def _alternar_marca(self, lista):
        """Control Espaco liga o modo de selecao e marca o item em foco;
        no modo, Espaco marca ou desmarca o item em foco."""
        if lista is self.lista_conv:
            conv = self._conversa_selecionada()
            if conv is None:
                return
            novo = not self.modo_conv
            self.modo_conv = True
            marcas, chave = self.marc_conv, conv.chave
        else:
            x = self._mensagem_selecionada()
            if x is None or x.id.startswith("local-"):
                if x is not None:
                    self.fala.falar("Esta mensagem ainda está sendo enviada.")
                return
            novo = not self.modo_msg
            self.modo_msg = True
            marcas, chave = self.marc_msg, x.id
        marcada = chave not in marcas
        marcas.add(chave) if marcada else marcas.discard(chave)
        if lista is self.lista_conv:
            self._preencher_conversas()
        else:
            self._preencher_mensagens()
        n = len(marcas)
        texto = ("Marcada" if marcada else "Desmarcada") + ", " + (
            "nenhuma marcada" if n == 0 else
            "1 marcada" if n == 1 else "%d marcadas" % n) + "."
        if novo:
            texto = ("Modo de seleção. " + texto + " Espaço marca ou "
                     "desmarca, a tecla Menu mostra as ações e Esc sai.")
        self.fala.falar(texto, interromper=True)

    def _sair_selecao(self, lista, falar=True):
        """Esc no modo de selecao: desfaz as marcas e sai do modo."""
        if lista is self.lista_conv:
            self.modo_conv, self.marc_conv = False, set()
            self._preencher_conversas()
        else:
            self.modo_msg, self.marc_msg = False, set()
            self._preencher_mensagens()
        if falar:
            self.fala.falar("Seleção desfeita.", interromper=True)

    def _menu_em_massa(self, lista, pos, opcoes):
        menu = wx.Menu()
        for rotulo, tratador in opcoes:
            it = menu.Append(wx.ID_ANY, rotulo)
            self.Bind(wx.EVT_MENU, seguro(lambda e, t=tratador: t()), it)
        if pos == wx.DefaultPosition:
            lista.PopupMenu(menu, wx.Point(20, 20))
        else:
            lista.PopupMenu(menu, lista.ScreenToClient(pos))
        menu.Destroy()

    @staticmethod
    def _plural(n, um, varios):
        return "%d %s" % (n, um if n == 1 else varios)

    def _opcoes_em_massa_conv(self):
        convs = self._marcadas_conv()
        n = self._plural(len(convs), "conversa", "conversas")
        return [
            ("%s %s" % ("Desarquivar" if all(c.arquivada for c in convs)
                        else "Arquivar", n),
             lambda: self._massa_conversas("arquivar")),
            ("%s %s" % ("Desafixar" if all(c.fixada for c in convs)
                        else "Fixar", n),
             lambda: self._massa_conversas("fixar")),
            ("%s %s" % ("Reativar o som de" if all(
                c.silenciada() for c in convs) else "Silenciar", n),
             lambda: self._massa_conversas("silenciar")),
            ("%s %s" % ("Destrancar" if all(c.trancada for c in convs)
                        else "Trancar", n),
             lambda: self._massa_conversas("trancar")),
            ("Apagar %s..." % n, lambda: self._massa_conversas("apagar")),
            ("Desfazer a seleção",
             lambda: self._sair_selecao(self.lista_conv))]

    def _opcoes_em_massa_msg(self):
        msgs = self._marcadas_msg()
        n = self._plural(len(msgs), "mensagem", "mensagens")
        fav = all(m.extras_de(x)["favorita"] for x in msgs)
        return [
            ("%s %s" % ("Desfavoritar" if fav else "Favoritar", n),
             lambda: self._massa_mensagens("favoritar")),
            ("Copiar o texto de %s" % n,
             lambda: self._massa_mensagens("copiar")),
            ("Encaminhar %s..." % n,
             lambda: self._massa_mensagens("encaminhar")),
            ("Apagar %s..." % n, lambda: self._massa_mensagens("apagar")),
            ("Desfazer a seleção",
             lambda: self._sair_selecao(self.lista_msgs))]

    def _massa_conversas(self, acao):
        """Executa nas conversas marcadas, de uma vez, o que o menu de
        contexto do modo de selecao oferece."""
        convs = self._marcadas_conv()
        if not convs:
            return
        n = len(convs)
        quantas = self._plural(n, "conversa", "conversas")
        if acao == "arquivar":
            arquivar = not all(c.arquivada for c in convs)
            so_aqui = False
            for c in convs:
                prov = self.contas.provedor(c.conta_id)
                try:
                    if not (prov and prov.arquivar_conversa(c.id, arquivar)):
                        so_aqui = True
                except Exception:
                    log.exception("erro ao arquivar na conta")
                    so_aqui = True
                c.arquivada = arquivar
            texto = "%s %s%s." % (
                quantas, "arquivadas" if arquivar else "desarquivadas",
                ", algumas só no TeleZapp" if so_aqui else "")
        elif acao == "fixar":
            fixar = not all(c.fixada for c in convs)
            for c in convs:
                c.fixada = fixar
                self._avisar_conta(
                    c, lambda p, c=c: p.fixar_conversa(c.id, fixar),
                    "O serviço não aceitou. A mudança ficou só no TeleZapp.")
            texto = "%s %s." % (quantas, "fixadas" if fixar else "desafixadas")
        elif acao == "silenciar":
            silenciar = not all(c.silenciada() for c in convs)
            segundos = 0
            if silenciar:
                dlg = wx.SingleChoiceDialog(
                    self, "Silenciar %s por quanto tempo?" % quantas,
                    "Silenciar", [r for r, _ in self.DURACOES_SILENCIO])
                try:
                    if dlg.ShowModal() != wx.ID_OK:
                        return
                    segundos = self.DURACOES_SILENCIO[dlg.GetSelection()][1]
                finally:
                    dlg.Destroy()
            for c in convs:
                c.silenciada_ate = (time.time() + segundos if segundos
                                    else -1.0) if silenciar else 0.0
                self._avisar_conta(
                    c, lambda p, c=c: p.silenciar_conversa(
                        c.id, silenciar, segundos),
                    "O serviço não aceitou. A mudança ficou só no TeleZapp.")
            texto = "%s %s." % (quantas, "silenciadas" if silenciar
                                else "com o som reativado")
        elif acao == "trancar":
            trancar = not all(c.trancada for c in convs)
            chaves = {c.chave for c in convs}
            locais = [k for k in (self.cfg.get("trancadas_locais") or [])
                      if tuple(k) not in chaves]
            for c in convs:
                c.trancada = trancar
                if trancar:
                    locais.append(list(c.chave))
            self.cfg.set("trancadas_locais", locais)
            texto = "%s %s, só no TeleZapp." % (
                quantas, "trancadas" if trancar else "destrancadas")
        else:
            if not self._apagar_varias_conversas(convs, quantas):
                return
            self._sair_selecao(self.lista_conv, falar=False)
            return
        if acao in ("arquivar", "trancar") and self.atual in {
                c.chave for c in convs}:
            self._fechar_conversa()
        self.banco.salvar_conversas(convs)
        self._sair_selecao(self.lista_conv, falar=False)
        self._montar_tipos()
        self._ordenar()
        self._preencher_conversas()
        self.fala.falar(texto, interromper=True)

    def _apagar_varias_conversas(self, convs, quantas):
        """Uma pergunta so para todas; False se a pessoa desistiu."""
        provs = {c.chave: self.contas.provedor(c.conta_id) for c in convs}
        no_celular = any(
            p and getattr(p, "APAGA_NA_CONTA", False) and
            self.estados.get(c.conta_id) == ev.CONECTADA
            for c, p in ((c, provs[c.chave]) for c in convs))
        texto = ("Apagar %s? As mensagens e as mídias delas serão apagadas "
                 "deste computador. Elas só voltam se chegar uma mensagem "
                 "nova." % quantas)
        if no_celular:
            dlg = wx.MessageDialog(
                self, texto + " Quer apagar também no celular?",
                "Apagar conversas",
                wx.YES_NO | wx.CANCEL | wx.CANCEL_DEFAULT | wx.ICON_QUESTION)
            dlg.SetYesNoCancelLabels("Apagar aqui e no celular",
                                     "Apagar só aqui", "Cancelar")
            try:
                r = dlg.ShowModal()
            finally:
                dlg.Destroy()
            if r == wx.ID_CANCEL:
                return False
            no_celular = r == wx.ID_YES
        else:
            r = wx.MessageBox(texto + " A conta não é afetada.",
                              "Apagar conversas",
                              wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
                              self)
            if r != wx.YES:
                return False
        for c in convs:
            prov = provs[c.chave]
            celular = no_celular and prov and getattr(
                prov, "APAGA_NA_CONTA", False) and                 self.estados.get(c.conta_id) == ev.CONECTADA
            ultima = None
            if celular:
                guardadas = self.banco.mensagens(c.conta_id, c.id, 1)
                ultima = guardadas[-1] if guardadas else None
            self._remover_conversa_local(c)
            if celular:
                threading.Thread(
                    target=self._apagar_no_celular, args=(prov, c, ultima),
                    daemon=True, name="apagar-no-celular").start()
        self.fala.falar("%s apagadas. Elas só voltam com uma mensagem nova."
                        % quantas.capitalize(), interromper=True)
        return True

    def _massa_mensagens(self, acao):
        msgs = self._marcadas_msg()
        if not msgs:
            return
        quantas = self._plural(len(msgs), "mensagem", "mensagens")
        if acao == "favoritar":
            favorita = not all(m.extras_de(x)["favorita"] for x in msgs)
            for x in msgs:
                m.atualizar_extras(x, favorita=favorita)
                prov = self.contas.provedor(x.conta_id)                     if self.contas else None
                if prov is not None and getattr(prov, "FAVORITA_NA_CONTA",
                                                False):
                    self._avisar_conta(
                        x, lambda p, x=x: p.favoritar_mensagem(x, favorita),
                        "O serviço não aceitou. A marca ficou só no "
                        "TeleZapp.")
            self.banco.salvar_mensagens(msgs)
            texto = "%s %s." % (quantas.capitalize(), (
                "favoritada" if len(msgs) == 1 else "favoritadas")
                if favorita else (
                "desfavoritada" if len(msgs) == 1 else "desfavoritadas"))
        elif acao == "encaminhar":
            self._sair_selecao(self.lista_msgs, falar=False)
            self._encaminhar(msgs)
            return
        elif acao == "copiar":
            partes = []
            for x in msgs:
                quem = "Você" if x.minha else (
                    x.autor or self._quem_enviou(x) or "Desconhecido")
                partes.append("%s: %s" % (quem, x.texto or m.conteudo(x)))
            self._sair_selecao(self.lista_msgs, falar=False)
            self._copiar_texto("\n".join(partes))
            return
        else:
            if not self._apagar_varias_mensagens(msgs, quantas):
                return
            self._sair_selecao(self.lista_msgs, falar=False)
            return
        self._sair_selecao(self.lista_msgs, falar=False)
        self.fala.falar(texto, interromper=True)

    def _apagar_varias_mensagens(self, msgs, quantas):
        """Uma pergunta so para todas; False se a pessoa desistiu."""
        def na_conta(x):
            prov = self.contas.provedor(x.conta_id) if self.contas else None
            return prov if prov is not None and \
                self.estados.get(x.conta_id) == ev.CONECTADA else None
        minhas_na_conta = any(x.minha and na_conta(x) for x in msgs)
        para_todos = False
        if minhas_na_conta:
            dlg = wx.MessageDialog(
                self, "Apagar %s? Elas somem daqui e do celular." % quantas,
                "Apagar mensagens",
                wx.YES_NO | wx.CANCEL | wx.CANCEL_DEFAULT | wx.ICON_QUESTION)
            dlg.SetYesNoCancelLabels(
                "Apagar as minhas para todos", "Apagar só para mim",
                "Cancelar")
            try:
                r = dlg.ShowModal()
            finally:
                dlg.Destroy()
            if r == wx.ID_CANCEL:
                return False
            para_todos = r == wx.ID_YES
        else:
            r = wx.MessageBox(
                "Apagar %s? Elas somem daqui e, se a conta estiver "
                "conectada, da conta também." % quantas,
                "Apagar mensagens",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
            if r != wx.YES:
                return False
        for x in msgs:
            prov = na_conta(x)
            self._remover_mensagem_local(x.conta_id, x.conversa_id, x.id)
            if prov is not None:
                threading.Thread(
                    target=self._apagar_na_conta,
                    args=(prov, x, para_todos and x.minha), daemon=True,
                    name="apagar-mensagem").start()
        self.fala.falar("%s apagadas." % quantas.capitalize(),
                        interromper=True)
        return True

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
        if conv.tipo == "grupo":
            pode_sair = bool(prov and getattr(prov, "SAI_DE_GRUPO", False)
                             and self.estados.get(conv.conta_id)
                             == ev.CONECTADA)
            acao = dialogos.escolher_acao_grupo(self, conv.nome, pode_sair)
            if acao is None:
                return
            if acao == "limpar":
                self._limpar_conversa(conv)
                return
            if acao in ("sair", "sair_apagar"):
                self._sair_do_grupo(conv, prov, acao == "sair_apagar")
                return
        no_celular = bool(prov and getattr(prov, "APAGA_NA_CONTA", False) and
                          conv.tipo != "status" and
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

    def _limpar_conversa(self, conv):
        """Apaga as mensagens e as mídias da conversa neste computador, mas
        deixa a conversa na lista (as favoritas tambem saem). O que e limpo
        nao volta por historico."""
        sel = limpeza.selecionar(self.banco, limpeza.Filtros(
            o_que=limpeza.MENSAGENS, conta_id=conv.conta_id,
            conversa_id=conv.id, manter_favoritas=False))
        if not sel.quantidade:
            self.fala.falar("A conversa já está vazia.", interromper=True)
            return
        feitos, liberados, falhas = limpeza.apagar(self.banco, sel)
        self._ao_limpar(sel)
        texto = "Conversa limpa: %d mensagens apagadas" % feitos
        if liberados:
            texto += ", %s liberados" % m.tamanho_legivel(liberados)
        texto += ". O grupo continua na lista."
        if falhas:
            texto += " %d não puderam ser apagadas (talvez em uso)." % falhas
        self.fala.falar(texto, interromper=True)

    def _sair_do_grupo(self, conv, prov, apagar):
        """Tira a conta do grupo, num thread, e so depois (se deu certo e
        `apagar`) tira a conversa da lista."""
        if prov is None or not getattr(prov, "SAI_DE_GRUPO", False) or \
                self.estados.get(conv.conta_id) != ev.CONECTADA:
            bipe("erro")
            self.fala.falar("Para sair do grupo a conta precisa estar "
                            "conectada.", interromper=True)
            return
        self.fala.falar("Saindo do grupo %s..." % conv.nome, interromper=True)

        def trabalho():
            try:
                ok = bool(prov.sair_do_grupo(conv.id))
            except Exception:
                log.exception("erro ao sair do grupo")
                ok = False
            wx.CallAfter(self._saiu_do_grupo, conv, apagar, ok)
        threading.Thread(target=trabalho, daemon=True,
                         name="sair-do-grupo").start()

    def _saiu_do_grupo(self, conv, apagar, ok):
        if not ok:
            bipe("erro")
            self.fala.falar("Não consegui sair do grupo %s. Nada foi "
                            "apagado." % conv.nome, interromper=True)
            return
        if apagar and conv.chave in self.indice:
            self._remover_conversa_local(conv)
        self.fala.falar("Você saiu do grupo %s%s." % (
            conv.nome, " e a conversa saiu da lista" if apagar else ""),
            interromper=True)

    def _apagar_no_celular(self, prov, conv, ultima):
        ok = prov.apagar_conversa(conv.id, ultima)
        wx.CallAfter(lambda: self.fala.falar(
            "Conversa apagada também no celular." if ok else
            "Não consegui apagar a conversa no celular. Ela foi apagada só "
            "aqui.", interromper=True))

    def _favoritar_mensagem(self, x=None):
        """Marca a mensagem como favorita, ou tira a marca. Favoritas nao
        entram na limpeza; no WhatsApp a conta tambem e avisada."""
        if x is None:
            x = self._mensagem_selecionada()
        if x is None:
            return
        if x.id.startswith("local-"):
            self.fala.falar("Esta mensagem ainda está sendo enviada.")
            return
        favorita = not m.extras_de(x)["favorita"]
        m.atualizar_extras(x, favorita=favorita)
        self.banco.salvar_mensagens([x])
        self._preencher_mensagens()
        prov = self.contas.provedor(x.conta_id) if self.contas else None
        if prov is not None and getattr(prov, "FAVORITA_NA_CONTA", False):
            self._avisar_conta(
                x, lambda p: p.favoritar_mensagem(x, favorita),
                "O serviço não aceitou. A marca ficou só no TeleZapp.")
        self.fala.falar("Mensagem favoritada." if favorita
                        else "Mensagem desfavoritada.", interromper=True)

    # ======================================================= encaminhar
    def _encaminhar(self, msgs=None):
        """Reenvia a mensagem selecionada (ou as marcadas) para as conversas
        que a pessoa escolher, de qualquer conta conectada. Midia so sai se
        ja foi baixada."""
        from telezapp.interface import encaminhar as je
        if msgs is None:
            x = self._mensagem_selecionada()
            msgs = [x] if x is not None else []
        msgs = [x for x in msgs if not x.id.startswith("local-")]
        if not msgs:
            self.fala.falar("Selecione uma mensagem.")
            return
        itens, pulados = [], []
        for x in sorted(msgs, key=lambda y: y.data):
            item, motivo = enc.preparar(x, self._caminho_da_midia)
            if item is None:
                pulados.append(motivo)
            else:
                itens.append(item)
        if not itens:
            bipe("erro")
            texto = "Nada para encaminhar: %s." % "; ".join(sorted(
                set(pulados)))
            self.fala.falar(texto, interromper=True)
            wx.MessageBox(texto, NOME, wx.OK | wx.ICON_WARNING, self)
            return
        nomes_contas = {d["id"]: d.get("nome") or d.get("telefone") or d["id"]
                        for d in self.cfg.contas()}
        varias = len(nomes_contas) > 1
        destinos = enc.destinos(
            list(self.indice.values()), self.banco.contatos(),
            lambda cid: self.estados.get(cid) == ev.CONECTADA and
            self.contas.provedor(cid) is not None,
            trancadas=self.trancadas_liberadas)
        if not destinos:
            self.fala.falar("Nenhuma conversa de conta conectada para "
                            "receber.", interromper=True)
            return

        def rotulo(d):
            partes = [d[2]]
            if d[3] == "grupo":
                partes.append("grupo")
            if varias:
                partes.append(nomes_contas.get(d[0], d[0]) + ", " + m.SERVICOS.get(
                    self.contas.servico(d[0]), ""))
            return ", ".join(partes)
        resumo = ("1 mensagem" if len(itens) == 1 else
                  "%d mensagens" % len(itens))
        if pulados:
            resumo += " (%d não pode ser encaminhada: %s)" % (
                len(pulados), "; ".join(sorted(set(pulados))))
        dlg = je.DialogoEncaminhar(self, destinos, rotulo, resumo)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            escolhidos = dlg.escolhidos()
        finally:
            dlg.Destroy()
        enviadas = falhas = 0
        for conta_id, conversa_id, nome, tipo in escolhidos:
            prov = self.contas.provedor(conta_id)
            if prov is None:
                falhas += len(itens)
                continue
            if (conta_id, conversa_id) not in self.indice:
                conv = m.Conversa(conta_id, conversa_id, nome,
                                  self.contas.servico(conta_id), "privada",
                                  data=time.time())
                self.indice[(conta_id, conversa_id)] = conv
                self._ordenar()
                self._preencher_conversas()
            for item in itens:
                try:
                    if item.tipo == "texto":
                        prov.enviar_texto(conversa_id, item.texto)
                    else:
                        try:
                            anexo = envio.preparar(
                                item.caminho, voz=item.tipo_midia == m.VOZ)
                        except envio.ErroEnvio:
                            if item.tipo_midia != m.VOZ:
                                raise
                            # voz que nao e Ogg/Opus: segue como arquivo
                            anexo = envio.preparar(item.caminho)
                        prov.enviar_arquivo(conversa_id, anexo, item.texto)
                    enviadas += 1
                except Exception as e:
                    log.warning("encaminhar falhou: %r", e)
                    falhas += 1
        texto = "%s para %s." % (
            "Encaminhando %d envios" % enviadas if enviadas != 1 else
            "Encaminhando 1 envio",
            "1 conversa" if len(escolhidos) == 1 else
            "%d conversas" % len(escolhidos))
        if falhas:
            texto += " %d não puderam ser enviados." % falhas
        if pulados:
            texto += " Não foram encaminhadas: %s." % "; ".join(sorted(
                set(pulados)))
        self.fala.falar(texto, interromper=True)

    def _caminho_da_midia(self, x):
        if self.midias is None or self.banco.foi_limpa(
                x.conta_id, x.conversa_id, x.id):
            return None
        return self.midias.caminho(x)

    def _apagar_mensagem(self, x=None):
        """Apaga a mensagem selecionada aqui e na conta (para todos, quando
        e minha e a pessoa escolhe, ou so para mim). Nao volta por historico
        nem por nova leitura."""
        if x is None:
            x = self._mensagem_selecionada()
        if x is None:
            return
        if x.id.startswith("local-"):
            self.fala.falar("Esta mensagem ainda está sendo enviada.")
            return
        prov = self.contas.provedor(x.conta_id) if self.contas else None
        na_conta = prov is not None and \
            self.estados.get(x.conta_id) == ev.CONECTADA
        para_todos = False
        if na_conta and x.minha:
            dlg = wx.MessageDialog(
                self, "Apagar esta mensagem? Ela some daqui e do celular.",
                "Apagar mensagem",
                wx.YES_NO | wx.CANCEL | wx.CANCEL_DEFAULT | wx.ICON_QUESTION)
            dlg.SetYesNoCancelLabels("Apagar para todos", "Apagar só para mim",
                                     "Cancelar")
            try:
                r = dlg.ShowModal()
            finally:
                dlg.Destroy()
            if r == wx.ID_CANCEL:
                return
            para_todos = r == wx.ID_YES
        else:
            r = wx.MessageBox(
                "Apagar esta mensagem?" + (
                    " Ela some daqui e do celular." if na_conta else
                    " A conta não está conectada: ela some só daqui."),
                "Apagar mensagem",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
            if r != wx.YES:
                return
        self._remover_mensagem_local(x.conta_id, x.conversa_id, x.id)
        if na_conta:
            threading.Thread(
                target=self._apagar_na_conta, args=(prov, x, para_todos),
                daemon=True, name="apagar-mensagem").start()
        self.fala.falar("Mensagem apagada.", interromper=True)

    def _apagar_na_conta(self, prov, x, para_todos):
        try:
            ok = bool(prov.apagar_mensagem(x, para_todos))
        except Exception:
            log.exception("erro ao apagar a mensagem na conta")
            ok = False
        if not ok:
            wx.CallAfter(lambda: self.fala.falar(
                "Não consegui apagar a mensagem na conta. Ela foi apagada só "
                "aqui.", interromper=True))

    def _remover_mensagem_local(self, conta_id, conversa_id, mensagem_id):
        limpeza.apagar_mensagem(self.banco, conta_id, conversa_id,
                                mensagem_id)
        self._tirar_da_memoria({(conta_id, conversa_id, mensagem_id)})

    def _ev_mensagem_apagada(self, e):
        """Mensagem apagada no celular: some daqui tambem."""
        aberta = (e.conta_id, e.conversa_id) == self.atual
        self._remover_mensagem_local(e.conta_id, e.conversa_id,
                                     e.mensagem_id)
        if aberta:
            self.fala.falar("Uma mensagem desta conversa foi apagada no "
                            "celular.")

    def _ev_autores_atualizados(self, e):
        """O servico achou o nome de gente que aparecia sem nome no grupo."""
        for lista in self.cache.values():
            for y in lista:
                if y.conta_id == e.conta_id and y.conversa_id == \
                        e.conversa_id and not y.minha and not y.autor and \
                        y.remetente in e.nomes:
                    y.autor = e.nomes[y.remetente]
        self._quem_cache.clear()
        if self.atual == (e.conta_id, e.conversa_id):
            self._preencher_mensagens()

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
            self._fim_do_envio(chave)
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
        self._ia_automatica(msg)
        self._previa_da_recebida(msg)
        log.info("mensagem nova (tipo %s, conversa aberta=%s)", msg.tipo,
                 aberta)
        if self._conversa_muda(conv, aberta):
            return        # arquivada ou trancada: sem som, fala nem aviso
        resumo = m.formatar(msg, m.ESTILO_AUTOR_PRIMEIRO,
                            quem=self._quem_enviou(msg))
        aviso = ("Nova mensagem. " + resumo) if aberta else \
            "Nova mensagem em %s. %s" % (conv.nome, resumo)
        if conv.tipo == "grupo" and self._cita_voce(msg):
            bipe("mencao_ou_resposta")          # no lugar do som comum
        else:
            bipe("nova_aberta" if aberta else
                 "nova_grupo" if conv.tipo == "grupo" else "nova")
        if self._deve_falar_nova(aberta):
            self.fala.falar(aviso)
        self.SetStatusText(aviso[:150])

    def _cita_voce(self, msg):
        """A mensagem de grupo me menciona ou responde a uma mensagem minha?"""
        if m.extras_de(msg)["citou_voce"]:
            return True
        if not msg.resposta_a:
            return False
        for x in self.cache.get((msg.conta_id, msg.conversa_id), []):
            if x.id == msg.resposta_a:
                return bool(x.minha)
        try:
            return any(x.minha for x in self.banco.mensagens_por_id(
                msg.conta_id, [msg.resposta_a], msg.conversa_id))
        except Exception:
            return False

    def _deve_falar_nova(self, aberta):
        """Fala a mensagem nova? Tres opcoes, uma por lugar: a conversa
        aberta, as outras conversas e fora do TeleZapp (janela sem foco).
        Nenhuma depende do som."""
        if not self.IsActive():
            return bool(self.cfg.get("falar_novas_fora_do_telezapp"))
        if aberta:
            return bool(self.cfg.get("falar_novas"))
        return bool(self.cfg.get("falar_novas_outras_conversas"))

    def _ev_sincronia(self, e):
        if not e.quantas:
            return
        texto = ("1 mensagem nova chegou" if e.quantas == 1 else
                 "%d mensagens novas chegaram" % e.quantas) + \
            " no WhatsApp enquanto o TeleZapp estava fechado."
        log.info("sincronia: %d mensagens novas", e.quantas)
        bipe("nova")
        if self._deve_falar_nova(False):
            self.fala.falar(texto)
        self.SetStatusText(texto)

    def _ev_falha(self, e):
        chave = (e.conta_id, e.conversa_id)
        self._fim_do_envio(chave)
        self._acao_concluida(chave, e.texto, False)
        achada = self._local_enviando(self.cache.get(chave, []), e.texto,
                                      getattr(e, "tipo", m.TEXTO))
        if achada is not None:
            achada.estado = m.FALHOU
        if chave == self.atual:
            self._preencher_mensagens()
            if e.devolver_texto and not self.caixa.GetValue():
                self.caixa.SetValue(e.texto)
        bipe("falha_envio")
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
            if e.mensagem.minha and e.emoji and e.quem != "Você":
                bipe("reacao_recebida")
            if e.mensagem.minha and e.emoji and e.quem != "Você" and \
                    self.cfg.get("falar_reacoes"):
                self.fala.falar("%s reagiu com %s à sua mensagem: %s" % (
                    e.quem, e.emoji, m.citacao(e.mensagem)))
                self.SetStatusText("%s reagiu com %s" % (e.quem, e.emoji))
        elif e.motivo == "enquete":
            if e.quem == "Você":
                bipe("voto_enviado")
            elif e.mensagem.minha and e.quem:
                bipe("voto_enquete")
                self.SetStatusText("%s votou na sua enquete" % e.quem)
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
        self._ligar_para(conv)

    def _ligar_para(self, conv):
        """Liga para a conversa com uma pessoa, se a conta puder."""
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

    def _ev_chamada_whatsapp(self, e):
        """Chamada do WhatsApp: o TeleZapp so avisa (a linha na conversa o
        provedor ja deixou). Janela com OK e Conversar; se a chamada acaba
        com a janela aberta, o texto muda."""
        chave = (e.conta_id, e.chamada_id)
        aviso = self.avisos_de_chamada.get(chave)
        if e.fase == "tocando":
            if not self.cfg.get("avisar_chamadas_whatsapp") or aviso:
                return
            bipe("toque")
            texto = ch.texto_do_aviso(e.nome, e.video)
            self.fala.falar(texto, interromper=True)

            def conversar():
                conv = self._garantir_conversa(e.conta_id, e.conversa_id,
                                               e.nome)
                self._abrir_conversa_de(conv)
            dlg = dialogos.DialogoAvisoDeChamada(self, texto, conversar)
            self.avisos_de_chamada[chave] = dlg
            dlg.Bind(wx.EVT_CLOSE, lambda ev_, k=chave, d=dlg:
                     self._fechou_aviso_de_chamada(k, d))
            dlg.Show()
            dlg.Raise()
            self.RequestUserAttention()
            return
        if aviso is None:
            return
        texto = ch.texto_do_fim(e.nome, e.video, e.fase, e.segundos)
        bipe("desligada")
        aviso.atualizar(texto)
        self.fala.falar(texto, interromper=True)

    def _fechou_aviso_de_chamada(self, chave, dlg):
        self.avisos_de_chamada.pop(chave, None)
        dlg.Destroy()

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
        if a.som:
            bipe(a.som)
            if toque:
                self._repetir_toque(c, c.estado, a.som)
        self._atualizar_dialogo_chamada(c)
        if c.estado == ch.ENCERRADA:
            self.chamada = None

    def _repetir_toque(self, c, estado, som):
        """Repete o som enquanto a chamada continua no mesmo estado."""
        def de_novo():
            if self.chamada is c and c.estado == estado:
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
            if k == wx.WXK_SPACE and not (evt.AltDown() or evt.ShiftDown()) \
                    and foco in (self.lista_conv, self.lista_msgs):
                modo = self.modo_conv if foco is self.lista_conv \
                    else self.modo_msg
                if evt.ControlDown() or modo:
                    self._alternar_marca(foco)
                    return
            if k == wx.WXK_ESCAPE and sem_mod and \
                    self._gravacao_rapida is not None:
                self._terminar_gravacao_rapida(enviar=False)
                return
            if k == wx.WXK_ESCAPE and sem_mod:
                if foco is self.lista_conv and self.modo_conv:
                    self._sair_selecao(self.lista_conv)
                    return
                if foco is self.lista_msgs and self.modo_msg:
                    self._sair_selecao(self.lista_msgs)
                    return
                if foco is self.caixa or foco in self.botoes_envio:
                    self._sair_da_caixa()
                    return
                if foco is self.lista_msgs:
                    if not self._cancelar_download() and \
                            not self._parar_audio() and \
                            not self._voltar_da_respondida():
                        self._esc_da_conversa()
                    return
            if k == wx.WXK_DELETE and sem_mod:
                if foco is self.lista_conv:
                    self._apagar_conversa()
                    return
                if foco is self.lista_msgs:
                    self._apagar_mensagem()
                    return
            if k in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and sem_mod:
                if foco is self.lista_conv:
                    self._abrir_selecionada_na_lista()
                    return
                if foco is self.lista_msgs:
                    self._detalhes_ou_marcador()
                    return
                if foco is self.caixa:
                    # segue para a caixa, que envia pelo EVT_TEXT_ENTER
                    evt.Skip()
                    return
        except Exception:
            log.error("erro no teclado:\n%s", traceback.format_exc())
            return
        evt.Skip()

    def _enter_na_caixa(self):
        """O Enter chegou ao controle (o leitor de tela o viu). Por padrao
        envia; sem a opcao, quebra a linha e so o Control Enter envia."""
        if self.cfg.get("enter_envia"):
            self._enviar_texto()
        else:
            self.caixa.WriteText("\n")

    def _tecla_de_enviar(self):
        """Como dizer a pessoa qual tecla envia a mensagem."""
        if self.cfg.get("enter_envia"):
            return "Enter"
        canon = self.atalhos.efetivo("enviar_msg")
        return nucleo_atalhos.texto_falado(canon) if canon \
            else "o botão Enviar"

    def _tecla_caixa(self, evt):
        """Enter com modificador na caixa. Se a combinacao e a tecla de
        enviar (Control Enter, de fabrica), envia: o campo de texto fica com
        a tecla antes da tabela de aceleracao da janela. As outras
        combinacoes com Shift ou Control quebram a linha, porque com
        TE_PROCESS_ENTER todo Enter viraria envio."""
        if evt.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and \
                (evt.ShiftDown() or evt.ControlDown()) and not evt.AltDown():
            canon = nucleo_atalhos.montar(evt.ControlDown(), False,
                                          evt.ShiftDown(), "Enter")
            if canon == self.atalhos.efetivo("enviar_msg"):
                self._enviar_texto()
            else:
                self.caixa.WriteText("\n")
            return
        evt.Skip()

    def _char_caixa(self, evt):
        """Um @ digitado no comeco ou depois de espaco, numa conversa de
        grupo, abre a lista de membros para mencionar."""
        evt.Skip()
        if evt.GetUnicodeKey() != ord("@") or self.atual is None or \
                self.editando is not None:
            return
        conv = self.indice.get(self.atual)
        if conv is None or conv.tipo != "grupo":
            return
        pos = self.caixa.GetInsertionPoint()
        texto = self.caixa.GetValue()
        if pos > 0 and not texto[pos - 1:pos].isspace():
            return
        wx.CallAfter(self._mencionar, self.atual, pos)

    @seguro
    def _mencionar(self, chave, pos):
        if chave != self.atual:
            return
        membros = self._membros_grupo.get(chave)
        if membros is None:
            prov = self.contas.provedor(chave[0])
            if prov is None or self.estados.get(chave[0]) != ev.CONECTADA \
                    or self._carregando_membros == chave:
                return
            self._carregando_membros = chave
            self.fala.falar("Carregando os membros do grupo.")

            def ler():
                try:
                    dados = prov.detalhes_do_grupo(chave[1]) or {}
                except Exception:
                    log.error("membros do grupo:\n%s", traceback.format_exc())
                    dados = {}
                gente = [x for x in dados.get("participantes", [])
                         if not x.get("eu")]
                wx.CallAfter(self._membros_chegaram, chave, pos, gente)
            threading.Thread(target=ler, daemon=True,
                             name="membros-do-grupo").start()
            return
        self._escolher_mencao(membros, pos)

    @seguro
    def _membros_chegaram(self, chave, pos, gente):
        self._carregando_membros = None
        if not gente:
            self.fala.falar("Não consegui a lista de membros deste grupo.",
                            interromper=True)
            return
        self._membros_grupo[chave] = gente
        if chave == self.atual:
            self._escolher_mencao(gente, pos)

    def _escolher_mencao(self, membros, pos):
        escolhido = dialogos.escolher_membro(self, membros)
        self.caixa.SetFocus()
        if escolhido is None:
            return
        nome = escolhido["nome"]
        for outro in self.mencoes:
            if outro["nome"] == nome and outro["id"] != escolhido["id"]:
                nome += " " + (escolhido.get("telefone") or
                               escolhido["id"].split("@")[0][-4:])
                break
        men = {"id": escolhido["id"], "nome": nome,
               "usuario": escolhido.get("usuario", "")}
        if not any(x["id"] == men["id"] and x["nome"] == nome
                   for x in self.mencoes):
            self.mencoes.append(men)
        texto = self.caixa.GetValue()
        marca = "@" + nome + " "
        if texto[pos:pos + 1] == "@":
            self.caixa.Replace(pos, pos + 1, marca)
            self.caixa.SetInsertionPoint(pos + len(marca))
        else:
            self.caixa.WriteText(marca)
        self.fala.falar("Mencionado %s." % nome)

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
        conv = self._escolher_topico(conv)
        if conv is None:
            return
        self.atual = conv.chave
        self.resposta_a = None
        self.mencoes = []
        self.editando = None
        self.modo_msg, self.marc_msg = False, set()
        self._quem_cache.clear()
        self._descartar_anexos()
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
        self._escrita_liberada = not conv.somente_leitura
        self._mostrar_conversa(True, self._escrita_liberada)
        self._atualizar_titulo()
        self.presenca = self.digitando = None
        p = self.contas.provedor(conv.conta_id)
        if p is not None:
            if self.cfg.get("status_no_titulo"):
                p.observar_presenca(conv.id)
            if hasattr(p, "conversa_aberta"):
                p.conversa_aberta(conv.id)
            if conv.somente_leitura:
                self.fala.falar("Conversa somente leitura: você não pode "
                                "escrever nela.")
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

    def _esc_da_conversa(self):
        """Esc na conversa. Dentro de um topico de grupo (Telegram), volta
        para a lista de topicos do grupo, sem sair dele; Esc ali fecha."""
        aberta = self.atual
        self._fechar_conversa()
        if aberta is None or "#" not in aberta[1]:
            return
        grupo = (aberta[0], aberta[1].split("#")[0])
        conv = self.indice.get(grupo)
        if conv is None:
            return
        self._abrir_conversa(conv)
        if self.atual is None and grupo in self._chaves_conv:
            self.lista_conv.SetSelection(self._chaves_conv.index(grupo))

    def _fechar_conversa(self):
        """Esc na lista de mensagens: fecha a conversa e volta para a lista
        de conversas. Mensagens que chegarem depois contam como novas."""
        if self._gravacao_rapida is not None:
            self._terminar_gravacao_rapida(enviar=False)
        if self.atual in self._chaves_conv:
            self.lista_conv.SetSelection(self._chaves_conv.index(self.atual))
        if self.resposta_a is not None:
            self._cancelar_resposta()
        self._descartar_anexos()
        self._cancelar_edicao(falar=False)
        self.modo_msg, self.marc_msg = False, set()
        self._guardar_posicao()
        self.volta_para = []
        texto = self.caixa.GetValue()
        if texto.strip():
            self.rascunhos[self.atual] = texto
        else:
            self.rascunhos.pop(self.atual, None)
        self.caixa.Clear()
        self.marcador_id = None
        self.marcador_n = 0
        antes = self.atual
        self.atual = None
        self.presenca = self.digitando = None
        pa = self.contas.provedor(antes[0]) if antes else None
        if pa is not None:
            pa.parar_presenca(antes[1])
        self._ordenar()               # com filtro, a conversa pode sair
        self._preencher_conversas()
        self.mapa = [None]
        self._itens_msgs = []
        self.rot_msgs.SetLabel("Mensagens")
        self.lista_msgs.Set([TEXTO_SEM_CONVERSA])
        self._mostrar_conversa(False, False)
        self._atualizar_titulo()
        self.lista_conv.SetFocus()

    def _somente_leitura(self):
        """A conversa aberta nao aceita mensagens da conta? Se sim, avisa."""
        conv = self.indice.get(self.atual) if self.atual else None
        if conv is not None and conv.somente_leitura:
            bipe("erro")
            self.fala.falar(TEXTO_SOMENTE_LEITURA, interromper=True)
            return True
        return False

    def _mostrar_caixa(self):
        if self.atual is None:
            self.fala.falar(TEXTO_SEM_CONVERSA)
            return
        if self._somente_leitura():
            return
        self.caixa.SetFocus()

    def _sair_da_caixa(self):
        """Esc na caixa: primeiro cancela a resposta em andamento; sem
        resposta, fecha a conversa (o rascunho fica guardado). Midias coladas
        esperando o envio saem antes de tudo."""
        if self.editando is not None:
            self._cancelar_edicao()
            return
        if self.anexos:
            self._descartar_anexos(True)
            return
        if self.resposta_a is not None:
            self._cancelar_resposta()
            return
        self._esc_da_conversa()

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
            itens.append(self._com_marca(
                m.formatar(x, self.estilo, anterior,
                           quem=self._quem_enviou(x),
                           respondida=self._original(x, porid)
                           or self._motivo_do_original_ausente(x)
                           or None),
                x.id in self.marc_msg))
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

    def _motivo_do_original_ausente(self, x):
        """Por que a mensagem respondida nao esta aqui, quando foi o proprio
        TeleZapp que a tirou (limpeza ou conversa apagada); '' se nao se
        sabe."""
        if not x.resposta_a or self.banco is None:
            return ""
        if self.banco.foi_limpa(x.conta_id, x.conversa_id, x.resposta_a):
            return "uma mensagem que foi limpa deste computador"
        if self.banco.apagada_ate(x.conta_id, x.conversa_id) is not None:
            return ("uma mensagem de antes de a conversa ser apagada deste "
                    "computador")
        return ""

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
                self._enter_na_midia(x)
                return
            self._mostrar_texto(x)
            return
        self._detalhes()

    ENTER_DA_MIDIA = {"audio": "enter_audio", "imagem": "enter_imagem",
                      "figurinha": "enter_imagem", "video": "enter_video",
                      "pdf": "enter_pdf"}

    def _enter_na_midia(self, x):
        """Enter numa midia faz o que a pessoa escolheu: abrir ou reproduzir,
        so baixar, ou transcrever/descrever (mostrando o texto se ja
        existe)."""
        opcao = self.ENTER_DA_MIDIA.get(self._genero_ia(x))
        acao = (self.cfg.get(opcao) if opcao else "abrir") or "abrir"
        if acao == "baixar":
            self._abrir_midia(False, x)
        elif acao == "ia":
            if m.extras_de(x)["ia"].get("texto"):
                self._ia_ver(x)
            else:
                self._ia_processar(x)
        else:
            self._abrir_midia(True, x)

    def _mostrar_texto(self, x):
        """Enter numa mensagem so de texto: o texto numa caixa somente
        leitura, com Copiar texto e Fechar (Esc fecha). Os detalhes seguem em
        Alt Enter."""
        if m.enquete_de(x):
            self._abrir_enquete(x)
            return
        autor = "você" if x.minha else (x.autor or "mensagem")
        dialogos.mostrar_mensagem(
            self, "Mensagem de %s" % autor, x.texto or m.conteudo(x),
            self._copiar_texto)

    def _nova_enquete(self):
        """Cria uma enquete na conversa aberta (WhatsApp e Telegram)."""
        if self._so_texto_no_status():
            return
        destino = self._destino_do_envio()
        if destino is None:
            return
        conta_id, conversa_id, prov = destino
        if not getattr(prov, "PODE_CRIAR_ENQUETE", False):
            self.fala.falar("Este serviço não cria enquetes.",
                            interromper=True)
            return
        pedido = ui_nova_enquete.pedir_enquete(
            self, self.contas.servico(conta_id), self.fala)
        if pedido is None:
            self.caixa.SetFocus()
            return
        pergunta, opcoes, multipla, anonima = pedido
        prov.criar_enquete(conversa_id, pergunta, opcoes, multipla, anonima)
        self.fala.falar("Criando a enquete.", interromper=True)
        self.caixa.SetFocus()

    def _abrir_enquete(self, x=None):
        """A janela da enquete: as opcoes com a contagem e, se o servico
        deixa e a conta esta conectada, o voto."""
        x = x or self._mensagem_selecionada()
        if x is None or not m.enquete_de(x):
            self.fala.falar("Esta mensagem não é uma enquete.",
                            interromper=True)
            return
        prov = self.contas.provedor(x.conta_id) if self.contas else None
        pode = bool(prov is not None and getattr(prov, "PODE_VOTAR", False)
                    and self.estados.get(x.conta_id) == ev.CONECTADA)

        def obter():
            return self.banco.mensagem(x.conta_id, x.conversa_id, x.id) or x
        if pode:
            prov.atualizar_enquete(x)         # o Telegram traz o resultado
        ui_enquete.abrir(
            self, obter, pode,
            (lambda escolhas: prov.votar_enquete(obter(), escolhas))
            if prov is not None else (lambda escolhas: None),
            (lambda: prov.atualizar_enquete(obter()))
            if prov is not None else (lambda: None), self.fala)

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
        em_grupo = bool(conv is not None and conv.tipo == "grupo" and x.minha)
        # so o WhatsApp avisa quem recebeu, abriu e reproduziu em grupos
        contagens = self.contas.servico(x.conta_id) == "whatsapp"
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
        controle = None
        if em_grupo and contagens and recibos:
            controle = ControleRecibos(self, conv, recibos, nomes)
        pessoa = dialogos.mostrar_texto(
            self, "Detalhes da mensagem",
            m.detalhes(x, conv.nome if conv else "", recibos=recibos,
                       nomes=nomes, midia=midia, grupo=em_grupo,
                       contagens=contagens),
            "Detalhes e texto completo", links=links,
            botoes_extra=controle.botoes() if controle else (),
            botoes=[tuple(b) for b in extras["botoes"]],
            mencoes=extras["mencoes"],
            acoes=[(a.get("rotulo", ""), a.get("tipo") == "lista")
                   for a in extras["acoes"]])
        if controle is not None and controle.abrir_conversa is not None:
            wx.CallAfter(self._abrir_conversa_de, controle.abrir_conversa)
        elif pessoa is not None and "_acao" in pessoa:
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
        if acao.get("tipo") == "entrar":
            self._entrar_no_grupo(x, acao, prov)
            return
        rotulo = acao.get("rotulo", "")
        self._acoes_enviadas.append((x.conta_id, x.conversa_id, rotulo))
        try:
            prov.responder_acao(x, acao)
        except NotImplementedError:
            self._acoes_enviadas.pop()
            bipe("erro")
            self.fala.falar("Este serviço ainda não responde a botões.")

    # =========================================== inteligencia artificial
    ROTULOS_IA = {"audio": "Transcrever o áudio",
                  "imagem": "Descrever a imagem",
                  "figurinha": "Descrever a figurinha",
                  "video": "Descrever o vídeo",
                  "pdf": "Converter o PDF em texto acessível"}

    @staticmethod
    def _genero_ia(x):
        """O que a IA faz com a mensagem: audio, imagem, figurinha, video ou
        pdf; vazio se nada."""
        if x.id.startswith("local-"):
            return ""
        if x.tipo in (m.VOZ, m.AUDIO):
            return "audio"
        if x.tipo == m.FOTO:
            return "imagem"
        if x.tipo == m.FIGURINHA:
            return "figurinha"
        if x.tipo == m.VIDEO:
            return "video"
        if x.tipo == m.DOCUMENTO and (x.nome_arquivo or "").lower().endswith(
                ".pdf"):
            return "pdf"
        return ""

    ROTULOS_ABRIR = {m.VOZ: "Reproduzir a mensagem de voz",
                     m.AUDIO: "Reproduzir o áudio", m.VIDEO: "Reproduzir o vídeo",
                     m.FOTO: "Abrir a foto", m.FIGURINHA: "Abrir a figurinha",
                     m.DOCUMENTO: "Abrir o documento"}

    def _opcoes_midia(self, x):
        """Abrir ou reproduzir, baixar e salvar copia no menu de contexto,
        qualquer que seja o que o Enter faz na midia (Configuracoes, Midias)."""
        if x.tipo not in armazem.BAIXAVEIS or x.id.startswith("local-") or \
                m.extras_de(x)["apagada"] or self.midias is None:
            return []
        opcoes = [(self.ROTULOS_ABRIR.get(x.tipo, "Abrir a mídia"),
                   lambda: self._abrir_midia(True, x))]
        if self.midias.caminho(x):
            opcoes.append(("Salvar cópia da mídia...", self._salvar_midia))
        else:
            opcoes.append(("Baixar a mídia sem abrir",
                           lambda: self._abrir_midia(False, x)))
        return opcoes

    def _opcoes_ia(self, x):
        genero = self._genero_ia(x)
        if not genero:
            return []
        rotulo = self.ROTULOS_IA[genero]
        if m.extras_de(x)["ia"].get("texto"):
            return [("Ver a " + m.rotulo_da_ia(x), lambda: self._ia_ver(x)),
                    (rotulo + " de novo", lambda: self._ia_processar(x))]
        return [(rotulo, lambda: self._ia_processar(x))]

    def _ia_processar(self, x, auto=False):
        """Transcreve, descreve ou converte a midia da mensagem com os
        provedores da tarefa, na ordem que a pessoa escolheu (o proximo
        entra se um falhar); baixa a midia antes, se preciso. `auto`: veio
        de uma mensagem recebida; nada de janelas nem de pergunta, so o que
        ja foi autorizado."""
        genero = self._genero_ia(x)
        if not genero:
            return
        tarefa = cat_ia.TAREFA_DO_GENERO[genero]
        ordens = self.cfg.get("ia_ordem") or {}
        ordem = [p for p in ordens.get(tarefa, [])
                 if cat_ia.aceita(p, genero)]
        if not ordem:
            if auto:
                return
            bipe("erro")
            self.fala.falar(
                "Marque e ordene os provedores para %s em Configurações, "
                "Inteligência artificial." %
                cat_ia.NOMES_DE_TAREFA[tarefa].lower(), interromper=True)
            self._configuracoes("Inteligência artificial")
            return
        com_chave = [p for p in ordem if self.cofre_ia.tem(p)]
        if not com_chave:
            if auto:
                return
            bipe("erro")
            self.fala.falar(
                "Nenhum dos provedores marcados tem chave. Digite a chave em "
                "Configurações, Inteligência artificial.", interromper=True)
            self._configuracoes("Inteligência artificial")
            return
        # a fala de um video e transcrita a parte, pelos provedores de voz,
        # quando o video vai por quadros
        com_chave_audio = []
        if genero == "video":
            com_chave_audio = [
                p for p in ordens.get(cat_ia.AUDIO, [])
                if cat_ia.aceita(p, "audio") and self.cofre_ia.tem(p)]
        if x.chave in self._ia_ocupadas:
            if not auto:
                self.fala.falar("Esta mensagem já está sendo processada.")
            return
        consentidos = self.cfg.get("ia_consentimento") or []
        novos = [p for p in dict.fromkeys(com_chave + com_chave_audio)
                 if p not in consentidos]
        if novos:
            if auto:
                self.SetStatusText("A IA automática espera você autorizar "
                                   "os provedores: use o menu da mensagem "
                                   "uma vez.")
                return
            nomes = ", ".join(cat_ia.PROVEDORES[p].nome for p in novos)
            r = wx.MessageBox(
                "Para isso o TeleZapp envia o arquivo (a voz, a imagem, o "
                "vídeo ou o PDF) para %s, serviço%s de terceiros, com a sua "
                "chave, na ordem escolhida. O que eles fazem com os dados "
                "depende da política de cada um (o botão de privacidade, em "
                "Configurações, abre a página). Continuar e lembrar esta "
                "escolha para %s?" % (nomes, "" if len(novos) == 1 else "s",
                                      nomes),
                "Enviar para a inteligência artificial",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
            if r != wx.YES:
                return
            self.cfg.set("ia_consentimento", list(consentidos) + novos)
        if x.tipo not in armazem.BAIXAVEIS or self.midias is None:
            return
        caminho = self.midias.caminho(x)
        if not caminho:
            if self.banco.foi_limpa(x.conta_id, x.conversa_id, x.id):
                if not auto:
                    bipe("erro")
                    self.fala.falar(TEXTO_LIMPA, interromper=True)
                return
            self._ia_pendentes[x.chave] = (x, auto)
            if auto:
                self.midias.baixar(x, automatica=True)
            else:
                self.midias.baixar(x)
            if not auto:
                self.fala.falar("Baixando a mídia primeiro.",
                                interromper=True)
            return
        modelos = dict(self.cfg.get("ia_modelos") or {})
        perfil = self.cfg.get("ia_perfil") or "medio"
        chaves = {p: self.cofre_ia.obter(p)
                  for p in com_chave + com_chave_audio}
        self._ia_ocupadas.add(x.chave)
        if not auto:
            self.fala.falar("Enviando para %s. Aviso quando terminar." %
                            cat_ia.PROVEDORES[com_chave[0]].nome,
                            interromper=True)

        def trabalho():
            # as automaticas esperam a vez: um grupo cheio de audios nao
            # dispara dezenas de pedidos de uma vez
            if auto:
                self._ia_vagas.acquire()
            try:
                r, erro = servico_ia.executar_em_ordem(
                    genero, caminho, com_chave, chaves.get, modelos,
                    perfil, ordem_audio=com_chave_audio), None
            except ErroIA as e:
                r, erro = None, e.texto
            except Exception:
                log.exception("inteligência artificial")
                r, erro = None, "Algo deu errado ao falar com o provedor."
            finally:
                if auto:
                    self._ia_vagas.release()
            wx.CallAfter(self._ia_pronto, x, genero, r, erro, auto)
        threading.Thread(target=trabalho, daemon=True,
                         name="inteligencia-artificial").start()

    def _ia_pronto(self, x, genero, resultado, erro, auto=False):
        self._ia_ocupadas.discard(x.chave)
        if erro:
            if auto:
                # sem janela nem fala: chegou sem a pessoa pedir
                log.info("IA automática falhou: %s", erro)
                self.SetStatusText(("Não consegui %s: %s" % (
                    "transcrever" if genero == "audio" else "descrever",
                    erro))[:150])
                return
            bipe("erro")
            self.fala.falar(erro, interromper=True)
            wx.MessageBox(erro, NOME, wx.OK | wx.ICON_WARNING, self)
            return
        m.atualizar_extras(x, ia={
            "genero": genero, "texto": resultado.texto,
            "provedor": resultado.provedor, "modelo": resultado.modelo,
            "quando": time.time()})
        self.banco.salvar_mensagens([x])
        for i, y in enumerate(self.cache.get((x.conta_id, x.conversa_id),
                                             [])):
            if y.id == x.id:
                self.cache[(x.conta_id, x.conversa_id)][i] = x
        if self.atual == (x.conta_id, x.conversa_id):
            self._preencher_mensagens()
        # o texto inteiro, sem cortar: a linha da mensagem mostra so o comeco
        texto = resultado.texto
        if auto:
            conv = self.indice.get((x.conta_id, x.conversa_id))
            aberta = self.atual == (x.conta_id, x.conversa_id)
            onde = "" if aberta or conv is None else " em " + conv.nome
            aviso = "%s%s: %s" % (m.rotulo_da_ia(x).capitalize(), onde, texto)
            self.SetStatusText(aviso[:150])
            if not (conv is not None and self._conversa_muda(conv, aberta)):
                self.fala.falar(aviso)      # sem cortar o que esta falando
            return
        bipe("tarefa_pronta")
        if genero == "pdf":
            self._ia_ver(x)
            return
        self.fala.falar("%s: %s" % (m.rotulo_da_ia(x).capitalize(), texto),
                        interromper=True)

    # ---- transcricao e descricao automaticas, conversa por conversa
    def _ia_auto_ligada(self, chave):
        return list(chave) in (self.cfg.get("ia_automatica_conversas") or [])

    def _alternar_ia_auto(self, conv):
        lista = [k for k in (self.cfg.get("ia_automatica_conversas") or [])
                 if k != list(conv.chave)]
        ligar = not self._ia_auto_ligada(conv.chave)
        if ligar:
            lista.append(list(conv.chave))
        self.cfg.set("ia_automatica_conversas", lista)
        if not ligar:
            self.fala.falar("Transcrição e descrição automáticas desligadas "
                            "em %s." % conv.nome, interromper=True)
            return
        self.fala.falar(
            "Transcrição e descrição automáticas ligadas em %s. Valem para "
            "as mensagens que chegarem daqui para frente, conforme as "
            "opções de Configurações, Inteligência artificial." % conv.nome,
            interromper=True)
        if not self.cfg.get("ia_ordem"):
            self.fala.falar("Falta marcar os provedores e digitar a chave em "
                            "Configurações, Inteligência artificial.")

    def _ia_automatica(self, msg):
        """Mensagem recebida numa conversa com a IA automatica ligada."""
        if not self._ia_auto_ligada((msg.conta_id, msg.conversa_id)):
            return
        genero = self._genero_ia(msg)
        if genero == "audio" and not self.cfg.get("ia_auto_audio"):
            return
        if genero in ("imagem", "figurinha") and \
                not self.cfg.get("ia_auto_imagem"):
            return
        if genero not in ("audio", "imagem", "figurinha") or \
                m.extras_de(msg)["ia"].get("texto"):
            return
        self._ia_processar(msg, auto=True)

    def _ia_ver(self, x):
        """O texto feito pela IA, numa caixa de leitura com Copiar e Salvar."""
        ia = m.extras_de(x)["ia"]
        if not ia.get("texto"):
            self.fala.falar("Esta mensagem ainda não tem texto da "
                            "inteligência artificial.")
            return
        rotulo = m.rotulo_da_ia(x)
        dialogos.mostrar_depuracao(
            self, rotulo.capitalize(), ia["texto"] + "\n\n(%s, %s)" % (
                ia.get("provedor", ""), ia.get("modelo", "")),
            self._copiar_texto, self._salvar_texto_ia, rotulo.capitalize())

    def _salvar_texto_ia(self, texto):
        nome = time.strftime("telezapp_texto_%Y%m%d_%H%M%S.txt")
        dlg = wx.FileDialog(self, "Salvar o texto", defaultFile=nome,
                            wildcard="Texto|*.txt",
                            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            caminho = dlg.GetPath()
        finally:
            dlg.Destroy()
        try:
            with open(caminho, "w", encoding="utf-8-sig") as f:
                f.write(texto)
        except OSError:
            bipe("erro")
            self.fala.falar("Não consegui salvar o arquivo.")
            return
        self.fala.falar("Texto salvo.")

    def _entrar_no_grupo(self, x, acao, prov):
        """Botao "Entrar no grupo": mostra o que o convite diz e, se a pessoa
        confirmar, entra. As consultas ao servico rodam fora da janela."""
        self.fala.falar("Consultando o convite...", interromper=True)

        def trabalho():
            try:
                previa = prov.previa_do_convite(x, acao)
            except Exception:
                log.exception("prévia do convite")
                previa = {"erro": "Não consegui consultar o convite."}
            wx.CallAfter(self._confirmar_entrada, x, acao, prov, previa)
        threading.Thread(target=trabalho, daemon=True,
                         name="previa-convite").start()

    @seguro
    def _confirmar_entrada(self, x, acao, prov, previa):
        if previa.get("erro"):
            bipe("erro")
            self.fala.falar(previa["erro"], interromper=True)
            wx.MessageBox(previa["erro"], NOME, wx.OK | wx.ICON_WARNING, self)
            return
        if previa.get("ja_participa"):
            texto = "Você já está em %s." % previa["nome"]
            self.fala.falar(texto, interromper=True)
            wx.MessageBox(texto, NOME, wx.OK | wx.ICON_INFORMATION, self)
            return
        partes = ["Entrar em %s?" % previa["nome"]]
        if previa.get("membros"):
            partes.append("%d membros." % previa["membros"])
        if previa.get("descricao"):
            partes.append("Descrição: %s" % previa["descricao"])
        pergunta = " ".join(partes)
        self.fala.falar(pergunta, interromper=True)
        r = wx.MessageBox(pergunta, "Entrar", wx.YES_NO | wx.ICON_QUESTION,
                          self)
        if r != wx.YES:
            return
        self.fala.falar("Entrando...", interromper=True)

        def trabalho():
            try:
                ok, texto = prov.entrar_no_grupo(x, acao)
            except Exception:
                log.exception("entrar no grupo")
                ok, texto = False, "Não consegui entrar."
            wx.CallAfter(self._entrou_no_grupo, ok, texto, prov)
        threading.Thread(target=trabalho, daemon=True,
                         name="entrar-no-grupo").start()

    def _entrou_no_grupo(self, ok, texto, prov):
        bipe("tarefa_pronta" if ok else "erro")
        self.fala.falar(texto, interromper=True)
        wx.MessageBox(texto, NOME, wx.OK | (
            wx.ICON_INFORMATION if ok else wx.ICON_WARNING), self)
        if ok:
            try:
                prov.atualizar_conversas()
            except Exception:
                pass

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
        """Escolhe a conta (so se houver mais de uma conectada) e a pessoa e
        abre a conversa com ela, onde a mensagem se escreve e se envia como
        qualquer outra."""
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
        conta_id, destino, pessoa = escolha
        achado = pessoa or self._resolver_destino(conta_id, destino, nm)
        if achado is None:
            bipe("erro")
            self.fala.falar("Não encontrei %s. Use o nome de um contato ou "
                            "conversa, um telefone no formato internacional (como "
                            "+55 51 99999 8888) ou um @usuário."
                            % destino, interromper=True)
            return
        conversa_id, nome = achado
        conv = self._garantir_conversa(conta_id, conversa_id, nome)
        if self.atual is not None and self.atual != conv.chave:
            self._fechar_conversa()
        self._abrir_conversa(conv)
        self._mostrar_caixa()          # a mensagem se escreve na conversa

    @seguro
    def _nova_chamada(self):
        """Liga para alguem sem abrir uma conversa antes: escolhe a conta
        (so se houver mais de uma que ligue) e a pessoa."""
        from telezapp.interface import contatos
        from telezapp.nucleo import nova_mensagem as nm
        if self.chamada is not None and self.chamada.ativa:
            self.fala.falar("Já há uma chamada em andamento.",
                            interromper=True)
            self._mostrar_chamada()
            return
        contas = [(d["id"], "%s, %s" % (
            d.get("nome") or d.get("telefone") or d["id"],
            m.SERVICOS.get(d.get("servico"), "")))
            for d in self.cfg.contas()
            if self.estados.get(d["id"]) == ev.CONECTADA
            and self._provedor_de_chamada(d["id"]) is not None]
        if not contas:
            bipe("erro")
            self.fala.falar("Nenhuma conta conectada faz chamadas.",
                            interromper=True)
            return

        def buscar(conta_id, texto):
            return nm.candidatos(
                texto, self.banco.contatos(conta_id),
                [c for c in self.indice.values()
                 if c.conta_id == conta_id])
        escolha = contatos.dialogo_nova_chamada(self, contas, buscar)
        if escolha is None:
            return
        conta_id, destino, pessoa = escolha
        achado = pessoa or self._resolver_destino(conta_id, destino, nm)
        if achado is None:
            bipe("erro")
            self.fala.falar("Não encontrei %s. Use o nome de um contato ou "
                            "conversa, um telefone no formato internacional (como "
                            "+55 51 99999 8888) ou um @usuário."
                            % destino, interromper=True)
            return
        conversa_id, nome = achado
        self._ligar_para(self._garantir_conversa(conta_id, conversa_id, nome))

    @seguro
    def _novo_contato(self):
        from telezapp.interface import contatos
        achado = contatos.adicionar_contato(
            self, self.banco, _ContasParaContatos(self),
            lambda t: self.fala.falar(t, interromper=True))
        if achado is not None:
            self._renomear_pelos_contatos()
            self.fala.falar(achado[1], interromper=True)

    @seguro
    def _nova_conversa(self, tipo):
        """Novo grupo, canal ou comunidade: pergunta os dados e cria na conta
        escolhida; o servico responde fora da janela."""
        from telezapp.interface.criar_conversa import DialogoCriarConversa
        from telezapp.nucleo import criar_conversa as cc
        contas = []
        for dados in self.cfg.contas():
            p = self.contas.provedor(dados["id"]) if self.contas else None
            if p is not None and tipo in getattr(p, "CRIA", ()) and \
                    self.estados.get(dados["id"]) == ev.CONECTADA:
                servico = self.contas.servico(dados["id"])
                contas.append((dados["id"], "%s, %s" % (
                    dados.get("nome") or dados.get("telefone") or dados["id"],
                    m.SERVICOS.get(servico, servico)), servico))
        if not contas:
            bipe("erro")
            self.fala.falar("Nenhuma conta conectada cria %s." %
                            cc.NOMES[tipo][1], interromper=True)
            return
        dlg = DialogoCriarConversa(self, tipo, contas)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            conta_id, nome, descricao, gente, topicos = dlg.escolhido()
        finally:
            dlg.Destroy()
        prov = self.contas.provedor(conta_id)
        if prov is None:
            return
        self.fala.falar("Criando. Aviso quando terminar.", interromper=True)

        def trabalho():
            try:
                ok, texto, cid = prov.criar_conversa(
                    tipo, nome, descricao, gente, topicos)
            except Exception:
                log.exception("criar %s", tipo)
                ok, texto, cid = False, "Não consegui criar.", ""
            wx.CallAfter(self._conversa_criada, conta_id, tipo, nome, ok,
                         texto, cid)
        threading.Thread(target=trabalho, daemon=True,
                         name="criar-conversa").start()

    @seguro
    def _conversa_criada(self, conta_id, tipo, nome, ok, texto, cid):
        from telezapp.nucleo import criar_conversa as cc
        if not ok:
            bipe("erro")
            self.fala.falar(texto, interromper=True)
            wx.MessageBox(texto, NOME, wx.OK | wx.ICON_WARNING, self)
            return
        bipe("tarefa_pronta")
        self.fala.falar(" ".join((cc.texto_pronto(tipo, nome), texto)).strip(),
                        interromper=True)
        conv = self.indice.get((conta_id, cid)) if cid else None
        if conv is not None:
            self._abrir_conversa_de(conv)

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
        if x is None or x.id.startswith("local-") or self._somente_leitura():
            return
        self.resposta_a = x
        autor = "você" if x.minha else (x.autor or "mensagem")
        self._rotular_caixa(autor)
        self.fala.falar("Respondendo a %s. Esc cancela a resposta." % autor)
        self._mostrar_caixa()

    def _pode_responder_em_particular(self, x):
        """Mensagem de outra pessoa num grupo, de um servico que sabe achar
        o telefone dela."""
        conv = self.indice.get((x.conta_id, x.conversa_id))
        prov = self.contas.provedor(x.conta_id) if self.contas else None
        return bool(conv is not None and conv.tipo == "grupo" and
                    not x.minha and x.remetente and prov is not None
                    and prov.pessoa_da_mensagem(x) is not None
                    and not x.id.startswith("local-"))

    def _responder_em_particular(self, x=None):
        """Abre a conversa particular com quem enviou a mensagem do grupo e
        deixa a resposta pronta, citando essa mensagem."""
        if x is None:
            x = self._mensagem_selecionada()
        if x is None:
            self.fala.falar("Selecione uma mensagem.")
            return
        if not self._pode_responder_em_particular(x):
            self.fala.falar("Só dá para responder em particular a uma "
                            "mensagem de outra pessoa num grupo.")
            return
        prov = self.contas.provedor(x.conta_id)
        id_, telefone, _ = prov.pessoa_da_mensagem(x)
        chave = (x.conta_id, id_)
        conv = self.indice.get(chave)
        if conv is None:
            nome = self.banco.nome_de_contato(x.conta_id, id_) or (
                x.autor if x.autor and not x.autor.startswith("+") else
                telefone)
            conv = m.Conversa(x.conta_id, id_, nome,
                              self.contas.servico(x.conta_id), "privada",
                              data=time.time())
            self.indice[chave] = conv
            self._ordenar()
            self._preencher_conversas()
        if self.atual is not None:
            self._fechar_conversa()
        self._abrir_conversa(conv)
        self.resposta_a = x
        autor = x.autor or conv.nome or "mensagem"
        self._rotular_caixa(autor)
        self.fala.falar("Respondendo em particular a %s, na conversa com "
                        "%s. Esc cancela a resposta." % (autor, conv.nome),
                        interromper=True)
        self._mostrar_caixa()

    def _rotular_caixa(self, autor=None):
        """Rotulo da caixa de digitar: diz se e resposta e quantas midias
        coladas esperam o Enter."""
        if self.resposta_a is not None and autor is None:
            autor = "você" if self.resposta_a.minha else (
                self.resposta_a.autor or "mensagem")
        texto = ("Respondendo a %s. Digite sua resposta" % autor) \
            if autor else "Digite sua mensagem"
        if self.editando is not None:
            texto = "Editando sua mensagem. %s salva e Esc cancela" % \
                self._tecla_de_enviar()
        if self.anexos:
            texto += ". %s, o texto vira legenda" % colagem.descricao(
                self.anexos)
        self.rot_caixa.SetLabel(texto)

    def _pode_editar(self, x):
        """Mensagem de texto minha, ainda dentro do prazo que o servico dá."""
        prov = self.contas.provedor(x.conta_id) if self.contas else None
        prazo = getattr(prov, "JANELA_EDICAO", 0) if prov else 0
        return bool(prazo and x.minha and x.tipo == m.TEXTO and x.texto and
                    not x.id.startswith("local-") and
                    not m.extras_de(x)["apagada"] and
                    self.estados.get(x.conta_id) == ev.CONECTADA and
                    time.time() - x.data <= prazo)

    def _editar_mensagem(self, x=None):
        """Poe o texto da mensagem na caixa para ser editado; Enter manda a
        edicao e Esc cancela."""
        if x is None:
            x = self._mensagem_selecionada()
        if x is None:
            self.fala.falar("Selecione uma mensagem.")
            return
        if not self._pode_editar(x):
            bipe("erro")
            self.fala.falar(
                "Só dá para editar mensagens de texto suas, enviadas há "
                "pouco tempo (15 minutos no WhatsApp, 48 horas no "
                "Telegram), com a conta conectada.", interromper=True)
            return
        if self._somente_leitura():
            return
        if self.editando is None:
            self._rascunho_da_edicao = self.caixa.GetValue()
        self.editando = x
        self.caixa.SetValue(x.texto)
        self._rotular_caixa()
        self.fala.falar("Editando a mensagem. %s salva, Esc cancela." %
                        self._tecla_de_enviar(), interromper=True)
        self.caixa.SetFocus()
        self.caixa.SetInsertionPointEnd()

    def _reagir(self, x=None):
        """Reage a mensagem selecionada: uma lista curta de emojis, com
        "Outro emoji..." para a busca completa e "Tirar a minha reação"."""
        if x is None:
            x = self._mensagem_selecionada()
        if x is None:
            self.fala.falar("Selecione uma mensagem.")
            return
        prov = self.contas.provedor(x.conta_id) if self.contas else None
        if prov is None or not getattr(prov, "PODE_REAGIR", False):
            self.fala.falar("Este serviço não aceita reações.")
            return
        if x.id.startswith("local-") or m.extras_de(x)["apagada"]:
            bipe("erro")
            self.fala.falar("Não dá para reagir a esta mensagem.",
                            interromper=True)
            return
        if self.estados.get(x.conta_id) != ev.CONECTADA:
            bipe("erro")
            self.fala.falar("A conta não está conectada.", interromper=True)
            return
        atual = m.minha_reacao(x)
        escolha = ui_emojis.escolher_reacao(self, atual)
        if escolha == ui_emojis.OUTRO:
            escolha = ui_emojis.escolher_emoji(self, "Reagir com outro emoji")
        if not escolha:
            return
        if escolha == ui_emojis.TIRAR:
            escolha = ""
        elif escolha == atual:
            self.fala.falar("Você já reagiu com este emoji.")
            return
        prov.reagir(x, escolha)
        self.fala.falar("Reação removida." if not escolha else
                        "Reagindo com %s." % emoji_falado(escolha),
                        interromper=True)

    def _inserir_emoji(self):
        """Escolhe um emoji pelo nome e o poe na caixa de digitar."""
        if self.atual is None:
            self.fala.falar(TEXTO_SEM_CONVERSA)
            return
        if self._somente_leitura():
            return
        simbolo = ui_emojis.escolher_emoji(self)
        self.caixa.SetFocus()
        if not simbolo:
            return
        self.caixa.WriteText(simbolo)
        self.fala.falar("Emoji inserido: %s." % emoji_falado(simbolo),
                        interromper=True)

    def _corretor(self):
        """O corretor do idioma escolhido; None (com aviso) se o Windows
        nao tiver o dicionario."""
        idioma = self.cfg.get("ortografia_idioma") or "pt-BR"
        if getattr(self, "_corretor_ort", None) is None or                 self._corretor_ort.idioma != idioma:
            self._corretor_ort = ortografia.Corretor(idioma)
        if not self._corretor_ort.disponivel:
            bipe("erro")
            self.fala.falar(
                "O Windows não tem o dicionário %s. Instale o idioma em "
                "Configurações do Windows, Hora e idioma, ou escolha outro "
                "idioma do corretor nas configurações do TeleZapp." % idioma,
                interromper=True)
            return None
        return self._corretor_ort

    def _verificar_ortografia(self, ao_enviar=False):
        """Percorre os erros do texto da caixa. Devolve True se terminou a
        revisao (sem erro sobrando ou com todos tratados)."""
        if self.atual is None:
            self.fala.falar(TEXTO_SEM_CONVERSA)
            return False
        texto = self.caixa.GetValue()
        if not texto.strip():
            self.fala.falar("A caixa de digitar está vazia.",
                            interromper=True)
            return False
        corretor = self._corretor()
        if corretor is None:
            return False
        novo, mudou, fim = ui_ortografia.revisar(
            self, corretor, texto, self.fala.falar)
        if mudou:
            self.caixa.SetValue(novo)
            self.caixa.SetInsertionPointEnd()
        self.caixa.SetFocus()
        if fim and not ao_enviar:
            self.fala.falar("Ortografia verificada." if mudou or novo != texto
                            else "Nenhum erro de ortografia.",
                            interromper=True)
        return fim

    def _checar_antes_de_enviar(self, texto):
        """True se pode enviar. Com a opcao ligada e palavras com erro,
        pergunta se corrige antes ou envia assim mesmo."""
        if not self.cfg.get("ortografia_ao_enviar"):
            return True
        corretor = getattr(self, "_corretor_ort", None)
        idioma = self.cfg.get("ortografia_idioma") or "pt-BR"
        if corretor is None or corretor.idioma != idioma:
            corretor = self._corretor_ort = ortografia.Corretor(idioma)
        erros = corretor.verificar(texto) if corretor.disponivel else []
        if not erros:
            return True
        dlg = wx.MessageDialog(
            self, "O corretor achou %d palavra%s que pode estar errada: %s. "
            "Corrigir antes de enviar?" % (
                len(erros), "" if len(erros) == 1 else "s",
                ", ".join(e.palavra for e in erros[:5])),
            "Ortografia", wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION)
        dlg.SetYesNoCancelLabels("&Corrigir", "&Enviar assim mesmo",
                                 "Ca&ncelar")
        try:
            r = dlg.ShowModal()
        finally:
            dlg.Destroy()
        if r == wx.ID_NO:
            return True
        if r == wx.ID_YES:
            self._verificar_ortografia(ao_enviar=True)
        self.caixa.SetFocus()
        return False

    def _cancelar_edicao(self, falar=True):
        if self.editando is None:
            return
        self.editando = None
        self.caixa.SetValue(self._rascunho_da_edicao)
        self._rascunho_da_edicao = ""
        self._rotular_caixa()
        if falar:
            self.fala.falar("Edição cancelada.")

    def _salvar_edicao(self):
        x = self.editando
        texto = self.caixa.GetValue().strip()
        if not texto:
            bipe("erro")
            self.fala.falar("A mensagem não pode ficar vazia. Para apagar, "
                            "use Apagar mensagem.", interromper=True)
            return
        if texto == x.texto:
            self._cancelar_edicao(falar=False)
            self.fala.falar("Nada mudou.", interromper=True)
            return
        if not self._pode_editar(x):
            self._cancelar_edicao(falar=False)
            bipe("erro")
            self.fala.falar("Já não dá mais para editar esta mensagem.",
                            interromper=True)
            return
        prov = self.contas.provedor(x.conta_id)
        self._cancelar_edicao(falar=False)
        prov.editar_mensagem(x, texto)
        self.fala.falar("Salvando a edição.", interromper=True)
        self.lista_msgs.SetFocus()

    def _cancelar_resposta(self):
        self.resposta_a = None
        self._rotular_caixa()
        self.fala.falar("Resposta cancelada.")

    def _copiar(self):
        x = self._mensagem_selecionada()
        if x is None:
            return
        self._copiar_texto(x.texto or m.conteudo(x))

    def _copiar_conteudo(self, x, tipo, valor):
        """Um item "Copiar ..." do menu da mensagem: o texto, o endereco ou o
        arquivo da midia (que precisa estar baixada)."""
        if m.extras_de(x)["apagada"]:
            self._avisar_apagado("A mensagem foi apagada. Não há conteúdo "
                                 "para copiar.")
            return
        if tipo != "midia":
            self._copiar_texto(valor)
            return
        if self.midias is None or x.id.startswith("local-"):
            return
        if self.banco.foi_limpa(x.conta_id, x.conversa_id, x.id):
            self._avisar_apagado("O conteúdo foi apagado. " + TEXTO_LIMPA)
            return
        caminho = self.midias.caminho(x)
        if not caminho:
            bipe("erro")
            self.fala.falar(
                "Esta mídia ainda não foi baixada. Aperte Enter na mensagem "
                "para baixar e depois copie.", interromper=True)
            return
        dados = wx.DataObjectComposite()
        arquivos = wx.FileDataObject()
        arquivos.AddFile(caminho)
        dados.Add(arquivos, True)
        if x.tipo == m.FOTO:
            img = wx.Image()
            with wx.LogNull():
                ok = img.LoadFile(caminho)
            if ok:
                imagem = wx.BitmapDataObject(wx.Bitmap(img))
                dados.Add(imagem)
        if wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(dados)
            finally:
                wx.TheClipboard.Close()
            self.fala.falar("Mídia copiada.")
        else:
            bipe("erro")
            self.fala.falar("Não consegui usar a área de transferência.")

    def _avisar_apagado(self, texto):
        bipe("erro")
        self.fala.falar(texto, interromper=True)
        wx.MessageBox(texto, NOME, wx.OK | wx.ICON_INFORMATION, self)

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

    def _pode_bloquear(self, conta_id):
        prov = self.contas.provedor(conta_id) if self.contas else None
        return bool(prov is not None and getattr(prov, "PODE_BLOQUEAR", False))

    def _bloquear_pessoa(self, conv=None):
        """Bloqueia a pessoa da conversa (ou desbloqueia, se ja esta
        bloqueada), depois de perguntar."""
        from telezapp.interface import bloqueados
        if conv is None:
            conv = self._conversa_privada_em_foco()
        if conv is None or conv.tipo != "privada":
            self.fala.falar("Selecione uma conversa com uma pessoa.")
            return
        if not self._pode_bloquear(conv.conta_id):
            self.fala.falar("Esta conta não bloqueia pessoas por aqui.")
            return
        bloqueados.alternar(
            self, self.contas.provedor(conv.conta_id), conv.id, conv.nome,
            lambda t: self.fala.falar(t, interromper=True))

    def _pessoa_para_bloquear(self):
        """Escolhe a conta (so se houver mais de uma que bloqueie) e a pessoa.
        Devolve (conta_id, conversa_id, nome) ou None."""
        from telezapp.interface import contatos
        from telezapp.nucleo import nova_mensagem as nm
        contas = [(d["id"], "%s, %s" % (
            d.get("nome") or d.get("telefone") or d["id"],
            m.SERVICOS.get(d.get("servico"), "")))
            for d in self.cfg.contas()
            if self.estados.get(d["id"]) == ev.CONECTADA
            and self._pode_bloquear(d["id"])]
        if not contas:
            bipe("erro")
            self.fala.falar("Nenhuma conta conectada bloqueia pessoas.",
                            interromper=True)
            return None

        def buscar(conta_id, texto):
            return [c for c in nm.candidatos(
                texto, self.banco.contatos(conta_id),
                [c for c in self.indice.values()
                 if c.conta_id == conta_id and c.tipo == "privada"])]
        escolha = contatos.dialogo_nova_mensagem(
            self, contas, buscar, "Bloquear contato")
        if escolha is None:
            return None
        conta_id, destino, pessoa = escolha
        achado = pessoa or self._resolver_destino(conta_id, destino, nm)
        if achado is None:
            bipe("erro")
            self.fala.falar("Não encontrei %s. Use o nome de um contato ou "
                            "conversa, um telefone no formato internacional "
                            "(como +55 51 99999 8888) ou um @usuário."
                            % destino, interromper=True)
            return None
        return conta_id, achado[0], achado[1]

    # ============================================================= perfil
    @seguro
    def _editar_perfil(self):
        """Escolhe a conta (so se houver mais de uma que edite o perfil), le
        o perfil dela e abre a janela de edicao."""
        contas = [(d["id"], "%s, %s" % (
            d.get("nome") or d.get("telefone") or d["id"],
            m.SERVICOS.get(d.get("servico"), "")))
            for d in self.cfg.contas()
            if self.estados.get(d["id"]) == ev.CONECTADA
            and getattr(self.contas.provedor(d["id"]), "PODE_EDITAR_PERFIL",
                        False)]
        if not contas:
            bipe("erro")
            self.fala.falar("Nenhuma conta conectada edita o perfil.",
                            interromper=True)
            return
        conta_id = contas[0][0]
        if len(contas) > 1:
            dlg = wx.SingleChoiceDialog(
                self, "De qual conta é o perfil?", "Editar o meu perfil",
                [r for _, r in contas])
            try:
                if dlg.ShowModal() != wx.ID_OK:
                    return
                conta_id = contas[dlg.GetSelection()][0]
            finally:
                dlg.Destroy()
        prov = self.contas.provedor(conta_id)

        def ler():
            try:
                atual, erro = prov.meu_perfil(), ""
            except ErroPerfil as e:
                atual, erro = None, str(e)
            except Exception:
                log.exception("ler o perfil")
                atual, erro = None, "Não consegui ler o seu perfil."
            wx.CallAfter(self._perfil_lido, conta_id, atual, erro)
        self.fala.falar("Lendo o seu perfil.", interromper=True)
        threading.Thread(target=ler, daemon=True, name="ler-perfil").start()

    @seguro
    def _perfil_lido(self, conta_id, atual, erro):
        from telezapp.interface import perfil as janela_perfil
        from telezapp.nucleo import perfil as np_
        if atual is None:
            bipe("erro")
            self.fala.falar(erro, interromper=True)
            wx.MessageBox(erro, NOME, wx.OK | wx.ICON_WARNING, self)
            return
        prov = self.contas.provedor(conta_id)
        servico = self.contas.servico(conta_id)
        valores, foto, nome_da_foto = dict(atual), None, ""
        while True:
            dlg = janela_perfil.DialogoPerfil(
                self, "Editar o meu perfil, %s" % m.SERVICOS.get(servico, ""),
                servico, valores, prov.PERFIL_SOBRENOME, foto, nome_da_foto)
            try:
                if dlg.ShowModal() != wx.ID_OK:
                    return
                novos = dlg.valores()
                foto, nome_da_foto = dlg.foto, dlg.nome_da_foto
            finally:
                dlg.Destroy()
            mudadas = np_.mudancas(atual, novos)
            problema = np_.validar(servico, mudadas)
            if not problema:
                break
            bipe("erro")
            self.fala.falar(problema, interromper=True)
            wx.MessageBox(problema, "Editar o meu perfil",
                          wx.OK | wx.ICON_WARNING, self)
            valores = novos             # reabre com o que ela digitou
        if not mudadas and not foto:
            self.fala.falar("Nada mudou no perfil.", interromper=True)
            return

        def gravar():
            try:
                feitos, erros = prov.salvar_perfil(mudadas, foto)
                texto = np_.resumo(feitos, erros)
            except ErroPerfil as e:
                feitos, erros, texto = [], [("", str(e))], str(e)
            except Exception:
                log.exception("salvar o perfil")
                feitos, erros = [], [("", "")]
                texto = "Não consegui salvar o perfil."
            wx.CallAfter(self._perfil_salvo, texto, bool(erros))
        self.fala.falar("Salvando o perfil.", interromper=True)
        threading.Thread(target=gravar, daemon=True,
                         name="salvar-perfil").start()

    @seguro
    def _perfil_salvo(self, texto, com_erro):
        bipe("erro" if com_erro else "tarefa_pronta")
        self.fala.falar(texto, interromper=True)
        if com_erro:
            wx.MessageBox(texto, "Editar o meu perfil",
                          wx.OK | wx.ICON_WARNING, self)

    def _contatos_bloqueados(self):
        from telezapp.interface import bloqueados
        dlg = bloqueados.GerenciadorBloqueados(
            self, _ContasParaContatos(self), self._pessoa_para_bloquear,
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

    def _nome_do_remetente(self, x):
        """Nome que a agenda ou as mensagens guardadas dao a quem enviou."""
        nome = self.banco.nome_de_contato(x.conta_id, x.remetente) or \
            self.banco.nome_do_remetente(x.conta_id, [x.remetente])
        if nome or not self.contas:
            return nome
        # o servico ainda pode saber (agenda, outro endereco da pessoa)
        prov = self.contas.provedor(x.conta_id)
        try:
            return prov.nome_de_participante(x.remetente) if prov else ""
        except Exception:
            return ""

    def _quem_enviou(self, x):
        """Quem enviou a mensagem, para a lista e a fala; so vale a pena
        quando ela nao traz o autor (por isso "" nos outros casos)."""
        if x.minha or x.autor:
            return ""
        chave = (x.conta_id, x.conversa_id, x.remetente)
        if chave not in self._quem_cache:
            self._quem_cache[chave] = m.quem_enviou(
                x, self.indice.get((x.conta_id, x.conversa_id)),
                self._nome_do_remetente)
        return self._quem_cache[chave]

    def _salvar_conversa(self, conv=None):
        """Salva num .zip o texto das mensagens guardadas e as midias ja
        baixadas da conversa (a do foco na lista ou a aberta)."""
        if conv is None:
            conv = self._conversa_selecionada()                 if self.FindFocus() is self.lista_conv else None
            if conv is None and self.atual is not None:
                conv = self.indice.get(self.atual)
            if conv is None:
                conv = self._conversa_selecionada()
        if conv is None:
            self.fala.falar("Selecione uma conversa.")
            return
        caminho = dialogos.escolher_destino_zip(
            self, exportar.nome_sugerido(conv),
            self.cfg.get("pasta_exportar") or "")
        if not caminho:
            return
        self.cfg.set("pasta_exportar", os.path.dirname(caminho))
        mensagens = self.banco.mensagens(conv.conta_id, conv.id, 10 ** 9)

        def da_midia(x):
            if x.tipo not in armazem.BAIXAVEIS or                     self.banco.foi_limpa(x.conta_id, x.conversa_id, x.id):
                return None
            reg = self.banco.midia(x.conta_id, x.conversa_id, x.id)
            return reg[0] if reg else None

        def trabalho():
            try:
                n, midias = exportar.gravar_zip(
                    caminho, conv, mensagens, da_midia,
                    nome_do_remetente=self._nome_do_remetente)
                texto = ("Conversa salva: %d mensagens e %d mídias em %s."
                         % (n, midias, caminho))
                grave = False
            except Exception as e:
                log.error("erro ao salvar a conversa:\n%s",
                          traceback.format_exc())
                texto = "Não consegui salvar a conversa: %s" % e
                grave = True
            wx.CallAfter(self._conversa_salva, texto, grave)
        self.fala.falar("Salvando %d mensagens da conversa com %s. Aviso "
                        "quando terminar." % (len(mensagens), conv.nome),
                        interromper=True)
        threading.Thread(target=trabalho, daemon=True).start()

    def _conversa_salva(self, texto, grave):
        bipe("erro" if grave else "tarefa_pronta")
        self.fala.falar(texto, interromper=True)
        if grave:
            wx.MessageBox(texto, NOME, wx.OK | wx.ICON_WARNING, self)

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
        contatos.avisar_conta(
            self.contas.provedor(conv.conta_id), conv.id, nome,
            telefone or base, lambda t: self.fala.falar(t))

    def _salvar_autor(self, x=None):
        """Salva como contato quem enviou a mensagem (a de um grupo, por
        exemplo): o nome vale nas mensagens dela e, no WhatsApp, a conta
        tambem passa a reconhece-lo."""
        from telezapp.interface import contatos
        if x is None:
            x = self._mensagem_selecionada()
        if x is None:
            self.fala.falar("Selecione uma mensagem.")
            return
        prov = self.contas.provedor(x.conta_id) if self.contas else None
        pessoa = prov.pessoa_da_mensagem(x) if prov is not None else None
        if pessoa is None:
            self.fala.falar("Não achei o telefone de quem enviou esta "
                            "mensagem.")
            return
        id_, telefone, ids = pessoa
        nome = self.banco.nome_de_contato(x.conta_id, id_) or (
            x.autor if x.autor and not x.autor.startswith("+") else "")
        servico = m.SERVICOS.get(self.contas.servico(x.conta_id), "")
        escolha = contatos.dialogo_salvar_pessoa(
            self, [(x.conta_id, servico)], nome, telefone)
        if escolha is None:
            return
        nome, tel = escolha
        tel = tel or telefone
        self.banco.salvar_contato(x.conta_id, id_, nome, tel)
        self.banco.renomear_autor(x.conta_id, ids, nome)
        for lista in self.cache.values():
            for y in lista:
                if y.conta_id == x.conta_id and not y.minha and \
                        y.remetente in ids:
                    y.autor = nome
        self._renomear_pelos_contatos()
        if self.atual:
            self._preencher_mensagens()
        self.fala.falar("Contato %s salvo." % nome, interromper=True)
        contatos.avisar_conta(prov, id_, nome, tel,
                              lambda t: self.fala.falar(t))

    def _renomear_pelos_contatos(self):
        """Poe nas conversas com pessoas o nome da agenda e, onde a pessoa
        removeu o contato, pede os nomes de novo ao servico."""
        self._quem_cache.clear()
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
        self.fala.falar(m.formatar(msgs[-1], m.ESTILO_AUTOR_PRIMEIRO,
                                   quem=self._quem_enviou(msgs[-1])),
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
                motivo = self._motivo_do_original_ausente(x)
                self.fala.falar(
                    "A mensagem original foi %s." % (
                        "limpa deste computador"
                        if "limpa" in motivo else
                        "apagada deste computador junto com a conversa")
                    if motivo else
                    "A mensagem original não está guardada no TeleZapp.")
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

    def _opcoes_da_conversa(self, conv, com_abrir=True, com_detalhes=True):
        """Os itens do menu de contexto de uma conversa: [(rotulo, funcao)].
        Valem na lista principal e nas listas da janela de detalhes."""
        opcoes = []
        if com_abrir:
            opcoes.append(("Abrir", lambda: self._abrir_conversa_de(conv)))
        if conv.tipo == "status":
            # status: so abrir e apagar daqui (nao ha detalhes nem ajustes)
            opcoes.append(("Apagar status...",
                           lambda: self._apagar_conversa(conv)))
            return opcoes
        if com_detalhes:
            opcoes.append(({"grupo": "Detalhes do grupo",
                            "canal": "Detalhes do canal"}.get(
                                conv.tipo, "Detalhes da conversa"),
                           lambda: self._detalhes_da_conversa(conv)))
        opcoes.append(("Desarquivar" if conv.arquivada else "Arquivar",
                       lambda: self._arquivar_conversa(conv)))
        opcoes.append(("Desafixar" if conv.fixada else "Fixar",
                       lambda: self._fixar_conversa(conv)))
        opcoes.append(("Reativar o som" if conv.silenciada() else "Silenciar",
                       lambda: self._silenciar_conversa(conv)))
        opcoes.append(("Destrancar" if conv.trancada else "Trancar",
                       lambda: self._trancar_conversa(conv)))
        opcoes.append(("Salvar o conteúdo da conversa...",
                       lambda: self._salvar_conversa(conv)))
        opcoes.append((
            "Desligar a transcrição e descrição automáticas"
            if self._ia_auto_ligada(conv.chave) else
            "Ligar a transcrição e descrição automáticas",
            lambda: self._alternar_ia_auto(conv)))
        opcoes.append(("Apagar conversa...",
                       lambda: self._apagar_conversa(conv)))
        if conv.tipo == "privada":
            opcoes.append(("Salvar como contato...",
                           lambda: self._salvar_pessoa(conv)))
            if self._pode_bloquear(conv.conta_id):
                opcoes.append(("Bloquear ou desbloquear...",
                               lambda: self._bloquear_pessoa(conv)))
        if self.cfg.get("depuracao"):
            opcoes.append(("Depurar conversa",
                           lambda: self._depurar_conversa(conv)))
        return opcoes

    def _garantir_conversa(self, conta_id, id_, nome, tipo="privada"):
        """A conversa com esse id; se ainda nao existe, cria uma vazia na
        lista (como ao abrir a conversa de uma pessoa mencionada)."""
        chave = (conta_id, id_)
        conv = self.indice.get(chave)
        if conv is None:
            conv = m.Conversa(
                conta_id, id_, self.banco.nome_de_contato(conta_id, id_)
                or nome or id_, self.contas.servico(conta_id), tipo,
                data=time.time())
            self.indice[chave] = conv
            self._ordenar()
            self._preencher_conversas()
        return conv

    def _abrir_conversa_de(self, conv):
        """Abre a conversa vinda de outra janela (detalhes, membros...)."""
        if self.atual is not None and self.atual != conv.chave:
            self._fechar_conversa()
        self._abrir_conversa(conv)
        self.fala.falar("Conversa com %s." % conv.nome, interromper=True)

    def _ver_na_conversa(self, x):
        """Abre a conversa da mensagem e leva a selecao ate ela."""
        conv = self.indice.get((x.conta_id, x.conversa_id))
        if conv is None:
            self.fala.falar("Esta conversa não está mais na lista.")
            return
        if self.atual != conv.chave:
            self.banco.salvar_posicao(x.conta_id, x.conversa_id, x.id)
            self._abrir_conversa_de(conv)
        wx.CallLater(900, lambda: self._selecionar_mensagem(x))

    def _selecionar_mensagem(self, x):
        if self.atual != (x.conta_id, x.conversa_id):
            return
        if x.id not in self.mapa:
            o = self.banco.mensagem(x.conta_id, x.conversa_id, x.id)
            if o is None:
                self.fala.falar("Esta mensagem não está mais guardada.")
                return
            self._mesclar(self.atual, [o])
            self._preencher_mensagens(x.id)
        if x.id in self.mapa:
            self.selecao_automatica = False
            self.lista_msgs.SetSelection(self.mapa.index(x.id))
            self.lista_msgs.SetFocus()

    def _abrir_endereco(self, url):
        if dialogos.abrir_link(url):
            self.fala.falar("Abrindo no navegador.", interromper=True)
        else:
            self.fala.falar("Não consegui abrir o link.", interromper=True)

    def _salvar_copia_de(self, x):
        caminho = self.midias.caminho(x) if self.midias else None
        if not caminho:
            self.fala.falar("Baixe a mídia antes: Abrir baixa e mostra.")
            return
        visualizadores.salvar_copia(self, x, caminho, self.fala)

    @seguro
    def _detalhes_da_conversa(self, conv=None):
        """Detalhes da conversa em foco (ou da dada): pessoa, grupo ou canal,
        com midias, membros, grupos em comum e administracao."""
        conv = conv or self._conversa_em_foco()
        if conv is None:
            self.fala.falar("Nenhuma conversa selecionada.")
            return
        ControleDetalhes(self, conv).abrir()

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
        if self.modo_conv and self._marcadas_conv():
            self._menu_em_massa(lista, pos, self._opcoes_em_massa_conv())
            return
        opcoes = self._opcoes_da_conversa(conv)
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
        if self.modo_msg and self._marcadas_msg():
            self._menu_em_massa(self.lista_msgs, evt.GetPosition(),
                                self._opcoes_em_massa_msg())
            return
        menu = wx.Menu()
        sel = self._mensagem_selecionada()
        opcoes = [("Responder", self._responder),
                  ("Reagir...", self._reagir)]
        if self._pode_editar(sel):
            opcoes.append(("Editar mensagem", self._editar_mensagem))
        if self._pode_responder_em_particular(sel):
            opcoes.append(("Responder em particular",
                           self._responder_em_particular))
        opcoes += [(rotulo, lambda t=tipo, v=valor: self._copiar_conteudo(
            sel, t, v)) for tipo, rotulo, valor in m.conteudos_copiaveis(
                sel, MAX_BOTOES_LINK)]
        opcoes += [("Encaminhar...", self._encaminhar),
                   ("Detalhes", self._detalhes),
                   ("Apagar mensagem...", self._apagar_mensagem)]
        opcoes.insert(0, ("Desfavoritar" if m.extras_de(sel)["favorita"]
                          else "Favoritar", self._favoritar_mensagem))
        if not sel.minha and sel.remetente:
            opcoes.append(("Salvar quem enviou como contato...",
                           self._salvar_autor))
        if self._mensagem_selecionada().resposta_a:
            opcoes.insert(1, ("Ir para a mensagem respondida",
                              self._ir_para_respondida))
        # transcrever/descrever e o primeiro item do menu; depois, abrir ou
        # reproduzir a midia (o Enter pode estar configurado para a IA)
        opcoes[0:0] = self._opcoes_ia(sel) + self._opcoes_midia(sel)
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
    def _postar_status(self):
        """Janela para publicar um status (WhatsApp) ou uma historia
        (Telegram) na conta escolhida."""
        contas = []
        for dados in self.cfg.contas():
            p = self.contas.provedor(dados["id"]) if self.contas else None
            if p is not None and getattr(p, "PODE_PUBLICAR_STATUS", False) \
                    and self.estados.get(dados["id"]) == ev.CONECTADA:
                servico = self.contas.servico(dados["id"])
                contas.append((dados["id"], "%s, %s" % (
                    dados.get("nome") or dados.get("telefone") or dados["id"],
                    m.SERVICOS.get(servico, servico)), servico))
        if not contas:
            bipe("erro")
            self.fala.falar("Nenhuma conta conectada publica status.",
                            interromper=True)
            return
        dlg = DialogoPublicarStatus(self, contas, self._escolher_midia_status)
        try:
            if dlg.ShowModal() != wx.ID_OK or dlg.resultado is None:
                return
            r = dlg.resultado
        finally:
            dlg.Destroy()
        p = self.contas.provedor(r["conta_id"])
        if p is None:
            return
        p.publicar_status(r["texto"], r["anexo"], r["publico"])
        self.fala.falar("Publicando. Aviso quando terminar.",
                        interromper=True)

    def _escolher_midia_status(self, pai):
        return dialogos.escolher_arquivo(
            pai, self.cfg.get("pasta_anexos") or "")

    def _conversa_de_status(self):
        conv = self.indice.get(self.atual) if self.atual else None
        return conv is not None and conv.tipo == "status"

    def _responder_ao_status(self):
        """Na conversa de status, o texto da caixa responde em particular ao
        status selecionado."""
        x = self._mensagem_selecionada()
        texto = self.caixa.GetValue().strip()
        prov = self.contas.provedor(x.conta_id) if x is not None else None
        if x is None or x.minha or prov is None:
            bipe("erro")
            self.fala.falar("Selecione o status de alguém para responder.",
                            interromper=True)
            return
        if not texto:
            bipe("erro")
            return
        if self.estados.get(x.conta_id) != ev.CONECTADA:
            bipe("erro")
            self.fala.falar("A conta não está conectada. A resposta não foi "
                            "enviada.", interromper=True)
            return
        prov.responder_status(x, texto)
        self.caixa.Clear()
        self.fala.falar("Resposta enviada a %s." % (x.autor or "quem postou"),
                        interromper=True)

    def _enviar_texto(self):
        if self.atual is None:
            bipe("erro")
            self.fala.falar(TEXTO_SEM_CONVERSA)
            return
        if self._somente_leitura():
            return
        if self._conversa_de_status():
            self._responder_ao_status()
            return
        if self.editando is not None:
            self._salvar_edicao()
            return
        if self.anexos:
            self._enviar_anexos()
            return
        texto = self.caixa.GetValue().strip()
        if not texto:
            bipe("erro")
            return
        if not self._checar_antes_de_enviar(texto):
            return
        texto = self.caixa.GetValue().strip()
        conta_id, conversa_id = self.atual
        p = self.contas.provedor(conta_id)
        if p is None or self.estados.get(conta_id) != ev.CONECTADA:
            bipe("erro")
            desativada = hasattr(self.contas, "esta_ativa") and \
                not self.contas.esta_ativa(conta_id)
            self.fala.falar(
                "A conta está desativada. A mensagem não foi enviada. Ative "
                "a conta em Ferramentas, Gerenciar contas." if desativada else
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
            self._rotular_caixa()
        # a selecao fica na mensagem em que a pessoa estava
        self._preencher_mensagens()
        self.caixa.SetFocus()
        mencoes, self.mencoes = self.mencoes, []
        p.enviar_texto(conversa_id, texto, resposta, mencoes or None)
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
        if self._somente_leitura():
            return None
        conta_id, conversa_id = self.atual
        p = self.contas.provedor(conta_id)
        if p is None or self.estados.get(conta_id) != ev.CONECTADA:
            bipe("erro")
            self.fala.falar("A conta não está conectada. Nada foi enviado.",
                            interromper=True)
            return None
        return conta_id, conversa_id, p

    def _so_texto_no_status(self):
        """Em status so se responde com texto; avisa e devolve True."""
        if self._conversa_de_status():
            bipe("erro")
            self.fala.falar("Num status só dá para responder com texto.",
                            interromper=True)
            return True
        return False

    def _anexar_arquivo(self):
        if self._so_texto_no_status():
            return
        if self._destino_do_envio() is None:
            return
        caminho = dialogos.escolher_arquivo(
            self, self.cfg.get("pasta_anexos") or "")
        if not caminho:
            return
        self.cfg.set("pasta_anexos", os.path.dirname(caminho))
        self._enviar_arquivo(caminho, como_documento=True)

    def _gravar_rapido(self, origem):
        """O atalho de gravar: o primeiro aperto comeca a gravar e o
        seguinte para e ja envia a nota de voz, sem janela. Esc descarta."""
        if self._gravacao_rapida is not None:
            self._terminar_gravacao_rapida(enviar=True)
            return
        if self._so_texto_no_status():
            return
        if self._destino_do_envio() is None:
            return
        g = Gravador(config.pasta_temporaria(), origem, maximo_segundos=3600)
        bipe("gravando")
        time.sleep(0.4)     # o bipe nao pode entrar na gravacao
        try:
            g.iniciar()
        except ErroGravacao as e:
            bipe("erro")
            self.fala.falar(str(e), interromper=True)
            return
        self._gravacao_rapida = {"gravador": g, "origem": origem}
        chave = "gravar_mic" if origem == MICROFONE else "gravar_som"
        atalho = self.atalhos.efetivo(chave)
        self.SetStatusText("Gravando...")
        self.fala.falar(
            "Gravando. %s Esc descarta." % (
                "Aperte %s de novo para parar e enviar." %
                nucleo_atalhos.texto_falado(atalho) if atalho else
                "Pare pelo menu Mídias."), interromper=True)

    def _pausar_gravacao_rapida(self):
        """Pausa ou continua a gravacao feita por atalho. O trecho da pausa
        nao entra na gravacao."""
        est = self._gravacao_rapida
        if est is None:
            self.fala.falar("Nenhuma gravação em andamento.",
                            interromper=True)
            return
        g = est["gravador"]
        if g.pausado:
            bipe("gravando")
            time.sleep(0.4)         # o bipe nao pode entrar na gravacao
            g.continuar()
            self.SetStatusText("Gravando...")
            self.fala.falar("Gravando de novo.", interromper=True)
        else:
            g.pausar()
            bipe("gravacao_parada")
            self.SetStatusText("Gravação pausada")
            self.fala.falar("Gravação pausada em %s." % formatar_tempo(
                g.decorrido), interromper=True)

    def _descartar_gravacao_rapida(self):
        if self._gravacao_rapida is None:
            self.fala.falar("Nenhuma gravação em andamento.",
                            interromper=True)
            return
        self._terminar_gravacao_rapida(enviar=False)

    def _terminar_gravacao_rapida(self, enviar):
        """Para a gravacao do atalho: envia como nota de voz ou descarta."""
        est, self._gravacao_rapida = self._gravacao_rapida, None
        if est is None:
            return
        g = est["gravador"]
        self.SetStatusText("")
        if not enviar:
            g.cancelar()
            bipe("erro")
            self.fala.falar("Gravação descartada.", interromper=True)
            return
        try:
            gravacao = g.parar()
        except ErroGravacao as e:
            bipe("erro")
            self.fala.falar(str(e), interromper=True)
            return
        bipe("gravacao_parada")
        log.info("gravação rápida (%s) de %.0fs pronta para enviar",
                 est["origem"], gravacao.segundos)
        if gravacao.silenciosa:
            self.fala.falar("Atenção: a gravação saiu quase em silêncio.",
                            interromper=True)
        self._enviar_arquivo(gravacao.caminho, voz=True, temporario=True)

    def _gravar(self, origem):
        if self._so_texto_no_status():
            return
        if self._destino_do_envio() is None:
            return
        pasta = config.pasta_temporaria()
        if origem == MICROFONE:
            titulo = "Gravar nota de voz do microfone"
            instrucao = ("Fale perto do microfone. Aperte Enter em Gravar "
                         "para começar. Gravando, Enter para e Pausar faz "
                         "uma pausa; depois você pode ouvir, gravar de novo "
                         "ou enviar. Esc descarta.")
        else:
            titulo = "Gravar o som do computador"
            instrucao = ("Vai ser gravado tudo o que o computador tocar, "
                         "inclusive a voz do leitor de tela, se ele falar. "
                         "Aperte Enter em Gravar para começar. Gravando, "
                         "Enter para e Pausar faz uma pausa; depois você "
                         "pode ouvir, gravar de novo ou enviar. Esc "
                         "descarta.")
        gravacao = dialogos.gravar_voz(
            self, lambda: Gravador(pasta, origem, maximo_segundos=3600),
            titulo, instrucao, self.fala)
        if gravacao is None:
            return
        log.info("gravação (%s) de %.0fs pronta para enviar", origem,
                 gravacao.segundos)
        self._enviar_arquivo(gravacao.caminho, voz=True, temporario=True)

    def _enviar_arquivo(self, caminho, voz=False, temporario=False,
                        como_documento=False):
        if self._destino_do_envio() is None:
            return
        try:
            anexo = envio.preparar(caminho, voz=voz, temporario=temporario,
                                   como_documento=como_documento)
        except envio.ErroEnvio as e:
            bipe("erro")
            self.fala.falar(str(e), interromper=True)
            return
        self._enviar_anexo(anexo)

    def _enviar_anexo(self, anexo, com_legenda=True, limpar_resposta=True):
        """Manda um anexo ja preparado; o texto da caixa vai de legenda (menos
        em audio e voz, que nao tem), a nao ser que `com_legenda` seja falso.
        Com uma resposta em andamento, a midia cita a mensagem respondida;
        `limpar_resposta` falso deixa a resposta para o proximo envio."""
        destino = self._destino_do_envio()
        if destino is None:
            return False
        conta_id, conversa_id, p = destino
        legenda = "" if anexo.tipo in (m.VOZ, m.AUDIO) or not com_legenda \
            else self.caixa.GetValue().strip()
        resposta = self.resposta_a.id if self.resposta_a is not None else ""
        self.locais += 1
        ultima = max((x.data for x in self._mensagens_atuais()), default=0)
        local = m.Mensagem(conta_id, conversa_id, "local-%d" % self.locais,
                           minha=True, data=max(time.time(), ultima + 0.001),
                           texto=legenda, tipo=anexo.tipo,
                           segundos=anexo.segundos, nome_arquivo=anexo.nome,
                           tamanho=anexo.tamanho, estado=m.ENVIANDO,
                           resposta_a=resposta)
        self._mesclar(self.atual, [local])
        if legenda:
            self.caixa.Clear()
        self._preencher_mensagens()
        texto = "Enviando %s, %s." % (m.NOMES_TIPOS[anexo.tipo],
                                      m.tamanho_legivel(anexo.tamanho))
        if anexo.aviso:
            texto += " " + anexo.aviso
        if resposta:
            texto += " Como resposta."
        self.fala.falar(texto, interromper=True)
        mencoes = self.mencoes if legenda else []
        if legenda:
            self.mencoes = []
        if resposta or mencoes:
            p.enviar_arquivo(conversa_id, anexo, legenda, resposta,
                             mencoes or None)
        else:
            p.enviar_arquivo(conversa_id, anexo, legenda)
        if resposta and limpar_resposta:
            self.resposta_a = None
            self._rotular_caixa()
        log.info("arquivo (%s, %d bytes) enviado para a fila", anexo.tipo,
                 anexo.tamanho)
        return True

    # ======================================================== colar midia
    def _ao_colar(self, evt):
        """Control V na caixa: arquivos ou imagem viram anexos que esperam o
        Enter; texto cola normalmente."""
        if self.atual is None:
            evt.Skip()
            return
        colagem.colar(evt, self.fala, self.anexos, self._rotular_caixa,
                      tecla=self._tecla_de_enviar())

    def _descartar_anexos(self, falar=False):
        if not self.anexos:
            return
        colagem.descartar(self.anexos)
        self._rotular_caixa()
        if falar:
            self.fala.falar("Mídia colada removida.")

    def _enviar_anexos(self):
        """Enter com midias coladas: o texto da caixa e a legenda da primeira
        que aceita legenda; se nenhuma aceita (so audio e voz), vai depois
        como mensagem de texto."""
        if self._destino_do_envio() is None:
            return
        anexos, self.anexos = self.anexos, []
        self._rotular_caixa()
        legenda_usada = False
        for a in anexos:
            aceita = a.tipo not in (m.VOZ, m.AUDIO) and not legenda_usada
            tinha = bool(self.caixa.GetValue().strip())
            if self._enviar_anexo(a, com_legenda=aceita,
                                  limpar_resposta=False) and aceita and tinha:
                legenda_usada = True
        if not legenda_usada and self.caixa.GetValue().strip():
            self._enviar_texto()
        elif self.resposta_a is not None:
            self.resposta_a = None
            self._rotular_caixa()
        self.caixa.SetFocus()

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
        prov = self.contas.provedor(x.conta_id) if self.contas else None
        if prov is not None:
            try:
                prov.marcar_ouvida(x)      # a marca tambem vai ao celular
            except Exception:
                log.exception("erro ao avisar que o áudio foi ouvido")
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

    def _pular_audio(self, segundos):
        """Volta ou avanca o audio que toca ao fundo (sem a janela do
        player, que tem as proprias setas) e fala em que ponto ficou."""
        if self.audio is None or self.audio[1].terminou:
            self.fala.falar("Nenhum áudio tocando.", interromper=True)
            return
        motor = self.audio[1]
        try:
            motor.avancar(segundos)
            self.fala.falar("%s de %s" % (
                formatar_tempo(motor.posicao), formatar_tempo(motor.duracao)),
                interromper=True)
        except Exception:
            log.exception("erro ao pular no áudio")

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
        self._tirar_da_memoria({(c, v, i) for c, v, i, *_ in selecao.itens})

    def _apagar_expiradas(self, repetir=True):
        """Mensagens temporarias cujo prazo acabou: apaga daqui (e a midia),
        se a opcao estiver ligada; confere a cada minuto e ao abrir."""
        try:
            if self.cfg.get("temporarias_apagar_aqui"):
                chaves = self.banco.mensagens_expiradas()
                if chaves:
                    for conta, conversa, mensagem in chaves:
                        limpeza.apagar_mensagem(self.banco, conta, conversa,
                                                mensagem)
                    self._tirar_da_memoria(set(chaves))
                    log.info("mensagens temporárias vencidas apagadas: %d",
                             len(chaves))
        except Exception:
            log.exception("erro ao apagar mensagens temporárias vencidas")
        finally:
            if repetir:
                wx.CallLater(60000, self._apagar_expiradas)

    def _tirar_da_memoria(self, chaves):
        """Tira as mensagens (conta, conversa, id) do cache e da lista."""
        for chave, lista in list(self.cache.items()):
            self.cache[chave] = [x for x in lista if (
                x.conta_id, x.conversa_id, x.id) not in chaves]
        if self.atual:
            self._preencher_mensagens()

    def _espaco_midias(self):
        """Janela com o espaço das mídias baixadas (Esc ou Fechar fecha), em
        vez de só falar: a fala passava depressa demais. Traz conversas,
        mensagens de texto e mídias, no total e por tipo."""
        texto = limpeza.resumo_de_espaco(self.banco, len(self.indice))
        dialogos.mostrar_mensagem(self, "Espaço usado pelas mídias", texto,
                                  self._copiar_texto)

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

    def _barra_de_transferencia(self, chave, pct, titulo, cancelar=None):
        """A janela com barra de progresso de um download pedido ou de um
        envio grande: so abre se a transferencia passa de um segundo (as
        rapidas nao tomam o foco). Devolve True se a barra esta aberta (a
        fala do avanco fica quieta, o NVDA toca os bipes da barra)."""
        if not self.cfg.get("barra_de_progresso"):
            return False
        agora = time.monotonic()
        inicio = self._inicio_progresso.setdefault(chave, agora)
        barra = self._barras.get(chave)
        if barra is None:
            if agora - inicio < 1.0 or pct >= 90:
                return False
            barra = JanelaDeProgresso(self, titulo, titulo,
                                      ao_cancelar=cancelar)
            self._barras[chave] = barra
            barra.mostrar()
        barra.atualizar(pct)
        return True

    def _fechar_barra_de_transferencia(self, chave):
        self._inicio_progresso.pop(chave, None)
        barra = self._barras.pop(chave, None)
        if barra is not None:
            barra.fechar()

    def _ev_progresso_midia(self, e):
        chave = (e.conta_id, e.conversa_id, e.mensagem_id)
        if self.progresso_midias.get(chave) != e.percentual:
            self.progresso_midias[chave] = e.percentual
            self._atualizar_titulo()
        if chave != self.abrindo:
            return
        if self._barra_de_transferencia(
                ("baixando",) + chave, e.percentual, "Baixando mídia",
                self._cancelar_download):
            self.SetStatusText("Baixando mídia: %d%%" % e.percentual)
            return
        passo = int(self.cfg.get("midias_passo_progresso") or 0)
        marco = e.percentual // passo * passo if passo > 0 else 0
        if 0 < marco < 100 and marco > self.progresso_falado:
            self.progresso_falado = marco
            self.fala.falar("%d por cento" % marco)
        self.SetStatusText("Baixando mídia: %d%%" % e.percentual)

    def _ev_progresso_envio(self, e):
        """O envio de um arquivo andou: titulo, barra de situacao e a fala
        no passo escolhido (o mesmo do download)."""
        chave = (e.conta_id, e.conversa_id)
        if e.percentual >= 100:
            self._fim_do_envio(chave)
            return
        antes = self.progresso_envios.get(chave)
        self.progresso_envios[chave] = e.percentual
        if antes != e.percentual:
            self._atualizar_titulo()
        self.SetStatusText("Enviando arquivo: %d%%" % e.percentual)
        if self._barra_de_transferencia(("enviando",) + chave, e.percentual,
                                        "Enviando arquivo"):
            return
        if e.percentual < self._envio_falado.get(chave, 0):
            self._envio_falado[chave] = 0          # outro envio na conversa
        passo = int(self.cfg.get("midias_passo_progresso") or 0)
        marco = e.percentual // passo * passo if passo > 0 else 0
        if 0 < marco < 100 and marco > self._envio_falado.get(chave, 0):
            self._envio_falado[chave] = marco
            self.fala.falar("%d por cento" % marco)

    def _fim_do_envio(self, chave):
        self._fechar_barra_de_transferencia(("enviando",) + tuple(chave))
        if self.progresso_envios.pop(chave, None) is not None:
            self._atualizar_titulo()
        self._envio_falado.pop(chave, None)

    def _ev_midia_baixada(self, e):
        chave = (e.conta_id, e.conversa_id, e.mensagem_id)
        self._fechar_barra_de_transferencia(("baixando",) + chave)
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
            self._ia_pendentes.pop(chave, None)
            if pedida or not e.automatica:
                bipe("erro")
                self.fala.falar(e.erro, interromper=True)
                wx.MessageBox(e.erro, NOME, wx.OK | wx.ICON_WARNING, self)
            return
        self.SetStatusText("Mídia baixada.")
        esperando = self._ia_pendentes.pop(chave, None)
        if esperando is not None:
            wx.CallAfter(self._ia_processar, esperando[0], esperando[1])
            return
        if not e.automatica:
            bipe("download_pronto")
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

    def _configuracoes(self, categoria=None):
        from telezapp.interface.configuracoes import DialogoConfiguracoes
        dlg = DialogoConfiguracoes(self, self.cfg, self._aplicar_opcao,
                                   categoria_inicial=categoria,
                                   fala=self.fala,
                                   privacidade=_PrivacidadeParaConfig(self),
                                   ia=_IaParaConfig(self),
                                   atalhos=self.atalhos)
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
        elif chave == "atalhos":
            self._aplicar_atalhos(valor)
        elif chave == "segundo_plano":
            self.cfg.set(chave, valor)
            self._atualizar_bandeja()
        elif chave == "iniciar_com_windows":
            self.cfg.set(chave, valor)
            if not inicializacao.definir(valor):
                self.fala.falar("O Windows não deixou mudar a abertura "
                                "automática.", interromper=True)
        elif chave == "mostrar_atalhos":
            self.cfg.set(chave, valor)
            self._atualizar_atalhos()
            self._rotular_controles()
        elif chave == "sons_pacotes":
            self.cfg.set("pacote_de_sons", valor["ativo"])
            self.cfg.set("sons_desativados", valor["desativados"])
            self._carregar_sons()
            for erro in valor.get("erros", []):
                self.fala.falar(erro)
        elif chave == "ia_credenciais":
            for prov, k in valor["chaves"].items():
                self.cofre_ia.guardar(prov, k)
            modelos = dict(self.cfg.get("ia_modelos") or {})
            modelos.update(valor["modelos"])
            self.cfg.set("ia_modelos", {p: v for p, v in modelos.items()
                                        if v})
            ordem = dict(self.cfg.get("ia_ordem") or {})
            ordem.update(valor.get("ordem", {}))
            self.cfg.set("ia_ordem", {t: v for t, v in ordem.items() if v})
            self.fala.falar("Chaves e modelos da inteligência artificial "
                            "salvos.")
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
        elif chave in ("falar_novas", "falar_novas_outras_conversas",
                      "falar_novas_fora_do_telezapp", "confirmar_envio",
                      "falar_reacoes"):
            self._opcao(chave, valor)
            self.itens[chave].Check(bool(valor))
        else:
            self.cfg.set(chave, valor)
            if chave in ("previa_receber", "previa_enviar"):
                self._carregar_previa_de_links()
            elif chave == "previa_links":
                m.definir_modo_previa(valor)
                if self.atual is not None:
                    self._preencher_mensagens()
            elif chave in ("ia_linha_descricao", "ia_linha_transcricao"):
                self._carregar_limites_ia()
                if self.atual is not None:
                    self._preencher_mensagens()

    def _carregar_previa_de_links(self):
        previa_links.definir(self.cfg.get("previa_receber"),
                             self.cfg.get("previa_enviar"))

    def _previa_da_recebida(self, msg):
        """Mensagem que chegou com link e sem previa: com a opcao ligada, a
        pagina e aberta ao fundo e a previa entra na mensagem."""
        if not previa_links.LIGADAS["receber"] or msg.minha or \
                msg.id.startswith("local-") or msg.tipo != m.TEXTO:
            return
        if m.extras_de(msg)["previa"]:
            return
        url = previa_links.primeiro_link(msg.texto)
        if not url:
            return

        def trabalho():
            previa = previa_links.buscar(url)
            if previa:
                wx.CallAfter(self._previa_pronta, msg, previa)
        threading.Thread(target=trabalho, daemon=True,
                         name="previa-de-link").start()

    def _previa_pronta(self, msg, previa):
        m.guardar_extras(msg, previa=previa)
        self.banco.salvar_mensagens([msg])
        chave = (msg.conta_id, msg.conversa_id)
        for i, y in enumerate(self.cache.get(chave, [])):
            if y.id == msg.id:
                self.cache[chave][i] = msg
        if self.atual == chave:
            self._preencher_mensagens()

    def _carregar_limites_ia(self):
        """Quanto do texto da IA entra na linha de cada mensagem."""
        m.definir_limites_ia(self.cfg.get("ia_linha_descricao"),
                             self.cfg.get("ia_linha_transcricao"))

    def _carregar_sons(self):
        """Passa ao modulo de sons o que a pessoa escolheu para cada evento."""
        ativo = self.cfg.get("pacote_de_sons")
        if ativo not in dict(pacotes_de_som.listar()):
            ativo = pacotes_de_som.PADRAO
        desativados = (self.cfg.get("sons_desativados") or {}).get(ativo, [])
        definir_sons(pacotes_de_som.mapa(ativo, desativados))

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
        self._abrir_pasta("logs")

    def _abrir_pasta(self, nome):
        pasta = config.pasta(nome)
        if os.name == "nt":
            subprocess.Popen(["explorer", pasta])
        else:
            self.fala.falar(pasta)

    # ============================================================ backup
    @seguro
    def _fazer_backup(self):
        """Salva num .zip (com senha, se a pessoa quiser) as partes que ela
        escolher: configuracoes, contas e sessoes, conversas e midias."""
        from telezapp.interface import backup as jb
        dlg = jb.DialogoBackup(self)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            partes, senha = dlg.partes(), dlg.senha.GetValue()
        finally:
            dlg.Destroy()
        nome = time.strftime("TeleZapp-backup-%Y%m%d-%H%M%S.zip")
        sel = wx.FileDialog(
            self, "Salvar o backup", defaultDir=self.cfg.get("pasta_backup")
            or "", defaultFile=nome, wildcard="Arquivo zip|*.zip",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        try:
            if sel.ShowModal() != wx.ID_OK:
                return
            caminho = sel.GetPath()
        finally:
            sel.Destroy()
        if not caminho.lower().endswith(".zip"):
            caminho += ".zip"
        self.cfg.set("pasta_backup", os.path.dirname(caminho))
        dados = dict(self.cfg.dados)

        andamento, fechar_barra = self._barra_de_tarefa("Fazendo o backup")

        def trabalho():
            try:
                resumo = backup.criar(
                    caminho, config.pasta_dados(), dados, partes, senha,
                    copiar_banco=self.banco.copiar_para,
                    progresso=andamento)
                texto = "Backup salvo em %s%s." % (
                    caminho, " (com senha)" if senha else "")
                grave = False
                log.info("backup salvo: %s", resumo)
            except Exception as e:
                log.error("erro ao fazer o backup:\n%s",
                          traceback.format_exc())
                texto = "Não consegui fazer o backup: %s" % e
                grave = True
            fechar_barra()
            wx.CallAfter(self._fim_do_backup, texto, grave)
        self.fala.falar("Fazendo o backup. Aviso quando terminar.",
                        interromper=True)
        threading.Thread(target=trabalho, daemon=True,
                         name="backup").start()

    def _barra_de_tarefa(self, titulo, ao_cancelar=None):
        """Abre uma janela com barra de progresso para uma tarefa que roda
        numa thread. Devolve (andamento, fechar): `andamento(pct, texto)` e
        `fechar()` podem ser chamadas da thread (vao para a janela pelo
        wx.CallAfter) e so atualizam quando a porcentagem muda."""
        barra = JanelaDeProgresso(self, titulo, titulo,
                                  ao_cancelar=ao_cancelar,
                                  falar=lambda t: self.fala.falar(
                                      t, interromper=True))
        barra.mostrar()
        ultimo = [-1]

        def andamento(pct, texto=""):
            if pct is None or int(pct) == ultimo[0]:
                return
            ultimo[0] = int(pct)
            wx.CallAfter(barra.atualizar, pct, texto or titulo)

        def fechar():
            wx.CallAfter(barra.fechar)
        return andamento, fechar

    def _fim_do_backup(self, texto, grave):
        bipe("erro" if grave else "tarefa_pronta")
        self.fala.falar(texto, interromper=True)
        wx.MessageBox(texto, NOME, wx.OK | (
            wx.ICON_WARNING if grave else wx.ICON_INFORMATION), self)

    @seguro
    def _restaurar_backup(self):
        """Restaura as partes que a pessoa escolher de um backup. As
        configuracoes valem na hora; o resto troca na proxima abertura."""
        from telezapp.interface import backup as jb
        sel = wx.FileDialog(
            self, "Escolha o backup", defaultDir=self.cfg.get("pasta_backup")
            or "", wildcard="Arquivo zip|*.zip",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        try:
            if sel.ShowModal() != wx.ID_OK:
                return
            arquivo = sel.GetPath()
        finally:
            sel.Destroy()
        senha = ""
        try:
            if backup.precisa_de_senha(arquivo):
                pd = wx.PasswordEntryDialog(self, "Senha do backup:",
                                            "Restaurar backup")
                try:
                    if pd.ShowModal() != wx.ID_OK:
                        return
                    senha = pd.GetValue()
                finally:
                    pd.Destroy()
            manifesto = backup.ler_manifesto(arquivo, senha)
        except backup.ErroBackup as e:
            bipe("erro")
            self.fala.falar(str(e), interromper=True)
            wx.MessageBox(str(e), NOME, wx.OK | wx.ICON_WARNING, self)
            return
        if not manifesto.partes:
            self.fala.falar("Este backup está vazio.")
            return
        dlg = jb.DialogoRestaurar(self, manifesto)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            partes = dlg.partes()
        finally:
            dlg.Destroy()
        if not partes:
            return
        if set(partes) - {"configuracoes"}:
            r = wx.MessageBox(
                "Restaurar vai trocar, na próxima abertura, o que o %s tem "
                "hoje nessas partes pelo conteúdo do backup (o que havia fica "
                "guardado). Continuar?" % NOME, "Restaurar backup",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
            if r != wx.YES:
                return

        andamento, fechar_barra = self._barra_de_tarefa("Restaurando o backup")

        def trabalho():
            try:
                extra = {}
                opcoes, espera = backup.restaurar(
                    arquivo, senha, partes, config.pasta_dados(), extra,
                    progresso=andamento)
                erro = ""
            except backup.ErroBackup as e:
                opcoes, espera, erro, extra = {}, [], str(e), {}
            except Exception as e:
                log.error("erro ao restaurar:\n%s", traceback.format_exc())
                opcoes, espera, erro, extra = {}, [], \
                    "Erro ao restaurar: %s" % e, {}
            fechar_barra()
            wx.CallAfter(self._fim_da_restauracao, opcoes, espera, erro,
                         extra.get("ia_chaves", 0))
        self.fala.falar("Restaurando o backup. Aviso quando terminar.",
                        interromper=True)
        threading.Thread(target=trabalho, daemon=True,
                         name="restaurar").start()

    @seguro
    def _fim_da_restauracao(self, opcoes, espera, erro, chaves_ia=0):
        if erro:
            bipe("erro")
            self.fala.falar(erro, interromper=True)
            wx.MessageBox(erro, NOME, wx.OK | wx.ICON_WARNING, self)
            return
        bipe("tarefa_pronta")
        mudadas = 0
        for chave, valor in opcoes.items():
            if self.cfg.get(chave) != valor:
                self._aplicar_opcao(chave, valor)
                mudadas += 1
        texto = "Backup restaurado."
        if opcoes:
            texto += " %d configurações mudaram." % mudadas
        if chaves_ia:
            texto += (" %d chave(s) de provedores de IA voltaram." %
                      chaves_ia)
        if espera:
            texto += (" O resto (%s) troca quando o %s abrir de novo." % (
                ", ".join(backup.NOMES_PARTES[p].split(" (")[0].split(",")[0]
                          .lower() for p in espera), NOME))
        self.fala.falar(texto, interromper=True)
        if espera:
            dlg = wx.MessageDialog(
                self, texto + "\n\nReiniciar o %s agora para terminar?" %
                NOME, NOME, wx.YES_NO | wx.ICON_QUESTION)
            dlg.SetYesNoLabels("&Reiniciar agora", "&Depois")
            try:
                r = dlg.ShowModal()
            finally:
                dlg.Destroy()
            if r == wx.ID_YES:
                self._reiniciar()
        else:
            wx.MessageBox(texto, NOME, wx.OK | wx.ICON_INFORMATION, self)

    def _modo_ou_aviso(self, esperado, aviso):
        """O modo atual do programa; se nao for o esperado, avisa e devolve
        None."""
        modo = instalacao.modo()
        if modo == esperado:
            return modo
        wx.MessageBox(aviso, NOME, wx.OK | wx.ICON_INFORMATION, self)
        return None

    @seguro
    def _instalar(self):
        """Instala esta copia portatil em %LOCALAPPDATA%/Programs."""
        if not self._modo_ou_aviso(
                "portatil", "Só uma cópia portátil pode ser instalada. "
                "Esta aqui %s." % (
                    "já é a versão instalada" if instalacao.modo() ==
                    "instalado" else "está rodando pelo código-fonte")):
            return
        from telezapp.interface import instalacao as ui_inst
        r = ui_inst.fluxo_instalar(self)
        if r and r[1]:
            self._abrir_depois(r[0])

    def _abrir_depois(self, exe):
        """Fecha este programa e abre o `exe` (o programa so abre uma vez)."""
        linha = "ping -n 5 127.0.0.1 >nul & start \"\" " + \
            subprocess.list2cmdline([exe])
        if not self.Close():
            return
        try:
            subprocess.Popen(
                linha, shell=True, cwd=os.path.dirname(exe), creationflags=(
                    subprocess.CREATE_NO_WINDOW |
                    subprocess.DETACHED_PROCESS))
        except OSError:
            log.exception("não consegui abrir a versão instalada")

    @seguro
    def _criar_portatil(self):
        """Cria uma copia portatil (programa + pasta dados) onde a pessoa
        escolher."""
        if instalacao.modo() == "desenvolvimento":
            wx.MessageBox("A cópia portátil só pode ser criada a partir do "
                          "executável, não pelo código-fonte.", NOME,
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        from telezapp.interface import instalacao as ui_inst
        ui_inst.fluxo_criar_portatil(
            self, self.cfg.get("pasta_backup") or os.path.expanduser("~"))

    @seguro
    def _desinstalar(self):
        if not self._modo_ou_aviso(
                "instalado", "Só a versão instalada pode ser desinstalada. "
                "Para uma cópia portátil, basta apagar a pasta."):
            return
        if wx.MessageBox(
                "Desinstalar o %s? O programa fecha. As suas contas e "
                "conversas ficam guardadas em %s (você pode fazer um backup "
                "antes, na próxima pergunta)." % (
                    NOME, instalacao.dados_do_computador()), NOME,
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self) != wx.YES:
            return
        from telezapp.interface import instalacao as ui_inst
        if not ui_inst.oferecer_backup(
                self, dict(self.cfg.dados), self.banco.copiar_para,
                self.cfg.get("pasta_backup") or ""):
            return
        instalacao.desinstalar(apagar_dados=False)
        self.Close()

    def _reiniciar(self):
        """Fecha o TeleZapp e o abre de novo: um processo separado espera o
        atual terminar (o programa so abre uma vez) e inicia outro igual."""
        if getattr(sys, "frozen", False):
            alvo = [sys.executable] + sys.argv[1:]
        else:
            alvo = [sys.executable, "-m", "telezapp"]
        linha = "ping -n 5 127.0.0.1 >nul & start \"\" " + \
            subprocess.list2cmdline(alvo)
        if not self.Close():
            return              # a pessoa desistiu de fechar
        try:
            subprocess.Popen(
                linha, shell=True, cwd=os.getcwd(), creationflags=(
                    subprocess.CREATE_NO_WINDOW |
                    subprocess.DETACHED_PROCESS))
        except OSError:
            log.exception("não consegui reiniciar")

    def _verificar_atualizacoes(self, manual=True):
        """Consulta as versoes publicadas no GitHub, sem travar a janela.
        Manual: sempre responde. Automatica (ao abrir): so fala se ha versao
        nova que ainda nao foi avisada, e nunca reclama de erro."""
        if manual:
            self.fala.falar("Verificando atualizações...", interromper=True)

        def trabalho():
            try:
                lanc, erro = atualizacao.consultar(), ""
            except atualizacao.ErroAtualizacao as e:
                lanc, erro = None, str(e)
            except Exception:
                log.exception("erro ao verificar atualizações")
                lanc, erro = None, "Erro ao verificar atualizações."
            wx.CallAfter(self._resultado_atualizacao, lanc, erro, manual)
        threading.Thread(target=trabalho, daemon=True,
                         name="verificar-atualizacoes").start()

    @seguro
    def _resultado_atualizacao(self, lanc, erro, manual):
        if erro:
            if manual:
                bipe("erro")
                self.fala.falar(erro, interromper=True)
                wx.MessageBox(erro, NOME, wx.OK | wx.ICON_WARNING, self)
            return
        if lanc is None or not atualizacao.e_mais_nova(lanc):
            if manual:
                texto = "Você está com a versão mais recente, %s." % VERSAO
                self.fala.falar(texto, interromper=True)
                wx.MessageBox(texto, NOME, wx.OK | wx.ICON_INFORMATION, self)
            return
        if not manual:
            if self.cfg.get("atualizacao_avisada") == lanc.versao:
                return
            self.cfg.set("atualizacao_avisada", lanc.versao)
        bipe("tarefa_pronta")
        from telezapp.interface.atualizacao import DialogoAtualizacao
        pode = bool(getattr(sys, "frozen", False) and lanc.url_zip
                    and lanc.url_hash)
        dlg = DialogoAtualizacao(self, lanc, VERSAO, pode,
                                 config.pasta_dados())
        try:
            dlg.ShowModal()
            escolha = dlg.escolha
        finally:
            dlg.Destroy()
        if escolha == "instalar":
            wx.CallAfter(self._atualizar, lanc)
        elif escolha == "pagina":
            dialogos.abrir_link(lanc.pagina)

    @seguro
    def _atualizar(self, lanc):
        """Baixa a versao nova, confere o hash, extrai e reinicia trocando a
        pasta do programa. Uma janela com barra de progresso mostra o avanco
        (o NVDA toca bipes do grave ao agudo) e deixa cancelar."""
        if getattr(self, "_atualizando", False):
            return
        programa = instalacao.pasta_do_programa()
        espera = atualizador.pasta_de_espera(programa)
        self._atualizando = True
        cancelou = [False]
        etapa_baixar = "Baixando a versão %s" % lanc.versao
        barra = JanelaDeProgresso(
            self, "Atualizando o %s" % NOME, etapa_baixar,
            ao_cancelar=lambda: cancelou.__setitem__(0, True),
            falar=lambda t: self.fala.falar(t, interromper=True))
        self._barra_atualizacao = barra
        barra.mostrar()

        def baixando(feito, total):
            if total:
                pct = feito * 90 // total        # baixar vai ate 90%
                wx.CallAfter(barra.atualizar, pct, etapa_baixar)

        def extraindo(feito, total):
            wx.CallAfter(barra.atualizar, 90 + feito * 10 // max(total, 1),
                         "Preparando a atualização")

        def trabalho():
            try:
                arquivo = atualizador.baixar(
                    lanc, espera, baixando,
                    cancelado=lambda: cancelou[0])
                nova = atualizador.extrair(
                    arquivo, os.path.join(espera, "novo"), extraindo)
                erro = ""
            except atualizador.ErroAtualizacao as e:
                nova, erro = None, str(e)
            except Exception as e:
                log.error("erro ao atualizar:\n%s", traceback.format_exc())
                nova, erro = None, "Não consegui atualizar: %s" % e
            wx.CallAfter(self._atualizacao_pronta, nova, erro, programa)
        self.fala.falar("Baixando a atualização.", interromper=True)
        threading.Thread(target=trabalho, daemon=True,
                         name="atualizar").start()

    @seguro
    def _atualizacao_pronta(self, nova, erro, programa):
        self._atualizando = False
        barra = getattr(self, "_barra_atualizacao", None)
        self._barra_atualizacao = None
        if barra is not None:
            barra.atualizar(100 if not erro else None)
            barra.fechar()
        if erro:
            if erro.startswith("Atualização cancelada"):
                self.fala.falar("Atualização cancelada.", interromper=True)
                return
            bipe("erro")
            self.fala.falar(erro, interromper=True)
            wx.MessageBox(erro, NOME, wx.OK | wx.ICON_WARNING, self)
            return
        bipe("tarefa_pronta")
        if not self.Close():
            return              # a pessoa desistiu de fechar
        atualizador.aplicar(programa, nova)

    def _sobre(self):
        wx.MessageBox(
            "%s %s\nCliente de WhatsApp e Telegram feito para leitores de "
            "tela.\nSoftware experimental: use por sua conta e risco.\n"
            "Software livre sob a licença GPL versão 3 ou "
            "posterior.\nDados guardados em: %s" % (
                NOME, VERSAO, config.pasta_dados()),
            "Sobre o %s" % NOME, wx.OK | wx.ICON_INFORMATION, self)

    # ================================================================ saida
    def _ao_fechar(self, evt):
        if self.cfg.get("segundo_plano") and not self._saindo and \
                hasattr(evt, "CanVeto") and evt.CanVeto():
            evt.Veto()
            self._esconder_na_bandeja()
            return
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
        self._saindo = True
        self._tirar_bandeja()
        if hasattr(self, "UnregisterHotKey"):
            try:
                self.UnregisterHotKey(self._id_global)
            except Exception:
                pass
        if self._gravacao_rapida is not None:
            self._terminar_gravacao_rapida(enviar=False)
        self.Hide()
        self._guardar_posicao()
        self._parar_audio(falar=False)
        try:
            if self.contas is not None:
                self.contas.parar_todos()
        finally:
            self.Destroy()


def _ordem(x):
    """Ordena por data; ids numericos desempatam."""
    return (x.data, int(x.id) if x.id.isdigit() else 0)

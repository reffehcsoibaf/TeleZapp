# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Pasta de dados, configuracoes e registro (log).

Tudo o que da acesso as contas (sessoes) e o banco local ficam em
%APPDATA%\\TeleZapp, fora da pasta do programa e do repositorio. A variavel
de ambiente TELEZAPP_DADOS troca essa pasta (usada nos testes).

O registro nunca grava o texto das mensagens, numeros de telefone completos,
codigos ou senhas.
"""
import json
import logging
import logging.handlers
import os
import re
import shutil
import sys
import threading
import unicodedata
from dataclasses import dataclass

from telezapp import NOME, VERSAO

log = logging.getLogger("telezapp")


def pasta_dados():
    especial = os.environ.get("TELEZAPP_DADOS")
    if especial:
        return especial
    if getattr(sys, "frozen", False):
        # copia portatil: a pasta "dados" ao lado do executavel
        portatil = os.path.join(os.path.dirname(os.path.abspath(
            sys.executable)), "dados")
        if os.path.isdir(portatil):
            return portatil
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, NOME)


def pasta(*partes):
    """Caminho dentro da pasta de dados, criando as pastas que faltam."""
    caminho = os.path.join(pasta_dados(), *partes)
    os.makedirs(caminho, exist_ok=True)
    return caminho


def configurar_registro():
    """Grava em logs\\telezapp.log (ate 5 arquivos de 1 MB)."""
    raiz = logging.getLogger("telezapp")
    if raiz.handlers:
        return os.path.join(pasta("logs"), "telezapp.log")
    arquivo = os.path.join(pasta("logs"), "telezapp.log")
    h = logging.handlers.RotatingFileHandler(
        arquivo, maxBytes=1024 * 1024, backupCount=4, encoding="utf-8")
    h.setFormatter(FormatadorSemTelefones(
        "%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    raiz.addHandler(h)
    raiz.setLevel(logging.INFO)
    raiz.propagate = False
    # Avisos das bibliotecas (reconexao, limites) ajudam a investigar
    # problemas. O neonize configura o log raiz ao ser importado; os dele
    # ficam so em avisos, aqui, e o nivel tambem vale para o lado em Go.
    for nome in ("telethon", "whatsmeow", "Whatsmeow", "neonize",
                 "neonize.utils.log"):
        lib = logging.getLogger(nome)
        lib.addHandler(h)
        lib.setLevel(logging.WARNING)
        lib.propagate = False
    raiz.info("==== %s %s iniciado ====", NOME, VERSAO)
    return arquivo


# Enderecos do WhatsApp (5551999998888@s.whatsapp.net, 5577...-1577...@g.us,
# 1011...@lid, com ou sem parte do aparelho) e telefones com "+": o registro
# nao pode levar numero de ninguem, porque o usuario o manda ao suporte.
_ENDERECO = re.compile(
    r"(?<![\w.:-])(\d{7,})((?:[.:]\d+)*)(-\d+)?"
    r"@(s\.whatsapp\.net|c\.us|g\.us|lid|hosted\.lid|hosted)\b")
_TELEFONE_COM_MAIS = re.compile(r"(?<!\w)\+(\d{8,15})\b")


def mascarar_texto(texto):
    """Troca telefones e enderecos do WhatsApp do texto pelo fim deles:
    '5551999998888@s.whatsapp.net' -> '...8888@s.whatsapp.net'; um grupo
    '557791063633-1577487873@g.us' -> '...3633-1577487873@g.us' (o numero
    antes do traco e de quem criou o grupo); '+5551999998888' ->
    '+55...8888'. O resto do texto fica como esta."""
    def endereco(m):
        return "...%s%s%s@%s" % (m.group(1)[-4:], m.group(2),
                                 m.group(3) or "", m.group(4))

    def telefone(m):
        n = m.group(1)
        return "+%s...%s" % (n[:2], n[-4:])
    return _TELEFONE_COM_MAIS.sub(telefone, _ENDERECO.sub(endereco,
                                                          str(texto)))


class FormatadorSemTelefones(logging.Formatter):
    """O formatador do registro: passa o texto final (inclusive o de uma
    excecao) por `mascarar_texto`."""

    def format(self, record):
        return mascarar_texto(super().format(record))


def mascarar_telefone(telefone):
    """+5551999998888 -> +55...8888 (para o registro)."""
    t = telefone or ""
    return t[:3] + "..." + t[-4:] if len(t) > 7 else "..."


def pasta_depuracao():
    """Onde a depuracao grava os textos salvos: C:\\logs no Windows (a
    pasta que a pessoa ja usa para os logs), senao a pasta de logs do app."""
    especial = os.environ.get("TELEZAPP_PASTA_DEPURACAO")
    if especial:
        os.makedirs(especial, exist_ok=True)
        return especial
    if os.name == "nt":
        os.makedirs("C:\\logs", exist_ok=True)
        return "C:\\logs"
    return pasta("logs")


def pasta_temporaria():
    """Arquivos temporarios do app: so aqui, nunca no %temp% do Windows."""
    return pasta("temp")


def pasta_sons():
    """Os arquivos de som que a pessoa escolheu para os avisos."""
    return pasta("sons")


def importar_som(origem):
    """Copia o arquivo de som para a pasta de sons (se ainda nao estiver
    nela) e devolve o nome dele la dentro. Um nome ja usado por outro arquivo
    ganha um numero."""
    destino_dir = pasta_sons()
    nome = os.path.basename(origem)
    destino = os.path.join(destino_dir, nome)
    if os.path.normcase(os.path.abspath(origem)) == \
            os.path.normcase(os.path.abspath(destino)):
        return nome
    base, ext = os.path.splitext(nome)
    n = 1
    while os.path.exists(destino):
        if os.path.getsize(destino) == os.path.getsize(origem) and \
                open(destino, "rb").read() == open(origem, "rb").read():
            return os.path.basename(destino)       # ja e o mesmo arquivo
        n += 1
        nome = "%s (%d)%s" % (base, n, ext)
        destino = os.path.join(destino_dir, nome)
    shutil.copyfile(origem, destino)
    return nome


def limpar_temporarios():
    """Apaga o conteudo da pasta temporaria (na abertura e no fechamento)."""
    caminho = os.path.join(pasta_dados(), "temp")
    if os.path.isdir(caminho):
        shutil.rmtree(caminho, ignore_errors=True)


# ------------------------------------------- pastas de dados por conta
_cfg_de_contas = None


def definir_cfg(cfg):
    """Lembra a configuracao ativa: as funcoes abaixo consultam o registro
    de cada conta para achar a pasta de dados dela."""
    global _cfg_de_contas
    _cfg_de_contas = cfg


def contas_separadas():
    """True quando cada conta guarda os dados em uma pasta propria (o
    banco de conversas, as sessoes e as midias). False (opcao
    "contas_em_pastas" desmarcada): todas dividem o layout antigo, um
    banco so, no lugar de sempre."""
    cfg = _cfg_de_contas
    if cfg is None:
        return False
    return bool(cfg.get("contas_em_pastas"))


def ids_das_contas():
    """Os ids das contas conhecidas (na configuracao ativa), ou None se
    nao ha configuracao carregada."""
    cfg = _cfg_de_contas
    if cfg is None:
        return None
    return [c["id"] for c in cfg.contas() if c.get("id")]


def _mesmo_caminho(a, b):
    """Os dois caminhos apontam para a mesma pasta?"""
    return os.path.normcase(os.path.abspath(a)) == \
        os.path.normcase(os.path.abspath(b))


def pasta_escolhida_do_layout_antigo(cfg=None):
    """Onde ficam o banco unico, as sessoes e as midias do layout antigo
    (sem separacao por conta): sempre a pasta de dados. A pasta que a
    pessoa escolhe so vale com a separacao por conta marcada."""
    return pasta_dados()


def pasta_do_layout_antigo(cfg=None):
    """Onde os dados do layout antigo estao: a pasta de dados. As opcoes,
    os logs, os sons e os backups tambem ficam sempre nela."""
    return pasta_dados()


def pasta_escolhida_das_contas(cfg=None):
    """A pasta que a pessoa escolheu para as pastas das contas ("" se nao
    escolheu ou se a separacao por conta esta desmarcada)."""
    if cfg is None:
        cfg = _cfg_de_contas
    if cfg is None or not cfg.get("contas_em_pastas"):
        return ""
    return (cfg.get("contas_pasta") or "").strip()


def pasta_das_contas():
    """A pasta que abriga a pasta de cada conta: a que a pessoa escolheu
    (opcao "contas_pasta", em Gerenciar contas) ou a padrao,
    a pasta contas dentro da de dados. Nao cria nada."""
    escolhida = pasta_escolhida_das_contas()
    if escolhida:
        return escolhida
    return os.path.join(pasta_dados(), "contas")


def pasta_da_conta(conta_id):
    """A pasta de dados de uma conta: <pasta das contas>\\<conta_id>.
    Nao cria nada; para criar, ver preparar_pasta_da_conta. Sem separacao
    (contas_em_pastas desmarcada) a conta nao tem pasta propria: as
    sessoes ficam em pasta_sessoes e as midias na pasta comum."""
    return os.path.join(pasta_das_contas(), conta_id)


def pasta_sessoes(conta_id):
    """Onde ficam os arquivos de sessao da conta: na pasta dela (com
    separacao) ou na pasta de sessoes do layout antigo (a personalizada,
    se escolhida; senao, <dados>\\sessoes)."""
    if not contas_separadas():
        return os.path.join(pasta_do_layout_antigo(), "sessoes")
    return os.path.join(pasta_da_conta(conta_id), "sessoes")


def pastas_das_contas():
    """As pastas de dados de cada conta conhecida, sem repetir (para somar
    tamanhos, por exemplo)."""
    vistas, saida = set(), []
    cfg = _cfg_de_contas
    if cfg is not None:
        for dados in cfg.contas():
            pasta = pasta_da_conta(dados["id"])
            if pasta not in vistas:
                vistas.add(pasta)
                saida.append(pasta)
    return saida


def preparar_pasta_da_conta(conta_id):
    """Cria as pastas que a conta precisa: a dela e a de sessoes (com
    separacao), ou so a pasta de sessoes comum. False se nao conseguir
    (ex.: a unidade da pasta escolhida esta desligada): a conta fica sem
    ligar ate a pasta voltar."""
    try:
        os.makedirs(pasta_sessoes(conta_id), exist_ok=True)
        return True
    except OSError as erro:
        log.warning("não consegui preparar a pasta da conta %s: %r",
                    conta_id, erro)
        return False


def limpar_pasta_da_conta(conta_id):
    """Depois de remover a conta: apaga a pasta dela, se tiver ficado
    vazia (a escolhida pela pessoa tambem — mas so se nao tiver mais nada
    dentro)."""
    pasta = pasta_da_conta(conta_id)
    try:
        os.rmdir(os.path.join(pasta, "sessoes"))
    except OSError:
        pass
    try:
        os.rmdir(pasta)
    except OSError:
        pass


# ------------------------------------------------- opcoes de configuracao
@dataclass(frozen=True)
class Opcao:
    """Uma opcao que a pessoa pode mudar. O registro unico serve aos menus
    de hoje e a janela de configuracoes com busca (etapa 4)."""
    chave: str
    rotulo: str
    categoria: str
    padrao: object
    descricao: str
    escolhas: tuple = ()     # vazio: sim ou nao; senao (valor, rotulo)
    numero: tuple = ()       # (minimo, maximo): numero digitado, sem lista
    som: str = ""            # evento de som (ver EVENTOS_SOM): "" = outra opcao
    grupo: str = ""          # botao da categoria que abre estas opcoes juntas
    texto: bool = False      # texto digitado
    pasta: bool = False      # o texto e uma pasta: ganha o botao de escolher
    # so vale quando o TeleZapp abre de novo: ao dar OK nas configuracoes
    # com uma destas mudada, ele oferece reiniciar
    reabrir: bool = False
    # so aparece nas configuracoes quando ha uma conta deste servico
    # ("whatsapp", "telegram"); vazio: aparece sempre
    servico: str = ""


MENSAGENS_POR_VEZ = (50, 5000)

# Recursos que ainda nao sabemos se funcionam bem para todos: cada um tem uma
# caixa propria, desligada, e marcar qualquer uma mostra um aviso (so OK).
CATEGORIA_EXPERIMENTAL = "Recursos experimentais"

# Escondida enquanto aparencia.MODO_VISUAL_DISPONIVEL for False
OPCAO_MODO_EXIBICAO = Opcao(
    "modo_exibicao", "Modo de exibição", "Interface", "automatico",
          "Para leitor de tela: a janela de sempre, feita para ser ouvida, "
          "com cada mensagem numa linha. Visual: para quem lê na tela, com "
          "as mensagens longas quebradas em várias linhas e as suas "
          "destacadas. Os atalhos e os menus são os mesmos nos dois. "
          "Automático: ao abrir, o TeleZapp usa o modo para leitor de tela "
          "se houver um leitor de tela ligado, e o visual se não houver. "
          "Vale na próxima vez que o TeleZapp abrir.",
          escolhas=(("automatico", "Automático, conforme haja leitor de "
                     "tela ligado"),
                    ("leitor", "Para leitor de tela"),
                    ("visual", "Visual")),
          reabrir=True)

OPCOES = (
    Opcao("mensagens_por_vez", "Quantas mensagens buscar por vez", "Mensagens",
          100,
          "Quantas mensagens a lista mostra ao abrir uma conversa e quantas "
          "traz a mais a cada Home na primeira da lista. Vale para todas as "
          "conversas. Conversas com mais não lidas que isso mostram todas "
          "elas. No WhatsApp, o que vem do celular chega em até 50 de cada "
          "vez.", numero=MENSAGENS_POR_VEZ),
    Opcao("tamanho_letra", "Tamanho da letra", "Interface", 100,
          "O tamanho das letras da janela principal: listas, caixa de "
          "digitar e botões. Vale na hora.",
          escolhas=((100, "Normal"), (125, "Grande"), (150, "Maior"),
                    (175, "Bem maior"), (200, "Dobro do normal"))),
    Opcao("status_no_titulo",
          "Mostrar status de presença no título da janela",
          "Interface", True,
          "Com uma conversa aberta, o título da janela mostra, depois do "
          "nome, se a pessoa está online, quando foi vista por último ou se "
          "está digitando. No WhatsApp isso exige que a sua conta fique "
          "disponível enquanto a conversa está aberta (o celular pode "
          "deixar de tocar nesse tempo) e, como no próprio WhatsApp, quem "
          "esconde o seu status também não vê o dos outros."),
    Opcao("avisar_chamadas_whatsapp", "Avisar chamadas recebidas",
          "Mídias", True,
          "Quando alguém liga pelo WhatsApp ou pelo Telegram, o TeleZapp "
          "avisa: no WhatsApp, quando ele não consegue atender (sem o "
          "componente de chamadas), abre uma janela dizendo quem está "
          "chamando e se é por voz ou por vídeo, com os botões OK e "
          "Conversar (atenda em outro dispositivo); no Telegram, toca e abre "
          "a janela da chamada para você atender. Desmarcada, o TeleZapp "
          "ignora as chamadas recebidas por completo: sem janela, som nem "
          "fala. No WhatsApp também some a linha da chamada na conversa e "
          "ela não conta como mensagem não lida, como se não tivesse "
          "acontecido. Ele não recusa a chamada: o celular e os outros "
          "aparelhos continuam tocando. Vale para as chamadas que chegarem "
          "depois de desmarcar.", servico="whatsapp,telegram",
          grupo="Chamadas de voz e vídeo"),
    Opcao("listas_do_whatsapp", "Listas do WhatsApp como filtro",
          "Interface", True,
          "Com uma só conta do WhatsApp escolhida na caixa de contas, mostra "
          "a caixa Lista para ver só as conversas de uma das suas listas, e "
          "o botão Listas, nos detalhes da conversa, para pôr ou tirar a "
          "conversa de uma lista. Na primeira vez, o TeleZapp baixa as "
          "listas do celular (o que pode repetir avisos antigos de "
          "conversas arquivadas ou fixadas). Desmarcada, a caixa e o botão "
          "somem e o TeleZapp não baixa nada.", servico="whatsapp"),
    Opcao("chat_de_voz_telegram",
          "Chat de voz de grupo e lives de canal do Telegram",
          CATEGORIA_EXPERIMENTAL, False,
          "Experimental. Liga o botão Entrar no chat de voz (e o item do "
          "menu Chamadas) nos grupos e canais do Telegram. Com um chat de "
          "voz ou uma live em andamento, você entra com o microfone "
          "silenciado, vê a lista de participantes, pode abrir o microfone "
          "ou levantar a mão e é avisado de quem entra e sai (só em chats "
          "pequenos). Nas lives de canal você só ouve. Entrar nunca cria um "
          "chat de voz. Ainda não sabemos se funciona bem em todos os "
          "computadores e contas; se o desempenho não for satisfatório, o "
          "recurso pode sair do TeleZapp nas próximas versões. Desmarcada, "
          "os botões e o item do menu somem.", servico="telegram"),
    Opcao("chat_de_voz_avisar_inicio",
          "Avisar chats de voz e lives que começam nas suas conversas",
          CATEGORIA_EXPERIMENTAL, False,
          "Experimental. Quando um chat de voz ou uma live começa num grupo "
          "ou canal do Telegram, o TeleZapp fala o aviso, e a linha da "
          "conversa na lista passa a dizer \"chat de voz em andamento\" ou "
          "\"live em andamento\" enquanto durar. Ao abrir o TeleZapp, a "
          "marca vale para o que já estava em andamento. Não precisa da "
          "caixa do chat de voz marcada, mas sem ela você não consegue "
          "entrar por aqui. Se o desempenho não for satisfatório, o recurso "
          "pode sair do TeleZapp nas próximas versões.",
          servico="telegram"),
    Opcao("chamada_em_espera",
          "Aviso de segunda chamada (chamada em espera)",
          CATEGORIA_EXPERIMENTAL, False,
          "Experimental. Quando uma chamada chega com outra em andamento, "
          "no WhatsApp ou no Telegram, o TeleZapp avisa em vez de recusar "
          "sozinho: você escolhe entre Recusar, que mantém a chamada atual, "
          "e Encerrar e aceitar, que desliga a atual e atende a nova. Não há "
          "colocar a primeira em espera: ao trocar, ela termina. Com a "
          "chamada em espera tocando, o atalho de atender faz Encerrar e "
          "aceitar e o de recusar recusa só a nova. Desmarcada, a segunda "
          "chamada é recusada em silêncio, como antes. Se o desempenho não "
          "for satisfatório, o recurso pode sair do TeleZapp nas próximas "
          "versões."),
    Opcao("chamada_grupo_whatsapp",
          "Chamadas em grupo do WhatsApp",
          CATEGORIA_EXPERIMENTAL, False,
          "Experimental. Nas conversas de grupo do WhatsApp, o botão Iniciar "
          "chamada (e Ligar para esta conversa, no menu Chamadas) liga para "
          "todos os membros: o WhatsApp só deixa em grupos de até 32 "
          "participantes. Uma chamada em grupo que chega passa a tocar com o "
          "nome do grupo, e a janela da chamada mostra quem está nela. "
          "Só voz, sem vídeo. Desmarcada, uma chamada em grupo que chega "
          "toca como antes, sem ser reconhecida como de grupo. Se o "
          "desempenho não for satisfatório, o recurso pode sair do TeleZapp "
          "nas próximas versões.", servico="whatsapp"),
    Opcao("chamada_em_andamento_whatsapp",
          "Entrar em chamadas em grupo do WhatsApp que já começaram",
          CATEGORIA_EXPERIMENTAL, False,
          "Experimental. Quando chega o convite de uma chamada em grupo, mesmo "
          "sem você atender, o TeleZapp guarda: enquanto a chamada durar, o "
          "botão da conversa do grupo vira Entrar na chamada em "
          "andamento. Só vale para chamadas cujo convite chegou com o "
          "TeleZapp aberto. Precisa da caixa das chamadas em grupo marcada. "
          "Se o desempenho não for satisfatório, o recurso pode sair do "
          "TeleZapp nas próximas versões.", servico="whatsapp"),
    Opcao("chamada_adicionar_whatsapp",
          "Adicionar participantes a uma chamada do WhatsApp",
          CATEGORIA_EXPERIMENTAL, False,
          "Experimental. Com uma chamada em andamento, liga o botão Adicionar "
          "participantes na janela da chamada (e o item do menu Chamadas). "
          "Numa chamada em grupo, oferece os membros do grupo que ainda não "
          "entraram; quem já foi chamado e não entrou é chamado de novo. "
          "Numa chamada individual, oferece os seus contatos salvos, e a "
          "chamada passa a ter várias pessoas, como no WhatsApp. Se o "
          "desempenho não for satisfatório, o recurso pode sair do TeleZapp "
          "nas próximas versões.", servico="whatsapp"),
    Opcao("enquetes_avancadas_whatsapp",
          "Enquetes avançadas do WhatsApp",
          CATEGORIA_EXPERIMENTAL, False,
          "Experimental. Na janela Nova enquete, num chat do WhatsApp, "
          "aparecem mais opções: quiz (com uma resposta certa), ocultar "
          "quem votou, permitir que os participantes acrescentem opções e "
          "um prazo para encerrar. A enquete sai no formato novo do "
          "WhatsApp (o mesmo que o aplicativo do celular usa para esses "
          "tipos). Se o WhatsApp não aceitar, a enquete pode chegar sem "
          "essas características; avise-nos se isso acontecer. Receber e "
          "ver esses tipos de enquete funciona sempre, com ou sem a caixa.",
          servico="whatsapp"),
    Opcao("chamada_por_link_whatsapp",
          "Chamadas por link do WhatsApp",
          CATEGORIA_EXPERIMENTAL, False,
          "Experimental. Entre em uma chamada a partir de um link "
          "call.whatsapp.com: ao abrir o link de uma mensagem (Enter na "
          "mensagem, Abrir link) ou pelo item Entrar em chamada por link, "
          "no menu Chamadas, o TeleZapp entra na chamada. Se o anfitrião "
          "exigir aprovação, você fica na sala de espera até ele deixar "
          "entrar. O item Criar link de chamada, no mesmo menu, cria um "
          "link de voz ou de vídeo para você mandar a outras pessoas. Nos "
          "links de vídeo (e nos de voz, se você ligar a câmera) a sua "
          "câmera e a tela podem ser enviadas, e o vídeo de quem está na "
          "chamada aparece numa grade só. A câmera sempre começa desligada. "
          "Se você administra o link, o menu Chamadas tem a Sala de espera "
          "(deixar entrar ou recusar, com aviso falado de quem pede para "
          "entrar) e a opção de exigir aprovação; qualquer pessoa pode "
          "reagir e levantar a mão, e o TeleZapp avisa quando outros fazem "
          "isso ou compartilham a tela. "
          "Desmarcada, o link abre no navegador, como antes. Se o "
          "desempenho não for satisfatório, o recurso pode sair do "
          "TeleZapp nas próximas versões.", servico="whatsapp"),
    Opcao("chat_de_voz_iniciar",
          "Poder iniciar um chat de voz em grupos e canais do Telegram",
          CATEGORIA_EXPERIMENTAL, False,
          "Experimental. Liga o item Iniciar um chat de voz nesta conversa, "
          "no menu Chamadas, para criar um chat de voz onde ainda não há "
          "nenhum. Isso avisa os membros do grupo ou canal, por isso o "
          "TeleZapp sempre pergunta antes; só administradores podem. Precisa "
          "da caixa do chat de voz marcada. Se o desempenho não for "
          "satisfatório, o recurso pode sair do TeleZapp nas próximas "
          "versões.", servico="telegram"),
    Opcao("chat_de_voz_video",
          "Mostrar o vídeo e a tela compartilhada dos chats de voz e lives",
          CATEGORIA_EXPERIMENTAL, False,
          "Experimental. Pede ao Telegram também a imagem (câmera e tela "
          "compartilhada) de quem aparecer no chat de voz ou na live, e a "
          "mostra na janela do chat de voz. Gasta mais do computador e da "
          "internet, e vale na próxima vez que você entrar. O som funciona "
          "igual com ou sem esta caixa. Precisa da caixa do chat de voz "
          "marcada. Se o desempenho não for satisfatório, o recurso pode "
          "sair do TeleZapp nas próximas versões.", servico="telegram"),
    Opcao("como_me_chamar", "Como me chamar nas mensagens", "Mensagens", "",
          "O nome que aparece no lugar de Você quando o autor é você: nas "
          "mensagens, na lista de conversas, nas reações, nos votos, na busca "
          "e nas conversas salvas. Vale só neste computador; quem recebe não "
          "vê este nome. Vazio, fica Você.",
          texto=True),
    Opcao("falar_novas", "Falar mensagens novas na conversa aberta",
          "Interface", False,
          "O leitor de tela fala o autor e o conteúdo de cada mensagem nova "
          "da conversa que está aberta, com o TeleZapp em uso. Não depende "
          "dos sons.",
          grupo="Conteúdo falado"),
    Opcao("falar_novas_outras_conversas",
          "Falar mensagens novas de outras conversas", "Interface", False,
          "Com o TeleZapp em uso, fala o nome da conversa, o autor e o "
          "conteúdo das mensagens que chegam em outra conversa que não é a "
          "aberta (ou quando nenhuma está aberta). Não depende dos "
          "sons.",
          grupo="Conteúdo falado"),
    Opcao("falar_novas_fora_do_telezapp",
          "Falar mensagens novas fora do TeleZapp", "Interface", False,
          "Fala as mensagens novas também quando você está em outro "
          "programa ou com a janela do TeleZapp minimizada, de qualquer "
          "conversa. Não depende dos sons.",
          grupo="Conteúdo falado"),
    Opcao("falar_voz_preparando",
          "Falar 'Preparando' ao gravar por mais de 20 segundos", "Interface",
          True,
          "Ao parar uma gravação de mais de 20 segundos, fala 'Preparando a "
          "gravação de 0:30...' enquanto o áudio é convertido. Desmarcada, a "
          "conversão continua em segundo plano e a gravação sai sozinha, só "
          "que em silêncio. Não muda os sons nem o envio.",
          grupo="Conteúdo falado"),
    Opcao("falar_voz_enviada",
          "Falar 'Enviando mensagem de voz' depois de enviar", "Interface",
          True,
          "Depois de enviar uma mensagem de voz, fala 'Enviando mensagem de "
          "voz, 174 KB'. Desmarcada, a mensagem sai sem esse anúncio. Não muda "
          "o que é falado ao enviar fotos, vídeos ou outros arquivos.",
          grupo="Conteúdo falado"),
    Opcao("confirmar_envio", "Falar mensagem enviada", "Interface", False,
          "Fala Enviada depois que uma mensagem sai.",
          grupo="Conteúdo falado"),
    Opcao("falar_reacoes", "Falar reações às minhas mensagens", "Interface",
          False,
          "Fala quem reagiu e com qual emoji quando alguém reage a uma "
          "mensagem sua. Desmarcada, a reação só aparece na mensagem.",
          grupo="Conteúdo falado"),
    Opcao("falar_quantas_no_filtro",
          "Falar quantas conversas há ao trocar de filtro", "Interface", True,
          "Ao passar pelas caixas de conta e de tipo de conversa, fala o "
          "filtro e quantas conversas há nele. Desmarcada, só o leitor de "
          "tela lê a opção escolhida.",
          grupo="Conteúdo falado"),
    Opcao("trancadas_exigir_codigo",
          "Esconder as conversas trancadas atrás de um código secreto",
          "Privacidade", True,
          "As conversas que você trancou no celular só aparecem depois que "
          "você digita, no campo de busca de conversas, o código secreto "
          "que definiu em Conversas, Código secreto das conversas "
          "trancadas. Sem código definido elas ficam escondidas. Desmarcada, "
          "o tipo Trancadas no celular aparece sempre.",
          grupo="Conversas trancadas"),
    Opcao("trancadas_esconder_ao_sair",
          "Esconder as conversas trancadas quando eu sair da janela",
          "Privacidade", True,
          "Depois de digitar o código, as trancadas ficam à mostra. Marcada, "
          "elas voltam a ficar escondidas assim que você troca para outro "
          "programa (ou o TeleZapp deixa de estar na frente). Minimizar a "
          "janela e apertar Esc na lista de conversas também as escondem.",
          grupo="Conversas trancadas"),
    Opcao("trancadas_esconder_minutos",
          "Esconder as conversas trancadas depois de quantos minutos sem "
          "usar o teclado (0 para nunca)", "Privacidade", 5,
          "Com as trancadas à mostra, se você não apertar nenhuma tecla do "
          "TeleZapp por este tempo, elas voltam a ficar escondidas e é "
          "preciso digitar o código de novo. 0 desliga.",
          numero=(0, 1440), grupo="Conversas trancadas"),
    Opcao("temporarias_apagar_aqui",
          "Apagar daqui as mensagens temporárias quando o prazo acabar",
          "Privacidade", True,
          "Nas conversas com mensagens temporárias (WhatsApp e Telegram), "
          "cada celular apaga a mensagem no prazo. Marcada, o TeleZapp "
          "também apaga daqui, com a mídia baixada, quando o prazo acaba "
          "(e confere ao abrir, para o que venceu com ele fechado). "
          "Desmarcada, as mensagens ficam guardadas aqui, marcadas como "
          "vencidas. O que o TeleZapp apaga não volta numa nova sincronia."),
    Opcao("seguranca_ao_entrar", "Pedir autenticação ao abrir o TeleZapp",
          "Privacidade", False,
          "Protege o TeleZapp contra o uso por outra pessoa. Ao marcar e dar "
          "OK, você cria um PIN do TeleZapp. Depois, ao abrir, neste "
          "computador vale o Windows Hello (digital, rosto ou o PIN do "
          "Windows), se ele estiver configurado; senão, o PIN do TeleZapp. "
          "Se a pasta do TeleZapp for copiada ou levada para outro "
          "computador, lá vale só o PIN do TeleZapp. Para desmarcar, o "
          "TeleZapp pede a autenticação. Guarde o PIN: sem ele não dá para "
          "abrir. A proteção vale para o uso do programa; os arquivos da "
          "pasta de dados não são cifrados."),
    Opcao("seguranca_usar_hello",
          "Usar o Windows Hello para entrar, quando disponível",
          "Privacidade", True,
          "Com a autenticação ao abrir ligada, usa o Windows Hello deste "
          "computador em vez de pedir o PIN do TeleZapp. Desmarcada, pede "
          "sempre o PIN do TeleZapp."),
    Opcao("limpar_manter_favoritas",
          "Manter as mensagens favoritas ao limpar a conversa",
          "Privacidade", True,
          "Ao limpar uma conversa pelo item do menu \"Limpar a conversa "
          "(aqui e no celular)\", ou várias marcadas de uma vez, as "
          "mensagens favoritas (e as mídias delas) não são apagadas, como já "
          "acontece na janela Limpar mídias e mensagens (o botão \"Limpar a "
          "conversa...\" dos Detalhes). Desmarcada, a limpeza apaga tudo, "
          "inclusive as favoritas."),
    Opcao("manter_apagadas",
          "Manter as mensagens que quem enviou apagar para todos",
          "Privacidade", False,
          "Quando alguém apaga uma mensagem para todos depois de o TeleZapp "
          "tê-la recebido, o WhatsApp e o Telegram tiram o conteúdo do "
          "celular. Marcada, o TeleZapp guarda o que já tinha (texto, "
          "áudio e outras mídias baixadas) e só acrescenta \"apagada pelo "
          "autor\" na linha da mensagem. Desmarcada, ela vira Mensagem "
          "apagada e a mídia baixada é descartada. Só vale para o que "
          "chegar depois de marcar; o que já foi apagado não volta. As "
          "mensagens que você mesmo apaga continuam sendo apagadas."),
    Opcao("manter_apagadas_no_celular",
          "Manter no computador o que eu apagar no WhatsApp do celular",
          "Privacidade", False,
          "Marcada, as mensagens e conversas que você apagar no WhatsApp do "
          "celular, ou em outro aparelho, continuam neste computador, com as "
          "mídias já baixadas. Uma mensagem sua apagada para todos fica "
          "marcada como apagada pelo autor. Desmarcada, o que você apaga lá "
          "também é apagado aqui. O que você apaga pelo próprio TeleZapp "
          "continua sendo apagado neste computador. Só vale para o que for "
          "apagado depois de marcar; o que já saiu não volta."),
    Opcao("verificar_atualizacoes",
          "Avisar quando houver versão nova do TeleZapp", "Atualizações",
          True,
          "Ao abrir, consulta as versões publicadas no GitHub. Sem versão "
          "nova, não diz nada. Havendo, abre a janela com as novidades e você "
          "escolhe se instala. Se responder Não, o TeleZapp pergunta se você "
          "quer \"Não me avise mais sobre essa versão\" (só volta a avisar "
          "quando sair outra) ou \"Talvez mais tarde\" (a janela volta na "
          "próxima vez que abrir o TeleZapp). Só lê a lista de "
          "versões; não baixa nada sem você aceitar. O GitHub vê o endereço "
          "de internet do computador, como em qualquer site. Desmarcada, só "
          "consulta quando você pedir, em Ajuda, Verificar atualizações."),
    Opcao("atualizacoes_periodicas",
          "Buscar atualizações periodicamente com o TeleZapp aberto",
          "Atualizações", True,
          "Além de consultar ao abrir, volta a consultar de tempos em tempos "
          "enquanto o TeleZapp estiver aberto, mesmo em segundo plano. As "
          "regras são as mesmas: sem versão nova, não diz nada. Em segundo "
          "plano, o TeleZapp só avisa em voz alta, e a janela com as novidades "
          "abre quando você o trouxer de volta. Durante uma chamada, ou com "
          "outra janela aberta, ele espera."),
    Opcao("atualizacoes_intervalo", "Intervalo da busca por atualizações",
          "Atualizações", 24,
          "De quanto em quanto tempo consultar, enquanto o TeleZapp estiver "
          "aberto.",
          escolhas=((1, "1 hora"), (6, "6 horas"), (12, "12 horas"),
                    (24, "24 horas"))),
    Opcao("depuracao", "Modo de depuração", "Avançado", False,
          "Guarda, no seu computador, a estrutura original das últimas 500 "
          "mensagens do WhatsApp para o menu Depurar mostrar. Contém o texto "
          "e os telefones dessas mensagens. Ao desligar, tudo é apagado."),
    Opcao("log_detalhado_whatsapp", "Registro técnico detalhado do WhatsApp",
          "Avançado", False,
          "Grava no log cada pacote que o WhatsApp troca com o TeleZapp "
          "(sem o texto das mensagens, que vai criptografado). Serve para "
          "investigar erros de envio; deixa o log grande. Vale na próxima "
          "abertura do TeleZapp."),
    Opcao("previa_links", "Prévia dos links nas mensagens", "Mensagens",
          "completa",
          "Quando quem enviou mandou junto a prévia de um link (título e "
          "descrição), ela é lida na linha da mensagem, antes do texto, "
          "seja a mensagem só o link ou um texto com link. O TeleZapp não abre "
          "o link para montar uma prévia. Nos detalhes da mensagem (Alt "
          "Enter) a prévia aparece sempre.",
          (("completa", "Título e descrição"), ("titulo", "Só o título"),
           ("nenhuma", "Não ler a prévia")),
          grupo="Prévia de links"),
    Opcao("previa_receber", "Buscar a prévia dos links recebidos",
          "Mensagens", False,
          "Quando chega uma mensagem com um link sem prévia, o TeleZapp abre "
          "a página para ler o título e a descrição. O site fica sabendo do "
          "IP deste computador e de que o link foi aberto. Só vale para "
          "mensagens que chegam com o programa aberto; endereços da rede "
          "local nunca são abertos.",
          grupo="Prévia de links"),
    Opcao("previa_enviar", "Gerar a prévia dos links que eu envio",
          "Mensagens", False,
          "No WhatsApp, o TeleZapp abre o primeiro link da mensagem que você "
          "envia e manda junto o título e a descrição, para quem recebe ver a "
          "prévia (o envio espera até 5 segundos). No Telegram, desmarcada, "
          "a mensagem sai sem a prévia de link. O site fica sabendo do IP "
          "deste computador.",
          grupo="Prévia de links"),
    Opcao("ortografia_idioma", "Idioma do corretor ortográfico", "Mensagens",
          "pt-BR",
          "O idioma do dicionário que Verificar ortografia (F7, menu "
          "Mensagens) usa na caixa de digitar. Os dicionários são os do "
          "Windows: se o idioma não estiver instalado, o corretor avisa. "
          "Em Configurações do Windows, Hora e idioma, Idioma e região, "
          "adicione o idioma para instalar o dicionário.",
          (("pt-BR", "Português do Brasil"), ("pt-PT", "Português de Portugal"),
           ("en-US", "Inglês dos Estados Unidos"), ("es-ES", "Espanhol"))),
    Opcao("ortografia_ao_enviar", "Avisar de erros de ortografia ao enviar",
          "Mensagens", False,
          "Ao enviar uma mensagem de texto, se o corretor achar palavras "
          "com erro, pergunta se você quer corrigir antes ou enviar assim "
          "mesmo. Desmarcada, a mensagem sai direto e você corrige quando "
          "quiser com Verificar ortografia (F7)."),
    Opcao("mostrar_atalhos", "Mostrar as teclas de atalho nos controles",
          "Atalhos", True,
          "Escreve a tecla de atalho no nome dos botões e dos itens de menu "
          "que têm uma, por exemplo \"Enviar (Enter)\" ou \"Escrever "
          "mensagem, Control E\". Desmarcada, os nomes ficam sem o atalho "
          "e os atalhos continuam funcionando. Os atalhos podem ser "
          "mudados em Configurações, Atalhos."),
    Opcao("trazer_contatos_ao_abrir",
          "Obter os contatos das contas ao abrir o TeleZapp", "Interface",
          True,
          "Ao conectar cada conta, copia para a agenda do TeleZapp os "
          "contatos que ela já tem (os salvos no celular ou só no "
          "WhatsApp), para as conversas e os autores aparecerem com o nome "
          "e não com o número. Não troca o nome de quem você já nomeou "
          "aqui. Desmarcada, só entram os contatos que você adicionar. A "
          "mesma caixa está na janela Contatos."),
    Opcao("varrer_ao_reconectar",
          "Buscar sozinho as mensagens que faltam ao reconectar", "Mensagens",
          True,
          "Quando o TeleZapp reconecta depois de ficar fechado, o WhatsApp "
          "entrega só a parte final das mensagens que chegaram nesse tempo. "
          "Com esta caixa marcada, o TeleZapp pede ao celular, uma conversa "
          "de cada vez, as mensagens que ficaram faltando antes dessas e "
          "avisa quando encontra alguma. O celular precisa estar ligado e "
          "com internet. Desmarcada, só a busca que você pede em Buscar "
          "mensagens que faltam no celular."),
    Opcao("falar_fim_da_busca_sozinha",
          "Falar quando a busca sozinha de mensagens terminar", "Mensagens",
          True,
          "Ao reconectar, o TeleZapp busca no celular as mensagens que "
          "faltam, uma conversa de cada vez. Marcada, ele fala quando a "
          "busca acaba em todas as conversas, dizendo quantas mensagens "
          "encontrou ou que não faltava nenhuma. Desmarcada, o aviso "
          "aparece só na barra de status e no registro.",),
    Opcao("compartilhar_uso",
          "Compartilhar informações de uso com o desenvolvedor", "Avançado",
          False,
          "Ajuda a saber quais recursos ficam lentos ou dão erro em outros "
          "computadores. Marcada, o TeleZapp envia, no máximo uma vez por "
          "dia, só números: versão do programa e do Windows, leitor de tela, "
          "quantas contas de cada serviço, faixa de quantidade de conversas, "
          "recursos experimentais ligados, tempo de abertura e do F5, e o "
          "nome e o tempo das ações da janela que demoraram ou deram erro. "
          "Nunca vão mensagens, nomes, telefones, arquivos nem registros "
          "(logs). O identificador é sorteado e não tem ligação com contas. "
          "Para ver o texto exato, use Ajuda, Ver o que o compartilhamento "
          "de uso envia. Desmarcada, nada é enviado."),
    Opcao("manter_posicao_fixadas", "Manter a posição das conversas fixadas",
          "Interface", False,
          "Marcada, as conversas fixadas ficam no topo da lista sempre na "
          "mesma ordem, e uma mensagem nova não sobe a conversa para o "
          "primeiro lugar entre as fixadas. Ao marcar, a ordem de partida é a "
          "que a lista tem naquele momento; uma conversa que você fixa depois "
          "entra no primeiro lugar, e a que você desafixa sai da ordem. "
          "Desmarcada, as fixadas ficam no topo, mas a que recebeu mensagem "
          "mais recentemente fica em primeiro lugar entre elas. As conversas "
          "que não estão fixadas seguem sempre pela mensagem mais recente."),
    Opcao("ocultar_contatos_duplicados", "Ocultar contatos duplicados",
          "Interface", True,
          "Nas listas de contatos (Contatos e a escolha de quem recebe em "
          "Nova mensagem e Nova chamada), mostra uma vez só a pessoa que "
          "aparece repetida: com o mesmo telefone, ou com o mesmo nome "
          "quando uma das cópias não tem telefone. Duas pessoas com o mesmo "
          "nome e telefones diferentes continuam as duas. Desmarcada, a "
          "lista mostra tudo o que está guardado. O mesmo botão está na "
          "janela Contatos."),
    Opcao("segundo_plano", "Continuar em segundo plano ao fechar a janela",
          "Sistema", False,
          "Fechar a janela (o botão de fechar ou Alt F4) só a minimiza: o "
          "TeleZapp segue conectado, dando os avisos de mensagens, o botão "
          "continua na barra de tarefas e um ícone fica na área de "
          "notificação do Windows. Para voltar, use a barra de tarefas, o "
          "ícone ou o atalho de chamar o TeleZapp (Configurações, Atalhos, "
          "\"Chamar o TeleZapp\"). Para encerrar de verdade, use Sair, em "
          "Ferramentas (Control Q), o botão Sair ou o menu do ícone."),
    Opcao("abrir_links_no_telezapp",
          "Oferecer o TeleZapp para abrir links do Telegram e do WhatsApp",
          "Sistema", True,
          "Faz o TeleZapp aparecer entre as opções do Windows para abrir links "
          "tg:// e whatsapp://. Quem abre continua sendo o programa que você "
          "escolheu: troque em Configurações do Windows, Aplicativos padrão."),
    Opcao("avisar_pedidos_de_entrada",
          "Avisar pedidos de entrada nos meus grupos", "Mensagens", False,
          "Nos grupos do WhatsApp em que você é administrador e que exigem "
          "aprovação, o TeleZapp olha se há pedidos de entrada esperando: "
          "ao abrir e, depois, de tempos em tempos (veja o intervalo "
          "abaixo). Ao abrir, mostra uma janela de aviso com quantos pedidos "
          "esperam e em quais grupos; depois, só quando chegar pedido novo. "
          "A janela pergunta se você quer ver os pedidos agora; a lista "
          "continua em Detalhes do grupo. Desmarcada, o TeleZapp não "
          "consulta nada."),
    Opcao("pedidos_de_entrada_intervalo",
          "Intervalo da consulta de pedidos de entrada", "Mensagens", 15,
          "De quanto em quanto tempo consultar os pedidos, enquanto o "
          "TeleZapp estiver aberto.",
          escolhas=((5, "5 minutos"), (15, "15 minutos"), (30, "30 minutos"),
                    (60, "1 hora"))),
    Opcao("avisar_disco_externo",
          "Avisar quando os dados estão em disco externo", "Sistema", True,
          "Se a pasta de dados do TeleZapp está em um pendrive, disco "
          "externo (USB) ou disco de rede, mostra ao abrir um aviso com os "
          "cuidados para não danificar o banco de conversas: fechar o "
          "TeleZapp antes de ejetar o disco, não deixar o computador "
          "suspender com o programa aberto e usar Backup e Restaurar para "
          "levar os dados para outro lugar. Desmarque para não ver mais "
          "esse aviso."),
    Opcao("iniciar_com_windows", "Abrir o TeleZapp ao entrar no Windows",
          "Sistema", False,
          "Abre o TeleZapp sozinho quando você entra na sua conta do "
          "Windows. Com \"Continuar em segundo plano\" ligado, ele abre "
          "minimizado na barra de tarefas, sem tirar o foco do que você "
          "está fazendo."),
    Opcao("prioridade_abertura", "Dar prioridade ao TeleZapp ao abrir",
          "Sistema", True,
          "Ao abrir, o TeleZapp pede ao Windows prioridade acima do normal "
          "(e sai do modo de economia de energia) por cerca de meio minuto, "
          "para não esperar atrás dos outros programas que abrem junto, "
          "como ao ligar o computador. Se o TeleZapp demora a responder "
          "quando é aberto depois de outros aplicativos, deixe marcada. "
          "Vale na próxima abertura.", reabrir=True),
    # As duas opcoes abaixo aparecem em Gerenciar contas (nao em
    # Configuracoes): ver Janela._gerenciar_contas
    Opcao("contas_em_pastas",
          "Guardar os dados de cada conta em uma pasta separada",
          "Sistema", False,
          "Cada conta tem uma pasta própria, com o banco de conversas, as "
          "sessões e as mídias dentro dela. Desmarcada, todas as contas "
          "dividem os mesmos dados na pasta de dados do TeleZapp, como nas "
          "versões antigas: um banco só. Ao marcar, na próxima abertura o "
          "TeleZapp separa os dados de cada conta; ao desmarcar, ele os "
          "junta de novo. Vale na próxima abertura.",
          reabrir=True),
    Opcao("contas_pasta", "Pasta dos dados das contas", "Sistema", "",
          "A pasta em que ficam as pastas das contas, uma subpasta para "
          "cada conta. Vazia, usa a pasta padrão do TeleZapp. Só vale com "
          "a separação por conta marcada. Na próxima abertura, o que "
          "estiver na pasta padrão vai para a escolhida (no mesmo disco "
          "é instantâneo; em outro disco é preciso ter espaço livre para "
          "tudo).",
          texto=True, pasta=True, reabrir=True),
    Opcao("barra_abre_comandos",
          "Barra na caixa de digitar abre os comandos do robô",
          "Mensagens", True,
          "No Telegram, uma barra digitada na caixa vazia mostra os comandos "
          "do robô da conversa. Sem robô, a barra fica como um caractere "
          "qualquer.", servico="telegram"),
    Opcao("formatacao_das_mensagens", "Formatação do texto das mensagens",
          "Mensagens", "original",
          "O que fazer com os asteriscos, sublinhados e outros símbolos que "
          "marcam o texto. No WhatsApp, *texto* é negrito, _texto_ é "
          "itálico, ~texto~ é tachado e `texto` é código; bots e IAs "
          "escrevem em Markdown: **texto** é negrito, # é título e - abre um "
          "item. Como veio: o texto com os símbolos, sem mudança. Anunciar: "
          "os símbolos viram palavras, como \"negrito: texto\", e o "
          "leitor de tela diz o que são. Tirar os símbolos: só o texto. "
          "Vale para o que você lê e ouve; copiar, salvar e exportar usam "
          "o texto original. Só pares bem formados são mudados.",
          escolhas=(("original", "Como veio, com os símbolos"),
                    ("anunciar", "Anunciar a formatação (negrito: texto)"),
                    ("tirar", "Tirar os símbolos"))),
    Opcao("botoes_midia", "Mostrar botões da mídia", "Mensagens", True,
          "Numa mensagem com foto, vídeo, áudio, voz, documento ou "
          "figurinha, botões logo depois da lista de mensagens, que o Tab "
          "alcança: abrir ou reproduzir, baixar ou salvar, copiar a mídia e "
          "a inteligência artificial. Desmarcado, as mesmas ações ficam no "
          "menu de contexto e nos detalhes da mensagem (Alt+Enter).",
          grupo="Botões depois das mensagens"),
    Opcao("botoes_resposta", "Mostrar botões de resposta e opções", "Mensagens",
          True,
          "Botões e opções que vêm na mensagem (de robôs, enquetes, "
          "convites), logo depois da lista de mensagens. Desmarcado, eles "
          "ficam nos detalhes da mensagem (Alt+Enter).",
          grupo="Botões depois das mensagens"),
    Opcao("botoes_links", "Mostrar links", "Mensagens", True,
          "Um botão para cada link do texto ou da legenda, logo depois da "
          "lista de mensagens. Desmarcado, os links ficam nos detalhes da "
          "mensagem (Alt+Enter).",
          grupo="Botões depois das mensagens"),
    Opcao("botoes_pessoas", "Mostrar pessoas mencionadas", "Mensagens", True,
          "Um botão para cada pessoa mencionada, que abre a conversa com "
          "ela, logo depois da lista de mensagens. Desmarcado, as pessoas "
          "ficam nos detalhes da mensagem (Alt+Enter).",
          grupo="Botões depois das mensagens"),
    Opcao("foco_ao_abrir_conversa", "Foco ao abrir uma conversa", "Mensagens",
          "mensagens",
          "Para onde vai o foco quando você abre uma conversa. Na lista de "
          "mensagens, o leitor de tela lê o ponto em que você parou ou a "
          "primeira não lida. Na caixa de digitar, você já pode escrever; "
          "as mensagens ficam a um Shift Tab, ou use o atalho de ir para as "
          "mensagens. Numa conversa só de leitura o foco vai sempre para a "
          "lista de mensagens.",
          escolhas=(("mensagens", "Na lista de mensagens"),
                    ("caixa", "Na caixa de digitar"))),
    Opcao("enter_envia", "Enter na caixa de digitar envia a mensagem",
          "Mensagens", True,
          "Marcada (o padrão), Enter envia e Shift Enter quebra a linha; "
          "Control Enter também envia. Desmarcada, só Control Enter envia e "
          "Enter quebra a linha, como no Telegram Web e no Gmail. A tecla "
          "de enviar também pode ser mudada em Atalhos, na função \"Enviar "
          "a mensagem digitada\"."),
    Opcao("ocultar_telefone_sem_nome",
          "Ocultar o telefone de remetentes sem nome", "Mensagens", False,
          "Quando o TeleZapp não acha o nome de quem enviou, a mensagem começa "
          "direto pelo conteúdo, sem o número de telefone, na lista de "
          "mensagens, na fala e na lista de conversas. O telefone continua "
          "nos detalhes e nas conversas salvas.",),
    Opcao("mostrar_avisos_de_membros",
          "Mostrar os avisos de entrada e saída de membros", "Mensagens", True,
          "Nos grupos do Telegram e do WhatsApp, mostra na lista de mensagens "
          "quem entrou, saiu, foi adicionado ou removido. Esses avisos não "
          "tocam som nem são falados ao chegar. Desmarcada, ficam escondidos, "
          "mas o Telegram ainda pode contá-los como não lidas ao abrir o "
          "programa."),
    Opcao("falar_descricoes", "Falar a descrição de cada opção",
          "Interface", True,
          "Na janela de configurações, o TeleZapp fala a explicação de cada "
          "opção logo depois que você chega nela. Desmarcada, a explicação "
          "só é falada com F1.",
          grupo="Conteúdo falado"),
    Opcao("pasta_salvar", "Pasta dos arquivos salvos", "Mídias", "",
          "A pasta onde ficam os arquivos que você salva: mídias, documentos, "
          "conversas, logs e textos. Vazia, a janela de salvar decide. Não "
          "vale para o backup, que tem a pasta dele.",
          texto=True, pasta=True),
    Opcao("salvar_direto", "Guardar direto na pasta, sem perguntar", "Mídias",
          False,
          "Marcada, o arquivo vai direto para a pasta definida e o TeleZapp "
          "diz onde ficou; se já houver um com o mesmo nome, nada é "
          "sobrescrito e o novo ganha um número. Desmarcada, a janela de "
          "salvar abre em cada salvamento, começando nessa pasta. Só vale com "
          "uma pasta definida.",),
    Opcao("gravar_som_com_microfone",
          "Gravar também o microfone ao gravar o som do computador",
          "Mídias", True,
          "Na janela \"Gravar o som do computador\", a caixa \"Gravar também "
          "o microfone\" já vem marcada: o que o computador toca e o que "
          "você fala entram juntos na mesma nota de voz. Dá para ligar e "
          "desligar o microfone durante a gravação. Desmarcada, a janela "
          "grava só o som do computador. O atalho Control Shift S grava sempre "
          "só o som do computador, e o Control Shift B grava sempre o som do "
          "computador com o microfone.",
          grupo="Gravação"),
    Opcao("gravar_microfone_estereo", "Gravar o microfone em estéreo",
          "Mídias", False,
          "Grava o microfone em dois canais, se ele tiver dois (muitos "
          "microfones têm um só: aí a gravação continua mono). Desmarcada, "
          "grava em mono, o formato comum das mensagens de voz. No WhatsApp "
          "a gravação em estéreo também é mensagem de voz (arquivo M4A, "
          "AAC), que toca no iPhone, com o controle de velocidade. No "
          "Telegram, a gravação em estéreo vai como áudio comum.",
          grupo="Gravação"),
    Opcao("gravar_som_estereo", "Gravar o som do computador em estéreo",
          "Mídias", False,
          "Grava em dois canais o que o computador toca, como música e "
          "vídeos, também quando o microfone entra junto. Desmarcada, grava "
          "em mono. No WhatsApp a gravação em estéreo também é mensagem de "
          "voz (arquivo M4A, AAC), que toca no iPhone, com o controle de "
          "velocidade. No Telegram, vai como áudio comum.",
          grupo="Gravação"),
    Opcao("qualidade_gravacao_mono", "Qualidade da gravação em mono",
          "Mídias", 64,
          "Quantos kbps a mensagem de voz gravada em mono usa. Mais kbps, "
          "som melhor e arquivo maior. 64 kbps é bom para voz.",
          escolhas=tuple((k, "%d kbps" % k) for k in
                         (32, 48, 64, 96, 128, 160, 192, 256)),
          grupo="Gravação"),
    Opcao("qualidade_gravacao_estereo", "Qualidade da gravação em estéreo",
          "Mídias", 128,
          "Quantos kbps a gravação em estéreo usa, somando os dois canais. "
          "128 kbps é bom para música.",
          escolhas=tuple((k, "%d kbps" % k) for k in
                         (32, 48, 64, 96, 128, 160, 192, 256)),
          grupo="Gravação"),
    Opcao("calar_avisos_ao_gravar",
          "Calar os avisos de mensagens enquanto grava voz",
          "Mídias", True,
          "Enquanto uma gravação de voz está em andamento (inclusive "
          "pausada), o TeleZapp não toca os sons nem fala os avisos de "
          "mensagens novas, reações, votos de enquete e mensagens editadas "
          "ou apagadas, para não entrarem na gravação. Os avisos que "
          "chegam nesse tempo não são repetidos depois; as mensagens "
          "continuam na lista. Chamadas e os sons da própria gravação "
          "seguem normais.",
          grupo="Gravação"),
    Opcao("calar_avisos_em_chamada",
          "Calar os avisos de mensagens durante uma chamada",
          "Mídias", False,
          "Enquanto você está numa chamada (conectando ou conversando), o "
          "TeleZapp não toca os sons nem fala os avisos de mensagens novas, "
          "reações, votos de enquete e mensagens editadas ou apagadas. Serve "
          "para a outra pessoa não ouvir os bips quando você compartilha o "
          "som do computador. Os avisos que chegam nesse tempo não são "
          "repetidos depois; as mensagens continuam na lista. O toque e os "
          "sons da própria chamada seguem normais.",
          grupo="Chamadas de voz e vídeo"),
    Opcao("volume_gravacao", "Volume da gravação, em porcentagem",
          "Mídias", 100,
          "Aumenta ou diminui o volume do que é gravado: microfone, som do "
          "computador ou os dois. 100 grava como chega; 200 grava com o "
          "dobro do volume; 50, com a metade. Um volume alto demais pode "
          "distorcer o som.",
          numero=(10, 400),
          grupo="Gravação"),
    Opcao("barra_de_progresso",
          "Janela com barra de progresso em downloads e envios longos",
          "Mídias", True,
          "Quando um download que você pediu, ou o envio de um arquivo "
          "grande, demora mais de um segundo, abre uma janela com uma barra "
          "de progresso. O leitor de tela acompanha a "
          "barra (o NVDA toca bipes que sobem do grave ao agudo conforme ela "
          "avança). O TeleZapp não fala nem escreve a "
          "porcentagem: quem decide se a barra fala, bipa, os dois ou fica "
          "quieta é a configuração de barras de progresso do próprio leitor de "
          "tela (no NVDA, Configurações, Apresentação de objetos). No "
          "download a "
          "janela tem o botão Cancelar (Esc também cancela). Com a janela "
          "aberta, a fala do avanço (Porcentagem falada no download) fica "
          "quieta. "
          "Desmarcada, o avanço só aparece no título, na barra de situação "
          "e na fala. Atualizar, instalar e fazer backup sempre mostram a "
          "barra.",
          grupo="Download de mídias"),
    Opcao("audio_janela", "Ao tocar um áudio ou mensagem de voz", "Mídias",
          "sem",
          "Só tocar começa a tocar sem abrir janela: Enter de novo pausa e "
          "continua, e Esc para. O player em janela tem avançar, voltar e "
          "posição.",
          (("sem", "Só tocar, sem janela"),
           ("janela", "Abrir a janela do player")),
          grupo="Reprodução de áudio"),
    Opcao("enter_audio", "O que o Enter faz numa mensagem de voz ou áudio", "Mídias",
          "abrir", "O que o Enter faz numa mensagem de voz ou áudio. "
          "Transcrever usa os provedores de Inteligência artificial e, se a "
          "transcrição já existe, só a mostra. Control O sempre reproduz e "
          "Control B sempre só baixa.",
          (("abrir", "Reproduzir (baixa antes, se preciso)"),
           ("baixar", "Só baixar"),
           ("ia", "Transcrever (ou mostrar a transcrição)")),
          grupo="Enter nas mídias"),
    Opcao("enter_imagem", "O que o Enter faz numa foto ou figurinha", "Mídias", "abrir",
          "O que o Enter faz numa foto ou figurinha. Descrever usa os "
          "provedores de Inteligência artificial e, se a descrição já "
          "existe, só a mostra.",
          (("abrir", "Abrir (baixa antes, se preciso)"),
           ("baixar", "Só baixar"),
           ("ia", "Descrever (ou mostrar a descrição)")),
          grupo="Enter nas mídias"),
    Opcao("enter_video", "O que o Enter faz num vídeo", "Mídias", "abrir",
          "O que o Enter faz num vídeo. Descrever usa o provedor de "
          "Inteligência artificial que aceita vídeo e, se a descrição já "
          "existe, só a mostra.",
          (("abrir", "Abrir (baixa antes, se preciso)"),
           ("baixar", "Só baixar"),
           ("ia", "Descrever (ou mostrar a descrição)")),
          grupo="Enter nas mídias"),
    Opcao("enter_pdf", "O que o Enter faz num PDF", "Mídias", "abrir",
          "O que o Enter faz num documento PDF. Converter usa os provedores "
          "de Inteligência artificial e, se o texto já existe, só o mostra.",
          (("abrir", "Abrir (baixa antes, se preciso)"),
           ("baixar", "Só baixar"),
           ("ia", "Converter em texto acessível (ou mostrar o texto)")),
          grupo="Enter nas mídias"),
    Opcao("audio_sequencia", "Sequência de áudios", "Mídias", "sim",
          "O que acontece quando um áudio ou mensagem de voz termina (sem "
          "janela). Todos da conversa: toca o próximo áudio, pulando as "
          "mensagens que não são áudio. Só os seguidos: toca os áudios um "
          "depois do outro e para na primeira mensagem que não for áudio, "
          "como um texto ou uma foto. Baixa antes, se preciso. Esc para.",
          (("sim", "Tocar todos os áudios da conversa em sequência"),
           ("bloco", "Tocar só os áudios seguidos, até uma mensagem que "
                     "não seja áudio"),
           ("nao", "Parar quando o áudio terminar")),
          grupo="Sequência de áudio"),
    Opcao("audio_passo_velocidade", "Quanto a velocidade do áudio muda a cada vez", "Mídias",
          0.25,
          "De quanto em quanto a velocidade de reprodução do áudio muda "
          "quando você a aumenta ou diminui.",
          ((0.25, "De 0,25 em 0,25 (de 0,25x até 3x)"),
           (0.5, "De 0,5 em 0,5 (de 0,5x até 3x)"),
           (1.0, "De 1 em 1 (1x, 2x e 3x)")),
          grupo="Reprodução de áudio"),
    Opcao("audio_velocidade", "Velocidade do áudio", "Mídias", 1.0,
          "Velocidade de reprodução de áudios e mensagens de voz, de 0,25x a "
          "3x, sem mudar o tom da voz. Os valores disponíveis dependem do "
          "passo escolhido.",
          tuple((v, ("%g" % v).replace(".", ",") + "x") for v in (
              0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75,
              3.0)),
          grupo="Reprodução de áudio"),
    Opcao("falar_pulo_audio",
          "Falar o ponto do áudio ao avançar ou voltar com as teclas",
          "Mídias", True,
          "Ao avançar ou voltar um áudio ou mensagem de voz com as teclas "
          "(as setas do player e os atalhos do menu Mídias), fala em que "
          "ponto ele ficou, por exemplo 0:35 de 1:10. Desmarcada, o áudio "
          "pula em silêncio. Os botões Voltar e Avançar do player sempre "
          "falam.",
          grupo="Reprodução de áudio"),
    Opcao("falar_quem_toca",
          "Ao tocar o primeiro áudio, falar de quem é e a duração",
          "Mídias", False,
          "Quando um áudio ou mensagem de voz começa a tocar, fala o que é, "
          "de quem e quanto dura. Desmarcada, não fala nada: o próprio áudio começa a tocar. Vale para o "
          "primeiro áudio; os que tocam depois dele, na sequência, seguem as "
          "opções \"Na sequência de áudios\" logo abaixo.",
          grupo="Reprodução de áudio"),
    Opcao("seq_falar_proximo", "Na sequência de áudios, falar Próximo áudio",
          "Mídias", False,
          "A cada áudio que começa na sequência, fala Próximo áudio antes "
          "do resto. Só vale quando um áudio toca depois do outro; o "
          "primeiro segue a opção Ao tocar o primeiro áudio, falar de "
          "quem é e a duração.",
          grupo="Sequência de áudio"),
    Opcao("seq_falar_tipo",
          "Na sequência de áudios, falar se é mensagem de voz ou áudio",
          "Mídias", False,
          "Fala Tocando mensagem de voz, ou Tocando áudio, a cada áudio da "
          "sequência.",
          grupo="Sequência de áudio"),
    Opcao("seq_falar_quem", "Na sequência de áudios, falar de quem é",
          "Mídias", False,
          "Fala o nome de quem enviou cada áudio da sequência. Em áudio "
          "seu, fala seu ou sua.",
          grupo="Sequência de áudio"),
    Opcao("seq_falar_duracao", "Na sequência de áudios, falar a duração",
          "Mídias", False,
          "Fala quanto dura cada áudio da sequência, por exemplo 12 "
          "segundos.",
          grupo="Sequência de áudio"),
    Opcao("seq_falar_velocidade",
          "Na sequência de áudios, falar a velocidade",
          "Mídias", False,
          "Fala a velocidade, por exemplo a 1,5x, quando ela não é a "
          "normal. Desmarcando todas as opções da sequência, nada é falado "
          "entre um áudio e outro.",
          grupo="Sequência de áudio"),
    Opcao("seq_falar_fim", "Na sequência de áudios, falar Fim da sequência",
          "Mídias", False,
          "Quando o último áudio da sequência termina e não há outro para "
          "tocar, fala Fim da sequência. Só vale se pelo menos dois áudios "
          "tocaram em sequência; um áudio sozinho não anuncia nada. "
          "Interromper o áudio com Esc também não anuncia.",
          grupo="Sequência de áudio"),
    Opcao("seq_acompanhar", "Na sequência de áudios, o cursor acompanha o "
          "áudio que toca", "Mídias", False,
          "Quando um áudio da sequência começa a tocar, a seleção da lista de "
          "mensagens passa para ele, sem tirar o foco de onde você está. "
          "Assim, ao voltar para a lista, você já está no áudio que tocou por "
          "último. Desmarcada, a seleção fica onde você deixou. Só vale se a "
          "conversa dos áudios estiver aberta.",
          grupo="Sequência de áudio"),
    Opcao("chamada_janela_ao_tocar", "Abrir a janela da chamada quando "
          "alguém me ligar", "Mídias", True,
          "Marcada, ao receber uma chamada o TeleZapp abre a janela da "
          "chamada e põe o foco no botão Atender: se você estiver digitando, "
          "a barra de espaço ou o Enter podem atender sem querer. Desmarcada, "
          "a janela não abre e o foco não sai de onde está: o TeleZapp toca e "
          "diz quem está ligando, e você atende ou recusa pelos atalhos "
          "Atender a chamada que está tocando e Recusar a chamada que está "
          "tocando, em Configurações, Atalhos, categoria Chamadas. A janela "
          "abre depois que você atende. Sem um atalho de atender escolhido, a "
          "janela abre mesmo assim, senão não haveria como atender. Vale "
          "para as chamadas que chegarem depois de mudar.",
          grupo="Chamadas de voz e vídeo", servico="whatsapp,telegram"),
    Opcao("chamada_eco", "Cancelar o eco nas chamadas de voz", "Mídias", True,
          "Quando você ouve a chamada pelo alto-falante, o microfone capta "
          "a voz da outra pessoa e ela se ouve de volta. Marcada, o TeleZapp "
          "tira esse eco do que envia, também quando ele volta atrasado "
          "por uma mesa de som com retorno. Use fone para o melhor "
          "resultado. Vale a partir da próxima chamada. Desmarque se a "
          "outra pessoa disser que sua voz sai cortada ou abafada.",
          grupo="Chamadas de voz e vídeo"),
    Opcao("chamada_ruido", "Reduzir o ruído do microfone nas chamadas de "
          "voz", "Mídias", True,
          "Diminui ruídos constantes captados pelo microfone, como "
          "ventilador, ar-condicionado e chiado. Vale a partir da próxima "
          "chamada.",
          grupo="Chamadas de voz e vídeo"),
    Opcao("video_camera_ao_atender", "Ligar a câmera ao atender uma chamada "
          "de vídeo", "Mídias", False,
          "Desmarcada, ao atender uma chamada de vídeo a sua câmera fica "
          "desligada: você ouve e vê a outra pessoa, mas ela não vê você, e "
          "a câmera pode ser ligada na janela da chamada. Marcada, a câmera "
          "liga junto com a chamada. Quem liga uma chamada de vídeo sempre "
          "começa com a câmera ligada.",
          grupo="Chamadas de voz e vídeo"),
    Opcao("chamada_retornar_sem_audio", "Ligar de volta quando a chamada "
          "recebida ficar sem som", "Mídias", True,
          "Às vezes você atende uma chamada do WhatsApp e o som da outra "
          "pessoa não chega. Marcada, depois de 20 segundos sem som o "
          "TeleZapp encerra a chamada e liga de volta para a mesma pessoa, "
          "o que costuma funcionar. A pessoa verá a chamada cair e receberá "
          "outra. Desmarcada, o TeleZapp só encerra e avisa.",
          grupo="Chamadas de voz e vídeo"),
    Opcao("chamada_retorno", "Tirar das chamadas de voz o retorno da minha "
          "voz", "Mídias", True,
          "Quando a outra pessoa usa uma mesa de som com retorno (monitor) "
          "ou ouve a chamada pelo alto-falante, a sua voz volta para você, "
          "atrasada, misturada com a dela, e você se ouve. Marcada, o "
          "TeleZapp mede se isso está acontecendo e, só então, tira esse "
          "retorno do que você ouve. Sem retorno, a voz dela passa "
          "intacta. Vale a partir da próxima chamada. A solução de verdade "
          "é do lado dela: um retorno sem a sua voz (mix-minus).",
          grupo="Chamadas de voz e vídeo"),
    Opcao("midias_baixar", "Quando baixar as mídias", "Mídias", "demanda",
          "Sob demanda baixa só quando você abre a mídia. Automático baixa "
          "ao receber, até o limite escolhido.",
          (("demanda", "Só quando eu abrir"),
           ("automatico", "Automaticamente ao receber")),
          grupo="Download de mídias"),
    Opcao("midias_limite_auto_mb", "Tamanho máximo do download automático", "Mídias",
          20, "Mídias maiores que isto (em MB) não baixam sozinhas.",
          ((5, "5 MB"), (10, "10 MB"), (20, "20 MB"), (50, "50 MB"),
           (100, "100 MB")),
          grupo="Download de mídias"),
    Opcao("midias_passo_progresso", "Falar o avanço do download",
          "Mídias", 25,
          "De quanto em quanto o avanço de um download pedido por você, ou "
          "de um arquivo que você envia, é falado (por exemplo, 10 por "
          "cento, 20 por cento). No WhatsApp o avanço só existe com a DLL do "
          "neonize que o TeleZapp usa; com a oficial, a mídia vai e vem "
          "inteira de uma vez, sem porcentagens no meio. A barra de situação "
          "e o título da janela mostram o avanço mesmo com a fala desligada.",
          ((25, "A cada 25%"), (20, "A cada 20%"), (10, "A cada 10%"),
           (5, "A cada 5%"), (1, "A cada 1%"), (0, "Não falar o avanço")),
          grupo="Download de mídias"),
    Opcao("midias_confirmar_mb", "Perguntar antes de baixar arquivos a partir de", "Mídias", 100,
          "Pergunta antes de baixar, a seu pedido, uma mídia maior que isto "
          "(em MB).",
          ((50, "50 MB"), (100, "100 MB"), (500, "500 MB"),
           (100000, "Nunca perguntar")),
          grupo="Download de mídias"),
)

from telezapp.nucleo import aparencia as _aparencia  # noqa: E402
if _aparencia.MODO_VISUAL_DISPONIVEL:
    OPCOES = (OPCAO_MODO_EXIBICAO,) + OPCOES


# Sons dos eventos: (nome em acessibilidade.fala.bipe, rotulo, descricao).
# O valor guardado e "" (som padrao do TeleZapp), "desligado" ou o caminho de
# um arquivo de som (WAV, Ogg, MP3, FLAC...).
EVENTOS_SOM = (
    ("nova", "mensagem recebida",
     "O som geral de mensagem nova numa conversa que não é a aberta. Os sons "
     "de mensagem individual, de grupo, de canal e de comunidade seguem este "
     "até receberem um som próprio."),
    ("nova_pessoal", "mensagem individual recebida",
     "Tocado quando chega uma mensagem numa conversa com uma pessoa que não "
     "está aberta. Sem um som próprio no pacote, toca o de mensagem "
     "recebida."),
    ("nova_canal", "mensagem recebida num canal",
     "Tocado quando chega uma mensagem num canal que não está aberto. Sem um "
     "som próprio no pacote, toca o de mensagem recebida."),
    ("nova_comunidade", "mensagem recebida numa comunidade",
     "Tocado quando chega uma mensagem numa comunidade do WhatsApp ou num "
     "grupo dela, sem estar aberta. Sem um som próprio no pacote, toca o de "
     "mensagem recebida num grupo."),
    ("enviada", "mensagem enviada",
     "Tocado quando uma mensagem, um arquivo ou uma tarefa em segundo plano "
     "(salvar a conversa, fazer o backup) termina bem."),
    ("erro", "erro",
     "Tocado quando algo não pôde ser feito, como um envio que falhou."),
    ("conectado", "conta conectada",
     "Tocado quando uma conta termina de conectar."),
    ("pronto", "código ou QR pronto",
     "Tocado quando o código de pareamento ou o QR Code fica pronto."),
    ("atualizado", "QR Code atualizado",
     "Tocado quando o QR Code do pareamento é trocado por um novo."),
    ("toque", "toque de chamada recebida",
     "Repetido enquanto uma chamada está tocando para você."),
    ("desligada", "chamada encerrada",
     "Tocado quando uma chamada termina."),
    ("nova_aberta", "mensagem recebida na conversa aberta",
     "Tocado quando chega uma mensagem na conversa que você está vendo. "
     "Com o som padrão, toca o mesmo som de mensagem recebida (e segue a "
     "escolha dele)."),
    ("nova_grupo", "mensagem recebida num grupo",
     "Tocado quando chega uma mensagem num grupo que não está aberto. Com o "
     "som padrão, toca o mesmo som de mensagem recebida."),
    ("desconectada", "conta desconectada",
     "Tocado quando uma conta que estava conectada cai."),
    ("reconectada", "conta reconectada",
     "Tocado quando uma conta que tinha caído volta a conectar. Com o som "
     "padrão, toca o mesmo som de conta conectada."),
    ("falha_envio", "mensagem ou arquivo que não saiu",
     "Tocado quando um envio falha. Com o som padrão, toca o mesmo som de "
     "erro."),
    ("download_pronto", "download de mídia concluído",
     "Tocado quando uma mídia que você pediu para baixar termina. Os "
     "downloads automáticos não tocam."),
    ("tarefa_pronta", "backup, restauração ou conversa salva",
     "Tocado quando terminam tarefas longas, como fazer o backup, restaurar "
     "ou salvar o conteúdo de uma conversa, e quando a atualização da lista "
     "de conversas (F5) termina. Com o som padrão, toca o mesmo som de "
     "mensagem enviada."),
    ("mencao_ou_resposta", "menção ou resposta a você num grupo",
     "Tocado quando chega, num grupo, uma mensagem que cita você com @ ou "
     "que responde a uma mensagem sua. Substitui o som de mensagem recebida "
     "num grupo para essa mensagem e não depende do som de mensagem "
     "recebida (desative este evento se não quiser). Não toca em grupo "
     "arquivado, trancado ou silenciado que não esteja aberto."),
    ("reacao_recebida", "reação a uma mensagem sua",
     "Tocado quando alguém reage com um emoji a uma mensagem sua (não toca "
     "em conversa arquivada, trancada ou silenciada, nem para a sua própria "
     "reação). A fala da reação continua sendo a opção Falar reações às "
     "minhas mensagens, em Interface, Conteúdo falado."),
    ("gravando", "gravação de voz iniciada",
     "Tocado quando começa a gravação de uma nota de voz ou do som do "
     "computador, pelo atalho ou pela janela de gravação. É curto, para não "
     "entrar na gravação."),
    ("gravacao_parada", "gravação de voz parada",
     "Tocado quando você para a gravação. Com o som padrão, toca o mesmo "
     "som de mensagem enviada."),
    ("voto_enquete", "voto numa enquete sua",
     "Tocado quando alguém vota numa enquete que você criou (não toca para "
     "o seu próprio voto, nem em conversa arquivada, trancada ou "
     "silenciada)."),
    ("voto_enviado", "voto seu enviado numa enquete",
     "Tocado quando o seu voto numa enquete é enviado. Com o som padrão, "
     "toca o mesmo som de mensagem enviada."),
    ("escondido", "janela escondida em segundo plano",
     "Tocado quando a janela some e o TeleZapp segue rodando em segundo "
     "plano."),
    ("voltou", "janela trazida de volta",
     "Tocado quando a janela volta do segundo plano, pelo ícone ou pelo "
     "atalho global."),
    ("limite_da_lista", "início ou fim de uma lista",
     "Tocado quando você aperta a seta para cima no primeiro item ou a seta "
     "para baixo no último, em qualquer lista do programa: conversas, "
     "mensagens e as listas das janelas. É um toque curto e grave."),
)
def _opcoes_de_ia():
    from telezapp.nucleo.ia import catalogo
    return (
        Opcao("ia_perfil", "Tamanho das descrições", "Inteligência "
              "artificial", "medio", "Quanto o provedor escreve ao descrever "
              "imagens, figurinhas e vídeos. Transcrições e PDFs sempre "
              "saem completos.", tuple(catalogo.PERFIS)),
        Opcao("ia_tom", "Tom ao redigir com a IA", "Inteligência "
              "artificial", "natural", "O tom da mensagem que a IA escreve "
              "em Mensagem, Inteligência artificial, Redigir a mensagem. "
              "Natural deixa a IA seguir o tom da conversa. O item Redigir "
              "com um tom à escolha pergunta o tom na hora, sem mudar esta "
              "opção.", tuple(catalogo.TONS)),
        Opcao("ia_linha_descricao", "Tamanho da descrição na lista de "
              "mensagens", "Inteligência artificial", 0, "Quantas letras da "
              "descrição de uma foto, figurinha ou vídeo a linha da mensagem "
              "traz, e portanto o que é falado ao passar por ela. "
              "Cortada, termina com a indicação de que o menu mostra tudo.",
              ((300, "300 letras"), (1000, "1000 letras"),
               (3000, "3000 letras"), (0, "Descrição inteira"))),
        Opcao("ia_linha_transcricao", "Tamanho da transcrição na lista de "
              "mensagens", "Inteligência artificial", 1000, "Quantas letras "
              "da transcrição de uma voz ou áudio, ou do texto de um PDF, a "
              "linha da mensagem traz. Textos longos deixam a lista pesada de "
              "ler.", ((300, "300 letras"), (1000, "1000 letras"),
                       (3000, "3000 letras"), (10000, "10000 letras"),
                       (0, "Texto inteiro"))),
        Opcao("ia_auto_audio", "Transcrever sozinho voz e áudio", "Inteligência "
              "artificial", True, "Nas conversas em que você ligou a "
              "transcrição e descrição automáticas (menu de contexto da "
              "conversa), transcreve as mensagens de voz e os áudios que "
              "chegam, usando os provedores da transcrição. A mídia é baixada "
              "sozinha. Os arquivos vão para o provedor, que pode cobrar da "
              "sua chave."),
        Opcao("ia_auto_imagem", "Descrever sozinho fotos e figurinhas",
              "Inteligência artificial", True, "Nas conversas em que você "
              "ligou a transcrição e descrição automáticas, descreve as "
              "fotos e figurinhas que chegam. A mídia é baixada sozinha."),
        Opcao("ia_meta_primeiro", "Tentar primeiro pela Meta AI",
              "Inteligência artificial", False, "Marcada, a transcrição de "
              "voz e áudio e a descrição de imagens, figurinhas e vídeos "
              "tentam primeiro a Meta AI, pela conversa dela na sua conta do "
              "WhatsApp, sem abrir janela. Se ela não responder, ou pedir "
              "para aceitar os termos pelo celular, vale a ordem dos "
              "provedores abaixo, como sempre. O arquivo vai para a Meta, e "
              "o pedido aparece na conversa com a Meta AI. Desmarcada, nada "
              "muda.", servico="whatsapp"),
        Opcao("ia_bot_primeiro", "Tentar primeiro por um bot do Telegram",
              "Inteligência artificial", False, "Marcada, a transcrição de "
              "voz e áudio e a descrição de imagens, figurinhas e vídeos "
              "tentam primeiro o bot do Telegram escolhido abaixo, pela sua "
              "conta do Telegram, sem abrir janela. O bot tem de responder "
              "sozinho ao arquivo, sem comando. Se ele não responder a tempo, "
              "vale a ordem dos provedores, como sempre. Privacidade: o bot é "
              "um serviço de terceiros, que não é do TeleZapp nem do "
              "Telegram. Cada arquivo (voz, áudio, foto, figurinha ou vídeo) "
              "vai para quem mantém o bot, pela sua conta do Telegram, e o "
              "que ele faz com os dados depende dele. O pedido e a resposta "
              "ficam na sua conversa com o bot. Marque só se aceita isso, e "
              "evite com arquivos sensíveis. Precisa de uma conta do "
              "Telegram conectada; sem ela, vale a ordem dos provedores. "
              "Quando as duas estão marcadas, o bot vem antes da Meta AI. "
              "Desmarcada, nada muda.", servico="telegram"),
        Opcao("ia_bot_traduzir", "Traduzir primeiro por um bot do Telegram",
              "Inteligência artificial", False, "Marcada, \"Traduzir o texto "
              "digitado\" e \"Traduzir a mensagem selecionada\" tentam "
              "primeiro o bot do Telegram escolhido abaixo, pela sua conta do "
              "Telegram, sem abrir janela. O TeleZapp pergunta o idioma, manda "
              "o texto como uma mensagem comum e, se o bot pedir para "
              "escolher o idioma por botões, aperta o botão desse idioma e "
              "espera a tradução. O bot tem de responder sozinho, sem "
              "comando. Se ele não responder a tempo, ou não tiver o botão "
              "do idioma, vale a ordem dos provedores, como sempre. Privacidade: o bot é um serviço de "
              "terceiros, que não é do TeleZapp nem do Telegram. O texto "
              "vai para quem mantém o bot, pela sua conta do Telegram, e o "
              "que ele faz com os dados depende dele. O pedido e a resposta "
              "ficam na sua conversa com o bot. Marque só se aceita isso, e "
              "evite com textos sensíveis. Precisa de uma conta do Telegram "
              "conectada e do @nome do bot abaixo. Desmarcada, nada muda.",
              servico="telegram"),
        Opcao("ia_bot_traducao_nome", "Bot do Telegram para traduzir",
              "Inteligência artificial", "@traduciendobot", "O @nome do bot que recebe o "
              "texto quando \"Traduzir primeiro por um bot do Telegram\" "
              "está marcada.", texto=True, servico="telegram"),
        Opcao("ia_bot_nome", "Bot do Telegram para descrever e transcrever",
              "Inteligência artificial", "@AmelieTelegramBot", "O @nome do "
              "bot que recebe os arquivos quando \"Tentar primeiro por um bot "
              "do Telegram\" está marcada.", texto=True, servico="telegram"),
    )


OPCOES = OPCOES + _opcoes_de_ia()

# Fica na tela de Sons (uma caixa so, que toca o tom ao escolher); aqui para
# a busca achar. O tom e feito pelo programa, nao e um arquivo do pacote.
OPCOES = OPCOES + (
    Opcao("tom_de_chamada", "Tom de chamada feita", "Sons", "europa",
          "O tom que você ouve enquanto espera a outra pessoa atender, "
          "repetido até ela atender. Europa: 425 Hz, 1 segundo de tom e 3 de "
          "silêncio. EUA: 440 e 480 Hz juntos, 2 segundos de tom e 4 de "
          "silêncio.",
          escolhas=(("europa", "Europa (425 Hz, 1 s de tom e 3 s de silêncio)"),
                    ("eua", "EUA (440 e 480 Hz, 2 s de tom e 4 s de silêncio)"))),
)


# Perguntas de confirmacao que a pessoa pode desligar (botao Confirmacoes da
# categoria Interface). As que protegem a conta e os dados (excluir conta,
# restaurar, desinstalar, enviar a uma IA, permissoes de robos) nao entram.
_SEM_PERGUNTA_APAGA_MENOS = (
    " Desmarcada, o TeleZapp apaga sem perguntar e faz a escolha que menos "
    "apaga: ")
OPCOES = OPCOES + (
    Opcao("confirmar_apagar_mensagens", "Perguntar antes de apagar mensagens",
          "Interface", True,
          "Ao apagar uma mensagem, ou várias marcadas, o TeleZapp pergunta "
          "antes e, nas suas, se é para todos ou só para você."
          + _SEM_PERGUNTA_APAGA_MENOS + "as suas mensagens saem só para "
          "você, nunca para todos.", grupo="Confirmações"),
    Opcao("confirmar_apagar_conversas", "Perguntar antes de apagar conversas",
          "Interface", True,
          "Ao apagar uma conversa, ou várias marcadas, o TeleZapp pergunta "
          "antes e, quando dá para apagar também no celular, se é aqui e no "
          "celular ou só aqui." + _SEM_PERGUNTA_APAGA_MENOS + "a conversa "
          "sai só deste computador. Sair de um grupo continua perguntando.",
          grupo="Confirmações"),
    Opcao("confirmar_limpeza", "Perguntar antes de limpar mídias e mensagens",
          "Interface", True,
          "Na janela Limpar mídias e mensagens, o botão Apagar diz quantos "
          "itens saem e quanto espaço é liberado, e pergunta se pode "
          "continuar. Desmarcada, apaga direto; o resultado continua sendo "
          "mostrado no fim.", grupo="Confirmações"),
    Opcao("confirmar_limpar_conversa",
          "Perguntar antes de limpar uma conversa",
          "Interface", True,
          "Ao limpar uma conversa (o item Limpar a conversa do menu "
          "Conversas ou a opção de limpar ao apagar um grupo), ou várias "
          "marcadas, o TeleZapp pergunta antes e, quando dá "
          "para limpar também no celular, se é aqui e no celular ou só aqui. "
          "Desmarcada, limpa na hora, aqui e também no celular quando a conta "
          "está conectada e deixa (o lembrete de abrir o WhatsApp no celular "
          "continua, se estiver marcado abaixo). A conversa continua na "
          "lista; as mensagens e as mídias dela é que saem.",
          grupo="Confirmações"),
    Opcao("confirmar_aviso_celular",
          "Lembrar de abrir o WhatsApp no celular antes de apagar lá",
          "Interface", True,
          "Quando você escolhe apagar também no celular, o TeleZapp lembra "
          "de deixar o WhatsApp aberto na tela do celular, para ele apagar "
          "junto, e espera o OK. Desmarcada, segue sem esse aviso.",
          grupo="Confirmações", servico="whatsapp"),
    Opcao("confirmar_grupos_e_canais",
          "Perguntar antes de entrar ou sair de grupos e canais",
          "Interface", True,
          "Pergunta antes de entrar num grupo ou canal por um link ou pela "
          "busca, de sair de um grupo pelos detalhes e de seguir ou deixar "
          "de seguir um canal. Desmarcada, faz na hora.",
          grupo="Confirmações"),
    Opcao("falar_aviso_estado_celular",
          "Falar o aviso para abrir o WhatsApp quando o celular não manda o estado",
          "Interface", True,
          "Quando as mudanças feitas no celular (favoritar, apagar, "
          "silenciar, arquivar) deixam de chegar porque o celular não "
          "mandou a cópia do estado, o TeleZapp fala que é preciso abrir o "
          "WhatsApp no celular por um minuto. Desmarcada, o aviso não é "
          "falado: aparece só na barra de status e no registro, e o "
          "TeleZapp continua tentando de novo sozinho.",
          grupo="Conteúdo falado", servico="whatsapp"),
    Opcao("confirmar_bloqueio",
          "Perguntar antes de bloquear ou desbloquear contatos",
          "Interface", True,
          "Pergunta antes de bloquear ou desbloquear alguém, um contato ou "
          "vários marcados. Desmarcada, faz na hora.",
          grupo="Confirmações"),
    Opcao("confirmar_remover_pessoas",
          "Perguntar antes de remover contatos e participantes",
          "Interface", True,
          "Pergunta antes de remover alguém dos contatos do TeleZapp, de "
          "remover um participante de um grupo e de recusar pedidos de "
          "entrada. Desmarcada, faz na hora.", grupo="Confirmações"),
)


def _com_variantes_por_servico(eventos):
    """Depois de cada evento que se diferencia por servico, uma linha para o
    WhatsApp e outra para o Telegram."""
    from telezapp.acessibilidade import fala
    nomes = {"whatsapp": "WhatsApp", "telegram": "Telegram"}
    saida = []
    for nome, rotulo, descricao in eventos:
        saida.append((nome, rotulo, descricao))
        if nome not in fala.EVENTOS_POR_SERVICO:
            continue
        for servico in fala.SERVICOS_DO_SOM:
            if servico == "telegram" and nome == "nova_comunidade":
                continue                   # o Telegram nao tem comunidades
            saida.append((
                "%s_%s" % (nome, servico),
                "%s (%s)" % (rotulo, nomes[servico]),
                "Só para o %s. Sem um som próprio no pacote, toca o de %s; "
                "desativado, esse serviço fica sem este som." % (
                    nomes[servico], rotulo)))
    return tuple(saida)


EVENTOS_SOM = _com_variantes_por_servico(EVENTOS_SOM)


def precisa_reabrir(chave):
    """True se a opcao so vale quando o TeleZapp abre de novo."""
    for o in OPCOES + (OPCAO_MODO_EXIBICAO,):
        if o.chave == chave:
            return o.reabrir
    return False


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


def buscar_opcoes(texto):
    """Opcoes cujo nome, categoria, grupo, descricao ou escolhas contem todas
    as palavras buscadas (sem diferenca de acento ou maiusculas)."""
    palavras = _sem_acento(texto).split()
    achadas = []
    for o in OPCOES:
        escolhas = [str(r) for _, r in o.escolhas or ()]
        alvo = _sem_acento(" ".join((o.rotulo, o.categoria, o.grupo or "",
                                     o.descricao, *escolhas)))
        if all(p in alvo for p in palavras):
            achadas.append(o)
    return achadas


# Opcoes que ficam na janela Gerenciar contas, nao em Configuracoes
OPCOES_DE_GERENCIAR_CONTAS = ("contas_em_pastas", "contas_pasta")


PADROES = {o.chave: o.padrao for o in OPCOES}
PADROES.update({
    "uso_resposta": "",        # "sim", "nao" (tocou no botao) ou "" (Esc)
    "uso_versao_perguntada": "",   # versao em que a pergunta foi feita
    "uso_pergunta_em": 0.0,    # quando a pergunta foi feita (sem resposta)
    "uso_id": "",              # identificador anonimo sorteado (nucleo/uso.py)
    "uso_ultimo_envio": 0.0,   # quando o ultimo resumo foi aceito
    "estilo": 1,             # antigo "Como cada mensagem e lida"; so migra
    "atalhos": {},           # funcao -> combinacao escolhida ("" = sem atalho)
    "participantes_silenciados": {},  # ver nucleo/silenciados.py
    "filtros_personalizados": {"ativo": False, "lista": []},  # ver
    #                                nucleo/filtros_personalizados.py
    "filtro_personalizado": "",       # o filtro escolhido na tela principal
    "sons_de_conversa": {},  # "conta|conversa" -> arquivo em sons/conversas
    "ordem_das_fixadas": [],  # "conta|conversa" na ordem em que as fixadas ficam
    "ia_ordem": {},          # tarefa -> provedores ligados, na ordem de tentativa
    "ia_lista_modelos": {},  # provedor -> modelos que ele ofereceu
    "ia_modelos": {},        # provedor -> modelo escolhido ("" = o padrao)
    "ia_url_personalizada": "",   # endereco do provedor personalizado (https)
    "pacote_de_sons": "padrao",   # padrao, telezapp ou p:<nome>
    "sons_desativados": {},      # pacote -> eventos sem som
    "lista_conversas": {"ordem": ["nome", "servico", "nao_lidas", "previa",
                                  "estado", "reacoes", "quem_reagiu"],
                        "ocultos": ["previa", "estado", "reacoes",
                                    "quem_reagiu"]},  # o que cada linha mostra
    "lista_mensagens": {"ordem": ["autor", "hora", "conteudo", "marcas",
                                  "links", "previa", "ia", "reacoes",
                                  "resposta", "estado"],
                        "ocultos": [],
                        "autor_so_quando_muda": False},  # a linha da mensagem
    "ia_automatica_conversas": [],  # [conta, conversa] com a IA automatica
    "ia_idioma_traducao": "English",  # ultimo idioma de destino da traducao
    "ia_consentimento_texto": [],  # provedores que podem receber seu texto
    "ia_consentimento": [],  # provedores que a pessoa autorizou a receber midia
    "contas": [],            # [{"id", "servico", "telefone", "nome"}]
    "chamada_microfone": "",     # nome do microfone usado nas chamadas
    "chamada_saida": "",         # nome da saida de som das chamadas
    "chamada_camera": "",        # nome da camera das chamadas de video
    "chamada_tela": "",          # nome da tela compartilhada nas chamadas
    "chamada_saida_pc": "",      # saida de som do computador compartilhada
    "chamada_tela_com_som": True,  # compartilhar a tela leva o som junto
    "notificacao_saida": "",     # nome da saida dos sons de aviso do app
    "telegram_api_id": 0,
    "telegram_api_hash": "",
    "filtro_conversas": "todas",   # tipo escolhido na janela principal
    "filtro_conta": "todas",       # servico ou conta escolhido nela
    "filtro_pasta": {},            # conta -> pasta (ou lista) escolhida
    # o que o aviso falado de mensagem nova diz (nucleo/aviso_de_nova.py)
    "aviso_nova": {"ordem": ["inicio", "conversa", "servico", "conta",
                             "autor", "hora", "conteudo"],
                   "ocultos": ["servico", "conta"]},
})


class Config:
    """Configuracoes em config.json, gravadas de forma atomica."""

    def __init__(self, caminho=None):
        self.caminho = caminho or os.path.join(pasta(), "config.json")
        self._trava = threading.Lock()
        self.dados = dict(PADROES)
        self.dados["contas"] = []
        self._carregar()

    def _carregar(self):
        try:
            with open(self.caminho, encoding="utf-8") as f:
                lido = json.load(f)
            if isinstance(lido, dict):
                self.dados.update(lido)
                if lido.get("falar_novas") and \
                        "falar_novas_outras_conversas" not in lido:
                    # antes uma opcao so falava tudo: mantem o que a pessoa
                    # ouvia ao separar em tres
                    self.dados["falar_novas_outras_conversas"] = True
                    self.dados["falar_novas_fora_do_telezapp"] = True
                if self.dados.pop("digitar_na_lista", None) == "campo":
                    # antes uma opcao so valia para as duas listas: cada uma
                    # fica com o que a pessoa tinha
                    for chave in ("lista_conversas", "lista_mensagens"):
                        atual = self.dados[chave]
                        self.dados[chave] = dict(
                            atual if isinstance(atual, dict) else {},
                            digitar="campo")
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            log.warning("config.json ilegivel, usando padroes: %r", e)

    def get(self, chave):
        return self.dados.get(chave, PADROES.get(chave))

    def set(self, chave, valor):
        self.dados[chave] = valor
        self.salvar()

    def salvar(self):
        with self._trava:
            tmp = self.caminho + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.dados, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.caminho)

    # ---------------------------------------------------------------- contas
    def contas(self):
        return [dict(c) for c in self.get("contas")]

    def salvar_conta(self, conta):
        contas = [c for c in self.get("contas") if c.get("id") != conta["id"]]
        contas.append(dict(conta))
        self.set("contas", contas)

    def remover_conta(self, conta_id):
        self.set("contas", [c for c in self.get("contas")
                            if c.get("id") != conta_id])


# --------------------------------------------------- credenciais do Telegram
# O api_id e o api_hash identificam o APLICATIVO perante o Telegram (nao a
# pessoa). O executavel leva os do projeto (telezapp/_credenciais.py, gerado
# na hora de empacotar e fora do git) e ninguem precisa informar nada. Sem
# eles, o app usa os da configuracao e, por fim, pergunta uma vez.
TELEGRAM_API_ID = 0
TELEGRAM_API_HASH = ""

ARQUIVO_TESTES = r"C:\TeleZapp\configuracao-telegram.txt"


def ler_chaves(caminho):
    """Le um arquivo CHAVE=valor (ignora linhas com #)."""
    d = {}
    with open(caminho, encoding="utf-8-sig") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            k, v = linha.split("=", 1)
            d[k.strip().upper()] = v.strip()
    return d


def credenciais_validas(api_id, api_hash):
    """api id cabe em 32 bits (telefone nao cabe) e api hash tem 32 digitos
    hexadecimais (nome nao tem): pegam quem digita os dados da pessoa."""
    try:
        return 0 < int(api_id) <= 2147483647 and re.fullmatch(
            "[0-9a-fA-F]{32}", str(api_hash).strip()) is not None
    except (TypeError, ValueError):
        return False


def credenciais_embutidas():
    """(api_id, api_hash) postas no programa na hora de empacotar
    (telezapp/_credenciais.py, fora do git: ferramentas/empacotar.py a gera),
    ou None. Com elas, quem instala nao informa nada."""
    try:
        from telezapp import _credenciais
    except ImportError:
        return None
    if credenciais_validas(_credenciais.API_ID, _credenciais.API_HASH):
        return int(_credenciais.API_ID), str(_credenciais.API_HASH).strip()
    return None


def credenciais_telegram(config, arquivo_testes=ARQUIVO_TESTES):
    """(api_id, api_hash) ou None se ainda nao houver.

    Ordem: as embutidas no programa, as da configuracao e, por fim, as do
    arquivo dos testes de viabilidade (C:\\TeleZapp), que sao copiadas para a
    configuracao para nao precisar digita-las.
    """
    if credenciais_validas(TELEGRAM_API_ID, TELEGRAM_API_HASH):
        return int(TELEGRAM_API_ID), TELEGRAM_API_HASH
    embutidas = credenciais_embutidas()
    if embutidas is not None:
        return embutidas
    api_id, api_hash = config.get("telegram_api_id"), config.get(
        "telegram_api_hash")
    if credenciais_validas(api_id, api_hash):
        return int(api_id), str(api_hash).strip()
    try:
        d = ler_chaves(arquivo_testes)
    except OSError:
        return None
    if credenciais_validas(d.get("API_ID"), d.get("API_HASH")):
        config.dados["telegram_api_id"] = int(d["API_ID"])
        config.dados["telegram_api_hash"] = d["API_HASH"].strip()
        config.salvar()
        log.info("credenciais do Telegram copiadas do arquivo dos testes")
        return int(d["API_ID"]), d["API_HASH"].strip()
    return None


def telefone_dos_testes(arquivo_testes=ARQUIVO_TESTES):
    """Telefone do arquivo dos testes de viabilidade, para sugerir no login."""
    try:
        return ler_chaves(arquivo_testes).get("TELEFONE", "")
    except OSError:
        return ""

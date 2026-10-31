# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""O contrato comum dos servicos.

A interface so conhece estes metodos. Todos voltam na hora: o trabalho roda
na thread do provedor, e os resultados chegam como eventos (nucleo.eventos).

Para pedir algo a pessoa durante o login (telefone, codigo, senha), o
provedor chama `pedir(etapa, erro)`, que bloqueia so a thread do provedor e
devolve o texto digitado, ou None se a pessoa cancelar.
"""
from abc import ABC, abstractmethod

# Etapas de login que o provedor pode pedir a interface
PEDIR_TELEFONE = "telefone"
PEDIR_CODIGO = "codigo"
PEDIR_SENHA = "senha"


class ErroMidia(Exception):
    """Falha esperada ao baixar uma midia; o texto e dito a pessoa."""


class ErroPrivacidade(Exception):
    """Nao deu para mudar a privacidade; o texto e dito a pessoa."""


class ErroBloqueio(Exception):
    """Nao deu para bloquear, desbloquear ou ler os bloqueados; o texto e
    dito a pessoa."""


class ErroPerfil(Exception):
    """Nao deu para ler ou mudar o perfil; o texto e dito a pessoa."""


class DownloadCancelado(Exception):
    """A pessoa cancelou o download."""


class Provedor(ABC):
    servico = ""
    # True quando o servico e a biblioteca de chamadas estao disponiveis
    suporta_chamadas = False

    def __init__(self, conta, barramento, banco, pedir):
        self.conta = conta
        self.barramento = barramento
        self.banco = banco
        self.pedir = pedir

    @abstractmethod
    def iniciar(self):
        """Conecta (fazendo login se preciso) e passa a receber mensagens."""

    @abstractmethod
    def parar(self):
        """Desconecta e encerra a thread. Pode demorar ate alguns segundos."""

    @abstractmethod
    def atualizar_conversas(self):
        """Busca a lista de conversas -> ConversasAtualizadas."""

    @abstractmethod
    def carregar_mensagens(self, conversa_id, limite=50):
        """Busca as ultimas mensagens -> MensagensCarregadas."""

    @abstractmethod
    def enviar_texto(self, conversa_id, texto, resposta_a="", mencoes=None):
        """Envia -> MensagemNova(enviada_daqui=True) ou EnvioFalhou.
        `mencoes`: quem foi mencionado com @ (ver nucleo.mencoes)."""

    @abstractmethod
    def marcar_como_lida(self, conversa_id):
        """Avisa o servico que a pessoa leu a conversa."""

    def apagar_mensagem(self, mensagem, para_todos=False):
        """Apaga a mensagem na conta do servico (para todos, ou so para
        mim). True se o servico foi avisado."""
        return False

    # True nos servicos em que a mensagem favorita tambem vale na conta
    FAVORITA_NA_CONTA = False

    def favoritar_mensagem(self, mensagem, favoritar):
        """Marca (ou desmarca) a mensagem como favorita na conta do servico.
        True se o servico foi avisado."""
        return False

    def pessoa_da_mensagem(self, mensagem):
        """Quem enviou a mensagem recebida, para salvar como contato:
        (id da conversa com a pessoa, '+telefone', [ids pelos quais ela
        aparece]) ou None se nao der para saber."""
        return None

    ACEITA_CONTATOS = False     # sabe avisar a conta do nome de um contato

    def salvar_contato(self, conversa_id, nome, telefone=""):
        """Avisa a conta do nome dado a este contato, para o proprio servico
        reconhecer a pessoa. True se foi aceito; False quando o contato
        fica so no TeleZapp."""
        return False

    def marcar_ouvida(self, mensagem):
        """Avisa o servico que a pessoa tocou esta voz ou audio recebido
        (a marca de ouvida tambem aparece no celular)."""

    def enviar_arquivo(self, conversa_id, anexo, legenda="", resposta_a="",
                       mencoes=None):
        """Envia foto, video, audio, documento ou nota de voz (`anexo`, ver
        midia.envio), citando a mensagem `resposta_a` quando houver e com as
        `mencoes` (ver nucleo.mencoes) da legenda. Volta na hora; o upload
        roda fora da fila de texto.
        Publica MensagemNova(enviada_daqui=True) ou EnvioFalhou."""
        raise NotImplementedError

    def responder_acao(self, msg, acao):
        """Toca um botao de resposta ou escolhe uma opcao de lista de uma
        mensagem (ex.: de empresa). Publica MensagemNova ou EnvioFalhou.
        Por padrao o servico nao tem isso."""
        raise NotImplementedError

    # ------------------------------------------------ chamadas de voz
    # Voltam na hora; o andamento chega como ev.EstadoChamada.
    def ligar(self, conversa_id, microfone="", saida=""):
        """Liga para a pessoa da conversa privada."""
        raise NotImplementedError

    def atender_chamada(self, conversa_id, microfone="", saida=""):
        """Atende a chamada que esta tocando."""
        raise NotImplementedError

    def encerrar_chamada(self, conversa_id):
        """Recusa (tocando), cancela (chamando) ou desliga (em chamada)."""
        raise NotImplementedError

    def silenciar_chamada(self, conversa_id, silenciar):
        """Silencia ou reativa o microfone durante a chamada."""
        raise NotImplementedError

    # Video nas chamadas: so o WhatsApp faz por enquanto.
    suporta_video = False

    def cameras(self):
        """Nomes das cameras que o provedor pode usar nas chamadas."""
        return []

    def ligar_camera(self, conversa_id, nome=""):
        """Liga a camera na chamada (numa chamada de voz, pede video)."""
        raise NotImplementedError

    def desligar_camera(self, conversa_id):
        raise NotImplementedError

    def definir_destino_video(self, destino):
        """`destino(conversa_id, largura, altura, rgb)` recebe os quadros do
        video do outro lado."""
        raise NotImplementedError

    def trocar_dispositivos(self, conversa_id, microfone="", saida=""):
        """Troca o microfone e/ou a saida de som no meio da chamada. Nome
        vazio mantem o atual."""
        raise NotImplementedError

    def dispositivos_de_audio(self):
        """([nomes dos microfones], [nomes das saidas de som]) que o motor
        de chamadas enxerga; listas vazias se nao houver."""
        return [], []

    def buscar_mensagens_que_faltam(self, conversa_id):
        """Pede ao celular as mensagens recentes da conversa que o TeleZapp
        pode nao ter recebido. Devolve "" se o pedido foi enviado (a resposta
        chega depois, com um ev.Aviso) ou o motivo de nao ter sido."""
        return "Este serviço não faz essa busca."

    def arquivar_conversa(self, conversa_id, arquivar):
        """Arquiva (ou desarquiva) a conversa na conta do servico. Devolve
        True se o servico foi avisado; False quando so da para guardar no
        TeleZapp."""
        return False

    def fixar_conversa(self, conversa_id, fixar):
        """Fixa (ou desafixa) a conversa na conta. True se o servico foi
        avisado; False quando so da para guardar no TeleZapp."""
        return False

    def silenciar_conversa(self, conversa_id, silenciar, segundos=0):
        """Silencia a conversa por `segundos` (0 = para sempre) ou tira o
        silencio. True se o servico foi avisado."""
        return False

    # True nos servicos em que o TeleZapp sabe apagar a conversa na conta
    # (no celular), alem de apaga-la aqui
    APAGA_NA_CONTA = False

    def apagar_conversa(self, conversa_id, ultima=None):
        """Apaga a conversa na conta do servico (no celular). `ultima`: a
        mensagem mais nova que o TeleZapp tem, ou None. Devolve True se o
        servico foi avisado."""
        return False

    # True nos servicos em que o TeleZapp sabe tirar a conta de um grupo
    SAI_DE_GRUPO = False

    def sair_do_grupo(self, conversa_id):
        """Tira a conta do grupo. Devolve True se o servico aceitou."""
        return False

    # Editar mensagem propria: quanto tempo depois do envio o servico deixa
    # (segundos); 0 = nao sabe editar
    JANELA_EDICAO = 0

    def editar_mensagem(self, msg, texto):
        """Troca o texto de uma mensagem de texto minha. Responde pelo
        barramento: MensagemAtualizada(motivo "editada") ou Aviso."""

    # ---- janela de detalhes da conversa (chamadas que esperam o servico:
    # rodam fora da thread da interface)
    def dados_do_contato(self, conversa_id):
        """{'telefone', 'usuario', 'nome_no_perfil', 'recado'} da pessoa; as
        chaves que o servico nao informa ficam de fora."""
        return {}

    COMANDOS_DO_ROBO = False

    def comandos_do_robo(self, conversa_id):
        """O que o robo da conversa, ou os robos do grupo, oferecem:
        {'comandos': [(texto a enviar, descricao)], 'menu': {'texto', 'url'} ou
        None, 'privacidade': endereco ou ''}. None se o servico nao respondeu.
        """
        return {"comandos": [], "menu": None, "privacidade": ""}

    def link_web_do_robo(self, conversa_id, url, robo="", menu=False):
        """O endereco para abrir o aplicativo web de um robo, ou "" se nao
        foi possivel. robo: o id dele, se nao for o da conversa."""
        return ""

    def link_app_do_robo(self, conversa_id, app="", inicio=""):
        """O endereco do aplicativo de um robo pelo nome curto (app) ou, sem
        nome, do principal; "" se nao foi possivel."""
        return ""

    def resolver_usuario(self, usuario):
        """{'id', 'nome', 'tipo', 'robo'} do @usuario; None se nao achou."""
        return None

    def iniciar_robo(self, conversa_id, parametro):
        """Inicia o robo com o parametro de um link. False se falhou."""
        return False

    def enviar_dados_do_app(self, conversa_id, rotulo, dados):
        """Entrega ao robo os dados que o aplicativo dele enviou."""

    def metodo_do_app(self, conversa_id, nome, params):
        """Chama um metodo do robo em nome do aplicativo: texto JSON."""
        raise NotImplementedError

    def permitir_escrita_do_robo(self, conversa_id):
        """Autoriza o robo a enviar mensagens. False se falhou."""
        return False

    def compartilhar_telefone(self, conversa_id):
        """Envia o numero da conta como contato. False se falhou."""
        return False

    def completar_nome(self, conversa_id):
        """Conversa que so mostra o numero: procura o nome na rede e, se
        achar, ja o poe na lista. Devolve o nome achado ou ""."""
        return ""

    def detalhes_do_grupo(self, conversa_id):
        """Dicionario do grupo (nome, descricao, criado_em, dono, anuncio,
        trancado, comunidade, sou_admin, participantes=[{id, nome, telefone,
        admin, dono}]) ou None se o servico nao informa."""
        return None

    def detalhes_do_canal(self, conversa_id):
        """Dicionario do canal (nome, descricao, seguidores, verificado,
        silenciado, papel, criado_em, link) ou None."""
        return None

    def grupos_em_comum(self, pessoa_id):
        """[(conversa_id, nome)] dos grupos que a conta divide com a pessoa."""
        return []

    def administrar_grupo(self, conversa_id, acao, valor=None):
        """Ferramentas de administrador (nome, descricao, anuncio, trancado,
        adicionar, remover, promover, rebaixar, foto (bytes JPEG), link, revogar_link, sair).
        Devolve (ok, texto)."""
        return False, "Esta conta não administra grupos por aqui."

    # True nos servicos com pedidos de entrada em grupo e foto do grupo
    PEDIDOS_DE_ENTRADA = False
    FOTO_DO_GRUPO = False
    FOTO_DO_CONTATO = False
    LISTA_GRUPOS_ADMIN = False
    ENTRA_POR_LINK = False       # "Entrar em um grupo por link"

    def pedidos_de_entrada(self, conversa_id):
        """Pedidos pendentes para entrar no grupo: (True, [{'id', 'nome',
        'telefone', 'quando'}]) ou (False, texto). Espera o servico."""
        return False, "Esta conta não gerencia pedidos de entrada."

    def responder_pedidos(self, conversa_id, ids, aprovar):
        """Aprova (ou recusa) pedidos de entrada. (ok, texto)."""
        return False, "Esta conta não gerencia pedidos de entrada."

    def foto_do_grupo(self, conversa_id):
        """Baixa a foto atual do grupo: (True, bytes) ou (False, texto)."""
        return False, "Esta conta não mostra a foto do grupo."

    def foto_do_contato(self, conversa_id):
        """Baixa a foto de perfil do contato: (True, bytes) ou (False, texto)."""
        return False, "Esta conta não mostra a foto do contato."

    def grupos_que_administro(self):
        """[(conversa_id, nome)] dos grupos em que a conta e administradora."""
        return []

    def grupos_da_conta(self):
        """[(conversa_id, nome)] de todos os grupos de que a conta participa,
        tenham ou nao conversa guardada aqui. Pode esperar a rede."""
        return []

    def administrar_canal(self, conversa_id, acao, valor=None):
        """Ferramentas do canal (silenciar, deixar_de_seguir). (ok, texto)."""
        return False, "Esta conta não gerencia canais por aqui."

    # tipos que o servico deixa criar: "grupo", "canal" e/ou "comunidade"
    CRIA = ()

    def criar_conversa(self, tipo, nome, descricao="", participantes=(),
                       topicos=False):
        """Cria um grupo, canal ou comunidade. `participantes`: telefones ou
        @usuarios para ja pôr no grupo; `topicos`: grupo dividido em topicos
        (onde o servico tem). Espera o servico (thread propria). Devolve
        (ok, texto, conversa_id); o id e "" quando nao se sabe."""
        return False, "Esta conta não cria grupos, canais ou comunidades.", ""

    def previa_do_convite(self, msg, acao):
        """Dados do grupo ou canal de um convite (acao do tipo "entrar"):
        {'nome', 'membros', 'descricao', 'ja_participa', 'erro'}; so 'erro'
        quando o convite nao vale. Espera o servico (thread propria)."""
        return {"erro": "Esta conta não entra em grupos por aqui."}

    def entrar_no_grupo(self, msg, acao):
        """Entra no grupo ou canal do convite. Devolve (ok, texto)."""
        return False, "Esta conta não entra em grupos por aqui."

    def conversa_aberta(self, conversa_id):
        """A pessoa abriu a conversa: o servico pode conferir (sem travar) se
        ela ainda pode escrever nela, marcando `somente_leitura`."""

    # True nos servicos que sabem reagir a uma mensagem
    PODE_REAGIR = False

    def reagir(self, mensagem, emoji):
        """Reage a mensagem com o emoji (vazio: tira a minha reacao). Volta
        na hora; o resultado chega como ev.MensagemAtualizada (motivo
        "reacao") ou ev.Aviso."""

    # True nos servicos em que da para criar uma enquete
    PODE_ENVIAR_LOCALIZACAO = False

    def enviar_localizacao(self, conversa_id, latitude, longitude):
        """Envia um ponto no mapa. O resultado chega como MensagemNova ou
        Aviso."""
        raise NotImplementedError

    PODE_FIXAR = False
    DURACOES_FIXAR = ()      # ((segundos, rotulo), ...) se o servico pedir prazo

    def fixar_mensagem(self, mensagem, fixar, segundos=0):
        """Fixa ou desafixa a mensagem na conversa. O resultado chega como
        MensagemAtualizada (motivo "fixada") ou Aviso."""
        raise NotImplementedError

    def fixadas_no_servico(self, conversa_id):
        """Pergunta ao servico o que esta fixado, atualiza as guardadas e
        devolve as fixadas que nao estao guardadas. None: o servico nao sabe
        dizer, valem as guardadas."""
        return None

    PODE_ENVIAR_CONTATOS = False

    def enviar_contatos(self, conversa_id, contatos):
        """Envia cartoes de contato: contatos e [(nome, telefone)]. O resultado
        chega como MensagemNova ou Aviso."""
        raise NotImplementedError

    PODE_CRIAR_ENQUETE = False

    def criar_enquete(self, conversa_id, pergunta, opcoes, multipla,
                      anonima=True):
        """Cria a enquete na conversa. Volta na hora; a mensagem criada chega
        como ev.MensagemNova(enviada_daqui=True) ou o erro como ev.Aviso."""

    # True nos servicos em que da para votar numa enquete
    PODE_VOTAR = False

    def votar_enquete(self, mensagem, escolhas):
        """Vota na enquete com as opcoes (posicoes); lista vazia tira o meu
        voto. Volta na hora; o resultado chega como ev.MensagemAtualizada
        (motivo "enquete") ou ev.Aviso."""

    def atualizar_enquete(self, mensagem):
        """Pede ao servico o resultado atual (onde ele nao manda sozinho)."""

    # True nos servicos em que da para ligar e desligar as mensagens
    # temporarias de uma conversa
    PODE_TEMPORARIAS = False

    def definir_temporaria(self, conversa_id, segundos):
        """Liga (segundos > 0) ou desliga (0) as mensagens temporarias da
        conversa. O resultado chega como ev.ConversasAtualizadas (com
        `temporaria_s` novo) ou ev.Aviso."""

    # True nos servicos em que da para publicar status (historia)
    PODE_PUBLICAR_STATUS = False

    def publicar_status(self, texto, anexo=None, publico="contatos"):
        """Publica um status: `texto` (no Telegram, a legenda) e, se houver,
        `anexo` (foto ou video). O resultado chega como ev.Aviso."""

    def responder_status(self, mensagem, texto):
        """Responde em particular a um status (ou historia) de alguem."""

    def observar_presenca(self, conversa_id):
        """A conversa foi aberta: passa a avisar (ev.Presenca) se a pessoa
        esta online, quando foi vista por ultimo e quando digita."""

    def parar_presenca(self, conversa_id):
        """A conversa foi fechada: nao precisa mais dos avisos."""

    def depurar_conversa(self, conversa_id):
        """Dados do servico sobre a conversa, para o menu Depurar (como o
        nome foi achado, identificadores). Dicionario; vazio se nao houver."""
        return {}

    def privacidade(self):
        """{campo: valor} da privacidade da conta (ver nucleo/
        privacidade_conta.py), ou None se o servico nao tem ou nao deu
        para ler."""
        return None

    def definir_privacidade(self, campo, valor):
        """Muda uma escolha de privacidade na conta."""
        raise NotImplementedError

    def privacidade_status(self):
        """(tipo, quantas) de quem pode ver o status: contacts, blacklist
        ou whitelist; None se nao souber."""
        return None

    # True nos servicos em que da para editar o proprio perfil; o sobrenome
    # existe so em alguns (PERFIL_SOBRENOME)
    PODE_EDITAR_PERFIL = False
    PERFIL_SOBRENOME = False

    def meu_perfil(self):
        """{'nome', 'sobrenome', 'recado'} do proprio perfil (as chaves que o
        servico nao tem ficam de fora). Espera o servico (thread propria).
        Levanta ErroPerfil."""
        raise ErroPerfil("Esta conta não edita o perfil por aqui.")

    def salvar_perfil(self, mudancas, foto=None):
        """Grava no servico os campos de `mudancas` ({'nome', 'sobrenome',
        'recado'}: so os que mudaram) e a `foto` (bytes JPEG), se houver.
        Espera o servico (thread propria). Devolve ([campos salvos],
        [(campo, motivo)]); levanta ErroPerfil se nem tentou (conta
        desconectada)."""
        raise ErroPerfil("Esta conta não edita o perfil por aqui.")

    # True nos servicos em que da para bloquear e desbloquear pessoas
    PODE_BLOQUEAR = False

    def bloqueados(self):
        """[(id, nome, telefone)] das pessoas que a conta bloqueou. Espera o
        servico (thread propria). Levanta ErroBloqueio."""
        return []

    def esta_bloqueado(self, conversa_id):
        """True se a pessoa da conversa esta bloqueada. Espera o servico
        (thread propria). Levanta ErroBloqueio."""
        return False

    def bloquear(self, conversa_id, bloquear=True):
        """Bloqueia a pessoa da conversa (ou desbloqueia, com `bloquear`
        falso). Espera o servico (thread propria). Levanta ErroBloqueio."""
        raise ErroBloqueio("Esta conta não bloqueia pessoas por aqui.")

    def resolver_destinatario(self, texto):
        """(conversa_id, nome) de quem o texto (@usuario, telefone) indica,
        ou None se o servico nao achou ou nao sabe."""
        return None

    def contatos_da_conta(self):
        """[(id, nome, telefone)] da agenda que o servico mantem na conta;
        vazio por padrao. Leitura local e rapida."""
        return []

    def formas_do_endereco(self, id_):
        """Os enderecos conhecidos da mesma pessoa de um grupo."""
        return {id_}

    def id_do_telefone(self, telefone):
        """Id de conversa de quem tem esse telefone ('+5551...'), ou ''
        quando o servico nao deixa saber sem consultar a rede."""
        return ""

    def nome_de_participante(self, participante_id):
        """Nome para mostrar de quem aparece num recibo (entregue, lida);
        vazio se nao souber."""
        return ""

    def baixar_arquivo(self, msg, base, progresso, cancelado):
        """Baixa a midia da mensagem e devolve o caminho do arquivo.

        Bloqueia ate terminar: roda numa thread do gerente de midias, nunca
        na da interface. `base` e o caminho sem extensao; `progresso(p)`
        recebe 0 a 100; `cancelado()` diz se a pessoa desistiu. Levanta
        ErroMidia (texto para a pessoa) ou DownloadCancelado."""
        raise ErroMidia("Este serviço ainda não baixa mídias.")

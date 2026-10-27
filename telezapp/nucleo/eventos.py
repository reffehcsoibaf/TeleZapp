# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Eventos que os provedores (cada um em sua thread) mandam para a interface.

O barramento recebe uma funcao `entregar` que leva a chamada para a thread da
interface (no app, wx.CallAfter). Assim nenhum provedor mexe na janela
diretamente, e a interface nunca espera a rede.
"""
import logging
import threading
from dataclasses import dataclass, field

log = logging.getLogger("telezapp.eventos")

# Estados de uma conta
DESCONECTADA, CONECTANDO, CONECTADA, PRECISA_LOGIN, ERRO = (
    "desconectada", "conectando", "conectada", "precisa de login", "erro")


@dataclass
class EstadoConta:
    conta_id: str
    estado: str
    detalhe: str = ""


@dataclass
class ContaPronta:
    """Login concluido: nome e telefone confirmados pelo servico."""
    conta_id: str
    nome: str
    telefone: str


@dataclass
class ConversasAtualizadas:
    conta_id: str
    conversas: list = field(default_factory=list)


@dataclass
class ConversaApagadaNoCelular:
    """A pessoa apagou a conversa no celular (aviso de estado do WhatsApp).
    `data`: quando, em segundos."""
    conta_id: str
    conversa_id: str
    data: float = 0.0


@dataclass
class AutoresAtualizados:
    """O servico descobriu o nome de quem enviou mensagens que estavam sem
    autor (grupo do WhatsApp com participante so em LID).
    `nomes`: {endereco de quem enviou: nome}."""
    conta_id: str
    conversa_id: str
    nomes: dict = field(default_factory=dict)


@dataclass
class MensagemApagadaNoCelular:
    """A pessoa apagou uma mensagem para si no celular (ou em outro
    aparelho)."""
    conta_id: str
    conversa_id: str
    mensagem_id: str


@dataclass
class MensagensCarregadas:
    conta_id: str
    conversa_id: str
    mensagens: list = field(default_factory=list)


@dataclass
class MensagemNova:
    mensagem: object
    conversa: object = None        # Conversa ja atualizada (nome, data...)
    enviada_daqui: bool = False    # enviada por este app: nao anunciar
    silenciosa: bool = False       # chegou na sincronia inicial: sem aviso


@dataclass
class SincronizacaoConcluida:
    """WhatsApp: terminou a entrega das mensagens que chegaram com o app
    fechado; `quantas` recebidas nesse lote (para um aviso so)."""
    conta_id: str
    quantas: int = 0


@dataclass
class EnvioFalhou:
    conta_id: str
    conversa_id: str
    texto: str
    motivo: str
    devolver_texto: bool = True    # False: resposta de botao, nada a devolver
    tipo: str = "texto"            # tipo da mensagem local que falhou


@dataclass
class LeituraConfirmada:
    """O outro lado leu as minhas mensagens ate `ate_id` (inclusive)."""
    conta_id: str
    conversa_id: str
    ate_id: int


@dataclass
class EstadosMensagens:
    """WhatsApp: as minhas mensagens `ids` foram entregues ou lidas."""
    conta_id: str
    conversa_id: str
    ids: list
    estado: str


@dataclass
class ProgressoSincronia:
    """WhatsApp: andamento (0 a 100) do historico que o celular envia."""
    conta_id: str
    percentual: int
    interrompida: bool = False   # a conexao caiu antes do fim


@dataclass
class ProgressoEnvio:
    """Um envio de arquivo andou: `percentual` de 0 a 100 (100 = chegou ao
    servidor; a mensagem enviada vem em seguida)."""
    conta_id: str
    conversa_id: str
    percentual: int


@dataclass
class ProgressoMidia:
    """Um download de midia andou: `percentual` de 0 a 100."""
    conta_id: str
    conversa_id: str
    mensagem_id: str
    percentual: int


@dataclass
class MidiaBaixada:
    """Fim de um download: `caminho` se deu certo; senao `erro` ou
    `cancelada`. `automatica`: baixada sem a pessoa pedir."""
    conta_id: str
    conversa_id: str
    mensagem_id: str
    caminho: str = ""
    erro: str = ""
    cancelada: bool = False
    automatica: bool = False


@dataclass
class QrPareamento:
    """WhatsApp: um novo QR Code para parear (troca a cada ~20 s)."""
    conta_id: str
    codigo: str


@dataclass
class Presenca:
    """Como esta a outra pessoa na conversa observada. `estado`: "online",
    "offline" (`quando` = ultima vez, em segundos; ou `aprox`, como
    "recentemente", quando o servico so informa isso), "digitando",
    "gravando", "enviando" (arquivo) ou "parou" (de digitar). `quem` e o nome
    de quem digita, nos grupos."""
    conta_id: str
    conversa_id: str
    estado: str
    quando: float = 0.0
    aprox: str = ""
    quem: str = ""


@dataclass
class PareamentoFalhou:
    """WhatsApp: o celular nao aceitou o codigo (`metodo` "codigo") ou o
    WhatsApp recusou o pareamento pelo QR Code ("qr"). A conexao precisa
    recomecar para valer de novo."""
    conta_id: str
    metodo: str


@dataclass
class CodigoPareamento:
    """WhatsApp: o codigo de 8 caracteres para digitar no celular, ou o
    motivo de nao ter conseguido gerar."""
    conta_id: str
    codigo: str = ""
    erro: str = ""


@dataclass
class MensagemAtualizada:
    """Uma mensagem ja conhecida mudou: `motivo` e "reacao" (alguem reagiu ou
    tirou a reacao), "editada", "apagada" ou "mencao" (so o nome de quem foi
    mencionado foi achado; a tela nao avisa). `mensagem` ja vem atualizada;
    `quem` e `emoji` so valem para reacao (emoji vazio: tirou)."""
    conta_id: str
    conversa_id: str
    mensagem: object
    motivo: str
    quem: str = ""
    emoji: str = ""


@dataclass
class EstadoChamada:
    """Uma chamada de voz mudou de estado (ver nucleo.chamadas). `entrante`:
    a chamada veio de fora. `motivo` e `erro` so valem quando encerrada."""
    conta_id: str
    conversa_id: str
    estado: str
    nome: str = ""
    entrante: bool = False
    motivo: str = ""
    erro: str = ""
    # video (WhatsApp): a chamada e de video, a nossa camera esta ligada, o
    # outro lado manda video, e se este provedor sabe fazer video
    video: bool = False
    camera: bool = False
    video_remoto: bool = False
    suporta_video: bool = False


@dataclass
class ChamadaWhatsApp:
    """Uma chamada do WhatsApp que o TeleZapp ainda nao atende: so avisa.
    `fase`: "tocando" (alguem esta ligando), "perdida", "recusada",
    "atendida" (em outro aparelho; `segundos` = duracao) ou "encerrada"."""
    conta_id: str
    conversa_id: str
    nome: str
    video: bool
    fase: str
    chamada_id: str = ""
    segundos: int = 0


@dataclass
class Aviso:
    """Algo que a pessoa precisa saber (erro de rede, limite do servico)."""
    conta_id: str
    texto: str
    grave: bool = False


class Barramento:
    def __init__(self, entregar=None):
        self._entregar = entregar or (lambda f, *a: f(*a))
        self._ouvintes = []
        self._trava = threading.Lock()

    def ouvir(self, funcao):
        with self._trava:
            self._ouvintes.append(funcao)

    def publicar(self, evento):
        """Pode ser chamado de qualquer thread."""
        with self._trava:
            ouvintes = list(self._ouvintes)
        for f in ouvintes:
            try:
                self._entregar(self._chamar, f, evento)
            except Exception:
                log.exception("falha ao entregar %s", type(evento).__name__)

    @staticmethod
    def _chamar(f, evento):
        try:
            f(evento)
        except Exception:
            log.exception("erro ao tratar %s", type(evento).__name__)

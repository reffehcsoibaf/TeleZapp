# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
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
class CodigoPareamento:
    """WhatsApp: o codigo de 8 caracteres para digitar no celular, ou o
    motivo de nao ter conseguido gerar."""
    conta_id: str
    codigo: str = ""
    erro: str = ""


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

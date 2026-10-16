# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
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
    def enviar_texto(self, conversa_id, texto, resposta_a=""):
        """Envia -> MensagemNova(enviada_daqui=True) ou EnvioFalhou."""

    @abstractmethod
    def marcar_como_lida(self, conversa_id):
        """Avisa o servico que a pessoa leu a conversa."""

    def enviar_arquivo(self, conversa_id, anexo, legenda=""):
        """Envia foto, video, audio, documento ou nota de voz (`anexo`, ver
        midia.envio). Volta na hora; o upload roda fora da fila de texto.
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

    def trocar_dispositivos(self, conversa_id, microfone="", saida=""):
        """Troca o microfone e/ou a saida de som no meio da chamada. Nome
        vazio mantem o atual."""
        raise NotImplementedError

    def dispositivos_de_audio(self):
        """([nomes dos microfones], [nomes das saidas de som]) que o motor
        de chamadas enxerga; listas vazias se nao houver."""
        return [], []

    def depurar_conversa(self, conversa_id):
        """Dados do servico sobre a conversa, para o menu Depurar (como o
        nome foi achado, identificadores). Dicionario; vazio se nao houver."""
        return {}

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

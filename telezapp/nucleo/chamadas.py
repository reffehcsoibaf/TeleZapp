# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Chamadas de voz: estados, textos falados e o que a janela deve mostrar.

Sem wx e sem rede, para ser testado fora do Windows. O provedor publica
`EstadoChamada` (nucleo.eventos); a janela guarda uma `Chamada` e pede a
`apresentar` o que mostrar e o que falar, em cada estado.

Fluxo de uma chamada:
    saida:   CHAMANDO -> EM_CHAMADA -> ENCERRADA
    entrada: TOCANDO  -> CONECTANDO -> EM_CHAMADA -> ENCERRADA
"""
import time
from dataclasses import dataclass, field

CHAMANDO = "chamando"          # eu liguei e o outro lado ainda nao atendeu
TOCANDO = "tocando"            # estao me ligando
CONECTANDO = "conectando"      # atendi, abrindo o audio
EM_CHAMADA = "em chamada"
ENCERRADA = "encerrada"

# Motivos de uma chamada encerrada
DESLIGADA = "desligada"        # alguem desligou depois de conectar
RECUSADA = "recusada"          # o outro lado recusou, ou eu recusei
CANCELADA = "cancelada"        # eu desisti antes de atenderem
PERDIDA = "perdida"            # tocou e a outra pessoa desistiu
OCUPADO = "ocupado"
SEM_RESPOSTA = "sem resposta"
FALHA = "falha"

# Botoes que a janela da chamada pode mostrar
ATENDER, RECUSAR, DESLIGAR, SILENCIAR, TEMPO, FECHAR = (
    "atender", "recusar", "desligar", "silenciar", "tempo", "fechar")


def formatar_duracao(segundos):
    """0:07, 12:03 ou 1:02:45 (para mostrar)."""
    s = max(0, int(segundos))
    h, resto = divmod(s, 3600)
    mi, se = divmod(resto, 60)
    return "%d:%02d:%02d" % (h, mi, se) if h else "%d:%02d" % (mi, se)


def falar_duracao(segundos):
    """'3 minutos e 5 segundos' (para o leitor de tela)."""
    s = max(0, int(segundos))
    h, resto = divmod(s, 3600)
    mi, se = divmod(resto, 60)
    partes = []
    if h:
        partes.append("%d %s" % (h, "hora" if h == 1 else "horas"))
    if mi:
        partes.append("%d %s" % (mi, "minuto" if mi == 1 else "minutos"))
    if se or not partes:
        partes.append("%d %s" % (se, "segundo" if se == 1 else "segundos"))
    return " e ".join(partes) if len(partes) < 3 else \
        ", ".join(partes[:-1]) + " e " + partes[-1]


@dataclass
class Chamada:
    conta_id: str
    conversa_id: str
    nome: str
    entrante: bool = False
    estado: str = CHAMANDO
    motivo: str = ""
    mudo: bool = False
    inicio_conexao: float = 0.0     # quando entrou em EM_CHAMADA (monotonic)
    erro: str = ""                  # explicacao da falha, ja em portugues
    _agora: object = field(default=time.monotonic, repr=False)

    @property
    def ativa(self):
        return self.estado != ENCERRADA

    @property
    def tocando_ou_chamando(self):
        return self.estado in (CHAMANDO, TOCANDO)

    def segundos(self):
        if self.estado == EM_CHAMADA and self.inicio_conexao:
            return self._agora() - self.inicio_conexao
        return 0.0

    def aplicar(self, estado, motivo="", erro=""):
        """Muda o estado; devolve True se algo mudou."""
        if estado == self.estado and motivo == self.motivo:
            return False
        if estado == EM_CHAMADA and self.estado != EM_CHAMADA:
            self.inicio_conexao = self._agora()
        self.estado, self.motivo = estado, motivo
        if erro:
            self.erro = erro
        return True


@dataclass
class Apresentacao:
    titulo: str            # titulo da janela (o leitor de tela le ao abrir)
    situacao: str          # texto da janela, atualizado a cada mudanca
    fala: str              # o que o leitor de tela fala na mudanca
    botoes: tuple          # botoes visiveis, na ordem de Tab
    foco: str              # botao que recebe o foco
    som: str = ""          # som curto (acessibilidade.fala.bipe), se houver


def _quem(nome):
    return nome or "contato"


def texto_encerramento(c):
    """O que aconteceu, em uma frase, para falar e mostrar."""
    quem = _quem(c.nome)
    if c.motivo == RECUSADA:
        return ("Chamada recusada." if c.entrante
                else "%s recusou a chamada." % quem)
    if c.motivo == CANCELADA:
        return "Chamada cancelada."
    if c.motivo == PERDIDA:
        return "Chamada perdida de %s." % quem
    if c.motivo == OCUPADO:
        return "%s está ocupado em outra chamada." % quem
    if c.motivo == SEM_RESPOSTA:
        return "%s não atendeu." % quem
    if c.motivo == FALHA:
        return c.erro or "A chamada falhou."
    return "Chamada encerrada."


def apresentar(c):
    """O que mostrar e falar para o estado atual da chamada `c`."""
    quem = _quem(c.nome)
    if c.estado == TOCANDO:
        return Apresentacao(
            "Chamada de %s" % quem,
            "%s está ligando para você." % quem,
            "Chamada de %s. Enter atende, Escape recusa." % quem,
            (ATENDER, RECUSAR), ATENDER, "toque")
    if c.estado == CHAMANDO:
        return Apresentacao(
            "Chamando %s" % quem,
            "Chamando %s. Esperando atender." % quem,
            "Chamando %s." % quem,
            (DESLIGAR,), DESLIGAR, "chamando")
    if c.estado == CONECTANDO:
        return Apresentacao(
            "Conectando com %s" % quem,
            "Conectando o áudio com %s." % quem,
            "Conectando.",
            (DESLIGAR,), DESLIGAR)
    if c.estado == EM_CHAMADA:
        mudo = " Seu microfone está silenciado." if c.mudo else ""
        return Apresentacao(
            "Em chamada com %s" % quem,
            "Em chamada com %s.%s" % (quem, mudo),
            "Conectado com %s.%s" % (quem, mudo),
            (SILENCIAR, TEMPO, DESLIGAR), DESLIGAR, "conectado")
    texto = texto_encerramento(c)
    return Apresentacao(
        "Chamada encerrada", texto, texto, (FECHAR,), FECHAR, "desligada")


def rotulo_silenciar(mudo):
    return "&Ativar o microfone" if mudo else "&Silenciar o microfone"


def fala_mudo(mudo):
    return "Microfone silenciado." if mudo else "Microfone ativado."


def motivo_da_excecao(erro):
    """(motivo, explicacao) para uma excecao da biblioteca de chamadas ou do
    Telegram. O nome da classe basta: nao dependemos de importar nada."""
    nome = type(erro).__name__
    if nome in ("CallDeclined", "PhoneCallDeclined"):
        return RECUSADA, ""
    if nome in ("CallBusy",):
        return OCUPADO, ""
    if nome in ("TimedOutAnswer", "TimeoutError"):
        return SEM_RESPOSTA, ""
    if nome in ("CallDiscarded",):
        return CANCELADA, ""
    if nome in ("UserPrivacyRestrictedError", "PrivacyRestricted"):
        return FALHA, ("Esta pessoa não permite receber chamadas suas, "
                       "pelas configurações de privacidade dela.")
    if nome in ("UserIsBlockedError", "UserBlocked"):
        return FALHA, "Você bloqueou esta pessoa, ou ela bloqueou você."
    if "Flood" in nome:
        return FALHA, ("O Telegram pediu para esperar antes de ligar de "
                       "novo.")
    return FALHA, "Não foi possível completar a chamada (%s)." % nome

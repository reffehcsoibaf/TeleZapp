# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
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
ATENDER, RECUSAR, DESLIGAR, SILENCIAR, TEMPO, FECHAR, CAMERA = (
    "atender", "recusar", "desligar", "silenciar", "tempo", "fechar",
    "camera")


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
    video: bool = False             # a chamada e (ou virou) de video
    camera: bool = False            # a nossa camera esta ligada
    video_remoto: bool = False      # o outro lado esta mandando video
    suporta_video: bool = False     # a conta sabe fazer video
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

    def aplicar_video(self, video, camera, video_remoto, suporta=None):
        """Atualiza o que e do video; devolve True se algo mudou."""
        novo = (bool(video), bool(camera), bool(video_remoto))
        if suporta is not None:
            self.suporta_video = bool(suporta)
        antigo = (self.video, self.camera, self.video_remoto)
        self.video, self.camera, self.video_remoto = novo
        return novo != antigo

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


def rotulo_camera(c):
    """O botao da camera: liga/desliga a nossa; numa chamada so de voz,
    ligar pede ao outro lado para passar a video."""
    if c.camera:
        return "Desligar a &câmera"
    return "Ligar a &câmera" if c.video else         "Passar para &vídeo (ligar a câmera)"


def fala_camera(camera, video):
    if camera:
        return "Câmera ligada."
    return "Câmera desligada." if video else "Câmera desligada."


def fala_do_video(antes, depois, nome):
    """O que falar quando so o video mudou. `antes` e `depois` sao
    (video, camera, video_remoto); "" se nada a dizer."""
    quem = _quem(nome)
    video0, camera0, remoto0 = antes
    video1, camera1, remoto1 = depois
    partes = []
    if video1 and not video0:
        partes.append("A chamada passou para vídeo.")
    if camera1 != camera0:
        partes.append("Sua câmera foi ligada." if camera1
                      else "Sua câmera foi desligada.")
    if remoto1 != remoto0:
        partes.append("%s ligou a câmera." % quem if remoto1
                      else "%s desligou a câmera." % quem)
    return " ".join(partes)


def texto_do_video(c):
    """O que o video da chamada esta fazendo, para a janela e o leitor."""
    if not c.video:
        return ""
    partes = ["Chamada de vídeo."]
    partes.append("Sua câmera está %s." % ("ligada" if c.camera
                                          else "desligada"))
    partes.append("%s %s vídeo." % (
        _quem(c.nome), "está mandando" if c.video_remoto
        else "não está mandando"))
    return " ".join(partes)


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
        de = "Chamada de vídeo de %s" if c.video else "Chamada de %s"
        return Apresentacao(
            de % quem,
            ("%s está ligando para você por vídeo." if c.video
             else "%s está ligando para você.") % quem,
            de % quem + ". Enter atende, Escape recusa.",
            (ATENDER, RECUSAR), ATENDER, "toque")
    if c.estado == CHAMANDO:
        por_video = " por vídeo" if c.video else ""
        return Apresentacao(
            "Chamando %s%s" % (quem, por_video),
            "Chamando %s%s. Esperando atender." % (quem, por_video),
            "Chamando %s%s." % (quem, por_video),
            (DESLIGAR,), DESLIGAR, "chamando")
    if c.estado == CONECTANDO:
        return Apresentacao(
            "Conectando com %s" % quem,
            "Conectando o áudio com %s." % quem,
            "Conectando.",
            (DESLIGAR,), DESLIGAR)
    if c.estado == EM_CHAMADA:
        mudo = " Seu microfone está silenciado." if c.mudo else ""
        video = (" " + texto_do_video(c)) if c.video else ""
        botoes = (SILENCIAR, CAMERA, TEMPO, DESLIGAR) if c.suporta_video             else (SILENCIAR, TEMPO, DESLIGAR)
        return Apresentacao(
            "Em chamada com %s" % quem,
            "Em chamada com %s.%s%s" % (quem, mudo, video),
            "Conectado com %s.%s%s" % (quem, mudo, video),
            botoes, DESLIGAR, "conectado")
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


# ------------------------------------------- chamadas do WhatsApp (so aviso)
def _tipo(video):
    return "vídeo" if video else "voz"


def texto_na_conversa(video, fase, segundos=0):
    """A linha que a chamada deixa na lista de mensagens da conversa."""
    base = "Chamada de %s" % _tipo(video)
    if fase == "tocando":
        return base + " recebida, tocando"
    if fase == "perdida":
        return base + " perdida"
    if fase == "recusada":
        return base + " recusada"
    if fase == "atendida":
        return base + " atendida em outro aparelho" + (
            ", durou " + falar_duracao(segundos) if segundos > 0 else "")
    return base + " encerrada"


def texto_do_aviso(nome, video):
    """O que a janela de aviso diz quando alguem liga."""
    return ("%s está te chamando por %s. O TeleZapp ainda não dá suporte "
            "para chamadas do WhatsApp: atenda em outro dispositivo ou abra "
            "uma conversa." % (nome or "Alguém", _tipo(video)))


def texto_do_fim(nome, video, fase, segundos=0):
    """O aviso atualizado quando a chamada acaba antes de a pessoa fechar a
    janela."""
    quem = nome or "Alguém"
    coisa = "A chamada de %s de %s" % (_tipo(video), quem)
    if fase == "perdida":
        return coisa + " terminou sem ser atendida."
    if fase == "recusada":
        return coisa + " foi recusada."
    if fase == "atendida":
        return coisa + " foi atendida em outro aparelho."
    return coisa + " terminou."

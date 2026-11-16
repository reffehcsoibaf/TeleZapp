# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Chat de voz de grupo e live de canal do Telegram (recurso EXPERIMENTAL).

Sem wx e sem rede, para ser testado fora do Windows. O provedor publica
`EstadoChatDeVoz` (nucleo.eventos); a janela guarda um `ChatDeVoz` e pede a
`apresentar` o que mostrar e falar.

Fluxo: CONECTANDO -> DENTRO -> ENCERRADO. Entra-se sempre com o microfone
silenciado; em live de canal so se ouve (`ouvinte`).
"""
import time
from dataclasses import dataclass, field

from telezapp.nucleo import chamadas as ch

CONECTANDO = "conectando"
DENTRO = "dentro"
ENCERRADO = "encerrado"

# Por que um chat de voz acabou
SAIU = "saiu"                  # eu sai
TERMINOU = "terminou"          # o chat de voz foi encerrado por quem o criou
REMOVIDO = "removido"          # fui retirado
FALHA = "falha"

# Botoes da janela
FALAR, MAO, QUEM, TEMPO, SAIR, FECHAR = (
    "falar", "mao", "quem", "tempo", "sair", "fechar")
CAMERA, TELA, SOM_PC = "camera", "tela", "som_pc"

# Passando disso, a lista mostra so os primeiros e os avisos de quem entra
# e sai ficam calados (centenas de avisos por minuto tornariam a fala inutil)
LISTA_MAXIMA = 200
AVISOS_ATE = 15

AVISO_EXPERIMENTAL = (
    "Recurso experimental: pode mudar ou sair do TeleZapp nas próximas "
    "versões se o desempenho não for bom.")


@dataclass
class Participante:
    id: int
    nome: str
    mudo: bool = True
    mao: bool = False
    eu: bool = False
    falando: bool = False

    @classmethod
    def de_tupla(cls, t):
        return cls(*t)


@dataclass
class ChatDeVoz:
    conta_id: str
    conversa_id: str
    nome: str
    estado: str = CONECTANDO
    ao_vivo: bool = False
    ouvinte: bool = False
    mudo: bool = True
    mao: bool = False
    participantes: list = field(default_factory=list)
    total: int = 0
    motivo: str = ""
    erro: str = ""
    inicio: float = 0.0
    camera: bool = False            # a nossa camera esta ligada
    tela: bool = False              # estamos compartilhando a tela
    som_pc: bool = False            # estamos compartilhando o som do PC
    suporta_video: bool = False
    suporta_tela: bool = False
    suporta_som_pc: bool = False
    _agora: object = field(default=time.monotonic, repr=False)

    @property
    def ativo(self):
        return self.estado != ENCERRADO

    def segundos(self):
        if self.estado == DENTRO and self.inicio:
            return self._agora() - self.inicio
        return 0.0

    def aplicar(self, e):
        """Copia o que o evento `e` (EstadoChatDeVoz) traz. Devolve True se o
        estado ou o motivo mudou."""
        mudou = (e.estado, e.motivo) != (self.estado, self.motivo)
        if e.estado == DENTRO and self.estado != DENTRO:
            self.inicio = self._agora()
        self.estado, self.motivo = e.estado, e.motivo
        if e.nome and not self.nome:
            self.nome = e.nome
        self.ao_vivo, self.ouvinte = bool(e.ao_vivo), bool(e.ouvinte)
        self.mudo, self.mao = bool(e.mudo), bool(e.mao)
        self.total = e.total
        self.participantes = [Participante.de_tupla(t)
                              for t in e.participantes]
        self.camera, self.tela, self.som_pc = (
            bool(e.camera), bool(e.tela), bool(e.som_pc))
        self.suporta_video = bool(e.suporta_video)
        self.suporta_tela = bool(e.suporta_tela)
        self.suporta_som_pc = bool(e.suporta_som_pc)
        if e.erro:
            self.erro = e.erro
        return mudou


def ordenar(participantes):
    """Eu no topo (para achar o meu estado de pronto), depois quem esta
    falando agora, quem levantou a mao (pede a vez), quem pode falar (microfone
    aberto) e por fim os silenciados; dentro de cada grupo, por nome."""
    return sorted(participantes, key=lambda p: (
        not p.eu, not p.falando, not p.mao, p.mudo,
        (p.nome or "").casefold()))


def rotulo(p):
    """A linha da lista, lida pelo leitor de tela."""
    partes = [p.nome or "Participante"]
    if p.eu:
        partes.append("você")
    if p.falando:
        partes.append("falando")
    elif p.mao:
        partes.append("mão levantada")
    elif p.mudo:
        partes.append("silenciado")
    else:
        partes.append("microfone aberto")
    return ", ".join(partes)


def rotulos(participantes):
    return [rotulo(p) for p in ordenar(participantes)[:LISTA_MAXIMA]]


def quem_fala(participantes):
    """A frase para o botao "Quem esta falando"."""
    nomes = [("você" if p.eu else (p.nome or "Participante"))
             for p in ordenar(participantes) if p.falando]
    if not nomes:
        return "Ninguém está falando agora."
    if len(nomes) == 1:
        return "%s está falando." % nomes[0].capitalize()
    return "%s e %s estão falando." % (", ".join(nomes[:-1]),
                                         nomes[-1]) if len(nomes) > 1 else ""


def texto_de_inicio(nome, ao_vivo):
    return "%s em %s." % ("Live começou" if ao_vivo
                           else "Chat de voz começou", nome or "uma conversa")


def marca_na_lista(ao_vivo):
    """O que a linha da conversa diz quando ha um em andamento."""
    return "live em andamento" if ao_vivo else "chat de voz em andamento"


def quantos(c):
    n = max(c.total, len(c.participantes))
    return "%d %s" % (n, "participante" if n == 1 else "participantes")


def avisos_ligados(total):
    """Os avisos de quem entra e sai so valem em chat de voz pequeno."""
    return total <= AVISOS_ATE


def aviso_de_entrada(nome, entrou):
    return "%s %s." % (nome or "Alguém", "entrou" if entrou else "saiu")


def aviso_de_mao(nome):
    return "%s levantou a mão." % (nome or "Alguém")


@dataclass
class Apresentacao:
    titulo: str
    situacao: str
    fala: str
    botoes: tuple
    foco: str
    som: str = ""


def _tipo(c):
    return "Live" if c.ao_vivo else "Chat de voz"


def apresentar(c):
    """O que mostrar e falar para o estado atual."""
    tipo = _tipo(c)
    quem = c.nome or "conversa"
    if c.estado == CONECTANDO:
        return Apresentacao(
            "Entrando em %s" % quem,
            "Entrando em %s: %s de %s. %s" % (
                tipo.lower(), tipo, quem, AVISO_EXPERIMENTAL),
            "Entrando em %s. %s" % (quem, AVISO_EXPERIMENTAL),
            (SAIR,), SAIR)
    if c.estado == DENTRO:
        botoes = [] if c.ouvinte else [FALAR, MAO]
        if not c.ouvinte:
            if c.suporta_som_pc:
                botoes.append(SOM_PC)
            if c.suporta_tela and c.suporta_video:
                botoes.append(TELA)
            if c.suporta_video:
                botoes.append(CAMERA)
        botoes += [QUEM, TEMPO, SAIR]
        if c.ouvinte:
            estado = "Você só ouve."
        elif c.mao:
            estado = "Sua mão está levantada."
        elif c.mudo:
            estado = "Seu microfone está silenciado."
        else:
            estado = "Seu microfone está aberto."
        mandando = texto_do_que_mandamos(c)
        if mandando:
            estado += " " + mandando
        n = quantos(c)
        return Apresentacao(
            "%s em %s" % (tipo, quem),
            "%s em %s, %s. %s %s" % (tipo, quem, n, estado,
                                       AVISO_EXPERIMENTAL),
            "Dentro de %s em %s, %s. %s" % (tipo.lower(), quem, n, estado),
            tuple(botoes), SAIR, "conectado")
    texto = texto_encerramento(c)
    return Apresentacao(
        "%s encerrado" % tipo, texto, texto, (FECHAR,), FECHAR, "desligada")


def texto_encerramento(c):
    tipo = _tipo(c)
    if c.motivo == TERMINOU:
        return "%s terminou." % tipo
    if c.motivo == REMOVIDO:
        return "Você foi removido do %s." % tipo.lower()
    if c.motivo == FALHA:
        return c.erro or "Não consegui entrar no %s." % tipo.lower()
    return "Você saiu do %s." % tipo.lower()


def texto_do_que_mandamos(c):
    """O que estamos mandando (camera, tela, som do computador)."""
    partes = []
    if c.camera:
        partes.append("a sua câmera")
    if c.tela:
        partes.append("a tela")
    if c.som_pc:
        partes.append("o som do computador")
    if not partes:
        return ""
    return "Você está mandando %s." % (
        partes[0] if len(partes) == 1 else
        ", ".join(partes[:-1]) + " e " + partes[-1])


def rotulo_camera(c):
    return "Desligar a &câmera" if c.camera else "Ligar a &câmera"


def fala_do_que_mandamos(antes, depois):
    """O que falar quando mudou o que estamos mandando. `antes` e `depois`
    sao (camera, tela, som_pc); "" se nada mudou."""
    cam0, tela0, som0 = antes
    cam1, tela1, som1 = depois
    partes = []
    if cam1 != cam0:
        partes.append("Câmera ligada." if cam1 else "Câmera desligada.")
    partes.append(ch.fala_compartilhamento((tela0, som0), (tela1, som1)))
    return " ".join(t for t in partes if t)


def rotulo_falar(mudo):
    return "&Abrir o microfone" if mudo else "&Silenciar o microfone"


def fala_falar(mudo):
    return "Microfone silenciado." if mudo else "Microfone aberto."


def rotulo_mao(mao):
    return "&Baixar a mão" if mao else "Levantar a &mão"


def fala_mao(mao):
    return "Mão levantada." if mao else "Mão baixada."


def falar_duracao(segundos):
    return ch.falar_duracao(segundos)


def motivo_da_excecao(erro, criar=False):
    """Frase para quem tentou entrar (ou iniciar) e nao conseguiu. Pelo nome
    da classe da excecao, sem importar nada da biblioteca."""
    nome = type(erro).__name__
    if criar and nome in ("ChatAdminRequiredError",
                          "GroupcallForbiddenError", "ChatWriteForbiddenError",
                          "ChatAdminInviteRequiredError"):
        return "Só administradores podem iniciar um chat de voz aqui."
    if criar:
        return "Não consegui iniciar o chat de voz."
    if nome in ("NoActiveGroupCall", "GroupcallInvalidError",
                "GroupcallJoinMissingError"):
        return "Não há chat de voz ativo nesta conversa."
    if nome in ("GroupcallForbiddenError", "ChatAdminRequiredError"):
        return "O Telegram não deixou você entrar neste chat de voz."
    if nome in ("TimedOutAnswer", "TimeoutError"):
        return "O chat de voz não respondeu a tempo."
    if nome == "FloodWaitError":
        return "O Telegram pediu para esperar um pouco antes de tentar de novo."
    return "Não consegui entrar no chat de voz."

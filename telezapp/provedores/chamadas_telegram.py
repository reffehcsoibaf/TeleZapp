# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Chamadas de voz 1 a 1 do Telegram, pelo py-tgcalls (motor NTgCalls).

Roda na mesma thread e no mesmo asyncio do provedor do Telegram, sobre o
mesmo cliente Telethon. Nada aqui toca na janela: o andamento sai como
`EstadoChamada`. O audio vai do microfone e para a saida de som do Windows
direto pela NTgCalls, sem FFmpeg (experimento 9, docs/decisoes.md).

O py-tgcalls e opcional: sem ele as chamadas ficam desligadas e o resto do
aplicativo segue igual.
"""
import logging

from telezapp.nucleo import chamadas as ch
from telezapp.nucleo import eventos as ev

log = logging.getLogger("telezapp.chamadas")

# Quanto esperar a outra pessoa atender antes de desistir (segundos)
ESPERA_ATENDER_S = 45


class Motor:
    """O que usamos do py-tgcalls, reunido num lugar so (e trocavel nos
    testes)."""

    def __init__(self):
        from pytgcalls import MediaDevices, PyTgCalls, filters
        from pytgcalls.types import (AudioQuality, CallConfig, ChatUpdate,
                                     MediaStream, RecordStream)
        self.PyTgCalls = PyTgCalls
        self.filters = filters
        self.ChatUpdate = ChatUpdate
        self.MediaStream = MediaStream
        self.RecordStream = RecordStream
        self.AudioQuality = AudioQuality
        self.CallConfig = CallConfig
        self.MediaDevices = MediaDevices

    def microfones(self):
        return list(self.MediaDevices.microphone_devices())

    def saidas(self):
        return list(self.MediaDevices.speaker_devices())

    def fluxo_microfone(self, dispositivo):
        return self.MediaStream(
            dispositivo, audio_parameters=self.AudioQuality.HIGH,
            video_flags=self.MediaStream.Flags.IGNORE)

    def fluxo_saida(self, dispositivo):
        return self.RecordStream(audio=dispositivo)


def disponivel():
    """True se o py-tgcalls pode ser importado."""
    try:
        import pytgcalls  # noqa: F401
        return True
    except Exception:
        return False


def _escolher(dispositivos, nome):
    """O dispositivo com esse nome (o Windows corta os nomes que a janela de
    dispositivos mostra, entao vale tambem o nome que comeca igual); senao o
    primeiro (o padrao do Windows)."""
    if not dispositivos:
        return None
    for d in dispositivos:
        if d.title == nome:
            return d
    from telezapp.midia.dispositivos import parecem_o_mesmo
    for d in dispositivos:
        if parecem_o_mesmo(nome, d.title):
            return d
    return dispositivos[0]


class ChamadasTelegram:
    def __init__(self, cliente, conta_id, barramento, nome_de, motor=None,
                 espera_s=ESPERA_ATENDER_S):
        """nome_de(chat_id) -> corrotina que devolve o nome a mostrar."""
        self.cliente = cliente
        self.conta_id = conta_id
        self.barramento = barramento
        self.nome_de = nome_de
        self.espera_s = espera_s
        self._motor_fabrica = motor or Motor
        self.motor = None
        self.app = None
        self.chamadas = {}      # chat_id -> ch.Chamada
        self._escolhas = {}     # chat_id -> (microfone, saida)
        self._nomes = ([], [])  # ultimos dispositivos vistos (microfones,
        #                         saidas); ver atualizar_dispositivos

    # ---------------------------------------------------------- inicio
    async def iniciar(self):
        """True se as chamadas ficaram disponiveis."""
        try:
            self.motor = self._motor_fabrica()
            self.app = self.motor.PyTgCalls(self.cliente)
            f, cu = self.motor.filters, self.motor.ChatUpdate
            self.app.on_update(f.chat_update(cu.Status.INCOMING_CALL))(
                self._ao_receber)
            self.app.on_update(f.chat_update(cu.Status.LEFT_CALL))(
                self._ao_sair)
            await self.app.start()
        except Exception as e:
            log.info("chamadas indisponíveis: %r", e)
            self.motor = self.app = None
            return False
        self.atualizar_dispositivos()
        log.info("chamadas de voz prontas")
        return True

    @property
    def pronta(self):
        return self.app is not None

    def atualizar_dispositivos(self):
        """Lista microfones e saidas. SO pode rodar na thread do provedor:
        a NTgCalls inicia o COM no modo dela, e na thread da interface (que o
        wx ja iniciou no modo dele) o processo cai."""
        if self.motor is None:
            return
        try:
            self._nomes = ([d.title for d in self.motor.microfones()],
                           [d.title for d in self.motor.saidas()])
        except Exception:
            log.exception("erro ao listar dispositivos de áudio")

    def dispositivos(self):
        """Os nomes da ultima listagem, sem tocar na NTgCalls (pode ser
        chamado de qualquer thread)."""
        mics, saidas = self._nomes
        return list(mics), list(saidas)

    # --------------------------------------------------------- estados
    def _publicar(self, c):
        self.barramento.publicar(ev.EstadoChamada(
            self.conta_id, str(c.conversa_id), c.estado, c.nome, c.entrante,
            c.motivo, c.erro))

    def _mudar(self, chat_id, estado, motivo="", erro=""):
        c = self.chamadas.get(chat_id)
        if c is None or not c.aplicar(estado, motivo, erro):
            return
        self._publicar(c)
        if estado == ch.ENCERRADA:
            self.chamadas.pop(chat_id, None)
            self._escolhas.pop(chat_id, None)

    def _nova(self, chat_id, nome, entrante, estado):
        c = ch.Chamada(self.conta_id, str(chat_id), nome, entrante, estado)
        self.chamadas[chat_id] = c
        self._publicar(c)
        return c

    # ------------------------------------------------------- saida
    async def ligar(self, chat_id, microfone="", saida=""):
        if not self.pronta:
            return
        if self.chamadas:
            log.info("já existe uma chamada; ligar ignorado")
            return
        self._escolhas[chat_id] = (microfone, saida)
        self.atualizar_dispositivos()
        self._nova(chat_id, await self.nome_de(chat_id), False, ch.CHAMANDO)
        await self._conectar(chat_id)

    async def atender(self, chat_id, microfone="", saida=""):
        c = self.chamadas.get(chat_id)
        if not self.pronta or c is None or c.estado != ch.TOCANDO:
            return
        self._escolhas[chat_id] = (microfone, saida)
        self._mudar(chat_id, ch.CONECTANDO)
        await self._conectar(chat_id)

    async def _conectar(self, chat_id):
        """Liga o microfone e a saida de som. Em chamadas feitas por nos,
        `play` so volta quando a outra pessoa atende."""
        import asyncio
        mic, saida = self._escolhas.get(chat_id, ("", ""))
        try:
            fluxo = self.motor.fluxo_microfone(
                _escolher(self.motor.microfones(), mic))
            cfg = self.motor.CallConfig(timeout=self.espera_s)
            await self.app.play(chat_id, fluxo, cfg)
            if chat_id not in self.chamadas:      # desligaram nesse meio
                return
            await self.app.record(chat_id, self.motor.fluxo_saida(
                _escolher(self.motor.saidas(), saida)))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            c = self.chamadas.get(chat_id)
            if c is None:         # ja foi encerrada por outro caminho
                return
            motivo, erro = ch.motivo_da_excecao(e)
            if c.estado == ch.CHAMANDO and motivo == ch.FALHA and \
                    type(e).__name__ == "Exception":
                motivo = ch.CANCELADA
            log.warning("chamada falhou: %s (%s)", type(e).__name__, motivo)
            self._mudar(chat_id, ch.ENCERRADA, motivo, erro)
            try:
                await self.app.leave_call(chat_id)
            except Exception:
                pass
            return
        self._mudar(chat_id, ch.EM_CHAMADA)

    # ----------------------------------------------------- controles
    async def encerrar(self, chat_id):
        c = self.chamadas.get(chat_id)
        if c is None:
            return
        if c.estado == ch.TOCANDO:
            motivo = ch.RECUSADA
        elif c.estado in (ch.CHAMANDO, ch.CONECTANDO):
            motivo = ch.CANCELADA
        else:
            motivo = ch.DESLIGADA
        self._mudar(chat_id, ch.ENCERRADA, motivo)
        try:
            await self.app.leave_call(chat_id)
        except Exception as e:
            log.info("leave_call: %r", e)

    async def silenciar(self, chat_id, silenciar):
        c = self.chamadas.get(chat_id)
        if c is None or c.estado != ch.EM_CHAMADA:
            return
        try:
            if silenciar:
                await self.app.mute(chat_id)
            else:
                await self.app.unmute(chat_id)
            c.mudo = bool(silenciar)
        except Exception:
            log.exception("erro ao silenciar")

    async def trocar_dispositivos(self, chat_id, microfone="", saida=""):
        c = self.chamadas.get(chat_id)
        if c is None or c.estado != ch.EM_CHAMADA:
            return
        mic, sai = self._escolhas.get(chat_id, ("", ""))
        mic, sai = microfone or mic, saida or sai
        self._escolhas[chat_id] = (mic, sai)
        try:
            if microfone:
                await self.app.play(chat_id, self.motor.fluxo_microfone(
                    _escolher(self.motor.microfones(), mic)))
            if saida:
                await self.app.record(chat_id, self.motor.fluxo_saida(
                    _escolher(self.motor.saidas(), sai)))
        except Exception:
            log.exception("erro ao trocar de dispositivo")

    # --------------------------------------------- eventos do motor
    async def _ao_receber(self, _cliente, update):
        chat_id = update.chat_id
        if self.chamadas:
            # ja ha uma chamada: recusa a nova sem incomodar
            log.info("chamada recebida enquanto outra está aberta: recusada")
            try:
                await self.app.leave_call(chat_id)
            except Exception:
                pass
            return
        try:
            nome = await self.nome_de(chat_id)
        except Exception:
            nome = ""
        self.atualizar_dispositivos()
        self._nova(chat_id, nome, True, ch.TOCANDO)

    async def _ao_sair(self, _cliente, update):
        chat_id = update.chat_id
        c = self.chamadas.get(chat_id)
        if c is None:
            return
        if c.estado == ch.TOCANDO:
            motivo = ch.PERDIDA
        elif c.estado == ch.CHAMANDO:
            motivo = ch.RECUSADA
        elif c.estado == ch.CONECTANDO:
            motivo = ch.FALHA
        else:
            motivo = ch.DESLIGADA
        self._mudar(chat_id, ch.ENCERRADA, motivo)

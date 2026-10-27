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
import asyncio
import logging
import time

from telezapp.midia import video as midia_video
from telezapp.nucleo import chamadas as ch
from telezapp.nucleo import eventos as ev

log = logging.getLogger("telezapp.chamadas")

# Quanto esperar a outra pessoa atender antes de desistir (segundos)
ESPERA_ATENDER_S = 45
# Sem quadros do outro lado por tanto tempo, a camera dele foi desligada
SEM_QUADROS_S = 3.0
LARGURA_VIDEO, ALTURA_VIDEO, QUADROS_POR_SEGUNDO = 640, 360, 15


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
        from pytgcalls.types import Device, Direction
        from pytgcalls.types.raw import VideoParameters
        self.Device, self.Direction = Device, Direction
        self.VideoParameters = VideoParameters

    def cameras(self):
        return list(self.MediaDevices.camera_devices())

    def fluxo_com_camera(self, camera, microfone):
        """Camera e microfone juntos: o py-tgcalls pede a chamada com video
        quando o fluxo tem camera."""
        return self.MediaStream(
            camera, audio_parameters=self.AudioQuality.HIGH,
            video_parameters=self.VideoParameters(
                LARGURA_VIDEO, ALTURA_VIDEO, QUADROS_POR_SEGUNDO),
            audio_path=microfone)

    def filtro_quadros(self):
        """Os quadros de camera que chegam do outro lado."""
        return self.filters.stream_frame(self.Direction.INCOMING,
                                         self.Device.CAMERA)

    def ouvir_pedidos(self, cliente, ao_pedido):
        """O py-tgcalls nao diz se a chamada que toca e de video: le o campo
        `video` do pedido no evento bruto do Telethon."""
        from telethon import events
        from telethon.tl.types import PhoneCallRequested, UpdatePhoneCall

        async def tratar(update):
            chamada = getattr(update, "phone_call", None)
            if isinstance(chamada, PhoneCallRequested):
                await ao_pedido(chamada.admin_id, bool(chamada.video))
        cliente.add_event_handler(tratar, events.Raw(UpdatePhoneCall))

    def microfones(self):
        return list(self.MediaDevices.microphone_devices())

    def saidas(self):
        return list(self.MediaDevices.speaker_devices())

    def fluxo_microfone(self, dispositivo):
        return self.MediaStream(
            dispositivo, audio_parameters=self.AudioQuality.HIGH,
            video_flags=self.MediaStream.Flags.IGNORE)

    def fluxo_saida(self, dispositivo, camera=False):
        return self.RecordStream(audio=dispositivo, camera=camera)


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
        self._cameras = []      # nomes das cameras da ultima listagem
        self.destino_video = None   # f(conversa_id, largura, altura, rgb)
        self._video_pedido = {}     # chat_id -> a chamada recebida e de video
        self._cam = {}          # chat_id -> camera: None desligada, "" a 1a
        self._ultimo_quadro = {}    # chat_id -> quando chegou o ultimo
        self._vigias = {}       # chat_id -> tarefa que vigia o video
        self._formato_visto = False

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
            if hasattr(self.motor, "filtro_quadros"):
                self.app.on_update(self.motor.filtro_quadros())(
                    self._ao_quadro)
                try:
                    self.motor.ouvir_pedidos(self.cliente, self._ao_pedido)
                except Exception:
                    log.exception("não consegui ouvir os pedidos de vídeo")
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
        if hasattr(self.motor, "cameras"):
            try:
                self._cameras = [d.title for d in self.motor.cameras()]
            except Exception:
                log.exception("erro ao listar as câmeras")

    @property
    def suporta_video(self):
        return self.pronta and hasattr(self.motor, "fluxo_com_camera")

    def cameras(self):
        """Os nomes da ultima listagem (de qualquer thread)."""
        return list(self._cameras)

    def dispositivos(self):
        """Os nomes da ultima listagem, sem tocar na NTgCalls (pode ser
        chamado de qualquer thread)."""
        mics, saidas = self._nomes
        return list(mics), list(saidas)

    # --------------------------------------------------------- estados
    def _publicar(self, c):
        c.suporta_video = self.suporta_video
        self.barramento.publicar(ev.EstadoChamada(
            self.conta_id, str(c.conversa_id), c.estado, c.nome, c.entrante,
            c.motivo, c.erro, c.video, c.camera, c.video_remoto,
            c.suporta_video))

    def _marcar_video(self, chat_id, video=None, camera=None, remoto=None):
        """Muda o que e do video na chamada e avisa a janela se mudou."""
        c = self.chamadas.get(chat_id)
        if c is None:
            return False
        mudou = c.aplicar_video(
            c.video if video is None else video,
            c.camera if camera is None else camera,
            c.video_remoto if remoto is None else remoto)
        if mudou:
            self._publicar(c)
        return mudou

    def _mudar(self, chat_id, estado, motivo="", erro=""):
        c = self.chamadas.get(chat_id)
        if c is None or not c.aplicar(estado, motivo, erro):
            return
        self._publicar(c)
        if estado == ch.ENCERRADA:
            self.chamadas.pop(chat_id, None)
            self._escolhas.pop(chat_id, None)
            self._cam.pop(chat_id, None)
            self._video_pedido.pop(chat_id, None)
            self._ultimo_quadro.pop(chat_id, None)
            vigia = self._vigias.pop(chat_id, None)
            if vigia is not None:
                vigia.cancel()

    def _nova(self, chat_id, nome, entrante, estado, video=False):
        c = ch.Chamada(self.conta_id, str(chat_id), nome, entrante, estado,
                       video=video)
        self.chamadas[chat_id] = c
        self._publicar(c)
        return c

    # ------------------------------------------------------- saida
    async def ligar(self, chat_id, microfone="", saida="", video=False,
                    camera=None):
        """`video`: chamada de video; `camera`: o nome da camera (vazio = a
        primeira) ou None para comecar sem ela."""
        if not self.pronta:
            return
        if self.chamadas:
            log.info("já existe uma chamada; ligar ignorado")
            return
        self._escolhas[chat_id] = (microfone, saida)
        self.atualizar_dispositivos()
        if video and not (self.suporta_video and self._cameras):
            self.barramento.publicar(ev.Aviso(
                self.conta_id, "Não encontrei nenhuma câmera neste "
                "computador. Ligando só com a voz.", False))
            video = False
        self._cam[chat_id] = camera if video else None
        self._nova(chat_id, await self.nome_de(chat_id), False, ch.CHAMANDO,
                   video=bool(video))
        await self._conectar(chat_id)

    async def atender(self, chat_id, microfone="", saida="", camera=None):
        c = self.chamadas.get(chat_id)
        if not self.pronta or c is None or c.estado != ch.TOCANDO:
            return
        self._escolhas[chat_id] = (microfone, saida)
        self._cam[chat_id] = camera if c.video else None
        self._mudar(chat_id, ch.CONECTANDO)
        await self._conectar(chat_id)

    # ----------------------------------------------------------- video
    def _camera_para(self, chat_id):
        """O dispositivo da camera desta chamada, ou None se ela deve ficar
        desligada. So na thread do provedor (lista pela NTgCalls)."""
        nome = self._cam.get(chat_id)
        if nome is None or not hasattr(self.motor, "cameras"):
            return None
        return _escolher(self.motor.cameras(), nome)

    def _fluxo_de_voz(self, chat_id, mic):
        """O que sai de nos: o microfone e, se a camera esta ligada, ela."""
        dispositivo = _escolher(self.motor.microfones(), mic)
        camera = self._camera_para(chat_id)
        if camera is not None:
            return self.motor.fluxo_com_camera(camera, dispositivo), True
        return self.motor.fluxo_microfone(dispositivo), False

    def _fluxo_de_saida(self, chat_id, saida):
        """O que chega: o som e, numa chamada de video, a camera dele."""
        dispositivo = _escolher(self.motor.saidas(), saida)
        c = self.chamadas.get(chat_id)
        if c is not None and c.video and \
                hasattr(self.motor, "filtro_quadros"):
            return self.motor.fluxo_saida(dispositivo, camera=True)
        return self.motor.fluxo_saida(dispositivo)

    async def ligar_camera(self, chat_id, nome=""):
        """Liga a nossa camera. Numa chamada so de voz, passa a chamada para
        video."""
        c = self.chamadas.get(chat_id)
        if c is None or c.estado != ch.EM_CHAMADA or not self.suporta_video:
            return
        self._cam[chat_id] = nome
        mic, saida = self._escolhas.get(chat_id, ("", ""))
        try:
            fluxo, com_camera = self._fluxo_de_voz(chat_id, mic)
            if not com_camera:
                raise LookupError("nenhuma câmera")
            await self.app.play(chat_id, fluxo)
            self._marcar_video(chat_id, video=True, camera=True)
            await self.app.record(chat_id, self._fluxo_de_saida(chat_id,
                                                                saida))
        except Exception:
            log.exception("não consegui ligar a câmera")
            self._cam[chat_id] = None
            self.barramento.publicar(ev.Aviso(
                self.conta_id, "Não consegui ligar a câmera.", False))

    async def desligar_camera(self, chat_id):
        """Desliga a nossa camera; a chamada segue com o som."""
        c = self.chamadas.get(chat_id)
        if c is None or not c.camera:
            return
        self._cam[chat_id] = None
        mic, _saida = self._escolhas.get(chat_id, ("", ""))
        try:
            fluxo, _ = self._fluxo_de_voz(chat_id, mic)
            await self.app.play(chat_id, fluxo)
        except Exception:
            log.exception("não consegui desligar a câmera")
        self._marcar_video(chat_id, camera=False)

    async def _ao_pedido(self, chat_id, video):
        """O pedido de chamada chegou (evento bruto): era de video?"""
        self._video_pedido[chat_id] = bool(video)
        if video:
            self._marcar_video(chat_id, video=True)

    async def _ao_quadro(self, _cliente, update):
        """Um quadro de video do outro lado."""
        chat_id = update.chat_id
        if chat_id not in self.chamadas or not update.frames:
            return
        quadro = update.frames[-1]
        largura, altura = quadro.info.width, quadro.info.height
        rgb = midia_video.quadro_para_rgb(quadro.frame, largura, altura)
        if rgb is None:
            if not self._formato_visto:
                self._formato_visto = True
                log.warning("quadro de vídeo em formato desconhecido: %d "
                            "bytes para %dx%d", len(quadro.frame), largura,
                            altura)
            return
        if not self._formato_visto:
            self._formato_visto = True
            log.info("vídeo do Telegram: formato %s, %dx%d, rotação %s",
                     midia_video.formato_do_quadro(
                         quadro.frame, largura, altura), largura, altura,
                     quadro.info.rotation)
        graus = getattr(quadro.info.rotation, "value", 0)
        rgb, largura, altura = midia_video.girar_rgb(rgb, largura, altura,
                                                     graus)
        self._ultimo_quadro[chat_id] = time.monotonic()
        self._marcar_video(chat_id, video=True, remoto=True)
        if chat_id not in self._vigias:
            self._vigias[chat_id] = asyncio.ensure_future(
                self._vigiar_video(chat_id))
        if self.destino_video is not None:
            self.destino_video(str(chat_id), largura, altura, rgb)

    async def _vigiar_video(self, chat_id):
        """Sem quadros por alguns segundos, o outro lado desligou a camera."""
        try:
            while chat_id in self.chamadas:
                await asyncio.sleep(1)
                visto = self._ultimo_quadro.get(chat_id, 0)
                if time.monotonic() - visto > SEM_QUADROS_S:
                    self._marcar_video(chat_id, remoto=False)
                    return
        finally:
            self._vigias.pop(chat_id, None)

    async def _conectar(self, chat_id):
        """Liga o microfone e a saida de som. Em chamadas feitas por nos,
        `play` so volta quando a outra pessoa atende."""
        import asyncio
        mic, saida = self._escolhas.get(chat_id, ("", ""))
        com_camera = False
        try:
            fluxo, com_camera = self._fluxo_de_voz(chat_id, mic)
            cfg = self.motor.CallConfig(timeout=self.espera_s)
            await self.app.play(chat_id, fluxo, cfg)
            if chat_id not in self.chamadas:      # desligaram nesse meio
                return
            await self.app.record(chat_id, self._fluxo_de_saida(chat_id,
                                                                saida))
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
        if com_camera:
            self._marcar_video(chat_id, camera=True)

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
                fluxo, _ = self._fluxo_de_voz(chat_id, mic)
                await self.app.play(chat_id, fluxo)
            if saida:
                await self.app.record(chat_id, self._fluxo_de_saida(
                    chat_id, sai))
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
        self._nova(chat_id, nome, True, ch.TOCANDO,
                   video=self._video_pedido.get(chat_id, False))

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

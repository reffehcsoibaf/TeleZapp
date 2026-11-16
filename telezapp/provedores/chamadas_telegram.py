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
import threading
import time

from telezapp import config
from telezapp.midia import som_pc as midia_som_pc
from telezapp.midia import video as midia_video
from telezapp.nucleo import chamadas as ch
from telezapp.nucleo import eventos as ev

log = logging.getLogger("telezapp.chamadas")

# Quanto esperar a outra pessoa atender antes de desistir (segundos)
ESPERA_ATENDER_S = 45
# Sem quadros do outro lado por tanto tempo, a camera dele foi desligada
SEM_QUADROS_S = 3.0
LARGURA_VIDEO, ALTURA_VIDEO, QUADROS_POR_SEGUNDO = 640, 360, 15
# Quando o audio sai de quadros nossos (som do computador somado ao microfone):
# 48 kHz, mono, quadros de 10 ms (480 amostras de 16 bits)
TAXA_EXTERNA = 48000
FRAME_AUDIO = 480
QUADROS_PENDENTES_MAX = 20


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
        try:
            from pytgcalls.types import ExternalMedia
            from pytgcalls.types.raw import AudioParameters
            from pytgcalls.types.stream.frame import Frame
            self.ExternalMedia = ExternalMedia
            self.AudioParameters = AudioParameters
            self.Frame = Frame
        except Exception:
            log.info("quadros externos indisponíveis neste py-tgcalls")
        try:
            from pytgcalls.types import GroupCallConfig, GroupCallParticipant
            self.GroupCallConfig = GroupCallConfig
            self.AcaoParticipante = GroupCallParticipant.Action
        except Exception:
            log.info("chat de voz de grupo indisponível neste py-tgcalls")

    def filtro_participantes(self):
        """Quem entra, sai, silencia ou levanta a mao num chat de voz."""
        return self.filters.call_participant()

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

    def fluxo_externo(self, audio, video, microfone=None, camera=None):
        """Fluxo de saida com quadros que o TeleZapp manda (compartilhar a
        tela e o som do computador). `audio`: True quando o audio sai de
        quadros nossos (microfone somado ao som do computador); senao vem do
        dispositivo `microfone`. `video`: "externo" (quadros nossos, a tela),
        "camera" (o dispositivo `camera`) ou None."""
        qualidade = self.AudioParameters(TAXA_EXTERNA, 1) if audio \
            else self.AudioQuality.HIGH
        video_params = self.VideoParameters(
            LARGURA_VIDEO, ALTURA_VIDEO, QUADROS_POR_SEGUNDO)
        ext = self.ExternalMedia
        if audio and video == "externo":
            return self.MediaStream(
                ext.AUDIO | ext.VIDEO, audio_parameters=qualidade,
                video_parameters=video_params)
        if audio and video == "camera":
            return self.MediaStream(
                camera, audio_parameters=qualidade,
                video_parameters=video_params, audio_path=ext.AUDIO)
        if audio:
            return self.MediaStream(ext.AUDIO, audio_parameters=qualidade)
        return self.MediaStream(
            ext.VIDEO, audio_parameters=qualidade,
            video_parameters=video_params, audio_path=microfone)

    async def enviar_quadro(self, app, chat_id, tipo, dados, largura=0,
                            altura=0):
        """Um quadro nosso: `tipo` "audio" (PCM s16le, 48 kHz, mono, 10 ms)
        ou "video" (I420, `largura` x `altura`)."""
        if tipo == "audio":
            await app.send_frame(chat_id, self.Device.MICROPHONE, dados)
        else:
            await app.send_frame(
                chat_id, self.Device.CAMERA, dados,
                self.Frame.Info(int(time.time() * 1000), largura, altura))

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

    def fluxo_saida(self, dispositivo, camera=False, tela=False):
        return self.RecordStream(audio=dispositivo, camera=camera,
                                 screen=tela)

    def filtro_quadros_tela(self):
        """Os quadros de tela compartilhada que chegam (so no chat de voz)."""
        return self.filters.stream_frame(self.Direction.INCOMING,
                                         self.Device.SCREEN)


def disponivel():
    """True se o py-tgcalls pode ser importado."""
    try:
        import pytgcalls  # noqa: F401
        return True
    except Exception:
        return False


def _chat_de_voz_em_uso(chamadas):
    """Ha uma sessao de chat de voz aberta (tolera objetos de teste sem
    o atributo `grupo`)."""
    grupo = getattr(chamadas, "grupo", None)
    return grupo is not None and grupo.em_uso


def _abrir_microfone(nome, taxa, amostras):
    """O microfone do Windows, em quadros de `amostras` (PCM de 16 bits,
    mono, `taxa` Hz), para o audio que montamos nos mesmos."""
    import sounddevice as sd
    from telezapp.midia import dispositivos
    fluxo = sd.RawInputStream(
        samplerate=taxa, channels=1, dtype="int16", blocksize=amostras,
        device=dispositivos.indice(nome, True))
    fluxo.start()
    return fluxo


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
        self._tela = {}         # chat_id -> a tela que estamos compartilhando
        self._som = {}          # chat_id -> o som do computador que mandamos
        self.video = midia_video        # trocavel nos testes
        self.som_pc = midia_som_pc      # trocavel nos testes
        self.abrir_microfone = _abrir_microfone   # idem
        self._nomes = ([], [])  # ultimos dispositivos vistos (microfones,
        #                         saidas); ver atualizar_dispositivos
        self._cameras = []      # nomes das cameras da ultima listagem
        self.destino_video = None   # f(conversa_id, largura, altura, rgb)
        self._video_pedido = {}     # chat_id -> a chamada recebida e de video
        self._cam = {}          # chat_id -> camera: None desligada, "" a 1a
        self._ultimo_quadro = {}    # chat_id -> quando chegou o ultimo
        self._vigias = {}       # chat_id -> tarefa que vigia o video
        self._formato_visto = False
        self._envios = {}           # (chat_id, tipo) -> [aceitos, recusados]
        self._t0 = {}               # chat_id -> quando a chamada apareceu
        self._t_em_chamada = {}     # chat_id -> quando entrou em chamada
        self._lista_logada = None
        self.grupo = None       # ChatDeVozTelegram (experimental), se houver

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
            self._iniciar_chat_de_voz()
            await self.app.start()
        except Exception as e:
            log.info("chamadas indisponíveis: %r", e)
            self.motor = self.app = None
            return False
        self.atualizar_dispositivos()
        log.info("chamadas de voz prontas")
        return True

    def _iniciar_chat_de_voz(self):
        """Chat de voz de grupo e live de canal (experimental): usa este
        mesmo PyTgCalls. Qualquer erro aqui deixa so o chat de voz de fora."""
        try:
            if not hasattr(self.motor, "filtro_participantes") or                     not hasattr(self.motor, "GroupCallConfig"):
                return
            from telezapp.provedores.chat_de_voz_telegram import (
                ChatDeVozTelegram)
            self.grupo = ChatDeVozTelegram(self)
            self.app.on_update(self.motor.filtro_participantes())(
                self.grupo.ao_participante)
            if hasattr(self.motor, "filtro_quadros_tela"):
                self.app.on_update(self.motor.filtro_quadros_tela())(
                    self._ao_quadro_do_grupo)
            try:
                self.grupo.registrar_brutos()
            except Exception:
                log.exception("não consegui ouvir os avisos de chat de voz")
        except Exception:
            log.exception("chat de voz indisponível")
            self.grupo = None

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
            if self._nomes != self._lista_logada:
                self._lista_logada = self._nomes
                log.info("dispositivos de áudio do Telegram: microfones=%s "
                         "saídas=%s", self._nomes[0], self._nomes[1])
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
    @property
    def suporta_tela(self):
        return self.suporta_video and hasattr(self.motor, "fluxo_externo")

    @property
    def suporta_som_pc(self):
        try:
            return self.pronta and hasattr(self.motor, "fluxo_externo") \
                and self.som_pc.disponivel()
        except Exception:
            return False

    def telas(self):
        """[(nome, (x, y, largura, altura))] das telas que da para mostrar."""
        try:
            return self.video.listar_telas()
        except Exception:
            return []

    def saidas_do_computador(self):
        try:
            return self.som_pc.saidas_do_computador()
        except Exception:
            return []

    def _publicar(self, c):
        c.suporta_video = self.suporta_video
        c.suporta_tela = self.suporta_tela
        c.suporta_som_pc = self.suporta_som_pc
        self.barramento.publicar(ev.EstadoChamada(
            self.conta_id, str(c.conversa_id), c.estado, c.nome, c.entrante,
            c.motivo, c.erro, c.video, c.camera, c.video_remoto,
            c.suporta_video, c.tela, c.som_pc, c.suporta_tela,
            c.suporta_som_pc))

    def _marcar_compartilhamento(self, chat_id, tela=None, som_pc=None):
        c = self.chamadas.get(chat_id)
        if c is None:
            g = getattr(self, "grupo", None)
            if g is not None and g.dentro(chat_id):
                return g.marcar_midia(tela=tela, som_pc=som_pc)
            return False
        mudou = c.aplicar_compartilhamento(
            c.tela if tela is None else tela,
            c.som_pc if som_pc is None else som_pc)
        if mudou:
            log.info("compartilhamento: tela %s, som do computador %s",
                     c.tela, c.som_pc)
            self._publicar(c)
        return mudou

    def _marcar_video(self, chat_id, video=None, camera=None, remoto=None):
        """Muda o que e do video na chamada e avisa a janela se mudou."""
        c = self.chamadas.get(chat_id)
        if c is None:
            g = getattr(self, "grupo", None)
            if g is not None and g.dentro(chat_id):
                return g.marcar_midia(camera=camera)
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
        agora = time.monotonic()
        if chat_id not in self._t0:
            self._t0[chat_id] = agora
        if estado == ch.EM_CHAMADA:
            self._t_em_chamada[chat_id] = agora
        em = self._t_em_chamada.get(chat_id)
        log.info("chamada %s: %s%s%s | %s | %.1f s desde o início%s",
                 chat_id, estado, f" ({motivo})" if motivo else "",
                 f" erro={erro}" if erro else "",
                 "recebida" if c.entrante else "feita por nós",
                 agora - self._t0[chat_id],
                 f", {agora - em:.1f} s em chamada" if em else "")
        self._publicar(c)
        if estado == ch.ENCERRADA:
            self._soltar_compartilhamento(chat_id)
            self._t0.pop(chat_id, None)
            self._t_em_chamada.pop(chat_id, None)
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
        if self.chamadas or _chat_de_voz_em_uso(self):
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

    @staticmethod
    def _logar_escolha(tipo, pedido, dispositivo):
        from telezapp.midia.dispositivos import parecem_o_mesmo
        usado = getattr(dispositivo, "title", None)
        achou = bool(pedido) and usado is not None and \
            parecem_o_mesmo(pedido, usado)
        log.info("áudio do Telegram, %s: pedido=%r, usado=%r (%s), 48000 Hz "
                 "estéreo", tipo, pedido, usado,
                 "o pedido" if achou else "padrão do sistema ou 1º da lista")

    def _fluxo_de_voz(self, chat_id, mic):
        """O que sai de nos: o microfone e, se a camera esta ligada, ela."""
        dispositivo = _escolher(self.motor.microfones(), mic)
        self._logar_escolha("microfone", mic, dispositivo)
        tela = chat_id in self._tela
        audio_nosso = chat_id in self._som
        camera = None if tela else self._camera_para(chat_id)
        if (tela or audio_nosso) and hasattr(self.motor, "fluxo_externo"):
            video = "externo" if tela else (
                "camera" if camera is not None else None)
            return (self.motor.fluxo_externo(audio_nosso, video, dispositivo,
                                             camera),
                    camera is not None)
        if camera is not None:
            return self.motor.fluxo_com_camera(camera, dispositivo), True
        return self.motor.fluxo_microfone(dispositivo), False

    def _chamada(self, chat_id):
        """A chamada 1 a 1 deste chat ou, no chat de voz, o adaptador que
        faz as rotinas de camera, tela e som funcionarem nos dois."""
        c = self.chamadas.get(chat_id)
        if c is None:
            g = getattr(self, "grupo", None)
            if g is not None:
                c = g.sombra(chat_id)
        return c

    def _fluxo_de_saida(self, chat_id, saida):
        """O que chega: o som e, numa chamada de video, a camera dele."""
        g = getattr(self, "grupo", None)
        if chat_id not in self.chamadas and g is not None and \
                g.dentro(chat_id):
            return g.fluxo_de_saida(saida)
        dispositivo = _escolher(self.motor.saidas(), saida)
        self._logar_escolha("saída (alto-falante)", saida, dispositivo)
        c = self.chamadas.get(chat_id)
        if c is not None and c.video and \
                hasattr(self.motor, "filtro_quadros"):
            return self.motor.fluxo_saida(dispositivo, camera=True)
        return self.motor.fluxo_saida(dispositivo)

    async def ligar_camera(self, chat_id, nome=""):
        """Liga a nossa camera. Numa chamada so de voz, passa a chamada para
        video."""
        c = self._chamada(chat_id)
        if c is None or c.estado != ch.EM_CHAMADA or not self.suporta_video:
            return
        self._cam[chat_id] = nome
        if chat_id in self._tela:       # a camera toma o lugar da tela
            self._parar_fonte_da_tela(chat_id)
            self._tela.pop(chat_id, None)
            self._marcar_compartilhamento(chat_id, tela=False)
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
        c = self._chamada(chat_id)
        if c is None or not c.camera:
            return
        if chat_id in self._tela:
            await self.parar_tela(chat_id)
            return
        self._cam[chat_id] = None
        mic, _saida = self._escolhas.get(chat_id, ("", ""))
        try:
            fluxo, _ = self._fluxo_de_voz(chat_id, mic)
            await self.app.play(chat_id, fluxo)
        except Exception:
            log.exception("não consegui desligar a câmera")
        self._marcar_video(chat_id, camera=False)

    # ----------------------------------- compartilhar a tela e o som do PC
    async def _tocar_de_novo(self, chat_id):
        """Refaz o fluxo de saida (o que sai de nos) e o de entrada."""
        mic, saida = self._escolhas.get(chat_id, ("", ""))
        fluxo, _ = self._fluxo_de_voz(chat_id, mic)
        await self.app.play(chat_id, fluxo)
        await self.app.record(chat_id, self._fluxo_de_saida(chat_id, saida))

    def _avisar_falha(self, texto):
        self.barramento.publicar(ev.Aviso(self.conta_id, texto, False))

    async def compartilhar_tela(self, chat_id, nome="", com_som=True):
        """Manda a tela (a `nome`; vazia = a principal) no lugar da camera.
        Por padrao leva junto o som do computador."""
        c = self._chamada(chat_id)
        if c is None or c.estado != ch.EM_CHAMADA or not self.suporta_tela:
            return False
        telas = self.telas()
        escolhida = next((t for t in telas if t[0] == nome), None) or (
            telas[0] if telas else None)
        if escolhida is None:
            self._avisar_falha("Não encontrei nenhuma tela para "
                               "compartilhar.")
            return False
        if chat_id in self._tela:
            self._parar_fonte_da_tela(chat_id)
        self._cam[chat_id] = None           # a tela toma o lugar da camera
        self._tela[chat_id] = {"nome": escolhida[0],
                               "retangulo": escolhida[1], "fonte": None,
                               "tamanho": None, "pendente": False}
        try:
            await self._tocar_de_novo(chat_id)
        except Exception:
            log.exception("não consegui compartilhar a tela")
            self._tela.pop(chat_id, None)
            self._avisar_falha("Não consegui compartilhar a tela.")
            return False
        self._iniciar_fonte_da_tela(chat_id, asyncio.get_running_loop())
        self._marcar_video(chat_id, video=True, camera=True)
        self._marcar_compartilhamento(chat_id, tela=True)
        if com_som and chat_id not in self._som:
            await self.compartilhar_som(chat_id)
        return True

    async def trocar_tela(self, chat_id, nome):
        estado = self._tela.get(chat_id)
        if estado is None:
            return
        escolhida = next((t for t in self.telas() if t[0] == nome), None)
        if escolhida is None:
            return
        self._parar_fonte_da_tela(chat_id)
        estado.update(nome=escolhida[0], retangulo=escolhida[1],
                      tamanho=None)
        self._iniciar_fonte_da_tela(chat_id, asyncio.get_running_loop())

    async def parar_tela(self, chat_id):
        if chat_id not in self._tela:
            return
        self._parar_fonte_da_tela(chat_id)
        self._tela.pop(chat_id, None)
        try:
            await self._tocar_de_novo(chat_id)
        except Exception:
            log.exception("não consegui parar a tela")
        self._marcar_video(chat_id, camera=False)
        self._marcar_compartilhamento(chat_id, tela=False)

    def _iniciar_fonte_da_tela(self, chat_id, loop):
        estado = self._tela[chat_id]

        def ao_quadro(quadro):
            try:
                if estado["pendente"]:
                    return                      # o anterior ainda nao saiu
                if estado["tamanho"] is None:
                    estado["tamanho"] = self.video.tamanho_cabivel(
                        quadro.width, quadro.height)
                largura, altura = estado["tamanho"]
                pronto = quadro.reformat(width=largura, height=altura,
                                         format="yuv420p")
                dados = pronto.to_ndarray().tobytes()
                estado["pendente"] = True
                futuro = asyncio.run_coroutine_threadsafe(
                    self.motor.enviar_quadro(self.app, chat_id, "video",
                                             dados, largura, altura), loop)
                futuro.add_done_callback(
                    lambda f: (estado.__setitem__("pendente", False),
                               self._contar_envio(chat_id, "video", f)))
            except Exception:
                estado["pendente"] = False
                log.exception("erro ao mandar um quadro da tela")
        fonte = self.video.Tela(estado["retangulo"], ao_quadro,
                                estado["nome"])
        estado["fonte"] = fonte
        fonte.iniciar()
        log.info("tela compartilhada (%s)", estado["nome"])

    def _parar_fonte_da_tela(self, chat_id):
        estado = self._tela.get(chat_id)
        if estado is not None and estado.get("fonte") is not None:
            estado["fonte"].parar()
            estado["fonte"] = None
            self._resumo_do_envio(chat_id, "video")

    def _contar_envio(self, chat_id, tipo, futuro):
        """Conta os quadros que o motor aceitou e os que recusou (o primeiro
        erro vai para o log): sem isso nao ha como saber, depois, se o
        Telegram recebeu a tela e o som."""
        conta = self._envios.setdefault((chat_id, tipo), [0, 0])
        try:
            erro = futuro.exception()
        except Exception as e:       # cancelado
            erro = e
        if erro is None:
            conta[0] += 1
            return
        conta[1] += 1
        if conta[1] == 1:
            log.warning("o Telegram recusou um quadro de %s: %r", tipo, erro)

    def _resumo_do_envio(self, chat_id, tipo):
        conta = self._envios.pop((chat_id, tipo), None)
        if conta is not None:
            log.info("quadros de %s mandados ao Telegram: %d aceitos, %d "
                     "recusados", tipo, conta[0], conta[1])

    async def compartilhar_som(self, chat_id, saida=""):
        """Manda o som do computador junto com o microfone: o audio passa a
        sair de quadros nossos (microfone somado ao som). O microfone
        continua valendo e continua podendo ser silenciado."""
        c = self._chamada(chat_id)
        if c is None or c.estado != ch.EM_CHAMADA or \
                not self.suporta_som_pc:
            return False
        if chat_id in self._som:
            self._parar_audio_nosso(chat_id)
        captura = self.som_pc.CapturaDoSom(
            saida, taxa=TAXA_EXTERNA, amostras=FRAME_AUDIO)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, captura.iniciar)
        if getattr(captura, "erro", ""):
            captura.parar()
            self._avisar_falha("Não consegui capturar o som do computador.")
            return False
        estado = {"captura": captura, "parar": threading.Event(),
                  "fio": None}
        self._som[chat_id] = estado
        try:
            if c.mudo:                  # o mute da NTgCalls calaria tudo
                try:
                    await self.app.unmute(chat_id)
                except Exception:
                    pass
            await self._tocar_de_novo(chat_id)
        except Exception:
            log.exception("não consegui compartilhar o som do computador")
            self._parar_audio_nosso(chat_id)
            self._avisar_falha("Não consegui compartilhar o som do "
                               "computador.")
            return False
        estado["fio"] = threading.Thread(
            target=self._laco_do_audio, args=(chat_id, loop, estado),
            name="chamada-audio-telegram", daemon=True)
        estado["fio"].start()
        self._marcar_compartilhamento(chat_id, som_pc=True)
        return True

    async def parar_som(self, chat_id):
        if chat_id not in self._som:
            return
        self._parar_audio_nosso(chat_id)
        c = self._chamada(chat_id)
        try:
            await self._tocar_de_novo(chat_id)
            if c is not None and c.mudo:    # voltou ao microfone do motor
                await self.app.mute(chat_id)
        except Exception:
            log.exception("não consegui parar o som do computador")
        self._marcar_compartilhamento(chat_id, som_pc=False)

    def _parar_audio_nosso(self, chat_id):
        estado = self._som.pop(chat_id, None)
        if estado is None:
            return
        estado["parar"].set()
        estado["captura"].parar()
        log.info("som do computador parado")
        self._resumo_do_envio(chat_id, "audio")

    def _laco_do_audio(self, chat_id, loop, estado):
        """Microfone + som do computador -> quadros de 10 ms para o motor.
        Silenciado, o microfone entra como silencio e o som do computador
        segue."""
        fluxo, aberto, pendentes = None, None, [0]
        silencio = bytes(FRAME_AUDIO * 2)
        try:
            while not estado["parar"].is_set():
                c = self._chamada(chat_id)
                if c is None:
                    break
                mic = self._escolhas.get(chat_id, ("", ""))[0]
                if fluxo is None or mic != aberto:
                    self._fechar_fluxo(fluxo)
                    fluxo = self.abrir_microfone(mic, TAXA_EXTERNA,
                                                 FRAME_AUDIO)
                    aberto = mic
                dados, _ = fluxo.read(FRAME_AUDIO)
                voz = silencio if c.mudo else bytes(dados)
                som = estado["captura"].ler()
                quadro = self.som_pc.misturar(voz, som)
                if pendentes[0] >= QUADROS_PENDENTES_MAX:
                    continue            # o motor nao deu conta: descarta
                pendentes[0] += 1
                futuro = asyncio.run_coroutine_threadsafe(
                    self.motor.enviar_quadro(self.app, chat_id, "audio",
                                             quadro), loop)
                futuro.add_done_callback(
                    lambda f: (pendentes.__setitem__(0, pendentes[0] - 1),
                               self._contar_envio(chat_id, "audio", f)))
        except Exception:
            log.exception("erro no áudio do compartilhamento")
        finally:
            self._fechar_fluxo(fluxo)

    @staticmethod
    def _fechar_fluxo(fluxo):
        if fluxo is None:
            return
        try:
            fluxo.stop()
            fluxo.close()
        except Exception:
            pass

    def _soltar_compartilhamento(self, chat_id):
        """A chamada acabou: para tudo o que estava sendo mandado."""
        self._parar_fonte_da_tela(chat_id)
        self._tela.pop(chat_id, None)
        self._parar_audio_nosso(chat_id)

    async def _ao_pedido(self, chat_id, video):
        """O pedido de chamada chegou (evento bruto): era de video?"""
        self._video_pedido[chat_id] = bool(video)
        if video:
            self._marcar_video(chat_id, video=True)

    async def _ao_quadro_do_grupo(self, _cliente, update):
        """Quadro de tela compartilhada num chat de voz."""
        await self._ao_quadro(_cliente, update, so_grupo=True)

    async def _ao_quadro(self, _cliente, update, so_grupo=False):
        """Um quadro de video do outro lado."""
        chat_id = update.chat_id
        if not update.frames:
            return
        grupo = getattr(self, "grupo", None)
        do_grupo = chat_id not in self.chamadas and grupo is not None \
            and grupo.aceita_quadros(chat_id)
        if so_grupo and not do_grupo:
            return
        if chat_id not in self.chamadas and not do_grupo:
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
        if do_grupo:
            if self.destino_video is not None:
                self.destino_video(str(chat_id), largura, altura, rgb)
            return
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
        log.info("chamada %s encerrada por nós (estado %s)", chat_id,
                 c.estado)
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
        if chat_id in self._som:
            # o microfone entra no que montamos: o silencio e nosso (um mute
            # da NTgCalls calaria tambem o som do computador)
            c.mudo = bool(silenciar)
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
            if microfone and chat_id not in self._som:
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
        if self.chamadas or _chat_de_voz_em_uso(self):
            # ja ha uma chamada: recusa a nova sem incomodar
            log.info("chamada recebida enquanto outra está aberta: recusada")
            try:
                await self.app.leave_call(chat_id)
            except Exception:
                pass
            return
        if not config.Config().get("avisar_chamadas_whatsapp"):
            # "Avisar chamadas recebidas" desmarcada: ignora, sem atender nem
            # recusar (o celular e os outros aparelhos seguem tocando)
            log.info("chamada recebida ignorada (aviso desligado)")
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
        grupo = getattr(self, "grupo", None)
        if grupo is not None and await grupo.ao_sair(update):
            return
        c = self.chamadas.get(chat_id)
        if c is None:
            return
        log.info("chamada %s: a biblioteca avisou que saiu da chamada "
                 "(estado %s)", chat_id, c.estado)
        if c.estado == ch.TOCANDO:
            motivo = ch.PERDIDA
        elif c.estado == ch.CHAMANDO:
            motivo = ch.RECUSADA
        elif c.estado == ch.CONECTANDO:
            motivo = ch.FALHA
        else:
            motivo = ch.DESLIGADA
        self._mudar(chat_id, ch.ENCERRADA, motivo)

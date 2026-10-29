# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Chamadas de voz 1 a 1 do WhatsApp, pelo mesmo cliente das mensagens.

A DLL do neonize de teste leva dentro o meowcaller (MIT,
github.com/purpshell/meowcaller), que fala o protocolo de chamadas do
WhatsApp (relay, codec MLow). Um unico pareamento serve para mensagens e
chamadas. Aqui ficam:

- `Ponte`: as funcoes `Call*` da DLL, por ctypes (trocavel nos testes);
- `Audio`: microfone e alto-falante pelo sounddevice, quadros de 60 ms
  (PCM s16le, 16 kHz, mono, 1920 bytes);
- `ChamadasWhatsApp`: o estado das chamadas, publicado como `EstadoChamada`
  (nucleo.chamadas), igual ao Telegram.

O protocolo vem de engenharia reversa e pode quebrar ou levar o WhatsApp a
limitar a conta. Sem a DLL de teste, as chamadas ficam indisponiveis e o
resto do aplicativo segue igual.
"""
import ctypes
import json
import logging
import threading
import time

from telezapp.nucleo import chamadas as ch
from telezapp.midia import eco as midia_eco
from telezapp.midia import video as midia_video
from telezapp.midia import prioridade
from telezapp.nucleo import eventos as ev

log = logging.getLogger("telezapp.chamadas")

BYTES_POR_QUADRO = 1920          # 960 amostras de 16 bits (60 ms a 16 kHz)
TAXA = 16000
AMOSTRAS = 960
ESPERA_ATENDER_S = 45            # chamando sem ninguem atender
FIM_DA_CHAMADA = -2              # retorno da DLL: a chamada acabou
LIMITE_DE_FALHAS = 20            # erros seguidos do som ate desistir
ESPERA_AUDIO_S = 20              # atendida, mas sem som do outro lado
QUADROS_POR_REGISTRO = 83        # um registro do eco a cada 5 s (quadros de 60 ms)
FASE_CONECTANDO = 3              # CallPhase do meowcaller: Connecting
BYTES_DO_VIDEO = 512 * 1024      # uma unidade de acesso H.264 cabe com folga
FIM_DO_VIDEO = -2                # retorno da DLL: a chamada acabou
# CallVideo: o que fazer com o video da chamada
VIDEO_PEDIR, VIDEO_ACEITAR, VIDEO_PARAR, VIDEO_LIGAR, VIDEO_DESLIGAR = (
    1, 2, 3, 4, 5)
# Ligado pela janela a partir da opcao `chamada_retornar_sem_audio`
RETORNAR_SEM_AUDIO = {"ligado": True}


def definir_retornar_sem_audio(ligado):
    RETORNAR_SEM_AUDIO["ligado"] = bool(ligado)


SEM_AUDIO_COM_RETORNO = ("A chamada foi atendida, mas o som do outro lado "
                         "não chegou. Ligando de volta para a pessoa.")
SEM_AUDIO = ("A chamada foi atendida, mas o som do outro lado não chegou. "
             "Pode ser a rede ou o firewall do Windows bloqueando o áudio "
             "da chamada. Veja se o TeleZapp está liberado no firewall e "
             "tente de novo.")


class Ponte:
    """As funcoes `Call*` da DLL. `uuid` e o identificador do cliente."""

    def __init__(self, uuid, gocode=None):
        self.uuid = uuid if isinstance(uuid, bytes) else str(uuid).encode()
        self.go = gocode or self._carregar()
        self._preparar()

    @staticmethod
    def _carregar():
        from neonize._binder import gocode
        return gocode

    @classmethod
    def disponivel(cls, gocode=None):
        """True se a DLL tem as funcoes de chamada."""
        try:
            go = gocode or cls._carregar()
            return all(hasattr(go, n) for n in (
                "CallsConfigure", "CallsNextEvent", "CallDial", "CallAnswer",
                "CallHangup", "CallReadAudio", "CallWriteAudio"))
        except Exception:
            return False

    @classmethod
    def configurar(cls, ligado, gocode=None):
        """Antes de conectar: pede a DLL para instalar o meowcaller no
        cliente (ele precisa estar la antes de a conexao abrir)."""
        go = gocode or cls._carregar()
        go.CallsConfigure.argtypes = [ctypes.c_int]
        go.CallsConfigure(1 if ligado else 0)

    def _preparar(self):
        g, c = self.go, ctypes
        g.CallsEnabled.argtypes = [c.c_char_p]
        g.CallsEnabled.restype = c.c_int
        g.CallsNextEvent.argtypes = [c.c_char_p, c.c_char_p, c.c_int, c.c_int]
        g.CallsNextEvent.restype = c.c_int
        g.CallDial.argtypes = [c.c_char_p, c.c_char_p, c.c_char_p, c.c_int]
        g.CallDial.restype = c.c_int
        g.CallAnswer.argtypes = [c.c_char_p, c.c_char_p]
        g.CallAnswer.restype = c.c_int
        g.CallHangup.argtypes = [c.c_char_p, c.c_char_p]
        g.CallHangup.restype = c.c_int
        g.CallReadAudio.argtypes = [c.c_char_p, c.c_char_p, c.c_char_p,
                                    c.c_int, c.c_int]
        g.CallReadAudio.restype = c.c_int
        g.CallWriteAudio.argtypes = [c.c_char_p, c.c_char_p, c.c_char_p,
                                     c.c_int]
        g.CallWriteAudio.restype = c.c_int
        self._buf_ev = ctypes.create_string_buffer(4096)
        self._buf_audio = ctypes.create_string_buffer(BYTES_POR_QUADRO)
        if self.suporta_video():
            g.CallDialWith.argtypes = [c.c_char_p, c.c_char_p, c.c_int,
                                       c.c_char_p, c.c_int]
            g.CallDialWith.restype = c.c_int
            g.CallVideo.argtypes = [c.c_char_p, c.c_char_p, c.c_int]
            g.CallVideo.restype = c.c_int
            g.CallWriteVideo.argtypes = [c.c_char_p, c.c_char_p, c.c_char_p,
                                         c.c_int, c.c_int]
            g.CallWriteVideo.restype = c.c_int
            g.CallReadVideo.argtypes = [c.c_char_p, c.c_char_p, c.c_char_p,
                                        c.c_int, c.c_int]
            g.CallReadVideo.restype = c.c_int
            self._buf_video = ctypes.create_string_buffer(BYTES_DO_VIDEO)

    def ligada(self):
        return self.go.CallsEnabled(self.uuid) == 1

    def proximo_evento(self, espera_ms=500):
        """Um evento (dict), None se nada chegou, ou False se a fila ainda
        nao existe (o cliente nao conectou)."""
        n = self.go.CallsNextEvent(self.uuid, self._buf_ev, 4096, espera_ms)
        if n > 0:
            return json.loads(self._buf_ev.value.decode("utf-8"))
        return False if n < 0 else None

    def suporta_video(self):
        """True se a DLL tem as funcoes de video das chamadas."""
        return all(hasattr(self.go, n) for n in (
            "CallDialWith", "CallVideo", "CallWriteVideo", "CallReadVideo"))

    def ligar(self, destino, video=False):
        """(id_da_chamada, peer, erro)."""
        buf = ctypes.create_string_buffer(1024)
        if video:
            n = self.go.CallDialWith(self.uuid, destino.encode(), 1, buf,
                                     1024)
        else:
            n = self.go.CallDial(self.uuid, destino.encode(), buf, 1024)
        if n <= 0:
            return "", "", "A DLL não respondeu."
        r = json.loads(buf.value.decode("utf-8"))
        if "call" not in r:
            return "", "", r.get("error", "erro desconhecido")
        return r["call"], r.get("peer", ""), ""

    def video(self, chamada, acao):
        """Pedir, aceitar ou parar o video; ligar ou desligar a camera."""
        return self.go.CallVideo(self.uuid, chamada.encode(), acao) == 0

    def escrever_video(self, chamada, unidade, duracao_ms=100):
        """False ate o outro lado confirmar o nosso video."""
        return self.go.CallWriteVideo(self.uuid, chamada.encode(), unidade,
                                      len(unidade), duracao_ms) == 0

    def ler_video(self, chamada, espera_ms=500):
        """Bytes de uma unidade de acesso, None (nada a tempo) ou False
        (a chamada acabou)."""
        n = self.go.CallReadVideo(self.uuid, chamada.encode(),
                                  self._buf_video, BYTES_DO_VIDEO, espera_ms)
        if n > 0:
            return self._buf_video.raw[:n]
        return False if n == FIM_DO_VIDEO else None

    def atender(self, chamada):
        return self.go.CallAnswer(self.uuid, chamada.encode()) == 0

    def desligar(self, chamada):
        return self.go.CallHangup(self.uuid, chamada.encode()) == 0

    def ler_quadro(self, chamada, espera_ms=100):
        """Bytes de um quadro, None (nada a tempo) ou False (acabou)."""
        n = self.go.CallReadAudio(self.uuid, chamada.encode(),
                                  self._buf_audio, BYTES_POR_QUADRO,
                                  espera_ms)
        if n == BYTES_POR_QUADRO:
            return self._buf_audio.raw
        return False if n == FIM_DA_CHAMADA else None

    def escrever_quadro(self, chamada, dados):
        return self.go.CallWriteAudio(self.uuid, chamada.encode(), dados,
                                      BYTES_POR_QUADRO) == 0


class Audio:
    """Microfone e alto-falante pelo sounddevice. Trocavel nos testes."""

    @staticmethod
    def listar():
        """([microfones], [saidas]) do Windows (sem repetir por API)."""
        import sounddevice as sd
        mics, saidas = [], []
        try:
            api = sd.query_hostapis(sd.default.hostapi)
            for i in api["devices"]:
                d = sd.query_devices(i)
                if d["max_input_channels"] > 0:
                    mics.append(d["name"])
                if d["max_output_channels"] > 0:
                    saidas.append(d["name"])
        except Exception:
            log.exception("erro ao listar dispositivos de áudio")
        return mics, saidas

    @staticmethod
    def _indice(nome, entrada):
        import sounddevice as sd
        if not nome:
            return None
        try:
            api = sd.query_hostapis(sd.default.hostapi)
            for i in api["devices"]:
                d = sd.query_devices(i)
                canais = d["max_input_channels" if entrada
                           else "max_output_channels"]
                if canais > 0 and d["name"] == nome:
                    return i
        except Exception:
            pass
        return None

    def abrir_microfone(self, nome):
        import sounddevice as sd
        fluxo = sd.RawInputStream(
            samplerate=TAXA, channels=1, dtype="int16", blocksize=AMOSTRAS,
            device=self._indice(nome, True))
        fluxo.start()
        return fluxo

    def abrir_saida(self, nome):
        import sounddevice as sd
        fluxo = sd.RawOutputStream(
            samplerate=TAXA, channels=1, dtype="int16", blocksize=AMOSTRAS,
            device=self._indice(nome, False))
        fluxo.start()
        return fluxo


class _Ligacao:
    """Uma chamada em andamento: ids, motivo desejado e as threads de audio."""

    def __init__(self, chamada, call_id=""):
        self.chamada = chamada          # ch.Chamada
        self.call_id = call_id
        self.intencao = ""              # motivo se fomos nos a encerrar
        self.rejeitada = False          # a DLL disse "rejected"
        self.mic = self.saida = ""
        self.erro = ""                  # explicacao se a intencao for FALHA
        self.audio_iniciado = False
        self.eco = None                 # midia.eco.CancelaEco da chamada
        self.retorno = None             # midia.eco.CancelaRetorno da chamada
        self.quadros_retorno = 0
        self.quadros_mic = 0
        self.vigia_audio = False
        self.parar = threading.Event()
        self.trocar_mic = threading.Event()
        self.trocar_saida = threading.Event()
        self.threads = []
        self.camera_nome = None         # None = camera desligada; "" = a 1a
        self.camera = None              # midia.video.Camera
        self.codificador = None         # midia.video.Codificador
        self.recebendo_video = False


class ChamadasWhatsApp:
    def __init__(self, ponte, conta_id, barramento, conversa_do_peer,
                 nome_de, destino_de, audio=None, espera_s=ESPERA_ATENDER_S,
                 espera_audio_s=ESPERA_AUDIO_S):
        """conversa_do_peer(peer) -> id da conversa; nome_de(cid) -> nome;
        destino_de(cid) -> texto para ligar (numero ou endereco)."""
        self.ponte = ponte
        self.conta_id = conta_id
        self.barramento = barramento
        self.conversa_do_peer = conversa_do_peer
        self.nome_de = nome_de
        self.destino_de = destino_de
        self.audio = audio or Audio()
        self.espera_s = espera_s
        self.espera_audio_s = espera_audio_s
        self.destino_video = None       # f(cid, largura, altura, rgb), da janela
        self.video = midia_video        # trocavel nos testes
        self.ligacoes = {}              # id da conversa -> _Ligacao
        self._trava = threading.RLock()
        self._parar = threading.Event()
        self._thread = None
        self._nomes = ([], [])

    # ---------------------------------------------------------- inicio
    def iniciar(self):
        self.atualizar_dispositivos()
        self._thread = threading.Thread(
            target=self._ouvir, name="chamadas-whatsapp", daemon=True)
        self._thread.start()

    def parar(self):
        self._parar.set()
        with self._trava:
            for lig in list(self.ligacoes.values()):
                lig.parar.set()

    @property
    def pronta(self):
        try:
            return self.ponte.ligada()
        except Exception:
            return False

    @property
    def suporta_video(self):
        try:
            return self.ponte.suporta_video() and self.video.disponivel()
        except Exception:
            return False

    def cameras(self):
        try:
            return self.video.listar_cameras()
        except Exception:
            return []

    def atualizar_dispositivos(self):
        try:
            self._nomes = self.audio.listar()
        except Exception:
            log.exception("erro ao listar dispositivos de áudio")

    def dispositivos(self):
        mics, saidas = self._nomes
        return list(mics), list(saidas)

    # --------------------------------------------------------- estados
    def _publicar(self, c):
        c.suporta_video = self.suporta_video
        self.barramento.publicar(ev.EstadoChamada(
            self.conta_id, str(c.conversa_id), c.estado, c.nome, c.entrante,
            c.motivo, c.erro, c.video, c.camera, c.video_remoto,
            c.suporta_video))

    def _mudar(self, cid, estado, motivo="", erro=""):
        with self._trava:
            lig = self.ligacoes.get(cid)
            if lig is None or not lig.chamada.aplicar(estado, motivo, erro):
                return
            c = lig.chamada
            if estado == ch.ENCERRADA:
                lig.parar.set()
                self._parar_camera(lig)
                self.ligacoes.pop(cid, None)
        self._publicar(c)

    def _achar(self, call_id):
        with self._trava:
            for cid, lig in self.ligacoes.items():
                if lig.call_id == call_id:
                    return cid, lig
        return None, None

    # ------------------------------------------------ eventos da DLL
    def _ouvir(self):
        while not self._parar.is_set():
            try:
                e = self.ponte.proximo_evento(500)
            except Exception:
                log.exception("erro ao ler eventos de chamada")
                time.sleep(1)
                continue
            if e is False:              # fila ainda nao existe
                time.sleep(1)
                continue
            if e is None:
                continue
            try:
                self._tratar(e)
            except Exception:
                log.exception("erro ao tratar evento de chamada: %r", e)

    def _tratar(self, e):
        tipo, call_id = e.get("ev"), e.get("call", "")
        if tipo == "incoming":
            self._ao_receber(call_id, e.get("peer", ""),
                             bool(e.get("video")))
        elif tipo == "video":
            cid, lig = self._achar(call_id)
            if lig is not None:
                self._ao_video_do_outro(cid, lig, e)
        elif tipo == "keyframe":
            cid, lig = self._achar(call_id)
            if lig is not None and lig.codificador is not None:
                lig.codificador.pedir_quadro_chave()
        elif tipo == "state":
            fase = e.get("phase")
            log.info("chamada %s: fase %s", call_id, fase)
            cid, lig = self._achar(call_id)
            # na chamada de saida a fase Connecting vem quando o relay e
            # alocado, ainda tocando: so a de entrada (que atendemos) conta
            if lig is not None and fase == FASE_CONECTANDO and                     lig.chamada.entrante:
                self._ao_conectar(cid, lig)
        elif tipo == "accepted":
            cid, lig = self._achar(call_id)
            if lig is not None and not lig.chamada.entrante:
                log.info("chamada %s: a outra pessoa atendeu", call_id)
                self._ao_conectar(cid, lig)
        elif tipo == "ready":
            cid, lig = self._achar(call_id)
            if lig is not None:
                log.info("chamada %s: som do outro lado chegando", call_id)
                self._mudar(cid, ch.EM_CHAMADA)
                self._iniciar_audio(cid, lig)
                self._iniciar_video(cid, lig)
        elif tipo == "end":
            cid, lig = self._achar(call_id)
            if lig is not None:
                self._ao_terminar(cid, lig, e.get("reason", ""))

    def _ao_conectar(self, cid, lig):
        """A chamada foi atendida (por nos ou pelo outro lado) e o som esta
        sendo aberto. Mostra
        "conectando" em vez de seguir chamando, abre o microfone e o
        alto-falante ja e, se o som do outro lado nao chegar a tempo, encerra
        explicando (sem isso a chamada ficava tocando para sempre enquanto a
        outra pessoa ja estava em chamada)."""
        if lig.chamada.estado == ch.CHAMANDO:
            self._mudar(cid, ch.CONECTANDO)
        self._iniciar_audio(cid, lig)
        self._vigiar_audio(cid, lig)

    def _vigiar_audio(self, cid, lig):
        with self._trava:
            if lig.vigia_audio:
                return
            lig.vigia_audio = True

        def vigia():
            fim = time.monotonic() + self.espera_audio_s
            while time.monotonic() < fim:
                if lig.parar.wait(0.5):
                    return
            if lig.chamada.estado == ch.CONECTANDO:
                log.warning("chamada atendida, mas sem som do outro lado "
                            "em %ds; encerrando", self.espera_audio_s)
                voltar = lig.chamada.entrante and \
                    RETORNAR_SEM_AUDIO["ligado"]
                erro = SEM_AUDIO_COM_RETORNO if voltar else SEM_AUDIO
                lig.intencao, lig.erro = ch.FALHA, erro
                if not self.ponte.desligar(lig.call_id):
                    self._mudar(cid, ch.ENCERRADA, ch.FALHA, erro)
                if voltar:
                    threading.Thread(target=self._ligar_de_volta,
                                     args=(cid, lig),
                                     name="chamada-de-volta",
                                     daemon=True).start()
        threading.Thread(target=vigia, name="chamada-vigia-audio",
                         daemon=True).start()

    def _ligar_de_volta(self, cid, lig):
        """Chamada recebida sem som do outro lado: a de saida costuma
        funcionar, entao liga para a mesma pessoa assim que a anterior
        terminar (a de saida nunca volta a ligar, sem repeticao)."""
        fim = time.monotonic() + 8
        while time.monotonic() < fim:
            if self._parar.is_set():
                return
            with self._trava:
                livre = cid not in self.ligacoes
            if livre:
                break
            time.sleep(0.2)
        else:
            log.warning("não liguei de volta: a chamada anterior não acabou")
            return
        log.info("ligando de volta para a conversa da chamada sem som")
        self.ligar(cid, lig.mic, lig.saida, video=lig.chamada.video,
                   camera=lig.camera_nome)

    def _ao_receber(self, call_id, peer, video=False):
        cid = self.conversa_do_peer(peer)
        with self._trava:
            ocupado = bool(self.ligacoes)
        if ocupado or not cid:
            log.info("chamada recebida com outra aberta: recusada")
            self.ponte.desligar(call_id)
            return
        try:
            nome = self.nome_de(cid)
        except Exception:
            nome = ""
        self.atualizar_dispositivos()
        c = ch.Chamada(self.conta_id, cid, nome, True, ch.TOCANDO,
                       video=bool(video))
        with self._trava:
            self.ligacoes[cid] = _Ligacao(c, call_id)
        self._publicar(c)

    def _ao_terminar(self, cid, lig, razao):
        c = lig.chamada
        if lig.intencao:
            motivo, erro = lig.intencao, lig.erro
        elif razao.startswith("server"):
            motivo, erro = ch.FALHA, ("O WhatsApp recusou a chamada (%s)."
                                      % razao)
        elif c.estado == ch.TOCANDO:
            motivo, erro = ch.PERDIDA, ""
        elif c.estado == ch.CHAMANDO:
            motivo = ch.RECUSADA if razao == "rejected" else ch.SEM_RESPOSTA
            erro = ""
        elif c.estado == ch.CONECTANDO:
            motivo, erro = ch.FALHA, "A chamada caiu ao conectar."
        else:
            motivo, erro = ch.DESLIGADA, ""
        self._mudar(cid, ch.ENCERRADA, motivo, erro)

    # ------------------------------------------------------- saida
    def ligar(self, cid, microfone="", saida="", video=False, camera=None):
        """`video`: chamada de video; `camera`: o nome da camera (vazio = a
        primeira) ou None para comecar com ela desligada."""
        with self._trava:
            if self.ligacoes:
                log.info("já existe uma chamada; ligar ignorado")
                return
            try:
                nome = self.nome_de(cid)
            except Exception:
                nome = ""
            video = bool(video) and self.suporta_video
            c = ch.Chamada(self.conta_id, cid, nome, False, ch.CHAMANDO,
                           video=video)
            lig = _Ligacao(c)
            lig.mic, lig.saida = microfone, saida
            lig.camera_nome = camera if video else None
            self.ligacoes[cid] = lig
        self.atualizar_dispositivos()
        self._publicar(c)
        threading.Thread(target=self._discar, args=(cid, lig),
                         name="chamada-discar", daemon=True).start()

    def _discar(self, cid, lig):
        call_id, _peer, erro = self.ponte.ligar(self.destino_de(cid),
                                                lig.chamada.video)
        if erro:
            log.warning("não foi possível ligar: %s", erro)
            self._mudar(cid, ch.ENCERRADA, ch.FALHA,
                        "Não foi possível ligar: %s" % erro)
            return
        with self._trava:
            lig.call_id = call_id
            desistiu = lig.intencao
        if desistiu:                   # a pessoa cancelou durante a discagem
            self.ponte.desligar(call_id)
            return
        self._esperar_atender(cid, lig)

    def _esperar_atender(self, cid, lig):
        def vigia():
            fim = time.monotonic() + self.espera_s
            while time.monotonic() < fim:
                if lig.parar.wait(0.5):
                    return
            if lig.chamada.estado == ch.CHAMANDO:
                log.info("ninguém atendeu em %ds", self.espera_s)
                lig.intencao = ch.SEM_RESPOSTA
                self.ponte.desligar(lig.call_id)
        threading.Thread(target=vigia, name="chamada-vigia",
                         daemon=True).start()

    # ----------------------------------------------------- controles
    def atender(self, cid, microfone="", saida="", camera=None):
        with self._trava:
            lig = self.ligacoes.get(cid)
            if lig is None or lig.chamada.estado != ch.TOCANDO:
                return
            lig.mic, lig.saida = microfone, saida
            lig.camera_nome = camera if lig.chamada.video else None
        self._mudar(cid, ch.CONECTANDO)
        self._vigiar_audio(cid, lig)
        if not self.ponte.atender(lig.call_id):
            self._mudar(cid, ch.ENCERRADA, ch.FALHA,
                        "Não foi possível atender a chamada.")

    def encerrar(self, cid):
        with self._trava:
            lig = self.ligacoes.get(cid)
            if lig is None:
                return
            c = lig.chamada
            if c.estado == ch.TOCANDO:
                lig.intencao = ch.RECUSADA
            elif c.estado in (ch.CHAMANDO, ch.CONECTANDO):
                lig.intencao = ch.CANCELADA
            else:
                lig.intencao = ch.DESLIGADA
            call_id = lig.call_id
        if call_id:
            if self.ponte.desligar(call_id):
                return
        # a DLL nao conhece mais a chamada (ou ainda esta discando)
        if call_id:
            self._mudar(cid, ch.ENCERRADA, lig.intencao)

    def silenciar(self, cid, silenciar):
        with self._trava:
            lig = self.ligacoes.get(cid)
            if lig is None or lig.chamada.estado != ch.EM_CHAMADA:
                return
            lig.chamada.mudo = bool(silenciar)

    def trocar_dispositivos(self, cid, microfone="", saida=""):
        with self._trava:
            lig = self.ligacoes.get(cid)
            if lig is None or lig.chamada.estado != ch.EM_CHAMADA:
                return
            lig.mic = microfone or lig.mic
            lig.saida = saida or lig.saida
        if microfone:
            lig.trocar_mic.set()
        if saida:
            lig.trocar_saida.set()

    # ----------------------------------------------------------- video
    def _iniciar_video(self, cid, lig):
        """Chamada de video que conectou: comeca a ler o video do outro lado
        e, se a camera foi pedida, a ligar."""
        if not lig.chamada.video or not self.suporta_video:
            return
        self._receber_video_em_segundo_plano(cid, lig)
        if lig.camera_nome is not None:
            self._iniciar_camera(cid, lig, lig.camera_nome)

    def _marcar_video(self, cid, lig, video=None, camera=None, remoto=None):
        """Muda o que e do video na chamada e avisa a janela se mudou."""
        with self._trava:
            c = lig.chamada
            mudou = c.aplicar_video(
                c.video if video is None else video,
                c.camera if camera is None else camera,
                c.video_remoto if remoto is None else remoto)
        if mudou:
            self._publicar(c)
        return mudou

    def _ao_video_do_outro(self, cid, lig, e):
        """O outro lado ligou ou desligou a camera, ou pediu para passar a
        chamada para video (aceito na hora; a nossa camera continua como
        estava)."""
        if e.get("upgrade"):
            if self.suporta_video and self.ponte.video(lig.call_id,
                                                       VIDEO_ACEITAR):
                log.info("chamada %s: o outro lado pediu video; aceito",
                         lig.call_id)
            else:
                log.warning("chamada %s: não consegui aceitar o video do "
                            "outro lado", lig.call_id)
        if e.get("upgrade") or e.get("active"):
            self._marcar_video(cid, lig, video=True,
                               remoto=bool(e.get("active")))
            if lig.chamada.estado in (ch.CONECTANDO, ch.EM_CHAMADA):
                self._receber_video_em_segundo_plano(cid, lig)
        else:
            self._marcar_video(cid, lig, remoto=False)

    def _receber_video_em_segundo_plano(self, cid, lig):
        with self._trava:
            if lig.recebendo_video:
                return
            lig.recebendo_video = True
        t = threading.Thread(target=self._receber_video, args=(cid, lig),
                             name="chamada-video", daemon=True)
        lig.threads.append(t)
        t.start()

    def _receber_video(self, cid, lig):
        """DLL -> decodificador -> a janela."""
        try:
            dec = self.video.Decodificador()
            while not lig.parar.is_set():
                unidade = self.ponte.ler_video(lig.call_id, 500)
                if unidade is False:
                    break
                if not unidade:
                    continue
                for largura, altura, rgb in dec.decodificar(unidade):
                    if not lig.chamada.video_remoto:
                        self._marcar_video(cid, lig, video=True, remoto=True)
                    if self.destino_video is not None:
                        self.destino_video(cid, largura, altura, rgb)
        except Exception:
            log.exception("erro ao receber o vídeo da chamada")
        finally:
            lig.recebendo_video = False
            log.info("vídeo do outro lado encerrado")

    def _iniciar_camera(self, cid, lig, nome):
        """Abre a camera `nome` (vazio = a primeira) e manda o video."""
        if lig.camera is not None:
            return True
        escolhida = nome or next(iter(self.cameras()), "")
        if not escolhida:
            log.warning("nenhuma câmera encontrada")
            self.barramento.publicar(ev.Aviso(
                self.conta_id, "Não encontrei nenhuma câmera neste "
                "computador.", False))
            return False
        lig.codificador = self.video.Codificador()

        def ao_quadro(quadro):
            for unidade in lig.codificador.codificar(quadro):
                self.ponte.escrever_video(lig.call_id, unidade,
                                          self.video.QUADRO_MS)
        lig.camera = self.video.Camera(escolhida, ao_quadro)
        lig.camera.iniciar()
        log.info("câmera ligada (%s)", escolhida)
        self._marcar_video(cid, lig, camera=True)
        return True

    def _parar_camera(self, lig):
        camera, lig.camera = lig.camera, None
        if camera is not None:
            camera.parar()
        if lig.codificador is not None:
            lig.codificador.fechar()
            lig.codificador = None

    def ligar_camera(self, cid, nome=""):
        """Liga a nossa camera. Numa chamada so de voz, pede ao outro lado
        para passar a video."""
        with self._trava:
            lig = self.ligacoes.get(cid)
        if lig is None or lig.chamada.estado != ch.EM_CHAMADA or \
                not self.suporta_video:
            return
        lig.camera_nome = nome
        if not lig.chamada.video:
            if not self.ponte.video(lig.call_id, VIDEO_PEDIR):
                self.barramento.publicar(ev.Aviso(
                    self.conta_id, "Não consegui passar a chamada para "
                    "vídeo.", False))
                return
            self._marcar_video(cid, lig, video=True)
            self._receber_video_em_segundo_plano(cid, lig)
        else:
            self.ponte.video(lig.call_id, VIDEO_LIGAR)
        self._iniciar_camera(cid, lig, nome)

    def desligar_camera(self, cid):
        """Desliga a nossa camera; a chamada segue (de video, sem a nossa
        imagem)."""
        with self._trava:
            lig = self.ligacoes.get(cid)
        if lig is None or lig.camera is None:
            return
        self._parar_camera(lig)
        lig.camera_nome = None
        self.ponte.video(lig.call_id, VIDEO_DESLIGAR)
        self._marcar_video(cid, lig, camera=False)

    # ----------------------------------------------------------- audio
    def _iniciar_audio(self, cid, lig):
        with self._trava:
            if lig.audio_iniciado:
                return
            lig.audio_iniciado = True
        if midia_eco.LIGADOS["eco"] or midia_eco.LIGADOS["ruido"]:
            lig.eco = midia_eco.CancelaEco(midia_eco.LIGADOS["eco"],
                                           midia_eco.LIGADOS["ruido"])
        if midia_eco.LIGADOS["retorno"]:
            lig.retorno = midia_eco.CancelaRetorno()
        for alvo, nome in ((self._enviar, "chamada-mic"),
                           (self._receber, "chamada-voz")):
            t = threading.Thread(target=alvo, args=(lig,), name=nome,
                                 daemon=True)
            lig.threads.append(t)
            t.start()

    def _abrir(self, abrir, nome, o_que):
        """Abre o microfone ou a saida pelo nome escolhido; se o dispositivo
        nao abrir, tenta o padrao do Windows (sem o som a chamada ficaria
        muda dos dois lados, sem a pessoa saber por que)."""
        try:
            fluxo = abrir(nome)
            log.info("%s aberto (%s)", o_que, nome or "padrão do Windows")
            return fluxo
        except Exception:
            if not nome:
                raise
            log.exception("%s '%s' não abriu; usando o padrão do Windows",
                          o_que, nome)
            fluxo = abrir("")
            log.info("%s aberto (padrão do Windows)", o_que)
            return fluxo

    def _fechar(self, fluxo):
        if fluxo is None:
            return
        try:
            fluxo.stop()
            fluxo.close()
        except Exception:
            pass

    def _enviar(self, lig):
        """Microfone -> DLL. Silenciado, manda silencio (o ritmo continua).
        Um erro passageiro do microfone ou da DLL nao derruba o envio: so a
        chamada que acabou (ou erros demais seguidos) o encerra."""
        silencio = bytes(BYTES_POR_QUADRO)
        fluxo, falhas, enviados = None, 0, 0
        ident = prioridade.thread_de_audio()
        try:
            while not lig.parar.is_set():
                try:
                    if fluxo is None or lig.trocar_mic.is_set():
                        self._fechar(fluxo)
                        fluxo = None
                        lig.trocar_mic.clear()
                        if lig.eco is not None:
                            lig.eco.reiniciar()
                        fluxo = self._abrir(self.audio.abrir_microfone,
                                            lig.mic, "microfone")
                    dados, _ = fluxo.read(AMOSTRAS)
                    if lig.chamada.mudo:
                        dados = silencio
                    elif lig.eco is not None:
                        dados = self._sem_eco(lig, bytes(dados))
                    self._avisar_retorno(lig, bytes(dados))
                    if not self.ponte.escrever_quadro(lig.call_id,
                                                      bytes(dados)):
                        falhas += 1
                        if falhas >= LIMITE_DE_FALHAS:
                            break
                        continue
                    falhas = 0
                    enviados += 1
                except Exception:
                    falhas += 1
                    log.exception("erro no microfone da chamada")
                    self._fechar(fluxo)
                    fluxo = None
                    if falhas >= LIMITE_DE_FALHAS:
                        break
                    lig.parar.wait(0.5)
        finally:
            self._fechar(fluxo)
            prioridade.soltar_thread(ident)
            log.info("microfone da chamada encerrado (%d quadros enviados)",
                     enviados)

    def _avisar_retorno(self, lig, dados):
        """Diz ao tira-retorno o que estamos mandando (a referencia dele)."""
        if lig.retorno is None:
            return
        try:
            lig.retorno.enviado(dados)
        except Exception:
            log.exception("erro no cancelamento do retorno; desligado")
            lig.retorno = None

    def _sem_retorno(self, lig, quadro):
        """O quadro recebido sem o retorno da nossa voz, se ele existir."""
        if lig.retorno is None:
            return quadro
        try:
            limpo = lig.retorno.recebido(quadro)
        except Exception:
            log.exception("erro no cancelamento do retorno; desligado")
            lig.retorno = None
            return quadro
        if lig.quadros_retorno % QUADROS_POR_REGISTRO == 0:
            log.info("retorno da chamada: %s", lig.retorno.diagnostico())
        lig.quadros_retorno += 1
        return limpo

    def _sem_eco(self, lig, dados):
        """O quadro do microfone sem eco nem ruido; qualquer problema manda o
        quadro como veio (a chamada nunca fica muda por isso). A cada 5 s
        registra no log quanto eco chega ao microfone e quanto sobra."""
        try:
            limpo = lig.eco.processar(dados)
            if len(limpo) != len(dados):
                return dados
            lig.quadros_mic += 1
            if lig.quadros_mic % QUADROS_POR_REGISTRO == 0:
                log.info("eco da chamada: %s", lig.eco.diagnostico())
            return limpo
        except Exception:
            log.exception("erro no cancelamento de eco")
            lig.eco = None
            return dados

    def _receber(self, lig):
        """DLL -> alto-falante, com a mesma tolerancia a erros do envio."""
        fluxo, falhas, tocados = None, 0, 0
        ident = prioridade.thread_de_audio()
        try:
            while not lig.parar.is_set():
                try:
                    if fluxo is None or lig.trocar_saida.is_set():
                        self._fechar(fluxo)
                        fluxo = None
                        lig.trocar_saida.clear()
                        if lig.eco is not None:
                            lig.eco.reiniciar()
                        fluxo = self._abrir(self.audio.abrir_saida,
                                            lig.saida, "alto-falante")
                    quadro = self.ponte.ler_quadro(lig.call_id, 100)
                    if quadro is False:
                        break
                    if quadro:
                        quadro = self._sem_retorno(lig, quadro)
                        fluxo.write(quadro)
                        tocados += 1
                        if lig.eco is not None:
                            lig.eco.referencia(quadro)
                    falhas = 0
                except Exception:
                    falhas += 1
                    log.exception("erro no alto-falante da chamada")
                    self._fechar(fluxo)
                    fluxo = None
                    if falhas >= LIMITE_DE_FALHAS:
                        break
                    lig.parar.wait(0.5)
        finally:
            self._fechar(fluxo)
            prioridade.soltar_thread(ident)
            log.info("alto-falante da chamada encerrado (%d quadros "
                     "tocados)", tocados)

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
import sys
import threading
import time
import traceback

from telezapp.nucleo import chamadas as ch
from telezapp.midia import eco as midia_eco
from telezapp.midia import som_pc as midia_som_pc
from telezapp.midia import video as midia_video
from telezapp.midia import prioridade
from telezapp.nucleo import eventos as ev

log = logging.getLogger("telezapp.chamadas")

# O WhatsApp nao deixa ligar para grupos com mais gente que isso
LIMITE_DO_GRUPO = 32
# Quanto esperar o convite de um grupo (evento "offer") depois do "incoming"
ESPERA_DA_OFERTA_S = 2.0
# Quanto tempo um convite de chamada em grupo continua valendo para entrar
VALIDADE_DA_OFERTA_S = 3600

BYTES_POR_QUADRO = 1920          # 960 amostras de 16 bits (60 ms a 16 kHz)
TAXA = 16000
AMOSTRAS = 960
ESPERA_ATENDER_S = 45            # chamando sem ninguem atender
FIM_DA_CHAMADA = -2              # retorno da DLL: a chamada acabou
LIMITE_DE_FALHAS = 20            # erros seguidos do som ate desistir
ESPERA_AUDIO_S = 20              # atendida, mas sem som do outro lado
PERIODO_DO_DIAGNOSTICO_S = 5     # janela do diagnostico do alto-falante
MINIMO_DE_QUADROS_TOCADOS = 20   # em 5 s (o normal passa de 70)
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
        self._preparar_grupo()
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

    def _preparar_grupo(self):
        """As funcoes de chamada em grupo, so se a DLL as tem."""
        g, c = self.go, ctypes
        if hasattr(g, "CallGroupDial"):
            g.CallGroupDial.argtypes = [c.c_char_p, c.c_char_p, c.c_int,
                                        c.c_char_p, c.c_int]
            g.CallGroupDial.restype = c.c_int
        if self.suporta_em_andamento():
            g.CallLobby.argtypes = [c.c_char_p, c.c_char_p, c.c_char_p,
                                    c.c_char_p, c.c_int]
            g.CallLobby.restype = c.c_int
            g.CallJoinOngoing.argtypes = [c.c_char_p, c.c_char_p, c.c_char_p,
                                          c.c_int, c.c_char_p, c.c_int]
            g.CallJoinOngoing.restype = c.c_int
            g.CallRoster.argtypes = [c.c_char_p, c.c_char_p, c.c_char_p,
                                     c.c_int]
            g.CallRoster.restype = c.c_int
        if hasattr(g, "CallAddParticipant"):
            g.CallAddParticipant.argtypes = [c.c_char_p, c.c_char_p,
                                             c.c_char_p, c.c_char_p, c.c_int]
            g.CallAddParticipant.restype = c.c_int

    def suporta_grupo(self):
        return hasattr(self.go, "CallGroupDial")

    def suporta_em_andamento(self):
        return all(hasattr(self.go, n) for n in (
            "CallLobby", "CallJoinOngoing", "CallRoster"))

    def suporta_adicionar(self):
        return hasattr(self.go, "CallAddParticipant")

    def _json(self, funcao, *args, tamanho=16384):
        """Chama uma funcao da DLL que escreve JSON e devolve o dict, ou
        {"error": texto} se ela nao respondeu."""
        buf = ctypes.create_string_buffer(tamanho)
        n = funcao(self.uuid, *args, buf, tamanho)
        if n <= 0:
            return {"error": "A DLL não respondeu."}
        try:
            return json.loads(buf.value.decode("utf-8"))
        except ValueError:
            return {"error": "Resposta ilegível da DLL."}

    def ligar_grupo(self, grupo, video=False):
        """(id_da_chamada, erro): liga para todos os membros do grupo."""
        r = self._json(self.go.CallGroupDial, grupo.encode(),
                       1 if video else 0, tamanho=1024)
        if "call" not in r:
            return "", r.get("error", "erro desconhecido")
        return r["call"], ""

    def lobby(self, chamada, criador):
        """Como esta uma chamada em grupo de que nao participamos:
        {"call", "groupJid", "video", "participants"}, {"over": True} ou
        {"error"}."""
        return self._json(self.go.CallLobby, chamada.encode(),
                          criador.encode())

    def entrar(self, chamada, criador, video=False):
        """(id_da_chamada, erro): entra numa chamada em grupo em andamento."""
        r = self._json(self.go.CallJoinOngoing, chamada.encode(),
                       criador.encode(), 1 if video else 0, tamanho=1024)
        if "call" not in r:
            return "", r.get("error", "erro desconhecido")
        return r["call"], ""

    def roster(self, chamada):
        """Lista [{"jid", "pn", "state"}] de quem esta na chamada, ou None se
        a DLL nao conhece a chamada."""
        r = self._json(self.go.CallRoster, chamada.encode())
        if "participants" not in r:
            return None
        return r["participants"]

    def adicionar(self, chamada, alvo):
        """Convida `alvo` (numero ou LID): "invited", "rang" ou "failed"."""
        r = self._json(self.go.CallAddParticipant, chamada.encode(),
                       alvo.encode(), tamanho=1024)
        if r.get("rang"):
            return "rang"
        return "invited" if r.get("ok") else "failed"

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


class _DiagnosticoDoAltoFalante:
    """A cada 5 s da chamada, registra quantos quadros o alto-falante tocou e
    quanto tempo o laco gastou em cada etapa (ler da DLL, tirar o retorno,
    escrever no dispositivo, passar a referencia ao eco). Se tocou muito
    menos do que devia (o som do outro lado parado), grava tambem o que cada
    thread do programa estava fazendo, para achar o que segura o laco."""

    def __init__(self, call_id, agora=time.monotonic):
        self.call_id = call_id
        self._agora = agora
        self._inicio = agora()
        self.quadros = 0
        self.leitura = self.retorno = self.escrita = self.referencia = 0.0
        self.maior_escrita = 0.0
        self.pilhas = 0

    def tocou(self, retorno, escrita):
        self.quadros += 1
        self.retorno += retorno
        self.escrita += escrita
        self.maior_escrita = max(self.maior_escrita, escrita)

    def periodo(self):
        agora = self._agora()
        if agora - self._inicio < PERIODO_DO_DIAGNOSTICO_S:
            return
        self._inicio = agora
        log.info("alto-falante da chamada %s, %ds: tocou %d quadros; tempo em "
                 "leitura=%.2fs retorno=%.2fs escrita=%.2fs (maior %.0f ms) "
                 "referencia=%.2fs", self.call_id, PERIODO_DO_DIAGNOSTICO_S,
                 self.quadros, self.leitura, self.retorno, self.escrita,
                 self.maior_escrita * 1000, self.referencia)
        if self.quadros < MINIMO_DE_QUADROS_TOCADOS and self.pilhas < 2:
            self.pilhas += 1
            log.warning("alto-falante da chamada %s tocou so %d quadros em "
                        "%d s; threads:\n%s", self.call_id, self.quadros,
                        PERIODO_DO_DIAGNOSTICO_S, pilhas_das_threads())
        self.quadros = 0
        self.leitura = self.retorno = self.escrita = self.referencia = 0.0
        self.maior_escrita = 0.0


def pilhas_das_threads():
    """Texto com a pilha de cada thread (nome e as ultimas chamadas)."""
    nomes = {t.ident: t.name for t in threading.enumerate()}
    partes = []
    for ident, quadro in sys._current_frames().items():
        pilha = "".join(traceback.format_stack(quadro, limit=6))
        partes.append("--- %s\n%s" % (nomes.get(ident, ident), pilha))
    return "\n".join(partes)


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


# quanto esperar a chamada atual acabar ao trocar para a segunda (segundos)
ESPERA_PARA_TROCAR_S = 6.0


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
        self.camera = None              # midia.video.Camera (ou Tela)
        self.tela_ativa = False         # o "camera" acima e uma Tela
        self.som_pc = None              # midia.som_pc.CapturaDoSom
        self.som_pc_saida = ""          # a saida de som que esta sendo captada
        self.eco_pc = None              # tira a voz do outro do som captado
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
        self.oferta_velha = None        # f(call_id): ja nao esta tocando
        self.video = midia_video        # trocavel nos testes
        self.som_pc = midia_som_pc      # trocavel nos testes
        self.ligacoes = {}              # id da conversa -> _Ligacao
        # chamadas em grupo (recurso experimental): o provedor liga e le
        # as caixas de Configuracoes, Recursos experimentais
        self.grupo_ligado = lambda: False
        self.andamento_ligado = lambda: False
        self.adicionar_ligado = lambda: False
        self.nome_de_jid = lambda jid, pn="": ""   # nome de um participante
        self.membros_de = lambda cid: None         # [jid] do grupo, ou None
        self._ofertas = {}              # call_id -> convite de chamada em grupo
        # segunda chamada com outra em andamento (recurso experimental)
        self.espera_ligada = lambda: False
        self._espera = {}               # id da conversa -> _Ligacao tocando
        self._trocando = False          # estamos trocando de chamada
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

    @property
    def suporta_som_pc(self):
        try:
            return self.som_pc.disponivel()
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
        # em grupo so ha voz: video e tela ficam de fora
        c.suporta_video = self.suporta_video and not c.grupo
        c.suporta_tela = self.suporta_video and not c.grupo
        c.suporta_som_pc = self.suporta_som_pc
        c.suporta_adicionar = self._pode_convidar(c)
        self.barramento.publicar(ev.EstadoChamada(
            self.conta_id, str(c.conversa_id), c.estado, c.nome, c.entrante,
            c.motivo, c.erro, c.video, c.camera, c.video_remoto,
            c.suporta_video, c.tela, c.som_pc, c.suporta_tela,
            c.suporta_som_pc, c.grupo, tuple(c.participantes),
            c.suporta_adicionar))

    def _pode_convidar(self, c):
        """Da para convidar mais gente? So em chamada em andamento e com a
        caixa dos Recursos experimentais marcada."""
        try:
            return bool(c.estado == ch.EM_CHAMADA and self.adicionar_ligado()
                        and self.ponte.suporta_adicionar())
        except Exception:
            return False

    def _mudar(self, cid, estado, motivo="", erro=""):
        with self._trava:
            lig = self.ligacoes.get(cid)
            if lig is None or not lig.chamada.aplicar(estado, motivo, erro):
                return
            c = lig.chamada
            if estado == ch.ENCERRADA:
                lig.parar.set()
                self._parar_camera(lig)
                self._parar_som_pc(lig)
                self.ligacoes.pop(cid, None)
        self._publicar(c)
        if estado == ch.ENCERRADA:
            self._promover_espera()

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
        if tipo == "offer":
            self._ao_convite_de_grupo(e)
        elif tipo == "group":
            cid, lig = self._achar(call_id)
            if lig is not None:
                self._atualizar_participantes(cid, lig)
        elif tipo == "incoming":
            self._ao_receber(call_id, e.get("peer", ""),
                             bool(e.get("video")), bool(e.get("group")))
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
            self._esquecer_convite(call_id)
            if self._acabou_a_espera(call_id):
                return
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

    def _ao_receber(self, call_id, peer, video=False, grupo=False):
        # sem desligar: a chamada pode seguir em outro aparelho
        if self.oferta_velha is not None and self.oferta_velha(call_id):
            return
        grupo = bool(grupo) and self.grupo_ligado()
        cid = self._grupo_da_oferta(call_id) if grupo else ""
        if not cid:
            cid = self.conversa_do_peer(peer)
            grupo = False          # sem saber o grupo, toca como antes
        with self._trava:
            ocupado = bool(self.ligacoes)
            pode_esperar = (ocupado and bool(cid) and not grupo
                            and not self._espera and cid not in self.ligacoes
                            and self._espera_ligada())
        if pode_esperar:
            self._receber_em_espera(cid, call_id, bool(video))
            return
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
                       video=bool(video) and not grupo, grupo=grupo)
        with self._trava:
            self.ligacoes[cid] = _Ligacao(c, call_id)
        self._publicar(c)

    # ------------------------------------------ segunda chamada (experimental)
    def _espera_ligada(self):
        try:
            return bool(self.espera_ligada())
        except Exception:
            return False

    def _receber_em_espera(self, cid, call_id, video):
        """Chegou uma chamada com outra em andamento: guarda e avisa, sem
        atender nem recusar. A pessoa escolhe (recusar_espera ou
        aceitar_espera)."""
        try:
            nome = self.nome_de(cid)
        except Exception:
            nome = ""
        c = ch.Chamada(self.conta_id, cid, nome, True, ch.TOCANDO,
                       video=video)
        with self._trava:
            self._espera[cid] = _Ligacao(c, call_id)
        log.info("segunda chamada em espera: %s", call_id)
        self.barramento.publicar(ev.ChamadaEmEspera(
            self.conta_id, str(cid), nome, video, "tocando"))

    def _acabou_a_espera(self, call_id):
        """A chamada em espera terminou (quem ligou desistiu)? Avisa e
        esquece; True se era ela."""
        with self._trava:
            achou = next((cid for cid, lig in self._espera.items()
                          if lig.call_id == call_id), None)
            lig = self._espera.pop(achou, None) if achou else None
        if lig is None:
            return False
        c = lig.chamada
        self.barramento.publicar(ev.ChamadaEmEspera(
            self.conta_id, str(achou), c.nome, c.video, "perdida"))
        return True

    def _promover_espera(self):
        """A chamada atual acabou e a outra ainda toca: passa a tocar como
        uma chamada comum (a menos que estejamos trocando de chamada)."""
        with self._trava:
            if self._trocando or self.ligacoes or not self._espera:
                return
            cid, lig = next(iter(self._espera.items()))
            self._espera.pop(cid)
            self.ligacoes[cid] = lig
        self._publicar(lig.chamada)

    def recusar_espera(self, cid):
        """Recusa a segunda chamada; a atual segue."""
        with self._trava:
            lig = self._espera.pop(cid, None)
        if lig is None:
            return
        c = lig.chamada
        self.ponte.desligar(lig.call_id)
        self.barramento.publicar(ev.ChamadaEmEspera(
            self.conta_id, str(cid), c.nome, c.video, "recusada"))

    def aceitar_espera(self, cid, microfone="", saida="", camera=None):
        """Encerra a chamada atual e atende a segunda. Se a atual nao acabar
        a tempo, a segunda continua em espera."""
        with self._trava:
            lig = self._espera.get(cid)
            if lig is None:
                return
            atuais = list(self.ligacoes)
            self._trocando = True
        try:
            for outra in atuais:
                self.encerrar(outra)
            fim = time.monotonic() + ESPERA_PARA_TROCAR_S
            while time.monotonic() < fim:
                with self._trava:
                    if not self.ligacoes:
                        break
                time.sleep(0.05)
            with self._trava:
                if self.ligacoes or self._espera.get(cid) is not lig:
                    livre = False
                else:
                    self._espera.pop(cid)
                    self.ligacoes[cid] = lig
                    livre = True
        finally:
            self._trocando = False
        if not livre:
            self._avisar("Não consegui encerrar a chamada atual a tempo. A "
                         "chamada em espera continua tocando.")
            return
        log.info("troca de chamada: atendendo a segunda (%s)", lig.call_id)
        self.atender(cid, microfone, saida, camera)

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
        grupo = cid.endswith("@g.us")
        if grupo and not self._pode_ligar_para_grupo(cid):
            return
        with self._trava:
            if self.ligacoes:
                log.info("já existe uma chamada; ligar ignorado")
                return
            try:
                nome = self.nome_de(cid)
            except Exception:
                nome = ""
            video = bool(video) and self.suporta_video and not grupo
            c = ch.Chamada(self.conta_id, cid, nome, False, ch.CHAMANDO,
                           video=video, grupo=grupo)
            lig = _Ligacao(c)
            lig.mic, lig.saida = microfone, saida
            lig.camera_nome = camera if video else None
            self.ligacoes[cid] = lig
        self.atualizar_dispositivos()
        self._publicar(c)
        threading.Thread(target=self._discar, args=(cid, lig),
                         name="chamada-discar", daemon=True).start()

    def _avisar(self, texto):
        self.barramento.publicar(ev.Aviso(self.conta_id, texto, False))

    def _pode_ligar_para_grupo(self, cid):
        """Confere o que a chamada em grupo exige; avisa e devolve False se
        nao da."""
        if not (self.grupo_ligado() and self.ponte.suporta_grupo()):
            self._avisar("Chamadas em grupo não estão disponíveis. Marque a "
                         "caixa em Configurações, Recursos experimentais.")
            return False
        try:
            membros = self.membros_de(cid)
        except Exception:
            membros = None
        if membros is not None and len(membros) > LIMITE_DO_GRUPO:
            self._avisar("O WhatsApp não deixa ligar para grupos com mais "
                         "de %d participantes." % LIMITE_DO_GRUPO)
            return False
        return True

    def _discar(self, cid, lig):
        if lig.chamada.grupo:
            call_id, erro = self.ponte.ligar_grupo(cid, False)
            _peer = ""
        else:
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

    # ------------------------------------------- chamada em grupo
    def _ao_convite_de_grupo(self, e):
        """Chegou o convite de uma chamada em grupo (tocando ou nao): guarda
        para poder entrar nela enquanto durar."""
        if not self.grupo_ligado():
            return
        call_id, grupo = e.get("call", ""), e.get("group", "")
        if not call_id or not grupo:
            return
        agora = time.monotonic()
        with self._trava:
            self._ofertas = {k: v for k, v in self._ofertas.items()
                             if agora - v["quando"] < VALIDADE_DA_OFERTA_S}
            self._ofertas[call_id] = {
                "grupo": grupo, "criador": e.get("creator", ""),
                "video": bool(e.get("video")), "quando": agora}
        try:
            cid = self.conversa_do_peer(grupo)
        except Exception:
            cid = ""
        if cid and self.andamento_ligado():
            self.barramento.publicar(ev.ChamadaEmAndamento(
                self.conta_id, cid, call_id, e.get("creator", ""),
                bool(e.get("video")), True))

    def _esquecer_convite(self, call_id):
        with self._trava:
            oferta = self._ofertas.pop(call_id, None)
        if oferta is None or not self.andamento_ligado():
            return
        try:
            cid = self.conversa_do_peer(oferta["grupo"])
        except Exception:
            return
        self.barramento.publicar(ev.ChamadaEmAndamento(
            self.conta_id, cid, call_id, oferta["criador"], oferta["video"],
            False))

    def _grupo_da_oferta(self, call_id):
        """O id da conversa do grupo de uma chamada que esta tocando. O
        convite pode chegar um instante depois do aviso de chamada."""
        fim = time.monotonic() + ESPERA_DA_OFERTA_S
        while True:
            with self._trava:
                oferta = self._ofertas.get(call_id)
            if oferta is not None:
                try:
                    return self.conversa_do_peer(oferta["grupo"])
                except Exception:
                    return ""
            if time.monotonic() >= fim:
                return ""
            time.sleep(0.05)

    def _atualizar_participantes(self, cid, lig):
        """Le a lista de quem esta na chamada em grupo e avisa a janela."""
        if not lig.call_id:
            return
        try:
            lista = self.ponte.roster(lig.call_id)
        except Exception:
            log.exception("erro ao ler os participantes da chamada")
            return
        if lista is None:
            return
        novos = []
        for p in lista:
            jid = p.get("pn") or p.get("jid", "")
            try:
                nome = self.nome_de_jid(p.get("jid", ""), p.get("pn", ""))
            except Exception:
                nome = ""
            novos.append((jid, nome, p.get("state", "")))
        novos.sort(key=lambda x: (x[2] != ch.CONECTADO,
                                  (x[1] or "").casefold()))
        with self._trava:
            c = lig.chamada
            mudou = not c.grupo or c.participantes != novos
            c.grupo = True
            c.participantes = novos
        if mudou:
            self._publicar(c)

    def adicionar(self, cid, alvos):
        """Convida gente para a chamada em andamento. `alvos`: [(jid, nome)].
        Avisa o resultado de cada um."""
        with self._trava:
            lig = self.ligacoes.get(cid)
        if lig is None or lig.chamada.estado != ch.EM_CHAMADA or \
                not lig.call_id:
            self._avisar("Só dá para convidar com a chamada em andamento.")
            return
        if not (self.adicionar_ligado() and self.ponte.suporta_adicionar()):
            self._avisar("Convidar para a chamada não está disponível.")
            return

        def trabalho():
            resultados = []
            for jid, nome in list(alvos)[:LIMITE_DO_GRUPO - 1]:
                try:
                    estado = self.ponte.adicionar(lig.call_id, jid)
                except Exception:
                    log.exception("erro ao convidar para a chamada")
                    estado = "failed"
                resultados.append((nome, estado))
            self.barramento.publicar(ev.ResultadoDeConvites(
                self.conta_id, cid, tuple(resultados)))
            self._atualizar_participantes(cid, lig)
        threading.Thread(target=trabalho, name="chamada-convidar",
                         daemon=True).start()

    def entrar_em_andamento(self, cid, call_id, microfone="", saida=""):
        """Entra na chamada em grupo `call_id` que ja esta acontecendo no
        grupo `cid` (o convite chegou antes e continua valendo)."""
        with self._trava:
            oferta = self._ofertas.get(call_id)
            ocupado = bool(self.ligacoes)
        if ocupado:
            self._avisar("Já há uma chamada em andamento.")
            return
        if oferta is None or not (self.andamento_ligado()
                                  and self.ponte.suporta_em_andamento()):
            self._avisar("Não achei essa chamada em andamento.")
            return
        threading.Thread(target=self._entrar,
                         args=(cid, call_id, oferta, microfone, saida),
                         name="chamada-entrar", daemon=True).start()

    def _entrar(self, cid, call_id, oferta, microfone="", saida=""):
        r = self.ponte.lobby(call_id, oferta["criador"])
        if r.get("over"):
            self._avisar("Essa chamada em grupo já terminou.")
            self._esquecer_convite(call_id)
            return
        if "error" in r:
            self._avisar("Não consegui saber como está a chamada em grupo.")
            return
        with self._trava:
            if self.ligacoes:
                return
            try:
                nome = self.nome_de(cid)
            except Exception:
                nome = ""
            c = ch.Chamada(self.conta_id, cid, nome, False, ch.CONECTANDO,
                           grupo=True)
            lig = _Ligacao(c)
            lig.mic, lig.saida = microfone, saida
            self.ligacoes[cid] = lig
        self.atualizar_dispositivos()
        self._publicar(c)
        nova, erro = self.ponte.entrar(call_id, oferta["criador"],
                                       bool(r.get("video")))
        if erro:
            log.warning("não consegui entrar na chamada em grupo: %s", erro)
            self._mudar(cid, ch.ENCERRADA, ch.FALHA,
                        "Não consegui entrar na chamada em grupo.")
            return
        with self._trava:
            lig.call_id = nova
        self._ao_conectar(cid, lig)

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
        if not lig.chamada.video or not self.suporta_video or \
                lig.chamada.grupo:
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
        lig.tela_ativa = False
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
        if lig.tela_ativa:          # a camera toma o lugar da tela
            self._parar_camera(lig)
            self._marcar_video(cid, lig, camera=False)
            self._marcar_compartilhamento(cid, lig, tela=False)
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
        self._marcar_compartilhamento(cid, lig, tela=False)

    # ---------------------------------------------- compartilhar a tela
    def compartilhar_tela(self, cid, nome="", com_som=True):
        """Manda a tela (a `nome`; vazio = a principal) no lugar da camera.
        Por padrao leva junto o som do computador."""
        with self._trava:
            lig = self.ligacoes.get(cid)
        if lig is None or lig.chamada.estado != ch.EM_CHAMADA or \
                not self.suporta_video:
            return False
        telas = self.telas()
        escolhida = next((t for t in telas if t[0] == nome), None) \
            or (telas[0] if telas else None)
        if escolhida is None:
            self.barramento.publicar(ev.Aviso(
                self.conta_id, "Não encontrei nenhuma tela para "
                "compartilhar.", False))
            return False
        if lig.camera is not None:      # a tela toma o lugar da camera
            self._parar_camera(lig)
            self.ponte.video(lig.call_id, VIDEO_DESLIGAR)
        if not lig.chamada.video:
            if not self.ponte.video(lig.call_id, VIDEO_PEDIR):
                self.barramento.publicar(ev.Aviso(
                    self.conta_id, "Não consegui passar a chamada para "
                    "vídeo.", False))
                return False
            self._marcar_video(cid, lig, video=True)
            self._receber_video_em_segundo_plano(cid, lig)
        else:
            self.ponte.video(lig.call_id, VIDEO_LIGAR)
        lig.codificador = self.video.Codificador()

        def ao_quadro(quadro):
            for unidade in lig.codificador.codificar(quadro):
                self.ponte.escrever_video(lig.call_id, unidade,
                                          self.video.QUADRO_MS)
        lig.camera = self.video.Tela(escolhida[1], ao_quadro, escolhida[0])
        lig.tela_ativa = True
        lig.camera.iniciar()
        log.info("tela compartilhada (%s)", escolhida[0])
        self._marcar_video(cid, lig, camera=True)
        self._marcar_compartilhamento(cid, lig, tela=True)
        if com_som and lig.som_pc is None:
            self.compartilhar_som(cid)
        return True

    def parar_tela(self, cid):
        with self._trava:
            lig = self.ligacoes.get(cid)
        if lig is None or not lig.tela_ativa:
            return
        self.desligar_camera(cid)

    def trocar_tela(self, cid, nome):
        """Troca a tela que esta sendo compartilhada."""
        with self._trava:
            lig = self.ligacoes.get(cid)
        if lig is None or not lig.tela_ativa:
            return
        com_som = lig.som_pc is not None
        self._parar_camera(lig)
        self.compartilhar_tela(cid, nome, com_som=False)
        if com_som and lig.som_pc is None:
            self.compartilhar_som(cid)

    # --------------------------------------- som do computador na chamada
    def compartilhar_som(self, cid, saida=""):
        """Manda, junto com o microfone, o som que toca em `saida` (vazio: a
        saida padrao do Windows). O microfone segue valendo (e continua
        podendo ser silenciado). A voz do outro lado e retirada do que sai:
        se o computador toca a chamada na mesma saida que e captada, o
        TeleZapp subtrai o que ele mesmo esta tocando."""
        with self._trava:
            lig = self.ligacoes.get(cid)
        if lig is None or lig.chamada.estado != ch.EM_CHAMADA or \
                not self.suporta_som_pc:
            return False
        if lig.som_pc is not None:
            self._parar_som_pc(lig)
        lig.som_pc_saida = saida
        captura = self.som_pc.CapturaDoSom(saida)
        lig.som_pc = captura
        captura.iniciar()
        if getattr(captura, "erro", ""):
            self._parar_som_pc(lig)
            self.barramento.publicar(ev.Aviso(
                self.conta_id, "Não consegui capturar o som do "
                "computador.", False))
            return False
        self._preparar_eco_do_som_pc(lig)
        self._marcar_compartilhamento(cid, lig, som_pc=True)
        return True

    def _preparar_eco_do_som_pc(self, lig):
        """Liga o tira-voz quando a saida captada e a mesma em que a chamada
        toca (ela e o que volta para o outro lado)."""
        lig.eco_pc = None
        if getattr(lig.som_pc, "exato", False):
            log.info("som do computador: captura por processo, sem o som "
                     "do TeleZapp (a voz do outro lado não entra)")
            return
        capturada = lig.som_pc_saida or self.som_pc.saida_padrao()
        tocando = lig.saida or self.som_pc.saida_padrao()
        from telezapp.midia.dispositivos import parecem_o_mesmo
        if capturada and tocando and not parecem_o_mesmo(capturada, tocando):
            log.info("som do computador: a chamada toca em outra saida "
                     "(%s); a voz do outro lado não entra", tocando)
            return
        lig.eco_pc = midia_eco.CancelaEco(eco=True, ruido=False)
        log.info("som do computador: tirando a voz do outro lado do que "
                 "sai (saida %s)", capturada or "padrão")

    def parar_som(self, cid):
        with self._trava:
            lig = self.ligacoes.get(cid)
        if lig is None or lig.som_pc is None:
            return
        self._parar_som_pc(lig)
        self._marcar_compartilhamento(cid, lig, som_pc=False)

    def _parar_som_pc(self, lig):
        captura, lig.som_pc = lig.som_pc, None
        lig.eco_pc = None
        if captura is not None:
            captura.parar()
            log.info("som do computador parado (%d quadros captados)",
                     getattr(captura, "quadros", 0))

    def _marcar_compartilhamento(self, cid, lig, tela=None, som_pc=None):
        with self._trava:
            c = lig.chamada
            antes = (c.tela, c.som_pc)
            mudou = c.aplicar_compartilhamento(
                c.tela if tela is None else tela,
                c.som_pc if som_pc is None else som_pc)
        if mudou:
            log.info("compartilhamento: tela %s -> %s, som do computador "
                     "%s -> %s", antes[0], c.tela, antes[1], c.som_pc)
            self._publicar(c)
        return mudou

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
                    dados = self._com_som_do_computador(lig, bytes(dados))
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

    def _com_som_do_computador(self, lig, dados):
        """O quadro do microfone (ou o silencio, se silenciado) somado ao som
        do computador, sem a voz do outro lado. Qualquer problema: o quadro
        segue como estava, so com o microfone."""
        captura = lig.som_pc
        if captura is None:
            return dados
        try:
            som = captura.ler()
            eco = lig.eco_pc
            if eco is not None:
                limpo = eco.processar(som)
                if len(limpo) == len(som):
                    som = limpo
            return self.som_pc.misturar(dados, som)
        except Exception:
            log.exception("erro no som do computador da chamada; desligado")
            self._parar_som_pc(lig)
            return dados

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
        diag = _DiagnosticoDoAltoFalante(lig.call_id)
        try:
            while not lig.parar.is_set():
                try:
                    diag.periodo()
                    if fluxo is None or lig.trocar_saida.is_set():
                        self._fechar(fluxo)
                        fluxo = None
                        lig.trocar_saida.clear()
                        if lig.eco is not None:
                            lig.eco.reiniciar()
                        fluxo = self._abrir(self.audio.abrir_saida,
                                            lig.saida, "alto-falante")
                    t0 = time.perf_counter()
                    quadro = self.ponte.ler_quadro(lig.call_id, 100)
                    t1 = time.perf_counter()
                    diag.leitura += t1 - t0
                    if quadro is False:
                        break
                    if quadro:
                        quadro = self._sem_retorno(lig, quadro)
                        t2 = time.perf_counter()
                        fluxo.write(quadro)
                        t3 = time.perf_counter()
                        tocados += 1
                        diag.tocou(t2 - t1, t3 - t2)
                        if lig.eco is not None:
                            lig.eco.referencia(quadro)
                        if lig.eco_pc is not None:
                            lig.eco_pc.referencia(quadro)
                        diag.referencia += time.perf_counter() - t3
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

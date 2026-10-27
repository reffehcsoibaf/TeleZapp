# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Video das chamadas: a camera, o codificador e o decodificador H.264.

O meowcaller leva o video do WhatsApp como H.264 em unidades de acesso
Annex-B (os NAL de um quadro, com os codigos de inicio) e nao codifica nem
decodifica pixels. Aqui isso e feito com o PyAV, que ja vem no TeleZapp, sem
ffmpeg externo:

- `Camera`: abre a camera do Windows (DirectShow) e entrega ate 10 quadros por
  segundo;
- `Codificador`: quadros da camera -> H.264 baseline, sem quadros B, um
  quadro-chave por segundo e o cabecalho (SPS/PPS) em cada um, um delimitador
  antes de cada quadro (que e retirado: o outro lado nao precisa dele);
- `Decodificador`: unidades de acesso -> imagens RGB.

Os parametros seguem os que o WinZapp mediu em chamadas reais (10 quadros por
segundo, no maximo 640x360, 400 kb/s, uma thread so: mais threads seguram uns
dez quadros e dao um segundo de atraso).
"""
import logging
import threading
import time
from fractions import Fraction

log = logging.getLogger("telezapp.video")

FPS = 10
QUADRO_MS = 1000 // FPS
LARGURA_MAX, ALTURA_MAX = 640, 360
BITS_POR_SEGUNDO = 400_000
TIPO_DELIMITADOR = 9             # NAL "access unit delimiter"
INICIO = b"\x00\x00\x01"


# ---------------------------------------------------------------- Annex-B
def _nals(dados):
    """[(inicio do codigo de inicio, inicio do cabecalho do NAL)]."""
    achados, i = [], dados.find(INICIO)
    while i >= 0 and i + 3 < len(dados):
        codigo = i - 1 if i > 0 and dados[i - 1] == 0 else i
        achados.append((codigo, i + 3))
        i = dados.find(INICIO, i + 3)
    return achados


def sem_delimitadores(unidade):
    """A unidade de acesso sem os NAL delimitadores (tipo 9)."""
    nals = _nals(unidade)
    if not nals:
        return unidade
    partes = []
    for n, (codigo, cabecalho) in enumerate(nals):
        fim = nals[n + 1][0] if n + 1 < len(nals) else len(unidade)
        if unidade[cabecalho] & 0x1F != TIPO_DELIMITADOR:
            partes.append(unidade[codigo:fim])
    return b"".join(partes)


def tem_quadro_chave(unidade):
    """True se a unidade traz um quadro IDR (NAL tipo 5)."""
    return any(unidade[cabecalho] & 0x1F == 5
               for _codigo, cabecalho in _nals(unidade))


def tamanho_cabivel(largura, altura, max_l=LARGURA_MAX, max_a=ALTURA_MAX):
    """(largura, altura) pares que cabem em max_l x max_a mantendo a
    proporcao (o H.264 em 4:2:0 pede medidas pares)."""
    if largura <= 0 or altura <= 0:
        return max_l, max_a
    escala = min(max_l / largura, max_a / altura, 1.0)
    return (max(2, int(largura * escala) // 2 * 2),
            max(2, int(altura * escala) // 2 * 2))


def disponivel():
    """True se o PyAV tem o codificador libx264 e o decodificador H.264."""
    try:
        import av
        av.codec.Codec("libx264", "w")
        av.codec.Codec("h264", "r")
        return True
    except Exception:
        return False


# ----------------------------------------------------------------- camera
def listar_cameras():
    """Nomes das cameras do Windows (DirectShow), na ordem em que o Windows
    as lista. O PyAV so as conta pelo registro do ffmpeg, entao o nome vem
    dali."""
    try:
        import re
        import av
        with av.logging.Capture() as registro:
            av.logging.set_level(av.logging.INFO)
            try:
                av.open("video=dummy", format="dshow",
                        options={"list_devices": "true"})
            except Exception:
                pass            # o ffmpeg sempre "falha" ao listar
        texto = "".join(m[2] for m in registro if len(m) > 2)
        nomes = []
        # cada dispositivo: "Nome" (video) ou "Nome" (audio)
        for achado in re.finditer(r'"([^"\n]+)"\s*\((video|audio)\)', texto):
            if achado.group(2) == "video" and achado.group(1) not in nomes:
                nomes.append(achado.group(1))
        return nomes
    except Exception:
        log.exception("erro ao listar as câmeras")
        return []


class Camera:
    """Le a camera numa thread e chama `ao_quadro(av.VideoFrame)` ate 10
    vezes por segundo."""

    def __init__(self, nome, ao_quadro):
        self.nome, self.ao_quadro = nome, ao_quadro
        self._parar = threading.Event()
        self._thread = None
        self.erro = ""

    def iniciar(self):
        self._thread = threading.Thread(target=self._ler, daemon=True,
                                        name="camera")
        self._thread.start()

    def parar(self):
        self._parar.set()

    def _abrir(self):
        import av
        return av.open("video=%s" % self.nome, format="dshow",
                       options={"rtbufsize": "20M"})

    def _ler(self):
        recipiente = None
        try:
            recipiente = self._abrir()
            ultimo = 0.0
            for quadro in recipiente.decode(video=0):
                if self._parar.is_set():
                    break
                agora = time.monotonic()
                if agora - ultimo < QUADRO_MS / 1000.0 * 0.9:
                    continue          # a camera entrega mais que 10 por s
                ultimo = agora
                self.ao_quadro(quadro)
        except Exception as e:
            self.erro = "%s: %s" % (type(e).__name__, e)
            if not self._parar.is_set():
                log.warning("a câmera parou: %s", self.erro)
        finally:
            if recipiente is not None:
                try:
                    recipiente.close()
                except Exception:
                    pass


# ------------------------------------------------------------ codificador
class Codificador:
    """Quadros da camera -> unidades de acesso H.264. O tamanho vem do
    primeiro quadro (cabivel em 640x360) e vale ate o fim."""

    def __init__(self):
        self._ctx = None
        self._pts = 0
        self._tamanho = None
        self._quer_chave = True
        self._trava = threading.Lock()

    def pedir_quadro_chave(self):
        self._quer_chave = True

    def _abrir(self, largura, altura):
        import av
        ctx = av.CodecContext.create("libx264", "w")
        ctx.width, ctx.height = largura, altura
        ctx.pix_fmt = "yuv420p"
        ctx.time_base = Fraction(1, FPS)
        ctx.framerate = Fraction(FPS, 1)
        ctx.bit_rate = BITS_POR_SEGUNDO
        ctx.gop_size = FPS
        ctx.max_b_frames = 0
        ctx.options = {"preset": "ultrafast", "tune": "zerolatency",
                       "profile": "baseline",
                       "x264-params": "aud=1:repeat-headers=1:threads=1"}
        ctx.open()
        self._ctx, self._tamanho = ctx, (largura, altura)

    def codificar(self, quadro):
        """Uma lista de unidades de acesso (em geral uma) para o quadro."""
        import av
        with self._trava:
            if self._ctx is None:
                self._abrir(*tamanho_cabivel(quadro.width, quadro.height))
            l, a = self._tamanho
            saida = quadro.reformat(width=l, height=a, format="yuv420p")
            saida.pts = self._pts
            saida.time_base = Fraction(1, FPS)
            self._pts += 1
            if self._quer_chave:
                saida.pict_type = av.video.frame.PictureType.I
                self._quer_chave = False
            return [sem_delimitadores(bytes(p))
                    for p in self._ctx.encode(saida)]

    def fechar(self):
        with self._trava:
            self._ctx = None


# ----------------------------------------------------------- decodificador
class Decodificador:
    """Unidades de acesso H.264 -> imagens RGB (largura, altura, bytes)."""

    def __init__(self):
        import av
        self._ctx = av.CodecContext.create("h264", "r")
        self.quadros = 0

    def decodificar(self, unidade):
        import av
        achados = []
        try:
            for quadro in self._ctx.decode(av.Packet(unidade)):
                rgb = quadro.to_ndarray(format="rgb24")
                alt, larg = rgb.shape[0], rgb.shape[1]
                achados.append((larg, alt, rgb.tobytes()))
                self.quadros += 1
        except Exception as e:
            log.debug("quadro de vídeo ignorado (%s)", e)
        return achados

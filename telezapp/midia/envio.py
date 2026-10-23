# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Prepara um arquivo para enviar: tipo, tipo MIME, duracao e tamanho.

Sem FFmpeg (os experimentos mostraram que nao e preciso): o video MP4 tem a
duracao e as dimensoes lidas pelo proprio cabecalho, a nota de voz pelo
cabecalho Ogg/Opus. Formatos que os servicos nao tratam como midia (MKV,
AVI, HEIC...) seguem como documento, sem recodificar.
"""
import mimetypes
import os
from dataclasses import dataclass, replace

from telezapp.midia import mp4, opus
from telezapp.nucleo import modelos as m

LIMITE_BYTES = 2000 * 1048576      # 2 GB: o teto dos dois servicos
EXT_FOTO_ENVIAVEL = {".jpg", ".jpeg", ".png", ".webp"}
MIME_VOZ = "audio/ogg; codecs=opus"
# o WhatsApp so toca como audio AAC, AMR, MP3, MP4 e Ogg/Opus: um WAV ou FLAC
# enviado como audio aparece como enviado e nao chega ao destino
EXT_AUDIO_QUE_O_WHATSAPP_NAO_TOCA = {".wav", ".flac"}
MIMES_DE_AUDIO = {".m4a": "audio/mp4", ".aac": "audio/aac",
                  ".mp3": "audio/mpeg", ".ogg": "audio/ogg",
                  ".opus": "audio/ogg"}


class ErroEnvio(Exception):
    """O arquivo nao pode ser enviado; o texto e dito a pessoa."""


@dataclass
class Anexo:
    caminho: str
    tipo: str                  # m.FOTO, VIDEO, VOZ, AUDIO ou DOCUMENTO
    nome: str
    mime: str
    tamanho: int
    segundos: int = 0
    largura: int = 0
    altura: int = 0
    aviso: str = ""            # algo que a pessoa deve saber antes
    temporario: bool = False   # gravado pelo app: pode ser movido, nao copiado
    colado: bool = False       # veio do Control V (audio WAV/FLAC e
    #                            convertido na hora de enviar)
    sem_conversao: bool = False   # colado: parece midia, mas nao deu para
    #                               converter; vai como documento

    @property
    def voz(self):
        return self.tipo == m.VOZ


def _mime(caminho, padrao="application/octet-stream"):
    ext = os.path.splitext(caminho)[1].lower()
    return MIMES_DE_AUDIO.get(ext) or mimetypes.guess_type(caminho)[0] \
        or padrao


def audio_que_o_whatsapp_nao_toca(anexo):
    return anexo.tipo == m.AUDIO and os.path.splitext(
        anexo.nome)[1].lower() in EXT_AUDIO_QUE_O_WHATSAPP_NAO_TOCA


def como_documento(anexo):
    """O mesmo arquivo, enviado como documento."""
    return replace(anexo, tipo=m.DOCUMENTO, segundos=0)


def converter_para_opus(anexo, pasta):
    """Anexo de audio comum (nao nota de voz) em Ogg/Opus, feito a partir de
    um WAV ou FLAC. Levanta ErroEnvio se nao der para ler o arquivo."""
    from telezapp.midia import gravador
    os.makedirs(pasta, exist_ok=True)
    nome = os.path.splitext(anexo.nome)[0] + ".ogg"
    destino = os.path.join(pasta, "conv-%d-%s" % (
        int(os.times()[4] * 1000), nome))
    try:
        gravador.converter(anexo.caminho, destino)
        segundos = int(round(opus.duracao_arquivo(destino)))
    except Exception as erro:
        try:
            os.remove(destino)
        except OSError:
            pass
        raise ErroEnvio("Não consegui converter %s para enviar como áudio "
                        "(%s)." % (anexo.nome, type(erro).__name__))
    return Anexo(destino, m.AUDIO, nome, MIME_VOZ, os.path.getsize(destino),
                 segundos, temporario=True)


def _duracao_audio(caminho):
    try:
        import soundfile as sf
        info = sf.info(caminho)
        return int(round(info.frames / float(info.samplerate)))
    except Exception:
        pass
    if os.path.splitext(caminho)[1].lower() in (".m4a", ".mp4"):
        try:                         # M4A tem a mesma estrutura do MP4
            return int(round(mp4.ler(caminho).segundos))
        except (mp4.NaoEMp4, OSError, ValueError):
            pass
    return 0


EXT_OGG = {".ogg", ".opus", ".oga"}


def _segundos_opus(caminho):
    """Duracao de um Ogg/Opus, ou None se o arquivo nao e Ogg/Opus (por
    exemplo Ogg Vorbis, que o WhatsApp nao toca)."""
    try:
        with open(caminho, "rb") as f:
            if b"OpusHead" not in f.read(512):
                return None
        return int(round(opus.duracao_arquivo(caminho)))
    except (ValueError, OSError):
        return None


def parece_midia(caminho):
    """True se a extensao e de foto, video ou audio (mesmo os formatos que
    os servicos nao tratam como midia)."""
    return os.path.splitext(caminho)[1].lower() in (
        m.EXT_FOTO | m.EXT_VIDEO | m.EXT_AUDIO)


def preparar(caminho, voz=False, temporario=False, como_documento=False,
             colado=False):
    """Anexo pronto para um provedor enviar; ErroEnvio se nao der.

    `como_documento`: o arquivo escolhido pelo botao de anexar vai sempre como
    documento, do jeito que esta. `colado`: veio do Control V; foto, video e
    audio seguem como midia quando o formato serve ou foi convertido, e os
    que nao deram vao como documento, marcados em `sem_conversao`."""
    anexo = _preparar(caminho, voz, temporario, como_documento)
    if colado:
        anexo.colado = True
        anexo.sem_conversao = anexo.tipo == m.DOCUMENTO and \
            parece_midia(caminho)
    return anexo


def _preparar(caminho, voz, temporario, como_documento):
    if not caminho or not os.path.isfile(caminho):
        raise ErroEnvio("O arquivo não foi encontrado.")
    tamanho = os.path.getsize(caminho)
    if tamanho == 0:
        raise ErroEnvio("O arquivo está vazio.")
    if tamanho > LIMITE_BYTES:
        raise ErroEnvio("O arquivo tem %s; o limite para enviar é 2 GB." %
                        m.tamanho_legivel(tamanho))
    nome = os.path.basename(caminho)
    ext = os.path.splitext(nome)[1].lower()

    if como_documento and not voz:
        return Anexo(caminho, m.DOCUMENTO, nome, _mime(caminho), tamanho,
                     temporario=temporario)

    if voz:
        try:
            segundos = int(round(opus.duracao_arquivo(caminho)))
        except (ValueError, OSError):
            raise ErroEnvio("A gravação não está em Ogg/Opus.")
        return Anexo(caminho, m.VOZ, nome, MIME_VOZ, tamanho, segundos,
                     temporario=temporario)

    tipo = m.classificar_arquivo(caminho)
    if tipo == m.FOTO:
        if ext not in EXT_FOTO_ENVIAVEL:
            tipo = m.DOCUMENTO     # BMP, HEIC, GIF: vao como documento
        else:
            return Anexo(caminho, m.FOTO, nome, _mime(caminho), tamanho,
                         temporario=temporario)
    elif tipo == m.VIDEO:
        try:
            info = mp4.ler(caminho)
        except (mp4.NaoEMp4, OSError, ValueError):
            tipo = m.DOCUMENTO     # MKV, AVI...: documento
        else:
            aviso = ("Este vídeo usa o formato HEVC (H.265) e pode não "
                     "tocar em todos os celulares.") if info.hevc else ""
            return Anexo(caminho, m.VIDEO, nome, "video/mp4", tamanho,
                         int(round(info.segundos)), info.largura,
                         info.altura, aviso, temporario)
    elif tipo == m.AUDIO and ext in EXT_OGG:
        # o WhatsApp so aceita como audio o Ogg com Opus, e com o tipo
        # "audio/ogg; codecs=opus": com "audio/ogg" so, ou com Vorbis, o envio
        # aparece como feito e nunca chega. Vorbis vai como documento.
        segundos = _segundos_opus(caminho)
        if segundos is not None:
            return Anexo(caminho, m.AUDIO, nome, MIME_VOZ, tamanho, segundos,
                         temporario=temporario)
    elif tipo == m.AUDIO:
        return Anexo(caminho, m.AUDIO, nome, _mime(caminho, "audio/mpeg"),
                     tamanho, _duracao_audio(caminho),
                     temporario=temporario)
    return Anexo(caminho, m.DOCUMENTO, nome, _mime(caminho), tamanho,
                 temporario=temporario)

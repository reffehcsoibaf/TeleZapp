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
    colado: bool = False       # veio do Control V (a legenda e a conversao
    #                            de audio dependem de como foi escolhido)

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
    return Anexo(destino, m.AUDIO, nome, "audio/ogg", os.path.getsize(destino),
                 segundos, temporario=True)


def _duracao_audio(caminho):
    try:
        import soundfile as sf
        info = sf.info(caminho)
        return int(round(info.frames / float(info.samplerate)))
    except Exception:
        return 0


def preparar(caminho, voz=False, temporario=False):
    """Anexo pronto para um provedor enviar; ErroEnvio se nao der."""
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
    elif tipo == m.AUDIO:
        return Anexo(caminho, m.AUDIO, nome, _mime(caminho, "audio/mpeg"),
                     tamanho, _duracao_audio(caminho),
                     temporario=temporario)
    return Anexo(caminho, m.DOCUMENTO, nome, _mime(caminho), tamanho,
                 temporario=temporario)

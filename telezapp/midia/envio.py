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
from dataclasses import dataclass

from telezapp.midia import mp4, opus
from telezapp.nucleo import modelos as m

LIMITE_BYTES = 2000 * 1048576      # 2 GB: o teto dos dois servicos
EXT_FOTO_ENVIAVEL = {".jpg", ".jpeg", ".png", ".webp"}
MIME_VOZ = "audio/ogg; codecs=opus"


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

    @property
    def voz(self):
        return self.tipo == m.VOZ


def _mime(caminho, padrao="application/octet-stream"):
    return mimetypes.guess_type(caminho)[0] or padrao


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

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Duracao, largura, altura e codec de videos da familia MP4.

Substitui o hachoir (GPL-2.0). Le so as caixas (boxes) necessarias, sem
carregar o arquivo inteiro: serve para MP4, MOV (iPhone), M4V e 3GP, que
usam a mesma estrutura (ISO base media file format).

Outros formatos (MKV, AVI, WMV, WEBM) levantam NaoEMp4: o app os envia como
documento.
"""
import struct
from dataclasses import dataclass

CONTEINERES = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"mvex", b"edts"}
CODECS_HEVC = {"hvc1", "hev1", "dvh1", "dvhe"}
MAX_CAIXAS = 100000


class NaoEMp4(ValueError):
    """O arquivo nao e da familia MP4."""


@dataclass
class InfoVideo:
    segundos: float
    largura: int
    altura: int
    codec: str = ""

    @property
    def hevc(self):
        """HEVC (H.265): pode nao tocar em todos os celulares."""
        return self.codec in CODECS_HEVC


def _caixas(f, inicio, fim):
    """Gera (tipo, inicio_do_conteudo, fim) das caixas entre inicio e fim."""
    pos = inicio
    n = 0
    while pos + 8 <= fim:
        n += 1
        if n > MAX_CAIXAS:
            raise NaoEMp4("estrutura invalida (caixas demais)")
        f.seek(pos)
        cab = f.read(8)
        if len(cab) < 8:
            return
        tamanho, tipo = struct.unpack(">I4s", cab)
        conteudo = pos + 8
        if tamanho == 1:
            grande = f.read(8)
            if len(grande) < 8:
                return
            tamanho = struct.unpack(">Q", grande)[0]
            conteudo = pos + 16
        elif tamanho == 0:
            tamanho = fim - pos
        if tamanho < conteudo - pos or pos + tamanho > fim:
            # caixa truncada: usa ate onde o arquivo vai
            tamanho = fim - pos
            if tamanho < conteudo - pos:
                return
        yield tipo, conteudo, pos + tamanho
        pos += tamanho


def _ler(f, pos, n):
    f.seek(pos)
    dados = f.read(n)
    if len(dados) < n:
        raise NaoEMp4("caixa truncada")
    return dados


def _mvhd(f, pos):
    versao = _ler(f, pos, 1)[0]
    if versao == 1:
        escala, duracao = struct.unpack(">IQ", _ler(f, pos + 20, 12))
    else:
        escala, duracao = struct.unpack(">II", _ler(f, pos + 12, 8))
    return escala, duracao


def _mdhd(f, pos):
    return _mvhd(f, pos)  # mesmo leiaute nos campos que usamos


def _tkhd(f, pos):
    """(id_da_trilha, largura, altura), ja considerando a rotacao."""
    versao = _ler(f, pos, 1)[0]
    id_trilha = struct.unpack(">I", _ler(f, pos + (20 if versao == 1 else 12),
                                         4))[0]
    base = pos + (4 + 32 if versao == 1 else 4 + 20)
    # base aponta para reserved(8); depois layer, alt, volume, reserved (8)
    matriz = struct.unpack(">9i", _ler(f, base + 16, 36))
    larg, alt = struct.unpack(">II", _ler(f, base + 52, 8))
    larg, alt = larg >> 16, alt >> 16
    a, b, c, d = matriz[0], matriz[1], matriz[3], matriz[4]
    if a == 0 and d == 0 and abs(b) == 0x10000 and abs(c) == 0x10000:
        larg, alt = alt, larg   # gravado em pe (90 ou 270 graus)
    return id_trilha, larg, alt


def _hdlr(f, pos):
    return _ler(f, pos + 8, 4).decode("latin-1")


def _stsd(f, pos):
    _versao, quantos = struct.unpack(">II", _ler(f, pos, 8))
    if quantos < 1:
        return ""
    return _ler(f, pos + 12, 4).decode("latin-1")


def _mehd(f, pos):
    versao = _ler(f, pos, 1)[0]
    if versao == 1:
        return struct.unpack(">Q", _ler(f, pos + 4, 8))[0]
    return struct.unpack(">I", _ler(f, pos + 4, 4))[0]


def _trilha(f, inicio, fim, info):
    """Le uma trak; devolve dados se for a trilha de video."""
    t = {"tkhd": None, "hdlr": "", "codec": "", "escala": 0, "duracao": 0}

    def andar(ini, fi):
        for tipo, c, fim_caixa in _caixas(f, ini, fi):
            if tipo == b"tkhd":
                t["tkhd"] = _tkhd(f, c)
            elif tipo == b"hdlr" and not t["hdlr"]:
                # no MOV ha um 2o hdlr (dentro de minf, tipo 'alis'): vale
                # o primeiro, o da caixa mdia
                t["hdlr"] = _hdlr(f, c)
            elif tipo == b"mdhd":
                t["escala"], t["duracao"] = _mdhd(f, c)
            elif tipo == b"stsd":
                t["codec"] = _stsd(f, c)
            elif tipo in CONTEINERES:
                andar(c, fim_caixa)

    andar(inicio, fim)
    if t["hdlr"] == "vide" and "video" not in info:
        info["video"] = t


def ler(caminho):
    """InfoVideo do arquivo; NaoEMp4 se nao for da familia MP4."""
    with open(caminho, "rb") as f:
        f.seek(0, 2)
        fim = f.tell()
        f.seek(0)
        inicio = f.read(12)
        if len(inicio) < 12 or inicio[4:8] not in (
                b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip"):
            raise NaoEMp4("nao e um arquivo da familia MP4")
        info = {}
        for tipo, c, fim_caixa in _caixas(f, 0, fim):
            if tipo == b"moov":
                _moov(f, c, fim_caixa, info)
                break
        if "mvhd" not in info:
            raise NaoEMp4("arquivo sem cabecalho de filme (moov)")

    escala, duracao = info["mvhd"]
    segundos = duracao / escala if escala else 0.0
    if not segundos and info.get("mehd") and escala:
        segundos = info["mehd"] / escala
    video = info.get("video")
    if not segundos and video and video["escala"]:
        segundos = video["duracao"] / video["escala"]
    if video is None or video["tkhd"] is None:
        raise NaoEMp4("arquivo sem trilha de video")
    id_trilha, larg, alt = video["tkhd"]
    if not segundos and video["escala"]:
        # MP4 fragmentado: soma a duracao das amostras de cada fragmento
        with open(caminho, "rb") as f:
            total = _duracao_fragmentos(f, fim, id_trilha,
                                        info.get("trex", {}).get(id_trilha, 0))
        segundos = total / video["escala"]
    return InfoVideo(segundos, larg, alt, video["codec"])


def _moov(f, inicio, fim, info):
    for tipo, c, fim_caixa in _caixas(f, inicio, fim):
        if tipo == b"mvhd":
            info["mvhd"] = _mvhd(f, c)
        elif tipo == b"trak":
            _trilha(f, c, fim_caixa, info)
        elif tipo == b"mvex":
            for t2, c2, _f2 in _caixas(f, c, fim_caixa):
                if t2 == b"mehd":
                    info["mehd"] = _mehd(f, c2)
                elif t2 == b"trex":
                    tid, _idx, dur = struct.unpack(">III", _ler(f, c2 + 4, 12))
                    info.setdefault("trex", {})[tid] = dur


def _duracao_fragmentos(f, fim, id_trilha, padrao_trex):
    """Soma das duracoes das amostras da trilha em todas as caixas moof."""
    total = 0
    for tipo, c, fim_moof in _caixas(f, 0, fim):
        if tipo != b"moof":
            continue
        for t2, c2, fim_traf in _caixas(f, c, fim_moof):
            if t2 != b"traf":
                continue
            padrao = padrao_trex
            dessa_trilha = False
            for t3, c3, _f3 in _caixas(f, c2, fim_traf):
                if t3 == b"tfhd":
                    flags, tid = struct.unpack(">II", _ler(f, c3, 8))
                    flags &= 0xFFFFFF
                    dessa_trilha = tid == id_trilha
                    pos = c3 + 8
                    if flags & 0x01:
                        pos += 8
                    if flags & 0x02:
                        pos += 4
                    if flags & 0x08:
                        padrao = struct.unpack(">I", _ler(f, pos, 4))[0]
                elif t3 == b"trun" and dessa_trilha:
                    total += _soma_trun(f, c3, padrao)
    return total


def _soma_trun(f, pos, padrao):
    flags, quantas = struct.unpack(">II", _ler(f, pos, 8))
    flags &= 0xFFFFFF
    pos += 8
    if flags & 0x01:
        pos += 4
    if flags & 0x04:
        pos += 4
    if not flags & 0x100:
        return padrao * quantas
    passo = 4 * bin(flags & 0xF00).count("1")
    dados = _ler(f, pos, passo * quantas)
    return sum(struct.unpack_from(">I", dados, i * passo)[0]
               for i in range(quantas))

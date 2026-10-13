# SPDX-License-Identifier: GPL-3.0-or-later
"""Leitura de MP4/MOV e Ogg/Opus com amostras reais geradas pelo FFmpeg."""
import os

import pytest

from telezapp.midia import mp4, opus

AMOSTRAS = os.path.join(os.path.dirname(__file__), "amostras")


def caminho(nome):
    return os.path.join(AMOSTRAS, nome)


def test_mp4_h264_com_audio():
    info = mp4.ler(caminho("h264.mp4"))
    assert info.largura == 320 and info.altura == 240
    assert abs(info.segundos - 3.0) < 0.1
    assert info.codec == "avc1" and not info.hevc


def test_mp4_com_moov_no_inicio():
    info = mp4.ler(caminho("rapido.mp4"))
    assert abs(info.segundos - 2.5) < 0.1
    assert (info.largura, info.altura) == (320, 240)


def test_mov_hevc_gravado_em_pe():
    info = mp4.ler(caminho("hevc_empe.mov"))
    assert info.hevc
    # 320x176 com rotacao de 90 graus: na tela fica em pe
    assert (info.largura, info.altura) == (176, 320)
    assert abs(info.segundos - 2.0) < 0.1


def test_mp4_fragmentado():
    info = mp4.ler(caminho("frag.mp4"))
    assert (info.largura, info.altura) == (320, 240)
    assert abs(info.segundos - 4.0) < 0.1


def test_mkv_nao_e_mp4():
    with pytest.raises(mp4.NaoEMp4):
        mp4.ler(caminho("fmt.mkv"))


def test_arquivo_qualquer_nao_e_mp4(tmp_path):
    p = tmp_path / "texto.mp4"
    p.write_bytes(b"isto nao e um video" * 10)
    with pytest.raises(mp4.NaoEMp4):
        mp4.ler(str(p))


def test_mp4_truncado(tmp_path):
    dados = open(caminho("h264.mp4"), "rb").read()
    p = tmp_path / "cortado.mp4"
    p.write_bytes(dados[:2000])
    with pytest.raises(mp4.NaoEMp4):
        mp4.ler(str(p))


def test_duracao_opus():
    assert abs(opus.duracao_arquivo(caminho("voz.ogg")) - 5.0) < 0.05


def test_opus_invalido():
    with pytest.raises(ValueError):
        opus.duracao(b"nada")

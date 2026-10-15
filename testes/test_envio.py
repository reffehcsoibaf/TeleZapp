# SPDX-License-Identifier: GPL-3.0-or-later
"""Preparo de arquivos para enviar (tipo, duracao, limites)."""
import os
import shutil

import pytest

from telezapp.midia import envio
from telezapp.nucleo import modelos as m

AMOSTRAS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "amostras")


def amostra(nome, tmp_path, como=None):
    destino = tmp_path / (como or nome)
    shutil.copy(os.path.join(AMOSTRAS, nome), destino)
    return str(destino)


def test_video_mp4_traz_duracao_e_dimensoes(tmp_path):
    a = envio.preparar(amostra("h264.mp4", tmp_path))
    assert a.tipo == m.VIDEO and a.mime == "video/mp4"
    assert a.largura > 0 and a.altura > 0 and a.segundos >= 0
    assert a.tamanho == os.path.getsize(a.caminho) and not a.aviso


def test_video_hevc_avisa_mas_continua_video(tmp_path):
    a = envio.preparar(amostra("hevc_empe.mov", tmp_path))
    assert a.tipo == m.VIDEO and "HEVC" in a.aviso


def test_video_que_nao_e_mp4_vai_como_documento(tmp_path):
    a = envio.preparar(amostra("fmt.mkv", tmp_path))
    assert a.tipo == m.DOCUMENTO and a.nome == "fmt.mkv"


def test_nota_de_voz_le_a_duracao_do_cabecalho(tmp_path):
    a = envio.preparar(amostra("voz.ogg", tmp_path), voz=True,
                       temporario=True)
    assert a.tipo == m.VOZ and a.voz and a.temporario
    assert a.mime == envio.MIME_VOZ and a.segundos >= 0


def test_voz_que_nao_e_ogg_e_recusada(tmp_path):
    f = tmp_path / "x.ogg"
    f.write_bytes(b"isto nao e ogg")
    with pytest.raises(envio.ErroEnvio):
        envio.preparar(str(f), voz=True)


def test_foto_enviavel_e_formato_estranho_como_documento(tmp_path):
    jpg = tmp_path / "a.JPG"
    jpg.write_bytes(b"\xff\xd8\xff")
    bmp = tmp_path / "b.bmp"
    bmp.write_bytes(b"BM")
    assert envio.preparar(str(jpg)).tipo == m.FOTO
    assert envio.preparar(str(jpg)).mime == "image/jpeg"
    assert envio.preparar(str(bmp)).tipo == m.DOCUMENTO


def test_audio_e_documento(tmp_path):
    mp3 = tmp_path / "som.mp3"
    mp3.write_bytes(b"ID3")
    pdf = tmp_path / "relatorio.pdf"
    pdf.write_bytes(b"%PDF")
    a = envio.preparar(str(mp3))
    assert a.tipo == m.AUDIO and a.mime == "audio/mpeg"
    d = envio.preparar(str(pdf))
    assert (d.tipo, d.mime, d.nome) == (m.DOCUMENTO, "application/pdf",
                                        "relatorio.pdf")


def test_arquivo_ausente_vazio_ou_grande_demais(tmp_path, monkeypatch):
    with pytest.raises(envio.ErroEnvio, match="não foi encontrado"):
        envio.preparar(str(tmp_path / "nao-existe.pdf"))
    vazio = tmp_path / "v.txt"
    vazio.write_bytes(b"")
    with pytest.raises(envio.ErroEnvio, match="vazio"):
        envio.preparar(str(vazio))
    grande = tmp_path / "g.bin"
    grande.write_bytes(b"x" * 100)
    monkeypatch.setattr(envio, "LIMITE_BYTES", 50)
    with pytest.raises(envio.ErroEnvio, match="limite"):
        envio.preparar(str(grande))

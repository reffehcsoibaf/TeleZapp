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


def test_pelo_botao_tudo_vai_como_documento(tmp_path):
    jpg = tmp_path / "a.jpg"
    jpg.write_bytes(b"\xff\xd8\xff")
    mp3 = tmp_path / "som.mp3"
    mp3.write_bytes(b"ID3")
    mp4 = amostra("video.mp4", tmp_path) if os.path.exists(
        os.path.join(AMOSTRAS, "video.mp4")) else None
    for caminho in [str(jpg), str(mp3)] + ([mp4] if mp4 else []):
        d = envio.preparar(caminho, como_documento=True)
        assert d.tipo == m.DOCUMENTO and d.nome == os.path.basename(caminho)
        assert not d.colado and not d.sem_conversao


def test_colado_marca_o_que_parece_midia_e_nao_deu_para_converter(tmp_path):
    ok = tmp_path / "a.jpg"
    ok.write_bytes(b"\xff\xd8\xff")
    heic = tmp_path / "foto.heic"
    heic.write_bytes(b"x" * 10)
    mkv = tmp_path / "filme.mkv"
    mkv.write_bytes(b"x" * 10)
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF")
    a = envio.preparar(str(ok), colado=True)
    assert a.tipo == m.FOTO and a.colado and not a.sem_conversao
    for ruim in (heic, mkv):
        d = envio.preparar(str(ruim), colado=True)
        assert d.tipo == m.DOCUMENTO and d.sem_conversao
    # um documento de verdade nao e "midia sem conversao": nao avisa
    d = envio.preparar(str(pdf), colado=True)
    assert d.tipo == m.DOCUMENTO and not d.sem_conversao


def test_wav_colado_continua_audio_para_converter_no_envio(tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF" + b"\0" * 40)
    a = envio.preparar(str(wav), colado=True)
    assert a.tipo == m.AUDIO and a.colado and not a.sem_conversao

# SPDX-License-Identifier: GPL-3.0-or-later
"""Gravador de nota de voz com uma fonte de audio simulada (sem hardware)."""
import threading
import time

import numpy as np
import pytest
import soundfile as sf

from telezapp.midia import envio, gravador
from telezapp.midia.gravador import ErroGravacao, Gravador


class FonteFalsa:
    """Entrega blocos de 100 ms de uma senoide (ou silencio)."""
    origem = "microfone"
    nome = "Microfone de teste"

    def __init__(self, taxa=48000, amplitude=0.5, atraso=0.1):
        self.taxa = taxa
        self.amplitude = amplitude
        self.atraso = atraso
        self.fechada = False
        self._n = 0

    def ler(self):
        time.sleep(self.atraso)
        n = self.taxa // 10
        t = (np.arange(n) + self._n) / self.taxa
        self._n += n
        return (self.amplitude * np.sin(2 * np.pi * 440 * t)).astype(
            "float32")

    def fechar(self):
        self.fechada = True


def gravar_por(pasta, segundos, **kw):
    fonte = FonteFalsa(**kw)
    g = Gravador(str(pasta), fabrica_fonte=lambda: fonte)
    g.iniciar()
    time.sleep(segundos)
    return g, fonte, g.parar()


def test_grava_e_gera_ogg_opus_de_48k(tmp_path):
    g, fonte, r = gravar_por(tmp_path, 0.6)
    assert fonte.fechada
    assert r.caminho.endswith(".ogg")
    assert 0.4 < r.segundos < 1.2
    assert not r.silenciosa and -8 < r.pico_db < -3
    info = sf.info(r.caminho)
    assert info.format == "OGG" and info.subtype == "OPUS"
    assert info.channels == 1
    # o cabecalho confere com o que o provedor usara como duracao
    a = envio.preparar(r.caminho, voz=True, temporario=True)
    assert abs(a.segundos - round(r.segundos)) <= 1
    # nao sobra o WAV temporario
    assert [p.suffix for p in tmp_path.iterdir()] == [".ogg"]


def test_taxa_diferente_e_reamostrada_para_48k(tmp_path):
    g, _, r = gravar_por(tmp_path, 0.6, taxa=16000)
    info = sf.info(r.caminho)
    assert info.samplerate == 48000
    assert abs(info.duration - r.segundos) < 0.1


def test_silencio_e_detectado(tmp_path):
    _, _, r = gravar_por(tmp_path, 0.3, amplitude=0.0)
    assert r.silenciosa


def test_cancelar_apaga_tudo(tmp_path):
    fonte = FonteFalsa()
    g = Gravador(str(tmp_path), fabrica_fonte=lambda: fonte)
    g.iniciar()
    time.sleep(0.25)
    g.cancelar()
    assert fonte.fechada and list(tmp_path.iterdir()) == []


def test_fonte_que_nao_abre_vira_erro_para_a_pessoa(tmp_path):
    def abrir():
        raise ErroGravacao("Não encontrei nenhum microfone.")
    g = Gravador(str(tmp_path), fabrica_fonte=abrir)
    with pytest.raises(ErroGravacao, match="microfone"):
        g.iniciar()
    assert list(tmp_path.iterdir()) == []


def test_erro_inesperado_da_fonte_nao_vaza_detalhes(tmp_path):
    def abrir():
        raise OSError("driver quebrou")
    g = Gravador(str(tmp_path), fabrica_fonte=abrir)
    with pytest.raises(ErroGravacao) as e:
        g.iniciar()
    assert "OSError" in str(e.value) and "quebrou" not in str(e.value)


def test_limite_de_tempo_para_sozinho(tmp_path):
    fonte = FonteFalsa()
    g = Gravador(str(tmp_path), fabrica_fonte=lambda: fonte,
                 maximo_segundos=0.3)
    g.iniciar()
    for _ in range(100):
        if not g.gravando:
            break
        time.sleep(0.02)
    assert not g.gravando and g.estourou_limite
    r = g.parar()
    assert 0.3 <= r.segundos < 0.7


def test_parar_sem_nada_gravado_e_erro(tmp_path):
    class Travada(FonteFalsa):
        def ler(self):
            time.sleep(0.05)
            return np.empty(0, dtype="float32")
    g = Gravador(str(tmp_path), fabrica_fonte=Travada)
    g.iniciar()
    with pytest.raises(ErroGravacao, match="Nada foi gravado"):
        g.parar()


def test_conversao_nao_perde_duracao_em_blocos(tmp_path):
    taxa = 44100
    n = taxa * 3 + 123
    wav = tmp_path / "a.wav"
    sf.write(str(wav), (0.3 * np.sin(np.arange(n) / 20)).astype("float32"),
             taxa, subtype="PCM_16")
    destino = tmp_path / "a.ogg"
    gravador.converter(str(wav), str(destino))
    assert abs(sf.info(str(destino)).duration - n / taxa) < 0.05


def test_pausa_nao_grava_o_trecho_da_pausa(tmp_path):
    fonte = FonteFalsa()
    g = Gravador(str(tmp_path), fabrica_fonte=lambda: fonte)
    g.iniciar()
    time.sleep(0.4)
    g.pausar()
    assert g.pausado and g.gravando       # a captura segue aberta
    time.sleep(0.1)
    antes = g.decorrido
    time.sleep(0.6)
    assert g.decorrido - antes < 0.15     # nada entrou durante a pausa
    g.continuar()
    time.sleep(0.4)
    r = g.parar()
    assert not g.pausado
    assert 0.6 <= r.segundos < 1.3

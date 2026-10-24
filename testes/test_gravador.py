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


# ------------------------------------------- som do computador + microfone
def test_misturar_soma_e_limita():
    som = np.full(480, 0.4, dtype="float32")
    mic = np.full(480, 0.3, dtype="float32")
    misto = gravador.misturar(som, mic)
    assert misto.shape == (480,) and abs(float(misto[0]) - 0.7) < 1e-6
    estourado = gravador.misturar(np.full(10, 0.9, "float32"),
                                  np.full(10, 0.9, "float32"))
    assert float(estourado.max()) <= 1.0


def test_misturar_reamostra_o_microfone_para_o_bloco_do_som():
    som = np.zeros(4800, dtype="float32")
    mic = np.full(1600, 0.5, dtype="float32")       # outro tamanho de bloco
    misto = gravador.misturar(som, mic, 16000)
    assert len(misto) == 4800 and abs(float(misto[1234]) - 0.5) < 1e-6
    sem_mic = gravador.misturar(som, np.empty(0, dtype="float32"))
    assert len(sem_mic) == 4800 and float(abs(sem_mic).max()) == 0.0


class FonteMistaFalsa:
    """Mistura de mentira: o som interno e o microfone separados."""
    origem = "som_e_microfone"
    nome = "Saida de teste"
    taxa = 48000

    def __init__(self, tem_microfone=True):
        self.microfone_disponivel = tem_microfone
        self.microfone_ligado = True
        self.aviso = "" if tem_microfone else "sem microfone"

    def ler(self):
        time.sleep(0.05)
        n = 4800
        som = np.full(n, 0.2, dtype="float32")
        if self.microfone_ligado and self.microfone_disponivel:
            return gravador.misturar(som, np.full(n, 0.3, "float32"))
        return som

    def fechar(self):
        pass


def test_microfone_liga_e_desliga_durante_a_gravacao(tmp_path):
    fonte = FonteMistaFalsa()
    g = Gravador(str(tmp_path), "som_e_microfone",
                 fabrica_fonte=lambda: fonte, microfone_ligado=False)
    g.iniciar()
    assert fonte.microfone_ligado is False         # comecou desligado
    g.microfone_ligado = True
    assert fonte.microfone_ligado is True
    g.microfone_ligado = False
    assert fonte.microfone_ligado is False
    g.cancelar()


def test_sem_microfone_a_mistura_grava_so_o_som_e_avisa(tmp_path):
    fonte = FonteMistaFalsa(tem_microfone=False)
    g = Gravador(str(tmp_path), "som_e_microfone",
                 fabrica_fonte=lambda: fonte)
    g.iniciar()
    assert g.microfone_disponivel is False and g.aviso == "sem microfone"
    g.microfone_ligado = True                      # nao liga o que nao existe
    assert fonte.microfone_ligado is False
    time.sleep(0.3)
    r = g.parar()
    assert r.segundos > 0.2

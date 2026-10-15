# SPDX-License-Identifier: GPL-3.0-or-later
"""Escala de velocidades e o esticador de tempo (sem mudar o tom)."""
import numpy as np
import pytest

from telezapp.midia import velocidade as v


def test_valores_por_passo():
    a = v.valores(0.25)
    assert a[0] == 0.25 and a[-1] == 3.0 and len(a) == 12
    assert all(round(b - c, 2) == 0.25 for c, b in zip(a, a[1:]))
    assert v.valores(0.5) == [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    assert v.valores(1.0) == [1.0, 2.0, 3.0]
    assert 1.0 in a and 1.0 in v.valores(0.5) and 1.0 in v.valores(1.0)
    assert v.valores("lixo") == a        # passo invalido: o padrao


def test_ajustar_ao_mudar_o_passo():
    assert v.ajustar(1.75, 0.5) == 1.5      # empate: o menor
    assert v.ajustar(2.25, 1.0) == 2.0
    assert v.ajustar(0.25, 1.0) == 1.0      # abaixo do menor disponivel
    assert v.ajustar(9, 0.25) == 3.0
    assert v.ajustar("x", 0.25) == 1.0


def test_proxima_sobe_desce_e_para_nos_extremos():
    assert v.proxima(1.0, 0.25, +1) == 1.25
    assert v.proxima(1.0, 0.5, +1) == 1.5
    assert v.proxima(1.0, 1.0, +1) == 2.0
    assert v.proxima(1.0, 0.25, -1) == 0.75
    assert v.proxima(3.0, 0.25, +1) == 3.0
    assert v.proxima(0.25, 0.25, -1) == 0.25
    assert v.proxima(1.0, 1.0, -1) == 1.0     # 1x e o menor com passo 1
    # velocidade fora da escala do passo novo: parte do valor mais proximo
    assert v.proxima(1.25, 0.5, +1) == 1.5
    assert v.proxima(1.25, 0.5, -1) == 1.0


def test_rotulo_em_portugues():
    assert v.rotulo(1.0) == "1x"
    assert v.rotulo(1.5) == "1,5x"
    assert v.rotulo(0.25) == "0,25x"
    assert v.rotulo(3) == "3x"


# ------------------------------------------------------------- esticador
TAXA = 16000


def leitor(dados):
    pos = [0]

    def ler(n):
        pedaco = dados[pos[0]:pos[0] + n]
        pos[0] += len(pedaco)
        return pedaco
    return ler


def senoide(segundos, freq=440.0, canais=1):
    t = np.arange(int(segundos * TAXA)) / TAXA
    x = (0.5 * np.sin(2 * np.pi * freq * t)).astype("float32")
    return np.repeat(x.reshape(-1, 1), canais, axis=1)


def tocar_tudo(dados, velocidade, bloco=1024):
    e = v.Esticador(TAXA, dados.shape[1], leitor(dados), len(dados))
    saida = []
    while True:
        pedaco = e.produzir(bloco, velocidade)
        saida.append(pedaco)
        if len(pedaco) < bloco:
            break
    return np.concatenate(saida), e


def frequencia(x):
    mono = x.mean(axis=1) if x.ndim == 2 else x
    f = np.abs(np.fft.rfft(mono * np.hanning(len(mono))))
    return np.fft.rfftfreq(len(mono), 1.0 / TAXA)[int(f.argmax())]


@pytest.mark.parametrize("vel", [0.5, 1.0, 1.5, 2.0, 3.0])
def test_duracao_muda_e_o_tom_nao(vel):
    entrada = senoide(3.0)
    saida, e = tocar_tudo(entrada, vel)
    esperado = len(entrada) / vel
    assert abs(len(saida) - esperado) < TAXA * 0.1      # 100 ms
    assert abs(frequencia(saida[TAXA // 4:]) - 440.0) < 8.0
    assert e.terminou
    # sem estouros: a soma das janelas nao passa do nivel original
    assert np.abs(saida).max() < 0.6


def test_quarto_de_velocidade_dobra_duas_vezes():
    entrada = senoide(1.0)
    saida, _ = tocar_tudo(entrada, 0.25)
    assert abs(len(saida) - len(entrada) * 4) < TAXA * 0.15
    assert abs(frequencia(saida[TAXA // 4:]) - 440.0) < 8.0


def test_estereo_e_troca_de_velocidade_no_meio():
    entrada = senoide(2.0, canais=2)
    e = v.Esticador(TAXA, 2, leitor(entrada), len(entrada))
    a = e.produzir(TAXA // 2, 1.0)
    b = e.produzir(TAXA // 2, 2.0)
    assert a.shape == (TAXA // 2, 2) and b.shape == (TAXA // 2, 2)
    # meio segundo a 1x + meio segundo a 2x consumiram ~1,5 s de entrada
    assert abs(e.posicao / TAXA - 1.5) < 0.1
    assert abs(frequencia(b) - 440.0) < 10.0


def test_reiniciar_volta_a_tocar_do_ponto():
    entrada = senoide(2.0)
    ler_pos = {"i": 0}

    def ler(n):
        p = entrada[ler_pos["i"]:ler_pos["i"] + n]
        ler_pos["i"] += len(p)
        return p
    e = v.Esticador(TAXA, 1, ler, len(entrada))
    e.produzir(2000, 2.0)
    ler_pos["i"] = TAXA              # o arquivo foi posicionado em 1 s
    e.reiniciar(TAXA)
    assert abs(e.posicao - TAXA) < 1
    saida = e.produzir(TAXA // 4, 2.0)
    assert len(saida) == TAXA // 4
    assert abs(e.posicao / TAXA - 1.5) < 0.05

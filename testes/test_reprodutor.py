# SPDX-License-Identifier: GPL-3.0-or-later
import numpy as np
import pytest

sf = pytest.importorskip("soundfile")

from telezapp.midia import reprodutor as r  # noqa: E402


class Saida:
    def __init__(self, taxa, canais, callback):
        self.taxa, self.canais, self.callback = taxa, canais, callback
        self.estado = "novo"

    def start(self):
        self.estado = "tocando"

    def stop(self):
        self.estado = "parado"

    def close(self):
        self.estado = "fechado"

    def puxar(self, quadros):
        saida = np.ones((quadros, self.canais), dtype="float32")
        self.callback(saida, quadros, None, None)
        return saida


def criar(tmp_path, nome="a.ogg", segundos=2, **k):
    caminho = str(tmp_path / nome)
    dados = (0.1 * np.sin(np.linspace(0, 600, 48000 * segundos))
             ).astype("float32")
    sf.write(caminho, dados, 48000, **k)
    saidas = []

    def fabrica(taxa, canais, cb):
        saidas.append(Saida(taxa, canais, cb))
        return saidas[-1]
    return r.Reprodutor(caminho, fabrica), saidas


@pytest.mark.parametrize("nome,k", [("a.ogg", {"subtype": "OPUS"}),
                                    ("a.wav", {}), ("a.flac", {})])
def test_toca_pausa_e_anda(tmp_path, nome, k):
    p, saidas = criar(tmp_path, nome, **k)
    assert abs(p.duracao - 2.0) < 0.05 and p.posicao == 0
    p.tocar()
    assert saidas[0].estado == "tocando" and p.tocando
    bloco = saidas[0].puxar(4800)
    assert np.abs(bloco).max() > 0.01 and abs(p.posicao - 0.1) < 0.01
    p.pausar()
    assert saidas[0].puxar(4800).max() == 0           # silencio
    assert abs(p.posicao - 0.1) < 0.01                # nao andou
    p.avancar(0.5)
    assert abs(p.posicao - 0.6) < 0.01
    p.avancar(-5)
    assert p.posicao == 0
    p.ir_para(100)
    assert abs(p.posicao - p.duracao) < 0.01
    p.fechar()
    assert saidas[0].estado == "fechado"


def test_fim_e_recomeco(tmp_path):
    p, saidas = criar(tmp_path, "a.wav", segundos=1)
    p.tocar()
    saidas[0].puxar(48000 // 2)
    saidas[0].puxar(48000)                            # passa do fim
    assert p.terminou and not p.tocando
    p.tocar()                                         # recomeca do zero
    assert not p.terminou and p.posicao == 0 and len(saidas) == 1
    p.fechar()


def test_formato_que_nao_abre(tmp_path):
    f = tmp_path / "x.m4a"
    f.write_bytes(b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 100)
    with pytest.raises(r.FormatoNaoSuportado):
        r.Reprodutor(str(f))


def test_formatar_tempo():
    assert r.formatar_tempo(5) == "0:05" and r.formatar_tempo(65.4) == "1:05"
    assert r.formatar_tempo(3725) == "1:02:05"


def test_velocidade_dobra_o_ritmo_e_a_posicao_acompanha(tmp_path):
    p, saidas = criar(tmp_path, "v.wav", segundos=4)
    p.velocidade = 2.0
    p.tocar()
    total = 0
    for _ in range(10):
        bloco = saidas[0].puxar(4800)
        total += 4800
    # 10 blocos de 0,1 s tocados a 2x consumiram ~2 s do arquivo
    assert abs(p.posicao - 2.0) < 0.15
    assert p.tocando
    # voltar a 1x continua do mesmo ponto
    p.velocidade = 1.0
    assert abs(p.posicao - 2.0) < 0.15
    saidas[0].puxar(4800)
    assert abs(p.posicao - 2.1) < 0.15


def test_velocidade_toca_ate_o_fim_e_avisa(tmp_path):
    p, saidas = criar(tmp_path, "w.wav", segundos=1)
    p.velocidade = 3.0
    p.tocar()
    for _ in range(20):
        saidas[0].puxar(4800)
        if p.terminou:
            break
    assert p.terminou and not p.tocando
    # tocar de novo recomeca do inicio na mesma velocidade
    p.tocar()
    assert p.posicao < 0.1 and p.tocando and p.velocidade == 3.0


def test_ir_para_com_velocidade(tmp_path):
    p, saidas = criar(tmp_path, "x.wav", segundos=4)
    p.velocidade = 1.5
    p.tocar()
    saidas[0].puxar(2400)
    p.ir_para(3.0)
    assert abs(p.posicao - 3.0) < 0.05
    saidas[0].puxar(4800)
    assert abs(p.posicao - 3.15) < 0.15

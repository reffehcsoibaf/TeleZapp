# SPDX-License-Identifier: GPL-3.0-or-later
"""Cancelamento de eco das chamadas: a logica de atraso sem o WebRTC e, se o
pacote estiver instalado, a reducao de eco de verdade num sinal sintetico."""
import numpy as np
import pytest

from telezapp.midia import eco

QUADRO_CHAMADA = 960             # 60 ms a 16 kHz


class ModuloFalso:
    """Guarda o que recebeu e devolve o microfone sem mexer."""

    def __init__(self):
        self.referencias = 0
        self.processados = 0

    def process_reverse_stream(self, quadro):
        self.referencias += 1

    def process_stream(self, quadro):
        self.processados += 1


class QuadroFalso:
    def __init__(self, amostras):
        self.data = bytearray(amostras.tobytes())


def _cancelador(**k):
    modulo = ModuloFalso()
    c = eco.CancelaEco(fabrica=lambda e, r: modulo, **k)
    return c, modulo


def _voz(segundos, semente=1):
    rng = np.random.default_rng(semente)
    n = int(eco.TAXA * segundos)
    t = np.arange(n) / eco.TAXA
    s = np.convolve(rng.standard_normal(n), np.ones(8) / 8, mode="same")
    return (s * (0.5 + 0.5 * np.sin(2 * np.pi * 3 * t) ** 2) * 6000).astype(
        np.int16)


def test_acoplamento_acha_o_atraso_do_eco():
    voz = _voz(2.5).astype(np.float64)
    ref = voz[::2]
    atraso = 400 * eco.TAXA_MEDIDA // 1000
    sinal = np.zeros(ref.size)
    sinal[atraso:] = ref[:-atraso] * 0.5
    janela = int(eco.JANELA_S * eco.TAXA_MEDIDA)
    coef, ms = eco.acoplamento(ref, sinal[-janela:])
    assert coef > 0.9 and abs(ms - 400) <= 2
    # silencio de um lado: nada a medir
    assert eco.acoplamento(ref, np.zeros(janela)) == (0.0, None)
    # sinal sem relacao nenhuma: correlacao baixa
    outro = _voz(2.5, semente=9).astype(np.float64)[::2][-janela:]
    assert eco.acoplamento(ref, outro)[0] < 0.4


def test_quadros_de_10_ms_e_a_saida_tem_o_tamanho_da_entrada(monkeypatch):
    monkeypatch.setattr(eco, "_quadro", QuadroFalso)
    c, modulo = _cancelador(eco=True, ruido=True)
    mic = bytes(QUADRO_CHAMADA * 2)
    c.referencia(mic)
    assert len(c.processar(mic)) == len(mic)
    assert modulo.referencias == 6 and modulo.processados == 6
    # um pedaco que nao fecha 10 ms espera o proximo
    assert c.processar(bytes(100)) == b""
    assert len(c.processar(bytes(220))) == 320


def test_sem_o_pacote_o_microfone_passa_sem_tratamento():
    def quebra(e, r):
        raise ImportError("sem livekit")
    c = eco.CancelaEco(fabrica=quebra)
    assert not c.disponivel
    pcm = bytes(range(64))
    assert c.processar(pcm) == pcm
    c.referencia(pcm)                        # nao faz nada, nao falha
    assert c.diagnostico()["motor"] == "indisponível"
    c.reiniciar()                            # nao tenta de novo, nem loga


def test_definir_guarda_o_que_a_janela_pediu():
    eco.definir(False, True)
    assert eco.LIGADOS == {"eco": False, "ruido": True, "retorno": True}
    eco.definir(True, True, False)
    assert eco.LIGADOS["retorno"] is False
    eco.definir(True, True, True)


def test_reducao_de_eco_de_verdade_com_atraso_curto_e_com_retorno_longo():
    pytest.importorskip("livekit.rtc")
    voz = _voz(12)
    n = voz.size
    for atraso_ms, seguro_min in ((60, 0), (800, 400)):
        c = eco.CancelaEco(eco=True, ruido=False)
        assert c.disponivel
        d = atraso_ms * eco.TAXA // 1000
        mic = np.zeros(n, dtype=np.int16)
        mic[d:] = (voz[:n - d] * 0.6).astype(np.int16)
        saida = []
        for i in range(0, n, QUADRO_CHAMADA):
            c.referencia(voz[i:i + QUADRO_CHAMADA].tobytes())
            saida.append(np.frombuffer(
                c.processar(mic[i:i + QUADRO_CHAMADA].tobytes()),
                dtype="<i2"))
        s = np.concatenate(saida)
        fim = slice(-3 * eco.TAXA, None)

        def rms(x):
            return float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
        reducao = 20 * np.log10(rms(mic[fim]) / max(rms(s[fim]), 1.0))
        assert reducao > 20, (atraso_ms, reducao)
        assert c.diagnostico()["referencia_segurada_ms"] >= seguro_min


def test_diagnostico_mede_o_eco_que_volta_do_outro_lado():
    """Nossa voz enviada volta, 400 ms depois, dentro do que recebemos: o
    log precisa mostrar isso (e o eco local, sem relacao, fica baixo)."""
    c, _ = _cancelador()
    enviado = _voz(5.0)
    recebido = np.zeros_like(enviado)
    atraso = int(0.4 * eco.TAXA)
    recebido[atraso:] = (enviado[:-atraso] * 0.5).astype(np.int16)
    passo = 160                                     # 10 ms
    for i in range(0, enviado.size - passo, passo):
        c.referencia(recebido[i:i + passo].tobytes())
        c.processar(enviado[i:i + passo].tobytes())
    d = c.diagnostico()
    assert d["eco_do_outro_lado"] > 0.8
    assert abs(d["eco_do_outro_lado_atraso_ms"] - 400) <= 30


def test_retorno_so_troca_o_som_quando_a_voz_nossa_volta():
    pytest.importorskip("livekit.rtc")
    nossa, dele = _voz(14, semente=3), _voz(14, semente=8)
    n = nossa.size
    atraso = 500 * eco.TAXA // 1000
    chega = dele.astype(np.int32).copy()
    chega[atraso:] += (nossa[:n - atraso] * 0.7).astype(np.int32)
    chega = np.clip(chega, -32768, 32767).astype(np.int16)
    r = eco.CancelaRetorno()
    assert r.disponivel
    saida = []
    for i in range(0, n, QUADRO_CHAMADA):
        r.enviado(nossa[i:i + QUADRO_CHAMADA].tobytes())
        saida.append(np.frombuffer(
            r.recebido(chega[i:i + QUADRO_CHAMADA].tobytes()), dtype="<i2"))
    s = np.concatenate(saida)
    assert r.ativo
    fim = slice(-3 * eco.TAXA, None)
    nossa_atrasada = np.zeros(n)
    nossa_atrasada[atraso:] = nossa[:n - atraso]

    def parecido_com(x, y):
        x, y = x[fim].astype(np.float64), y[fim].astype(np.float64)
        return abs(float(np.dot(x, y))) / (np.linalg.norm(x) *
                                           np.linalg.norm(y) + 1e-9)
    # o que chega tem a nossa voz atrasada; depois de tirar, bem menos
    antes = parecido_com(chega, nossa_atrasada)
    depois = parecido_com(s, nossa_atrasada)
    assert depois < antes * 0.5, (antes, depois)


def test_sem_retorno_o_que_chega_passa_como_veio():
    r = eco.CancelaRetorno(fabrica=lambda e, rr: ModuloFalso())
    enviado, chega = _voz(3, semente=1), _voz(3, semente=2)
    passo = 960
    for i in range(0, enviado.size - passo, passo):
        r.enviado(enviado[i:i + passo].tobytes())
        quadro = chega[i:i + passo].tobytes()
        assert r.recebido(quadro) == quadro
    assert not r.ativo

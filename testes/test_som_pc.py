# SPDX-License-Identifier: GPL-3.0-or-later
"""O som do computador numa chamada e a tela como fonte de video."""
import time

import numpy as np

from telezapp.midia import som_pc as sp
from telezapp.midia import video


def quadro_de(valor):
    return np.full(sp.AMOSTRAS, valor, dtype="<i2").tobytes()


def test_misturar_soma_sem_estourar():
    mic, pc = quadro_de(1000), quadro_de(-300)
    assert np.frombuffer(sp.misturar(mic, pc), "<i2")[0] == 700
    alto = np.frombuffer(sp.misturar(quadro_de(30000), quadro_de(30000)),
                         "<i2")
    assert alto[0] == 32767                  # limitado, sem dar a volta
    assert sp.misturar(mic, b"") == mic      # nada do computador
    assert sp.misturar(mic, b"curto") == mic  # tamanho diferente
    assert sp.misturar(b"", pc) == pc


def test_captura_entrega_os_quadros_na_ordem_e_silencio_quando_falta():
    entregues = [quadro_de(1), quadro_de(2), quadro_de(3)]

    class Fonte:
        nome = "Alto-falantes"

        def __init__(self):
            self.n = 0

        def ler(self):
            if self.n < len(entregues):
                self.n += 1
                return entregues[self.n - 1]
            time.sleep(0.01)
            return b""                         # nada tocando: sem quadro

        def fechar(self):
            self.fechada = True
    fonte = Fonte()
    c = sp.CapturaDoSom("", abrir=lambda nome: fonte)
    assert c.ler() == sp.SILENCIO                # antes de iniciar
    c.iniciar()
    for _ in range(500):
        if c.quadros == 3:
            break
        time.sleep(0.01)
    assert [c.ler() for _ in range(3)] == entregues
    assert c.ler() == sp.SILENCIO                # acabou: silencio
    assert c.nome == "Alto-falantes"
    c.parar()
    c._thread.join(5)             # (join, e nao espera com sleep: outros
    assert not c.viva             # testes podem deixar o sleep trocado)
    assert getattr(fonte, "fechada", False)


def test_captura_que_nao_abre_guarda_o_erro_e_segue_em_silencio():
    def nao_abre(nome):
        raise OSError("sem saida")
    c = sp.CapturaDoSom("X", abrir=nao_abre)
    c.iniciar()
    for _ in range(500):
        if c.erro:
            break
        time.sleep(0.01)
    assert "sem saida" in c.erro
    assert c.ler() == sp.SILENCIO


def test_tela_e_uma_camera_com_retangulo(monkeypatch):
    abertos = []

    class Recipiente:
        def decode(self, video=0):
            return iter(())

        def close(self):
            pass

    class FalsoAv:
        @staticmethod
        def open(*a, **k):
            abertos.append((a, k))
            return Recipiente()
    import sys
    monkeypatch.setitem(sys.modules, "av", FalsoAv)
    t = video.Tela((100, 50, 1280, 720), lambda q: None)
    t._abrir()
    (arg,), opcoes = abertos[0]
    assert arg == "desktop" and opcoes["format"] == "gdigrab"
    assert opcoes["options"]["video_size"] == "1280x720"
    assert opcoes["options"]["offset_x"] == "100"
    assert video.tamanho_cabivel(1280, 720) == (640, 360)


def test_captura_por_processo_diz_que_e_exata_e_a_comum_nao():
    class Exata:
        nome = "Todo o som"
        exato = True

        def ler(self):
            time.sleep(0.01)
            return b""

        def fechar(self):
            pass

    class Comum(Exata):
        exato = False
    for classe, esperado in ((Exata, True), (Comum, False)):
        c = sp.CapturaDoSom("", abrir=lambda nome, k=classe: k())
        c.iniciar()                       # espera abrir
        assert c.exato is esperado and c.nome == "Todo o som"
        c.parar()
        c._thread.join(5)


def test_captura_que_nao_abre_termina_o_iniciar_sem_esperar_o_limite():
    def nao_abre(nome):
        raise OSError("sem saida")
    c = sp.CapturaDoSom("", abrir=nao_abre)
    inicio = time.monotonic()
    c.iniciar(espera_s=5.0)
    assert time.monotonic() - inicio < 2.0
    assert "sem saida" in c.erro


def test_ajudantes_da_captura_por_processo():
    from telezapp.midia import som_por_processo as pp
    a = pp._guid("41D949AB-9862-444A-80F6-C261334DA5EB")
    assert a.Data1 == 0x41D949AB and a.Data2 == 0x9862 and a.Data3 == 0x444A
    assert bytes(a.Data4) == bytes.fromhex("80F6C261334DA5EB")
    assert pp._mesmo_guid(a, pp.IID_HANDLER)
    assert not pp._mesmo_guid(a, pp.IID_AGILE)
    mono = np.sin(np.arange(44100) * 2 * np.pi * 440 / 44100).astype("float32")
    saida = pp._para_16k(mono, 44100)
    assert abs(len(saida) - 16000) <= 1
    assert pp._para_16k(mono, 16000) is mono


def test_captura_por_processo_exclui_o_proprio_processo():
    """Com o Windows que tem o loopback por processo, o que este processo
    toca nao entra; sem ele, o teste nao se aplica."""
    import pytest
    from telezapp.midia import som_por_processo as pp
    if not pp.disponivel():
        pytest.skip("Windows sem o loopback por processo")
    try:
        captura = pp.abrir()
    except pp.ErroPorProcesso as e:
        pytest.skip("sem captura por processo: %s" % e)
    try:
        assert captura.exato
        quadro = captura.ler()
        assert len(quadro) == sp.BYTES_POR_QUADRO
    finally:
        captura.fechar()

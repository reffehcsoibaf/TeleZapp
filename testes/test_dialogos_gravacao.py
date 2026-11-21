# SPDX-License-Identifier: GPL-3.0-or-later
"""Titulo da janelinha de gravacao com o tempo decorrido (wx simulado)."""
import sys

from testes import wx_falso

sys.modules["wx"] = wx_falso

from telezapp.interface import dialogos  # noqa: E402


class GravadorFalso:
    def __init__(self, segundos=0.0):
        self._segundos = segundos
        self.iniciado = False
        self.parado = False
        self.cancelado = False
        self.microfone_disponivel = True
        self.estourou_limite = False

    @property
    def decorrido(self):
        return self._segundos

    @property
    def gravando(self):
        return self.iniciado and not self.parado

    def iniciar(self):
        self.iniciado = True

    def pausar(self):
        pass

    def continuar(self):
        pass

    def parar(self):
        self.parado = True
        return type("Gravacao", (), {"segundos": self._segundos,
                                      "silenciosa": False,
                                      "caminho": "voz.ogg"})()

    def cancelar(self):
        self.cancelado = True


class FalaFalsa:
    def __init__(self):
        self.ditos = []

    def falar(self, texto, interromper=False):
        self.ditos.append(texto)


def _abrir(monkeypatch, gravadores, ao_tempo=None):
    monkeypatch.setattr(dialogos.time, "sleep", lambda _s: None)
    fala = FalaFalsa()
    antes = len(wx_falso.criados)
    dlg = dialogos.gravar_voz(
        None, lambda: gravadores.pop(0), "Gravar voz", "Instrução", fala,
        ao_terminar=lambda _r: None, ocultar=lambda _d: None,
        ao_tempo=ao_tempo)
    novos = wx_falso.criados[antes:]
    botoes = {b.GetLabel(): b for b in novos
              if isinstance(b, wx_falso.Button)}
    return dlg, botoes


def _apertar(botoes, rotulo):
    botoes[rotulo].ligacoes[wx_falso.EVT_BUTTON]()


def _tick(dlg):
    dlg.ligacoes[wx_falso.EVT_TIMER]()


def test_titulo_com_segundos_e_pausa(monkeypatch):
    g = GravadorFalso()
    dlg, botoes = _abrir(monkeypatch, [g])
    assert dlg.GetTitle() == "Gravar voz"

    _apertar(botoes, "&Gravar")
    assert dlg.GetTitle() == "Gravando - 0 segundos"

    g._segundos = 12.7
    _tick(dlg)
    assert dlg.GetTitle() == "Gravando - 12 segundos"

    _apertar(botoes, "Pausa&r")
    assert dlg.GetTitle() == "Pausado - 12 segundos"
    _tick(dlg)
    assert dlg.GetTitle() == "Pausado - 12 segundos"

    _apertar(botoes, "Pausa&r")
    assert dlg.GetTitle() == "Gravando - 12 segundos"
    g._segundos = 13.9
    _tick(dlg)
    assert dlg.GetTitle() == "Gravando - 13 segundos"


def test_titulo_volta_ao_original_ao_parar(monkeypatch):
    g = GravadorFalso()
    dlg, botoes = _abrir(monkeypatch, [g])
    _apertar(botoes, "&Gravar")
    g._segundos = 5.9
    _tick(dlg)
    assert dlg.GetTitle() == "Gravando - 5 segundos"

    _apertar(botoes, "&Parar de gravar")
    assert dlg.GetTitle() == "Gravar voz"


def test_titulo_volta_ao_original_ao_descartar(monkeypatch):
    g = GravadorFalso()
    dlg, botoes = _abrir(monkeypatch, [g])
    _apertar(botoes, "&Gravar")
    g._segundos = 3.0
    _tick(dlg)
    assert dlg.GetTitle() == "Gravando - 3 segundos"

    _apertar(botoes, "&Descartar")
    assert dlg.GetTitle() == "Gravar voz"
    assert g.cancelado


def test_titulo_volta_ao_original_com_conversao_em_segundo_plano(monkeypatch):
    convertidas = []
    monkeypatch.setattr(dialogos, "parar_em_segundo_plano",
                        lambda g, depois: convertidas.append(g))
    g = GravadorFalso()
    dlg, botoes = _abrir(monkeypatch, [g])
    _apertar(botoes, "&Gravar")
    g._segundos = 25.0

    _apertar(botoes, "&Parar de gravar")
    assert dlg.GetTitle() == "Gravar voz"
    assert convertidas == [g]


def test_avisa_a_janela_principal_do_tempo(monkeypatch):
    tempos = []
    g = GravadorFalso()
    dlg, botoes = _abrir(monkeypatch, [g], ao_tempo=tempos.append)
    assert tempos == []

    _apertar(botoes, "&Gravar")
    assert tempos[-1] == (0, False)
    g._segundos = 8.9
    _tick(dlg)
    assert tempos[-1] == (8, False)
    _apertar(botoes, "Pausa&r")
    assert tempos[-1] == (8, True)
    _apertar(botoes, "Pausa&r")
    assert tempos[-1] == (8, False)
    _apertar(botoes, "&Parar de gravar")
    assert tempos[-1] is None

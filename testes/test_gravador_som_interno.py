# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Captura do som do computador: se a abertura falha no formato de sempre,
tenta outros e registra o motivo de cada falha no log."""
import logging
import sys
import types

import pytest

from telezapp.midia import gravador


class _Gravador:
    def __init__(self, falha):
        self.falha = falha

    def __enter__(self):
        if self.falha:
            raise RuntimeError("erro 0x88890008 de teste")
        return self

    def __exit__(self, *a):
        return False


class _Captura:
    channels = 2

    def __init__(self, aceita):
        self.aceita = aceita          # (canais, bloco) que abrem
        self.pedidos = []

    def recorder(self, samplerate, channels, blocksize):
        self.pedidos.append((channels, blocksize))
        return _Gravador((channels, blocksize) not in self.aceita)


def _soundcard(monkeypatch, captura):
    sc = types.SimpleNamespace(
        default_speaker=lambda: types.SimpleNamespace(name="Saida"),
        all_speakers=lambda: [],
        get_microphone=lambda id, include_loopback: captura)
    monkeypatch.setitem(sys.modules, "soundcard", sc)


def test_abre_no_formato_de_sempre(monkeypatch):
    captura = _Captura({(2, int(gravador.TAXA * gravador.BLOCO_S))})
    _soundcard(monkeypatch, captura)
    gravador.FonteSomInterno()
    assert len(captura.pedidos) == 1


def test_tenta_outro_formato_e_registra(monkeypatch, caplog):
    captura = _Captura({(2, None)})
    _soundcard(monkeypatch, captura)
    with caplog.at_level(logging.INFO, logger="telezapp.gravador"):
        gravador.FonteSomInterno()
    assert len(captura.pedidos) == 2
    assert "0x88890008" in caplog.text
    assert "aberta com 2 canais" in caplog.text


def test_todas_falham_diz_o_tipo_e_registra(monkeypatch, caplog):
    captura = _Captura(set())
    _soundcard(monkeypatch, captura)
    with caplog.at_level(logging.WARNING, logger="telezapp.gravador"):
        with pytest.raises(gravador.ErroGravacao) as e:
            gravador.FonteSomInterno()
    assert "RuntimeError" in str(e.value)
    assert caplog.text.count("falhou") == 3        # (2,bloco) (2,None) (1,None)

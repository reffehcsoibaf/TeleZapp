# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
import sys
import types

import pytest

from telezapp.midia import dispositivos as d

APARELHOS = [
    {"name": "Mapeador de som Microsoft - Input", "max_input_channels": 2,
     "max_output_channels": 0},
    {"name": "Grupo de microfones (Realtek(R)", "max_input_channels": 2,
     "max_output_channels": 0},
    {"name": "Mapeador de som Microsoft - Output", "max_input_channels": 0,
     "max_output_channels": 2},
    {"name": "Alto-falantes (Realtek(R) Audio", "max_input_channels": 0,
     "max_output_channels": 2},
    {"name": "Fone (USB)", "max_input_channels": 1,
     "max_output_channels": 2},
]


@pytest.fixture(autouse=True)
def sd_falso(monkeypatch):
    sd = types.SimpleNamespace(
        default=types.SimpleNamespace(hostapi=0),
        query_hostapis=lambda i: {"devices": list(range(len(APARELHOS)))},
        query_devices=lambda i: APARELHOS[i])
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    d.definir("", "")
    yield
    d.definir("", "")


def test_lista_sem_o_mapeador_e_separa_entrada_de_saida():
    mics, saidas = d.listar()
    assert mics == ["Grupo de microfones (Realtek(R)", "Fone (USB)"]
    assert saidas == ["Alto-falantes (Realtek(R) Audio", "Fone (USB)"]


def test_vazio_e_o_padrao_do_windows():
    assert d.indice_do_microfone() is None
    assert d.indice_da_saida() is None


def test_indice_do_escolhido():
    d.definir("Fone (USB)", "Alto-falantes (Realtek(R) Audio")
    assert d.indice_do_microfone() == 4
    assert d.indice_da_saida() == 3


def test_nome_completo_vale_como_o_cortado():
    d.definir("", "Alto-falantes (Realtek(R) Audio Premium)")
    assert d.indice_da_saida() == 3
    assert d.parecem_o_mesmo("Alto-falantes (Realtek(R) Audio",
                             "Alto-falantes (Realtek(R) Audio Premium)")
    assert not d.parecem_o_mesmo("Fone", "Alto-falantes")
    assert not d.parecem_o_mesmo("", "Fone")


def test_dispositivo_que_sumiu_volta_ao_padrao():
    d.definir("Fone que foi desligado", "")
    assert d.indice_do_microfone() is None


def test_opcoes_e_nome_escolhido():
    itens, pos = d.opcoes(["A", "B"], "B")
    assert itens == ["Padrão do Windows", "A", "B"] and pos == 2
    assert d.nome_escolhido(itens, pos) == "B"
    assert d.opcoes(["A", "B"], "")[1] == 0
    assert d.opcoes(["A", "B"], "sumiu")[1] == 0
    assert d.nome_escolhido(itens, 0) == ""

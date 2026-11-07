# SPDX-License-Identifier: GPL-3.0-or-later
"""Janela Dispositivos de som: cada caixa combinada tem o rotulo criado logo
antes dela (e a ordem em que o leitor de tela acha o nome da caixa)."""
import sys

from testes import wx_falso

sys.modules["wx"] = wx_falso

from telezapp.interface import dispositivos as ui  # noqa: E402


def test_cada_caixa_vem_logo_depois_do_seu_rotulo():
    wx_falso.criados.clear()
    ui.DialogoDispositivos(None, ["Microfone A", "Microfone B"],
                           ["Alto-falantes", "Fone"])
    seq = list(wx_falso.criados)
    caixas = [c for c in seq if isinstance(c, wx_falso.Choice)]
    assert len(caixas) == 3
    esperados = ["Saída de &som", "&Microfone", "Saída dos sons de a&viso"]
    for caixa, inicio in zip(caixas, esperados):
        anterior = seq[seq.index(caixa) - 1]
        assert isinstance(anterior, wx_falso.StaticText)
        assert anterior.label.startswith(inicio), anterior.label

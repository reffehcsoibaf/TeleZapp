# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
from telezapp.nucleo import mencoes as mc

ANA = {"id": "5551@s.whatsapp.net", "nome": "Ana"}
ANA_LIMA = {"id": "5552@s.whatsapp.net", "nome": "Ana Lima"}


def test_localiza_so_depois_de_espaco_ou_no_comeco():
    achados = mc.localizar("@Ana oi mail@Ana e @Ana", [ANA])
    assert [(i, f) for i, f, _ in achados] == [(0, 4), (19, 23)]


def test_nome_mais_longo_vence():
    achados = mc.localizar("oi @Ana Lima e @Ana", [ANA, ANA_LIMA])
    assert [x[2]["id"] for x in achados] == [ANA_LIMA["id"], ANA["id"]]


def test_aplicar_troca_e_diz_onde_ficou():
    novo, pos = mc.aplicar("oi @Ana Lima!", [ANA_LIMA],
                           lambda men: "@5552")
    assert novo == "oi @5552!"
    assert pos == [(3, 8, ANA_LIMA)]


def test_sem_mencoes_nada_muda():
    assert mc.aplicar("oi @Ana", [], str) == ("oi @Ana", [])
    assert mc.aplicar("oi", [ANA], str) == ("oi", [])

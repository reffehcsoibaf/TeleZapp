# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Modo de exibicao e tamanho da letra."""
from telezapp import config
from telezapp.nucleo import aparencia as ap


def test_modo_automatico_segue_o_leitor_de_tela():
    assert ap.modo("automatico", leitor_ligado=True) == ap.LEITOR
    assert ap.modo("automatico", leitor_ligado=False) == ap.VISUAL
    assert ap.modo("qualquer", leitor_ligado=True) == ap.LEITOR


def test_modo_escolhido_vale_com_ou_sem_leitor():
    assert ap.modo("leitor", leitor_ligado=False) == ap.LEITOR
    assert ap.modo("visual", leitor_ligado=True) == ap.VISUAL


def test_tamanho_da_letra_e_limitado():
    assert ap.tamanho_da_letra(9, 100) == 9
    assert ap.tamanho_da_letra(9, 150) == 13.5
    assert ap.tamanho_da_letra(9, 50) == 9          # nunca menor que o normal
    assert ap.tamanho_da_letra(9, "x") == 9
    assert ap.tamanho_da_letra(10, 900) == 30


def test_quebra_entre_palavras_e_corta_palavra_longa():
    medir = len                       # 1 pixel por letra
    assert ap.quebrar_linhas("um dois tres", 7, medir) == ["um dois", "tres"]
    assert ap.quebrar_linhas("abcdefghij", 4, medir) == ["abcd", "efgh", "ij"]
    assert ap.quebrar_linhas("a\nb", 10, medir) == ["a", "b"]
    assert ap.quebrar_linhas("", 10, medir) == [""]


def test_rotulo_do_dia():
    import time
    agora = time.mktime((2026, 11, 3, 15, 0, 0, 0, 0, -1))
    assert ap.rotulo_do_dia(agora - 3600, agora) == "Hoje"
    assert ap.rotulo_do_dia(agora - 86400, agora) == "Ontem"
    assert ap.rotulo_do_dia(agora - 3 * 86400, agora) == "31/10/2026"
    assert ap.rotulo_do_dia(0, agora) == ""


def test_opcoes_na_aparencia():
    chaves = {o.chave: o for o in config.OPCOES}
    assert chaves["modo_exibicao"].categoria == "Aparência"
    assert chaves["modo_exibicao"].padrao == "automatico"
    assert chaves["tamanho_letra"].padrao == 100
    assert [v for v, _ in chaves["tamanho_letra"].escolhas][0] == 100

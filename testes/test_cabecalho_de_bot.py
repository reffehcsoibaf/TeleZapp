# SPDX-License-Identifier: GPL-3.0-or-later
from telezapp.nucleo.ia.cabecalho_de_bot import sem_cabecalho_de_idiomas as f


def test_tira_o_cabecalho_de_idiomas():
    assert f("Welsh → Portugues\nOlá, tudo bem?") == "Olá, tudo bem?"
    assert f("🏴 Welsh ➡️ 🇧🇷 Português\n\nOlá") == "Olá"
    assert f("English -> Portuguese\r\nBom dia") == "Bom dia"


def test_nao_mexe_no_que_nao_e_cabecalho():
    assert f("Olá, tudo bem?") == "Olá, tudo bem?"
    assert f("Ir → casa, agora mesmo.\nOutra linha") == \
        "Ir → casa, agora mesmo.\nOutra linha"
    assert f("Welsh → Portugues") == "Welsh → Portugues"   # nada depois
    assert f("") == ""

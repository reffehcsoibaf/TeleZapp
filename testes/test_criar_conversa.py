# SPDX-License-Identifier: GPL-3.0-or-later
"""Conferencia do que se digita ao criar grupo, canal ou comunidade."""
from telezapp.nucleo import criar_conversa as cc


def test_tipos_por_servico():
    assert cc.tipos_do_servico("whatsapp") == [cc.GRUPO, cc.CANAL,
                                               cc.COMUNIDADE]
    assert cc.tipos_do_servico("telegram") == [cc.GRUPO, cc.CANAL]
    assert cc.tipos_do_servico("outro") == []


def test_validar_nome_vazio_longo_e_descricao_longa():
    assert cc.validar("whatsapp", cc.GRUPO, "  ")[2] == \
        "Escreva o nome do grupo."
    assert cc.validar("whatsapp", cc.COMUNIDADE, "")[2] == \
        "Escreva o nome da comunidade."
    nome, desc, erro = cc.validar("whatsapp", cc.GRUPO, " Turma ", " oi ")
    assert (nome, desc, erro) == ("Turma", "oi", "")
    assert "25 letras" in cc.validar("whatsapp", cc.GRUPO, "x" * 26)[2]
    assert cc.validar("telegram", cc.GRUPO, "x" * 26)[2] == ""
    assert "255 letras" in cc.validar("telegram", cc.CANAL, "N",
                                      "y" * 256)[2]
    assert "não cria comunidades" in cc.validar(
        "telegram", cc.COMUNIDADE, "X")[2]


def test_separar_participantes_tira_vazios_e_repetidos():
    assert cc.separar_participantes(
        "+55 51 99999-1111, @Bia;\n@bia ,, 5551888880000") == [
        "+55 51 99999-1111", "@Bia", "5551888880000"]
    assert cc.separar_participantes("") == []
    assert cc.separar_participantes(None) == []


def test_texto_pronto_concorda_com_o_genero():
    assert cc.texto_pronto(cc.GRUPO, "Turma") == "Grupo Turma criado."
    assert cc.texto_pronto(cc.CANAL, "Notícias") == "Canal Notícias criado."
    assert cc.texto_pronto(cc.COMUNIDADE, "Bairro") == \
        "Comunidade Bairro criada."

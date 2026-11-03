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


def test_menciona_todos_so_com_all_sozinho():
    assert mc.menciona_todos("@all reuniao hoje")
    assert mc.menciona_todos("pessoal, @All, olhem")
    assert mc.menciona_todos("oi\n@ALL")
    assert not mc.menciona_todos("mail@all.com")
    assert not mc.menciona_todos("@allan chegou")
    assert mc.menciona_todos("@todos, reunião")
    assert not mc.menciona_todos("@todosjuntos")
    assert not mc.menciona_todos("")
    assert mc.todos_para_enviar("oi @All e @todos") == "oi @all e @all"
    assert mc.todos_visivel("oi @all") == "oi @todos"


def test_item_todos_e_achado_por_todos_ou_all():
    item = mc.membro_todos()
    rotulo = "%s, %s" % (item["nome"], item["telefone"])
    assert item["todos"] and "@todos" in rotulo and "@all" in rotulo


def test_all_aparece_como_todos_so_em_grupo():
    from telezapp.nucleo import modelos as m
    grupo = m.Mensagem("w1", "120363@g.us", "1", texto="@all bom dia")
    pessoa = m.Mensagem("w1", "5551@s.whatsapp.net", "2", texto="@all oi")
    assert m.conteudo(grupo) == "@todos bom dia"
    assert grupo.texto == "@all bom dia"          # o guardado nao muda
    assert m.conteudo(pessoa) == "@all oi"

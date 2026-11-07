# SPDX-License-Identifier: GPL-3.0-or-later
"""O que o aviso falado de mensagem nova diz e em que ordem."""
from telezapp.nucleo import aviso_de_nova as an

PARTES = {"inicio": "Nova mensagem", "conversa": "Família",
          "servico": "WhatsApp", "conta": "Fábio", "autor": "Ana",
          "hora": "10:00", "conteudo": "oi"}


def test_padrao_e_o_aviso_de_antes():
    assert an.montar(None, PARTES) == "Nova mensagem em Família. Ana, 10:00, oi"
    # na conversa aberta o nome dela nao entra
    assert an.montar(None, PARTES, aberta=True) == \
        "Nova mensagem. Ana, 10:00, oi"


def test_escolher_o_que_falar_e_a_ordem():
    v = an.padrao()
    v, _ = an.alternar(v, "inicio")           # tira "Nova mensagem"
    v, _ = an.alternar(v, "hora")
    v, ativado = an.alternar(v, "servico")
    assert ativado
    v, pos = an.mover(v, "conteudo", -1)      # conteudo antes do autor
    v, pos = an.mover(v, "conteudo", -1)
    assert an.ativos(v) == ["conversa", "servico", "conteudo", "autor"]
    assert an.montar(v, PARTES) == "Família. WhatsApp, oi, Ana"


def test_sempre_sobra_um_item_e_valor_ruim_vira_padrao():
    v = {"ordem": ["conteudo"], "ocultos": list(an.CHAVES)}
    assert an.normalizar(v)["ocultos"] == []
    unico = {"ordem": list(an.CHAVES),
             "ocultos": [c for c in an.CHAVES if c != "conteudo"]}
    _, ativado = an.alternar(unico, "conteudo")
    assert ativado is None
    assert an.normalizar("lixo") == an.padrao()
    assert an.eh_padrao(an.padrao())
    assert an.texto_do_item(an.padrao(), "conta") == \
        "Conta que recebeu: desativado"

# SPDX-License-Identifier: GPL-3.0-or-later
"""Grupo 1: versao, opcoes, paginas, tabelas novas do banco e detalhes."""
import os
import re

import telezapp
from telezapp import config
from telezapp.armazenamento.banco import Banco
from telezapp.nucleo import modelos as m
from telezapp.nucleo import paginas

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_versao_no_formato_e_na_ultima_entrada_dos_registros():
    assert telezapp.versao_valida(telezapp.VERSAO)
    for ruim in ("0.1.0", "2026.13.1.0", "2026.2.30.0", "2026.1.1.70000",
                 "", "2026.1.1"):
        assert not telezapp.versao_valida(ruim)
    assert telezapp.versao_valida("2026.10.9.1")
    with open(os.path.join(RAIZ, "CHANGELOG.md"), encoding="utf-8") as f:
        assert re.search(r"^## %s$" % re.escape(telezapp.VERSAO), f.read(),
                         re.M)
    with open(os.path.join(RAIZ, "telezapp", "ajuda", "novidades.html"),
              encoding="utf-8") as f:
        titulos = re.findall(r"<h2>Versão ([\d.]+)</h2>", f.read())
    assert titulos[0] == telezapp.VERSAO


def test_paginas_trazem_a_versao_e_o_rodape(tmp_path):
    for nome in paginas.PAGINAS:
        caminho = paginas.gerar(nome, str(tmp_path / "temp"))
        html = open(caminho, encoding="utf-8").read()
        assert "{{" not in html
        assert telezapp.VERSAO in html and "<footer>" in html
        assert "GPL" in html and telezapp.SITE in html
    assert paginas.gerar("../config.py", str(tmp_path)) is None


def test_opcoes_e_busca_sem_acento():
    chaves = [o.chave for o in config.OPCOES]
    assert len(chaves) == len(set(chaves))
    assert set(chaves) <= set(config.PADROES)
    assert all(o.categoria and o.descricao for o in config.OPCOES)
    assert [o.chave for o in config.buscar_opcoes("leitor DE TELA")] == \
        ["falar_novas"]
    assert [o.chave for o in config.buscar_opcoes("conteudo")]
    assert config.buscar_opcoes("zzz") == []


def test_temporarios_so_na_pasta_do_app(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path))
    pasta = config.pasta_temporaria()
    assert pasta.startswith(str(tmp_path))
    open(os.path.join(pasta, "x.html"), "w").close()
    config.limpar_temporarios()
    assert not os.path.exists(pasta)


def test_banco_recibos_status_e_midias(tmp_path):
    b = Banco(str(tmp_path / "g.db"))
    b.salvar_recibos("c", "v", ["1", "2"], "ana", "lida", 100)
    b.salvar_recibos("c", "v", ["1"], "ana", "lida", 999)   # repetido
    b.salvar_recibos("c", "v", ["1"], "bia", "entregue", 50)
    assert b.recibos("c", "v", "1") == [("bia", "entregue", 50),
                                        ("ana", "lida", 100)]
    b.salvar_status("c", {"id": "s1", "autor": "Ana", "data": 5})
    b.salvar_status("c", {"id": "s2", "autor": "Bia", "data": 9})
    assert [s["id"] for s in b.status("c")] == ["s2", "s1"]
    b.registrar_midia("c", "v", "1", "foto", "x.jpg", 10, 1)
    assert b.midias("c", "v")[0][3] == "x.jpg"
    b.esquecer_midia("c", "v", "1")
    assert b.midias("c") == []
    b.registrar_midia("c", "v", "1", "foto", "x.jpg", 10, 1)
    b.apagar_conta("c")
    assert b.recibos("c", "v", "1") == [] and b.status("c") == [] and \
        b.midias("c") == []
    b.fechar()


def test_banco_antigo_ganha_as_tabelas(tmp_path):
    import sqlite3
    caminho = str(tmp_path / "v2.db")
    con = sqlite3.connect(caminho)
    con.executescript("CREATE TABLE conversas (conta_id TEXT, id TEXT);"
                      "PRAGMA user_version=2;")
    con.close()
    b = Banco(caminho)
    assert b.recibos("c", "v", "1") == []
    b.fechar()


def test_detalhes_mostram_quem_recebeu_e_leu():
    x = m.Mensagem("c", "v", "1", minha=True, data=100, texto="oi",
                   estado=m.LIDA)
    txt = m.detalhes(x, "Grupo", recibos=[("ana", "entregue", 110),
                                          ("ana", "lida", 120)],
                     nomes={"ana": "Ana"})
    assert "Entregue a Ana em" in txt and "Lida a Ana em" in txt
    assert "Texto completo:" in txt
    outra = m.Mensagem("c", "v", "2", minha=False, texto="x")
    assert "Lida a" not in m.detalhes(outra, "G", recibos=[("a", "lida", 1)])


def test_detalhes_mostram_se_a_midia_esta_baixada():
    x = m.Mensagem("c", "v", "1", tipo=m.FOTO, data=100)
    assert "Mídia: baixada" in m.detalhes(x, "G", midia="baixada")
    assert "Mídia" not in m.detalhes(x, "G")


def test_posicao_da_conversa(tmp_path):
    from telezapp.armazenamento.banco import Banco
    b = Banco(str(tmp_path / "p.db"))
    assert b.posicao("c", "1") is None
    b.salvar_posicao("c", "1", "m5")
    b.salvar_posicao("c", "2", "")
    assert b.posicao("c", "1") == "m5" and b.posicao("c", "2") == ""
    b.apagar_conta("c")
    assert b.posicao("c", "1") is None
    b.fechar()


def test_extras_na_mensagem_e_migracao_do_banco(tmp_path):
    import sqlite3
    from telezapp.armazenamento.banco import Banco
    from telezapp.nucleo import modelos as m
    x = m.Mensagem("c", "1", "9", texto="oi")
    assert m.extras_de(x) == {"links": [], "botoes": [], "mencoes": []}
    m.guardar_extras(x, links=[("https://a.com", "clique aqui")],
                     botoes=[("Abrir", "https://b.com")],
                     mencoes=[{"nome": "Ana", "id": "5"}])
    caminho = str(tmp_path / "v.db")
    b = Banco(caminho)
    b.salvar_mensagens([x])
    volta = b.mensagem("c", "1", "9")
    assert m.extras_de(volta)["links"] == [["https://a.com", "clique aqui"]]
    assert m.extras_de(volta)["mencoes"][0]["nome"] == "Ana"
    b.fechar()
    # banco antigo (sem a coluna extras) ganha a coluna sem perder mensagens
    con = sqlite3.connect(str(tmp_path / "velho.db"))
    con.executescript("""
        CREATE TABLE mensagens (conta_id TEXT, conversa_id TEXT, id TEXT,
            autor TEXT NOT NULL DEFAULT '', minha INTEGER NOT NULL DEFAULT 0,
            data REAL NOT NULL DEFAULT 0, tipo TEXT NOT NULL DEFAULT 'texto',
            texto TEXT NOT NULL DEFAULT '', segundos INTEGER NOT NULL
            DEFAULT 0, nome_arquivo TEXT NOT NULL DEFAULT '', tamanho INTEGER
            NOT NULL DEFAULT 0, estado TEXT NOT NULL DEFAULT '', resposta_a
            TEXT NOT NULL DEFAULT '', remetente TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (conta_id, conversa_id, id));
        INSERT INTO mensagens (conta_id, conversa_id, id, texto)
            VALUES ('c', '1', '1', 'antiga');""")
    con.commit()
    con.close()
    b2 = Banco(str(tmp_path / "velho.db"))
    assert b2.mensagem("c", "1", "1").texto == "antiga"
    assert b2.mensagem("c", "1", "1").extras == ""
    b2.fechar()

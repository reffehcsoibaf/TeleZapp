

def test_nome_do_remetente_acha_o_nome_mais_recente(tmp_path):
    from telezapp.armazenamento.banco import Banco
    from telezapp.nucleo import modelos as m
    b = Banco(str(tmp_path / "b.db"))
    for i, (aut, data) in enumerate([("+5511999", 1), ("Bia", 2), ("Bia B", 3)]):
        x = m.Mensagem("t1", "g@g.us", str(i + 1), autor=aut, data=data,
                       texto="oi")
        x.remetente = "77@lid"
        b.salvar_mensagens([x])
    assert b.nome_do_remetente("t1", {"77@lid", "x"}) == "Bia B"
    assert b.nome_do_remetente("t1", {"99@lid"}) == ""
    assert b.nome_do_remetente("t1", []) == ""


def test_agenda_de_contatos(tmp_path):
    from telezapp.armazenamento.banco import Banco
    b = Banco(str(tmp_path / "c.db"))
    b.salvar_contato("t1", "10", "Zé", "+5551999998888")
    b.salvar_contato("t1", "11", "ana")
    b.salvar_contato("w1", "5551@s.whatsapp.net", "Bia", "+5551")
    assert [c[2] for c in b.contatos()] == ["ana", "Bia", "Zé"]
    assert [c[2] for c in b.contatos("t1")] == ["ana", "Zé"]
    assert b.nome_de_contato("t1", "x", "10") == "Zé"   # primeiro id que existe
    b.salvar_contato("t1", "10", "José")                 # o cache acompanha
    assert b.nome_de_contato("t1", "10") == "José"
    b.remover_contato("t1", "10")
    assert b.nome_de_contato("t1", "10") == ""
    b.apagar_conta("w1")
    assert b.contatos("w1") == []


def test_conversa_trancada_e_arquivada_vao_e_voltam_do_banco(tmp_path):
    from telezapp.armazenamento.banco import Banco
    from telezapp.nucleo import modelos as m
    b = Banco(str(tmp_path / "t.db"))
    b.salvar_conversas([m.Conversa("w1", "1@s.whatsapp.net", "A", "whatsapp",
                                   trancada=True, arquivada=True)])
    c = b.conversas("w1")[0]
    assert c.trancada and c.arquivada


# ------------------------------------------------ mensagens temporarias
def test_prazo_da_conversa_e_da_mensagem_sao_guardados(tmp_path):
    from telezapp.armazenamento.banco import Banco
    from telezapp.nucleo import modelos as m
    b = Banco(str(tmp_path / "t.db"))
    b.salvar_conversas([m.Conversa("c", "1", "Ana", "whatsapp",
                                   temporaria_s=604800)])
    assert b.conversas("c")[0].temporaria_s == 604800
    b.salvar_mensagens([
        m.Mensagem("c", "1", "a", data=100, expira=500),
        m.Mensagem("c", "1", "b", data=100, expira=5000),
        m.Mensagem("c", "1", "c", data=100)])
    assert b.mensagens_expiradas(1000) == [("c", "1", "a")]
    assert b.mensagens_expiradas(10 ** 6) == [("c", "1", "a"), ("c", "1", "b")]
    assert [x.expira for x in b.mensagens("c", "1")] == [500, 5000, 0]
    b.fechar()


def test_banco_antigo_ganha_as_colunas_das_temporarias(tmp_path):
    import sqlite3
    from telezapp.armazenamento import banco as bd
    from telezapp.armazenamento.banco import Banco
    from telezapp.nucleo import modelos as m
    caminho = str(tmp_path / "velho.db")
    antigo = "\n".join(l for l in bd.ESQUEMA.splitlines()
                       if "temporaria_s" not in l and "expira REAL" not in l)
    con = sqlite3.connect(caminho)
    con.executescript(antigo)
    con.execute("INSERT INTO mensagens (conta_id, conversa_id, id, data) "
                "VALUES ('c', '1', 'x', 5)")
    con.commit()
    con.close()
    b = Banco(caminho)
    assert b.mensagens("c", "1")[0].expira == 0
    b.salvar_conversas([m.Conversa("c", "1", "Ana", "telegram",
                                   temporaria_s=86400)])
    assert b.conversas("c")[0].temporaria_s == 86400
    b.fechar()


def test_mensagens_com_recibo_de_reproduzida_viram_reproduzidas_ao_abrir(
        tmp_path):
    from telezapp.armazenamento.banco import Banco
    from telezapp.nucleo import modelos as m
    caminho = str(tmp_path / "r.db")
    b = Banco(caminho)
    b.salvar_mensagens([
        m.Mensagem("w1", "c", "V1", tipo=m.VOZ, minha=True, data=1,
                   estado=m.LIDA),
        m.Mensagem("w1", "c", "V2", tipo=m.VOZ, minha=True, data=2,
                   estado=m.LIDA)])
    b.salvar_recibos("w1", "c", ["V1"], "p", "ouvida", 5)
    b.fechar()
    b = Banco(caminho)                        # abrir de novo corrige V1
    assert b.mensagem("w1", "c", "V1").estado == m.REPRODUZIDA
    assert b.mensagem("w1", "c", "V2").estado == m.LIDA
    b.fechar()


def test_gravar_tenta_de_novo_quando_o_banco_esta_ocupado(monkeypatch):
    import sqlite3
    from telezapp.armazenamento import banco as bd
    esperas = []
    monkeypatch.setattr(bd.time, "sleep", esperas.append)
    chamadas = []

    def gravar():
        chamadas.append(1)
        if len(chamadas) < 3:
            raise sqlite3.OperationalError("database is locked")
        return "ok"
    assert bd._com_tentativas(gravar) == "ok"
    assert len(chamadas) == 3 and esperas == [0.5, 2]


def test_gravar_desiste_e_nao_esconde_outros_erros(monkeypatch):
    import sqlite3
    import pytest
    from telezapp.armazenamento import banco as bd
    monkeypatch.setattr(bd.time, "sleep", lambda s: None)

    def travado():
        raise sqlite3.OperationalError("database is locked")
    with pytest.raises(sqlite3.OperationalError):
        bd._com_tentativas(travado)

    chamadas = []

    def outro():
        chamadas.append(1)
        raise sqlite3.OperationalError("no such table: x")
    with pytest.raises(sqlite3.OperationalError):
        bd._com_tentativas(outro)
    assert len(chamadas) == 1

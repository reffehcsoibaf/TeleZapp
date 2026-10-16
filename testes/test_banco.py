

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

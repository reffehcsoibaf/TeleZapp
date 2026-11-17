# SPDX-License-Identifier: GPL-3.0-or-later
"""Filtros personalizados da lista de conversas."""
from telezapp.nucleo import filtros_personalizados as fp
from telezapp.nucleo import modelos as m

CONTAS = m.opcoes_de_conta([("w1", "whatsapp", "Fábio"), ("w2", "whatsapp", "Ana"),
                            ("t1", "telegram", "Tel")])


def conv(servico="whatsapp", tipo="privada", nao_lidas=0, arquivada=False,
         trancada=False, conta="w1"):
    c = m.Conversa(conta, "x", "Nome", servico)
    c.tipo, c.nao_lidas = tipo, nao_lidas
    c.arquivada, c.trancada = arquivada, trancada
    return c


def test_ou_dentro_de_cada_lista_e_e_entre_as_duas():
    f = {"contas": ["whatsapp"],
         "tipos": ["nao_lidas", "grupos", "arquivadas"]}
    assert fp.passa(conv(nao_lidas=2), f)
    assert fp.passa(conv(tipo="grupo"), f)
    assert fp.passa(conv(arquivada=True), f)
    assert not fp.passa(conv(), f)                       # lida e individual
    assert not fp.passa(conv(servico="telegram", tipo="grupo"), f)


def test_lista_vazia_nao_filtra_e_trancada_nunca_aparece():
    assert fp.passa(conv(), {"contas": [], "tipos": []})
    assert not fp.passa(conv(trancada=True), {"contas": [], "tipos": []})
    assert not fp.passa(conv(trancada=True),
                        {"contas": [], "tipos": ["trancadas"]})


def test_normalizar_descarta_o_que_nao_serve():
    v = fp.normalizar({"ativo": 1, "lista": [
        {"id": "a", "nome": " Um ", "contas": ["whatsapp", "whatsapp", 3],
         "tipos": ["grupos", "trancadas", "inventado"]},
        {"id": "a", "nome": "Repetido"},
        {"id": "b", "nome": ""},
        "lixo"]})
    assert v == {"ativo": True, "lista": [
        {"id": "a", "nome": "Um", "contas": ["whatsapp"],
         "tipos": ["grupos"]}]}
    assert fp.normalizar(None) == {"ativo": False, "lista": []}
    assert fp.em_uso(v)
    assert not fp.em_uso({"ativo": True, "lista": []})
    assert not fp.em_uso({"ativo": False, "lista": v["lista"]})


def test_nome_sugerido_com_os_itens_marcados():
    assert fp.nome_sugerido(
        ["whatsapp"], ["nao_lidas", "grupos", "arquivadas"], CONTAS) == \
        "WhatsApp, Não lidas, Grupos, Arquivadas"
    assert fp.nome_sugerido(["todas"], ["nao_lidas"], CONTAS) == "Não lidas"
    assert fp.nome_sugerido(["telegram"], ["todas"], CONTAS) == "Telegram"
    assert fp.nome_sugerido(["todas"], ["todas"], CONTAS) == \
        "Todas as conversas"
    assert fp.nome_sugerido([], [], CONTAS) == "Todas as conversas"
    assert fp.nome_sugerido(["conta:w1"], ["grupos"], CONTAS) == \
        "Fábio, WhatsApp, Grupos"


def test_nome_livre_e_id_novo():
    lista = [{"id": "f1", "nome": "Grupos"}, {"id": "f2", "nome": "grupos (2)"}]
    assert fp.nome_livre("Outro", lista) == "Outro"
    assert fp.nome_livre("GRUPOS", lista) == "GRUPOS (3)"
    assert fp.nome_livre("Grupos", lista, ignorar_id="f1") == "Grupos"
    assert fp.novo_id(lista) not in {"f1", "f2"}


def test_achar_devolve_o_filtro_ou_o_primeiro():
    v = {"ativo": True, "lista": [{"id": "a", "nome": "A"},
                                  {"id": "b", "nome": "B"}]}
    assert fp.achar(v, "b")["nome"] == "B"
    assert fp.achar(v, "sumiu")["nome"] == "A"
    assert fp.achar(None, "a") is None


def test_nao_mostrar_tira_conversas_do_filtro():
    f = {"contas": ["whatsapp"], "tipos": ["grupos"],
         "nao_tipos": ["silenciadas"]}
    g = conv(tipo="grupo")
    assert fp.passa(g, f)
    g.silenciada_ate = -1
    assert not fp.passa(g, f)
    so_fora = {"nao_contas": ["telegram"], "nao_tipos": ["grupos"]}
    assert fp.passa(conv(), so_fora)
    assert not fp.passa(conv(tipo="grupo"), so_fora)
    assert not fp.passa(conv(servico="telegram"), so_fora)
    assert not fp.passa(conv(trancada=True), so_fora)


def test_nao_mostrar_conta_e_normalizar():
    f = {"nao_contas": ["conta:w2"]}
    assert not fp.passa(conv(conta="w2"), f)
    assert fp.passa(conv(conta="w1"), f)
    v = fp.normalizar({"lista": [{"id": "a", "nome": "X",
                                  "nao_tipos": ["todas", "grupos",
                                                "trancadas", "zzz"],
                                  "nao_contas": ["todas", "telegram"]}]})
    assert v["lista"][0]["nao_tipos"] == ["grupos"]
    assert v["lista"][0]["nao_contas"] == ["telegram"]
    assert fp.usa_favoritas({"nao_tipos": ["favoritas"]})


def test_nome_sugerido_com_menos():
    assert fp.nome_sugerido(["whatsapp"], ["grupos"], CONTAS, [],
                            ["silenciadas"]) == \
        "WhatsApp, Grupos menos Silenciadas"
    assert fp.nome_sugerido([], [], CONTAS, [], ["grupos"]) == \
        "Todas as conversas, menos Grupos"

# SPDX-License-Identifier: GPL-3.0-or-later
"""Busca de canais do WhatsApp: a parte sem wx e sem rede."""
import pytest

from telezapp.nucleo import canais_whatsapp as cw


def no(id="123@newsletter", nome="Notícias", seguidores=1500, papel="GUEST",
       **extra):
    d = {"id": id, "thread_metadata": {
        "name": {"text": nome}, "description": {"text": "  Tudo   do dia  "},
        "subscribers_count": str(seguidores), "verification": "VERIFIED",
        "invite": "AbCdEf123456"}, "viewer_metadata": {"role": papel}}
    d.update(extra)
    return d


def test_pedidos_de_busca_levam_texto_categoria_e_limite():
    pedidos = cw.pedidos("  futebol  ", "SPORTS", "", 20)
    qid, vars_, campo = pedidos[0]
    assert (qid, campo) == cw.BUSCA[0]
    assert vars_ == {"input": {"search_text": "futebol",
                               "categories": ["SPORTS"], "limit": 20,
                               "start_cursor": None}}
    assert [p[0] for p in pedidos[:3]] == [q for q, _ in cw.BUSCA]
    assert pedidos[3][1]["fetch_status_metadata"] is False


def test_pedidos_sem_texto_comecam_pela_lista_do_diretorio():
    pedidos = cw.pedidos("", "", "", 30, ["BR"])
    primeira = pedidos[0]
    assert primeira[0] == cw.LISTA[0][0] and primeira[2] == cw.LISTA[0][1]
    assert primeira[1] == {"input": {
        "view": "RECOMMENDED", "filters": {"country_codes": ["BR"]},
        "limit": 30}}
    cursores = [p[1]["input"].get("start_cursor", "ausente")
                for p in pedidos[:6]]
    assert cursores == ["ausente", None, "", "ausente", None, ""]
    assert [p[1]["input"]["filters"]["country_codes"]
            for p in pedidos[:6]] == [["BR"]] * 3 + [[]] * 3
    reserva = [p for p in pedidos if p[2] == cw.RECOMENDADOS[0][1]]
    assert reserva[0][1] == {"input": {"limit": 20,
                                       "country_codes": ["BR"]}}
    assert reserva[1][1] == {"input": {"limit": 20, "country_codes": []}}
    # sem pais conhecido, so as variacoes sem pais
    semp = cw.pedidos("", "", "")
    assert all(p[1]["input"]["filters"]["country_codes"] == []
               for p in semp if "filters" in p[1]["input"])


def test_pedidos_de_visao_ou_categoria_so_usam_a_lista_do_diretorio():
    pedidos = cw.pedidos("", "", "TRENDING", 5)
    assert pedidos[0][0] == cw.LISTA[0][0]
    assert {p[2] for p in pedidos} == {cw.LISTA[0][1]}
    assert pedidos[0][1]["input"]["view"] == "TRENDING"
    assert pedidos[0][1]["input"]["limit"] == 5
    assert "categories" not in pedidos[0][1]["input"]["filters"]
    pedidos = cw.pedidos("", "NEWS", "")
    assert pedidos[0][1]["input"]["filters"]["categories"] == ["NEWS"]
    assert pedidos[0][1]["input"]["view"] == "RECOMMENDED"


def test_pais_do_telefone():
    assert cw.pais_do_telefone("+55 51 99999 8888") == "BR"
    assert cw.pais_do_telefone("+351 912 345 678") == "PT"
    assert cw.pais_do_telefone("+1 202 555 0100") == "US"
    assert cw.pais_do_telefone("") == "" and cw.pais_do_telefone("+999") == ""


def test_pedidos_ignoram_categoria_e_visao_desconhecidas_e_limitam():
    pedidos = cw.pedidos("x" * 500, "INVENTADA", "OUTRA", 999)
    entrada = pedidos[0][1]["input"]
    assert entrada["categories"] == []
    assert len(entrada["search_text"]) == 100 and entrada["limit"] == 50
    assert cw.pedidos("", "", "OUTRA")[0][0] == cw.LISTA[0][0]


def test_canal_de_le_nome_seguidores_e_convite():
    c = cw.canal_de(no())
    assert c.id == "123@newsletter" and c.nome == "Notícias"
    assert c.seguidores == 1500 and c.verificado and not c.seguindo
    assert c.link == "https://whatsapp.com/channel/AbCdEf123456"
    assert cw.canal_de(no(papel="SUBSCRIBER")).seguindo
    assert cw.canal_de(no(papel="OWNER")).seguindo


def test_canal_de_descarta_o_que_nao_e_canal_ou_sumiu():
    assert cw.canal_de(None) is None
    assert cw.canal_de(no(id="5511@s.whatsapp.net")) is None
    assert cw.canal_de(no(state={"type": "DELETED"})) is None
    assert cw.canal_de(no(state={"type": "ACTIVE"})) is not None
    vazio = cw.canal_de({"id": "9@newsletter"})
    assert vazio.nome == "" and vazio.seguidores is None and vazio.link == ""


def test_canais_da_resposta_aceita_lista_e_resultado_sem_repetir():
    dados = {"xwa2_newsletters_directory_search": {"result": [
        no(), no(), no(id="7@newsletter", nome="Outro"), {"lixo": 1}]}}
    canais = cw.canais_da_resposta(dados, "xwa2_newsletters_directory_search")
    assert [c.id for c in canais] == ["123@newsletter", "7@newsletter"]
    dados = {"xwa2_newsletters_recommended": [no()]}
    assert len(cw.canais_da_resposta(
        dados, "xwa2_newsletters_recommended")) == 1
    assert cw.canais_da_resposta({"campo": None}, "campo") == []


def test_canais_da_resposta_estranha_levanta_erro():
    with pytest.raises(ValueError):
        cw.canais_da_resposta({"outro": []}, "campo")
    with pytest.raises(ValueError):
        cw.canais_da_resposta({"campo": "texto"}, "campo")
    with pytest.raises(ValueError):
        cw.canais_da_resposta(None, "campo")


def test_linha_diz_nome_verificado_seguidores_e_se_ja_segue():
    c = cw.canal_de(no(papel="SUBSCRIBER"))
    assert cw.linha(c) == ("Notícias, verificado, 1.500 seguidores, você já "
                           "segue. Tudo do dia")
    um = cw.canal_de(no(seguidores=1))
    assert "1 seguidor" in cw.linha(um) and "segue" not in cw.linha(um)
    longo = cw.CanalWA("1@newsletter", "", "a" * 300, None, False, False, "")
    texto = cw.linha(longo, 20)
    assert texto.startswith("Canal sem nome. ") and texto.endswith("…")


def test_resumo():
    assert cw.resumo(0) == "Nenhum canal encontrado."
    assert cw.resumo(1) == "1 canal encontrado."
    assert cw.resumo(12) == "12 canais encontrados."


def test_pedidos_com_cursor_repetem_o_formato_e_mandam_o_cursor():
    primeira = cw.pedidos("", "", "", 30, ["BR"])[0]
    seguinte = cw.pedidos("", "", "", 30, ["BR"], "ABC==")
    assert len(seguinte) == 2 * len(cw.LISTA)    # com e sem pais, por id
    assert seguinte[0][0] == primeira[0]
    assert seguinte[0][1]["input"]["start_cursor"] == "ABC=="
    assert cw.forma_da_consulta(seguinte[0][1]) == \
        cw.forma_da_consulta(primeira[1])
    busca = cw.pedidos("bom", "", "", 30, [], "XYZ")
    assert busca[0][1]["input"]["start_cursor"] == "XYZ"
    assert cw.forma_da_consulta(busca[0][1]) == cw.forma_da_consulta(
        cw.pedidos("bom")[0][1])
    assert cw.tipo_do_cursor(busca[0][1]) == "pagina"
    tipos = [cw.tipo_do_cursor(p[1]) for p in cw.pedidos("", "", "", 30,
                                                          ["BR"])[:3]]
    assert tipos == ["ausente", "nulo", "vazio"]


def test_proximo_cursor_le_page_info_e_o_fim():
    campo = "xwa2_newsletters_directory_list"
    assert cw.proximo_cursor({campo: {
        "result": [], "page_info": {"endCursor": "abc"}}}, campo) == "abc"
    assert cw.proximo_cursor({campo: {
        "pageInfo": {"end_cursor": "z", "hasNextPage": True}}}, campo) == "z"
    assert cw.proximo_cursor({campo: {"page_info": {
        "endCursor": "abc", "hasNextPage": False}}}, campo) == ""
    assert cw.proximo_cursor({campo: {"page_info": {
        "startCursor": "ini", "endCursor": "fim"}}}, campo) == "fim"
    assert cw.proximo_cursor({campo: {"page_info": {
        "nextCursor": "x"}}}, campo) == ""     # so o cursor do fim vale
    assert cw.resumo_da_pagina({campo: {"page_info": {
        "endCursor": "A" * 30, "hasNextPage": True}}}, campo) == \
        "endCursor='AAAAAAAAAAAA...', hasNextPage=True"
    assert cw.resumo_da_pagina({campo: {}}, campo) == "sem page_info"
    assert cw.proximo_cursor({campo: {"result": []}}, campo) == ""
    assert cw.proximo_cursor({campo: [no()]}, campo) == ""
    assert cw.proximo_cursor(None, campo) == ""
    assert cw.proximo_cursor({campo: {"page_info": {"endCursor": 5}}},
                             campo) == ""


class _Pagina:
    pass


def _dialogo(monkeypatch, buscar, seguir=None, falar=None):
    import sys
    from testes import wx_falso
    sys.modules["wx"] = wx_falso
    from telezapp.interface import busca_canais as bc
    monkeypatch.setattr(bc.threading, "Thread", _ThreadNaHora)
    return bc, bc.DialogoBuscaDeCanais(
        None, [("w1", "Vivo")], buscar, seguir, falar=falar)


def test_dialogo_busca_mostra_resultados_e_segue_com_confirmacao(monkeypatch):
    from testes import wx_falso
    canal = cw.canal_de(no())
    ditas, seguidos = [], []
    bc, d = _dialogo(
        monkeypatch, lambda *a: cw.Pagina([canal]),
        lambda conta, c: seguidos.append(c.id) or (True, "Seguindo!"),
        ditas.append)
    d.termo.SetValue("noticias")
    d.buscar()
    assert d.canais == [canal] and "1 canal encontrado." in ditas
    assert d.lista.GetSelection() == 0
    monkeypatch.setattr(bc.dialogos, "perguntar", lambda *a, **k: wx_falso.NO)
    d._seguir()
    assert seguidos == []                        # recusou
    monkeypatch.setattr(bc.dialogos, "perguntar", lambda *a, **k: wx_falso.YES)
    d._seguir()
    assert seguidos == ["123@newsletter"] and ditas[-1] == "Seguindo!"
    assert d.canais[0].seguindo and "você já segue" in d.lista.GetString(0)
    d._seguir()
    assert ditas[-1] == "Você já segue este canal."


def test_dialogo_ver_mais_acrescenta_ate_o_whatsapp_nao_ter_mais(monkeypatch):
    paginas = {"": cw.Pagina([cw.canal_de(no(id="1@newsletter")),
                              cw.canal_de(no(id="2@newsletter"))], "C1"),
               "C1": cw.Pagina([cw.canal_de(no(id="2@newsletter")),
                                cw.canal_de(no(id="3@newsletter")),
                                cw.canal_de(no(id="4@newsletter"))], "C2"),
               "C2": cw.Pagina([cw.canal_de(no(id="3@newsletter"))], "C3"),
               "C3": cw.Pagina([], "")}
    pedidos, ditas = [], []

    def buscar(conta, texto, categoria, visao, cursor=""):
        pedidos.append((texto, categoria, visao, cursor))
        return paginas[cursor]
    bc, d = _dialogo(monkeypatch, buscar, falar=ditas.append)
    d.termo.SetValue("bom")
    d.categoria.SetSelection(1)
    d.buscar()
    assert len(d.canais) == 2 and d.proximo == "C1" and d.b_mais.IsEnabled()
    assert not d.fim
    d.termo.SetValue("outra coisa")              # mudar o campo nao muda o pedido
    d.lista.SetSelection(1)
    d.ver_mais()
    assert [c.id for c in d.canais] == ["1@newsletter", "2@newsletter",
                                        "3@newsletter", "4@newsletter"]
    assert pedidos[1] == ("bom", "NEWS", "RECOMMENDED", "C1")
    assert d.lista.GetSelection() == 2           # no primeiro canal novo
    assert d.proximo == "C2" and d.b_mais.IsEnabled()
    assert "2 canais a mais, 4 no total." in ditas[-1]
    d.ver_mais()                                 # so repete um e vem vazia: acabou
    assert d.proximo == "" and d.fim and not d.b_mais.IsEnabled()
    assert ditas[-1] == "O WhatsApp não tem mais canais."
    d.ver_mais()
    assert ditas[-1] == "Não há mais canais."
    assert len(pedidos) == 4                     # C2 sem novos segue ate C3


def test_dialogo_atravessa_paginas_vazias_com_cursor(monkeypatch):
    chamadas = []
    paginas = {"": cw.Pagina([], "C1"), "C1": cw.Pagina([], "C2"),
               "C2": cw.Pagina([cw.canal_de(no(id="7@newsletter"))], "C3"),
               "C3": cw.Pagina([], "C4"), "C4": cw.Pagina([], "C4")}

    def buscar(conta, texto, categoria, visao, cursor=""):
        chamadas.append(cursor)
        return paginas[cursor]
    ditas = []
    bc, d = _dialogo(monkeypatch, buscar, falar=ditas.append)
    d.buscar()                              # a 1a pagina vem vazia, com cursor
    assert chamadas == ["", "C1", "C2"]
    assert [c.id for c in d.canais] == ["7@newsletter"] and d.proximo == "C3"
    d.ver_mais()                            # C3 vazia, C4 vazia e repetida
    assert chamadas[3:] == ["C3", "C4"]
    assert d.fim and ditas[-1] == "O WhatsApp não tem mais canais."


def test_dialogo_para_depois_de_muitas_paginas_vazias(monkeypatch):
    chamadas = []

    def buscar(conta, texto, categoria, visao, cursor=""):
        chamadas.append(cursor)
        return cw.Pagina([], "P%d" % len(chamadas))
    bc, d = _dialogo(monkeypatch, buscar)
    d.buscar()
    assert len(chamadas) == 1 + bc.PAGINAS_VAZIAS_SEGUIDAS
    assert d.canais == []


def test_dialogo_ver_mais_sem_cursor_continua_ligado_e_explica(monkeypatch):
    ditas = []
    bc, d = _dialogo(monkeypatch, lambda *a: cw.Pagina([cw.canal_de(no())]),
                     falar=ditas.append)
    d.ver_mais()
    assert ditas[-1] == "Faça uma busca antes."
    d.buscar()
    assert d.proximo == "" and d.b_mais.IsEnabled()      # o leitor o acha
    d.ver_mais()
    assert ditas[-1] == ("O WhatsApp não informou a próxima página desta "
                         "lista.")


def test_dialogo_ver_mais_com_erro_mantem_a_lista_e_o_botao(monkeypatch):
    estado = {"falha": False}

    def buscar(conta, texto, categoria, visao, cursor=""):
        if cursor and estado["falha"]:
            raise RuntimeError("O WhatsApp demorou demais para responder.")
        return cw.Pagina([cw.canal_de(no())], "C1")
    ditas = []
    bc, d = _dialogo(monkeypatch, buscar, falar=ditas.append)
    d.buscar()
    estado["falha"] = True
    d.ver_mais()
    assert len(d.canais) == 1 and d.proximo == "C1" and d.b_mais.IsEnabled()
    assert ditas[-1].startswith("O WhatsApp demorou")


def test_dialogo_busca_mostra_o_erro_da_busca(monkeypatch):
    def falha(*a):
        raise RuntimeError("O WhatsApp demorou demais para responder.")
    ditas = []
    bc, d = _dialogo(monkeypatch, falha, falar=ditas.append)
    d.buscar()
    assert d.canais == [] and ditas[-1].startswith("O WhatsApp demorou")


class _ThreadNaHora:
    def __init__(self, target=None, **k):
        self.target = target

    def start(self):
        self.target()

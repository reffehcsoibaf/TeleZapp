# SPDX-License-Identifier: GPL-3.0-or-later
"""Formularios do WhatsApp (Flows): a ponte com a pagina da Meta, a busca dos
dados e a resposta final, tudo sem rede nem janela."""
import io
import json
import types

import pytest

from telezapp.nucleo import ponte_flows as pf

PARAMS = {
    "flow_message_version": "3", "flow_token": "ficha-123", "flow_id": "999",
    "flow_cta": "Iniciar atendimento", "flow_action": "navigate",
    "flow_action_payload": {"screen": "RECOMMEND"}, "mode": "published",
    "flow_metadata": {"flow_name": "x", "www_proxy_secret": "segredo",
                      "flow_token_signature": "assinatura", "categories": []}}


def test_dados_do_formulario_juntam_botao_json_e_chave():
    d = pf.dados_do_formulario(PARAMS, {"screens": [], "version": "7.3"},
                               chave_publica="CHAVE", biz_jid="5561@s",
                               nome_da_empresa="Sicoob")
    assert d["extension_id"] == "999" and d["flow_token"] == "ficha-123"
    assert d["public_key"] == "CHAVE" and d["business_name"] == "Sicoob"
    assert d["flow_action"] == "navigate"
    # sem chave da empresa, vale uma de reserva no formato que a pagina quer
    import base64
    reserva = pf.dados_do_formulario(PARAMS, "{}")["public_key"]
    assert base64.b64decode(reserva).startswith(b"-----BEGIN PUBLIC KEY-----")
    assert len(reserva) > 500
    import base64
    assert json.loads(base64.b64decode(d["flow_action_payload"])) == {
        "screen": "RECOMMEND"}               # em base64, como o WhatsApp Web
    assert d["response_viewer"] == "CONSUMER" and d["biz_platform"] == 4
    assert d["entry_point_conversation_initiated"] == -1
    assert json.loads(d["flow_json"])["version"] == "7.3"
    assert d["www_proxy_secret"] == "segredo"
    assert d["flow_token_signature"] is None      # como o WhatsApp Web
    assert d["extension_status"] == "PUBLISHED" and d["is_flow_interactive"]
    # os mesmos campos que o WhatsApp Web entrega
    assert set(d) >= {"public_key", "biz_jid", "flow_token", "qpl_message_id",
                      "wam_message_id", "wam_session_id", "extension_id",
                      "qpl_session_id", "is_template", "biz_platform",
                      "flow_entry_point", "response_viewer"}


def test_ab_props_devolvem_o_padrao_de_cada_um():
    pedido = {"1777": {"type": "bool", "defaultValue": "false"},
              "13022": {"type": "double", "defaultValue": "10"}}
    assert pf.valores_dos_ab_props(pedido) == {
        "1777": {"type": "bool", "value": "false"},
        "13022": {"type": "double", "value": "10"}}
    assert pf.valores_dos_ab_props(None) == {}


def test_resposta_final_leva_o_que_o_formulario_entregou_e_o_token():
    j = json.loads(pf.resposta_final({"response": {"cpf": "1"}}, "tok"))
    assert j == {"cpf": "1", "flow_token": "tok"}
    j = json.loads(pf.resposta_final({"data": '{"a": 2}'}, "tok"))
    assert j == {"a": 2, "flow_token": "tok"}
    j = json.loads(pf.resposta_final({"flow_token": "ja", "x": 1}, "tok"))
    assert j == {"flow_token": "ja", "x": 1}
    assert json.loads(pf.resposta_final("texto", "t"))["response"] == "texto"


def test_formato_nunca_guarda_o_que_foi_preenchido():
    f = pf.formato({"cpf": "12345678900", "dados": {"nome": "Ana"},
                    "lista": ["a", "b", "c"], "n": 5, "ok": True})
    texto = json.dumps(f)
    assert "12345678900" not in texto and "Ana" not in texto
    assert f["cpf"] == "<texto 11>" and f["n"] == "<n>" and f["ok"] is True


def test_script_de_resposta_entrega_um_texto_json():
    js = pf.script_de_resposta({"responseData": None, "callbackID": "c1"})
    assert js.startswith("window.__tzFlows(") and "callbackID" in js
    # como o WhatsApp Web: o texto JSON entre aspas, nao um objeto
    assert js.startswith('window.__tzFlows("')
    assert pf.ler_mensagem("não é json") is None
    assert pf.ler_mensagem('{"eventName": "x"}') == {"eventName": "x"}


class UIFalsa:
    def __init__(self):
        self.chamadas = []

    def carregada(self):
        self.chamadas.append("carregada")

    def dados(self):
        self.chamadas.append("dados")
        return {"flow_token": "t"}

    def titulo(self, texto):
        self.chamadas.append(("titulo", texto))

    def fechar(self):
        self.chamadas.append("fechar")

    def completar(self, payload):
        self.chamadas.append(("completar", payload))

    def abrir_url(self, url):
        self.chamadas.append(("url", url))


def test_ponte_responde_cada_pedido_da_pagina():
    ui = UIFalsa()
    p = pf.Ponte(ui)
    assert p.tratar({"eventName": pf.EV_CARREGADA}) is pf.Ponte.NADA
    assert p.tratar({"eventName": pf.EV_DADOS, "callbackID": "1"}) == {
        "flow_token": "t"}
    ab = p.tratar({"eventName": pf.EV_AB_PROPS, "payload": {
        "1": {"type": "bool", "defaultValue": "true"}}})
    assert ab == {"1": {"type": "bool", "value": "true"}}
    assert p.tratar({"eventName": pf.EV_BARRA, "payload": {
        "title": "Passo 1"}}) is None
    assert p.tratar({"eventName": pf.EV_TROCA_DE_DADOS, "payload": {
        "data": {}, "screen": "A"}}) is None
    assert p.tratar({"eventName": "WAMLogger", "payload": {}}) is None
    p.tratar({"eventName": pf.EV_COMPLETAR, "payload": {"response": {"a": 1}}})
    p.tratar({"eventName": pf.EV_ABRIR_URL, "payload": {
        "url": "https://exemplo.com"}})
    p.tratar({"eventName": pf.EV_FECHAR})
    assert ui.chamadas == ["carregada", "dados", ("titulo", "Passo 1"),
                           ("completar", {"response": {"a": 1}}),
                           ("url", "https://exemplo.com"), "fechar"]
    assert pf.EV_DADOS in p.eventos


# ------------------------------------------------------------ o provedor
neonize = pytest.importorskip("neonize")
from neonize.proto.waE2E import WAWebProtobufsE2E_pb2 as E  # noqa: E402

from telezapp.nucleo import modelos as m  # noqa: E402
from telezapp.provedores import whatsapp as wa  # noqa: E402


def _botao_de_formulario():
    nf = E.InteractiveMessage.NativeFlowMessage(buttons=[
        E.InteractiveMessage.NativeFlowMessage.NativeFlowButton(
            name="galaxy_message", buttonParamsJSON=json.dumps(PARAMS))])
    return E.Message(interactiveMessage=E.InteractiveMessage(
        body=E.InteractiveMessage.Body(text="Clique abaixo"),
        nativeFlowMessage=nf))


def test_a_acao_do_formulario_guarda_os_parametros_inteiros():
    acoes = wa.acoes_do_whatsapp(_botao_de_formulario())
    assert len(acoes) == 1 and acoes[0]["tipo"] == "formulario"
    assert acoes[0]["rotulo"] == "Iniciar atendimento"
    assert json.loads(acoes[0]["params"])["flow_token"] == "ficha-123"


class RespostaHttp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _provedor_de_formulario(monkeypatch, json_do_fluxo=None, erro_http=None):
    p = object.__new__(wa.ProvedorWhatsApp)
    p.cliente, p._conectada = None, False      # sem mapa de LID
    p._conversas = {"5561@s.whatsapp.net": m.Conversa(
        "w1", "5561@s.whatsapp.net", "Sicoob", "whatsapp")}
    visto = {"gets": []}

    def urlopen(pedido, timeout=0):
        if erro_http:
            raise erro_http
        visto["gets"].append(pedido.full_url)
        return RespostaHttp(json.dumps(
            json_do_fluxo or {"screens": [], "version": "7.3"}).encode())
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return p, visto


def _msg():
    return m.Mensagem(conta_id="w1", conversa_id="5561@s.whatsapp.net",
                      id="m1", texto="x")


def test_buscar_formulario_estatico_baixa_o_json_e_usa_a_chave_de_reserva(
        monkeypatch):
    p, visto = _provedor_de_formulario(monkeypatch)
    d = p.buscar_formulario(_msg(), {"tipo": "formulario", "id": "999",
                                     "params": json.dumps(PARAMS)})
    assert visto["gets"] == ["https://web.whatsapp.com/flows/json/999"]
    assert d["public_key"] == pf.chave_de_reserva()
    assert json.loads(d["flow_json"])["version"] == "7.3"
    assert d["business_name"] == "Sicoob" and d["extension_id"] == "999"


def test_formulario_que_consulta_a_empresa_avisa_em_vez_de_abrir(
        monkeypatch):
    p, visto = _provedor_de_formulario(monkeypatch)
    dinamico = dict(PARAMS, flow_metadata=dict(
        PARAMS["flow_metadata"], data_api_version=3))
    with pytest.raises(RuntimeError, match="consulta a empresa"):
        p.buscar_formulario(_msg(), {"tipo": "formulario", "id": "999",
                                     "params": json.dumps(dinamico)})
    assert visto["gets"] == []           # nem baixa o JSON: avisa direto


def test_formulario_dinamico_e_estatico_se_reconhecem_pelos_parametros():
    assert pf.formulario_consulta_a_empresa(PARAMS) is False
    assert pf.formulario_consulta_a_empresa(dict(PARAMS, flow_metadata={
        "data_api_version": 3})) is True
    assert pf.formulario_consulta_a_empresa(dict(PARAMS, flow_metadata={
        "data_api_protocol": "x"})) is True


def test_buscar_formulario_diz_o_motivo_quando_nao_baixa(monkeypatch):
    import urllib.error
    p, _ = _provedor_de_formulario(
        monkeypatch, erro_http=urllib.error.URLError("sem rede"))
    msg = m.Mensagem(conta_id="w1", conversa_id="5561@s.whatsapp.net",
                     id="m1", texto="x")
    with pytest.raises(RuntimeError, match="baixar o formulário"):
        p.buscar_formulario(msg, {"tipo": "formulario", "id": "999",
                                  "params": json.dumps(PARAMS)})
    with pytest.raises(RuntimeError, match="número do formulário"):
        p.buscar_formulario(msg, {"tipo": "formulario", "id": "",
                                  "params": "{}"})


def test_resposta_do_formulario_vira_native_flow_response():
    p = object.__new__(wa.ProvedorWhatsApp)
    msg = m.Mensagem(conta_id="w1", conversa_id="5561@s.whatsapp.net",
                     id="m1", texto="Clique abaixo")
    resposta = pf.resposta_final({"response": {"cpf": "1"}}, "ficha-123")
    acao = {"tipo": "formulario_resposta", "resposta": resposta,
            "rotulo": "Enviado"}
    mensagem = p._mensagem_de_acao(msg, acao)
    r = mensagem.interactiveResponseMessage
    assert r.nativeFlowResponseMessage.name == "galaxy_message"
    assert json.loads(r.nativeFlowResponseMessage.paramsJSON) == {
        "cpf": "1", "flow_token": "ficha-123"}
    assert r.nativeFlowResponseMessage.version == 3
    assert r.body.text == "Enviado"
    assert r.contextInfo.stanzaID == "m1"


def test_responder_formulario_usa_o_token_do_botao(monkeypatch):
    p = object.__new__(wa.ProvedorWhatsApp)
    enviadas = []
    p.responder_acao = lambda msg, acao: enviadas.append(acao)
    msg = m.Mensagem(conta_id="w1", conversa_id="5561@s.whatsapp.net",
                     id="m1", texto="x")
    p.responder_formulario(msg, {"tipo": "formulario",
                                 "params": json.dumps(PARAMS)},
                           {"response": {"nome": "Ana"}})
    assert enviadas[0]["tipo"] == "formulario_resposta"
    assert json.loads(enviadas[0]["resposta"]) == {
        "nome": "Ana", "flow_token": "ficha-123"}

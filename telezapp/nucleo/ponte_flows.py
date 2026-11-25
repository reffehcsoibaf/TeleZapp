# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Formularios do WhatsApp (Flows): a conversa entre a pagina da Meta e o
TeleZapp. Sem wx.

O WhatsApp Web mostra o formulario com uma pagina da Meta
(https://flows.whatsapp.net/flows-v2/wa-web/) dentro de um quadro, e ela fala
com o aplicativo por `postMessage`: `{eventName, payload, callbackID}` para
pedir, e `{responseData, callbackID}` para a resposta. Aqui a pagina abre
sozinha no WebView2: o script injetado no inicio faz `window.postMessage`
entregar tudo ao TeleZapp e devolve as respostas como se viessem de
https://web.whatsapp.com. Pesquisa e eventos: docs/flows-whatsapp-pesquisa.md.
"""
import base64
import json
import logging
import uuid

log = logging.getLogger("telezapp.flows")

URL_DA_PAGINA = "https://flows.whatsapp.net/flows-v2/wa-web/"
URL_DO_JSON = "https://web.whatsapp.com/flows/json/%s"
ORIGEM_DO_APLICATIVO = "https://web.whatsapp.com"
NOME_DO_MANIPULADOR = "telezappFlows"

# Nomes dos eventos que a pagina manda (WAFlowsWebBridgeEventNames)
EV_CARREGADA = "flows-iframe-loaded"
EV_DADOS = "WAExtensionsGetFlowData"
EV_AB_PROPS = "WAExtensionsGetClientAbProps"
EV_COMPLETAR = "WAExtensionsComplete"
EV_FECHAR = "WAExtensionsClose"
EV_BARRA = "WAExtensionsConfigureNavBar"
EV_NAVEGAR = "WAExtensionsNavigate"
EV_ABRIR_URL = "WAFlowsOpenURL"
EV_NAVEGACAO_EXTERNA = "WAFlowsExternalNavigation"
EV_TROCA_DE_DADOS = "WAExtensionsDataChannelExchange"

# O script injetado no inicio da pagina: a pagina chama window.parent
# .postMessage; como ela abre sozinha na janela, `window.parent` e `window.top`
# passam a ser um quadro invisivel (mesma origem) cujo postMessage entrega tudo
# ao TeleZapp. `__tzFlows(texto)` entrega uma resposta como o WhatsApp Web faz:
# o texto JSON num evento message vindo de https://web.whatsapp.com.
SCRIPT_DA_PONTE = """
(function () {
  var enviar = function (m) {
    try {
      var texto = (typeof m === "string") ? m : JSON.stringify(m);
      window.%(manipulador)s.postMessage(texto);
    } catch (e) {}
  };
  // a pagina foi feita para ficar num quadro: window.parent e uma janela
  // diferente da dela, e as respostas chegam com essa janela como origem do
  // evento. Um quadro invisivel (mesma origem) faz o papel do aplicativo.
  var pai = null;
  var janelaDoPai = function () {
    if (pai) { return pai; }
    var q = document.createElement("iframe");
    q.setAttribute("aria-hidden", "true");
    q.tabIndex = -1;
    q.style.cssText = "position:absolute;width:0;height:0;border:0;" +
                      "visibility:hidden";
    (document.documentElement || document.body).appendChild(q);
    pai = q.contentWindow;
    pai.postMessage = function (m) {
      var d = m;
      if (typeof d === "string") { try { d = JSON.parse(d); } catch (e) {} }
      if (d && typeof d === "object") { enviar(d); }
    };
    return pai;
  };
  try {
    Object.defineProperty(window, "parent", {configurable: true,
                                              get: janelaDoPai});
    Object.defineProperty(window, "top", {configurable: true,
                                          get: janelaDoPai});
  } catch (e) {}
  // erros e avisos da pagina vao ao registro (so para achar o que falta)
  var avisar = function (nivel, args) {
    try {
      var t = Array.prototype.slice.call(args).map(function (x) {
        return (x && x.message) ? x.message : String(x); }).join(" ");
      enviar({eventName: "__tzlog", payload: {nivel: nivel,
                                              texto: t.slice(0, 300)}});
    } catch (e) {}
  };
  ["error", "warn"].forEach(function (n) {
    var o = console[n];
    console[n] = function () { avisar(n, arguments);
                               return o.apply(console, arguments); };
  });
  window.addEventListener("error", function (e) {
    avisar("erro", [e.message, e.filename ? "@" + e.filename.slice(-40) : ""]);
  });
  window.addEventListener("unhandledrejection", function (e) {
    avisar("rejeicao", [e.reason]);
  });
  window.__tzRecebidas = 0;
  window.__tzFlows = function (dados) {
    window.__tzRecebidas++;
    window.dispatchEvent(new MessageEvent("message", {
      data: dados, origin: "%(origem)s", source: janelaDoPai()}));
  };
})();
""" % {"manipulador": NOME_DO_MANIPULADOR, "origem": ORIGEM_DO_APLICATIVO}


def script_de_resposta(corpo):
    """O JavaScript que entrega `corpo` (dict) a pagina."""
    # o WhatsApp Web entrega a resposta como texto JSON (nao como objeto)
    return "window.__tzFlows(%s);" % json.dumps(json.dumps(corpo))


def ler_mensagem(texto):
    """O dict que a pagina enviou, ou None se nao fizer sentido."""
    try:
        dados = json.loads(texto)
    except (ValueError, TypeError):
        return None
    return dados if isinstance(dados, dict) else None


def formato(valor, profundidade=0):
    """So o formato de um valor (chaves e tipos, textos viram o tamanho): o
    registro nunca guarda o que a pessoa preencheu."""
    if profundidade > 5:
        return "…"
    if valor is None or isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return "<n>"
    if isinstance(valor, str):
        return "<texto %d>" % len(valor)
    if isinstance(valor, (list, tuple)):
        return ["<%d itens>" % len(valor)] + [
            formato(v, profundidade + 1) for v in valor[:2]]
    if isinstance(valor, dict):
        return {str(k): formato(v, profundidade + 1)
                for k, v in list(valor.items())[:30]}
    return "<%s>" % type(valor).__name__


# ------------------------------------------------------------ os dados
def parametros_do_botao(texto):
    """O JSON dos parametros do botao `galaxy_message` (buttonParamsJSON)."""
    try:
        dados = json.loads(texto or "{}")
    except (ValueError, TypeError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _em_base64(valor):
    """A pagina espera o `flow_action_payload` como o JSON em base64 (o
    WhatsApp Web o entrega assim); um texto ja em base64 passa como esta."""
    if isinstance(valor, str):
        try:
            base64.b64decode(valor, validate=True)
            return valor
        except ValueError:
            pass
        valor = json.loads(valor) if valor.strip().startswith("{") else {}
    texto = json.dumps(valor if valor is not None else {},
                       ensure_ascii=False, separators=(",", ":"))
    return base64.b64encode(texto.encode("utf-8")).decode("ascii")


def formulario_consulta_a_empresa(params):
    """O formulario troca dados com a empresa a cada tela (precisa da chave
    publica dela)? Os parametros do botao dizem: `data_api_version`."""
    meta = params.get("flow_metadata") or {}
    return meta.get("data_api_version") is not None or         meta.get("data_api_protocol") is not None


_CHAVE_DE_RESERVA = []


def chave_de_reserva():
    """Uma chave publica valida (base64 do PEM, como a pagina espera) para
    quando a consulta do WhatsApp nao devolve a da empresa. Basta para os
    formularios sem troca de dados com a empresa: a pagina so confere o
    formato. Gerada uma vez por abertura do programa."""
    if not _CHAVE_DE_RESERVA:
        from Cryptodome.PublicKey import RSA
        pem = RSA.generate(2048).publickey().export_key().decode("ascii")
        _CHAVE_DE_RESERVA.append(base64.b64encode(
            pem.encode("ascii")).decode("ascii"))
    return _CHAVE_DE_RESERVA[0]


def dados_do_formulario(params, flow_json, chave_publica="", biz_jid="",
                        nome_da_empresa="", logo=""):
    """O `responseData` de WAExtensionsGetFlowData: o que a pagina precisa
    para desenhar o formulario. `params` sao os parametros do botao."""
    meta = params.get("flow_metadata") or {}
    texto_do_json = flow_json if isinstance(flow_json, str) else json.dumps(
        flow_json, ensure_ascii=False, separators=(",", ":"))
    return {
        "public_key": chave_publica or chave_de_reserva(),
        "biz_jid": biz_jid,
        "flow_token": params.get("flow_token", ""),
        "extension_status": "PUBLISHED" if params.get(
            "mode", "published") == "published" else "DRAFT",
        "qpl_message_id": str(uuid.uuid4()),
        "wam_message_id": str(uuid.uuid4()),
        "wam_session_id": str(uuid.uuid4()),
        "extension_id": str(params.get("flow_id", "")),
        "qpl_session_id": str(uuid.uuid4()),
        "business_name": nome_da_empresa,
        "biz_logo": logo,
        "is_template": False,
        "biz_platform": 4,
        "entry_point_conversation_initiated": -1,
        "flow_action": params.get("flow_action", "navigate"),
        "flow_action_payload": _em_base64(params.get("flow_action_payload")),
        "flow_json": texto_do_json,
        "flow_entry_point": 0,
        "click_sequence_number": None,
        "is_flow_interactive": True,
        "response_viewer": "CONSUMER",
        "www_proxy_secret": meta.get("www_proxy_secret", ""),
        # o WhatsApp Web manda null aqui mesmo quando o botao traz assinatura
        "flow_token_signature": None,
    }


def valores_dos_ab_props(pedido):
    """`{id: {type, value}}` para o pedido `{id: {type, defaultValue}}`: o
    TeleZapp nao tem essas configuracoes, entao vale o padrao de cada uma."""
    saida = {}
    for chave, item in (pedido or {}).items():
        if not isinstance(item, dict):
            continue
        padrao = item.get("defaultValue", "")
        saida[chave] = {"type": item.get("type", "string"),
                        "value": padrao if isinstance(padrao, str)
                        else json.dumps(padrao)}
    return saida


# --------------------------------------------------------- a resposta
def resposta_final(payload, flow_token=""):
    """O texto JSON (`paramsJSON`) da resposta que o formulario concluido
    manda a empresa. `payload` e o que a pagina entregou em
    WAExtensionsComplete."""
    corpo = payload
    if isinstance(payload, dict):
        for chave in ("response", "response_json", "data", "payload"):
            if isinstance(payload.get(chave), (dict, str)):
                corpo = payload[chave]
                break
    if isinstance(corpo, str):
        try:
            corpo = json.loads(corpo)
        except ValueError:
            corpo = {"response": corpo}
    if not isinstance(corpo, dict):
        corpo = {"response": corpo}
    corpo = dict(corpo)
    if flow_token and "flow_token" not in corpo:
        corpo["flow_token"] = flow_token
    return json.dumps(corpo, ensure_ascii=False, separators=(",", ":"))


class Ponte:
    """Decide o que fazer com cada pedido da pagina. `ui` implementa:
    carregada(), dados() -> responseData, titulo(texto), fechar(),
    completar(payload), abrir_url(url). Devolve o `responseData` para
    responder na hora, ou `Ponte.NADA` para nao responder."""

    NADA = object()

    def __init__(self, ui):
        self.ui = ui
        self.eventos = []          # nomes vistos, para o registro

    def tratar(self, mensagem):
        nome = mensagem.get("eventName") or mensagem.get("type") or ""
        payload = mensagem.get("payload")
        if nome == "__tzlog":
            log.info("formulário: a página disse (%s): %s",
                     (payload or {}).get("nivel"), (payload or {}).get(
                         "texto"))
            return self.NADA
        self.eventos.append(nome)
        log.info("formulário: evento %s%s", nome, (" payload " + json.dumps(
            formato(payload), ensure_ascii=False)[:300]
            if payload not in (None, {}) else ""))
        if nome == EV_CARREGADA:
            self.ui.carregada()
            return self.NADA
        if nome == EV_DADOS:
            return self.ui.dados()
        if nome == EV_AB_PROPS:
            return valores_dos_ab_props(payload)
        if nome == EV_BARRA:
            if isinstance(payload, dict):
                self.ui.titulo(str(payload.get("title") or ""))
            return None
        if nome == EV_COMPLETAR:
            self.ui.completar(payload)
            return None
        if nome == EV_FECHAR:
            self.ui.fechar()
            return None
        if nome in (EV_ABRIR_URL, EV_NAVEGACAO_EXTERNA):
            url = payload.get("url") if isinstance(payload, dict) else payload
            if isinstance(url, str):
                self.ui.abrir_url(url)
            return None
        # DataChannelExchange, Navigate, telemetria (WAMLogger, WAQPLLogger),
        # vibrar, arrastar...: sem efeito aqui; a pagina so espera a resposta
        return None

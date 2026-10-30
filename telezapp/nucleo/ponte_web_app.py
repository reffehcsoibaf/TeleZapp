# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""A conversa entre um aplicativo de robo do Telegram e o TeleZapp.

A pagina chama `window.TelegramWebviewProxy.postEvent(tipo, dados)`, como faz
no aplicativo do Telegram para computador, e recebe as respostas por
`window.Telegram.WebView.receiveEvent(tipo, dados)`. Sem wx: `tratar` decide o
que cada pedido faz e usa `ui`, que a janela implementa. Referencia dos eventos:
https://core.telegram.org/api/web-events
"""
import json
import logging

log = logging.getLogger("telezapp.app_do_robo")

SCRIPT_DA_PONTE = """
window.TelegramWebviewProxy = {
  postEvent: function (tipo, dados) {
    window.telezappPonte.postMessage(JSON.stringify([tipo, dados || ""]));
  }
};
"""
NOME_DO_MANIPULADOR = "telezappPonte"
TEMA = {"bg_color": "#ffffff", "text_color": "#000000",
        "hint_color": "#707579", "link_color": "#0b5cad",
        "button_color": "#0b5cad", "button_text_color": "#ffffff",
        "secondary_bg_color": "#f1f1f1", "header_bg_color": "#ffffff",
        "accent_text_color": "#0b5cad", "section_bg_color": "#ffffff",
        "section_header_text_color": "#0b5cad",
        "subtitle_text_color": "#707579", "destructive_text_color": "#c00000",
        "bottom_bar_bg_color": "#ffffff"}
BOTOES = {"web_app_setup_main_button": "principal",
          "web_app_setup_secondary_button": "secundario",
          "web_app_setup_back_button": "voltar",
          "web_app_setup_settings_button": "configuracoes"}
EVENTO_DO_BOTAO = {"principal": "main_button_pressed",
                   "secundario": "secondary_button_pressed",
                   "voltar": "back_button_pressed",
                   "configuracoes": "settings_button_pressed"}
AREA_ZERO = {"top": 0, "bottom": 0, "left": 0, "right": 0}


def ler_mensagem(texto):
    """(tipo, dados) do que a pagina enviou; (None, {}) se nao fizer sentido.
    A pagina manda os dados como texto JSON, ou nada."""
    try:
        tipo, dados = json.loads(texto)
        if isinstance(dados, str):
            dados = json.loads(dados) if dados else {}
    except (ValueError, TypeError):
        return None, {}
    if not isinstance(tipo, str):
        return None, {}
    return tipo, dados if isinstance(dados, dict) else {}


def script_de_resposta(tipo, dados=None):
    """O JavaScript que entrega um evento a pagina."""
    return ("window.Telegram && window.Telegram.WebView && "
            "window.Telegram.WebView.receiveEvent(%s, %s);" % (
                json.dumps(tipo), json.dumps(dados or {})))


def tratar(tipo, dados, ui):
    """Faz o que a pagina pediu. Devolve [(evento, dados)] para responder na
    hora (pedidos que dependem do servico respondem depois, pela `ui`)."""
    if tipo in BOTOES:
        ui.botao(BOTOES[tipo], bool(dados.get("is_visible")),
                 dados.get("text", ""), dados.get("is_active", True))
    elif tipo == "web_app_close":
        ui.fechar()
    elif tipo == "web_app_request_theme":
        return [("theme_changed", {"theme_params": TEMA})]
    elif tipo in ("web_app_request_viewport", "web_app_expand"):
        largura, altura = ui.tamanho()
        return [("viewport_changed", {
            "width": largura, "height": altura, "is_expanded": True,
            "is_state_stable": True})]
    elif tipo == "web_app_request_safe_area":
        return [("safe_area_changed", AREA_ZERO)]
    elif tipo == "web_app_request_content_safe_area":
        return [("content_safe_area_changed", AREA_ZERO)]
    elif tipo == "web_app_open_link":
        ui.abrir_link(dados.get("url", ""))
    elif tipo == "web_app_open_tg_link":
        ui.abrir_link("https://t.me" + (dados.get("path_full") or ""))
    elif tipo == "web_app_open_popup":
        return [("popup_closed", {"button_id": ui.janelinha(
            dados.get("title", ""), dados.get("message", ""),
            dados.get("buttons") or [])})]
    elif tipo == "web_app_data_send":
        ui.enviar_dados(dados.get("data", ""))
    elif tipo == "web_app_invoke_custom_method":
        ui.metodo(dados.get("req_id", ""), dados.get("method", ""),
                  dados.get("params") or {})
    elif tipo == "web_app_request_write_access":
        ui.pedir_escrita()
    elif tipo == "web_app_request_phone":
        ui.pedir_telefone()
    elif tipo == "web_app_open_invoice":
        ui.pagar(dados.get("slug", ""))
    elif tipo == "payment_form_submit":
        ui.pagamento(dados.get("credentials") or {})
    elif tipo == "web_app_read_text_from_clipboard":
        return [("clipboard_text_received", dict(
            {"req_id": dados.get("req_id", "")}, **ui.ler_area()))]
    elif tipo == "web_app_open_scan_qr_popup":
        ui.ler_qr(dados.get("text", ""))
    elif tipo == "web_app_switch_inline_query":
        ui.buscar_inline(dados.get("query", ""))
    elif tipo == "web_app_setup_closing_behavior":
        ui.confirmar_ao_fechar(bool(dados.get("need_confirmation")))
    elif tipo == "web_app_biometry_get_info":
        ui.info_da_biometria()
    elif tipo == "web_app_biometry_request_access":
        ui.acesso_a_biometria(dados.get("reason", ""))
    elif tipo == "web_app_biometry_request_auth":
        ui.autenticar_biometria(dados.get("reason", ""))
    elif tipo == "web_app_biometry_update_token":
        ui.guardar_segredo(dados.get("token", ""))
    elif tipo == "web_app_biometry_open_settings":
        ui.abrir_ajustes_da_biometria()
    elif tipo == "web_app_check_location":
        ui.conferir_localizacao()
    elif tipo == "web_app_request_location":
        ui.pedir_localizacao()
    elif tipo == "web_app_open_location_settings":
        ui.abrir_ajustes_da_localizacao()
    else:
        log.debug("evento do aplicativo sem tratamento: %s", tipo)
    return []

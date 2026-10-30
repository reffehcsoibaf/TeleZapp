# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""O que um link do Telegram ou do WhatsApp pede para o TeleZapp fazer.

Sem wx nem rede. `interpretar` devolve um dicionario, ou None para o que nao
e destes servicos (ou que o TeleZapp nao sabe abrir): esse segue para o
navegador. Chaves:
  servico   "telegram" ou "whatsapp"
  acao      "entrar" (grupo ou canal por convite), "usuario" (Telegram: uma
            pessoa, robo, grupo ou canal pelo @) ou "telefone" (WhatsApp)
  convite   "entrar": a acao no formato de nucleo.grupo e do provedor
  usuario, start, startapp, app, texto   "usuario"; start e startapp ficam
            None quando o link nao os traz (startapp pode vir vazio)
  telefone, texto   "telefone"
"""
import re
from urllib.parse import parse_qs, unquote, urlsplit

from telezapp.nucleo import grupo as ng

HOSTS_TELEGRAM = {"t.me", "www.t.me", "telegram.me", "www.telegram.me"}
HOSTS_WHATSAPP_CONVERSA = {"wa.me", "www.wa.me", "api.whatsapp.com",
                           "web.whatsapp.com", "www.whatsapp.com"}
HOSTS_WHATSAPP_CONVITE = {"chat.whatsapp.com", "whatsapp.com",
                          "www.whatsapp.com"}
# caminhos de t.me que nao sao o @ de ninguem
RESERVADOS = {"joinchat", "addstickers", "addemoji", "share", "proxy", "socks",
              "login", "setlanguage", "addtheme", "bg", "boost", "iv",
              "invoice", "contact", "c", "s", "m", "giftcode", "confirmphone",
              "addlist", "nft"}
RE_USUARIO = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
RE_APP = re.compile(r"^[A-Za-z0-9_]{1,64}$")
RE_CONVITE = re.compile(r"^[A-Za-z0-9_-]{10,}$")
LIMITE = 4096


def _um(q, chave):
    """O valor do parametro; None se o link nao o traz."""
    valores = q.get(chave)
    return valores[0] if valores else None


def _convite_telegram(codigo):
    if not RE_CONVITE.match(codigo or ""):
        return None
    return {"servico": "telegram", "acao": "entrar",
            "convite": {"tipo": "entrar", "modo": "convite", "codigo": codigo,
                        "rotulo": "Entrar no grupo ou canal (convite)"}}


def _usuario(usuario, q, app=""):
    if not RE_USUARIO.match(usuario or "") or usuario.lower() in RESERVADOS:
        return None
    if app and not RE_APP.match(app):
        app = ""
    return {"servico": "telegram", "acao": "usuario", "usuario": usuario,
            "start": _um(q, "start"), "startapp": _um(q, "startapp"),
            "app": app, "texto": _um(q, "text") or ""}


def _telegram_web(partes, q):
    if not partes:
        return None
    primeiro = partes[0]
    if primeiro.startswith("+"):
        return _convite_telegram(primeiro[1:])
    if primeiro == "joinchat" and len(partes) > 1:
        return _convite_telegram(partes[1])
    # t.me/robo/aplicativo; t.me/canal/123 e o link de uma postagem
    segundo = partes[1] if len(partes) > 1 else ""
    return _usuario(primeiro, q, "" if segundo.isdigit() else segundo)


def _telegram_tg(host, q):
    if host == "join":
        return _convite_telegram(_um(q, "invite"))
    if host == "resolve":
        return _usuario(_um(q, "domain"), q, _um(q, "appname") or "")
    return None


def _telefone(numero, q):
    digitos = re.sub(r"\D", "", numero or "")
    if not 8 <= len(digitos) <= 15:
        return None
    return {"servico": "whatsapp", "acao": "telefone", "telefone": digitos,
            "texto": _um(q, "text") or ""}


def _whatsapp_web(host, partes, q, url):
    if host in HOSTS_WHATSAPP_CONVITE and (
            host == "chat.whatsapp.com" or partes[:1] == ["channel"]):
        convite = ng.acao_do_link(url)
        return {"servico": "whatsapp", "acao": "entrar", "convite": convite} \
            if convite else None
    if host not in HOSTS_WHATSAPP_CONVERSA:
        return None
    if host in ("wa.me", "www.wa.me"):
        return _telefone(partes[0], q) if partes else None
    if partes[:1] == ["send"]:
        return _telefone(_um(q, "phone"), q)
    return None


def interpretar(url):
    url = (url or "").strip()
    if not url or len(url) > LIMITE:
        return None
    try:
        partes_url = urlsplit(url)
    except ValueError:
        return None
    esquema = partes_url.scheme.lower()
    host = (partes_url.hostname or "").lower()
    q = parse_qs(partes_url.query, keep_blank_values=True)
    partes = [unquote(p) for p in partes_url.path.split("/") if p]
    if esquema == "tg":
        return _telegram_tg(host, q)
    if esquema == "whatsapp":
        return _telefone(_um(q, "phone"), q) if host == "send" else None
    if esquema not in ("http", "https"):
        return None
    if host in HOSTS_TELEGRAM:
        return _telegram_web(partes, q)
    return _whatsapp_web(host, partes, q, url)

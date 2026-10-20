# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Previa de links buscada pelo proprio TeleZapp (titulo, descricao e nome do
site de uma pagina), para as mensagens recebidas e as que ele envia.

Ligar isso faz o computador da pessoa abrir o link: o site fica sabendo do IP
dela. Por isso as duas opcoes (receber e enviar) vem desligadas e a busca e
cautelosa: so http e https, nada de enderecos da rede local ou do proprio
computador (nem depois de redirecionamentos), poucos segundos de espera e no
maximo 400 KB de pagina. A rede entra como parametro, para testar."""
import html.parser
import ipaddress
import logging
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

from telezapp import VERSAO
from telezapp.nucleo import modelos as m

log = logging.getLogger("telezapp.previa")

TEMPO_LIMITE = 5          # segundos
MAX_BYTES = 400 * 1024
MAX_REDIRECIONAMENTOS = 4
USER_AGENT = "Mozilla/5.0 (compatible; TeleZapp/%s; previa de link)" % VERSAO

# Ligadas pela janela a partir das opcoes `previa_receber` e `previa_enviar`
LIGADAS = {"receber": False, "enviar": False}


def definir(receber, enviar):
    LIGADAS["receber"], LIGADAS["enviar"] = bool(receber), bool(enviar)


def endereco_publico(url):
    """http ou https, com um nome que so resolve para enderecos da internet
    (nunca o proprio computador nem a rede local)."""
    try:
        partes = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    if partes.scheme not in ("http", "https") or not partes.hostname:
        return False
    try:
        achados = socket.getaddrinfo(partes.hostname, partes.port or None,
                                     proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError):
        return False
    enderecos = {a[4][0].split("%")[0] for a in achados}
    return bool(enderecos) and all(
        ipaddress.ip_address(e).is_global for e in enderecos)


class _Pagina(html.parser.HTMLParser):
    """Junta <title> e os <meta> uteis do comeco da pagina."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.titulo, self.meta = "", {}
        self._no_titulo = False
        self.acabou = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title" and not self.titulo:
            self._no_titulo = True
        elif tag == "meta":
            chave = (a.get("property") or a.get("name") or "").lower()
            if chave and a.get("content") and chave not in self.meta:
                self.meta[chave] = a["content"]
            if a.get("charset"):
                self.meta.setdefault("_charset", a["charset"])
        elif tag == "body":
            self.acabou = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._no_titulo = False
        elif tag == "head":
            self.acabou = True

    def handle_data(self, dados):
        if self._no_titulo:
            self.titulo += dados


def _charset(cabecalho, bruto):
    achado = re.search(r"charset=([\w-]+)", cabecalho or "", re.I) or \
        re.search(rb"charset=[\"']?([\w-]+)", bruto[:2048], re.I)
    if achado:
        nome = achado.group(1)
        return nome.decode("ascii", "ignore") if isinstance(
            nome, bytes) else nome
    return "utf-8"


def ler_previa(url, tipo, bruto):
    """Previa ({url, titulo, descricao, site}) do html; {} se nao e pagina."""
    if "html" not in (tipo or "").lower():
        return {}
    cabecalho = tipo or ""
    try:
        texto = bruto.decode(_charset(cabecalho, bruto), "replace")
    except LookupError:
        texto = bruto.decode("utf-8", "replace")
    pagina = _Pagina()
    try:
        for i in range(0, len(texto), 4096):
            pagina.feed(texto[i:i + 4096])
            if pagina.acabou:
                break
    except Exception:
        log.info("pagina com html que nao deu para ler")
    meta = pagina.meta
    titulo = meta.get("og:title") or meta.get("twitter:title") or pagina.titulo
    descricao = meta.get("og:description") or meta.get(
        "twitter:description") or meta.get("description") or ""
    site = meta.get("og:site_name") or urllib.parse.urlsplit(url).hostname
    return m.previa_de_link(meta.get("og:url") or url, titulo, descricao,
                            site or "")


class _SoPublico(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECIONAMENTOS

    def redirect_request(self, req, fp, code, msg, headers, novo):
        if not endereco_publico(novo):
            raise urllib.error.URLError("redirecionamento para endereço "
                                        "não público")
        return super().redirect_request(req, fp, code, msg, headers, novo)


def baixar_pagina(url):
    """(tipo de conteudo, primeiros bytes) da pagina; levanta OSError."""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5"})
    opener = urllib.request.build_opener(_SoPublico)
    with opener.open(req, timeout=TEMPO_LIMITE) as r:
        return r.headers.get("Content-Type", ""), r.read(MAX_BYTES)


def primeiro_link(texto):
    """O primeiro endereco de um texto, ou ""."""
    achados = m.extrair_links(texto)
    return achados[0][0] if achados else ""


def buscar(url, baixar=baixar_pagina):
    """A previa do link ou {} (sem rede, pagina que nao e html, endereco que
    nao e publico...). Nunca levanta."""
    try:
        if not endereco_publico(url):
            return {}
        tipo, bruto = baixar(url)
        return ler_previa(url, tipo, bruto)
    except Exception as e:
        log.info("sem previa de link (%s)", type(e).__name__)
        return {}

# SPDX-License-Identifier: GPL-3.0-or-later
"""Previa de links buscada pelo TeleZapp: leitura da pagina e as travas."""
import urllib.error

import pytest

from telezapp.nucleo import previa_links as pl

HTML = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<title>  Titulo   da página </title>"
    "<meta name='description' content='Descrição simples'>"
    "<meta property='og:title' content='Título do OG'>"
    "<meta property='og:description' content='Descrição do OG'>"
    "<meta property='og:site_name' content='Meu Site'>"
    "</head><body><p>nada daqui</p><title>outro</title></body></html>"
).encode("utf-8")


def test_le_titulo_descricao_e_site_da_pagina():
    p = pl.ler_previa("https://exemplo.com/a", "text/html; charset=utf-8", HTML)
    assert (p["titulo"], p["descricao"], p["site"]) == (
        "Título do OG", "Descrição do OG", "Meu Site")
    # sem Open Graph: <title> e description; site vira o endereco
    simples = (b"<html><head><title> So  titulo </title>"
               b"<meta name='description' content='D'></head></html>")
    p = pl.ler_previa("https://www.exemplo.com/x", "text/html", simples)
    assert (p["titulo"], p["descricao"], p["site"]) == (
        "So titulo", "D", "www.exemplo.com")
    # latin-1 declarado no cabecalho
    latin = "<title>Ação</title>".encode("latin-1")
    assert pl.ler_previa("https://a.com", "text/html; charset=iso-8859-1",
                         latin)["titulo"] == "Ação"
    # nao e pagina, ou nao tem nada
    assert pl.ler_previa("https://a.com/f.pdf", "application/pdf", b"%PDF") \
        == {}
    assert pl.ler_previa("https://a.com", "text/html", b"<html></html>") == {}


def test_so_enderecos_publicos_http_e_https():
    assert pl.endereco_publico("https://8.8.8.8/x")
    assert not pl.endereco_publico("http://127.0.0.1:8000/")
    assert not pl.endereco_publico("http://localhost/")
    assert not pl.endereco_publico("http://192.168.0.10/")
    assert not pl.endereco_publico("http://10.1.2.3/")
    assert not pl.endereco_publico("http://169.254.169.254/latest")
    assert not pl.endereco_publico("http://[::1]/")
    assert not pl.endereco_publico("ftp://8.8.8.8/")
    assert not pl.endereco_publico("file:///c:/segredo.txt")
    assert not pl.endereco_publico("https:///sem-host")
    assert not pl.endereco_publico("javascript:alert(1)")


def test_buscar_nunca_levanta_e_respeita_as_travas():
    chamadas = []

    def baixar(url):
        chamadas.append(url)
        return "text/html", HTML
    assert pl.buscar("http://127.0.0.1/admin", baixar) == {}
    assert chamadas == []                          # nem tentou
    p = pl.buscar("https://8.8.8.8/a", baixar)
    assert p["titulo"] == "Título do OG" and chamadas == ["https://8.8.8.8/a"]

    def cai(url):
        raise urllib.error.URLError("sem rede")
    assert pl.buscar("https://8.8.8.8/a", cai) == {}
    assert pl.primeiro_link("veja https://a.com/x e https://b.com") == \
        "https://a.com/x"
    assert pl.primeiro_link("sem link") == ""


def test_redirecionamento_para_a_rede_local_e_recusado():
    manipulador = pl._SoPublico()
    with pytest.raises(urllib.error.URLError):
        manipulador.redirect_request(
            None, None, 302, "Found", {}, "http://192.168.0.1/roteador")

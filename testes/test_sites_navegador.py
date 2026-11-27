# SPDX-License-Identifier: GPL-3.0-or-later
"""O que o navegador interno lembra de cada site (nucleo/sites_navegador.py)."""
import json

from telezapp.nucleo import sites_navegador as s


def _sites(tmp_path):
    return s.SitesDoNavegador(str(tmp_path / "sites.json"))


def test_dominio_e_host():
    assert s.host_do_site("https://www.exemplo.com/a") == "exemplo.com"
    assert s.host_do_site("ftp://exemplo.com") == ""
    assert s.dominio_do_site("https://trip.uber.com/x6uGg6") == "uber.com"
    assert s.dominio_do_site("https://m.uber.com/") == "uber.com"
    assert s.dominio_do_site("https://loja.exemplo.com.br/p") == "exemplo.com.br"
    assert s.dominio_do_site("http://127.0.0.1:8000/") == "127.0.0.1"


def test_exibicao_vale_para_o_dominio_todo(tmp_path):
    st = _sites(tmp_path)
    assert st.exibicao("https://trip.uber.com/x") == ""
    st.definir_exibicao("https://trip.uber.com/x", s.CELULAR)
    assert st.exibicao("https://m.uber.com/") == s.CELULAR
    assert st.exibicao("https://outro.com/") == ""
    st.definir_exibicao("https://m.uber.com/", "")
    assert st.exibicao("https://trip.uber.com/x") == ""


def test_campos_por_pagina_e_cifrados(tmp_path):
    st = _sites(tmp_path)
    st.guardar_campos("https://a.com/conf", {"c:aviso:1": "1", "t:nome": "Maria"})
    st.guardar_campos("https://a.com/conf", {"t:nome": "Ana"})
    assert st.campos("https://a.com/conf?x=1") == {"c:aviso:1": "1", "t:nome": "Ana"}
    assert st.campos("https://a.com/outra") == {}
    assert st.campos("https://b.com/conf") == {}
    bruto = (tmp_path / "sites.json").read_text(encoding="utf-8")
    assert "Ana" not in bruto and "Maria" not in bruto


def test_senha_cifrada_e_por_endereco_exato(tmp_path):
    st = _sites(tmp_path)
    assert st.senha_guardada("https://a.com/login") is None
    st.guardar_senha("https://a.com/login", "eu@x.com", "segredo123")
    assert st.senha_guardada("https://www.a.com/outra") == ("eu@x.com", "segredo123")
    assert st.senha_guardada("https://sub.a.com/") is None
    assert st.mesma_senha("https://a.com/", "eu@x.com", "segredo123")
    assert not st.mesma_senha("https://a.com/", "eu@x.com", "outra")
    bruto = (tmp_path / "sites.json").read_text(encoding="utf-8")
    assert "segredo123" not in bruto and "eu@x.com" not in bruto
    st.guardar_senha("https://a.com/", "eu@x.com", "nova")
    assert st.senha_guardada("https://a.com/") == ("eu@x.com", "nova")
    assert len(json.loads(bruto)["senhas"]["a.com"]) == 1


def test_nunca_guardar_e_esquecer(tmp_path):
    st = _sites(tmp_path)
    st.nunca_guardar("https://a.com/")
    assert st.nunca_guarda("https://a.com/x")
    st.guardar_senha("https://a.com/", "u", "p")   # guardar de novo desfaz o "nunca"
    assert not st.nunca_guarda("https://a.com/")
    st.guardar_campos("https://a.com/", {"t:x": "1"})
    st.definir_exibicao("https://a.com/", s.CELULAR)
    st.esquecer_site("https://a.com/")
    assert st.senha_guardada("https://a.com/") is None
    assert st.campos("https://a.com/") == {}
    assert st.exibicao("https://a.com/") == ""

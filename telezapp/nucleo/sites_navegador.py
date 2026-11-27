# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""O que o navegador interno lembra de cada site: a exibicao (celular ou
computador), o que a pessoa marcou ou preencheu nos formularios e o usuario e
a senha que ela mandou guardar.

Tudo fica num arquivo da pasta de dados. Valores de campos e senhas sao
cifrados com o DPAPI do Windows (so o mesmo usuario, neste computador, os
le), como as chaves de IA (nucleo/ia/cofre.py). Nada vai no log.
"""
import base64
import json
import logging
import os
import re
from urllib.parse import urlsplit

from telezapp.nucleo.ia.cofre import _dpapi

log = logging.getLogger("telezapp.sites")

CELULAR = "celular"
COMPUTADOR = "computador"

# Segundo nivel de dominios nacionais (com.br, co.uk...): ai o "site" tem 3
# partes. Nao e a lista publica de sufixos, mas cobre o uso comum.
_SEGUNDO_NIVEL = {"com", "net", "org", "gov", "edu", "co", "ac", "mil"}


def host_do_site(url):
    """Endereco sem o "www." ("" se nao for http/https)."""
    try:
        partes = urlsplit(url)
    except ValueError:
        return ""
    if partes.scheme.lower() not in ("http", "https"):
        return ""
    host = (partes.hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def dominio_do_site(url):
    """O dominio "de verdade" (trip.uber.com e m.uber.com -> uber.com):
    vale para a exibicao, que e do site todo."""
    host = host_do_site(url)
    if not host or re.fullmatch(r"[\d.]+", host) or ":" in host:
        return host
    rotulos = host.split(".")
    if len(rotulos) >= 3 and rotulos[-2] in _SEGUNDO_NIVEL \
            and len(rotulos[-1]) == 2:
        return ".".join(rotulos[-3:])
    return ".".join(rotulos[-2:])


def caminho_da_pagina(url):
    try:
        return urlsplit(url).path or "/"
    except ValueError:
        return "/"


def _cifrar(texto):
    return base64.b64encode(_dpapi(texto.encode("utf-8"), True)).decode("ascii")


def _decifrar(bruto):
    try:
        return _dpapi(base64.b64decode(bruto), False).decode("utf-8")
    except (OSError, ValueError):
        return None


class SitesDoNavegador:
    def __init__(self, caminho):
        self.caminho = caminho

    # -- arquivo
    def _ler(self):
        try:
            with open(self.caminho, encoding="utf-8") as f:
                dados = json.load(f)
            return dados if isinstance(dados, dict) else {}
        except (OSError, ValueError):
            return {}

    def _gravar(self, dados):
        try:
            tmp = self.caminho + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(dados, f)
            os.replace(tmp, self.caminho)
        except OSError:
            log.exception("não consegui gravar as preferências dos sites")

    # -- exibicao (por dominio)
    def exibicao(self, url):
        """"celular", "computador" ou "" (nunca escolheu: o padrao)."""
        v = self._ler().get("exibicao", {}).get(dominio_do_site(url), "")
        return v if v in (CELULAR, COMPUTADOR) else ""

    def definir_exibicao(self, url, modo):
        dom = dominio_do_site(url)
        if not dom:
            return
        dados = self._ler()
        mapa = dados.setdefault("exibicao", {})
        if modo in (CELULAR, COMPUTADOR):
            mapa[dom] = modo
        else:
            mapa.pop(dom, None)
        self._gravar(dados)

    # -- campos de formulario (por site e pagina)
    def campos(self, url):
        """{campo: valor} guardado para esta pagina."""
        host = host_do_site(url)
        bruto = self._ler().get("campos", {}).get(host, {}).get(
            caminho_da_pagina(url))
        saida = {}
        for chave, valor in (bruto or {}).items():
            texto = _decifrar(valor)
            if texto is not None:
                saida[chave] = texto
        return saida

    def guardar_campos(self, url, novos):
        """Junta os campos mexidos pela pessoa aos ja guardados."""
        host = host_do_site(url)
        if not host or not isinstance(novos, dict) or not novos:
            return
        dados = self._ler()
        pagina = dados.setdefault("campos", {}).setdefault(
            host, {}).setdefault(caminho_da_pagina(url), {})
        for chave, valor in list(novos.items())[:200]:
            if isinstance(chave, str) and isinstance(valor, str) \
                    and len(valor) <= 5000:
                pagina[chave[:200]] = _cifrar(valor)
        self._gravar(dados)

    # -- senhas (por endereco exato)
    def senha_guardada(self, url):
        """(usuario, senha) da ultima conta guardada para este site, ou None."""
        contas = self._ler().get("senhas", {}).get(host_do_site(url)) or []
        if not isinstance(contas, list) or not contas:
            return None
        ultima = contas[-1]
        usuario = _decifrar(ultima.get("u", ""))
        senha = _decifrar(ultima.get("s", ""))
        if usuario is None or senha is None:
            return None
        return usuario, senha

    def guardar_senha(self, url, usuario, senha):
        host = host_do_site(url)
        if not host or not senha:
            return
        dados = self._ler()
        contas = dados.setdefault("senhas", {}).setdefault(host, [])
        contas[:] = [c for c in contas if _decifrar(c.get("u", "")) != usuario]
        contas.append({"u": _cifrar(usuario), "s": _cifrar(senha)})
        dados.get("nunca", {}).pop(host, None)
        self._gravar(dados)

    def nunca_guardar(self, url, valor=True):
        host = host_do_site(url)
        if not host:
            return
        dados = self._ler()
        mapa = dados.setdefault("nunca", {})
        if valor:
            mapa[host] = True
        else:
            mapa.pop(host, None)
        self._gravar(dados)

    def nunca_guarda(self, url):
        return bool(self._ler().get("nunca", {}).get(host_do_site(url)))

    def mesma_senha(self, url, usuario, senha):
        """True se ja ha exatamente esta conta e senha guardadas."""
        contas = self._ler().get("senhas", {}).get(host_do_site(url)) or []
        for c in contas:
            if _decifrar(c.get("u", "")) == usuario \
                    and _decifrar(c.get("s", "")) == senha:
                return True
        return False

    # -- esquecer
    def apagar_tudo(self):
        """Apaga tudo o que foi guardado, de todos os sites."""
        try:
            os.remove(self.caminho)
        except FileNotFoundError:
            pass
        except OSError:
            log.exception("não consegui apagar as preferências dos sites")

    def esquecer_site(self, url):
        """Apaga campos, senhas e a recusa de guardar do endereco; a exibicao
        (do dominio) tambem volta ao padrao."""
        host = host_do_site(url)
        dados = self._ler()
        for chave in ("campos", "senhas", "nunca"):
            dados.get(chave, {}).pop(host, None)
        dados.get("exibicao", {}).pop(dominio_do_site(url), None)
        self._gravar(dados)

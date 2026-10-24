# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Consulta as Releases do GitHub para saber se ha versao nova. So le: nao
baixa nem instala nada. Sem dependencia de wxPython."""
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from telezapp import SITE, VERSAO, versao_valida

REPO = "reffehcsoibaf/TeleZapp"
URL_LANCAMENTOS = "https://api.github.com/repos/%s/releases?per_page=15" % REPO
URL_PAGINA = SITE + "/releases"


class ErroAtualizacao(Exception):
    """A consulta nao deu certo; o texto e dito a pessoa."""


@dataclass
class Lancamento:
    versao: str
    notas: str
    pagina: str
    pre: bool = False
    nome_zip: str = ""
    url_zip: str = ""
    url_hash: str = ""
    tamanho: int = 0
    # [(versao, texto das novidades)] de cada versao publicada depois da que
    # esta em uso, ate esta, da mais nova para a mais velha
    historico: list = field(default_factory=list)


def como_tupla(versao):
    """(ano, mes, dia, digito) de uma versao valida, senao None."""
    if not versao_valida(versao):
        return None
    return tuple(int(x) for x in versao.split("."))


def _arquivos(r, versao):
    """(nome, url do zip, url do hash, tamanho) dos arquivos da Release, se
    ela tem o zip e o .sha256 que o publicar.py monta."""
    achados = {}
    for a in r.get("assets") or []:
        if isinstance(a, dict):
            achados[str(a.get("name"))] = a
    # nome fixo; as primeiras Releases traziam a versao no nome
    for nome in ("TeleZapp.zip", "TeleZapp-%s.zip" % versao):
        zip_, hash_ = achados.get(nome), achados.get(nome + ".sha256")
        if zip_ and hash_:
            break
    else:
        return "", "", "", 0
    return (nome, str(zip_.get("browser_download_url") or ""),
            str(hash_.get("browser_download_url") or ""),
            int(zip_.get("size") or 0))


def novidades_do_corpo(corpo, versao):
    """O texto de `## Novidades da versao X` das notas da Release (sem o
    aviso, o como usar e o hash). Sem essa secao, as notas inteiras."""
    corpo = str(corpo or "").replace("\r\n", "\n").strip()
    achou = re.search(r"^##\s+Novidades da vers[ãa]o[^\n]*\n(.*?)(?=^##\s|\Z)",
                      corpo, re.S | re.M | re.I)
    texto = achou.group(1).strip() if achou else corpo
    return texto or "(sem texto de novidades)"


def mais_nova(dados, atual=VERSAO):
    """O lancamento de maior versao entre os da lista da API (rascunhos e
    tags que nao seguem ano.mes.dia.digito ficam de fora), ou None."""
    melhor = None
    for r in dados if isinstance(dados, list) else []:
        if not isinstance(r, dict) or r.get("draft"):
            continue
        versao = str(r.get("tag_name") or "").lstrip("vV")
        chave = como_tupla(versao)
        if chave is None:
            continue
        if melhor is None or chave > melhor[0]:
            melhor = (chave, Lancamento(
                versao, str(r.get("body") or "").strip(),
                str(r.get("html_url") or URL_PAGINA),
                bool(r.get("prerelease")), *_arquivos(r, versao)))
    if not melhor:
        return None
    lanc = melhor[1]
    velha = como_tupla(atual)
    vistos = {}
    for r in dados:
        if not isinstance(r, dict) or r.get("draft"):
            continue
        versao = str(r.get("tag_name") or "").lstrip("vV")
        chave = como_tupla(versao)
        if chave and velha and velha < chave <= melhor[0]:
            vistos[chave] = (versao, novidades_do_corpo(r.get("body"),
                                                         versao))
    lanc.historico = [vistos[k] for k in sorted(vistos, reverse=True)]
    return lanc


def e_mais_nova(lancamento, atual=VERSAO):
    nova, velha = como_tupla(lancamento.versao), como_tupla(atual)
    return nova is not None and velha is not None and nova > velha


def deve_avisar_ao_abrir(lancamento, ignorada):
    """Ao abrir o programa: avisa de uma versao nova a cada abertura, ate a
    pessoa atualizar ou marcar "Nao avisar mais nesta versao" (`ignorada` e
    a versao marcada). Uma versao mais nova que a ignorada volta a avisar."""
    return bool(lancamento) and e_mais_nova(lancamento) and \
        lancamento.versao != (ignorada or "")


def _buscar_json(url, tempo=10):
    pedido = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "TeleZapp/" + VERSAO})
    with urllib.request.urlopen(pedido, timeout=tempo) as r:
        return json.loads(r.read().decode("utf-8"))


def consultar(buscar=_buscar_json):
    """O lancamento mais novo publicado (ou None se ainda nao ha nenhum).
    ErroAtualizacao se nao der para consultar o GitHub."""
    try:
        return mais_nova(buscar(URL_LANCAMENTOS))
    except (urllib.error.URLError, OSError, ValueError):
        raise ErroAtualizacao(
            "Não consegui consultar o GitHub. Veja a conexão com a internet "
            "e tente de novo.")

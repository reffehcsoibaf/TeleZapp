# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Guia de uso e novidades: paginas HTML com a versao atual.

Os modelos ficam em telezapp/ajuda com marcas {{versao}} e {{site}}; ao abrir,
a pagina pronta e gravada na pasta temporaria do proprio app.
"""
import os

from telezapp import SITE, VERSAO

PASTA_MODELOS = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "ajuda")
PAGINAS = ("guia.html", "novidades.html")


def gerar(nome, pasta_destino):
    """Grava a pagina `nome` com a versao atual; devolve o caminho ou None
    se o modelo nao existir."""
    if nome not in PAGINAS:
        return None
    origem = os.path.join(PASTA_MODELOS, nome)
    if not os.path.isfile(origem):
        return None
    with open(origem, encoding="utf-8") as f:
        html = f.read()
    html = html.replace("{{versao}}", VERSAO).replace("{{site}}", SITE)
    os.makedirs(pasta_destino, exist_ok=True)
    destino = os.path.join(pasta_destino, nome)
    with open(destino, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    return destino

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Guia de uso e novidades, com a versao atual.

Os modelos ficam em telezapp/ajuda com marcas {{versao}} e {{site}}. O guia e
um texto dividido em assuntos, mostrado numa janela do programa; as novidades
sao uma pagina HTML, gravada pronta na pasta temporaria do proprio app.
"""
import os
import unicodedata

from telezapp import SITE, VERSAO

PASTA_MODELOS = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "ajuda")
PAGINAS = ("novidades.html",)
GUIA = "guia.txt"


def ler_assuntos(nome=GUIA):
    """Lista de (titulo, texto); no arquivo, "# Titulo" abre cada assunto."""
    assuntos = []
    with open(os.path.join(PASTA_MODELOS, nome), encoding="utf-8") as f:
        for linha in f:
            if linha.startswith("# "):
                assuntos.append((linha[2:].strip(), []))
            elif assuntos:
                assuntos[-1][1].append(linha.rstrip())
    return [(titulo, "\n".join(linhas).strip().replace(
        "{{versao}}", VERSAO).replace("{{site}}", SITE))
        for titulo, linhas in assuntos]


def _sem_acento(texto):
    """Minusculas e sem acentos, devolvendo tambem, para cada caractere do
    resultado, a posicao do caractere de origem (para achar o trecho no texto
    original mesmo quando um caractere vira varios)."""
    saida, origem = [], []
    for i, c in enumerate(texto):
        for d in unicodedata.normalize("NFKD", c):
            if not unicodedata.combining(d):
                saida.append(d.lower())
                origem.append(i)
    return "".join(saida), origem


def palavras(termo):
    return _sem_acento(termo)[0].split()


def pesquisar(assuntos, termo):
    """Posicoes dos assuntos (titulo ou texto) que tem TODAS as palavras do
    termo, em qualquer ordem, sem diferenciar maiusculas nem acentos. Termo
    vazio: todos."""
    ps = palavras(termo)
    if not ps:
        return list(range(len(assuntos)))
    achados = []
    for n, (titulo, texto) in enumerate(assuntos):
        base = _sem_acento(titulo + "\n" + texto)[0]
        if all(p in base for p in ps):
            achados.append(n)
    return achados


def primeiro_trecho(texto, termo):
    """(inicio, fim) no `texto` original da primeira ocorrencia da palavra
    mais longa do termo que aparece nele (as curtas, como "da", cairiam no
    meio de qualquer palavra), ou None."""
    base, origem = _sem_acento(texto)
    for p in sorted(palavras(termo), key=len, reverse=True):
        i = base.find(p)
        if i >= 0:
            return origem[i], origem[i + len(p) - 1] + 1
    return None


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

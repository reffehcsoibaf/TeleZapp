# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Guardar direto na pasta escolhida nas configuracoes. Sem wx."""
import os
import re

_PROIBIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVADOS = {"CON", "PRN", "AUX", "NUL"} | {
    "%s%d" % (p, n) for p in ("COM", "LPT") for n in range(1, 10)}


def nome_seguro(nome):
    """O nome vem de quem enviou o arquivo e aqui ninguem o confere numa
    janela: sem pasta no meio e so com o que o Windows aceita."""
    nome = _PROIBIDOS.sub("_", nome or "").strip(" .")
    if not nome:
        return "arquivo"
    if os.path.splitext(nome)[0].upper() in _RESERVADOS:
        return "_" + nome
    return nome


def caminho_livre(pasta, nome):
    """Caminho na pasta que nao sobrescreve nada: 'a.pdf', 'a (2).pdf'..."""
    nome = nome_seguro(nome)
    raiz, ext = os.path.splitext(nome)
    caminho, n = os.path.join(pasta, nome), 1
    while os.path.exists(caminho):
        n += 1
        caminho = os.path.join(pasta, "%s (%d)%s" % (raiz, n, ext))
    return caminho


def direto(pasta, guardar_direto, nome):
    """Onde guardar sem perguntar, ou "" se a janela deve abrir: a opcao esta
    desligada, nao ha pasta ou nao deu para usa-la."""
    if not guardar_direto or not pasta:
        return ""
    try:
        os.makedirs(pasta, exist_ok=True)
    except OSError:
        return ""
    return caminho_livre(pasta, nome)

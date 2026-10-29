# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Texto de uma localizacao recebida (WhatsApp e Telegram): o que a pessoa
escreveu, o nome e o endereco do lugar, as coordenadas e um link para abrir
no mapa. A mensagem so guarda texto, entao tudo vai nele."""


def link_do_mapa(latitude, longitude):
    return "https://www.google.com/maps?q=%.6f,%.6f" % (latitude, longitude)


def descrever(latitude=0.0, longitude=0.0, nome="", endereco="",
              ao_vivo=False, legenda=""):
    """'localização: Nome, Endereço', a legenda, as coordenadas e o link.
    Em tempo real: 'localização em tempo real'. Sem coordenadas (0, 0 e sem
    nome) so a palavra, como antes."""
    titulo = "localização em tempo real" if ao_vivo else "localização"
    lugar = ", ".join(p.strip() for p in (nome, endereco) if p and p.strip())
    linhas = [titulo + (": " + lugar if lugar else "")]
    if legenda and legenda.strip():
        linhas.append(legenda.strip())
    if latitude or longitude:
        linhas.append("coordenadas %.5f, %.5f" % (latitude, longitude))
        linhas.append(link_do_mapa(latitude, longitude))
    return "\n".join(linhas)

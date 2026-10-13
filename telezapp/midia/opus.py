# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Duracao de notas de voz Ogg/Opus lendo so o cabecalho e a ultima pagina."""


def duracao(dados):
    """Duracao em segundos de um Ogg/Opus (bytes)."""
    inicio = dados.find(b"OpusHead")
    pre_skip = 0
    if inicio >= 0 and len(dados) >= inicio + 12:
        pre_skip = int.from_bytes(dados[inicio + 10:inicio + 12], "little")
    ultimo = dados.rfind(b"OggS")
    if ultimo < 0 or len(dados) < ultimo + 14:
        raise ValueError("arquivo Ogg invalido")
    granule = int.from_bytes(dados[ultimo + 6:ultimo + 14], "little",
                             signed=True)
    if granule < 0:
        raise ValueError("posicao final do Ogg invalida")
    return max(0.0, (granule - pre_skip) / 48000.0)


def duracao_arquivo(caminho):
    with open(caminho, "rb") as f:
        return duracao(f.read())

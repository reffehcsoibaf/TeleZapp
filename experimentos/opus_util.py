# -*- coding: utf-8 -*-
"""Funcoes de apoio para audio e notas de voz (Ogg/Opus), sem FFmpeg."""
import math


def duracao_ogg_opus(dados):
    """Duracao em segundos de um arquivo Ogg/Opus, lendo so o cabecalho."""
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


def para_dbfs(valor):
    """Converte amplitude (0 a 1) em dBFS, com piso em -120."""
    return 20 * math.log10(max(float(valor), 1e-6))


def reamostrar(np, dados, sr_origem, sr_destino):
    """Reamostragem simples por interpolacao linear (suficiente para voz)."""
    if sr_origem == sr_destino:
        return dados
    n_destino = int(round(len(dados) * sr_destino / sr_origem))
    x_origem = np.linspace(0.0, 1.0, num=len(dados), endpoint=False)
    x_destino = np.linspace(0.0, 1.0, num=n_destino, endpoint=False)
    return np.interp(x_destino, x_origem, dados).astype("float32")

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Gera os sons de exemplo dos eventos do TeleZapp, todos sintetizados aqui
(nenhuma amostra de terceiros), em Ogg Vorbis estereo.

Cada som e curto (no maximo 2 segundos), comeca no primeiro instante do
arquivo (sem silencio antes, so uma subida de 2 ms contra estalos) e termina
em zero. Uso:

    venv\\Scripts\\python ferramentas\\gerar_sons.py [pasta de saida]

Sem argumento grava em telezapp/sons, o pacote de sons "TeleZapp" (Configuracoes,
Sons, Pacote de sons).
"""
import os
import sys

import numpy as np
import soundfile as sf

TAXA = 44100
PICO = 0.45          # suave: cerca de -7 dBFS
MAXIMO = 2.0         # segundos
NOTAS = {"C4": 261.63, "E4": 329.63, "G4": 392.00, "A4": 440.00,
         "C5": 523.25, "E5": 659.25, "G5": 783.99, "A5": 880.00,
         "C6": 1046.50, "E6": 1318.51, "G6": 1567.98}

# parciais (multiplo da frequencia, volume, rapidez do apagar) por timbre
TIMBRES = {
    "sino": ((1.0, 1.0, 5.0), (2.0, 0.30, 8.0), (3.0, 0.10, 12.0),
             (4.2, 0.04, 16.0)),
    "grave": ((1.0, 1.0, 4.0), (2.0, 0.22, 7.0), (3.0, 0.06, 10.0)),
}


def nota(freq, dur, timbre="sino"):
    """Uma nota: ataque de 2 ms, apagando como um sino macio."""
    n = int(TAXA * dur)
    t = np.arange(n) / TAXA
    onda = np.zeros(n)
    for mult, vol, rapidez in TIMBRES[timbre]:
        apagar = np.exp(-rapidez * t / dur * 1.0)
        onda += vol * np.sin(2 * np.pi * freq * mult * t) * apagar
    ataque = np.minimum(1.0, t / 0.002)
    return onda * ataque


def compor(notas, timbre="sino"):
    """notas: [(inicio_s, nome_da_nota, duracao_s, volume, pan -1..1)] ->
    array estereo (n, 2)."""
    fim = max(i + d for i, _, d, _, _ in notas)
    n = int(TAXA * (fim + 0.12))            # sobra para o eco
    esq, dir_ = np.zeros(n), np.zeros(n)
    for inicio, nome, dur, vol, pan in notas:
        som = nota(NOTAS[nome], dur, timbre) * vol
        k = int(TAXA * inicio)
        esq[k:k + len(som)] += som * (1.0 - max(0.0, pan) * 0.55)
        dir_[k:k + len(som)] += som * (1.0 + min(0.0, pan) * 0.55)
    # largura: o lado direito chega 5 ms depois e cada lado ganha ecos
    # curtos diferentes, tudo dentro da sobra do final
    atraso = int(TAXA * 0.005)
    dir_ = np.concatenate([np.zeros(atraso), dir_])[:n]
    for ms, g in ((31, 0.18), (67, 0.10)):
        d = int(TAXA * ms / 1000)
        esq[d:] += esq[:-d] * g
    for ms, g in ((43, 0.18), (83, 0.10)):
        d = int(TAXA * ms / 1000)
        dir_[d:] += dir_[:-d] * g
    saida = np.stack([esq, dir_], axis=1)
    saida = saida[:int(TAXA * MAXIMO)]
    saida *= PICO / max(np.abs(saida).max(), 1e-9)
    f = int(TAXA * 0.04)                    # termina em zero, sem estalo
    saida[-f:] *= np.linspace(1.0, 0.0, f)[:, None]
    return saida.astype(np.float32)


def sequencia(nomes, passo, dur, vol=1.0, pan=0.0, vai_e_volta=False):
    saida = []
    for k, nome in enumerate(nomes):
        p = pan * (1 if k % 2 == 0 else -1) if vai_e_volta else pan
        saida.append((k * passo, nome, dur, vol, p))
    return saida


# evento -> (notas, timbre)
SONS = {
    "nova": (sequencia(["E5", "A5"], 0.13, 0.42), "sino"),
    "nova_aberta": ([(0.0, "C6", 0.24, 0.8, 0.0)], "sino"),
    "nova_grupo": (sequencia(["G5", "E5"], 0.12, 0.38, 0.9, 0.25, True),
                   "sino"),
    "enviada": (sequencia(["C5", "G5"], 0.08, 0.30), "sino"),
    "erro": ([(0.0, "E4", 0.38, 1.0, 0.0), (0.2, "C4", 0.62, 1.0, 0.0)],
             "grave"),
    "conectado": (sequencia(["C5", "E5", "G5", "C6"], 0.10, 0.62), "sino"),
    "pronto": ([(0.0, "G5", 0.75, 0.9, -0.2), (0.0, "C6", 0.75, 0.7, 0.2),
                (0.14, "E6", 0.55, 0.5, 0.0)], "sino"),
    "atualizado": ([(0.0, "A5", 0.22, 0.8, 0.0)], "sino"),
    "toque": (sequencia(["E5", "G5", "E5", "G5"], 0.22, 0.32, 1.0, 0.2, True)
              + [(1.0 + k * 0.22, n, 0.32, 1.0, 0.2 if k % 2 == 0 else -0.2)
                 for k, n in enumerate(["E5", "G5", "E5", "G5"])], "sino"),
    "chamando": ([(0.0, "A4", 0.55, 0.9, -0.15), (0.0, "E5", 0.55, 0.6, 0.15),
                  (1.0, "A4", 0.55, 0.9, -0.15),
                  (1.0, "E5", 0.55, 0.6, 0.15)], "sino"),
    "desligada": (sequencia(["G5", "C5"], 0.14, 0.45), "sino"),
    "desconectada": (sequencia(["A5", "E5", "C5"], 0.12, 0.5, 0.9), "grave"),
    "reconectada": (sequencia(["C5", "G5"], 0.12, 0.45), "sino"),
    "falha_envio": ([(0.0, "G4", 0.30, 1.0, 0.0), (0.15, "E4", 0.45, 1.0, 0.0)],
                    "grave"),
    "download_pronto": (sequencia(["C6", "E6"], 0.09, 0.30, 0.85), "sino"),
    "tarefa_pronta": (sequencia(["C5", "E5", "G5"], 0.09, 0.45), "sino"),
    # dois toques descendentes e mais firmes: alguem chamou voce no grupo
    "mencao_ou_resposta": (sequencia(["E6", "C6"], 0.17, 0.5, 1.0, 0.25,
                                     True), "sino"),
    # um toque curto e brilhante, diferente do de mensagem nova
    "reacao_recebida": (sequencia(["E6", "G6"], 0.07, 0.26, 0.8, 0.3, True),
                        "sino"),
    # a gravacao so comeca depois do bipe (0,3 s): este e curto
    "gravando": (sequencia(["G5", "C6"], 0.05, 0.10, 0.9), "sino"),
    "gravacao_parada": (sequencia(["C6", "G5"], 0.07, 0.20, 0.9), "sino"),
    "voto_enquete": (sequencia(["G5", "C6", "E6"], 0.06, 0.24, 0.8, 0.2,
                               True), "sino"),
    "voto_enviado": (sequencia(["E5", "G5"], 0.06, 0.20, 0.9), "sino"),
    "escondido": (sequencia(["E5", "C5"], 0.10, 0.30, 0.9), "sino"),
    "voltou": (sequencia(["C5", "E5"], 0.10, 0.30, 0.9), "sino"),
}


def gerar(destino):
    os.makedirs(destino, exist_ok=True)
    caminhos = []
    for evento, (notas, timbre) in SONS.items():
        som = compor(notas, timbre)
        caminho = os.path.join(destino, evento + ".ogg")
        sf.write(caminho, som, TAXA, format="OGG", subtype="VORBIS")
        caminhos.append(caminho)
    return caminhos


def main():
    destino = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "telezapp", "sons")
    for c in gerar(destino):
        dados, taxa = sf.read(c)
        print("%-22s %.2f s, %d canais" % (os.path.basename(c),
                                          len(dados) / taxa, dados.shape[1]))


if __name__ == "__main__":
    main()

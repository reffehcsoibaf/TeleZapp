# -*- coding: utf-8 -*-
"""Mede o tamanho de uma pasta (usado no teste de empacotamento).

Uso: python medir_pasta.py <pasta> <arquivo-de-log>
"""
import os
import sys
import time


def log(logfile, msg):
    linha = time.strftime("%H:%M:%S") + " " + msg
    print(linha, flush=True)
    try:
        with open(logfile, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except OSError:
        pass


def main():
    if len(sys.argv) < 3:
        print("Uso: medir_pasta.py <pasta> <log>")
        return 2
    pasta, logfile = sys.argv[1], sys.argv[2]
    if not os.path.isdir(pasta):
        log(logfile, "pasta nao encontrada: " + pasta)
        return 1
    arquivos = []
    for raiz, _, nomes in os.walk(pasta):
        for nome in nomes:
            caminho = os.path.join(raiz, nome)
            try:
                arquivos.append((os.path.getsize(caminho),
                                 os.path.relpath(caminho, pasta)))
            except OSError:
                pass
    total = sum(t for t, _ in arquivos)
    log(logfile, "tamanho total: %.1f MB em %d arquivos" % (
        total / 1048576, len(arquivos)))
    maiores = sorted(arquivos, reverse=True)[:12]
    log(logfile, "os 12 maiores arquivos:")
    for tamanho, rel in maiores:
        log(logfile, "  %7.1f MB  %s" % (tamanho / 1048576, rel))
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""Ajudantes do teste de arquivos grandes (usados pelos dois servicos)."""
import hashlib
import os

BASE = os.path.dirname(os.path.abspath(__file__))
ARQ_CONF = os.path.join(BASE, "configuracao-arquivos-grandes.txt")
PASTA = os.path.join(BASE, "arquivos-grandes")
PADRAO_MB = 20
MINIMO_MB = 1
MAXIMO_MB = 500

MODELO = (
    "# Tamanho do arquivo de teste, em megabytes (de 1 a 500).\n"
    "# Comece com 20. Depois do resultado, tente 100.\n"
    "# Salve com Control S antes de rodar o teste de novo.\n"
    "TAMANHO_MB=%d\n" % PADRAO_MB)


def ler_tamanho_mb(log):
    """Le TAMANHO_MB do arquivo de configuracao (cria com o padrao se faltar)."""
    if not os.path.isfile(ARQ_CONF):
        with open(ARQ_CONF, "w", encoding="utf-8") as f:
            f.write(MODELO)
        log("configuracao criada com %d MB (edite configuracao-arquivos-grandes"
            ".txt para mudar)" % PADRAO_MB)
    mb = PADRAO_MB
    try:
        with open(ARQ_CONF, encoding="utf-8-sig") as f:
            for linha in f:
                linha = linha.strip()
                if linha.upper().startswith("TAMANHO_MB="):
                    mb = int(linha.split("=", 1)[1].strip())
    except (OSError, ValueError):
        log("aviso: nao consegui ler TAMANHO_MB; usando %d" % PADRAO_MB)
        mb = PADRAO_MB
    return max(MINIMO_MB, min(MAXIMO_MB, mb))


def gerar_arquivo(nome, mb):
    """Cria um arquivo de dados aleatorios (nao comprimiveis) com mb MB."""
    os.makedirs(PASTA, exist_ok=True)
    caminho = os.path.join(PASTA, nome)
    bloco = 1024 * 1024
    with open(caminho, "wb") as f:
        for _ in range(mb):
            f.write(os.urandom(bloco))
    return caminho


def sha256_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while True:
            parte = f.read(1024 * 1024)
            if not parte:
                break
            h.update(parte)
    return h.hexdigest()


def velocidade(nbytes, segundos):
    """Texto 'x,y MB/s' (com virgula decimal)."""
    if segundos <= 0:
        return "-"
    return ("%.2f MB/s" % (nbytes / 1048576 / segundos)).replace(".", ",")


def segundos_txt(s):
    return ("%.1f s" % s).replace(".", ",")


def limpar():
    """Apaga a pasta de arquivos de teste."""
    import shutil
    shutil.rmtree(PASTA, ignore_errors=True)

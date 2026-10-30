# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Compacta a pasta de logs para a pessoa mandar ao suporte. Sem wx.

O .zip fica fora de `temp`, que e apagada ao abrir e fechar o programa: a pessoa
pode copiar agora e colar depois. So o ultimo fica guardado.
"""
import logging
import os
import time
import zipfile

from telezapp import VERSAO, config

log = logging.getLogger("telezapp.exportar_logs")

PASTA = "logs-exportados"


def compactar(pasta_logs=None, destino=None, agora=None):
    """Cria o .zip e devolve o caminho. Um arquivo que nao der para ler fica de
    fora (fica registrado no proprio zip). Levanta OSError se nao houver como
    gravar."""
    pasta_logs = pasta_logs or config.pasta("logs")
    destino = destino or config.pasta(PASTA)
    for manipulador in logging.getLogger("telezapp").handlers:
        manipulador.flush()
    for antigo in os.listdir(destino):
        if antigo.lower().endswith(".zip"):
            try:
                os.remove(os.path.join(destino, antigo))
            except OSError:
                log.info("não consegui apagar um zip antigo de logs")
    instante = time.strftime("%Y-%m-%d-%H%M", time.localtime(agora))
    caminho = os.path.join(destino, "TeleZapp-logs-%s-%s.zip" % (
        VERSAO, instante))
    ignorados = []
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        for raiz, _pastas, nomes in os.walk(pasta_logs):
            for nome in sorted(nomes):
                arquivo = os.path.join(raiz, nome)
                relativo = os.path.relpath(arquivo, pasta_logs)
                try:
                    z.write(arquivo, relativo)
                except OSError:
                    ignorados.append(relativo)
        if ignorados:
            z.writestr("arquivos-que-nao-foram.txt", "\n".join(ignorados))
    return caminho


def tamanho_em_texto(bytes_):
    if bytes_ >= 1024 * 1024:
        return ("%.1f MB" % (bytes_ / (1024 * 1024))).replace(".", ",")
    return "%d KB" % max(1, round(bytes_ / 1024))

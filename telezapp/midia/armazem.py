# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Onde as midias baixadas ficam: so dentro da pasta de dados do TeleZapp
(%APPDATA%\\TeleZapp\\midias\\<conta>\\<conversa>), nunca espalhadas pelo
sistema."""
import hashlib
import mimetypes
import os
import re
import shutil

from telezapp import config
from telezapp.nucleo import modelos as m

EXTENSAO_PADRAO = {m.FOTO: ".jpg", m.VIDEO: ".mp4", m.VOZ: ".ogg",
                   m.AUDIO: ".ogg", m.DOCUMENTO: ".bin",
                   m.FIGURINHA: ".webp"}
BAIXAVEIS = tuple(EXTENSAO_PADRAO)


def _limpo(texto, limite=60):
    """Nome seguro para o Windows: sem caracteres proibidos nem pontos ou
    espacos no fim."""
    t = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", texto or "").strip(" .")
    return t[:limite].rstrip(" .")


def pasta_midias():
    return config.pasta("midias")


def pasta_da_conversa(conta_id, conversa_id):
    base = os.path.join(pasta_midias(), _limpo(conta_id, 80))
    # o id da conversa pode ser longo ou ter caracteres proibidos
    sub = hashlib.sha1(conversa_id.encode("utf-8")).hexdigest()[:12]
    pasta = os.path.join(base, sub)
    os.makedirs(pasta, exist_ok=True)
    return pasta


def caminho_base(msg):
    """Caminho do arquivo, sem a extensao quando o nome nao a traz."""
    pasta = pasta_da_conversa(msg.conta_id, msg.conversa_id)
    nome = _limpo(msg.nome_arquivo)
    ident = _limpo(msg.id, 40) or "msg"
    return os.path.join(pasta, "%s_%s" % (ident, nome) if nome else ident)


def extensao(mime, tipo, nome=""):
    """Extensao (com ponto) pelo nome do arquivo, pelo tipo MIME ou pelo
    tipo da mensagem."""
    ext = os.path.splitext(nome or "")[1].lower()
    if ext and len(ext) <= 8:
        return ext
    mime = (mime or "").split(";")[0].strip().lower()
    if mime == "audio/ogg" or "opus" in mime:
        return ".ogg"
    if mime == "image/jpeg":
        return ".jpg"
    ext = mimetypes.guess_extension(mime) if mime else None
    return ext or EXTENSAO_PADRAO.get(tipo, ".bin")


def com_extensao(base, ext):
    return base if os.path.splitext(base)[1].lower() == ext else base + ext


def guardar_enviada(msg, origem, mover=False):
    """Deixa uma copia (ou move, se for temporario) do arquivo enviado na
    pasta da conversa, para a pessoa poder abri-lo depois sem baixar."""
    destino = com_extensao(caminho_base(msg),
                           os.path.splitext(origem)[1].lower() or ".bin")
    if os.path.abspath(origem) != os.path.abspath(destino):
        if mover:
            shutil.move(origem, destino)
        else:
            shutil.copy2(origem, destino)
    return destino


def tamanho_da_pasta(conta_id=None):
    total = 0
    raiz = pasta_midias() if conta_id is None else os.path.join(
        pasta_midias(), _limpo(conta_id, 80))
    for pasta, _, arquivos in os.walk(raiz):
        for a in arquivos:
            try:
                total += os.path.getsize(os.path.join(pasta, a))
            except OSError:
                pass
    return total


def apagar_conta(conta_id):
    shutil.rmtree(os.path.join(pasta_midias(), _limpo(conta_id, 80)),
                  ignore_errors=True)

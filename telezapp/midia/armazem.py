# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Onde as midias baixadas ficam: dentro da pasta da conta
(<pasta da conta>\\midias\\<conversa>; ver config.pasta_da_conta), nunca
espalhadas pelo sistema."""
import hashlib
import mimetypes
import os
import re
import shutil
import time
import uuid

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


def pasta_midias(conta_id):
    """A pasta de midias da conta: na pasta dela (com separacao) ou na
    pasta de midias do layout antigo (a personalizada, se escolhida;
    senao, <dados>\\midias; a pasta da conta fica dentro)."""
    if not config.contas_separadas():
        return os.path.join(config.pasta_do_layout_antigo(), "midias")
    return os.path.join(config.pasta_da_conta(conta_id), "midias")


def pasta_da_conversa(conta_id, conversa_id):
    base = pasta_midias(conta_id)
    # o id da conversa pode ser longo ou ter caracteres proibidos
    sub = hashlib.sha1(conversa_id.encode("utf-8")).hexdigest()[:12]
    pasta = os.path.join(base, sub)
    os.makedirs(pasta, exist_ok=True)
    return pasta


def apagar_conversa(conta_id, conversa_id):
    """Apaga a pasta de midias da conversa (sem cria-la)."""
    sub = hashlib.sha1(conversa_id.encode("utf-8")).hexdigest()[:12]
    shutil.rmtree(os.path.join(pasta_midias(conta_id), sub),
                  ignore_errors=True)


def caminho_base(msg):
    """Caminho do arquivo, sem a extensao quando o nome nao a traz."""
    pasta = pasta_da_conversa(msg.conta_id, msg.conversa_id)
    nome = _limpo(msg.nome_arquivo)
    ident = _limpo(msg.id, 40) or "msg"
    return os.path.join(pasta, "%s_%s" % (ident, nome) if nome else ident)


def nome_para_copiar(msg, caminho):
    """O nome que a midia tem ao ser colada: o que quem enviou deu ao arquivo,
    sem o codigo da mensagem que o armazem poe na frente ("<codigo>_nome"). Sem
    nome (foto, voz...), o tipo e a data e hora, ex.: "foto 2026-11-19
    14-30-05.jpg"."""
    nome = os.path.basename(caminho)
    prefixo = "%s_" % (_limpo(msg.id, 40) or "msg")
    if nome.startswith(prefixo) and len(nome) > len(prefixo):
        return nome[len(prefixo):]
    quando = ""
    try:
        quando = " " + time.strftime("%Y-%m-%d %H-%M-%S",
                                     time.localtime(float(msg.data)))
    except (TypeError, ValueError, OverflowError, OSError):
        pass
    return m.NOMES_TIPOS.get(msg.tipo, "arquivo") + quando + \
        os.path.splitext(nome)[1]


def copia_para_colar(msg, caminho):
    """Caminho de uma copia (elo fisico quando da, para nao duplicar um
    video grande) com o nome limpo, na pasta temporaria, que o programa apaga
    ao abrir e ao fechar. Se nao der, devolve o proprio arquivo."""
    from telezapp.nucleo import pasta_salvar
    try:
        base = os.path.join(config.pasta_dados(), "temp", "copias")
        shutil.rmtree(base, ignore_errors=True)    # as copias antigas
        pasta = os.path.join(base, uuid.uuid4().hex[:8])
        os.makedirs(pasta, exist_ok=True)
        destino = os.path.join(
            pasta, pasta_salvar.nome_seguro(nome_para_copiar(msg, caminho)))
        try:
            os.link(caminho, destino)
        except OSError:
            shutil.copy2(caminho, destino)
        return destino
    except OSError:
        return caminho


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
    """Quantos bytes de midias a conta tem (ou todas as contas juntas)."""
    total = 0
    if conta_id:
        raizes = [pasta_midias(conta_id)]
    elif not config.contas_separadas():
        raizes = [pasta_midias("")]    # a pasta comum, uma vez so
    else:
        raizes = [os.path.join(p, "midias")
                  for p in config.pastas_das_contas()]
    for raiz in raizes:
        for pasta, _, arquivos in os.walk(raiz):
            for a in arquivos:
                try:
                    total += os.path.getsize(os.path.join(pasta, a))
                except OSError:
                    pass
    return total


def apagar_conta(conta_id):
    """Apaga as midias da conta (sem tocar nas das outras)."""
    if not config.contas_separadas():
        shutil.rmtree(os.path.join(pasta_midias(conta_id),
                                   _limpo(conta_id, 80)), ignore_errors=True)
        return
    shutil.rmtree(pasta_midias(conta_id), ignore_errors=True)

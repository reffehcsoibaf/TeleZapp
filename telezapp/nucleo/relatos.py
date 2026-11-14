# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Envia um relato (Ajuda, Feedback) ao mesmo recebedor do formulario da
pagina, sem navegador; veja relatos/LEIAME.md. Sem wx."""
import json
import logging
import os
import re
import urllib.error
import urllib.request
import uuid

from telezapp import VERSAO, config
from telezapp.nucleo import modelos
from telezapp.nucleo.atualizacao import abrir_url

log = logging.getLogger("telezapp.relatos")

ENDERECO = "https://telezapp.fabioscheffer.workers.dev/relato"
# o recebedor recusa mais de 5 MB; a sobra cobre o que o envio acrescenta
LIMITE_LOGS = 4800 * 1024
# (nome, quanto do fim do arquivo cabe); a queda nativa vem antes por ser curta
# e explicar um fechamento do programa
ARQUIVOS = (("falha-nativa.log", 512 * 1024), ("telezapp.log", LIMITE_LOGS),
            ("telezapp.log.1", LIMITE_LOGS))
SEM_DESCRICAO = "(sem descrição: só os logs)"


class ErroRelato(Exception):
    """O texto e dito a pessoa."""


VIAS = (("telegram", "Telegram"), ("whatsapp", "WhatsApp"),
        ("email", "E-mail"))
DICAS = {"telegram": "Contato: seu usuário do Telegram (como @fulano) ou o "
                     "número do telefone com DDD",
         "whatsapp": "Contato: seu número de WhatsApp com DDD",
         "email": "Contato: seu endereço de e-mail"}


def via_de(contato):
    """A via que combina com um contato ja escrito (de antes da escolha)."""
    t = (contato or "").strip()
    if "@" in t[1:]:
        return "email"
    if sum(c.isdigit() for c in t) >= 8:
        return "whatsapp"
    return "telegram"


def contato_de(via, valor):
    """(texto para o relato, erro). O texto leva a via na frente, como
    "WhatsApp: +5521977425383"; `erro` e a frase para a pessoa, ou vazio."""
    t = (valor or "").strip()
    nome = dict(VIAS).get(via, via)
    if via == "email":
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", t):
            return "", "Escreva o e-mail completo, como nome@exemplo.com."
        return "%s: %s" % (nome, t), ""
    if via == "whatsapp" or (via == "telegram" and not re.search(
            r"[A-Za-z_]", t) and t):
        fone = modelos.normalizar_telefone(t)
        if fone is None:
            return "", "Escreva o número com DDD, como 21 99999-8888."
        return "%s: %s" % (nome, fone), ""
    usuario = t[1:] if t.startswith("@") else t
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", usuario):
        return "", ("Escreva o usuário do Telegram, como @fulano (de 5 a 32 "
                    "letras, números ou _), ou o número com DDD.")
    return "%s: @%s" % (nome, usuario), ""


def falta(contato, descricao, com_logs):
    """O campo obrigatorio vazio, ou "". Com os logs a descricao e opcional."""
    if not contato.strip():
        return "contato"
    if not descricao.strip() and not com_logs:
        return "descricao"
    return ""


def _fim_do_arquivo(caminho, maximo):
    with open(caminho, "rb") as f:
        tamanho = os.fstat(f.fileno()).st_size
        if tamanho <= maximo:
            return f.read()
        f.seek(tamanho - maximo)
        dados = f.read()
    # a primeira linha veio cortada
    return dados[dados.find(b"\n") + 1:]


def juntar_logs(pasta=None, limite=LIMITE_LOGS):
    """[(nome, bytes)] dos logs que cabem no limite, sem os arquivos vazios."""
    pasta = pasta or config.pasta("logs")
    for manipulador in logging.getLogger("telezapp").handlers:
        manipulador.flush()
    logs = []
    for nome, maximo in ARQUIVOS:
        if limite <= 0:
            break
        try:
            dados = _fim_do_arquivo(os.path.join(pasta, nome),
                                    min(maximo, limite))
        except OSError:
            continue
        if dados:
            logs.append((nome, dados))
            limite -= len(dados)
    return logs


def corpo_do_envio(campos, logs, fronteira):
    """O corpo multipart/form-data, o que o formulario da pagina manda."""
    partes = []
    for nome, valor in campos.items():
        partes.append(('--%s\r\nContent-Disposition: form-data; name="%s"'
                       '\r\n\r\n%s\r\n' % (fronteira, nome, valor))
                      .encode("utf-8"))
    for nome, dados in logs:
        partes.append(('--%s\r\nContent-Disposition: form-data; name="log"; '
                       'filename="%s"\r\nContent-Type: text/plain\r\n\r\n' % (
                           fronteira, nome)).encode("utf-8"))
        partes.append(dados + b"\r\n")
    partes.append(("--%s--\r\n" % fronteira).encode("utf-8"))
    return b"".join(partes)


def enviar(tipo, nome, contato, descricao, quando, com_logs, abrir=abrir_url,
           pasta_logs=None):
    """Manda o relato. ErroRelato com o motivo, se nao der."""
    logs = juntar_logs(pasta_logs) if com_logs else []
    if not descricao.strip() and not logs:
        raise ErroRelato("Não achei logs para enviar. Escreva a descrição.")
    campos = {"tipo": tipo, "nome": nome, "contato": contato,
              "descricao": descricao.strip() or SEM_DESCRICAO,
              "quando": quando, "versao": VERSAO}
    if logs:
        campos["consentimento"] = "sim"
    fronteira = "telezapp" + uuid.uuid4().hex
    pedido = urllib.request.Request(
        ENDERECO, data=corpo_do_envio(campos, logs, fronteira), headers={
            "Content-Type": "multipart/form-data; boundary=" + fronteira,
            "User-Agent": "TeleZapp/" + VERSAO})
    try:
        with abrir(pedido, 60) as r:
            r.read()
    except urllib.error.HTTPError as e:
        log.warning("relato recusado: HTTP %d", e.code)
        try:
            motivo = json.loads(e.read().decode("utf-8")).get("erro")
        except (OSError, ValueError, AttributeError):
            motivo = ""
        raise ErroRelato(motivo or "O envio foi recusado (erro %d)." % e.code)
    except OSError as e:
        log.warning("relato não enviado: %s", type(e).__name__)
        raise ErroRelato("Não consegui enviar agora. Confira a internet e "
                         "tente de novo.")

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Salvar o conteudo de uma conversa num .zip: o texto de todas as mensagens
guardadas neste computador (conversa.txt) e as midias ja baixadas (pasta
midias). Sem wx."""
import os
import re
import time
import zipfile

from telezapp.nucleo import modelos as m

NOME_TEXTO = "conversa.txt"
PASTA_MIDIAS = "midias"


def nome_seguro(texto, padrao="conversa"):
    """Nome de arquivo valido no Windows."""
    texto = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", texto or "").strip(" .")
    return texto[:80] or padrao


def nome_sugerido(conv):
    return "Conversa com %s.zip" % nome_seguro(conv.nome, "conversa")


def _quando(ts):
    return time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(ts)) \
        if ts else "sem data"


def linha(msg, arquivo="", autor=None):
    """'[18/10/2026 14:03:00] Ana: foto, legenda: oi (midias/xxx.jpg)'. Texto
    de varias linhas segue com recuo."""
    if msg.tipo == m.TEXTO and not m.extras_de(msg)["apagada"]:
        corpo = msg.texto
    else:
        corpo = m.conteudo(msg, com_estado=False)
    if arquivo:
        corpo += " (%s)" % arquivo
    corpo = corpo.replace("\r\n", "\n").replace("\n", "\n    ")
    return "[%s] %s: %s" % (_quando(msg.data),
                            autor or m.quem_enviou(msg), corpo)


def gravar_zip(caminho, conv, mensagens, caminho_da_midia, progresso=None,
               nome_do_remetente=None):
    """Grava o .zip. `mensagens`: da mais antiga para a mais nova;
    `caminho_da_midia(msg)`: arquivo baixado da mensagem, ou None;
    `progresso(feitas, total)` e chamado de vez em quando;
    `nome_do_remetente(msg)`: nome conhecido de quem enviou, se a mensagem
    nao traz o autor (ver `modelos.quem_enviou`). Devolve
    (n_mensagens, n_midias). Em erro apaga o arquivo parcial e deixa a
    excecao subir."""
    linhas, n_midias = [], 0
    try:
        with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED,
                             allowZip64=True) as z:
            for i, msg in enumerate(mensagens, 1):
                arquivo = ""
                origem = caminho_da_midia(msg) \
                    if msg.tipo != m.TEXTO else None
                if origem and os.path.isfile(origem):
                    base = nome_seguro(msg.nome_arquivo or
                                       os.path.basename(origem), "midia")
                    arquivo = "%s/%s_%s_%s" % (
                        PASTA_MIDIAS,
                        time.strftime("%Y%m%d_%H%M%S",
                                      time.localtime(msg.data or 0)),
                        nome_seguro(msg.id, "x"), base)
                    z.write(origem, arquivo)
                    n_midias += 1
                linhas.append(linha(msg, arquivo, m.quem_enviou(
                    msg, conv, nome_do_remetente)))
                if progresso and i % 50 == 0:
                    progresso(i, len(mensagens))
            cabecalho = "Conversa com %s (%s)\nSalva em %s\n%d mensagens, " \
                "%d mídias\n\n" % (
                    conv.nome, m.SERVICOS.get(conv.servico, conv.servico),
                    _quando(time.time()), len(mensagens), n_midias)
            z.writestr(NOME_TEXTO, (cabecalho + "\n".join(linhas) +
                                    "\n").encode("utf-8-sig"))
    except BaseException:
        try:
            os.remove(caminho)
        except OSError:
            pass
        raise
    return len(mensagens), n_midias

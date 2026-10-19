# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Detalhes de uma conversa: contagens por tipo de conteudo, espaco usado e a
lista de midias com filtro. Sem wx."""
import os
import re

from telezapp.nucleo import modelos as m

# (chave, rotulo no plural) na ordem em que o filtro oferece
TIPOS_DE_MIDIA = (
    ("foto", "Fotos"), ("video", "Vídeos"), ("link", "Links"),
    ("documento", "Documentos"), ("figurinha", "Figurinhas"),
    ("contato", "Contatos"), ("voz", "Mensagens de voz"),
    ("audio", "Áudios"))
NOMES_DE_MIDIA = dict(TIPOS_DE_MIDIA)
TODAS = "todas"

_POR_TIPO = {m.FOTO: "foto", m.VIDEO: "video", m.DOCUMENTO: "documento",
             m.FIGURINHA: "figurinha", m.VOZ: "voz", m.AUDIO: "audio"}
# na ordem do armazem: so estes tipos viram arquivo baixado
BAIXAVEIS = ("foto", "video", "documento", "figurinha", "voz", "audio")
BAIXAVEIS_TIPOS = (m.FOTO, m.VIDEO, m.DOCUMENTO, m.FIGURINHA, m.VOZ, m.AUDIO)


def e_contato(msg):
    return msg.tipo == m.OUTRO and bool(
        re.match(r"(contato:|\d+ contatos)", msg.texto or ""))


def classes(msg):
    """Chaves de TIPOS_DE_MIDIA a que a mensagem pertence (uma foto com um
    link na legenda e foto e link)."""
    achadas = []
    if m.extras_de(msg)["apagada"]:
        return achadas
    chave = _POR_TIPO.get(msg.tipo)
    if chave:
        achadas.append(chave)
    if e_contato(msg):
        achadas.append("contato")
    if m.tem_links(msg):
        achadas.append("link")
    return achadas


def midias(mensagens, filtro=TODAS):
    """As mensagens que tem algum tipo de midia (ou o tipo `filtro`), da mais
    nova para a mais antiga."""
    itens = [x for x in mensagens if (
        classes(x) if filtro == TODAS else filtro in classes(x))]
    return sorted(itens, key=lambda x: (x.data, x.id), reverse=True)


def _tamanho(caminho):
    """Tamanho do arquivo no disco, ou None se ele nao esta mais la."""
    try:
        return os.path.getsize(caminho)
    except OSError:
        return None


def estatisticas(mensagens, registros_de_midia):
    """Contagens da conversa.

    mensagens: [Mensagem]; registros_de_midia: linhas de banco.midias
    ((conversa_id, mensagem_id, tipo, caminho, tamanho, data))."""
    por_tipo = {k: 0 for k, _ in TIPOS_DE_MIDIA}
    for x in mensagens:
        for k in classes(x):
            por_tipo[k] += 1
    baixadas = {k: [0, 0] for k in BAIXAVEIS}
    chaves = {x.id: classes(x) for x in mensagens}
    for _, mid, tipo, caminho, tamanho, _d in registros_de_midia:
        real = _tamanho(caminho)
        if real is None:
            continue                          # arquivo que sumiu do disco
        k = next((c for c in chaves.get(mid, []) if c in baixadas),
                 _POR_TIPO.get(tipo))
        if k in baixadas:
            baixadas[k][0] += 1
            baixadas[k][1] += real
    texto = sum(len((x.texto or "").encode("utf-8")) for x in mensagens)
    return {"mensagens": len(mensagens), "por_tipo": por_tipo,
            "baixadas": baixadas,
            "bytes_midias": sum(b for _, b in baixadas.values()),
            "bytes_texto": texto}


def linhas_de_uso(est):
    """Texto do que a conversa guarda: mensagens, midias por tipo e espaco."""
    n = est["mensagens"]
    linhas = ["Mensagens guardadas: %d." % n]
    for chave, rotulo in TIPOS_DE_MIDIA:
        q = est["por_tipo"].get(chave, 0)
        if not q:
            continue
        linha = "%s: %d" % (rotulo, q)
        if chave in est["baixadas"] and est["baixadas"][chave][0]:
            b = est["baixadas"][chave]
            linha += " (%d baixad%s, %s)" % (
                b[0], "a" if b[0] == 1 else "as", m.tamanho_legivel(b[1]))
        linhas.append(linha + ".")
    total = est["bytes_midias"] + est["bytes_texto"]
    linhas.append("Espaço no TeleZapp: %s (mídias baixadas %s, texto %s)." % (
        m.tamanho_legivel(total), m.tamanho_legivel(est["bytes_midias"]),
        m.tamanho_legivel(est["bytes_texto"])))
    return linhas


def rotulo_do_item(msg):
    """Uma linha da lista de midias: quem, quando e o que e."""
    return m.formatar(msg, m.ESTILO_AUTOR_PRIMEIRO)

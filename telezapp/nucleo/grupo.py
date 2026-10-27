# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Textos e arquivos das ferramentas de grupo (pedidos de entrada, foto e
convite com QR). Sem wx, para testar em qualquer sistema; quem fala com o
servico sao os provedores."""
import io
import re
import time


def rotulo_do_pedido(p):
    """A linha de um pedido de entrada na lista: nome, telefone e quando."""
    partes = [p.get("nome") or p.get("telefone") or "Pessoa sem nome"]
    if p.get("telefone") and p["telefone"] != partes[0]:
        partes.append(p["telefone"])
    if p.get("quando"):
        partes.append("pediu em " + time.strftime(
            "%d/%m/%Y %H:%M", time.localtime(p["quando"])))
    return ", ".join(partes)


def resumo_dos_pedidos(n):
    if n == 0:
        return "Nenhum pedido de entrada esperando."
    return "%d pedido%s de entrada esperando." % (n, "" if n == 1 else "s")


def png_do_qr(texto, escala=10):
    """Bytes de um PNG com o QR Code do texto (preto sobre branco)."""
    import segno
    destino = io.BytesIO()
    segno.make_qr(texto, error="m").save(destino, kind="png", scale=escala,
                                         border=4)
    return destino.getvalue()


def extensao_da_imagem(dados):
    if dados[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return ".webp"
    return ".jpg"


def codigo_do_convite(texto):
    """O codigo de um link chat.whatsapp.com/CODIGO (ou o proprio codigo);
    "" se nao parece um convite."""
    texto = (texto or "").strip()
    achado = re.search(r"chat\.whatsapp\.com/(?:invite/)?([A-Za-z0-9]{10,64})",
                       texto)
    if achado:
        return achado.group(1)
    return texto if re.fullmatch(r"[A-Za-z0-9]{10,64}", texto) else ""


RE_CONVITE_WHATSAPP = re.compile(
    r"chat\.whatsapp\.com/(?:invite/)?([A-Za-z0-9]{20,24})")
RE_CANAL_WHATSAPP = re.compile(
    r"whatsapp\.com/channel/([A-Za-z0-9_-]{10,64})")


def entradas_de_links(texto, vistos=None):
    """Acoes "entrar" dos links de convite no texto: grupo ou comunidade
    (chat.whatsapp.com/CODIGO) e canal (whatsapp.com/channel/CODIGO).
    `vistos`: conjunto de codigos que ja tem botao (e recebe os novos)."""
    vistos = set() if vistos is None else vistos
    entradas = []
    for codigo in RE_CONVITE_WHATSAPP.findall(texto or ""):
        if codigo not in vistos:
            vistos.add(codigo)
            entradas.append({"tipo": "entrar", "rotulo": "Entrar no grupo "
                             "(link de convite)", "codigo": codigo})
    for codigo in RE_CANAL_WHATSAPP.findall(texto or ""):
        if codigo not in vistos:
            vistos.add(codigo)
            entradas.append({"tipo": "entrar", "modo": "canal",
                             "rotulo": "Seguir o canal (link)",
                             "codigo": codigo})
    return entradas


def acao_do_link(texto):
    """A acao "entrar" de um link colado: grupo ou comunidade
    (chat.whatsapp.com/CODIGO) ou canal (whatsapp.com/channel/CODIGO); None
    se nao parece um convite."""
    achado = re.search(r"whatsapp\.com/channel/([A-Za-z0-9_-]{10,64})",
                       texto or "")
    if achado:
        return {"codigo": achado.group(1), "modo": "canal"}
    codigo = codigo_do_convite(texto)
    return {"codigo": codigo} if codigo else None

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Enviar contatos numa conversa: quem pode ser enviado e o cartao. Sem wx."""
from telezapp.nucleo import modelos as m


def opcoes(contatos):
    """[(nome, telefone)] da agenda ([(conta_id, id, nome, telefone)]), por
    nome e sem repetir telefone. Sem telefone nao ha o que enviar."""
    achados, vistos = [], set()
    for _, _, nome, telefone in contatos:
        tel = m.normalizar_telefone(telefone)
        if nome and tel and tel not in vistos:
            vistos.add(tel)
            achados.append((nome, tel))
    return sorted(achados, key=lambda c: c[0].casefold())


def filtrar(itens, busca):
    """Os (nome, telefone) que casam com o nome ou os digitos buscados."""
    busca = (busca or "").strip()
    if not busca:
        return list(itens)
    digitos = "".join(ch for ch in busca if ch.isdigit())
    return [c for c in itens if m.casa_busca(c[0], busca)
            or (digitos and digitos in c[1])]


def _escapar(texto):
    """Valor de vCard: sem quebra de linha e com os separadores protegidos."""
    texto = " ".join((texto or "").split())
    for ch in ("\\", ";", ","):
        texto = texto.replace(ch, "\\" + ch)
    return texto


def vcard(nome, telefone):
    """O cartao de um contato. waid= e o que faz o WhatsApp oferecer a conversa
    com a pessoa."""
    digitos = "".join(ch for ch in telefone if ch.isdigit())
    valor = _escapar(nome)
    return ("BEGIN:VCARD\nVERSION:3.0\nN:;%s;;;\nFN:%s\n"
            "TEL;type=CELL;waid=%s:+%s\nEND:VCARD" % (
                valor, valor, digitos, digitos))

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Nova mensagem: para quem enviar e por qual conta. Sem wx.

O destino digitado pode ser o nome de um contato ou de uma conversa, um
telefone com DDD ou um @usuario (Telegram). Contatos e conversas ja
conhecidos se resolvem aqui; telefone e @usuario dependem do servico.
"""
from telezapp.nucleo import modelos as m

NOME, TELEFONE, USUARIO = "nome", "telefone", "usuario"


def tipo_de_destino(texto):
    """nome, telefone ou usuario, pelo que foi digitado."""
    texto = (texto or "").strip()
    if texto.startswith("@") and len(texto) > 1:
        return USUARIO
    if m.normalizar_telefone(texto) and not any(
            c.isalpha() for c in texto):
        return TELEFONE
    return NOME


def candidatos(busca, contatos, conversas):
    """[(conversa_id, nome, telefone)] de contatos e conversas com pessoas
    (nao grupos nem canais) cujo nome (ou telefone) casa com a busca, sem
    repetir. Busca vazia traz todos. Os contatos vem primeiro.

    contatos: [(conta_id, id, nome, telefone)] ja filtrados pela conta;
    conversas: [Conversa] da conta."""
    achados, vistos = [], set()
    busca = (busca or "").strip()
    digitos = "".join(ch for ch in busca if ch.isdigit())
    for _, id_, nome, telefone in contatos:
        if id_ not in vistos and (m.casa_busca(nome, busca) or (
                digitos and telefone and digitos in telefone)):
            vistos.add(id_)
            achados.append((id_, nome, telefone))
    for c in conversas:
        if c.tipo == "privada" and c.id not in vistos and \
                m.casa_busca(c.nome, busca):
            vistos.add(c.id)
            achados.append((c.id, c.nome, ""))
    return achados


def rotulo(nome, telefone=""):
    """'Ana Souza, +5551999998888'."""
    return "%s, %s" % (nome, telefone) if telefone else nome

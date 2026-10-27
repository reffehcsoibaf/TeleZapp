# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
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


# O que a janela Nova mensagem deixa escolher mostrar: valor e texto.
MODOS = (("tudo", "Contatos, conversas e grupos"),
         ("contatos", "Só contatos"),
         ("conversas", "Só conversas"),
         ("grupos", "Só grupos"))


def grupos_candidatos(busca, conversas, grupos=(), so_com_conversa=False):
    """[(id, nome, "grupo")] dos grupos cujo nome casa com a busca: os das
    conversas (tipo grupo) e, se nao `so_com_conversa`, os `grupos`
    [(id, nome)] de que a conta participa mesmo sem conversa guardada."""
    achados, vistos = [], set()
    for c in conversas:
        if c.tipo == "grupo" and c.id not in vistos and                 m.casa_busca(c.nome, busca):
            vistos.add(c.id)
            achados.append((c.id, c.nome, "grupo"))
    if not so_com_conversa:
        for id_, nome in grupos:
            if id_ not in vistos and m.casa_busca(nome, busca):
                vistos.add(id_)
                achados.append((id_, nome, "grupo"))
    return achados


def _nome_simples(nome):
    import unicodedata
    base = unicodedata.normalize("NFD", (nome or "").strip().lower())
    return " ".join("".join(c for c in base
                            if unicodedata.category(c) != "Mn").split())


def _digitos(id_, telefone):
    """Digitos do telefone do contato; sem telefone, os do endereco quando
    ele e um telefone (@s.whatsapp.net). O endereco @lid nao conta."""
    digitos = "".join(c for c in telefone or "" if c.isdigit())
    if not digitos and (id_ or "").endswith("@s.whatsapp.net"):
        digitos = "".join(c for c in id_.split("@")[0] if c.isdigit())
    return digitos


def sem_duplicados(itens, dados, entre_contas=False):
    """Tira da lista a mesma pessoa repetida, mantendo a ordem e o primeiro.
    `dados(item)` -> (grupo, id, nome, telefone); grupo e a conta (so se
    comparam contatos do mesmo grupo). Sao a mesma pessoa: o mesmo telefone
    e, quando um dos dois nao tem telefone (aparece so pelo endereco @lid,
    por exemplo), o mesmo nome. Duas pessoas com o mesmo nome e telefones
    diferentes continuam as duas. Com `entre_contas`, o grupo e ignorado: a
    mesma pessoa em varias contas aparece uma vez so."""
    fichas = []
    for x in itens:
        grupo, id_, nome, tel = dados(x)
        if entre_contas:
            grupo = None
        fichas.append((x, grupo, _digitos(id_, tel), _nome_simples(nome)))
    com_telefone = {(g, n) for _, g, d, n in fichas if d and n}
    vistos, saida = set(), []
    for x, grupo, digitos, nome in fichas:
        if digitos:
            chave = (grupo, "tel", digitos)
        elif not nome:
            chave = None
        elif (grupo, nome) in com_telefone:
            continue                # o mesmo nome ja aparece com telefone
        else:
            chave = (grupo, "nome", nome)
        if chave is not None:
            if chave in vistos:
                continue
            vistos.add(chave)
        saida.append(x)
    return saida


def rotulo(nome, telefone=""):
    """'Ana Souza, +5551999998888'."""
    return "%s, %s" % (nome, telefone) if telefone else nome

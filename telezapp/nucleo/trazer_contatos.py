# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Trazer para a agenda do TeleZapp os contatos que as contas ja tem. Sem wx.

Nao troca o nome de quem a pessoa ja nomeou no TeleZapp: so entram os
contatos que ainda nao estao na agenda."""


def ler(provedor):
    """[(id, nome, telefone)] da agenda da conta, ou [] se nao deu para ler.
    Leitura local no provedor; pode ir numa thread."""
    if provedor is None:
        return []
    try:
        return list(provedor.contatos_da_conta())
    except Exception:
        return []


def salvar(banco, conta_id, contatos):
    """Guarda os contatos que faltam; devolve quantos entraram."""
    ja = {(c[0], c[1]) for c in banco.contatos(conta_id)}
    novos = 0
    for id_, nome, tel in contatos:
        if (conta_id, id_) not in ja:
            banco.salvar_contato(conta_id, id_, nome, tel)
            ja.add((conta_id, id_))
            novos += 1
    return novos

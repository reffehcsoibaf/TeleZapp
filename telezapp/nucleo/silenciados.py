# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Participantes silenciados por grupo. Sem wx. So neste computador: o servico
nao fica sabendo, e as mensagens continuam guardadas.

No config: {"conta|grupo": {id da pessoa: {"nome", "formas"}}}. `formas` sao os
enderecos da mesma pessoa: no WhatsApp ela aparece pelo telefone ou pelo LID."""


def _chave(conta_id, conversa_id):
    return "%s|%s" % (conta_id, conversa_id)


def do_grupo(dados, conta_id, conversa_id):
    """{id: {"nome", "formas"}} do grupo."""
    return (dados or {}).get(_chave(conta_id, conversa_id)) or {}


def formas_do_grupo(dados, conta_id, conversa_id):
    """Todos os enderecos silenciados do grupo."""
    achadas = set()
    for id_, pessoa in do_grupo(dados, conta_id, conversa_id).items():
        achadas.add(id_)
        achadas.update(pessoa.get("formas") or ())
    return achadas


def com_participante(dados, conta_id, conversa_id, id_, nome, formas=()):
    """Novo dicionario com a pessoa silenciada."""
    novo = {k: dict(v) for k, v in (dados or {}).items()}
    novo.setdefault(_chave(conta_id, conversa_id), {})[id_] = {
        "nome": nome, "formas": sorted(set(formas) | {id_})}
    return novo


def sem_participante(dados, conta_id, conversa_id, id_):
    """Novo dicionario sem a pessoa; grupo vazio sai do config."""
    novo = {k: dict(v) for k, v in (dados or {}).items()}
    chave = _chave(conta_id, conversa_id)
    novo.get(chave, {}).pop(id_, None)
    if chave in novo and not novo[chave]:
        del novo[chave]
    return novo

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Pastas do Telegram (e, no futuro, listas do WhatsApp) como filtro extra da
lista de conversas. Sem wxPython nem Telethon.

Uma pasta e {"id": texto, "nome": texto, "incluir": [ids], "excluir": [ids],
"contatos", "nao_contatos", "grupos", "canais", "bots": bool,
"sem_silenciadas", "sem_lidas", "sem_arquivadas": bool}. Quem tem ids em
"incluir" entra sempre; as demais entram pelas categorias marcadas e saem
pelas exclusoes, como no Telegram.

A caixa so aparece quando o filtro de contas aponta para uma conta so (uma
conta escolhida ou um servico que tem uma unica conta): pastas de contas
diferentes nao se misturam."""
from telezapp.nucleo import modelos as m

# o que cada servico chama de seu agrupamento
ROTULOS = {"telegram": "Pasta", "whatsapp": "Lista"}
TODAS = ""          # valor da primeira opcao: sem filtrar por pasta
ROTULO_TODAS = {"telegram": "Todas as pastas", "whatsapp": "Todas as listas"}


def conta_unica(filtro_conta, contas):
    """O id da unica conta a que o filtro de contas se refere, ou None.
    `contas`: [(id, servico)]. Conta escolhida: ela. Servico escolhido: a
    conta dele, se for uma so. Todas as contas: nenhuma."""
    if isinstance(filtro_conta, str) and filtro_conta.startswith("conta:"):
        id_ = filtro_conta[6:]
        return id_ if any(c == id_ for c, _s in contas) else None
    if filtro_conta in m.SERVICOS:
        do_servico = [c for c, s in contas if s == filtro_conta]
        return do_servico[0] if len(do_servico) == 1 else None
    return None


def pasta_de_dados(f):
    """Normaliza o que o provedor devolve (ids em texto)."""
    return {
        "id": str(f.get("id")), "nome": str(f.get("nome") or "").strip(),
        "incluir": {str(x) for x in f.get("incluir") or ()},
        "excluir": {str(x) for x in f.get("excluir") or ()},
        **{k: bool(f.get(k)) for k in (
            "contatos", "nao_contatos", "grupos", "canais", "bots",
            "sem_silenciadas", "sem_lidas", "sem_arquivadas")}}


def membros(pasta, dialogos):
    """Os ids das conversas que a pasta mostra. `dialogos`: lista de
    {"id", "contato", "usuario", "bot", "grupo", "canal", "silenciada",
    "nao_lida", "arquivada"} (bool onde nao ha outro tipo)."""
    saida = set()
    for d in dialogos:
        if d["id"] in pasta["incluir"]:
            saida.add(d["id"])
            continue
        if d["id"] in pasta["excluir"]:
            continue
        if d.get("bot"):
            entra = pasta["bots"]
        elif d.get("usuario"):
            entra = pasta["contatos"] if d.get("contato") \
                else pasta["nao_contatos"]
        elif d.get("canal"):
            entra = pasta["canais"]
        else:
            entra = pasta["grupos"] and d.get("grupo", True)
        if not entra:
            continue
        if pasta["sem_silenciadas"] and d.get("silenciada"):
            continue
        if pasta["sem_lidas"] and not d.get("nao_lida"):
            continue
        if pasta["sem_arquivadas"] and d.get("arquivada"):
            continue
        saida.add(d["id"])
    return saida


def passa(conversa_id, pasta_id, pastas):
    """A conversa aparece com a pasta escolhida? `pastas`: {id: set de ids}.
    Sem pasta escolhida (TODAS) ou pasta que sumiu, nao filtra."""
    if not pasta_id or pasta_id not in pastas:
        return True
    return conversa_id in pastas[pasta_id]

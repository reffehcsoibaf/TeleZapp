# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Filtros personalizados da lista de conversas: cada um junta, de uma vez,
o que as duas caixas da tela principal fazem separadas (serviço ou conta, e
tipo de conversa).

Um filtro e {"id", "nome", "contas": [valores do filtro de conta],
"tipos": [valores do filtro de tipo]}. Dentro de cada lista, basta casar
com um dos itens marcados (Individuais ou Grupos); entre as duas listas, as
duas precisam casar (WhatsApp e Grupos). Lista vazia nao filtra. As
conversas trancadas nao entram em filtro nenhum: so aparecem do jeito de
sempre, com o codigo secreto.

O valor guardado nas configuracoes e {"ativo": bool, "lista": [filtros]}.
Sem wxPython.
"""
import time

from telezapp.nucleo import modelos as m

# Os tipos que um filtro personalizado pode usar (todos, menos as trancadas)
TIPOS = tuple(t for t in m.FILTROS_TIPO if t[0] != "trancadas")
_TIPOS_VALIDOS = {v for v, _ in TIPOS}


def padrao():
    return {"ativo": False, "lista": []}


def _lista_de_texto(valor, validos=None):
    saida = []
    for v in valor if isinstance(valor, (list, tuple)) else ():
        if isinstance(v, str) and v and v not in saida and (
                validos is None or v in validos):
            saida.append(v)
    return saida


def normalizar(valor):
    """O valor guardado, so com o que serve: filtros com id e nome unicos,
    contas e tipos em texto (tipo desconhecido e Trancadas saem)."""
    if not isinstance(valor, dict):
        return padrao()
    lista, ids = [], set()
    for f in valor.get("lista") or []:
        if not isinstance(f, dict):
            continue
        nome = str(f.get("nome") or "").strip()
        id_ = str(f.get("id") or "")
        if not nome or not id_ or id_ in ids:
            continue
        ids.add(id_)
        lista.append({"id": id_, "nome": nome,
                      "contas": _lista_de_texto(f.get("contas")),
                      "tipos": _lista_de_texto(f.get("tipos"),
                                               _TIPOS_VALIDOS)})
    return {"ativo": bool(valor.get("ativo")), "lista": lista}


def em_uso(valor):
    """Os filtros valem na tela principal: caixa ativada e pelo menos um
    filtro criado."""
    valor = normalizar(valor)
    return valor["ativo"] and bool(valor["lista"])


def passa(c, filtro, busca="", com_favoritas=()):
    """A conversa aparece na lista com esse filtro? Conversa trancada nunca
    (so no tipo Trancadas, que nao e deste filtro)."""
    contas = filtro.get("contas") or [m.CONTA_TODAS]
    tipos = ([t for t in filtro.get("tipos") or () if t != "trancadas"]
             or ["todas"])
    return any(m.passa_filtro(c, t, v, busca, com_favoritas)
               for v in contas for t in tipos)


def usa_favoritas(filtro):
    return "favoritas" in (filtro.get("tipos") or ())


def nome_sugerido(contas, tipos, rotulos_de_conta):
    """O nome que o TeleZapp sugere para o filtro, com os itens marcados:
    "WhatsApp, Não lidas, Grupos, Arquivadas". "Todas as contas" e "Todas
    as conversas" so aparecem quando nao ha outro item na lista."""
    r_conta = dict(rotulos_de_conta)
    r_tipo = dict(TIPOS)
    contas = [c for c in contas if c in r_conta]
    tipos = [t for t in tipos if t in r_tipo]
    todas_contas = m.CONTA_TODAS in contas      # "todas" cobre as outras
    todos_tipos = "todas" in tipos
    if todas_contas:
        contas = [m.CONTA_TODAS]
    if todos_tipos:
        tipos = ["todas"]
    if contas and tipos:                        # so um dos dois vira "todas"
        if todas_contas:
            contas = []
        if todos_tipos:
            tipos = []
    partes = [r_conta[c] for c in contas] + [r_tipo[t] for t in tipos]
    return ", ".join(partes) if partes else r_tipo["todas"]


def nome_livre(nome, filtros, ignorar_id=""):
    """`nome`, ou com " (2)", " (3)"... se outro filtro ja usa o mesmo."""
    usados = {f["nome"].casefold() for f in filtros
              if f["id"] != ignorar_id}
    if nome.casefold() not in usados:
        return nome
    n = 2
    while ("%s (%d)" % (nome, n)).casefold() in usados:
        n += 1
    return "%s (%d)" % (nome, n)


def novo_id(filtros):
    usados = {f["id"] for f in filtros}
    base = int(time.time())
    while "f%d" % base in usados:
        base += 1
    return "f%d" % base


def achar(valor, id_):
    """O filtro com esse id, ou o primeiro; None se nao ha filtros."""
    lista = normalizar(valor)["lista"]
    for f in lista:
        if f["id"] == id_:
            return f
    return lista[0] if lista else None

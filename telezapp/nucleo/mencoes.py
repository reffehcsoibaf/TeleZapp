# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Mencoes (@) ao escrever numa mensagem de grupo.

Na caixa de digitar a mencao fica como "@Nome", legivel para quem escreve.
Ao enviar, cada servico troca esse trecho pelo que ele entende. Uma mencao
e um dicionario {"id": identificador do participante, "nome": nome mostrado,
"usuario": "@usuario" quando o servico tem}.

Mencionar todos do grupo (so no WhatsApp) e o trecho "@all" no texto: e ele
que o WhatsApp destaca, e e ele que liga o aviso a todos ao enviar.
"""
import re

TODOS = "@all"
NOME_TODOS = "Todos do grupo"
_TODOS = re.compile(r"(?:^|(?<=\s))@all(?![\w@])", re.IGNORECASE)


def membro_todos():
    """O item "Todos do grupo" que abre a lista de quem mencionar; o filtro
    acha ele por "todos" ou por "all"."""
    return {"id": "", "nome": NOME_TODOS, "telefone": TODOS, "todos": True}


def menciona_todos(texto):
    """O texto tem "@all" sozinho (no comeco ou depois de espaco)?"""
    return bool(_TODOS.search(texto or ""))


def com_todos_minusculo(texto):
    """"@All" ou "@ALL" viram "@all", a forma que o WhatsApp reconhece."""
    return _TODOS.sub(TODOS, texto or "")


def localizar(texto, mencoes):
    """[(inicio, fim, mencao)] dos trechos '@nome' do texto, em ordem. O
    nome mais longo vence quando um e parte do outro, e o '@' precisa estar
    no comeco ou depois de espaco."""
    achados = []
    ocupado = []
    for men in sorted(mencoes or [], key=lambda x: -len(x.get("nome", ""))):
        marca = "@" + (men.get("nome") or "")
        if len(marca) < 2:
            continue
        pos = 0
        while True:
            i = texto.find(marca, pos)
            if i < 0:
                break
            pos = i + len(marca)
            if i > 0 and not texto[i - 1].isspace():
                continue
            if any(i < f and pos > a for a, f in ocupado):
                continue
            ocupado.append((i, pos))
            achados.append((i, pos, men))
    achados.sort(key=lambda x: x[0])
    return achados


def aplicar(texto, mencoes, trocar):
    """Troca cada '@nome' por `trocar(mencao)` e devolve (novo_texto,
    [(inicio, fim, mencao)]) com as posicoes dos trechos no novo texto."""
    saida, posicoes, ultimo = [], [], 0
    atual = 0
    for i, f, men in localizar(texto, mencoes):
        saida.append(texto[ultimo:i])
        atual += i - ultimo
        novo = trocar(men)
        saida.append(novo)
        posicoes.append((atual, atual + len(novo), men))
        atual += len(novo)
        ultimo = f
    saida.append(texto[ultimo:])
    return "".join(saida), posicoes

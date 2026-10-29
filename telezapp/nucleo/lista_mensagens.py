# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""O que cada linha da lista de mensagens mostra, e em que ordem.

Sem wx, para testar em qualquer sistema. A escolha vive em `lista_mensagens`
(config): {"ordem": [as chaves de ITENS, na ordem], "ocultos": [chaves que
ficam de fora], "autor_so_quando_muda": bool}. Sempre sobra pelo menos um item
ativado. Substitui a antiga opcao `estilo` ("Como cada mensagem e lida"):
`do_estilo` converte o que a pessoa tinha.
"""

ITENS = (
    ("autor", "Nome de quem enviou"),
    ("hora", "Hora ou data da mensagem"),
    ("conteudo", "Conteúdo (texto, tipo da mídia e legenda)"),
    ("marcas", "Marcas: editada, apagada pelo autor, favorita, temporária"),
    ("links", "Aviso de links, botões e opções (Tab)"),
    ("previa", "Prévia do link"),
    ("ia", "Transcrição ou descrição feita pela IA"),
    ("reacoes", "Reações"),
    ("resposta", "Em resposta a quem"),
    ("estado", "Estado das minhas mensagens (enviada, entregue, lida)"),
)
CHAVES = tuple(c for c, _ in ITENS)
ROTULOS = dict(ITENS)
CONTEUDO = ("conteudo", "marcas", "links", "previa", "ia", "reacoes",
            "resposta")
# a linha de sempre: "Ana, 10:00: oi (editada) ... Lida"
PADRAO = {"ordem": list(CHAVES), "ocultos": [], "autor_so_quando_muda": False}
MENSAGEM_DO_MINIMO = "Pelo menos um item precisa ficar ativado."
ROTULO_SO_QUANDO_MUDA = ("Mostrar o nome de quem enviou só quando muda "
                         "(some também a repetição seguida)")


def normalizar(valor):
    """O valor guardado, corrigido: as chaves uma vez cada (as desconhecidas
    saem, as que faltam entram no fim), ocultos so entre elas e pelo menos um
    ativado (se tudo estiver oculto, voltam todos)."""
    if not isinstance(valor, dict):
        return {"ordem": list(PADRAO["ordem"]), "ocultos": [],
                "autor_so_quando_muda": False}
    ordem = []
    for c in valor.get("ordem") or []:
        if c in CHAVES and c not in ordem:
            ordem.append(c)
    ordem += [c for c in CHAVES if c not in ordem]
    escondidos = valor.get("ocultos") or []
    ocultos = [c for c in ordem if c in escondidos]
    if len(ocultos) >= len(ordem):
        ocultos = []
    return {"ordem": ordem, "ocultos": ocultos,
            "autor_so_quando_muda": valor.get("autor_so_quando_muda") is True}


def do_estilo(estilo):
    """O valor equivalente a um dos tres estilos de antes: 1 autor e hora
    primeiro (o padrao), 2 conteudo primeiro, 3 autor so quando muda."""
    lay = padrao()
    resto = [c for c in CHAVES if c not in ("autor", "hora", "estado")]
    if estilo == 2:
        lay["ordem"] = resto + ["autor", "hora", "estado"]
    elif estilo == 3:
        lay["ordem"] = ["autor"] + resto + ["hora", "estado"]
        lay["ocultos"] = ["hora"]
        lay["autor_so_quando_muda"] = True
    return normalizar(lay)


def ativos(valor):
    """As chaves ativadas, na ordem em que aparecem."""
    lay = normalizar(valor)
    return [c for c in lay["ordem"] if c not in lay["ocultos"]]


def so_quando_muda(valor):
    return normalizar(valor)["autor_so_quando_muda"]


def definir_so_quando_muda(valor, ligado):
    lay = normalizar(valor)
    lay["autor_so_quando_muda"] = bool(ligado)
    return lay


def padrao():
    return normalizar(None)


def eh_padrao(valor):
    return normalizar(valor) == padrao()


def alternar(valor, chave):
    """(novo valor, ativado). `ativado` e None quando nada mudou porque era o
    unico item ativado."""
    lay = normalizar(valor)
    if chave not in CHAVES:
        return lay, None
    if chave in lay["ocultos"]:
        lay["ocultos"].remove(chave)
        return lay, True
    if len(lay["ocultos"]) >= len(lay["ordem"]) - 1:
        return lay, None
    lay["ocultos"].append(chave)
    return lay, False


def mover(valor, chave, delta):
    """(novo valor, posicao nova). A posicao nao muda no inicio ou no fim."""
    lay = normalizar(valor)
    i = lay["ordem"].index(chave) if chave in lay["ordem"] else -1
    j = i + delta
    if i < 0 or not 0 <= j < len(lay["ordem"]):
        return lay, i
    lay["ordem"][i], lay["ordem"][j] = lay["ordem"][j], lay["ordem"][i]
    return lay, j


def texto_do_item(valor, chave):
    """"Conteúdo: ativado" para a lista da janela."""
    lay = normalizar(valor)
    return "%s: %s" % (ROTULOS[chave], "desativado"
                       if chave in lay["ocultos"] else "ativado")

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""O que o aviso falado de mensagem nova diz, e em que ordem (como a lista
de conversas e a de mensagens). Sem wx.

A escolha vive em `aviso_nova` (config): {"ordem": [chaves de ITENS],
"ocultos": [chaves que ficam de fora]}. Sempre sobra pelo menos um item.
O padrao repete o aviso de antes: "Nova mensagem em Ana. Ana, 10:00: oi".
"""

ITENS = (
    ("inicio", "As palavras \"Nova mensagem\""),
    ("conversa", "Nome da conversa (fora da conversa aberta)"),
    ("servico", "Serviço (WhatsApp ou Telegram)"),
    ("conta", "Conta que recebeu"),
    ("autor", "Nome de quem enviou"),
    ("hora", "Hora da mensagem"),
    ("conteudo", "Conteúdo (texto, tipo da mídia e legenda)"),
)
CHAVES = tuple(c for c, _ in ITENS)
ROTULOS = dict(ITENS)
PADRAO_OCULTOS = ("servico", "conta")
MENSAGEM_DO_MINIMO = "Pelo menos um item precisa ficar ativado."


def normalizar(valor):
    """Chaves uma vez cada (as desconhecidas saem, as que faltam entram no
    fim, ocultas), ocultos so entre elas e pelo menos um ativado."""
    if not isinstance(valor, dict):
        return padrao()
    ordem = []
    for c in valor.get("ordem") or []:
        if c in CHAVES and c not in ordem:
            ordem.append(c)
    novas = [c for c in CHAVES if c not in ordem]
    ordem += novas
    escondidos = list(valor.get("ocultos") or []) + [
        c for c in novas if c in PADRAO_OCULTOS]
    ocultos = [c for c in ordem if c in escondidos]
    if len(ocultos) >= len(ordem):
        ocultos = []
    return {"ordem": ordem, "ocultos": ocultos}


def padrao():
    return {"ordem": list(CHAVES), "ocultos": list(PADRAO_OCULTOS)}


def eh_padrao(valor):
    return normalizar(valor) == padrao()


def ativos(valor):
    lay = normalizar(valor)
    return [c for c in lay["ordem"] if c not in lay["ocultos"]]


def alternar(valor, chave):
    """(novo valor, ativado); ativado None se era o unico ativado."""
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
    lay = normalizar(valor)
    i = lay["ordem"].index(chave) if chave in lay["ordem"] else -1
    j = i + delta
    if i < 0 or not 0 <= j < len(lay["ordem"]):
        return lay, i
    lay["ordem"][i], lay["ordem"][j] = lay["ordem"][j], lay["ordem"][i]
    return lay, j


def texto_do_item(valor, chave):
    estado = "desativado" if chave in normalizar(valor)["ocultos"] \
        else "ativado"
    return "%s: %s" % (ROTULOS[chave], estado)


def montar(valor, partes, aberta=False):
    """O aviso. `partes`: {chave: texto} (vazio = nao entra). Na conversa
    aberta o nome dela nao entra. "Nova mensagem" seguida da conversa vira
    "Nova mensagem em Ana"; o inicio e a conversa terminam com ponto, como
    antes, e o resto vai separado por virgulas."""
    itens = [c for c in ativos(valor)
             if partes.get(c) and not (aberta and c == "conversa")]
    trechos = []
    i = 0
    while i < len(itens):
        c = itens[i]
        if c == "inicio" and i + 1 < len(itens) and \
                itens[i + 1] == "conversa":
            trechos.append(("cabeca", "%s em %s" % (
                partes["inicio"], partes["conversa"])))
            i += 2
            continue
        trechos.append(("cabeca" if c in ("inicio", "conversa") else "corpo",
                        partes[c]))
        i += 1
    texto = ""
    for k, (tipo, t) in enumerate(trechos):
        if k == 0:
            texto = t
        elif tipo == "cabeca" or trechos[k - 1][0] == "cabeca":
            texto += ". " + t
        else:
            texto += ", " + t
    return texto

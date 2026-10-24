# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""O que cada linha da lista de conversas mostra, e em que ordem.

Sem wx, para testar em qualquer sistema. A escolha vive em `lista_conversas`
(config): {"ordem": [as quatro chaves, na ordem], "ocultos": [chaves que
ficam de fora]}. Sempre sobra pelo menos um item ativado.
"""
from telezapp.nucleo import modelos as m

ITENS = (
    ("nome", "Nome da conversa"),
    ("servico", "Serviço a que a conversa pertence"),
    ("nao_lidas", "Quantidade de mensagens não lidas"),
    ("previa", "Trecho da última mensagem"),
)
CHAVES = tuple(c for c, _ in ITENS)
ROTULOS = dict(ITENS)
# o trecho da ultima mensagem vem desligado: a leitura da lista segue como
# sempre foi ate a pessoa ligar
PADRAO = {"ordem": list(CHAVES), "ocultos": ["previa"]}
TAMANHO_DA_PREVIA = 80
MENSAGEM_DO_MINIMO = "Pelo menos um item precisa ficar ativado."


def normalizar(valor):
    """O valor guardado, corrigido: as quatro chaves uma vez cada (as
    desconhecidas saem, as que faltam entram no fim), ocultos so entre elas
    e pelo menos um ativado (se tudo estiver oculto, voltam todos)."""
    if not isinstance(valor, dict):
        return {"ordem": list(PADRAO["ordem"]),
                "ocultos": list(PADRAO["ocultos"])}
    ordem = []
    for c in valor.get("ordem") or []:
        if c in CHAVES and c not in ordem:
            ordem.append(c)
    ordem += [c for c in CHAVES if c not in ordem]
    ocultos = [c for c in ordem if c in (valor.get("ocultos") or [])]
    if len(ocultos) >= len(ordem):
        ocultos = []
    return {"ordem": ordem, "ocultos": ocultos}


def ativos(valor):
    """As chaves ativadas, na ordem em que aparecem."""
    lay = normalizar(valor)
    return [c for c in lay["ordem"] if c not in lay["ocultos"]]


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
    """"Nome da conversa: ativado" para a lista da janela."""
    lay = normalizar(valor)
    return "%s: %s" % (ROTULOS[chave], "desativado"
                       if chave in lay["ocultos"] else "ativado")


def previa_da_mensagem(msg, grupo=False, quem=""):
    """O trecho da ultima mensagem: "Você: texto", "Ana: texto" (em grupo) ou
    so o texto, numa linha e sem passar de TAMANHO_DA_PREVIA caracteres."""
    if msg is None:
        return ""
    corpo = " ".join(m.conteudo(msg, com_estado=False).split())
    if not corpo:
        return ""
    if len(corpo) > TAMANHO_DA_PREVIA:
        corpo = corpo[:TAMANHO_DA_PREVIA - 1].rstrip() + "…"
    autor = "Você" if msg.minha else ((msg.autor or quem) if grupo else "")
    return "%s: %s" % (autor, corpo) if autor else corpo


def _nao_lidas(c):
    if c.nao_lidas <= 0:
        return ""
    if c.tipo == "status":
        return "1 não visto" if c.nao_lidas == 1 \
            else "%d não vistos" % c.nao_lidas
    return "1 não lida" if c.nao_lidas == 1 else "%d não lidas" % c.nao_lidas


def rotulo(c, valor=None, previa=""):
    """A linha da conversa na lista. Fixada e silenciada aparecem sempre,
    logo depois do servico (ou do nome, se o servico estiver de fora). Se os
    itens ativados nao tiverem nada para mostrar nesta conversa (sem nao
    lidas e sem mensagem, por exemplo), vale o nome."""
    partes = []
    for chave in ativos(valor):
        texto = {"nome": c.nome,
                 "servico": m.SERVICOS.get(c.servico, c.servico),
                 "nao_lidas": _nao_lidas(c),
                 "previa": previa}[chave]
        if texto:
            partes.append((chave, texto))
    marcas = (["fixada"] if c.fixada else []) + (
        ["silenciada"] if c.silenciada() else [])
    if marcas:
        # depois do servico; sem ele, do nome; sem os dois, no comeco
        onde = {chave: k for k, (chave, _) in enumerate(partes)}
        pos = onde["servico"] + 1 if "servico" in onde else \
            onde["nome"] + 1 if "nome" in onde else 0
        partes[pos:pos] = [("marca", t) for t in marcas]
    if not partes:
        return c.nome
    return ", ".join(t for _, t in partes)

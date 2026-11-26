# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""O que o aviso falado de mensagem nova diz, e em que ordem (como a lista
de conversas e a de mensagens). Sem wx.

A escolha vive em `aviso_nova` (config): {"ordem": [chaves de ITENS],
"ocultos": [chaves que ficam de fora], "modelo": texto com as flags}.
Cada item tem uma flag ($New, $conversation_out, ...): o texto fora delas é
falado como está escrito, e repetir uma flag repete o pedaço. Modelo vazio
desliga a fala do aviso (o som da notificação continua).
O padrão repete o aviso de antes: "Nova mensagem em Ana. Ana, 10:00: oi".
"""
import re

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
FLAGS = {
    "inicio": "$New",
    "conversa": "$conversation_out",
    "servico": "$Service",
    "conta": "$Account",
    "autor": "$Sender_Name",
    "hora": "$Time",
    "conteudo": "$Content",
}
CHAVE_POR_FLAG = {flag: chave for chave, flag in FLAGS.items()}
PADRAO_OCULTOS = ("servico", "conta")
MODELO_PADRAO = "$New em $conversation_out. $Sender_Name, $Time, $Content"
AUSENTE = "(sem conteúdo)"
_PADRAO_DE_FLAGS = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*")


def _modelo_dos_ativos(ordem):
    """Flags dos itens ativos, na ordem da lista, separadas por espaço."""
    return " ".join(FLAGS[c] for c in ordem)


def normalizar(valor):
    """Chaves uma vez cada (as desconhecidas saem, as que faltam entram no
    fim, ocultas), ocultos so entre elas, e o modelo como texto. Config
    antiga sem modelo ganha o padrão quando a escolha também é a padrão, ou
    as flags dos ativos na ordem em que estavam."""
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
    if isinstance(valor.get("modelo"), str):
        modelo = valor["modelo"]
    else:
        ativos = [c for c in ordem if c not in ocultos]
        modelo = (MODELO_PADRAO if ativos ==
                  [c for c in CHAVES if c not in PADRAO_OCULTOS]
                  else _modelo_dos_ativos(ativos))
    return {"ordem": ordem, "ocultos": ocultos, "modelo": modelo}


def padrao():
    return {"ordem": list(CHAVES), "ocultos": list(PADRAO_OCULTOS),
            "modelo": MODELO_PADRAO}


def eh_padrao(valor):
    return normalizar(valor) == padrao()


def ativos(valor):
    lay = normalizar(valor)
    return [c for c in lay["ordem"] if c not in lay["ocultos"]]


def flags_usadas(modelo):
    """As flags conhecidas que aparecem no modelo, na ordem em que foram
    escritas (repetições contam)."""
    if not isinstance(modelo, str):
        return []
    return [f for f in _PADRAO_DE_FLAGS.findall(modelo)
            if f in CHAVE_POR_FLAG]


def _inserir(modelo, flag):
    if not isinstance(modelo, str) or not modelo.strip():
        return flag
    return modelo.rstrip() + " " + flag


def _remover(modelo, flag):
    if not isinstance(modelo, str):
        return ""
    sem = re.sub(re.escape(flag) + r"(?![A-Za-z0-9_])", "", modelo)
    return re.sub(r"[ \t]{2,}", " ", sem).strip()


def alternar(valor, chave):
    """(novo valor, ativado); ativado None se a chave nao existe. Pode sobrar
    nenhum item ativado: e o jeito de desligar a fala pelo modelo."""
    lay = normalizar(valor)
    if chave not in CHAVES:
        return lay, None
    if chave in lay["ocultos"]:
        lay["ocultos"].remove(chave)
        lay["modelo"] = _inserir(lay["modelo"], FLAGS[chave])
        return lay, True
    lay["ocultos"].append(chave)
    lay["modelo"] = _remover(lay["modelo"], FLAGS[chave])
    if not flags_usadas(lay["modelo"]):
        lay["modelo"] = ""   # sem flag nenhuma, a frase toda sai
    return lay, False


def definir_modelo(valor, modelo):
    """Troca o texto e ajusta a lista: fica ativo quem tem flag no modelo."""
    lay = normalizar(valor)
    lay["modelo"] = modelo if isinstance(modelo, str) else ""
    usadas = set(flags_usadas(lay["modelo"]))
    lay["ocultos"] = [c for c in lay["ordem"] if FLAGS[c] not in usadas]
    return lay


def mover(valor, chave, delta):
    """Muda só a ordem da lista. A ordem da frase é a do modelo, escrito
    pelo usuario."""
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


def renderizar(modelo, partes, aberta=False):
    """Troca cada flag pelo pedaço correspondente. Pedaço que nao existe
    (ou a conversa aberta) vira `(sem conteúdo)`; flag desconhecida fica
    como texto. Modelo vazio nao fala nada."""
    if not isinstance(modelo, str) or not modelo.strip():
        return ""

    def troca(m):
        flag = m.group(0)
        chave = CHAVE_POR_FLAG.get(flag)
        if chave is None or (aberta and chave == "conversa"):
            return AUSENTE if chave is not None else flag
        return partes.get(chave) or AUSENTE

    return _PADRAO_DE_FLAGS.sub(troca, modelo)


def montar(valor, partes, aberta=False):
    """O aviso, com o modelo escolhido (Configurações, Interface, Aviso
    falado de mensagem nova)."""
    return renderizar(normalizar(valor)["modelo"], partes, aberta)

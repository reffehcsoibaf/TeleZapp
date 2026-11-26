# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""O que o aviso falado de mensagem nova diz, e em que ordem (como a lista
de conversas e a de mensagens). Sem wx.

Ha um bloco por tipo de conversa (privada, grupo, canal), cada um com
`ordem`, `ocultos` e `modelo`. Cada item tem uma flag ($New,
$conversation_out, ...): o texto fora delas é falado como está escrito, e
repetir uma flag repete o pedaço. Modelo vazio desliga a fala daquele tipo
(o som da notificação continua).
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

TIPOS = ("privada", "grupo", "canal")
TIPO_PADRAO = "privada"
ROTULOS_TIPO = {
    "privada": "Conversas individuais",
    "grupo": "Grupos",
    "canal": "Canais",
}


def normalizar_tipo(tipo):
    """Tipo de conversa conhecido; o resto cai em conversa individual."""
    return tipo if tipo in TIPOS else TIPO_PADRAO


def rotulo_tipo(tipo):
    return ROTULOS_TIPO[normalizar_tipo(tipo)]


def _bloco_padrao():
    return {"ordem": list(CHAVES), "ocultos": list(PADRAO_OCULTOS),
            "modelo": MODELO_PADRAO}


def padrao():
    return {"tipos": {t: _bloco_padrao() for t in TIPOS}}


def _normalizar_bloco(valor):
    """Chaves uma vez cada (as desconhecidas saem, as que faltam entram no
    fim, ocultas), ocultos só entre elas, e modelo como texto. Bloco sem
    modelo (config muito antiga) ganha o padrão se a escolha também for a
    padrão, ou as flags dos ativos na ordem em que estavam."""
    if not isinstance(valor, dict):
        return _bloco_padrao()
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
        ativos_ = [c for c in ordem if c not in ocultos]
        modelo = (MODELO_PADRAO if ativos_ ==
                  [c for c in CHAVES if c not in PADRAO_OCULTOS]
                  else _modelo_dos_ativos(ativos_))
    return {"ordem": ordem, "ocultos": ocultos, "modelo": modelo}


def normalizar(valor):
    """Config completa. Quem vem de uma versão com um modelo só começa com
    os três blocos no padrão, como decidido para a atualização."""
    if not isinstance(valor, dict) or not isinstance(valor.get("tipos"), dict):
        return padrao()
    return {"tipos": {t: _normalizar_bloco(valor["tipos"].get(t))
                      for t in TIPOS}}


def bloco(valor, tipo=TIPO_PADRAO):
    """O bloco normalizado de um tipo, sem mexer nos outros."""
    return normalizar(valor)["tipos"][normalizar_tipo(tipo)]


def definir_bloco(valor, novo, tipo=TIPO_PADRAO):
    """Troca o bloco de um tipo na config completa."""
    lay = normalizar(valor)
    lay["tipos"][normalizar_tipo(tipo)] = _normalizar_bloco(novo)
    return lay


def _modelo_dos_ativos(ordem):
    """Flags dos itens ativos, na ordem da lista, separadas por espaço."""
    return " ".join(FLAGS[c] for c in ordem)


def eh_padrao(valor, tipo=TIPO_PADRAO):
    return bloco(valor, tipo) == _bloco_padrao()


def ativos(valor, tipo=TIPO_PADRAO):
    lay = bloco(valor, tipo)
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


def _alternar_bloco(lay, chave):
    if chave not in CHAVES:
        return lay, None
    lay = dict(lay)
    lay["ordem"] = list(lay["ordem"])
    lay["ocultos"] = list(lay["ocultos"])
    if chave in lay["ocultos"]:
        lay["ocultos"].remove(chave)
        lay["modelo"] = _inserir(lay["modelo"], FLAGS[chave])
        return lay, True
    lay["ocultos"].append(chave)
    lay["modelo"] = _remover(lay["modelo"], FLAGS[chave])
    if not flags_usadas(lay["modelo"]):
        lay["modelo"] = ""   # sem flag nenhuma, a frase toda sai
    return lay, False


def alternar(valor, chave, tipo=TIPO_PADRAO):
    """(nova config, ativado); ativado None se a chave não existe."""
    novo, ativado = _alternar_bloco(bloco(valor, tipo), chave)
    return definir_bloco(valor, novo, tipo), ativado


def _definir_modelo_bloco(lay, modelo):
    lay = dict(lay)
    lay["modelo"] = modelo if isinstance(modelo, str) else ""
    usadas = set(flags_usadas(lay["modelo"]))
    lay["ocultos"] = [c for c in lay["ordem"] if FLAGS[c] not in usadas]
    return lay


def definir_modelo(valor, modelo, tipo=TIPO_PADRAO):
    """Troca o texto e ajusta a lista daquele tipo: fica ativo quem tem
    flag no modelo."""
    novo = _definir_modelo_bloco(bloco(valor, tipo), modelo)
    return definir_bloco(valor, novo, tipo)


def _mover_bloco(lay, chave, delta):
    lay = dict(lay)
    lay["ordem"] = list(lay["ordem"])
    i = lay["ordem"].index(chave) if chave in lay["ordem"] else -1
    j = i + delta
    if i < 0 or not 0 <= j < len(lay["ordem"]):
        return lay, i
    lay["ordem"][i], lay["ordem"][j] = lay["ordem"][j], lay["ordem"][i]
    return lay, j


def mover(valor, chave, delta, tipo=TIPO_PADRAO):
    """Muda só a ordem da lista daquele tipo. A ordem da frase é a do
    modelo, escrito pela pessoa."""
    novo, pos = _mover_bloco(bloco(valor, tipo), chave, delta)
    return definir_bloco(valor, novo, tipo), pos


def texto_do_item(valor, chave, tipo=TIPO_PADRAO):
    estado = "desativado" if chave in bloco(valor, tipo)["ocultos"] \
        else "ativado"
    return "%s: %s" % (ROTULOS[chave], estado)


def renderizar(modelo, partes, aberta=False):
    """Troca cada flag pelo pedaço correspondente. Pedaço que não existe
    (ou a conversa aberta) vira `(sem conteúdo)`; flag desconhecida fica
    como texto. Modelo vazio não fala nada."""
    if not isinstance(modelo, str) or not modelo.strip():
        return ""

    def troca(m):
        flag = m.group(0)
        chave = CHAVE_POR_FLAG.get(flag)
        if chave is None or (aberta and chave == "conversa"):
            return AUSENTE if chave is not None else flag
        return partes.get(chave) or AUSENTE

    return _PADRAO_DE_FLAGS.sub(troca, modelo)


def montar(valor, partes, aberta=False, tipo=TIPO_PADRAO):
    """O aviso, com o modelo do tipo de conversa (Configurações, Interface,
    Aviso falado de mensagem nova)."""
    return renderizar(bloco(valor, tipo)["modelo"], partes, aberta)

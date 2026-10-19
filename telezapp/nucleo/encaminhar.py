# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Encaminhar mensagens: o que enviar de cada uma e para onde. Sem wx.

O TeleZapp reenvia o conteudo (texto, ou o arquivo ja baixado com a legenda)
pelo envio normal de cada conta, entao vale entre conversas, contas e
servicos diferentes. Nao e o encaminhamento do proprio servico (sem o
aviso "Encaminhada").
"""
import os
from dataclasses import dataclass

from telezapp.nucleo import modelos as m


@dataclass
class Item:
    """Uma mensagem pronta para sair. tipo: "texto" (usa `texto`) ou
    "arquivo" (usa `caminho`, `tipo_midia` e `texto` como legenda)."""
    tipo: str
    texto: str = ""
    caminho: str = ""
    tipo_midia: str = ""


MIDIAS = (m.FOTO, m.VIDEO, m.VOZ, m.AUDIO, m.DOCUMENTO, m.FIGURINHA)


def preparar(msg, caminho_da_midia):
    """(Item, "") ou (None, motivo): o que dizer da mensagem que nao da para
    encaminhar. `caminho_da_midia(msg)`: arquivo baixado, ou None."""
    if m.extras_de(msg)["apagada"]:
        return None, "mensagem apagada"
    if msg.tipo in MIDIAS:
        caminho = caminho_da_midia(msg)
        if not caminho or not os.path.isfile(caminho):
            return None, "%s ainda não baixado(a)" % m.NOMES_TIPOS[msg.tipo]
        return Item("arquivo", msg.texto if msg.tipo not in (
            m.VOZ, m.AUDIO, m.FIGURINHA) else "", caminho, msg.tipo), ""
    texto = msg.texto or m.conteudo(msg, com_estado=False)
    if msg.tipo == m.AGUARDANDO or not texto:
        return None, "mensagem sem conteúdo"
    return Item("texto", texto), ""


def destinos(conversas, contatos, conectada, trancadas=False):
    """[(conta_id, conversa_id, nome, tipo)] para onde encaminhar, por nome:
    as conversas de contas conectadas (sem as trancadas, a menos que
    `trancadas`) e os contatos que ainda nao tem conversa.

    conversas: [Conversa]; contatos: [(conta_id, id, nome, telefone)];
    conectada(conta_id) -> bool."""
    achados, vistos = [], set()
    for c in conversas:
        if not conectada(c.conta_id) or c.somente_leitura or (
                c.trancada and not trancadas):
            continue
        achados.append((c.conta_id, c.id, c.nome, c.tipo))
        vistos.add((c.conta_id, c.id))
    for conta_id, id_, nome, telefone in contatos:
        if (conta_id, id_) in vistos or not conectada(conta_id):
            continue
        vistos.add((conta_id, id_))
        achados.append((conta_id, id_, nome or telefone or id_, "privada"))
    return sorted(achados, key=lambda d: d[2].lower())


def filtrar(lista, busca):
    return [d for d in lista if m.casa_busca(d[2], busca)]

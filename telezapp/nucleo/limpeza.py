# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Limpeza de midias baixadas e de mensagens: escolhe pelos filtros, mostra o
total e so depois apaga. O que foi limpo fica registrado (tabela `limpas`),
e por isso nao volta por historico, nova leitura ou download; so volta com um
novo pareamento da conta. Sem dependencia de wxPython."""
import os
import time
from dataclasses import dataclass, field

from telezapp.nucleo import modelos as m

DIA = 86400
MIDIAS, MENSAGENS = "midias", "mensagens"


# Os tipos como a limpeza e o resumo de espaco os agrupam: (rotulo, tipos)
GRUPOS_TIPOS = (("mensagens de texto", (m.TEXTO,)), ("fotos", (m.FOTO,)),
                ("vídeos", (m.VIDEO,)),
                ("mensagens de voz e áudios", (m.VOZ, m.AUDIO)),
                ("documentos", (m.DOCUMENTO,)),
                ("figurinhas", (m.FIGURINHA,)))


@dataclass
class Filtros:
    o_que: str = MIDIAS           # MIDIAS (so os arquivos) ou MENSAGENS
    conta_id: str = ""            # '' = todas as contas
    conversa_id: str = ""         # '' = todas as conversas da conta
    tipos: tuple = ()             # () = todos os tipos
    dias: int = 0                 # so as de ha mais de N dias (0 = todas)
    mb: int = 0                   # so as maiores que N MB (0 = qualquer)
    manter_favoritas: bool = True  # as favoritas nao entram na limpeza


@dataclass
class Selecao:
    o_que: str = MIDIAS
    itens: list = field(default_factory=list)
    bytes: int = 0                # espaco de arquivos que sera liberado

    @property
    def quantidade(self):
        return len(self.itens)


def _tamanho(caminho, registrado):
    try:
        return os.path.getsize(caminho)
    except OSError:
        return registrado or 0


def selecionar(banco, filtros, agora=None):
    """O que passa pelos filtros, com o espaco de arquivos que sai."""
    agora = agora or time.time()
    corte = agora - filtros.dias * DIA if filtros.dias else None
    minimo = filtros.mb * 1048576
    sel = Selecao(filtros.o_que)
    favoritas = banco.favoritas() if filtros.manter_favoritas else set()
    if filtros.o_que == MENSAGENS:
        sel.itens = [linha for linha in banco.mensagens_para_limpar(
            filtros.conta_id, filtros.conversa_id, filtros.tipos, corte,
            minimo) if tuple(linha[:3]) not in favoritas]
        for conta, conversa, mensagem, *_ in sel.itens:
            reg = banco.midia(conta, conversa, mensagem)
            if reg:
                sel.bytes += _tamanho(*reg)
        return sel
    for linha in banco.todas_midias():
        conta, conversa, _, tipo, caminho, tam, data = linha
        if filtros.conta_id and conta != filtros.conta_id:
            continue
        if filtros.conversa_id and conversa != filtros.conversa_id:
            continue
        if (conta, conversa, linha[2]) in favoritas:
            continue
        if filtros.tipos and tipo not in filtros.tipos:
            continue
        if corte is not None and data > corte:
            continue
        real = _tamanho(caminho, tam)
        if minimo and real <= minimo:
            continue
        sel.itens.append(linha)
        sel.bytes += real
    return sel


def _apagar_arquivo(caminho):
    if os.path.isfile(caminho):
        os.remove(caminho)


def apagar(banco, selecao):
    """Apaga e registra o que foi limpo. Devolve (apagados, bytes liberados,
    falhas); um arquivo que ja nao existe conta como apagado."""
    apagados = liberados = falhas = 0
    if selecao.o_que == MENSAGENS:
        feitas = []
        for conta, conversa, mensagem, *_ in selecao.itens:
            reg = banco.midia(conta, conversa, mensagem)
            if reg:
                try:
                    real = _tamanho(*reg)
                    _apagar_arquivo(reg[0])
                    liberados += real
                except OSError:
                    falhas += 1       # em uso: a mensagem fica
                    continue
            feitas.append((conta, conversa, mensagem))
        banco.apagar_mensagens(feitas)
        banco.registrar_limpeza(feitas, "mensagem")
        return len(feitas), liberados, falhas
    feitas = []
    for conta, conversa, mensagem, _, caminho, tam, _d in selecao.itens:
        try:
            real = _tamanho(caminho, tam)
            _apagar_arquivo(caminho)
        except OSError:
            falhas += 1
            continue
        liberados += real
        banco.esquecer_midia(conta, conversa, mensagem)
        feitas.append((conta, conversa, mensagem))
    banco.apagar_fichas(feitas)
    banco.registrar_limpeza(feitas, "midia")
    return len(feitas), liberados, falhas


def apagar_mensagem(banco, conta_id, conversa_id, mensagem_id):
    """Apaga uma mensagem, a midia dela, e registra para nao voltar. Devolve
    os bytes liberados."""
    liberados = 0
    reg = banco.midia(conta_id, conversa_id, mensagem_id)
    if reg:
        try:
            liberados = _tamanho(*reg)
            _apagar_arquivo(reg[0])
        except OSError:
            liberados = 0
    chave = [(conta_id, conversa_id, mensagem_id)]
    banco.apagar_mensagens(chave)
    banco.registrar_limpeza(chave, "mensagem")
    return liberados


def apagar_midia_da_mensagem(banco, conta_id, conversa_id, mensagem_id):
    """O autor apagou a mensagem para todos: o arquivo baixado sai daqui, mas
    a mensagem fica (marcada como apagada). Devolve os bytes liberados."""
    reg = banco.midia(conta_id, conversa_id, mensagem_id)
    if not reg:
        return 0
    liberados = 0
    try:
        liberados = _tamanho(*reg)
        _apagar_arquivo(reg[0])
    except OSError:
        return 0
    banco.esquecer_midia(conta_id, conversa_id, mensagem_id)
    return liberados


def resumo_de_espaco(banco, n_conversas):
    """Texto do espaco usado: conversas, mensagens de texto, midias baixadas
    (quantas e quanto ocupam) e o mesmo por tipo, como na limpeza."""
    por_tipo = {}                  # tipo -> [quantidade, bytes]
    for _, _, _, tipo, caminho, tamanho, _ in banco.todas_midias():
        if not os.path.isfile(caminho):
            continue
        item = por_tipo.setdefault(tipo, [0, 0])
        item[0] += 1
        item[1] += _tamanho(caminho, tamanho)
    total_n = sum(q for q, _ in por_tipo.values())
    total_b = sum(b for _, b in por_tipo.values())
    linhas = ["Conversas: %d." % n_conversas,
              "Mensagens de texto: %d." % banco.contar_mensagens(m.TEXTO),
              "Mídias baixadas: %d no total, ocupando %s." % (
                  total_n, m.tamanho_legivel(total_b)),
              "", "Mídias por tipo:"]
    for rotulo, tipos in GRUPOS_TIPOS[1:]:
        q = sum(por_tipo.get(t, [0, 0])[0] for t in tipos)
        b = sum(por_tipo.get(t, [0, 0])[1] for t in tipos)
        linhas.append("%s: %s." % (rotulo.capitalize(), (
            "%d, ocupando %s" % (q, m.tamanho_legivel(b))) if q
            else "nenhuma"))
    return "\n".join(linhas)

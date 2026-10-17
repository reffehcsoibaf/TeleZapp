# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Limpeza de midias baixadas e de mensagens: escolhe pelos filtros, mostra o
total e so depois apaga. O que foi limpo fica registrado (tabela `limpas`),
e por isso nao volta por historico, nova leitura ou download; so volta com um
novo pareamento da conta. Sem dependencia de wxPython."""
import os
import time
from dataclasses import dataclass, field

DIA = 86400
MIDIAS, MENSAGENS = "midias", "mensagens"


@dataclass
class Filtros:
    o_que: str = MIDIAS           # MIDIAS (so os arquivos) ou MENSAGENS
    conta_id: str = ""            # '' = todas as contas
    conversa_id: str = ""         # '' = todas as conversas da conta
    tipos: tuple = ()             # () = todos os tipos
    dias: int = 0                 # so as de ha mais de N dias (0 = todas)
    mb: int = 0                   # so as maiores que N MB (0 = qualquer)


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
    if filtros.o_que == MENSAGENS:
        sel.itens = banco.mensagens_para_limpar(
            filtros.conta_id, filtros.conversa_id, filtros.tipos, corte,
            minimo)
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

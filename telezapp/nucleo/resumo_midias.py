# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Resumo de conversa que aproveita audios e imagens. Sem wx.

Antes de resumir, o que ainda nao tem transcricao ou descricao pode ser
processado, com a pessoa escolhendo. O resultado fica guardado na mensagem,
entao o que ja foi feito nao gasta de novo.
"""
from dataclasses import dataclass, field

GENEROS = ("audio", "imagem", "figurinha")  # video e PDF ficam so a pedido
LIMITE = 50                                 # midias processadas por resumo
NOMES = {"audio": ("áudio", "áudios"), "imagem": ("imagem", "imagens"),
         "figurinha": ("figurinha", "figurinhas")}


@dataclass
class Plano:
    prontas: list = field(default_factory=list)    # ja tem o texto da IA
    processar: list = field(default_factory=list)  # as mais novas, em ordem
    fora: list = field(default_factory=list)       # passaram do limite


def planejar(mensagens, genero_de, tem_ia, pode, limite=LIMITE):
    """Separa as midias da conversa. genero_de(msg) -> genero ou ""; tem_ia(msg)
    -> ja processada?; pode(genero) -> ha provedor para esse genero?"""
    plano, candidatas = Plano(), []
    for x in mensagens:
        genero = genero_de(x)
        if genero not in GENEROS:
            continue
        if tem_ia(x):
            plano.prontas.append(x)
        elif pode(genero):
            candidatas.append(x)
    corte = max(0, len(candidatas) - limite)
    plano.fora, plano.processar = candidatas[:corte], candidatas[corte:]
    return plano


def contagem(mensagens, genero_de):
    """"3 áudios e 1 imagem"."""
    partes = []
    for genero in GENEROS:
        n = sum(1 for x in mensagens if genero_de(x) == genero)
        if n:
            partes.append("%d %s" % (n, NOMES[genero][0 if n == 1 else 1]))
    if len(partes) > 1:
        return ", ".join(partes[:-1]) + " e " + partes[-1]
    return partes[0] if partes else ""


def pergunta(plano, genero_de):
    """O texto da janela que pergunta se processa as midias."""
    texto = "Há %s sem transcrição ou descrição" % contagem(
        plano.processar + plano.fora, genero_de)
    if plano.prontas:
        texto += " (e %d já %s)" % (
            len(plano.prontas),
            "processada" if len(plano.prontas) == 1 else "processadas")
    texto += ". Processar %d para um resumo mais completo? Elas são enviadas " \
             "ao provedor de inteligência artificial, o que pode gastar a sua " \
             "cota e levar alguns minutos." % len(plano.processar)
    if plano.fora:
        texto += " As %d mais antigas ficam de fora: o limite é de %d por " \
                 "resumo." % (len(plano.fora), LIMITE)
    return texto


def aviso_final(falhas, fora):
    """O que o resumo nao cobriu, para aparecer junto dele ("" se nada)."""
    faltam = falhas + fora
    if not faltam:
        return ""
    return ("1 mídia ficou de fora deste resumo." if faltam == 1 else
            "%d mídias ficaram de fora deste resumo." % faltam)


class LoteDeResumo:
    """Acompanha as midias em processamento. `ao_andar(feitas, total)` e
    `ao_fim(falhas)` rodam na janela."""

    def __init__(self, chaves, ao_andar, ao_fim):
        self.pendentes = set(chaves)
        self.total = len(self.pendentes)
        self.falhas = 0
        self.cancelado = False
        self.ao_andar = ao_andar
        self.ao_fim = ao_fim

    def acabou(self, chave, falha=False):
        if chave not in self.pendentes:
            return
        self.pendentes.discard(chave)
        self.falhas += 1 if falha else 0
        if self.cancelado:
            return
        self.ao_andar(self.total - len(self.pendentes), self.total)
        if not self.pendentes:
            self.ao_fim(self.falhas)

    def cancelar(self):
        self.cancelado = True

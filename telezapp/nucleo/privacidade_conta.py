# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Privacidade da conta (WhatsApp e Telegram): visto por ultimo, online,
recado, confirmacao de leitura, quem me adiciona a grupos.

Essas escolhas ficam na conta do servico, nao no TeleZapp: o provedor as le
e as grava la. Aqui so a lista de campos e as regras, sem wx, para testar em
qualquer sistema. O Telegram nao separa "online" do visto por ultimo e nao
tem o status do WhatsApp.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Campo:
    """Uma escolha de privacidade. `nome` e o da biblioteca do WhatsApp;
    `opcoes` pareia o valor do WhatsApp com o texto mostrado."""
    nome: str
    rotulo: str
    opcoes: tuple


TODOS = ("all", "Todos")
CONTATOS = ("contacts", "Meus contatos")
NINGUEM = ("none", "Ninguém")

CAMPOS = (
    Campo("last", "Quem pode ver meu visto por último",
          (TODOS, CONTATOS, NINGUEM)),
    Campo("online", "Quem pode ver quando estou online",
          (TODOS, ("match_last_seen", "Os mesmos do visto por último"))),
    Campo("status", "Quem pode ver meu recado",
          (TODOS, CONTATOS, NINGUEM)),
    Campo("readreceipts",
          "Confirmação de leitura (mensagem lida e áudio reproduzido)",
          (("all", "Ativada"), ("none", "Desativada"))),
    Campo("groupadd", "Quem pode me adicionar a grupos",
          (TODOS, CONTATOS)),
)

# o que o WhatsApp devolve para "meus contatos, exceto alguns" e afins
VALOR_COM_LISTA = "contact_blacklist"

# Telegram: quais campos existem e como se chamam la
CAMPOS_TELEGRAM = ("last", "status", "readreceipts", "groupadd")
ROTULOS_TELEGRAM = {
    "last": "Quem pode ver meu visto por último e online",
    "readreceipts": "Confirmação de leitura (mostrar a hora em que li)",
}


def campos_do(servico):
    """Os campos que o servico tem, com o texto certo para ele."""
    if servico != "telegram":
        return CAMPOS
    return tuple(
        Campo(c.nome, ROTULOS_TELEGRAM.get(c.nome, c.rotulo), c.opcoes)
        for c in CAMPOS if c.nome in CAMPOS_TELEGRAM)


def indice(campo, atual):
    """Posicao do valor atual entre as opcoes; -1 se o WhatsApp respondeu
    algo que a lista nao tem (por exemplo, "meus contatos, exceto..."): a
    caixa fica sem escolha em vez de adivinhar."""
    for i, (valor, _) in enumerate(campo.opcoes):
        if valor == atual:
            return i
    return -1


def ilegivel(valores):
    """Nenhum campo tem um valor conhecido: nao deu para ler a privacidade."""
    if not isinstance(valores, dict):
        return True
    return all(indice(c, valores.get(c.nome)) == -1 for c in CAMPOS)


def desconhecidos(valores):
    """Campos cujo valor atual nao esta na lista (ficam como estao)."""
    return [c for c in CAMPOS if indice(c, valores.get(c.nome)) == -1]


def mudancas(carregado, escolhido):
    """[(campo, valor)] so do que mudou. `escolhido`: campo -> posicao
    escolhida (ausente ou -1 = a pessoa nao mexeu)."""
    feitas = []
    for c in CAMPOS:
        i = escolhido.get(c.nome, -1)
        if 0 <= i < len(c.opcoes):
            valor = c.opcoes[i][0]
            if carregado.get(c.nome) != valor:
                feitas.append((c.nome, valor))
    return feitas


def nao_confirmadas(pedidas, relido):
    """Campos pedidos que o WhatsApp nao devolve como mudados numa nova
    leitura: um pedido pode "dar certo" sem fazer nada, so a releitura prova."""
    if ilegivel(relido):
        return [campo for campo, _ in pedidas]
    return [campo for campo, valor in pedidas if relido.get(campo) != valor]


def rotulo_do_campo(nome):
    return next((c.rotulo for c in CAMPOS if c.nome == nome), nome)


def texto_status(tipo, quantas):
    """Frase sobre quem ve o status (stories). `tipo`: contacts, blacklist
    ou whitelist; `quantas`: tamanho da lista. So leitura: mudar isso pede
    o celular."""
    if tipo == "blacklist":
        return ("Meus contatos, exceto %d pessoa%s" % (
            quantas, "" if quantas == 1 else "s")
            if quantas else "Meus contatos")
    if tipo == "whitelist":
        return "Somente %d pessoa%s" % (quantas, "" if quantas == 1 else "s")
    return "Meus contatos"

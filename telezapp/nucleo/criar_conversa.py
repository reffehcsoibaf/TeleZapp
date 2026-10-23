# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Criar grupo, canal ou comunidade: o que cada servico aceita e a conferencia
do que a pessoa digitou, antes de enviar. Sem wx, para testar."""
import re

GRUPO, CANAL, COMUNIDADE = "grupo", "canal", "comunidade"

# como cada tipo entra nas frases: ("do grupo", "grupos", titulo da janela)
NOMES = {GRUPO: ("do grupo", "grupos", "Novo grupo"),
         CANAL: ("do canal", "canais", "Novo canal"),
         COMUNIDADE: ("da comunidade", "comunidades", "Nova comunidade")}

# limites de letras por servico e tipo: (nome, descricao)
LIMITES = {
    ("whatsapp", GRUPO): (25, 2048), ("whatsapp", COMUNIDADE): (25, 2048),
    ("whatsapp", CANAL): (100, 2048),
    ("telegram", GRUPO): (128, 255), ("telegram", CANAL): (128, 255),
}


def tipos_do_servico(servico):
    """Tipos que o TeleZapp cria no servico, na ordem do menu."""
    return [t for t in (GRUPO, CANAL, COMUNIDADE) if (servico, t) in LIMITES]


def separar_participantes(texto):
    """Lista de enderecos digitados (telefones ou @usuarios), separados por
    virgula, ponto e virgula ou linha, sem repetir nem deixar vazios."""
    vistos, itens = set(), []
    for parte in re.split(r"[,;\n]+", texto or ""):
        parte = parte.strip()
        if parte and parte.lower() not in vistos:
            vistos.add(parte.lower())
            itens.append(parte)
    return itens


def validar(servico, tipo, nome, descricao=""):
    """(nome limpo, descricao limpa, erro). `erro` vazio se pode criar."""
    nome, descricao = (nome or "").strip(), (descricao or "").strip()
    limites = LIMITES.get((servico, tipo))
    de, plural, _ = NOMES.get(tipo, ("disto", "isto", ""))
    if limites is None:
        return nome, descricao, "Esta conta não cria %s." % plural
    if not nome:
        return nome, descricao, "Escreva o nome %s." % de
    if len(nome) > limites[0]:
        return nome, descricao, ("O nome %s passa de %d letras (tem %d)."
                                 % (de, limites[0], len(nome)))
    if len(descricao) > limites[1]:
        return nome, descricao, ("A descrição passa de %d letras (tem %d)."
                                 % (limites[1], len(descricao)))
    return nome, descricao, ""


def texto_pronto(tipo, nome):
    """Frase falada quando a criacao deu certo."""
    return "%s %s criad%s." % (
        {GRUPO: "Grupo", CANAL: "Canal", COMUNIDADE: "Comunidade"}[tipo],
        nome, "a" if tipo == COMUNIDADE else "o")

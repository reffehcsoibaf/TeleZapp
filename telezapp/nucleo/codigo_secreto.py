# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Codigo secreto das conversas trancadas no celular.

O WhatsApp tranca uma conversa atras de um codigo que so o celular conhece.
No TeleZapp o codigo e outro, escolhido aqui: so quem digitar esse codigo no
campo de busca ve as conversas trancadas. Guarda-se so um resumo
(PBKDF2 com sal), nunca o codigo. Sem wx, para testar em qualquer sistema.
"""
import hashlib
import hmac
import os

MIN_DIGITOS = 4
MAX_DIGITOS = 12
ITERACOES = 120_000


def valido(codigo):
    """Codigo com 4 a 12 digitos, so numeros."""
    return isinstance(codigo, str) and codigo.isascii() and \
        codigo.isdigit() and MIN_DIGITOS <= len(codigo) <= MAX_DIGITOS


def _resumo(codigo, sal, iteracoes):
    return hashlib.pbkdf2_hmac("sha256", codigo.encode("ascii"), sal,
                               iteracoes)


def criar(codigo):
    """Dados para guardar no config (nada que revele o codigo)."""
    if not valido(codigo):
        raise ValueError("codigo invalido")
    sal = os.urandom(16)
    return {"sal": sal.hex(), "it": ITERACOES,
            "resumo": _resumo(codigo, sal, ITERACOES).hex()}


def confere(codigo, dados):
    """O texto digitado e o codigo guardado? Falso para qualquer lixo."""
    try:
        if not valido(codigo) or not dados:
            return False
        sal = bytes.fromhex(dados["sal"])
        esperado = bytes.fromhex(dados["resumo"])
        return hmac.compare_digest(
            _resumo(codigo, sal, int(dados["it"])), esperado)
    except (KeyError, TypeError, ValueError):
        return False


def pode_ser_codigo(texto):
    """Vale a pena conferir este texto da busca? (so digitos, tamanho certo;
    evita o custo do resumo a cada letra digitada)."""
    return valido(texto)

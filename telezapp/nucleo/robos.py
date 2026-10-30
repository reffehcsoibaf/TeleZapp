# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Contas pequenas dos robos do Telegram, sem wx nem rede."""
import re

# moedas sem casas decimais; as demais do Telegram usam duas
SEM_CENTAVOS = {"JPY", "KRW", "VND", "CLP", "ISK", "UGX", "PYG", "RWF"}
ESTRELAS = "XTR"


def ler_coordenadas(texto):
    """(latitude, longitude) de "-30.03, -51.22"; None se nao fizer sentido."""
    numeros = re.findall(r"-?\d+(?:[.,]\d+)?", (texto or "").replace(", ", " "))
    if len(numeros) != 2:
        return None
    lat, lon = (float(n.replace(",", ".")) for n in numeros)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


CAMPOS_DE_ENDERECO = (
    ("rua1", "Endereço", True), ("rua2", "Complemento", False),
    ("cidade", "Cidade", True), ("estado", "Estado", False),
    ("pais", "País, em duas letras (como BR)", True),
    ("cep", "CEP ou código postal", True))


def campos_pedidos(pede):
    """[(chave, rotulo, obrigatorio)] do que o vendedor pede. `pede`:
    {'nome', 'telefone', 'email', 'endereco'} verdadeiros ou falsos."""
    campos = []
    if pede.get("nome"):
        campos.append(("nome", "Nome completo", True))
    if pede.get("telefone"):
        campos.append(("telefone", "Telefone", True))
    if pede.get("email"):
        campos.append(("email", "E-mail", True))
    if pede.get("endereco"):
        campos += CAMPOS_DE_ENDERECO
    return campos


def faltando(pede, valores):
    """O rotulo do primeiro campo a corrigir, ou ""."""
    for chave, rotulo, obrigatorio in campos_pedidos(pede):
        valor = (valores.get(chave) or "").strip()
        if obrigatorio and not valor:
            return rotulo
        if chave == "pais" and not re.fullmatch(r"[A-Za-z]{2}", valor):
            return rotulo
    return ""


def preco(moeda, total):
    """O total (na menor unidade da moeda) em texto."""
    if moeda == ESTRELAS:
        return "1 estrela" if total == 1 else "%d estrelas" % total
    if moeda in SEM_CENTAVOS:
        return "%d %s" % (total, moeda)
    return "%.2f %s" % (total / 100, moeda)

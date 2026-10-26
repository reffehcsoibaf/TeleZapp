# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""TeleZapp: cliente de WhatsApp e Telegram para Windows, feito para leitores
de tela."""

import re

NOME = "TeleZapp"
# ano.mes.dia.digito: o ultimo numero sobe quando sai mais de uma versao no
# mesmo dia (2026.10.13.0, 2026.10.13.1...)
VERSAO = "2026.10.26.0"
SITE = "https://github.com/reffehcsoibaf/TeleZapp"
# a pagina do projeto e o formulario de relatos (pasta site/, no GitHub Pages)
PAGINA_DO_PROJETO = "https://reffehcsoibaf.github.io/TeleZapp/"
PAGINA_DE_RELATOS = PAGINA_DO_PROJETO + "relatar.html"


def versao_valida(texto):
    """Formato ano.mes.dia.digito, cabendo nos metadados do Windows (quatro
    numeros de 0 a 65535) e com uma data que existe."""
    import datetime
    if not re.fullmatch(r"\d{4}\.\d{1,2}\.\d{1,2}\.\d+", texto or ""):
        return False
    ano, mes, dia, n = (int(x) for x in texto.split("."))
    if n > 65535:
        return False
    try:
        datetime.date(ano, mes, dia)
    except ValueError:
        return False
    return True

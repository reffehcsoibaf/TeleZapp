# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Os registros da abertura do programa (para achar onde ela demora ou cai)."""
import logging

from telezapp import __main__ as principal


def test_etapa_registra_o_tempo_desde_o_inicio(caplog):
    log = logging.getLogger("telezapp.teste_abertura")
    with caplog.at_level(logging.INFO, logger=log.name):
        principal.etapa(log, "janela mostrada")
    assert "abertura: janela mostrada (" in caplog.text
    assert "s desde o início)" in caplog.text


def test_ambiente_registra_sistema_python_e_pasta_de_dados(caplog):
    log = logging.getLogger("telezapp.teste_abertura")
    with caplog.at_level(logging.INFO, logger=log.name):
        principal.descrever_ambiente(log)
    assert "ambiente:" in caplog.text and "Python" in caplog.text
    assert "dados em" in caplog.text


def test_marca_de_sessao_conta_quando_foi_o_ultimo_sinal(tmp_path):
    marca = tmp_path / "sessao-aberta"
    principal.escrever_marca(str(marca))
    texto = principal.descrever_marca(str(marca))
    assert "O último sinal da vez anterior foi às" in texto
    assert "há 0 min" in texto


def test_marca_antiga_so_com_o_numero_do_processo(tmp_path):
    marca = tmp_path / "sessao-aberta"
    marca.write_text("13620")
    assert "não traz a hora" in principal.descrever_marca(str(marca))

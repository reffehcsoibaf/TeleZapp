# SPDX-License-Identifier: GPL-3.0-or-later
"""Mensagem encaminhada: a marca na linha, nos detalhes, na busca e o que cada
servico diz."""
import types

from telezapp.nucleo import busca, modelos as m
from telezapp.provedores import telegram, whatsapp


def _msg(**extras):
    msg = m.Mensagem(conta_id="c", conversa_id="v", id="1", autor="Ana",
                     data=1700000000.0, texto="oi")
    m.atualizar_extras(msg, **extras)
    return msg


def test_linha_traz_a_marca_encaminhada():
    linha = m.formatar(_msg(encaminhada=True), m.ESTILO_AUTOR_PRIMEIRO)
    assert "(encaminhada)" in linha
    assert "(encaminhada)" not in m.formatar(_msg(), m.ESTILO_AUTOR_PRIMEIRO)


def test_detalhes_dizem_encaminhada():
    linhas = m.detalhes(_msg(encaminhada=True), "Conversa")
    assert "Encaminhada: sim" in linhas


def test_busca_filtra_por_encaminhada():
    assert ("encaminhada", "Encaminhada") in busca.CARACTERISTICAS
    assert busca._caracteristica("encaminhada", _msg(encaminhada=True),
                                 m.extras_de(_msg(encaminhada=True)))


def test_whatsapp_reconhece_o_contexto_encaminhado():
    ctx = types.SimpleNamespace(isForwarded=True, forwardingScore=1)
    assert whatsapp._encaminhada(ctx)
    assert whatsapp._encaminhada(types.SimpleNamespace(
        isForwarded=False, forwardingScore=3))
    assert not whatsapp._encaminhada(types.SimpleNamespace(
        isForwarded=False, forwardingScore=0))
    assert not whatsapp._encaminhada(None)


def test_telegram_marca_quando_tem_fwd_from():
    base = types.SimpleNamespace(id=5, message="oi", out=False, date=None,
                                 fwd_from=object())
    assert m.extras_de(telegram.converter(base, "c", "v"))["encaminhada"]
    base.fwd_from = None
    assert not m.extras_de(telegram.converter(base, "c", "v"))["encaminhada"]

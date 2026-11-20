# SPDX-License-Identifier: GPL-3.0-or-later
"""Ritmo do encaminhamento em lote (protege a conta do WhatsApp): nada e
recusado; o que passa do limite entra numa fila e sai devagar."""
import random

from telezapp.nucleo import ritmo_de_envio as r

WA, TG = "whatsapp", "telegram"


def test_ate_20_envios_nao_pergunta_nada():
    p = r.avaliar(4, [(WA, False)] * 5)
    assert not p.confirmar and p.envios_whatsapp == 20 and p.na_fila == 0


def test_acima_de_20_envios_pergunta_e_diz_quantos_ficam_na_fila():
    p = r.avaliar(5, [(WA, False)] * 5)
    assert p.na_fila == 5 and "25 envios" in p.confirmar
    assert "ficam numa fila" in p.confirmar and "minuto" in p.confirmar
    assert "restringir" in p.confirmar


def test_400_mensagens_nao_sao_recusadas_vao_para_a_fila():
    p = r.avaliar(400, [(WA, False)])
    assert p.na_fila == 380 and "400 envios" in p.confirmar
    assert "horas" in p.confirmar


def test_telegram_nao_entra_na_conta_do_whatsapp():
    p = r.avaliar(100, [(TG, False)] * 10)
    assert not p.confirmar and p.envios_whatsapp == 0
    misto = r.avaliar(10, [(WA, False)] * 3 + [(TG, False)] * 8)
    assert misto.envios_whatsapp == 30 and misto.na_fila == 10


def test_status_conta_nos_envios():
    p = r.avaliar(3, [(WA, False)] * 5 + [(WA, True)])
    assert p.envios_whatsapp == 18


def test_pausa_do_whatsapp_comeca_curta_e_depois_fica_lenta():
    rng = random.Random(1)
    assert all(2 <= r.pausa(WA, 0, rng) <= 5 for _ in range(200))
    assert all(2 <= r.pausa(WA, 19, rng) <= 5 for _ in range(200))
    assert all(10 <= r.pausa(WA, 20, rng) <= 20 for _ in range(200))
    assert all(10 <= r.pausa(WA, 300, rng) <= 20 for _ in range(200))
    assert all(0.5 <= r.pausa(TG, 300, rng) <= 1.5 for _ in range(200))


def test_duracao_estimada():
    assert r.duracao_estimada(5) == "1 minuto"
    assert r.duracao_estimada(20) == "1 minuto"
    assert r.duracao_estimada(60) == "11 minutos"
    assert r.duracao_estimada(400) == "1,6 horas"

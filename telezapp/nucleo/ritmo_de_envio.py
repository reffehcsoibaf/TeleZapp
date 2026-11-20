# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Ritmo do encaminhamento em lote.

O WhatsApp restringe contas que mandam muitas mensagens em rajada (um usuario
foi restrito depois de encaminhar cerca de 400). A Meta nao publica limites;
estes valores sao nossos, bem abaixo do que parece suspeito. Nada e recusado:
os primeiros envios saem logo, com uma pausa curta, e o que passar disso fica
numa fila e sai aos poucos. Ficam fixos aqui, num so lugar.
"""
import random
from dataclasses import dataclass

WHATSAPP = "whatsapp"
WA_RAPIDOS = 20                 # primeiros envios, com a pausa curta
WA_PAUSA = (2.0, 5.0)           # segundos entre envios, no comeco
WA_PAUSA_LENTA = (10.0, 20.0)   # depois dos rapidos: cerca de 4 por minuto
OUTRO_PAUSA = (0.5, 1.5)        # Telegram: o servidor ja manda esperar


@dataclass
class Plano:
    confirmar: str = ""         # pergunta, se precisa de confirmacao
    envios_whatsapp: int = 0
    envios_total: int = 0
    na_fila: int = 0            # os que esperam, saindo devagar


def avaliar(n_itens, destinos):
    """`destinos`: lista de (servico, e_status) dos escolhidos. Cada conversa
    recebe todos os itens; cada status tambem publica todos."""
    wa = sum(1 for s, _status in destinos if s == WHATSAPP) * n_itens
    p = Plano(envios_whatsapp=wa, envios_total=len(destinos) * n_itens,
              na_fila=max(0, wa - WA_RAPIDOS))
    if p.na_fila:
        p.confirmar = (
            "Isso são %d envios pelo WhatsApp. Para não fazer o WhatsApp "
            "restringir a sua conta, os primeiros %d saem logo, com uma "
            "pausa de poucos segundos, e os outros %d ficam numa fila e "
            "saem devagar, cerca de 4 por minuto. No total levam cerca de "
            "%s. Mantenha o TeleZapp aberto (pode ficar em segundo plano). "
            "Continuar?" % (wa, WA_RAPIDOS, p.na_fila, duracao_estimada(wa)))
    return p


def pausa(servico, enviados_whatsapp=0, rng=random):
    """Segundos de espera depois de um envio deste servico, sabendo quantos
    do WhatsApp ja sairam neste lote."""
    if servico != WHATSAPP:
        a, b = OUTRO_PAUSA
    elif enviados_whatsapp >= WA_RAPIDOS:
        a, b = WA_PAUSA_LENTA
    else:
        a, b = WA_PAUSA
    return rng.uniform(a, b)


def duracao_estimada(envios):
    """Texto para a pessoa: cerca de quanto tempo levam `envios` envios do
    WhatsApp."""
    rapidos = min(envios, WA_RAPIDOS)
    segundos = rapidos * sum(WA_PAUSA) / 2 + \
        (envios - rapidos) * sum(WA_PAUSA_LENTA) / 2
    minutos = max(1, round(segundos / 60))
    if minutos == 1:
        return "1 minuto"
    if minutos < 90:
        return "%d minutos" % minutos
    return "%s horas" % ("%.1f" % (minutos / 60)).replace(".", ",")

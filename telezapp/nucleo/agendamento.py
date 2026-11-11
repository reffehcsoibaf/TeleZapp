# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Mensagens agendadas: ler a data e a hora que a pessoa digitou, conferir os
limites do servico e dizer o horario em palavras. Sem wx, para testar em
qualquer sistema.

No Telegram o servidor guarda a mensagem e a envia na hora marcada, mesmo com
o TeleZapp fechado; aqui so se decide quando."""
import re
from datetime import date, datetime, timedelta

# o Telegram nao aceita uma data quase colada em "agora" nem muito distante
MINIMO_SEGUNDOS = 60
# quanto depois da hora o TeleZapp ainda envia sozinho (agenda propria)
TOLERANCIA_SEGUNDOS = 120
MAXIMO_DIAS = 365

DIAS_DA_SEMANA = ("segunda-feira", "terça-feira", "quarta-feira",
                  "quinta-feira", "sexta-feira", "sábado", "domingo")


def _sem_acento(texto):
    return (texto.lower().replace("ã", "a").replace("á", "a")
            .replace("â", "a").replace("é", "e").replace("ê", "e")
            .replace("í", "i").replace("ó", "o").replace("ô", "o")
            .replace("ú", "u").replace("ç", "c"))


def interpretar_data(texto, hoje):
    """A data (date) de "hoje", "amanhã", "dd/mm", "dd/mm/aa" ou
    "dd/mm/aaaa" (tambem com - ou .); None se nao entende. Sem o ano, vale o
    proximo dia com aquele dia e mes (se ja passou neste ano, o do ano
    seguinte)."""
    t = _sem_acento((texto or "").strip())
    if t == "hoje":
        return hoje
    if t == "amanha":
        return hoje + timedelta(days=1)
    if t in ("depois de amanha", "depois"):
        return hoje + timedelta(days=2)
    achou = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{2}|\d{4}))?", t)
    if not achou:
        return None
    dia, mes = int(achou.group(1)), int(achou.group(2))
    ano = achou.group(3)
    try:
        if ano:
            ano = int(ano)
            if ano < 100:
                ano += 2000
            return date(ano, mes, dia)
        candidata = date(hoje.year, mes, dia)
        if candidata < hoje:
            candidata = date(hoje.year + 1, mes, dia)
        return candidata
    except ValueError:
        return None


def interpretar_hora(texto):
    """(hora, minuto) de "hh:mm", "hh.mm", "hh h mm", "hhmm" ou "hh"; None se
    nao entende."""
    t = _sem_acento((texto or "").strip())
    achou = re.fullmatch(r"(\d{1,2})\s*(?:[:.h]\s*(\d{2})?)?\s*(?:h|horas)?", t)
    if achou:
        hora = int(achou.group(1))
        minuto = int(achou.group(2) or 0)
    else:
        achou = re.fullmatch(r"(\d{1,2})(\d{2})", t)
        if not achou:
            return None
        hora, minuto = int(achou.group(1)), int(achou.group(2))
    if 0 <= hora <= 23 and 0 <= minuto <= 59:
        return hora, minuto
    return None


def montar(data_txt, hora_txt, agora):
    """(datetime, "") para a data e a hora digitadas, ou (None, motivo).
    `agora` e um datetime comum (hora local)."""
    dia = interpretar_data(data_txt, agora.date())
    if dia is None:
        return None, ("Não entendi a data. Use, por exemplo, hoje, amanhã ou "
                      "25/12/2026.")
    hm = interpretar_hora(hora_txt)
    if hm is None:
        return None, "Não entendi a hora. Use, por exemplo, 14:30 ou 9."
    quando = datetime(dia.year, dia.month, dia.day, hm[0], hm[1])
    if quando < agora + timedelta(seconds=MINIMO_SEGUNDOS):
        return None, ("Esse horário já passou ou está perto demais. "
                      "Escolha pelo menos um minuto à frente.")
    if quando > agora + timedelta(days=MAXIMO_DIAS):
        return None, "Só dá para agendar até um ano à frente."
    return quando, ""


def sugestao(agora):
    """(data, hora) de partida: a proxima hora cheia, em texto."""
    proxima = (agora.replace(minute=0, second=0, microsecond=0)
               + timedelta(hours=1))
    return proxima.strftime("%d/%m/%Y"), proxima.strftime("%H:%M")


def descricao(quando, agora):
    """"hoje às 15:00", "amanhã às 09:00", "quinta-feira, 12/11/2026 às
    09:00"; so a data se for a mais de uma semana."""
    hora = quando.strftime("%H:%M")
    dias = (quando.date() - agora.date()).days
    if dias == 0:
        return "hoje às %s" % hora
    if dias == 1:
        return "amanhã às %s" % hora
    data = quando.strftime("%d/%m/%Y")
    if 0 < dias < 7:
        return "%s, %s às %s" % (DIAS_DA_SEMANA[quando.weekday()], data, hora)
    return "%s às %s" % (data, hora)


def linha(texto, quando, agora, limite=120, atrasada=False):
    """A linha da mensagem na lista de agendadas."""
    corpo = " ".join((texto or "").split()) or "(mensagem sem texto)"
    if len(corpo) > limite:
        corpo = corpo[:limite].rstrip() + "..."
    marca = " (passou da hora, não enviada)" if atrasada else ""
    return "%s%s: %s" % (descricao(quando, agora), marca, corpo)

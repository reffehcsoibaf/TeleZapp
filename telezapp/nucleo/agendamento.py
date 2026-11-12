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
    if t.isdigit():
        return _data_so_com_numeros(t, hoje)
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


def _data_so_com_numeros(t, hoje):
    """A data de uma sequencia de numeros: 1 ou 2 digitos sao o dia (neste
    mes, ou no proximo se ja passou), 4 sao ddmm, 6 sao ddmmaa e 8 sao
    ddmmaaaa. Outros tamanhos sao ambiguos (112 pode ser 1/12 ou 11/2):
    None."""
    try:
        if len(t) <= 2:
            dia = int(t)
            ano, mes = hoje.year, hoje.month
            for _ in range(13):
                try:
                    candidata = date(ano, mes, dia)
                except ValueError:
                    candidata = None
                if candidata is not None and candidata >= hoje:
                    return candidata
                mes += 1
                if mes > 12:
                    ano, mes = ano + 1, 1
            return None
        if len(t) not in (4, 6, 8):
            return None
        dia, mes = int(t[:2]), int(t[2:4])
        if len(t) == 4:
            candidata = date(hoje.year, mes, dia)
            if candidata < hoje:
                candidata = date(hoje.year + 1, mes, dia)
            return candidata
        ano = int(t[4:])
        return date(ano + 2000 if ano < 100 else ano, mes, dia)
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
        return None, ("Não entendi a data. Use, por exemplo, hoje, amanhã, "
                      "25/12/2026 ou só os números, como 25122026.")
    hm = interpretar_hora(hora_txt)
    if hm is None:
        return None, ("Não entendi a hora. Use, por exemplo, 14:30, 1430 "
                      "ou 9.")
    quando = datetime(dia.year, dia.month, dia.day, hm[0], hm[1])
    if quando < agora + timedelta(seconds=MINIMO_SEGUNDOS):
        return None, ("Esse horário já passou ou está perto demais. "
                      "Escolha pelo menos um minuto à frente.")
    if quando > agora + timedelta(days=MAXIMO_DIAS):
        return None, "Só dá para agendar até um ano à frente."
    return quando, ""


def data_falada(dia, hoje):
    """"amanhã, quinta-feira, 12/11/2026": como a data nova e dita ao
    mudar com as setas."""
    base = "%s, %s" % (DIAS_DA_SEMANA[dia.weekday()],
                       dia.strftime("%d/%m/%Y"))
    dias = (dia - hoje).days
    if dias == 0:
        return "hoje, " + base
    if dias == 1:
        return "amanhã, " + base
    return base


def mudar_data(texto, direcao, grande, hoje):
    """(texto da data nova, como dizer) ao apertar seta para cima (direcao 1)
    ou para baixo (-1); `grande` (Page Up e Page Down) anda uma semana. Parte
    do que esta digitado (ou de hoje) e fica entre hoje e um ano a frente."""
    base = interpretar_data(texto, hoje) or hoje
    nova = base + timedelta(days=direcao * (7 if grande else 1))
    nova = max(hoje, min(nova, hoje + timedelta(days=MAXIMO_DIAS)))
    return nova.strftime("%d/%m/%Y"), data_falada(nova, hoje)


PASSO_DA_HORA = 15


def mudar_hora(texto, direcao, grande, agora):
    """(hh:mm novo, o mesmo para dizer) ao apertar seta para cima (1) ou para
    baixo (-1): anda para o proximo quarto de hora (ou uma hora, com
    `grande`) e da a volta nas 24 horas. Sem hora valida, parte da atual."""
    hm = interpretar_hora(texto) or (agora.hour, agora.minute)
    total = hm[0] * 60 + hm[1]
    if grande:
        total += direcao * 60
    elif direcao > 0:
        total = (total // PASSO_DA_HORA + 1) * PASSO_DA_HORA
    else:
        total = ((total + PASSO_DA_HORA - 1) // PASSO_DA_HORA - 1) \
            * PASSO_DA_HORA
    total %= 24 * 60
    novo = "%02d:%02d" % (total // 60, total % 60)
    return novo, novo


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


def com_midia(rotulo, legenda="", nome=""):
    """O texto de uma agendada com arquivo na lista: "foto (a.jpg): legenda"."""
    base = "%s (%s)" % (rotulo, nome) if nome else rotulo
    legenda = " ".join((legenda or "").split())
    return "%s: %s" % (base, legenda) if legenda else base


def linha(texto, quando, agora, limite=120, atrasada=False):
    """A linha da mensagem na lista de agendadas."""
    corpo = " ".join((texto or "").split()) or "(mensagem sem texto)"
    if len(corpo) > limite:
        corpo = corpo[:limite].rstrip() + "..."
    marca = " (passou da hora, não enviada)" if atrasada else ""
    return "%s%s: %s" % (descricao(quando, agora), marca, corpo)

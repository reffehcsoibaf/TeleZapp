# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Textos do menu Depurar: tudo que o TeleZapp sabe sobre uma mensagem ou
uma conversa, em texto simples para ler, copiar e colar num relato."""
import json
import time
from dataclasses import asdict
from collections import Counter

from telezapp.nucleo import modelos as m

AVISO = ("Este texto contém mensagens e telefones. Não contém senhas nem "
         "chaves de acesso. Confira antes de compartilhar.")


def _json(x):
    return json.dumps(x, ensure_ascii=False, indent=2, default=str)


def _data(t):
    try:
        return time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(t))
    except (OverflowError, OSError, ValueError):
        return str(t)


def texto_mensagem(msg, conversa=None, bruto="", recibos=(), versao="",
                   modo_ligado=False):
    """Depuracao de uma mensagem. `bruto` e a estrutura original guardada
    (JSON em texto), ou '' se nao ha."""
    campos = asdict(msg)
    campos["extras"] = m.extras_de(msg)
    campos["data"] = "%s (%s)" % (msg.data, _data(msg.data))
    linhas = ["DEPURAÇÃO DE MENSAGEM", AVISO, "TeleZapp " + versao, "",
              "== Conversa ==",
              _json(asdict(conversa)) if conversa is not None else
              "(conversa não encontrada na lista)", "",
              "== Mensagem como o TeleZapp guardou ==", _json(campos)]
    if recibos:
        linhas += ["", "== Recibos (quem, estado, quando) ==",
                   _json([[q, e, _data(t)] for q, e, t in recibos])]
    linhas += ["", "== Estrutura original do serviço =="]
    if bruto:
        linhas.append(bruto)
    elif modo_ligado:
        linhas.append("Não guardada: esta mensagem chegou antes de o modo de "
                      "depuração ser ligado, ou o serviço não oferece.")
    else:
        linhas.append("Não guardada. Ligue o Modo de depuração no menu "
                      "Depurar; vale para as mensagens que chegarem depois.")
    return "\n".join(linhas)


def texto_conversa(conversa, mensagens, dados_servico=None, versao="",
                   ultimas=20):
    """Depuracao de uma conversa: seus campos, como o servico a identificou
    e um resumo das mensagens carregadas."""
    tipos = Counter(x.tipo for x in mensagens)
    linhas = ["DEPURAÇÃO DE CONVERSA", AVISO, "TeleZapp " + versao, "",
              "== Conversa como o TeleZapp guardou ==",
              _json(asdict(conversa)), "",
              "== O que o serviço informa ==",
              _json(dados_servico) if dados_servico else "(nada)", "",
              "== Mensagens carregadas: %d ==" % len(mensagens),
              _json(dict(tipos))]
    sem_texto = [x for x in mensagens if x.tipo == m.OUTRO]
    if sem_texto:
        linhas.append("Sem suporte ainda: %d" % len(sem_texto))
    linhas += ["", "== Últimas %d mensagens (id, tipo, de, quando, texto) =="
               % min(ultimas, len(mensagens))]
    for x in mensagens[-ultimas:]:
        linhas.append("%s | %s | %s | %s | %s" % (
            x.id, x.tipo, "eu" if x.minha else (x.remetente or x.autor or "?"),
            _data(x.data), (x.texto or "").replace("\n", " ")[:120]))
    return "\n".join(linhas)

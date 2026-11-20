# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Informações de uso, opcionais: só números e nomes de recursos, nunca
conteúdo. Veja docs/decisoes.md (19/11/2026). Sem wx.

O que vai: versão, sistema, leitor de tela, quantas contas por serviço,
quantidade de conversas em faixa, quais recursos experimentais estão ligados,
tempos (abertura, F5), tratadores da janela que passaram de 0,2 s (nome e
tempo), quantas vezes cada tratador deu erro (só o nome do tratador), quedas
de conexão por serviço e causa, quantos avisos e erros o registro teve por
módulo (só a contagem, nunca o texto), resultado da conferência do banco ao
abrir (estado, tempo, faixa de tamanho), tipo do disco dos dados, se a vez
anterior terminou sem fechar e versões do Python e das bibliotecas. Nada de
mensagens, nomes, telefones, ids de conversa, caminhos, textos de erro ou
logs. Só envia com a caixa "Compartilhar informações de uso" marcada, no
máximo uma vez por dia, em segundo plano e sem nunca avisar de falha.
"""
import atexit
import json
import logging
import os
import platform
import re
import sys
import threading
import time
import urllib.request
import uuid

from telezapp import VERSAO, config

log = logging.getLogger("telezapp.uso")

ENDERECO = "https://telezapp.fabioscheffer.workers.dev/uso"
INTERVALO_S = 20 * 3600          # um resumo por dia, com folga
MAX_TRATADORES = 30              # os mais lentos/errados; o resto some
INICIO = time.time()             # quando o módulo foi importado (abertura)

_trava = threading.Lock()
_lentos = {}      # nome do tratador -> [vezes, pior tempo em s]
_erros = {}       # nome do tratador -> vezes
_tempos = {}      # "f5" -> último tempo em s
_contagens = {}   # grupo -> {nome: vezes} (quedas, registro...)
_fatos = {}       # dados únicos desta abertura (banco, queda anterior...)
_chamadas = []    # um registro por chamada (nucleo/uso_chamadas.py)
MAX_CHAMADAS_GUARDADAS = 100     # na memória e no arquivo
MAX_CHAMADAS_POR_ENVIO = 10      # a amostra de cada resumo
RESULTADOS_DE_FALHA = frozenset({"sem_som", "falha"})


def registrar_lento(nome, segundos):
    with _trava:
        v = _lentos.setdefault(nome, [0, 0.0])
        v[0] += 1
        v[1] = max(v[1], segundos)


def registrar_erro(nome):
    with _trava:
        _erros[nome] = _erros.get(nome, 0) + 1


def registrar_tempo(nome, segundos):
    with _trava:
        _tempos[nome] = round(segundos, 2)


def registrar_chamada(registro):
    """Guarda o registro de uma chamada que terminou (so categorias e
    numeros; ver nucleo/uso_chamadas.py)."""
    with _trava:
        _chamadas.append(dict(registro))
        del _chamadas[:-MAX_CHAMADAS_GUARDADAS]


def amostra_de_chamadas(chamadas):
    """Ate MAX_CHAMADAS_POR_ENVIO registros, com as falhas na frente (senao
    a amostra seria so de chamadas boas) e, dentro de cada grupo, as mais
    recentes."""
    ordem = sorted(range(len(chamadas)), key=lambda i: (
        chamadas[i].get("resultado") not in RESULTADOS_DE_FALHA, -i))
    return [chamadas[i] for i in ordem[:MAX_CHAMADAS_POR_ENVIO]]


def contar(grupo, chave, n=1):
    """Conta um acontecimento (ex.: contar("quedas", "whatsapp")). So nomes
    escritos pelo programa, nunca texto vindo de fora."""
    chave = re.sub(r"[^a-zA-Z0-9_]", "_", str(chave))[:60] or "_"
    with _trava:
        g = _contagens.setdefault(grupo, {})
        g[chave] = g.get(chave, 0) + n


def registrar_fato(nome, valor):
    """Um dado unico desta abertura (estado do banco, queda anterior...)."""
    with _trava:
        _fatos[nome] = valor


# O registro das chamadas feito no Go chega aqui sempre como WARNING, mesmo
# sendo so informacao (3293 linhas assim num log real): nao diz nada de erro.
SEM_CONTAGEM = frozenset({"whatsmeow.Client.Chamadas"})


class ContadorDeRegistro(logging.Handler):
    """Conta avisos e erros do registro (log) por modulo e nivel. Guarda so o
    nome do modulo e o nivel: o texto da mensagem nunca e lido."""

    def emit(self, registro):
        try:
            if registro.levelno < logging.WARNING:
                return
            nome = registro.name
            if nome in SEM_CONTAGEM:
                return
            if nome.startswith("telezapp."):
                nome = nome[len("telezapp."):]
            nivel = "erro" if registro.levelno >= logging.ERROR else "aviso"
            contar("registro", "%s_%s" % (nome, nivel))
        except Exception:
            pass


_contador_instalado = False


def instalar_contador_de_registro():
    global _contador_instalado
    if not _contador_instalado:
        logging.getLogger().addHandler(ContadorDeRegistro())
        _contador_instalado = True


def _versao_de(pacote):
    try:
        from importlib import metadata
        return metadata.version(pacote)
    except Exception:
        return ""


def _ambiente():
    try:
        import wx
        versao_wx = wx.version().split()[0]
    except Exception:
        versao_wx = ""
    return {
        "python": platform.python_version(),
        "arquitetura": platform.machine(),
        "cpus": os.cpu_count() or 0,
        "wx": versao_wx,
        "neonize": _versao_de("neonize"),
        "telethon": _versao_de("telethon"),
    }


def faixa(n):
    """Quantidade aproximada: nunca o número exato."""
    for limite, texto in ((1, "0"), (50, "1 a 49"), (200, "50 a 199"),
                          (1000, "200 a 999"), (3000, "1000 a 2999"),
                          (10000, "3000 a 9999")):
        if n < limite:
            return texto
    return "10000 ou mais"


def _arquivo():
    return os.path.join(config.pasta_dados(), "uso-pendente.json")


def guardar_pendente():
    """Grava as medidas em andamento na pasta de dados, para a próxima
    abertura enviá-las (elas só existem na memória; sem isto, o que aconteceu
    durante o uso se perderia ao fechar). Sem medidas, apaga o arquivo."""
    with _trava:
        dados = {"lentos": {k: list(v) for k, v in _lentos.items()},
                 "erros": dict(_erros), "tempos": dict(_tempos),
                 "contagens": {g: dict(v) for g, v in _contagens.items()},
                 "chamadas": list(_chamadas)}
    vazio = not (dados["lentos"] or dados["erros"] or dados["tempos"]
                 or dados["contagens"] or dados["chamadas"])
    caminho = _arquivo()
    try:
        if vazio:
            if os.path.exists(caminho):
                os.remove(caminho)
            return
        provisorio = caminho + ".tmp"
        with open(provisorio, "w", encoding="utf-8") as f:
            json.dump(dados, f)
        os.replace(provisorio, caminho)
    except OSError as e:
        log.info("medidas de uso não gravadas: %r", e)


def carregar_pendente():
    """Soma às medidas atuais as que a(s) vez(es) anterior(es) deixou."""
    caminho = _arquivo()
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
        os.remove(caminho)
    except (OSError, ValueError):
        return
    try:
        with _trava:
            for k, v in dados.get("lentos", {}).items():
                atual = _lentos.setdefault(k, [0, 0.0])
                atual[0] += int(v[0])
                atual[1] = max(atual[1], float(v[1]))
            for k, v in dados.get("erros", {}).items():
                _erros[k] = _erros.get(k, 0) + int(v)
            for k, v in dados.get("tempos", {}).items():
                _tempos.setdefault(k, v)
            antigas = [c for c in dados.get("chamadas", [])
                       if isinstance(c, dict)]
            _chamadas[:0] = antigas
            del _chamadas[:-MAX_CHAMADAS_GUARDADAS]
            for g, c in dados.get("contagens", {}).items():
                alvo = _contagens.setdefault(g, {})
                for k, v in c.items():
                    alvo[k] = alvo.get(k, 0) + int(v)
    except (TypeError, ValueError, IndexError, AttributeError):
        log.info("medidas de uso da vez anterior ilegíveis; ignoradas")


_gravador_ligado = False


def iniciar_gravacao(cfg, a_cada_s=120):
    """Com a caixa marcada, guarda as medidas de tempos em tempos e ao
    fechar. Sem a caixa, nada é gravado."""
    global _gravador_ligado
    if _gravador_ligado or not cfg.get("compartilhar_uso"):
        return
    _gravador_ligado = True

    def laco():
        while True:
            time.sleep(a_cada_s)
            if cfg.get("compartilhar_uso"):
                guardar_pendente()
    threading.Thread(target=laco, daemon=True, name="uso-gravacao").start()
    atexit.register(lambda: cfg.get("compartilhar_uso")
                    and guardar_pendente())


def faixa_mb(mb):
    for limite, texto in ((50, "menos de 50 MB"), (200, "50 a 199 MB"),
                          (1000, "200 a 999 MB"), (5000, "1000 a 4999 MB")):
        if mb < limite:
            return texto
    return "5000 MB ou mais"


def registrar_banco(estado, segundos, bytes_):
    """Resultado da conferência do banco ao abrir. Se houver mais de um
    arquivo, o com defeito (ou o primeiro) é o que fica."""
    with _trava:
        atual = _fatos.get("banco")
        if atual and (atual.get("estado") != "ok" or estado == "ok"):
            return
        _fatos["banco"] = {"estado": estado, "s": round(segundos, 1),
                           "tamanho": faixa_mb(bytes_ / 1048576)}


def id_anonimo(cfg):
    """Sorteado na primeira vez; não tem ligação com conta nem número."""
    ident = cfg.get("uso_id")
    if not ident:
        ident = uuid.uuid4().hex
        cfg.set("uso_id", ident)
    return ident


def _sistema():
    try:
        build = sys.getwindowsversion().build
    except AttributeError:
        build = 0
    return "%s %s (build %s)" % (platform.system(), platform.release(), build)


def montar(cfg, conversas=0, leitor=""):
    """O resumo que seria enviado (um dict que vira JSON)."""
    contas = {}
    for c in cfg.contas():
        s = c.get("servico", "")
        if s in ("whatsapp", "telegram"):
            contas[s] = contas.get(s, 0) + 1
    experimentais = sorted(
        o.chave for o in config.OPCOES
        if o.categoria == config.CATEGORIA_EXPERIMENTAL and not o.escolhas
        and cfg.get(o.chave) is True)
    with _trava:
        lentos = dict(sorted(_lentos.items(), key=lambda x: -x[1][0])
                      [:MAX_TRATADORES])
        erros = dict(sorted(_erros.items(), key=lambda x: -x[1])
                     [:MAX_TRATADORES])
        tempos = dict(_tempos)
        contagens = {g: dict(sorted(v.items(), key=lambda x: -x[1])
                             [:MAX_TRATADORES])
                     for g, v in _contagens.items()}
        fatos = dict(_fatos)
        chamadas = amostra_de_chamadas(_chamadas)
    return {
        "chamadas": chamadas,
        "ambiente": _ambiente(),
        "quedas": contagens.get("quedas", {}),
        "causas_de_queda": contagens.get("causas_de_queda", {}),
        "registro": contagens.get("registro", {}),
        "banco": fatos.get("banco", {}),
        "disco": fatos.get("disco", ""),
        "fechou_sem_fechar": bool(fatos.get("fechou_sem_fechar", False)),
        "versao": VERSAO,
        "id": id_anonimo(cfg),
        "sistema": _sistema(),
        "empacotado": bool(getattr(sys, "frozen", False)),
        "leitor": leitor or "",
        "contas": contas,
        "conversas": faixa(conversas),
        "experimentais": experimentais,
        "abertura_s": tempos.pop("abertura", 0),
        "tempos": tempos,
        "lentos": {k: {"n": v[0], "max_s": round(v[1], 2)}
                   for k, v in lentos.items()},
        "erros": erros,
    }


def texto_para_ver(dados):
    """O que seria enviado, em frases para ler com o leitor de tela, mais o
    JSON exato no fim."""
    linhas = [
        "Estas são as informações que o TeleZapp enviaria, no máximo uma vez "
        "por dia. Não vai nenhuma mensagem, nome, telefone, arquivo nem "
        "registro (log).",
        "As medidas de uso (tempos, quedas, ações lentas, erros) se acumulam "
        "enquanto você usa o programa e são enviadas na abertura seguinte. "
        "Logo depois de abrir, várias aparecem vazias ou ainda não medidas.",
        "",
        "Versão do programa: %s" % dados["versao"],
        "Sistema: %s%s" % (dados["sistema"], ", programa instalado"
                           if dados["empacotado"] else ", rodando do código"),
        "Leitor de tela: %s" % (dados["leitor"] or "nenhum"),
        "Contas: %s" % (", ".join("%d de %s" % (n, s) for s, n in
                                  dados["contas"].items()) or "nenhuma"),
        "Quantidade de conversas (faixa): %s" % dados["conversas"],
        "Recursos experimentais ligados: %s" % (
            ", ".join(dados["experimentais"]) or "nenhum"),
        "Tempo de abertura: %s" % (
            "%s s" % dados["abertura_s"] if dados["abertura_s"] else "ainda "
            "não medido"),
    ]
    for nome, s in dados["tempos"].items():
        linhas.append("Tempo de %s: %s s" % (nome, s))
    linhas.append("Ações da janela que demoraram mais de 0,2 s: %s" % (
        "; ".join("%s, %d vezes, pior %s s" % (k, v["n"], v["max_s"])
                  for k, v in dados["lentos"].items()) or "nenhuma"))
    linhas.append("Ações da janela que deram erro: %s" % (
        "; ".join("%s, %d vezes" % x for x in dados["erros"].items())
        or "nenhuma"))
    cham = dados.get("chamadas") or []
    linhas.append("Chamadas (uma amostra de até %d, as com problema na "
                  "frente; nunca vão nomes, números, ids nem os relays): "
                  "%s" % (MAX_CHAMADAS_POR_ENVIO,
                          "%d registros, listados no texto exato abaixo" %
                          len(cham) if cham else "nenhuma"))
    for c in cham:
        linhas.append("  - %s, %s%s, %s, resultado %s%s%s" % (
            c.get("servico", "?"), c.get("direcao", "?"),
            ", em grupo" if c.get("grupo") else "", c.get("tipo", "?"),
            c.get("resultado", "?"),
            ", quem liga: %s %s" % (c["plataforma"], c.get("versao_wa", ""))
            if c.get("plataforma") else "",
            ", codec %s" % c["codec"] if c.get("codec") else ""))
    amb = dados.get("ambiente", {})
    linhas.append("Programas usados: Python %s, wxPython %s, neonize %s, "
                  "Telethon %s; processador %s com %s núcleos" % (
                      amb.get("python") or "?", amb.get("wx") or "?",
                      amb.get("neonize") or "?", amb.get("telethon") or "?",
                      amb.get("arquitetura") or "?", amb.get("cpus") or "?"))
    linhas.append("Quedas de conexão desde o último envio: %s" % (
        "; ".join("%s, %d" % x for x in dados.get("quedas", {}).items())
        or "nenhuma"))
    linhas.append("Causa das quedas do WhatsApp: %s" % (
        "; ".join("%s, %d" % x
                  for x in dados.get("causas_de_queda", {}).items())
        or "nenhuma"))
    linhas.append("Avisos e erros do registro, só a contagem por módulo, sem "
                  "o texto: %s" % (
                      "; ".join("%s, %d" % x
                                for x in dados.get("registro", {}).items())
                      or "nenhum"))
    b = dados.get("banco") or {}
    linhas.append("Conferência do banco ao abrir: %s" % (
        "%s em %s s, tamanho %s" % (b.get("estado"), b.get("s"),
                                    b.get("tamanho"))
        if b else "ainda não feita"))
    linhas.append("Disco dos dados: %s" % (dados.get("disco") or
                                         "interno ou desconhecido"))
    linhas.append("A vez anterior terminou sem fechar normalmente: %s" % (
        "sim" if dados.get("fechou_sem_fechar") else "não"))
    linhas.append("Identificador anônimo desta instalação (sorteado, sem "
                  "ligação com contas ou números): %s" % dados["id"])
    linhas += ["", "Texto exato enviado:",
               json.dumps(dados, ensure_ascii=False, indent=1)]
    return "\n".join(linhas)


# Quem sai da pergunta com Esc nao disse nem sim nem nao: a pergunta volta
# quando sai uma versao nova, mas nao antes deste prazo (saem versoes quase
# todo dia). Quem toca em "Nao compartilhar" nao e perguntado de novo.
ESPERA_ENTRE_PERGUNTAS_S = 7 * 24 * 3600


def devo_perguntar(cfg, agora=None):
    if cfg.get("compartilhar_uso") or cfg.get("uso_resposta") in ("sim",
                                                                  "nao"):
        return False
    if cfg.get("uso_versao_perguntada") == VERSAO:
        return False
    ultima = float(cfg.get("uso_pergunta_em") or 0)
    return (agora or time.time()) - ultima >= ESPERA_ENTRE_PERGUNTAS_S


def registrar_pergunta(cfg, resposta, agora=None):
    """resposta: "sim", "nao" ou "depois" (Esc ou fechar a janela)."""
    cfg.set("uso_versao_perguntada", VERSAO)
    cfg.set("uso_pergunta_em", agora or time.time())
    if resposta == "sim":
        cfg.set("compartilhar_uso", True)
        cfg.set("uso_resposta", "sim")
    elif resposta == "nao":
        cfg.set("uso_resposta", "nao")


def devido(cfg, agora=None):
    return bool(cfg.get("compartilhar_uso")) and \
        (agora or time.time()) - float(cfg.get("uso_ultimo_envio") or 0) \
        >= INTERVALO_S


def _enviar(dados):
    corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
    pedido = urllib.request.Request(
        ENDERECO, data=corpo, method="POST",
        headers={"Content-Type": "application/json",
                 "User-Agent": "TeleZapp/" + VERSAO})
    with urllib.request.urlopen(pedido, timeout=15) as r:
        if not 200 <= r.status < 300:
            return False
        # so vale o "ok" do nosso Worker: um servidor que responde 200 a
        # qualquer endereco (como o Worker antigo, sem a rota /uso) nao
        # recebeu nada, e o dia nao pode contar como enviado
        try:
            return json.loads(r.read(2000).decode("utf-8")).get("ok") is True
        except (ValueError, AttributeError):
            return False


def enviar_em_segundo_plano(cfg, dados):
    """Manda o resumo sem atrasar nada. Falha só vai ao registro; só zera as
    medidas e marca o dia quando o servidor aceitou."""
    def trabalho():
        try:
            if _enviar(dados):
                with _trava:
                    _lentos.clear()
                    _erros.clear()
                    _tempos.clear()
                    _contagens.clear()
                    _chamadas.clear()
                    _fatos.pop("fechou_sem_fechar", None)
                guardar_pendente()      # apaga o arquivo: ja foi enviado
                cfg.set("uso_ultimo_envio", time.time())
                log.info("informações de uso enviadas")
        except Exception as e:
            log.info("informações de uso não enviadas: %r", e)
    threading.Thread(target=trabalho, daemon=True, name="uso").start()

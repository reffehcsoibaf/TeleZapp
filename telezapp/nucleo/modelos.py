# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Formato comum aos dois servicos (conta, conversa, mensagem) e o texto que
o leitor de tela fala para cada item. Sem dependencia de wxPython."""
import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass

SERVICOS = {"telegram": "Telegram", "whatsapp": "WhatsApp"}

# Tipos de mensagem
TEXTO, FOTO, VIDEO, VOZ, AUDIO, DOCUMENTO, FIGURINHA, OUTRO = (
    "texto", "foto", "video", "voz", "audio", "documento", "figurinha",
    "outro")
# Marca de lugar de uma mensagem que o WhatsApp avisou mas nao conseguiu
# entregar (nao decifrada); a mensagem de verdade, com o mesmo id, a substitui
AGUARDANDO = "aguardando"
NOMES_TIPOS = {
    TEXTO: "texto", FOTO: "foto", VIDEO: "vídeo", VOZ: "mensagem de voz",
    AUDIO: "áudio", DOCUMENTO: "documento", FIGURINHA: "figurinha",
    OUTRO: "mensagem sem suporte ainda",
    AGUARDANDO: "mensagem ainda não recebida",
}

# Estados de uma mensagem enviada
ENVIANDO, ENVIADA, ENTREGUE, LIDA, FALHOU, REPRODUZIDA = (
    "enviando", "enviada", "entregue", "lida", "falhou", "reproduzida")
# ordem de avanco: um estado nunca volta para um anterior (reproduzida: voz,
# audio ou video que a outra pessoa tocou)
ORDEM_ESTADOS = {ENVIANDO: 0, ENVIADA: 1, ENTREGUE: 2, LIDA: 3,
                 REPRODUZIDA: 4}

# Estilos de leitura da lista de mensagens
ESTILO_AUTOR_PRIMEIRO = 1
ESTILO_CONTEUDO_PRIMEIRO = 2
ESTILO_AUTOR_SO_QUANDO_MUDA = 3
NOMES_ESTILOS = {
    ESTILO_AUTOR_PRIMEIRO: "Autor e hora primeiro",
    ESTILO_CONTEUDO_PRIMEIRO: "Conteúdo primeiro",
    ESTILO_AUTOR_SO_QUANDO_MUDA: "Autor só quando muda",
}


@dataclass
class Conta:
    id: str
    servico: str
    telefone: str = ""
    nome: str = ""


@dataclass
class Conversa:
    conta_id: str
    id: str
    nome: str
    servico: str = "telegram"
    tipo: str = "privada"      # privada, grupo, canal
    nao_lidas: int = 0
    data: float = 0.0          # momento da ultima mensagem (timestamp)
    lidas_ate: int = 0         # Telegram: ultima msg minha lida pelo outro
    arquivada: bool = False    # arquivada no servico (so no filtro Arquivadas)
    trancada: bool = False     # WhatsApp: "Trancar conversa" do celular
    fixada: bool = False       # fixada no topo da lista
    silenciada_ate: float = 0.0   # 0 = com som; -1 = para sempre; senao ate
                                  # quando (timestamp)
    somente_leitura: bool = False  # a conta nao pode escrever aqui (canal,
                                   # grupo so de admins, grupo que saiu...)
    temporaria_s: int = 0      # mensagens temporarias: segundos ate sumirem
                               # (0 = desligado)
    citacoes: int = 0          # grupo: das nao lidas, quantas me mencionam ou
                               # respondem a mim (so as que chegaram ao vivo)

    @property
    def chave(self):
        return (self.conta_id, self.id)

    def contar_nova(self, cita_voce=False):
        """Chegou uma mensagem dos outros. A contagem de citacoes recomeca
        quando nao havia nada por ler (as antigas ja foram lidas)."""
        if self.nao_lidas <= 0:
            self.citacoes = 0
        self.nao_lidas += 1
        if cita_voce:
            self.citacoes += 1

    def tem_citacao_nao_lida(self):
        """Ha mensagem nao lida me mencionando ou respondendo a mim?"""
        return min(self.citacoes, self.nao_lidas) > 0

    def silenciada(self, agora=None):
        """Em silencio agora? (o silencio com hora marcada expira sozinho)"""
        ate = self.silenciada_ate
        if ate == 0:
            return False
        return ate < 0 or ate > (agora if agora is not None else time.time())


@dataclass
class Mensagem:
    conta_id: str
    conversa_id: str
    id: str
    autor: str = ""
    minha: bool = False
    data: float = 0.0
    tipo: str = TEXTO
    texto: str = ""
    segundos: int = 0
    nome_arquivo: str = ""
    tamanho: int = 0
    estado: str = ""
    resposta_a: str = ""       # id da mensagem respondida
    remetente: str = ""        # WhatsApp: jid de quem enviou (para "lida")
    extras: str = ""           # JSON: links, botoes e mencoes (ver extras_de)
    expira: float = 0.0        # mensagem temporaria: quando some (timestamp);
                               # 0 = nao some

    @property
    def chave(self):
        return (self.conta_id, self.conversa_id, self.id)


# ------------------------------------------------- mensagens temporarias
# Periodos que cada servico oferece, em segundos (0 = desligadas).
PERIODOS_TEMPORARIAS = {
    "whatsapp": ((0, "Desligadas"), (86400, "24 horas"),
                 (604800, "7 dias"), (7776000, "90 dias")),
    "telegram": ((0, "Desligadas"), (86400, "1 dia"), (604800, "1 semana"),
                 (2678400, "1 mês")),
}


def texto_periodo(segundos, servico=None):
    """86400 -> "24 horas" (WhatsApp) ou "1 dia" (Telegram); 604800 -> "7
    dias"; 2678400 -> "1 mês"... Sem servico, vale o nome do WhatsApp."""
    s = int(segundos or 0)
    if s <= 0:
        return "desligadas"
    proprios = PERIODOS_TEMPORARIAS.get(servico, ())[1:]
    for valor, rotulo in (proprios + PERIODOS_TEMPORARIAS["whatsapp"][1:] +
                          PERIODOS_TEMPORARIAS["telegram"][1:]):
        if s == valor:
            return rotulo
    if s % 86400 == 0:
        d = s // 86400
        return "1 dia" if d == 1 else "%d dias" % d
    if s % 3600 == 0:
        h = s // 3600
        return "1 hora" if h == 1 else "%d horas" % h
    if s % 60 == 0:
        mi = s // 60
        return "1 minuto" if mi == 1 else "%d minutos" % mi
    return "%d segundos" % s


def periodos_temporarias(servico):
    return PERIODOS_TEMPORARIAS.get(servico, PERIODOS_TEMPORARIAS["telegram"])


def texto_temporaria(msg, agora=None):
    """"temporária, some hoje às 14:30" numa mensagem que tem prazo; "" nas
    outras."""
    if not getattr(msg, "expira", 0):
        return ""
    quando = hora_legivel(msg.expira, agora)
    if not quando:
        return "temporária"
    if quando.startswith("ontem "):
        quando = "ontem às " + quando[6:]
    elif len(quando) == 5:
        quando = "hoje às " + quando
    elif len(quando) > 5 and quando[2] == "/" and " " in quando:
        dia, hm = quando.split(" ", 1)
        quando = "em %s às %s" % (dia, hm)
    else:
        quando = "em " + quando
    agora = time.time() if agora is None else agora
    if msg.expira <= agora:
        return "temporária, já passou do prazo"
    return "temporária, some " + quando


def expira_em(data, segundos):
    """Quando uma mensagem de `data` com prazo de `segundos` some."""
    segundos = int(segundos or 0)
    return float(data) + segundos if segundos > 0 and data else 0.0


# ---------------------------------------------------- links, botoes, mencoes
def extras_de(msg):
    """{'links': [[endereco, texto]], 'botoes': [[rotulo, endereco]],
    'mencoes': [{'nome', 'usuario', 'id', 'telefone'}],
    'acoes': [{'tipo', 'rotulo', 'id', 'indice', 'descricao'}]} da mensagem; as
    chaves que nao existem vem como lista vazia."""
    try:
        dados = json.loads(msg.extras) if msg.extras else {}
    except ValueError:
        dados = {}
    if not isinstance(dados, dict):
        dados = {}
    return {"links": list(dados.get("links") or []),
            "botoes": list(dados.get("botoes") or []),
            "mencoes": list(dados.get("mencoes") or []),
            "acoes": list(dados.get("acoes") or []),
            "original": dados.get("original") or "",
            "editada": bool(dados.get("editada")),
            "apagada": bool(dados.get("apagada")),
            "apagada_pelo_autor": bool(dados.get("apagada_pelo_autor")),
            "ouvida": bool(dados.get("ouvida")),
            "favorita": bool(dados.get("favorita")),
            "reacoes": list(dados.get("reacoes") or []),
            "enquete": dados.get("enquete")
            if isinstance(dados.get("enquete"), dict) else {},
            "citou_voce": bool(dados.get("citou_voce")),
            "previa": dados.get("previa")
            if isinstance(dados.get("previa"), dict) else {},
            "ia": dados.get("ia") if isinstance(dados.get("ia"), dict)
            else {}}


def guardar_extras(msg, links=(), botoes=(), mencoes=(), acoes=(),
                   original="", previa=None):
    """Poe links, botoes, mencoes e acoes (botoes de resposta e opcoes de
    lista que podem ser tocados) na mensagem (nada, se tudo vazio). A
    previa de link ({url, titulo, descricao, site}) que a mensagem ja tinha
    fica, a menos que venha outra."""
    dados = {}
    previa = previa or extras_de(msg)["previa"]
    if previa:
        dados["previa"] = dict(previa)
    if extras_de(msg)["enquete"]:
        dados["enquete"] = dict(extras_de(msg)["enquete"])
    if extras_de(msg)["citou_voce"]:
        dados["citou_voce"] = True
    if links:
        dados["links"] = [list(x) for x in links]
    if botoes:
        dados["botoes"] = [list(x) for x in botoes]
    if mencoes:
        dados["mencoes"] = [dict(x) for x in mencoes]
    if acoes:
        dados["acoes"] = [dict(x) for x in acoes]
    if original:
        dados["original"] = original    # JSON da mensagem com botoes
    msg.extras = json.dumps(dados, ensure_ascii=False) if dados else ""
    return msg


def atualizar_extras(msg, **campos):
    """Muda so as chaves dadas dos extras (editada, apagada, reacoes...),
    mantendo links, botoes e o resto. Valor vazio ou falso remove a chave."""
    try:
        dados = json.loads(msg.extras) if msg.extras else {}
    except ValueError:
        dados = {}
    if not isinstance(dados, dict):
        dados = {}
    for chave, valor in campos.items():
        if valor in (None, False, "", [], {}):
            dados.pop(chave, None)
        else:
            dados[chave] = valor
    msg.extras = json.dumps(dados, ensure_ascii=False) if dados else ""
    return msg


# --------------------------------------------------------------- enquetes
def enquete_de(msg):
    """A enquete da mensagem, ja arrumada, ou {} se nao e uma enquete:
    pergunta, opcoes (textos), maximo (quantas opcoes dá para marcar), votos
    ({quem: {"nome", "escolhas": [posicoes]}}, quando o servico diz quem
    votou), contagem e total (quando o servico ja manda as contagens), meus
    (posicoes em que eu votei), encerrada, anonima, ids (Telegram) e poll_id."""
    bruta = extras_de(msg)["enquete"]
    opcoes = [str(o) for o in bruta.get("opcoes") or []]
    if not opcoes:
        return {}
    votos = {}
    for quem, v in (bruta.get("votos") or {}).items():
        escolhas = [i for i in v.get("escolhas") or []
                    if isinstance(i, int) and 0 <= i < len(opcoes)]
        votos[quem] = {"nome": v.get("nome") or "", "escolhas": escolhas}
    contagem = bruta.get("contagem")
    if not (isinstance(contagem, list) and len(contagem) == len(opcoes)):
        contagem = None
    try:
        maximo = max(1, int(bruta.get("maximo") or 1))
    except (TypeError, ValueError):
        maximo = 1
    return {"pergunta": str(bruta.get("pergunta") or ""), "opcoes": opcoes,
            "maximo": min(maximo, len(opcoes)), "votos": votos,
            "contagem": contagem, "total": bruta.get("total"),
            "meus": [i for i in bruta.get("meus") or []
                     if isinstance(i, int) and 0 <= i < len(opcoes)],
            "encerrada": bool(bruta.get("encerrada")),
            "anonima": bool(bruta.get("anonima")),
            "ids": list(bruta.get("ids") or []),
            "poll_id": str(bruta.get("poll_id") or "")}


def contagens_da_enquete(enq):
    """Votos de cada opcao: a contagem que o servico mandou ou, sem ela, a
    soma dos votos de quem se sabe que votou."""
    if enq["contagem"] is not None:
        return [int(n or 0) for n in enq["contagem"]]
    soma = [0] * len(enq["opcoes"])
    for v in enq["votos"].values():
        for i in v["escolhas"]:
            soma[i] += 1
    return soma


def votantes_da_enquete(enq):
    """Quantas pessoas votaram."""
    if enq["total"] is not None:
        try:
            return int(enq["total"])
        except (TypeError, ValueError):
            pass
    return sum(1 for v in enq["votos"].values() if v["escolhas"])


def quem_votou_em(enq, posicao):
    """Nomes de quem votou na opcao (vazio nas enquetes anonimas)."""
    return [v["nome"] or quem for quem, v in enq["votos"].items()
            if posicao in v["escolhas"]]


def resumo_enquete(msg):
    """'enquete: Pergunta, 3 opções, 5 votos' (+ 'seu voto: A, B')."""
    enq = enquete_de(msg)
    if not enq:
        return ""
    n = len(enq["opcoes"])
    votantes = votantes_da_enquete(enq)
    partes = ["enquete" + (" encerrada" if enq["encerrada"] else "") + ": " +
              enq["pergunta"],
              "%d opções" % n,
              "nenhum voto" if votantes == 0 else
              "1 voto" if votantes == 1 else "%d votos" % votantes]
    if enq["meus"]:
        partes.append("seu voto: " + ", ".join(
            enq["opcoes"][i] for i in enq["meus"]))
    return ", ".join(partes)


def linhas_da_enquete(enq):
    """Uma linha por opcao para a lista da janela: 'Sexta: 2 votos (67%)'."""
    cont = contagens_da_enquete(enq)
    votantes = votantes_da_enquete(enq)
    linhas = []
    for i, opcao in enumerate(enq["opcoes"]):
        n = cont[i]
        pct = int(round(100.0 * n / votantes)) if votantes else 0
        extra = ", seu voto" if i in enq["meus"] else ""
        linhas.append("%s: %s (%d%%)%s" % (
            opcao, "nenhum voto" if n == 0 else "1 voto" if n == 1
            else "%d votos" % n, pct, extra))
    return linhas


LIMITE_OPCOES_ENQUETE = {"whatsapp": (2, 12), "telegram": (2, 10)}
MAX_PERGUNTA_ENQUETE = 255
MAX_OPCAO_ENQUETE = 100


def erro_da_enquete(servico, pergunta, opcoes):
    """O que falta ou esta errado numa enquete a criar ("" se esta boa)."""
    minimo, maximo = LIMITE_OPCOES_ENQUETE.get(servico, (2, 10))
    pergunta = (pergunta or "").strip()
    if not pergunta:
        return "Escreva a pergunta."
    if len(pergunta) > MAX_PERGUNTA_ENQUETE:
        return "A pergunta pode ter até %d letras." % MAX_PERGUNTA_ENQUETE
    if len(opcoes) < minimo:
        return "Acrescente pelo menos %d opções." % minimo
    if len(opcoes) > maximo:
        return "O limite é de %d opções." % maximo
    if len({o.strip().lower() for o in opcoes}) != len(opcoes):
        return "As opções não podem se repetir."
    if any(not o.strip() or len(o) > MAX_OPCAO_ENQUETE for o in opcoes):
        return "Cada opção deve ter de 1 a %d letras." % MAX_OPCAO_ENQUETE
    return ""


def pode_marcar_mais(enq, escolhidas):
    """False se ja ha tantas opcoes marcadas quanto a enquete permite."""
    return len(escolhidas) < enq["maximo"]


def minha_reacao(msg):
    """O emoji com que eu reagi a esta mensagem ("" se nao reagi)."""
    for r in extras_de(msg)["reacoes"]:
        if r.get("minha") or r.get("quem") == "Você":
            return r.get("emoji", "")
    return ""


def resumo_reacoes(msg, maximo=3):
    """'👍 de Ana, ❤ de Bruno' (ate `maximo`; com mais, so a contagem)."""
    reacoes = extras_de(msg)["reacoes"]
    if not reacoes:
        return ""
    if len(reacoes) > maximo:
        return "%d reações" % len(reacoes)
    return ", ".join("%s de %s" % (r.get("emoji", ""), r.get("quem", ""))
                     for r in reacoes)


# ------------------------------------------------------------- formatacao
def tamanho_legivel(n):
    if n < 1024:
        return "%d bytes" % n
    if n < 1024 * 1024:
        return "%d KB" % round(n / 1024)
    return ("%.1f MB" % (n / 1048576)).replace(".", ",")


def duracao_legivel(seg):
    seg = int(round(seg))
    if seg < 60:
        return "1 segundo" if seg == 1 else "%d segundos" % seg
    m, s = divmod(seg, 60)
    txt = "%d minuto%s" % (m, "" if m == 1 else "s")
    if s:
        txt += " e %d segundo%s" % (s, "" if s == 1 else "s")
    return txt


def hora_legivel(ts, agora=None):
    """'08:10' hoje, 'ontem 08:10', '12/10 08:10' no ano, '12/10/2025' antes."""
    if not ts or ts < 0:
        return ""
    agora = time.time() if agora is None else agora
    try:
        t = time.localtime(ts)
    except (OSError, OverflowError, ValueError):
        return ""            # data impossivel (o Windows recusa)
    a = time.localtime(agora)
    hm = time.strftime("%H:%M", t)
    if (t.tm_year, t.tm_yday) == (a.tm_year, a.tm_yday):
        return hm
    ontem = time.localtime(agora - 86400)
    if (t.tm_year, t.tm_yday) == (ontem.tm_year, ontem.tm_yday):
        return "ontem " + hm
    if t.tm_year == a.tm_year:
        return time.strftime("%d/%m ", t) + hm
    return time.strftime("%d/%m/%Y", t)


def texto_visto_por_ultimo(quando, aprox="", agora=None):
    """"visto por último hoje às 08:10", "ontem às ...", "em 12/10 às ...";
    com so uma ideia aproximada ("recentemente"), ela entra no lugar. ""
    se o servico nao informa (a pessoa escondeu)."""
    h = hora_legivel(quando, agora) if quando else ""
    if h:
        if h.startswith("ontem "):
            h = "ontem às " + h[6:]
        elif len(h) == 5:
            h = "hoje às " + h
        elif len(h) > 5 and h[2] == "/" and " " in h:
            dia, hm = h.split(" ", 1)
            h = "em %s às %s" % (dia, hm)
        else:
            h = "em " + h
        return "visto por último " + h
    if aprox:
        return "visto por último " + aprox
    return ""


def texto_presenca(estado, quando=0.0, aprox="", quem="", agora=None):
    """O status da pessoa para o titulo da janela; "" se nao ha o que dizer."""
    if estado == "online":
        return "online"
    if estado == "offline":
        return texto_visto_por_ultimo(quando, aprox, agora)
    acao = {"digitando": "digitando", "gravando": "gravando áudio",
            "enviando": "enviando arquivo"}.get(estado)
    if acao is None:
        return ""
    return "%s está %s" % (quem, acao) if quem else acao


def _partes(*itens):
    return ", ".join(p for p in itens if p)


def conteudo(m, com_estado=True):
    """Texto falado do conteudo de uma mensagem, sem autor nem hora.
    `com_estado`: acrescenta "ouvida" num audio ou voz que ja foi tocado
    (nao entra em citacoes)."""
    extras = extras_de(m)
    if extras["apagada"]:
        return "mensagem apagada"
    ouvida = "ouvida" if com_estado and extras["ouvida"] and \
        not m.minha else ""
    legenda = ("legenda: " + m.texto) if m.texto else ""
    dur = duracao_legivel(m.segundos) if m.segundos else ""
    tam = tamanho_legivel(m.tamanho) if m.tamanho else ""
    if m.tipo == TEXTO:
        return m.texto
    if m.tipo == FOTO:
        return _partes("foto", legenda)
    if m.tipo == VIDEO:
        return _partes("vídeo", dur, tam, legenda)
    if m.tipo == VOZ:
        return _partes("mensagem de voz", dur, ouvida)
    if m.tipo == AUDIO:
        return _partes("áudio", m.nome_arquivo, dur, tam, ouvida, legenda)
    if m.tipo == DOCUMENTO:
        return _partes("documento", m.nome_arquivo, tam, legenda)
    if m.tipo == FIGURINHA:
        return _partes("figurinha", m.texto)
    if m.tipo == AGUARDANDO:
        return ("mensagem ainda não recebida: o WhatsApp não entregou o "
                "conteúdo, ela pode chegar depois")
    if m.texto and not m.texto.startswith("tipo do WhatsApp"):
        # contato, enquete, local, convite, evento, produto...: o TeleZapp
        # entende e descreve; so o que ele nao reconhece diz "sem suporte"
        return m.texto
    return _partes(NOMES_TIPOS[OUTRO], m.texto)


def _juntar(cont, resto):
    """Junta duas partes sem dobrar a pontuacao."""
    if not resto:
        return cont
    if not cont:
        return resto
    final = cont.rstrip()[-1:]
    return cont + (" " if final in ".!?…" else ", ") + resto


LIMITE_CITACAO = 80


def anuncio_reproducao(msg, velocidade="", proximo=False,
                       detalhado=True):
    """O que o leitor de tela fala quando um audio ou mensagem de voz comeca
    a tocar: quem enviou, o que e e quanto dura.
    'Tocando mensagem de voz de Ana, 12 segundos.' `velocidade` e o rotulo
    ('1,5x'), dito so quando nao e a normal; `proximo`: veio da sequencia.
    `detalhado` falso: nada (texto vazio); o proprio audio e o aviso."""
    if not detalhado:
        return "Próximo áudio." if proximo else ""
    coisa = {VOZ: "mensagem de voz", AUDIO: "áudio",
             VIDEO: "vídeo"}.get(msg.tipo, "áudio")
    if msg.minha:
        o_que = "sua " + coisa if msg.tipo == VOZ else "seu " + coisa
    else:
        o_que = coisa + (" de " + msg.autor if msg.autor else "")
    partes = ["Tocando " + o_que]
    if msg.segundos:
        partes.append(duracao_legivel(msg.segundos))
    if velocidade:
        partes.append("a " + velocidade)
    texto = ", ".join(partes) + "."
    return ("Próximo áudio. " + texto) if proximo else texto


def anuncio_sequencia(msg, velocidade="", proximo=True, tipo=True,
                      quem=True, duracao=True, mostrar_velocidade=True):
    """O que se fala quando um audio da sequencia comeca, conforme as
    opcoes da pessoa. Tudo ligado = 'Próximo áudio. Tocando mensagem de voz
    de Ana, 12 segundos, a 1,5x.'; tudo desligado = nada (texto vazio).
    `velocidade`: rotulo ('1,5x'), vazio na velocidade normal."""
    coisa = {VOZ: "mensagem de voz", AUDIO: "áudio",
             VIDEO: "vídeo"}.get(msg.tipo, "áudio")
    partes = []
    if tipo and quem and msg.minha:
        partes.append("Tocando " + ("sua " if msg.tipo == VOZ else "seu ")
                      + coisa)
    elif tipo and quem:
        partes.append("Tocando " + coisa
                      + (" de " + msg.autor if msg.autor else ""))
    elif tipo:
        partes.append("Tocando " + coisa)
    elif quem:
        partes.append("Enviado por você" if msg.minha else
                      ("De " + msg.autor if msg.autor else ""))
    if duracao and msg.segundos:
        partes.append(duracao_legivel(msg.segundos))
    if mostrar_velocidade and velocidade:
        partes.append("a " + velocidade)
    partes = [p for p in partes if p]
    corpo = ", ".join(partes) + "." if partes else ""
    if proximo:
        return "Próximo áudio. " + corpo if corpo else "Próximo áudio."
    return corpo


def citacao(original, max_caracteres=LIMITE_CITACAO):
    """Trecho curto de uma mensagem para mostrar numa resposta."""
    texto = " ".join(conteudo(original, com_estado=False).split())
    if len(texto) > max_caracteres:
        texto = texto[:max_caracteres].rsplit(" ", 1)[0].rstrip(" ,;:.") + "…"
    return texto


def _telefone_do_endereco(remetente):
    """'+5551999998888' de '5551999998888@s.whatsapp.net'; o proprio endereco
    quando nao e um telefone (@lid, por exemplo)."""
    usuario, _, dominio = (remetente or "").partition("@")
    if dominio == "s.whatsapp.net" and usuario.isdigit():
        return "+" + usuario
    return remetente or ""


def nome_para_autor(conv):
    """O nome com que a pessoa de uma conversa privada aparece como autor das
    mensagens que ela envia: o nome da conversa (o do contato salvo vale mais
    que o do perfil). "" quando a conversa so tem o telefone ou nao tem nome
    ainda (nao serve para apagar um nome de perfil que a mensagem trouxe)."""
    if conv is None or conv.tipo != "privada":
        return ""
    nome = (conv.nome or "").strip()
    if not nome or nome.startswith("+") or nome == "Contato sem nome":
        return ""
    return nome


def alinhar_autores(conv, msgs):
    """Poe em todas as mensagens recebidas de uma conversa privada o mesmo
    autor (nome_para_autor). Devolve as que mudaram."""
    nome = nome_para_autor(conv)
    mudaram = []
    if nome:
        for x in msgs:
            if not x.minha and x.autor != nome:
                x.autor = nome
                mudaram.append(x)
    return mudaram


def quem_enviou(msg, conv=None, nome_do_remetente=None):
    """Quem enviou, na lista e no arquivo salvo: o autor da mensagem; sem ele, o nome
    da conversa (se e com uma pessoa), o nome que a agenda ou as outras
    mensagens guardadas dao ao remetente, o telefone dele e, so no fim,
    Desconhecido. `nome_do_remetente(msg)` e opcional."""
    if msg.minha:
        return "Você"
    if msg.autor:
        return msg.autor
    if conv is not None and conv.tipo == "privada" and conv.nome:
        return conv.nome
    if nome_do_remetente is not None and msg.remetente:
        nome = nome_do_remetente(msg)
        if nome:
            return nome
    usuario, _, dominio = (msg.remetente or "").partition("@")
    if dominio == "lid" and usuario:
        # endereco interno do WhatsApp: nao diz nada a quem ouve, mas o fim
        # separa uma pessoa da outra no grupo
        return "Participante final %s" % usuario[-4:]
    return _telefone_do_endereco(msg.remetente) or "Desconhecido"


# Quantas letras do texto da IA a linha da mensagem traz (0 = tudo): uma para
# as descricoes de foto, figurinha e video, outra para transcricoes e PDFs
# Como a previa de um link (titulo e descricao que o servico manda junto)
# entra na linha da mensagem: "completa", "titulo" ou "nenhuma"
MODO_PREVIA = ["completa"]
LIMITE_PREVIA = 400


def definir_modo_previa(modo):
    MODO_PREVIA[0] = modo if modo in ("completa", "titulo", "nenhuma") \
        else "completa"


def previa_de_link(url="", titulo="", descricao="", site=""):
    """Dicionario da previa, ou {} se nao ha titulo nem descricao."""
    titulo, descricao = " ".join((titulo or "").split()), \
        " ".join((descricao or "").split())
    if not titulo and not descricao:
        return {}
    return {"url": url or "", "titulo": titulo, "descricao": descricao,
            "site": " ".join((site or "").split())}


def trecho_da_previa(msg):
    """"prévia do link: Título. Descrição" para a linha da mensagem."""
    previa = extras_de(msg)["previa"]
    modo = MODO_PREVIA[0]
    if not previa or modo == "nenhuma":
        return ""
    titulo, descricao = previa.get("titulo", ""), previa.get("descricao", "")
    partes = [titulo]
    if modo == "completa" and descricao and descricao != titulo:
        partes.append(descricao)
    texto = ". ".join(p.rstrip(".") for p in partes if p)
    if len(texto) > LIMITE_PREVIA:
        texto = texto[:LIMITE_PREVIA].rstrip() + "…"
    return "prévia do link: " + texto if texto else ""


def _so_link(m):
    """Verdadeiro se a mensagem e um texto que e apenas um link e tem previa."""
    if m.tipo != TEXTO or extras_de(m)["apagada"] or not (m.texto or "").strip():
        return False
    achados = extrair_links(m.texto)
    return len(achados) == 1 and m.texto.strip().rstrip(_FIM_DE_LINK) == \
        achados[0][1] and bool(trecho_da_previa(m))


LIMITE_IA_NA_LINHA = {"descricao": 0, "transcricao": 1000}

# Ligado pela janela a partir da opcao `manter_apagadas`: o que o remetente
# apaga para todos continua guardado aqui, so marcado.
MANTER = {"apagadas": False}


def definir_manter_apagadas(ligado):
    MANTER["apagadas"] = bool(ligado)


def definir_limites_ia(descricao, transcricao):
    LIMITE_IA_NA_LINHA["descricao"] = max(0, int(descricao or 0))
    LIMITE_IA_NA_LINHA["transcricao"] = max(0, int(transcricao or 0))


def rotulo_da_ia(msg):
    """"transcrição" ou "descrição", conforme o que a IA fez na mensagem."""
    ia = extras_de(msg)["ia"]
    if not ia.get("texto"):
        return ""
    return "transcrição" if ia.get("genero") == "audio" else (
        "texto do PDF" if ia.get("genero") == "pdf" else "descrição")


def trecho_da_ia(msg):
    """O comeco do texto feito pela IA, para a linha da mensagem."""
    rotulo = rotulo_da_ia(msg)
    if not rotulo:
        return ""
    ia = extras_de(msg)["ia"]
    texto = " ".join(ia["texto"].split())
    limite = LIMITE_IA_NA_LINHA["descricao" if ia.get("genero") in (
        "imagem", "figurinha", "video") else "transcricao"]
    if limite and len(texto) > limite:
        texto = texto[:limite].rstrip() + "… (o menu mostra tudo)"
    return "%s: %s" % (rotulo, texto)


def formatar(m, estilo, anterior=None, agora=None, respondida=None,
             quem=None):
    """Uma linha da lista de mensagens, no estilo escolhido.

    respondida: a mensagem respondida (Mensagem), se conhecida; ou só o nome
    do autor (texto). quem: nome de quem enviou, quando a mensagem nao traz
    o autor (ver quem_enviou).
    """
    cont = conteudo(m).replace("\r", " ").replace("\n", " ")
    if enquete_de(m):
        cont = resumo_enquete(m) + " (Enter para ver e votar)"
    so_link = _so_link(m)
    if so_link:
        # mensagem so com o link: a previa vem antes, para saber do que se
        # trata sem ouvir o endereco inteiro
        cont = _juntar(trecho_da_previa(m), cont)
    if extras_de(m)["editada"]:
        cont = _juntar(cont, "(editada)")
    if extras_de(m)["apagada_pelo_autor"]:
        cont = _juntar(cont, "(apagada pelo autor)")
    if extras_de(m)["favorita"]:
        cont = _juntar(cont, "(favorita)")
    if getattr(m, "expira", 0):
        cont = _juntar(cont, "(temporária)")
    n_links = len(itens_de_link(m))
    if n_links:
        cont = _juntar(cont, "com %d %s (Tab)" % (
            n_links, "link" if n_links == 1 else "links"))
    acoes = extras_de(m)["acoes"]
    if acoes:
        so_opcoes = all(a.get("tipo") == "lista" for a in acoes)
        cont = _juntar(cont, "com %d %s (Tab)" % (
            len(acoes), ("opção" if len(acoes) == 1 else "opções")
            if so_opcoes else ("botão" if len(acoes) == 1 else "botões")))
    if not so_link:
        cont = _juntar(cont, trecho_da_previa(m))
    cont = _juntar(cont, trecho_da_ia(m))
    reacoes = resumo_reacoes(m)
    if reacoes:
        cont = _juntar(cont, "reações: " + reacoes if " de " in reacoes
                       else "com " + reacoes)
    if m.resposta_a:
        if isinstance(respondida, Mensagem):
            quem = "você" if respondida.minha else (
                respondida.autor or "mensagem")
            cont = _juntar(cont, 'em resposta a %s: "%s"' % (
                quem, citacao(respondida)))
        elif respondida:
            cont = _juntar(cont, "em resposta a %s" % respondida)
        else:
            cont = _juntar(cont, "em resposta a uma mensagem mais antiga")
    autor = "Você" if m.minha else (m.autor or quem or "Desconhecido")
    estado = m.estado if (m.minha and m.estado) else ""
    hora = hora_legivel(m.data, agora)
    if estilo == ESTILO_CONTEUDO_PRIMEIRO:
        return _juntar(cont, _partes(autor, hora, estado))
    if estilo == ESTILO_AUTOR_SO_QUANDO_MUDA:
        mudou = anterior is None or anterior.minha != m.minha or \
            anterior.autor != m.autor
        prefixo = ("%s: " % autor) if mudou else ""
        return _juntar(prefixo + cont, estado)
    return _juntar("%s, %s: %s" % (autor, hora, cont), estado)


FILTROS_TIPO = (("todas", "Todas as conversas"),
                ("nao_lidas", "Não lidas"),
                ("citacoes", "Menções e respostas"),
                ("pessoais", "Pessoais"),
                ("grupos", "Grupos"),
                ("canais", "Canais"),
                ("fixadas", "Fixadas"),
                ("silenciadas", "Silenciadas"),
                ("arquivadas", "Arquivadas"),
                ("status", "Status e histórias"),
                ("trancadas", "Trancadas no celular"))
CONTA_TODAS = "todas"


def tipos_visiveis(trancadas):
    """FILTROS_TIPO; o tipo Trancadas so entra quando liberado."""
    return tuple(t for t in FILTROS_TIPO if trancadas or t[0] != "trancadas")


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


def casa_busca(nome, busca):
    """Todas as palavras da busca aparecem no nome (sem maiusculas nem
    acentos)? Busca vazia casa com tudo."""
    alvo = _sem_acento(nome or "")
    return all(p in alvo for p in _sem_acento(busca or "").split())
ROTULO_TODAS_AS_CONTAS = "Todas as contas"


def passa_filtro(c, tipo="todas", conta=CONTA_TODAS, busca=""):
    """A conversa aparece na lista? `conta`: "todas", um servico
    ("telegram", "whatsapp") ou "conta:<id>". `tipo`: ver FILTROS_TIPO. As
    arquivadas so aparecem no tipo Arquivadas. Valor desconhecido nao
    filtra."""
    if busca and not casa_busca(c.nome, busca):
        return False
    if conta in SERVICOS and c.servico != conta:
        return False
    if conta.startswith("conta:") and c.conta_id != conta[6:]:
        return False
    if tipo == "status":
        return c.tipo == "status"        # um por pessoa, como uma conversa
    if c.tipo == "status":
        return False                     # so aparece no filtro Status
    if tipo == "trancadas":
        return bool(c.trancada)
    if c.trancada:
        return False             # trancada: so no tipo Trancadas
    if tipo == "arquivadas":
        return bool(c.arquivada)
    if c.arquivada:
        return False
    if tipo == "nao_lidas":
        return c.nao_lidas > 0
    if tipo == "citacoes":
        return c.tipo == "grupo" and c.tem_citacao_nao_lida()
    if tipo == "pessoais":
        return c.tipo == "privada"
    if tipo == "grupos":
        return c.tipo == "grupo"
    if tipo == "canais":
        return c.tipo == "canal"
    if tipo == "fixadas":
        return bool(c.fixada)
    if tipo == "silenciadas":
        return c.silenciada()
    return True


def opcoes_de_conta(contas):
    """[(valor, rotulo)] do filtro de conta. contas: [(id, servico, nome)].
    Todas as contas, os servicos que tem conta e, para o servico com mais de
    uma conta, cada conta."""
    opcoes = [(CONTA_TODAS, ROTULO_TODAS_AS_CONTAS)]
    for servico, nome_servico in SERVICOS.items():
        do_servico = [c for c in contas if c[1] == servico]
        if not do_servico:
            continue
        opcoes.append((servico, nome_servico))
        if len(do_servico) > 1:
            opcoes += [("conta:" + i, "%s, %s" % (n, nome_servico))
                       for i, _, n in do_servico]
    return opcoes


def rotulo_conversa(c, lista=None, previa="", reacoes=0, quem_reagiu=()):
    """A linha da conversa na lista (ver nucleo/lista_conversas.py)."""
    from telezapp.nucleo import lista_conversas
    return lista_conversas.rotulo(c, lista, previa, reacoes,
                                  quem_reagiu)


_LINK = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)
_FIM_DE_LINK = ".,;:!?)]}»”’'\""


def extrair_links(texto):
    """Links (http, https e www) de um texto, na ordem, sem repetir.
    Devolve [(endereco_para_abrir, como_aparece_no_texto)]."""
    achados, vistos = [], set()
    for t in _LINK.findall(texto or ""):
        t = t.rstrip(_FIM_DE_LINK)
        if len(t) < 5:
            continue
        url = t if t.lower().startswith("http") else "https://" + t
        if url not in vistos:
            vistos.add(url)
            achados.append((url, t))
    return achados


def itens_de_link(m):
    """O que a janela mostra como botoes para abrir no navegador, na ordem:
    os links do texto ou da legenda e os botoes de endereco (Telegram).
    [(rotulo, endereco)]; so http e https, sem repetir endereco."""
    extras = extras_de(m)
    itens, vistos = [], set()

    def juntar(rotulo, url):
        ok = url and url.lower().startswith(("http://", "https://"))
        if ok and url not in vistos:
            vistos.add(url)
            itens.append((rotulo, url))
    for url, texto in extras["links"]:
        juntar("Link: " + (texto or url), url)
    for url, texto in extrair_links(m.texto):
        juntar("Link: " + (texto or url), url)
    for rotulo, url in extras["botoes"]:
        juntar("Botão: " + (rotulo or url), url)
    return itens


def conteudos_copiaveis(msg, maximo_links=12):
    """O que da para copiar da mensagem, um item por tipo de conteudo:
    [(tipo, rotulo, valor)], com tipo "texto" (valor = o texto), "midia"
    (valor vazio: o arquivo baixado) ou "link" (valor = o endereco). Uma
    mensagem so com texto tem so o texto; uma foto com legenda e link tem a
    legenda, a foto e o link. Sem nada para copiar (mensagem apagada, sem
    suporte), sobra o texto falado da mensagem."""
    itens = []
    if extras_de(msg)["apagada"]:
        return [("texto", "Copiar texto", conteudo(msg))]
    ia = extras_de(msg)["ia"].get("texto")
    midia = msg.tipo in (FOTO, VIDEO, VOZ, AUDIO, DOCUMENTO, FIGURINHA)
    if msg.texto and msg.tipo not in (VOZ, FIGURINHA):
        itens.append(("texto", "Copiar legenda" if midia else "Copiar texto",
                      msg.texto))
    if midia:
        itens.append(("midia", "Copiar " + NOMES_TIPOS[msg.tipo], ""))
    if ia:
        itens.append(("texto", "Copiar " + rotulo_da_ia(msg), ia))
    links = itens_de_link(msg)[:maximo_links]
    for rotulo, url in links:
        itens.append(("link", "Copiar link" if len(links) == 1
                      else "Copiar " + rotulo, url))
    if not itens:
        itens.append(("texto", "Copiar texto", conteudo(msg)))
    return itens


def tem_links(m):
    """A mensagem tem algum link (na legenda ou escondido)?"""
    return bool(extrair_links(m.texto) or extras_de(m)["links"])


def texto_marcador(n):
    return "Início das mensagens não lidas: %d %s" % (
        n, "mensagem" if n == 1 else "mensagens")


def _quem_legivel(quem):
    """Identificador de participante que nunca mostra o codigo interno."""
    if quem.endswith("@s.whatsapp.net"):
        return "+" + quem.split("@")[0]
    if "@" in quem:
        return "Contato sem nome"
    return quem


# O que cada recibo quer dizer para quem enviou: recebeu, abriu, reproduziu
ROTULOS_RECIBO = (("entregue", "Recebida", "recebeu"),
                  ("lida", "Aberta", "abriu"),
                  ("ouvida", "Reproduzida", "reproduziu"))


def pessoas_por_recibo(recibos):
    """{tipo: [(participante, data)]}, uma vez por pessoa, na ordem do
    evento; `recibos` e a lista (participante, tipo, data) do banco."""
    saida = {tipo: [] for tipo, _, _ in ROTULOS_RECIBO}
    vistos = set()
    for quem, tipo, data in recibos or []:
        if tipo in saida and (quem, tipo) not in vistos:
            vistos.add((quem, tipo))
            saida[tipo].append((quem, data))
    return saida


def texto_pessoas(n):
    return "1 pessoa" if n == 1 else "%d pessoas" % n


def detalhes(m, nome_conversa, agora=None, recibos=None, nomes=None,
             midia=None, grupo=False, contagens=True):
    linhas = [
        "Conversa: %s" % nome_conversa,
        "De: %s" % ("Você" if m.minha else (m.autor or "Desconhecido")),
        "Data: %s" % (time.strftime("%d/%m/%Y %H:%M", time.localtime(m.data))
                      if m.data else "-"),
        "Tipo: %s" % NOMES_TIPOS.get(m.tipo, m.tipo),
    ]
    extras_m = extras_de(m)
    if extras_m["editada"]:
        linhas.append("Editada: sim")
    if extras_m["apagada"]:
        linhas.append("Apagada pelo autor: sim")
    temp = texto_temporaria(m, agora)
    if temp:
        linhas.append("Mensagem " + temp)
    for r in extras_m["reacoes"]:
        linhas.append("Reação: %s de %s" % (r.get("emoji", ""),
                                            r.get("quem", "")))
    previa = extras_m["previa"]
    if previa:
        linhas.append("Prévia do link: %s" % " - ".join(
            p for p in (previa.get("titulo"), previa.get("site")) if p))
        if previa.get("descricao"):
            linhas.append("Descrição da prévia: %s" % previa["descricao"])
        if previa.get("url"):
            linhas.append("Endereço da prévia: %s" % previa["url"])
    if m.nome_arquivo:
        linhas.append("Arquivo: %s" % m.nome_arquivo)
    if m.tamanho:
        linhas.append("Tamanho: %s" % tamanho_legivel(m.tamanho))
    if m.segundos:
        linhas.append("Duração: %s" % duracao_legivel(m.segundos))
    if m.minha and m.estado:
        linhas.append("Estado: %s" % m.estado)
    if midia:
        linhas.append("Mídia: %s" % midia)
    if m.minha and grupo:
        # grupo: so o resumo; quem e quando fica nas listas dos botoes
        linhas.append("Enviada em: %s" % (time.strftime(
            "%d/%m/%Y %H:%M:%S", time.localtime(m.data)) if m.data else "-"))
        por_tipo = pessoas_por_recibo(recibos)
        for tipo, rotulo, _ in ROTULOS_RECIBO:
            n = len(por_tipo[tipo])
            if contagens and (n or tipo != "ouvida" or
                              m.tipo in (VOZ, AUDIO, VIDEO)):
                linhas.append("%s por %s" % (rotulo, texto_pessoas(n)))
    elif m.minha and recibos:
        nomes = nomes or {}
        rotulos = {"entregue": "Entregue", "lida": "Lida",
                   "ouvida": "Reproduzida"}
        linhas.append("")
        for quem, tipo, data in recibos:
            linhas.append("%s a %s em %s" % (
                rotulos.get(tipo, tipo),
                nomes.get(quem) or _quem_legivel(quem),
                time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(data))
                if data else "-"))
    if m.texto:
        linhas += ["", "Texto completo:", m.texto]
    return "\n".join(linhas)


EXT_FOTO = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"}
EXT_VIDEO = {".mp4", ".mov", ".m4v", ".3gp", ".mkv", ".avi", ".webm", ".wmv"}
EXT_AUDIO = {".ogg", ".opus", ".mp3", ".m4a", ".wav", ".aac", ".flac"}


def classificar_arquivo(caminho):
    ext = os.path.splitext(caminho)[1].lower()
    if ext in EXT_FOTO:
        return FOTO
    if ext in EXT_VIDEO:
        return VIDEO
    if ext in EXT_AUDIO:
        return AUDIO
    return DOCUMENTO


def normalizar_telefone(texto, ddi_padrao="55"):
    """'(51) 99999-8888' -> '+5551999998888'; None se nao parecer telefone.

    Sem o sinal de mais e com 10 ou 11 digitos, assume o Brasil.
    """
    t = (texto or "").strip()
    mais = t.startswith("+")
    digitos = re.sub(r"\D", "", t)
    if t.startswith("00"):
        digitos, mais = digitos[2:], True
    if not mais and len(digitos) in (10, 11):
        digitos = ddi_padrao + digitos
    if not 8 <= len(digitos) <= 15:
        return None
    return "+" + digitos

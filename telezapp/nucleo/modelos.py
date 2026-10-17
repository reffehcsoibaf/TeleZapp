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
NOMES_TIPOS = {
    TEXTO: "texto", FOTO: "foto", VIDEO: "vídeo", VOZ: "mensagem de voz",
    AUDIO: "áudio", DOCUMENTO: "documento", FIGURINHA: "figurinha",
    OUTRO: "mensagem sem suporte ainda",
}

# Estados de uma mensagem enviada
ENVIANDO, ENVIADA, ENTREGUE, LIDA, FALHOU = (
    "enviando", "enviada", "entregue", "lida", "falhou")
# ordem de avanco: um estado nunca volta para um anterior
ORDEM_ESTADOS = {ENVIANDO: 0, ENVIADA: 1, ENTREGUE: 2, LIDA: 3}

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

    @property
    def chave(self):
        return (self.conta_id, self.id)

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

    @property
    def chave(self):
        return (self.conta_id, self.conversa_id, self.id)


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
            "ouvida": bool(dados.get("ouvida")),
            "reacoes": list(dados.get("reacoes") or [])}


def guardar_extras(msg, links=(), botoes=(), mencoes=(), acoes=(),
                   original=""):
    """Poe links, botoes, mencoes e acoes (botoes de resposta e opcoes de
    lista que podem ser tocados) na mensagem (nada, se tudo vazio)."""
    dados = {}
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
    if not ts:
        return ""
    agora = time.time() if agora is None else agora
    t = time.localtime(ts)
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
    `detalhado` falso: so 'Tocando.' (com a velocidade, se nao e a normal)."""
    if not detalhado:
        texto = "Tocando" + (", a " + velocidade if velocidade else "") + "."
        return ("Próximo áudio. " + texto) if proximo else texto
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


def formatar(m, estilo, anterior=None, agora=None, respondida=None):
    """Uma linha da lista de mensagens, no estilo escolhido.

    respondida: a mensagem respondida (Mensagem), se conhecida; ou só o nome
    do autor (texto).
    """
    cont = conteudo(m).replace("\r", " ").replace("\n", " ")
    if extras_de(m)["editada"]:
        cont = _juntar(cont, "(editada)")
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
    autor = "Você" if m.minha else (m.autor or "Desconhecido")
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
                ("pessoais", "Pessoais"),
                ("grupos", "Grupos"),
                ("canais", "Canais"),
                ("fixadas", "Fixadas"),
                ("silenciadas", "Silenciadas"),
                ("arquivadas", "Arquivadas"),
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


def rotulo_conversa(c):
    base = "%s, %s" % (c.nome, SERVICOS.get(c.servico, c.servico))
    if c.fixada:
        base += ", fixada"
    if c.silenciada():
        base += ", silenciada"
    if c.nao_lidas == 1:
        return base + ", 1 não lida"
    if c.nao_lidas > 1:
        return base + ", %d não lidas" % c.nao_lidas
    return base


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


def detalhes(m, nome_conversa, agora=None, recibos=None, nomes=None,
             midia=None):
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
    for r in extras_m["reacoes"]:
        linhas.append("Reação: %s de %s" % (r.get("emoji", ""),
                                            r.get("quem", "")))
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
    if m.minha and recibos:
        nomes = nomes or {}
        rotulos = {"entregue": "Entregue", "lida": "Lida",
                   "ouvida": "Ouvida"}
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

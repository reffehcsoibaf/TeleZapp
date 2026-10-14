# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Formato comum aos dois servicos (conta, conversa, mensagem) e o texto que
o leitor de tela fala para cada item. Sem dependencia de wxPython."""
import json
import os
import re
import time
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

    @property
    def chave(self):
        return (self.conta_id, self.id)


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
            "original": dados.get("original") or ""}


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


def conteudo(m):
    """Texto falado do conteudo de uma mensagem, sem autor nem hora."""
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
        return _partes("mensagem de voz", dur)
    if m.tipo == AUDIO:
        return _partes("áudio", m.nome_arquivo, dur, tam, legenda)
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


def citacao(original, max_caracteres=LIMITE_CITACAO):
    """Trecho curto de uma mensagem para mostrar numa resposta."""
    texto = " ".join(conteudo(original).split())
    if len(texto) > max_caracteres:
        texto = texto[:max_caracteres].rsplit(" ", 1)[0].rstrip(" ,;:.") + "…"
    return texto


def formatar(m, estilo, anterior=None, agora=None, respondida=None):
    """Uma linha da lista de mensagens, no estilo escolhido.

    respondida: a mensagem respondida (Mensagem), se conhecida; ou só o nome
    do autor (texto).
    """
    cont = conteudo(m).replace("\r", " ").replace("\n", " ")
    if m.tipo not in (TEXTO, VOZ, FIGURINHA) and tem_links(m):
        cont = _juntar(cont, "com link (Enter)")
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


def rotulo_conversa(c):
    base = "%s, %s" % (c.nome, SERVICOS.get(c.servico, c.servico))
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

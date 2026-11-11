# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Busca de canais do WhatsApp no diretório do próprio WhatsApp, a parte sem
wx e sem rede.

O whatsmeow só sabe seguir um canal, ler um por convite e listar os que a
conta já segue. A busca e as listas do diretório (recomendados, em alta,
populares, novos, por categoria) são consultas MEX do WhatsApp Web; a DLL do
TeleZapp tem uma função genérica (`NewsletterMex`) que as envia, e o provedor
chama por ctypes. Os números das consultas foram lidos no WhatsApp Web por
outro projeto (CDP, 04/11/2026) e podem mudar sem aviso: por isso há uma
lista de alternativas por consulta e o erro do WhatsApp chega até a pessoa.
"""
import json
import re
from dataclasses import dataclass

# Consultas MEX por tarefa: (id, campo da resposta). A ordem importa: primeiro
# os ids da tabela de consultas do whatsmeow (a versao do WhatsApp que o
# TeleZapp declara), depois os que o whatsmeow usa nos canais, por ultimo os
# lidos no WhatsApp Web de outro projeto (versao mais nova, pode nao valer).
BUSCA = (("8422355807877290", "xwa2_newsletters_directory_search"),
         ("9006011396096776", "xwa2_newsletters_search"),
         ("26301059626252132", "xwa2_newsletters_directory_search"))
RECOMENDADOS = (("27256776790637714", "xwa2_newsletters_recommended"),
                ("7263823273662354", "xwa2_newsletters_recommended"),
                ("25806748772361516", "xwa2_newsletters_recommended"))
LISTA = (("8629852843766813", "xwa2_newsletters_directory_list"),
         ("6190824427689257", "xwa2_newsletters_directory_list"),
         ("26125047313831973", "xwa2_newsletters_directory_list"))

CATEGORIAS = (
    ("", "Todas as categorias"), ("NEWS", "Notícias"),
    ("SPORTS", "Esportes"), ("ENTERTAINMENT", "Entretenimento"),
    ("BUSINESS", "Negócios"), ("LIFESTYLE", "Estilo de vida"),
    ("ORGANIZATIONS", "Organizações"), ("PEOPLE", "Pessoas"))
VISOES = (
    ("RECOMMENDED", "Recomendados"), ("TRENDING", "Em alta"),
    ("POPULAR", "Populares"), ("NEW", "Novos"))

PREFIXO_CONVITE = "https://whatsapp.com/channel/"
_CANAL = re.compile(r"\d+@newsletter")
_SUMIDOS = ("DELETED", "GEOSUSPENDED", "SUSPENDED", "NON_EXISTING")
LIMITE_PADRAO = 30


@dataclass(frozen=True)
class Pagina:
    """Uma pagina de resultados: os canais e o cursor da proxima ('' quando o
    WhatsApp nao tem mais)."""
    canais: list
    proximo: str = ""


@dataclass(frozen=True)
class CanalWA:
    id: str
    nome: str
    descricao: str
    seguidores: int | None
    verificado: bool
    seguindo: bool
    convite: str

    @property
    def link(self):
        return PREFIXO_CONVITE + self.convite if self.convite else ""


def _categorias_e_visao(categoria, visao):
    categoria = (categoria or "").upper()
    categorias = [categoria] if categoria and         categoria in dict(CATEGORIAS) else []
    visao = (visao or "").upper()
    return categorias, visao if visao in dict(VISOES) else ""


# prefixo telefonico -> pais (so para dizer ao diretorio de que pais sao os
# canais; as consultas de lista recusaram `country_codes` vazio?)
PAISES_POR_DDI = {
    "55": "BR", "351": "PT", "1": "US", "44": "GB", "34": "ES", "54": "AR",
    "52": "MX", "57": "CO", "56": "CL", "598": "UY", "595": "PY", "51": "PE",
    "58": "VE", "244": "AO", "258": "MZ", "33": "FR", "49": "DE", "39": "IT",
    "91": "IN", "81": "JP", "61": "AU", "27": "ZA", "41": "CH", "31": "NL"}


def pais_do_telefone(telefone):
    """O codigo de pais (BR, PT...) do telefone com DDI, ou ''."""
    digitos = re.sub(r"\D", "", telefone or "")
    for n in (3, 2, 1):
        if digitos[:n] in PAISES_POR_DDI:
            return PAISES_POR_DDI[digitos[:n]]
    return ""


_SEM = object()          # chave ausente das variaveis


def forma_da_consulta(variaveis):
    """O formato das variaveis sem o cursor: identifica qual variacao o
    WhatsApp aceitou, para repeti-la nas proximas paginas."""
    entrada = dict(variaveis.get("input") or {})
    entrada.pop("start_cursor", None)
    return json.dumps(dict(variaveis, input=entrada), sort_keys=True)


def tipo_do_cursor(variaveis):
    """Como a primeira pagina mandou o `start_cursor`: ausente, nulo ou
    vazio (as paginas seguintes mandam o cursor de verdade). Faz parte do
    que o WhatsApp aceitou na primeira pagina."""
    entrada = variaveis.get("input") or {}
    if "start_cursor" not in entrada:
        return "ausente"
    cursor = entrada["start_cursor"]
    return "nulo" if cursor is None else "vazio" if cursor == "" else "pagina"


def identidade(consulta, variaveis, primeira_pagina=True):
    """O que se lembra de uma consulta que valeu: o id, o formato e, na
    primeira pagina, o jeito de mandar o cursor."""
    base = (consulta, forma_da_consulta(variaveis))
    return base + (tipo_do_cursor(variaveis),) if primeira_pagina else base


def _entradas_de_lista(base, paises, cursores):
    """Variacoes da entrada da lista: com o pais da conta e sem ele, e o
    start_cursor ausente, nulo ou vazio. A consulta de cada versao do
    WhatsApp aceita um formato so, e o erro nao diz qual."""
    saida = []
    for lista in ([list(paises)] if paises else []) + [[]]:
        for cursor in cursores:
            entrada = dict(base)
            entrada["filters"] = dict(base["filters"],
                                      country_codes=lista)
            if cursor is not _SEM:
                entrada["start_cursor"] = cursor
            saida.append(entrada)
    return saida


def pedidos(texto="", categoria="", visao="", limite=LIMITE_PADRAO,
            paises=(), cursor=""):
    """As consultas a tentar, em ordem, para o que a pessoa pediu: lista de
    (id da consulta, variaveis, campo da resposta). A primeira que o WhatsApp
    aceitar vale. Pela busca de texto, ou pela lista do diretorio na visao
    pedida (restrita a uma categoria, se houver); categoria ou visao
    desconhecida e ignorada. `paises`: codigos de pais da conta, para as
    listas. As consultas de lista e de recomendados foram recusadas (400) com
    `country_codes` vazio e `start_cursor` nulo no primeiro teste real; a
    busca por texto, que nao os usa, funcionou. `cursor`: o da pagina
    seguinte (devolvido na pagina anterior); sem ele, a primeira pagina."""
    texto = (texto or "").strip()[:100]
    try:
        limite = max(1, min(50, int(limite)))
    except (TypeError, ValueError):
        limite = LIMITE_PADRAO
    categorias, visao = _categorias_e_visao(categoria, visao)
    if texto:
        entrada = {"search_text": texto, "categories": categorias,
                   "limit": limite, "start_cursor": cursor or None}
        return [(qid, {"input": dict(entrada)}, campo)
                for qid, campo in BUSCA] + [
            (qid, {"input": dict(entrada),
                   "fetch_status_metadata": False}, campo)
            for qid, campo in BUSCA]
    filtros = {}
    if categorias:
        filtros["categories"] = categorias
    base = {"view": visao or "RECOMMENDED", "filters": filtros,
            "limit": limite}
    saida = []
    for n, (qid, campo) in enumerate(LISTA):
        cursores = (cursor,) if cursor else (
            (_SEM, None, "") if n < 2 else (None,))
        for entrada in _entradas_de_lista(base, paises, cursores):
            saida.append((qid, {"input": entrada}, campo))
    if categorias or visao not in ("", "RECOMMENDED") or cursor:
        return saida
    curto = min(limite, 20)
    for qid, campo in RECOMENDADOS[:2]:
        for lista in ([list(paises)] if paises else []) + [[]]:
            saida.append((qid, {"input": {"limit": curto,
                                          "country_codes": lista}}, campo))
    return saida


def _texto(valor):
    if isinstance(valor, dict):
        valor = valor.get("text")
    return valor.strip() if isinstance(valor, str) else ""


def _inteiro(valor):
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def canal_de(no):
    """O CanalWA de um nó da resposta, ou None se não for um canal ou o
    WhatsApp disser que ele não existe mais."""
    if not isinstance(no, dict):
        return None
    cid = no.get("id")
    if not isinstance(cid, str) or not _CANAL.fullmatch(cid):
        return None
    estado = no.get("state")
    if isinstance(estado, dict) and \
            str(estado.get("type") or "").upper() in _SUMIDOS:
        return None
    meta = no.get("thread_metadata")
    meta = meta if isinstance(meta, dict) else {}
    visto = no.get("viewer_metadata")
    visto = visto if isinstance(visto, dict) else {}
    convite = meta.get("invite")
    return CanalWA(
        id=cid, nome=_texto(meta.get("name")),
        descricao=_texto(meta.get("description")),
        seguidores=_inteiro(meta.get("subscribers_count")),
        verificado=str(meta.get("verification") or "").upper() == "VERIFIED",
        seguindo=str(visto.get("role") or "").strip().upper() in (
            "OWNER", "ADMIN", "SUBSCRIBER"),
        convite=convite.strip() if isinstance(convite, str) else "")


def canais_da_resposta(dados, campo):
    """Os canais de uma resposta da busca ou das listas, sem repetir.
    ValueError se a resposta não tem o campo esperado."""
    if not isinstance(dados, dict) or campo not in dados:
        raise ValueError("resposta inesperada")
    corpo = dados[campo]
    if isinstance(corpo, dict):
        corpo = corpo.get("result")
    if corpo is None:
        return []
    if not isinstance(corpo, list):
        raise ValueError("resposta inesperada")
    vistos, saida = set(), []
    for no in corpo:
        c = canal_de(no)
        if c is not None and c.id not in vistos:
            vistos.add(c.id)
            saida.append(c)
    return saida


def proximo_cursor(dados, campo):
    """O cursor da pagina seguinte de uma resposta ('' se nao ha). O
    WhatsApp manda `page_info` com `endCursor`; a ausencia de proxima pagina
    pode vir como `hasNextPage` falso."""
    corpo = dados.get(campo) if isinstance(dados, dict) else None
    if not isinstance(corpo, dict):
        return ""
    info = corpo.get("page_info") or corpo.get("pageInfo")
    if not isinstance(info, dict):
        return ""
    for chave, valor in info.items():
        if valor is False and "next" in chave.lower():
            return ""            # hasNextPage / has_next_page falso
    achados = [(chave, valor) for chave, valor in info.items()
               if "cursor" in chave.lower() and isinstance(valor, str)
               and valor]
    for chave, valor in achados:         # o do fim da pagina, de preferencia
        if "end" in chave.lower():
            return valor
    return ""


def resumo_da_pagina(dados, campo, mostrar=12):
    """Os campos do `page_info` da resposta, com os cursores encurtados, para
    o log (ajuda a ver como o WhatsApp pagina)."""
    corpo = dados.get(campo) if isinstance(dados, dict) else None
    info = (corpo.get("page_info") or corpo.get("pageInfo")) \
        if isinstance(corpo, dict) else None
    if not isinstance(info, dict):
        return "sem page_info"
    partes = []
    for chave, valor in info.items():
        if isinstance(valor, str) and len(valor) > mostrar:
            valor = valor[:mostrar] + "..."
        partes.append("%s=%r" % (chave, valor))
    return ", ".join(partes) or "page_info vazio"


def seguidores_por_extenso(n):
    if n is None:
        return ""
    if n == 1:
        return "1 seguidor"
    return "%s seguidores" % format(n, ",").replace(",", ".")


# Tipos de publicacao de um canal: (campo da mensagem, como dizer, campo do texto)
TIPOS_DE_PUBLICACAO = (
    ("conversation", "Texto", None),
    ("extendedTextMessage", "Texto", "text"),
    ("imageMessage", "Foto", "caption"),
    ("videoMessage", "Vídeo", "caption"),
    ("audioMessage", "Áudio", None),
    ("documentMessage", "Documento", "caption"),
    ("stickerMessage", "Figurinha", None),
    ("pollCreationMessage", "Enquete", "name"),
    ("pollCreationMessageV2", "Enquete", "name"),
    ("pollCreationMessageV3", "Enquete", "name"),
    ("locationMessage", "Localização", "name"),
    ("contactMessage", "Contato", "displayName"),
)


def resumo_da_publicacao(msg):
    """(tipo, texto) de uma mensagem de canal (waE2E Message): o tipo em
    português e o texto ou a legenda; ("Outro tipo", "") se nao reconhece."""
    for campo, rotulo, texto in TIPOS_DE_PUBLICACAO:
        try:
            if not msg.HasField(campo):
                continue
        except ValueError:
            continue
        valor = getattr(msg, campo)
        if texto is None:
            return rotulo, (valor if isinstance(valor, str) else "")
        return rotulo, (getattr(valor, texto, "") or "")
    return "Outro tipo", ""


def texto_das_publicacoes(canal_nome, itens):
    """O texto da janela "Ver publicações": da mais nova para a mais antiga.
    itens: [(id no servidor, tipo, texto, visualizacoes)]."""
    if not itens:
        return "%s não tem publicações para mostrar." % (
            canal_nome or "Este canal")
    linhas = ["Últimas %d publicações de %s, da mais nova para a mais "
              "antiga." % (len(itens), canal_nome or "este canal"), ""]
    for n, (_sid, tipo, texto, vistas) in enumerate(itens, 1):
        cabeca = "%d. %s" % (n, tipo)
        if vistas:
            cabeca += " (%d visualizações)" % vistas
        linhas.append(cabeca + (": " + texto.strip() if texto.strip()
                                else "."))
    return "\n".join(linhas)


def linha(c, limite_descricao=120):
    """A linha do canal na lista: nome, verificado, seguidores, se já segue e
    o começo da descrição."""
    partes = [c.nome or "Canal sem nome"]
    if c.verificado:
        partes.append("verificado")
    s = seguidores_por_extenso(c.seguidores)
    if s:
        partes.append(s)
    if c.seguindo:
        partes.append("você já segue")
    texto = ", ".join(partes)
    d = " ".join(c.descricao.split())
    if d:
        if len(d) > limite_descricao:
            d = d[:limite_descricao].rstrip() + "…"
        texto += ". " + d
    return texto


def resumo(n):
    """O que dizer quando a busca termina."""
    if n == 0:
        return "Nenhum canal encontrado."
    return "1 canal encontrado." if n == 1 else "%d canais encontrados." % n

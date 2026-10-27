# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Provedor do Telegram (Telethon), numa thread com o seu proprio asyncio.

Nada aqui toca na janela: os resultados saem como eventos. O registro nunca
grava texto de mensagens, telefones completos, codigos ou senhas.
"""
import asyncio
import logging
import os
import re
import threading
import time

from telezapp import NOME, VERSAO, config
from telezapp.midia import armazem
from telezapp.nucleo import eventos as ev
from telezapp.nucleo import mencoes as nucleo_mencoes
from telezapp.nucleo import modelos as m
from telezapp.nucleo import previa_links
from telezapp.provedores.base import (PEDIR_CODIGO, PEDIR_SENHA,
                                      PEDIR_TELEFONE, DownloadCancelado,
                                      ErroBloqueio, ErroMidia, ErroPerfil,
                                      ErroPrivacidade, Provedor)

log = logging.getLogger("telezapp.telegram")

LIMITE_CONVERSAS = 300
# Download em partes de 512 KB, 8 ao mesmo tempo: nos testes foi de 0,6 para
# cerca de 10 MB/s (docs/resultados-experimentos.md)
PARTE_DOWNLOAD = 512 * 1024
DOWNLOADS_PARALELOS = 8


# ----------------------------------------------------- conversao (testavel)
def tipo_da_mensagem(msg):
    """Tipo comum (modelos) de uma mensagem do Telethon."""
    if getattr(msg, "voice", None):
        return m.VOZ
    if getattr(msg, "video_note", None) or getattr(msg, "gif", None) or \
            getattr(msg, "video", None):
        return m.VIDEO
    if getattr(msg, "sticker", None):
        return m.FIGURINHA
    if getattr(msg, "photo", None):
        return m.FOTO
    if getattr(msg, "audio", None):
        return m.AUDIO
    if getattr(msg, "document", None):
        return m.DOCUMENTO
    if getattr(msg, "media", None) and not getattr(msg, "web_preview", None):
        return m.OUTRO
    return m.TEXTO


def _texto_extra(msg):
    """Descricao curta de tipos ainda sem suporte (enquete, local...)."""
    poll = getattr(msg, "poll", None)
    if poll is not None:
        try:
            return "enquete: " + poll.poll.question.text
        except AttributeError:
            return "enquete"
    if getattr(msg, "geo", None):
        return "localização"
    contato = getattr(msg, "contact", None)
    if contato is not None:
        nome = " ".join(p for p in (getattr(contato, "first_name", ""),
                                    getattr(contato, "last_name", "")) if p)
        telefone = getattr(contato, "phone_number", "") or ""
        if telefone and not telefone.startswith("+"):
            telefone = "+" + telefone
        return ", ".join(p for p in (
            "contato: " + nome if nome else "contato", telefone) if p)
    return ""


def somente_leitura_do_telegram(ent):
    """A conta nao pode escrever neste chat? Canal em que nao posta, grupo
    que so administradores usam, grupo de que saiu ou que foi desativado."""
    if ent is None:
        return False
    nome = type(ent).__name__
    if nome in ("ChatForbidden", "ChannelForbidden") or \
            getattr(ent, "left", False) or getattr(ent, "deactivated", False):
        return True
    direitos = getattr(ent, "admin_rights", None)
    admin = bool(getattr(ent, "creator", False) or direitos)
    if getattr(ent, "broadcast", False):
        return not (getattr(ent, "creator", False) or (
            direitos is not None and getattr(direitos, "post_messages",
                                             False)))
    for campo in ("banned_rights", "default_banned_rights"):
        r = getattr(ent, campo, None)
        if r is not None and getattr(r, "send_messages", False):
            return not admin or campo == "banned_rights" and not (
                getattr(ent, "creator", False))
    return False


def nome_de(entidade):
    """Nome para exibir de um usuario, grupo ou canal."""
    if entidade is None:
        return ""
    titulo = getattr(entidade, "title", None)
    if titulo:
        return titulo
    partes = [getattr(entidade, "first_name", "") or "",
              getattr(entidade, "last_name", "") or ""]
    nome = " ".join(p for p in partes if p).strip()
    if nome:
        return nome
    usuario = getattr(entidade, "username", "")
    return "@" + usuario if usuario else ""


LIMITE_BUSCAS_POR_VEZ = 10     # @usuarios novos resolvidos a cada lote


def _trecho(texto, offset, tamanho):
    """O Telegram conta posicoes em unidades UTF-16."""
    dados = texto.encode("utf-16-le")
    return dados[offset * 2:(offset + tamanho) * 2].decode("utf-16-le",
                                                           "ignore")


def _endereco(texto):
    return texto if texto.lower().startswith(("http://", "https://")) \
        else "https://" + texto


def _url_do_botao(botao):
    """Endereco de um botao que abre um link; '' para os outros (voto,
    callback, compra...). Vale para o formato novo do Telethon (o tipo do
    botao carrega o endereco) e para o antigo (KeyboardButtonUrl)."""
    tipo = getattr(botao, "type", None)
    if type(tipo).__name__ == "InlineButtonTypeUrl":
        return getattr(tipo, "url", "") or ""
    if type(botao).__name__ == "KeyboardButtonUrl":
        return getattr(botao, "url", "") or ""
    return ""


RE_CONVITE_TELEGRAM = re.compile(
    r"(?:t(?:elegram)?\.me/(?:\+|joinchat/)|tg://join\?invite=)"
    r"([A-Za-z0-9_-]{10,})", re.I)
RE_PUBLICO_TELEGRAM = re.compile(
    r"(?:^|[/@])(?:https?://)?(?:t|telegram)\.me/([A-Za-z][A-Za-z0-9_]{3,31})"
    r"/?(?:\?.*)?$", re.I)
RESERVADOS_TELEGRAM = {"joinchat", "addstickers", "addemoji", "share",
                       "proxy", "socks", "login", "setlanguage", "addtheme",
                       "bg", "boost", "iv", "invoice", "contact", "c", "s",
                       "m", "giftcode", "confirmphone"}


def entradas_do_telegram(links):
    """Botoes "Entrar" para os links de convite (t.me/+codigo, joinchat) e
    de grupos e canais publicos (t.me/nome). Tipo "entrar" nas acoes."""
    entradas, vistos = [], set()
    for url, _texto in links:
        achou = RE_CONVITE_TELEGRAM.search(url)
        if achou and achou.group(1) not in vistos:
            vistos.add(achou.group(1))
            entradas.append({"tipo": "entrar", "modo": "convite",
                             "codigo": achou.group(1),
                             "rotulo": "Entrar no grupo ou canal (convite)"})
            continue
        publico = RE_PUBLICO_TELEGRAM.search(url)
        if publico and publico.group(1).lower() not in RESERVADOS_TELEGRAM \
                and "usuario:" + publico.group(1).lower() not in vistos:
            vistos.add("usuario:" + publico.group(1).lower())
            entradas.append({"tipo": "entrar", "modo": "publico",
                             "usuario": publico.group(1),
                             "rotulo": "Entrar em @%s (grupo ou canal)" %
                             publico.group(1)})
    return entradas


# Cada pessoa (ou canal) com historias vira uma "conversa" de tipo status,
# `status:<id>`, com as historias como mensagens (id = id da historia)
PREFIXO_STATUS = "status:"

# Grupo com topicos (forum): o grupo e uma conversa da lista e cada topico e
# uma conversa `<grupo>#<topico>` ("Grupo › Tópico"), que a janela esconde da
# lista e abre quando a pessoa escolhe o topico. O Geral e sempre o numero 1.
SEPARADOR_TOPICO = "#"
TOPICO_GERAL = 1


def id_do_topico(chat_id, topico):
    return "%s%s%d" % (chat_id, SEPARADOR_TOPICO, int(topico))


def separar_topico(conversa_id):
    """(id do chat, topico) de uma conversa; topico 0 = conversa comum."""
    chat, sep, topico = str(conversa_id).partition(SEPARADOR_TOPICO)
    if sep and topico.isdigit():
        return chat, int(topico)
    return str(conversa_id), 0


def topico_da_mensagem(msg):
    """Topico de uma mensagem de grupo com topicos: o do cabecalho de
    resposta ou, sem ele, o Geral."""
    resp = getattr(msg, "reply_to", None)
    if resp is None or not getattr(resp, "forum_topic", False):
        return TOPICO_GERAL
    return int(getattr(resp, "reply_to_top_id", 0) or
               getattr(resp, "reply_to_msg_id", 0) or TOPICO_GERAL)


def nome_do_topico(grupo, titulo):
    return "%s › %s" % (grupo, titulo or "Tópico")
ATUALIZAR_HISTORIAS_A_CADA = 10      # segundos, entre duas buscas


def tipo_de_historia(media):
    """foto, video, audio ou documento de uma historia (ou outro)."""
    nome = type(media).__name__
    if nome == "MessageMediaPhoto":
        return m.FOTO
    doc = getattr(media, "document", None)
    if nome == "MessageMediaDocument" and doc is not None:
        for a in getattr(doc, "attributes", None) or []:
            ntipo = type(a).__name__
            if ntipo == "DocumentAttributeVideo":
                return m.VIDEO
            if ntipo == "DocumentAttributeAudio":
                return m.AUDIO
        return m.DOCUMENTO
    return m.OUTRO


def dados_da_midia_de_historia(media):
    """(segundos, nome do arquivo, tamanho, mime) da midia da historia."""
    segundos, nome, tamanho, mime = 0, "", 0, ""
    doc = getattr(media, "document", None)
    if doc is not None:
        tamanho = int(getattr(doc, "size", 0) or 0)
        mime = getattr(doc, "mime_type", "") or ""
        for a in getattr(doc, "attributes", None) or []:
            segundos = int(getattr(a, "duration", 0) or segundos)
            nome = getattr(a, "file_name", "") or nome
    foto = getattr(media, "photo", None)
    if foto is not None:
        mime = "image/jpeg"
        tamanhos = [getattr(t, "size", 0) or 0
                    for t in getattr(foto, "sizes", None) or []]
        tamanho = int(max(tamanhos)) if tamanhos else 0
    return segundos, nome, tamanho, mime


def mensagem_de_historia(conta_id, sid, item, nome, pid):
    """Mensagem para uma historia (StoryItem)."""
    media = getattr(item, "media", None)
    segundos, arquivo, tamanho, _ = dados_da_midia_de_historia(media)
    data = getattr(item, "date", None)
    return m.Mensagem(
        conta_id=conta_id, conversa_id=sid, id=str(item.id), autor=nome,
        minha=bool(getattr(item, "out", False)),
        data=data.timestamp() if data is not None else time.time(),
        tipo=tipo_de_historia(media), texto=getattr(item, "caption", "") or "",
        segundos=segundos, nome_arquivo=arquivo, tamanho=tamanho,
        remetente=str(pid))


def previa_do_telegram(msg):
    """A previa de link que o Telegram montou para a mensagem (titulo,
    descricao e nome do site); {} se nao ha."""
    pagina = getattr(msg, "web_preview", None)
    if pagina is None:
        return {}
    return m.previa_de_link(getattr(pagina, "url", "") or "",
                            getattr(pagina, "title", "") or "",
                            getattr(pagina, "description", "") or "",
                            getattr(pagina, "site_name", "") or "")


def extras_do_telegram(msg):
    """(links, botoes, mencoes) de uma mensagem do Telethon.

    links: [(endereco, texto visivel)], incluindo os escondidos atras de um
    texto; botoes: so os que abrem um endereco; mencoes: @usuario (a
    resolucao do nome e do id e feita depois) e mencoes por id."""
    texto = getattr(msg, "message", "") or ""
    links, mencoes = [], []
    vistos = set()
    for ent in getattr(msg, "entities", None) or []:
        nome = type(ent).__name__
        visivel = _trecho(texto, getattr(ent, "offset", 0),
                          getattr(ent, "length", 0))
        if nome == "MessageEntityTextUrl" and getattr(ent, "url", ""):
            url = ent.url
            if url not in vistos:
                vistos.add(url)
                links.append((url, visivel or url))
        elif nome == "MessageEntityUrl" and visivel:
            url = _endereco(visivel)
            if url not in vistos:
                vistos.add(url)
                links.append((url, visivel))
        elif nome == "MessageEntityMention" and visivel.startswith("@"):
            nova = {"usuario": visivel[1:]}
            if nova not in mencoes:
                mencoes.append(nova)
        elif nome == "MessageEntityMentionName":
            nova = {"id": str(ent.user_id), "nome": visivel}
            if nova not in mencoes:
                mencoes.append(nova)
    contato = getattr(msg, "contact", None)
    if contato is not None:
        nome_c = " ".join(p for p in (getattr(contato, "first_name", ""),
                                      getattr(contato, "last_name", "")) if p)
        telefone = getattr(contato, "phone_number", "") or ""
        if telefone and not telefone.startswith("+"):
            telefone = "+" + telefone
        id_c = getattr(contato, "user_id", 0) or 0
        if nome_c or telefone:
            mencoes.append({"nome": nome_c, "telefone": telefone,
                            "id": str(id_c) if id_c else ""})
    botoes = []
    markup = getattr(msg, "reply_markup", None)
    for linha in getattr(markup, "rows", None) or []:
        for b in getattr(linha, "buttons", None) or []:
            url = _url_do_botao(b)
            if url:
                botoes.append((getattr(b, "text", "") or url, url))
    return links, botoes, mencoes


def prazo_da_mensagem(msg):
    """Segundos das mensagens temporarias (ttl_period) de uma mensagem; 0 se
    nao ha."""
    try:
        return int(getattr(msg, "ttl_period", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _texto_de(x):
    """O texto de um campo que pode ser str ou TextWithEntities."""
    return str(getattr(x, "text", x) or "")


def aplicar_resultados(enq, results):
    """Poe em `enq` (dict da enquete) as contagens e as opcoes em que eu votei,
    a partir dos PollResults do Telegram. Sem os numeros (o Telegram esconde
    ate a pessoa votar), so o total, se vier."""
    if results is None:
        return enq
    lista = getattr(results, "results", None) or []
    if lista:
        por_opcao = {bytes(r.option).hex(): r for r in lista}
        enq["contagem"] = [int(getattr(por_opcao.get(i), "voters", 0) or 0)
                           for i in enq["ids"]]
        enq["meus"] = [n for n, i in enumerate(enq["ids"])
                       if getattr(por_opcao.get(i), "chosen", False)]
    elif getattr(results, "results", None) is not None:
        enq["meus"] = []
    total = getattr(results, "total_voters", None)
    if total is not None:
        enq["total"] = int(total)
    return enq


def enquete_do_telegram(msg):
    """Dados da enquete de uma mensagem do Telethon ({} se nao e enquete)."""
    media = getattr(msg, "poll", None)
    poll = getattr(media, "poll", None)
    if poll is None:
        return {}
    respostas = list(getattr(poll, "answers", None) or [])
    if not respostas:
        return {}
    enq = {"pergunta": _texto_de(poll.question),
           "opcoes": [_texto_de(a.text) for a in respostas],
           "ids": [bytes(a.option).hex() for a in respostas],
           "maximo": len(respostas) if getattr(poll, "multiple_choice",
                                               False) else 1,
           "encerrada": bool(getattr(poll, "closed", False)),
           "anonima": not bool(getattr(poll, "public_voters", False)),
           "poll_id": str(getattr(poll, "id", "") or "")}
    return aplicar_resultados(enq, getattr(media, "results", None))


def converter(msg, conta_id, conversa_id, lidas_ate=0, nome_padrao=""):
    """Mensagem do Telethon -> modelos.Mensagem (None para mensagens de
    servico, como 'fulano entrou no grupo')."""
    if getattr(msg, "action", None) is not None:
        return None
    tipo = tipo_da_mensagem(msg)
    texto = getattr(msg, "message", "") or ""
    if tipo == m.OUTRO:
        texto = _texto_extra(msg) or texto
    arq = getattr(msg, "file", None) if tipo not in (m.TEXTO, m.OUTRO) \
        else None
    segundos = int(round(getattr(arq, "duration", 0) or 0)) if arq else 0
    nome_arquivo = (getattr(arq, "name", "") or "") if arq else ""
    tamanho = (getattr(arq, "size", 0) or 0) if arq else 0
    minha = bool(getattr(msg, "out", False))
    if minha:
        autor = ""
    else:
        autor = nome_de(getattr(msg, "sender", None)) or \
            (getattr(msg, "post_author", "") or "") or nome_padrao
    estado = ""
    if minha:
        estado = m.LIDA if lidas_ate and msg.id <= lidas_ate else m.ENVIADA
    resposta = getattr(msg, "reply_to", None)
    resposta_a = getattr(resposta, "reply_to_msg_id", None) if resposta \
        else None
    data = getattr(msg, "date", None)
    nova = m.Mensagem(
        conta_id=conta_id, conversa_id=str(conversa_id), id=str(msg.id),
        autor=autor, minha=minha,
        data=data.timestamp() if data is not None else time.time(),
        tipo=tipo, texto=texto, segundos=segundos,
        nome_arquivo=nome_arquivo, tamanho=tamanho, estado=estado,
        resposta_a=str(resposta_a) if resposta_a else "")
    nova.expira = m.expira_em(nova.data, prazo_da_mensagem(msg))
    links, botoes, mencoes = extras_do_telegram(msg)
    m.guardar_extras(nova, links, botoes, mencoes,
                     acoes=entradas_do_telegram(links),
                     previa=previa_do_telegram(msg))
    enquete = enquete_do_telegram(msg)
    if enquete:
        m.atualizar_extras(nova, enquete=enquete)
    # o Telegram marca as mensagens que citam esta conta (@ ou nome)
    if not minha and getattr(msg, "mentioned", False) is True:
        m.atualizar_extras(nova, citou_voce=True)
    # voz ou audio que o Telegram diz ja ter sido tocado (em outro aparelho)
    if not minha and tipo in (m.VOZ, m.AUDIO) and \
            getattr(msg, "media_unread", None) is False:
        m.atualizar_extras(nova, ouvida=True)
    return nova


# --------------------------------------------------------- privacidade
_COM_EXCECOES = ("PrivacyValueAllowUsers", "PrivacyValueDisallowUsers",
                 "PrivacyValueAllowChatParticipants",
                 "PrivacyValueDisallowChatParticipants",
                 "PrivacyValueAllowPremium", "PrivacyValueAllowBots",
                 "PrivacyValueDisallowBots")


def valor_das_regras(regras):
    """all, contacts ou none, conforme as regras de privacidade do Telegram;
    None quando ha excecoes por pessoa ou grupo (so o aplicativo as edita)
    ou o valor e desconhecido."""
    nomes = [type(r).__name__ for r in regras or ()]
    if any(n in _COM_EXCECOES for n in nomes):
        return None
    if "PrivacyValueAllowAll" in nomes:
        return "all"
    if "PrivacyValueAllowContacts" in nomes:
        return "contacts"
    if "PrivacyValueDisallowAll" in nomes:
        return "none"
    return None


# campo -> tipo da chave de privacidade do Telegram
CHAVES_PRIVACIDADE = {"last": "InputPrivacyKeyStatusTimestamp",
                      "status": "InputPrivacyKeyAbout",
                      "groupadd": "InputPrivacyKeyChatInvite"}
_REGRA_DO_VALOR = {"all": "InputPrivacyValueAllowAll",
                   "contacts": "InputPrivacyValueAllowContacts",
                   "none": "InputPrivacyValueDisallowAll"}


def silencio_do_dialogo(d):
    """0.0 (com som), -1.0 (para sempre) ou o timestamp do fim do silencio
    de um dialogo do Telegram."""
    try:
        ate = d.dialog.notify_settings.mute_until
    except AttributeError:
        return 0.0
    if not ate:
        return 0.0
    ate = ate.timestamp() if hasattr(ate, "timestamp") else float(ate)
    if ate <= time.time():
        return 0.0
    return -1.0 if ate > time.time() + 5 * 365 * 86400 else ate


def tipo_da_conversa(dialogo):
    if getattr(dialogo, "is_channel", False) and not \
            getattr(dialogo, "is_group", False):
        return "canal"
    if getattr(dialogo, "is_group", False):
        return "grupo"
    return "privada"


# ---------------------------------------------------------------- provedor
class ProvedorTelegram(Provedor):
    servico = "telegram"

    def __init__(self, conta, barramento, banco, pedir, credenciais,
                 pasta_sessoes=None, perguntar_telefone=False):
        super().__init__(conta, barramento, banco, pedir)
        self.credenciais = credenciais          # (api_id, api_hash)
        # conta nova: sempre mostra o campo do numero (com a sugestao)
        self.perguntar_telefone = perguntar_telefone
        self.pasta_sessoes = pasta_sessoes or config.pasta("sessoes")
        self.cliente = None
        self._loop = None
        self._thread = None
        self._entidades = {}                    # conversa_id -> InputPeer
        self._observada = None                  # conversa com a presenca aberta
        self._historias_em = 0.0                # ultima busca de historias
        self._conversas = {}                    # conversa_id -> Conversa
        self._foruns = set()                    # grupos com topicos (ids)
        self._usuarios = {}                     # @usuario -> dados ou None
        self._pronto = threading.Event()
        self._chamadas = None                   # ChamadasTelegram, se houver
        self._destino_video = None              # f(cid, largura, altura, rgb)

    # ----------------------------------------------------------- execucao
    def iniciar(self):
        if self._thread is not None:
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._rodar, name="telegram-" + self.conta.id, daemon=True)
        self._thread.start()

    def _rodar(self):
        asyncio.set_event_loop(self._loop)
        self._loop.create_task(self._protegido(self._conectar()))
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    def _agendar(self, corotina):
        if self._loop is None or self._loop.is_closed():
            corotina.close()
            return None
        return asyncio.run_coroutine_threadsafe(
            self._protegido(corotina), self._loop)

    async def _protegido(self, corotina):
        from telethon import errors
        try:
            return await corotina
        except errors.FloodWaitError as e:
            log.warning("limite do Telegram: esperar %ss", e.seconds)
            self._avisar("O Telegram pediu para esperar %d segundos antes "
                         "de tentar de novo." % e.seconds)
        except (ConnectionError, OSError) as e:
            log.warning("falha de conexao: %r", e)
            self._avisar("Sem conexão com o Telegram. Ele tenta reconectar "
                         "sozinho.")
        except Exception:
            log.exception("erro no provedor do Telegram")
            self._avisar("Erro no Telegram. Os detalhes estão no log.")

    def contatos_da_conta(self):
        """[(id, nome, telefone)] dos contatos salvos na conta do Telegram
        (os mesmos que o aplicativo mostra em Contatos)."""
        try:
            return self._executar(self._ler_contatos())
        except Exception:
            log.info("não consegui ler os contatos do Telegram")
            return []

    async def _ler_contatos(self):
        from telethon.tl import functions
        r = await self.cliente(functions.contacts.GetContactsRequest(hash=0))
        achados = []
        for u in getattr(r, "users", None) or []:
            if getattr(u, "bot", False) or getattr(u, "deleted", False):
                continue
            nome = nome_de(u)
            if not nome:
                continue
            fone = getattr(u, "phone", "") or ""
            achados.append((str(u.id), nome, "+" + fone if fone else ""))
        return achados

    def resolver_destinatario(self, texto):
        """@usuario, telefone de contato ou id: acha a pessoa no Telegram."""
        try:
            return self._executar(self._resolver_destinatario(texto))
        except Exception:
            log.info("não achei o destinatário no Telegram")
            return None

    async def _resolver_destinatario(self, texto):
        from telethon import utils
        entidade = await self.cliente.get_entity(texto)
        cid = str(utils.get_peer_id(entidade))
        self._entidades[cid] = await self.cliente.get_input_entity(entidade)
        return cid, nome_de(entidade)

    # ------------------------------------------------------ privacidade
    def _executar(self, corotina, espera=20):
        """Roda no loop do Telegram e devolve o resultado (ou levanta o
        erro), sem o aviso generico de _protegido."""
        if self._loop is None or self._loop.is_closed():
            corotina.close()
            raise ErroPrivacidade("A conta do Telegram não está conectada.")
        return asyncio.run_coroutine_threadsafe(
            corotina, self._loop).result(timeout=espera)

    def privacidade(self):
        try:
            return self._executar(self._ler_privacidade())
        except Exception:
            log.exception("não consegui ler a privacidade do Telegram")
            return None

    async def _ler_privacidade(self):
        from telethon.tl import functions, types
        valores = {}
        for campo, nome in CHAVES_PRIVACIDADE.items():
            tipo = getattr(types, nome, None)
            if tipo is None:
                continue
            r = await self.cliente(functions.account.GetPrivacyRequest(
                tipo()))
            valores[campo] = valor_das_regras(r.rules)
        g = await self.cliente(
            functions.account.GetGlobalPrivacySettingsRequest())
        valores["readreceipts"] = "none" if getattr(
            g, "hide_read_marks", False) else "all"
        return valores

    def definir_privacidade(self, campo, valor):
        try:
            self._executar(self._gravar_privacidade(campo, valor))
        except ErroPrivacidade:
            raise
        except Exception as e:
            if "PREMIUM" in str(e).upper():
                raise ErroPrivacidade(
                    "Esta opção exige Telegram Premium.") from e
            raise

    async def _gravar_privacidade(self, campo, valor):
        from telethon.tl import functions, types
        if campo == "readreceipts":
            atual = await self.cliente(
                functions.account.GetGlobalPrivacySettingsRequest())
            atual.hide_read_marks = valor == "none"
            await self.cliente(functions.account.SetGlobalPrivacySettingsRequest(
                settings=atual))
            return
        tipo = getattr(types, CHAVES_PRIVACIDADE.get(campo, ""), None)
        regra = getattr(types, _REGRA_DO_VALOR.get(valor, ""), None)
        if tipo is None or regra is None:
            raise ErroPrivacidade("Esta opção não existe no Telegram.")
        await self.cliente(functions.account.SetPrivacyRequest(
            key=tipo(), rules=[regra()]))

    # ------------------------------------------------------------ perfil
    PODE_EDITAR_PERFIL = True
    PERFIL_SOBRENOME = True

    def _executar_perfil(self, corotina, falha):
        """Como _executar, mas todo erro vira ErroPerfil com o texto `falha`."""
        try:
            return self._executar(corotina)
        except ErroPerfil:
            raise
        except ErroPrivacidade as e:          # conta nao conectada
            raise ErroPerfil(str(e)) from e
        except Exception as e:
            log.exception("perfil do Telegram")
            raise ErroPerfil(falha) from e

    def meu_perfil(self):
        return self._executar_perfil(
            self._ler_perfil(), "Não consegui ler o seu perfil no Telegram.")

    async def _ler_perfil(self):
        from telethon.tl import functions, types
        eu = await self.cliente.get_me()
        completo = await self.cliente(functions.users.GetFullUserRequest(
            types.InputUserSelf()))
        return {"nome": getattr(eu, "first_name", "") or "",
                "sobrenome": getattr(eu, "last_name", "") or "",
                "recado": getattr(completo.full_user, "about", "") or ""}

    def salvar_perfil(self, mudancas, foto=None):
        return self._executar_perfil(
            self._gravar_perfil(mudancas, foto),
            "Não consegui salvar o perfil no Telegram.")

    async def _gravar_perfil(self, mudancas, foto):
        import io
        from telethon import errors
        from telethon.tl import functions
        feitos, erros = [], []
        campos = {"nome": "first_name", "sobrenome": "last_name",
                  "recado": "about"}
        pedido = {campos[c]: mudancas[c] for c in campos if c in mudancas}
        if pedido:
            try:
                await self.cliente(functions.account.UpdateProfileRequest(
                    **pedido))
                feitos += [c for c in campos if c in mudancas]
            except errors.FirstNameInvalidError:
                erros.append(("nome", "o Telegram não aceitou esse nome."))
            except errors.AboutTooLongError:
                erros.append(("recado", "passou do limite do Telegram (70 "
                              "caracteres; 140 com Premium)."))
            except errors.FloodWaitError as e:
                erros.append(("nome", "o Telegram pediu para esperar %d "
                              "segundos." % e.seconds))
            except Exception as e:
                log.warning("perfil do Telegram: %s", type(e).__name__)
                erros.append(("nome", "o Telegram não aceitou (%s)."
                              % type(e).__name__))
        if foto:
            try:
                arquivo = io.BytesIO(foto)
                arquivo.name = "foto.jpg"
                enviado = await self.cliente.upload_file(arquivo)
                await self.cliente(functions.photos.UploadProfilePhotoRequest(
                    file=enviado))
                feitos.append("foto")
            except (errors.PhotoInvalidError, errors.ImageProcessFailedError):
                erros.append(("foto", "o Telegram não aceitou essa imagem."))
            except Exception as e:
                log.warning("foto do Telegram: %s", type(e).__name__)
                erros.append(("foto", "o Telegram não aceitou (%s)."
                              % type(e).__name__))
        return feitos, erros

    # ------------------------------------------------------- bloqueados
    PODE_BLOQUEAR = True

    def _executar_bloqueio(self, corotina, falha):
        """Como _executar, mas todo erro vira ErroBloqueio com o texto
        `falha` (ou o proprio texto, quando ja e um ErroBloqueio)."""
        try:
            return self._executar(corotina)
        except ErroBloqueio:
            raise
        except ErroPrivacidade as e:          # conta nao conectada
            raise ErroBloqueio(str(e)) from e
        except Exception as e:
            log.exception("bloqueados do Telegram")
            raise ErroBloqueio(falha) from e

    def bloqueados(self):
        return self._executar_bloqueio(
            self._ler_bloqueados(),
            "Não consegui ler a lista de bloqueados do Telegram.")

    async def _ler_bloqueados(self):
        from telethon.tl import functions
        achados, vistos, inicio = [], set(), 0
        while True:
            r = await self.cliente(functions.contacts.GetBlockedRequest(
                offset=inicio, limit=100))
            bloqueados = getattr(r, "blocked", None) or []
            por_id = {u.id: u for u in getattr(r, "users", None) or []}
            for b in bloqueados:
                u = por_id.get(getattr(b.peer_id, "user_id", None))
                if u is None or str(u.id) in vistos:
                    continue
                vistos.add(str(u.id))
                fone = getattr(u, "phone", "") or ""
                achados.append((str(u.id), nome_de(u) or str(u.id),
                                "+" + fone if fone else ""))
            inicio += len(bloqueados)
            if not bloqueados or inicio >= getattr(r, "count", inicio):
                return achados

    def _id_de_pessoa(self, conversa_id):
        """Id numerico do usuario da conversa; so pessoas se bloqueiam."""
        try:
            id_ = int(conversa_id)
        except ValueError:
            id_ = 0
        if id_ <= 0:
            raise ErroBloqueio("Só dá para bloquear pessoas.")
        return id_

    def esta_bloqueado(self, conversa_id):
        self._id_de_pessoa(conversa_id)
        return self._executar_bloqueio(
            self._ver_se_bloqueado(conversa_id),
            "Não consegui ver se a pessoa está bloqueada no Telegram.")

    async def _ver_se_bloqueado(self, conversa_id):
        from telethon.tl import functions
        completo = await self.cliente(functions.users.GetFullUserRequest(
            await self._entidade(conversa_id)))
        return bool(getattr(completo.full_user, "blocked", False))

    def bloquear(self, conversa_id, bloquear=True):
        self._id_de_pessoa(conversa_id)
        self._executar_bloqueio(
            self._mudar_bloqueio(conversa_id, bloquear),
            "O Telegram não aceitou %s a pessoa."
            % ("bloquear" if bloquear else "desbloquear"))

    async def _mudar_bloqueio(self, conversa_id, bloquear):
        from telethon.tl import functions
        pedido = functions.contacts.BlockRequest if bloquear \
            else functions.contacts.UnblockRequest
        await self.cliente(pedido(id=await self._entidade(conversa_id)))

    def _avisar(self, texto, grave=False):
        self.barramento.publicar(ev.Aviso(self.conta.id, texto, grave))

    def _estado(self, estado, detalhe=""):
        log.info("estado: %s %s", estado, detalhe)
        self.barramento.publicar(ev.EstadoConta(self.conta.id, estado,
                                                detalhe))

    def parar(self):
        if self._loop is None or self._loop.is_closed():
            return

        async def fechar():
            if self.cliente is not None:
                try:
                    await self.cliente.disconnect()
                except Exception:
                    log.exception("erro ao desconectar")
            self._loop.stop()
        try:
            asyncio.run_coroutine_threadsafe(fechar(), self._loop)
        except RuntimeError:
            return
        if self._thread is not None:
            self._thread.join(timeout=6)

    # -------------------------------------------------------------- login
    async def _perguntar(self, etapa, erro=""):
        return await asyncio.get_running_loop().run_in_executor(
            None, self.pedir, etapa, erro)

    def _novo_cliente(self):
        from telethon import TelegramClient
        api_id, api_hash = self.credenciais
        caminho = os.path.join(self.pasta_sessoes, self.conta.id)
        return TelegramClient(
            caminho, api_id, api_hash, device_model=NOME,
            system_version="Windows", app_version=VERSAO, lang_code="pt",
            system_lang_code="pt-BR")

    async def _conectar(self):
        from telethon import events
        from telethon.tl import types as tipos
        self._estado(ev.CONECTANDO)
        inicio = time.perf_counter()
        self.cliente = self._novo_cliente()
        await self.cliente.connect()
        log.info("conectou aos servidores em %.2fs",
                 time.perf_counter() - inicio)
        if not await self.cliente.is_user_authorized():
            if not await self._login():
                self._estado(ev.PRECISA_LOGIN, "login cancelado")
                await self.cliente.disconnect()
                return
        eu = await self.cliente.get_me()
        telefone = "+" + eu.phone if getattr(eu, "phone", None) else \
            self.conta.telefone
        self.conta.nome = nome_de(eu) or self.conta.nome
        self.conta.telefone = telefone
        self.barramento.publicar(ev.ContaPronta(
            self.conta.id, self.conta.nome, telefone))
        self.cliente.add_event_handler(self._ao_receber, events.NewMessage())
        self.cliente.add_event_handler(
            self._ao_ler, events.MessageRead(inbox=False))
        self.cliente.add_event_handler(self._ao_acao_no_chat,
                                       events.ChatAction())
        self.cliente.add_event_handler(self._ao_mensagens_apagadas,
                                       events.MessageDeleted())
        self.cliente.add_event_handler(
            self._ao_conteudo_lido,
            events.Raw((tipos.UpdateReadMessagesContents,
                        tipos.UpdateChannelReadMessagesContents)))
        self.cliente.add_event_handler(self._ao_usuario, events.UserUpdate())
        self.cliente.add_event_handler(
            self._ao_reacoes, events.Raw(tipos.UpdateMessageReactions))
        self.cliente.add_event_handler(
            self._ao_enquete, events.Raw(tipos.UpdateMessagePoll))
        self.cliente.add_event_handler(
            self._ao_historia, events.Raw(tipos.UpdateStory))
        self._estado(ev.CONECTADA)
        self._pronto.set()
        await self._atualizar_conversas()
        await self._iniciar_chamadas()

    async def _login(self):
        """Pede telefone, codigo e senha pela interface. False se cancelar."""
        from telethon import errors
        telefone = "" if self.perguntar_telefone else self.conta.telefone
        erro = ""
        while True:
            if not telefone:
                resposta = await self._perguntar(PEDIR_TELEFONE, erro)
                if resposta is None:
                    return False
                self.conta.telefone = resposta
                telefone = m.normalizar_telefone(resposta)
                if telefone is None:
                    erro = "Número inválido. Use DDD e número, por exemplo " \
                           "51 99999 8888."
                    continue
            try:
                await self.cliente.send_code_request(telefone)
                log.info("codigo pedido para %s",
                         config.mascarar_telefone(telefone))
                self.perguntar_telefone = False
                break
            except errors.PhoneNumberInvalidError:
                erro = "O Telegram não reconheceu esse número."
                telefone = ""
            except errors.PhoneNumberBannedError:
                self._avisar("Esse número está bloqueado no Telegram.", True)
                return False
        self.conta.telefone = telefone

        erro = ""
        while True:
            codigo = await self._perguntar(PEDIR_CODIGO, erro)
            if codigo is None:
                return False
            codigo = "".join(c for c in codigo if c.isdigit())
            try:
                await self.cliente.sign_in(telefone, codigo)
                log.info("login com codigo concluido")
                return True
            except errors.PhoneCodeInvalidError:
                erro = "Código incorreto. Confira e digite de novo."
            except errors.PhoneCodeExpiredError:
                await self.cliente.send_code_request(telefone)
                erro = "O código expirou. Um novo código foi enviado."
            except errors.SessionPasswordNeededError:
                break

        erro = ""
        while True:
            senha = await self._perguntar(PEDIR_SENHA, erro)
            if senha is None:
                return False
            try:
                await self.cliente.sign_in(password=senha)
                log.info("login com senha de duas etapas concluido")
                return True
            except errors.PasswordHashInvalidError:
                erro = "Senha incorreta. Tente de novo."

    # ---------------------------------------------------------- conversas
    def atualizar_conversas(self):
        self._agendar(self._atualizar_conversas())

    async def _atualizar_conversas(self):
        inicio = time.perf_counter()
        lista = []
        citacoes = {x.id: x.citacoes
                    for x in self.banco.conversas(self.conta.id)}
        # O Telegram so devolve a pasta principal (0) se nao se pede a
        # pasta de arquivadas (1): sao duas buscas.
        for pasta in (0, 1):
            async for d in self.cliente.iter_dialogs(
                    limit=LIMITE_CONVERSAS, folder=pasta):
                cid = str(d.id)
                self._entidades[cid] = d.input_entity
                c = m.Conversa(
                    conta_id=self.conta.id, id=cid,
                    nome=d.name or "Sem nome",
                    servico=self.servico, tipo=tipo_da_conversa(d),
                    nao_lidas=d.unread_count or 0,
                    data=d.date.timestamp() if d.date else 0.0,
                    lidas_ate=getattr(d.dialog, "read_outbox_max_id", 0) or 0,
                    arquivada=pasta == 1,
                    fixada=bool(getattr(d, "pinned", False)),
                    silenciada_ate=silencio_do_dialogo(d),
                    somente_leitura=somente_leitura_do_telegram(
                        getattr(d, "entity", None)),
                    temporaria_s=int(getattr(d.dialog, "ttl_period", 0) or 0))
                # o Telegram conta as mencoes e respostas nao lidas; a conta
                # guardada cobre o que chegou ao vivo
                c.citacoes = max(
                    citacoes.get(cid, 0),
                    int(getattr(d.dialog, "unread_mentions_count", 0) or 0))
                self._conversas[cid] = c
                if getattr(getattr(d, "entity", None), "forum", False):
                    topicos = await self._conversas_de_topicos(d, c)
                    if topicos:
                        # o grupo fica na lista e a janela pergunta o topico
                        # ao abrir; os topicos viajam junto, fora da lista
                        self._foruns.add(cid)
                        c.data = max([c.data] + [t.data for t in topicos])
                        c.nao_lidas = sum(t.nao_lidas for t in topicos)
                        lista += topicos
                lista.append(c)
        self.banco.salvar_conversas(lista)
        log.info("conversas: %d em %.2fs", len(lista),
                 time.perf_counter() - inicio)
        lista += [c for c in self._conversas.values() if c.tipo == "status"]
        self.barramento.publicar(ev.ConversasAtualizadas(self.conta.id, lista))
        await self._atualizar_historias()

    PODE_TEMPORARIAS = True

    def definir_temporaria(self, conversa_id, segundos):
        """Liga ou desliga as mensagens temporarias (setHistoryTTL)."""
        entidade = self._entidades.get(conversa_id)
        if entidade is None:
            return
        self._agendar(self._definir_temporaria(conversa_id, entidade,
                                               int(segundos or 0)))

    async def _definir_temporaria(self, conversa_id, entidade, segundos):
        from telethon.tl.functions.messages import SetHistoryTTLRequest
        try:
            await self.cliente(SetHistoryTTLRequest(peer=entidade,
                                                    period=segundos))
        except Exception as e:
            log.warning("mensagens temporárias: falhou: %s", type(e).__name__)
            self.barramento.publicar(ev.Aviso(
                self.conta.id, "Não consegui mudar as mensagens temporárias "
                "(%s)." % type(e).__name__, True))
            return
        conv = self._conversas.get(conversa_id)
        if conv is not None:
            self._temporaria_mudou(conv, segundos, True)

    def _temporaria_mudou(self, conv, segundos, minha):
        """O prazo das mensagens temporarias mudou (aqui ou em outro
        aparelho)."""
        if conv.temporaria_s == segundos:
            return
        conv.temporaria_s = segundos
        self.banco.salvar_conversas([conv])
        lista = sorted(self._conversas.values(), key=lambda c: -c.data)
        self.barramento.publicar(ev.ConversasAtualizadas(self.conta.id,
                                                         lista))
        self.barramento.publicar(ev.Aviso(
            self.conta.id, "%s as mensagens temporárias de %s: %s." % (
                "Você mudou" if minha else "Mudaram", conv.nome,
                m.texto_periodo(segundos, "telegram"))))

    def fixar_conversa(self, conversa_id, fixar):
        """Fixa a conversa no topo (ou tira a fixacao) na conta."""
        entidade = self._entidades.get(conversa_id)
        if entidade is None:
            return False
        from telethon.tl.functions.messages import ToggleDialogPinRequest
        self._agendar(self.cliente(ToggleDialogPinRequest(
            peer=entidade, pinned=bool(fixar))))
        return True

    def silenciar_conversa(self, conversa_id, silenciar, segundos=0):
        """Silencia a conversa por `segundos` (0 = para sempre) ou reativa."""
        entidade = self._entidades.get(conversa_id)
        if entidade is None:
            return False
        from telethon.tl.functions.account import UpdateNotifySettingsRequest
        from telethon.tl.types import InputNotifyPeer, InputPeerNotifySettings
        ate = 0
        if silenciar:
            ate = int(time.time() + segundos) if segundos else 2 ** 31 - 1
        self._agendar(self.cliente(UpdateNotifySettingsRequest(
            peer=InputNotifyPeer(peer=entidade),
            settings=InputPeerNotifySettings(mute_until=ate))))
        return True

    def arquivar_conversa(self, conversa_id, arquivar):
        """Move a conversa para a pasta Arquivadas (ou de volta) na conta."""
        entidade = self._entidades.get(conversa_id)
        if entidade is None:
            return False
        self._agendar(self.cliente.edit_folder(entidade, 1 if arquivar else 0))
        return True

    # ----------------------------------------- detalhes da conversa
    def _sincrono(self, corotina, tempo=20):
        futuro = self._agendar(corotina)
        if futuro is None:
            return None
        try:
            return futuro.result(tempo)
        except Exception:
            log.info("consulta ao Telegram sem resposta")
            return None

    def dados_do_contato(self, conversa_id):
        async def ler():
            ent = await self.cliente.get_entity(self._chat_id(conversa_id))
            dados = {}
            if getattr(ent, "phone", None):
                dados["telefone"] = "+" + ent.phone.lstrip("+")
            if getattr(ent, "username", None):
                dados["usuario"] = "@" + ent.username
            return dados
        return self._sincrono(ler()) or {}

    def detalhes_do_grupo(self, conversa_id):
        async def ler():
            from telethon.tl import functions, types as T
            ent = await self.cliente.get_entity(self._chat_id(conversa_id))
            gente = []
            async for u in self.cliente.iter_participants(ent, limit=500):
                papel = type(getattr(u, "participant", None)).__name__
                gente.append({
                    "id": str(u.id), "nome": nome_de(u),
                    "telefone": ("+" + u.phone) if getattr(u, "phone", None)
                    else "", "usuario": ("@" + u.username)
                    if getattr(u, "username", None) else "",
                    "admin": "Admin" in papel or "Creator" in papel,
                    "dono": "Creator" in papel, "eu": bool(
                        getattr(u, "is_self", False))})
            gente.sort(key=lambda x: (not x["dono"], not x["admin"],
                                      x["nome"].lower()))
            sobre = ""
            try:
                if isinstance(ent, T.Channel):
                    cheio = await self.cliente(
                        functions.channels.GetFullChannelRequest(ent))
                else:
                    cheio = await self.cliente(
                        functions.messages.GetFullChatRequest(ent.id))
                sobre = cheio.full_chat.about or ""
            except Exception:
                pass
            direitos = getattr(ent, "admin_rights", None)
            return {
                "nome": nome_de(ent), "descricao": sobre, "dono": "",
                "criado_em": ent.date.timestamp() if getattr(
                    ent, "date", None) else 0.0,
                "anuncio": bool(getattr(getattr(
                    ent, "default_banned_rights", None), "send_messages",
                    False)),
                "trancado": bool(getattr(getattr(
                    ent, "default_banned_rights", None), "change_info",
                    False)), "comunidade": False,
                "da_comunidade": False,
                "sou_admin": bool(getattr(ent, "creator", False) or direitos),
                "participantes": gente}
        return self._sincrono(ler(), 40)

    def previa_do_convite(self, msg, acao):
        return self._sincrono(self._previa(acao), 25) or {
            "erro": "O Telegram não respondeu."}

    async def _previa(self, acao):
        from telethon.tl import functions, types as T
        try:
            if acao.get("modo") == "convite":
                r = await self.cliente(functions.messages.CheckChatInviteRequest(
                    acao["codigo"]))
                if isinstance(r, T.ChatInviteAlready):
                    return {"nome": nome_de(r.chat), "membros": 0,
                            "descricao": "", "ja_participa": True}
                return {"nome": r.title,
                        "membros": int(r.participants_count or 0),
                        "descricao": getattr(r, "about", "") or "",
                        "ja_participa": False}
            ent = await self.cliente.get_entity(acao["usuario"])
            if isinstance(ent, T.User):
                return {"erro": "Este endereço é de uma pessoa ou de um bot, "
                                "não de um grupo ou canal."}
            return {"nome": nome_de(ent), "membros": int(
                getattr(ent, "participants_count", 0) or 0), "descricao": "",
                "ja_participa": bool(not getattr(ent, "left", True))}
        except Exception as e:
            log.info("prévia do convite falhou: %s", type(e).__name__)
            return {"erro": "O convite não vale mais ou foi cancelado."}

    def entrar_no_grupo(self, msg, acao):
        return self._sincrono(self._entrar(acao), 30) or (
            False, "O Telegram não respondeu.")

    async def _entrar(self, acao):
        from telethon import errors
        from telethon.tl import functions
        try:
            if acao.get("modo") == "convite":
                await self.cliente(functions.messages.ImportChatInviteRequest(
                    acao["codigo"]))
            else:
                ent = await self.cliente.get_entity(acao["usuario"])
                await self.cliente(functions.channels.JoinChannelRequest(ent))
        except errors.InviteRequestSentError:
            return True, ("O pedido para entrar foi enviado. Um "
                          "administrador precisa aprovar.")
        except errors.UserAlreadyParticipantError:
            return False, "Você já está neste grupo ou canal."
        except Exception as e:
            log.warning("entrar falhou: %s", type(e).__name__)
            return False, ("O Telegram não deixou entrar (%s)." %
                           type(e).__name__)
        self._agendar(self._atualizar_conversas())
        return True, "Você entrou."

    def administrar_grupo(self, conversa_id, acao, valor=None):
        resposta = self._sincrono(
            self._administrar(conversa_id, acao, valor), 45)
        return resposta or (False, "O Telegram não respondeu.")

    async def _administrar(self, cid, acao, valor):
        from telethon.tl import functions, types as T
        try:
            ent = await self.cliente.get_entity(self._chat_id(cid))
            peer = await self.cliente.get_input_entity(ent)
            canal = isinstance(ent, T.Channel)
            if acao == "nome":
                if canal:
                    await self.cliente(functions.channels.EditTitleRequest(
                        ent, valor))
                else:
                    await self.cliente(
                        functions.messages.EditChatTitleRequest(
                            ent.id, valor))
                return True, "Nome do grupo mudado."
            if acao == "descricao":
                await self.cliente(functions.messages.EditChatAboutRequest(
                    peer, valor))
                return True, "Descrição do grupo mudada."
            if acao in ("anuncio", "trancado"):
                atuais = getattr(ent, "default_banned_rights", None)
                flags = {k: v for k, v in (atuais.to_dict().items()
                                           if atuais else [])
                         if isinstance(v, bool)}
                flags["send_messages" if acao == "anuncio"
                      else "change_info"] = bool(valor)
                await self.cliente(
                    functions.messages.EditChatDefaultBannedRightsRequest(
                        peer, T.ChatBannedRights(until_date=None, **flags)))
                if acao == "anuncio":
                    return True, ("Agora só administradores enviam "
                                  "mensagens." if valor else
                                  "Agora todos enviam mensagens.")
                return True, ("Agora só administradores editam o grupo."
                              if valor else "Agora todos editam o grupo.")
            if acao == "adicionar":
                texto = str(valor).strip()
                digitos = "".join(c for c in texto if c.isdigit())
                alvo = texto if texto.startswith("@") else (
                    "+" + digitos if digitos else "")
                if not alvo:
                    return False, "Digite @usuário ou o telefone com país."
                usuario = await self.cliente.get_entity(alvo)
                if canal:
                    await self.cliente(functions.channels.InviteToChannelRequest(
                        ent, [usuario]))
                else:
                    await self.cliente(functions.messages.AddChatUserRequest(
                        ent.id, usuario, fwd_limit=50))
                return True, "Participante adicionado."
            if acao in ("remover", "promover", "rebaixar"):
                usuario = await self.cliente.get_entity(int(valor))
                if acao == "remover":
                    await self.cliente.kick_participant(ent, usuario)
                    return True, "Participante removido."
                if acao == "promover":
                    await self.cliente.edit_admin(
                        ent, usuario, is_admin=True, change_info=True,
                        delete_messages=True, ban_users=True,
                        invite_users=True, pin_messages=True)
                    return True, "Agora é administrador."
                await self.cliente.edit_admin(ent, usuario, is_admin=False)
                return True, "Deixou de ser administrador."
            if acao in ("link", "revogar_link"):
                convite = await self.cliente(
                    functions.messages.ExportChatInviteRequest(
                        peer, legacy_revoke_permanent=(
                            True if acao == "revogar_link" else None)))
                return True, convite.link
            if acao == "sair":
                await self.cliente.delete_dialog(ent)
                return True, "Você saiu do grupo."
        except Exception as e:
            log.warning("administrar grupo (%s) falhou: %s", acao,
                        type(e).__name__)
            return False, "O Telegram não aceitou (%s)." % type(e).__name__
        return False, "Ação desconhecida."

    def administrar_canal(self, conversa_id, acao, valor=None):
        resposta = self._sincrono(
            self._administrar_canal(conversa_id, acao, valor), 45)
        return resposta or (False, "O Telegram não respondeu.")

    async def _administrar_canal(self, cid, acao, valor):
        from telethon.tl import functions, types as T
        try:
            ent = await self.cliente.get_entity(self._chat_id(cid))
            peer = await self.cliente.get_input_entity(ent)
            if acao == "silenciar":
                await self.cliente(functions.account.UpdateNotifySettingsRequest(
                    peer=T.InputNotifyPeer(peer=peer),
                    settings=T.InputPeerNotifySettings(
                        mute_until=2 ** 31 - 1 if valor else 0)))
                return True, ("Canal silenciado." if valor
                              else "Som do canal reativado.")
            if acao == "deixar_de_seguir":
                if isinstance(ent, T.Channel):
                    await self.cliente(functions.channels.LeaveChannelRequest(
                        peer))
                else:
                    await self.cliente.delete_dialog(ent)
                return True, "Você deixou de seguir o canal."
        except Exception as e:
            log.warning("administrar canal (%s) falhou: %s", acao,
                        type(e).__name__)
            return False, "O Telegram não aceitou (%s)." % type(e).__name__
        return False, "Ação desconhecida."

    CRIA = ("grupo", "canal")

    def criar_conversa(self, tipo, nome, descricao="", participantes=(),
                       topicos=False):
        return self._sincrono(
            self._criar(tipo, nome, descricao, participantes, topicos),
            60) or (False, "O Telegram não respondeu.", "")

    async def _criar(self, tipo, nome, descricao, participantes, topicos):
        from telethon import utils
        from telethon.tl import functions
        grupo = tipo == "grupo"
        try:
            r = await self.cliente(functions.channels.CreateChannelRequest(
                title=nome, about=descricao, broadcast=not grupo,
                megagroup=grupo, forum=True if grupo and topicos else None))
            canal = r.chats[0]
        except Exception as e:
            log.warning("criar %s falhou: %s", tipo, type(e).__name__)
            return False, ("O Telegram não deixou criar (%s)." %
                           type(e).__name__), ""
        faltaram = []
        if participantes:
            alvos = []
            for texto in participantes:
                alvo = texto if texto.startswith("@") else (
                    m.normalizar_telefone(texto) or "")
                try:
                    alvos.append(await self.cliente.get_input_entity(alvo))
                except Exception:
                    faltaram.append(texto)
            if alvos:
                try:
                    await self.cliente(functions.channels.InviteToChannelRequest(
                        canal, alvos))
                except Exception as e:
                    log.info("convite aos participantes falhou (%s)",
                             type(e).__name__)
                    faltaram = list(participantes)
        cid = str(utils.get_peer_id(canal))
        self._entidades[cid] = utils.get_input_peer(canal)
        try:
            await self._atualizar_conversas()
        except Exception:
            log.info("lista de conversas nao atualizou depois de criar")
        log.info("%s criado pelo TeleZapp", tipo)
        aviso = ""
        if faltaram:
            aviso = (" Não consegui adicionar: %s." % ", ".join(faltaram))
        return True, aviso.strip(), (
            id_do_topico(cid, TOPICO_GERAL) if grupo and topicos else cid)

    @staticmethod
    def _canal_silenciado(cheio):
        try:
            ate = cheio.full_chat.notify_settings.mute_until
        except AttributeError:
            return False
        if not ate:
            return False
        ate = ate.timestamp() if hasattr(ate, "timestamp") else float(ate)
        return ate > time.time()

    def detalhes_do_canal(self, conversa_id):
        async def ler():
            from telethon.tl import functions
            ent = await self.cliente.get_entity(self._chat_id(conversa_id))
            cheio = await self.cliente(
                functions.channels.GetFullChannelRequest(ent))
            direitos = getattr(ent, "admin_rights", None)
            usuario = getattr(ent, "username", None)
            return {
                "nome": nome_de(ent), "descricao": cheio.full_chat.about or "",
                "seguidores": int(cheio.full_chat.participants_count or 0),
                "verificado": bool(getattr(ent, "verified", False)),
                "silenciado": self._canal_silenciado(cheio), "papel": (
                    "dono" if getattr(ent, "creator", False) else
                    "administrador" if direitos else "seguidor"),
                "criado_em": ent.date.timestamp() if getattr(
                    ent, "date", None) else 0.0,
                "link": ("https://t.me/" + usuario) if usuario else "",
                "sou_admin": bool(getattr(ent, "creator", False) or direitos)}
        return self._sincrono(ler(), 30)

    def administrar_canal(self, conversa_id, acao, valor=None):
        resposta = self._sincrono(
            self._administrar_canal(conversa_id, acao, valor), 45)
        return resposta or (False, "O Telegram não respondeu.")

    async def _administrar_canal(self, cid, acao, valor):
        from telethon.tl import functions
        from telethon.tl.types import InputNotifyPeer, InputPeerNotifySettings
        try:
            ent = await self.cliente.get_entity(self._chat_id(cid))
            if acao == "silenciar":
                ate = 2 ** 31 - 1 if valor else 0
                peer = await self.cliente.get_input_entity(ent)
                await self.cliente(
                    functions.account.UpdateNotifySettingsRequest(
                        peer=InputNotifyPeer(peer=peer),
                        settings=InputPeerNotifySettings(mute_until=ate)))
                return True, ("Canal silenciado." if valor
                              else "Som do canal reativado.")
            if acao == "deixar_de_seguir":
                await self.cliente.delete_dialog(ent)
                self._agendar(self._atualizar_conversas())
                return True, "Você deixou de seguir o canal."
        except Exception as e:
            log.warning("administrar canal (%s) falhou: %s", acao,
                        type(e).__name__)
            return False, "O Telegram não aceitou (%s)." % type(e).__name__
        return False, "Ação desconhecida."

    JANELA_EDICAO = 48 * 3600     # o Telegram deixa editar por 48 horas

    def editar_mensagem(self, msg, texto):
        self._agendar(self._editar(msg, texto))

    async def _editar(self, msg, texto):
        try:
            ent = await self._entidade(msg.conversa_id)
            await self.cliente.edit_message(ent, int(msg.id), texto)
        except Exception as e:
            log.warning("edição falhou: %s", type(e).__name__)
            self._avisar("Não consegui editar a mensagem (%s)." %
                         type(e).__name__, False)
            return
        x = self.banco.mensagem(self.conta.id, msg.conversa_id, msg.id)
        if x is None:
            return
        x.texto = texto
        m.atualizar_extras(x, editada=True)
        self.banco.salvar_mensagens([x])
        self.barramento.publicar(ev.MensagemAtualizada(
            self.conta.id, msg.conversa_id, x, "editada"))

    # ----------------------------------------------------------- historias
    async def _atualizar_historias(self):
        """Busca as historias de quem voce segue e as guarda como mensagens
        da "conversa" de cada pessoa; as que sumiram saem. Nunca levanta."""
        try:
            await self._buscar_historias()
        except Exception as e:
            log.info("historias do Telegram indisponiveis (%s)",
                     type(e).__name__)

    async def _buscar_historias(self):
        from telethon import utils
        from telethon.tl import functions, types as tipos
        pares, proximo, estado = [], None, None
        for _ in range(5):
            r = await self.cliente(functions.stories.GetAllStoriesRequest(
                next=proximo, state=estado))
            if not hasattr(r, "peer_stories"):
                return                      # nada novo, ou sem suporte
            usuarios = {u.id: u for u in getattr(r, "users", [])}
            canais = {c.id: c for c in getattr(r, "chats", [])}
            pares += [(ps, usuarios, canais) for ps in r.peer_stories]
            if not getattr(r, "has_more", False):
                break
            proximo, estado = True, r.state
        eu = None
        atuais, novas = {}, []
        for ps, usuarios, canais in pares:
            pid = utils.get_peer_id(ps.peer)
            ent = usuarios.get(getattr(ps.peer, "user_id", None)) or \
                canais.get(getattr(ps.peer, "channel_id", None))
            meu = bool(getattr(ent, "is_self", False) or
                       getattr(ent, "self", False))
            nome = "Você" if meu else (nome_de(ent) or str(pid))
            itens = [s for s in ps.stories if isinstance(s, tipos.StoryItem)]
            if not itens:
                continue
            sid = PREFIXO_STATUS + str(pid)
            lidas = getattr(ps, "max_read_id", 0) or 0
            msgs = [mensagem_de_historia(self.conta.id, sid, s, nome, pid)
                    for s in itens]
            for x in msgs:
                x.minha = x.minha or meu
            conv = m.Conversa(
                conta_id=self.conta.id, id=sid,
                nome="Meu status" if meu else "Histórias de " + nome,
                servico=self.servico, tipo="status",
                nao_lidas=0 if meu else len(
                    [s for s in itens if s.id > lidas]),
                data=max(x.data for x in msgs))
            try:
                self._entidades[str(pid)] = await \
                    self.cliente.get_input_entity(ps.peer)
            except Exception:
                pass
            self.banco.salvar_conversas([conv])
            self.banco.salvar_mensagens(msgs)
            atuais[sid] = {x.id for x in msgs}
            novas.append(conv)
            self._conversas[sid] = conv
        # o que sumiu (expirou ou foi apagado) sai do computador tambem
        mudou = bool(novas)
        for sid in [c.id for c in list(self._conversas.values())
                    if c.tipo == "status"]:
            if sid not in atuais:
                self.banco.apagar_conversa(self.conta.id, sid, 0)
                self._conversas.pop(sid, None)
                mudou = True
                continue
            velhas = [(self.conta.id, sid, x.id) for x in
                      self.banco.mensagens(self.conta.id, sid, 10 ** 4)
                      if x.id not in atuais[sid]]
            if velhas:
                self.banco.apagar_mensagens(velhas)
        self._historias_em = time.time()
        if mudou:
            self.barramento.publicar(ev.ConversasAtualizadas(
                self.conta.id, sorted(self._conversas.values(),
                                      key=lambda c: -c.data)))

    PODE_PUBLICAR_STATUS = True

    def publicar_status(self, texto, anexo=None, publico="contatos"):
        """Publica uma historia (foto ou video, com a legenda). `publico`:
        "contatos" ou "todos"."""
        if anexo is None:
            self._avisar("No Telegram a história precisa de foto ou vídeo.",
                         False)
            return
        self._agendar(self._publicar_historia(texto, anexo, publico))

    async def _publicar_historia(self, texto, anexo, publico):
        from telethon.tl import functions, types as tipos
        try:
            arquivo = await self.cliente.upload_file(anexo.caminho)
            if anexo.tipo == m.FOTO:
                media = tipos.InputMediaUploadedPhoto(file=arquivo)
            else:
                media = tipos.InputMediaUploadedDocument(
                    file=arquivo, mime_type=anexo.mime or "video/mp4",
                    attributes=[tipos.DocumentAttributeVideo(
                        duration=anexo.segundos, w=anexo.largura or 720,
                        h=anexo.altura or 1280, supports_streaming=True)])
            regra = tipos.InputPrivacyValueAllowAll() if publico == "todos" \
                else tipos.InputPrivacyValueAllowContacts()
            await self.cliente(functions.stories.SendStoryRequest(
                peer=tipos.InputPeerSelf(), media=media,
                privacy_rules=[regra], caption=texto or None,
                random_id=int.from_bytes(os.urandom(8), "big", signed=True),
                period=86400))
        except Exception as e:
            nome = type(e).__name__
            log.warning("publicar historia falhou: %s", nome)
            premium = "premium" in str(e).lower()
            self._avisar("Não consegui publicar a história: %s." % (
                "o Telegram pede uma conta Premium para isso" if premium
                else _motivo(e)), False)
            return
        log.info("historia publicada")
        self._avisar("História publicada.", False)
        await self._atualizar_historias()

    async def _ao_historia(self, evento):
        """Uma historia nova (ou mudou): atualiza, no maximo a cada poucos
        segundos."""
        if time.time() - self._historias_em >= ATUALIZAR_HISTORIAS_A_CADA:
            await self._atualizar_historias()

    async def _midia_da_historia(self, msg):
        """A midia da historia, no formato que o download espera."""
        import types as tipos_py
        from telethon.tl import functions
        ent = await self._entidade(msg.conversa_id[len(PREFIXO_STATUS):])
        r = await self.cliente(functions.stories.GetStoriesByIDRequest(
            peer=ent, id=[int(msg.id)]))
        itens = [s for s in getattr(r, "stories", []) if hasattr(s, "media")]
        if not itens:
            return None
        _, _, tamanho, mime = dados_da_midia_de_historia(itens[0].media)
        return tipos_py.SimpleNamespace(
            media=itens[0].media,
            file=tipos_py.SimpleNamespace(mime_type=mime, size=tamanho))

    async def _ver_historias(self, sid):
        """Marca as historias da pessoa como vistas (ela fica sabendo)."""
        from telethon.tl import functions
        ent = await self._entidade(sid[len(PREFIXO_STATUS):])
        ids = [int(x.id) for x in self.banco.mensagens(
            self.conta.id, sid, 10 ** 4) if not x.minha]
        if ids:
            await self.cliente(functions.stories.ReadStoriesRequest(
                peer=ent, max_id=max(ids)))
        conv = self._conversas.get(sid)
        if conv is not None:
            conv.nao_lidas = 0
        self.banco.atualizar_conversa(self.conta.id, sid, nao_lidas=0)

    def responder_status(self, mensagem, texto):
        """Resposta em particular a uma historia: vai para a conversa com
        quem a publicou, citando a historia."""
        if mensagem.minha:
            return
        self._agendar(self._responder_historia(mensagem, texto))

    async def _responder_historia(self, msg, texto):
        from telethon.tl import functions, types as tipos
        try:
            ent = await self._entidade(msg.conversa_id[len(PREFIXO_STATUS):])
            await self.cliente(functions.messages.SendMessageRequest(
                peer=ent, message=texto,
                random_id=int.from_bytes(os.urandom(8), "big", signed=True),
                reply_to=tipos.InputReplyToStory(peer=ent,
                                                 story_id=int(msg.id))))
        except Exception as e:
            log.warning("resposta a historia falhou: %s", type(e).__name__)
            self.barramento.publicar(ev.EnvioFalhou(
                self.conta.id, msg.conversa_id, texto, _motivo(e),
                devolver_texto=True))

    PODE_CRIAR_ENQUETE = True

    def criar_enquete(self, conversa_id, pergunta, opcoes, multipla,
                      anonima=True):
        self._agendar(self._criar_enquete(
            conversa_id, pergunta, list(opcoes), multipla, anonima))

    async def _criar_enquete(self, cid, pergunta, opcoes, multipla, anonima):
        from telethon.tl import types as tipos

        def texto(t):
            return tipos.TextWithEntities(text=t, entities=[])
        try:
            ent = await self._entidade(cid)
            poll = tipos.Poll(
                id=0, question=texto(pergunta), hash=0,
                answers=[tipos.PollAnswer(text=texto(o), option=bytes([i]))
                         for i, o in enumerate(opcoes)],
                multiple_choice=bool(multipla),
                public_voters=not anonima)
            enviada = await self.cliente.send_message(
                ent, file=tipos.InputMediaPoll(poll=poll))
        except Exception as e:
            log.warning("criar enquete falhou: %s", type(e).__name__)
            self._avisar("Não consegui criar a enquete (%s)." % _motivo(e),
                         False)
            return
        await self._registrar_enviada(enviada, cid)

    PODE_VOTAR = True

    def votar_enquete(self, mensagem, escolhas):
        self._agendar(self._votar_enquete(mensagem, escolhas))

    def atualizar_enquete(self, mensagem):
        self._agendar(self._atualizar_enquete(mensagem))

    async def _votar_enquete(self, msg, escolhas):
        from telethon.tl import functions
        enq = m.enquete_de(msg)
        try:
            if not enq or not enq["ids"]:
                raise ValueError("enquete sem opções")
            ent = await self._entidade(msg.conversa_id)
            await self.cliente(functions.messages.SendVoteRequest(
                peer=ent, msg_id=int(msg.id),
                options=[bytes.fromhex(enq["ids"][i]) for i in escolhas]))
        except Exception as e:
            log.warning("voto em enquete falhou: %s", type(e).__name__)
            self._avisar("Não consegui enviar o voto (%s)." %
                         type(e).__name__, False)
            return
        await self._atualizar_enquete(msg, avisar=False, quem="Você")

    async def _atualizar_enquete(self, msg, avisar=True, quem=""):
        """Busca de novo a mensagem da enquete para ter o resultado atual."""
        try:
            ent = await self._entidade(msg.conversa_id)
            atual = await self.cliente.get_messages(ent, ids=int(msg.id))
            novo = enquete_do_telegram(atual)
            if not novo:
                return
        except Exception as e:
            log.warning("atualizar enquete falhou: %s", type(e).__name__)
            if avisar:
                self._avisar("Não consegui atualizar a enquete (%s)." %
                             type(e).__name__, False)
            return
        self._guardar_enquete(msg.conversa_id, msg.id, novo, quem)

    def _guardar_enquete(self, cid, mid, enquete, quem=""):
        x = self.banco.mensagem(self.conta.id, cid, mid)
        if x is None:
            return
        m.atualizar_extras(x, enquete=enquete)
        self.banco.salvar_mensagens([x])
        self.barramento.publicar(ev.MensagemAtualizada(
            self.conta.id, cid, x, "enquete", quem))

    async def _ao_enquete(self, evento):
        """Alguem votou (ou a enquete foi encerrada)."""
        try:
            x = self.banco.mensagem_da_enquete(self.conta.id,
                                               evento.poll_id)
            if x is None:
                return
            enq = m.enquete_de(x)
            antes = m.votantes_da_enquete(enq)
            poll = getattr(evento, "poll", None)
            if poll is not None:
                enq["encerrada"] = bool(getattr(poll, "closed", False))
            aplicar_resultados(enq, getattr(evento, "results", None))
            # o Telegram nao diz quem votou: so avisa que alguem votou
            self._guardar_enquete(
                x.conversa_id, x.id, enq,
                "alguém" if m.votantes_da_enquete(enq) > antes else "")
        except Exception:
            log.exception("erro ao tratar voto em enquete")

    PODE_REAGIR = True

    def reagir(self, mensagem, emoji):
        self._agendar(self._reagir(mensagem, emoji))

    async def _reagir(self, msg, emoji):
        from telethon import errors
        from telethon.tl import functions, types as tipos
        try:
            if msg.conversa_id.startswith(PREFIXO_STATUS):
                ent = await self._entidade(
                    msg.conversa_id[len(PREFIXO_STATUS):])
                await self.cliente(functions.stories.SendReactionRequest(
                    peer=ent, story_id=int(msg.id),
                    reaction=tipos.ReactionEmoji(emoticon=emoji)
                    if emoji else tipos.ReactionEmpty()))
            else:
                ent = await self._entidade(msg.conversa_id)
                await self.cliente(functions.messages.SendReactionRequest(
                    peer=ent, msg_id=int(msg.id),
                    reaction=[tipos.ReactionEmoji(emoticon=emoji)]
                    if emoji else []))
        except errors.ReactionInvalidError:
            self._avisar("O Telegram não aceita este emoji como reação "
                         "nesta conversa.", False)
            return
        except Exception as e:
            log.warning("reação falhou: %s", type(e).__name__)
            self._avisar("Não consegui enviar a reação (%s)." %
                         type(e).__name__, False)
            return
        x = self.banco.mensagem(self.conta.id, msg.conversa_id, msg.id)
        if x is None:
            return
        reacoes = [y for y in m.extras_de(x)["reacoes"]
                   if not y.get("minha")]
        if emoji:
            reacoes.append({"id": "eu", "quem": "Você", "emoji": emoji,
                            "minha": True})
        m.atualizar_extras(x, reacoes=reacoes)
        self.banco.salvar_mensagens([x])
        self.barramento.publicar(ev.MensagemAtualizada(
            self.conta.id, msg.conversa_id, x, "reacao", "Você", emoji))

    async def _ao_reacoes(self, evento):
        """Reacoes de outras pessoas (e a minha, feita em outro aparelho)."""
        try:
            cid = self._id_do_peer(evento.peer)
            x = self.banco.mensagem(self.conta.id, cid, str(evento.msg_id))
            if x is None:
                return
            antigas = {(r.get("id"), r.get("emoji"))
                       for r in m.extras_de(x)["reacoes"]}
            reacoes = []
            recentes = getattr(evento.reactions, "recent_reactions", None) \
                or []
            for r in recentes:
                emoji = getattr(r.reaction, "emoticon", "")
                if not emoji:
                    continue
                if r.my:
                    reacoes.append({"id": "eu", "quem": "Você",
                                    "emoji": emoji, "minha": True})
                    continue
                pid = getattr(r.peer_id, "user_id", 0)
                try:
                    quem = nome_de(await self.cliente.get_entity(r.peer_id))
                except Exception:
                    quem = ""
                reacoes.append({"id": str(pid), "quem": quem or "alguém",
                                "emoji": emoji})
            if not recentes:
                # grupos grandes: o Telegram so manda a contagem
                for r in getattr(evento.reactions, "results", []):
                    emoji = getattr(r.reaction, "emoticon", "")
                    if emoji:
                        reacoes.append({"id": "n" + emoji, "emoji": emoji,
                                        "quem": "%d pessoa%s" % (
                                            r.count,
                                            "" if r.count == 1 else "s")})
            novas = {(r.get("id"), r.get("emoji")) for r in reacoes}
            if novas == antigas:
                return
            m.atualizar_extras(x, reacoes=reacoes)
            self.banco.salvar_mensagens([x])
            nova = [r for r in reacoes
                    if (r.get("id"), r.get("emoji")) not in antigas]
            self.barramento.publicar(ev.MensagemAtualizada(
                self.conta.id, cid, x, "reacao",
                nova[0]["quem"] if nova else "",
                nova[0]["emoji"] if nova else ""))
        except Exception:
            log.exception("erro ao tratar reações")

    @staticmethod
    def _id_do_peer(peer):
        from telethon import utils
        return str(utils.get_peer_id(peer))

    SAI_DE_GRUPO = True

    def sair_do_grupo(self, conversa_id):
        """Sai do grupo (no Telegram, sair apaga tambem o historico da
        conta)."""
        entidade = self._entidades.get(conversa_id)
        if entidade is None:
            return False
        self._agendar(self.cliente.delete_dialog(entidade))
        return True

    async def _resolver_mencoes(self, mensagens):
        """Acha o id e o nome de quem foi mencionado por @usuario (com cache;
        poucas buscas por vez, para nao irritar o limite do Telegram)."""
        buscas = 0
        for x in mensagens:
            extras = m.extras_de(x)
            mudou = False
            for men in extras["mencoes"]:
                usuario = men.get("usuario")
                if not usuario or men.get("id"):
                    continue
                if usuario not in self._usuarios:
                    if buscas >= LIMITE_BUSCAS_POR_VEZ:
                        continue
                    buscas += 1
                    self._usuarios[usuario] = await self._buscar_usuario(
                        usuario)
                dados = self._usuarios.get(usuario)
                if dados:
                    men.update(dados)
                    mudou = True
            if mudou:
                m.guardar_extras(x, extras["links"], extras["botoes"],
                                 extras["mencoes"])

    async def _buscar_usuario(self, usuario):
        try:
            ent = await self.cliente.get_entity(usuario)
        except Exception as e:
            log.info("não achei um @usuario mencionado (%s)",
                     type(e).__name__)
            return None
        nome = nome_de(ent)
        if nome == "@" + usuario:
            nome = ""
        return {"id": str(ent.id), "nome": nome}

    async def _conversas_de_topicos(self, d, grupo):
        """Conversas dos topicos de um grupo com topicos, ou [] se o
        Telegram nao deu a lista (o grupo fica como uma conversa so)."""
        from telethon.tl import functions
        try:
            r = await self.cliente(functions.messages.GetForumTopicsRequest(
                peer=d.input_entity, offset_date=None, offset_id=0,
                offset_topic=0, limit=100))
        except Exception as e:
            log.info("topicos do grupo indisponiveis (%s)", type(e).__name__)
            return []
        datas = {x.id: x.date for x in getattr(r, "messages", [])}
        conversas = []
        for t in r.topics:
            if not hasattr(t, "title"):
                continue            # ForumTopicDeleted
            cid = id_do_topico(grupo.id, t.id)
            data = datas.get(getattr(t, "top_message", 0))
            c = m.Conversa(
                conta_id=self.conta.id, id=cid,
                nome=nome_do_topico(grupo.nome, t.title),
                servico=self.servico, tipo="grupo",
                nao_lidas=int(getattr(t, "unread_count", 0) or 0),
                data=data.timestamp() if data else grupo.data,
                lidas_ate=grupo.lidas_ate, arquivada=grupo.arquivada,
                fixada=bool(getattr(t, "pinned", False)),
                silenciada_ate=grupo.silenciada_ate,
                somente_leitura=grupo.somente_leitura or bool(
                    getattr(t, "closed", False)))
            self._conversas[cid] = c
            self._entidades[cid] = d.input_entity
            conversas.append(c)
        return conversas

    async def _conversa_do_topico(self, chat, grupo_nome, topico):
        """Conversa de um topico que ainda nao se conhece (topico novo)."""
        from telethon.tl import functions
        cid = id_do_topico(chat, topico)
        conv = self._conversas.get(cid)
        if conv is not None:
            return conv
        titulo = "Geral" if topico == TOPICO_GERAL else ""
        try:
            ent = await self._entidade(str(chat))
            r = await self.cliente(functions.messages.GetForumTopicsByIDRequest(
                peer=ent, topics=[topico]))
            titulo = next((t.title for t in r.topics
                           if hasattr(t, "title")), titulo)
        except Exception as e:
            log.info("titulo do topico indisponivel (%s)", type(e).__name__)
        conv = m.Conversa(self.conta.id, cid,
                          nome_do_topico(grupo_nome, titulo), self.servico,
                          "grupo")
        self._conversas[cid] = conv
        self._entidades[cid] = self._entidades.get(str(chat))
        return conv

    @staticmethod
    def _resposta_em(conversa_id, resposta_a):
        """A que mensagem a nova responde: a escolhida ou, na conversa de um
        topico (fora o Geral), o proprio topico, que e onde ela vai cair."""
        if resposta_a:
            return int(resposta_a)
        topico = separar_topico(conversa_id)[1]
        return topico if topico > TOPICO_GERAL else None

    def _chat_id(self, conversa_id):
        """Id numerico do chat de uma conversa (a de um topico e do grupo)."""
        return int(separar_topico(conversa_id)[0])

    async def _entidade(self, conversa_id):
        ent = self._entidades.get(conversa_id)
        if ent is None:
            chat = separar_topico(conversa_id)[0]
            ent = self._entidades.get(chat)
            if ent is None:
                ent = await self.cliente.get_input_entity(int(chat))
                self._entidades[chat] = ent
            self._entidades[conversa_id] = ent
        return ent

    # ---------------------------------------------------------- mensagens
    def carregar_mensagens(self, conversa_id, limite=50):
        self._agendar(self._carregar(conversa_id, limite))

    async def _carregar(self, conversa_id, limite):
        if conversa_id.startswith(PREFIXO_STATUS):
            self.barramento.publicar(ev.MensagensCarregadas(
                self.conta.id, conversa_id,
                self.banco.mensagens(self.conta.id, conversa_id, 10 ** 4)))
            return
        ent = await self._entidade(conversa_id)
        conv = self._conversas.get(conversa_id)
        lidas_ate = conv.lidas_ate if conv else 0
        nome = conv.nome if conv else ""
        msgs = []
        topico = separar_topico(conversa_id)[1]
        if topico > TOPICO_GERAL:
            fonte = self.cliente.iter_messages(ent, limit=limite,
                                               reply_to=topico)
        else:
            fonte = self.cliente.iter_messages(
                ent, limit=limite * 5 if topico else limite)
        async for msg in fonte:
            if topico == TOPICO_GERAL and topico_da_mensagem(msg) != topico:
                continue            # de outro topico: nao entra no Geral
            x = converter(msg, self.conta.id, conversa_id, lidas_ate, nome)
            if x is not None:
                msgs.append(x)
                if len(msgs) >= limite:
                    break
        msgs.reverse()
        await self._resolver_mencoes(msgs)
        self.banco.salvar_mensagens(msgs)
        log.info("mensagens carregadas: %d", len(msgs))
        self.barramento.publicar(
            ev.MensagensCarregadas(self.conta.id, conversa_id, msgs))

    def baixar_arquivo(self, msg, base, progresso, cancelado):
        if self._loop is None or self._loop.is_closed() or \
                self.cliente is None:
            raise ErroMidia("Sem conexão com o Telegram.")
        futuro = asyncio.run_coroutine_threadsafe(
            self._baixar(msg, base, progresso, cancelado), self._loop)
        return futuro.result()

    async def _baixar(self, msg, base, progresso, cancelado):
        if msg.conversa_id.startswith(PREFIXO_STATUS):
            original = await self._midia_da_historia(msg)
        else:
            ent = await self._entidade(msg.conversa_id)
            original = await self.cliente.get_messages(ent, ids=int(msg.id))
        if original is None or not getattr(original, "media", None):
            raise ErroMidia("O Telegram não tem mais a mídia desta mensagem.")
        arquivo = getattr(original, "file", None)
        caminho = armazem.com_extensao(base, armazem.extensao(
            getattr(arquivo, "mime_type", ""), msg.tipo, msg.nome_arquivo))
        parcial = caminho + ".parte"

        def andamento(feito, total):
            if cancelado():
                raise DownloadCancelado()
            if total:
                progresso(int(feito * 100 / total))
        tamanho = int(getattr(arquivo, "size", 0) or 0)
        try:
            progresso(0)
            inicio = time.perf_counter()
            if tamanho >= 2 * PARTE_DOWNLOAD:
                await self._baixar_em_partes(original, parcial, tamanho,
                                             andamento)
            else:
                await self.cliente.download_media(
                    original, file=parcial, progress_callback=andamento)
            gasto = max(time.perf_counter() - inicio, 0.001)
            log.info("mídia do Telegram: %s em %.1fs (%.2f MB/s)",
                     m.tamanho_legivel(tamanho), gasto,
                     tamanho / 1048576 / gasto)
            if cancelado():
                raise DownloadCancelado()
            os.replace(parcial, caminho)
        except (DownloadCancelado, ErroMidia):
            raise
        except Exception as e:
            log.warning("download falhou: %s", type(e).__name__)
            raise ErroMidia("O Telegram não entregou a mídia (%s)."
                            % type(e).__name__)
        finally:
            if os.path.exists(parcial):
                os.remove(parcial)
        progresso(100)
        return caminho

    async def _baixar_em_partes(self, original, destino, tamanho, andamento):
        """Varios trechos em andamento juntos: o trabalhador i baixa as
        partes i, i+N, i+2N... e grava cada uma na posicao certa."""
        n = DOWNLOADS_PARALELOS
        total = (tamanho + PARTE_DOWNLOAD - 1) // PARTE_DOWNLOAD
        feitos = [0]
        with open(destino, "wb") as f:
            f.truncate(tamanho)
        f = open(destino, "r+b")
        try:
            async def trabalhador(i):
                limite = (total - i + n - 1) // n
                if limite <= 0:
                    return
                k = 0
                async for dados in self.cliente.iter_download(
                        original.media, offset=i * PARTE_DOWNLOAD,
                        stride=n * PARTE_DOWNLOAD, chunk_size=PARTE_DOWNLOAD,
                        request_size=PARTE_DOWNLOAD, limit=limite,
                        file_size=tamanho):
                    f.seek((i + k * n) * PARTE_DOWNLOAD)
                    f.write(dados)
                    k += 1
                    feitos[0] += len(dados)
                    andamento(feitos[0], tamanho)
            tarefas = [asyncio.ensure_future(trabalhador(i))
                       for i in range(n)]
            try:
                await asyncio.gather(*tarefas)
            except BaseException:
                for t in tarefas:
                    t.cancel()
                raise
        finally:
            f.close()

    def enviar_texto(self, conversa_id, texto, resposta_a="", mencoes=None):
        self._agendar(self._enviar(conversa_id, texto, resposta_a, mencoes))

    async def _com_mencoes(self, texto, mencoes):
        """(texto, entidades): quem tem @usuario vira '@usuario' no texto; os
        demais viram mencao por entidade, que o Telegram mostra como o nome."""
        if not mencoes:
            return texto, None
        from telethon.tl import types
        entidades = []

        def trocar(men):
            return men.get("usuario") or "@" + men.get("nome", "")
        novo, posicoes = nucleo_mencoes.aplicar(texto, mencoes, trocar)
        for i, f, men in posicoes:
            if men.get("usuario"):
                continue
            try:
                usuario = await self.cliente.get_input_entity(int(men["id"]))
            except Exception:
                log.info("não consegui mencionar alguém sem @usuario")
                continue
            comeco = len(novo[:i].encode("utf-16-le")) // 2
            tamanho = len(novo[i:f].encode("utf-16-le")) // 2
            entidades.append(types.InputMessageEntityMentionName(
                comeco, tamanho, usuario))
        return novo, entidades or None

    async def _enviar(self, conversa_id, texto, resposta_a, mencoes=None):
        inicio = time.perf_counter()
        try:
            ent = await self._entidade(conversa_id)
            enviar, entidades = await self._com_mencoes(texto, mencoes)
            enviada = await self.cliente.send_message(
                ent, enviar, reply_to=self._resposta_em(
                    conversa_id, resposta_a),
                link_preview=previa_links.LIGADAS["enviar"],
                **({"formatting_entities": entidades} if entidades else {}))
        except Exception as e:
            log.warning("envio falhou: %s", type(e).__name__)
            self.barramento.publicar(ev.EnvioFalhou(
                self.conta.id, conversa_id, texto, _motivo(e)))
            return
        log.info("texto enviado em %.2fs", time.perf_counter() - inicio)
        await self._registrar_enviada(enviada, conversa_id)

    def enviar_arquivo(self, conversa_id, anexo, legenda="", resposta_a="",
                       mencoes=None):
        self._agendar(self._enviar_arquivo(conversa_id, anexo, legenda,
                                           resposta_a, mencoes))

    async def _enviar_arquivo(self, conversa_id, anexo, legenda,
                              resposta_a="", mencoes=None):
        from telethon.tl import types
        inicio = time.perf_counter()
        try:
            ent = await self._entidade(conversa_id)
            texto_legenda, entidades = await self._com_mencoes(legenda,
                                                               mencoes)
            extra = {"formatting_entities": entidades} if entidades else {}
            if anexo.tipo == m.VOZ:
                extra.update(voice_note=True, attributes=[
                    types.DocumentAttributeAudio(duration=anexo.segundos,
                                                 voice=True)])
            elif anexo.tipo == m.AUDIO:
                extra.update(attributes=[types.DocumentAttributeAudio(
                    duration=anexo.segundos, title=anexo.nome)])
            elif anexo.tipo == m.VIDEO:
                extra.update(attributes=[types.DocumentAttributeVideo(
                    duration=anexo.segundos, w=anexo.largura,
                    h=anexo.altura, supports_streaming=True)])
            ultimo = [-1]

            def andamento(feito, total):
                pct = int(feito * 100 / total) if total else 0
                if pct != ultimo[0] and pct < 100:
                    ultimo[0] = pct
                    self.barramento.publicar(ev.ProgressoEnvio(
                        self.conta.id, conversa_id, pct))
            enviada = await self.cliente.send_file(
                ent, anexo.caminho, caption=texto_legenda or None,
                reply_to=self._resposta_em(conversa_id, resposta_a),
                force_document=anexo.tipo == m.DOCUMENTO,
                progress_callback=andamento, **extra)
            self.barramento.publicar(ev.ProgressoEnvio(
                self.conta.id, conversa_id, 100))
        except Exception as e:
            log.warning("envio de %s falhou: %s", anexo.tipo,
                        type(e).__name__)
            self.barramento.publicar(ev.EnvioFalhou(
                self.conta.id, conversa_id, legenda, _motivo(e),
                devolver_texto=False, tipo=anexo.tipo))
            return
        log.info("%s enviado em %.2fs (%d bytes)", anexo.tipo,
                 time.perf_counter() - inicio, anexo.tamanho)
        await self._registrar_enviada(
            enviada, conversa_id,
            arquivo=(anexo.caminho, anexo.temporario))

    async def _registrar_enviada(self, enviada, conversa_id, arquivo=None):
        msg = converter(enviada, self.conta.id, conversa_id)
        if arquivo is not None and msg is not None:
            try:
                destino = armazem.guardar_enviada(msg, *arquivo)
                self.banco.registrar_midia(
                    msg.conta_id, msg.conversa_id, msg.id, msg.tipo,
                    destino, os.path.getsize(destino), time.time())
            except OSError:
                log.warning("não consegui guardar a cópia da mídia enviada",
                            exc_info=True)
        conv = self._conversas.get(conversa_id)
        if conv is None:
            # primeira mensagem de uma conversa nova (ex.: aberta por uma
            # mencao): passa a existir de verdade
            try:
                nome = nome_de(await self.cliente.get_entity(
                    self._chat_id(conversa_id)))
            except Exception:
                nome = ""
            conv = m.Conversa(self.conta.id, conversa_id, nome or "Sem nome",
                              self.servico, "privada", data=msg.data)
            self._conversas[conversa_id] = conv
            self.banco.salvar_conversas([conv])
        else:
            conv.data = msg.data
            self.banco.atualizar_conversa(self.conta.id, conversa_id,
                                          data=msg.data)
        self.banco.salvar_mensagens([msg])
        self.barramento.publicar(ev.MensagemNova(msg, conv,
                                                 enviada_daqui=True))

    def marcar_como_lida(self, conversa_id):
        self._agendar(self._marcar_lida(conversa_id))

    async def _marcar_lida(self, conversa_id):
        if conversa_id.startswith(PREFIXO_STATUS):
            await self._ver_historias(conversa_id)
            return
        ent = await self._entidade(conversa_id)
        topico = separar_topico(conversa_id)[1]
        if topico:
            # grupo com topicos: le-se um topico por vez
            ultima = [x.id for x in self.banco.mensagens(
                self.conta.id, conversa_id, 1) if x.id.isdigit()]
            if ultima:
                from telethon.tl import functions
                await self.cliente(functions.messages.ReadDiscussionRequest(
                    peer=ent, msg_id=topico, read_max_id=int(ultima[-1])))
        else:
            await self.cliente.send_read_acknowledge(ent)
        conv = self._conversas.get(conversa_id)
        if conv is not None:
            conv.nao_lidas = 0
        self.banco.atualizar_conversa(self.conta.id, conversa_id, nao_lidas=0)

    # ------------------------------------------------- chamadas de voz
    @property
    def suporta_chamadas(self):
        return self._chamadas is not None and self._chamadas.pronta

    async def _iniciar_chamadas(self):
        from telezapp.provedores.chamadas_telegram import (ChamadasTelegram,
                                                           disponivel)
        if not disponivel():
            log.info("py-tgcalls não instalado: sem chamadas de voz")
            return
        chamadas = ChamadasTelegram(self.cliente, self.conta.id,
                                    self.barramento, self._nome_da_conversa)
        chamadas.destino_video = self._destino_video
        if await chamadas.iniciar():
            self._chamadas = chamadas

    async def _nome_da_conversa(self, chat_id):
        conv = self._conversas.get(str(chat_id))
        if conv is not None and conv.nome:
            return conv.nome
        try:
            return nome_de(await self.cliente.get_entity(chat_id))
        except Exception:
            return ""

    def _chat(self, conversa_id):
        try:
            return int(conversa_id)
        except (TypeError, ValueError):
            return None

    def _comando_de_chamada(self, nome_metodo, conversa_id, *args):
        chat = self._chat(conversa_id)
        if not self.suporta_chamadas or chat is None or chat < 0:
            self._avisar("Chamadas de voz não estão disponíveis nesta "
                         "conversa.")
            return
        self._agendar(getattr(self._chamadas, nome_metodo)(chat, *args))

    def ligar(self, conversa_id, microfone="", saida="", video=False,
              camera=None):
        if video or camera is not None:
            self._comando_de_chamada("ligar", conversa_id, microfone, saida,
                                     video, camera)
        else:
            self._comando_de_chamada("ligar", conversa_id, microfone, saida)

    def atender_chamada(self, conversa_id, microfone="", saida="",
                        camera=None):
        if camera is not None:
            self._comando_de_chamada("atender", conversa_id, microfone,
                                     saida, camera)
        else:
            self._comando_de_chamada("atender", conversa_id, microfone,
                                     saida)

    @property
    def suporta_video(self):
        return self._chamadas is not None and self._chamadas.suporta_video

    def cameras(self):
        return self._chamadas.cameras() if self._chamadas is not None else []

    def ligar_camera(self, conversa_id, nome=""):
        self._comando_de_chamada("ligar_camera", conversa_id, nome)

    def desligar_camera(self, conversa_id):
        self._comando_de_chamada("desligar_camera", conversa_id)

    def definir_destino_video(self, destino):
        self._destino_video = destino
        if self._chamadas is not None:
            self._chamadas.destino_video = destino

    def encerrar_chamada(self, conversa_id):
        self._comando_de_chamada("encerrar", conversa_id)

    def silenciar_chamada(self, conversa_id, silenciar):
        self._comando_de_chamada("silenciar", conversa_id, silenciar)

    def trocar_dispositivos(self, conversa_id, microfone="", saida=""):
        self._comando_de_chamada("trocar_dispositivos", conversa_id,
                                 microfone, saida)

    def dispositivos_de_audio(self):
        if self._chamadas is None:
            return [], []
        return self._chamadas.dispositivos()

    # ----------------------------------------------------- eventos do servico
    async def _ao_receber(self, evento):
        try:
            msg = evento.message
            cid = str(evento.chat_id)
            conv = self._conversas.get(cid)
            if conv is not None and conv.id in self._foruns:
                conv = await self._conversa_do_topico(
                    cid, conv.nome, topico_da_mensagem(msg))
                cid = conv.id
            if conv is None:
                chat = await evento.get_chat()
                self._entidades[cid] = await evento.get_input_chat()
                conv = m.Conversa(
                    conta_id=self.conta.id, id=cid,
                    nome=nome_de(chat) or "Sem nome", servico=self.servico,
                    tipo="grupo" if evento.is_group else (
                        "canal" if evento.is_channel else "privada"),
                    somente_leitura=somente_leitura_do_telegram(chat))
                self._conversas[cid] = conv
                if getattr(chat, "forum", False):
                    self._foruns.add(cid)
                    conv = await self._conversa_do_topico(
                        cid, conv.nome, topico_da_mensagem(msg))
                    cid = conv.id
            if not getattr(msg, "out", False) and msg.sender is None:
                await evento.get_sender()
            acao = getattr(msg, "action", None)
            if type(acao).__name__ == "MessageActionSetMessagesTTL":
                self._temporaria_mudou(conv, int(acao.period or 0),
                                       bool(getattr(msg, "out", False)))
                return
            nova = converter(msg, self.conta.id, cid, conv.lidas_ate,
                             conv.nome)
            if nova is None:
                return
            await self._resolver_mencoes([nova])
            prazo = prazo_da_mensagem(msg)
            if conv.temporaria_s != prazo:
                conv.temporaria_s = prazo
            conv.data = nova.data
            if not nova.minha:
                conv.contar_nova(conv.tipo == "grupo" and
                                 m.extras_de(nova)["citou_voce"])
            self.banco.salvar_conversas([conv])
            self.banco.salvar_mensagens([nova])
            self.barramento.publicar(ev.MensagemNova(nova, conv))
        except Exception:
            log.exception("erro ao tratar mensagem recebida")

    # ------------------------------------------------------------ presenca
    def observar_presenca(self, conversa_id):
        """Le o status atual da pessoa; as mudancas e o "digitando" chegam
        pelos avisos do Telegram, que valem para todas as conversas."""
        if conversa_id.startswith(PREFIXO_STATUS):
            return
        self._observada = conversa_id
        self._agendar(self._ler_status(conversa_id))

    def parar_presenca(self, conversa_id):
        if self._observada == conversa_id:
            self._observada = None

    async def _ler_status(self, conversa_id):
        from telethon.tl import types as tipos
        try:
            ent = await self.cliente.get_entity(self._chat_id(conversa_id))
        except Exception:
            return
        estado = getattr(ent, "status", None)
        if isinstance(estado, tipos.UserStatusOnline):
            p = ev.Presenca(self.conta.id, conversa_id, "online")
        elif isinstance(estado, tipos.UserStatusOffline):
            p = ev.Presenca(self.conta.id, conversa_id, "offline",
                            quando=estado.was_online.timestamp())
        elif isinstance(estado, tipos.UserStatusRecently):
            p = ev.Presenca(self.conta.id, conversa_id, "offline",
                            aprox="recentemente")
        elif isinstance(estado, tipos.UserStatusLastWeek):
            p = ev.Presenca(self.conta.id, conversa_id, "offline",
                            aprox="na última semana")
        elif isinstance(estado, tipos.UserStatusLastMonth):
            p = ev.Presenca(self.conta.id, conversa_id, "offline",
                            aprox="no último mês")
        else:
            return
        self.barramento.publicar(p)

    async def _ao_usuario(self, evento):
        """Online, visto por ultimo e "digitando" de quem a conversa
        observada e (ou de quem digita no grupo observado)."""
        try:
            observada = self._observada
            if observada is None:
                return
            em_grupo = getattr(evento, "chat_id", None)
            cid = str(em_grupo) if em_grupo else str(evento.user_id)
            if cid != observada:
                return
            quem = ""
            if em_grupo:
                try:
                    quem = nome_de(await self.cliente.get_entity(
                        evento.user_id))
                except Exception:
                    quem = ""
            if evento.typing:
                estado = "digitando"
            elif evento.recording:
                estado = "gravando"
            elif evento.uploading:
                estado = "enviando"
            elif evento.cancel:
                estado = "parou"
            elif em_grupo:
                return
            elif evento.online:
                estado = "online"
            elif evento.last_seen:
                self.barramento.publicar(ev.Presenca(
                    self.conta.id, cid, "offline",
                    quando=evento.last_seen.timestamp()))
                return
            elif evento.recently:
                self.barramento.publicar(ev.Presenca(
                    self.conta.id, cid, "offline", aprox="recentemente"))
                return
            elif evento.within_weeks:
                self.barramento.publicar(ev.Presenca(
                    self.conta.id, cid, "offline",
                    aprox="na última semana"))
                return
            elif evento.within_months:
                self.barramento.publicar(ev.Presenca(
                    self.conta.id, cid, "offline", aprox="no último mês"))
                return
            else:
                return
            self.barramento.publicar(ev.Presenca(
                self.conta.id, cid, estado, quem=quem))
        except Exception:
            log.exception("erro ao tratar a presença")

    async def _ao_acao_no_chat(self, evento):
        """Mudanca no grupo ou canal; aqui so a troca de nome interessa."""
        try:
            novo = getattr(evento, "new_title", None)
            if not novo:
                return
            cid = str(evento.chat_id)
            conv = self._conversas.get(cid)
            if conv is None or conv.nome == novo:
                return
            conv.nome = novo
            log.info("grupo ou canal renomeado")
            self.banco.salvar_conversas([conv])
            self.barramento.publicar(ev.ConversasAtualizadas(
                self.conta.id, sorted(self._conversas.values(),
                                      key=lambda c: -c.data)))
        except Exception:
            log.exception("erro ao tratar mudança no chat")

    async def _ao_mensagens_apagadas(self, evento):
        """Mensagens apagadas em outro aparelho (ou por quem as enviou)."""
        chat = getattr(evento, "chat_id", None)
        conversa = str(chat) if chat else None
        for x in self.banco.mensagens_por_id(
                self.conta.id, evento.deleted_ids, conversa):
            if m.MANTER["apagadas"] and not x.minha:
                # opcao "manter as apagadas": fica guardada, so marcada
                m.atualizar_extras(x, apagada_pelo_autor=True)
                self.banco.salvar_mensagens([x])
                self.barramento.publicar(ev.MensagemAtualizada(
                    self.conta.id, x.conversa_id, x, "apagada"))
                continue
            self.barramento.publicar(ev.MensagemApagadaNoCelular(
                self.conta.id, x.conversa_id, x.id))

    def apagar_mensagem(self, mensagem, para_todos=False):
        """Apaga a mensagem no Telegram (para todos, ou so para mim onde o
        Telegram deixa)."""
        try:
            ident = int(mensagem.id)
        except ValueError:
            return False
        self._agendar(self._apagar_mensagem(mensagem, ident, para_todos))
        return True

    async def _apagar_mensagem(self, mensagem, ident, para_todos):
        ent = await self._entidade(mensagem.conversa_id)
        await self.cliente.delete_messages(ent, [ident], revoke=para_todos)

    async def _ao_conteudo_lido(self, upd):
        """Voz ou audio tocado em outro aparelho: passa a constar ouvido."""
        from telethon import utils
        from telethon.tl import types as T
        ids = list(getattr(upd, "messages", []) or [])
        conversa = None
        if isinstance(upd, T.UpdateChannelReadMessagesContents):
            conversa = str(utils.get_peer_id(T.PeerChannel(upd.channel_id)))
        for x in self.banco.mensagens_por_id(self.conta.id, ids, conversa):
            if x.minha or x.tipo not in (m.VOZ, m.AUDIO) or \
                    m.extras_de(x)["ouvida"]:
                continue
            m.atualizar_extras(x, ouvida=True)
            self.banco.salvar_mensagens([x])
            self.barramento.publicar(ev.MensagemAtualizada(
                self.conta.id, x.conversa_id, x, "ouvida"))

    def marcar_ouvida(self, mensagem):
        """A pessoa tocou esta voz ou audio recebido: avisa o Telegram."""
        if not mensagem.minha:
            self._agendar(self._enviar_ouvida(mensagem))

    async def _enviar_ouvida(self, x):
        from telethon.tl import functions, types as T
        try:
            ident = int(x.id)
        except ValueError:
            return
        ent = await self._entidade(x.conversa_id)
        if isinstance(ent, T.InputPeerChannel):
            await self.cliente(functions.channels.ReadMessageContentsRequest(
                channel=ent, id=[ident]))
        else:
            await self.cliente(functions.messages.ReadMessageContentsRequest(
                id=[ident]))

    async def _ao_ler(self, evento):
        try:
            if evento.max_id is None:
                return
            cid = str(evento.chat_id)
            ate = int(evento.max_id)
            conv = self._conversas.get(cid)
            if conv is not None:
                conv.lidas_ate = max(conv.lidas_ate, ate)
                self.banco.salvar_conversas([conv])
            self.banco.marcar_lidas_pelo_outro(self.conta.id, cid, ate, m.LIDA)
            self.barramento.publicar(
                ev.LeituraConfirmada(self.conta.id, cid, ate))
        except Exception:
            log.exception("erro ao tratar confirmacao de leitura")


def _motivo(erro):
    nome = type(erro).__name__
    if "Flood" in nome:
        return "o Telegram pediu para esperar antes de enviar de novo"
    if "Write" in nome or "Forbidden" in nome or "Admin" in nome:
        return "você não tem permissão para escrever nesta conversa"
    if isinstance(erro, (ConnectionError, OSError)):
        return "sem conexão"
    return "erro do Telegram (%s)" % nome

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Provedor do Telegram (Telethon), numa thread com o seu proprio asyncio.

Nada aqui toca na janela: os resultados saem como eventos. O registro nunca
grava texto de mensagens, telefones completos, codigos ou senhas.
"""
import asyncio
import logging
import os
import threading
import time

from telezapp import NOME, VERSAO, config
from telezapp.midia import armazem
from telezapp.nucleo import eventos as ev
from telezapp.nucleo import modelos as m
from telezapp.provedores.base import (PEDIR_CODIGO, PEDIR_SENHA,
                                      PEDIR_TELEFONE, DownloadCancelado,
                                      ErroMidia, ErroPrivacidade, Provedor)

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
        return "contato: " + nome if nome else "contato"
    return ""


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
    botoes = []
    markup = getattr(msg, "reply_markup", None)
    for linha in getattr(markup, "rows", None) or []:
        for b in getattr(linha, "buttons", None) or []:
            url = _url_do_botao(b)
            if url:
                botoes.append((getattr(b, "text", "") or url, url))
    return links, botoes, mencoes


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
    links, botoes, mencoes = extras_do_telegram(msg)
    m.guardar_extras(nova, links, botoes, mencoes)
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
        self._conversas = {}                    # conversa_id -> Conversa
        self._usuarios = {}                     # @usuario -> dados ou None
        self._pronto = threading.Event()
        self._chamadas = None                   # ChamadasTelegram, se houver

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
                    silenciada_ate=silencio_do_dialogo(d))
                self._conversas[cid] = c
                lista.append(c)
        self.banco.salvar_conversas(lista)
        log.info("conversas: %d em %.2fs", len(lista),
                 time.perf_counter() - inicio)
        self.barramento.publicar(ev.ConversasAtualizadas(self.conta.id, lista))

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

    async def _entidade(self, conversa_id):
        ent = self._entidades.get(conversa_id)
        if ent is None:
            ent = await self.cliente.get_input_entity(int(conversa_id))
            self._entidades[conversa_id] = ent
        return ent

    # ---------------------------------------------------------- mensagens
    def carregar_mensagens(self, conversa_id, limite=50):
        self._agendar(self._carregar(conversa_id, limite))

    async def _carregar(self, conversa_id, limite):
        ent = await self._entidade(conversa_id)
        conv = self._conversas.get(conversa_id)
        lidas_ate = conv.lidas_ate if conv else 0
        nome = conv.nome if conv else ""
        msgs = []
        async for msg in self.cliente.iter_messages(ent, limit=limite):
            x = converter(msg, self.conta.id, conversa_id, lidas_ate, nome)
            if x is not None:
                msgs.append(x)
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

    def enviar_texto(self, conversa_id, texto, resposta_a=""):
        self._agendar(self._enviar(conversa_id, texto, resposta_a))

    async def _enviar(self, conversa_id, texto, resposta_a):
        inicio = time.perf_counter()
        try:
            ent = await self._entidade(conversa_id)
            enviada = await self.cliente.send_message(
                ent, texto, reply_to=int(resposta_a) if resposta_a else None)
        except Exception as e:
            log.warning("envio falhou: %s", type(e).__name__)
            self.barramento.publicar(ev.EnvioFalhou(
                self.conta.id, conversa_id, texto, _motivo(e)))
            return
        log.info("texto enviado em %.2fs", time.perf_counter() - inicio)
        await self._registrar_enviada(enviada, conversa_id)

    def enviar_arquivo(self, conversa_id, anexo, legenda=""):
        self._agendar(self._enviar_arquivo(conversa_id, anexo, legenda))

    async def _enviar_arquivo(self, conversa_id, anexo, legenda):
        from telethon.tl import types
        inicio = time.perf_counter()
        try:
            ent = await self._entidade(conversa_id)
            extra = {}
            if anexo.tipo == m.VOZ:
                extra = dict(voice_note=True, attributes=[
                    types.DocumentAttributeAudio(duration=anexo.segundos,
                                                 voice=True)])
            elif anexo.tipo == m.AUDIO:
                extra = dict(attributes=[types.DocumentAttributeAudio(
                    duration=anexo.segundos, title=anexo.nome)])
            elif anexo.tipo == m.VIDEO:
                extra = dict(attributes=[types.DocumentAttributeVideo(
                    duration=anexo.segundos, w=anexo.largura,
                    h=anexo.altura, supports_streaming=True)])
            enviada = await self.cliente.send_file(
                ent, anexo.caminho, caption=legenda or None,
                force_document=anexo.tipo == m.DOCUMENTO, **extra)
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
                nome = nome_de(await self.cliente.get_entity(int(conversa_id)))
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
        ent = await self._entidade(conversa_id)
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

    def ligar(self, conversa_id, microfone="", saida=""):
        self._comando_de_chamada("ligar", conversa_id, microfone, saida)

    def atender_chamada(self, conversa_id, microfone="", saida=""):
        self._comando_de_chamada("atender", conversa_id, microfone, saida)

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
            if conv is None:
                chat = await evento.get_chat()
                self._entidades[cid] = await evento.get_input_chat()
                conv = m.Conversa(
                    conta_id=self.conta.id, id=cid,
                    nome=nome_de(chat) or "Sem nome", servico=self.servico,
                    tipo="grupo" if evento.is_group else (
                        "canal" if evento.is_channel else "privada"))
                self._conversas[cid] = conv
            if not getattr(msg, "out", False) and msg.sender is None:
                await evento.get_sender()
            nova = converter(msg, self.conta.id, cid, conv.lidas_ate,
                             conv.nome)
            if nova is None:
                return
            await self._resolver_mencoes([nova])
            conv.data = nova.data
            if not nova.minha:
                conv.nao_lidas += 1
            self.banco.salvar_conversas([conv])
            self.banco.salvar_mensagens([nova])
            self.barramento.publicar(ev.MensagemNova(nova, conv))
        except Exception:
            log.exception("erro ao tratar mensagem recebida")

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

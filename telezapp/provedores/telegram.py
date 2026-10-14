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
                                      ErroMidia, Provedor)

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
    return m.Mensagem(
        conta_id=conta_id, conversa_id=str(conversa_id), id=str(msg.id),
        autor=autor, minha=minha,
        data=data.timestamp() if data is not None else time.time(),
        tipo=tipo, texto=texto, segundos=segundos,
        nome_arquivo=nome_arquivo, tamanho=tamanho, estado=estado,
        resposta_a=str(resposta_a) if resposta_a else "")


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
        self._pronto = threading.Event()

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
        self._estado(ev.CONECTADA)
        self._pronto.set()
        await self._atualizar_conversas()

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
        async for d in self.cliente.iter_dialogs(limit=LIMITE_CONVERSAS,
                                                 archived=False):
            cid = str(d.id)
            self._entidades[cid] = d.input_entity
            c = m.Conversa(
                conta_id=self.conta.id, id=cid, nome=d.name or "Sem nome",
                servico=self.servico, tipo=tipo_da_conversa(d),
                nao_lidas=d.unread_count or 0,
                data=d.date.timestamp() if d.date else 0.0,
                lidas_ate=getattr(d.dialog, "read_outbox_max_id", 0) or 0)
            self._conversas[cid] = c
            lista.append(c)
        self.banco.salvar_conversas(lista)
        log.info("conversas: %d em %.2fs", len(lista),
                 time.perf_counter() - inicio)
        self.barramento.publicar(ev.ConversasAtualizadas(self.conta.id, lista))

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
        msg = converter(enviada, self.conta.id, conversa_id)
        conv = self._conversas.get(conversa_id)
        if conv is not None:
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
            conv.data = nova.data
            if not nova.minha:
                conv.nao_lidas += 1
            self.banco.salvar_conversas([conv])
            self.banco.salvar_mensagens([nova])
            self.barramento.publicar(ev.MensagemNova(nova, conv))
        except Exception:
            log.exception("erro ao tratar mensagem recebida")

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

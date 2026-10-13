# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Provedor do WhatsApp (neonize, ligacao Python da whatsmeow).

- O neonize bloqueia ao conectar: connect() roda numa thread so dele, e os
  envios passam por uma fila com a sua propria thread.
- Os eventos do WhatsApp chegam em threads do neonize: aqui so se converte,
  grava no banco e publica eventos para a interface.
- O WhatsApp nao entrega historico depois do pareamento: o banco local e a
  fonte das conversas. Nesta etapa (2a) o pacote de historico do pareamento
  so e registrado no log em numeros, para planejar a etapa 2b.
- As mensagens enviadas pelo app nao voltam como evento: o app as registra.

O registro nunca grava texto de mensagens, telefones completos ou codigos.
"""
import logging
import os
import queue
import threading
import time

from telezapp import config
from telezapp.nucleo import eventos as ev
from telezapp.nucleo import modelos as m
from telezapp.provedores.base import Provedor

log = logging.getLogger("telezapp.whatsapp")

EMBRULHOS = ("deviceSentMessage", "ephemeralMessage", "viewOnceMessage",
             "viewOnceMessageV2", "viewOnceMessageV2Extension",
             "documentWithCaptionMessage", "editedMessage")
# Campos sem conteudo para a pessoa (chaves, controle): a mensagem e ignorada
SO_CONTROLE = {"senderKeyDistributionMessage", "messageContextInfo",
               "protocolMessage", "reactionMessage", "pollUpdateMessage",
               "keepInChatMessage", "pinInChatMessage"}
# Tipos de recibo do neonize (Receipt.Type)
RECIBO_ENTREGUE, RECIBO_LIDO, RECIBO_LIDO_POR_MIM, RECIBO_OUVIDO = 1, 4, 5, 6
MAX_GUARDADAS = 2000


# ----------------------------------------------------- conversao (testavel)
def campos(msg):
    try:
        return [f.name for f, _ in msg.ListFields()]
    except Exception:
        return []


def desembrulhar(msg):
    """Abre os envelopes ate a mensagem de verdade."""
    for _ in range(6):
        for nome in EMBRULHOS:
            try:
                if msg.HasField(nome):
                    msg = getattr(msg, nome).message
                    break
            except (ValueError, AttributeError):
                continue
        else:
            break
    return msg


def jid_texto(jid):
    """JID -> 'usuario@servidor', sem o numero do aparelho."""
    if jid is None or not getattr(jid, "User", ""):
        return ""
    return "%s@%s" % (jid.User, jid.Server)


def segundos(ts):
    """Timestamp do neonize (segundos ou milissegundos) -> segundos."""
    t = float(ts or 0)
    return t / 1000.0 if t > 1e11 else t


def _contexto(interna):
    for nome in ("extendedTextMessage", "imageMessage", "videoMessage",
                 "audioMessage", "documentMessage", "stickerMessage"):
        try:
            if interna.HasField(nome):
                sub = getattr(interna, nome)
                if sub.HasField("contextInfo"):
                    return sub.contextInfo
        except (ValueError, AttributeError):
            continue
    return None


def conteudo_de(interna):
    """(tipo, texto, segundos, nome_arquivo, tamanho) ou None se a mensagem
    nao tem nada para mostrar (chaves, reacoes, controle)."""
    presentes = set(campos(interna))
    if not presentes or presentes <= SO_CONTROLE:
        return None
    if interna.conversation:
        return m.TEXTO, interna.conversation, 0, "", 0
    if "extendedTextMessage" in presentes:
        return m.TEXTO, interna.extendedTextMessage.text, 0, "", 0
    if "imageMessage" in presentes:
        x = interna.imageMessage
        return m.FOTO, x.caption, 0, "", x.fileLength
    if "videoMessage" in presentes:
        x = interna.videoMessage
        return m.VIDEO, x.caption, x.seconds, "", x.fileLength
    if "audioMessage" in presentes:
        x = interna.audioMessage
        return (m.VOZ if x.PTT else m.AUDIO), "", x.seconds, "", x.fileLength
    if "documentMessage" in presentes:
        x = interna.documentMessage
        return (m.DOCUMENTO, x.caption, 0, x.fileName or x.title,
                x.fileLength)
    if "stickerMessage" in presentes:
        return m.FIGURINHA, "", 0, "", 0
    for nome in ("pollCreationMessage", "pollCreationMessageV2",
                 "pollCreationMessageV3"):
        if nome in presentes:
            return m.OUTRO, "enquete: " + getattr(interna, nome).name, 0, \
                "", 0
    if "locationMessage" in presentes or "liveLocationMessage" in presentes:
        return m.OUTRO, "localização", 0, "", 0
    if "contactMessage" in presentes:
        return m.OUTRO, "contato: " + interna.contactMessage.displayName, 0, \
            "", 0
    return m.OUTRO, "", 0, "", 0


def converter(evento, conta_id, conversa_id, autor=""):
    """MessageEv do neonize -> modelos.Mensagem, ou None se for so controle.
    Devolve tambem o JID (texto) de quem enviou, para responder e marcar
    como lida."""
    interna = desembrulhar(evento.Message)
    dados = conteudo_de(interna)
    if dados is None:
        return None, ""
    tipo, texto, seg, arquivo, tamanho = dados
    info = evento.Info
    origem = info.MessageSource
    minha = bool(origem.IsFromMe)
    ctx = _contexto(interna)
    msg = m.Mensagem(
        conta_id=conta_id, conversa_id=conversa_id, id=info.ID,
        autor="" if minha else (autor or info.Pushname or ""),
        minha=minha, data=segundos(info.Timestamp) or time.time(),
        tipo=tipo, texto=texto or "", segundos=int(seg or 0),
        nome_arquivo=arquivo or "", tamanho=int(tamanho or 0),
        estado=m.ENVIADA if minha else "",
        resposta_a=(ctx.stanzaID if ctx is not None and ctx.stanzaID
                    else ""))
    return msg, jid_texto(origem.Sender)


def resumo_historico(dados):
    """Numeros do pacote de historico (sem conteudo), para o log."""
    convs = list(dados.conversations)
    msgs = sum(len(c.messages) for c in convs)
    return {
        "tipo": int(dados.syncType),
        "conversas": len(convs),
        "mensagens": msgs,
        "com_nome": sum(1 for c in convs if c.name or c.displayName),
        "grupos": sum(1 for c in convs if c.ID.endswith("@g.us")),
        "lid": sum(1 for c in convs if c.ID.endswith("@lid")),
        "nao_lidas": sum(c.unreadCount for c in convs),
        "pushnames": len(dados.pushnames),
        "progresso": int(dados.progress),
    }


# ---------------------------------------------------------------- provedor
class ProvedorWhatsApp(Provedor):
    servico = "whatsapp"

    def __init__(self, conta, barramento, banco, pedir=None,
                 pasta_sessoes=None, fabrica_cliente=None):
        super().__init__(conta, barramento, banco, pedir)
        self.pasta_sessoes = pasta_sessoes or config.pasta("sessoes")
        self.fabrica_cliente = fabrica_cliente or self._criar_cliente
        self.cliente = None
        self._fila = queue.Queue()
        self._parar = threading.Event()
        self._threads = []
        self._conversas = {c.id: c for c in banco.conversas(conta.id)}
        self._remetentes = {}      # id da msg -> (jid de quem enviou, texto)
        self._nao_lidas = {}       # conversa -> [(id, jid do remetente)]
        self._vistas = set()
        self._nomes_grupo_pedidos = set()
        self._conectada = False
        self._trava = threading.RLock()

    # ----------------------------------------------------------- execucao
    def _criar_cliente(self):
        from neonize.client import NewClient
        from neonize.proto.waCompanionReg.WAWebProtobufsCompanionReg_pb2 \
            import DeviceProps
        caminho = os.path.join(self.pasta_sessoes, self.conta.id + ".db")
        props = DeviceProps(os="TeleZapp",
                            platformType=DeviceProps.DESKTOP)
        return NewClient(caminho, props=props)

    def iniciar(self):
        if self._threads:
            return
        for alvo, nome in ((self._conectar, "conexao"),
                           (self._trabalhar, "envios")):
            t = threading.Thread(target=alvo, daemon=True,
                                 name="whatsapp-%s-%s" % (nome, self.conta.id))
            self._threads.append(t)
            t.start()

    def _avisar(self, texto, grave=False):
        self.barramento.publicar(ev.Aviso(self.conta.id, texto, grave))

    def _estado(self, estado, detalhe=""):
        log.info("estado: %s %s", estado, detalhe)
        self.barramento.publicar(ev.EstadoConta(self.conta.id, estado,
                                                detalhe))

    def _conectar(self):
        try:
            import neonize.events as nev
            self.cliente = self.fabrica_cliente()
            registros = {
                "ConnectedEv": self._ao_conectar,
                "PairStatusEv": self._ao_parear,
                "LoggedOutEv": self._ao_sair,
                "DisconnectedEv": self._ao_desconectar,
                "MessageEv": self._ao_receber,
                "ReceiptEv": self._ao_recibo,
                "HistorySyncEv": self._ao_historico,
                "TemporaryBanEv": self._ao_banimento,
                "StreamReplacedEv": self._ao_substituida,
                "ConnectFailureEv": self._ao_falha_conexao,
                "ClientOutdatedEv": self._ao_desatualizado,
            }
            for nome, funcao in registros.items():
                classe = getattr(nev, nome, None)
                if classe is None:
                    log.warning("evento %s não existe nesta versão", nome)
                    continue
                self.cliente.event(classe)(funcao)
            self.cliente.event.qr(self._ao_qr)
            self._estado(ev.CONECTANDO)
            self._inicio = time.perf_counter()
            self.cliente.connect()   # bloqueia ate parar()
            log.info("connect() retornou")
        except Exception:
            if not self._parar.is_set():
                log.exception("erro na conexão do WhatsApp")
                self._estado(ev.ERRO, "falha na conexão")
                self._avisar("Erro na conexão do WhatsApp. Os detalhes estão "
                             "no log.", True)

    def _trabalhar(self):
        while not self._parar.is_set():
            try:
                tarefa = self._fila.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                tarefa()
            except Exception:
                log.exception("erro numa tarefa do WhatsApp")

    def parar(self):
        self._parar.set()
        if self.cliente is not None:
            # so o stop() encerra o connect(), que roda numa thread do
            # neonize que nao e "daemon" e seguraria o fechamento do app
            try:
                self.cliente.stop()
            except Exception:
                log.exception("erro ao parar o cliente")
        for t in self._threads:
            t.join(timeout=6)

    # ---------------------------------------------------------- pareamento
    def _ao_qr(self, cliente, dados):
        codigo = dados.decode() if isinstance(dados, bytes) else str(dados)
        log.info("QR Code de pareamento recebido")
        self.barramento.publicar(ev.QrPareamento(self.conta.id, codigo))

    def pedir_codigo_pareamento(self, telefone):
        """Gera o codigo de 8 caracteres para o numero (so digitos, com o
        codigo do pais) -> CodigoPareamento."""
        self._fila.put(lambda: self._gerar_codigo(telefone))

    def _gerar_codigo(self, telefone):
        from neonize.utils.enum import ClientName, ClientType
        digitos = "".join(c for c in telefone if c.isdigit())
        ultimo = None
        for tentativa in range(1, 6):
            if self._parar.is_set():
                return
            try:
                codigo = self.cliente.PairPhone(
                    digitos, True, ClientName.WINDOWS, ClientType.EDGE)
                log.info("código de pareamento gerado (tentativa %d) para "
                         "%s", tentativa, config.mascarar_telefone(
                             "+" + digitos))
                self.barramento.publicar(ev.CodigoPareamento(
                    self.conta.id, codigo))
                return
            except Exception as e:
                ultimo = e
                log.warning("pareamento por código, tentativa %d: %r",
                            tentativa, e)
                time.sleep(3)
        self.barramento.publicar(ev.CodigoPareamento(
            self.conta.id, erro="O WhatsApp não gerou o código (%s). "
            "Confira o número ou use o QR Code." % type(ultimo).__name__))

    def _ao_parear(self, cliente, e):
        if e.Error:
            log.warning("pareamento falhou: %s", e.Error)
            self._avisar("O pareamento falhou. Tente de novo.", True)
        else:
            log.info("pareamento concluído")

    def _ao_conectar(self, cliente, e):
        log.info("conectado em %.2fs", time.perf_counter() - getattr(
            self, "_inicio", time.perf_counter()))
        self._conectada = True
        nome, telefone = self.conta.nome, self.conta.telefone
        try:
            eu = self.cliente.get_me()
            telefone = "+" + eu.JID.User if eu.JID.User else telefone
            nome = eu.PushName or nome or telefone
        except Exception:
            log.exception("não consegui ler os dados da conta")
        self.conta.nome, self.conta.telefone = nome, telefone
        self.barramento.publicar(ev.ContaPronta(self.conta.id, nome,
                                                telefone))
        self._estado(ev.CONECTADA)
        self._publicar_conversas()

    def _ao_sair(self, cliente, e):
        self._conectada = False
        log.warning("sessão encerrada pelo WhatsApp (motivo %s)", e.Reason)
        self._estado(ev.PRECISA_LOGIN, "desconectada pelo celular")
        self._avisar("O WhatsApp desconectou esta conta. Ela foi removida "
                     "dos aparelhos conectados do celular, ou ficou muito "
                     "tempo sem uso. Será preciso parear de novo.", True)

    def _ao_desconectar(self, cliente, e):
        if self._parar.is_set():
            return
        self._conectada = False
        self._estado(ev.DESCONECTADA, "reconectando")

    def _ao_banimento(self, cliente, e):
        log.warning("banimento temporário: %s", e)
        self._avisar("O WhatsApp bloqueou esta conta temporariamente.", True)

    def _ao_substituida(self, cliente, e):
        log.warning("sessão substituída por outro aparelho")
        self._estado(ev.ERRO, "aberta em outro lugar")
        self._avisar("Esta sessão do WhatsApp foi aberta em outro lugar.",
                     True)

    def _ao_falha_conexao(self, cliente, e):
        log.warning("falha de conexão: %s", e)

    def _ao_desatualizado(self, cliente, e):
        log.warning("cliente desatualizado")
        self._avisar("O WhatsApp diz que esta versão do componente de "
                     "conexão está desatualizada.", True)

    # ----------------------------------------------------------- conversas
    def _publicar_conversas(self):
        with self._trava:
            lista = sorted(self._conversas.values(), key=lambda c: -c.data)
        self.barramento.publicar(ev.ConversasAtualizadas(self.conta.id,
                                                         lista))

    def atualizar_conversas(self):
        self._publicar_conversas()

    def _id_da_conversa(self, chat):
        """JID da conversa -> texto. Conversas individuais com endereco LID
        sao trocadas pelo numero, quando o WhatsApp informa."""
        if chat.Server == "lid" and self.cliente is not None:
            try:
                pn = self.cliente.get_pn_from_lid(chat)
                if pn.User:
                    return jid_texto(pn)
            except Exception:
                log.info("sem número para um endereço LID")
        return jid_texto(chat)

    def _nome_contato(self, jid, pushname=""):
        try:
            info = self.cliente.contact.get_contact(jid)
            nome = info.FullName or info.FirstName or info.BusinessName or \
                info.PushName
            if nome:
                return nome
        except Exception:
            pass
        return pushname or ("+" + jid.User if jid.Server ==
                            "s.whatsapp.net" else jid.User)

    def _conversa(self, conversa_id, chat, pushname, grupo, data):
        with self._trava:
            conv = self._conversas.get(conversa_id)
            if conv is None:
                nome = "Grupo" if grupo else self._nome_contato(chat, pushname)
                conv = m.Conversa(self.conta.id, conversa_id, nome,
                                  self.servico,
                                  "grupo" if grupo else "privada", data=data)
                self._conversas[conversa_id] = conv
            if grupo and conv.nome == "Grupo" and \
                    conversa_id not in self._nomes_grupo_pedidos:
                self._nomes_grupo_pedidos.add(conversa_id)
                self._fila.put(lambda: self._buscar_nome_grupo(conversa_id,
                                                               chat))
        return conv

    def _buscar_nome_grupo(self, conversa_id, chat):
        info = self.cliente.get_group_info(chat)
        nome = info.GroupName.Name
        if not nome:
            return
        with self._trava:
            conv = self._conversas.get(conversa_id)
            if conv is None:
                return
            conv.nome = nome
        self.banco.salvar_conversas([conv])
        self._publicar_conversas()

    # ----------------------------------------------------------- mensagens
    def _ao_receber(self, cliente, evento):
        try:
            info = evento.Info
            with self._trava:
                if info.ID in self._vistas:
                    return
                self._vistas.add(info.ID)
                if len(self._vistas) > MAX_GUARDADAS:
                    self._vistas = set(list(self._vistas)[-MAX_GUARDADAS // 2:])
            origem = info.MessageSource
            grupo = bool(origem.IsGroup)
            cid = self._id_da_conversa(origem.Chat)
            autor = ""
            if grupo and not origem.IsFromMe:
                autor = self._nome_contato(origem.Sender, info.Pushname)
            msg, remetente = converter(evento, self.conta.id, cid, autor)
            if msg is None:
                return
            conv = self._conversa(cid, origem.Chat, info.Pushname, grupo,
                                  msg.data)
            with self._trava:
                conv.data = max(conv.data, msg.data)
                self._remetentes[msg.id] = (remetente, msg.texto)
                if not msg.minha:
                    conv.nao_lidas += 1
                    self._nao_lidas.setdefault(cid, []).append(
                        (msg.id, origem.Sender))
            self.banco.salvar_conversas([conv])
            self.banco.salvar_mensagens([msg])
            self.barramento.publicar(ev.MensagemNova(msg, conv))
        except Exception:
            log.exception("erro ao tratar mensagem recebida")

    def carregar_mensagens(self, conversa_id, limite=50):
        msgs = self.banco.mensagens(self.conta.id, conversa_id,
                                    max(limite, 100))
        self.barramento.publicar(ev.MensagensCarregadas(
            self.conta.id, conversa_id, msgs))

    def enviar_texto(self, conversa_id, texto, resposta_a=""):
        self._fila.put(lambda: self._enviar(conversa_id, texto, resposta_a))

    def _jid(self, conversa_id):
        from neonize.utils.jid import build_jid
        usuario, servidor = conversa_id.split("@", 1)
        return build_jid(usuario, servidor)

    def _mensagem_de_texto(self, conversa_id, texto, resposta_a):
        from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
            ContextInfo, ExtendedTextMessage, Message)
        if not resposta_a:
            return Message(conversation=texto)
        remetente, citado = self._remetentes.get(resposta_a, ("", ""))
        if not remetente or not citado:
            # mensagem de antes desta abertura do app: busca no banco
            for x in self.banco.mensagens(self.conta.id, conversa_id, 500):
                if x.id == resposta_a:
                    citado = citado or x.texto or m.conteudo(x)
                    if not remetente and not conversa_id.endswith("@g.us"):
                        remetente = (
                            self.conta.telefone.lstrip("+")
                            + "@s.whatsapp.net") if x.minha else conversa_id
                    break
        ctx = ContextInfo(stanzaID=resposta_a,
                          quotedMessage=Message(conversation=citado or ""))
        if remetente:
            ctx.participant = remetente
        return Message(extendedTextMessage=ExtendedTextMessage(
            text=texto, contextInfo=ctx))

    def _enviar(self, conversa_id, texto, resposta_a):
        inicio = time.perf_counter()
        try:
            if not self._conectada:
                raise ConnectionError("sem conexão")
            resp = self.cliente.send_message(
                self._jid(conversa_id),
                self._mensagem_de_texto(conversa_id, texto, resposta_a))
        except Exception as e:
            log.warning("envio falhou: %s", type(e).__name__)
            motivo = "sem conexão" if isinstance(e, ConnectionError) else \
                "erro do WhatsApp (%s)" % type(e).__name__
            self.barramento.publicar(ev.EnvioFalhou(
                self.conta.id, conversa_id, texto, motivo))
            return
        log.info("texto enviado em %.2fs", time.perf_counter() - inicio)
        msg = m.Mensagem(self.conta.id, conversa_id, resp.ID, minha=True,
                         data=segundos(resp.Timestamp) or time.time(),
                         texto=texto, estado=m.ENVIADA, resposta_a=resposta_a)
        with self._trava:
            self._vistas.add(resp.ID)
            self._remetentes[resp.ID] = ("", texto)
            conv = self._conversas.get(conversa_id)
            if conv is not None:
                conv.data = max(conv.data, msg.data)
        if conv is not None:
            self.banco.salvar_conversas([conv])
        self.banco.salvar_mensagens([msg])
        self.barramento.publicar(ev.MensagemNova(msg, conv,
                                                 enviada_daqui=True))

    def marcar_como_lida(self, conversa_id):
        with self._trava:
            pendentes = self._nao_lidas.pop(conversa_id, [])
            conv = self._conversas.get(conversa_id)
            if conv is not None:
                conv.nao_lidas = 0
        self.banco.atualizar_conversa(self.conta.id, conversa_id, nao_lidas=0)
        if pendentes:
            self._fila.put(lambda: self._enviar_leitura(conversa_id,
                                                        pendentes))

    def _enviar_leitura(self, conversa_id, pendentes):
        from neonize.utils.enum import ReceiptType
        chat = self._jid(conversa_id)
        por_remetente = {}
        for mid, remetente in pendentes:
            chave = (remetente.User, remetente.Server)
            por_remetente.setdefault(chave, (remetente, []))[1].append(mid)
        for remetente, ids in por_remetente.values():
            self.cliente.mark_read(*ids, chat=chat, sender=remetente,
                                   receipt=ReceiptType.READ)
        log.info("leitura confirmada ao WhatsApp (%d mensagens)",
                 len(pendentes))

    # ------------------------------------------------------------- recibos
    def _ao_recibo(self, cliente, e):
        try:
            origem = e.MessageSource
            cid = self._id_da_conversa(origem.Chat)
            tipo = int(e.Type)
            if tipo == RECIBO_LIDO_POR_MIM:
                # lida no celular ou em outro aparelho
                with self._trava:
                    self._nao_lidas.pop(cid, None)
                    conv = self._conversas.get(cid)
                    if conv is None or conv.nao_lidas == 0:
                        return
                    conv.nao_lidas = 0
                self.banco.atualizar_conversa(self.conta.id, cid, nao_lidas=0)
                self._publicar_conversas()
                return
            estado = {RECIBO_ENTREGUE: m.ENTREGUE, RECIBO_LIDO: m.LIDA,
                      RECIBO_OUVIDO: m.LIDA}.get(tipo)
            if estado is None or origem.IsFromMe:
                return
            mudaram = self.banco.mudar_estado(self.conta.id, cid,
                                              list(e.MessageIDs), estado)
            if mudaram:
                self.barramento.publicar(ev.EstadosMensagens(
                    self.conta.id, cid, mudaram, estado))
        except Exception:
            log.exception("erro ao tratar recibo")

    # ----------------------------------------------------------- historico
    def _ao_historico(self, cliente, e):
        try:
            log.info("pacote de histórico: %s", ", ".join(
                "%s=%s" % kv for kv in resumo_historico(e.Data).items()))
        except Exception:
            log.exception("erro ao ler o pacote de histórico")

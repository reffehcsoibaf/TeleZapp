# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Provedor do WhatsApp (neonize, ligacao Python da whatsmeow).

- O neonize bloqueia ao conectar: connect() roda numa thread so dele, e os
  envios passam por uma fila com a sua propria thread.
- Os eventos do WhatsApp chegam em threads do neonize: aqui so se converte,
  grava no banco e publica eventos para a interface.
- O WhatsApp so entrega historico logo depois do pareamento: o banco local e
  a fonte das conversas. O pacote de historico e guardado conforme o periodo
  escolhido pela pessoa antes de parear (OPCOES_HISTORICO).
- As mensagens enviadas pelo app nao voltam como evento: o app as registra.

O registro nunca grava texto de mensagens, telefones completos ou codigos.
"""
import json
import logging
import os
import queue
import re
import threading
import time

from telezapp import config
from telezapp.midia import armazem
from telezapp.nucleo import eventos as ev
from telezapp.nucleo import modelos as m
from telezapp.provedores.base import DownloadCancelado, ErroMidia, Provedor

log = logging.getLogger("telezapp.whatsapp")

EMBRULHOS = ("deviceSentMessage", "ephemeralMessage", "viewOnceMessage",
             "viewOnceMessageV2", "viewOnceMessageV2Extension",
             "documentWithCaptionMessage", "editedMessage",
             "associatedChildMessage", "commentMessage")
# Campos sem conteudo para a pessoa (chaves, controle): a mensagem e ignorada
SO_CONTROLE = {"senderKeyDistributionMessage", "messageContextInfo",
               "protocolMessage", "reactionMessage", "pollUpdateMessage",
               "keepInChatMessage", "pinInChatMessage",
               # cabecalho de album (as fotos e videos chegam um a um),
               # aviso de grupo mencionado em status e aviso de historico
               "albumMessage", "groupStatusMentionMessage",
               "messageHistoryNotice"}
# Tipos de recibo do neonize (Receipt.Type)
RECIBO_ENTREGUE, RECIBO_LIDO, RECIBO_LIDO_POR_MIM, RECIBO_OUVIDO = 1, 4, 5, 6
MAX_GUARDADAS = 2000
# Sem o aviso de fim da sincronia, os avisos voltam depois deste tempo
TEMPO_MAX_SINCRONIA = 45
# espera (segundos) antes de cada nova tentativa de conexao; a ultima repete
ESPERAS_RECONEXAO = (3, 10, 30, 60, 120)
# Status de mensagem no historico (WebMessageInfo.Status)
HIST_ENTREGUE, HIST_LIDA, HIST_OUVIDA = 3, 4, 5
# Conversas que nao sao conversas para a pessoa
IGNORAR_CONVERSAS = ("status@broadcast",)
IGNORAR_SERVIDORES = ("newsletter", "broadcast")

# Quanto historico pedir ao celular no pareamento: chave -> (rotulo, dias).
# None = o padrao do WhatsApp (so as mensagens recentes).
OPCOES_HISTORICO = {
    "recentes": ("Só as recentes (padrão do WhatsApp)", None),
    "30": ("Últimos 30 dias", 30),
    "180": ("Últimos 6 meses", 180),
    "365": ("Último ano", 365),
    "tudo": ("Todo o histórico (pode demorar e ocupar bastante espaço)",
             3650),
}


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


SEM_NOME = "Contato sem nome"
CANAL_SEM_NOME = "Canal"


def parece_codigo(nome):
    """O 'nome' e so o codigo interno do WhatsApp (numero de endereco LID,
    JID)? Telefones de verdade aparecem com '+'."""
    nome = (nome or "").strip()
    return "@" in nome or (nome.isdigit() and len(nome) >= 14)


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


def mencoes_do_contexto(ctx):
    """[{'jid': ...}] de quem foi mencionado (@) na mensagem; os nomes sao
    achados depois, pelo provedor, que tem acesso aos contatos."""
    if ctx is None:
        return []
    return [{"jid": str(j)} for j in ctx.mentionedJID if str(j)]


def rotulos_dos_botoes(interna):
    """(botoes, opcoes): rotulos dos botoes e das linhas de lista."""
    botoes, opcoes = [], []
    try:
        if interna.HasField("buttonsMessage"):
            botoes += [b.buttonText.displayText
                       for b in interna.buttonsMessage.buttons]
        inter = None
        if interna.HasField("templateMessage"):
            t = interna.templateMessage
            h = t.hydratedTemplate if t.HasField("hydratedTemplate") else \
                t.hydratedFourRowTemplate
            for b in h.hydratedButtons:
                for nome in ("quickReplyButton", "urlButton", "callButton"):
                    if b.HasField(nome):
                        botoes.append(getattr(b, nome).displayText)
            if t.HasField("interactiveMessageTemplate"):
                inter = t.interactiveMessageTemplate
        if interna.HasField("interactiveMessage"):
            inter = interna.interactiveMessage
        if inter is not None and inter.HasField("nativeFlowMessage"):
            for b in inter.nativeFlowMessage.buttons:
                dados = json.loads(b.buttonParamsJSON or "{}")
                botoes.append(dados.get("display_text") or "")
        if interna.HasField("listMessage"):
            for sec in interna.listMessage.sections:
                opcoes += [r.title for r in sec.rows]
    except Exception:
        log.info("não consegui ler os rótulos dos botões")
    return ([b for b in botoes if b], [o for o in opcoes if o])


def _partes_texto(*partes):
    return "\n".join(p.strip() for p in partes if p and p.strip())


def texto_estruturado(interna, presentes):
    """Texto das mensagens de empresa (botoes, modelos, listas, respostas a
    botoes, pedidos), com os botoes e opcoes no fim. None se o tipo nao e um
    destes."""
    texto = _texto_estruturado(interna, presentes)
    if texto is None:
        return None
    botoes, opcoes = rotulos_dos_botoes(interna)
    return _partes_texto(texto,
                         ("Botões: " + ", ".join(botoes)) if botoes else "",
                         ("Opções: " + ", ".join(opcoes)) if opcoes else "")


def _texto_estruturado(interna, presentes):
    if "buttonsMessage" in presentes:
        x = interna.buttonsMessage
        return _partes_texto(x.text, x.contentText, x.footerText)
    if "templateMessage" in presentes:
        x = interna.templateMessage
        h = x.hydratedTemplate if x.HasField("hydratedTemplate") else \
            x.hydratedFourRowTemplate
        texto = _partes_texto(h.hydratedTitleText, h.hydratedContentText,
                              h.hydratedFooterText)
        if texto:
            return texto
        if x.HasField("interactiveMessageTemplate"):
            return _texto_interativo(x.interactiveMessageTemplate)
        return ""
    if "interactiveMessage" in presentes:
        return _texto_interativo(interna.interactiveMessage)
    if "listMessage" in presentes:
        x = interna.listMessage
        return _partes_texto(x.title, x.description, x.footerText)
    if "buttonsResponseMessage" in presentes:
        return "resposta: " + interna.buttonsResponseMessage.\
            selectedDisplayText
    if "listResponseMessage" in presentes:
        return "resposta: " + interna.listResponseMessage.title
    if "templateButtonReplyMessage" in presentes:
        return "resposta: " + interna.templateButtonReplyMessage.\
            selectedDisplayText
    if "interactiveResponseMessage" in presentes:
        return "resposta: " + interna.interactiveResponseMessage.body.text
    if "orderMessage" in presentes:
        x = interna.orderMessage
        return _partes_texto("pedido", x.orderTitle, x.message)
    return None


NOMES_ACOES_INTERATIVAS = {
    "payment_info": "solicitação de pagamento",
    "review_and_pay": "solicitação de pagamento",
    "order_details": "detalhes do pedido",
    "send_location": "pedido de localização",
}


def _texto_interativo(x):
    texto = _partes_texto(x.header.title, x.body.text, x.footer.text)
    if texto or not x.HasField("nativeFlowMessage"):
        return texto
    nomes = [NOMES_ACOES_INTERATIVAS.get(b.name, b.name)
             for b in x.nativeFlowMessage.buttons if b.name]
    return ("mensagem interativa: " + ", ".join(nomes)) if nomes else ""


def botoes_do_whatsapp(interna):
    """[(rotulo, endereco)] dos botoes de link de mensagens de empresa."""
    botoes = []
    try:
        if interna.HasField("templateMessage"):
            t = interna.templateMessage
            h = t.hydratedTemplate if t.HasField("hydratedTemplate") else \
                t.hydratedFourRowTemplate
            for b in h.hydratedButtons:
                if not b.HasField("urlButton"):
                    continue
                url = b.urlButton.URL
                if url:
                    botoes.append((b.urlButton.displayText or url, url))
        inter = None
        if interna.HasField("interactiveMessage"):
            inter = interna.interactiveMessage
        elif interna.HasField("templateMessage") and \
                interna.templateMessage.HasField("interactiveMessageTemplate"):
            inter = interna.templateMessage.interactiveMessageTemplate
        if inter is not None and inter.HasField("nativeFlowMessage"):
            for b in inter.nativeFlowMessage.buttons:
                if b.name != "cta_url":
                    continue
                dados = json.loads(b.buttonParamsJSON or "{}")
                url = dados.get("url") or dados.get("merchant_url") or ""
                if url:
                    botoes.append((dados.get("display_text") or url, url))
    except Exception:
        log.info("não consegui ler os botões de uma mensagem de empresa")
    return botoes


def acoes_do_whatsapp(interna):
    """Botoes de resposta e opcoes de lista que o toque pode acionar:
    [{'tipo', 'rotulo', 'id', 'indice', 'descricao'}]. Tipos: modelo
    (botao de resposta rapida de modelo de empresa), botoes (buttonsMessage),
    fluxo (quick_reply de mensagem interativa) e lista (linha de lista).
    Botoes de link, ligar e pagamento nao entram: nao sao respostas."""
    acoes = []
    try:
        if interna.HasField("buttonsMessage"):
            for i, b in enumerate(interna.buttonsMessage.buttons):
                if b.buttonText.displayText:
                    acoes.append({"tipo": "botoes", "indice": i,
                                  "rotulo": b.buttonText.displayText,
                                  "id": b.buttonID})
        inter = None
        if interna.HasField("templateMessage"):
            t = interna.templateMessage
            h = t.hydratedTemplate if t.HasField("hydratedTemplate") else \
                t.hydratedFourRowTemplate
            for pos, b in enumerate(h.hydratedButtons):
                if b.HasField("quickReplyButton") and \
                        b.quickReplyButton.displayText:
                    acoes.append({
                        "tipo": "modelo",
                        "indice": b.index if b.index else pos,
                        "rotulo": b.quickReplyButton.displayText,
                        "id": b.quickReplyButton.ID})
            if t.HasField("interactiveMessageTemplate"):
                inter = t.interactiveMessageTemplate
        if interna.HasField("interactiveMessage"):
            inter = interna.interactiveMessage
        if inter is not None and inter.HasField("nativeFlowMessage"):
            for i, b in enumerate(inter.nativeFlowMessage.buttons):
                if b.name != "quick_reply":
                    continue
                dados = json.loads(b.buttonParamsJSON or "{}")
                if dados.get("display_text"):
                    acoes.append({"tipo": "fluxo", "indice": i,
                                  "rotulo": dados["display_text"],
                                  "id": dados.get("id") or str(i)})
        if interna.HasField("listMessage"):
            for sec in interna.listMessage.sections:
                for r in sec.rows:
                    if r.title:
                        acoes.append({"tipo": "lista", "indice": 0,
                                      "rotulo": r.title, "id": r.rowID,
                                      "descricao": r.description})
    except Exception:
        log.info("não consegui ler as ações de uma mensagem de empresa")
    return acoes


CAMPOS_INTERATIVOS = ("buttonsMessage", "templateMessage", "interactiveMessage",
                      "listMessage", "buttonsResponseMessage",
                      "listResponseMessage", "templateButtonReplyMessage",
                      "interactiveResponseMessage")


_CAMPOS_PESADOS = ("JPEGThumbnail", "jpegThumbnail", "contextInfo",
                   "mediaKey", "thumbnail", "fileEncSHA256", "fileSHA256",
                   "mediaKeyTimestamp", "directPath", "fileEncSha256",
                   "fileSha256", "streamingSidecar")


def _limpar(x, truncar=0, manter=()):
    """Tira miniaturas e chaves de midia de uma estrutura (dict/list) e, se
    `truncar`, corta textos maiores que isso."""
    if isinstance(x, dict):
        return {k: _limpar(v, truncar, manter) for k, v in x.items()
                if k not in _CAMPOS_PESADOS or k in manter}
    if isinstance(x, list):
        return [_limpar(v, truncar, manter) for v in x]
    if truncar and isinstance(x, str) and len(x) > truncar:
        return x[:truncar] + "…"
    return x


def original_com_acoes(interna, acoes):
    """JSON (sem miniaturas) da mensagem que tem botoes/opcoes, guardado
    para citar a mensagem inteira ao responder, como faz o celular. Vazio
    se nao ha acoes."""
    if not acoes:
        return ""
    from google.protobuf.json_format import MessageToDict
    try:
        return json.dumps(_limpar(MessageToDict(interna)), ensure_ascii=False,
                          separators=(",", ":"))
    except Exception:
        return ""


def estrutura_bruta(mensagem, info=None):
    """Estrutura original (JSON, sem miniaturas nem chaves) de uma mensagem
    do WhatsApp, para o menu Depurar. `mensagem` e o protobuf Message ou
    WebMessageInfo; `info` (opcional) e o Info do evento ao vivo."""
    from google.protobuf.json_format import MessageToDict
    saida = {}
    try:
        if info is not None:
            saida["info"] = _limpar(MessageToDict(info))
        saida["mensagem"] = _limpar(MessageToDict(mensagem), manter=(
            "contextInfo",))
    except Exception as e:
        saida["erro"] = "não consegui ler a estrutura: %s" % type(e).__name__
    return json.dumps(saida, ensure_ascii=False, indent=2, default=str)


def estrutura_interativa(interna):
    """Formato (sem textos longos nem imagens) de uma mensagem de empresa
    com botoes ou lista, para o registro: serve para implementarmos o toque
    nos botoes com dados reais. None se nao e deste tipo."""
    from google.protobuf.json_format import MessageToDict
    for nome in CAMPOS_INTERATIVOS:
        try:
            if not interna.HasField(nome):
                continue
            dados = MessageToDict(getattr(interna, nome))
        except Exception:
            continue

        return {nome: _limpar(dados, 80)}
    return None


def nome_verificado(info):
    """Nome verificado de empresa que vem junto da mensagem, ou ''."""
    try:
        return info.VerifiedName.Details.verifiedName or ""
    except Exception:
        return ""


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
    if "groupInviteMessage" in presentes:
        x = interna.groupInviteMessage
        return m.OUTRO, _partes_texto(
            "convite para o grupo: " + (x.groupName or "sem nome"),
            x.caption), 0, "", 0
    if "contactMessage" in presentes:
        return m.OUTRO, "contato: " + interna.contactMessage.displayName, 0, \
            "", 0
    texto = texto_estruturado(interna, presentes)
    if texto:
        return m.TEXTO, texto, 0, "", 0
    # nao reconhecido: o nome do campo fica na mensagem e no registro, para
    # tratarmos cada caso
    desconhecidos = sorted(presentes - SO_CONTROLE)
    log.info("conteúdo ainda sem suporte: %s", ", ".join(desconhecidos))
    return m.OUTRO, "tipo do WhatsApp: " + ", ".join(desconhecidos), 0, \
        "", 0


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
    forma = estrutura_interativa(interna)
    if forma:
        log.info("mensagem interativa: %s", json.dumps(forma,
                                                       ensure_ascii=False))
    msg = m.Mensagem(
        conta_id=conta_id, conversa_id=conversa_id, id=info.ID,
        autor="" if minha else (autor or info.Pushname or
                                nome_verificado(info)),
        minha=minha, data=segundos(info.Timestamp) or time.time(),
        tipo=tipo, texto=texto or "", segundos=int(seg or 0),
        nome_arquivo=arquivo or "", tamanho=int(tamanho or 0),
        estado=m.ENVIADA if minha else "",
        resposta_a=(ctx.stanzaID if ctx is not None and ctx.stanzaID
                    else ""),
        remetente="" if minha else jid_texto(origem.Sender))
    interna_ = desembrulhar(evento.Message)
    acoes_ = acoes_do_whatsapp(interna_)
    m.guardar_extras(msg, botoes=botoes_do_whatsapp(interna_),
                     mencoes=mencoes_do_contexto(ctx), acoes=acoes_,
                     original=original_com_acoes(interna_, acoes_))
    return msg, msg.remetente


CAMPOS_MIDIA = ("imageMessage", "videoMessage", "audioMessage",
                "documentMessage", "stickerMessage")


def ficha_de(interna):
    """O minimo que o WhatsApp exige para baixar a midia depois (chaves e
    caminho), sem miniatura nem resposta citada. None se nao ha midia."""
    from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import Message
    for nome in CAMPOS_MIDIA:
        try:
            if not interna.HasField(nome):
                continue
        except (ValueError, AttributeError):
            continue
        sub = type(getattr(interna, nome))()
        sub.CopyFrom(getattr(interna, nome))
        for campo in ("contextInfo", "JPEGThumbnail", "caption"):
            try:
                sub.ClearField(campo)
            except ValueError:
                pass
        return Message(**{nome: sub}).SerializeToString()
    return None


def mime_da_ficha(dados):
    from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import Message
    interna = Message.FromString(dados)
    for nome in CAMPOS_MIDIA:
        if interna.HasField(nome):
            return getattr(interna, nome).mimetype
    return ""


def jid_de_texto(texto):
    """'usuario@servidor' -> (usuario, servidor)."""
    if "@" not in (texto or ""):
        return texto or "", "s.whatsapp.net"
    usuario, servidor = texto.split("@", 1)
    return usuario.split(":")[0], servidor


def converter_historico(wmi, conta_id, conversa_id, autor=""):
    """WebMessageInfo do pacote de historico -> (Mensagem, jid de quem
    enviou) ou (None, "") se for so controle."""
    if not wmi.HasField("message"):
        return None, ""
    dados = conteudo_de(desembrulhar(wmi.message))
    if dados is None:
        return None, ""
    tipo, texto, seg, arquivo, tamanho = dados
    minha = bool(wmi.key.fromMe)
    estado = ""
    if minha:
        estado = {HIST_ENTREGUE: m.ENTREGUE, HIST_LIDA: m.LIDA,
                  HIST_OUVIDA: m.LIDA}.get(int(wmi.status), m.ENVIADA)
    forma = estrutura_interativa(desembrulhar(wmi.message))
    if forma:
        log.info("mensagem interativa: %s", json.dumps(forma,
                                                       ensure_ascii=False))
    ctx = _contexto(desembrulhar(wmi.message))
    remetente = wmi.key.participant or wmi.participant or wmi.key.remoteJID
    msg = m.Mensagem(
        conta_id=conta_id, conversa_id=conversa_id, id=wmi.key.ID,
        autor="" if minha else (autor or wmi.pushName or ""),
        minha=minha, data=segundos(wmi.messageTimestamp),
        tipo=tipo, texto=texto or "", segundos=int(seg or 0),
        nome_arquivo=arquivo or "", tamanho=int(tamanho or 0),
        estado=estado,
        resposta_a=(ctx.stanzaID if ctx is not None and ctx.stanzaID
                    else ""),
        remetente="" if minha else _sem_aparelho(remetente))
    interna_ = desembrulhar(wmi.message)
    acoes_ = acoes_do_whatsapp(interna_)
    m.guardar_extras(msg, botoes=botoes_do_whatsapp(interna_),
                     mencoes=mencoes_do_contexto(ctx), acoes=acoes_,
                     original=original_com_acoes(interna_, acoes_))
    return msg, remetente


def _sem_aparelho(jid):
    """'5551...:12@s.whatsapp.net' -> '5551...@s.whatsapp.net'."""
    usuario, servidor = jid_de_texto(jid)
    return "%s@%s" % (usuario, servidor) if usuario else ""


def props_do_aparelho(historico):
    """DeviceProps: o nome 'TeleZapp' no celular e quanto historico pedir."""
    from neonize.proto.waCompanionReg.WAWebProtobufsCompanionReg_pb2 \
        import DeviceProps
    props = DeviceProps(os="TeleZapp", platformType=DeviceProps.DESKTOP)
    dias = OPCOES_HISTORICO.get(historico, OPCOES_HISTORICO["recentes"])[1]
    if dias:
        props.requireFullSync = True
        props.historySyncConfig.fullSyncDaysLimit = dias
        props.historySyncConfig.fullSyncSizeMbLimit = 102400
        props.historySyncConfig.storageQuotaMb = 102400
    return props


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
                 pasta_sessoes=None, fabrica_cliente=None,
                 historico="recentes"):
        super().__init__(conta, barramento, banco, pedir)
        self.historico = historico
        self._desligada = False     # desconectada pelo celular
        self._nao_reconectar = False  # banida ou aberta em outro lugar
        self._lid_para_numero = {}  # do pacote de historico
        self._apelidos = {}         # jid -> nome de perfil (pushname)
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
        self._nomes_empresa_pedidos = set()
        self._sem_nome_registrados = set()
        self._conectada = False
        self._cache_mencoes = {}   # jid mencionado -> nome, id, telefone
        self._sincronizando = False
        self._progresso_historico = 0   # 0 = nada em andamento
        self._recebidas_na_sincronia = 0
        self._trava = threading.RLock()

    # ----------------------------------------------------------- execucao
    def _criar_cliente(self):
        from neonize.client import NewClient
        self._ligar_log_detalhado()
        caminho = caminho_sessao(self.pasta_sessoes, self.conta.id)
        return NewClient(caminho, props=props_do_aparelho(self.historico))

    @staticmethod
    def _ligar_log_detalhado():
        """Com a opcao ligada, o lado em Go grava cada pacote trocado com o
        WhatsApp no log (o nivel e lido quando o cliente conecta)."""
        try:
            from telezapp import config
            if not config.Config().get("log_detalhado_whatsapp"):
                return
            from neonize.utils import log as log_neonize
            log_neonize.setLevel(logging.DEBUG)
            # os registros do lado em Go chegam com nomes whatsmeow.*, que
            # herdam o nivel destes
            for nome in ("whatsmeow", "Whatsmeow"):
                logging.getLogger(nome).setLevel(logging.DEBUG)
            log.info("registro técnico detalhado do WhatsApp ligado")
        except Exception:
            log.exception("não consegui ligar o registro detalhado")

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
        """Mantem a conexao: se o connect() terminar sem que ninguem tenha
        pedido (queda de rede, websocket fechado), avisa e tenta de novo
        com espera crescente."""
        tentativa = 0
        while not self._parar.is_set():
            inicio = time.monotonic()
            if not self._uma_conexao():
                return          # erro de configuracao: nao adianta repetir
            if self._parar.is_set() or self._desligada \
                    or self._nao_reconectar:
                return
            if time.monotonic() - inicio > 300:
                tentativa = 0   # ficou conectada um bom tempo
            self._conectada = False
            self._avisar_sincronia_interrompida()
            espera = ESPERAS_RECONEXAO[min(tentativa,
                                           len(ESPERAS_RECONEXAO) - 1)]
            tentativa += 1
            log.warning("conexão do WhatsApp encerrada sem pedido; nova "
                        "tentativa em %ds (tentativa %d)", espera, tentativa)
            self._estado(ev.DESCONECTADA, "reconectando")
            if self._parar.wait(espera):
                return

    def _avisar_sincronia_interrompida(self):
        """Se o historico estava chegando, diz em quantos por cento parou."""
        pct = self._progresso_historico
        if 0 < pct < 100:
            self._progresso_historico = 0
            self.barramento.publicar(ev.ProgressoSincronia(
                self.conta.id, pct, interrompida=True))

    def _uma_conexao(self):
        """Cria o cliente e conecta (bloqueia ate a conexao acabar).
        Devolve False se houve erro que nao adianta repetir."""
        try:
            import neonize.events as nev
            self.cliente = self.fabrica_cliente()
            registros = {
                "ConnectedEv": self._ao_conectar,
                "PairStatusEv": self._ao_parear,
                "LoggedOutEv": self._ao_sair,
                "DisconnectedEv": self._ao_desconectar,
                "MessageEv": self._ao_receber,
                "GroupInfoEv": self._ao_grupo_mudou,
                "JoinedGroupEv": self._ao_entrou_no_grupo,
                "ReceiptEv": self._ao_recibo,
                "HistorySyncEv": self._ao_historico,
                "TemporaryBanEv": self._ao_banimento,
                "StreamReplacedEv": self._ao_substituida,
                "ConnectFailureEv": self._ao_falha_conexao,
                "ClientOutdatedEv": self._ao_desatualizado,
                "OfflineSyncCompletedEv": self._ao_fim_sincronia,
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
            return True
        except Exception:
            if not self._parar.is_set():
                log.exception("erro na conexão do WhatsApp")
                self._estado(ev.ERRO, "falha na conexão")
                self._avisar("Erro na conexão do WhatsApp. Os detalhes estão "
                             "no log.", True)
            return False

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
        if self._desligada:
            return   # so pareia de novo quando a pessoa pedir
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
        # as mensagens que chegaram com o app fechado vem agora: sem avisos
        # uma a uma ate o fim da sincronia
        with self._trava:
            self._sincronizando = True
            self._recebidas_na_sincronia = 0
        relogio = threading.Timer(TEMPO_MAX_SINCRONIA,
                                  lambda: self._ao_fim_sincronia(None, None))
        relogio.daemon = True
        relogio.start()
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

    def _ao_fim_sincronia(self, cliente, e):
        with self._trava:
            if not self._sincronizando:
                return
            self._sincronizando = False
            quantas = self._recebidas_na_sincronia
        log.info("sincronia inicial concluída (%d mensagens recebidas)",
                 quantas)
        self.barramento.publicar(ev.SincronizacaoConcluida(self.conta.id,
                                                           quantas))

    def _ao_sair(self, cliente, e):
        self._conectada = False
        self._desligada = True
        log.warning("sessão encerrada pelo WhatsApp (motivo %s)", e.Reason)
        self._estado(ev.PRECISA_LOGIN, DESCONECTADA_PELO_CELULAR)

    def _ao_desconectar(self, cliente, e):
        if self._parar.is_set():
            return
        self._conectada = False
        self._avisar_sincronia_interrompida()
        self._estado(ev.DESCONECTADA, "reconectando")

    def _ao_banimento(self, cliente, e):
        log.warning("banimento temporário: %s", e)
        self._avisar("O WhatsApp bloqueou esta conta temporariamente.", True)

    def _ao_substituida(self, cliente, e):
        log.warning("sessão substituída por outro aparelho")
        self._nao_reconectar = True
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
        if chat.Server == "lid" and jid_texto(chat) in self._lid_para_numero:
            return self._lid_para_numero[jid_texto(chat)]
        if chat.Server == "lid" and self.cliente is not None:
            try:
                pn = self.cliente.get_pn_from_lid(chat)
                if pn.User:
                    return jid_texto(pn)
            except Exception:
                log.info("sem número para um endereço LID")
        return jid_texto(chat)

    def _numero_do_jid(self, jid):
        """JID de telefone (s.whatsapp.net) de um endereco LID, ou o proprio
        JID. Sem numero conhecido, devolve o JID como veio."""
        if jid.Server != "lid":
            return jid
        outro = self._lid_para_numero.get(jid_texto(jid))
        if outro:
            usuario, servidor = jid_de_texto(outro)
            return _jid_obj(usuario, servidor)
        if self.cliente is not None:
            try:
                pn = self.cliente.get_pn_from_lid(jid)
                if pn.User:
                    return pn
            except Exception:
                log.info("sem número para um endereço LID")
        return jid

    def _nome_contato(self, jid, pushname=""):
        """Nome do contato (agenda), senao o nome de registro (perfil da
        pessoa, nome verificado da empresa) e, por ultimo, o telefone. Nunca
        o codigo interno do WhatsApp."""
        pushname = pushname or self._apelidos.get(jid_texto(jid), "")
        alvo = self._numero_do_jid(jid)
        empresa = ""
        for tentativa in (alvo, jid) if alvo is not jid else (jid,):
            try:
                info = self.cliente.contact.get_contact(tentativa)
            except Exception:
                continue
            nome = info.FullName or info.FirstName
            if nome and not parece_codigo(nome):
                return nome
            pushname = pushname or info.PushName
            empresa = empresa or info.BusinessName
        for nome in (pushname, empresa):
            if nome and not parece_codigo(nome):
                return nome
        if alvo.Server == "s.whatsapp.net" and alvo.User:
            return "+" + alvo.User
        return SEM_NOME

    def depurar_conversa(self, conversa_id):
        """Como o nome da conversa foi achado (menu Depurar)."""
        dados = {"conversa_id": conversa_id}
        if self.cliente is None or "@" not in (conversa_id or ""):
            return dados
        try:
            usuario, servidor = jid_de_texto(conversa_id)
            jid = _jid_obj(usuario, servidor)
            alvo = self._numero_do_jid(jid)
            dados["servidor"] = servidor
            dados["numero"] = "%s@%s" % (alvo.User, alvo.Server)
            dados["apelido_visto_nas_mensagens"] = self._apelidos.get(
                conversa_id, "")
            for tentativa in (alvo, jid) if alvo is not jid else (jid,):
                try:
                    info = self.cliente.contact.get_contact(tentativa)
                except Exception as e:
                    dados["contato_%s" % tentativa.Server] = \
                        "erro: %s" % type(e).__name__
                    continue
                dados["contato_%s" % tentativa.Server] = {
                    "nome_na_agenda": info.FullName or info.FirstName,
                    "nome_no_perfil": info.PushName,
                    "nome_verificado_da_empresa": info.BusinessName}
            dados["nome_escolhido"] = self._nome_contato(jid)
        except Exception as e:
            dados["erro"] = type(e).__name__
        return dados

    def nome_de_participante(self, participante_id):
        """Nome de quem entregou/leu uma mensagem, para os detalhes."""
        if self.cliente is None or "@" not in (participante_id or ""):
            return ""
        try:
            usuario, servidor = jid_de_texto(participante_id)
            nome = self._nome_contato(_jid_obj(usuario, servidor))
        except Exception:
            return ""
        return "" if nome == SEM_NOME else nome

    def _dados_mencao(self, jid_txt):
        """{'nome', 'id', 'telefone'} de quem foi mencionado (com cache)."""
        achado = self._cache_mencoes.get(jid_txt)
        if achado is not None:
            return achado
        usuario, servidor = jid_de_texto(jid_txt)
        jid = _jid_obj(usuario, servidor)
        if servidor == "lid":
            try:
                pn = self.cliente.get_pn_from_lid(jid)
                if pn.User:
                    jid = pn
            except Exception:
                log.info("sem número para uma menção com endereço LID")
        telefone = "+" + jid.User if jid.Server == "s.whatsapp.net" else ""
        achado = {"nome": self._nome_contato(jid) or usuario,
                  "id": jid_texto(jid), "telefone": telefone}
        self._cache_mencoes[jid_txt] = achado
        return achado

    def _enriquecer_mencoes(self, msg):
        """Poe nome, telefone e id em cada @ e troca '@numero' por '@nome'
        no texto da mensagem."""
        extras = m.extras_de(msg)
        if not extras["mencoes"]:
            return
        texto = msg.texto
        for men in extras["mencoes"]:
            if not men.get("jid") or men.get("nome"):
                continue
            try:
                men.update(self._dados_mencao(men["jid"]))
            except Exception:
                log.exception("erro ao achar o nome de uma menção")
                continue
            usuario = jid_de_texto(men["jid"])[0]
            nome = men["nome"]
            texto = re.sub(r"@%s(?!\d)" % re.escape(usuario),
                           lambda _: "@" + nome, texto)
        msg.texto = texto
        m.guardar_extras(msg, extras["links"], extras["botoes"],
                         extras["mencoes"], extras["acoes"],
                         extras["original"])

    def _conversa(self, conversa_id, chat, pushname, grupo, data):
        canal = chat.Server == "newsletter"
        with self._trava:
            conv = self._conversas.get(conversa_id)
            if conv is None:
                if grupo:
                    nome = "Grupo"
                elif canal:
                    nome = CANAL_SEM_NOME
                else:
                    nome = self._nome_contato(chat, pushname)
                conv = m.Conversa(self.conta.id, conversa_id, nome,
                                  self.servico,
                                  "grupo" if grupo else (
                                      "canal" if canal else "privada"),
                                  data=data)
                self._conversas[conversa_id] = conv
            elif not grupo and not canal and (
                    parece_codigo(conv.nome) or conv.nome == SEM_NOME or
                    conv.nome.startswith("+")):
                # so com codigo, sem nome ou so com o telefone: tenta de novo
                conv.nome = self._nome_contato(chat, pushname)
            if grupo and conv.nome == "Grupo" and \
                    conversa_id not in self._nomes_grupo_pedidos:
                self._nomes_grupo_pedidos.add(conversa_id)
                self._fila.put(lambda: self._buscar_nome_grupo(conversa_id,
                                                               chat))
            if not grupo and not canal and (
                    conv.nome.startswith("+") or conv.nome == SEM_NOME) and \
                    conversa_id not in self._nomes_empresa_pedidos:
                # so o telefone: pergunta ao WhatsApp se e uma empresa
                self._nomes_empresa_pedidos.add(conversa_id)
                self._fila.put(lambda: self._buscar_nome_empresa(
                    conversa_id, chat))
            if canal and (conv.nome == CANAL_SEM_NOME or
                          parece_codigo(conv.nome)) and \
                    conversa_id not in self._nomes_grupo_pedidos:
                self._nomes_grupo_pedidos.add(conversa_id)
                self._fila.put(lambda: self._buscar_nome_canal(conversa_id,
                                                               chat))
        return conv

    def _buscar_nome_empresa(self, conversa_id, chat):
        self._consultar_empresas([conversa_id])

    def _consultar_empresas(self, ids):
        """Nome verificado de empresa, pedido ao WhatsApp em lotes (roda na
        fila). So para conversas que ainda tem apenas o telefone."""
        for inicio in range(0, len(ids), 40):
            lote = ids[inicio:inicio + 40]
            jids = {}
            for cid in lote:
                usuario, servidor = jid_de_texto(cid)
                jids[cid] = self._numero_do_jid(_jid_obj(usuario, servidor))
            try:
                achados = self.cliente.get_user_info(*jids.values())
            except Exception:
                log.info("não consegui consultar o nome de %d conversas",
                         len(lote))
                continue
            # A whatsmeow guarda o nome verificado no cadastro de contatos
            # (BusinessName) ao receber a resposta, mas nao o devolve em
            # UserInfo: por isso o nome e lido do cadastro depois da consulta.
            por_usuario = {}
            for x in achados:
                try:
                    por_usuario[x.JID.User] = \
                        x.UserInfo.VerifiedName.Details.verifiedName
                except Exception:
                    pass
            for cid, jid in jids.items():
                if por_usuario.get(jid.User):
                    continue
                usuario, servidor = jid_de_texto(cid)
                for tentativa in (jid, _jid_obj(usuario, servidor)):
                    try:
                        info = self.cliente.contact.get_contact(tentativa)
                    except Exception:
                        continue
                    if info.BusinessName:
                        por_usuario[jid.User] = info.BusinessName
                        break
            log.info("consulta de empresa: %d conversas, %d com nome "
                     "verificado", len(lote),
                     sum(1 for n in por_usuario.values() if n))
            mudou = []
            with self._trava:
                for cid, jid in jids.items():
                    nome = por_usuario.get(jid.User, "")
                    conv = self._conversas.get(cid)
                    if not nome or parece_codigo(nome) or conv is None or \
                            not (conv.nome.startswith("+") or
                                 conv.nome == SEM_NOME):
                        continue
                    conv.nome = nome
                    mudou.append(conv)
            if mudou:
                self.banco.salvar_conversas(mudou)
                self._publicar_conversas()

    def _buscar_nome_canal(self, conversa_id, chat):
        try:
            info = self.cliente.get_newsletter_info(chat)
            nome = info.ThreadMeta.Name.Text
        except Exception:
            log.info("não consegui o nome de um canal")
            return
        if not nome:
            return
        with self._trava:
            conv = self._conversas.get(conversa_id)
            if conv is None:
                return
            conv.nome = nome
        self.banco.salvar_conversas([conv])
        self._publicar_conversas()

    def _ao_grupo_mudou(self, cliente, evento):
        """Alguem mudou os dados do grupo; aqui so o nome interessa."""
        try:
            if evento.HasField("Name"):
                self._renomear_grupo(jid_texto(evento.JID), evento.Name.Name)
        except Exception:
            log.exception("erro ao tratar mudança no grupo")

    def _ao_entrou_no_grupo(self, cliente, evento):
        """O WhatsApp reenvia os dados do grupo (nome atual) ao entrar nele
        ou ao reconectar depois de ficar fora."""
        try:
            info = evento.GroupInfo
            self._renomear_grupo(jid_texto(info.JID), info.GroupName.Name)
        except Exception:
            log.exception("erro ao tratar entrada no grupo")

    def _renomear_grupo(self, conversa_id, nome):
        """Troca o nome de um grupo ja conhecido; so avisa se mudou."""
        if not conversa_id or not nome:
            return
        with self._trava:
            conv = self._conversas.get(conversa_id)
            if conv is None or conv.nome == nome:
                return
            conv.nome = nome
        log.info("grupo renomeado")
        self.banco.salvar_conversas([conv])
        self._publicar_conversas()

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
                autor = self._nome_contato(
                    origem.Sender, info.Pushname or nome_verificado(info))
            msg, remetente = converter(evento, self.conta.id, cid, autor)
            if msg is None:
                return
            self._enriquecer_mencoes(msg)
            if self.banco.depuracao:
                self.banco.guardar_depuracao(
                    self.conta.id, cid, msg.id,
                    estrutura_bruta(evento.Message, info))
            if cid in IGNORAR_CONVERSAS:
                self._guardar_status(msg, origem, info.Pushname)
                return
            if msg.tipo in armazem.BAIXAVEIS:
                ficha = ficha_de(desembrulhar(evento.Message))
                if ficha:
                    self.banco.salvar_fichas(
                        [(self.conta.id, cid, msg.id, ficha)])
            conv = self._conversa(cid, origem.Chat,
                                  info.Pushname or nome_verificado(info), grupo,
                                  msg.data)
            if not grupo and conv.nome.startswith("+") and \
                    cid not in self._sem_nome_registrados:
                self._sem_nome_registrados.add(cid)
                log.info("mensagem ao vivo de conversa só com telefone: "
                         "perfil=%s, nome verificado=%s",
                         "veio" if info.Pushname else "não veio",
                         "veio" if nome_verificado(info) else "não veio")
            if not grupo and not msg.minha and not msg.autor:
                msg.autor = conv.nome       # conversa privada: quem fala
            with self._trava:
                conv.data = max(conv.data, msg.data)
                self._remetentes[msg.id] = (remetente, msg.texto)
                silenciosa = self._sincronizando
                if not msg.minha:
                    conv.nao_lidas += 1
                    self._nao_lidas.setdefault(cid, []).append(
                        (msg.id, origem.Sender))
                    if silenciosa:
                        self._recebidas_na_sincronia += 1
            self.banco.salvar_conversas([conv])
            self.banco.salvar_mensagens([msg])
            self.barramento.publicar(ev.MensagemNova(msg, conv,
                                                     silenciosa=silenciosa))
        except Exception:
            log.exception("erro ao tratar mensagem recebida")

    def baixar_arquivo(self, msg, base, progresso, cancelado):
        dados = self.banco.ficha(msg.conta_id, msg.conversa_id, msg.id)
        if dados is None:
            raise ErroMidia(
                "Esta mídia chegou antes do TeleZapp guardar os dados para "
                "baixá-la. Só as mídias recebidas daqui para a frente, ou do "
                "histórico de um novo pareamento, podem ser baixadas.")
        if not self._conectada or self.cliente is None:
            raise ErroMidia("Sem conexão com o WhatsApp.")
        from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import Message
        caminho = armazem.com_extensao(base, armazem.extensao(
            mime_da_ficha(dados), msg.tipo, msg.nome_arquivo))
        parcial = caminho + ".parte"
        if cancelado():
            raise DownloadCancelado()
        progresso(0)
        try:
            self.cliente.download_any(Message.FromString(dados), parcial)
            if cancelado():
                raise DownloadCancelado()
            os.replace(parcial, caminho)
        except (DownloadCancelado, ErroMidia):
            raise
        except Exception as e:
            log.warning("download falhou: %s", type(e).__name__)
            raise ErroMidia("O WhatsApp não entregou a mídia (%s). Ela pode "
                            "ter expirado no servidor." % type(e).__name__)
        finally:
            if os.path.exists(parcial):
                os.remove(parcial)
        progresso(100)
        return caminho

    def _guardar_status(self, msg, origem, pushname):
        """Status (stories) nao sao conversas: ficam numa tabela a parte,
        para ver, curtir e responder numa etapa futura."""
        autor_id = self._id_da_conversa(origem.Sender)
        self.banco.salvar_status(self.conta.id, {
            "id": msg.id, "autor_id": autor_id,
            "autor": "Você" if msg.minha else self._nome_contato(
                origem.Sender, pushname),
            "minha": msg.minha, "data": msg.data, "tipo": msg.tipo,
            "texto": msg.texto, "segundos": msg.segundos,
            "nome_arquivo": msg.nome_arquivo, "tamanho": msg.tamanho})
        log.info("status guardado (%s)", msg.tipo)

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
            for x in self.banco.mensagens(self.conta.id, conversa_id, 1000):
                if x.id == resposta_a:
                    citado = citado or x.texto or m.conteudo(x)
                    if not remetente:
                        remetente = (self.conta.telefone.lstrip("+") +
                                     "@s.whatsapp.net") if x.minha else (
                            x.remetente or ("" if conversa_id.endswith(
                                "@g.us") else conversa_id))
                    break
        ctx = ContextInfo(stanzaID=resposta_a,
                          quotedMessage=Message(conversation=citado or ""))
        if remetente:
            ctx.participant = remetente
        return Message(extendedTextMessage=ExtendedTextMessage(
            text=texto, contextInfo=ctx))

    def responder_acao(self, msg, acao):
        """Toca um botao de resposta (ou escolhe uma opcao de lista) de uma
        mensagem de empresa: manda a resposta citando a mensagem."""
        descricao = "tipo=%s id=%r indice=%s" % (
            acao.get("tipo"), acao.get("id"), acao.get("indice"))
        log.info("resposta de botão: %s", descricao)
        self._fila.put(lambda: self._enviar(
            msg.conversa_id, acao.get("rotulo", ""), msg.id,
            lambda: self._variantes_da_acao(msg, acao), descricao))

    def _variantes_da_acao(self, msg, acao):
        """[(nome, destino, Message, add_msg_secret)]: do mais parecido com o
        que o celular envia ao mais simples. O servidor recusa (479) o que
        considera invalido; as variantes seguintes so sao tentadas nesse
        caso, e nada foi entregue quando ele recusa."""
        from google.protobuf.json_format import ParseDict
        from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import Message
        original = None
        bruto = m.extras_de(msg)["original"]
        if bruto:
            try:
                original = ParseDict(json.loads(bruto), Message(),
                                     ignore_unknown_fields=True)
            except Exception:
                original = None
        simples = Message(conversation=msg.texto or m.conteudo(msg))
        lid = msg.remetente if msg.remetente.endswith("@lid") else ""
        candidatas = []
        if original is not None:
            if lid:
                candidatas.append(("como o celular (conversa LID)", lid,
                                   original, True))
            candidatas.append(("citando a mensagem inteira",
                               msg.conversa_id, original, False))
        candidatas.append(("citação simples", msg.conversa_id, simples,
                           False))
        variantes = [(nome, dest, self._mensagem_de_acao(msg, acao, citada),
                      segredo)
                     for nome, dest, citada, segredo in candidatas]
        if acao.get("tipo") == "botoes" and variantes:
            # EXPERIMENTAL: o servidor recusa (479) a resposta de botão com
            # o no <biz><buttons_response/> que a biblioteca poe sozinha; o
            # celular nao manda esse no. A biblioteca so o poe quando
            # reconhece a mensagem, e nao olha dentro do envelope de
            # "documento com legenda".
            from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
                FutureProofMessage)
            nome, dest, interna, segredo = variantes[0]
            variantes.insert(0, (
                "experimental: dentro de documento com legenda", dest,
                Message(documentWithCaptionMessage=FutureProofMessage(
                    message=interna)), segredo))
        return variantes

    def _mensagem_de_acao(self, msg, acao, citada=None):
        from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
            ButtonsResponseMessage, ContextInfo, InteractiveResponseMessage,
            ListResponseMessage, Message, TemplateButtonReplyMessage)
        rotulo = acao.get("rotulo", "")
        tipo = acao.get("tipo", "")
        remetente = msg.remetente or (
            "" if msg.conversa_id.endswith("@g.us") else msg.conversa_id)
        if citada is None:
            citada = Message(conversation=msg.texto or m.conteudo(msg))
        ctx = ContextInfo(stanzaID=msg.id, quotedMessage=citada)
        if remetente:
            ctx.participant = remetente
        if tipo == "modelo":
            return Message(templateButtonReplyMessage=TemplateButtonReplyMessage(
                selectedID=acao.get("id", ""), selectedDisplayText=rotulo,
                selectedIndex=int(acao.get("indice", 0)), contextInfo=ctx))
        if tipo == "botoes":
            return Message(buttonsResponseMessage=ButtonsResponseMessage(
                selectedButtonID=acao.get("id", ""),
                selectedDisplayText=rotulo,
                type=ButtonsResponseMessage.DISPLAY_TEXT, contextInfo=ctx))
        if tipo == "lista":
            resp = ListResponseMessage(
                title=rotulo, description=acao.get("descricao", ""),
                listType=ListResponseMessage.SINGLE_SELECT, contextInfo=ctx)
            resp.singleSelectReply.selectedRowID = acao.get("id", "")
            return Message(listResponseMessage=resp)
        if tipo == "fluxo":
            resp = InteractiveResponseMessage(contextInfo=ctx)
            resp.body.text = rotulo
            resp.nativeFlowResponseMessage.name = "quick_reply"
            resp.nativeFlowResponseMessage.paramsJSON = json.dumps(
                {"display_text": rotulo, "id": acao.get("id", "")},
                ensure_ascii=False)
            resp.nativeFlowResponseMessage.version = 3
            return Message(interactiveResponseMessage=resp)
        raise ValueError("ação desconhecida: %s" % tipo)

    def _enviar_variantes(self, variantes):
        """Tenta cada variante enquanto o servidor responder 479 (recusou o
        formato); qualquer outro erro, ou a ultima recusa, sobe."""
        for i, (nome, destino, mensagem, segredo) in enumerate(variantes):
            try:
                resp = self.cliente.send_message(
                    self._jid(destino), mensagem, add_msg_secret=segredo)
            except Exception as e:
                if i + 1 < len(variantes) and "479" in str(e):
                    log.info("resposta de botão recusada (479) na variante "
                             "'%s'; tentando a próxima", nome)
                    continue
                log.info("resposta de botão recusada na variante '%s'", nome)
                raise
            log.info("resposta de botão aceita na variante '%s'", nome)
            return resp

    def _enviar(self, conversa_id, texto, resposta_a, construir=None,
                descricao_acao=""):
        inicio = time.perf_counter()
        try:
            if not self._conectada:
                raise ConnectionError("sem conexão")
            if construir is None:
                resp = self.cliente.send_message(
                    self._jid(conversa_id),
                    self._mensagem_de_texto(conversa_id, texto, resposta_a))
            else:
                resp = self._enviar_variantes(construir())
        except Exception as e:
            log.warning("envio falhou: %s: %s%s", type(e).__name__,
                        str(e)[:300],
                        (" (resposta de botão %s)" % descricao_acao)
                        if descricao_acao else "", exc_info=True)
            motivo = "sem conexão" if isinstance(e, ConnectionError) else \
                "erro do WhatsApp (%s)" % type(e).__name__
            self.barramento.publicar(ev.EnvioFalhou(
                self.conta.id, conversa_id, texto, motivo,
                devolver_texto=construir is None))
            return
        log.info("texto enviado em %.2fs", time.perf_counter() - inicio)
        msg = m.Mensagem(self.conta.id, conversa_id, resp.ID, minha=True,
                         data=segundos(resp.Timestamp) or time.time(),
                         texto=texto, estado=m.ENVIADA, resposta_a=resposta_a)
        with self._trava:
            self._vistas.add(resp.ID)
            self._remetentes[resp.ID] = ("", texto)
            conv = self._conversas.get(conversa_id)
        if conv is None:
            # primeira mensagem de uma conversa nova (ex.: aberta por uma
            # mencao): passa a existir de verdade
            conv = self._conversa(conversa_id, self._jid(conversa_id), "",
                                  conversa_id.endswith("@g.us"), msg.data)
        with self._trava:
            conv.data = max(conv.data, msg.data)
        self.banco.salvar_conversas([conv])
        self.banco.salvar_mensagens([msg])
        self.barramento.publicar(ev.MensagemNova(msg, conv,
                                                 enviada_daqui=True))

    def marcar_como_lida(self, conversa_id):
        with self._trava:
            ao_vivo = self._nao_lidas.pop(conversa_id, [])
            conv = self._conversas.get(conversa_id)
            antes = conv.nao_lidas if conv is not None else 0
            if conv is not None:
                conv.nao_lidas = 0
        pendentes = {mid: jid for mid, jid in ao_vivo}
        if antes > len(pendentes):
            # nao lidas que vieram do historico: as ultimas recebidas, com o
            # remetente guardado no banco (nos grupos, quem enviou cada uma)
            individual = not conversa_id.endswith("@g.us")
            recebidas = [x for x in self.banco.mensagens(
                self.conta.id, conversa_id, min(antes * 3, 3000))
                if not x.minha][-antes:]
            for x in recebidas:
                rem = x.remetente or (conversa_id if individual else "")
                if x.id not in pendentes and rem:
                    pendentes[x.id] = _jid_obj(*jid_de_texto(rem))
        pendentes = list(pendentes.items())
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

    def _id_do_participante(self, jid):
        """Numero de quem recebeu ou leu (troca o endereco LID pelo numero
        quando o WhatsApp informa)."""
        return self._id_da_conversa(jid)

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
            self.banco.salvar_recibos(
                self.conta.id, cid, list(e.MessageIDs),
                self._id_do_participante(origem.Sender),
                {RECIBO_ENTREGUE: "entregue", RECIBO_LIDO: "lida",
                 RECIBO_OUVIDO: "ouvida"}[tipo], segundos(e.Timestamp))
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
            self.guardar_historico(e.Data)
            pct = min(100, int(e.Data.progress))
            self._progresso_historico = 0 if pct >= 100 else pct
            self.barramento.publicar(ev.ProgressoSincronia(
                self.conta.id, pct))
        except Exception:
            log.exception("erro ao ler o pacote de histórico")

    def guardar_historico(self, dados):
        """Guarda conversas, nomes e mensagens de um pacote de historico."""
        inicio = time.perf_counter()
        for x in dados.phoneNumberToLidMappings:
            if x.lidJID and x.pnJID:
                self._lid_para_numero[x.lidJID] = x.pnJID
        for x in dados.pushnames:
            if x.ID and x.pushname:
                self._apelidos[x.ID] = x.pushname
        dias = OPCOES_HISTORICO.get(self.historico,
                                    OPCOES_HISTORICO["recentes"])[1]
        limite = time.time() - dias * 86400 if dias else 0
        convs, msgs, fichas = [], [], []
        for c in dados.conversations:
            cid = self._normalizar_id(c.ID)
            if not cid or cid in IGNORAR_CONVERSAS or \
                    jid_de_texto(cid)[1] in IGNORAR_SERVIDORES:
                continue
            grupo = cid.endswith("@g.us")
            usuario, servidor = jid_de_texto(cid)
            nome = c.name or c.displayName or ""
            data = segundos(c.conversationTimestamp or c.lastMsgTimestamp)
            novas = []
            for h in c.messages:
                x, rem = converter_historico(
                    h.message, self.conta.id, cid,
                    self._apelidos.get(h.message.key.participant or
                                       h.message.participant, ""))
                if x is None or (limite and x.data < limite):
                    continue
                self._enriquecer_mencoes(x)
                if self.banco.depuracao:
                    self.banco.guardar_depuracao(
                        self.conta.id, cid, x.id, estrutura_bruta(h.message))
                novas.append(x)
                if x.tipo in armazem.BAIXAVEIS and \
                        h.message.HasField("message"):
                    ficha = ficha_de(desembrulhar(h.message.message))
                    if ficha:
                        fichas.append((self.conta.id, cid, x.id, ficha))
                if not x.minha:
                    self._remetentes[x.id] = (rem, x.texto)
            if novas:
                data = max(data, max(x.data for x in novas))
            with self._trava:
                conv = self._conversas.get(cid)
                if conv is None:
                    if not nome:
                        nome = "Grupo" if grupo else self._nome_por_texto(
                            usuario, servidor)
                    conv = m.Conversa(self.conta.id, cid, nome, self.servico,
                                      "grupo" if grupo else "privada",
                                      data=data)
                    self._conversas[cid] = conv
                elif nome and conv.nome in ("Grupo", "", SEM_NOME) or \
                        (nome and (conv.nome.startswith("+") or
                                   parece_codigo(conv.nome))):
                    conv.nome = nome
                conv.data = max(conv.data, data)
                if c.HasField("unreadCount"):
                    conv.nao_lidas = int(c.unreadCount)
            if not grupo:
                for x in novas:
                    if not x.minha and not x.autor:
                        x.autor = conv.nome
            if grupo and conv.nome == "Grupo" and \
                    cid not in self._nomes_grupo_pedidos:
                self._nomes_grupo_pedidos.add(cid)
                self._fila.put(lambda cid=cid, u=usuario, s=servidor:
                               self._buscar_nome_grupo(cid, _jid_obj(u, s)))
            convs.append(conv)
            msgs.extend(novas)
        so_telefone = [c.id for c in convs if c.tipo == "privada" and (
            c.nome.startswith("+") or c.nome == SEM_NOME)
            and c.id not in self._nomes_empresa_pedidos]
        if so_telefone:
            self._nomes_empresa_pedidos.update(so_telefone)
            self._fila.put(lambda ids=so_telefone:
                           self._consultar_empresas(ids))
        if convs:
            self.banco.salvar_conversas(convs)
        if msgs:
            self.banco.salvar_mensagens(msgs)
            if fichas:
                self.banco.salvar_fichas(fichas)
        log.info("histórico guardado: %d conversas e %d mensagens em %.2fs",
                 len(convs), len(msgs), time.perf_counter() - inicio)
        if convs:
            self._publicar_conversas()

    def _normalizar_id(self, texto):
        usuario, servidor = jid_de_texto(texto)
        cid = "%s@%s" % (usuario, servidor) if usuario else ""
        return self._lid_para_numero.get(cid, cid)

    def _nome_por_texto(self, usuario, servidor):
        if self.cliente is not None:
            try:
                return self._nome_contato(_jid_obj(usuario, servidor))
            except Exception:
                pass
        apelido = self._apelidos.get("%s@%s" % (usuario, servidor))
        if apelido:
            return apelido
        return "+" + usuario if servidor == "s.whatsapp.net" else SEM_NOME


DESCONECTADA_PELO_CELULAR = "desconectada pelo celular"


def caminho_sessao(pasta, conta_id):
    return os.path.join(pasta, conta_id + ".db")


def _jid_obj(usuario, servidor):
    from neonize.utils.jid import build_jid
    return build_jid(usuario, servidor)

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
import hashlib
import json
import logging
import os
import queue
import re
import threading
import time
import uuid

from telezapp import config
from telezapp.midia import armazem, envio
from telezapp.nucleo import chamadas as ch
from telezapp.nucleo import eventos as ev
from telezapp.nucleo import mencoes as nucleo_mencoes
from telezapp.nucleo import modelos as m
from telezapp.nucleo import previa_links
from telezapp.provedores.base import DownloadCancelado, ErroMidia, Provedor

log = logging.getLogger("telezapp.whatsapp")

EMBRULHOS = ("deviceSentMessage", "ephemeralMessage", "viewOnceMessage",
             "viewOnceMessageV2", "viewOnceMessageV2Extension",
             "documentWithCaptionMessage", "editedMessage",
             "associatedChildMessage", "commentMessage",
             # outros envelopes (FutureProofMessage) do WhatsApp
             "groupMentionedMessage", "spoilerMessage", "botInvokeMessage",
             "limitSharingMessage", "questionMessage", "questionReplyMessage",
             "botForwardedMessage", "groupStatusMessage")
# Campos sem conteudo para a pessoa (chaves, controle): a mensagem e ignorada
SO_CONTROLE = {"senderKeyDistributionMessage", "messageContextInfo",
               "protocolMessage", "reactionMessage", "pollUpdateMessage",
               "keepInChatMessage", "pinInChatMessage",
               # cabecalho de album (as fotos e videos chegam um a um),
               # aviso de grupo mencionado em status e aviso de historico
               "albumMessage", "groupStatusMentionMessage",
               "messageHistoryNotice",
               # edicao de um evento ou de uma enquete, cifrada com o segredo
               # da mensagem original: nao traz mensagem nova
               "secretEncryptedMessage"}
# Tipos de recibo do neonize (Receipt.Type)
RECIBO_ENTREGUE, RECIBO_LIDO, RECIBO_LIDO_POR_MIM, RECIBO_OUVIDO = 1, 4, 5, 6
RECIBO_OUVIDO_POR_MIM = 7     # toquei a voz ou audio no celular
MAX_GUARDADAS = 2000
# Sem o aviso de fim da sincronia, os avisos voltam depois deste tempo
TEMPO_MAX_SINCRONIA = 45
# espera (segundos) antes de cada nova tentativa de conexao; a ultima repete
ESPERAS_RECONEXAO = (3, 10, 30, 60, 120)
# Status de mensagem no historico (WebMessageInfo.Status)
HIST_ENTREGUE, HIST_LIDA, HIST_OUVIDA = 3, 4, 5
# Conversas que nao sao conversas para a pessoa
IGNORAR_CONVERSAS = ("status@broadcast",)
# Cada pessoa com status vira uma "conversa" de tipo status, `status:<jid>`,
# com os status dela como mensagens (somem 24 h depois, como no WhatsApp)
# Arquivos a partir deste tamanho sobem e descem direto do disco, com
# progresso (e sem carregar o arquivo na memoria), se a DLL sabe fazer isso
LIMITE_ENVIO_POR_ARQUIVO = 8 * 1024 * 1024
PREFIXO_STATUS = "status:"
RESPOSTA_A_STATUS = "status!"       # resposta_a de um envio que cita status
VALIDADE_STATUS = 24 * 3600 + 3600
INTERVALO_ARQUIVADAS = 60   # segundos entre conferencias das arquivadas
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


class ListaDeTransmissao(Exception):
    """Envio para uma lista de transmissao: a biblioteca nao suporta."""


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


def _prazo(ctx):
    """Segundos de prazo (mensagens temporarias) do contexto da mensagem; 0
    se nao ha."""
    try:
        return int(ctx.expiration or 0) if ctx is not None else 0
    except (TypeError, ValueError, AttributeError):
        return 0


def com_expiracao(mensagem, segundos):
    """A mensagem pronta para enviar, com o prazo das mensagens temporarias
    da conversa (o servidor nao poe sozinho: sem isso a mensagem nao some
    no celular). Texto simples vira extendedTextMessage."""
    segundos = int(segundos or 0)
    if segundos <= 0:
        return mensagem
    from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
        ContextInfo, ExtendedTextMessage)
    if mensagem.HasField("conversation"):
        texto = mensagem.conversation
        mensagem.ClearField("conversation")
        mensagem.extendedTextMessage.CopyFrom(ExtendedTextMessage(
            text=texto, contextInfo=ContextInfo(expiration=segundos)))
        return mensagem
    for nome in ("extendedTextMessage", "imageMessage", "videoMessage",
                 "audioMessage", "documentMessage", "stickerMessage",
                 "pollCreationMessage"):
        if mensagem.HasField(nome):
            getattr(mensagem, nome).contextInfo.expiration = segundos
            return mensagem
    return mensagem


def _valor_vcard(linha):
    return linha.split(":", 1)[1].strip() if ":" in linha else ""


def telefones_do_vcard(vcard):
    """[(telefone legivel, id do WhatsApp ou '')] dos TEL de um vCard. O
    parametro waid= diz o numero no WhatsApp; sem ele, so o texto."""
    achados = []
    for linha in (vcard or "").replace("\r", "").split("\n"):
        if not linha.upper().startswith(("TEL", "ITEM1.TEL", "ITEM2.TEL")):
            continue
        achou = re.search(r"waid=(\d+)", linha, re.I)
        texto = _valor_vcard(linha)
        digitos = achou.group(1) if achou else ""
        if digitos:
            achados.append(("+" + digitos, digitos + "@s.whatsapp.net"))
        elif texto:
            achados.append((texto, ""))
    return achados


def contatos_da_mensagem(interna, presentes=None):
    """[{'nome', 'telefone', 'id'}] dos cartoes de contato (um ou varios) da
    mensagem, um item por telefone. Entram nas pessoas da mensagem, e Enter
    numa delas abre a conversa."""
    cartoes = []
    try:
        if interna.HasField("contactMessage"):
            cartoes.append(interna.contactMessage)
        if interna.HasField("contactsArrayMessage"):
            cartoes += list(interna.contactsArrayMessage.contacts)
    except (ValueError, AttributeError):
        return []
    pessoas = []
    for c in cartoes:
        nome = c.displayName or ""
        tels = telefones_do_vcard(c.vcard) or [("", "")]
        for tel, id_ in tels[:3]:
            if nome or tel:
                pessoas.append({"nome": nome, "telefone": tel, "id": id_})
    return pessoas


RE_CONVITE_WHATSAPP = re.compile(
    r"chat\.whatsapp\.com/(?:invite/)?([A-Za-z0-9]{20,24})")


def entradas_de_grupo(interna, texto=""):
    """Botoes "Entrar no grupo": o convite que um administrador manda (para
    quem so aceita grupos de contatos) e os links chat.whatsapp.com do texto.
    Entram junto das acoes da mensagem, com tipo "entrar"."""
    entradas, vistos = [], set()
    try:
        if interna.HasField("groupInviteMessage"):
            x = interna.groupInviteMessage
            if x.inviteCode:
                vistos.add(x.inviteCode)
                nome = x.groupName or "sem nome"
                entradas.append({
                    "tipo": "entrar", "rotulo": "Entrar no grupo " + nome,
                    "codigo": x.inviteCode, "grupo": x.groupJID,
                    "expira": int(x.inviteExpiration or 0), "nome": nome})
    except (ValueError, AttributeError):
        pass
    for codigo in RE_CONVITE_WHATSAPP.findall(texto or ""):
        if codigo not in vistos:
            vistos.add(codigo)
            entradas.append({"tipo": "entrar", "rotulo": "Entrar no grupo "
                             "(link de convite)", "codigo": codigo})
    return entradas


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


_NOME_DE_ENUM = re.compile(r"^[A-Z][A-Z0-9_]{2,40}$")


def forma_sem_textos(x):
    """So o formato de uma estrutura (chaves e nomes de tipo em maiusculas):
    os textos viram '<texto N>', para o registro nao guardar o que foi
    escrito nas mensagens."""
    if isinstance(x, dict):
        return {k: forma_sem_textos(v) for k, v in x.items()}
    if isinstance(x, list):
        return [forma_sem_textos(v) for v in x[:5]]
    if isinstance(x, str):
        return x if _NOME_DE_ENUM.match(x) else "<texto %d>" % len(x)
    return "<n>" if isinstance(x, (int, float)) else x


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


def _texto_do_evento(x):
    """'evento: nome, inicio, local, descricao' (ou 'evento cancelado')."""
    partes = ["evento cancelado" if x.isCanceled else "evento: " + x.name]
    if x.isCanceled and x.name:
        partes.append(x.name)
    if x.startTime:
        partes.append("início " + time.strftime(
            "%d/%m/%Y %H:%M", time.localtime(x.startTime)))
    if x.endTime:
        partes.append("fim " + time.strftime(
            "%d/%m/%Y %H:%M", time.localtime(x.endTime)))
    local = x.location.name or x.location.address
    if local:
        partes.append("local: " + local)
    if x.joinLink:
        partes.append("link: " + x.joinLink)
    texto = ", ".join(partes)
    return texto + ("\n" + x.description if x.description else "")


def _texto_do_produto(x):
    """'produto: titulo, preco, descricao' de uma mensagem de catalogo."""
    p = x.product
    partes = ["produto: " + (p.title or "sem nome")]
    if p.priceAmount1000:
        partes.append("%s %.2f" % (p.currencyCode or "",
                                   p.priceAmount1000 / 1000))
    if p.URL:
        partes.append(p.URL)
    texto = ", ".join(p_.strip() for p_ in partes)
    return _partes_texto(texto, p.description, x.body)


def previa_do_whatsapp(interna):
    """A previa de link que quem enviou mandou junto do texto (titulo e
    descricao); o TeleZapp nao abre o link para gerar uma."""
    if not interna.HasField("extendedTextMessage"):
        return {}
    x = interna.extendedTextMessage
    return m.previa_de_link(x.matchedText, x.title,
                            x.description)


def enquete_do_whatsapp(interna):
    """Pergunta, opcoes e quantas dá para marcar de uma enquete criada ({} se
    a mensagem nao e uma enquete)."""
    presentes = set(campos(interna))
    for nome in ("pollCreationMessage", "pollCreationMessageV2",
                 "pollCreationMessageV3"):
        if nome in presentes:
            p = getattr(interna, nome)
            opcoes = [o.optionName for o in p.options]
            if not opcoes:
                return {}
            return {"pergunta": p.name, "opcoes": opcoes,
                    "maximo": int(p.selectableOptionsCount or 0) or
                    len(opcoes)}
    return {}


def consertar_decifrar_voto(cliente):
    """O neonize 0.5.2 esqueceu `DecryptPollVote` na lista das funcoes cujo
    retorno (um ponteiro de bytes do Go) vira `bytes`: sem isso, decifrar um
    voto levanta TypeError (\"expected bytes, LP_Bytes found\"). Poe o mesmo
    tratamento que as outras funcoes ja tem. Roda uma vez por biblioteca."""
    import ctypes
    go = next((getattr(cliente, a) for a in dir(cliente)
               if a.endswith("__client")), None)
    funcao = getattr(go, "DecryptPollVote", None)
    if funcao is None or getattr(funcao, "errcheck", None) is not None:
        return False

    def consumir(resultado, func, argumentos):
        if not resultado:
            return b""
        try:
            conteudo = resultado.contents
            if not conteudo.ptr or conteudo.size == 0:
                return b""
            return ctypes.string_at(conteudo.ptr, conteudo.size)
        finally:
            go.FreeBytesStruct(resultado)
    funcao.errcheck = consumir
    return True


def indices_do_voto(opcoes, selecionados):
    """Posicoes das opcoes escolhidas num voto: o WhatsApp manda o SHA-256 do
    texto de cada opcao marcada."""
    por_hash = {hashlib.sha256(o.encode()).digest(): i
                for i, o in enumerate(opcoes)}
    return sorted({por_hash[bytes(h)] for h in selecionados
                   if bytes(h) in por_hash})


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
        x = interna.contactMessage
        tels = [t for t, _ in telefones_do_vcard(x.vcard)]
        return m.OUTRO, ", ".join(p for p in (
            "contato: " + (x.displayName or "sem nome"),
            ", ".join(tels)) if p), 0, "", 0
    if "ptvMessage" in presentes:       # mensagem de video (bolinha)
        x = interna.ptvMessage
        return m.VIDEO, x.caption, x.seconds, "", x.fileLength
    if "contactsArrayMessage" in presentes:
        x = interna.contactsArrayMessage
        nomes = []
        for c in x.contacts:
            tels = [t for t, _ in telefones_do_vcard(c.vcard)]
            nome = ", ".join(p for p in (c.displayName, *tels[:1]) if p)
            if nome:
                nomes.append(nome)
        return m.OUTRO, "%d contatos: %s" % (
            len(x.contacts), ("; " if any(", " in n for n in nomes)
                              else ", ").join(nomes)) if nomes else \
            "%d contatos" % len(x.contacts), 0, "", 0
    if "eventMessage" in presentes:
        return m.OUTRO, _texto_do_evento(interna.eventMessage), 0, "", 0
    if "productMessage" in presentes:
        return m.OUTRO, _texto_do_produto(interna.productMessage), 0, "", 0
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
        log.info("mensagem interativa: %s", json.dumps(
            forma_sem_textos(forma), ensure_ascii=False))
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
    msg.expira = m.expira_em(msg.data, _prazo(ctx))
    interna_ = desembrulhar(evento.Message)
    acoes_ = acoes_do_whatsapp(interna_)
    m.guardar_extras(msg, botoes=botoes_do_whatsapp(interna_),
                     mencoes=mencoes_do_contexto(ctx) +
                     contatos_da_mensagem(interna_),
                     acoes=acoes_ + entradas_de_grupo(interna_, msg.texto),
                     original=original_com_acoes(interna_, acoes_),
                     previa=previa_do_whatsapp(interna_))
    enquete_ = enquete_do_whatsapp(interna_)
    if enquete_:
        m.atualizar_extras(msg, enquete=enquete_)
    return msg, msg.remetente


CAMPOS_MIDIA = ("imageMessage", "videoMessage", "audioMessage",
                "documentMessage", "stickerMessage")


def ficha_de(interna):
    """O minimo que o WhatsApp exige para baixar a midia depois (chaves e
    caminho), sem miniatura nem resposta citada. None se nao ha midia."""
    from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import Message
    try:
        if interna.HasField("ptvMessage"):
            # mensagem de video: e um VideoMessage, mas o whatsmeow so baixa
            # pelo campo videoMessage
            video = type(interna.ptvMessage)()
            video.CopyFrom(interna.ptvMessage)
            for campo in ("contextInfo", "JPEGThumbnail", "caption"):
                video.ClearField(campo)
            return Message(videoMessage=video).SerializeToString()
    except (ValueError, AttributeError):
        pass
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


# Colecoes do estado do aplicativo (arquivar, fixar, favoritar, contatos...)
COLECOES_DE_ESTADO = ("regular_high", "regular_low", "regular",
                      "critical_unblock_low", "critical_block")
COLECAO_DO_TIPO = {1: "critical_block", 2: "critical_unblock_low",
                   3: "regular_low", 4: "regular_high", 5: "regular"}


def fim_do_silencio(valor, ms=False):
    """Fim do silencio como o WhatsApp manda (segundos, ou milissegundos
    com ms=True; -1 ou um numero enorme = para sempre) -> 0.0 (com som),
    -1.0 (para sempre) ou o timestamp em segundos."""
    valor = int(valor or 0)
    if valor == 0:
        return 0.0
    if valor < 0 or valor >= 2 ** 62:
        return -1.0
    if ms:
        valor /= 1000
    return -1.0 if valor > 4e9 else float(valor)


def silencio_do_armazem(valor):
    """O mesmo para MutedUntil do armazem do whatsmeow (segundos; o tempo
    zero do Go vem negativo e quer dizer sem silencio)."""
    valor = float(valor or 0)
    if valor <= 0:
        return 0.0
    return -1.0 if valor > 4e9 else valor


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
                  HIST_OUVIDA: m.REPRODUZIDA}.get(int(wmi.status),
                                                  m.ENVIADA)
    forma = estrutura_interativa(desembrulhar(wmi.message))
    if forma:
        log.info("mensagem interativa: %s", json.dumps(
            forma_sem_textos(forma), ensure_ascii=False))
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
    msg.expira = m.expira_em(msg.data, _prazo(ctx))
    interna_ = desembrulhar(wmi.message)
    acoes_ = acoes_do_whatsapp(interna_)
    m.guardar_extras(msg, botoes=botoes_do_whatsapp(interna_),
                     mencoes=mencoes_do_contexto(ctx) +
                     contatos_da_mensagem(interna_),
                     acoes=acoes_ + entradas_de_grupo(interna_, msg.texto),
                     original=original_com_acoes(interna_, acoes_),
                     previa=previa_do_whatsapp(interna_))
    enquete_ = enquete_do_whatsapp(interna_)
    if enquete_:
        m.atualizar_extras(msg, enquete=enquete_)
    if wmi.starred:
        m.atualizar_extras(msg, favorita=True)
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
def _ultima_vez(valor):
    """Segundos desde 1970 de um "visto por ultimo", ou 0 se o valor nao
    serve (escondido costuma vir como a data zero do Go, negativa, e alguns
    avisos trazem milissegundos)."""
    try:
        v = float(valor or 0)
    except (TypeError, ValueError):
        return 0.0
    if v > 1e11:
        v /= 1000
    return v if 0 < v < time.time() + 86400 else 0.0


class ProvedorWhatsApp(Provedor):
    servico = "whatsapp"

    def __init__(self, conta, barramento, banco, pedir=None,
                 pasta_sessoes=None, fabrica_cliente=None,
                 historico="recentes"):
        super().__init__(conta, barramento, banco, pedir)
        self.historico = historico
        self._desligada = False     # desconectada pelo celular
        self._pareando = False      # QR ou codigo em andamento
        self._chamadas = {}         # id da chamada -> dados (so aviso)
        self._voz = None            # ChamadasWhatsApp, se as chamadas estao ligadas
        self._disponivel = False    # presenca "disponivel" enviada
        self._observadas = {}       # JID da conversa observada -> conversa_id
        self._presenca_cid = None   # a conversa aberta com presenca
        self._ouvinte = None
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
        self._mencoes_tentadas = {}  # jid sem nome -> quando procurei por ultimo
        self._escrita_conferida = {}   # grupo -> quando conferi se posso escrever
        self._grupos_lidos = {}    # grupo -> quando os participantes foram lidos
        self._arquivada_vista = {}  # conversa -> arquivada, como o celular disse
        self._ajustes_vistos = {}   # (conversa, campo) -> fixada/silenciada
        self._recuperando = set()   # colecoes do estado em recuperacao
        self._ultima_conferencia = 0.0
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
            self._preparar_chamadas()
            registros = {
                "ConnectedEv": self._ao_conectar,
                "PairStatusEv": self._ao_parear,
                "LoggedOutEv": self._ao_sair,
                "DisconnectedEv": self._ao_desconectar,
                "MessageEv": self._ao_receber,
                "UndecryptableMessageEv": self._ao_indecifravel,
                "MessageDeleteForMeEv": self._ao_apagar_mensagem,
                "MessageStarEv": self._ao_favoritar_mensagem,
                "GroupInfoEv": self._ao_grupo_mudou,
                "JoinedGroupEv": self._ao_entrou_no_grupo,
                "ReceiptEv": self._ao_recibo,
                "CallOfferEv": self._ao_chamada,
                "CallAcceptEv": self._ao_chamada_atendida,
                "CallTerminateEv": self._ao_chamada_encerrada,
                "PresenceEv": self._ao_presenca,
                "ChatPresenceEv": self._ao_digitando,
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
            # avisos de estado do celular (arquivar, trancar): so as versoes
            # novas do neonize os repassam; nas antigas vale a conferencia
            # periodica das arquivadas
            for nome, funcao in (("ChatArchiveEv", self._ao_arquivar),
                                 ("ChatLockEv", self._ao_trancar),
                                 ("ChatPinEv", self._ao_fixar),
                                 ("ChatMuteEv", self._ao_silenciar),
                                 ("ChatDeleteEv", self._ao_apagar_conversa),
                                 ("ChatMarkAsReadEv", self._ao_marcar_lida)):
                classe = getattr(nev, nome, None)
                if classe is not None:
                    self.cliente.event(classe)(funcao)
                    log.info("aviso %s ligado", nome)
            self.cliente.event.qr(self._ao_qr)
            if self._ouvinte is None:
                self._ouvir_falhas_do_pareamento()
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
                if self._conectada and time.time() - \
                        self._ultima_conferencia >= INTERVALO_ARQUIVADAS:
                    try:
                        self._conferir_arquivadas()
                    except Exception:
                        log.exception("erro ao conferir as arquivadas")
                continue
            try:
                tarefa()
            except Exception:
                log.exception("erro numa tarefa do WhatsApp")

    def parar(self):
        self._parar.set()
        if self._voz is not None:
            self._voz.parar()
        if self._ouvinte is not None:
            logging.getLogger("whatsmeow.Client").removeHandler(
                self._ouvinte)
            self._ouvinte = None
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
    def _ouvir_falhas_do_pareamento(self):
        """O whatsmeow so conta no registro que o pareamento falhou; este
        ouvinte transforma esses dois avisos num evento, para a janela
        recomecar a conexao (o QR e o codigo antigos deixam de valer)."""
        provedor = self

        class Ouvinte(logging.Handler):
            def emit(self, registro):
                if not provedor._pareando:
                    return
                texto = registro.getMessage()
                if "Failed to handle code pair notification" in texto:
                    metodo = "codigo"
                elif "Failed to pair device" in texto:
                    metodo = "qr"
                else:
                    return
                log.warning("pareamento recusado (%s)", metodo)
                provedor.barramento.publicar(
                    ev.PareamentoFalhou(provedor.conta.id, metodo))
        self._ouvinte = Ouvinte(logging.ERROR)
        logging.getLogger("whatsmeow.Client").addHandler(self._ouvinte)

    def _ao_qr(self, cliente, dados):
        if self._desligada:
            return   # so pareia de novo quando a pessoa pedir
        self._pareando = True
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
        self._pareando = True
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
        self._pareando = False
        self._disponivel = False
        self._fila.put(self._limpar_status_antigos)
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
        self._fila.put(self._conferir_estado)

    def _conferir_estado(self):
        """Confere as colecoes do estado do aplicativo. Se uma saiu de
        sincronia ("mismatching LTHash"), as mudancas feitas no celular
        deixam de chegar e as daqui sao recusadas. Roda fora da fila, porque
        pedir a copia ao celular pode levar um minuto."""
        threading.Thread(target=self._conferir_colecoes, daemon=True,
                         name="estado-do-app").start()

    def _conferir_colecoes(self):
        for nome in COLECOES_DE_ESTADO:
            self._reparar_colecao(nome, forcar=False)

    def _reparar_colecao(self, nome, forcar=True):
        """Sincroniza a colecao. Se nao bate: baixa tudo de novo e, se ainda
        assim nao bate (acontece quando o celular reescreve registros antigos
        e o whatsmeow nao consegue conferir), pede ao celular uma copia nova
        do estado. True se terminou bem."""
        fetch = getattr(self.cliente, "fetch_app_state", None)
        if fetch is None or not self._conectada:
            return False
        try:
            fetch(nome, full_sync=forcar)
            if forcar:
                log.info("estado %s baixado de novo", nome)
            return True
        except Exception as e:
            if "LTHash" not in str(e):
                log.warning("não consegui sincronizar o estado %s: %s",
                            nome, e)
                return False
            if not forcar:
                log.warning("estado %s fora de sincronia; baixando de novo",
                            nome)
                return self._reparar_colecao(nome, forcar=True)
            return self._recuperar_colecao(nome)

    ESPERA_DA_RECUPERACAO = 90      # segundos, no total
    PASSO_DA_RECUPERACAO = 5        # segundos entre as conferencias

    def _recuperar_colecao(self, nome):
        """Pede ao celular a copia do estado e espera ela chegar. O iPhone so
        responde com o WhatsApp aberto, entao, se nao vier, a pessoa e
        avisada."""
        with self._trava:
            if nome in self._recuperando:
                return False
            self._recuperando.add(nome)
        try:
            log.warning("estado %s: pedindo ao celular uma copia nova", nome)
            try:
                self.cliente.request_app_state_recovery(nome)
            except Exception as e:
                log.warning("não consegui pedir a cópia do estado: %s", e)
                return False
            fim = time.time() + self.ESPERA_DA_RECUPERACAO
            while time.time() < fim:
                if self._parar.wait(self.PASSO_DA_RECUPERACAO):
                    return False
                try:
                    self.cliente.fetch_app_state(nome)
                    log.info("estado %s recuperado com a cópia do celular",
                             nome)
                    return True
                except Exception as e:
                    if "LTHash" not in str(e):
                        log.warning("estado %s: %s", nome, e)
                        return False
            log.warning("o celular não respondeu ao pedido do estado %s",
                        nome)
            self._avisar(
                "Para as mudanças do celular (favoritar, apagar, silenciar) "
                "voltarem a chegar, abra o WhatsApp no celular e deixe-o "
                "aberto por um minuto; o TeleZapp tenta de novo ao "
                "reconectar.", False)
            return False
        finally:
            with self._trava:
                self._recuperando.discard(nome)

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
        # grupos renomeados com o app fechado: o WhatsApp so avisa na hora
        self._fila.put(self._atualizar_nomes_de_grupos)

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
            for c in self._conversas.values():
                if c.tipo == "canal":
                    c.somente_leitura = True     # canais: so quem administra
            lista = sorted(self._conversas.values(), key=lambda c: -c.data)
        self.barramento.publicar(ev.ConversasAtualizadas(self.conta.id,
                                                         lista))

    def atualizar_conversas(self):
        self._publicar_conversas()
        self._fila.put(self._conferir_arquivadas)
        self._fila.put(self._atualizar_nomes_de_grupos)

    def _ajustes_no_celular(self, conversa_id):
        """Arquivada, fixada e silenciada como o celular deixou a conversa
        (armazem local do whatsmeow, que os avisos do celular mantem em
        dia); None se o armazem nao conhece a conversa."""
        usuario, servidor = jid_de_texto(conversa_id)
        jid = _jid_obj(usuario, servidor)
        candidatos = [jid]
        if servidor == "s.whatsapp.net":
            try:                      # o armazem pode guardar sob o LID
                lid = self.cliente.get_lid_from_pn(jid)
                if lid.User:
                    candidatos.append(lid)
            except Exception:
                pass
        for alvo in candidatos:
            try:
                dados = self.cliente.chat_settings.get_chat_settings(alvo)
            except Exception:
                continue
            if dados.Found:
                return dados
        return None

    PODE_TEMPORARIAS = True

    def definir_temporaria(self, conversa_id, segundos):
        self._fila.put(lambda: self._definir_temporaria(conversa_id,
                                                        int(segundos or 0)))

    def _definir_temporaria(self, conversa_id, segundos):
        try:
            if not self._conectada or self.cliente is None:
                raise ConnectionError("sem conexão")
            jid = self._jid(conversa_id)
            dados = jid.SerializeToString()
            # o neonize converte o prazo de um jeito que nao serve (o Go o
            # le em nanossegundos e a hora da mudanca em milissegundos);
            # chama a DLL direto
            erro = self.cliente._NewClient__client.SetDisappearingTimer(
                self.cliente.uuid, dados, len(dados),
                segundos * 1_000_000_000, int(time.time() * 1000))
            erro = erro.decode() if isinstance(erro, bytes) else (erro or "")
            if erro:
                raise RuntimeError(erro)
        except Exception as e:
            log.warning("mensagens temporárias: falhou: %s: %s",
                        type(e).__name__, str(e)[:200])
            self._avisar("Não consegui mudar as mensagens temporárias: %s" % (
                "sem conexão" if isinstance(e, ConnectionError)
                else str(e)[:120] or type(e).__name__), True)
            return
        self._temporaria_mudou(conversa_id, segundos, True)

    def _temporaria_mudou(self, conversa_id, segundos, minha):
        """O prazo das mensagens temporarias da conversa mudou (aqui ou em
        outro aparelho)."""
        with self._trava:
            conv = self._conversas.get(conversa_id)
            if conv is None or conv.temporaria_s == segundos:
                return
            conv.temporaria_s = segundos
        log.info("mensagens temporárias de uma conversa: %s",
                 m.texto_periodo(segundos, "whatsapp"))
        self.banco.salvar_conversas([conv])
        self._publicar_conversas()
        self._avisar("%s as mensagens temporárias de %s%s." % (
            "Você mudou" if minha else "Mudaram", conv.nome,
            ": " + m.texto_periodo(segundos, "whatsapp") if segundos else
            ": desligadas"))

    def _marcar_conversa(self, evento, campo, valor):
        """Poe uma marca (arquivada, trancada) numa conversa que o celular
        acabou de mudar; so conversas que o TeleZapp ja conhece."""
        cid = self._id_da_conversa(evento.JID)
        with self._trava:
            conv = self._conversas.get(cid)
            if conv is None or getattr(conv, campo) == valor:
                return False
            setattr(conv, campo, valor)
        log.info("conversa %s no celular: %s=%s", "mudou", campo, valor)
        self.banco.salvar_conversas([conv])
        self._publicar_conversas()
        return True

    def _ao_arquivar(self, cliente, evento):
        try:
            valor = bool(evento.Action.archived)
            with self._trava:
                self._arquivada_vista[self._id_da_conversa(evento.JID)] = valor
            self._marcar_conversa(evento, "arquivada", valor)
        except Exception:
            log.exception("erro ao tratar o aviso de arquivar")

    def _ao_fixar(self, cliente, evento):
        try:
            self._marcar_conversa(evento, "fixada",
                                  bool(evento.Action.pinned))
        except Exception:
            log.exception("erro ao tratar o aviso de fixar")

    def _ao_silenciar(self, cliente, evento):
        try:
            a = evento.Action
            if not a.muted:
                ate = 0.0
            elif a.HasField("muteEndTimestamp"):
                ate = fim_do_silencio(a.muteEndTimestamp, ms=True)
            else:
                ate = -1.0
            self._marcar_conversa(evento, "silenciada_ate", ate)
        except Exception:
            log.exception("erro ao tratar o aviso de silenciar")

    def _ao_marcar_lida(self, cliente, evento):
        """Conversa lida no celular (ou em outro aparelho), inclusive o que o
        celular fez com o TeleZapp fechado e chega na sincronia ao conectar:
        zera as nao lidas, a menos que ja haja mensagem mais nova que a
        marca."""
        try:
            a = evento.Action
            if not a.read:
                return
            cid = self._id_da_conversa(evento.JID)
            ate = segundos(a.messageRange.lastMessageTimestamp)                 if a.HasField("messageRange") else 0
            with self._trava:
                self._nao_lidas.pop(cid, None)
                conv = self._conversas.get(cid)
                if conv is None or conv.nao_lidas == 0:
                    return
                if ate and conv.data > ate + 5:
                    log.info("conversa marcada como lida no celular, mas há "
                             "mensagem mais nova: mantida como não lida")
                    return
                conv.nao_lidas = 0
            log.info("conversa marcada como lida no celular")
            self.banco.atualizar_conversa(self.conta.id, cid, nao_lidas=0)
            self._publicar_conversas()
        except Exception:
            log.exception("erro ao tratar o aviso de conversa lida")

    def _ao_trancar(self, cliente, evento):
        try:
            self._marcar_conversa(evento, "trancada",
                                  bool(evento.Action.locked))
        except Exception:
            log.exception("erro ao tratar o aviso de trancar")

    def _enviar_estado(self, indice, versao, tipo, valor, conversa_id,
                       extra=()):
        """Manda um aviso de estado (fixar, silenciar...) ao WhatsApp, como
        o celular faz para os outros aparelhos. True se foi aceito."""
        if self.cliente is None or not self._conectada or \
                "@" not in (conversa_id or ""):
            return False
        try:
            from neonize.proto.Neonize_pb2 import MutationInfo, PatchInfo
            usuario, servidor = jid_de_texto(conversa_id)
            patch = PatchInfo(
                Timestamp=time.time_ns(), Type=tipo,
                Mutations=[MutationInfo(
                    Index=[indice, "%s@%s" % (usuario, servidor),
                           *extra],
                    Version=versao, Value=valor)])
            try:
                self.cliente.send_app_state(patch)
            except Exception as e:
                # colecao fora de sincronia: baixa de novo e tenta mais uma
                if "LTHash" not in str(e) and "409" not in str(e):
                    raise
                if not self._reparar_colecao(COLECAO_DO_TIPO.get(
                        int(tipo), "regular_high")):
                    raise
                self.cliente.send_app_state(patch)
            return True
        except Exception:
            log.exception("não consegui avisar o WhatsApp (%s)", indice)
            return False

    def fixar_conversa(self, conversa_id, fixar):
        from neonize.proto.Neonize_pb2 import PatchInfo
        from neonize.proto.waSyncAction.WAWebProtobufSyncAction_pb2 import (
            PinAction, SyncActionValue)
        return self._enviar_estado(
            "pin_v1", 5, PatchInfo.REGULAR_LOW,
            SyncActionValue(pinAction=PinAction(pinned=bool(fixar))),
            conversa_id)

    def silenciar_conversa(self, conversa_id, silenciar, segundos=0):
        from neonize.proto.Neonize_pb2 import PatchInfo
        from neonize.proto.waSyncAction.WAWebProtobufSyncAction_pb2 import (
            MuteAction, SyncActionValue)
        acao = MuteAction(muted=bool(silenciar))
        if silenciar:
            acao.muteEndTimestamp = int((time.time() + segundos) * 1000) \
                if segundos else -1
        return self._enviar_estado(
            "mute", 2, PatchInfo.REGULAR_HIGH,
            SyncActionValue(muteAction=acao), conversa_id)

    APAGA_NA_CONTA = True

    def apagar_conversa(self, conversa_id, ultima=None):
        """Apaga a conversa no celular, com as midias: manda o aviso de estado
        `deleteChat` (o mesmo que o celular manda aos outros aparelhos). Devolve True
        se o WhatsApp aceitou."""
        if self.cliente is None or not self._conectada or \
                "@" not in (conversa_id or ""):
            return False
        try:
            from neonize.proto.Neonize_pb2 import MutationInfo, PatchInfo
            from neonize.proto.waCommon.WACommon_pb2 import MessageKey
            from neonize.proto.waSyncAction.WAWebProtobufSyncAction_pb2 import (
                DeleteChatAction, SyncActionMessage, SyncActionMessageRange,
                SyncActionValue)
            usuario, servidor = jid_de_texto(conversa_id)
            jid = "%s@%s" % (usuario, servidor)
            agora = int(time.time())
            quando = int(ultima.data) if ultima is not None and \
                ultima.data else agora
            # limite da faixa = agora, para cobrir ate a ultima mensagem (com
            # o horario dela a conversa continuava no celular, com ela)
            faixa = SyncActionMessageRange(
                lastMessageTimestamp=max(agora, quando))
            if ultima is not None and not ultima.id.startswith("local-"):
                chave = MessageKey(remoteJID=jid, fromMe=bool(ultima.minha),
                                   ID=ultima.id)
                if servidor == "g.us" and not ultima.minha and \
                        ultima.remetente:
                    chave.participant = ultima.remetente
                faixa.messages.append(SyncActionMessage(
                    key=chave, timestamp=quando))
            patch = PatchInfo(
                Timestamp=time.time_ns(), Type=PatchInfo.REGULAR_HIGH,
                Mutations=[MutationInfo(
                    Index=["deleteChat", jid, "1"], Version=6,
                    Value=SyncActionValue(
                        deleteChatAction=DeleteChatAction(
                            messageRange=faixa)))])
            self.cliente.send_app_state(patch)
            with self._trava:
                self._conversas.pop(conversa_id, None)
            log.info("conversa apagada no celular a pedido do TeleZapp")
            return True
        except Exception:
            log.exception("não consegui apagar a conversa no celular")
            return False

    # ----------------------------------------- detalhes da conversa
    def _eu(self, info):
        """O participante do grupo que e esta conta, ou None."""
        eu = self.cliente.get_me()
        meus = {eu.JID.User, eu.LID.User} - {""}
        for p in info.Participants:
            if meus & {p.JID.User, p.LID.User, p.PhoneNumber.User}:
                return p
        return None

    def _id_da_pessoa(self, p):
        """O id da conversa particular com o participante (o telefone, e nao
        o endereco LID, quando o WhatsApp informa)."""
        return jid_texto(p.PhoneNumber) if p.PhoneNumber.User else \
            jid_texto(self._numero_do_jid(p.JID))

    def dados_do_contato(self, conversa_id):
        dados = {}
        if self.cliente is None or not self._conectada or \
                "@" not in conversa_id:
            return dados
        usuario, servidor = jid_de_texto(conversa_id)
        jid = self._numero_do_jid(_jid_obj(usuario, servidor))
        if jid.Server == "s.whatsapp.net" and jid.User:
            dados["telefone"] = "+" + jid.User
        try:
            apelido = self._apelidos.get(jid_texto(jid), "")
            info = self.cliente.contact.get_contact(jid)
            apelido = info.PushName or apelido
            if apelido and not parece_codigo(apelido):
                dados["nome_no_perfil"] = apelido
        except Exception:
            pass
        try:
            for u in self.cliente.get_user_info(jid):
                if u.UserInfo.Status:
                    dados["recado"] = u.UserInfo.Status
                break
        except Exception:
            log.info("sem o recado do contato")
        return dados

    def detalhes_do_grupo(self, conversa_id):
        if self.cliente is None or not self._conectada or \
                not conversa_id.endswith("@g.us"):
            return None
        usuario, servidor = jid_de_texto(conversa_id)
        info = self.cliente.get_group_info(_jid_obj(usuario, servidor))
        eu = self._eu(info)
        meus = {x.User for x in (self.cliente.get_me().JID,
                                 self.cliente.get_me().LID)} - {""}
        participantes = []
        for p in info.Participants:
            pessoa = self._numero_do_jid(p.JID) if not p.PhoneNumber.User \
                else p.PhoneNumber
            tel = "+" + pessoa.User if pessoa.Server == "s.whatsapp.net" \
                and pessoa.User else ""
            nome = self._nome_contato(pessoa, p.DisplayName)
            if tel and nome == tel:
                nome = p.DisplayName or tel
            participantes.append({
                "id": self._id_da_pessoa(p), "nome": nome, "telefone": tel,
                "admin": bool(p.IsAdmin or p.IsSuperAdmin),
                "dono": bool(p.IsSuperAdmin),
                "eu": bool(meus & {p.JID.User, p.LID.User,
                                   p.PhoneNumber.User})})
        participantes.sort(key=lambda x: (not x["dono"], not x["admin"],
                                          x["nome"].lower()))
        dono = ""
        if info.OwnerPN.User:
            dono = self._nome_contato(info.OwnerPN)
        subgrupos = []
        if info.GroupParent.IsParent:
            try:
                for alvo in self.cliente.get_sub_groups(
                        _jid_obj(usuario, servidor)):
                    subgrupos.append((jid_texto(alvo.JID),
                                      alvo.GroupName.Name or "Grupo"))
            except Exception:
                log.info("sem a lista de grupos da comunidade")
        return {"subgrupos": subgrupos,
            "nome": info.GroupName.Name, "descricao": info.GroupTopic.Topic,
            "id_descricao": info.GroupTopic.TopicID,
            "criado_em": float(info.GroupCreated or 0), "dono": dono,
            "anuncio": bool(info.GroupAnnounce.IsAnnounce),
            "trancado": bool(info.GroupLocked.isLocked),
            "comunidade": bool(info.GroupParent.IsParent),
            "da_comunidade": bool(info.GroupLinkedParent.LinkedParentJID.User),
            "sou_admin": bool(eu is not None and (eu.IsAdmin or
                                                  eu.IsSuperAdmin)),
            "participantes": participantes}

    def detalhes_do_canal(self, conversa_id):
        if self.cliente is None or not self._conectada or \
                not conversa_id.endswith("@newsletter"):
            return None
        usuario, servidor = jid_de_texto(conversa_id)
        info = self.cliente.get_newsletter_info(_jid_obj(usuario, servidor))
        meta, eu = info.ThreadMeta, info.ViewerMeta
        papel = {1: "seguidor", 2: "visitante", 3: "administrador",
                 4: "dono"}.get(int(eu.Role), "")
        codigo = meta.InviteCode
        return {
            "nome": meta.Name.Text, "descricao": meta.Description.Text,
            "seguidores": int(meta.SubscriberCount),
            "verificado": int(meta.VerificationState) == 1,
            "silenciado": int(eu.Mute) == 1, "papel": papel,
            "criado_em": float(meta.CreationTime or 0),
            "link": ("https://whatsapp.com/channel/" + codigo) if codigo
            else "",
            "sou_admin": papel in ("administrador", "dono")}

    def grupos_em_comum(self, pessoa_id):
        if self.cliente is None or not self._conectada:
            return []
        usuario = jid_de_texto(pessoa_id)[0]
        alvo = self._numero_do_jid(_jid_obj(*jid_de_texto(pessoa_id)))
        procurados = {usuario, alvo.User} - {""}
        achados = []
        for g in self.cliente.get_joined_groups():
            for p in g.Participants:
                if procurados & {p.JID.User, p.LID.User, p.PhoneNumber.User}:
                    achados.append((jid_texto(g.JID), g.GroupName.Name
                                    or "Grupo"))
                    break
        return sorted(achados, key=lambda g: g[1].lower())

    def _jid_do_convite(self, msg, acao):
        grupo = acao.get("grupo") or ""
        convidou = msg.remetente or msg.conversa_id
        return (_jid_obj(*jid_de_texto(grupo)) if grupo else None,
                _jid_obj(*jid_de_texto(convidou)) if convidou else None)

    def previa_do_convite(self, msg, acao):
        if self.cliente is None or not self._conectada:
            return {"erro": "Sem conexão com o WhatsApp."}
        try:
            grupo, convidou = self._jid_do_convite(msg, acao)
            if grupo is not None and convidou is not None:
                info = self.cliente.get_group_info_from_invite(
                    grupo, convidou, acao["codigo"],
                    int(acao.get("expira") or 0))
            else:
                info = self.cliente.get_group_info_from_link(acao["codigo"])
        except Exception as e:
            log.info("prévia do convite falhou: %s", type(e).__name__)
            return {"erro": "O convite não vale mais ou foi cancelado."}
        return {"nome": info.GroupName.Name or acao.get("nome") or "grupo",
                "membros": len(info.Participants),
                "descricao": info.GroupTopic.Topic, "ja_participa": bool(
                    info.Participants and self._eu(info) is not None)}

    def entrar_no_grupo(self, msg, acao):
        if self.cliente is None or not self._conectada:
            return False, "Sem conexão com o WhatsApp."
        try:
            grupo, convidou = self._jid_do_convite(msg, acao)
            if grupo is not None and convidou is not None:
                self.cliente.join_group_with_invite(
                    grupo, convidou, acao["codigo"],
                    int(acao.get("expira") or 0))
            else:
                self.cliente.join_group_with_link(acao["codigo"])
        except Exception as e:
            texto = str(e).lower()
            log.warning("entrar no grupo falhou: %s", type(e).__name__)
            if "already" in texto or "participant" in texto:
                return False, "Você já está neste grupo."
            if "approval" in texto or "request" in texto:
                return True, ("O pedido para entrar foi enviado. Um "
                              "administrador precisa aprovar.")
            return False, ("O WhatsApp não deixou entrar (o convite pode "
                           "ter expirado ou o grupo estar cheio).")
        self._fila.put(self._atualizar_nomes_de_grupos)
        return True, "Você entrou no grupo."

    def administrar_grupo(self, conversa_id, acao, valor=None):
        if self.cliente is None or not self._conectada:
            return False, "Sem conexão com o WhatsApp."
        from neonize.utils.enum import ParticipantChange
        usuario, servidor = jid_de_texto(conversa_id)
        jid = _jid_obj(usuario, servidor)
        try:
            if acao == "nome":
                self.cliente.set_group_name(jid, valor)
                self._renomear_grupo(conversa_id, valor)
                return True, "Nome do grupo mudado."
            if acao == "descricao":
                info = self.cliente.get_group_info(jid)
                self.cliente.set_group_topic(
                    jid, info.GroupTopic.TopicID, uuid.uuid4().hex.upper(),
                    valor)
                return True, "Descrição do grupo mudada."
            if acao == "anuncio":
                self.cliente.set_group_announce(jid, bool(valor))
                self._marcar_escrita_apos_mudanca(conversa_id)
                return True, ("Agora só administradores enviam mensagens."
                              if valor else "Agora todos enviam mensagens.")
            if acao == "trancado":
                self.cliente.set_group_locked(jid, bool(valor))
                return True, ("Agora só administradores editam o grupo."
                              if valor else "Agora todos editam o grupo.")
            if acao in ("adicionar", "remover", "promover", "rebaixar"):
                if acao == "adicionar":
                    digitos = "".join(c for c in str(valor) if c.isdigit())
                    if len(digitos) < 8:
                        return False, "Digite o número com DDD e país."
                    alvo = _jid_obj(digitos, "s.whatsapp.net")
                else:
                    alvo = _jid_obj(*jid_de_texto(valor))
                mudanca = {"adicionar": ParticipantChange.ADD,
                           "remover": ParticipantChange.REMOVE,
                           "promover": ParticipantChange.PROMOTE,
                           "rebaixar": ParticipantChange.DEMOTE}[acao]
                resp = self.cliente.update_group_participants(
                    jid, [alvo], mudanca)
                for r in resp:
                    if r.Error:
                        return False, ("O WhatsApp recusou (erro %s)." %
                                       r.Error)
                return True, {"adicionar": "Participante adicionado.",
                              "remover": "Participante removido.",
                              "promover": "Agora é administrador.",
                              "rebaixar": "Deixou de ser administrador."
                              }[acao]
            if acao in ("link", "revogar_link"):
                return True, self.cliente.get_group_invite_link(
                    jid, acao == "revogar_link")
            if acao == "sair":
                self.cliente.leave_group(jid)
                return True, "Você saiu do grupo."
        except Exception as e:
            log.warning("administrar grupo (%s) falhou: %s", acao,
                        type(e).__name__, exc_info=True)
            return False, "O WhatsApp não aceitou (%s)." % type(e).__name__
        return False, "Ação desconhecida."

    def _marcar_escrita_apos_mudanca(self, cid):
        self._fila.put(lambda: self._conferir_escrita(cid, True))

    def administrar_canal(self, conversa_id, acao, valor=None):
        if self.cliente is None or not self._conectada:
            return False, "Sem conexão com o WhatsApp."
        usuario, servidor = jid_de_texto(conversa_id)
        jid = _jid_obj(usuario, servidor)
        try:
            if acao == "silenciar":
                self.cliente.newsletter_toggle_mute(jid, bool(valor))
                return True, ("Canal silenciado." if valor
                              else "Som do canal reativado.")
            if acao == "deixar_de_seguir":
                self.cliente.unfollow_newsletter(jid)
                return True, "Você deixou de seguir o canal."
        except Exception as e:
            log.warning("administrar canal (%s) falhou: %s", acao,
                        type(e).__name__, exc_info=True)
            return False, "O WhatsApp não aceitou (%s)." % type(e).__name__
        return False, "Ação desconhecida."

    CRIA = ("grupo", "canal", "comunidade")

    def criar_conversa(self, tipo, nome, descricao="", participantes=(),
                       topicos=False):
        if self.cliente is None or not self._conectada:
            return False, "Sem conexão com o WhatsApp.", ""
        try:
            if tipo == "canal":
                meta = self.cliente.create_newsletter(nome, descricao, b"")
                cid, conv_tipo = jid_texto(meta.ID), "canal"
            else:
                cid = self._criar_grupo(tipo, nome, descricao, participantes)
                conv_tipo = "grupo"
        except Exception as e:
            log.warning("criar %s falhou: %s: %s", tipo, type(e).__name__,
                        str(e)[:200])
            return False, ("O WhatsApp não deixou criar (%s)." %
                           (str(e)[:120] or type(e).__name__)), ""
        with self._trava:
            conv = self._conversas.get(cid)
            if conv is None:
                conv = m.Conversa(self.conta.id, cid, nome, self.servico,
                                  conv_tipo, data=time.time())
                self._conversas[cid] = conv
        self.banco.salvar_conversas([conv])
        self._publicar_conversas()
        log.info("%s criado pelo TeleZapp", tipo)
        return True, "", cid

    def _criar_grupo(self, tipo, nome, descricao, participantes):
        """Cria o grupo (ou a comunidade) e devolve o endereco dele."""
        from neonize.proto.Neonize_pb2 import GroupParent
        alvos = []
        for texto in participantes:
            tel = m.normalizar_telefone(str(texto))    # sem + no Brasil: +55
            if tel:
                alvos.append(_jid_obj(tel.lstrip("+"), "s.whatsapp.net"))
        pai = GroupParent(
            IsParent=True,
            DefaultMembershipApprovalMode="request_required") \
            if tipo == "comunidade" else None
        info = self.cliente.create_group(
            nome, [] if pai else alvos, group_parent=pai)
        jid = info.JID
        if descricao:
            try:
                self.cliente.set_group_topic(
                    jid, "", uuid.uuid4().hex.upper(), descricao)
            except Exception:
                log.info("grupo criado, mas sem a descrição")
        return jid_texto(jid)

    JANELA_EDICAO = 15 * 60       # o WhatsApp deixa editar por 15 minutos

    def editar_mensagem(self, msg, texto):
        self._fila.put(lambda: self._editar(msg, texto))

    def _editar(self, msg, texto):
        try:
            if self.cliente is None or not self._conectada:
                raise ConnectionError("sem conexão")
            nova = self._mensagem_de_texto(msg.conversa_id, texto,
                                           msg.resposta_a)
            self.cliente.edit_message(self._jid(msg.conversa_id), msg.id,
                                      nova)
        except Exception as e:
            log.warning("edição falhou: %s: %s", type(e).__name__,
                        str(e)[:200])
            self._avisar("Não consegui editar a mensagem (%s)." % (
                "sem conexão" if isinstance(e, ConnectionError)
                else "o WhatsApp recusou, talvez já tenham passado 15 "
                "minutos"), False)
            return

        def aplicar(x):
            x.texto = texto
            m.atualizar_extras(x, editada=True)
        self._alterar(msg.conversa_id, msg.id, aplicar, "editada")
        log.info("mensagem editada pelo TeleZapp")

    SAI_DE_GRUPO = True

    def sair_do_grupo(self, conversa_id):
        """Sai do grupo (a conta deixa de ser participante). Bloqueia ate o
        WhatsApp responder: chamar fora da thread da interface."""
        if self.cliente is None or not self._conectada:
            return False
        usuario, servidor = jid_de_texto(conversa_id)
        if servidor != "g.us":
            return False
        try:
            self.cliente.leave_group(_jid_obj(usuario, servidor))
            log.info("saiu do grupo a pedido do TeleZapp")
            return True
        except Exception:
            log.exception("não consegui sair do grupo")
            return False

    def _ao_apagar_mensagem(self, cliente, evento):
        """Mensagem apagada so para mim no celular: a interface tira daqui."""
        try:
            if evento.FromFullSync:
                return      # exclusao antiga, de antes: nao apaga daqui
            cid = self._id_da_conversa(evento.ChatJID)
            log.info("mensagem apagada no celular")
            self.barramento.publicar(ev.MensagemApagadaNoCelular(
                self.conta.id, cid, evento.MessageID))
        except Exception:
            log.exception("erro ao tratar o aviso de apagar mensagem")

    ACEITA_CONTATOS = True

    def pessoa_da_mensagem(self, mensagem):
        """Quem enviou a mensagem (num grupo, o remetente; o endereco LID
        vira o telefone quando o WhatsApp o informa)."""
        if mensagem.minha or not mensagem.remetente or \
                self.cliente is None:
            return None
        usuario, servidor = jid_de_texto(mensagem.remetente)
        alvo = self._numero_do_jid(_jid_obj(usuario, servidor))
        if alvo.Server != "s.whatsapp.net" or not alvo.User:
            return None
        id_ = jid_texto(alvo)
        return id_, "+" + alvo.User, [id_, mensagem.remetente,
                                      "%s@%s" % (usuario, servidor)]

    def salvar_contato(self, conversa_id, nome, telefone=""):
        """O nome dado no TeleZapp passa a valer no WhatsApp da conta: manda
        o aviso de estado `contact` (o do WhatsApp Web ao adicionar um
        contato), com `saveOnPrimaryAddressbook` desligado, entao o celular
        reconhece a pessoa sem gravar nada na agenda do aparelho. True se o
        WhatsApp aceitou."""
        nome = (nome or "").strip()
        if not nome or conversa_id.endswith("@g.us") or "@" not in conversa_id:
            return False
        from neonize.proto.Neonize_pb2 import PatchInfo
        from neonize.proto.waSyncAction.WAWebProtobufSyncAction_pb2 import (
            ContactAction, SyncActionValue)
        usuario, servidor = jid_de_texto(conversa_id)
        if servidor != "s.whatsapp.net":
            return False
        jid = "%s@%s" % (usuario, servidor)
        acao = ContactAction(fullName=nome, firstName=nome.split()[0],
                             saveOnPrimaryAddressbook=False, pnJID=jid)
        try:
            lid = self.cliente.get_lid_from_pn(_jid_obj(usuario, servidor))
            if lid.User:
                acao.lidJID = "%s@%s" % (lid.User, lid.Server)
        except Exception:
            pass
        return self._enviar_estado(
            "contact", 2, PatchInfo.CRITICAL_UNBLOCK_LOW,
            SyncActionValue(contactAction=acao), conversa_id)

    FAVORITA_NA_CONTA = True

    def _ao_favoritar_mensagem(self, cliente, evento):
        """Mensagem favoritada (ou nao) no celular."""
        try:
            favorita = bool(evento.Action.starred)
            self._alterar(
                self._id_da_conversa(evento.ChatJID), evento.MessageID,
                lambda x: m.atualizar_extras(x, favorita=favorita),
                "favorita")
        except Exception:
            log.exception("erro ao tratar o aviso de favoritar")

    def favoritar_mensagem(self, mensagem, favoritar):
        """Avisa o WhatsApp (aviso de estado `star`, o do celular) que a
        mensagem foi favoritada ou desfavoritada. True se foi aceito."""
        from neonize.proto.Neonize_pb2 import PatchInfo
        from neonize.proto.waSyncAction.WAWebProtobufSyncAction_pb2 import (
            StarAction, SyncActionValue)
        remetente = "0"
        if not mensagem.minha and mensagem.conversa_id.endswith("@g.us") \
                and mensagem.remetente:
            remetente = mensagem.remetente
        return self._enviar_estado(
            "star", 2, PatchInfo.REGULAR_HIGH,
            SyncActionValue(starAction=StarAction(starred=bool(favoritar))),
            mensagem.conversa_id,
            extra=(mensagem.id, "1" if mensagem.minha else "0", remetente))

    def apagar_mensagem(self, mensagem, para_todos=False):
        """Apaga a mensagem no WhatsApp: para todos (so as minhas, o mesmo
        'apagar para todos' do celular) ou so para mim (aviso de estado
        `deleteMessageForMe`). True se o WhatsApp aceitou."""
        if self.cliente is None or not self._conectada:
            return False
        try:
            if para_todos:
                if not mensagem.minha:
                    return False
                self.cliente.revoke_message(
                    self._jid(mensagem.conversa_id),
                    self.cliente.get_me().JID, mensagem.id)
                return True
            from neonize.proto.Neonize_pb2 import PatchInfo
            from neonize.proto.waSyncAction.WAWebProtobufSyncAction_pb2 import (
                DeleteMessageForMeAction, SyncActionValue)
            remetente = "0"
            if not mensagem.minha and \
                    mensagem.conversa_id.endswith("@g.us") and \
                    mensagem.remetente:
                remetente = mensagem.remetente
            return self._enviar_estado(
                "deleteMessageForMe", 3, PatchInfo.REGULAR_HIGH,
                SyncActionValue(
                    deleteMessageForMeAction=DeleteMessageForMeAction(
                        deleteMedia=True,
                        messageTimestamp=int(mensagem.data))),
                mensagem.conversa_id,
                extra=(mensagem.id, "1" if mensagem.minha else "0",
                       remetente))
        except Exception:
            log.exception("não consegui apagar a mensagem no WhatsApp")
            return False

    def _ao_apagar_conversa(self, cliente, evento):
        """A conversa foi apagada no celular: sai das conversas do
        provedor e a interface decide se apaga tambem (so se nao ha mensagem
        mais nova que o aviso)."""
        try:
            if evento.FromFullSync:
                return      # exclusao antiga, de antes: nao apaga daqui
            cid = self._id_da_conversa(evento.JID)
            with self._trava:
                self._conversas.pop(cid, None)
            log.info("conversa apagada no celular")
            self.barramento.publicar(ev.ConversaApagadaNoCelular(
                self.conta.id, cid, float(evento.Timestamp)))
        except Exception:
            log.exception("erro ao tratar o aviso de apagar conversa")

    def _conferir_arquivadas(self):
        """Poe em cada conversa a marca de arquivada que o celular tem. O
        celular manda isso como aviso de estado (nao ha evento no neonize),
        entao e lido do armazem a cada INTERVALO_ARQUIVADAS segundos. A
        primeira leitura de uma conversa vale; depois so conta se o valor
        do celular mudou (assim o que se arquiva aqui nao e desfeito)."""
        if not self._conectada or self.cliente is None:
            return
        self._ultima_conferencia = time.time()
        with self._trava:
            convs = [c for c in self._conversas.values()
                     if c.id not in IGNORAR_CONVERSAS]
        mudou = []
        for conv in convs:
            dados = self._ajustes_no_celular(conv.id)
            if dados is None:
                continue
            valor = bool(dados.Archived)
            visto = self._arquivada_vista.get(conv.id)
            self._arquivada_vista[conv.id] = valor
            alterada = valor != visto and valor != conv.arquivada
            if alterada:
                conv.arquivada = valor
            for campo, novo in (
                    ("fixada", bool(dados.Pinned)),
                    ("silenciada_ate",
                     silencio_do_armazem(dados.MutedUntil))):
                visto = self._ajustes_vistos.get((conv.id, campo))
                self._ajustes_vistos[(conv.id, campo)] = novo
                if novo != visto and novo != getattr(conv, campo):
                    setattr(conv, campo, novo)
                    alterada = True
            if alterada:
                mudou.append(conv)
        if mudou:
            log.info("arquivadas conferidas: %d conversas mudaram de lugar",
                     len(mudou))
            self.banco.salvar_conversas(mudou)
            self._publicar_conversas()

    def _atualizar_nomes_de_grupos(self):
        """Pergunta ao WhatsApp o nome atual de todos os grupos e corrige os
        que mudaram (o aviso de mudanca so chega com o app aberto)."""
        if not self._conectada or self.cliente is None:
            return
        try:
            grupos = list(self.cliente.get_joined_groups())
        except Exception:
            log.info("não consegui a lista de grupos para conferir os nomes")
            return
        mudou = []
        with self._trava:
            for g in grupos:
                conv = self._conversas.get(jid_texto(g.JID))
                nome = g.GroupName.Name
                if conv is not None and nome and conv.nome != nome:
                    conv.nome = nome
                    mudou.append(conv)
        log.info("conferi o nome de %d grupos: %d mudaram", len(grupos),
                 len(mudou))
        if mudou:
            self.banco.salvar_conversas(mudou)
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
        alvo = self._numero_do_jid(jid)
        da_agenda = self.banco.nome_de_contato(
            self.conta.id, jid_texto(alvo), jid_texto(jid))
        if da_agenda:
            return da_agenda        # o nome dado no TeleZapp vale mais
        pushname = pushname or self._apelidos.get(jid_texto(jid), "")
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

    # nomes que o neonize usa para cada valor de privacidade
    _VALORES_PRIVACIDADE = {2: "all", 3: "contacts", 4: "contact_blacklist",
                            5: "match_last_seen", 6: "known", 7: "none"}

    def privacidade(self):
        if self.cliente is None or not self._conectada:
            return None
        try:
            c = self.cliente.get_privacy_settings()
        except Exception:
            log.exception("não consegui ler a privacidade da conta")
            return None
        v = self._VALORES_PRIVACIDADE.get
        return {"last": v(c.LastSeen), "online": v(c.Online),
                "status": v(c.Status), "readreceipts": v(c.ReadReceipts),
                "groupadd": v(c.GroupAdd)}

    def definir_privacidade(self, campo, valor):
        from neonize.utils.enum import PrivacySetting, PrivacySettingType
        self.cliente.set_privacy_setting(PrivacySettingType(campo),
                                         PrivacySetting(valor))

    def privacidade_status(self):
        if self.cliente is None or not self._conectada:
            return None
        try:
            itens = list(self.cliente.get_status_privacy())
        except Exception:
            log.info("não consegui ler quem vê o status")
            return None
        if not itens:
            return None
        padrao = next((i for i in itens if i.IsDefault), itens[0])
        tipo = {1: "contacts", 2: "blacklist", 3: "whitelist"}.get(
            padrao.Type, "contacts")
        return tipo, len(padrao.List)

    def id_do_telefone(self, telefone):
        digitos = re.sub(r"\D", "", telefone or "")
        return digitos + "@s.whatsapp.net" if digitos else ""

    def contatos_da_conta(self):
        """[(id, nome, telefone)] da agenda sincronizada com a conta (os
        contatos salvos no celular ou so no WhatsApp). Leitura local."""
        achados = []
        for c in self.cliente.contact.get_all_contacts():
            nome = c.Info.FullName or c.Info.FirstName
            if not nome or parece_codigo(nome):
                continue
            alvo = self._numero_do_jid(c.JID)
            if alvo.Server != "s.whatsapp.net" or not alvo.User:
                continue
            achados.append((jid_texto(alvo), nome, "+" + alvo.User))
        return achados

    def nome_de_participante(self, participante_id):
        """Nome de quem recebeu, abriu ou reproduziu uma mensagem, para os
        detalhes: agenda, nome de perfil visto nas mensagens (por qualquer
        endereco da pessoa) e mensagens guardadas, sem consultar a rede (a
        lista pode ter centenas de pessoas). Telefone se nada acha; vazio se
        so ha o codigo interno."""
        if self.cliente is None or "@" not in (participante_id or ""):
            return ""
        try:
            nome = self._dados_mencao(participante_id, rede=False).get(
                "nome") or ""
        except Exception:
            return ""
        usuario = jid_de_texto(participante_id)[0]
        return "" if nome in (SEM_NOME, usuario) else nome

    def _lembrar_apelido(self, jid, pushname, alternativo=None):
        """Guarda o nome de perfil que veio numa mensagem, sob o endereco
        original (LID ou telefone), sob o telefone e sob o segundo endereco
        que a propria mensagem informa (`alternativo`: o telefone de quem
        aparece como LID, ou o contrario), para as mencoes."""
        try:
            self._apelidos[jid_texto(jid)] = pushname
            if alternativo is not None and alternativo.User:
                self._aprender_par(jid, alternativo)
                self._apelidos[jid_texto(alternativo)] = pushname
            alvo = self._numero_do_jid(jid)
            if alvo is not jid:
                self._apelidos.setdefault(jid_texto(alvo), pushname)
        except Exception:
            log.info("não consegui guardar um nome de perfil")

    def _aprender_par(self, a, b):
        """Dois enderecos da mesma pessoa (LID e telefone), na ordem que for:
        vale para as proximas buscas, mesmo sem a consulta ao WhatsApp."""
        lid = a if a.Server == "lid" else b if b.Server == "lid" else None
        pn = a if a.Server == "s.whatsapp.net" else \
            b if b.Server == "s.whatsapp.net" else None
        if lid is not None and pn is not None and lid.User and pn.User:
            self._lid_para_numero.setdefault(jid_texto(lid), jid_texto(pn))

    def _formas_do_endereco(self, jid_txt):
        """Todos os enderecos conhecidos da mesma pessoa: o dado, o telefone
        e os LIDs. As mensagens de grupo guardam quem enviou por um deles e a
        mencao vem por outro."""
        formas = {jid_txt}
        usuario, servidor = jid_de_texto(jid_txt)
        jid = _jid_obj(usuario, servidor)
        try:
            alvo = self._numero_do_jid(jid)
            formas.add(jid_texto(alvo))
        except Exception:
            alvo = jid
        for lid, pn in list(self._lid_para_numero.items()):
            if lid in formas or pn in formas:
                formas.update((lid, pn))
        if self.cliente is not None and alvo.Server == "s.whatsapp.net":
            try:
                lid = self.cliente.get_lid_from_pn(alvo)
                if lid.User:
                    formas.add(jid_texto(lid))
            except Exception:
                pass
        return {f for f in formas if f and not f.startswith("@")}

    def _aprender_do_grupo(self, grupo):
        """Le a lista de participantes do grupo: o WhatsApp informa o
        telefone de quem aparece so como LID e, em alguns grupos, o nome.
        No maximo uma consulta por grupo a cada 10 minutos."""
        agora = time.time()
        if agora - self._grupos_lidos.get(grupo, 0) < 600:
            return
        self._grupos_lidos[grupo] = agora
        usuario, servidor = jid_de_texto(grupo)
        info = self.cliente.get_group_info(_jid_obj(usuario, servidor))
        for p in info.Participants:
            lid, pn = jid_texto(p.LID), jid_texto(p.PhoneNumber)
            if p.LID.User and p.PhoneNumber.User:
                self._lid_para_numero.setdefault(lid, pn)
            if p.DisplayName and not parece_codigo(p.DisplayName):
                for chave in (lid, pn, jid_texto(p.JID)):
                    if chave and chave != "@":
                        self._apelidos.setdefault(chave, p.DisplayName)

    def _nome_verificado_de(self, jid):
        """Nome verificado de uma empresa, pela consulta de usuario."""
        try:
            for u in self.cliente.get_user_info(jid):
                nome = u.UserInfo.VerifiedName.Details.verifiedName
                if nome:
                    return nome
        except Exception:
            log.info("sem nome verificado para uma menção")
        return ""

    def _dados_mencao(self, jid_txt, grupo="", rede=True):
        """{'nome', 'id', 'telefone'} de quem foi mencionado (com cache).
        Um resultado so com o telefone nao fica no cache: o nome de perfil
        pode chegar depois, numa mensagem da pessoa.

        Fontes, em ordem: agenda, nome de perfil visto nas mensagens e no
        historico, lista de participantes do grupo, mensagens guardadas e
        nome verificado de empresa."""
        achado = self._cache_mencoes.get(jid_txt)
        if achado is not None:
            return achado
        usuario, servidor = jid_de_texto(jid_txt)

        formas = []

        def apelido():
            for f in (formas or [jid_txt]):
                if self._apelidos.get(f):
                    return self._apelidos[f]
            return ""

        def resolver():
            jid = self._numero_do_jid(_jid_obj(usuario, servidor))
            tel = "+" + jid.User if jid.Server == "s.whatsapp.net" else ""
            nome = self._nome_contato(jid, apelido()) or usuario
            return jid, tel, nome

        def sem_nome(nome, tel):
            return nome in (tel, SEM_NOME, usuario)
        jid, telefone, nome = resolver()
        if sem_nome(nome, telefone):
            # a pessoa pode ter falado por outro endereco dela (LID ou
            # telefone): procura o nome por todos
            formas.extend(sorted(self._formas_do_endereco(jid_txt)))
            jid, telefone, nome = resolver()
        if sem_nome(nome, telefone) and grupo and rede:
            try:
                self._aprender_do_grupo(grupo)
                jid, telefone, nome = resolver()
            except Exception:
                log.info("não consegui ler os participantes do grupo")
        if sem_nome(nome, telefone):
            try:
                guardado = self.banco.nome_do_remetente(
                    self.conta.id, set(formas) | {jid_txt, jid_texto(jid)})
            except Exception:
                guardado = ""
            nome = guardado or nome
        if rede and sem_nome(nome, telefone):
            nome = self._nome_verificado_de(jid) or nome
        achado = {"nome": nome, "id": jid_texto(jid), "telefone": telefone}
        if not sem_nome(nome, telefone):
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
                men.update(self._dados_mencao(men["jid"], msg.conversa_id))
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

    def _cita_voce(self, msg):
        """A mensagem menciona (@) esta conta, pelo telefone ou pelo LID?"""
        mencoes = m.extras_de(msg)["mencoes"]
        if not mencoes or self.cliente is None:
            return False
        try:
            eu = self.cliente.get_me()
            meus = {eu.JID.User, eu.LID.User} - {""}
        except Exception:
            return False
        return any(jid_de_texto(men.get("jid") or "")[0] in meus
                   for men in mencoes)

    @staticmethod
    def _mencao_sem_nome(men):
        nome = men.get("nome") or ""
        return not nome or nome.startswith("+") or nome == SEM_NOME or \
            nome == jid_de_texto(men.get("jid") or "")[0]

    def _reavaliar_mencoes(self, msgs, maximo=300):
        """Mensagens guardadas cuja mencao ficou so com o telefone: o nome
        pode ter sido aprendido depois (a pessoa falou, o grupo foi lido).
        Tenta de novo e regrava o que mudou. Devolve as que mudaram. Quem
        continua sem nome so e procurado de novo depois de 10 minutos (cada
        procura pode ir a rede)."""
        mudaram, tentativas = [], 0
        agora = time.time()
        for x in msgs:
            extras = m.extras_de(x)
            pendentes = [
                men for men in extras["mencoes"] if men.get("jid") and (
                    self._mencao_sem_nome(men) or re.search(
                        r"@%s(?!\d)" % re.escape(jid_de_texto(men["jid"])[0]),
                        x.texto))]
            if not pendentes:
                continue
            texto, alterou = x.texto, False
            for men in pendentes:
                if tentativas >= maximo:
                    break
                if agora - self._mencoes_tentadas.get(men["jid"], 0) < 600:
                    continue
                tentativas += 1
                antigo = men.get("nome") or ""
                try:
                    achado = self._dados_mencao(men["jid"], x.conversa_id)
                except Exception:
                    log.exception("erro ao achar o nome de uma menção")
                    continue
                novo = achado.get("nome") or ""
                if not novo or self._mencao_sem_nome({**men, **achado}):
                    self._mencoes_tentadas[men["jid"]] = agora
                    continue
                self._mencoes_tentadas.pop(men["jid"], None)
                men.update(achado)
                usuario = jid_de_texto(men["jid"])[0]
                for velho in {antigo, "+" + usuario, usuario}:
                    if velho:
                        texto = re.sub(r"@%s(?!\d)" % re.escape(velho),
                                       lambda _: "@" + novo, texto)
                alterou = True
            if alterou:
                x.texto = texto
                m.guardar_extras(x, extras["links"], extras["botoes"],
                                 extras["mencoes"], extras["acoes"],
                                 extras["original"])
                mudaram.append(x)
        if mudaram:
            self.banco.salvar_mensagens(mudaram)
        return mudaram

    def _rever_mencoes_do_grupo(self, conversa_id):
        """Em segundo plano, depois de abrir um grupo: corrige as mencoes
        que ficaram so com o telefone e avisa a tela de cada mensagem que
        mudou."""
        try:
            if self.cliente is None or not self._conectada:
                return
            msgs = self.banco.mensagens(self.conta.id, conversa_id, 1000)
            for x in self._reavaliar_mencoes(msgs):
                self.barramento.publicar(ev.MensagemAtualizada(
                    self.conta.id, conversa_id, x, "mencao"))
        except Exception:
            log.exception("erro ao rever as menções")

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
                    conv.nome.startswith("+") or
                    (self.conta.nome and conv.nome == self.conta.nome)):
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

    # ------------------------------------------------------------ presenca
    def observar_presenca(self, conversa_id):
        """Online, visto por ultimo e "digitando": o WhatsApp so manda isso
        a quem esta disponivel (e quem esconde o proprio status tambem nao
        ve o dos outros). A conta fica disponivel so enquanto uma conversa
        esta aberta; por isso fechar a conversa volta ao normal."""
        if conversa_id.endswith(("@newsletter", "@broadcast")) or \
                conversa_id.startswith(PREFIXO_STATUS):
            return
        self._fila.put(lambda: self._assinar_presenca(conversa_id))

    def parar_presenca(self, conversa_id):
        self._fila.put(lambda: self._largar_presenca(conversa_id))

    def _assinar_presenca(self, cid):
        if self.cliente is None or not self._conectada:
            return
        from neonize.utils.enum import Presence
        self._observadas = {}       # so uma conversa aberta por vez
        self._presenca_cid = cid
        try:
            if not self._disponivel:
                self.cliente.send_presence(Presence.AVAILABLE)
                self._disponivel = True
            if not cid.endswith("@g.us"):
                jid = self._jid(cid)
                self._observadas[jid_texto(jid)] = cid
                self.cliente.subscribe_presence(jid)
        except Exception as e:
            log.warning("não consegui observar a presença: %r", e)

    def _largar_presenca(self, cid):
        if self._presenca_cid != cid:
            return                  # ja abriram outra conversa
        self._presenca_cid = None
        self._observadas = {}
        if self.cliente is None or not self._conectada or \
                not self._disponivel:
            return
        from neonize.utils.enum import Presence
        try:
            self.cliente.send_presence(Presence.UNAVAILABLE)
        except Exception as e:
            log.warning("não consegui voltar a presença ao normal: %r", e)
        self._disponivel = False

    def _id_observado(self, jid):
        return self._observadas.get(jid_texto(jid)) or \
            self._id_da_conversa(jid)

    def _ao_presenca(self, cliente, e):
        """Online ou visto por ultimo da pessoa da conversa aberta."""
        try:
            cid = self._id_observado(e.From)
            if e.Unavailable:
                self.barramento.publicar(ev.Presenca(
                    self.conta.id, cid, "offline",
                    quando=_ultima_vez(e.LastSeen)))
            else:
                self.barramento.publicar(ev.Presenca(
                    self.conta.id, cid, "online"))
        except Exception:
            log.exception("erro ao tratar a presença")

    def _ao_digitando(self, cliente, e):
        try:
            origem = e.MessageSource
            cid = self._id_observado(origem.Chat)
            grupo = origem.Chat.Server == "g.us"
            quem = ""
            if grupo:
                quem = self._apelidos.get(jid_texto(origem.Sender), "")
            if e.State == 1:     # COMPOSING
                estado = "gravando" if e.Media == 2 else "digitando"
            else:
                estado = "parou"
            self.barramento.publicar(ev.Presenca(
                self.conta.id, cid, estado, quem=quem))
        except Exception:
            log.exception("erro ao tratar o aviso de digitando")

    def conversa_aberta(self, conversa_id):
        if conversa_id.endswith("@g.us"):
            self._fila.put(lambda: self._conferir_escrita(conversa_id))
            self._fila.put(lambda: self._completar_autores(conversa_id))

    def _completar_autores(self, cid):
        """Mensagens de grupo (do historico, sobretudo) de gente que so
        aparece como LID ficam sem autor: acha o nome pela agenda, pelos
        nomes vistos e pela lista de participantes do grupo, grava e avisa a
        tela."""
        try:
            if self.cliente is None or not self._conectada:
                return
            sem = {x.remetente for x in self.banco.mensagens(
                self.conta.id, cid, 3000)
                if not x.minha and not x.autor and x.remetente}
            if not sem:
                return
            try:
                self._aprender_do_grupo(cid)
            except Exception:
                log.info("não consegui ler os participantes do grupo")
            nomes = {}
            for rem in sem:
                nome = self.nome_de_participante(rem)
                if not nome:
                    continue
                formas = {rem} | set(self._formas_do_endereco(rem))
                if self.banco.renomear_autor(self.conta.id, formas, nome):
                    nomes[rem] = nome
            if nomes:
                log.info("autores achados para %d participantes de um grupo",
                         len(nomes))
                self.barramento.publicar(ev.AutoresAtualizados(
                    self.conta.id, cid, nomes))
        except Exception:
            log.exception("erro ao completar os autores do grupo")

    def _conferir_escrita(self, cid, forcar=False):
        """Grupo so de administradores em que nao sou admin, ou grupo de que
        saí ou fui removido: a conversa passa a ser so de leitura."""
        agora = time.time()
        if self.cliente is None or not self._conectada or (
                not forcar and agora - self._escrita_conferida.get(cid, 0)
                < 300):
            return
        self._escrita_conferida[cid] = agora
        usuario, servidor = jid_de_texto(cid)
        try:
            info = self.cliente.get_group_info(_jid_obj(usuario, servidor))
        except Exception as e:
            texto = str(e).lower()
            if "403" in texto or "not-authorized" in texto or \
                    "forbidden" in texto or "not in" in texto:
                self._marcar_escrita(cid, False)       # nao participo mais
            return
        pode = True
        if info.GroupAnnounce.IsAnnounce:
            eu = self.cliente.get_me()
            meus = {eu.JID.User, eu.LID.User} - {""}
            for p in info.Participants:
                if meus & {p.JID.User, p.LID.User, p.PhoneNumber.User}:
                    pode = bool(p.IsAdmin or p.IsSuperAdmin)
                    break
        self._marcar_escrita(cid, pode)

    def _marcar_escrita(self, cid, pode):
        with self._trava:
            conv = self._conversas.get(cid)
            if conv is None or conv.somente_leitura == (not pode):
                return
            conv.somente_leitura = not pode
        log.info("conversa de grupo: %s", "pode escrever" if pode else
                 "somente leitura")
        self.banco.atualizar_conversa(self.conta.id, cid,
                                      somente_leitura=int(not pode))
        self._publicar_conversas()

    def _ao_grupo_mudou(self, cliente, evento):
        """Alguem mudou os dados do grupo: o nome, e quem pode escrever."""
        try:
            if evento.HasField("Announce") or evento.Promote or \
                    evento.Demote or evento.Leave:
                cid = jid_texto(evento.JID)
                self._fila.put(lambda: self._conferir_escrita(cid, True))
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
            origem = info.MessageSource
            grupo = bool(origem.IsGroup)
            cid = self._id_da_conversa(origem.Chat)
            chat_da_msg = origem.Chat
            if origem.Chat.Server == "broadcast" and \
                    cid not in IGNORAR_CONVERSAS:
                # Lista de transmissao: o WhatsApp nao deixa responder nela.
                # A mensagem recebida vai para a conversa com quem a enviou
                # (como no celular); a que eu mandei pela lista e ignorada.
                if origem.IsFromMe:
                    return
                cid = self._id_da_conversa(origem.Sender)
                chat_da_msg = origem.Sender
                grupo = False
            autor = ""
            if not origem.IsFromMe:
                self._aprender_par(origem.Sender, origem.SenderAlt)
            if not origem.IsFromMe and info.Pushname:
                self._lembrar_apelido(origem.Sender, info.Pushname,
                                      origem.SenderAlt)
            if grupo and not origem.IsFromMe:
                autor = self._nome_contato(
                    origem.Sender, info.Pushname or nome_verificado(info))
            if self._tratar_alteracao(evento, cid, info, origem):
                return
            msg, remetente = converter(evento, self.conta.id, cid, autor)
            if msg is None:
                # So controle (chave de grupo, reacao...). O ID NAO entra em
                # _vistas: num grupo, quem troca a chave de envio manda a
                # chave e o texto no mesmo pacote, e o whatsmeow entrega dois
                # eventos com o mesmo ID; o do texto vem depois.
                ignorados = sorted(set(campos(desembrulhar(evento.Message)))
                                   - {"senderKeyDistributionMessage",
                                      "messageContextInfo"})
                if ignorados:
                    log.info("evento sem conteúdo para mostrar: id=%s "
                             "campos=%s", info.ID, ", ".join(ignorados))
                return
            with self._trava:
                if info.ID in self._vistas:      # outro evento ja tratou
                    return
                self._vistas.add(info.ID)
                if len(self._vistas) > MAX_GUARDADAS:
                    self._vistas = set(list(self._vistas)[-MAX_GUARDADAS // 2:])
            self._enriquecer_mencoes(msg)
            if grupo and not msg.minha and self._cita_voce(msg):
                m.atualizar_extras(msg, citou_voce=True)
            if self.banco.depuracao:
                self.banco.guardar_depuracao(
                    self.conta.id, cid, msg.id,
                    estrutura_bruta(evento.Message, info))
            if cid in IGNORAR_CONVERSAS:
                self._guardar_status(msg, evento, origem, info)
                return
            if msg.tipo in armazem.BAIXAVEIS:
                ficha = ficha_de(desembrulhar(evento.Message))
                if ficha:
                    self.banco.salvar_fichas(
                        [(self.conta.id, cid, msg.id, ficha)])
            # numa mensagem minha o nome de perfil e o meu, nao o da conversa
            conv = self._conversa(
                cid, chat_da_msg,
                "" if origem.IsFromMe else (
                    info.Pushname or nome_verificado(info)),
                grupo, msg.data)
            if not grupo and conv.nome.startswith("+") and \
                    cid not in self._sem_nome_registrados:
                self._sem_nome_registrados.add(cid)
                log.info("mensagem ao vivo de conversa só com telefone: "
                         "perfil=%s, nome verificado=%s",
                         "veio" if info.Pushname else "não veio",
                         "veio" if nome_verificado(info) else "não veio")
            if not grupo and not msg.minha and not msg.autor:
                msg.autor = conv.nome       # conversa privada: quem fala
            prazo = _prazo(_contexto(desembrulhar(evento.Message)))
            with self._trava:
                conv.data = max(conv.data, msg.data)
                self._remetentes[msg.id] = (remetente, msg.texto)
                silenciosa = self._sincronizando
                if conv.temporaria_s != prazo:
                    conv.temporaria_s = prazo
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

    def _ao_indecifravel(self, cliente, evento):
        """O WhatsApp entregou uma mensagem que nao deu para decifrar (chave
        do grupo que ainda nao chegou, por exemplo). O whatsmeow pede de novo
        ao remetente e, se der certo, a mensagem chega depois, com o mesmo
        id. Enquanto isso fica uma marca no lugar dela, para a conversa nao
        parecer faltar uma mensagem."""
        try:
            info = evento.Info
            origem = info.MessageSource
            cid = self._id_da_conversa(origem.Chat)
            log.warning(
                "mensagem não decifrada: id=%s conversa=%s remetente=%s "
                "indisponível=%s modo=%s", info.ID, cid,
                jid_texto(origem.Sender), bool(evento.IsUnavailable),
                int(evento.DecryptFailMode))
            if origem.Chat.Server == "broadcast" or cid in IGNORAR_CONVERSAS \
                    or int(evento.DecryptFailMode) == 2:   # DECRYPT_FAIL_HIDE
                return
            with self._trava:
                if info.ID in self._vistas:
                    return
            grupo = bool(origem.IsGroup)
            minha = bool(origem.IsFromMe)
            nome = "" if minha else (info.Pushname or nome_verificado(info))
            autor = ""
            if grupo and not minha:
                autor = self._nome_contato(origem.Sender, nome)
            msg = m.Mensagem(
                conta_id=self.conta.id, conversa_id=cid, id=info.ID,
                autor=autor, minha=minha,
                data=segundos(info.Timestamp) or time.time(),
                tipo=m.AGUARDANDO, estado=m.ENVIADA if minha else "",
                remetente="" if minha else jid_texto(origem.Sender))
            conv = self._conversa(cid, origem.Chat, nome, grupo, msg.data)
            if not grupo and not minha and not msg.autor:
                msg.autor = conv.nome
            with self._trava:
                conv.data = max(conv.data, msg.data)
            self.banco.salvar_conversas([conv])
            self.banco.salvar_mensagens([msg])
            self.barramento.publicar(ev.MensagemNova(msg, conv,
                                                     silenciosa=True))
        except Exception:
            log.exception("erro ao tratar mensagem não decifrada")

    def _tratar_alteracao(self, evento, cid, info, origem):
        """Reacao, edicao ou 'apagar para todos' de uma mensagem que ja
        conhecemos. True se o evento era disso (nao e uma mensagem nova)."""
        interna = desembrulhar(evento.Message)
        presentes = set(campos(interna))
        if "reactionMessage" in presentes:
            r = interna.reactionMessage
            alvo = r.key.ID
            quem_id = jid_texto(origem.Sender)
            quem = "Você" if origem.IsFromMe else self._nome_contato(
                origem.Sender, info.Pushname or nome_verificado(info))
            emoji = r.text

            def aplicar(x):
                reacoes = [y for y in m.extras_de(x)["reacoes"]
                           if y.get("id") != quem_id]
                if emoji:
                    reacoes.append({"id": quem_id, "quem": quem,
                                    "emoji": emoji,
                                    "minha": bool(origem.IsFromMe)})
                m.atualizar_extras(x, reacoes=reacoes)
            self._alterar(cid, alvo, aplicar, "reacao", quem, emoji)
            return True
        if "pollUpdateMessage" in presentes:
            self._tratar_voto(evento, cid, info, origem, interna)
            return True
        if "protocolMessage" in presentes:
            p = interna.protocolMessage
            if p.HasField("type") and p.type == p.EPHEMERAL_SETTING:
                self._temporaria_mudou(cid, int(p.ephemeralExpiration or 0),
                                       bool(origem.IsFromMe))
                return True
            if not p.HasField("type") or not p.key.ID:
                return False
            alvo = p.key.ID
            if p.type == p.REVOKE:
                def apagar(x):
                    x.texto = ""
                    m.atualizar_extras(x, apagada=True, links=[], botoes=[],
                                       acoes=[], original="")
                self._alterar(cid, alvo, apagar, "apagada")
                return True
            if p.type == p.MESSAGE_EDIT:
                novo = conteudo_de(desembrulhar(p.editedMessage))
                if novo is None:
                    return True

                def editar(x):
                    # o texto novo traz as suas proprias mencoes (@): sem
                    # elas ficaria o numero no lugar do nome
                    x.texto = novo[1] or ""
                    editada = desembrulhar(p.editedMessage)
                    m.atualizar_extras(
                        x, editada=True,
                        mencoes=mencoes_do_contexto(_contexto(editada)))
                    self._enriquecer_mencoes(x)
                self._alterar(cid, alvo, editar, "editada")
                return True
        return False

    PODE_REAGIR = True

    def reagir(self, mensagem, emoji):
        self._fila.put(lambda: self._reagir(mensagem, emoji))

    def _reagir(self, msg, emoji):
        cid = msg.conversa_id
        try:
            if not self._conectada or self.cliente is None:
                raise ConnectionError("sem conexão")
            eu = self.cliente.get_me().JID
            if msg.minha:
                autor = eu
            else:
                individual = not cid.endswith("@g.us")
                rem = msg.remetente or (cid if individual else "")
                if not rem:
                    raise ValueError("sem o remetente da mensagem")
                autor = _jid_obj(*jid_de_texto(rem))
            if cid.startswith(PREFIXO_STATUS):
                # curtir um status: a reacao vai para a conversa com quem o
                # publicou e cita o status
                if msg.minha:
                    raise ValueError("status proprio")
                from neonize.proto.waCommon import WACommon_pb2 as C
                from neonize.proto.waE2E import WAWebProtobufsE2E_pb2 as E
                chave = C.MessageKey(remoteJID="status@broadcast",
                                     fromMe=False, ID=msg.id,
                                     participant=jid_texto(autor))
                self.cliente.send_message(autor, E.Message(
                    reactionMessage=E.ReactionMessage(
                        key=chave, text=emoji,
                        senderTimestampMS=int(time.time() * 1000))))
            else:
                chat = self._jid(cid)
                self.cliente.send_message(
                    chat, self.cliente.build_reaction(chat, autor, msg.id,
                                                      emoji))
        except Exception as e:
            log.warning("reação falhou: %s", type(e).__name__)
            self._avisar("Não consegui enviar a reação (%s)." %
                         type(e).__name__, False)
            return
        quem_id = jid_texto(eu)

        def aplicar(x):
            reacoes = [y for y in m.extras_de(x)["reacoes"]
                       if y.get("id") != quem_id]
            if emoji:
                reacoes.append({"id": quem_id, "quem": "Você",
                                "emoji": emoji, "minha": True})
            m.atualizar_extras(x, reacoes=reacoes)
        self._alterar(cid, msg.id, aplicar, "reacao", "Você", emoji)

    def _tratar_voto(self, evento, cid, info, origem, interna):
        """Voto numa enquete: o WhatsApp o manda cifrado com o segredo da
        enquete, que o neonize guarda quando recebe a pergunta. Votos de
        enquetes de antes do TeleZapp (sem o segredo) nao dá para ler."""
        alvo = interna.pollUpdateMessage.pollCreationMessageKey.ID
        try:
            consertar_decifrar_voto(self.cliente)
            voto = self.cliente.decrypt_poll_vote(evento)
        except Exception as e:
            log.info("voto em enquete que não consegui decifrar (%s: %s)",
                     type(e).__name__, str(e)[:120])
            return
        quem_id = jid_texto(origem.Sender)
        quem = "Você" if origem.IsFromMe else self._nome_contato(
            origem.Sender, info.Pushname or nome_verificado(info))

        def aplicar(x):
            enq = m.enquete_de(x)
            if not enq:
                return
            escolhas = indices_do_voto(enq["opcoes"], voto.selectedOptions)
            votos = dict(enq["votos"])
            votos[quem_id] = {"nome": quem, "escolhas": escolhas}
            atual = dict(m.extras_de(x)["enquete"])
            atual["votos"] = votos
            if origem.IsFromMe:
                atual["meus"] = escolhas
            m.atualizar_extras(x, enquete=atual)
        self._alterar(cid, alvo, aplicar, "enquete", quem)

    PODE_CRIAR_ENQUETE = True

    def criar_enquete(self, conversa_id, pergunta, opcoes, multipla,
                      anonima=True):
        self._fila.put(lambda: self._criar_enquete(
            conversa_id, pergunta, list(opcoes), multipla))

    def _criar_enquete(self, cid, pergunta, opcoes, multipla):
        try:
            if not self._conectada or self.cliente is None:
                raise ConnectionError("sem conexão")
            from neonize.utils.enum import VoteType
            jid = self._jid(cid)
            criada = self.cliente.build_poll_vote_creation(
                pergunta, opcoes,
                VoteType.MULTIPLE if multipla else VoteType.SINGLE)
            resp = self.cliente.send_message(
                jid, com_expiracao(criada, self._prazo_da_conversa(cid)))
        except Exception as e:
            log.warning("criar enquete falhou: %s: %s", type(e).__name__,
                        str(e)[:200])
            self._avisar("Não consegui criar a enquete (%s)." %
                         ("sem conexão" if isinstance(e, ConnectionError)
                          else type(e).__name__), False)
            return
        self._registrar_enviada(
            resp, cid, "enquete: " + pergunta, tipo=m.OUTRO,
            enquete={"pergunta": pergunta, "opcoes": opcoes,
                     "maximo": len(opcoes) if multipla else 1})

    PODE_VOTAR = True

    def votar_enquete(self, mensagem, escolhas):
        self._fila.put(lambda: self._votar_enquete(mensagem, escolhas))

    def _votar_enquete(self, msg, escolhas):
        cid = msg.conversa_id
        enq = m.enquete_de(msg)
        try:
            if not self._conectada or self.cliente is None:
                raise ConnectionError("sem conexão")
            if not enq:
                raise ValueError("não é uma enquete")
            from neonize.proto.Neonize_pb2 import MessageInfo, MessageSource
            eu = self.cliente.get_me().JID
            if msg.minha:
                autor = eu
            else:
                individual = not cid.endswith("@g.us")
                rem = msg.remetente or (cid if individual else "")
                if not rem:
                    raise ValueError("sem o remetente da enquete")
                autor = _jid_obj(*jid_de_texto(rem))
            chat = self._jid(cid)
            origem = MessageSource(Chat=chat, Sender=autor,
                                   IsFromMe=bool(msg.minha),
                                   IsGroup=cid.endswith("@g.us"))
            enquete_info = MessageInfo(MessageSource=origem, ID=msg.id)
            nomes = [enq["opcoes"][i] for i in escolhas]
            self.cliente.send_message(
                chat, self.cliente.build_poll_vote(enquete_info, nomes))
        except Exception as e:
            log.warning("voto em enquete falhou: %s: %s", type(e).__name__,
                        str(e)[:200])
            self._avisar("Não consegui enviar o voto (%s)." %
                         type(e).__name__, False)
            return
        quem_id = jid_texto(eu)

        def aplicar(x):
            atual = dict(m.extras_de(x)["enquete"])
            votos = dict(m.enquete_de(x)["votos"])
            votos[quem_id] = {"nome": "Você", "escolhas": list(escolhas)}
            atual["votos"] = votos
            atual["meus"] = list(escolhas)
            m.atualizar_extras(x, enquete=atual)
        self._alterar(cid, msg.id, aplicar, "enquete", "Você")

    def _alterar(self, cid, alvo, aplicar, motivo, quem="", emoji=""):
        """Aplica `aplicar` a mensagem guardada, grava e avisa a interface.
        Se a mensagem e de antes do TeleZapp guardar, nao faz nada."""
        x = self.banco.mensagem(self.conta.id, cid, alvo)
        if x is None:
            log.info("%s de uma mensagem que não está guardada", motivo)
            return
        aplicar(x)
        self.banco.salvar_mensagens([x])
        self.barramento.publicar(ev.MensagemAtualizada(
            self.conta.id, cid, x, motivo, quem, emoji))

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
            mensagem = Message.FromString(dados)
            if self._tem_transferencias():
                self._baixar_por_arquivo(mensagem, parcial, msg, progresso,
                                         cancelado)
            else:
                self.cliente.download_any(mensagem, parcial)
            if cancelado():
                raise DownloadCancelado()
            os.replace(parcial, caminho)
        except (DownloadCancelado, ErroMidia):
            raise
        except Exception as e:
            if cancelado():
                raise DownloadCancelado()
            log.warning("download falhou: %s", type(e).__name__)
            raise ErroMidia("O WhatsApp não entregou a mídia (%s). Ela pode "
                            "ter expirado no servidor." % type(e).__name__)
        finally:
            if os.path.exists(parcial):
                os.remove(parcial)
        progresso(100)
        return caminho

    def _tem_transferencias(self):
        """A DLL baixa e envia por arquivo, com progresso e cancelamento?"""
        funcao = getattr(self.cliente, "tem_transferencias", None)
        try:
            return bool(funcao and funcao())
        except Exception:
            return False

    def _baixar_por_arquivo(self, mensagem, parcial, msg, progresso,
                            cancelado):
        """Baixa direto para o arquivo; o avanco vem do tamanho dele em
        relacao ao tamanho da midia (so nao ha porcentagem se a mensagem nao
        traz o tamanho)."""
        chave = "dl-" + uuid.uuid4().hex
        fim = threading.Event()

        def vigiar():
            ultimo = 0
            while not fim.wait(0.3):
                if cancelado():
                    self.cliente.transfer_cancel(chave)
                    return
                if msg.tamanho and os.path.exists(parcial):
                    pct = min(99, int(os.path.getsize(parcial) * 100 /
                                      msg.tamanho))
                    if pct > ultimo:
                        ultimo = pct
                        progresso(pct)
        vigia = threading.Thread(target=vigiar, daemon=True,
                                 name="whatsapp-vigia-download")
        vigia.start()
        try:
            self.cliente.download_any_to_file(mensagem, parcial, chave)
        finally:
            fim.set()
            vigia.join(2)

    def _guardar_status(self, msg, evento, origem, info):
        """Um status (story): vira uma mensagem na "conversa" de status de
        quem o publicou, para ver, ouvir, responder e curtir como numa
        conversa. A midia fica baixavel (a ficha vai junto)."""
        autor_id = self._id_da_conversa(origem.Sender)
        sid = PREFIXO_STATUS + autor_id
        meu = bool(origem.IsFromMe)
        nome = "Você" if meu else self._nome_contato(
            origem.Sender, info.Pushname or nome_verificado(info))
        msg.conversa_id, msg.autor, msg.remetente = sid, nome, autor_id
        if msg.tipo in armazem.BAIXAVEIS:
            ficha = ficha_de(desembrulhar(evento.Message))
            if ficha:
                self.banco.salvar_fichas([(self.conta.id, sid, msg.id,
                                           ficha)])
        titulo = "Meu status" if meu else "Status de " + nome
        with self._trava:
            conv = self._conversas.get(sid)
            if conv is None:
                conv = m.Conversa(self.conta.id, sid, titulo, self.servico,
                                  "status", data=msg.data)
                self._conversas[sid] = conv
            conv.nome = titulo
            conv.data = max(conv.data, msg.data)
            if not meu:
                conv.nao_lidas += 1
                self._nao_lidas.setdefault(sid, []).append(
                    (msg.id, origem.Sender))
        self.banco.salvar_conversas([conv])
        self.banco.salvar_mensagens([msg])
        self.barramento.publicar(ev.MensagemNova(msg, conv, silenciosa=True))
        log.info("status guardado (%s)", msg.tipo)
        self._fila.put(self._limpar_status_antigos)

    PODE_PUBLICAR_STATUS = True

    def publicar_status(self, texto, anexo=None, publico="contatos"):
        """Publica o status de texto, foto ou video. Quem ve e o que a conta
        escolheu para o status no celular (contatos, exceto ou so alguns)."""
        threading.Thread(target=self._publicar_status, args=(texto, anexo),
                         daemon=True, name="whatsapp-status").start()

    def _publicar_status(self, texto, anexo):
        from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
            ExtendedTextMessage, Message)
        try:
            if not self._conectada or self.cliente is None:
                raise ConnectionError("sem conexão")
            destino = _jid_obj("status", "broadcast")
            if anexo is None:
                resp = self.cliente.send_message(destino, Message(
                    extendedTextMessage=ExtendedTextMessage(
                        text=texto, textArgb=0xFFFFFFFF,
                        backgroundArgb=0xFF1B8755, font=0)))
            elif anexo.tipo == m.FOTO:
                resp = self.cliente.send_image(destino, anexo.caminho,
                                               caption=texto or None)
            else:
                resp = self.cliente.send_message(
                    destino, self._mensagem_de_midia(anexo, texto))
        except Exception as e:
            log.warning("publicar status falhou: %s: %s", type(e).__name__,
                        str(e)[:300], exc_info=True)
            motivo = "sem conexão" if isinstance(e, ConnectionError) else \
                "erro do WhatsApp (%s)" % type(e).__name__
            self._avisar("Não consegui publicar o status: %s." % motivo)
            return
        log.info("status publicado")
        self._guardar_meu_status(resp, texto, anexo)
        self._avisar("Status publicado.")

    def _guardar_meu_status(self, resp, texto, anexo):
        """O status que acabei de publicar entra em "Meu status"."""
        eu = jid_texto(self.cliente.get_me().JID)
        sid = PREFIXO_STATUS + eu
        with self._trava:
            if sid not in self._conversas:
                self._conversas[sid] = m.Conversa(
                    self.conta.id, sid, "Meu status", self.servico, "status",
                    data=time.time())
        campos = {}
        if anexo is not None:
            campos = dict(tipo=anexo.tipo, segundos=anexo.segundos,
                          nome_arquivo=anexo.nome, tamanho=anexo.tamanho)
        msg = self._registrar_enviada(
            resp, sid, texto, remetente=eu,
            arquivo=(anexo.caminho, anexo.temporario) if anexo else None,
            **campos)
        return msg

    def _limpar_status_antigos(self):
        """Apaga os status com mais de um dia (o WhatsApp tambem os tira) e
        as "conversas" que ficaram vazias."""
        limite = time.time() - VALIDADE_STATUS
        mudou = False
        for sid in [c.id for c in list(self._conversas.values())
                    if c.tipo == "status"]:
            msgs = self.banco.mensagens(self.conta.id, sid, 10 ** 6)
            velhas = [(self.conta.id, sid, x.id) for x in msgs
                      if x.data < limite]
            if velhas:
                self.banco.apagar_mensagens(velhas)
                mudou = True
            if len(velhas) == len(msgs):
                self.banco.apagar_conversa(self.conta.id, sid, 0)
                with self._trava:
                    self._conversas.pop(sid, None)
                    self._nao_lidas.pop(sid, None)
        if mudou:
            self._publicar_conversas()

    def responder_status(self, mensagem, texto):
        """Resposta em particular ao status: vai para a conversa com quem o
        publicou, citando o status."""
        autor = mensagem.remetente
        if not autor or mensagem.minha:
            return
        self._fila.put(lambda: self._enviar(
            autor, texto, RESPOSTA_A_STATUS + mensagem.id))

    def carregar_mensagens(self, conversa_id, limite=50):
        msgs = self.banco.mensagens(self.conta.id, conversa_id,
                                    max(limite, 100))
        self.barramento.publicar(ev.MensagensCarregadas(
            self.conta.id, conversa_id, msgs))
        if conversa_id.endswith("@g.us"):
            # pode ir a rede: nunca na abertura da conversa
            self._fila.put(lambda: self._rever_mencoes_do_grupo(conversa_id))

    def enviar_texto(self, conversa_id, texto, resposta_a="", mencoes=None):
        self._fila.put(lambda: self._enviar(conversa_id, texto, resposta_a,
                                            mencoes=mencoes))

    def _jid(self, conversa_id):
        from neonize.utils.jid import build_jid
        usuario, servidor = conversa_id.split("@", 1)
        return build_jid(usuario, servidor)

    def _mencoes_no_texto(self, texto, mencoes):
        """(texto, [JID de quem foi mencionado]): cada '@Nome' escolhido na
        caixa vira '@numero', que e como o WhatsApp mostra a mencao."""
        if not mencoes:
            return texto, []
        jids = []

        def trocar(men):
            usuario, servidor = jid_de_texto(men.get("id", ""))
            jids.append(jid_texto(_jid_obj(usuario, servidor)))
            return "@" + usuario
        novo, _ = nucleo_mencoes.aplicar(texto, mencoes, trocar)
        return novo, jids

    def _mensagem_de_texto(self, conversa_id, texto, resposta_a, previa=None,
                           mencoes=None):
        from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
            ContextInfo, ExtendedTextMessage, Message)
        campos = {}
        if previa:
            campos = {"matchedText": previa.get("url", ""),
                      "title": previa.get("titulo", ""),
                      "description": previa.get("descricao", "")}
        texto, jids = self._mencoes_no_texto(texto, mencoes)
        if not resposta_a:
            if campos or jids:
                return Message(extendedTextMessage=ExtendedTextMessage(
                    text=texto, contextInfo=ContextInfo(
                        mentionedJID=jids) if jids else None, **campos))
            return Message(conversation=texto)
        if resposta_a.startswith(RESPOSTA_A_STATUS):
            return self._resposta_a_status(
                conversa_id, texto, resposta_a[len(RESPOSTA_A_STATUS):])
        ctx = self._contexto_da_resposta(conversa_id, resposta_a)
        if jids:
            ctx.mentionedJID.extend(jids)
        return Message(extendedTextMessage=ExtendedTextMessage(
            text=texto, contextInfo=ctx, **campos))

    def _contexto_da_resposta(self, conversa_id, resposta_a):
        """O ContextInfo que cita a mensagem `resposta_a` da conversa."""
        from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
            ContextInfo, Message)
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
        # resposta em particular a uma mensagem de grupo: a citada esta em
        # outra conversa; o WhatsApp quer saber qual, e o texto e o autor
        # vem de la
        grupo_de_origem = ""
        if not self.banco.mensagens_por_id(self.conta.id, [resposta_a],
                                           conversa_id):
            for x in self.banco.mensagens_por_id(self.conta.id,
                                                 [resposta_a]):
                grupo_de_origem = x.conversa_id
                citado = citado or x.texto or m.conteudo(x)
                remetente = remetente or x.remetente
                break
        ctx = ContextInfo(stanzaID=resposta_a,
                          quotedMessage=Message(conversation=citado or ""))
        if remetente:
            ctx.participant = remetente
        if grupo_de_origem:
            ctx.remoteJID = grupo_de_origem
        return ctx

    def _resposta_a_status(self, autor_id, texto, status_id):
        from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
            ContextInfo, ExtendedTextMessage, Message)
        sid = PREFIXO_STATUS + autor_id
        citado = ""
        for x in self.banco.mensagens_por_id(self.conta.id, [status_id], sid):
            citado = x.texto or m.conteudo(x)
        ctx = ContextInfo(stanzaID=status_id, participant=autor_id,
                          remoteJID="status@broadcast",
                          quotedMessage=Message(conversation=citado))
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
        # Nota: o servidor recusa (479) a resposta de botao ou de lista com o
        # no <biz><buttons_response/> (ou <list_response/>) que o whatsmeow
        # poe sozinho; o WhatsApp Web nao manda esse no. A DLL de teste do
        # neonize (Backup\neonize-0.5.2-teste) vem sem ele (docs/neonize).
        # Embrulhar a resposta em "documento com legenda" tira o no mas o
        # servidor aceita e a empresa ignora a mensagem: nao fazer isso.
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
                descricao_acao="", mencoes=None):
        inicio = time.perf_counter()
        previa = {}
        try:
            if not self._conectada:
                raise ConnectionError("sem conexão")
            if conversa_id.endswith("@broadcast"):
                raise ListaDeTransmissao()
            if construir is None:
                previa = self._previa_ao_enviar(texto)
                resp = self.cliente.send_message(
                    self._jid(conversa_id),
                    com_expiracao(self._mensagem_de_texto(
                        conversa_id, texto, resposta_a, previa, mencoes),
                        self._prazo_da_conversa(conversa_id)))
            else:
                resp = self._enviar_variantes(construir())
        except Exception as e:
            log.warning("envio falhou: %s: %s%s", type(e).__name__,
                        str(e)[:300],
                        (" (resposta de botão %s)" % descricao_acao)
                        if descricao_acao else "", exc_info=True)
            if isinstance(e, ConnectionError):
                motivo = "sem conexão"
            elif isinstance(e, ListaDeTransmissao):
                motivo = "listas de transmissão não aceitam envio pelo " \
                         "TeleZapp"
            else:
                motivo = "erro do WhatsApp (%s)" % type(e).__name__
            self.barramento.publicar(ev.EnvioFalhou(
                self.conta.id, conversa_id, texto, motivo,
                devolver_texto=construir is None))
            return
        log.info("texto enviado em %.2fs", time.perf_counter() - inicio)
        self._registrar_enviada(
            resp, conversa_id, texto,
            resposta_a="" if resposta_a.startswith(RESPOSTA_A_STATUS)
            else resposta_a, previa=previa)

    def _prazo_da_conversa(self, conversa_id):
        """Segundos das mensagens temporarias da conversa (0 = desligadas)."""
        with self._trava:
            conv = self._conversas.get(conversa_id)
        return int(conv.temporaria_s) if conv is not None else 0

    @staticmethod
    def _previa_ao_enviar(texto):
        """Com a opcao ligada, a previa do primeiro link do texto."""
        if not previa_links.LIGADAS["enviar"]:
            return {}
        url = previa_links.primeiro_link(texto)
        return previa_links.buscar(url) if url else {}

    def _registrar_enviada(self, resp, conversa_id, texto, resposta_a="",
                           arquivo=None, previa=None, enquete=None,
                           **campos):
        """Guarda e publica a mensagem que o servidor confirmou. `arquivo`
        (origem, mover): copia a midia enviada para o armazem do app."""
        msg = m.Mensagem(self.conta.id, conversa_id, resp.ID, minha=True,
                         data=segundos(resp.Timestamp) or time.time(),
                         texto=texto, estado=m.ENVIADA, resposta_a=resposta_a,
                         **campos)
        msg.expira = m.expira_em(msg.data,
                                 self._prazo_da_conversa(conversa_id))
        if previa:
            m.guardar_extras(msg, previa=previa)
        if enquete:
            m.atualizar_extras(msg, enquete=enquete)
        if arquivo is not None:
            try:
                destino = armazem.guardar_enviada(msg, *arquivo)
                self.banco.registrar_midia(
                    msg.conta_id, msg.conversa_id, msg.id, msg.tipo,
                    destino, os.path.getsize(destino), time.time())
            except OSError:
                log.warning("não consegui guardar a cópia da mídia enviada",
                            exc_info=True)
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
        return msg

    # ------------------------------------------------------ arquivos
    def enviar_arquivo(self, conversa_id, anexo, legenda="", resposta_a="",
                       mencoes=None):
        # thread propria: um upload grande nao pode travar a fila de texto
        threading.Thread(
            target=self._enviar_arquivo,
            args=(conversa_id, anexo, legenda, resposta_a, mencoes),
            daemon=True, name="whatsapp-envio").start()

    def _contexto_da_midia(self, conversa_id, legenda, resposta_a, mencoes):
        """(legenda, ContextInfo ou None) de uma midia enviada como resposta
        e/ou com mencoes na legenda."""
        legenda, jids = self._mencoes_no_texto(legenda, mencoes)
        if resposta_a.startswith(RESPOSTA_A_STATUS):
            resposta_a = ""         # status so recebe resposta de texto
        if not resposta_a and not jids:
            return legenda, None
        from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import ContextInfo
        ctx = self._contexto_da_resposta(conversa_id, resposta_a) \
            if resposta_a else ContextInfo()
        ctx.mentionedJID.extend(jids)
        return legenda, ctx

    @staticmethod
    def _com_contexto(mensagem, ctx):
        """Poe o ContextInfo (citacao, mencoes) na midia ja montada."""
        if ctx is None:
            return mensagem
        for nome in ("imageMessage", "videoMessage", "audioMessage",
                     "documentMessage"):
            if mensagem.HasField(nome):
                getattr(mensagem, nome).contextInfo.MergeFrom(ctx)
                break
        return mensagem

    def _enviar_por_arquivo(self, conversa_id, anexo, legenda):
        """Sobe o arquivo direto do disco, publicando o avanco, e devolve a
        mensagem pronta para enviar."""
        from neonize.utils.enum import MediaType
        tipo = {m.FOTO: MediaType.MediaImage, m.VIDEO: MediaType.MediaVideo,
                m.VOZ: MediaType.MediaAudio, m.AUDIO: MediaType.MediaAudio
                }.get(anexo.tipo, MediaType.MediaDocument)
        chave = "up-" + uuid.uuid4().hex
        fim = threading.Event()
        avisos = [0, -1]          # quantos avancos publicados, ultimo valor
        log.info("envio por arquivo: %d bytes", anexo.tamanho)

        def vigiar():
            ultimo = -1
            while not fim.wait(0.3):
                pct = self.cliente.transfer_progress(chave)
                avisos[1] = pct
                if pct >= 0 and pct != ultimo and pct < 100:
                    ultimo = pct
                    avisos[0] += 1
                    self.barramento.publicar(ev.ProgressoEnvio(
                        self.conta.id, conversa_id, pct))
        vigia = threading.Thread(target=vigiar, daemon=True,
                                 name="whatsapp-vigia-envio")
        vigia.start()
        try:
            up = self.cliente.upload_file(anexo.caminho, tipo, chave)
        finally:
            fim.set()
            vigia.join(2)
            log.info("envio por arquivo terminou: %d avisos de avanço "
                     "(último valor lido %d)", avisos[0], avisos[1])
        self.barramento.publicar(ev.ProgressoEnvio(self.conta.id,
                                                   conversa_id, 100))
        return self._mensagem_de_midia(anexo, legenda, up)

    def _mensagem_de_midia(self, anexo, legenda, up=None):
        """Mensagem de midia montada a mao: o neonize so sabe montar foto e
        documento sem FFmpeg. `up`: o envio ja feito (por arquivo); sem ele a
        midia e lida inteira e enviada de uma vez."""
        from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
            AudioMessage, DocumentMessage, ImageMessage, Message,
            VideoMessage)
        if up is None:
            with open(anexo.caminho, "rb") as f:
                dados = f.read()
            up = self.cliente.upload(dados)
        comum = dict(URL=up.url, directPath=up.DirectPath,
                     fileEncSHA256=up.FileEncSHA256, fileLength=up.FileLength,
                     fileSHA256=up.FileSHA256, mediaKey=up.MediaKey)
        if anexo.tipo == m.FOTO:
            return Message(imageMessage=ImageMessage(
                caption=legenda or None, mimetype=anexo.mime or "image/jpeg",
                width=anexo.largura, height=anexo.altura, **comum))
        if anexo.tipo == m.DOCUMENTO:
            return Message(documentMessage=DocumentMessage(
                caption=legenda or None, fileName=anexo.nome,
                title=anexo.nome,
                mimetype=anexo.mime or "application/octet-stream", **comum))
        if anexo.tipo == m.VIDEO:
            return Message(videoMessage=VideoMessage(
                caption=legenda, seconds=anexo.segundos,
                width=anexo.largura, height=anexo.altura,
                mimetype="video/mp4", **comum))
        voz = anexo.tipo == m.VOZ
        return Message(audioMessage=AudioMessage(
            seconds=anexo.segundos, PTT=voz,
            mimetype="audio/ogg; codecs=opus" if voz else
            (anexo.mime or "audio/mpeg"), **comum))

    def _anexo_que_o_whatsapp_toca(self, anexo):
        """WAV e FLAC nao tocam no WhatsApp: pelo botao de anexar vao como
        documento (o arquivo original); colados na caixa viram um audio
        Ogg/Opus comum."""
        if not envio.audio_que_o_whatsapp_nao_toca(anexo):
            return anexo
        if anexo.colado:
            try:
                novo = envio.converter_para_opus(anexo, config.pasta_temporaria())
                log.info("audio %s convertido para Ogg/Opus (%d bytes)",
                         os.path.splitext(anexo.nome)[1], novo.tamanho)
                return novo
            except envio.ErroEnvio:
                log.warning("conversao do audio falhou; vai como documento",
                            exc_info=True)
        return envio.como_documento(anexo)

    def _enviar_arquivo(self, conversa_id, anexo, legenda, resposta_a="",
                        mencoes=None):
        inicio = time.perf_counter()
        original = legenda
        try:
            if not self._conectada or self.cliente is None:
                raise ConnectionError("sem conexão")
            anexo = self._anexo_que_o_whatsapp_toca(anexo)
            jid = self._jid(conversa_id)
            prazo = self._prazo_da_conversa(conversa_id)
            legenda, ctx = self._contexto_da_midia(
                conversa_id, legenda, resposta_a, mencoes)
            if anexo.tamanho >= LIMITE_ENVIO_POR_ARQUIVO and \
                    self._tem_transferencias():
                resp = self.cliente.send_message(
                    jid, com_expiracao(self._com_contexto(
                        self._enviar_por_arquivo(conversa_id, anexo, legenda),
                        ctx), prazo))
            elif prazo or ctx is not None:
                # com mensagens temporarias, resposta ou mencao a mensagem e
                # montada a mao, para levar o prazo e o contexto
                resp = self.cliente.send_message(
                    jid, com_expiracao(self._com_contexto(
                        self._mensagem_de_midia(anexo, legenda), ctx),
                        prazo))
            elif anexo.tipo == m.FOTO:
                resp = self.cliente.send_image(jid, anexo.caminho,
                                               caption=legenda or None)
            elif anexo.tipo in (m.VIDEO, m.VOZ, m.AUDIO):
                resp = self.cliente.send_message(
                    jid, self._mensagem_de_midia(anexo, legenda))
            else:
                resp = self.cliente.send_document(
                    jid, anexo.caminho, caption=legenda or None,
                    filename=anexo.nome, mimetype=anexo.mime)
        except Exception as e:
            log.warning("envio de %s falhou: %s: %s", anexo.tipo,
                        type(e).__name__, str(e)[:300], exc_info=True)
            motivo = "sem conexão" if isinstance(e, ConnectionError) else \
                "erro do WhatsApp (%s)" % type(e).__name__
            self.barramento.publicar(ev.EnvioFalhou(
                self.conta.id, conversa_id, original, motivo,
                devolver_texto=False, tipo=anexo.tipo))
            return
        log.info("%s enviado em %.2fs (%d bytes, %s, %ds)", anexo.tipo,
                 time.perf_counter() - inicio, anexo.tamanho, anexo.mime,
                 anexo.segundos)
        self._registrar_enviada(
            resp, conversa_id, original, tipo=anexo.tipo,
            resposta_a="" if resposta_a.startswith(RESPOSTA_A_STATUS)
            else resposta_a,
            segundos=anexo.segundos, nome_arquivo=anexo.nome,
            tamanho=anexo.tamanho,
            arquivo=(anexo.caminho, anexo.temporario))

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
        # status: o recibo de "visto" vai para o chat de status
        chat = _jid_obj("status", "broadcast") \
            if conversa_id.startswith(PREFIXO_STATUS) else self._jid(conversa_id)
        por_remetente = {}
        for mid, remetente in pendentes:
            chave = (remetente.User, remetente.Server)
            por_remetente.setdefault(chave, (remetente, []))[1].append(mid)
        for remetente, ids in por_remetente.values():
            self.cliente.mark_read(*ids, chat=chat, sender=remetente,
                                   receipt=ReceiptType.READ)
        log.info("leitura confirmada ao WhatsApp (%d mensagens)",
                 len(pendentes))

    def marcar_ouvida(self, mensagem):
        """A pessoa tocou esta voz ou audio recebido: o WhatsApp recebe o
        recibo de reproduzida (a marca de ouvida aparece no celular)."""
        if mensagem.minha:
            return
        self._fila.put(lambda: self._enviar_ouvida(mensagem))

    def _enviar_ouvida(self, x):
        from neonize.utils.enum import ReceiptType
        if self.cliente is None or not self._conectada:
            return
        remetente = x.remetente or (
            x.conversa_id if not x.conversa_id.endswith("@g.us") else "")
        if not remetente:
            return
        # com a confirmacao de leitura desligada o WhatsApp so avisa os
        # proprios aparelhos, sem contar a quem enviou
        recibo = ReceiptType.PLAYED
        try:
            valores = self.privacidade() or {}
            if valores.get("readreceipts") == "none":
                recibo = ReceiptType.PLAYED_SELF
        except Exception:
            pass
        self.cliente.mark_read(
            x.id, chat=self._jid(x.conversa_id),
            sender=_jid_obj(*jid_de_texto(remetente)), receipt=recibo)
        log.info("reprodução confirmada ao WhatsApp (%s)", recibo.name)

    def _id_do_participante(self, jid):
        """Numero de quem recebeu ou leu (troca o endereco LID pelo numero
        quando o WhatsApp informa)."""
        return self._id_da_conversa(jid)

    # ------------------------------------------------------------- recibos
    # ------------------------------------------------- chamadas de voz
    # O meowcaller vai dentro da DLL de teste do neonize e usa este mesmo
    # cliente; sem essa DLL as chamadas ficam indisponiveis.
    @property
    def suporta_chamadas(self):
        return self._voz is not None and self._voz.pronta

    def _preparar_chamadas(self):
        """Antes de conectar: liga o meowcaller no cliente, se a DLL tiver."""
        if self._voz is not None:
            self._voz.parar()
            self._voz = None
        try:
            from telezapp.provedores.chamadas_whatsapp import (
                ChamadasWhatsApp, Ponte)
            if not Ponte.disponivel():
                log.info("a DLL do neonize não tem o meowcaller: sem "
                         "chamadas de voz do WhatsApp")
                return
            Ponte.configurar(True)
            self._voz = ChamadasWhatsApp(
                Ponte(self.cliente.uuid), self.conta.id, self.barramento,
                self._conversa_do_peer, self._nome_da_conversa,
                self._destino_da_chamada)
            self._voz.iniciar()
            log.info("chamadas de voz do WhatsApp ligadas")
        except Exception:
            log.exception("erro ao preparar as chamadas do WhatsApp")
            self._voz = None

    def _conversa_do_peer(self, peer):
        usuario, servidor = jid_de_texto(peer)
        return self._id_da_conversa(_jid_obj(usuario, servidor))

    def _nome_da_conversa(self, cid):
        conv = self._conversas.get(cid)
        return conv.nome if conv is not None and conv.nome else ""

    def _destino_da_chamada(self, cid):
        """O texto que a DLL liga: o numero, ou o endereco LID."""
        usuario, servidor = jid_de_texto(cid)
        return usuario if servidor == "s.whatsapp.net" else             "%s@%s" % (usuario, servidor)

    def _comando_de_chamada(self, metodo, conversa_id, *args):
        if not self.suporta_chamadas or "@g.us" in conversa_id or                 "@newsletter" in conversa_id:
            self._avisar("Chamadas de voz não estão disponíveis nesta "
                         "conversa.")
            return
        threading.Thread(target=getattr(self._voz, metodo),
                         args=(conversa_id,) + args, daemon=True,
                         name="chamada-" + metodo).start()

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
        if self._voz is None:
            return [], []
        return self._voz.dispositivos()

    # ------------------------------------------------------------ chamadas
    def _tem_tag(self, no, tag):
        """A tag aparece em algum lugar da arvore do pacote da chamada?"""
        if no is None:
            return False
        if no.Tag == tag:
            return True
        return any(self._tem_tag(n, tag) for n in no.Nodes)

    def _ao_chamada(self, cliente, e):
        """Alguem esta ligando: o TeleZapp ainda nao atende chamadas do
        WhatsApp, entao so registra na conversa e avisa."""
        try:
            meta = e.basicCallMeta
            chamada = meta.callID
            if not chamada or chamada in self._chamadas:
                return
            criador = meta.callCreator
            eu = self.cliente.get_me().JID if self.cliente else None
            if eu is not None and criador.User == eu.User:
                return                 # liguei de outro aparelho
            if not criador.User and meta.callCreatorAlt.User:
                criador = meta.callCreatorAlt
            cid = self._id_da_conversa(criador)
            video = self._tem_tag(e.data, "video")
            conv = self._conversa(cid, criador, "", False,
                                  float(meta.timestamp or time.time()))
            dados = {"cid": cid, "video": video, "nome": conv.nome,
                     "inicio": float(meta.timestamp or time.time()),
                     "atendida": 0.0}
            self._chamadas[chamada] = dados
            msg = m.Mensagem(
                self.conta.id, cid, "chamada-" + chamada, autor=conv.nome,
                data=dados["inicio"], tipo=m.OUTRO, remetente=cid,
                texto=ch.texto_na_conversa(video, "tocando"))
            with self._trava:
                conv.data = max(conv.data, msg.data)
                conv.nao_lidas += 1
                self._nao_lidas.setdefault(cid, []).append(
                    (msg.id, criador))
            self.banco.salvar_conversas([conv])
            self.banco.salvar_mensagens([msg])
            # sem o aviso de mensagem nova: a janela da chamada avisa
            self.barramento.publicar(ev.MensagemNova(msg, conv,
                                                     silenciosa=True))
            if not self.suporta_chamadas:
                self.barramento.publicar(ev.ChamadaWhatsApp(
                    self.conta.id, cid, conv.nome, video, "tocando",
                    chamada))
        except Exception:
            log.exception("erro ao tratar chamada recebida")

    def _ao_chamada_atendida(self, cliente, e):
        dados = self._chamadas.get(e.basicCallMeta.callID)
        if dados is not None:
            dados["atendida"] = float(e.basicCallMeta.timestamp or
                                      time.time())

    def _ao_chamada_encerrada(self, cliente, e):
        try:
            meta = e.basicCallMeta
            dados = self._chamadas.pop(meta.callID, None)
            if dados is None:
                return
            motivo = (e.reason or "").lower()
            fim = float(meta.timestamp or time.time())
            if dados["atendida"]:
                fase = "atendida"
                segundos = max(0, int(fim - dados["atendida"]))
            elif "reject" in motivo or "declin" in motivo:
                fase, segundos = "recusada", 0
            else:
                fase, segundos = "perdida", 0
            texto = ch.texto_na_conversa(dados["video"], fase, segundos)

            def aplicar(x):
                x.texto = texto
            self._alterar(dados["cid"], "chamada-" + meta.callID, aplicar,
                          "chamada")
            self.barramento.publicar(ev.ChamadaWhatsApp(
                self.conta.id, dados["cid"], dados["nome"], dados["video"],
                fase, meta.callID, segundos))
        except Exception:
            log.exception("erro ao tratar o fim da chamada")

    def _ao_recibo(self, cliente, e):
        try:
            origem = e.MessageSource
            cid = self._id_da_conversa(origem.Chat)
            tipo = int(e.Type)
            if tipo in (RECIBO_LIDO_POR_MIM, RECIBO_OUVIDO_POR_MIM):
                log.info("recibo de outro aparelho meu: %s (%d mensagens)",
                         "lida" if tipo == RECIBO_LIDO_POR_MIM else "ouvida",
                         len(e.MessageIDs))
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
            if tipo == RECIBO_OUVIDO_POR_MIM:
                # voz ou audio recebido que eu toquei em outro aparelho
                for alvo in list(e.MessageIDs):
                    self._alterar(
                        cid, alvo,
                        lambda x: m.atualizar_extras(x, ouvida=True)
                        if not x.minha else None, "ouvida")
                return
            estado = {RECIBO_ENTREGUE: m.ENTREGUE, RECIBO_LIDO: m.LIDA,
                      RECIBO_OUVIDO: m.REPRODUZIDA}.get(tipo)
            if estado is None and not origem.IsFromMe:
                log.info("recibo de tipo %d ignorado (%d mensagens)", tipo,
                         len(e.MessageIDs))
            if estado is None or origem.IsFromMe:
                return
            if tipo == RECIBO_OUVIDO:
                log.info("recibo de reproduzida (%d mensagens)",
                         len(e.MessageIDs))
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
                if c.HasField("archived"):
                    conv.arquivada = bool(c.archived)
                if c.HasField("locked"):
                    conv.trancada = bool(c.locked)
                if c.HasField("pinned"):
                    conv.fixada = int(c.pinned) > 0
                if c.HasField("muteEndTime"):
                    conv.silenciada_ate = fim_do_silencio(c.muteEndTime)
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
        log.info("histórico guardado: %d conversas e %d mensagens em %.2fs "
                 "(%d arquivadas, %d trancadas no celular)",
                 len(convs), len(msgs), time.perf_counter() - inicio,
                 sum(1 for c in convs if c.arquivada),
                 sum(1 for c in convs if c.trancada))
        if convs:
            self._publicar_conversas()
            self._fila.put(self._conferir_arquivadas)

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

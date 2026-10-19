# SPDX-License-Identifier: GPL-3.0-or-later
"""Provedor do WhatsApp com mensagens protobuf de verdade do neonize e um
cliente simulado (sem rede)."""
import os
import queue
import threading
import types

import pytest

pytest.importorskip("neonize")

from neonize.proto import Neonize_pb2 as N  # noqa: E402
from neonize.proto.waE2E import WAWebProtobufsE2E_pb2 as E  # noqa: E402
from neonize.proto.waHistorySync import (  # noqa: E402
    WAWebProtobufsHistorySync_pb2 as H)

from telezapp.armazenamento.banco import Banco  # noqa: E402
from telezapp.nucleo import eventos as ev  # noqa: E402
from telezapp.nucleo import modelos as m  # noqa: E402
from telezapp.provedores import base, whatsapp as wa  # noqa: E402

TS = 1792000000


def jid(user, server="s.whatsapp.net"):
    return N.JID(User=user, Server=server)


def evento(id, mensagem, chat="5551988887777", de_mim=False, grupo=False,
           remetente=None, pushname="Ana", ts=TS, servidor=None):
    servidor = servidor or ("g.us" if grupo else "s.whatsapp.net")
    origem = N.MessageSource(Chat=jid(chat, servidor), IsFromMe=de_mim,
                             IsGroup=grupo,
                             Sender=jid(remetente or chat, servidor))
    info = N.MessageInfo(MessageSource=origem, ID=id, Pushname=pushname,
                         Timestamp=ts)
    return N.Message(Info=info, Message=mensagem)


# ------------------------------------------------------------ conversao
def test_texto_simples_e_estendido_com_resposta():
    msg, rem = wa.converter(evento("A1", E.Message(conversation="Oi")),
                            "w1", "c")
    assert (msg.id, msg.tipo, msg.texto, msg.autor, msg.minha) == (
        "A1", m.TEXTO, "Oi", "Ana", False)
    assert msg.data == TS and rem == "5551988887777@s.whatsapp.net"
    ctx = E.ContextInfo(stanzaID="A0")
    est = E.Message(extendedTextMessage=E.ExtendedTextMessage(
        text="sim", contextInfo=ctx))
    msg, _ = wa.converter(evento("A2", est), "w1", "c")
    assert msg.texto == "sim" and msg.resposta_a == "A0"


def test_timestamp_em_milissegundos():
    msg, _ = wa.converter(evento("A3", E.Message(conversation="x"),
                                 ts=TS * 1000), "w1", "c")
    assert msg.data == TS


def test_midias():
    voz = E.Message(audioMessage=E.AudioMessage(PTT=True, seconds=9,
                                                fileLength=3000))
    assert wa.converter(evento("B1", voz), "w1", "c")[0].tipo == m.VOZ
    aud = E.Message(audioMessage=E.AudioMessage(seconds=200))
    assert wa.converter(evento("B2", aud), "w1", "c")[0].tipo == m.AUDIO
    foto = E.Message(imageMessage=E.ImageMessage(caption="praia"))
    x = wa.converter(evento("B3", foto), "w1", "c")[0]
    assert (x.tipo, x.texto) == (m.FOTO, "praia")
    doc = E.Message(documentMessage=E.DocumentMessage(
        fileName="a.pdf", fileLength=2048))
    x = wa.converter(evento("B4", doc), "w1", "c")[0]
    assert (x.tipo, x.nome_arquivo, x.tamanho) == (m.DOCUMENTO, "a.pdf",
                                                   2048)
    vid = E.Message(videoMessage=E.VideoMessage(seconds=12, caption="olha"))
    x = wa.converter(evento("B5", vid), "w1", "c")[0]
    assert (x.tipo, x.segundos, x.texto) == (m.VIDEO, 12, "olha")


def test_envelopes_sao_abertos():
    interna = E.Message(conversation="enviada do celular")
    emb = E.Message(deviceSentMessage=E.DeviceSentMessage(message=interna))
    x = wa.converter(evento("C1", emb, de_mim=True), "w1", "c")[0]
    assert x.texto == "enviada do celular" and x.minha and \
        x.estado == m.ENVIADA
    temp = E.Message(ephemeralMessage=E.FutureProofMessage(
        message=E.Message(conversation="temporária")))
    assert wa.converter(evento("C2", temp), "w1", "c")[0].texto == \
        "temporária"


def test_mensagens_so_de_controle_sao_ignoradas():
    chave = E.Message(senderKeyDistributionMessage=(
        E.SenderKeyDistributionMessage(groupID="g")))
    assert wa.converter(evento("D1", chave), "w1", "c") == (None, "")
    reacao = E.Message(reactionMessage=E.ReactionMessage(text="👍"))
    assert wa.converter(evento("D2", reacao), "w1", "c")[0] is None


def test_resumo_do_historico_sem_conteudo():
    h = H.HistorySync(syncType=0, progress=50, conversations=[
        H.Conversation(ID="5551@s.whatsapp.net", name="Ana", unreadCount=2,
                       messages=[H.HistorySyncMsg(), H.HistorySyncMsg()]),
        H.Conversation(ID="123@g.us"),
        H.Conversation(ID="999@lid")])
    r = wa.resumo_historico(h)
    assert r == {"tipo": 0, "conversas": 3, "mensagens": 2, "com_nome": 1,
                 "grupos": 1, "lid": 1, "nao_lidas": 2, "pushnames": 0,
                 "progresso": 50}


# ------------------------------------------------- provedor de verdade
class Registro:
    def __init__(self):
        self.funcoes = {}
        self.funcao_qr = None

    def __call__(self, classe):
        return lambda f: self.funcoes.__setitem__(classe.__name__, f)

    def qr(self, f):
        self.funcao_qr = f


class ClienteFalso:
    def __init__(self):
        self.event = Registro()
        self.parar = threading.Event()
        self.enviadas, self.lidas, self.pareamentos = [], [], []
        self.contact = types.SimpleNamespace(get_contact=self._contato)

    outros = {}      # usuario -> dados de ContactInfo (perfil, empresa...)

    def _contato(self, j):
        nomes = {"5551988887777": "Ana Silva"}
        if j.User in self.outros:
            return N.ContactInfo(Found=True, **self.outros[j.User])
        return N.ContactInfo(Found=j.User in nomes,
                             FullName=nomes.get(j.User, ""))

    def connect(self):
        self.parar.wait(10)

    def stop(self):
        self.parar.set()

    def get_me(self):
        return N.Device(JID=jid("5551999998888"), PushName="Fábio")

    def get_pn_from_lid(self, j):
        return jid("5551977776666") if j.User == "lid1" else N.JID()

    empresas = {}    # usuario -> nome verificado devolvido por get_user_info

    def get_user_info(self, *jids):
        """Como a whatsmeow: o nome verificado vai para o cadastro de
        contatos (BusinessName) e nao volta em UserInfo."""
        saida = []
        for j in jids:
            if j.User in self.empresas:
                self.outros[j.User] = dict(BusinessName=self.empresas[j.User])
            saida.append(N.GetUserInfoSingleReturnFunction(
                JID=j, UserInfo=N.UserInfo()))
        return saida

    def get_newsletter_info(self, j):
        return N.NewsletterMetadata(ThreadMeta=N.NewsletterThreadMetadata(
            Name=N.NewsletterText(Text="Canal de Notícias")))

    grupos = ()      # GroupInfo de get_joined_groups

    def get_joined_groups(self):
        if self.grupos is None:
            raise RuntimeError("sem rede")
        return list(self.grupos)

    def get_group_info(self, j):
        return N.GroupInfo(GroupName=N.GroupName(Name="Família"))

    def PairPhone(self, telefone, push, nome, tipo):
        self.pareamentos.append(telefone)
        if len(self.pareamentos) == 1:
            raise RuntimeError("ainda conectando")
        return "ABCD-EFGH"

    def send_message(self, para, mensagem, **kw):
        if mensagem.conversation == "falhar":
            raise RuntimeError("erro")
        if getattr(self, "recusar_479", 0) > 0 and (
                mensagem.HasField("buttonsResponseMessage") or
                mensagem.HasField("documentWithCaptionMessage") or
                mensagem.HasField("templateButtonReplyMessage")):
            self.recusar_479 -= 1
            raise RuntimeError("server returned error 479")
        self.enviadas.append((wa.jid_texto(para), mensagem))
        return N.SendResponse(ID="EU1", Timestamp=TS + 60)

    def upload(self, dados, media_type=None):
        self.uploads = getattr(self, "uploads", [])
        self.uploads.append(len(dados))
        return types.SimpleNamespace(
            url="https://mmg/x", DirectPath="/d", FileEncSHA256=b"e",
            FileLength=len(dados), FileSHA256=b"s", MediaKey=b"k")

    def send_image(self, para, arquivo, caption=None, **kw):
        self.enviadas.append((wa.jid_texto(para), ("imagem", arquivo,
                                                   caption)))
        return N.SendResponse(ID="IMG1", Timestamp=TS + 60)

    def send_document(self, para, arquivo, caption=None, filename=None,
                      mimetype=None, **kw):
        if caption == "falhar":
            raise RuntimeError("erro")
        self.enviadas.append((wa.jid_texto(para), (
            "documento", arquivo, caption, filename, mimetype)))
        return N.SendResponse(ID="DOC1", Timestamp=TS + 60)

    def download_any(self, mensagem, path=None):
        self.baixadas = getattr(self, "baixadas", [])
        self.baixadas.append(mensagem)
        if getattr(self, "falha_download", False):
            raise RuntimeError("expirou")
        with open(path, "wb") as f:
            f.write(b"conteudo")

    def send_app_state(self, patch):
        self.patches = getattr(self, "patches", [])
        self.patches.append(patch)

    def revoke_message(self, chat, sender, message_id):
        self.revogadas = getattr(self, "revogadas", [])
        self.revogadas.append((wa.jid_texto(chat), message_id))

    def mark_read(self, *ids, chat, sender, receipt):
        self.lidas.append((list(ids), wa.jid_texto(chat), sender.User))
        self.recibos = getattr(self, "recibos", [])
        self.recibos.append(receipt.name)


@pytest.fixture
def dados_midia(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path / "dados"))
    return tmp_path / "dados"


@pytest.fixture
def amb(tmp_path, monkeypatch):
    monkeypatch.setattr(wa.time, "sleep", lambda s: None)
    fila = queue.Queue()
    b = ev.Barramento()
    b.ouvir(fila.put)
    banco = Banco(str(tmp_path / "w.db"))
    cliente = ClienteFalso()
    conta = m.Conta("w1", "whatsapp")
    p = wa.ProvedorWhatsApp(conta, b, banco, pasta_sessoes=str(tmp_path),
                            fabrica_cliente=lambda: cliente)
    p.iniciar()
    for _ in range(100):
        if cliente.event.funcao_qr:
            break
        threading.Event().wait(0.02)
    yield types.SimpleNamespace(p=p, c=cliente, fila=fila, banco=banco,
                                f=cliente.event.funcoes)
    p.parar()
    banco.fechar()


def esperar(fila, tipo):
    while True:
        e = fila.get(timeout=5)
        if isinstance(e, tipo):
            return e


def test_qr_e_codigo_de_pareamento(amb):
    amb.c.event.funcao_qr(amb.c, b"2@abc,def")
    assert esperar(amb.fila, ev.QrPareamento).codigo == "2@abc,def"
    amb.p.pedir_codigo_pareamento("+55 (51) 99999-8888")
    cod = esperar(amb.fila, ev.CodigoPareamento)
    assert cod.codigo == "ABCD-EFGH" and not cod.erro
    assert amb.c.pareamentos == ["5551999998888"] * 2   # tentou de novo


def test_conectar_receber_responder_e_ler(amb):
    amb.f["Connected"](amb.c, N.Connected())
    pronta = esperar(amb.fila, ev.ContaPronta)
    assert (pronta.nome, pronta.telefone) == ("Fábio", "+5551999998888")

    amb.f["Message"](amb.c, evento("M1", E.Message(conversation="Oi")))
    nova = esperar(amb.fila, ev.MensagemNova)
    assert nova.conversa.nome == "Ana Silva" and nova.conversa.nao_lidas == 1
    assert nova.mensagem.conversa_id == "5551988887777@s.whatsapp.net"
    # o mesmo evento repetido nao duplica
    amb.f["Message"](amb.c, evento("M1", E.Message(conversation="Oi")))
    assert amb.banco.conversas("w1")[0].nao_lidas == 1

    cid = "5551988887777@s.whatsapp.net"
    amb.p.enviar_texto(cid, "tudo bem?", resposta_a="M1")
    enviada = esperar(amb.fila, ev.MensagemNova)
    assert enviada.enviada_daqui and enviada.mensagem.id == "EU1"
    para, proto = amb.c.enviadas[0]
    ctx = proto.extendedTextMessage.contextInfo
    assert para == cid and ctx.stanzaID == "M1" and \
        ctx.participant == cid and ctx.quotedMessage.conversation == "Oi"

    amb.p.marcar_como_lida(cid)
    amb.p.enviar_texto(cid, "x")       # garante que a fila andou
    esperar(amb.fila, ev.MensagemNova)
    assert amb.c.lidas == [(["M1"], cid, "5551988887777")]
    assert amb.banco.conversas("w1")[0].nao_lidas == 0

    amb.f["Receipt"](amb.c, N.Receipt(
        MessageSource=N.MessageSource(Chat=jid("5551988887777")),
        MessageIDs=["EU1"], Type=1))
    est = esperar(amb.fila, ev.EstadosMensagens)
    assert (est.ids, est.estado) == (["EU1"], m.ENTREGUE)
    amb.f["Receipt"](amb.c, N.Receipt(
        MessageSource=N.MessageSource(Chat=jid("5551988887777")),
        MessageIDs=["EU1"], Type=4))
    assert esperar(amb.fila, ev.EstadosMensagens).estado == m.LIDA
    # um "entregue" atrasado nao volta o estado
    assert amb.banco.mudar_estado("w1", cid, ["EU1"], m.ENTREGUE) == []


def test_grupo_busca_o_nome_e_lid_vira_numero(amb):
    amb.f["Message"](amb.c, evento(
        "G1", E.Message(conversation="oi grupo"), chat="12345", grupo=True,
        remetente="5551988887777"))
    nova = esperar(amb.fila, ev.MensagemNova)
    assert nova.mensagem.autor == "Ana Silva"
    lista = esperar(amb.fila, ev.ConversasAtualizadas).conversas
    assert lista[0].nome == "Família" and lista[0].tipo == "grupo"

    e = evento("L1", E.Message(conversation="via lid"))
    e.Info.MessageSource.Chat.CopyFrom(jid("lid1", "lid"))
    amb.f["Message"](amb.c, e)
    assert esperar(amb.fila, ev.MensagemNova).mensagem.conversa_id == \
        "5551977776666@s.whatsapp.net"


def test_grupo_renomeado_atualiza_a_conversa(amb):
    amb.f["Message"](amb.c, evento(
        "G9", E.Message(conversation="oi"), chat="12345", grupo=True,
        remetente="5551988887777"))
    esperar(amb.fila, ev.MensagemNova)
    assert esperar(amb.fila, ev.ConversasAtualizadas).conversas[0].nome == \
        "Família"
    cid = "12345@g.us"

    amb.f["GroupInfoEvent"](amb.c, N.GroupInfoEvent(
        JID=jid("12345", "g.us"), Name=N.GroupName(Name="Família da Ana")))
    lista = esperar(amb.fila, ev.ConversasAtualizadas).conversas
    assert [c.nome for c in lista if c.id == cid] == ["Família da Ana"]
    assert [c.nome for c in amb.banco.conversas("w1") if c.id == cid] == \
        ["Família da Ana"]

    # o mesmo nome de novo, ou uma mudanca que nao e de nome: nada
    amb.f["GroupInfoEvent"](amb.c, N.GroupInfoEvent(
        JID=jid("12345", "g.us"), Name=N.GroupName(Name="Família da Ana")))
    amb.f["GroupInfoEvent"](amb.c, N.GroupInfoEvent(
        JID=jid("12345", "g.us"), Topic=N.GroupTopic(Topic="novo assunto")))
    assert amb.fila.empty()

    # ao entrar de novo no grupo o WhatsApp manda o nome atual
    amb.f["JoinedGroup"](amb.c, N.JoinedGroup(GroupInfo=N.GroupInfo(
        JID=jid("12345", "g.us"), GroupName=N.GroupName(Name="Os Silva"))))
    lista = esperar(amb.fila, ev.ConversasAtualizadas).conversas
    assert [c.nome for c in lista if c.id == cid] == ["Os Silva"]
    # grupo que ainda nao tem conversa: ignora
    amb.f["GroupInfoEvent"](amb.c, N.GroupInfoEvent(
        JID=jid("777", "g.us"), Name=N.GroupName(Name="Outro")))
    assert amb.fila.empty()


def test_nomes_de_grupos_sao_conferidos_depois_de_ficar_fora(amb):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    amb.f["Message"](amb.c, evento(
        "G8", E.Message(conversation="oi"), chat="12345", grupo=True,
        remetente="5551988887777"))
    esperar(amb.fila, ev.MensagemNova)
    assert esperar(amb.fila, ev.ConversasAtualizadas).conversas[0].nome == \
        "Família"
    # o grupo foi renomeado com o app fechado; outro grupo nao mudou e um
    # terceiro nao tem conversa: so o primeiro muda
    amb.c.grupos = [
        N.GroupInfo(JID=jid("12345", "g.us"),
                    GroupName=N.GroupName(Name="Família Silva")),
        N.GroupInfo(JID=jid("777", "g.us"),
                    GroupName=N.GroupName(Name="Sem conversa"))]
    amb.f["OfflineSyncCompleted"](amb.c, N.OfflineSyncCompleted(Count=0))
    lista = esperar(amb.fila, ev.ConversasAtualizadas).conversas
    assert [c.nome for c in lista if c.id == "12345@g.us"] == ["Família Silva"]
    assert [c.nome for c in amb.banco.conversas("w1")
            if c.id == "12345@g.us"] == ["Família Silva"]

    # de novo (ex.: F5), sem mudanca: nada novo; e sem rede: nao quebra
    amb.p.atualizar_conversas()
    esperar(amb.fila, ev.ConversasAtualizadas)
    amb.c.grupos = None
    amb.p.atualizar_conversas()
    esperar(amb.fila, ev.ConversasAtualizadas)
    amb.p.enviar_texto("5551@s.whatsapp.net", "garante que a fila andou")
    esperar(amb.fila, ev.MensagemNova)
    assert amb.fila.empty()


def test_falha_de_envio_e_lida_em_outro_aparelho(amb):
    amb.p.enviar_texto("5551@s.whatsapp.net", "sem conexão ainda")
    assert esperar(amb.fila, ev.EnvioFalhou).motivo == "sem conexão"
    amb.f["Connected"](amb.c, N.Connected())
    amb.p.enviar_texto("5551@s.whatsapp.net", "falhar")
    assert "erro do WhatsApp" in esperar(amb.fila, ev.EnvioFalhou).motivo

    amb.f["Message"](amb.c, evento("R1", E.Message(conversation="a")))
    esperar(amb.fila, ev.MensagemNova)
    amb.f["Receipt"](amb.c, N.Receipt(
        MessageSource=N.MessageSource(Chat=jid("5551988887777"),
                                      IsFromMe=True),
        MessageIDs=["R1"], Type=5))
    convs = esperar(amb.fila, ev.ConversasAtualizadas).conversas
    assert [c.nao_lidas for c in convs] == [0]




# ------------------------------------------------------------- historico
def wmi(id, texto, de_mim=False, ts=TS, status=0, chat="5551988887777"):
    from neonize.proto.waWeb import WAWebProtobufsWeb_pb2 as W
    from neonize.proto.waCommon import WACommon_pb2 as C
    return W.WebMessageInfo(
        key=C.MessageKey(remoteJID=chat + "@s.whatsapp.net", fromMe=de_mim,
                         ID=id),
        message=E.Message(conversation=texto), messageTimestamp=ts,
        status=status, pushName="Ana")


def test_props_pedem_o_periodo_escolhido():
    assert not wa.props_do_aparelho("recentes").requireFullSync
    p = wa.props_do_aparelho("365")
    assert p.requireFullSync and p.historySyncConfig.fullSyncDaysLimit == 365
    assert p.os == "TeleZapp"


def test_historico_guarda_conversas_nomes_e_mensagens(amb):
    import time as t
    agora = int(t.time())
    h = H.HistorySync(
        syncType=0,
        pushnames=[H.Pushname(ID="5551966665555@s.whatsapp.net",
                              pushname="Bia")],
        phoneNumberToLidMappings=[H.PhoneNumberToLIDMapping(
            lidJID="77@lid", pnJID="5551966665555@s.whatsapp.net")],
        conversations=[
            H.Conversation(ID="5551988887777@s.whatsapp.net", unreadCount=1,
                           conversationTimestamp=agora, messages=[
                               H.HistorySyncMsg(message=wmi("H1", "antiga",
                                                            ts=agora - 60)),
                               H.HistorySyncMsg(message=wmi(
                                   "H2", "minha", de_mim=True, status=4,
                                   ts=agora - 30)),
                               H.HistorySyncMsg(message=wmi("H3", "nova",
                                                            ts=agora - 10)),
                               H.HistorySyncMsg(message=wmi(
                                   "H0", "velha demais",
                                   ts=agora - 400 * 86400))]),
            H.Conversation(ID="77@lid", conversationTimestamp=agora - 5),
            H.Conversation(ID="123@g.us", name="Família"),
            H.Conversation(ID="status@broadcast"),
            H.Conversation(ID="999@newsletter")])
    amb.p.historico = "365"
    amb.p.guardar_historico(h)
    convs = {c.id: c for c in amb.banco.conversas("w1")}
    assert set(convs) == {"5551988887777@s.whatsapp.net",
                          "5551966665555@s.whatsapp.net", "123@g.us"}
    assert convs["5551988887777@s.whatsapp.net"].nome == "Ana Silva"
    assert convs["5551988887777@s.whatsapp.net"].nao_lidas == 1
    assert convs["5551966665555@s.whatsapp.net"].nome == "Bia"
    assert convs["123@g.us"].nome == "Família"
    msgs = amb.banco.mensagens("w1", "5551988887777@s.whatsapp.net")
    assert [x.id for x in msgs] == ["H1", "H2", "H3"]   # H0 fora do periodo
    assert msgs[1].minha and msgs[1].estado == m.LIDA
    assert esperar(amb.fila, ev.ConversasAtualizadas).conversas

    # abrir a conversa marca como lida a ultima recebida, vinda do historico
    amb.f["Connected"](amb.c, N.Connected())
    amb.p.marcar_como_lida("5551988887777@s.whatsapp.net")
    amb.p.enviar_texto("5551988887777@s.whatsapp.net", "x")
    esperar(amb.fila, ev.MensagemNova)
    assert amb.c.lidas == [(["H3"], "5551988887777@s.whatsapp.net",
                            "5551988887777")]


def test_recentes_guarda_tudo_que_vier(amb):
    h = H.HistorySync(syncType=3, conversations=[H.Conversation(
        ID="5551988887777@s.whatsapp.net", messages=[H.HistorySyncMsg(
            message=wmi("V1", "bem antiga", ts=TS - 3000 * 86400))])])
    amb.p.guardar_historico(h)
    assert [x.id for x in amb.banco.mensagens(
        "w1", "5551988887777@s.whatsapp.net")] == ["V1"]


def test_depois_de_desconectada_ignora_qr(amb):
    amb.f["LoggedOut"](amb.c, N.LoggedOut())
    e = esperar(amb.fila, ev.EstadoConta)
    while e.estado != ev.PRECISA_LOGIN:
        e = esperar(amb.fila, ev.EstadoConta)
    assert e.detalhe == wa.DESCONECTADA_PELO_CELULAR
    amb.c.event.funcao_qr(amb.c, b"2@novo")
    import queue as q
    with pytest.raises(q.Empty):
        while True:
            x = amb.fila.get(timeout=0.3)
            assert not isinstance(x, ev.QrPareamento)


def test_sincronia_inicial_sem_avisos_e_resumo(amb):
    amb.f["Connected"](amb.c, N.Connected())
    amb.f["Message"](amb.c, evento("S1", E.Message(conversation="a")))
    amb.f["Message"](amb.c, evento("S2", E.Message(conversation="b")))
    assert esperar(amb.fila, ev.MensagemNova).silenciosa
    assert esperar(amb.fila, ev.MensagemNova).silenciosa
    amb.f["OfflineSyncCompleted"](amb.c, N.OfflineSyncCompleted(Count=2))
    assert esperar(amb.fila, ev.SincronizacaoConcluida).quantas == 2
    amb.f["Message"](amb.c, evento("S3", E.Message(conversation="c")))
    nova = esperar(amb.fila, ev.MensagemNova)
    assert not nova.silenciosa
    assert amb.banco.mensagens("w1", nova.mensagem.conversa_id)[-1] \
        .remetente == "5551988887777@s.whatsapp.net"


def test_grupo_do_historico_marca_lida_com_cada_remetente(amb):
    from neonize.proto.waWeb import WAWebProtobufsWeb_pb2 as W
    from neonize.proto.waCommon import WACommon_pb2 as C
    import time as t
    agora = int(t.time())

    def do_grupo(id, quem, ts):
        return W.WebMessageInfo(
            key=C.MessageKey(remoteJID="123@g.us", ID=id,
                             participant=quem + ":3@s.whatsapp.net"),
            message=E.Message(conversation="oi"), messageTimestamp=ts)
    h = H.HistorySync(syncType=0, conversations=[H.Conversation(
        ID="123@g.us", name="Família", unreadCount=2, messages=[
            H.HistorySyncMsg(message=do_grupo("G1", "5551", agora - 30)),
            H.HistorySyncMsg(message=do_grupo("G2", "5552", agora - 20)),
            H.HistorySyncMsg(message=do_grupo("G3", "5553", agora - 10))])])
    amb.p.guardar_historico(h)
    amb.f["Connected"](amb.c, N.Connected())
    amb.p.marcar_como_lida("123@g.us")
    amb.p.enviar_texto("123@g.us", "x")
    esperar(amb.fila, ev.MensagemNova)
    lidas = sorted(amb.c.lidas)
    assert lidas == [(["G2"], "123@g.us", "5552"), (["G3"], "123@g.us",
                                                    "5553")]


def test_voz_ouvida_aqui_manda_o_recibo_de_reproduzida(amb):
    amb.f["Connected"](amb.c, N.Connected())
    voz = m.Mensagem("w1", "5551@s.whatsapp.net", "V1", tipo=m.VOZ,
                     segundos=4, data=TS)
    amb.p.marcar_ouvida(voz)
    amb.p.enviar_texto("5551@s.whatsapp.net", "x")     # espera a fila
    esperar(amb.fila, ev.MensagemNova)
    assert amb.c.lidas == [(["V1"], "5551@s.whatsapp.net", "5551")]
    assert amb.c.recibos == ["PLAYED"]
    minha = m.Mensagem("w1", "5551@s.whatsapp.net", "V2", tipo=m.VOZ,
                       minha=True)
    amb.p.marcar_ouvida(minha)                  # a propria voz: nada a avisar
    assert len(amb.c.lidas) == 1


def test_recibos_por_participante_e_status_guardado(amb):
    cid = "120363@g.us"
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    amb.f["Message"](amb.c, evento("EU9", E.Message(conversation="oi"),
                                   chat="120363", grupo=True, de_mim=True,
                                   remetente="5551999998888"))
    esperar(amb.fila, ev.MensagemNova)
    origem = N.MessageSource(Chat=jid("120363", "g.us"), IsGroup=True,
                             Sender=jid("5551988887777"))
    amb.f["Receipt"](amb.c, N.Receipt(MessageSource=origem, MessageIDs=["EU9"],
                                      Type=1, Timestamp=TS + 5))
    amb.f["Receipt"](amb.c, N.Receipt(MessageSource=origem, MessageIDs=["EU9"],
                                      Type=4, Timestamp=TS + 9))
    esperar(amb.fila, ev.EstadosMensagens)
    esperar(amb.fila, ev.EstadosMensagens)
    rec = amb.banco.recibos("w1", cid, "EU9")
    assert [(r[1], r[2]) for r in rec] == [("entregue", TS + 5),
                                           ("lida", TS + 9)]
    assert rec[0][0] == "5551988887777@s.whatsapp.net"

    # status: nao vira conversa, vai para a tabela de status
    origem_st = N.MessageSource(Chat=jid("status", "broadcast"),
                                Sender=jid("5551988887777"))
    amb.f["Message"](amb.c, N.Message(
        Info=N.MessageInfo(MessageSource=origem_st, ID="S1", Pushname="Ana",
                           Timestamp=TS),
        Message=E.Message(conversation="meu status")))
    for _ in range(100):
        if amb.banco.status("w1"):
            break
        threading.Event().wait(0.02)
    st = amb.banco.status("w1")
    assert [(s["id"], s["texto"]) for s in st] == [("S1", "meu status")]
    assert all("status" not in c.id for c in amb.banco.conversas("w1"))


def msg_foto(id, legenda="olha"):
    return E.Message(imageMessage=E.ImageMessage(
        mimetype="image/jpeg", fileLength=8, caption=legenda,
        JPEGThumbnail=b"miniatura", mediaKey=b"k" * 32,
        directPath="/v/t62/abc",
        contextInfo=E.ContextInfo(stanzaID="X")))


def test_ficha_guarda_so_o_necessario_e_baixa(amb, dados_midia):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    amb.f["Message"](amb.c, evento("F1", msg_foto("F1")))
    nova = esperar(amb.fila, ev.MensagemNova).mensagem
    assert nova.tipo == m.FOTO and nova.texto == "olha"
    ficha = amb.banco.ficha("w1", nova.conversa_id, "F1")
    assert ficha and b"miniatura" not in ficha and b"olha" not in ficha
    assert wa.mime_da_ficha(ficha) == "image/jpeg"

    progressos = []
    caminho = amb.p.baixar_arquivo(nova, base_de(nova), progressos.append,
                                   lambda: False)
    assert caminho.endswith(".jpg") and open(caminho, "rb").read() == \
        b"conteudo"
    assert not os.path.exists(caminho + ".parte")
    assert progressos == [0, 100]
    chave = amb.c.baixadas[0].imageMessage
    assert chave.directPath == "/v/t62/abc"


def test_download_cancelado_com_falha_ou_sem_ficha(amb, dados_midia):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    amb.f["Message"](amb.c, evento("F2", msg_foto("F2")))
    nova = esperar(amb.fila, ev.MensagemNova).mensagem
    with pytest.raises(base.DownloadCancelado):
        amb.p.baixar_arquivo(nova, base_de(nova), lambda p: None,
                             lambda: True)
    amb.c.falha_download = True
    with pytest.raises(base.ErroMidia, match="expirado"):
        amb.p.baixar_arquivo(nova, base_de(nova), lambda p: None,
                             lambda: False)
    assert not any(n.endswith(".parte") for _, _, ns in os.walk(
        str(dados_midia)) for n in ns)
    velha = m.Mensagem("w1", "c@s.whatsapp.net", "SEM", tipo=m.FOTO)
    with pytest.raises(base.ErroMidia, match="chegou antes"):
        amb.p.baixar_arquivo(velha, base_de(velha), lambda p: None,
                             lambda: False)


def test_pacote_de_historico_informa_o_progresso(amb):
    h = H.HistorySync(syncType=2, progress=37, conversations=[])
    amb.f["HistorySync"](amb.c, types.SimpleNamespace(Data=h))
    assert esperar(amb.fila, ev.ProgressoSincronia).percentual == 37


def test_historico_guarda_a_ficha_das_midias(amb):
    from neonize.proto.waWeb import WAWebProtobufsWeb_pb2 as W
    from neonize.proto.waCommon import WACommon_pb2 as C
    import time as t
    agora = int(t.time())
    info = W.WebMessageInfo(
        key=C.MessageKey(remoteJID="5551988887777@s.whatsapp.net", ID="H9"),
        message=msg_foto("H9"), messageTimestamp=agora, pushName="Ana")
    amb.p.guardar_historico(H.HistorySync(syncType=3, conversations=[
        H.Conversation(ID="5551988887777@s.whatsapp.net",
                       messages=[H.HistorySyncMsg(message=info)])]))
    assert amb.banco.ficha("w1", "5551988887777@s.whatsapp.net", "H9")


def base_de(msg):
    from telezapp.midia import armazem
    return armazem.caminho_base(msg)


def test_reconecta_sozinho_e_avisa_sincronia_interrompida(tmp_path,
                                                          monkeypatch):
    monkeypatch.setattr(wa, "ESPERAS_RECONEXAO", (0.05,))
    fila = queue.Queue()
    b = ev.Barramento()
    b.ouvir(fila.put)
    banco = Banco(str(tmp_path / "r.db"))
    clientes = []

    class Cai(ClienteFalso):
        def connect(self):
            if len(clientes) == 1:      # a primeira conexao cai logo
                return
            super().connect()

    def fabrica():
        c = Cai()
        clientes.append(c)
        return c

    p = wa.ProvedorWhatsApp(m.Conta("w1", "whatsapp"), b, banco,
                            pasta_sessoes=str(tmp_path),
                            fabrica_cliente=fabrica)
    p._progresso_historico = 57          # o historico estava no meio
    p.iniciar()
    try:
        e = esperar(fila, ev.ProgressoSincronia)
        assert e.interrompida and e.percentual == 57
        for _ in range(200):
            if len(clientes) >= 2:
                break
            threading.Event().wait(0.02)
        assert len(clientes) == 2         # criou outro cliente e reconectou
    finally:
        p.parar()
        banco.fechar()


def test_nao_reconecta_se_a_sessao_foi_aberta_em_outro_lugar(tmp_path,
                                                             monkeypatch):
    monkeypatch.setattr(wa, "ESPERAS_RECONEXAO", (0.05,))
    b = ev.Barramento()
    banco = Banco(str(tmp_path / "s.db"))
    clientes = []

    def fabrica():
        c = ClienteFalso()
        c.connect = lambda: None
        clientes.append(c)
        return c

    p = wa.ProvedorWhatsApp(m.Conta("w1", "whatsapp"), b, banco,
                            pasta_sessoes=str(tmp_path),
                            fabrica_cliente=fabrica)
    p._nao_reconectar = True
    p.iniciar()
    threading.Event().wait(0.4)
    p.parar()
    banco.fechar()
    assert len(clientes) == 1


def _com_mencoes(texto, *jids):
    ctx = E.ContextInfo(mentionedJID=list(jids))
    return E.Message(extendedTextMessage=E.ExtendedTextMessage(
        text=texto, contextInfo=ctx))


def test_converter_guarda_quem_foi_mencionado():
    x, _ = wa.converter(evento("A9", _com_mencoes(
        "oi @5551988887777", "5551988887777@s.whatsapp.net")), "w1", "c")
    assert m.extras_de(x)["mencoes"] == [
        {"jid": "5551988887777@s.whatsapp.net"}]
    sem, _ = wa.converter(evento("A8", E.Message(conversation="oi")),
                          "w1", "c")
    assert m.extras_de(sem)["mencoes"] == []


def test_mencoes_com_nome_do_contato_perfil_empresa_e_telefone(amb):
    amb.c.outros = {
        "5551977770001": dict(PushName="Beto do Perfil"),
        "5551977770002": dict(BusinessName="Padaria Central"),
        "5551977770003": dict(PushName="Perfil", BusinessName="Empresa",
                              FullName="Nome na Agenda")}
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    texto = ("@5551988887777 @5551977770001 @5551977770002 "
             "@5551977770003 @5551900000000 e @55519777700011")
    jids = ["5551988887777@s.whatsapp.net", "5551977770001@s.whatsapp.net",
            "5551977770002@s.whatsapp.net", "5551977770003@s.whatsapp.net",
            "5551900000000@s.whatsapp.net"]
    amb.f["Message"](amb.c, evento("MM1", _com_mencoes(texto, *jids),
                                   grupo=True, chat="1203", remetente=
                                   "5551988887777"))
    nova = esperar(amb.fila, ev.MensagemNova).mensagem
    # contato > perfil > empresa > telefone; "@...11" (outro numero) intacto
    assert nova.texto == ("@Ana Silva @Beto do Perfil @Padaria Central "
                          "@Nome na Agenda @+5551900000000 e @55519777700011")
    men = m.extras_de(nova)["mencoes"]
    assert men[0] == {"jid": jids[0], "nome": "Ana Silva",
                      "id": jids[0], "telefone": "+5551988887777"}
    assert men[4]["nome"] == "+5551900000000"
    guardada = amb.banco.mensagem("w1", "1203@g.us", "MM1")
    assert guardada.texto == nova.texto


def test_mencao_com_endereco_lid_vira_o_numero(amb):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    amb.f["Message"](amb.c, evento("MM2", _com_mencoes(
        "oi @lid1", "lid1@lid"), grupo=True, chat="1203",
        remetente="5551988887777"))
    nova = esperar(amb.fila, ev.MensagemNova).mensagem
    men = m.extras_de(nova)["mencoes"][0]
    assert men["id"] == "5551977776666@s.whatsapp.net"
    assert men["telefone"] == "+5551977776666"
    assert nova.texto == "oi @+5551977776666"


def test_historico_tambem_guarda_as_mencoes():
    from neonize.proto.waWeb import WAWebProtobufsWeb_pb2 as W
    info = W.WebMessageInfo(
        key=W.WebMessageInfo.DESCRIPTOR.fields_by_name["key"].message_type
        ._concrete_class(remoteJID="1203@g.us", fromMe=False, ID="H1"),
        message=_com_mencoes("oi @5551988887777",
                             "5551988887777@s.whatsapp.net"),
        messageTimestamp=TS)
    x, _ = wa.converter_historico(info, "w1", "1203@g.us")
    assert m.extras_de(x)["mencoes"] == [
        {"jid": "5551988887777@s.whatsapp.net"}]


def _receber(amb, id, chat, servidor, pushname="", texto="oi"):
    amb.f["Message"](amb.c, evento(id, E.Message(conversation=texto),
                                   chat=chat, servidor=servidor,
                                   pushname=pushname))
    return esperar(amb.fila, ev.MensagemNova).conversa


def test_conversa_com_endereco_lid_nunca_mostra_o_codigo(amb):
    amb.c.outros = {"99887766554433221": dict(BusinessName="Padaria Central"),
                    "11223344556677889": dict(PushName="Beto do Perfil")}
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    # empresa (so nome de registro), pessoa (so perfil) e sem nada
    assert _receber(amb, "L1", "99887766554433221", "lid").nome == \
        "Padaria Central"
    assert _receber(amb, "L2", "11223344556677889", "lid").nome == \
        "Beto do Perfil"
    assert _receber(amb, "L3", "55544433322211100", "lid").nome == \
        wa.SEM_NOME
    # com numero conhecido, vence o nome da agenda do numero
    assert _receber(amb, "L4", "lid1", "lid").nome == "+5551977776666"


def test_conversa_guardada_com_codigo_ganha_nome_quando_chega_mensagem(amb):
    amb.c.outros = {"99887766554433221": dict(PushName="Carla")}
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    antiga = m.Conversa(amb.p.conta.id, "99887766554433221@lid",
                        "99887766554433221", "whatsapp", "privada")
    amb.p._conversas[antiga.id] = antiga
    assert _receber(amb, "L5", "99887766554433221", "lid").nome == "Carla"


def test_mensagem_de_canal_ganha_o_nome_do_canal(amb):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    conv = _receber(amb, "C1", "120363000000000001", "newsletter")
    assert conv.tipo == "canal"
    for _ in range(50):
        if conv.nome != wa.CANAL_SEM_NOME:
            break
        threading.Event().wait(0.02)
    assert amb.p._conversas["120363000000000001@newsletter"].nome == \
        "Canal de Notícias"


def test_nome_de_participante_usa_agenda_ou_telefone(amb):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    assert amb.p.nome_de_participante("5551988887777@s.whatsapp.net") == \
        "Ana Silva"
    assert amb.p.nome_de_participante("5551900000000@s.whatsapp.net") == \
        "+5551900000000"
    assert amb.p.nome_de_participante("55544433322211100@lid") == ""


def test_mensagem_de_empresa_com_modelo_e_botao_de_link():
    h = E.TemplateMessage.HydratedFourRowTemplate(
        hydratedTitleText="Pedido enviado",
        hydratedContentText="Seu pedido 123 saiu para entrega.",
        hydratedFooterText="Loja X",
        hydratedButtons=[E.HydratedTemplateButton(
            urlButton=E.HydratedTemplateButton.HydratedURLButton(
                displayText="Rastrear", URL="https://x.com/r/123"))])
    msg, _ = wa.converter(evento("T1", E.Message(
        templateMessage=E.TemplateMessage(hydratedTemplate=h))), "w1", "c")
    assert msg.tipo == m.TEXTO
    assert msg.texto == ("Pedido enviado\nSeu pedido 123 saiu para entrega."
                         "\nLoja X\nBotões: Rastrear")
    assert m.extras_de(msg)["botoes"] == [["Rastrear", "https://x.com/r/123"]]


def test_mensagem_interativa_com_botao_cta_url_e_botoes_simples():
    nf = E.InteractiveMessage.NativeFlowMessage(buttons=[
        E.InteractiveMessage.NativeFlowMessage.NativeFlowButton(
            name="cta_url", buttonParamsJSON=
            '{"display_text":"Abrir site","url":"https://loja.com"}'),
        E.InteractiveMessage.NativeFlowMessage.NativeFlowButton(
            name="quick_reply", buttonParamsJSON='{"display_text":"Sim"}')])
    inter = E.InteractiveMessage(
        body=E.InteractiveMessage.Body(text="Olá! Veja a oferta."),
        footer=E.InteractiveMessage.Footer(text="Loja"), nativeFlowMessage=nf)
    msg, _ = wa.converter(evento("I1", E.Message(interactiveMessage=inter)),
                          "w1", "c")
    assert msg.texto == "Olá! Veja a oferta.\nLoja\nBotões: Abrir site, Sim"
    assert m.extras_de(msg)["botoes"] == [["Abrir site", "https://loja.com"]]
    resp = E.Message(buttonsResponseMessage=E.ButtonsResponseMessage(
        selectedDisplayText="Sim"))
    msg, _ = wa.converter(evento("I2", resp), "w1", "c")
    assert msg.texto == "resposta: Sim" and msg.tipo == m.TEXTO


def test_conteudo_desconhecido_diz_qual_e_o_tipo_para_tratarmos():
    msg, _ = wa.converter(evento("U1", E.Message(
        requestPhoneNumberMessage=E.RequestPhoneNumberMessage())), "w1", "c")
    assert msg.tipo == m.OUTRO
    assert "requestPhoneNumberMessage" in msg.texto


def test_conversa_so_com_telefone_ganha_nome_verificado_da_empresa(amb):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    antiga = m.Conversa(amb.p.conta.id, "556136863608@s.whatsapp.net",
                        "+556136863608", "whatsapp", "privada")
    amb.p._conversas[antiga.id] = antiga
    ev_ = evento("V1", E.Message(conversation="oi"), chat="556136863608",
                 pushname="")
    ev_.Info.VerifiedName.Details.verifiedName = "Banco Exemplo"
    amb.f["Message"](amb.c, ev_)
    assert esperar(amb.fila, ev.MensagemNova).conversa.nome == "Banco Exemplo"


def test_conversa_privada_sem_pushname_usa_o_nome_da_conversa_como_autor(amb):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    amb.f["Message"](amb.c, evento("P1", E.Message(conversation="oi"),
                                   chat="5511912617423", pushname=""))
    nova = esperar(amb.fila, ev.MensagemNova).mensagem
    assert nova.autor == "+5511912617423"


def test_conversa_so_com_telefone_pergunta_o_nome_da_empresa_ao_whatsapp(amb):
    amb.c.empresas = {"556136863608": "99 Pay"}
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    conv = _receber(amb, "E1", "556136863608", "s.whatsapp.net", pushname="")
    for _ in range(50):
        if conv.nome == "99 Pay":
            break
        threading.Event().wait(0.02)
    assert conv.nome == "99 Pay"
    for _ in range(50):
        if amb.p.banco.conversas(amb.p.conta.id)[0].nome == "99 Pay":
            break
        threading.Event().wait(0.02)
    assert amb.p.banco.conversas(amb.p.conta.id)[0].nome == "99 Pay"


def test_estrutura_interativa_descreve_botoes_sem_imagem_nem_texto_longo():
    nf = E.InteractiveMessage.NativeFlowMessage(buttons=[
        E.InteractiveMessage.NativeFlowMessage.NativeFlowButton(
            name="quick_reply", buttonParamsJSON='{"id":"1","display_text":"Sim"}')])
    inter = E.InteractiveMessage(
        body=E.InteractiveMessage.Body(text="x" * 200), nativeFlowMessage=nf)
    forma = wa.estrutura_interativa(E.Message(interactiveMessage=inter))
    botao = forma["interactiveMessage"]["nativeFlowMessage"]["buttons"][0]
    assert botao["name"] == "quick_reply"
    assert len(forma["interactiveMessage"]["body"]["text"]) <= 81
    assert wa.estrutura_interativa(E.Message(conversation="oi")) is None


def test_album_foto_dentro_de_associated_child_aparece_e_cabecalho_some():
    foto = E.Message(imageMessage=E.ImageMessage(caption="da viagem",
                                                  fileLength=10))
    filha = E.Message(associatedChildMessage=E.FutureProofMessage(
        message=foto))
    msg, _ = wa.converter(evento("A1", filha), "w1", "c")
    assert msg.tipo == m.FOTO and msg.texto == "da viagem"
    cab = E.Message(albumMessage=E.AlbumMessage(expectedImageCount=3))
    assert wa.converter(evento("A2", cab), "w1", "c") == (None, "")
    aviso = E.Message(groupStatusMentionMessage=E.FutureProofMessage())
    assert wa.converter(evento("A3", aviso), "w1", "c") == (None, "")


def test_comentario_e_convite_de_grupo_viram_texto():
    com = E.Message(commentMessage=E.CommentMessage(
        message=E.Message(conversation="boa ideia")))
    msg, _ = wa.converter(evento("K1", com), "w1", "c")
    assert msg.tipo == m.TEXTO and msg.texto == "boa ideia"
    conv = E.Message(groupInviteMessage=E.GroupInviteMessage(
        groupName="Família", caption="entra aí"))
    msg, _ = wa.converter(evento("K2", conv), "w1", "c")
    assert msg.tipo == m.OUTRO
    assert msg.texto == "convite para o grupo: Família\nentra aí"


def test_lista_mostra_as_opcoes_no_texto():
    lista = E.ListMessage(title="Escolha", description="Como podemos ajudar?",
                          sections=[E.ListMessage.Section(rows=[
                              E.ListMessage.Row(title="Segunda via"),
                              E.ListMessage.Row(title="Atendente")])])
    msg, _ = wa.converter(evento("LS1", E.Message(listMessage=lista)),
                          "w1", "c")
    assert msg.texto.endswith("Opções: Segunda via, Atendente")


def test_consulta_de_empresas_em_lote_renomeia_so_quem_tem_telefone(amb):
    amb.c.empresas = {"556136863608": "99 Pay", "5511953057252": "Verisure"}
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    conta = amb.p.conta.id
    for cid, nome in (("556136863608@s.whatsapp.net", "+556136863608"),
                      ("5511953057252@s.whatsapp.net", "+5511953057252"),
                      ("5551988887777@s.whatsapp.net", "Ana Silva")):
        amb.p._conversas[cid] = m.Conversa(conta, cid, nome, "whatsapp",
                                           "privada")
    amb.p._consultar_empresas(list(amb.p._conversas))
    nomes = {c.id.split("@")[0]: c.nome for c in amb.p._conversas.values()}
    assert nomes["556136863608"] == "99 Pay"
    assert nomes["5511953057252"] == "Verisure"
    assert nomes["5551988887777"] == "Ana Silva"


def test_pagamento_interativo_sem_texto_vira_solicitacao_de_pagamento():
    nf = E.InteractiveMessage.NativeFlowMessage(buttons=[
        E.InteractiveMessage.NativeFlowMessage.NativeFlowButton(
            name="payment_info", buttonParamsJSON='{"currency":"BRL"}')])
    msg, _ = wa.converter(evento("PG1", E.Message(
        interactiveMessage=E.InteractiveMessage(nativeFlowMessage=nf))),
        "w1", "c")
    assert msg.tipo == m.TEXTO
    assert msg.texto == "mensagem interativa: solicitação de pagamento"


def _modelo_com_botoes():
    h = E.TemplateMessage.HydratedFourRowTemplate(
        hydratedContentText="Você confirma a consulta?",
        hydratedButtons=[
            E.HydratedTemplateButton(
                index=0, quickReplyButton=E.HydratedTemplateButton.
                HydratedQuickReplyButton(displayText="Sim", ID="s")),
            E.HydratedTemplateButton(
                index=1, quickReplyButton=E.HydratedTemplateButton.
                HydratedQuickReplyButton(displayText="Não", ID="n")),
            E.HydratedTemplateButton(
                index=2, urlButton=E.HydratedTemplateButton.
                HydratedURLButton(displayText="Site", URL="https://x.com"))])
    return E.Message(templateMessage=E.TemplateMessage(
        hydratedFourRowTemplate=h))


def test_acoes_guardam_so_botoes_de_resposta_e_opcoes_de_lista():
    msg, _ = wa.converter(evento("A1", _modelo_com_botoes()), "w1", "c")
    acoes = m.extras_de(msg)["acoes"]
    assert [(a["tipo"], a["rotulo"], a["id"], a["indice"]) for a in acoes] \
        == [("modelo", "Sim", "s", 0), ("modelo", "Não", "n", 1)]
    lista = E.ListMessage(title="Escolha", sections=[E.ListMessage.Section(
        rows=[E.ListMessage.Row(title="Convênio", rowID="c1",
                                description="Plano"),
              E.ListMessage.Row(title="Particular", rowID="p1")])])
    msg, _ = wa.converter(evento("A2", E.Message(listMessage=lista)),
                          "w1", "c")
    acoes = m.extras_de(msg)["acoes"]
    assert [(a["tipo"], a["rotulo"], a["id"]) for a in acoes] == [
        ("lista", "Convênio", "c1"), ("lista", "Particular", "p1")]
    msg, _ = wa.converter(evento("A3", E.Message(conversation="oi")),
                          "w1", "c")
    assert m.extras_de(msg)["acoes"] == []


def test_tocar_botao_de_modelo_responde_citando_a_mensagem(amb):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    amb.f["Message"](amb.c, evento("B1", _modelo_com_botoes()))
    recebida = esperar(amb.fila, ev.MensagemNova).mensagem
    acao = m.extras_de(recebida)["acoes"][1]
    amb.p.responder_acao(recebida, acao)
    esperar(amb.fila, ev.MensagemNova)
    _, proto = amb.c.enviadas[-1]
    r = proto.templateButtonReplyMessage
    assert (r.selectedID, r.selectedDisplayText, r.selectedIndex) == \
        ("n", "Não", 1)
    assert r.contextInfo.stanzaID == "B1"


def test_escolher_opcao_de_lista_e_botoes_simples(amb):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    recebida = m.Mensagem("w1", "5551988887777@s.whatsapp.net", "L1",
                          texto="Escolha")
    amb.p.responder_acao(recebida, {"tipo": "lista", "rotulo": "Particular",
                                    "id": "p1", "descricao": ""})
    esperar(amb.fila, ev.MensagemNova)
    r = amb.c.enviadas[-1][1].listResponseMessage
    assert r.title == "Particular" and r.singleSelectReply.selectedRowID == "p1"
    amb.p.responder_acao(recebida, {"tipo": "botoes", "rotulo": "Sim",
                                    "id": "1"})
    esperar(amb.fila, ev.MensagemNova)
    # 1a variante, experimental: a resposta vai dentro de um documento com
    # legenda (assim a biblioteca nao poe o no <biz><buttons_response/>)
    b = amb.c.enviadas[-1][1].documentWithCaptionMessage.message \
        .buttonsResponseMessage
    assert (b.selectedButtonID, b.selectedDisplayText) == ("1", "Sim")


def test_falha_ao_tocar_botao_nao_devolve_texto_para_a_caixa(amb):
    recebida = m.Mensagem("w1", "5551988887777@s.whatsapp.net", "L1")
    amb.p.responder_acao(recebida, {"tipo": "botoes", "rotulo": "Sim",
                                    "id": "1"})
    falha = esperar(amb.fila, ev.EnvioFalhou)
    assert falha.motivo == "sem conexão" and not falha.devolver_texto


def test_modo_de_depuracao_guarda_a_estrutura_original(amb):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    amb.f["Message"](amb.c, evento("D0", E.Message(conversation="antes")))
    esperar(amb.fila, ev.MensagemNova)
    cid = "5551988887777@s.whatsapp.net"
    assert amb.banco.depuracao_de("w1", cid, "D0") == ""     # modo desligado
    amb.banco.depuracao = True
    amb.f["Message"](amb.c, evento("D1", _modelo_com_botoes()))
    esperar(amb.fila, ev.MensagemNova)
    bruto = amb.banco.depuracao_de("w1", cid, "D1")
    assert "Você confirma a consulta?" in bruto and "quickReplyButton" in bruto
    assert "info" in bruto and "mensagem" in bruto


def test_depurar_conversa_explica_como_o_nome_foi_achado(amb):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    dados = amb.p.depurar_conversa("5551988887777@s.whatsapp.net")
    assert dados["numero"] == "5551988887777@s.whatsapp.net"
    assert "nome_escolhido" in dados
    assert amb.p.depurar_conversa("sem-arroba") == {
        "conversa_id": "sem-arroba"}


def _buttons_message():
    return E.Message(buttonsMessage=E.ButtonsMessage(
        contentText="Você precisa de assistência?", buttons=[
            E.ButtonsMessage.Button(
                buttonID="1", buttonText=E.ButtonsMessage.Button.ButtonText(
                    displayText="Automóvel"), type=1),
            E.ButtonsMessage.Button(
                buttonID="2", buttonText=E.ButtonsMessage.Button.ButtonText(
                    displayText="Residência"), type=1)]))


def test_mensagem_com_botoes_guarda_o_original_para_citar_inteira():
    msg, _ = wa.converter(evento("O1", _buttons_message()), "w1", "c")
    extras = m.extras_de(msg)
    assert "Residência" in extras["original"]
    assert [a["id"] for a in extras["acoes"]] == ["1", "2"]
    msg, _ = wa.converter(evento("O2", E.Message(conversation="oi")),
                          "w1", "c")
    assert m.extras_de(msg)["original"] == ""


def test_resposta_de_botao_tenta_variantes_quando_o_servidor_recusa(amb):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    ev_ = evento("O3", _buttons_message())
    amb.f["Message"](amb.c, ev_)
    recebida = esperar(amb.fila, ev.MensagemNova).mensagem
    recebida.remetente = "94476496285751@lid"
    acao = m.extras_de(recebida)["acoes"][1]
    amb.c.recusar_479 = 2                    # a experimental e a do celular
    amb.p.responder_acao(recebida, acao)
    esperar(amb.fila, ev.MensagemNova)
    destino, proto = amb.c.enviadas[-1]
    r = proto.buttonsResponseMessage
    assert destino == "5551988887777@s.whatsapp.net"      # 3a variante
    assert (r.selectedButtonID, r.selectedDisplayText) == ("2", "Residência")
    assert r.contextInfo.quotedMessage.HasField("buttonsMessage")
    assert r.contextInfo.participant == "94476496285751@lid"


def test_resposta_de_botao_so_falha_se_todas_as_variantes_forem_recusadas(
        amb):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    amb.f["Message"](amb.c, evento("O4", _buttons_message()))
    recebida = esperar(amb.fila, ev.MensagemNova).mensagem
    recebida.remetente = "94476496285751@lid"
    amb.c.recusar_479 = 99
    amb.p.responder_acao(recebida, m.extras_de(recebida)["acoes"][0])
    falha = esperar(amb.fila, ev.EnvioFalhou)
    assert "erro do WhatsApp" in falha.motivo and not falha.devolver_texto
    assert amb.c.recusar_479 == 99 - 4       # tentou as 4 variantes


def test_resposta_de_botao_tenta_primeiro_a_variante_experimental(amb):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    amb.f["Message"](amb.c, evento("O5", _buttons_message()))
    recebida = esperar(amb.fila, ev.MensagemNova).mensagem
    recebida.remetente = "94476496285751@lid"
    amb.p.responder_acao(recebida, m.extras_de(recebida)["acoes"][1])
    esperar(amb.fila, ev.MensagemNova)
    destino, proto = amb.c.enviadas[-1]
    assert destino == "94476496285751@lid"
    assert not proto.HasField("buttonsResponseMessage")
    r = proto.documentWithCaptionMessage.message.buttonsResponseMessage
    assert (r.selectedButtonID, r.selectedDisplayText) == ("2", "Residência")
    assert r.contextInfo.stanzaID == "O5"


def test_enviar_voz_foto_e_documento(amb, dados_midia, tmp_path):
    from telezapp.midia import envio
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    cid = "5551988887777@s.whatsapp.net"
    ogg = tmp_path / "voz-1.ogg"
    ogg.write_bytes(open(os.path.join(os.path.dirname(__file__), "amostras",
                                      "voz.ogg"), "rb").read())
    voz = envio.preparar(str(ogg), voz=True, temporario=True)
    amb.p.enviar_arquivo(cid, voz)
    nova = esperar(amb.fila, ev.MensagemNova)
    assert nova.enviada_daqui and nova.mensagem.tipo == m.VOZ
    assert nova.mensagem.segundos == voz.segundos
    audio = amb.c.enviadas[-1][1].audioMessage
    assert audio.PTT and audio.seconds == voz.segundos
    assert audio.mimetype == "audio/ogg; codecs=opus" and audio.URL
    assert not ogg.exists()                       # movida para o armazem
    reg = amb.banco.midia("w1", cid, nova.mensagem.id)
    assert reg and os.path.isfile(reg[0])

    foto = tmp_path / "f.jpg"
    foto.write_bytes(b"\xff\xd8\xff")
    amb.p.enviar_arquivo(cid, envio.preparar(str(foto)), "olha")
    nova = esperar(amb.fila, ev.MensagemNova)
    assert nova.mensagem.tipo == m.FOTO and nova.mensagem.texto == "olha"
    assert amb.c.enviadas[-1][1] == ("imagem", str(foto), "olha")
    assert foto.exists()

    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF")
    amb.p.enviar_arquivo(cid, envio.preparar(str(pdf)), "falhar")
    falha = esperar(amb.fila, ev.EnvioFalhou)
    assert falha.tipo == m.DOCUMENTO and not falha.devolver_texto
    assert "erro do WhatsApp" in falha.motivo


def test_enviar_arquivo_sem_conexao(amb, tmp_path):
    from telezapp.midia import envio
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF")
    amb.p.enviar_arquivo("5551@s.whatsapp.net", envio.preparar(str(pdf)))
    assert esperar(amb.fila, ev.EnvioFalhou).motivo == "sem conexão"


def test_mensagem_de_grupo_com_chave_e_conteudo_no_mesmo_pacote(amb):
    """Quando alguem fala no grupo depois de trocar a chave de envio, o
    pacote traz duas partes cifradas (a chave e o conteudo) e o whatsmeow
    entrega DOIS eventos com o mesmo ID: primeiro so a chave, depois o texto.
    Marcar o ID como visto antes de ver se ha conteudo descartava o texto."""
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    chave = E.Message(senderKeyDistributionMessage=(
        E.SenderKeyDistributionMessage(groupID="g")))
    kw = dict(chat="120363000000000001", grupo=True, remetente="5551977776666")

    amb.f["Message"](amb.c, evento("G1", chave, **kw))
    amb.f["Message"](amb.c, evento("G1", E.Message(conversation="Oi grupo"),
                                   **kw))
    nova = esperar(amb.fila, ev.MensagemNova)
    assert nova.mensagem.id == "G1" and nova.mensagem.texto == "Oi grupo"

    # o conteudo repetido continua sendo ignorado (nao duplica)
    amb.f["Message"](amb.c, evento("G1", E.Message(conversation="Oi grupo"),
                                   **kw))
    assert amb.banco.conversas("w1")[0].nao_lidas == 1
    assert len([x for x in amb.banco.mensagens("w1", nova.mensagem.conversa_id,
                                               50) if x.id == "G1"]) == 1


# --------------------------------------------- reacoes, edicoes e apagadas
def _chave(id, de_mim=False, grupo=False):
    from neonize.proto.waCommon import WACommon_pb2 as C
    return C.MessageKey(ID=id, fromMe=de_mim)


def _chegou(amb, id="M1", texto="Olá"):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    amb.f["Message"](amb.c, evento(id, E.Message(conversation=texto)))
    return esperar(amb.fila, ev.MensagemNova).mensagem


def test_reacao_aparece_na_mensagem_e_pode_ser_trocada(amb):
    original = _chegou(amb)
    reacao = E.Message(reactionMessage=E.ReactionMessage(
        key=_chave("M1"), text="👍"))
    amb.f["Message"](amb.c, evento("R1", reacao, pushname="Bruno"))
    a = esperar(amb.fila, ev.MensagemAtualizada)
    assert (a.motivo, a.emoji) == ("reacao", "👍")
    assert a.quem                       # o nome do contato ou do perfil
    assert [r["emoji"] for r in m.extras_de(a.mensagem)["reacoes"]] == ["👍"]
    assert m.resumo_reacoes(a.mensagem) == "👍 de " + a.quem

    # a mesma pessoa troca de emoji: continua uma so reacao
    reacao2 = E.Message(reactionMessage=E.ReactionMessage(
        key=_chave("M1"), text="❤"))
    amb.f["Message"](amb.c, evento("R2", reacao2, pushname="Bruno"))
    b = esperar(amb.fila, ev.MensagemAtualizada)
    assert [r["emoji"] for r in m.extras_de(b.mensagem)["reacoes"]] == ["❤"]

    # e depois tira a reacao (texto vazio)
    tirar = E.Message(reactionMessage=E.ReactionMessage(key=_chave("M1"),
                                                        text=""))
    amb.f["Message"](amb.c, evento("R3", tirar, pushname="Bruno"))
    c = esperar(amb.fila, ev.MensagemAtualizada)
    assert m.extras_de(c.mensagem)["reacoes"] == []
    assert original.id == "M1"


def test_edicao_troca_o_texto_e_marca_editada(amb):
    _chegou(amb, texto="Oi")
    novo = E.Message(conversation="Oi, tudo bem?")
    edicao = E.Message(protocolMessage=E.ProtocolMessage(
        key=_chave("M1"), type=E.ProtocolMessage.MESSAGE_EDIT,
        editedMessage=novo))
    amb.f["Message"](amb.c, evento("E1", edicao))
    a = esperar(amb.fila, ev.MensagemAtualizada)
    assert a.motivo == "editada" and a.mensagem.texto == "Oi, tudo bem?"
    assert m.extras_de(a.mensagem)["editada"] is True
    assert "(editada)" in m.formatar(a.mensagem, m.ESTILO_CONTEUDO_PRIMEIRO)
    assert amb.banco.mensagem("w1", a.conversa_id, "M1").texto == \
        "Oi, tudo bem?"


def test_apagar_para_todos_esconde_o_conteudo(amb):
    _chegou(amb, texto="segredo")
    apagar = E.Message(protocolMessage=E.ProtocolMessage(
        key=_chave("M1"), type=E.ProtocolMessage.REVOKE))
    amb.f["Message"](amb.c, evento("D1", apagar))
    a = esperar(amb.fila, ev.MensagemAtualizada)
    assert a.motivo == "apagada" and a.mensagem.texto == ""
    assert m.conteudo(a.mensagem) == "mensagem apagada"
    assert "segredo" not in m.formatar(a.mensagem, m.ESTILO_AUTOR_PRIMEIRO)


def test_alteracao_de_mensagem_desconhecida_e_ignorada(amb):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    reacao = E.Message(reactionMessage=E.ReactionMessage(
        key=_chave("NAOEXISTE"), text="👍"))
    amb.f["Message"](amb.c, evento("R9", reacao))
    # nada novo na fila: uma mensagem de verdade chega em seguida
    amb.f["Message"](amb.c, evento("M2", E.Message(conversation="depois")))
    assert esperar(amb.fila, ev.MensagemNova).mensagem.id == "M2"


def test_reacoes_no_resumo_e_nos_detalhes():
    x = m.Mensagem("w1", "c", "1", autor="Ana", texto="oi")
    m.atualizar_extras(x, reacoes=[
        {"id": "a", "quem": "Bruno", "emoji": "👍"},
        {"id": "b", "quem": "Carla", "emoji": "❤"}])
    assert m.resumo_reacoes(x) == "👍 de Bruno, ❤ de Carla"
    assert "reações: 👍 de Bruno, ❤ de Carla" in m.formatar(
        x, m.ESTILO_CONTEUDO_PRIMEIRO)
    m.atualizar_extras(x, reacoes=[{"id": str(i), "quem": "p", "emoji": "👍"}
                                   for i in range(5)])
    assert m.resumo_reacoes(x) == "5 reações"
    # os outros extras continuam
    m.guardar_extras(x, links=[("https://a.com", "a")])
    m.atualizar_extras(x, editada=True)
    assert m.extras_de(x)["links"] == [["https://a.com", "a"]]
    assert m.extras_de(x)["editada"] is True


# ------------------------------------------ audio e voz "ouvida" na lista
def test_voz_ouvida_aparece_na_linha_mas_nao_na_citacao():
    x = m.Mensagem("w1", "c", "1", autor="Ana", tipo=m.VOZ, segundos=12)
    assert m.conteudo(x) == "mensagem de voz, 12 segundos"
    m.atualizar_extras(x, ouvida=True)
    assert m.conteudo(x) == "mensagem de voz, 12 segundos, ouvida"
    assert "ouvida" in m.formatar(x, m.ESTILO_AUTOR_PRIMEIRO)
    assert "ouvida" not in m.citacao(x)
    minha = m.Mensagem("w1", "c", "2", minha=True, tipo=m.VOZ, segundos=5)
    m.atualizar_extras(minha, ouvida=True)
    assert "ouvida" not in m.conteudo(minha)


def test_whatsapp_voz_tocada_no_celular_vira_ouvida(amb):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    voz = E.Message(audioMessage=E.AudioMessage(PTT=True, seconds=7,
                                                fileLength=900))
    amb.f["Message"](amb.c, evento("V1", voz))
    esperar(amb.fila, ev.MensagemNova)
    amb.f["Receipt"](amb.c, N.Receipt(
        MessageSource=N.MessageSource(Chat=jid("5551988887777"),
                                      IsFromMe=True),
        MessageIDs=["V1"], Type=7))
    a = esperar(amb.fila, ev.MensagemAtualizada)
    assert a.motivo == "ouvida" and m.extras_de(a.mensagem)["ouvida"]
    assert amb.banco.mensagem("w1", a.conversa_id, "V1") is not None
    assert m.extras_de(amb.banco.mensagem(
        "w1", a.conversa_id, "V1"))["ouvida"] is True


def test_arquivadas_seguem_o_celular(tmp_path):
    """O armazem local do whatsmeow guarda o que o celular arquivou."""
    b = ev.Barramento()
    banco = Banco(str(tmp_path / "s.db"))
    p = wa.ProvedorWhatsApp(m.Conta("w1", "whatsapp"), b, banco,
                            pasta_sessoes=str(tmp_path),
                            fabrica_cliente=ClienteFalso)
    cel = {"5551@s.whatsapp.net": True, "5552@s.whatsapp.net": False}

    class Armazem:
        def get_chat_settings(self, alvo):
            chave = "%s@%s" % (alvo.User, alvo.Server)
            if chave in cel:
                return N.LocalChatSettings(Found=True, Archived=cel[chave])
            return N.LocalChatSettings(Found=False)

    p.cliente = types.SimpleNamespace(
        chat_settings=Armazem(),
        get_lid_from_pn=lambda j: (_ for _ in ()).throw(RuntimeError("n")))
    p._conectada = True
    a = m.Conversa("w1", "5551@s.whatsapp.net", "A", "whatsapp")
    c = m.Conversa("w1", "5552@s.whatsapp.net", "C", "whatsapp",
                   arquivada=True)         # estava marcada aqui, celular nao
    d = m.Conversa("w1", "5553@s.whatsapp.net", "D", "whatsapp")
    p._conversas = {x.id: x for x in (a, c, d)}
    p._conferir_arquivadas()
    assert (a.arquivada, c.arquivada, d.arquivada) == (True, False, False)
    # arquiva aqui: enquanto o celular nao mudar, continua arquivada
    d.arquivada = True
    c.arquivada = True
    p._conferir_arquivadas()
    assert d.arquivada and c.arquivada
    cel["5551@s.whatsapp.net"] = False       # desarquivou no celular
    p._conferir_arquivadas()
    assert a.arquivada is False
    banco.fechar()


def test_avisos_de_arquivar_e_trancar_do_celular(tmp_path):
    b = ev.Barramento()
    banco = Banco(str(tmp_path / "s.db"))
    p = wa.ProvedorWhatsApp(m.Conta("w1", "whatsapp"), b, banco,
                            pasta_sessoes=str(tmp_path),
                            fabrica_cliente=ClienteFalso)
    c = m.Conversa("w1", "5551@s.whatsapp.net", "A", "whatsapp")
    p._conversas = {c.id: c}

    def aviso(**acao):
        return types.SimpleNamespace(JID=jid("5551"),
                                     Action=types.SimpleNamespace(**acao))
    p._ao_arquivar(None, aviso(archived=True))
    p._ao_trancar(None, aviso(locked=True))
    assert c.arquivada and c.trancada
    assert p._arquivada_vista[c.id] is True        # a conferencia nao desfaz
    p._ao_trancar(None, aviso(locked=False))
    assert not c.trancada
    p._ao_arquivar(None, types.SimpleNamespace(
        JID=jid("9999"), Action=types.SimpleNamespace(archived=True)))
    assert [x.arquivada for x in banco.conversas("w1")] == [True]
    banco.fechar()


def test_mensagem_nao_decifrada_deixa_marca_e_a_de_verdade_a_substitui(amb):
    info = N.MessageInfo(
        MessageSource=N.MessageSource(
            Chat=jid("123", "g.us"), IsGroup=True, Sender=jid("5552")),
        ID="G9", Pushname="Bia", Timestamp=TS)
    amb.f["UndecryptableMessage"](amb.c, N.UndecryptableMessage(
        Info=info, IsUnavailable=False,
        DecryptFailMode=N.UndecryptableMessage.DECRYPT_FAIL_SHOW))
    marca = esperar(amb.fila, ev.MensagemNova)
    assert marca.mensagem.tipo == m.AGUARDANDO and marca.silenciosa
    assert marca.mensagem.id == "G9"
    assert "ainda não recebida" in m.conteudo(marca.mensagem)
    # o pedido de novo ao remetente deu certo: a mensagem chega com o mesmo id
    amb.f["Message"](amb.c, evento(
        "G9", E.Message(conversation="oi do grupo"), chat="123", grupo=True,
        remetente="5552"))
    real = esperar(amb.fila, ev.MensagemNova)
    assert real.mensagem.id == "G9" and real.mensagem.texto == "oi do grupo"
    guardadas = amb.banco.mensagens("w1", "123@g.us")
    assert [(x.id, x.tipo) for x in guardadas] == [("G9", m.TEXTO)]


def test_mensagem_nao_decifrada_que_o_whatsapp_manda_esconder_so_registra(amb):
    info = N.MessageInfo(
        MessageSource=N.MessageSource(
            Chat=jid("5551"), IsGroup=False, Sender=jid("5551")),
        ID="X1", Timestamp=TS)
    amb.f["UndecryptableMessage"](amb.c, N.UndecryptableMessage(
        Info=info, IsUnavailable=True,
        DecryptFailMode=N.UndecryptableMessage.DECRYPT_FAIL_HIDE))
    amb.f["Message"](amb.c, evento("X2", E.Message(conversation="e")))
    primeira = esperar(amb.fila, ev.MensagemNova)
    assert primeira.mensagem.id == "X2"       # a marca nao foi criada


def test_mensagem_apagada_no_celular_vira_evento(amb):
    amb.f["MessageDeleteForMe"](amb.c, N.MessageDeleteForMe(
        ChatJID=jid("123", "g.us"), IsFromMe=False, MessageID="G7",
        Timestamp=TS, FromFullSync=False))
    e = esperar(amb.fila, ev.MensagemApagadaNoCelular)
    assert (e.conversa_id, e.mensagem_id) == ("123@g.us", "G7")


def test_apagar_mensagem_aqui_avisa_o_whatsapp(amb):
    amb.f["Connected"](amb.c, N.Connected())
    outra = m.Mensagem("w1", "123@g.us", "G7", remetente="5552@s.whatsapp.net",
                       data=TS)
    assert amb.p.apagar_mensagem(outra)             # so para mim
    mut = amb.c.patches[0].Mutations[0]
    assert list(mut.Index) == ["deleteMessageForMe", "123@g.us", "G7", "0",
                               "5552@s.whatsapp.net"]
    assert mut.Version == 3 and mut.Value.deleteMessageForMeAction.deleteMedia
    minha = m.Mensagem("w1", "5551@s.whatsapp.net", "M1", minha=True,
                       data=TS)
    assert amb.p.apagar_mensagem(minha, para_todos=True)      # para todos
    assert amb.c.revogadas == [("5551@s.whatsapp.net", "M1")]
    assert not amb.p.apagar_mensagem(outra, para_todos=True)  # so as minhas



def test_tipos_novos_ganham_texto_e_o_de_edicao_nao_vira_mensagem():
    video = E.VideoMessage(seconds=7, fileLength=1234, caption="")
    tipo, texto, seg, _, tam = wa.conteudo_de(E.Message(ptvMessage=video))
    assert (tipo, seg, tam) == (m.VIDEO, 7, 1234)
    ficha = wa.ficha_de(E.Message(ptvMessage=E.VideoMessage(
        mimetype="video/mp4", directPath="/d", fileLength=9)))
    assert E.Message.FromString(ficha).HasField("videoMessage")
    assert wa.mime_da_ficha(ficha) == "video/mp4"

    contatos = E.ContactsArrayMessage(contacts=[
        E.ContactMessage(displayName="Ana"),
        E.ContactMessage(displayName="Bia")])
    assert wa.conteudo_de(E.Message(contactsArrayMessage=contatos))[1] == \
        "2 contatos: Ana, Bia"

    evento_ = E.EventMessage(name="Aniversário", startTime=TS,
                             location=E.LocationMessage(name="Salão"),
                             description="Levar bolo")
    texto = wa.conteudo_de(E.Message(eventMessage=evento_))[1]
    assert texto.startswith("evento: Aniversário, início ")
    assert "local: Salão" in texto and texto.endswith("\nLevar bolo")

    produto = E.ProductMessage(product=E.ProductMessage.ProductSnapshot(
        title="Cadeira", currencyCode="BRL", priceAmount1000=129900))
    assert wa.conteudo_de(E.Message(productMessage=produto))[1] == \
        "produto: Cadeira, BRL 129.90"

    # edicao de evento ou enquete (cifrada): so controle, nao e mensagem
    assert wa.conteudo_de(E.Message(
        secretEncryptedMessage=E.SecretEncryptedMessage())) is None


def test_contato_salvo_no_telezapp_vai_ao_whatsapp_sem_tocar_a_agenda(amb):
    amb.f["Connected"](amb.c, N.Connected())
    assert amb.p.salvar_contato("5551988887777@s.whatsapp.net", "Ana Maria")
    patch = amb.c.patches[-1]
    assert patch.Type == N.PatchInfo.CRITICAL_UNBLOCK_LOW
    mut = patch.Mutations[0]
    assert list(mut.Index) == ["contact", "5551988887777@s.whatsapp.net"]
    assert mut.Version == 2
    acao = mut.Value.contactAction
    assert acao.fullName == "Ana Maria" and acao.firstName == "Ana"
    assert acao.saveOnPrimaryAddressbook is False          # so no WhatsApp
    assert acao.pnJID == "5551988887777@s.whatsapp.net"
    # grupos e nome vazio nao sao contatos
    assert not amb.p.salvar_contato("123@g.us", "Grupo")
    assert not amb.p.salvar_contato("5551988887777@s.whatsapp.net", "  ")


def test_pessoa_da_mensagem_de_grupo_vira_telefone_e_renomeia_o_autor(amb):
    amb.f["Connected"](amb.c, N.Connected())
    x = m.Mensagem("w1", "123@g.us", "G1", autor="Bia", data=TS,
                   remetente="5552@s.whatsapp.net")
    id_, tel, ids = amb.p.pessoa_da_mensagem(x)
    assert (id_, tel) == ("5552@s.whatsapp.net", "+5552")
    assert "5552@s.whatsapp.net" in ids
    assert amb.p.pessoa_da_mensagem(
        m.Mensagem("w1", "123@g.us", "G2", minha=True)) is None
    amb.banco.salvar_mensagens([x])
    assert amb.banco.renomear_autor("w1", ids, "Beatriz") == 1
    assert amb.banco.mensagem("w1", "123@g.us", "G1").autor == "Beatriz"


def test_favoritar_vai_ao_whatsapp_e_vem_do_celular(amb):
    from neonize.proto.waSyncAction import WAWebProtobufSyncAction_pb2 as SA
    amb.f["Connected"](amb.c, N.Connected())
    x = m.Mensagem("w1", "123@g.us", "G1", remetente="5552@s.whatsapp.net",
                   data=TS)
    assert amb.p.favoritar_mensagem(x, True)
    mut = amb.c.patches[-1].Mutations[0]
    assert list(mut.Index) == ["star", "123@g.us", "G1", "0",
                               "5552@s.whatsapp.net"]
    assert mut.Version == 2 and mut.Value.starAction.starred
    # do celular: a mensagem guardada ganha a marca
    amb.banco.salvar_mensagens([x])
    amb.f["MessageStar"](amb.c, N.MessageStar(
        ChatJID=jid("123", "g.us"), IsFromMe=False, MessageID="G1",
        Timestamp=TS, FromFullSync=False,
        Action=SA.StarAction(starred=True)))
    e = esperar(amb.fila, ev.MensagemAtualizada)
    assert e.motivo == "favorita" and m.extras_de(e.mensagem)["favorita"]


def test_colecao_fora_de_sincronia_e_recuperada_e_o_envio_repete(amb):
    c = amb.c
    c.sincronias, c.recuperacoes = [], []
    estado = {"regular_high": "estragada"}      # estragada, recuperada

    def fetch_app_state(nome, full_sync=False):
        c.sincronias.append((nome, full_sync))
        if estado.get(nome) == "estragada" and not c.recuperacoes:
            raise RuntimeError("failed to verify patch v59: mismatching LTHash")
        if estado.get(nome) == "estragada":
            estado[nome] = "recuperada"     # o celular respondeu
    c.fetch_app_state = fetch_app_state
    c.request_app_state_recovery = lambda nome: c.recuperacoes.append(nome)
    amb.p.PASSO_DA_RECUPERACAO = 0.01      # sem esperar de verdade
    amb.f["Connected"](amb.c, N.Connected())
    for _ in range(100):
        if estado["regular_high"] == "recuperada":
            break
        threading.Event().wait(0.05)
    assert ("regular_high", False) in c.sincronias
    assert ("regular_high", True) in c.sincronias          # baixou de novo
    assert c.recuperacoes == ["regular_high"]              # e pediu ao celular
    assert estado["regular_high"] == "recuperada"
    assert ("regular_low", True) not in c.sincronias       # as boas ficam

    # um envio recusado por conflito: repara a colecao e tenta mais uma vez
    tentativas = []

    def send_app_state(patch):
        tentativas.append(1)
        if len(tentativas) == 1:
            raise RuntimeError('409 conflict ... mismatching LTHash')
    c.send_app_state = send_app_state
    x = m.Mensagem("w1", "5551@s.whatsapp.net", "M1", data=TS)
    assert amb.p.favoritar_mensagem(x, True)
    assert len(tentativas) == 2


def test_envelopes_novos_do_whatsapp_sao_abertos():
    for envelope in ("groupMentionedMessage", "spoilerMessage",
                     "questionMessage"):
        msg = E.Message(**{envelope: E.FutureProofMessage(
            message=E.Message(conversation="oi @todos"))})
        assert wa.conteudo_de(wa.desembrulhar(msg))[1] == "oi @todos", envelope


def test_mensagem_minha_para_quem_nao_esta_nos_contatos_nao_poe_meu_nome(amb):
    amb.f["Connected"](amb.c, N.Connected())
    esperar(amb.fila, ev.ContaPronta)
    amb.f["Message"](amb.c, evento("M1", E.Message(conversation="oi"),
                                   chat="5511912617423", de_mim=True,
                                   pushname="Meu Nome"))
    conv = esperar(amb.fila, ev.MensagemNova).conversa
    assert conv.nome != "Meu Nome"
    assert conv.nome.startswith("+")


def test_aviso_de_conversa_lida_no_celular_zera_as_nao_lidas(tmp_path):
    b = ev.Barramento()
    banco = Banco(str(tmp_path / "s.db"))
    p = wa.ProvedorWhatsApp(m.Conta("w1", "whatsapp"), b, banco,
                            pasta_sessoes=str(tmp_path),
                            fabrica_cliente=ClienteFalso)
    c = m.Conversa("w1", "5551@s.whatsapp.net", "A", "whatsapp",
                   nao_lidas=3, data=TS)
    banco.salvar_conversas([c])
    p._conversas = {c.id: c}

    def aviso(lida, ate=None):

        class Faixa:
            lastMessageTimestamp = ate or 0

        class Acao:
            read = lida

            @staticmethod
            def HasField(nome):
                return ate is not None
            messageRange = Faixa
        return types.SimpleNamespace(JID=jid("5551"), Action=Acao)
    p._ao_marcar_lida(None, aviso(False))                 # marcada como nao lida
    assert c.nao_lidas == 3
    p._ao_marcar_lida(None, aviso(True, TS - 600))        # ha mensagem mais nova
    assert c.nao_lidas == 3
    p._ao_marcar_lida(None, aviso(True, TS))
    assert c.nao_lidas == 0
    assert banco.conversas("w1")[0].nao_lidas == 0
    banco.fechar()


def test_cartao_de_contato_mostra_o_telefone_e_vira_pessoa_da_mensagem():
    vcard = ("BEGIN:VCARD\nVERSION:3.0\nFN:Ana Souza\n"
             "TEL;type=CELL;waid=5551999998888:+55 51 99999-8888\nEND:VCARD")
    um = E.Message(contactMessage=E.ContactMessage(
        displayName="Ana Souza", vcard=vcard))
    assert wa.conteudo_de(um)[1] == "contato: Ana Souza, +5551999998888"
    assert wa.contatos_da_mensagem(um) == [{
        "nome": "Ana Souza", "telefone": "+5551999998888",
        "id": "5551999998888@s.whatsapp.net"}]
    msg, _ = wa.converter(evento("C1", um), "w1", "c")
    assert m.extras_de(msg)["mencoes"][0]["id"] == \
        "5551999998888@s.whatsapp.net"
    varios = E.Message(contactsArrayMessage=E.ContactsArrayMessage(contacts=[
        E.ContactMessage(displayName="Ana", vcard=vcard),
        E.ContactMessage(displayName="Bia")]))
    texto = wa.conteudo_de(varios)[1]
    assert texto == "2 contatos: Ana, +5551999998888; Bia"
    assert [p["nome"] for p in wa.contatos_da_mensagem(varios)] == [
        "Ana", "Bia"]
    sem_waid = E.Message(contactMessage=E.ContactMessage(
        displayName="Cao", vcard="BEGIN:VCARD\nTEL:11 2222-3333\nEND:VCARD"))
    assert wa.contatos_da_mensagem(sem_waid) == [
        {"nome": "Cao", "telefone": "11 2222-3333", "id": ""}]


def test_resposta_em_particular_a_mensagem_de_grupo_diz_de_qual_grupo(
        tmp_path):
    b = ev.Barramento()
    banco = Banco(str(tmp_path / "s.db"))
    p = wa.ProvedorWhatsApp(m.Conta("w1", "whatsapp"), b, banco,
                            pasta_sessoes=str(tmp_path),
                            fabrica_cliente=ClienteFalso)
    banco.salvar_mensagens([m.Mensagem(
        "w1", "123@g.us", "G1", autor="Bia", texto="oi pessoal",
        remetente="5551999990000@s.whatsapp.net")])
    msg = p._mensagem_de_texto("5551999990000@s.whatsapp.net", "falo aqui",
                               "G1")
    ctx = msg.extendedTextMessage.contextInfo
    assert ctx.stanzaID == "G1" and ctx.remoteJID == "123@g.us"
    assert ctx.quotedMessage.conversation == "oi pessoal"
    assert ctx.participant == "5551999990000@s.whatsapp.net"
    # resposta normal, na mesma conversa: sem remoteJID
    banco.salvar_mensagens([m.Mensagem(
        "w1", "5551999990000@s.whatsapp.net", "P1", texto="e ai",
        remetente="5551999990000@s.whatsapp.net")])
    normal = p._mensagem_de_texto("5551999990000@s.whatsapp.net", "ok", "P1")
    assert not normal.extendedTextMessage.contextInfo.remoteJID
    banco.fechar()


def test_grupo_so_de_admins_vira_somente_leitura_para_quem_nao_e_admin(
        tmp_path):
    b = ev.Barramento()
    banco = Banco(str(tmp_path / "s.db"))
    p = wa.ProvedorWhatsApp(m.Conta("w1", "whatsapp"), b, banco,
                            pasta_sessoes=str(tmp_path),
                            fabrica_cliente=ClienteFalso)
    c = m.Conversa("w1", "123@g.us", "Aviso", "whatsapp", "grupo")
    banco.salvar_conversas([c])
    p._conversas = {c.id: c}
    p._conectada = True

    def info(anuncio, admin):
        return N.GroupInfo(
            GroupAnnounce=N.GroupAnnounce(IsAnnounce=anuncio),
            Participants=[
                N.GroupParticipant(JID=jid("5551999990000"), IsAdmin=admin),
                N.GroupParticipant(JID=jid("5551888880000"), IsAdmin=True)])
    dados = {"info": info(True, False)}
    p.cliente = types.SimpleNamespace(
        get_group_info=lambda j_: dados["info"],
        get_me=lambda: types.SimpleNamespace(
            JID=jid("5551999990000"), LID=jid("")))
    p._conferir_escrita(c.id, True)
    assert c.somente_leitura and banco.conversas("w1")[0].somente_leitura
    dados["info"] = info(True, True)                 # virei admin
    p._conferir_escrita(c.id, True)
    assert not c.somente_leitura
    dados["info"] = info(False, False)               # todos podem escrever
    p._conferir_escrita(c.id, True)
    assert not c.somente_leitura

    def sai(j_):
        raise RuntimeError("403 forbidden")
    p.cliente.get_group_info = sai                   # nao participo mais
    p._conferir_escrita(c.id, True)
    assert c.somente_leitura
    canal = m.Conversa("w1", "999@newsletter", "Canal", "whatsapp", "canal")
    p._conversas[canal.id] = canal
    p._publicar_conversas()
    assert canal.somente_leitura
    banco.fechar()


def test_editar_mensagem_manda_a_edicao_e_atualiza_o_texto(tmp_path):
    b = ev.Barramento()
    banco = Banco(str(tmp_path / "s.db"))
    p = wa.ProvedorWhatsApp(m.Conta("w1", "whatsapp"), b, banco,
                            pasta_sessoes=str(tmp_path),
                            fabrica_cliente=ClienteFalso)
    cid = "5551@s.whatsapp.net"
    x = m.Mensagem("w1", cid, "E1", minha=True, texto="oi", data=TS)
    banco.salvar_mensagens([x])
    enviados = []
    p.cliente = types.SimpleNamespace(
        edit_message=lambda chat, id_, nova: enviados.append(
            (id_, nova.conversation)))
    p._conectada = True
    publicados = []
    p.barramento = types.SimpleNamespace(
        publicar=lambda e: publicados.append(e))
    p._editar(x, "oi, tudo bem?")
    assert enviados == [("E1", "oi, tudo bem?")]
    guardada = banco.mensagem("w1", cid, "E1")
    assert guardada.texto == "oi, tudo bem?"
    assert m.extras_de(guardada)["editada"]
    assert publicados[-1].motivo == "editada"
    p.cliente = types.SimpleNamespace(
        edit_message=lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    p._editar(x, "outra")
    assert isinstance(publicados[-1], ev.Aviso)
    assert banco.mensagem("w1", cid, "E1").texto == "oi, tudo bem?"
    banco.fechar()


def _provedor_com_cliente(tmp_path, cliente):
    b = ev.Barramento()
    banco = Banco(str(tmp_path / "s.db"))
    p = wa.ProvedorWhatsApp(m.Conta("w1", "whatsapp"), b, banco,
                            pasta_sessoes=str(tmp_path),
                            fabrica_cliente=ClienteFalso)
    p.cliente = cliente
    p._conectada = True
    return p, banco


def _grupo_info(nome="Turma"):
    return N.GroupInfo(
        JID=jid("123", "g.us"), GroupName=N.GroupName(Name=nome),
        GroupTopic=N.GroupTopic(Topic="Aviso", TopicID="T1"),
        GroupAnnounce=N.GroupAnnounce(IsAnnounce=True),
        GroupCreated=TS,
        Participants=[
            N.GroupParticipant(JID=jid("5551999990000"), IsAdmin=True),
            N.GroupParticipant(JID=jid("5551888880000"),
                               DisplayName="Bia"),
            N.GroupParticipant(JID=jid("77", "lid"),
                               PhoneNumber=jid("5551777770000"),
                               IsSuperAdmin=True, IsAdmin=True)])


def test_detalhes_do_grupo_lista_participantes_e_diz_se_sou_admin(tmp_path):
    cliente = types.SimpleNamespace(
        get_group_info=lambda j_: _grupo_info(),
        get_me=lambda: types.SimpleNamespace(
            JID=jid("5551999990000"), LID=jid("")),
        contact=types.SimpleNamespace(
            get_contact=lambda j_: types.SimpleNamespace(
                FullName="", FirstName="", PushName="", BusinessName="")))
    p, banco = _provedor_com_cliente(tmp_path, cliente)
    d = p.detalhes_do_grupo("123@g.us")
    assert d["nome"] == "Turma" and d["descricao"] == "Aviso"
    assert d["anuncio"] and d["sou_admin"] and not d["comunidade"]
    nomes = [x["id"] for x in d["participantes"]]
    assert nomes[0] == "5551777770000@s.whatsapp.net"      # dono primeiro
    assert [x["admin"] for x in d["participantes"]] == [True, True, False]
    assert sum(1 for x in d["participantes"] if x["eu"]) == 1
    assert p.detalhes_do_grupo("5551@s.whatsapp.net") is None
    banco.fechar()


def test_grupos_em_comum_acha_pelo_telefone_ou_pelo_lid(tmp_path):
    outro = _grupo_info("Outro")
    outro.JID.CopyFrom(jid("456", "g.us"))
    cliente = types.SimpleNamespace(
        get_joined_groups=lambda: [_grupo_info(), outro,
                                   N.GroupInfo(GroupName=N.GroupName(
                                       Name="Sem ela"))])
    p, banco = _provedor_com_cliente(tmp_path, cliente)
    achados = p.grupos_em_comum("5551888880000@s.whatsapp.net")
    assert [g[1] for g in achados] == ["Outro", "Turma"]
    assert p.grupos_em_comum("5559@s.whatsapp.net") == []
    banco.fechar()


def test_administrar_grupo_chama_o_whatsapp_e_traduz_a_resposta(tmp_path):
    chamadas = []
    cliente = types.SimpleNamespace(
        set_group_name=lambda j_, nome: chamadas.append(("nome", nome)),
        set_group_announce=lambda j_, v: chamadas.append(("anuncio", v)),
        get_group_info=lambda j_: _grupo_info(),
        set_group_topic=lambda j_, ant, novo, t: chamadas.append(
            ("topico", ant, t)),
        update_group_participants=lambda j_, lista, acao: chamadas.append(
            (acao.value, lista[0].User)) or [],
        get_group_invite_link=lambda j_, revogar: "https://chat/x")
    p, banco = _provedor_com_cliente(tmp_path, cliente)
    cid = "123@g.us"
    assert p.administrar_grupo(cid, "nome", "Novo")[0]
    assert p.administrar_grupo(cid, "descricao", "Texto")[0]
    assert p.administrar_grupo(cid, "anuncio", True)[0]
    assert p.administrar_grupo(cid, "adicionar", "+55 51 99999-1111")[0]
    assert p.administrar_grupo(cid, "promover",
                               "5551888880000@s.whatsapp.net")[0]
    assert p.administrar_grupo(cid, "link") == (True, "https://chat/x")
    ok, texto = p.administrar_grupo(cid, "adicionar", "12")
    assert not ok and "número" in texto
    assert chamadas[0] == ("nome", "Novo")
    assert chamadas[1][:2] == ("topico", "T1")
    assert ("add", "5551999991111") in chamadas
    assert ("promote", "5551888880000") in chamadas

    def recusa(*a):
        raise RuntimeError("403")
    cliente.set_group_name = recusa
    ok, texto = p.administrar_grupo(cid, "nome", "X")
    assert not ok and "RuntimeError" in texto
    banco.fechar()


def test_detalhes_do_canal(tmp_path):
    meta = N.NewsletterThreadMetadata(
        Name=N.NewsletterText(Text="Canal"),
        Description=N.NewsletterText(Text="Sobre"), SubscriberCount=1234,
        VerificationState=1, InviteCode="abc")
    info = N.NewsletterMetadata(
        ThreadMeta=meta, ViewerMeta=N.NewsletterViewerMetadata(Mute=1, Role=3))
    p, banco = _provedor_com_cliente(tmp_path, types.SimpleNamespace(
        get_newsletter_info=lambda j_: info))
    d = p.detalhes_do_canal("999@newsletter")
    assert (d["nome"], d["seguidores"], d["verificado"], d["silenciado"],
            d["papel"], d["sou_admin"]) == ("Canal", 1234, True, True,
                                             "administrador", True)
    assert d["link"] == "https://whatsapp.com/channel/abc"
    banco.fechar()


def test_convite_de_grupo_e_link_viram_botao_de_entrar():
    convite = E.Message(groupInviteMessage=E.GroupInviteMessage(
        groupJID="123@g.us", inviteCode="ABCDEFGHIJKLMNOPQRST",
        inviteExpiration=1790000000, groupName="Turma"))
    msg, _ = wa.converter(evento("I1", convite), "w1", "c")
    acoes = m.extras_de(msg)["acoes"]
    assert [a["tipo"] for a in acoes] == ["entrar"]
    assert acoes[0]["rotulo"] == "Entrar no grupo Turma"
    assert acoes[0]["codigo"] == "ABCDEFGHIJKLMNOPQRST"
    assert acoes[0]["expira"] == 1790000000 and acoes[0]["grupo"] == "123@g.us"
    link = E.Message(conversation="entra aqui "
                     "https://chat.whatsapp.com/KLMNOPQRSTABCDEFGHIJ valeu")
    msg, _ = wa.converter(evento("I2", link), "w1", "c")
    acoes = m.extras_de(msg)["acoes"]
    assert len(acoes) == 1 and acoes[0]["codigo"] == "KLMNOPQRSTABCDEFGHIJ"
    assert "link" in acoes[0]["rotulo"]
    # o mesmo codigo no convite e no texto nao vira dois botoes
    dobro = E.Message(extendedTextMessage=E.ExtendedTextMessage(
        text="https://chat.whatsapp.com/ABCDEFGHIJKLMNOPQRST"))
    assert len(wa.entradas_de_grupo(dobro, "https://chat.whatsapp.com/"
                                    "ABCDEFGHIJKLMNOPQRST")) == 1


def test_entrar_no_grupo_pelo_convite_ou_pelo_link(tmp_path):
    chamadas = []
    cliente = types.SimpleNamespace(
        join_group_with_invite=lambda g, q, c, e: chamadas.append(
            ("convite", g.User, q.User, c, e)),
        join_group_with_link=lambda c: chamadas.append(("link", c)),
        get_group_info_from_invite=lambda g, q, c, e: _grupo_info("Turma"),
        get_group_info_from_link=lambda c: _grupo_info("Do link"),
        get_me=lambda: types.SimpleNamespace(JID=jid("1"), LID=jid("")))
    p, banco = _provedor_com_cliente(tmp_path, cliente)
    msg = m.Mensagem("w1", "5551@s.whatsapp.net", "I1",
                     remetente="5551@s.whatsapp.net")
    por_convite = {"tipo": "entrar", "codigo": "ABC", "grupo": "123@g.us",
                   "expira": 17}
    por_link = {"tipo": "entrar", "codigo": "XYZ"}
    assert p.previa_do_convite(msg, por_convite)["nome"] == "Turma"
    assert p.previa_do_convite(msg, por_link)["nome"] == "Do link"
    assert p.previa_do_convite(msg, por_link)["membros"] == 3
    assert p.entrar_no_grupo(msg, por_convite) == (True, "Você entrou no grupo.")
    assert p.entrar_no_grupo(msg, por_link)[0]
    assert chamadas == [("convite", "123", "5551", "ABC", 17),
                        ("link", "XYZ")]

    def recusa(*a):
        raise RuntimeError("gone")
    cliente.join_group_with_link = recusa
    cliente.get_group_info_from_link = recusa
    ok, texto = p.entrar_no_grupo(msg, por_link)
    assert not ok and "convite" in texto
    assert "erro" in p.previa_do_convite(msg, por_link)
    banco.fechar()

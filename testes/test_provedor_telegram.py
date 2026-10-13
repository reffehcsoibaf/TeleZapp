# SPDX-License-Identifier: GPL-3.0-or-later
"""Provedor do Telegram com um cliente simulado (sem rede).

Roda o provedor de verdade, na thread dele, e confere os eventos que chegam
a 'interface' e o que fica gravado no banco.
"""
import datetime
import queue
import types

import pytest
from telethon import errors

from telezapp.armazenamento.banco import Banco
from telezapp.nucleo import eventos as ev
from telezapp.nucleo import modelos as m
from telezapp.provedores import base
from telezapp.provedores import telegram as tg

DATA = datetime.datetime(2026, 10, 13, 18, 0, tzinfo=datetime.timezone.utc)


def mensagem(id, texto="", out=False, sender=None, **extra):
    campos = dict(id=id, message=texto, out=out, sender=sender, date=DATA,
                  action=None, reply_to=None, post_author=None, media=None,
                  web_preview=None, file=None)
    for k in ("voice", "video_note", "gif", "video", "sticker", "photo",
              "audio", "document", "poll", "geo", "contact"):
        campos[k] = None
    campos.update(extra)
    return types.SimpleNamespace(**campos)


ANA = types.SimpleNamespace(first_name="Ana", last_name="Silva",
                            username="ana", title=None)


# ------------------------------------------------------------ conversao
def test_converter_texto_recebido():
    x = tg.converter(mensagem(7, "Oi", sender=ANA), "t1", 10)
    assert (x.id, x.conversa_id, x.autor, x.minha, x.tipo, x.texto) == (
        "7", "10", "Ana Silva", False, m.TEXTO, "Oi")
    assert x.data == DATA.timestamp()


def test_converter_minha_lida_e_resposta():
    resp = types.SimpleNamespace(reply_to_msg_id=5)
    x = tg.converter(mensagem(8, "ok", out=True, reply_to=resp), "t1", 10,
                     lidas_ate=8)
    assert x.minha and x.estado == m.LIDA and x.resposta_a == "5"
    y = tg.converter(mensagem(9, "e?", out=True), "t1", 10, lidas_ate=8)
    assert y.estado == m.ENVIADA


def test_converter_midias():
    arq = types.SimpleNamespace(duration=12.4, name="", size=3000)
    voz = tg.converter(mensagem(1, voice=object(), document=object(),
                                media=object(), file=arq), "t1", 1)
    assert voz.tipo == m.VOZ and voz.segundos == 12
    doc_arq = types.SimpleNamespace(duration=None, name="a.pdf", size=2048)
    doc = tg.converter(mensagem(2, "veja", document=object(), media=object(),
                                file=doc_arq), "t1", 1)
    assert (doc.tipo, doc.nome_arquivo, doc.tamanho, doc.texto) == (
        m.DOCUMENTO, "a.pdf", 2048, "veja")
    link = tg.converter(mensagem(3, "https://x", media=object(),
                                 web_preview=object()), "t1", 1)
    assert link.tipo == m.TEXTO


def test_converter_enquete_e_servico():
    poll = types.SimpleNamespace(poll=types.SimpleNamespace(
        question=types.SimpleNamespace(text="Pizza?")))
    x = tg.converter(mensagem(4, media=object(), poll=poll), "t1", 1)
    assert x.tipo == m.OUTRO and x.texto == "enquete: Pizza?"
    assert tg.converter(mensagem(5, action=object()), "t1", 1) is None


def test_canal_usa_assinatura_ou_nome_da_conversa():
    x = tg.converter(mensagem(6, "post", post_author="Redação"), "t1", 1,
                     nome_padrao="Canal")
    assert x.autor == "Redação"
    y = tg.converter(mensagem(7, "post"), "t1", 1, nome_padrao="Canal")
    assert y.autor == "Canal"


# ------------------------------------------------- provedor de verdade
class ClienteFalso:
    def __init__(self, autorizado=True, codigo_certo="12345", senha=None):
        self.autorizado = autorizado
        self.codigo_certo = codigo_certo
        self.senha = senha
        self.enviadas = []
        self.lidas = []
        self.pedidos_codigo = []
        self.handlers = []
        self.desconectou = False

    async def connect(self):
        pass

    async def disconnect(self):
        self.desconectou = True

    async def is_user_authorized(self):
        return self.autorizado

    async def send_code_request(self, telefone):
        if telefone == "+5500000000000":
            raise errors.PhoneNumberInvalidError(None)
        self.pedidos_codigo.append(telefone)

    async def sign_in(self, telefone=None, codigo=None, password=None):
        if password is not None:
            if password != self.senha:
                raise errors.PasswordHashInvalidError(None)
            self.autorizado = True
            return
        if codigo != self.codigo_certo:
            raise errors.PhoneCodeInvalidError(None)
        if self.senha:
            raise errors.SessionPasswordNeededError(None)
        self.autorizado = True

    async def get_me(self):
        return types.SimpleNamespace(first_name="Fábio", last_name="",
                                     username="", title=None,
                                     phone="5551999998888")

    def add_event_handler(self, f, evento):
        self.handlers.append(f)

    async def iter_dialogs(self, limit=None, archived=None):
        for d in (
            types.SimpleNamespace(
                id=10, name="Ana", unread_count=2, date=DATA,
                input_entity="peer10", is_group=False, is_channel=False,
                dialog=types.SimpleNamespace(read_outbox_max_id=3)),
            types.SimpleNamespace(
                id=-100, name="Família", unread_count=0, date=None,
                input_entity="peer-100", is_group=True, is_channel=True,
                dialog=types.SimpleNamespace(read_outbox_max_id=0))):
            yield d

    async def iter_messages(self, ent, limit=None):
        for i in (4, 3, 2):
            yield mensagem(i, "m%d" % i, out=(i == 3), sender=ANA)
        yield mensagem(1, action=object())

    async def get_input_entity(self, id):
        return "peer%d" % id

    async def send_message(self, ent, texto, reply_to=None):
        if texto == "falhar":
            raise errors.ChatWriteForbiddenError(None)
        self.enviadas.append((ent, texto, reply_to))
        return mensagem(99, texto, out=True)

    async def send_read_acknowledge(self, ent):
        self.lidas.append(ent)


class Provedor(tg.ProvedorTelegram):
    def __init__(self, cliente, *a, **k):
        super().__init__(*a, **k)
        self._falso = cliente

    def _novo_cliente(self):
        return self._falso


@pytest.fixture
def ambiente(tmp_path):
    fila = queue.Queue()
    barramento = ev.Barramento()
    barramento.ouvir(fila.put)
    banco = Banco(str(tmp_path / "t.db"))
    respostas = {}

    def pedir(etapa, erro):
        lista = respostas.get(etapa, [])
        return lista.pop(0) if lista else None

    def criar(cliente, telefone="", nova=False):
        conta = m.Conta("t1", "telegram", telefone)
        p = Provedor(cliente, conta, barramento, banco, pedir, (1, "x" * 32),
                     str(tmp_path), perguntar_telefone=nova)
        return p
    yield types.SimpleNamespace(fila=fila, banco=banco, criar=criar,
                                respostas=respostas)
    banco.fechar()


def esperar(fila, tipo, segundos=5):
    while True:
        e = fila.get(timeout=segundos)
        if isinstance(e, tipo):
            return e


def test_sessao_salva_conecta_e_lista_conversas(ambiente):
    cliente = ClienteFalso()
    p = ambiente.criar(cliente)
    p.iniciar()
    try:
        pronta = esperar(ambiente.fila, ev.ContaPronta)
        assert pronta.telefone == "+5551999998888" and pronta.nome == "Fábio"
        convs = esperar(ambiente.fila, ev.ConversasAtualizadas).conversas
        assert [(c.nome, c.tipo, c.nao_lidas) for c in convs] == [
            ("Ana", "privada", 2), ("Família", "grupo", 0)]
        assert len(ambiente.banco.conversas("t1")) == 2
        assert len(cliente.handlers) == 2

        p.carregar_mensagens("10")
        msgs = esperar(ambiente.fila, ev.MensagensCarregadas).mensagens
        assert [x.id for x in msgs] == ["2", "3", "4"]   # sem a de servico
        assert msgs[1].minha and msgs[1].estado == m.LIDA  # 3 <= lidas_ate
        assert len(ambiente.banco.mensagens("t1", "10")) == 3

        p.enviar_texto("10", "olá", resposta_a="4")
        nova = esperar(ambiente.fila, ev.MensagemNova)
        assert nova.enviada_daqui and nova.mensagem.id == "99"
        assert cliente.enviadas == [("peer10", "olá", 4)]

        p.enviar_texto("10", "falhar")
        falha = esperar(ambiente.fila, ev.EnvioFalhou)
        assert "permissão" in falha.motivo and falha.texto == "falhar"

        p.marcar_como_lida("10")
        p.carregar_mensagens("-100")   # garante que a anterior terminou
        esperar(ambiente.fila, ev.MensagensCarregadas)
        assert cliente.lidas == ["peer10"]
        assert ambiente.banco.conversas("t1")[0].nao_lidas == 0
    finally:
        p.parar()
    assert cliente.desconectou


def test_login_com_erros_e_senha(ambiente):
    cliente = ClienteFalso(autorizado=False, senha="segredo")
    ambiente.respostas.update({
        base.PEDIR_TELEFONE: ["12", "+5500000000000", "51 99999 8888"],
        base.PEDIR_CODIGO: ["111", "1 2 3 4 5"],
        base.PEDIR_SENHA: ["errada", "segredo"],
    })
    p = ambiente.criar(cliente)
    p.iniciar()
    try:
        esperar(ambiente.fila, ev.ContaPronta)
        assert cliente.pedidos_codigo == ["+5551999998888"]
        assert ambiente.respostas[base.PEDIR_SENHA] == []
    finally:
        p.parar()


def test_conta_nova_pergunta_o_numero_mesmo_com_sugestao(ambiente):
    cliente = ClienteFalso(autorizado=False)
    ambiente.respostas.update({base.PEDIR_TELEFONE: ["51 98888 7777"],
                               base.PEDIR_CODIGO: ["12345"]})
    p = ambiente.criar(cliente, telefone="+5551999998888", nova=True)
    p.iniciar()
    try:
        esperar(ambiente.fila, ev.ContaPronta)
        assert cliente.pedidos_codigo == ["+5551988887777"]
    finally:
        p.parar()


def test_login_cancelado(ambiente):
    cliente = ClienteFalso(autorizado=False)
    p = ambiente.criar(cliente, telefone="+5551999998888")
    p.iniciar()   # nao ha resposta para o codigo: pedir devolve None
    try:
        e = esperar(ambiente.fila, ev.EstadoConta)
        while e.estado != ev.PRECISA_LOGIN:
            e = esperar(ambiente.fila, ev.EstadoConta)
        assert e.detalhe == "login cancelado"
    finally:
        p.parar()


def test_mensagem_recebida_e_leitura(ambiente):
    import asyncio
    cliente = ClienteFalso()
    p = ambiente.criar(cliente)
    p.iniciar()
    try:
        esperar(ambiente.fila, ev.ConversasAtualizadas)
        receber, ler = cliente.handlers

        async def chegar():
            async def get_chat():
                return ANA

            async def get_input_chat():
                return "peer77"
            evento = types.SimpleNamespace(
                message=mensagem(50, "nova", sender=ANA), chat_id=77,
                is_group=False, is_channel=False, get_chat=get_chat,
                get_input_chat=get_input_chat)
            await receber(evento)
            await ler(types.SimpleNamespace(chat_id=10, max_id=4))
        asyncio.run_coroutine_threadsafe(chegar(), p._loop).result(5)
        nova = esperar(ambiente.fila, ev.MensagemNova)
        assert not nova.enviada_daqui and nova.conversa.nome == "Ana Silva"
        assert nova.conversa.nao_lidas == 1
        leitura = esperar(ambiente.fila, ev.LeituraConfirmada)
        assert (leitura.conversa_id, leitura.ate_id) == ("10", 4)
    finally:
        p.parar()

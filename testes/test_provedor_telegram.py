# SPDX-License-Identifier: GPL-3.0-or-later
"""Provedor do Telegram com um cliente simulado (sem rede).

Roda o provedor de verdade, na thread dele, e confere os eventos que chegam
a 'interface' e o que fica gravado no banco.
"""
import datetime
import os
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

    async def get_entity(self, usuario):
        self.buscas = getattr(self, "buscas", [])
        self.buscas.append(usuario)
        if usuario == "naoexiste":
            raise ValueError("sem usuario")
        return types.SimpleNamespace(id=777, first_name="Bia", last_name="",
                                     username=usuario, title=None)

    async def send_message(self, ent, texto, reply_to=None):
        if texto == "falhar":
            raise errors.ChatWriteForbiddenError(None)
        self.enviadas.append((ent, texto, reply_to))
        return mensagem(99, texto, out=True)

    async def get_messages(self, ent, ids=None):
        if ids == 404:
            return None
        grande = ids == 500
        return mensagem(ids, media=object(), photo=object(),
                        file=types.SimpleNamespace(
                            mime_type="video/mp4" if grande else "image/png",
                            size=len(self.conteudo_grande) if grande else 0))

    async def download_media(self, msg, file=None, progress_callback=None):
        if self.falha_download:
            raise OSError("rede")
        progress_callback(50, 100)
        progress_callback(100, 100)
        with open(file, "wb") as f:
            f.write(b"png")

    falha_download = False
    conteudo_grande = bytes((i * 7) % 251 for i in range(
        5 * 512 * 1024 + 1000))        # 5 partes e meia

    async def iter_download(self, media, offset=0, stride=None,
                            chunk_size=None, request_size=None, limit=None,
                            file_size=None):
        self.pedidos_partes = getattr(self, "pedidos_partes", [])
        for k in range(limit):
            ini = offset + k * stride
            self.pedidos_partes.append(ini)
            yield self.conteudo_grande[ini:ini + chunk_size]

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
        assert len(cliente.handlers) == 3

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
        receber, ler, _ = cliente.handlers

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


def test_baixar_arquivo(ambiente, tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path / "dados"))
    from telezapp.midia import armazem
    cliente = ClienteFalso()
    p = ambiente.criar(cliente)
    p.iniciar()
    try:
        esperar(ambiente.fila, ev.ConversasAtualizadas)
        x = m.Mensagem("t1", "10", "7", tipo=m.FOTO)
        feitos = []
        caminho = p.baixar_arquivo(x, armazem.caminho_base(x), feitos.append,
                                   lambda: False)
        assert caminho.endswith(".png") and open(caminho, "rb").read() == \
            b"png"
        assert feitos == [0, 50, 100, 100]
        assert not os.path.exists(caminho + ".parte")

        with pytest.raises(base.DownloadCancelado):
            p.baixar_arquivo(x, armazem.caminho_base(x), lambda v: None,
                             lambda: True)
        with pytest.raises(base.ErroMidia, match="não tem mais"):
            p.baixar_arquivo(m.Mensagem("t1", "10", "404", tipo=m.FOTO),
                             armazem.caminho_base(x), lambda v: None,
                             lambda: False)
        cliente.falha_download = True
        with pytest.raises(base.ErroMidia, match="não entregou"):
            p.baixar_arquivo(x, armazem.caminho_base(x) + "2",
                             lambda v: None, lambda: False)
    finally:
        p.parar()


def test_baixar_arquivo_grande_em_partes_paralelas(ambiente, tmp_path,
                                                   monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path / "dados"))
    from telezapp.midia import armazem
    cliente = ClienteFalso()
    p = ambiente.criar(cliente)
    p.iniciar()
    try:
        esperar(ambiente.fila, ev.ConversasAtualizadas)
        x = m.Mensagem("t1", "10", "500", tipo=m.VIDEO)
        feitos = []
        caminho = p.baixar_arquivo(x, armazem.caminho_base(x), feitos.append,
                                   lambda: False)
        assert caminho.endswith(".mp4")
        assert open(caminho, "rb").read() == ClienteFalso.conteudo_grande
        assert sorted(cliente.pedidos_partes) == [
            k * tg.PARTE_DOWNLOAD for k in range(6)]
        assert feitos[0] == 0 and feitos[-1] == 100
        assert feitos == sorted(feitos)
        with pytest.raises(base.DownloadCancelado):
            p.baixar_arquivo(x, armazem.caminho_base(x) + "b",
                             lambda v: None, lambda: True)
        assert not [n for _, _, ns in os.walk(str(tmp_path / "dados"))
                    for n in ns if n.endswith(".parte")]
    finally:
        p.parar()


def test_converter_links_escondidos_botoes_e_mencoes():
    from telethon.tl import types as T
    # a figurinha de emoji conta 2 posicoes UTF-16: confere o deslocamento
    texto = "😀 veja aqui, fale com @bia e Carla, ou t.me/canal"
    off_aqui = len("😀 veja ".encode("utf-16-le")) // 2
    off_bia = len("😀 veja aqui, fale com ".encode("utf-16-le")) // 2
    off_carla = len("😀 veja aqui, fale com @bia e ".encode("utf-16-le")) // 2
    off_url = len("😀 veja aqui, fale com @bia e Carla, ou ".encode(
        "utf-16-le")) // 2
    ents = [
        T.MessageEntityTextUrl(offset=off_aqui, length=4,
                               url="https://exemplo.com/x"),
        T.MessageEntityMention(offset=off_bia, length=4),
        T.MessageEntityMentionName(offset=off_carla, length=5, user_id=42),
        T.MessageEntityUrl(offset=off_url, length=10)]
    marcador = T.ReplyInlineMarkup(rows=[T.KeyboardInlineButtonRow(buttons=[
        T.KeyboardInlineButton(text="Site",
                               type=T.InlineButtonTypeUrl(url="https://s.com")),
        T.KeyboardInlineButton(text="Votar",
                               type=T.InlineButtonTypeCallback(data=b"x"))])])
    x = tg.converter(mensagem(7, texto, sender=ANA, entities=ents,
                              reply_markup=marcador), "t1", 10)
    extras = m.extras_de(x)
    assert extras["links"] == [["https://exemplo.com/x", "aqui"],
                               ["https://t.me/canal", "t.me/canal"]]
    assert extras["botoes"] == [["Site", "https://s.com"]]   # sem callback
    assert extras["mencoes"] == [{"usuario": "bia"},
                                 {"id": "42", "nome": "Carla"}]


def test_mencao_por_usuario_ganha_id_e_nome(ambiente):
    from telethon.tl import types as T
    cliente = ClienteFalso()

    async def iter_messages(ent, limit=None):
        t = "oi @bia e @carla e @naoexiste"
        yield mensagem(5, t, sender=ANA, entities=[
            T.MessageEntityMention(offset=t.index("@bia"), length=4),
            T.MessageEntityMention(offset=t.index("@carla"), length=6),
            T.MessageEntityMention(offset=t.index("@naoexiste"), length=10)])
    cliente.iter_messages = iter_messages
    p = ambiente.criar(cliente)
    p.iniciar()
    try:
        esperar(ambiente.fila, ev.ConversasAtualizadas)
        p.carregar_mensagens("10")
        x = esperar(ambiente.fila, ev.MensagensCarregadas).mensagens[0]
        men = m.extras_de(x)["mencoes"]
        assert men[0] == {"usuario": "bia", "id": "777", "nome": "Bia"}
        assert men[1]["usuario"] == "carla" and men[1]["id"] == "777"
        assert "id" not in men[2]               # nao achou: fica sem id
        assert cliente.buscas == ["bia", "carla", "naoexiste"]
        guardada = ambiente.banco.mensagem("t1", "10", "5")
        assert m.extras_de(guardada)["mencoes"][0]["nome"] == "Bia"
    finally:
        p.parar()


def test_botao_de_link_no_formato_antigo_do_telethon():
    class KeyboardButtonUrl:           # nome da classe nas versoes antigas
        def __init__(self, text, url):
            self.text, self.url = text, url

    class KeyboardButtonCallback:
        def __init__(self, text):
            self.text = text
    linha = types.SimpleNamespace(buttons=[
        KeyboardButtonUrl("Site", "https://s.com"),
        KeyboardButtonCallback("Votar")])
    x = tg.converter(mensagem(7, "oi", sender=ANA,
                              reply_markup=types.SimpleNamespace(
                                  rows=[linha])), "t1", 10)
    assert m.extras_de(x)["botoes"] == [["Site", "https://s.com"]]


def test_grupo_renomeado_no_telegram_atualiza_a_conversa(ambiente):
    import asyncio
    cliente = ClienteFalso()
    p = ambiente.criar(cliente)
    p.iniciar()
    try:
        esperar(ambiente.fila, ev.ConversasAtualizadas)
        acao = cliente.handlers[2]
        asyncio.run(acao(types.SimpleNamespace(new_title="Família 2",
                                               chat_id=10)))
        convs = esperar(ambiente.fila, ev.ConversasAtualizadas).conversas
        assert "Família 2" in [c.nome for c in convs]
        assert "Família 2" in [c.nome for c in ambiente.banco.conversas("t1")]
        # sem mudanca de nome, ou de uma conversa desconhecida: nada
        asyncio.run(acao(types.SimpleNamespace(new_title=None, chat_id=10)))
        asyncio.run(acao(types.SimpleNamespace(new_title="X", chat_id=999)))
        assert ambiente.fila.empty()
    finally:
        p.parar()

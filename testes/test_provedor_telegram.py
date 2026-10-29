# SPDX-License-Identifier: GPL-3.0-or-later
"""Provedor do Telegram com um cliente simulado (sem rede).

Roda o provedor de verdade, na thread dele, e confere os eventos que chegam
a 'interface' e o que fica gravado no banco.
"""
import datetime
import os
import queue
import time
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
        self.requisicoes = []
        self.apagadas = []
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

    async def iter_dialogs(self, limit=None, folder=None, archived=None):
        if folder == 1:
            yield types.SimpleNamespace(
                id=77, name="Velha", unread_count=0, date=DATA,
                input_entity="peer77", is_group=False, is_channel=False,
                dialog=types.SimpleNamespace(read_outbox_max_id=0))
            return
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

    async def send_message(self, ent, texto="", reply_to=None,
                           link_preview=True, file=None):
        if texto == "falhar":
            raise errors.ChatWriteForbiddenError(None)
        if file is not None:
            self.enquetes = getattr(self, "enquetes", []) + [file]
            poll = file.poll
            return types.SimpleNamespace(
                id=98, message="", out=True, date=DATA, action=None,
                poll=types.SimpleNamespace(poll=types.SimpleNamespace(
                    id=555, question=poll.question, answers=poll.answers,
                    multiple_choice=poll.multiple_choice, closed=False,
                    public_voters=poll.public_voters), results=None),
                media=object(), sender=None, post_author="")
        self.enviadas.append((ent, texto, reply_to))
        return mensagem(99, texto, out=True)

    async def send_file(self, ent, caminho, caption=None,
                        force_document=False, voice_note=False,
                        attributes=None, **kw):
        if caption == "falhar":
            raise errors.ChatWriteForbiddenError(None)
        self.arquivos = getattr(self, "arquivos", [])
        self.arquivos.append(dict(ent=ent, caminho=caminho, caption=caption,
                                  documento=force_document,
                                  voz=voice_note, atributos=attributes))
        extra = dict(voice=object()) if voice_note else dict(
            document=object())
        return mensagem(100, caption or "", out=True, media=object(),
                        file=types.SimpleNamespace(
                            duration=3, name="", size=os.path.getsize(
                                caminho)), **extra)

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

    sem_foto = False

    async def download_profile_photo(self, ent, file=None):
        self.fotos = getattr(self, "fotos", []) + [(ent.id, file)]
        return None if self.sem_foto else b"\xff\xd8\xff"

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

    async def delete_messages(self, ent, ids, revoke=True):
        self.apagadas.append((ent, list(ids), revoke))

    async def __call__(self, requisicao):
        self.requisicoes.append(requisicao)


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
        assert [(c.nome, c.tipo, c.nao_lidas, c.arquivada) for c in convs] == [
            ("Ana", "privada", 2, False), ("Família", "grupo", 0, False),
            ("Velha", "privada", 0, True)]       # a da pasta de arquivadas
        assert len(ambiente.banco.conversas("t1")) == 3
        assert [c.arquivada for c in ambiente.banco.conversas("t1")
                if c.nome == "Velha"] == [True]
        assert len(cliente.handlers) == 9

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
        receber, ler, _, _, _, _, _, _, _ = cliente.handlers

        async def chegar():
            async def get_chat():
                return ANA

            async def get_input_chat():
                return "peer88"
            evento = types.SimpleNamespace(
                message=mensagem(50, "nova", sender=ANA), chat_id=88,
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


def test_voz_ouvida_aqui_avisa_o_telegram_e_ouvida_la_marca_aqui(ambiente):
    import asyncio
    cliente = ClienteFalso()
    p = ambiente.criar(cliente)
    p.iniciar()
    try:
        esperar(ambiente.fila, ev.ConversasAtualizadas)
        voz = m.Mensagem("t1", "10", "60", tipo=m.VOZ, segundos=5,
                         data=time.time())
        ambiente.banco.salvar_mensagens([voz])
        # tocada aqui: o Telegram recebe a leitura do conteudo
        p.marcar_ouvida(voz)
        def leituras():
            return [r for r in cliente.requisicoes if hasattr(r, "id")]
        for _ in range(100):
            if leituras():
                break
            time.sleep(0.05)
        assert leituras()[0].id == [60]
        # tocada no celular: a mensagem passa a constar ouvida
        conteudo_lido = cliente.handlers[4]
        asyncio.run_coroutine_threadsafe(
            conteudo_lido(types.SimpleNamespace(messages=[60])),
            p._loop).result(5)
        e = esperar(ambiente.fila, ev.MensagemAtualizada)
        assert e.motivo == "ouvida" and m.extras_de(e.mensagem)["ouvida"]
        assert m.extras_de(
            ambiente.banco.mensagem("t1", "10", "60"))["ouvida"]
    finally:
        p.parar()


def test_manter_apagadas_no_telegram_marca_em_vez_de_remover(
        ambiente, monkeypatch):
    import asyncio
    monkeypatch.setitem(m.MANTER, "apagadas", True)
    cliente = ClienteFalso()
    p = ambiente.criar(cliente)
    p.iniciar()
    try:
        esperar(ambiente.fila, ev.ConversasAtualizadas)
        ambiente.banco.salvar_mensagens([
            m.Mensagem("t1", "10", "61", texto="oi", data=time.time()),
            m.Mensagem("t1", "10", "62", texto="meu", minha=True,
                       data=time.time())])
        apagadas = cliente.handlers[3]
        asyncio.run_coroutine_threadsafe(
            apagadas(types.SimpleNamespace(deleted_ids=[61, 62],
                                           chat_id=None)),
            p._loop).result(5)
        a = esperar(ambiente.fila, ev.MensagemAtualizada)
        assert (a.mensagem.id, a.motivo) == ("61", "apagada")
        assert a.mensagem.texto == "oi"
        assert m.extras_de(a.mensagem)["apagada_pelo_autor"]
        # a minha, apagada em outro aparelho, continua sendo removida
        e = esperar(ambiente.fila, ev.MensagemApagadaNoCelular)
        assert e.mensagem_id == "62"
    finally:
        p.parar()


def test_mensagem_apagada_no_celular_e_apagada_daqui(ambiente):
    import asyncio
    cliente = ClienteFalso()
    p = ambiente.criar(cliente)
    p.iniciar()
    try:
        esperar(ambiente.fila, ev.ConversasAtualizadas)
        ambiente.banco.salvar_mensagens([
            m.Mensagem("t1", "10", "61", texto="oi", data=time.time())])
        apagadas = cliente.handlers[3]
        asyncio.run_coroutine_threadsafe(
            apagadas(types.SimpleNamespace(deleted_ids=[61], chat_id=None)),
            p._loop).result(5)
        e = esperar(ambiente.fila, ev.MensagemApagadaNoCelular)
        assert (e.conversa_id, e.mensagem_id) == ("10", "61")
        # apagada aqui: o Telegram recebe o pedido, para todos ou so para mim
        x = m.Mensagem("t1", "10", "61")
        assert p.apagar_mensagem(x, para_todos=True)
        for _ in range(100):
            if cliente.apagadas:
                break
            time.sleep(0.05)
        assert cliente.apagadas == [("peer10", [61], True)]
    finally:
        p.parar()


def test_foto_de_perfil_do_contato_e_do_grupo(ambiente):
    cliente = ClienteFalso()
    p = ambiente.criar(cliente)
    assert p.FOTO_DO_CONTATO and p.FOTO_DO_GRUPO
    assert p.foto_do_contato("10") == (False, "Sem conexão com o Telegram.")
    p.iniciar()
    try:
        esperar(ambiente.fila, ev.ConversasAtualizadas)
        assert p.foto_do_contato("10") == (True, b"\xff\xd8\xff")
        assert p.foto_do_grupo("-100") == (True, b"\xff\xd8\xff")
        assert cliente.fotos == [(777, bytes), (777, bytes)]
        cliente.sem_foto = True
        ok, texto = p.foto_do_contato("10")
        assert not ok and texto.startswith("Este contato não tem foto")
        ok, texto = p.foto_do_grupo("-100")
        assert not ok and texto.startswith("Este grupo não tem foto")
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


def test_enviar_nota_de_voz_e_documento(ambiente, tmp_path, monkeypatch):
    from telezapp.midia import envio
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path / "dados"))
    ogg = tmp_path / "voz-1.ogg"
    with open(os.path.join(os.path.dirname(__file__), "amostras",
                           "voz.ogg"), "rb") as f:
        ogg.write_bytes(f.read())
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    cliente = ClienteFalso()
    p = ambiente.criar(cliente)
    p.iniciar()
    try:
        esperar(ambiente.fila, ev.ConversasAtualizadas)
        voz = envio.preparar(str(ogg), voz=True, temporario=True)
        p.enviar_arquivo("10", voz)
        nova = esperar(ambiente.fila, ev.MensagemNova)
        assert nova.enviada_daqui and nova.mensagem.tipo == m.VOZ
        enviado = cliente.arquivos[0]
        assert enviado["voz"] and not enviado["documento"]
        assert enviado["atributos"][0].voice
        # a gravacao temporaria foi movida para o armazem do app
        assert not ogg.exists()
        guardada = ambiente.banco.midia("t1", "10", "100")
        assert guardada and os.path.isfile(guardada[0])

        p.enviar_arquivo("10", envio.preparar(str(pdf)), "o relatório")
        nova = esperar(ambiente.fila, ev.MensagemNova)
        assert nova.mensagem.id == "100"
        enviado = cliente.arquivos[1]
        assert enviado["documento"] and enviado["caption"] == "o relatório"
        assert pdf.exists()            # arquivo do usuario so e copiado

        p.enviar_arquivo("10", envio.preparar(str(pdf)), "falhar")
        falha = esperar(ambiente.fila, ev.EnvioFalhou)
        assert falha.tipo == m.DOCUMENTO and not falha.devolver_texto
        assert "permissão" in falha.motivo
    finally:
        p.parar()


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


def test_voz_ja_tocada_em_outro_aparelho_chega_como_ouvida():
    ja_ouvida = tg.converter(mensagem(1, voice=object(), media=object(),
                                      sender=ANA, media_unread=False),
                             "t1", 10)
    nova = tg.converter(mensagem(2, voice=object(), media=object(),
                                 sender=ANA, media_unread=True), "t1", 10)
    assert m.extras_de(ja_ouvida)["ouvida"] is True
    assert m.extras_de(nova)["ouvida"] is False
    minha = tg.converter(mensagem(3, voice=object(), media=object(),
                                  out=True, media_unread=False), "t1", 10)
    assert m.extras_de(minha)["ouvida"] is False


def test_contato_do_telegram_mostra_o_telefone_e_vira_pessoa():
    contato = types.SimpleNamespace(first_name="Ana", last_name="Lima",
                                    phone_number="5551999998888", user_id=77)
    x = tg.converter(mensagem(3, contact=contato, media=object()), "t1", 1)
    assert x.tipo == m.OUTRO
    assert x.texto == "contato: Ana Lima, +5551999998888"
    assert m.extras_de(x)["mencoes"] == [{
        "nome": "Ana Lima", "telefone": "+5551999998888", "id": "77"}]


def test_telegram_diz_quando_a_conta_nao_pode_escrever():
    def ent(nome, **k):
        cls = type(nome, (), {})
        o = cls()
        for a, v in dict(broadcast=False, left=False, creator=False,
                         admin_rights=None, banned_rights=None,
                         default_banned_rights=None, deactivated=False).items():
            setattr(o, a, k.get(a, v))
        return o
    sem_envio = types.SimpleNamespace(send_messages=True)
    assert not tg.somente_leitura_do_telegram(None)
    assert not tg.somente_leitura_do_telegram(ent("User"))
    assert tg.somente_leitura_do_telegram(ent("Channel", broadcast=True))
    assert not tg.somente_leitura_do_telegram(
        ent("Channel", broadcast=True, creator=True))
    assert not tg.somente_leitura_do_telegram(ent(
        "Channel", broadcast=True,
        admin_rights=types.SimpleNamespace(post_messages=True)))
    assert tg.somente_leitura_do_telegram(ent("Channel", left=True))
    assert tg.somente_leitura_do_telegram(ent(
        "Channel", default_banned_rights=sem_envio))
    assert not tg.somente_leitura_do_telegram(ent(
        "Channel", default_banned_rights=sem_envio,
        admin_rights=types.SimpleNamespace(post_messages=False)))
    assert tg.somente_leitura_do_telegram(ent("Chat", deactivated=True))
    assert tg.somente_leitura_do_telegram(ent("ChannelForbidden"))


def test_administrar_grupo_do_telegram_monta_os_pedidos_certos():
    import asyncio
    from telethon.tl import functions, types as T
    ent = T.Channel(id=1, title="G", photo=T.ChatPhotoEmpty(), date=DATA,
                    megagroup=True, access_hash=5,
                    default_banned_rights=T.ChatBannedRights(
                        until_date=None, send_media=True))
    usuario = T.User(id=9, first_name="Bia")
    pedidos, chamadas = [], []

    class Cliente:
        async def __call__(self, req):
            pedidos.append(req)
            return types.SimpleNamespace(link="https://t.me/+abc")

        async def get_entity(self, quem):
            return ent if quem == 1 else usuario

        async def get_input_entity(self, e):
            return T.InputPeerChannel(1, 5)

        async def kick_participant(self, e, u):
            chamadas.append(("kick", u.id))

        async def edit_admin(self, e, u, is_admin=True, **k):
            chamadas.append(("admin", u.id, is_admin))

        async def delete_dialog(self, e):
            chamadas.append(("sair",))
    p = tg.ProvedorTelegram.__new__(tg.ProvedorTelegram)
    p.cliente = Cliente()

    def rodar(acao, valor=None):
        return asyncio.run(p._administrar("1", acao, valor))
    assert rodar("nome", "Novo") == (True, "Nome do grupo mudado.")
    assert isinstance(pedidos[-1], functions.channels.EditTitleRequest)
    assert rodar("descricao", "Sobre")[0]
    assert isinstance(pedidos[-1], functions.messages.EditChatAboutRequest)
    ok, texto = rodar("anuncio", True)
    direitos = pedidos[-1].banned_rights
    assert ok and direitos.send_messages and direitos.send_media   # manteve
    assert rodar("trancado", True)[0]
    assert pedidos[-1].banned_rights.change_info
    assert rodar("adicionar", "@bia")[0]
    assert isinstance(pedidos[-1], functions.channels.InviteToChannelRequest)
    assert rodar("adicionar", "")[0] is False
    assert rodar("remover", "9")[0] and chamadas[-1] == ("kick", 9)
    assert rodar("promover", "9")[0] and chamadas[-1] == ("admin", 9, True)
    assert rodar("rebaixar", "9")[0] and chamadas[-1] == ("admin", 9, False)
    assert rodar("link") == (True, "https://t.me/+abc")
    assert rodar("revogar_link")[0]
    assert pedidos[-1].legacy_revoke_permanent
    assert rodar("sair")[0] and chamadas[-1] == ("sair",)
    assert rodar("xyz") == (False, "Ação desconhecida.")


def test_links_do_telegram_viram_botao_de_entrar():
    links = [("https://t.me/+AbCdEfGhIjKlMn", "convite"),
             ("https://t.me/joinchat/XyZ1234567890", "antigo"),
             ("https://t.me/turma_do_bairro", "publico"),
             ("https://t.me/turma_do_bairro?start=1", "repetido"),
             ("https://t.me/addstickers/Pacote", "figurinhas"),
             ("https://t.me/c/123/45", "mensagem"),
             ("https://t.me/canal/123", "mensagem de canal"),
             ("https://exemplo.com/t.me/x", "outro site")]
    entradas = tg.entradas_do_telegram(links)
    assert [(e["modo"], e.get("codigo") or e.get("usuario"))
            for e in entradas] == [
        ("convite", "AbCdEfGhIjKlMn"), ("convite", "XyZ1234567890"),
        ("publico", "turma_do_bairro")]
    assert entradas[2]["rotulo"] == "Entrar em @turma_do_bairro (grupo ou canal)"
    class MessageEntityUrl:
        offset, length = 5, 29
    texto = "olha https://t.me/+AbCdEfGhIjKlMn"
    x = tg.converter(mensagem(5, texto, sender=ANA,
                              entities=[MessageEntityUrl()]), "t1", 1)
    acoes = m.extras_de(x)["acoes"]
    assert [a["tipo"] for a in acoes] == ["entrar"]
    assert acoes[0]["codigo"] == "AbCdEfGhIjKlMn"


def test_presenca_do_telegram_online_visto_e_digitando(ambiente):
    import asyncio
    cliente = ClienteFalso()
    p = ambiente.criar(cliente)
    p.cliente = cliente
    p._observada = "10"
    def ev_usuario(**campos):
        base = dict(user_id=10, chat_id=None, typing=False, recording=False,
                    uploading=False, cancel=False, online=False,
                    last_seen=None, recently=False, within_weeks=False,
                    within_months=False)
        base.update(campos)
        return types.SimpleNamespace(**base)
    def rodar(e):
        asyncio.run(p._ao_usuario(e))
        return esperar(ambiente.fila, ev.Presenca)
    assert rodar(ev_usuario(online=True)).estado == "online"
    visto = rodar(ev_usuario(last_seen=DATA))
    assert (visto.estado, visto.quando) == ("offline", DATA.timestamp())
    assert rodar(ev_usuario(recently=True)).aprox == "recentemente"
    assert rodar(ev_usuario(within_weeks=True)).aprox == "na última semana"
    assert rodar(ev_usuario(typing=True)).estado == "digitando"
    assert rodar(ev_usuario(recording=True)).estado == "gravando"
    assert rodar(ev_usuario(cancel=True)).estado == "parou"
    # outra conversa nao e a observada
    asyncio.run(p._ao_usuario(ev_usuario(user_id=99, typing=True)))
    assert ambiente.fila.empty()
    # grupo: digitando de alguem, com o nome
    p._observada = "-100"
    e = rodar(ev_usuario(chat_id=-100, user_id=777, typing=True))
    assert (e.conversa_id, e.estado, e.quem) == ("-100", "digitando", "Bia")
    p.parar_presenca("-100")
    assert p._observada is None


def test_reagir_no_telegram_e_ver_a_reacao_dos_outros(ambiente):
    import asyncio
    from telethon.tl import types as tipos
    cliente = ClienteFalso()
    p = ambiente.criar(cliente)
    p.cliente = cliente
    x = m.Mensagem("t1", "10", "5", texto="oi", data=DATA.timestamp())
    ambiente.banco.salvar_mensagens([x])
    asyncio.run(p._reagir(x, "👍"))
    a = esperar(ambiente.fila, ev.MensagemAtualizada)
    assert (a.motivo, a.emoji, a.quem) == ("reacao", "👍", "Você")
    req = cliente.requisicoes[-1]
    assert req.msg_id == 5 and req.reaction[0].emoticon == "👍"
    assert m.minha_reacao(a.mensagem) == "👍"
    # tirar: lista vazia
    asyncio.run(p._reagir(a.mensagem, ""))
    b = esperar(ambiente.fila, ev.MensagemAtualizada)
    assert cliente.requisicoes[-1].reaction == []
    assert m.extras_de(b.mensagem)["reacoes"] == []
    # alguem reage
    nova = types.SimpleNamespace(
        peer=tipos.PeerUser(10), msg_id=5,
        reactions=types.SimpleNamespace(recent_reactions=[
            types.SimpleNamespace(reaction=tipos.ReactionEmoji("❤"), my=False,
                                  peer_id=tipos.PeerUser(10))], results=[]))
    asyncio.run(p._ao_reacoes(nova))
    c = esperar(ambiente.fila, ev.MensagemAtualizada)
    assert (c.motivo, c.emoji) == ("reacao", "❤") and c.quem == "Bia"
    assert m.resumo_reacoes(c.mensagem) == "❤ de Bia"
    # a mesma reacao de novo nao avisa; so a contagem (grupo grande) entra
    asyncio.run(p._ao_reacoes(nova))
    assert ambiente.fila.empty()
    contagem = types.SimpleNamespace(
        peer=tipos.PeerUser(10), msg_id=5,
        reactions=types.SimpleNamespace(recent_reactions=None, results=[
            types.SimpleNamespace(reaction=tipos.ReactionEmoji("👍"),
                                  count=3)]))
    asyncio.run(p._ao_reacoes(contagem))
    d = esperar(ambiente.fila, ev.MensagemAtualizada)
    assert m.resumo_reacoes(d.mensagem) == "👍 de 3 pessoas"


def test_previa_de_link_do_telegram():
    pagina = types.SimpleNamespace(url="https://exemplo.com/a",
                                   title="Exemplo", description="Descrição",
                                   site_name="Exemplo.com")
    msg = mensagem(5, "olha https://exemplo.com/a",
                   web_preview=pagina, media=object())
    x = tg.converter(msg, "t1", 10)
    previa = m.extras_de(x)["previa"]
    assert (previa["titulo"], previa["descricao"], previa["site"]) == (
        "Exemplo", "Descrição", "Exemplo.com")
    # pagina ainda sem titulo nem descricao: nada
    vazia = types.SimpleNamespace(url="https://a.com")
    assert m.extras_de(tg.converter(mensagem(6, "x", web_preview=vazia),
                                    "t1", 10))["previa"] == {}
    assert m.extras_de(tg.converter(mensagem(7, "sem link"),
                                    "t1", 10))["previa"] == {}


def _item(id_, legenda="", out=False, video=False):
    from telethon.tl import types as tipos
    media = tipos.MessageMediaDocument(document=types.SimpleNamespace(
        attributes=[tipos.DocumentAttributeVideo(
            duration=7, w=1, h=1)], size=900, mime_type="video/mp4")) \
        if video else tipos.MessageMediaPhoto()
    return tipos.StoryItem(id=id_, date=DATA, expire_date=DATA, media=media,
                           caption=legenda or None, out=out or None)


class ClienteDeHistorias(ClienteFalso):
    def __init__(self, resposta):
        super().__init__()
        self.resposta = resposta

    async def __call__(self, requisicao):
        self.requisicoes.append(requisicao)
        if type(requisicao).__name__ == "GetAllStoriesRequest":
            return self.resposta
        if type(requisicao).__name__ == "GetStoriesByIDRequest":
            return types.SimpleNamespace(stories=[_item(2, video=True)])
        return None


def _todas(*pares):
    from telethon.tl import types as tipos
    return types.SimpleNamespace(
        peer_stories=[tipos.PeerStories(peer=tipos.PeerUser(i), stories=its,
                                        max_read_id=lido)
                      for i, its, lido, _ in pares],
        users=[types.SimpleNamespace(id=i, first_name=nome, last_name="",
                                     username="", is_self=eu)
               for i, _, _, (nome, eu) in pares],
        chats=[], has_more=False)


def test_historias_do_telegram_viram_conversas_de_status(ambiente):
    import asyncio
    cliente = ClienteDeHistorias(_todas(
        (10, [_item(1, "praia"), _item(2, video=True)], 1, ("Bia", False)),
        (99, [_item(5)], 0, ("Eu", True))))
    p = ambiente.criar(cliente)
    p.cliente = cliente
    asyncio.run(p._buscar_historias())
    atual = esperar(ambiente.fila, ev.ConversasAtualizadas)
    por_id = {c.id: c for c in atual.conversas}
    bia, eu = por_id["status:10"], por_id["status:99"]
    assert (bia.nome, bia.tipo, bia.nao_lidas) == ("Histórias de Bia",
                                                   "status", 1)   # so a 2
    assert (eu.nome, eu.nao_lidas) == ("Meu status", 0)
    msgs = ambiente.banco.mensagens("t1", "status:10", 10)
    assert [(x.id, x.tipo, x.texto, x.segundos) for x in msgs] == [
        ("1", m.FOTO, "praia", 0), ("2", m.VIDEO, "", 7)]
    assert msgs[0].autor == "Bia" and msgs[0].remetente == "10"
    assert ambiente.banco.mensagens("t1", "status:99", 10)[0].minha
    # abrir a conversa carrega do banco
    asyncio.run(p._carregar("status:10", 50))
    assert [x.id for x in esperar(ambiente.fila, ev.MensagensCarregadas)
            .mensagens] == ["1", "2"]
    # a historia 1 expirou e a da Bia segue; a minha sumiu
    cliente.resposta = _todas((10, [_item(2, video=True)], 1, ("Bia", False)))
    asyncio.run(p._buscar_historias())
    esperar(ambiente.fila, ev.ConversasAtualizadas)
    assert [x.id for x in ambiente.banco.mensagens(
        "t1", "status:10", 10)] == ["2"]
    assert "status:99" not in [c.id for c in ambiente.banco.conversas("t1")]
    # nada novo do servidor: nada muda
    cliente.resposta = types.SimpleNamespace()
    asyncio.run(p._buscar_historias())
    assert [x.id for x in ambiente.banco.mensagens(
        "t1", "status:10", 10)] == ["2"]


def test_ver_curtir_responder_e_baixar_historia(ambiente):
    import asyncio
    cliente = ClienteDeHistorias(_todas(
        (10, [_item(1), _item(2, video=True)], 0, ("Bia", False))))
    p = ambiente.criar(cliente)
    p.cliente = cliente
    asyncio.run(p._buscar_historias())
    esperar(ambiente.fila, ev.ConversasAtualizadas)
    x = ambiente.banco.mensagens("t1", "status:10", 10)[1]
    # ver: marca como vistas ate a mais nova
    asyncio.run(p._marcar_lida("status:10"))
    lida = cliente.requisicoes[-1]
    assert type(lida).__name__ == "ReadStoriesRequest" and lida.max_id == 2
    assert ambiente.banco.conversas("t1")[0].nao_lidas == 0 or all(
        c.nao_lidas == 0 for c in ambiente.banco.conversas("t1")
        if c.tipo == "status")
    # curtir
    asyncio.run(p._reagir(x, "❤"))
    curtida = [r for r in cliente.requisicoes
               if type(r).__name__ == "SendReactionRequest"][-1]
    assert curtida.story_id == 2 and curtida.reaction.emoticon == "❤"
    a = esperar(ambiente.fila, ev.MensagemAtualizada)
    assert a.motivo == "reacao" and a.mensagem.conversa_id == "status:10"
    asyncio.run(p._reagir(x, ""))
    assert type([r for r in cliente.requisicoes
                 if type(r).__name__ == "SendReactionRequest"][-1]
                .reaction).__name__ == "ReactionEmpty"
    # responder em particular, citando a historia
    asyncio.run(p._responder_historia(x, "que lindo"))
    envio = [r for r in cliente.requisicoes
             if type(r).__name__ == "SendMessageRequest"][-1]
    assert envio.message == "que lindo"
    assert envio.reply_to.story_id == 2 and type(
        envio.reply_to).__name__ == "InputReplyToStory"
    # baixar: a midia vem da historia, com mime e tamanho
    original = asyncio.run(p._midia_da_historia(x))
    assert original.file.mime_type == "video/mp4" and original.file.size == 900
    # presenca nao se aplica a historias
    p.observar_presenca("status:10")
    assert p._observada is None


def test_publicar_historia_no_telegram(ambiente, tmp_path):
    import asyncio
    from telezapp.midia import envio

    class Cliente(ClienteDeHistorias):
        async def upload_file(self, caminho):
            self.enviado = caminho
            return "arquivo-enviado"
    cliente = Cliente(types.SimpleNamespace())
    p = ambiente.criar(cliente)
    p.cliente = cliente
    foto = tmp_path / "f.jpg"
    foto.write_bytes(b"\xff\xd8\xff" + b"0" * 50)
    anexo = envio.preparar(str(foto))
    assert tg.ProvedorTelegram.PODE_PUBLICAR_STATUS
    asyncio.run(p._publicar_historia("legenda", anexo, "todos"))
    pedido = [r for r in cliente.requisicoes
              if type(r).__name__ == "SendStoryRequest"][-1]
    assert cliente.enviado == str(foto)
    assert pedido.caption == "legenda"
    assert type(pedido.privacy_rules[0]).__name__ == \
        "InputPrivacyValueAllowAll"
    assert type(pedido.peer).__name__ == "InputPeerSelf"
    assert esperar(ambiente.fila, ev.Aviso).texto == "História publicada."
    asyncio.run(p._publicar_historia("", anexo, "contatos"))
    esperar(ambiente.fila, ev.Aviso)
    ultimo = [r for r in cliente.requisicoes
              if type(r).__name__ == "SendStoryRequest"][-1]
    assert type(ultimo.privacy_rules[0]).__name__ == \
        "InputPrivacyValueAllowContacts" and ultimo.caption is None
    # sem foto nem video, nem tenta
    p.publicar_status("so texto", None)
    assert "precisa de foto ou vídeo" in esperar(ambiente.fila,
                                                 ev.Aviso).texto


def test_envio_de_arquivo_no_telegram_publica_o_avanco(ambiente, tmp_path):
    import asyncio
    from telezapp.midia import envio

    class Cliente(ClienteFalso):
        async def send_file(self, ent, caminho, caption=None,
                            force_document=False, voice_note=False,
                            attributes=None, progress_callback=None, **kw):
            for feito in (10, 50, 50, 100):
                progress_callback(feito, 100)
            return await super().send_file(
                ent, caminho, caption=caption, force_document=force_document,
                voice_note=voice_note, attributes=attributes, **kw)
    cliente = Cliente()
    p = ambiente.criar(cliente)
    p.cliente = cliente
    foto = tmp_path / "f.jpg"
    foto.write_bytes(b"\xff\xd8\xff" + b"0" * 50)
    asyncio.run(p._enviar_arquivo("10", envio.preparar(str(foto)), "oi"))
    avancos = []
    while not ambiente.fila.empty():
        x = ambiente.fila.get()
        if isinstance(x, ev.ProgressoEnvio):
            avancos.append(x.percentual)
    assert avancos == [10, 50, 100]                  # sem repetir


def test_mensagem_do_telegram_que_cita_esta_conta_fica_marcada():
    citou = tg.converter(mensagem(5, "oi @eu", mentioned=True), "t1", 10)
    assert m.extras_de(citou)["citou_voce"]
    assert not m.extras_de(tg.converter(mensagem(6, "oi"), "t1", 10))[
        "citou_voce"]
    # as minhas nunca contam
    minha = tg.converter(mensagem(7, "oi", out=True, mentioned=True), "t1", 10)
    assert not m.extras_de(minha)["citou_voce"]


# ------------------------------------------------ mensagens temporarias
def test_converter_guarda_o_prazo_das_mensagens_temporarias():
    x = tg.converter(mensagem(7, "Oi", sender=ANA, ttl_period=86400), "t1", 10)
    assert x.expira == DATA.timestamp() + 86400
    assert tg.converter(mensagem(8, "Oi", sender=ANA), "t1", 10).expira == 0


def test_prazo_ao_vivo_aviso_de_servico_e_definir(ambiente):
    import asyncio
    cliente = ClienteFalso()
    p = ambiente.criar(cliente)
    p.iniciar()
    try:
        esperar(ambiente.fila, ev.ConversasAtualizadas)
        receber = cliente.handlers[0]

        async def chat():
            return ANA

        async def entrada():
            return "peer88"

        def evento(msg):
            return types.SimpleNamespace(
                message=msg, chat_id=88, is_group=False, is_channel=False,
                get_chat=chat, get_input_chat=entrada)

        async def rodar(msg):
            await receber(evento(msg))
        # uma mensagem com prazo: a conversa passa a ser temporaria
        asyncio.run_coroutine_threadsafe(
            rodar(mensagem(50, "nova", sender=ANA, ttl_period=604800)),
            p._loop).result(5)
        esperar(ambiente.fila, ev.MensagemNova)
        assert ambiente.banco.conversas("t1")[0].temporaria_s == 604800 or \
            [c.temporaria_s for c in ambiente.banco.conversas("t1")
             if c.id == "88"] == [604800]
        # o aviso de servico do Telegram muda o prazo e avisa
        acao = type("MessageActionSetMessagesTTL", (), {})()
        acao.period = 86400
        asyncio.run_coroutine_threadsafe(
            rodar(mensagem(51, "", sender=ANA, action=acao)),
            p._loop).result(5)
        aviso = esperar(ambiente.fila, ev.Aviso)
        assert "1 dia" in aviso.texto and aviso.texto.startswith("Mudaram")
        assert p._conversas["88"].temporaria_s == 86400
        # definir daqui: pede o setHistoryTTL e atualiza
        assert p.PODE_TEMPORARIAS
        p.definir_temporaria("88", 2678400)
        aviso = esperar(ambiente.fila, ev.Aviso)
        assert aviso.texto.startswith("Você mudou") and "1 mês" in aviso.texto
        pedido = [r for r in cliente.requisicoes
                  if type(r).__name__ == "SetHistoryTTLRequest"][0]
        assert pedido.period == 2678400
        assert p._conversas["88"].temporaria_s == 2678400
    finally:
        p.parar()


def _enquete_falsa(votos=None, fechada=False, multipla=False, publica=False):
    from telethon.tl import types as tipos
    respostas = [types.SimpleNamespace(text=types.SimpleNamespace(text=t),
                                       option=bytes([i]))
                 for i, t in enumerate(("Sexta", "Sábado", "Domingo"))]
    poll = types.SimpleNamespace(
        id=777, question=types.SimpleNamespace(text="Qual dia?"),
        answers=respostas, multiple_choice=multipla, closed=fechada,
        public_voters=publica)
    resultados = None
    if votos is not None:
        resultados = types.SimpleNamespace(
            results=[types.SimpleNamespace(option=bytes([i]), voters=n,
                                           chosen=i in votos.get("meus", ()))
                     for i, n in enumerate(votos["contagem"])],
            total_voters=sum(votos["contagem"]))
    return types.SimpleNamespace(
        id=5, message="", out=False, date=DATA, action=None,
        poll=types.SimpleNamespace(poll=poll, results=resultados),
        media=object(), sender=None, post_author="Ana")


def test_enquete_do_telegram_vira_dados_da_mensagem():
    from telezapp.provedores import telegram as tg
    nova = tg.converter(_enquete_falsa({"contagem": [2, 0, 1],
                                         "meus": [2]}), "t1", "10")
    e = m.enquete_de(nova)
    assert e["pergunta"] == "Qual dia?"
    assert e["opcoes"] == ["Sexta", "Sábado", "Domingo"]
    assert e["maximo"] == 1 and e["anonima"] and not e["encerrada"]
    assert m.contagens_da_enquete(e) == [2, 0, 1] and e["meus"] == [2]
    assert m.votantes_da_enquete(e) == 3
    assert e["poll_id"] == "777" and e["ids"] == ["00", "01", "02"]
    assert nova.texto == "enquete: Qual dia?"
    # sem resultados (ainda nao votei) nem multipla escolha
    sem = m.enquete_de(tg.converter(_enquete_falsa(None, multipla=True),
                                    "t1", "10"))
    assert sem["contagem"] is None and sem["maximo"] == 3


def test_votar_no_telegram_manda_a_opcao_e_atualiza(ambiente):
    import asyncio
    cliente = ClienteFalso()
    from telezapp.provedores import telegram as tg
    p = ambiente.criar(cliente)
    p.cliente = cliente
    nova = tg.converter(_enquete_falsa(), "t1", "10")
    ambiente.banco.salvar_mensagens([nova])

    async def get_messages(entidade, ids=None):
        return _enquete_falsa({"contagem": [0, 1, 0], "meus": [1]})
    cliente.get_messages = get_messages
    asyncio.run(p._votar_enquete(nova, [1]))
    pedido = [r for r in cliente.requisicoes
              if type(r).__name__ == "SendVoteRequest"][-1]
    assert pedido.msg_id == 5 and pedido.options == [b"\x01"]
    a = esperar(ambiente.fila, ev.MensagemAtualizada)
    assert a.motivo == "enquete"
    assert m.enquete_de(a.mensagem)["meus"] == [1]
    assert m.contagens_da_enquete(m.enquete_de(a.mensagem)) == [0, 1, 0]


def test_voto_de_outra_pessoa_chega_pela_atualizacao_da_enquete(ambiente):
    import asyncio
    cliente = ClienteFalso()
    from telezapp.provedores import telegram as tg
    p = ambiente.criar(cliente)
    p.cliente = cliente
    nova = tg.converter(_enquete_falsa({"contagem": [0, 0, 0]}), "t1", "10")
    ambiente.banco.salvar_mensagens([nova])
    atual = _enquete_falsa({"contagem": [3, 1, 0]})
    evento = types.SimpleNamespace(poll_id=777, poll=None,
                                   results=atual.poll.results)
    asyncio.run(p._ao_enquete(evento))
    a = esperar(ambiente.fila, ev.MensagemAtualizada)
    assert a.motivo == "enquete" and a.quem == "alguém"   # os votos subiram
    assert m.contagens_da_enquete(m.enquete_de(a.mensagem)) == [3, 1, 0]
    # enquete encerrada
    fechada = types.SimpleNamespace(
        poll_id=777, poll=types.SimpleNamespace(closed=True),
        results=atual.poll.results)
    asyncio.run(p._ao_enquete(fechada))
    b = esperar(ambiente.fila, ev.MensagemAtualizada)
    assert m.enquete_de(b.mensagem)["encerrada"] is True
    assert b.quem == ""                              # nenhum voto novo
    # enquete que nao conhecemos: nada acontece
    asyncio.run(p._ao_enquete(types.SimpleNamespace(
        poll_id=1, poll=None, results=None)))
    assert ambiente.fila.empty()


def test_criar_enquete_no_telegram_manda_a_pergunta_e_as_opcoes(ambiente):
    import asyncio
    cliente = ClienteFalso()
    p = ambiente.criar(cliente)
    p.cliente = cliente
    asyncio.run(p._criar_enquete("10", "Qual dia?", ["Sexta", "Sábado"],
                                 True, False))
    media = cliente.enquetes[-1]
    poll = media.poll
    assert poll.question.text == "Qual dia?"
    assert [a.text.text for a in poll.answers] == ["Sexta", "Sábado"]
    assert [a.option for a in poll.answers] == [b"\x00", b"\x01"]
    assert poll.multiple_choice is True and poll.public_voters is True
    nova = esperar(ambiente.fila, ev.MensagemNova)
    e = m.enquete_de(nova.mensagem)
    assert nova.enviada_daqui and e["opcoes"] == ["Sexta", "Sábado"]
    assert e["maximo"] == 2 and e["poll_id"] == "555"


# ------------------------------------------------ grupos com topicos
def test_ids_e_topicos_de_um_grupo_com_topicos():
    assert tg.id_do_topico("-100", 7) == "-100#7"
    assert tg.separar_topico("-100#7") == ("-100", 7)
    assert tg.separar_topico("-100") == ("-100", 0)
    assert tg.separar_topico("status:5") == ("status:5", 0)
    assert tg.nome_do_topico("Equipe", "Avisos") == "Equipe › Avisos"
    assert tg.topico_da_mensagem(mensagem(1)) == tg.TOPICO_GERAL
    direta = mensagem(2, reply_to=types.SimpleNamespace(
        forum_topic=True, reply_to_msg_id=9, reply_to_top_id=None))
    assert tg.topico_da_mensagem(direta) == 9
    resposta = mensagem(3, reply_to=types.SimpleNamespace(
        forum_topic=True, reply_to_msg_id=20, reply_to_top_id=9))
    assert tg.topico_da_mensagem(resposta) == 9
    resp_geral = mensagem(4, reply_to=types.SimpleNamespace(
        forum_topic=False, reply_to_msg_id=2, reply_to_top_id=None))
    assert tg.topico_da_mensagem(resp_geral) == tg.TOPICO_GERAL


class ClienteComForum(ClienteFalso):
    """Um grupo com topicos (Geral e Avisos) e uma conversa comum."""

    async def iter_dialogs(self, limit=None, folder=None, archived=None):
        if folder == 1:
            return
        yield types.SimpleNamespace(
            id=10, name="Ana", unread_count=0, date=DATA,
            input_entity="peer10", is_group=False, is_channel=False,
            dialog=types.SimpleNamespace(read_outbox_max_id=0))
        yield types.SimpleNamespace(
            id=-100, name="Equipe", unread_count=5, date=DATA,
            input_entity="peer-100", is_group=True, is_channel=True,
            entity=types.SimpleNamespace(forum=True),
            dialog=types.SimpleNamespace(read_outbox_max_id=0))

    async def iter_messages(self, ent, limit=None, reply_to=None):
        self.filtros = getattr(self, "filtros", []) + [reply_to]
        topico = types.SimpleNamespace(forum_topic=True, reply_to_msg_id=9,
                                       reply_to_top_id=None)
        if reply_to == 9:
            yield mensagem(21, "no topico", reply_to=topico, sender=ANA)
            return
        yield mensagem(30, "no geral", sender=ANA)
        yield mensagem(21, "no topico", reply_to=topico, sender=ANA)
        yield mensagem(10, "antiga do geral", sender=ANA)

    async def __call__(self, requisicao):
        await super().__call__(requisicao)
        nome = type(requisicao).__name__
        if nome == "GetForumTopicsRequest":
            def topico(id, titulo, nao_lidas, mensagem_id, fechado=False):
                return types.SimpleNamespace(
                    id=id, title=titulo, unread_count=nao_lidas,
                    top_message=mensagem_id, pinned=False, closed=fechado)
            return types.SimpleNamespace(
                topics=[topico(1, "Geral", 2, 30),
                        topico(9, "Avisos", 3, 21, fechado=True),
                        types.SimpleNamespace(id=4)],     # apagado
                messages=[mensagem(30), mensagem(21)])
        return types.SimpleNamespace(chats=[types.SimpleNamespace(id=555)])


def test_grupo_com_topicos_vira_uma_conversa_por_topico(ambiente):
    cliente = ClienteComForum()
    p = ambiente.criar(cliente)
    p.iniciar()
    try:
        esperar(ambiente.fila, ev.ContaPronta)
        convs = esperar(ambiente.fila, ev.ConversasAtualizadas).conversas
        por_id = {c.id: c for c in convs}
        assert sorted(por_id) == ["-100", "-100#1", "-100#9", "10"]
        assert por_id["-100"].nome == "Equipe"
        assert por_id["-100"].nao_lidas == 5           # soma dos topicos
        assert por_id["-100#9"].nome == "Equipe › Avisos"
        assert por_id["-100#9"].nao_lidas == 3
        assert por_id["-100#9"].somente_leitura        # topico fechado
        assert not por_id["-100#1"].somente_leitura
        assert por_id["-100#1"].tipo == "grupo"

        p.carregar_mensagens("-100#9")
        msgs = esperar(ambiente.fila, ev.MensagensCarregadas).mensagens
        assert [x.id for x in msgs] == ["21"]
        assert cliente.filtros[-1] == 9
        assert msgs[0].conversa_id == "-100#9"
        p.carregar_mensagens("-100#1")                  # o Geral
        msgs = esperar(ambiente.fila, ev.MensagensCarregadas).mensagens
        assert [x.id for x in msgs] == ["10", "30"]     # sem a do topico

        p.enviar_texto("-100#9", "oi")
        esperar(ambiente.fila, ev.MensagemNova)
        p.enviar_texto("-100#1", "geral")
        esperar(ambiente.fila, ev.MensagemNova)
        p.enviar_texto("-100#9", "resp", resposta_a="21")
        esperar(ambiente.fila, ev.MensagemNova)
        # no topico responde ao topico; no Geral e na resposta, como antes
        assert [(e[0], e[2]) for e in cliente.enviadas] == [
            ("peer-100", 9), ("peer-100", None), ("peer-100", 21)]
    finally:
        p.parar()


def test_marcar_topico_como_lido_le_so_aquele_topico(ambiente):
    cliente = ClienteComForum()
    p = ambiente.criar(cliente)
    p.iniciar()
    try:
        esperar(ambiente.fila, ev.ContaPronta)
        esperar(ambiente.fila, ev.ConversasAtualizadas)
        p.carregar_mensagens("-100#9")
        esperar(ambiente.fila, ev.MensagensCarregadas)
        p.marcar_como_lida("-100#9")
        p.carregar_mensagens("10")       # garante que a anterior terminou
        esperar(ambiente.fila, ev.MensagensCarregadas)
        leitura = [r for r in cliente.requisicoes
                   if type(r).__name__ == "ReadDiscussionRequest"]
        assert leitura and leitura[0].msg_id == 9 and \
            leitura[0].read_max_id == 21
        assert cliente.lidas == []        # nao leu o grupo inteiro
    finally:
        p.parar()


def test_criar_grupo_e_canal_no_telegram_monta_os_pedidos(ambiente,
                                                          monkeypatch):
    from telethon import utils
    cliente = ClienteComForum()
    p = ambiente.criar(cliente)
    monkeypatch.setattr(utils, "get_peer_id", lambda c: -1000000000555)
    monkeypatch.setattr(utils, "get_input_peer", lambda c: "peerNovo")
    p.iniciar()
    try:
        esperar(ambiente.fila, ev.ContaPronta)
        assert p.CRIA == ("grupo", "canal")
        ok, aviso, cid = p.criar_conversa("grupo", "Equipe", "Sobre", [],
                                          topicos=True)
        pedido = next(r for r in cliente.requisicoes
                      if type(r).__name__ == "CreateChannelRequest")
        assert ok and cid == "-1000000000555#1"
        assert pedido.megagroup and pedido.forum and not pedido.broadcast
        assert (pedido.title, pedido.about) == ("Equipe", "Sobre")
        ok, aviso, cid = p.criar_conversa("canal", "Notícias", "")
        pedido = [r for r in cliente.requisicoes
                  if type(r).__name__ == "CreateChannelRequest"][-1]
        assert ok and cid == "-1000000000555"
        assert pedido.broadcast and not pedido.megagroup and not pedido.forum
    finally:
        p.parar()


def test_deixar_de_seguir_e_silenciar_canal_do_telegram():
    import asyncio
    from telethon.tl import functions, types as T
    canal = T.Channel(id=1, title="C", photo=T.ChatPhotoEmpty(), date=DATA,
                      broadcast=True, access_hash=5)
    pedidos = []

    class Cliente:
        async def __call__(self, req):
            pedidos.append(req)

        async def get_entity(self, quem):
            return canal

        async def get_input_entity(self, e):
            return T.InputPeerChannel(1, 5)

        async def delete_dialog(self, e):
            # o que o Telethon faz num canal: sair dele
            await self(functions.channels.LeaveChannelRequest(
                T.InputChannel(1, 5)))
    p = tg.ProvedorTelegram.__new__(tg.ProvedorTelegram)
    p.cliente = Cliente()
    p._agendar = lambda corotina: corotina.close()   # a atualizacao da lista

    def rodar(acao, valor=None):
        return asyncio.run(p._administrar_canal("1", acao, valor))
    assert rodar("deixar_de_seguir") == (
        True, "Você deixou de seguir o canal.")
    assert isinstance(pedidos[-1], functions.channels.LeaveChannelRequest)
    assert rodar("silenciar", True)[0]
    assert pedidos[-1].settings.mute_until > 0
    assert rodar("silenciar", False)[0]
    assert pedidos[-1].settings.mute_until == 0
    assert rodar("xyz") == (False, "Ação desconhecida.")


def test_video_do_telegram_sem_chamadas_nao_declara_suporte(ambiente):
    p = ambiente.criar(object())
    assert p.suporta_video is False and p.cameras() == []
    vistos = []
    p.definir_destino_video(lambda *a: vistos.append(a))
    assert p._destino_video is not None            # guardado para quando abrir


def test_video_do_telegram_repassa_camera_e_destino_as_chamadas(ambiente):
    p = ambiente.criar(object())
    chamadas = []

    class Falsa:
        pronta = True
        suporta_video = True
        destino_video = None

        def cameras(self):
            return ["Câmera A"]

        async def ligar(self, chat, *args):
            chamadas.append(("ligar", chat) + args)

        async def atender(self, chat, *args):
            chamadas.append(("atender", chat) + args)

        async def ligar_camera(self, chat, nome=""):
            chamadas.append(("ligar_camera", chat, nome))
    p._chamadas = Falsa()
    p._agendar = lambda coro: __import__("asyncio").run(coro)
    assert p.suporta_video and p.cameras() == ["Câmera A"]
    p.ligar("10", "Mic", "Saída")                       # voz: igual a antes
    p.ligar("10", "Mic", "Saída", video=True, camera="")
    p.atender_chamada("10", "Mic", "Saída", camera="Câmera A")
    p.ligar_camera("10", "Câmera A")
    assert chamadas == [("ligar", 10, "Mic", "Saída"),
                        ("ligar", 10, "Mic", "Saída", True, ""),
                        ("atender", 10, "Mic", "Saída", "Câmera A"),
                        ("ligar_camera", 10, "Câmera A")]
    p.definir_destino_video(print)
    assert p._chamadas.destino_video is print


def test_localizacao_do_telegram_traz_lugar_coordenadas_e_mapa():
    geo = types.SimpleNamespace(lat=-23.5505, long=-46.6333)
    simples = tg.converter(mensagem(1, "", geo=geo, media=object(),
                                    sender=ANA), "t1", 10)
    assert simples.texto.split("\n") == [
        "localização", "coordenadas -23.55050, -46.63330",
        "https://www.google.com/maps?q=-23.550500,-46.633300"]
    lugar = types.SimpleNamespace(title="Café", address="Rua A, 10")
    x = tg.converter(mensagem(2, "", geo=geo, venue=lugar, media=object(),
                              sender=ANA), "t1", 10)
    assert x.texto.startswith("localização: Café, Rua A, 10\n")

    class MessageMediaGeoLive:
        pass
    viva = tg.converter(mensagem(3, "", geo=geo, media=MessageMediaGeoLive(),
                                 sender=ANA), "t1", 10)
    assert viva.texto.startswith("localização em tempo real\n")

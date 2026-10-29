# SPDX-License-Identifier: GPL-3.0-or-later
"""Ferramentas de grupo do WhatsApp: pedidos de entrada (listar, aprovar e
recusar), foto, grupos que a conta administra e entrar por link, com um
cliente simulado (sem rede)."""
import types

import pytest

pytest.importorskip("neonize")

from neonize.proto import Neonize_pb2 as N  # noqa: E402

from testes.test_provedor_whatsapp import (  # noqa: E402
    TS, _grupo_info, _provedor_com_cliente, jid)

from telezapp.nucleo import grupo as ng  # noqa: E402
from telezapp.provedores import base  # noqa: E402


def _pedido(user, quando=TS, servidor="s.whatsapp.net"):
    return N.GroupParticipantRequest(Participant=jid(user, servidor),
                                     TimeAt=quando)


def _contato():
    return types.SimpleNamespace(get_contact=lambda j_: types.SimpleNamespace(
        FullName="", FirstName="", PushName="", BusinessName=""))


# ------------------------------------------------------------ helpers puros
def test_rotulo_do_pedido_junta_nome_telefone_e_data():
    r = ng.rotulo_do_pedido({"nome": "Bia", "telefone": "+5551",
                             "quando": TS})
    assert r.startswith("Bia, +5551, pediu em ")
    assert ng.rotulo_do_pedido({"nome": "+5551", "telefone": "+5551",
                                "quando": 0}) == "+5551"
    assert ng.rotulo_do_pedido({}) == "Pessoa sem nome"


def test_resumo_dos_pedidos_no_singular_e_no_plural():
    assert ng.resumo_dos_pedidos(0) == "Nenhum pedido de entrada esperando."
    assert ng.resumo_dos_pedidos(1) == "1 pedido de entrada esperando."
    assert ng.resumo_dos_pedidos(3) == "3 pedidos de entrada esperando."


def test_png_do_qr_e_um_png():
    assert ng.png_do_qr("https://chat.whatsapp.com/ABCDEFGHIJ")[:8] == \
        b"\x89PNG\r\n\x1a\n"


def test_extensao_da_imagem_pelos_primeiros_bytes():
    assert ng.extensao_da_imagem(b"\xff\xd8\xff\xe0") == ".jpg"
    assert ng.extensao_da_imagem(b"\x89PNG\r\n\x1a\nxx") == ".png"
    assert ng.extensao_da_imagem(b"RIFF\0\0\0\0WEBPxx") == ".webp"
    assert ng.extensao_da_imagem(b"???") == ".jpg"


def test_codigo_do_convite_aceita_link_ou_codigo():
    assert ng.codigo_do_convite(
        " https://chat.whatsapp.com/AbCdEfGhIjKl?x=1 ") == "AbCdEfGhIjKl"
    assert ng.codigo_do_convite("AbCdEfGhIjKl") == "AbCdEfGhIjKl"
    assert ng.codigo_do_convite("oi") == ""
    assert ng.codigo_do_convite("https://exemplo.com/AbCdEfGhIjKl") == ""


# ------------------------------------------------------ pedidos de entrada
def test_pedidos_de_entrada_lista_do_mais_antigo_para_o_mais_novo(tmp_path):
    cliente = types.SimpleNamespace(
        get_group_request_participants=lambda j_: [
            _pedido("5551888880000", TS + 50),
            _pedido("99", TS, "lid")],
        contact=_contato())
    p, banco = _provedor_com_cliente(tmp_path, cliente)
    ok, lista = p.pedidos_de_entrada("123@g.us")
    assert ok and len(lista) == 2
    assert lista[0]["id"] == "99@lid" and lista[0]["quando"] == TS
    assert lista[1]["id"] == "5551888880000@s.whatsapp.net"
    assert lista[1]["telefone"] == "+5551888880000"
    banco.fechar()


def test_pedidos_de_entrada_sem_ser_admin_explica(tmp_path):
    def recusa(j_):
        raise RuntimeError("403")
    p, banco = _provedor_com_cliente(tmp_path, types.SimpleNamespace(
        get_group_request_participants=recusa))
    ok, texto = p.pedidos_de_entrada("123@g.us")
    assert not ok and "administradores" in texto
    p._conectada = False
    assert p.pedidos_de_entrada("123@g.us") == (
        False, "Sem conexão com o WhatsApp.")
    banco.fechar()


def test_responder_pedidos_chama_a_funcao_nova_do_neonize(tmp_path):
    from neonize.utils.enum import ParticipantRequestChange
    chamadas = []

    def atualizar(j_, lista, mudanca):
        chamadas.append((j_.User, [x.User for x in lista], mudanca))
        return [N.GroupParticipant() for _ in lista]
    p, banco = _provedor_com_cliente(tmp_path, types.SimpleNamespace(
        update_group_request_participants=atualizar))
    ok, texto = p.responder_pedidos(
        "123@g.us", ["5551888880000@s.whatsapp.net", "99@lid"], True)
    assert ok and texto == "2 pedidos aprovados."
    assert chamadas[0] == ("123", ["5551888880000", "99"],
                           ParticipantRequestChange.APPROVE)
    ok, texto = p.responder_pedidos("123@g.us", ["99@lid"], False)
    assert ok and texto == "1 pedido recusado."
    assert chamadas[1][2] == ParticipantRequestChange.REJECT
    assert p.responder_pedidos("123@g.us", [], True)[0] is False
    banco.fechar()


def test_responder_pedidos_conta_os_que_o_whatsapp_recusou(tmp_path):
    def atualizar(j_, lista, mudanca):
        return [N.GroupParticipant(Error=409),
                N.GroupParticipant()][:len(lista)]
    p, banco = _provedor_com_cliente(tmp_path, types.SimpleNamespace(
        update_group_request_participants=atualizar))
    ok, texto = p.responder_pedidos("123@g.us", ["1@lid", "2@lid"], True)
    assert ok and "1 pedido aprovado." in texto and "1 não deu certo" in texto
    ok, texto = p.responder_pedidos("123@g.us", ["1@lid"], True)
    assert not ok and "409" in texto
    banco.fechar()


def test_responder_pedidos_sem_a_dll_nova_diz_o_que_falta(tmp_path):
    p, banco = _provedor_com_cliente(tmp_path, types.SimpleNamespace())
    ok, texto = p.responder_pedidos("123@g.us", ["1@lid"], True)
    assert not ok and "DLL de teste nova" in texto
    banco.fechar()


def test_responder_pedidos_traduz_a_excecao(tmp_path):
    def quebra(*a):
        raise RuntimeError("x")
    p, banco = _provedor_com_cliente(tmp_path, types.SimpleNamespace(
        update_group_request_participants=quebra))
    ok, texto = p.responder_pedidos("123@g.us", ["1@lid"], False)
    assert not ok and "RuntimeError" in texto
    banco.fechar()


# ------------------------------------------------------------------- foto
def test_trocar_a_foto_do_grupo_manda_os_bytes(tmp_path):
    enviados = []
    p, banco = _provedor_com_cliente(tmp_path, types.SimpleNamespace(
        set_group_photo=lambda j_, dados: enviados.append((j_.User, dados))
        or "ID"))
    assert p.administrar_grupo("123@g.us", "foto", b"JPEG") == (
        True, "Foto do grupo mudada.")
    assert enviados == [("123", b"JPEG")]
    banco.fechar()


def test_foto_do_grupo_baixa_pelo_endereco_do_whatsapp(tmp_path, monkeypatch):
    import urllib.request

    class Resposta:
        def __init__(self, dados):
            self.dados = dados

        def read(self, n=-1):
            return self.dados

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    pedidos = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=0:
                        pedidos.append(url) or Resposta(b"\xff\xd8\xff"))
    p, banco = _provedor_com_cliente(tmp_path, types.SimpleNamespace(
        get_profile_picture=lambda j_: N.ProfilePictureInfo(
            URL="https://pps.whatsapp.net/f.jpg")))
    assert p.foto_do_grupo("123@g.us") == (True, b"\xff\xd8\xff")
    assert pedidos == ["https://pps.whatsapp.net/f.jpg"]
    banco.fechar()


def test_foto_do_grupo_sem_foto_ou_escondida(tmp_path):
    p, banco = _provedor_com_cliente(tmp_path, types.SimpleNamespace(
        get_profile_picture=lambda j_: N.ProfilePictureInfo()))
    ok, texto = p.foto_do_grupo("123@g.us")
    assert not ok and "não tem foto" in texto

    def recusa(j_):
        raise RuntimeError("not authorized")
    p.cliente.get_profile_picture = recusa
    assert not p.foto_do_grupo("123@g.us")[0]
    banco.fechar()


def test_foto_do_contato_usa_o_endereco_do_contato(tmp_path, monkeypatch):
    import urllib.request

    class Resposta:
        def read(self, n=-1):
            return b"\x89PNG"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    vistos = []
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda url, timeout=0: Resposta())
    p, banco = _provedor_com_cliente(tmp_path, types.SimpleNamespace(
        get_profile_picture=lambda j_: vistos.append(j_.User) or
        N.ProfilePictureInfo(URL="https://pps.whatsapp.net/c.png")))
    assert p.foto_do_contato("5551@s.whatsapp.net") == (True, b"\x89PNG")
    assert vistos == ["5551"]
    banco.fechar()


def test_foto_do_contato_sem_foto_fala_de_contato(tmp_path):
    p, banco = _provedor_com_cliente(tmp_path, types.SimpleNamespace(
        get_profile_picture=lambda j_: N.ProfilePictureInfo()))
    ok, texto = p.foto_do_contato("5551@s.whatsapp.net")
    assert not ok and texto.startswith("Este contato não tem foto")
    banco.fechar()


def test_fotos_temporarias_sao_apagadas(tmp_path, monkeypatch):
    import os
    import tempfile
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    assert ng.limpar_fotos_temporarias() == 0         # sem a pasta: nada
    pasta = ng.pasta_das_fotos()
    assert pasta == str(tmp_path / "TeleZapp-fotos")
    os.makedirs(pasta)
    for nome in ("contato-1.jpg", "grupo-2.png"):
        with open(os.path.join(pasta, nome), "wb") as f:
            f.write(b"x")
    assert ng.limpar_fotos_temporarias() == 2
    assert not os.path.exists(pasta)


# ------------------------------------------------ grupos que eu administro
def test_grupos_que_administro_so_os_que_a_conta_administra(tmp_path):
    outro = N.GroupInfo(
        JID=jid("456", "g.us"), GroupName=N.GroupName(Name="Aberto"),
        Participants=[N.GroupParticipant(JID=jid("5551999990000"))])
    comunidade = _grupo_info("Comunidade")
    comunidade.GroupParent.IsParent = True
    p, banco = _provedor_com_cliente(tmp_path, types.SimpleNamespace(
        get_joined_groups=lambda: [outro, _grupo_info("Turma"), comunidade],
        get_me=lambda: types.SimpleNamespace(
            JID=jid("5551999990000"), LID=jid(""))))
    assert p.grupos_que_administro() == [("123@g.us", "Turma")]
    banco.fechar()


def test_adicionar_ao_grupo_aceita_o_endereco_da_conversa(tmp_path):
    chamadas = []
    p, banco = _provedor_com_cliente(tmp_path, types.SimpleNamespace(
        update_group_participants=lambda j_, lista, acao: chamadas.append(
            (lista[0].User, lista[0].Server)) or []))
    assert p.administrar_grupo("123@g.us", "adicionar",
                               "5551888880000@s.whatsapp.net")[0]
    assert chamadas == [("5551888880000", "s.whatsapp.net")]
    banco.fechar()


# -------------------------------------------------- entrar por um link
def test_entrar_por_link_sem_mensagem_usa_so_o_codigo(tmp_path):
    vistos = []
    cliente = types.SimpleNamespace(
        get_group_info_from_link=lambda codigo: vistos.append(
            ("previa", codigo)) or _grupo_info("Turma"),
        join_group_with_link=lambda codigo: vistos.append(("entrar", codigo)),
        get_me=lambda: types.SimpleNamespace(
            JID=jid("5551000000000"), LID=jid("")))
    p, banco = _provedor_com_cliente(tmp_path, cliente)
    previa = p.previa_do_convite(None, {"codigo": "ABCDEFGHIJ"})
    assert previa["nome"] == "Turma" and not previa["ja_participa"]
    assert p.entrar_no_grupo(None, {"codigo": "ABCDEFGHIJ"})[0]
    assert vistos == [("previa", "ABCDEFGHIJ"), ("entrar", "ABCDEFGHIJ")]
    banco.fechar()


# ------------------------------------------------------ outros servicos
def test_servicos_sem_o_recurso_dizem_que_nao_tem():
    P = base.Provedor
    assert P.pedidos_de_entrada(None, "1")[0] is False
    assert P.responder_pedidos(None, "1", ["2"], True)[0] is False
    assert P.foto_do_grupo(None, "1")[0] is False
    assert P.foto_do_contato(None, "1")[0] is False
    assert P.grupos_que_administro(None) == []
    assert not (base.Provedor.PEDIDOS_DE_ENTRADA
                or base.Provedor.FOTO_DO_GRUPO
                or base.Provedor.FOTO_DO_CONTATO
                or base.Provedor.LISTA_GRUPOS_ADMIN
                or base.Provedor.ENTRA_POR_LINK)

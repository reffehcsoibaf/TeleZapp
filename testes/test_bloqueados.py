# SPDX-License-Identifier: GPL-3.0-or-later
"""Bloquear, desbloquear e a lista de bloqueados (WhatsApp, Telegram e a
janela), com clientes simulados."""
import asyncio
import sys
import types

import pytest

from testes import wx_falso

sys.modules["wx"] = wx_falso

from telezapp.interface import bloqueados as bl          # noqa: E402
from telezapp.provedores import base                      # noqa: E402
from telezapp.provedores import telegram as tg            # noqa: E402
from telezapp.provedores import whatsapp as wa            # noqa: E402


class Sincrona:
    """Thread que roda na hora, para os testes serem previsiveis."""

    def __init__(self, target=None, daemon=None, name=None, args=()):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@pytest.fixture(autouse=True)
def sem_threads(monkeypatch):
    # so o modulo da janela troca de thread; o resto (o neonize, por
    # exemplo) segue com a threading de verdade
    monkeypatch.setattr(bl, "threading", types.SimpleNamespace(
        Thread=Sincrona))
    wx_falso.mensagens.clear()
    wx_falso.resposta_messagebox[0] = wx_falso.YES
    yield
    wx_falso.resposta_messagebox[0] = wx_falso.NO


# ------------------------------------------------------------- WhatsApp
def _jid(usuario, servidor="s.whatsapp.net"):
    return wa._jid_obj(usuario, servidor)


class ClienteWhatsApp:
    def __init__(self, bloqueados=()):
        self.lista = list(bloqueados)
        self.pedidos = []
        self.contact = types.SimpleNamespace(get_contact=self._contato)

    def _contato(self, j):
        from neonize.proto import Neonize_pb2 as N
        nomes = {"5551988887777": "Ana Silva"}
        return N.ContactInfo(Found=j.User in nomes,
                             FullName=nomes.get(j.User, ""))

    def get_blocklist(self):
        return types.SimpleNamespace(JIDs=list(self.lista))

    def update_blocklist(self, jid, acao):
        self.pedidos.append((jid.User, jid.Server, acao.name))
        if acao.name == "BLOCK":
            self.lista.append(jid)
        else:
            self.lista = [j for j in self.lista if j.User != jid.User]

    def get_pn_from_lid(self, j):
        from neonize.proto import Neonize_pb2 as N
        return _jid("5551977776666") if j.User == "lid1" else N.JID()


def whatsapp(bloqueados=()):
    p = wa.ProvedorWhatsApp.__new__(wa.ProvedorWhatsApp)
    p.cliente = ClienteWhatsApp(bloqueados)
    p._conectada = True
    p._lid_para_numero = {}
    p._apelidos = {}
    p.conta = types.SimpleNamespace(id="w1")
    p.banco = types.SimpleNamespace(nome_de_contato=lambda *a: "")
    return p


def test_whatsapp_lista_os_bloqueados_com_nome_e_telefone():
    p = whatsapp([_jid("5551988887777"), _jid("lid1", "lid")])
    assert p.PODE_BLOQUEAR
    assert p.bloqueados() == [
        ("5551988887777@s.whatsapp.net", "Ana Silva", "+5551988887777"),
        ("5551977776666@s.whatsapp.net", "+5551977776666", "+5551977776666")]


def test_whatsapp_bloqueia_e_desbloqueia_pelo_endereco_da_lista():
    p = whatsapp([_jid("lid1", "lid")])        # a lista guarda o LID
    assert p.esta_bloqueado("5551977776666@s.whatsapp.net")
    assert not p.esta_bloqueado("5551988887777@s.whatsapp.net")
    p.bloquear("5551988887777@s.whatsapp.net", True)
    assert p.cliente.pedidos[-1] == ("5551988887777", "s.whatsapp.net",
                                     "BLOCK")
    p.bloquear("5551977776666@s.whatsapp.net", False)
    assert p.cliente.pedidos[-1] == ("lid1", "lid", "UNBLOCK")
    assert not p.esta_bloqueado("5551977776666@s.whatsapp.net")
    n = len(p.cliente.pedidos)
    p.bloquear("5551977776666@s.whatsapp.net", False)     # ja desbloqueado
    assert len(p.cliente.pedidos) == n


def test_whatsapp_so_bloqueia_pessoas_e_com_a_conta_conectada():
    p = whatsapp()
    with pytest.raises(base.ErroBloqueio):
        p.bloquear("120363@g.us", True)
    p._conectada = False
    with pytest.raises(base.ErroBloqueio):
        p.bloqueados()
    with pytest.raises(base.ErroBloqueio):
        p.bloquear("5551988887777@s.whatsapp.net", True)


def test_whatsapp_erro_do_servico_vira_erro_de_bloqueio():
    p = whatsapp()

    def falha(*a):
        raise RuntimeError("boom")
    p.cliente.update_blocklist = falha
    with pytest.raises(base.ErroBloqueio) as e:
        p.bloquear("5551988887777@s.whatsapp.net", True)
    assert "WhatsApp" in str(e.value)


# ------------------------------------------------------------- Telegram
class ClienteTelegram:
    def __init__(self, bloqueado=False):
        self.pedidos, self.bloqueado = [], bloqueado

    async def __call__(self, req):
        self.pedidos.append(type(req).__name__)
        nome = type(req).__name__
        if nome == "GetBlockedRequest":
            if req.offset:
                return types.SimpleNamespace(blocked=[], users=[], count=2)
            usuarios = [types.SimpleNamespace(
                id=5, first_name="Ana", last_name="Souza", phone="5551999",
                username=None), types.SimpleNamespace(
                id=6, first_name=None, last_name=None, phone="",
                username="bruno")]
            return types.SimpleNamespace(
                blocked=[types.SimpleNamespace(
                    peer_id=types.SimpleNamespace(user_id=u.id))
                    for u in usuarios], users=usuarios, count=2)
        if nome == "GetFullUserRequest":
            return types.SimpleNamespace(
                full_user=types.SimpleNamespace(blocked=self.bloqueado))
        return True


def telegram(bloqueado=False):
    p = tg.ProvedorTelegram.__new__(tg.ProvedorTelegram)
    p.cliente = ClienteTelegram(bloqueado)
    p._entidades = {"5": "entidade-5"}
    p._executar = lambda corotina, espera=20: asyncio.run(corotina)
    return p


def test_telegram_lista_os_bloqueados():
    p = telegram()
    assert p.PODE_BLOQUEAR
    assert p.bloqueados() == [("5", "Ana Souza", "+5551999"),
                              ("6", "@bruno", "")]


def test_telegram_ve_bloqueia_e_desbloqueia():
    p = telegram(bloqueado=True)
    assert p.esta_bloqueado("5") is True
    p.bloquear("5", True)
    p.bloquear("5", False)
    assert p.cliente.pedidos[-2:] == ["BlockRequest", "UnblockRequest"]


def test_telegram_so_bloqueia_pessoas():
    p = telegram()
    for conversa in ("-1001234", "abc", "0"):
        with pytest.raises(base.ErroBloqueio):
            p.bloquear(conversa, True)


def test_telegram_erro_vira_erro_de_bloqueio():
    p = telegram()

    async def falha(req):
        raise RuntimeError("boom")
    p.cliente = falha
    with pytest.raises(base.ErroBloqueio) as e:
        p.bloquear("5", True)
    assert "Telegram" in str(e.value)


def test_provedor_sem_bloqueio_diz_que_nao_sabe():
    assert not base.Provedor.PODE_BLOQUEAR
    assert base.Provedor.bloqueados(None) == []
    with pytest.raises(base.ErroBloqueio):
        base.Provedor.bloquear(None, "1", True)


# --------------------------------------------------------------- janela
class ProvFalso:
    PODE_BLOQUEAR = True

    def __init__(self, lista=(), bloqueada=False, erro=None):
        self.lista, self.bloqueada, self.erro = list(lista), bloqueada, erro
        self.pedidos = []

    def bloqueados(self):
        if self.erro:
            raise self.erro
        return self.lista

    def esta_bloqueado(self, conversa_id):
        return self.bloqueada

    def bloquear(self, conversa_id, bloquear=True):
        if self.erro:
            raise self.erro
        self.pedidos.append((conversa_id, bloquear))
        if not bloquear:
            self.lista = [x for x in self.lista if x[0] != conversa_id]


class ContasFalsas:
    def __init__(self, **provedores):
        self.provedores = provedores

    def lista(self):
        return [("w1", "whatsapp", "Fábio"), ("t1", "telegram", "Fábio")]

    def provedor(self, conta_id):
        return self.provedores.get(conta_id)


def test_ler_bloqueados_junta_as_contas_e_avisa_de_quem_falhou():
    w = ProvFalso([("5551@s.whatsapp.net", "Ana", "+5551")])
    t = ProvFalso(erro=base.ErroBloqueio("Sem conexão."))
    itens, avisos = bl.ler_bloqueados(ContasFalsas(w1=w, t1=t))
    assert itens == [("w1", "5551@s.whatsapp.net", "Ana", "+5551")]
    assert avisos == ["Telegram (Fábio): Sem conexão."]


def test_janela_de_bloqueados_mostra_e_desbloqueia():
    w = ProvFalso([("2@s.whatsapp.net", "Bruno", "+2"),
                   ("1@s.whatsapp.net", "Ana", "")])
    falas = []
    g = bl.GerenciadorBloqueados(None, ContasFalsas(w1=w), lambda: None,
                                 falas.append)
    assert g.lista.itens == ["Ana, WhatsApp (Fábio)",
                             "Bruno, +2, WhatsApp (Fábio)"]
    assert falas[-1] == "2 contatos bloqueados."
    g.lista.SetSelection(1)
    g._desbloquear()
    assert w.pedidos == [("2@s.whatsapp.net", False)]
    assert g.lista.itens == ["Ana, WhatsApp (Fábio)"]
    assert "Contato Bruno desbloqueado." in falas


def test_janela_de_bloqueados_vazia_e_bloquear_alguem():
    w = ProvFalso()
    falas = []
    g = bl.GerenciadorBloqueados(
        None, ContasFalsas(w1=w),
        lambda: ("w1", "9@s.whatsapp.net", "Carla"), falas.append)
    assert g.lista.itens == ["Nenhum contato bloqueado"]
    wx_falso.resposta_messagebox[0] = wx_falso.NO       # desistiu
    g._bloquear()
    assert w.pedidos == []
    wx_falso.resposta_messagebox[0] = wx_falso.YES
    g._bloquear()
    assert w.pedidos == [("9@s.whatsapp.net", True)]
    assert "Contato Carla bloqueado." in falas


def test_alternar_pergunta_e_bloqueia_ou_desbloqueia():
    falas = []
    p = ProvFalso(bloqueada=False)
    bl.alternar(None, p, "5", "Ana", falas.append)
    assert p.pedidos == [("5", True)]
    assert "Bloquear Ana?" in wx_falso.mensagens[0]
    p2 = ProvFalso(bloqueada=True)
    bl.alternar(None, p2, "5", "Ana", falas.append)
    assert p2.pedidos == [("5", False)]
    assert "Desbloquear Ana?" in wx_falso.mensagens[1]
    assert "Contato Ana desbloqueado." in falas


def test_alternar_nao_faz_nada_se_a_pessoa_desiste_ou_o_servico_falha():
    falas = []
    p = ProvFalso()
    wx_falso.resposta_messagebox[0] = wx_falso.NO
    bl.alternar(None, p, "5", "Ana", falas.append)
    assert p.pedidos == []
    wx_falso.resposta_messagebox[0] = wx_falso.YES
    ruim = ProvFalso(erro=base.ErroBloqueio("Conta desconectada."))
    bl.alternar(None, ruim, "5", "Ana", falas.append)
    assert falas[-1] == "Conta desconectada."
    assert "Conta desconectada." in wx_falso.mensagens

# SPDX-License-Identifier: GPL-3.0-or-later
"""Janelas das ferramentas de grupo (pedidos de entrada, convite) e os
botoes que os detalhes do grupo mostram, com wx falso e provedor simulado."""
import sys
import types

import pytest

from testes import wx_falso

sys.modules["wx"] = wx_falso

from telezapp.interface import detalhes as det            # noqa: E402
from telezapp.interface import grupo_extras as ge         # noqa: E402
from telezapp.nucleo import modelos as m                  # noqa: E402


class Sincrona:
    def __init__(self, target=None, daemon=None, name=None, args=()):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@pytest.fixture(autouse=True)
def sem_threads(monkeypatch):
    for modulo in (ge, det):
        monkeypatch.setattr(modulo, "threading", types.SimpleNamespace(
            Thread=Sincrona))
    wx_falso.mensagens.clear()
    wx_falso.resposta_messagebox[0] = wx_falso.YES


class Fala:
    def __init__(self):
        self.ditas = []

    def falar(self, texto, interromper=False):
        self.ditas.append(texto)


class Prov:
    PEDIDOS_DE_ENTRADA = True

    def __init__(self):
        self.respostas = []
        self.pedidos = [
            {"id": "1@lid", "nome": "Bia", "telefone": "+5551", "quando": 0},
            {"id": "2@lid", "nome": "Caio", "telefone": "", "quando": 0}]

    def pedidos_de_entrada(self, cid):
        return True, list(self.pedidos)

    def responder_pedidos(self, cid, ids, aprovar):
        self.respostas.append((cid, ids, aprovar))
        self.pedidos = [p for p in self.pedidos if p["id"] not in ids]
        return True, "ok"


def test_pedidos_listam_e_aprovam_o_escolhido():
    prov, fala = Prov(), Fala()
    dlg = ge.DialogoPedidos(None, prov, "9@g.us", "Turma", fala)
    assert dlg.lista.itens == ["Bia, +5551", "Caio"]
    assert fala.ditas[-1] == "2 pedidos de entrada esperando."
    dlg.lista.SetSelection(1)
    dlg.responder(True)
    assert prov.respostas == [("9@g.us", ["2@lid"], True)]
    assert dlg.lista.itens == ["Bia, +5551"]          # recarregou


def test_recusar_pede_confirmacao_e_desistir_nao_envia():
    prov, fala = Prov(), Fala()
    dlg = ge.DialogoPedidos(None, prov, "9@g.us", "Turma", fala)
    wx_falso.resposta_messagebox[0] = wx_falso.NO
    dlg.responder(False)
    assert prov.respostas == []
    wx_falso.resposta_messagebox[0] = wx_falso.YES
    dlg.responder(False)
    assert prov.respostas == [("9@g.us", ["1@lid"], False)]
    assert "Recusar 1 pedido?" in wx_falso.mensagens[0]


def test_sem_pedidos_ou_sem_escolha_diz_o_que_acontece():
    prov, fala = Prov(), Fala()
    prov.pedidos = []
    dlg = ge.DialogoPedidos(None, prov, "9@g.us", "Turma", fala)
    assert dlg.lista.itens == ["Nenhum pedido."]
    assert fala.ditas[-1] == "Nenhum pedido de entrada esperando."
    dlg.responder(True)
    assert fala.ditas[-1] == "Escolha um pedido na lista."
    assert prov.respostas == []


def test_falha_ao_responder_avisa_e_nao_recarrega():
    prov, fala = Prov(), Fala()
    prov.responder_pedidos = lambda *a: (False, "precisa da DLL de teste nova")
    dlg = ge.DialogoPedidos(None, prov, "9@g.us", "Turma", fala)
    dlg.lista.SetSelection(0)
    dlg.responder(True)
    assert fala.ditas[-1] == "precisa da DLL de teste nova"
    assert wx_falso.mensagens[-1] == "precisa da DLL de teste nova"


def test_convite_troca_o_link_e_copia_o_novo():
    copiados, fala = [], Fala()
    dlg = ge.DialogoConvite(None, "https://chat/velho", copiados.append,
                            lambda: (True, "https://chat/novo"), fala)
    dlg.copiar()
    dlg.trocar()
    assert copiados == ["https://chat/velho", "https://chat/novo"]
    assert dlg.link == "https://chat/novo"
    assert fala.ditas[-1] == "Link trocado e copiado."


def test_convite_que_nao_troca_mantem_o_link():
    fala = Fala()
    dlg = ge.DialogoConvite(None, "https://chat/velho", lambda t: None,
                            lambda: (False, "O WhatsApp não aceitou."), fala)
    dlg.trocar()
    assert dlg.link == "https://chat/velho"
    assert fala.ditas[-1] == "O WhatsApp não aceitou."


# ------------------------------------------------ botoes dos detalhes
def _controle(prov, tipo, dados):
    jan = types.SimpleNamespace(
        contas=types.SimpleNamespace(provedor=lambda conta: prov),
        indice={}, fala=Fala())
    conv = m.Conversa("w1", "9@g.us" if tipo == "grupo" else "5@s.whatsapp.net",
                      "Alvo", "whatsapp", tipo)
    ctl = det.ControleDetalhes(jan, conv)
    ctl.dados = dados
    return ctl


def _rotulos(ctl):
    return [r.replace("&", "") for r, _ in ctl._botoes()]


def test_admin_ve_pedidos_e_todos_veem_a_foto_do_grupo():
    prov = types.SimpleNamespace(FOTO_DO_GRUPO=True, PEDIDOS_DE_ENTRADA=True)
    admin = _rotulos(_controle(prov, "grupo", {"sou_admin": True}))
    assert "Ver a foto do grupo" in admin
    assert "Pedidos de entrada..." in admin
    comum = _rotulos(_controle(prov, "grupo", {"sou_admin": False}))
    assert "Ver a foto do grupo" in comum
    assert "Pedidos de entrada..." not in comum


def test_servico_sem_o_recurso_nao_mostra_os_botoes():
    prov = types.SimpleNamespace()
    rotulos = _rotulos(_controle(prov, "grupo", {"sou_admin": True}))
    assert not [r for r in rotulos if "foto" in r or "Pedidos" in r]
    assert "Adicionar a um grupo..." not in _rotulos(
        _controle(prov, "privada", {}))


def test_conversa_privada_oferece_adicionar_a_um_grupo():
    prov = types.SimpleNamespace(LISTA_GRUPOS_ADMIN=True)
    assert "Adicionar a um grupo..." in _rotulos(
        _controle(prov, "privada", {}))


def test_adicionar_a_um_grupo_escolhido_chama_administrar(monkeypatch):
    chamadas = []
    prov = types.SimpleNamespace(
        LISTA_GRUPOS_ADMIN=True,
        grupos_que_administro=lambda: [("7@g.us", "Turma")],
        administrar_grupo=lambda cid, acao, valor: chamadas.append(
            (cid, acao, valor)) or (True, "x"))
    ctl = _controle(prov, "privada", {})
    ctl.dlg = types.SimpleNamespace()

    class Escolha:
        def __init__(self, *a, **k):
            pass

        def ShowModal(self):
            return wx_falso.ID_OK

        def GetSelection(self):
            return 0

        def Destroy(self):
            pass
    monkeypatch.setattr(det.wx, "SingleChoiceDialog", Escolha, raising=False)
    ctl.adicionar_a_grupo()
    assert chamadas == [("7@g.us", "adicionar", "5@s.whatsapp.net")]
    assert "Alvo foi adicionado ao grupo Turma." in wx_falso.mensagens


def _canal_deixado(resposta):
    removidos = []
    ctl = _controle(types.SimpleNamespace(), "canal", {})
    ctl.conv = m.Conversa("w1", "c@newsletter", "Canal", "whatsapp", "canal")
    ctl.jan.indice = {ctl.conv.chave: ctl.conv}
    ctl.jan._remover_conversa_local = removidos.append
    ctl.dlg = types.SimpleNamespace(EndModal=lambda i: None)
    wx_falso.resposta_messagebox[0] = resposta
    ctl._resultado_canal("deixar_de_seguir", True, "Você deixou de seguir.")
    return removidos, ctl


def test_deixar_de_seguir_pergunta_e_apaga_se_a_pessoa_quiser():
    removidos, ctl = _canal_deixado(wx_falso.YES)
    assert removidos == [ctl.conv]
    assert "Apagar a conversa" in wx_falso.mensagens[-1]


def test_deixar_de_seguir_mantem_na_lista_por_padrao():
    removidos, _ = _canal_deixado(wx_falso.NO)
    assert removidos == []

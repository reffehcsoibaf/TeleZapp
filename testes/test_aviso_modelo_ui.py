# SPDX-License-Identifier: GPL-3.0-or-later
"""Campo de modelo do aviso falado e o botão de flags na janela."""
import sys

from testes import wx_falso

sys.modules["wx"] = wx_falso

from telezapp.interface import lista_conversas as ui    # noqa: E402
from telezapp.nucleo import aviso_de_nova as an          # noqa: E402


class Fala:
    def __init__(self):
        self.ditas = []

    def falar(self, texto, interromper=False):
        self.ditas.append(texto)


class Gravador:
    def __init__(self, valor):
        self.valor = valor

    def ler(self):
        return self.valor

    def gravar(self, novo):
        self.valor = novo


def dialogo(valor=None):
    g, fala = Gravador(valor), Fala()
    d = ui.DialogoListaConversas(
        None, g.ler, g.gravar, fala, nucleo=an,
        titulo="Aviso falado de mensagem nova")
    return d, g, fala


def test_dialogo_tem_campo_de_modelo_e_botao_de_flags():
    d, g, _ = dialogo()
    assert d.modelo.GetValue() == an.MODELO_PADRAO
    assert d.botao_flags is not None
    assert d.lista.itens[0] == \
        'As palavras "Nova mensagem": ativado'
    assert d.lista.itens[2] == 'Serviço (WhatsApp ou Telegram): desativado'


def test_digitar_no_modelo_ativa_e_desativa_os_itens():
    d, g, _ = dialogo()
    d.modelo.SetValue("$New $Sender_Name")
    d.mudar_modelo()
    assert g.valor["modelo"] == "$New $Sender_Name"
    assert an.ativos(g.valor) == ["inicio", "autor"]
    assert d.lista.itens[1] == \
        "Nome da conversa (fora da conversa aberta): desativado"
    d.modelo.SetValue("")
    d.mudar_modelo()
    assert an.ativos(g.valor) == []


def test_alternar_um_item_escreve_e_apaga_a_flag_no_campo():
    d, g, fala = dialogo()
    d.lista.SetSelection(5)                # hora
    d.alternar()
    assert "$Time" not in d.modelo.GetValue()
    assert fala.ditas[-1] == "desativado"
    d.lista.SetSelection(2)                # servico
    d.alternar()
    assert d.modelo.GetValue().endswith("$Service")
    assert fala.ditas[-1] == "ativado"


def test_botao_insere_a_flag_no_ponto_do_cursor(monkeypatch):
    class FlagsFalsas:
        def __init__(self, *a, **k):
            self.escolhida = "$Time"

        def ShowModal(self):
            return wx_falso.ID_OK

        def Destroy(self):
            pass

    monkeypatch.setattr(ui, "DialogoFlags", FlagsFalsas)
    d, g, _ = dialogo()
    d.modelo.SetValue("$New de $Sender_Name")
    d.modelo.SetInsertionPoint(4)
    d.inserir_flag()
    assert g.valor["modelo"] == "$New$Time de $Sender_Name"
    assert "hora" not in g.valor["ocultos"]


def test_popup_de_flags_escolhe_com_enter():
    fala = Fala()
    dlg = ui.DialogoFlags(None, an.FLAGS, an.ROTULOS, fala)
    assert dlg.lista.itens[0] == '$New — As palavras "Nova mensagem"'
    dlg.escolher(2)
    assert dlg.escolhida == "$Service"
    assert fala.ditas[-1] == "Inserir $Service."
    assert dlg.encerrado == wx_falso.ID_OK


def test_restaurar_volta_o_modelo_padrao_e_a_busca_acha_o_campo():
    d, g, _ = dialogo()
    d.modelo.SetValue("$New")
    d.mudar_modelo()
    d.restaurar()
    assert g.valor == an.padrao()
    assert d.modelo.GetValue() == an.MODELO_PADRAO
    g = Gravador(None)
    d = ui.DialogoListaConversas(None, g.ler, g.gravar, foco="modelo",
                                 nucleo=an)
    assert wx_falso._foco[0] is d.modelo

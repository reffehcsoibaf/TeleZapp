# SPDX-License-Identifier: GPL-3.0-or-later
"""Janela do aviso com um bloco de lista + modelo por tipo de conversa."""
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


def dialogo(valor=None, foco=None):
    g, fala = Gravador(valor), Fala()
    d = ui.DialogoAvisoNova(None, g.ler, g.gravar, fala, foco=foco)
    return d, g, fala


def test_janela_tem_um_bloco_por_tipo():
    d, g, _ = dialogo()
    assert list(d.blocos) == list(an.TIPOS)
    for tipo in an.TIPOS:
        bloco = d.blocos[tipo]
        assert bloco.rotulo_info.GetLabel() == (
            "Informações de %s (Enter ou Espaço ativa e desativa):"
            % an.ROTULOS_TIPO[tipo].lower())
        assert bloco.modelo.GetValue() == an.MODELO_PADRAO
        assert bloco.lista.itens[0] == \
            'As palavras "Nova mensagem": ativado'
        assert bloco.lista.itens[2] == \
            'Serviço (WhatsApp ou Telegram): desativado'


def test_digitar_num_tipo_nao_mexe_os_outros():
    d, g, _ = dialogo()
    bloco = d.blocos["grupo"]
    bloco.modelo.SetValue("$New de $Sender_Name")
    bloco.mudar_modelo()
    assert an.bloco(g.valor, "grupo")["modelo"] == "$New de $Sender_Name"
    assert an.ativos(g.valor, "grupo") == ["inicio", "autor"]
    assert an.bloco(g.valor, "privada")["modelo"] == an.MODELO_PADRAO
    assert an.bloco(g.valor, "canal")["modelo"] == an.MODELO_PADRAO
    bloco.modelo.SetValue("")
    bloco.mudar_modelo()
    assert an.ativos(g.valor, "grupo") == []
    assert an.ativos(g.valor, "privada") != []


def test_alternar_um_item_escreve_e_apaga_a_flag_so_do_seu_tipo():
    d, g, fala = dialogo()
    bloco = d.blocos["canal"]
    bloco.lista.SetSelection(5)                # hora
    bloco.alternar()
    assert "$Time" not in bloco.modelo.GetValue()
    assert fala.ditas[-1] == "desativado"
    bloco.lista.SetSelection(2)                # servico
    bloco.alternar()
    assert bloco.modelo.GetValue().endswith("$Service")
    assert fala.ditas[-1] == "ativado"
    assert "$Service" not in d.blocos["privada"].modelo.GetValue()


def test_botao_abre_um_menu_com_todas_as_flags():
    bloco = dialogo()[0].blocos["privada"]
    bloco.inserir_flag()
    menu = bloco.botao_flags.menu_popup
    assert [i.GetLabel() for i in menu.itens] == [
        '$New — As palavras "Nova mensagem"',
        "$conversation_out — Nome da conversa (fora da conversa aberta)",
        "$Service — Serviço (WhatsApp ou Telegram)",
        "$Account — Conta que recebeu",
        "$Sender_Name — Nome de quem enviou",
        "$Time — Hora da mensagem",
        "$Content — Conteúdo (texto, tipo da mídia e legenda)"]
    assert menu.destruido


def test_flag_escolhida_no_menu_vai_para_o_fim_do_campo_do_tipo():
    d, g, _ = dialogo()
    bloco = d.blocos["grupo"]
    bloco.modelo.SetValue("$New de $Sender_Name")
    bloco.modelo.SetInsertionPoint(4)      # o cursor nao importa: entra no fim
    bloco.inserir_flag()
    menu = bloco.botao_flags.menu_popup
    hora = menu.itens[5]
    # O comando do item de um popup vai para a janela, nao para o menu.
    d.ligacoes_por_id[(wx_falso.EVT_MENU, hora.GetId())](None)
    assert g.valor["tipos"]["grupo"]["modelo"] == \
        "$New de $Sender_Name$Time"
    assert "hora" not in an.bloco(g.valor, "grupo")["ocultos"]
    assert bloco.modelo.GetValue() == "$New de $Sender_Name$Time"
    assert bloco.modelo.GetInsertionPoint() == len("$New de $Sender_Name$Time")
    assert wx_falso._foco[0] is bloco.modelo
    assert an.bloco(g.valor, "canal")["modelo"] == an.MODELO_PADRAO


def test_restaurar_volta_o_padrao_so_do_bloco():
    d, g, _ = dialogo()
    bloco = d.blocos["canal"]
    bloco.modelo.SetValue("$Content")
    bloco.mudar_modelo()
    bloco.restaurar()
    assert an.bloco(g.valor, "canal") == an.bloco(an.padrao(), "canal")
    assert bloco.modelo.GetValue() == an.MODELO_PADRAO
    assert g.valor["tipos"]["privada"] == an.bloco(an.padrao(), "privada")


def test_busca_pode_focar_o_modelo_de_cada_tipo():
    for tipo in an.TIPOS:
        g = Gravador(None)
        d = ui.DialogoAvisoNova(
            None, g.ler, g.gravar, foco="modelo:%s" % tipo)
        assert wx_falso._foco[0] is d.blocos[tipo].modelo

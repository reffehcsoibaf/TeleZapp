# SPDX-License-Identifier: GPL-3.0-or-later
"""Tons de pele nos emojis: a familia de cada emoji, e as setas esquerda e
direita na busca completa e na lista curta de reacoes."""
import sys

from testes import wx_falso

sys.modules["wx"] = wx_falso

from telezapp.interface import emojis as ui              # noqa: E402
from telezapp.nucleo import emojis                       # noqa: E402

CLARO, MORENO, ESCURO = "👍🏻", "👍🏽", "👍🏿"


class Fala:
    def __init__(self):
        self.ditas = []

    def falar(self, texto, interromper=False):
        self.ditas.append(texto)


class Tecla:
    def __init__(self, codigo):
        self.codigo, self.pulou = codigo, False

    def GetKeyCode(self):
        return self.codigo

    def ControlDown(self):
        return False

    AltDown = ShiftDown = ControlDown

    def Skip(self):
        self.pulou = True


# ---------------------------------------------------------------- regras
def test_o_emoji_sem_tom_abre_a_familia_do_claro_ao_escuro():
    primeiro = emojis.passo_de_tom("👍", 1)
    assert primeiro.simbolo == CLARO and "clara" in primeiro.nome
    seguidos = ["👍"]
    for _ in range(5):
        seguidos.append(emojis.passo_de_tom(seguidos[-1], 1).simbolo)
    assert seguidos[1] == CLARO and seguidos[3] == MORENO
    assert seguidos[5] == ESCURO
    assert emojis.passo_de_tom(ESCURO, 1).simbolo == "👍"       # da a volta
    assert emojis.passo_de_tom("👍", -1).simbolo == ESCURO
    assert emojis.passo_de_tom(CLARO, -1).simbolo == "👍"


def test_emoji_sem_tons_nao_tem_passo():
    assert emojis.passo_de_tom("😂", 1) is None
    assert emojis.passo_de_tom("❤️", 1) is None
    assert emojis.passo_de_tom("", 1) is None


def test_a_lista_continua_sem_as_variantes_e_o_nome_vale_para_elas():
    simbolos = {e.simbolo for e in emojis.todos()}
    assert "👍" in simbolos and CLARO not in simbolos
    assert "pele" in emojis.nome_de(MORENO)
    assert emojis.nome_de("👍") == "polegar para cima"


def test_emoji_com_seletor_de_variacao_tambem_tem_tons():
    # ✋ e escrito com U+FE0F em alguns pacotes e sem nos tons
    mao = emojis.passo_de_tom("✋", 1)
    assert mao is not None and mao.simbolo.startswith("✋")


# ------------------------------------------------------ busca completa
def _busca(texto="joinha"):
    fala = Fala()
    dlg = ui.DialogoEmoji(None, fala=fala)
    dlg.busca.SetValue(texto)
    dlg._preencher()
    dlg.lista.SetSelection(0)
    return dlg, fala


def test_setas_na_busca_trocam_o_tom_e_falam():
    dlg, fala = _busca()
    assert dlg._achados[0].simbolo == "👍"
    assert dlg.passo_de_tom(1)
    assert dlg.lista.itens[0].startswith(CLARO) and "pele clara" in \
        dlg.lista.itens[0]
    assert fala.ditas[-1] == dlg.lista.itens[0]
    dlg._escolher()
    assert dlg.escolhido == CLARO
    # esquerda volta
    dlg2, _ = _busca()
    assert dlg2.passo_de_tom(-1) and dlg2._achados[0].simbolo == ESCURO


def test_seta_em_emoji_sem_tom_deixa_a_tecla_passar():
    dlg, fala = _busca("rindo")
    dlg.lista.SetSelection(0)
    tecla = Tecla(wx_falso.WXK_RIGHT)
    dlg._tecla_lista(tecla)
    assert tecla.pulou and not fala.ditas
    tecla = Tecla(wx_falso.WXK_DOWN)
    dlg._tecla_lista(tecla)
    assert tecla.pulou
    tecla = Tecla(wx_falso.WXK_RIGHT)
    dlg2, fala2 = _busca()
    dlg2._tecla_lista(tecla)
    assert not tecla.pulou and fala2.ditas       # a seta foi tratada


# ------------------------------------------------------ reacoes rapidas
def test_reacao_rapida_com_tom_de_pele():
    fala = Fala()
    dlg = ui.DialogoReacao(None, "", fala)
    assert dlg.itens[0][0] == "👍"
    dlg.lista.SetSelection(0)
    tecla = Tecla(wx_falso.WXK_RIGHT)
    dlg._tecla(tecla)
    assert not tecla.pulou and dlg.itens[0][0] == CLARO
    dlg.passo_de_tom(1)
    assert dlg.itens[0][0] == emojis.passo_de_tom(CLARO, 1).simbolo
    assert fala.ditas[-1] == dlg.lista.itens[0]
    dlg._escolher()
    assert dlg.escolhido == dlg.itens[0][0] and dlg.escolhido != "👍"


def test_setas_nao_mexem_em_outro_emoji_nem_em_tirar():
    dlg = ui.DialogoReacao(None, "👍🏽", Fala())
    assert [v for v, _ in dlg.itens[-2:]] == [ui.OUTRO, ui.TIRAR]
    for i in (len(dlg.itens) - 2, len(dlg.itens) - 1):
        dlg.lista.SetSelection(i)
        assert not dlg.passo_de_tom(1)
    # ❤️ nao tem tons: a seta passa
    dlg.lista.SetSelection(1)
    assert dlg.itens[1][0] == "❤️" and not dlg.passo_de_tom(1)
    tecla = Tecla(wx_falso.WXK_LEFT)
    dlg._tecla(tecla)
    assert tecla.pulou

# SPDX-License-Identifier: GPL-3.0-or-later
"""Janela Colaborar financeiramente (Pix), seu botao na janela de versao nova
e o texto do site."""
import os
import types

import pytest
import wx

from telezapp.interface import atualizacao as at
from telezapp.interface import colaborar as co

# wx de verdade so existe fora da suite (outros testes trocam o modulo por
# um falso); estes dois rodam sozinhos, em area de trabalho oculta
def exigir_wx_real():
    if not hasattr(wx, "App"):
        pytest.skip("wx falso nesta execucao")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_texto_traz_chave_nome_e_banco():
    t = co.texto_do_pix()
    assert "51989404175" in t and "Fabio Scheffer Moraes" in t
    assert "Caixa Econômica Federal" in t


def test_site_tem_a_mesma_chave_e_o_botao_de_copiar():
    html = open(os.path.join(RAIZ, "site", "index.html"),
                encoding="utf-8").read()
    assert co.PIX_CHAVE in html and "botao-copiar-pix" in html
    assert co.PIX_NOME in html and co.PIX_BANCO in html


def test_botao_fica_entre_o_texto_e_o_sim():
    exigir_wx_real()
    app = wx.App(False)
    lanc = types.SimpleNamespace(versao="2099.1.1.0", pre=False, tamanho=0,
                                 historico=[], notas="x")
    dlg = at.DialogoAtualizacao(None, lanc, "2026.1.1.0", True, "p")
    try:
        filhos = [c for c in dlg.GetChildren()
                  if isinstance(c, (wx.TextCtrl, wx.Button))]
        ordem = [c for c in filhos]
        assert ordem.index(dlg.texto) < ordem.index(dlg.colaborar) \
            < ordem.index(dlg.principal)
        assert "olaborar" in dlg.colaborar.GetLabel()
    finally:
        dlg.Destroy()
        del app


def test_copiar_usa_a_chave_e_avisa(monkeypatch):
    exigir_wx_real()
    app = wx.App(False)
    copiado, ditas = [], []
    monkeypatch.setattr(co, "copiar_para_a_area",
                        lambda t: copiado.append(t) or True)
    fala = types.SimpleNamespace(falar=lambda t, interromper=False:
                                 ditas.append(t))
    dlg = co.DialogoColaborar(None, fala)
    try:
        dlg._copiar(None)
    finally:
        dlg.Destroy()
        del app
    assert copiado == ["51989404175"] and "copiada" in ditas[0]

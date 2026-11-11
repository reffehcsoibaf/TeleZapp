# SPDX-License-Identifier: GPL-3.0-or-later
"""Som de limite de lista: seta para cima no primeiro item ou para baixo no
ultimo, em qualquer lista."""
import sys

from testes import wx_falso

sys.modules["wx"] = wx_falso

from telezapp.interface import limite_de_lista as ll  # noqa: E402

CIMA, BAIXO = wx_falso.WXK_UP, wx_falso.WXK_DOWN


class Lista:
    def __init__(self, n, i):
        self.n, self.i = n, i

    def GetCount(self):
        return self.n

    def GetSelection(self):
        return self.i


class Tabela:
    def __init__(self, n, i):
        self.n, self.i = n, i

    def GetItemCount(self):
        return self.n

    def GetFocusedItem(self):
        return self.i


class Arvore:
    def GetCount(self):
        return 4

    def GetSelection(self):
        return object()


def test_no_primeiro_e_no_ultimo_item_toca():
    assert ll.no_limite(Lista(5, 0), CIMA)
    assert ll.no_limite(Lista(5, 4), BAIXO)
    assert ll.no_limite(Tabela(3, 0), CIMA)
    assert ll.no_limite(Tabela(3, 2), BAIXO)
    assert ll.no_limite(Lista(1, 0), CIMA) and ll.no_limite(Lista(1, 0), BAIXO)


def test_no_meio_com_modificador_ou_vazia_nao_toca():
    assert not ll.no_limite(Lista(5, 2), CIMA)
    assert not ll.no_limite(Lista(5, 0), BAIXO)
    assert not ll.no_limite(Lista(5, 4), CIMA)
    assert not ll.no_limite(Lista(0, -1), CIMA)
    assert not ll.no_limite(Lista(5, -1), BAIXO)
    assert not ll.no_limite(Lista(5, 0), CIMA, shift=True)
    assert not ll.no_limite(Lista(5, 0), CIMA, ctrl_ou_alt=True)
    assert not ll.no_limite(Lista(5, 0), wx_falso.WXK_HOME)


def test_o_que_nao_e_lista_nao_toca():
    assert not ll.no_limite(object(), CIMA)
    assert not ll.no_limite(Arvore(), CIMA)


def test_o_evento_de_tecla_toca_o_bipe(monkeypatch):
    tocados = []
    monkeypatch.setattr(ll.fala, "bipe", lambda t, **k: tocados.append(t))

    class Evt:
        def __init__(self, obj, tecla):
            self.obj, self.tecla = obj, tecla

        def GetEventObject(self):
            return self.obj

        def GetKeyCode(self):
            return self.tecla

        def ShiftDown(self):
            return False

        def ControlDown(self):
            return False

        def AltDown(self):
            return False
    ll.tocar_se_no_limite(Evt(Lista(3, 2), BAIXO))
    ll.tocar_se_no_limite(Evt(Lista(3, 1), BAIXO))
    ll.tocar_se_no_limite(Evt(object(), BAIXO))
    assert tocados == ["limite_da_lista"]

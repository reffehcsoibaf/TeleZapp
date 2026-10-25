# SPDX-License-Identifier: GPL-3.0-or-later
"""Limpeza so de uma conversa (botao dos detalhes da conversa)."""
import sys

from testes import wx_falso

sys.modules["wx"] = wx_falso

from telezapp.armazenamento.banco import Banco               # noqa: E402
from telezapp.interface.limpeza import DialogoLimpeza        # noqa: E402
from telezapp.nucleo import limpeza                          # noqa: E402
from telezapp.nucleo import modelos as m                     # noqa: E402


def _dialogo(banco, conversa=("c", "v", "Ana")):
    ditas, limpas = [], []
    d = DialogoLimpeza(None, banco, [("c", "Conta")],
                       [("c", "v", "Ana"), ("c", "w", "Bia")],
                       ditas.append, limpas.append, so_a_conversa=conversa)
    return d, ditas, limpas


def test_filtros_ficam_presos_na_conversa(tmp_path):
    banco = Banco(str(tmp_path / "b.db"))
    try:
        d, _, _ = _dialogo(banco)
        f = d.filtros()
        assert (f.conta_id, f.conversa_id) == ("c", "v")
        assert f.o_que == limpeza.MIDIAS and f.manter_favoritas
        d.o_que.SetSelection(1)
        d.dias.SetValue(30)
        f = d.filtros()
        assert f.o_que == limpeza.MENSAGENS and f.dias == 30
        assert (f.conta_id, f.conversa_id) == ("c", "v")
        assert not hasattr(d, "conta") and not hasattr(d, "conversa")
    finally:
        banco.fechar()


def test_so_limpa_a_conversa_pedida(tmp_path):
    banco = Banco(str(tmp_path / "b.db"))
    try:
        arq_v, arq_w = tmp_path / "v", tmp_path / "w"
        arq_v.write_bytes(b"x" * 10)
        arq_w.write_bytes(b"y" * 10)
        banco.salvar_mensagens([
            m.Mensagem("c", "v", "1", tipo="foto", data=1.0),
            m.Mensagem("c", "w", "2", tipo="foto", data=1.0)])
        banco.registrar_midia("c", "v", "1", "foto", str(arq_v), 10, 1.0)
        banco.registrar_midia("c", "w", "2", "foto", str(arq_w), 10, 1.0)
        d, _, _ = _dialogo(banco)
        sel = limpeza.selecionar(banco, d.filtros())
        assert [i[:3] for i in sel.itens] == [("c", "v", "1")]
        limpeza.apagar(banco, sel)
        assert not arq_v.exists() and arq_w.exists()
    finally:
        banco.fechar()


def test_titulo_traz_o_nome_da_conversa(tmp_path):
    banco = Banco(str(tmp_path / "b.db"))
    try:
        d, _, _ = _dialogo(banco)
        assert d.so_a_conversa == ("c", "v", "Ana")
    finally:
        banco.fechar()

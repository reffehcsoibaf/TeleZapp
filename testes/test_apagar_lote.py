# SPDX-License-Identifier: GPL-3.0-or-later
"""Apagar muitas mensagens na conta de uma vez (apagar_lote)."""
import types

from telezapp.provedores import base
from telezapp.provedores.telegram import ProvedorTelegram


def _msg(conversa, ident, minha=False):
    return types.SimpleNamespace(conversa_id=conversa, id=ident, minha=minha,
                                 data=0, remetente="")


def test_telegram_um_pedido_por_conversa():
    p = ProvedorTelegram.__new__(ProvedorTelegram)
    agendados = []
    p._agendar = lambda corrotina: (agendados.append(corrotina),
                                    corrotina.close())
    msgs = [_msg("-100", str(i)) for i in range(1517)] + \
        [_msg("-100", "9999", minha=True), _msg("42", "1"), _msg("42", "x")]
    aceitas, pendentes, recusadas = p.apagar_lote(msgs, para_todos=True)
    # canal: as dos outros sem revogar, a minha revogada; a outra conversa
    assert len(agendados) == 3
    assert (aceitas, pendentes, recusadas) == (1519, 0, 1)


def test_base_apaga_uma_a_uma_e_conta_o_resultado():
    p = types.SimpleNamespace()
    respostas = iter([True, base.APAGAR_PENDENTE, False])
    p.apagar_mensagem = lambda x, todos: next(respostas)
    r = base.Provedor.apagar_lote(p, [_msg("a", "1"), _msg("a", "2"),
                                          _msg("a", "3")])
    assert r == (1, 1, 1)


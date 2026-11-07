# SPDX-License-Identifier: GPL-3.0-or-later
"""Seguranca ao entrar: PIN, este computador x outro, adulteracao."""
import json
import os

import pytest

from telezapp.nucleo import backup
from telezapp.nucleo import seguranca as seg


def dpapi_de(computador):
    """DPAPI falso: o que um computador cifra so ele decifra."""
    def dpapi(dados, cifrar):
        if cifrar:
            return computador.encode() + b"|" + dados
        dono, _, resto = dados.partition(b"|")
        return resto if dono == computador.encode() else None
    return dpapi


def test_ligar_e_conferir_o_pin(tmp_path):
    t = seg.Trava(str(tmp_path), dpapi_de("pc1"))
    assert not t.ligada
    with pytest.raises(seg.ErroSeguranca):
        t.ligar("12")                       # curto demais
    t.ligar("4321")
    assert t.ligada and t.deste_computador() and t.usar_hello()
    gravado = (tmp_path / seg.ARQUIVO).read_text(encoding="utf-8")
    assert "4321" not in gravado            # o PIN nunca e gravado
    de_novo = seg.Trava(str(tmp_path), dpapi_de("pc1"))
    assert de_novo.conferir_pin("4321") and not de_novo.conferir_pin("0000")


def test_em_outro_computador_vale_so_o_pin(tmp_path):
    seg.Trava(str(tmp_path), dpapi_de("pc1")).ligar("4321")
    longe = seg.Trava(str(tmp_path), dpapi_de("pc2"))
    assert longe.ligada and not longe.deste_computador()
    assert longe.conferir_pin("4321")
    assert longe.vincular_este_computador() and longe.deste_computador()


def test_marca_sem_arquivo_e_adulteracao(tmp_path):
    t = seg.Trava(str(tmp_path), dpapi_de("pc1"))
    assert not t.adulterada(False) and t.adulterada(True)
    t.ligar("4321")
    assert not seg.Trava(str(tmp_path)).adulterada(True)
    (tmp_path / seg.ARQUIVO).write_text("{estragado", encoding="utf-8")
    assert seg.Trava(str(tmp_path)).adulterada(True)


def test_espera_depois_de_varios_erros(tmp_path, monkeypatch):
    t = seg.Trava(str(tmp_path), dpapi_de("pc1"))
    t.ligar("4321")
    for _ in range(seg.TENTATIVAS_ANTES_DE_ESPERAR):
        assert not t.conferir_pin("0000")
    with pytest.raises(seg.ErroSeguranca):
        t.conferir_pin("4321")              # certo, mas tem de esperar
    monkeypatch.setattr(seg.time, "monotonic",
                        lambda: 10 ** 9)    # o tempo passou
    assert t.conferir_pin("4321")


def test_desligar_apaga_o_arquivo(tmp_path):
    t = seg.Trava(str(tmp_path), dpapi_de("pc1"))
    t.ligar("4321")
    t.desligar()
    assert not os.path.exists(tmp_path / seg.ARQUIVO) and not t.ligada


def test_backup_nunca_leva_nem_restaura_a_marca():
    assert "seguranca_ao_entrar" not in backup.opcoes_do_backup(
        {"seguranca_ao_entrar": True})
    assert "aviso_nova" in backup.opcoes_do_backup({})


def test_dpapi_de_verdade_deste_windows(tmp_path):
    if os.name != "nt":
        pytest.skip("Windows")
    blob = seg._dpapi(b"segredo", True)
    assert blob and blob != b"segredo"
    assert seg._dpapi(blob, False) == b"segredo"
    t = seg.Trava(str(tmp_path))
    t.ligar("4321")
    assert seg.Trava(str(tmp_path)).deste_computador()


def _autenticar_com(tmp_path, monkeypatch, resposta_do_hello, pin="1234"):
    import sys
    from testes import wx_falso
    sys.modules.setdefault("wx", wx_falso)
    from telezapp.interface import seguranca as ui
    trava = seg.Trava(str(tmp_path))
    trava.ligar("1234", True)
    pedidos = []
    monkeypatch.setattr(seg, "hello_disponivel", lambda: True)
    monkeypatch.setattr(ui, "pedir_hello",
                        lambda pai, motivo: resposta_do_hello)
    monkeypatch.setattr(ui, "_pedir_pin",
                        lambda pai, texto, titulo="": pedidos.append(texto)
                        or pin)
    return ui.autenticar(None, trava), pedidos


def test_hello_verificado_entra_sem_pedir_o_pin(tmp_path, monkeypatch):
    ok, pedidos = _autenticar_com(tmp_path, monkeypatch, seg.HELLO_OK)
    assert ok is True and pedidos == []


def test_hello_recusado_ou_trocado_pelo_pin_pede_o_pin(tmp_path, monkeypatch):
    for resposta in (seg.HELLO_CANCELADO, seg.HELLO_INDISPONIVEL, "usar_pin"):
        ok, pedidos = _autenticar_com(tmp_path, monkeypatch, resposta)
        assert ok is True and len(pedidos) == 1


def test_guid_do_hello_tem_a_ordem_do_windows():
    from telezapp.nucleo import hello_janela as h
    g = h._guid(h.IID_INTEROP)
    assert (g.a, g.b, g.c) == (0x39E050C3, 0x4E74, 0x441A)
    assert bytes(g.d) == bytes.fromhex("8DC0B81104DF949C")

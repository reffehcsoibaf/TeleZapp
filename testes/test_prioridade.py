# SPDX-License-Identifier: GPL-3.0-or-later
"""Modo chamada: o processo nao pode ser tratado como "de fundo" pelo
Windows enquanto ha uma chamada."""
import sys

import pytest

from telezapp.midia import prioridade


def test_fora_do_windows_nao_faz_nada(monkeypatch):
    monkeypatch.setattr(prioridade, "_WINDOWS", False)
    monkeypatch.setattr(prioridade, "_ativa", [False])
    prioridade.chamada_em_curso(True)
    assert not prioridade.esta_ativa()
    assert prioridade.thread_de_audio() == 0
    prioridade.soltar_thread(0)


@pytest.mark.skipif(sys.platform != "win32", reason="so no Windows")
def test_liga_e_desliga_sem_erro_no_windows():
    prioridade.chamada_em_curso(False)
    prioridade.chamada_em_curso(True)
    assert prioridade.esta_ativa()
    prioridade.chamada_em_curso(True)            # repetir nao faz mal
    prioridade.chamada_em_curso(False)
    assert not prioridade.esta_ativa()
    ident = prioridade.thread_de_audio()
    prioridade.soltar_thread(ident)


def test_erro_do_windows_nao_estoura(monkeypatch):
    monkeypatch.setattr(prioridade, "_WINDOWS", True)

    def falha(_):
        raise OSError("sem permissão")
    monkeypatch.setattr(prioridade, "_energia_do_processo", falha)
    monkeypatch.setattr(prioridade, "_ativa", [False])
    prioridade.chamada_em_curso(True)            # so vai para o log


def test_abertura_fora_do_windows_nao_faz_nada(monkeypatch):
    monkeypatch.setattr(prioridade, "_WINDOWS", False)
    monkeypatch.setattr(prioridade, "_na_abertura", [False])
    prioridade.abertura(True)
    assert not prioridade.na_abertura()


def test_abertura_pede_prioridade_e_devolve_ao_normal(monkeypatch):
    chamadas = []
    monkeypatch.setattr(prioridade, "_WINDOWS", True)
    monkeypatch.setattr(prioridade, "_na_abertura", [False])
    monkeypatch.setattr(prioridade, "_ativa", [False])
    monkeypatch.setattr(prioridade, "_classe_do_processo",
                        lambda c: chamadas.append(("classe", c)))
    monkeypatch.setattr(prioridade, "_energia_do_processo",
                        lambda sem: chamadas.append(("energia", sem)))
    prioridade.abertura(True)
    prioridade.abertura(True)                    # repetir nao faz mal
    assert prioridade.na_abertura()
    assert chamadas == [("classe", prioridade._ACIMA_DO_NORMAL),
                        ("energia", True)]
    prioridade.abertura(False)
    assert not prioridade.na_abertura()
    assert chamadas[2:] == [("classe", prioridade._NORMAL),
                            ("energia", False)]


def test_abertura_nao_solta_a_energia_com_chamada_em_curso(monkeypatch):
    chamadas = []
    monkeypatch.setattr(prioridade, "_WINDOWS", True)
    monkeypatch.setattr(prioridade, "_na_abertura", [True])
    monkeypatch.setattr(prioridade, "_ativa", [True])
    monkeypatch.setattr(prioridade, "_classe_do_processo",
                        lambda c: chamadas.append(("classe", c)))
    monkeypatch.setattr(prioridade, "_energia_do_processo",
                        lambda sem: chamadas.append(("energia", sem)))
    prioridade.abertura(False)
    assert chamadas == [("classe", prioridade._NORMAL)]


def test_erro_da_abertura_nao_estoura(monkeypatch):
    monkeypatch.setattr(prioridade, "_WINDOWS", True)
    monkeypatch.setattr(prioridade, "_na_abertura", [False])

    def falha(_):
        raise OSError("sem permissão")
    monkeypatch.setattr(prioridade, "_classe_do_processo", falha)
    prioridade.abertura(True)                    # so vai para o log


@pytest.mark.skipif(sys.platform != "win32", reason="so no Windows")
def test_abertura_real_no_windows_liga_e_desliga():
    prioridade.abertura(False)
    prioridade.abertura(True)
    assert prioridade.na_abertura()
    prioridade.abertura(False)
    assert not prioridade.na_abertura()

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

# SPDX-License-Identifier: GPL-3.0-or-later
"""Saude dos dados: banco danificado e disco externo."""
import sqlite3
import types

import pytest

from telezapp.nucleo import saude_dados as sd
from telezapp.nucleo import midias as nm


def _banco(caminho, linhas=3000):
    con = sqlite3.connect(caminho)
    con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, x TEXT)")
    con.executemany("INSERT INTO t (x) VALUES (?)",
                    [("linha %d" % i * 5,) for i in range(linhas)])
    con.execute("CREATE INDEX i ON t(x)")
    con.commit()
    con.close()


def test_banco_inteiro_confere_ok(tmp_path):
    arquivo = str(tmp_path / "a.db")
    _banco(arquivo)
    estado, detalhe, _ = sd.conferir_banco(arquivo)
    assert (estado, detalhe) == ("ok", "")


def test_banco_com_pagina_estragada_e_danificado(tmp_path):
    arquivo = str(tmp_path / "a.db")
    _banco(arquivo)
    with open(arquivo, "r+b") as f:
        f.seek(4096 * 6)
        f.write(b"\xff" * 4096)
    estado, detalhe, _ = sd.conferir_banco(arquivo)
    assert estado == "danificado" and detalhe


def test_arquivo_que_nao_e_banco_e_danificado_e_ausente_e_inconclusivo(
        tmp_path):
    lixo = tmp_path / "b.db"
    lixo.write_bytes(b"isto nao e um banco" * 500)
    assert sd.conferir_banco(str(lixo))[0] == "danificado"
    assert sd.conferir_banco(str(tmp_path / "nao-existe.db"))[0] == \
        "inconclusivo"


def test_banco_travado_nao_vira_dano(tmp_path):
    def travado(caminho, timeout):
        raise sqlite3.OperationalError("database is locked")
    arquivo = tmp_path / "c.db"
    arquivo.write_bytes(b"x")
    assert sd.conferir_banco(str(arquivo), abrir=travado)[0] == \
        "inconclusivo"


def test_disco_so_e_perguntado_no_windows(tmp_path):
    assert sd.tipo_do_disco(str(tmp_path), sistema="linux") == ""


def test_avisos_trazem_o_cuidado_e_a_pasta():
    pasta = r"E:\TeleZapp\dados"
    texto = sd.aviso_do_disco(sd.USB, pasta, "TeleZapp")
    assert pasta in texto and "ejetar" in texto
    assert "disco externo" in texto
    erro = sd.aviso_do_banco("da conta x", "malformed", "TeleZapp")
    assert "malformed" in erro and "Feedback" in erro


def test_leitura_de_midia_com_banco_danificado_nao_derruba(monkeypatch):
    avisos = []
    monkeypatch.setattr(sd, "_ja_avisados", set())
    monkeypatch.setattr(sd, "ao_falhar", lambda onde, d: avisos.append(onde))

    class Banco:
        def midia(self, *a):
            raise sqlite3.DatabaseError("database disk image is malformed")
    gerente = nm.GerenteMidias.__new__(nm.GerenteMidias)
    gerente.banco = Banco()
    msg = types.SimpleNamespace(conta_id="c", conversa_id="v", id="m")
    assert gerente.caminho(msg) is None
    assert gerente.caminho(msg) is None
    assert avisos == ["as mídias"]                 # avisa uma vez só


def test_outro_erro_do_banco_continua_subindo(monkeypatch):
    class Banco:
        def midia(self, *a):
            raise sqlite3.OperationalError("database is locked")
    gerente = nm.GerenteMidias.__new__(nm.GerenteMidias)
    gerente.banco = Banco()
    msg = types.SimpleNamespace(conta_id="c", conversa_id="v", id="m")
    with pytest.raises(sqlite3.OperationalError):
        gerente.caminho(msg)

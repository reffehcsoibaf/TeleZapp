# SPDX-License-Identifier: GPL-3.0-or-later
"""O libmagic nao acha o banco de tipos numa pasta com letra acentuada."""
import os
import shutil

import pytest

magic = pytest.importorskip("magic")
from magic import magic as mg  # noqa: E402

from telezapp.midia import tipos_de_arquivo as ta  # noqa: E402


def test_banco_em_pasta_com_acento_passa_para_um_caminho_sem_acento(
        tmp_path, monkeypatch):
    acentuada = tmp_path / "Lucas Aribé" / "magic"
    acentuada.mkdir(parents=True)
    copia = acentuada / "magic.mgc"
    shutil.copyfile(mg.default_magic_file, copia)
    monkeypatch.setattr(mg, "default_magic_file", str(copia))
    monkeypatch.setattr(mg, "_instances", {})
    publica = tmp_path / "publica"
    publica.mkdir()
    monkeypatch.setenv("PUBLIC", str(publica))
    # sem nome curto (8.3): vale a copia na pasta publica
    monkeypatch.setattr(ta, "_caminho_curto", lambda c: "")
    assert ta.consertar_caminho_do_magic()
    assert mg.default_magic_file.isascii() and os.path.isfile(
        mg.default_magic_file)
    assert magic.from_buffer(b"%PDF-1.4\n" + bytes(64),
                             mime=True) == "application/pdf"


def test_caminho_sem_acento_fica_como_esta(monkeypatch):
    monkeypatch.setattr(mg, "default_magic_file", "C:/x/magic.mgc")
    assert not ta.consertar_caminho_do_magic()

# SPDX-License-Identifier: GPL-3.0-or-later
"""Escolha do leitor de midia (a parte que nao depende da tela)."""
import sys

import pytest

from testes import wx_falso

sys.modules["wx"] = wx_falso

from telezapp.interface import visualizadores as v  # noqa: E402
from telezapp.nucleo import modelos as m  # noqa: E402


@pytest.mark.parametrize("tipo,arquivo,esperado", [
    (m.FOTO, "a.jpg", v.IMAGEM), (m.FIGURINHA, "a.webp", v.IMAGEM),
    (m.VOZ, "a.ogg", v.AUDIO), (m.AUDIO, "a.m4a", v.AUDIO),
    (m.VIDEO, "a.mp4", v.VIDEO),
    (m.DOCUMENTO, "video.mp4", v.VIDEO),       # video enviado como arquivo
    (m.DOCUMENTO, "musica.mp3", v.AUDIO),
    (m.DOCUMENTO, "foto.png", v.IMAGEM),
    (m.DOCUMENTO, "a.pdf", v.DOCUMENTO), (m.DOCUMENTO, "a.docx", v.DOCUMENTO),
])
def test_escolher(tmp_path, tipo, arquivo, esperado):
    assert v.escolher(tipo, str(tmp_path / arquivo)) == esperado


def test_texto_pequeno_abre_no_app_e_grande_nao(tmp_path):
    pequeno = tmp_path / "a.txt"
    pequeno.write_text("oi")
    assert v.escolher(m.DOCUMENTO, str(pequeno)) == v.TEXTO
    grande = tmp_path / "b.txt"
    grande.write_bytes(b"x" * (v.LIMITE_TEXTO + 1))
    assert v.escolher(m.DOCUMENTO, str(grande)) == v.DOCUMENTO
    assert v.escolher(m.DOCUMENTO, str(tmp_path / "nao_existe.txt")) == \
        v.DOCUMENTO


def test_descricao_e_nome_para_salvar():
    x = m.Mensagem("c", "v", "1", autor="Ana", tipo=m.DOCUMENTO,
                   nome_arquivo="relatório.pdf", tamanho=2048, data=1.0)
    d = v.descricao(x, "Família")
    assert d.startswith("Conversa: Família") and "relatório.pdf" in d
    assert v.nome_para_salvar(x, "/x/1_relatório.pdf") == "relatório.pdf"
    y = m.Mensagem("c", "v", "9", tipo=m.FOTO)
    assert v.nome_para_salvar(y, "/x/9_nome.jpg") == "nome.jpg"
    assert v.nome_para_salvar(y, "/x/9.jpg") == "9.jpg"

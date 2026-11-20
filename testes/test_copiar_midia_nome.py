# SPDX-License-Identifier: GPL-3.0-or-later
"""Copiar uma midia: ao colar, o arquivo nao leva o codigo da mensagem."""
import os

from telezapp import config
from telezapp.midia import armazem
from telezapp.nucleo import modelos as m


def _msg(tipo, id_="3EB0A1B2C3", nome="", data=1763560205.0):
    return m.Mensagem("w1", "10", id_, tipo=tipo, nome_arquivo=nome,
                      data=data)


def test_documento_cola_so_com_o_nome_dado_por_quem_enviou():
    x = _msg(m.DOCUMENTO, nome="relatorio final.pdf")
    caminho = armazem.com_extensao(armazem.caminho_base(x), ".pdf")
    assert os.path.basename(caminho).startswith("3EB0A1B2C3_")
    assert armazem.nome_para_copiar(x, caminho) == "relatorio final.pdf"


def test_sem_nome_vira_tipo_data_e_hora_e_mantem_a_extensao():
    x = _msg(m.VOZ)
    nome = armazem.nome_para_copiar(x, "C:/p/3EB0A1B2C3.ogg")
    assert nome.startswith("mensagem de voz 20") and nome.endswith(".ogg")
    assert "3EB0A1B2C3" not in nome


def test_copia_para_colar_cria_arquivo_com_nome_limpo(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "pasta_dados", lambda: str(tmp_path))
    original = tmp_path / "3EB0A1B2C3_foto da familia.jpg"
    original.write_bytes(b"dados")
    x = _msg(m.FOTO, nome="foto da familia.jpg")
    copia = armazem.copia_para_colar(x, str(original))
    assert os.path.basename(copia) == "foto da familia.jpg"
    assert copia != str(original) and open(copia, "rb").read() == b"dados"
    assert os.path.exists(original)             # o original fica
    # a copia anterior some quando se copia outra
    outra = armazem.copia_para_colar(x, str(original))
    assert os.path.exists(outra) and not os.path.exists(copia)


def test_se_nao_der_para_copiar_usa_o_proprio_arquivo(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "pasta_dados", lambda: str(tmp_path))
    x = _msg(m.DOCUMENTO, nome="a.pdf")
    assert armazem.copia_para_colar(x, str(tmp_path / "nao_existe.pdf")) == \
        str(tmp_path / "nao_existe.pdf")

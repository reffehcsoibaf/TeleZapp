# SPDX-License-Identifier: GPL-3.0-or-later
"""Envio de relatos pela janela de Feedback."""
import io
import urllib.error

import pytest

from telezapp import VERSAO
from telezapp.nucleo import relatos as rl


class Resposta:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b'{"ok": true}'


def test_contato_e_obrigatorio_e_descricao_so_sem_logs():
    assert rl.falta(" ", "algo", True) == "contato"
    assert rl.falta("a@b", " ", False) == "descricao"
    assert rl.falta("a@b", " ", True) == ""
    assert rl.falta("a@b", "algo", False) == ""


def test_logs_ficam_no_limite_e_guardam_o_fim(tmp_path):
    (tmp_path / "falha-nativa.log").write_bytes(b"queda\n")
    (tmp_path / "telezapp.log").write_bytes(b"velha\n" * 100 + b"ultima\n")
    (tmp_path / "telezapp.log.1").write_bytes(b"x" * 500)
    (tmp_path / "config.json").write_bytes(b"segredo")
    logs = dict(rl.juntar_logs(str(tmp_path), limite=100))
    assert logs["falha-nativa.log"] == b"queda\n"
    assert logs["telezapp.log"].endswith(b"ultima\n")
    assert logs["telezapp.log"].startswith(b"velha\n")       # sem linha cortada
    assert sum(map(len, logs.values())) <= 100
    assert "config.json" not in logs


def test_sem_arquivos_de_log_nada_e_anexado(tmp_path):
    assert rl.juntar_logs(str(tmp_path)) == []
    with pytest.raises(rl.ErroRelato):
        rl.enviar("problema", "", "a@b", " ", "", True, abrir=None,
                  pasta_logs=str(tmp_path))


def test_envio_com_logs_autoriza_e_preenche_a_descricao(tmp_path):
    (tmp_path / "telezapp.log").write_bytes("registro é\n".encode("utf-8"))
    pedidos = []
    rl.enviar("sugestao", "Ana é", "a@b", "", "hoje", True,
              abrir=lambda p, tempo: pedidos.append(p) or Resposta(),
              pasta_logs=str(tmp_path))
    pedido = pedidos[0]
    corpo = pedido.data.decode("utf-8")
    assert pedido.full_url == rl.ENDERECO
    assert pedido.get_header("User-agent") == "TeleZapp/" + VERSAO
    assert pedido.get_header("Origin") is None
    assert 'name="consentimento"\r\n\r\nsim' in corpo
    assert 'name="log"; filename="telezapp.log"' in corpo
    assert "registro é" in corpo and "Ana é" in corpo
    assert rl.SEM_DESCRICAO in corpo and VERSAO in corpo
    fronteira = pedido.get_header("Content-type").split("boundary=")[1]
    assert corpo.endswith("--%s--\r\n" % fronteira)


def test_envio_sem_logs_nao_le_a_pasta_nem_pede_autorizacao(tmp_path):
    (tmp_path / "telezapp.log").write_bytes(b"registro")
    pedidos = []
    rl.enviar("duvida", "", "a@b", "minha dúvida", "", False,
              abrir=lambda p, tempo: pedidos.append(p) or Resposta(),
              pasta_logs=str(tmp_path))
    corpo = pedidos[0].data.decode("utf-8")
    assert "registro" not in corpo and "consentimento" not in corpo


def test_erro_do_recebedor_e_da_rede_viram_frase():
    def recusa(pedido, tempo):
        raise urllib.error.HTTPError(
            "u", 429, "x", {}, io.BytesIO('{"erro": "Muitos envios."}'.encode()))

    def sem_rede(pedido, tempo):
        raise urllib.error.URLError("sem rede")
    with pytest.raises(rl.ErroRelato, match="Muitos envios"):
        rl.enviar("problema", "", "a@b", "x", "", False, abrir=recusa)
    with pytest.raises(rl.ErroRelato, match="internet"):
        rl.enviar("problema", "", "a@b", "x", "", False, abrir=sem_rede)

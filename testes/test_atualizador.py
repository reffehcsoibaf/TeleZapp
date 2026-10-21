# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Atualizar pelo proprio programa: baixar, conferir, extrair e trocar."""
import hashlib
import io
import os
import subprocess
import time
import zipfile

import pytest

from telezapp.nucleo import atualizacao as at
from telezapp.nucleo import atualizador as au


def _zip(conteudo=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nome, dados in (conteudo or {
                "TeleZapp/TeleZapp.exe": b"novo",
                "TeleZapp/telezapp/x.txt": b"x"}).items():
            z.writestr(nome, dados)
    return buf.getvalue()


class Resp(io.BytesIO):
    def __init__(self, dados):
        super().__init__(dados)
        self.headers = {"Content-Length": str(len(dados))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _lanc(versao="2026.11.1.0"):
    nome = "TeleZapp-%s.zip" % versao
    return at.Lancamento(
        versao, "", "p", False, nome,
        "https://github.com/reffehcsoibaf/TeleZapp/releases/download/x/" + nome,
        "https://github.com/reffehcsoibaf/TeleZapp/releases/download/x/"
        + nome + ".sha256", 10)


def _abrir_de(zip_bytes, hash_texto=None):
    h = hash_texto or "%s *x.zip\n" % hashlib.sha256(zip_bytes).hexdigest()

    def abrir(url, tempo=30):
        return Resp(h.encode() if url.endswith(".sha256") else zip_bytes)
    return abrir


def test_release_com_zip_e_hash_vira_lancamento_atualizavel():
    versao = "2026.11.1.0"
    nome = "TeleZapp-%s.zip" % versao
    dados = [{"tag_name": versao, "assets": [
        {"name": nome, "browser_download_url": "https://github.com/z",
         "size": 7},
        {"name": nome + ".sha256", "browser_download_url": "https://github.com/h"}]}]
    lanc = at.mais_nova(dados)
    assert (lanc.nome_zip, lanc.url_zip, lanc.url_hash, lanc.tamanho) == (
        nome, "https://github.com/z", "https://github.com/h", 7)
    # nome fixo, o que o publicar.py passou a usar
    dados[0]["assets"] = [
        {"name": "TeleZapp.zip", "browser_download_url": "https://github.com/z2"},
        {"name": "TeleZapp.zip.sha256", "browser_download_url": "https://github.com/h2"}]
    assert at.mais_nova(dados).nome_zip == "TeleZapp.zip"
    dados[0]["assets"] = [
        {"name": nome, "browser_download_url": "https://github.com/z",
         "size": 7},
        {"name": nome + ".sha256", "browser_download_url": "https://github.com/h"}]
    # sem o .sha256, nao atualiza sozinho
    del dados[0]["assets"][1]
    assert at.mais_nova(dados).url_zip == ""


def test_baixar_confere_o_hash(tmp_path):
    dados = _zip()
    caminho = au.baixar(_lanc(), str(tmp_path), abrir=_abrir_de(dados))
    assert open(caminho, "rb").read() == dados
    with pytest.raises(au.ErroAtualizacao):
        au.baixar(_lanc(), str(tmp_path), abrir=_abrir_de(
            dados, "0" * 64 + " *x\n"))
    assert not os.path.exists(caminho)
    with pytest.raises(au.ErroAtualizacao):
        au.baixar(_lanc(), str(tmp_path), abrir=_abrir_de(dados, "lixo"))


def test_baixar_recusa_endereco_que_nao_e_do_github(tmp_path):
    lanc = _lanc()
    lanc.url_zip = "https://exemplo.com/a.zip"
    with pytest.raises(au.ErroAtualizacao):
        au.baixar(lanc, str(tmp_path), abrir=_abrir_de(_zip()))
    lanc.url_zip = "http://github.com/a.zip"
    with pytest.raises(au.ErroAtualizacao):
        au.baixar(lanc, str(tmp_path), abrir=_abrir_de(_zip()))


def test_extrair_valida_o_conteudo(tmp_path):
    z = tmp_path / "a.zip"
    z.write_bytes(_zip())
    nova = au.extrair(str(z), str(tmp_path / "espera"))
    assert os.path.isfile(os.path.join(nova, "TeleZapp.exe"))
    z.write_bytes(_zip({"TeleZapp/outro.txt": b"x"}))
    with pytest.raises(au.ErroAtualizacao):
        au.extrair(str(z), str(tmp_path / "espera"))
    z.write_bytes(_zip({"TeleZapp/TeleZapp.exe": b"x",
                        "../fora.txt": b"x"}))
    with pytest.raises(au.ErroAtualizacao):
        au.extrair(str(z), str(tmp_path / "espera"))


def test_script_troca_a_pasta_e_mantem_os_dados(tmp_path):
    if os.name != "nt":
        pytest.skip("script do Windows")
    prog = tmp_path / "TeleZapp"
    (prog / "dados").mkdir(parents=True)
    (prog / "dados" / "conta.db").write_text("meus dados")
    (prog / "instalado.txt").write_text("sim")
    (prog / "TeleZapp.cmd").write_text("@echo velho")
    (prog / "so-na-velha.txt").write_text("x")
    espera = tmp_path / "TeleZapp.atualizacao"
    nova = espera / "TeleZapp"
    nova.mkdir(parents=True)
    # o "executavel" da nova grava um sinal para provar que foi aberto
    (nova / "TeleZapp.cmd").write_text(
        '@echo aberto> "%s"' % (tmp_path / "sinal.txt"))
    script = au.aplicar(str(prog), str(nova), executavel="TeleZapp.cmd")
    assert os.path.isfile(script)
    for _ in range(100):
        if (tmp_path / "sinal.txt").exists():
            break
        time.sleep(0.2)
    assert (tmp_path / "sinal.txt").exists()
    assert (prog / "dados" / "conta.db").read_text() == "meus dados"
    assert (prog / "instalado.txt").exists()
    assert not (prog / "so-na-velha.txt").exists()
    assert (prog / "TeleZapp.cmd").read_text().startswith("@echo aberto")
    time.sleep(0.5)
    au.limpar_restos(str(prog))
    assert not espera.exists() and not (tmp_path / "TeleZapp.antiga").exists()


def test_baixar_pode_ser_cancelado_e_apaga_o_parcial(tmp_path):
    dados = _zip({"TeleZapp/TeleZapp.exe": b"x" * (3 << 20)})
    chamadas = []

    def cancelado():
        chamadas.append(1)
        return len(chamadas) >= 2           # desiste no segundo pedaco
    with pytest.raises(au.ErroAtualizacao) as e:
        au.baixar(_lanc(), str(tmp_path), abrir=_abrir_de(dados),
                  cancelado=cancelado)
    assert "cancelada" in str(e.value)
    assert not os.path.exists(tmp_path / "TeleZapp.zip")


def test_extrair_informa_o_avanco(tmp_path):
    z = tmp_path / "a.zip"
    z.write_bytes(_zip())
    vistos = []
    au.extrair(str(z), str(tmp_path / "espera"),
               lambda feito, total: vistos.append((feito, total)))
    assert vistos[-1][0] == vistos[-1][1] == 2 and len(vistos) == 2

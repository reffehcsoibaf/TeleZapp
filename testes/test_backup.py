# SPDX-License-Identifier: GPL-3.0-or-later
"""Backup e restauracao: partes, senha, troca na proxima abertura."""
import json
import os
import sqlite3

import pyzipper
import pytest

from telezapp import config
from telezapp.nucleo import backup as bk


def preparar(pasta):
    os.makedirs(pasta / "sessoes")
    os.makedirs(pasta / "midias" / "w1")
    (pasta / "midias" / "w1" / "a.jpg").write_bytes(b"JPG")
    (pasta / "sessoes" / "whatsapp-1.db").write_bytes(b"nao e sqlite")
    con = sqlite3.connect(str(pasta / "telezapp.db"))
    con.execute("CREATE TABLE midias (caminho TEXT)")
    con.execute("INSERT INTO midias VALUES (?)",
                (str(pasta / "midias" / "w1" / "a.jpg"),))
    con.commit()
    con.close()
    return {"status_no_titulo": False, "estilo": 3, "contas": [{"id": "w1"}],
            "telegram_api_id": 7, "codigo_trancadas": "hash",
            "trancadas_exigir_codigo": True, "depuracao": True,
            "pasta_anexos": "C:\nao-leva"}


def test_so_as_opcoes_seguras_vao_no_backup():
    dados = bk.opcoes_do_backup({"status_no_titulo": False, "depuracao": True,
                                 "trancadas_exigir_codigo": False,
                                 "contas": [1], "pasta_anexos": "x"})
    assert dados["status_no_titulo"] is False
    assert "depuracao" not in dados and "trancadas_exigir_codigo" not in dados
    assert "contas" not in dados and "pasta_anexos" not in dados


def test_opcoes_validas_descarta_lixo_e_valores_fora_da_faixa():
    boas = bk.opcoes_validas({"status_no_titulo": "sim", "estilo": 2, "inexistente": 1,
                              "mensagens_por_conversa": 10 ** 9,
                              "depuracao": True, "audio_velocidade": 1.5})
    assert boas == {"estilo": 2, "audio_velocidade": 1.5}


def test_backup_com_senha_restaura_configuracoes_e_deixa_o_resto_em_espera(
        tmp_path):
    origem = tmp_path / "a"
    cfg = preparar(origem)
    arquivo = str(tmp_path / "b.zip")
    resumo = bk.criar(arquivo, str(origem), cfg,
                      ["configuracoes", "contas", "conversas", "midias"],
                      senha="segredo")
    assert resumo == {"configuracoes": 1, "contas": 1, "conversas": 1,
                      "midias": 1}
    assert bk.precisa_de_senha(arquivo)
    with pytest.raises(bk.ErroBackup):
        bk.ler_manifesto(arquivo)                     # sem senha
    with pytest.raises(bk.ErroBackup):
        bk.ler_manifesto(arquivo, "errada")
    assert bk.ler_manifesto(arquivo, "segredo").partes == [
        "configuracoes", "contas", "conversas", "midias"]

    destino = tmp_path / "b"
    os.makedirs(destino / "sessoes")
    (destino / "sessoes" / "velha.db").write_bytes(b"v")
    (destino / "config.json").write_text(json.dumps(
        {"contas": [], "status_no_titulo": True}), encoding="utf-8")
    opcoes, espera = bk.restaurar(arquivo, "segredo",
                                  ["configuracoes", "contas", "conversas",
                                   "midias"], str(destino))
    assert opcoes["status_no_titulo"] is False and opcoes["estilo"] == 3
    assert "depuracao" not in opcoes
    assert espera == ["contas", "conversas", "midias"]
    assert bk.ha_pendente(str(destino))
    trocadas = bk.aplicar_pendente(str(destino))
    assert trocadas == ["contas", "conversas", "midias"]
    assert not bk.ha_pendente(str(destino))
    novo = json.loads((destino / "config.json").read_text(encoding="utf-8"))
    assert novo["contas"] == [{"id": "w1"}] and novo["codigo_trancadas"] == "hash"
    assert novo["status_no_titulo"] is True            # as opcoes se aplicam a parte
    assert (destino / "sessoes" / "whatsapp-1.db").exists()
    assert not (destino / "sessoes" / "velha.db").exists()
    assert (destino / "midias" / "w1" / "a.jpg").read_bytes() == b"JPG"
    antes = os.listdir(destino / bk.ANTES)
    assert len(antes) == 1
    assert (destino / bk.ANTES / antes[0] / "sessoes" / "velha.db").exists()
    con = sqlite3.connect(str(destino / "telezapp.db"))
    caminho = con.execute("SELECT caminho FROM midias").fetchone()[0]
    con.close()
    assert caminho == str(destino / "midias" / "w1" / "a.jpg")


def test_backup_sem_senha_e_so_configuracoes(tmp_path):
    origem = tmp_path / "a"
    cfg = preparar(origem)
    arquivo = str(tmp_path / "b.zip")
    bk.criar(arquivo, str(origem), cfg, ["configuracoes"])
    assert not bk.precisa_de_senha(arquivo)
    opcoes, espera = bk.restaurar(arquivo, "", ["configuracoes", "midias"],
                                  str(tmp_path / "b"))
    assert opcoes["estilo"] == 3 and espera == []
    assert not bk.ha_pendente(str(tmp_path / "b"))


def test_arquivo_que_nao_e_backup_e_recusado(tmp_path):
    lixo = tmp_path / "x.zip"
    lixo.write_bytes(b"nao e zip")
    with pytest.raises(bk.ErroBackup):
        bk.ler_manifesto(str(lixo))
    with pytest.raises(bk.ErroBackup):
        bk.criar(str(tmp_path / "y.zip"), str(tmp_path), {}, [])


def test_backup_usa_a_copia_consistente_do_banco(tmp_path):
    from telezapp.armazenamento.banco import Banco
    from telezapp.nucleo import modelos as m
    origem = tmp_path / "a"
    os.makedirs(origem)
    banco = Banco(str(origem / "telezapp.db"))
    banco.salvar_mensagens([m.Mensagem("t1", "1", "1", texto="oi")])
    arquivo = str(tmp_path / "b.zip")
    bk.criar(arquivo, str(origem), {}, ["conversas"],
             copiar_banco=banco.copiar_para)
    bk.restaurar(arquivo, "", ["conversas"], str(tmp_path / "b"))
    bk.aplicar_pendente(str(tmp_path / "b"))
    copia = Banco(str(tmp_path / "b" / "telezapp.db"))
    assert [x.texto for x in copia.mensagens("t1", "1")] == ["oi"]
    copia.fechar()
    banco.fechar()


def test_backup_leva_a_ordem_dos_provedores_de_ia_mas_nunca_as_chaves():
    dados = bk.opcoes_do_backup({
        "ia_ordem": {"audio": ["groq", "openai"]},
        "ia_modelos": {"gemini": "gemini-x"}, "ia_chaves": {"x": "segredo"}})
    assert dados["ia_ordem"] == {"audio": ["groq", "openai"]}
    assert dados["ia_modelos"] == {"gemini": "gemini-x"}
    assert "ia_chaves" not in dados and "segredo" not in str(dados)
    boas = bk.opcoes_validas({
        "ia_ordem": {"audio": ["groq", "inexistente"], "tarefa-falsa": ["groq"],
                     "pdf": "nao-e-lista"},
        "ia_modelos": {"gemini": "m", "inexistente": "x", "claude": 5}})
    assert boas["ia_ordem"] == {"audio": ["groq"]}
    assert boas["ia_modelos"] == {"gemini": "m"}


def _cofre(pasta):
    from telezapp.nucleo.ia.cofre import Cofre
    os.makedirs(str(pasta), exist_ok=True)
    return Cofre(os.path.join(str(pasta), "ia_chaves.json"))


def test_chaves_de_ia_so_vao_em_backup_com_senha(tmp_path):
    origem = tmp_path / "a"
    cfg = preparar(origem)
    _cofre(origem).guardar("groq", "chave-secreta-groq")
    _cofre(origem).guardar("gemini", "chave-gemini")
    # sem senha: ficam de fora (o zip seria legivel)
    sem = str(tmp_path / "sem.zip")
    resumo = bk.criar(sem, str(origem), cfg, ["configuracoes"])
    assert "ia_chaves" not in resumo
    with pyzipper.AESZipFile(sem) as z:
        assert bk.CHAVES_IA not in z.namelist()
    # com senha: vao, cifradas no zip
    com = str(tmp_path / "com.zip")
    resumo = bk.criar(com, str(origem), cfg, ["configuracoes"], "segredo")
    assert resumo["ia_chaves"] == 2
    with pyzipper.AESZipFile(com) as z:
        with pytest.raises(RuntimeError):
            z.read(bk.CHAVES_IA)                       # sem a senha
    assert b"chave-secreta-groq" not in open(com, "rb").read()
    # restaurar em outra pasta: as chaves voltam ao cofre
    destino = tmp_path / "b"
    extra = {}
    bk.restaurar(com, "segredo", ["configuracoes"], str(destino), extra)
    assert extra == {"ia_chaves": 2}
    cofre = _cofre(destino)
    assert cofre.obter("groq") == "chave-secreta-groq"
    assert cofre.obter("gemini") == "chave-gemini"
    # sem escolher configuracoes, as chaves nao voltam
    outro = tmp_path / "c"
    extra = {}
    bk.restaurar(com, "segredo", ["conversas"], str(outro), extra)
    assert extra == {} and not _cofre(outro).provedores_com_chave()
    # chave de provedor desconhecido ou vazia no arquivo e ignorada
    ruim = str(tmp_path / "ruim.zip")
    with pyzipper.AESZipFile(ruim, "w") as z:
        z.setpassword(b"s")
        z.setencryption(pyzipper.WZ_AES, nbits=256)
        z.writestr(bk.MANIFESTO, json.dumps(
            {"versao": "x", "data": 1, "partes": ["configuracoes"]}))
        z.writestr("configuracoes.json", json.dumps({"opcoes": {}}))
        z.writestr(bk.CHAVES_IA, json.dumps(
            {"groq": "ok", "inventado": "x", "gemini": " "}))
    extra = {}
    bk.restaurar(ruim, "s", ["configuracoes"], str(tmp_path / "d"), extra)
    assert extra == {"ia_chaves": 1}


def test_backup_e_restauracao_informam_o_avanco(tmp_path):
    origem = tmp_path / "a"
    cfg = preparar(origem)
    for i in range(5):
        (origem / "midias" / "w1" / ("f%d.jpg" % i)).write_bytes(b"x" * 10)
    arquivo = str(tmp_path / "b.zip")
    vistos = []
    bk.criar(arquivo, str(origem), cfg,
             ["configuracoes", "contas", "conversas", "midias"], "senha",
             progresso=lambda pct, texto="": vistos.append((pct, texto)))
    pcts = [p for p, _ in vistos]
    assert pcts == sorted(pcts) and pcts[-1] == 100
    assert all(0 <= p <= 100 for p in pcts) and len(set(pcts)) > 3
    assert "Copiando as mídias" in {t for _, t in vistos}
    # restaurar tambem informa
    vistos.clear()
    bk.restaurar(arquivo, "senha", ["contas", "conversas", "midias"],
                 str(tmp_path / "c"),
                 progresso=lambda pct, texto="": vistos.append(pct))
    assert vistos == sorted(vistos) and vistos[-1] >= 90

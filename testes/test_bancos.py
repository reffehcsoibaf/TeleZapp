# SPDX-License-Identifier: GPL-3.0-or-later
"""Os lugares onde os dados das contas ficam: a fachada Bancos, com uma
pasta (e um banco) por conta, o banco unico do layout antigo, as passagens
entre os dois (migrar) e a copia para a pasta escolhida."""
import hashlib
import os
import shutil
import sqlite3

import pytest

from telezapp import config
from telezapp.armazenamento.banco import Banco
from telezapp.armazenamento.bancos import Bancos
from telezapp.midia import armazem
from telezapp.nucleo import backup
from telezapp.nucleo import migracao
from telezapp.nucleo import modelos as m


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path / "dados"))
    c = config.Config()
    monkeypatch.setattr(config, "_cfg_de_contas", c)
    return c


# ------------------------------------------------------------------ Bancos
def test_cada_conta_tem_o_seu_banco(cfg):
    b = Bancos(cfg)
    b.salvar_mensagens([m.Mensagem("t1", "1", "1", texto="oi", data=1),
                        m.Mensagem("t2", "1", "1", texto="ola", data=1)])
    db1 = os.path.join(config.pasta_da_conta("t1"), "conversas.db")
    db2 = os.path.join(config.pasta_da_conta("t2"), "conversas.db")
    assert os.path.isfile(db1) and os.path.isfile(db2) and db1 != db2
    assert [x.texto for x in b.mensagens("t1", "1")] == ["oi"]
    assert [x.texto for x in b.mensagens("t2", "1")] == ["ola"]
    assert set(b.ultimas_mensagens()) == {("t1", "1"), ("t2", "1")}
    b.fechar()


def test_listas_globais_juntam_todas_as_contas(cfg):
    b = Bancos(cfg)
    b.salvar_conversas([m.Conversa("t1", "1", "A", "telegram"),
                        m.Conversa("t2", "1", "B", "telegram")])
    b.salvar_mensagens([m.Mensagem("t1", "1", "2", texto="z", data=5),
                        m.Mensagem("t2", "1", "1", texto="a", data=9)])
    assert [x.conta_id for x, _ in b.buscar_mensagens()] == ["t2", "t1"]
    assert [x.conta_id for x, _ in b.buscar_mensagens(
        mais_antigas_primeiro=True)] == ["t1", "t2"]
    assert b.contar_mensagens(m.TEXTO) == 2
    assert b.mensagens_expiradas() == []
    b.fechar()


def test_grupos_por_conta_sao_despachados(cfg):
    b = Bancos(cfg)
    b.salvar_fichas([("t1", "c", "1", b"f1"), ("t2", "c", "1", b"f2")])
    assert b.ficha("t1", "c", "1") == b"f1"
    assert b.ficha("t2", "c", "1") == b"f2"
    b.registrar_limpeza([("t1", "c", "1")], "midia")
    assert b.foi_limpa("t1", "c", "1") == "midia"
    assert b.foi_limpa("t2", "c", "1") is None
    b.apagar_fichas([("t1", "c", "1")])
    assert b.ficha("t1", "c", "1") is None
    b.fechar()


def test_agendadas_por_numero_e_por_conta(cfg):
    b = Bancos(cfg)
    id1 = b.guardar_agendada("t1", "c", "a", 100)
    id2 = b.guardar_agendada("t2", "c", "b", 200)
    assert id1 == id2               # a sequencia e por conta: se repetem
    assert b.agendada(id1, "t1")["conta_id"] == "t1"
    assert b.agendada(id2, "t2")["conta_id"] == "t2"
    b.fechar()


def test_apagar_conta_fecha_e_apaga_o_banco(cfg):
    b = Bancos(cfg)
    b.salvar_mensagens([m.Mensagem("t1", "1", "1", texto="oi", data=1)])
    db1 = os.path.join(config.pasta_da_conta("t1"), "conversas.db")
    b.apagar_conta("t1")
    assert not os.path.isfile(db1)
    b.fechar()


def test_depuracao_e_repassada_as_contas(cfg):
    b = Bancos(cfg)
    b.depuracao = True
    b.guardar_depuracao("t1", "c", "1", "dados")
    assert b.depuracao_de("t1", "c", "1") == "dados"
    b.limpar_depuracao()
    assert b.depuracao_de("t1", "c", "1") == ""
    b.fechar()


# ---------------------------------------------------- o banco unico (antigo)
def test_sem_separacao_tudo_no_banco_unico(cfg):
    """Com contas_em_pastas desmarcada, todas as contas dividem o mesmo
    banco (telezapp.db), as sessoes e as midias."""
    cfg.set("contas_em_pastas", False)
    b = Bancos(cfg)
    b.salvar_mensagens([m.Mensagem("t1", "1", "1", texto="oi", data=1),
                        m.Mensagem("t2", "1", "1", texto="ola", data=1)])
    assert config.contas_separadas() is False
    unico = os.path.join(config.pasta_dados(), "telezapp.db")
    assert os.path.isfile(unico)
    assert not os.path.exists(os.path.join(config.pasta_dados(), "contas"))
    assert [x.texto for x in b.mensagens("t1", "1")] == ["oi"]
    assert [x.texto for x in b.mensagens("t2", "1")] == ["ola"]
    assert set(b.ultimas_mensagens()) == {("t1", "1"), ("t2", "1")}
    assert b.contar_mensagens(m.TEXTO) == 2
    assert config.pasta_sessoes("t1") == os.path.join(
        config.pasta_dados(), "sessoes")
    assert armazem.pasta_midias("t1") == os.path.join(
        config.pasta_dados(), "midias")
    # apagar a conta tira so as linhas dela (o banco unico fica)
    b.apagar_conta("t1")
    assert os.path.isfile(unico)
    assert b.contar_mensagens(m.TEXTO) == 1
    b.fechar()


def test_sem_separacao_as_listas_globais_nao_duplicam(cfg):
    cfg.set("contas_em_pastas", False)
    b = Bancos(cfg)
    b.salvar_conversas([m.Conversa("t1", "1", "A", "telegram")])
    b.salvar_mensagens([m.Mensagem("t1", "1", "1", texto="oi", data=1)])
    assert [x.conta_id for x, _ in b.buscar_mensagens()] == ["t1"]
    assert list(b.todas_midias()) == []
    assert b.favoritas() == set()
    assert b.conversas_com_favoritas() == set()
    b.fechar()


# -------------------------------------------------------------- pasta da conta
def test_pasta_personalizada_das_contas(cfg, tmp_path):
    escolhida = str(tmp_path / "escolhida")
    cfg.set("contas_pasta_personalizada", True)
    cfg.set("contas_pasta", escolhida)
    assert config.pasta_da_conta("t1") == os.path.join(escolhida, "t1")
    assert config.pasta_da_conta("t2") == os.path.join(escolhida, "t2")
    assert armazem.pasta_midias("t1") == os.path.join(escolhida, "t1",
                                                      "midias")
    cfg.set("contas_pasta_personalizada", False)
    assert config.pasta_da_conta("t1") == os.path.join(
        config.pasta(), "contas", "t1")      # desmarcada: a padrao
    cfg.set("contas_pasta_personalizada", True)
    cfg.set("contas_pasta", "")              # marcada, sem pasta: a padrao
    assert config.pasta_da_conta("t1") == os.path.join(
        config.pasta(), "contas", "t1")


def test_preparar_e_limpar_a_pasta(cfg):
    assert config.preparar_pasta_da_conta("t1")
    assert os.path.isdir(os.path.join(config.pasta_da_conta("t1"),
                                      "sessoes"))
    config.limpar_pasta_da_conta("t1")
    assert not os.path.exists(config.pasta_da_conta("t1"))


def test_acertar_caminhos_pela_conexao_aberta(cfg):
    """A troca de caminhos das midias roda na conexao ja aberta do banco
    (sem abrir o arquivo de novo) e tambem pelo arquivo."""
    arquivo = os.path.join(config.pasta(), "outro.db")
    b = Banco(arquivo)
    b.salvar_mensagens([m.Mensagem("t1", "1", "1", texto="oi", data=1)])
    b.registrar_midia("t1", "1", "1", m.FOTO, "c\\antigo\\1\\a.jpg",
                      3, 1.0)
    backup._acertar_caminhos_das_midias(arquivo, "c\\antigo", "c\\novo",
                                        con=b._con)
    assert b.midia("t1", "1", "1")[0].startswith("c\\novo")
    b.fechar()
    backup._acertar_caminhos_das_midias(arquivo, "c\\novo", "c\\outro")
    b2 = Banco(arquivo)
    assert b2.midia("t1", "1", "1")[0].startswith("c\\outro")
    b2.fechar()


# ------------------------------------------------------------------ migracao
def test_migracao_do_layout_antigo(cfg):
    cfg.salvar_conta({"id": "t1", "servico": "telegram", "nome": "Um"})
    cfg.salvar_conta({"id": "t2", "servico": "telegram", "nome": "Dois"})
    raiz = config.pasta()
    antigo = Banco(os.path.join(raiz, "telezapp.db"))
    antigo.salvar_conversas([m.Conversa("t1", "1", "A", "telegram"),
                             m.Conversa("t2", "1", "B", "telegram")])
    antigo.salvar_mensagens([m.Mensagem("t1", "1", "9", texto="guardada",
                                        data=1)])
    pasta_midia = os.path.join(raiz, "midias", "t1", "abc")
    os.makedirs(pasta_midia)
    arquivo_midia = os.path.join(pasta_midia, "f.jpg")
    open(arquivo_midia, "wb").write(b"JPG")
    antigo.registrar_midia("t1", "1", "9", m.FOTO, arquivo_midia, 3, 1.0)
    os.makedirs(os.path.join(raiz, "sessoes"))
    open(os.path.join(raiz, "sessoes", "t1.session"), "wb").write(b"s")
    antigo.fechar()
    assert migracao.migrar(cfg) == 2
    # o banco antigo ficou guardado com outro nome
    assert not os.path.exists(os.path.join(raiz, "telezapp.db"))
    assert os.path.isfile(os.path.join(
        raiz, "telezapp.db.antes-da-migracao"))
    db1 = os.path.join(config.pasta_da_conta("t1"), "conversas.db")
    b1 = Banco(db1)
    assert [x.texto for x in b1.mensagens("t1", "1")] == ["guardada"]
    assert b1.conversas("t2") == []     # a conta t2 tem o banco dela
    assert os.path.isfile(os.path.join(config.pasta_da_conta("t1"),
                                       "sessoes", "t1.session"))
    caminho = b1.midia("t1", "1", "9")[0]
    assert os.path.isfile(caminho)
    assert caminho.startswith(os.path.join(config.pasta_da_conta("t1"),
                                           "midias"))
    b1.fechar()
    assert not os.path.exists(os.path.join(raiz, "midias", "t1"))
    assert migracao.migrar(cfg) == 0    # nao mexe de novo


def test_migracao_retomada_acerta_os_caminhos_das_midias(cfg):
    """A migracao pode falhar depois de copiar as linhas (o arquivo novo
    ficava inacessivel por um instante); retomar acerta os caminhos das
    midias, mesmo com o banco da conta ja existindo."""
    cfg.salvar_conta({"id": "t1", "servico": "telegram"})
    raiz = config.pasta()
    antigo = Banco(os.path.join(raiz, "telezapp.db"))
    pasta_midia = os.path.join(raiz, "midias", "t1", "abc")
    os.makedirs(pasta_midia)
    arquivo_midia = os.path.join(pasta_midia, "f.jpg")
    open(arquivo_midia, "wb").write(b"JPG")
    antigo.registrar_midia("t1", "1", "9", m.FOTO, arquivo_midia, 3, 1.0)
    antigo.fechar()
    # o estado de uma migracao interrompida depois da copia: as linhas ja
    # estao no banco da conta, as midias ja foram levadas para a pasta
    # dela, e os caminhos ainda apontam para o lugar antigo
    pasta = config.pasta_da_conta("t1")
    shutil.copytree(os.path.join(raiz, "midias", "t1"),
                    os.path.join(pasta, "midias"))
    shutil.rmtree(os.path.join(raiz, "midias", "t1"))
    origem = Banco(os.path.join(raiz, "telezapp.db"))
    novo = Banco(os.path.join(pasta, "conversas.db"))
    novo.copiar_conta_de("t1", origem)
    origem.fechar()
    novo.fechar()
    # a retomada: nao conta de novo (o banco ja tinha), mas acerta os
    # caminhos e aposenta o banco antigo
    assert migracao.migrar(cfg) == 0
    b = Banco(os.path.join(pasta, "conversas.db"))
    caminho = b.midia("t1", "1", "9")[0]
    assert caminho.startswith(os.path.join(pasta, "midias"))
    assert os.path.isfile(caminho)
    b.fechar()
    assert not os.path.exists(os.path.join(raiz, "telezapp.db"))


def test_migracao_guarda_o_banco_antigo_com_outro_nome_quando_ja_ha(cfg):
    """Ja existindo a copia de seguranca (de uma migracao anterior), o
    banco antigo leva um numero no nome, em vez de ficar no lugar (e a
    migracao recomecar em toda abertura)."""
    cfg.salvar_conta({"id": "t1", "servico": "telegram"})
    raiz = config.pasta()
    antigo = Banco(os.path.join(raiz, "telezapp.db"))
    antigo.salvar_conversas([m.Conversa("t1", "1", "A", "telegram")])
    antigo.fechar()
    open(os.path.join(raiz, "telezapp.db.antes-da-migracao"),
         "wb").write(b"x")
    assert migracao.migrar(cfg) == 1
    assert not os.path.exists(os.path.join(raiz, "telezapp.db"))
    assert os.path.isfile(os.path.join(
        raiz, "telezapp.db.antes-da-migracao-2"))


def test_migracao_sem_banco_antigo_nao_faz_nada(cfg):
    assert migracao.migrar(cfg) == 0
    assert not os.path.exists(os.path.join(config.pasta(), "contas"))


def test_migracao_leva_para_a_pasta_escolhida(cfg, tmp_path):
    """Com a pasta das contas personalizada, o que esta na pasta padrao
    vai para a escolhida na abertura."""
    cfg.salvar_conta({"id": "t1", "servico": "telegram"})
    b = Bancos(cfg)
    b.salvar_mensagens([m.Mensagem("t1", "1", "1", texto="oi", data=1)])
    b.registrar_midia("t1", "1", "1", m.FOTO,
                      os.path.join(armazem.pasta_da_conversa("t1", "1"),
                                   "a.jpg"), 3, 1.0)
    b.fechar()
    padrao = config.pasta_da_conta("t1")      # a de antes, a padrao
    cfg.set("contas_pasta_personalizada", True)
    cfg.set("contas_pasta", str(tmp_path / "escolhida"))
    assert migracao.migrar(cfg) == 1
    destino = os.path.join(str(tmp_path / "escolhida"), "t1")
    assert os.path.isfile(os.path.join(destino, "conversas.db"))
    assert not os.path.exists(padrao)
    b2 = Bancos(cfg)
    assert [x.texto for x in b2.mensagens("t1", "1")] == ["oi"]
    assert b2.midia("t1", "1", "1")[0].startswith(destino)
    b2.fechar()
    assert migracao.migrar(cfg) == 0    # tudo ja esta no lugar


def test_migracao_acerta_caminhos_quando_a_origem_ja_foi_embora(
        cfg, tmp_path):
    """Se uma abertura anterior levou a pasta mas nao conseguiu acertar os
    caminhos (a origem nao existe mais), a abertura seguinte acerta."""
    cfg.salvar_conta({"id": "t1", "servico": "telegram"})
    b = Bancos(cfg)
    b.salvar_mensagens([m.Mensagem("t1", "1", "1", texto="oi", data=1)])
    arquivo = os.path.join(armazem.pasta_da_conversa("t1", "1"), "a.jpg")
    open(arquivo, "wb").write(b"JPG")
    b.registrar_midia("t1", "1", "1", m.FOTO, arquivo, 3, 1.0)
    b.fechar()
    padrao = config.pasta_da_conta("t1")
    escolhida = str(tmp_path / "escolhida")
    destino = os.path.join(escolhida, "t1")
    shutil.copytree(padrao, destino)        # como uma copia que ficou
    shutil.rmtree(padrao)                   # e a origem ja foi apagada
    cfg.set("contas_pasta_personalizada", True)
    cfg.set("contas_pasta", escolhida)
    assert migracao.migrar(cfg) == 0        # nada a mover: so acertar
    b2 = Bancos(cfg)
    caminho = b2.midia("t1", "1", "1")[0]
    assert caminho.startswith(os.path.join(destino, "midias"))
    assert os.path.isfile(caminho)
    b2.fechar()


def test_migracao_para_a_pasta_escolhida_espera_o_banco_soltar(
        cfg, tmp_path, monkeypatch):
    """Se o banco recem-copiado nao abre para escrita, a abertura nao
    cai: a origem fica (os caminhos antigos valem) e a proxima acerta."""
    cfg.salvar_conta({"id": "t1", "servico": "telegram"})
    b = Bancos(cfg)
    b.salvar_mensagens([m.Mensagem("t1", "1", "1", texto="oi", data=1)])
    arquivo = os.path.join(armazem.pasta_da_conversa("t1", "1"), "a.jpg")
    open(arquivo, "wb").write(b"JPG")
    b.registrar_midia("t1", "1", "1", m.FOTO, arquivo, 3, 1.0)
    b.fechar()
    padrao = config.pasta_da_conta("t1")
    escolhida = str(tmp_path / "escolhida")
    destino = os.path.join(escolhida, "t1")
    cfg.set("contas_pasta_personalizada", True)
    cfg.set("contas_pasta", escolhida)
    real = migracao._acertar_caminhos_da_pasta

    def sem_abrir(*a, **k):
        raise sqlite3.OperationalError("unable to open database file")
    monkeypatch.setattr(migracao, "_acertar_caminhos_da_pasta", sem_abrir)
    assert migracao.migrar(cfg) == 1
    assert os.path.isdir(padrao)                       # a origem ficou
    assert os.path.isfile(os.path.join(destino, "conversas.db"))
    b2 = Bancos(cfg)                     # o app abre mesmo assim
    caminho = b2.midia("t1", "1", "1")[0]
    assert caminho.startswith(padrao)                  # e a midia vale
    assert os.path.isfile(caminho)
    b2.fechar()
    monkeypatch.setattr(migracao, "_acertar_caminhos_da_pasta", real)
    assert migracao.migrar(cfg) == 1                   # o que sobrou vai
    assert not os.path.exists(padrao)
    b3 = Bancos(cfg)
    caminho = b3.midia("t1", "1", "1")[0]
    assert caminho.startswith(os.path.join(destino, "midias"))
    assert os.path.isfile(caminho)
    b3.fechar()


def test_migrar_para_as_pastas_nao_cai_quando_a_troca_falha(
        cfg, monkeypatch):
    """Se a troca dos caminhos falhar na ida para as pastas, a abertura nao
    cai: as midias ficam na raiz (os caminhos antigos valem) e a proxima
    abertura termina."""
    cfg.salvar_conta({"id": "t1", "servico": "telegram"})
    cfg.set("contas_em_pastas", False)      # comeca no banco unico
    b = Bancos(cfg)
    b.salvar_mensagens([m.Mensagem("t1", "1", "1", texto="oi", data=1)])
    # midias de um layout antigo (as novas vao direto em <dados>\\midias)
    na_raiz = os.path.join(config.pasta(), "midias", "t1")
    os.makedirs(na_raiz)
    arquivo = os.path.join(na_raiz, "a.jpg")
    open(arquivo, "wb").write(b"JPG")
    b.registrar_midia("t1", "1", "1", m.FOTO, arquivo, 3, 1.0)
    b.fechar()
    cfg.set("contas_em_pastas", True)
    real = backup._acertar_caminhos_das_midias

    def sem_escrever(*a, **k):
        raise sqlite3.OperationalError("unable to open database file")
    monkeypatch.setattr(backup, "_acertar_caminhos_das_midias", sem_escrever)
    assert migracao.migrar(cfg) == 0
    assert os.path.isdir(na_raiz)              # as midias nao se mexeram
    assert os.path.isfile(os.path.join(config.pasta(), "telezapp.db"))
    b2 = Bancos(cfg)                           # o app abre mesmo assim
    caminho = b2.midia("t1", "1", "1")[0]
    assert caminho.startswith(na_raiz)         # e a midia vale
    assert os.path.isfile(caminho)
    b2.fechar()
    monkeypatch.setattr(backup, "_acertar_caminhos_das_midias", real)
    migracao.migrar(cfg)                       # a proxima abertura termina
    assert not os.path.exists(na_raiz)
    b3 = Bancos(cfg)
    caminho = b3.midia("t1", "1", "1")[0]
    assert caminho.startswith(config.pasta_da_conta("t1"))
    assert os.path.isfile(caminho)
    b3.fechar()


def test_voltar_ao_banco_unico_nao_cai_quando_a_troca_falha(cfg, monkeypatch):
    """Se a troca dos caminhos falhar na volta ao banco unico, a abertura
    nao cai: a pasta da conta fica (os caminhos antigos valem) e a proxima
    abertura termina."""
    cfg.salvar_conta({"id": "t1", "servico": "telegram"})
    b = Bancos(cfg)
    b.salvar_mensagens([m.Mensagem("t1", "1", "1", texto="oi", data=1)])
    arquivo = os.path.join(armazem.pasta_da_conversa("t1", "1"), "a.jpg")
    open(arquivo, "wb").write(b"JPG")
    b.registrar_midia("t1", "1", "1", m.FOTO, arquivo, 3, 1.0)
    b.fechar()
    pasta = config.pasta_da_conta("t1")
    cfg.set("contas_em_pastas", False)
    real = backup._acertar_caminhos_das_midias

    def sem_escrever(*a, **k):
        raise sqlite3.OperationalError("unable to open database file")
    monkeypatch.setattr(backup, "_acertar_caminhos_das_midias", sem_escrever)
    assert migracao.migrar(cfg) == 0
    assert os.path.isdir(pasta)                # a pasta da conta fica
    b2 = Bancos(cfg)                           # o app abre mesmo assim
    caminho = b2.midia("t1", "1", "1")[0]
    assert caminho.startswith(pasta)           # e a midia vale
    assert os.path.isfile(caminho)
    b2.fechar()
    monkeypatch.setattr(backup, "_acertar_caminhos_das_midias", real)
    assert migracao.migrar(cfg) == 1           # a proxima abertura termina
    assert not os.path.exists(pasta)
    b3 = Bancos(cfg)
    caminho = b3.midia("t1", "1", "1")[0]
    assert caminho.startswith(os.path.join(config.pasta(), "midias", "t1"))
    assert os.path.isfile(caminho)
    b3.fechar()


def test_voltar_ao_banco_unico_nao_cai_com_erro_inesperado(cfg, monkeypatch):
    """Um erro que nao seja da troca de caminhos tambem nao derruba a
    abertura: a pasta da conta fica para a proxima."""
    cfg.salvar_conta({"id": "t1", "servico": "telegram"})
    b = Bancos(cfg)
    b.salvar_mensagens([m.Mensagem("t1", "1", "1", texto="oi", data=1)])
    b.fechar()
    pasta = config.pasta_da_conta("t1")
    cfg.set("contas_em_pastas", False)

    def explode(*a, **k):
        raise OSError("o arquivo esta ocupado")
    monkeypatch.setattr(migracao, "_voltar_conta", explode)
    assert migracao.migrar(cfg) == 0
    assert os.path.isdir(pasta)
    b2 = Bancos(cfg)                           # o app abre mesmo assim
    b2.fechar()


def test_pasta_personalizada_no_layout_antigo(cfg, tmp_path):
    """Com a separacao desmarcada, a pasta personalizada tambem vale: o
    banco unico, as sessoes e as midias vao para a pasta escolhida, e os
    caminhos das midias sao acertados; desmarcar devolve tudo."""
    cfg.salvar_conta({"id": "t1", "servico": "telegram"})
    cfg.set("contas_em_pastas", False)
    b = Bancos(cfg)
    b.salvar_mensagens([m.Mensagem("t1", "1", "1", texto="oi", data=1)])
    raiz = config.pasta_dados()
    na_raiz = os.path.join(raiz, "midias", "t1")
    os.makedirs(na_raiz)
    arquivo = os.path.join(na_raiz, "a.jpg")
    open(arquivo, "wb").write(b"JPG")
    b.registrar_midia("t1", "1", "1", m.FOTO, arquivo, 3, 1.0)
    b.fechar()
    os.makedirs(os.path.join(raiz, "sessoes"), exist_ok=True)
    open(os.path.join(raiz, "sessoes", "t1.session"), "wb").write(b"s")
    escolhida = str(tmp_path / "escolhida")
    cfg.set("contas_pasta_personalizada", True)
    cfg.set("contas_pasta", escolhida)
    assert config.pasta_do_layout_antigo() == raiz   # o banco ainda esta la
    # enquanto a migracao nao roda, sessoes e midias seguem a raiz em uso
    assert config.pasta_sessoes("t1") == os.path.join(raiz, "sessoes")
    assert armazem.pasta_midias("t1") == os.path.join(raiz, "midias")
    assert migracao.migrar(cfg) == 0
    assert os.path.isfile(os.path.join(escolhida, "telezapp.db"))
    assert not os.path.exists(os.path.join(raiz, "telezapp.db"))
    assert not os.path.exists(na_raiz)
    assert os.path.isfile(os.path.join(escolhida, "sessoes", "t1.session"))
    assert not os.path.exists(os.path.join(raiz, "sessoes"))
    assert config.pasta_do_layout_antigo() == escolhida
    assert config.pasta_sessoes("t1") == os.path.join(escolhida, "sessoes")
    assert armazem.pasta_midias("t1") == os.path.join(escolhida, "midias")
    b2 = Bancos(cfg)             # abre o banco unico da pasta escolhida
    assert [x.texto for x in b2.mensagens("t1", "1")] == ["oi"]
    caminho = b2.midia("t1", "1", "1")[0]
    assert caminho.startswith(os.path.join(escolhida, "midias"))
    assert os.path.isfile(caminho)
    b2.fechar()
    assert migracao.migrar(cfg) == 0        # ja esta tudo no lugar

    # desmarcar a pasta personalizada devolve tudo para a pasta de dados
    cfg.set("contas_pasta_personalizada", False)
    assert migracao.migrar(cfg) == 0
    assert os.path.isfile(os.path.join(raiz, "telezapp.db"))
    assert not os.path.exists(os.path.join(escolhida, "telezapp.db"))
    assert os.path.isfile(os.path.join(raiz, "sessoes", "t1.session"))
    assert os.path.isfile(os.path.join(raiz, "midias", "t1", "a.jpg"))
    b3 = Bancos(cfg)
    caminho = b3.midia("t1", "1", "1")[0]
    assert caminho.startswith(os.path.join(raiz, "midias"))
    assert os.path.isfile(caminho)
    b3.fechar()


def test_pasta_personalizada_no_layout_antigo_nao_cai_se_a_troca_falha(
        cfg, tmp_path, monkeypatch):
    """Se a troca dos caminhos falhar ao levar o layout antigo para a
    pasta escolhida, a abertura nao cai: o banco fica na pasta de dados
    (os caminhos antigos valem) e a proxima abertura termina."""
    cfg.salvar_conta({"id": "t1", "servico": "telegram"})
    cfg.set("contas_em_pastas", False)
    b = Bancos(cfg)
    b.salvar_mensagens([m.Mensagem("t1", "1", "1", texto="oi", data=1)])
    raiz = config.pasta_dados()
    na_raiz = os.path.join(raiz, "midias", "t1")
    os.makedirs(na_raiz)
    arquivo = os.path.join(na_raiz, "a.jpg")
    open(arquivo, "wb").write(b"JPG")
    b.registrar_midia("t1", "1", "1", m.FOTO, arquivo, 3, 1.0)
    b.fechar()
    escolhida = str(tmp_path / "escolhida")
    cfg.set("contas_pasta_personalizada", True)
    cfg.set("contas_pasta", escolhida)
    real = backup._acertar_caminhos_das_midias

    def sem_escrever(*a, **k):
        raise sqlite3.OperationalError("unable to open database file")
    monkeypatch.setattr(backup, "_acertar_caminhos_das_midias", sem_escrever)
    assert migracao.migrar(cfg) == 0
    assert os.path.isfile(os.path.join(raiz, "telezapp.db"))
    assert not os.path.isfile(os.path.join(escolhida, "telezapp.db"))
    assert config.pasta_do_layout_antigo() == raiz
    b2 = Bancos(cfg)                     # o app abre mesmo assim
    caminho = b2.midia("t1", "1", "1")[0]
    assert caminho.startswith(na_raiz)              # e a midia vale
    assert os.path.isfile(caminho)
    b2.fechar()
    monkeypatch.setattr(backup, "_acertar_caminhos_das_midias", real)
    migracao.migrar(cfg)                 # a proxima abertura termina
    assert os.path.isfile(os.path.join(escolhida, "telezapp.db"))
    assert not os.path.exists(os.path.join(raiz, "telezapp.db"))
    b3 = Bancos(cfg)
    caminho = b3.midia("t1", "1", "1")[0]
    assert caminho.startswith(os.path.join(escolhida, "midias"))
    assert os.path.isfile(caminho)
    b3.fechar()


def test_desmarcar_as_duas_devolve_da_pasta_escolhida(cfg, tmp_path):
    """Desmarcar a separacao e a pasta personalizada (as duas caixas): as
    contas que estavam em pastas na pasta escolhida voltam para o layout
    antigo na pasta de dados, com o banco, as sessoes e as midias — mesmo
    com uma sessao nova sem autorizacao esperando na pasta de dados."""
    cfg.salvar_conta({"id": "t1", "servico": "telegram"})
    cfg.set("contas_em_pastas", False)
    b = Bancos(cfg)          # os dados nascem no banco unico, no antigo
    b.salvar_mensagens([m.Mensagem("t1", "1", "1", texto="oi", data=1)])
    raiz = config.pasta_dados()
    os.makedirs(os.path.join(raiz, "midias", "t1"))
    arquivo = os.path.join(raiz, "midias", "t1", "a.jpg")
    open(arquivo, "wb").write(b"JPG")
    b.registrar_midia("t1", "1", "1", m.FOTO, arquivo, 3, 1.0)
    b.fechar()
    os.makedirs(os.path.join(raiz, "sessoes"))
    open(os.path.join(raiz, "sessoes", "t1.session"), "wb").write(b"s")

    # as duas caixas marcadas: a conta vai para a pasta dela
    cfg.set("contas_em_pastas", True)
    cfg.set("contas_pasta_personalizada", True)
    escolhida = str(tmp_path / "escolhida")
    cfg.set("contas_pasta", escolhida)
    assert migracao.migrar(cfg) >= 1
    pasta = os.path.join(escolhida, "t1")
    assert os.path.isfile(os.path.join(pasta, "conversas.db"))
    assert os.path.isfile(os.path.join(pasta, "sessoes", "t1.session"))
    assert os.path.isfile(os.path.join(pasta, "midias", "a.jpg"))
    assert not os.path.exists(os.path.join(raiz, "telezapp.db"))

    # as duas caixas desmarcadas: tudo volta para a pasta de dados
    cfg.set("contas_em_pastas", False)
    cfg.set("contas_pasta_personalizada", False)
    # uma sessao nova (sem autorizacao) que a abertura bugada deixou la
    open(os.path.join(raiz, "sessoes", "t1.session"), "wb").write(b"nova")
    assert migracao.migrar(cfg) >= 1
    b2 = Bancos(cfg)
    assert [x.texto for x in b2.mensagens("t1", "1")] == ["oi"]
    caminho = b2.midia("t1", "1", "1")[0]
    assert caminho.startswith(os.path.join(raiz, "midias"))
    assert os.path.isfile(caminho)
    b2.fechar()
    assert open(os.path.join(raiz, "sessoes", "t1.session"),
                "rb").read() == b"s"
    assert os.path.isfile(os.path.join(raiz, "midias", "t1", "a.jpg"))
    assert not os.path.exists(pasta)


def test_voltar_ao_layout_antigo(cfg):
    """Com a separacao desmarcada, os dados de cada conta voltam para o
    banco unico, as sessoes comuns e as midias comuns."""
    cfg.salvar_conta({"id": "t1", "servico": "telegram"})
    b = Bancos(cfg)
    b.salvar_conversas([m.Conversa("t1", "1", "A", "telegram")])
    b.salvar_mensagens([m.Mensagem("t1", "1", "1", texto="oi", data=1)])
    arquivo = os.path.join(armazem.pasta_da_conversa("t1", "1"), "a.jpg")
    open(arquivo, "wb").write(b"JPG")
    b.registrar_midia("t1", "1", "1", m.FOTO, arquivo, 3, 1.0)
    b.fechar()
    os.makedirs(os.path.join(config.pasta_da_conta("t1"), "sessoes"))
    open(os.path.join(config.pasta_da_conta("t1"), "sessoes", "t1.session"),
         "wb").write(b"s")
    cfg.set("contas_em_pastas", False)
    raiz = config.pasta_dados()
    assert migracao.migrar(cfg) == 1
    assert os.path.isfile(os.path.join(raiz, "telezapp.db"))
    assert os.path.isfile(os.path.join(raiz, "sessoes", "t1.session"))
    sub = hashlib.sha1("1".encode("utf-8")).hexdigest()[:12]
    assert os.path.isfile(os.path.join(raiz, "midias", "t1", sub, "a.jpg"))
    # a pasta da conta foi embora (tudo conferiu)
    assert not os.path.exists(config.pasta_da_conta("t1"))
    b2 = Bancos(cfg)            # no modo unico: o banco e o mesmo
    assert [x.texto for x in b2.mensagens("t1", "1")] == ["oi"]
    caminho = b2.midia("t1", "1", "1")[0]
    assert caminho.startswith(os.path.join(raiz, "midias"))
    assert os.path.isfile(caminho)
    b2.fechar()
    # de novo nao mexe (nao ha mais pasta de conta com dados)
    assert migracao.migrar(cfg) == 0


def test_voltar_ao_layout_antigo_mantem_o_que_ja_esta_la(cfg):
    """Sessoes e midias que a pasta comum ja tem ficam (a copia da conta
    e que sai)."""
    cfg.salvar_conta({"id": "t1", "servico": "telegram"})
    b = Bancos(cfg)
    b.salvar_mensagens([m.Mensagem("t1", "1", "1", texto="oi", data=1)])
    arquivo = os.path.join(armazem.pasta_da_conversa("t1", "1"), "a.jpg")
    open(arquivo, "wb").write(b"JPG")
    b.registrar_midia("t1", "1", "1", m.FOTO, arquivo, 3, 1.0)
    b.fechar()
    raiz = config.pasta_dados()
    os.makedirs(os.path.join(raiz, "sessoes"))
    open(os.path.join(raiz, "sessoes", "t1.session"), "wb").write(b"comum")
    cfg.set("contas_em_pastas", False)
    assert migracao.migrar(cfg) == 1
    assert open(os.path.join(raiz, "sessoes", "t1.session"),
                "rb").read() == b"comum"
    # a copia que sobrou na conta saiu junto com a pasta dela
    assert not os.path.exists(config.pasta_da_conta("t1"))
    assert migracao.migrar(cfg) == 0

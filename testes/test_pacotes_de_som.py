# SPDX-License-Identifier: GPL-3.0-or-later
"""Pacotes de sons: Padrao, TeleZapp e personalizados, com eventos ativados
ou desativados e arquivos importados ao aplicar."""
import os

import numpy as np
import pytest
import soundfile as sf

from telezapp import config
from telezapp.acessibilidade import fala
from telezapp.nucleo import pacotes_de_som as pk
from telezapp.nucleo.configuracoes import ModeloConfiguracoes


@pytest.fixture
def dados(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path / "dados"))
    yield tmp_path
    fala.definir_sons({})


def som(pasta, nome):
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / nome
    sf.write(str(caminho), np.zeros((800, 2), dtype="float32"), 8000)
    return str(caminho)


def test_pacotes_da_casa_e_personalizados_listados(dados):
    assert pk.listar() == [("padrao", "Padrão: bips do sistema"),
                           ("telezapp", "TeleZapp")]
    pacote_id, erro = pk.criar("  Meu   pacote ")
    assert (pacote_id, erro) == ("p:Meu pacote", "")
    assert pk.listar()[-1] == ("p:Meu pacote", "Meu pacote")
    assert pk.editavel(pacote_id) and not pk.editavel("telezapp")
    assert pk.criar("meu pacote")[1] == "Já existe um pacote com este nome."
    assert pk.criar("telezapp")[1]                     # nome da casa
    assert pk.criar("")[1] and pk.criar("a/b")[1] and pk.criar("x" * 41)[1]
    pk.excluir(pacote_id)
    pk.excluir("telezapp")                             # nao exclui os da casa
    assert [i for i, _ in pk.listar()] == ["padrao", "telezapp"]


def test_mapa_de_cada_pacote_para_o_modulo_de_sons(dados):
    eventos = {e for e, _ in pk.eventos()}
    assert pk.mapa("padrao") == {e: fala.BIP for e in eventos}
    assert pk.mapa("padrao", ["nova"])["nova"] == "desligado"
    telezapp = pk.mapa("telezapp", ["erro"])
    assert telezapp["erro"] == "desligado"
    assert telezapp["nova"].endswith("nova.ogg") and os.path.isfile(
        telezapp["nova"])
    pacote_id, _ = pk.criar("Meu")
    assert set(pk.mapa(pacote_id).values()) == {fala.BIP}   # sem arquivo: bip
    destino = pk.importar_arquivo(pacote_id, "nova", som(dados / "x", "a.MP3"))
    assert destino.endswith(os.path.join("Meu", "nova.mp3"))
    assert pk.mapa(pacote_id)["nova"] == destino
    # trocar por outro formato apaga o anterior
    novo = pk.importar_arquivo(pacote_id, "nova", som(dados / "x", "b.wav"))
    assert novo.endswith("nova.wav") and not os.path.exists(destino)
    # o valor do pacote chega aos eventos do modulo de sons
    fala.definir_sons(pk.mapa(pacote_id, ["erro"]))
    assert fala.acao_do_som("nova") == ("arquivo", novo)
    assert fala.acao_do_som("erro") == ("nenhum", "")
    assert fala.acao_do_som("enviada") == ("padrao", "")      # bip
    assert fala.acao_do_som("nova_aberta") == ("padrao", "")  # bip proprio
    fala.definir_sons(pk.mapa("padrao", ["nova"]))
    assert fala.acao_do_som("nova") == ("nenhum", "")
    assert fala.acao_do_som("nova_aberta") == ("padrao", "")  # nao herda


def test_estado_da_tela_so_vai_ao_disco_ao_aplicar(dados):
    cfg = config.Config()
    est = ModeloConfiguracoes(cfg).sons
    assert est.ativo == "padrao"
    # pacotes da casa: eventos podem ser desativados, sem escolher arquivo
    assert est.ativado("padrao", "nova")
    assert est.alternar("padrao", "nova") is False
    est.escolher("telezapp", "nova", "C:/x.wav")              # ignorado
    assert est.texto_do_evento("padrao", "nova", "mensagem recebida") == \
        "Mensagem recebida: desativado"
    assert est.texto_do_evento("telezapp", "nova", "mensagem recebida") == \
        "Mensagem recebida: ativado, som: nova.ogg"
    # pacote novo e arquivo escolhido: nada no disco ainda
    pacote_id, erro = est.criar("Meu")
    assert not erro and ("p:Meu", "Meu") in est.pacotes()
    assert not os.path.exists(os.path.join(pk.pasta_dos_pacotes(), "Meu"))
    est.selecionar(pacote_id)
    origem = som(dados / "fora", "campainha.ogg")
    est.escolher(pacote_id, "nova", origem)
    assert est.texto_do_evento(pacote_id, "nova", "mensagem recebida") == \
        "Mensagem recebida: ativado, som: campainha.ogg"
    assert est.texto_do_evento(pacote_id, "erro", "erro") == \
        "Erro: ativado, som: bip do sistema"
    assert est.valor_para_ouvir(pacote_id, "nova") == origem
    assert est.valor_para_ouvir("padrao", "nova") == fala.BIP
    est.alternar(pacote_id, "erro")
    resultado = est.aplicar()
    assert resultado["ativo"] == "p:Meu" and resultado["erros"] == []
    assert resultado["desativados"] == {"padrao": ["nova"],
                                        "p:Meu": ["erro"]}
    # agora o arquivo foi importado para a pasta do pacote, com o nome do evento
    esperado = os.path.join(pk.pasta_dos_pacotes(), "Meu", "nova.ogg")
    assert os.path.isfile(esperado) and pk.arquivo_do_evento(
        "p:Meu", "nova") == esperado
    assert not est.mudou()
    # excluir o pacote ativo volta ao Padrao e remove a pasta ao aplicar
    est2 = ModeloConfiguracoes(cfg).sons
    est2.ativo = "p:Meu"
    assert est2.excluir("padrao") != "" and est2.excluir("telezapp") != ""
    assert est2.excluir("p:Meu") == "" and est2.ativo == "padrao"
    assert os.path.isdir(os.path.dirname(esperado))     # ainda la
    assert est2.aplicar()["ativo"] == "padrao"
    assert not os.path.exists(os.path.dirname(esperado))


def test_aplicar_entrega_os_sons_ao_aplicador_e_so_quando_mudou(dados):
    cfg = config.Config()
    modelo = ModeloConfiguracoes(cfg)
    chamadas = []
    modelo.aplicar(lambda k, v: chamadas.append(k))
    assert "sons_pacotes" not in chamadas
    modelo.sons.selecionar("telezapp")
    modelo.aplicar(lambda k, v: chamadas.append((k, v)))
    assert ("sons_pacotes", {"ativo": "telezapp", "desativados": {},
                             "erros": []}) in chamadas


def test_quem_escolhia_um_som_por_evento_ganha_o_pacote_personalizado(dados):
    cfg = config.Config()
    sons = config.pasta_sons()
    som(__import__("pathlib").Path(sons), "meu.wav")
    cfg.dados.update({"som_nova": "meu.wav", "som_erro": "desligado",
                      "som_enviada": "", "pacote_de_sons": "personalizado"})
    pk.migrar_antigos(cfg)
    assert cfg.get("pacote_de_sons") == "p:Personalizado"
    assert cfg.get("sons_desativados") == {"p:Personalizado": ["erro"]}
    assert os.path.isfile(os.path.join(pk.pasta_dos_pacotes(),
                                       "Personalizado", "nova.wav"))
    assert not any(k.startswith("som_") and k != "som" for k in cfg.dados)
    # sem escolhas antigas, nada muda; valor invalido volta ao padrao
    cfg2 = config.Config(str(dados / "outro.json"))
    cfg2.dados["pacote_de_sons"] = "personalizado"
    pk.migrar_antigos(cfg2)
    assert cfg2.get("pacote_de_sons") == "padrao"
    assert [i for i, _ in pk.listar()].count("p:Personalizado") == 1

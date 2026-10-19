# SPDX-License-Identifier: GPL-3.0-or-later
"""Sons dos eventos: padrao, desligado ou arquivo escolhido."""
import struct
import sys
import types
import wave

from telezapp import config
from telezapp.acessibilidade import fala
from telezapp.nucleo import backup


def wav(caminho, segundos=1, taxa=8000):
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(struct.pack("<h", 1000) * (taxa * segundos))
    return str(caminho)


def test_cada_evento_tem_uma_opcao_de_som_e_o_padrao_e_o_som_de_hoje():
    eventos = {nome for nome, _, _ in config.EVENTOS_SOM}
    assert eventos == {"nova", "enviada", "erro", "conectado", "pronto",
                       "atualizado", "toque", "chamando", "desligada",
                       "nova_aberta", "nova_grupo", "desconectada",
                       "reconectada", "falha_envio", "download_pronto",
                       "tarefa_pronta"}
    por_som = {o.som: o for o in config.OPCOES if o.som}
    assert set(por_som) == eventos
    assert all(o.categoria == "Sons" and o.padrao == "" for o in
               por_som.values())


def test_acao_do_som(tmp_path):
    fala.definir_sons({})
    assert fala.acao_do_som("nova") == ("padrao", "")
    fala.definir_sons({"nova": "desligado", "erro": str(tmp_path / "x.wav"),
                       "enviada": wav(tmp_path / "e.wav")})
    assert fala.acao_do_som("nova") == ("nenhum", "")
    assert fala.acao_do_som("erro") == ("padrao", "")      # arquivo sumiu
    assert fala.acao_do_som("enviada")[0] == "arquivo"
    assert fala.acao_do_som("nova", "")[0] == "padrao"     # ouvir antes
    fala.definir_sons({})


def test_arquivo_de_som_toca_pelo_sounddevice(tmp_path, monkeypatch):
    tocados = []
    falso = types.SimpleNamespace(
        play=lambda dados, taxa: tocados.append((dados.shape, taxa)))
    monkeypatch.setitem(sys.modules, "sounddevice", falso)
    fala._tocar_arquivo("nova", wav(tmp_path / "a.wav", segundos=30))
    (quadros, canais), taxa = tocados[0]
    assert taxa == 8000 and canais == 1
    assert quadros == 8000 * fala.LIMITE_SEGUNDOS_ARQUIVO     # so o comeco


def test_arquivo_ilegivel_cai_no_som_padrao(tmp_path, monkeypatch):
    ruim = tmp_path / "ruim.wav"
    ruim.write_bytes(b"nao e som")
    padrao = []
    monkeypatch.setattr(fala, "_tocar", lambda tipo: padrao.append(tipo))
    monkeypatch.setattr(fala, "winsound", object())
    monkeypatch.setitem(sys.modules, "sounddevice",
                        types.SimpleNamespace(play=lambda *a: None))
    fala._tocar_arquivo("erro", str(ruim))
    assert padrao == ["erro"]


def test_bipe_desligado_nao_toca_nada(monkeypatch):
    fala.definir_sons({"nova": "desligado"})
    monkeypatch.setattr(fala.threading, "Thread", lambda *a, **k: (_ for _ in
                                                                   ()).throw(
        AssertionError("nao devia tocar")))
    fala.bipe("nova")
    fala.definir_sons({})


def test_backup_leva_e_valida_as_escolhas_de_som():
    dados = backup.opcoes_do_backup({"som_nova": "desligado",
                                     "som_erro": "C:/sons/erro.wav"})
    assert dados["som_nova"] == "desligado"
    boas = backup.opcoes_validas(dados)
    assert boas["som_erro"] == "C:/sons/erro.wav"
    assert "som_nova" in boas and backup.opcoes_validas(
        {"som_nova": 5}) == {}


def test_importar_som_copia_para_a_pasta_de_sons(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path / "dados"))
    de_fora = wav(tmp_path / "campainha.wav")
    nome = config.importar_som(de_fora)
    assert nome == "campainha.wav"
    assert (tmp_path / "dados" / "sons" / "campainha.wav").exists()
    assert config.importar_som(de_fora) == "campainha.wav"      # mesmo arquivo
    outro = tmp_path / "outra"
    outro.mkdir()
    diferente = wav(outro / "campainha.wav", segundos=2)
    assert config.importar_som(diferente) == "campainha (2).wav"
    dentro = str(tmp_path / "dados" / "sons" / "campainha.wav")
    assert config.importar_som(dentro) == "campainha.wav"       # ja la dentro


def test_nome_de_som_vale_na_pasta_de_sons_e_arquivo_que_sumiu_cai_no_padrao(
        tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path))
    nome = config.importar_som(wav(tmp_path / "x.wav"))
    fala.definir_sons({"nova": nome})
    assert fala.acao_do_som("nova") == (
        "arquivo", str(tmp_path / "sons" / "x.wav"))
    (tmp_path / "sons" / "x.wav").unlink()
    assert fala.acao_do_som("nova") == ("padrao", "")
    fala.definir_sons({})


def test_backup_das_configuracoes_leva_a_pasta_de_sons(tmp_path):
    origem = tmp_path / "a"
    (origem / "sons").mkdir(parents=True)
    wav(origem / "sons" / "meu.wav")
    arquivo = str(tmp_path / "b.zip")
    resumo = backup.criar(arquivo, str(origem), {"som_nova": "meu.wav"},
                          ["configuracoes"])
    assert resumo["configuracoes"] == 2
    destino = tmp_path / "b"
    opcoes, espera = backup.restaurar(arquivo, "", ["configuracoes"],
                                      str(destino))
    assert opcoes["som_nova"] == "meu.wav" and espera == []
    assert (destino / "sons" / "meu.wav").exists()          # na hora


def test_eventos_novos_acompanham_o_som_do_evento_de_origem(tmp_path):
    fala.definir_sons({})
    assert fala.tom_padrao("nova_grupo") == "nova"
    assert fala.tom_padrao("falha_envio") == "erro"
    assert fala.tom_padrao("download_pronto") == "download_pronto"
    # sem escolha, acompanha o outro; com "sem som" no outro, fica mudo
    assert fala.acao_do_som("nova_aberta") == ("padrao", "")
    fala.definir_sons({"nova": "desligado"})
    assert fala.acao_do_som("nova_aberta") == ("nenhum", "")
    assert fala.acao_do_som("nova_grupo", "") == ("nenhum", "")
    # escolha propria vale sobre a do outro
    fala.definir_sons({"nova": "desligado", "nova_aberta": wav(
        tmp_path / "a.wav")})
    assert fala.acao_do_som("nova_aberta")[0] == "arquivo"
    fala.definir_sons({"erro": wav(tmp_path / "e.wav")})
    assert fala.acao_do_som("falha_envio")[0] == "arquivo"
    fala.definir_sons({})


def test_evento_novo_sem_herdar_toca_o_proprio_tom(monkeypatch):
    tons = []
    monkeypatch.setattr(fala, "winsound", types.SimpleNamespace(
        Beep=lambda f, d: tons.append(f)))
    fala._tocar("desconectada")
    fala._tocar("download_pronto")
    assert tons == [440, 330, 740, 988]

# SPDX-License-Identifier: GPL-3.0-or-later
"""Sons dos eventos: padrao, desligado ou arquivo escolhido."""
import struct
import sys
import types
import wave

import pytest

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


def test_todo_evento_tem_um_som_nos_pacotes_da_casa():
    from telezapp.nucleo import pacotes_de_som as pk
    eventos = {nome for nome, _, _ in config.EVENTOS_SOM}
    assert eventos == {"nova", "enviada", "erro", "conectado", "pronto",
                       "atualizado", "toque", "chamando", "desligada",
                       "nova_aberta", "nova_grupo", "desconectada",
                       "reconectada", "falha_envio", "download_pronto",
                       "tarefa_pronta", "reacao_recebida",
                       "mencao_ou_resposta", "gravando", "gravacao_parada",
                       "voto_enquete", "voto_enviado", "escondido",
                       "voltou"}
    assert {e for e, _ in pk.eventos()} == eventos
    assert not [o for o in config.OPCOES if getattr(o, "som", "")]
    for e in eventos:                            # o pacote TeleZapp e completo
        assert pk.arquivo_do_evento(pk.TELEZAPP, e), e


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


def test_backup_leva_e_valida_o_pacote_e_os_eventos_desativados():
    dados = backup.opcoes_do_backup({"pacote_de_sons": "p:Meu",
                                     "sons_desativados": {"p:Meu": ["nova"]}})
    assert dados["pacote_de_sons"] == "p:Meu"
    boas = backup.opcoes_validas(dados)
    assert boas["pacote_de_sons"] == "p:Meu"
    assert boas["sons_desativados"] == {"p:Meu": ["nova"]}
    ruins = backup.opcoes_validas({"pacote_de_sons": 5,
                                   "sons_desativados": {"x": "nova"}})
    assert "pacote_de_sons" not in ruins
    assert ruins.get("sons_desativados") == {}


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
    fala._thread_pre_carga.join()       # a pre-carga ainda pode ter o arquivo
    (tmp_path / "sons" / "x.wav").unlink()
    assert fala.acao_do_som("nova") == ("padrao", "")
    fala.definir_sons({})


def test_backup_dos_sons_leva_a_pasta_de_sons(tmp_path):
    origem = tmp_path / "a"
    (origem / "sons").mkdir(parents=True)
    wav(origem / "sons" / "meu.wav")
    arquivo = str(tmp_path / "b.zip")
    resumo = backup.criar(arquivo, str(origem), {"pacote_de_sons": "p:Meu"},
                          ["sons"])
    assert resumo["sons"] == 2
    destino = tmp_path / "b"
    opcoes, espera = backup.restaurar(arquivo, "", ["sons"], str(destino))
    assert opcoes["pacote_de_sons"] == "p:Meu" and espera == []
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


def test_gerador_cria_sons_curtos_estereo_que_comecam_logo(tmp_path):
    import importlib.util
    import os
    import numpy as np
    import soundfile as sf
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "gerar_sons", os.path.join(raiz, "ferramentas", "gerar_sons.py"))
    gerador = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gerador)
    from telezapp import config
    caminhos = gerador.gerar(str(tmp_path))
    assert {os.path.basename(c)[:-4] for c in caminhos} == \
        {nome for nome, _, _ in config.EVENTOS_SOM}      # um por evento
    for c in caminhos:
        dados, taxa = sf.read(c)
        assert dados.ndim == 2 and dados.shape[1] == 2, c        # estereo
        assert len(dados) / taxa <= 2.0, c                       # curto
        assert np.abs(dados[:int(taxa * 0.02)]).max() > 0.2, c   # sem silencio
        assert np.abs(dados).max() < 0.6, c                      # sem estourar
        assert np.abs(dados[-40:]).max() < 0.01, c               # termina mudo


def test_tom_de_chamando_do_pacote_padrao_dura_um_segundo_e_meio(monkeypatch):
    tons = []
    monkeypatch.setattr(fala, "winsound", types.SimpleNamespace(
        Beep=lambda freq, ms: tons.append((freq, ms))))
    fala._tocar("chamando")
    assert tons == [(425, 1500)]
    tons.clear()
    fala._tocar("toque")                      # o toque de quem recebe segue
    assert len(tons) == 4 and all(ms == 120 for _, ms in tons)


def test_som_curto_fica_pre_carregado_e_o_longo_nao(tmp_path):
    curto = wav(tmp_path / "curto.wav")
    longo = wav(tmp_path / "longo.wav", segundos=5)
    fala.definir_sons({"enviada": curto, "toque": longo})
    fala._thread_pre_carga.join()
    assert curto in fala._pre_carregados
    assert longo not in fala._pre_carregados
    fala.definir_sons({})
    assert not fala._pre_carregados


def test_eventos_novos_herdam_o_som_certo_e_tem_bip_proprio():
    # parar a gravacao e enviar o voto usam, de fabrica, o som de enviada
    assert fala.tom_padrao("gravacao_parada") == "enviada"
    assert fala.tom_padrao("voto_enviado") == "enviada"
    for evento in ("gravando", "voto_enquete", "escondido", "voltou"):
        assert fala.tom_padrao(evento) == evento


def test_aviso_no_dispositivo_escolhido_toca_pelo_sounddevice(monkeypatch):
    tocados, beeps = [], []
    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(
        play=lambda dados, taxa, device=None: tocados.append(
            (len(dados), taxa, device))))
    monkeypatch.setattr(fala, "winsound", types.SimpleNamespace(
        Beep=lambda f, ms: beeps.append(f)))
    monkeypatch.setattr(fala, "_indice_dos_avisos", lambda: 7)
    fala._tocar("nova")
    assert beeps == []                         # nao foi pelo winsound
    quadros, taxa, dispositivo = tocados[0]
    assert dispositivo == 7 and taxa == fala.TAXA_SINTETICA
    assert quadros == int(taxa * 0.09) + int(taxa * 0.12)


def test_aviso_sem_dispositivo_escolhido_segue_no_winsound(monkeypatch):
    beeps = []
    monkeypatch.setattr(fala, "winsound", types.SimpleNamespace(
        Beep=lambda f, ms: beeps.append((f, ms))))
    monkeypatch.setattr(fala, "_indice_dos_avisos", lambda: None)
    fala._tocar("nova")
    assert beeps == [(880, 90), (1175, 120)]


def test_arquivo_de_aviso_vai_para_o_dispositivo_escolhido(tmp_path,
                                                           monkeypatch):
    tocados = []
    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(
        play=lambda dados, taxa, device=None: tocados.append(device)))
    monkeypatch.setattr(fala, "_indice_dos_avisos", lambda: 3)
    fala._tocar_arquivo("nova", wav(tmp_path / "a.wav"))
    assert tocados == [3]


def test_dispositivo_dos_avisos_guarda_e_nao_mexe_nos_outros():
    from telezapp.midia import dispositivos
    try:
        dispositivos.definir("Mic", "Saida", "Caixa")
        assert dispositivos.notificacao() == "Caixa"
        dispositivos.definir("Mic2", "Saida2")           # sem mexer no aviso
        assert dispositivos.notificacao() == "Caixa"
        assert dispositivos.microfone() == "Mic2"
        dispositivos.definir("", "", "")
        assert dispositivos.notificacao() == ""
    finally:
        dispositivos.definir("", "", "")

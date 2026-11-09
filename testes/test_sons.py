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
    eventos = {nome for nome, _, _ in config.EVENTOS_SOM
               if nome not in pk.VARIANTES_POR_SERVICO}
    assert eventos == {"nova", "enviada", "erro", "conectado", "pronto",
                       "atualizado", "toque", "desligada",
                       "nova_aberta", "nova_grupo", "nova_pessoal",
                       "nova_canal", "nova_comunidade", "desconectada",
                       "reconectada", "falha_envio", "download_pronto",
                       "tarefa_pronta", "reacao_recebida",
                       "mencao_ou_resposta", "gravando", "gravacao_parada",
                       "voto_enquete", "voto_enviado", "escondido",
                       "voltou"}
    assert {e for e, _ in pk.eventos()
            if e not in pk.VARIANTES_POR_SERVICO} == eventos
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


def test_arquivo_de_som_toca_pelo_fluxo(tmp_path, monkeypatch):
    tocados = []
    monkeypatch.setattr(fala, "_indice_dos_avisos", lambda: None)
    monkeypatch.setattr(fala, "_tocar_pelo_fluxo",
                        lambda dados, taxa, dispositivo=None:
                        tocados.append((dados.shape, taxa, dispositivo)))
    fala._tocar_arquivo("nova", wav(tmp_path / "a.wav", segundos=30))
    (quadros, canais), taxa, dispositivo = tocados[0]
    assert taxa == 8000 and canais == 1 and dispositivo is None
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
    from telezapp.nucleo import pacotes_de_som as pk
    assert {os.path.basename(c)[:-4] for c in caminhos} == \
        {nome for nome, _, _ in config.EVENTOS_SOM
         if nome not in pk.VARIANTES_POR_SERVICO}        # um por evento
    for c in caminhos:
        dados, taxa = sf.read(c)
        assert dados.ndim == 2 and dados.shape[1] == 2, c        # estereo
        assert len(dados) / taxa <= 2.0, c                       # curto
        assert np.abs(dados[:int(taxa * 0.02)]).max() > 0.2, c   # sem silencio
        assert np.abs(dados).max() < 0.6, c                      # sem estourar
        assert np.abs(dados[-40:]).max() < 0.01, c               # termina mudo


def test_tom_de_chamada_padrao_e_o_da_europa_e_o_eua_e_opcional(monkeypatch):
    tons = []
    monkeypatch.setattr(fala, "winsound", types.SimpleNamespace(
        Beep=lambda freq, ms: tons.append((freq, ms))))
    monkeypatch.setattr(fala, "_indice_dos_avisos", lambda: None)
    assert config.PADROES["tom_de_chamada"] == "europa"
    assert fala.TONS_DE_CHAMADA["europa"] == ((425,), 1000, 4000)
    assert fala.TONS_DE_CHAMADA["eua"] == ((440, 480), 2000, 6000)
    fala.definir_tom_de_chamada("europa")
    fala._tocar_tom("europa")
    assert tons == [(425, 1000)]
    assert fala.intervalo_do_tom_de_chamada() == 4000     # 1 s de tom + 3 s
    fala.definir_tom_de_chamada("eua")
    assert fala.intervalo_do_tom_de_chamada() == 6000     # 2 s de tom + 4 s
    fala.definir_tom_de_chamada("qualquer")                # invalido: padrao
    assert fala.intervalo_do_tom_de_chamada() == 4000
    assert fala.INTERVALO_TOQUE_MS == 3000       # o toque de quem recebe segue
    tons.clear()
    fala._tocar("toque")
    assert len(tons) == 4 and all(ms == 120 for _, ms in tons)


def test_tom_de_chamada_do_eua_junta_as_duas_frequencias():
    import numpy as np
    onda = fala._onda((((440, 480), 2000),))
    assert len(onda) == fala.TAXA_SINTETICA * 2
    espectro = np.abs(np.fft.rfft(onda))
    freqs = np.fft.rfftfreq(len(onda), 1 / fala.TAXA_SINTETICA)
    picos = sorted(freqs[np.argsort(espectro)[-2:]])
    assert [round(f) for f in picos] == [440, 480]
    assert np.abs(onda).max() <= 0.31


def test_chamando_nao_e_mais_um_evento_de_som_do_pacote():
    assert "chamando" not in {n for n, _, _ in config.EVENTOS_SOM}


def test_bipe_chamando_toca_o_tom_escolhido_mesmo_com_som_antigo(monkeypatch):
    tocados = []
    monkeypatch.setattr(fala, "tocar_tom_de_chamada",
                        lambda tom=None: tocados.append(tom))
    fala.definir_sons({"chamando": "desligado"})   # escolha antiga, ignorada
    fala.bipe("chamando")
    fala.definir_sons({})
    assert tocados == [None]


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


def test_aviso_no_dispositivo_escolhido_toca_pelo_fluxo(monkeypatch):
    tocados, beeps = [], []
    monkeypatch.setattr(fala, "_tocar_pelo_fluxo",
                        lambda dados, taxa, dispositivo=None:
                        tocados.append((len(dados), taxa, dispositivo)))
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
    monkeypatch.setattr(fala, "_tocar_pelo_fluxo",
                        lambda dados, taxa, dispositivo=None:
                        tocados.append(dispositivo))
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


def test_preparar_som_vira_estereo_na_taxa_dos_avisos():
    import numpy as np
    mono = np.zeros((800, 1), dtype="float32")
    pronto = fala._preparar_som(mono, 8000)
    assert pronto.shape == (4410, 2)                # 0,1 s a 44100 Hz
    assert pronto.dtype == np.float32
    assert np.array_equal(pronto[:, 0], pronto[:, 1])   # mono nos dois canais

    tres = np.zeros((100, 3), dtype="float32")
    assert fala._preparar_som(tres, fala.TAXA_DOS_AVISOS).shape == (100, 2)

    um = np.zeros(100, dtype="float32")             # 1-D vira dois canais
    assert fala._preparar_som(um, fala.TAXA_DOS_AVISOS).shape == (100, 2)


class _FluxoFalso:
    def __init__(self, **parametros):
        self.parametros = parametros
        self.callback = parametros["callback"]
        self.active = True
        self.iniciado = self.parado = self.fechado = False

    def start(self):
        self.iniciado = True

    def stop(self, *a):
        self.active = False
        self.parado = True

    def close(self, *a):
        self.fechado = True


class _SaidaFalsa:
    def __init__(self):
        self.fluxos = []

    def __call__(self, **parametros):
        fluxo = _FluxoFalso(**parametros)
        self.fluxos.append(fluxo)
        return fluxo


def test_fluxo_dos_avisos_abre_uma_vez_e_troca_o_som(monkeypatch):
    import numpy as np
    fabrica = _SaidaFalsa()
    monkeypatch.setitem(sys.modules, "sounddevice",
                        types.SimpleNamespace(OutputStream=fabrica))
    saida = fala._SaidaDosAvisos()
    som = np.zeros((100, 2), dtype="float32")
    saida.tocar(som, fala.TAXA_DOS_AVISOS)
    saida.tocar(som, fala.TAXA_DOS_AVISOS)
    assert len(fabrica.fluxos) == 1                 # nao reabriu o dispositivo
    assert fabrica.fluxos[0].iniciado
    assert fabrica.fluxos[0].parametros["latency"] == "low"
    assert fabrica.fluxos[0].parametros["channels"] == 2

    saida.tocar(som, fala.TAXA_DOS_AVISOS, dispositivo=3)
    assert len(fabrica.fluxos) == 2                 # trocou de dispositivo
    assert fabrica.fluxos[0].parado and fabrica.fluxos[0].fechado
    assert fabrica.fluxos[1].parametros["device"] == 3

    saida.fechar()
    assert fabrica.fluxos[1].parado and fabrica.fluxos[1].fechado


def test_callback_do_fluxo_entrega_o_som_e_depois_silencio(monkeypatch):
    import numpy as np
    fabrica = _SaidaFalsa()
    monkeypatch.setitem(sys.modules, "sounddevice",
                        types.SimpleNamespace(OutputStream=fabrica))
    saida = fala._SaidaDosAvisos()
    som = np.arange(6, dtype="float32").reshape(-1, 1) + np.zeros((6, 2))
    saida.tocar(som, fala.TAXA_DOS_AVISOS)
    callback = fabrica.fluxos[0].callback

    primeiro = np.zeros((4, 2), dtype="float32")
    callback(primeiro, 4, None, None)
    assert np.array_equal(primeiro, som[:4])

    segundo = np.zeros((4, 2), dtype="float32")
    callback(segundo, 4, None, None)
    assert np.array_equal(segundo[:2], som[4:])     # o resto do som
    assert np.array_equal(segundo[2:], np.zeros((2, 2), dtype="float32"))

    terceiro = np.zeros((4, 2), dtype="float32")
    callback(terceiro, 4, None, None)               # acabou: so silencio
    assert not terceiro.any()
    assert saida._dados is None



def test_fluxo_dos_avisos_fecha_depois_de_ficar_ocioso(monkeypatch):
    import numpy as np
    fabrica = _SaidaFalsa()
    monkeypatch.setitem(sys.modules, "sounddevice",
                        types.SimpleNamespace(OutputStream=fabrica))
    saida = fala._SaidaDosAvisos()
    relogio = [100.0]
    saida._agora = lambda: relogio[0]
    som = np.zeros((10, 2), dtype="float32")
    saida.tocar(som, fala.TAXA_DOS_AVISOS)
    assert saida._ocioso is not None and saida._ocioso.daemon

    relogio[0] += fala.TEMPO_OCIOSO_DOS_AVISOS_S - 5
    saida._fechar_ocioso()                       # ainda nao deu o tempo
    assert not fabrica.fluxos[0].fechado

    fabrica.fluxos[0].callback(np.zeros((20, 2), dtype="float32"), 20,
                               None, None)       # o som acabou de sair
    relogio[0] += 10
    saida._fechar_ocioso()                       # deu: fecha o fluxo
    assert fabrica.fluxos[0].parado and fabrica.fluxos[0].fechado
    assert saida._fluxo is None

    saida.tocar(som, fala.TAXA_DOS_AVISOS)       # o proximo aviso reabre
    assert len(fabrica.fluxos) == 2 and fabrica.fluxos[1].iniciado
    saida.fechar()
    assert saida._ocioso is None


def test_fluxo_dos_avisos_nao_fecha_com_som_ainda_tocando(monkeypatch):
    import numpy as np
    fabrica = _SaidaFalsa()
    monkeypatch.setitem(sys.modules, "sounddevice",
                        types.SimpleNamespace(OutputStream=fabrica))
    saida = fala._SaidaDosAvisos()
    relogio = [0.0]
    saida._agora = lambda: relogio[0]
    saida.tocar(np.zeros((10, 2), dtype="float32"), fala.TAXA_DOS_AVISOS)
    relogio[0] = fala.TEMPO_OCIOSO_DOS_AVISOS_S + 1
    saida._fechar_ocioso()                       # o som nao acabou de sair
    assert not fabrica.fluxos[0].fechado
    saida.fechar()


def test_som_por_servico_herda_o_comum_ate_ter_um_proprio(tmp_path):
    from telezapp import config
    from telezapp.nucleo import pacotes_de_som as pk
    nomes = {n for n, _, _ in config.EVENTOS_SOM}
    assert {"nova_pessoal_telegram", "nova_pessoal_whatsapp",
            "toque_telegram", "reacao_recebida_whatsapp"} <= nomes
    assert "nova_comunidade_telegram" not in nomes   # sem comunidades
    arquivo = tmp_path / "t.wav"
    arquivo.write_bytes(b"RIFF")
    fala.definir_sons({"nova": "", "nova_pessoal": "",
                       "nova_pessoal_telegram": str(arquivo),
                       "nova_pessoal_whatsapp": ""})
    # o Telegram tem som proprio; o WhatsApp segue o comum
    assert fala.tipo_do_servico("nova_pessoal", "telegram") == \
        "nova_pessoal_telegram"
    assert fala.acao_do_som("nova_pessoal_telegram") == \
        ("arquivo", str(arquivo))
    assert fala.acao_do_som("nova_pessoal_whatsapp") == ("padrao", "")
    # desativado so o do Telegram: fica sem som, o do WhatsApp segue
    fala.definir_sons({"nova_pessoal": "", "nova_pessoal_telegram": "desligado",
                       "nova_pessoal_whatsapp": ""})
    assert fala.acao_do_som("nova_pessoal_telegram") == ("nenhum", "")
    assert fala.acao_do_som("nova_pessoal_whatsapp") == ("padrao", "")
    # evento sem variante ou servico desconhecido: o proprio evento
    assert fala.tipo_do_servico("erro", "telegram") == "erro"
    assert fala.tipo_do_servico("nova_pessoal", "") == "nova_pessoal"
    fala.definir_sons({})


def test_mensagem_individual_e_o_nome_na_tela_de_sons_e_no_filtro():
    from telezapp import config
    from telezapp.nucleo import modelos as m
    rotulos = {n: r for n, r, _ in config.EVENTOS_SOM}
    assert rotulos["nova_pessoal"] == "mensagem individual recebida"
    assert rotulos["nova_pessoal_telegram"] == \
        "mensagem individual recebida (Telegram)"
    assert ("pessoais", "Individuais") in m.FILTROS_TIPO   # a chave nao mudou
    assert not any("pessoal" in r or "pessoais" in r.lower()
                   for r in rotulos.values())

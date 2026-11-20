# SPDX-License-Identifier: GPL-3.0-or-later
"""Registro de chamadas para o resumo de uso: so categorias e numeros."""
import json
import logging

import pytest

from telezapp import config
from telezapp.nucleo import uso, uso_chamadas as uc

# linhas no formato real do registro (ids e numeros trocados)
STANZA = ('chamadas: meowcaller {"level":"info","stanza":"e=70441 offline=0 '
          'platform=android t=1794183348 version=2.26.43.76","filhos_da_oferta"'
          ':"audio[enc,rate] audio[enc,rate] capability[ver] enc[type,v] '
          'net[medium] voip_settings[uncompressed]","message":"TeleZapp: '
          'oferta recebida, stanza e filhos"}')
CONTROLE = ('chamadas: meowcaller {"level":"info","controle":"offer",'
            '"atributos":"call-creator=...6118@lid call-id=ABC123DEF '
            'caller_country_code=BR caller_pn=...6966@s.whatsapp.net '
            'device_class=2016 joinable=1","filhos":11,"message":"controle '
            'da chamada recebido: offer"}')
CRIADA = "chamadas: chamada ABC123DEF criada (entrante=true, com=...6118@lid)"
CODEC = ('chamadas: meowcaller {"level":"info","call_id":"ABC123DEF","codec":'
         '"mlow","use_mlow_codec_v1":true,"message":"selected audio codec"}')
RELAYS = ('chamadas: meowcaller {"level":"info","inbound":true,"ofertas":'
          '"bsb1c01(fna=false tok=1 auth=0 rtt=33) gru1c02(fna=false tok=0 '
          'auth=0 rtt=20) gig4c02(fna=false tok=0 auth=0 rtt=24)","escolhido"'
          ':"gru1c02","sem_fna_heuristica":true,"message":"TeleZapp: relays"}')
TENTATIVA = ('chamadas: meowcaller {"level":"info","call_id":"ABC123DEF",'
             '"relay":"bsb1c01","tentativa":3,"de":3,"message":"TeleZapp: '
             'midia no relay"}')
FASE3 = "chamadas: chamada ABC123DEF: fase 3 depois de 4.0s"
SOM = ("chamadas: chamada ABC123DEF: som do outro lado chegou (primeiro RTP) "
       "depois de 11.0s")
FIM = ("chamadas: chamada ABC123DEF encerrada (hangup) depois de 162.4s: "
       "quadros do outro lado=1153, do microfone=2200")


@pytest.fixture(autouse=True)
def limpo():
    uc._andamento.clear()
    uc._oferta_pendente.clear()
    uc._ultima[0] = ""
    uso._chamadas.clear()
    yield
    uc._andamento.clear()
    uc._oferta_pendente.clear()
    uso._chamadas.clear()


def _chamada_recebida(motivo="desligada", sem_som=False, fim=FIM):
    for linha in (STANZA, CONTROLE, CRIADA, CODEC, FASE3, RELAYS, TENTATIVA,
                  SOM, fim):
        uc.tratar_linha(linha)
    return uc.concluir("ABC123DEF", entrante=True, video=False, grupo=False,
                       por_link=False, motivo=motivo, sem_som=sem_som)


def test_chamada_de_android_vira_registro_so_com_categorias():
    r = _chamada_recebida()
    assert r["plataforma"] == "android" and r["versao_wa"] == "2.26.43.76"
    assert r["classe"] == 2016 and r["itens_da_oferta"] == 11
    assert r["codec"] == "mlow"
    assert r["relays"] == 3 and r["relay_tentativa"] == 3
    assert r["relay_posicao_rtt"] == 1 and r["relay_heuristica"] is True
    assert r["relay_fna"] is False
    # o tempo do som conta desde que atendemos (4,0 s), nao desde o toque
    assert r["t_toque_s"] == 4.0 and r["t_som_apos_atender_s"] == 7.0
    assert "t_som_s" not in r and r["dur_s"] == 162.4
    assert r["rx"] == "1000 ou mais" and r["tx"] == "1000 ou mais"
    assert r["direcao"] == "entrada" and r["tipo"] == "voz"
    assert r["resultado"] == "desligada" and r["motivo_dll"] == "hangup"
    texto = json.dumps(r)
    for proibido in ("ABC123DEF", "6118", "6966", "gru1c02", "bsb1c01",
                     "BR", "1794183348"):
        assert proibido not in texto
    assert uso._chamadas and uso._chamadas[-1] == r
    assert "ABC123DEF" not in uc._andamento     # o id nao fica guardado


def test_atendida_sem_som_conta_como_problema():
    r = _chamada_recebida(motivo="falha", sem_som=True)
    assert r["resultado"] == "sem_som"


def test_desligada_depois_de_muito_tempo_sem_quadros_e_sem_som():
    fim = FIM.replace("1153", "0")
    r = _chamada_recebida(fim=fim)
    assert r["resultado"] == "sem_som"


def test_chamada_perdida_sem_nada_da_dll_ainda_gera_registro():
    r = uc.concluir("nao-vista", entrante=True, video=True, grupo=False,
                    por_link=False, motivo="perdida", sem_som=False)
    assert r["resultado"] == "perdida" and r["tipo"] == "video"
    assert "plataforma" not in r


def test_grupo_leva_so_a_faixa_de_pessoas():
    r = uc.concluir("g1", entrante=False, video=False, grupo=True,
                    por_link=False, motivo="desligada", sem_som=False,
                    pessoas=7)
    assert r["grupo"] is True and r["pessoas"] == "6 a 10"


def test_o_leitor_do_registro_so_olha_o_modulo_da_dll():
    uc.instalar()
    logging.getLogger(uc.MODULO_DA_DLL).warning(CRIADA)
    assert "ABC123DEF" in uc._andamento


def test_amostra_leva_no_maximo_10_com_as_falhas_na_frente():
    for i in range(12):
        uso.registrar_chamada({"resultado": "desligada", "n": i})
    uso.registrar_chamada({"resultado": "sem_som", "n": 100})
    uso.registrar_chamada({"resultado": "falha", "n": 101})
    a = uso.amostra_de_chamadas(uso._chamadas)
    assert len(a) == uso.MAX_CHAMADAS_POR_ENVIO
    assert {x["n"] for x in a[:2]} == {100, 101}
    assert [x["n"] for x in a[2:4]] == [11, 10]      # as mais recentes


def test_chamadas_entram_no_resumo_no_texto_e_sobrevivem_ao_fechar(
        tmp_path, monkeypatch):
    monkeypatch.setattr(uso, "_arquivo", lambda: str(tmp_path / "p.json"))
    cfg = config.Config(str(tmp_path / "config.json"))
    _chamada_recebida()
    d = uso.montar(cfg)
    assert len(d["chamadas"]) == 1
    assert "android" in uso.texto_para_ver(d)
    uso.guardar_pendente()
    uso._chamadas.clear()
    uso.carregar_pendente()
    assert len(uso._chamadas) == 1

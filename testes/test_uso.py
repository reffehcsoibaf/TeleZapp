# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Informações de uso opcionais (nucleo/uso.py): só números, nunca conteúdo."""
import json
import threading

import pytest

from telezapp import config
from telezapp.nucleo import uso


@pytest.fixture
def cfg(tmp_path):
    c = config.Config(str(tmp_path / "config.json"))
    uso._lentos.clear()
    uso._erros.clear()
    uso._tempos.clear()
    uso._contagens.clear()
    uso._fatos.clear()
    uso._chamadas.clear()
    yield c
    uso._lentos.clear()
    uso._erros.clear()
    uso._tempos.clear()
    uso._contagens.clear()
    uso._fatos.clear()
    uso._chamadas.clear()


def test_padrao_e_desligado_e_nunca_perguntado(cfg):
    assert cfg.get("compartilhar_uso") is False
    assert cfg.get("uso_resposta") == ""
    assert not uso.devido(cfg)


def test_pergunta_logo_na_primeira_vez(cfg):
    assert uso.devo_perguntar(cfg, 1_000_000)


def test_nao_compartilhar_encerra_o_assunto(cfg):
    uso.registrar_pergunta(cfg, "nao", 1_000_000)
    assert cfg.get("compartilhar_uso") is False
    assert not uso.devo_perguntar(cfg, 1_000_000 + 365 * 86400)


def test_compartilhar_liga_a_caixa_e_nao_pergunta_mais(cfg):
    uso.registrar_pergunta(cfg, "sim", 1_000_000)
    assert cfg.get("compartilhar_uso") is True
    assert not uso.devo_perguntar(cfg, 1_000_000 + 365 * 86400)
    cfg.set("compartilhar_uso", False)       # mudou de ideia nas opcoes
    assert not uso.devo_perguntar(cfg, 1_000_000 + 365 * 86400)


def test_esc_volta_numa_versao_nova_mas_nao_antes_de_sete_dias(
        cfg, monkeypatch):
    uso.registrar_pergunta(cfg, "depois", 1_000_000)
    assert cfg.get("compartilhar_uso") is False
    # na mesma versao nunca repete
    assert not uso.devo_perguntar(cfg, 1_000_000 + 30 * 86400)
    # versao nova, mas cedo demais
    monkeypatch.setattr(uso, "VERSAO", "2099.1.1.0")
    assert not uso.devo_perguntar(cfg, 1_000_000 + 2 * 86400)
    # versao nova e passou a espera
    assert uso.devo_perguntar(cfg, 1_000_000 + 8 * 86400)


def test_faixa_nunca_diz_o_numero_exato():
    assert uso.faixa(0) == "0"
    assert uso.faixa(37) == "1 a 49"
    assert uso.faixa(1500) == "1000 a 2999"
    assert uso.faixa(50000) == "10000 ou mais"


def test_id_anonimo_e_sorteado_uma_vez(cfg):
    a = uso.id_anonimo(cfg)
    assert len(a) == 32 and uso.id_anonimo(cfg) == a


def test_resumo_so_tem_numeros_e_nomes_de_recursos(cfg):
    cfg.salvar_conta({"id": "w1", "servico": "whatsapp",
                      "nome": "Maria Silva", "telefone": "+5551999990000"})
    cfg.salvar_conta({"id": "t1", "servico": "telegram", "nome": "João"})
    uso.registrar_lento("_abrir_conversa", 0.5)
    uso.registrar_lento("_abrir_conversa", 0.9)
    uso.registrar_erro("_enviar")
    uso.registrar_tempo("f5", 3.456)
    uso.registrar_tempo("abertura", 7.0)
    d = uso.montar(cfg, conversas=1234, leitor="jaws")
    assert d["contas"] == {"whatsapp": 1, "telegram": 1}
    assert d["conversas"] == "1000 a 2999"
    assert d["leitor"] == "jaws"
    assert d["lentos"] == {"_abrir_conversa": {"n": 2, "max_s": 0.9}}
    assert d["erros"] == {"_enviar": 1}
    assert d["tempos"] == {"f5": 3.46} and d["abertura_s"] == 7.0
    texto = json.dumps(d, ensure_ascii=False)
    for proibido in ("Maria", "Silva", "João", "5551999990000", "w1", "t1"):
        assert proibido not in texto


def test_dados_tecnicos_sem_conteudo(cfg):
    import logging
    uso.contar("quedas", "whatsapp")
    uso.contar("quedas", "whatsapp")
    uso.contar("causas_de_queda", "servidor")
    uso.registrar_fato("fechou_sem_fechar", True)
    uso.registrar_fato("disco", "USB")
    uso.registrar_banco("ok", 1.234, 120 * 1048576)
    uso.registrar_banco("danificado", 2.0, 120 * 1048576)
    uso.registrar_banco("ok", 0.5, 1)        # nao esconde o defeito
    uso.instalar_contador_de_registro()
    logging.getLogger("telezapp.provedores.whatsapp").warning(
        "mensagem de Maria para +5551999990000")
    logging.getLogger("telezapp.provedores.whatsapp").error("x")
    # o Go manda informacao das chamadas como WARNING: nao e aviso de verdade
    logging.getLogger("whatsmeow.Client.Chamadas").warning("meowcaller {}")
    d = uso.montar(cfg)
    assert not any("Chamadas" in k for k in d["registro"])
    assert d["quedas"] == {"whatsapp": 2}
    assert d["causas_de_queda"] == {"servidor": 1}
    assert d["fechou_sem_fechar"] is True and d["disco"] == "USB"
    assert d["banco"] == {"estado": "danificado", "s": 2.0,
                          "tamanho": "50 a 199 MB"}
    assert d["registro"]["provedores_whatsapp_aviso"] >= 1
    assert d["registro"]["provedores_whatsapp_erro"] >= 1
    assert d["ambiente"]["python"]
    texto = json.dumps(d, ensure_ascii=False)
    assert "Maria" not in texto and "5551999990000" not in texto
    assert "Quedas de conexão" in uso.texto_para_ver(d)


def test_medidas_sobrevivem_ao_fechar_e_somam_na_proxima_abertura(
        cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(uso, "_arquivo", lambda: str(tmp_path / "p.json"))
    uso.registrar_lento("_x", 0.5)
    uso.registrar_erro("_y")
    uso.contar("quedas", "telegram")
    uso.guardar_pendente()
    assert (tmp_path / "p.json").exists()
    # "fecha" o programa: a memoria some
    uso._lentos.clear(); uso._erros.clear(); uso._contagens.clear()
    # nova abertura, ja com uma medida propria
    uso.registrar_lento("_x", 0.9)
    uso.carregar_pendente()
    assert uso._lentos["_x"] == [2, 0.9]
    assert uso._erros == {"_y": 1}
    assert uso._contagens["quedas"] == {"telegram": 1}
    assert not (tmp_path / "p.json").exists()     # nao conta duas vezes


def test_sem_medidas_apaga_o_arquivo_e_arquivo_ruim_e_ignorado(
        cfg, tmp_path, monkeypatch):
    arq = tmp_path / "p.json"
    monkeypatch.setattr(uso, "_arquivo", lambda: str(arq))
    arq.write_text("{ruim", encoding="utf-8")
    uso.carregar_pendente()                       # nao quebra
    uso.registrar_erro("_y")
    uso.guardar_pendente()
    assert arq.exists()
    uso._erros.clear()
    uso.guardar_pendente()
    assert not arq.exists()


def test_gravacao_so_com_a_caixa_marcada(cfg, monkeypatch):
    monkeypatch.setattr(uso, "_gravador_ligado", False)
    uso.iniciar_gravacao(cfg)
    assert uso._gravador_ligado is False


def test_experimentais_so_as_ligadas(cfg):
    ex = [o.chave for o in config.OPCOES
          if o.categoria == config.CATEGORIA_EXPERIMENTAL and not o.escolhas]
    assert ex
    assert uso.montar(cfg)["experimentais"] == []
    cfg.set(ex[0], True)
    assert uso.montar(cfg)["experimentais"] == [ex[0]]


def test_texto_para_ver_mostra_o_json_exato(cfg):
    d = uso.montar(cfg, conversas=10)
    t = uso.texto_para_ver(d)
    assert "Não vai nenhuma mensagem" in t
    assert json.dumps(d, ensure_ascii=False, indent=1) in t


def test_so_envia_uma_vez_por_dia_e_com_a_caixa_marcada(cfg):
    assert not uso.devido(cfg, 1_000_000)
    cfg.set("compartilhar_uso", True)
    assert uso.devido(cfg, 1_000_000)
    cfg.set("uso_ultimo_envio", 1_000_000)
    assert not uso.devido(cfg, 1_000_000 + 3600)
    assert uso.devido(cfg, 1_000_000 + 24 * 3600)


def test_envio_aceito_zera_as_medidas_e_marca_o_dia(cfg, monkeypatch):
    cfg.set("compartilhar_uso", True)
    uso.registrar_lento("_x", 0.4)
    enviados = []
    pronto = threading.Event()

    def falso(dados):
        enviados.append(dados)
        return True
    monkeypatch.setattr(uso, "_enviar", falso)
    uso.enviar_em_segundo_plano(cfg, uso.montar(cfg))
    for _ in range(100):
        if cfg.get("uso_ultimo_envio"):
            break
        pronto.wait(0.02)
    assert enviados and cfg.get("uso_ultimo_envio") > 0
    assert uso._lentos == {}


def test_envio_que_falha_nao_marca_o_dia_nem_zera(cfg, monkeypatch):
    cfg.set("compartilhar_uso", True)
    uso.registrar_lento("_x", 0.4)

    def falha(dados):
        raise OSError("sem rede")
    monkeypatch.setattr(uso, "_enviar", falha)
    uso.enviar_em_segundo_plano(cfg, uso.montar(cfg))
    threading.Event().wait(0.3)
    assert not cfg.get("uso_ultimo_envio") and "_x" in uso._lentos


def _servidor(resposta, status=200):
    """Um servidor local que responde sempre `resposta` (bytes)."""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(status)
            self.send_header("Content-Length", str(len(resposta)))
            self.end_headers()
            self.wfile.write(resposta)
    s = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


@pytest.mark.parametrize("resposta,esperado", [
    (b'{"ok":true}', True),
    # o Worker antigo respondia 200 a qualquer endereco: nao e envio
    (b"TeleZapp: recebimento de relatos.", False),
    (b'{"erro":"Formato invalido."}', False),
    (b'{"ok":false}', False),
    (b"[]", False),
])
def test_so_conta_como_enviado_com_o_ok_do_worker(monkeypatch, resposta,
                                                  esperado):
    s = _servidor(resposta)
    try:
        monkeypatch.setattr(uso, "ENDERECO",
                            "http://127.0.0.1:%d/uso" % s.server_port)
        assert uso._enviar({"versao": "x"}) is esperado
    finally:
        s.shutdown()


def test_espera_da_autenticacao_sai_do_tempo_de_abertura(monkeypatch):
    import logging
    import telezapp.__main__ as principal
    from telezapp.nucleo import uso
    monkeypatch.setattr(principal, "_INICIO", 100.0)
    monkeypatch.setattr(uso, "INICIO", 1000.0)
    log = logging.getLogger("teste")
    principal._descontar_a_espera(log, 0.05)       # sem protecao: nada
    assert principal._INICIO == 100.0 and uso.INICIO == 1000.0
    principal._descontar_a_espera(log, 3.0)        # Hello levou 3 s
    assert principal._INICIO == 103.0 and uso.INICIO == 1003.0

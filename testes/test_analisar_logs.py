# SPDX-License-Identifier: GPL-3.0-or-later
"""ferramentas/analisar_logs.py: estatisticas a partir de logs de relatos."""
import importlib.util
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "analisar_logs", os.path.join(RAIZ, "ferramentas", "analisar_logs.py"))
al = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(al)

ID = "ABC123DEF456"
W = "whatsmeow.Client.Chamadas"


def _l(hora, nivel, modulo, texto):
    return "2026-11-19 %s %s %s: %s\n" % (hora, nivel, modulo, texto)


LOG = "".join([
    _l("19:30:00", "INFO", "telezapp", "==== TeleZapp 2026.11.18.0 iniciado ===="),
    _l("19:30:01", "WARNING", "telezapp", "a vez anterior terminou sem "
       "fechar normalmente (queda do programa ou do Windows)"),
    _l("19:32:10", "WARNING", W, 'chamadas: meowcaller {"level":"info",'
       '"stanza":"e=0 platform=android t=1 version=2.26.44.90",'
       '"filhos_da_oferta":"audio[enc,rate] net[medium]"}'),
    _l("19:32:11", "WARNING", W, 'chamadas: meowcaller {"controle":"offer",'
       '"atributos":"call-creator=...1@lid call-id=%s device_class=2015",'
       '"filhos":12}' % ID),
    _l("19:32:12", "WARNING", W, "chamadas: chamada %s criada "
       "(entrante=true, com=...1@lid)" % ID),
    _l("19:32:12", "WARNING", W, 'chamadas: meowcaller {"call_id":"%s",'
       '"message":"inbound call advertises video"}' % ID),
    _l("19:32:19", "WARNING", W, "chamadas: chamada %s: fase 3 depois de "
       "7.8s" % ID),
    _l("19:32:20", "WARNING", W, "chamadas: chamada %s: som do outro lado "
       "chegou (primeiro RTP) depois de 8.2s" % ID),
    _l("19:32:50", "WARNING", W, "chamadas: chamada %s encerrada (hangup) "
       "depois de 37.6s: quadros do outro lado=121, do microfone=474" % ID),
    _l("19:32:50", "INFO", "telezapp.janela", "chamada: encerrada desligada "),
    _l("19:33:00", "WARNING", "telezapp.janela", "lento: _abrir demorou "
       "0.50 s"),
    _l("19:33:01", "WARNING", "whatsmeow.Client", "Keepalive timed out"),
    _l("19:33:02", "ERROR", "telezapp.janela", "erro qualquer com Maria"),
])


def test_uma_chamada_de_video_de_android_vira_estatistica(tmp_path):
    (tmp_path / "r1").mkdir()
    (tmp_path / "r1" / "telezapp.log").write_text(LOG, encoding="utf-8")
    (tmp_path / "r1" / "relato.html").write_text("<p>x</p>", encoding="utf-8")
    achados = al.achar_logs([str(tmp_path)])
    assert list(achados) == [str(tmp_path / "r1")]       # so o log
    est = al.Estatisticas()
    for arquivos in achados.values():
        est.ler_relato(arquivos)
    assert est.versoes == {"2026.11.18.0": 1} and est.sem_fechar == 1
    assert len(est.chamadas) == 1
    c = est.chamadas[0]
    assert c["plataforma"] == "android" and c["versao_wa"] == "2.26.44.90"
    assert c["classe"] == 2015 and c["direcao"] == "entrada"
    assert c["tipo"] == "video" and c["resultado"] == "desligada"
    assert c["t_toque_s"] == 7.8 and c["t_som_apos_atender_s"] == 0.4
    assert c["dur_s"] == 37.6
    assert est.lentos["_abrir"] == [1, 0.5]
    assert est.quedas == {"keepalive": 1}
    assert est.registro[("janela", "erro")] == 1
    texto = est.relatorio()
    assert "android 2.26.44.90 → desligada: 1" in texto
    for proibido in (ID, "Maria", "...1@lid"):
        assert proibido not in texto


def test_o_mesmo_trecho_em_dois_relatos_conta_uma_vez(tmp_path):
    for nome in ("r1", "r2"):
        (tmp_path / nome).mkdir()
        (tmp_path / nome / "telezapp.log").write_text(LOG, encoding="utf-8")
    est = al.Estatisticas()
    for arquivos in al.achar_logs([str(tmp_path)]).values():
        est.ler_relato(arquivos)
    assert len(est.chamadas) == 1 and est.quedas == {"keepalive": 1}
    assert est.relatos == 1          # o segundo nao trouxe nenhuma linha nova

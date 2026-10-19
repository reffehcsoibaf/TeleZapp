# SPDX-License-Identifier: GPL-3.0-or-later
"""Contagens e filtro de midias dos detalhes da conversa."""
from telezapp.nucleo import detalhes as d
from telezapp.nucleo import modelos as m


def msg(id, **k):
    base = dict(conta_id="t1", conversa_id="g", id=id, autor="Ana",
                data=1000 + int(id))
    base.update(k)
    return m.Mensagem(**base)


MSGS = [msg("1", texto="oi"),
        msg("2", tipo=m.FOTO, texto="olha https://x.com/a"),
        msg("3", tipo=m.VIDEO),
        msg("4", tipo=m.OUTRO, texto="contato: Ana, +5551"),
        msg("5", tipo=m.OUTRO, texto="2 contatos: Ana; Bia"),
        msg("6", tipo=m.VOZ), msg("7", tipo=m.AUDIO),
        msg("8", tipo=m.DOCUMENTO), msg("9", tipo=m.FIGURINHA),
        msg("10", texto="veja https://y.com")]


def test_classes_de_uma_mensagem():
    assert d.classes(MSGS[0]) == []
    assert d.classes(MSGS[1]) == ["foto", "link"]
    assert d.classes(MSGS[3]) == ["contato"]
    assert d.classes(MSGS[9]) == ["link"]
    apagada = m.atualizar_extras(msg("11", tipo=m.FOTO), apagada=True)
    assert d.classes(apagada) == []


def test_filtro_traz_o_tipo_pedido_do_mais_novo_para_o_mais_antigo():
    assert [x.id for x in d.midias(MSGS, "foto")] == ["2"]
    assert [x.id for x in d.midias(MSGS, "link")] == ["10", "2"]
    assert [x.id for x in d.midias(MSGS, "contato")] == ["5", "4"]
    todas = [x.id for x in d.midias(MSGS)]
    assert todas == ["10", "9", "8", "7", "6", "5", "4", "3", "2"]
    assert d.midias(MSGS, "voz")[0].id == "6"


def test_estatisticas_contam_por_tipo_e_somam_o_espaco(tmp_path):
    foto = tmp_path / "f.jpg"
    foto.write_bytes(b"x" * 2048)
    registros = [("g", "2", m.FOTO, str(foto), 2048, 1.0),
                 ("g", "3", m.VIDEO, str(tmp_path / "sumiu.mp4"), 99, 1.0)]
    est = d.estatisticas(MSGS, registros)
    assert est["mensagens"] == 10
    assert est["por_tipo"]["foto"] == 1 and est["por_tipo"]["link"] == 2
    assert est["por_tipo"]["contato"] == 2
    assert est["baixadas"]["foto"] == [1, 2048]
    assert est["baixadas"]["video"] == [0, 0]          # o arquivo sumiu
    assert est["bytes_midias"] == 2048 and est["bytes_texto"] > 0
    linhas = d.linhas_de_uso(est)
    assert linhas[0] == "Mensagens guardadas: 10."
    assert "Fotos: 1 (1 baixada, 2 KB)." in linhas
    assert "Vídeos: 1." in linhas
    assert linhas[-1].startswith("Espaço no TeleZapp: ")

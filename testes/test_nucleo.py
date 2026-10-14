# SPDX-License-Identifier: GPL-3.0-or-later
"""Modelos, formatacao, eventos, banco e configuracao."""
import json
import threading
import time

from telezapp import config
from telezapp.armazenamento.banco import Banco
from telezapp.nucleo import eventos as ev
from telezapp.nucleo import modelos as m

AGORA = time.mktime((2026, 10, 13, 15, 0, 0, 0, 0, -1))


def msg(**k):
    base = dict(conta_id="t1", conversa_id="10", id="1", autor="Ana",
                data=AGORA - 60)
    base.update(k)
    return m.Mensagem(**base)


# ----------------------------------------------------------- formatacao
def test_hora_legivel():
    assert m.hora_legivel(AGORA - 60, AGORA) == "14:59"
    assert m.hora_legivel(AGORA - 86400, AGORA).startswith("ontem ")
    assert m.hora_legivel(AGORA - 10 * 86400, AGORA) == "03/10 15:00"
    assert m.hora_legivel(AGORA - 400 * 86400, AGORA).count("/") == 2
    assert m.hora_legivel(0, AGORA) == ""


def test_estilos():
    a = msg(texto="Bom dia!")
    b = msg(id="2", texto="Tudo bem?")
    assert m.formatar(a, m.ESTILO_AUTOR_PRIMEIRO, agora=AGORA) == \
        "Ana, 14:59: Bom dia!"
    assert m.formatar(a, m.ESTILO_CONTEUDO_PRIMEIRO, agora=AGORA) == \
        "Bom dia! Ana, 14:59"
    assert m.formatar(b, m.ESTILO_AUTOR_SO_QUANDO_MUDA, a, AGORA) == \
        "Tudo bem?"
    eu = msg(id="3", minha=True, texto="Tudo", estado=m.LIDA)
    assert m.formatar(eu, m.ESTILO_AUTOR_PRIMEIRO, agora=AGORA) == \
        "Você, 14:59: Tudo, lida"


def test_conteudo_de_midias():
    assert m.conteudo(msg(tipo=m.VOZ, segundos=75)) == \
        "mensagem de voz, 1 minuto e 15 segundos"
    assert m.conteudo(msg(tipo=m.DOCUMENTO, nome_arquivo="a.pdf",
                          tamanho=2048)) == "documento, a.pdf, 2 KB"
    assert m.conteudo(msg(tipo=m.FOTO, texto="praia")) == \
        "foto, legenda: praia"
    assert m.conteudo(msg(tipo=m.OUTRO)) == "mensagem sem suporte ainda"


def test_resposta():
    r = msg(id="5", texto="sim", resposta_a="1")
    assert m.formatar(r, 1, agora=AGORA, respondida="Bruno") == \
        "Ana, 14:59: sim, em resposta a Bruno"
    assert "sim, em resposta a uma mensagem mais antiga" in m.formatar(
        r, 1, agora=AGORA)
    original = msg(id="1", texto="você vai hoje?")
    assert m.formatar(r, 1, agora=AGORA, respondida=original) == \
        'Ana, 14:59: sim, em resposta a Ana: "você vai hoje?"'


def test_rotulo_conversa():
    c = m.Conversa("t1", "10", "Grupo", "telegram", nao_lidas=3)
    assert m.rotulo_conversa(c) == "Grupo, Telegram, 3 não lidas"
    c.nao_lidas = 1
    assert m.rotulo_conversa(c).endswith("1 não lida")


def test_normalizar_telefone():
    assert m.normalizar_telefone("(51) 99999-8888") == "+5551999998888"
    assert m.normalizar_telefone("+55 51 99999 8888") == "+5551999998888"
    assert m.normalizar_telefone("0044 7700 900123") == "+447700900123"
    assert m.normalizar_telefone("123") is None
    assert m.normalizar_telefone("") is None


# --------------------------------------------------------------- eventos
def test_barramento_isola_erros():
    recebidos = []
    b = ev.Barramento()
    b.ouvir(lambda e: 1 / 0)
    b.ouvir(recebidos.append)
    b.publicar(ev.Aviso("t1", "oi"))
    assert recebidos and recebidos[0].texto == "oi"


def test_barramento_usa_entregador():
    usados = []

    def entregar(f, *a):
        usados.append(threading.current_thread().name)
        f(*a)
    b = ev.Barramento(entregar)
    b.ouvir(lambda e: None)
    b.publicar(ev.Aviso("t1", "x"))
    assert usados


# ----------------------------------------------------------------- banco
def test_banco_conversas_e_mensagens(tmp_path):
    b = Banco(str(tmp_path / "t.db"))
    b.salvar_conversas([
        m.Conversa("t1", "10", "Ana", data=AGORA - 10, nao_lidas=2),
        m.Conversa("t1", "20", "Bruno", data=AGORA),
        m.Conversa("w1", "30", "Outra conta"),
    ])
    assert [c.nome for c in b.conversas("t1")] == ["Bruno", "Ana"]
    b.atualizar_conversa("t1", "10", nao_lidas=0)
    assert b.conversas("t1")[1].nao_lidas == 0

    lista = [msg(id=str(i), data=AGORA + i, texto="m%d" % i,
                 minha=(i % 2 == 0)) for i in range(1, 8)]
    b.salvar_mensagens(lista)
    ult = b.mensagens("t1", "10", limite=3)
    assert [x.id for x in ult] == ["5", "6", "7"]
    assert ult[1].minha is True and ult[0].minha is False

    b.salvar_mensagens([msg(id="7", data=AGORA + 7, texto="editada")])
    assert b.mensagens("t1", "10")[-1].texto == "editada"

    b.marcar_lidas_pelo_outro("t1", "10", 4, m.LIDA)
    estados = {x.id: x.estado for x in b.mensagens("t1", "10")}
    assert estados["2"] == m.LIDA and estados["4"] == m.LIDA
    assert estados["6"] == ""

    b.apagar_conta("t1")
    assert b.conversas("t1") == [] and b.mensagens("t1", "10") == []
    assert len(b.conversas("w1")) == 1
    b.fechar()


def test_banco_ids_numericos_ordenam_como_numero(tmp_path):
    b = Banco(str(tmp_path / "t.db"))
    b.salvar_mensagens([msg(id="9", data=AGORA), msg(id="10", data=AGORA)])
    assert [x.id for x in b.mensagens("t1", "10")] == ["9", "10"]


def test_banco_varias_threads(tmp_path):
    b = Banco(str(tmp_path / "t.db"))

    def gravar(k):
        b.salvar_mensagens([msg(id="%d-%d" % (k, i)) for i in range(50)])
    ts = [threading.Thread(target=gravar, args=(k,)) for k in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(b.mensagens("t1", "10", limite=1000)) == 200


# ---------------------------------------------------------------- config
def test_config_e_contas(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path))
    c = config.Config()
    assert c.get("estilo") == 1 and c.contas() == []
    c.salvar_conta({"id": "t1", "servico": "telegram", "telefone": "+55"})
    c.set("som", False)
    c2 = config.Config()
    assert c2.get("som") is False and c2.contas()[0]["id"] == "t1"
    c2.remover_conta("t1")
    assert config.Config().contas() == []


def test_config_corrompida_usa_padroes(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path))
    (tmp_path / "config.json").write_text("{nao e json", encoding="utf-8")
    assert config.Config().get("falar_novas") is True


def test_credenciais_do_arquivo_de_testes(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path))
    arq = tmp_path / "configuracao-telegram.txt"
    arq.write_text("# comentario\nAPI_ID=12345\nAPI_HASH=0123456789abcdef01\n"
                   "TELEFONE=+5551999998888\n", encoding="utf-8")
    c = config.Config()
    assert config.credenciais_telegram(c, str(tmp_path / "nao.txt")) is None
    assert config.credenciais_telegram(c, str(arq)) == (
        12345, "0123456789abcdef01")
    # ficou gravado na configuracao
    salvo = json.loads((tmp_path / "config.json").read_text("utf-8"))
    assert salvo["telegram_api_id"] == 12345
    assert config.telefone_dos_testes(str(arq)) == "+5551999998888"


def test_mascarar_telefone():
    assert config.mascarar_telefone("+5551999998888") == "+55...8888"
    assert "9999" not in config.mascarar_telefone("+5551999998888")


def test_banco_antigo_ganha_a_coluna_remetente(tmp_path):
    import sqlite3
    caminho = str(tmp_path / "antigo.db")
    con = sqlite3.connect(caminho)
    con.executescript("""
        CREATE TABLE mensagens (conta_id TEXT NOT NULL, conversa_id TEXT NOT
        NULL, id TEXT NOT NULL, autor TEXT NOT NULL DEFAULT '', minha INTEGER
        NOT NULL DEFAULT 0, data REAL NOT NULL DEFAULT 0, tipo TEXT NOT NULL
        DEFAULT 'texto', texto TEXT NOT NULL DEFAULT '', segundos INTEGER NOT
        NULL DEFAULT 0, nome_arquivo TEXT NOT NULL DEFAULT '', tamanho INTEGER
        NOT NULL DEFAULT 0, estado TEXT NOT NULL DEFAULT '', resposta_a TEXT
        NOT NULL DEFAULT '', PRIMARY KEY (conta_id, conversa_id, id));
        INSERT INTO mensagens (conta_id, conversa_id, id, texto)
            VALUES ('w1', 'c', '1', 'velha');
    """)
    con.commit()
    con.close()
    b = Banco(caminho)
    velha = b.mensagens("w1", "c")[0]
    assert velha.texto == "velha" and velha.remetente == ""
    b.salvar_mensagens([msg(conta_id="w1", conversa_id="c", id="2",
                            remetente="555@s.whatsapp.net")])
    assert b.mensagens("w1", "c")[-1].remetente == "555@s.whatsapp.net"
    b.fechar()


def test_extrair_links():
    t = ("veja https://exemplo.com/a?b=1, e (www.site.org/x). "
         "De novo: https://exemplo.com/a?b=1! e HTTP://OUTRO.com.")
    assert m.extrair_links(t) == [
        ("https://exemplo.com/a?b=1", "https://exemplo.com/a?b=1"),
        ("https://www.site.org/x", "www.site.org/x"),
        ("HTTP://OUTRO.com", "HTTP://OUTRO.com")]
    assert m.extrair_links("sem link, só www. e texto") == []
    assert m.extrair_links("") == [] and m.extrair_links(None) == []


def test_abrir_link_so_http(monkeypatch):
    from telezapp.interface import dialogos
    abertos = []
    monkeypatch.setattr(dialogos.wx, "LaunchDefaultBrowser",
                        lambda u: abertos.append(u) or True, raising=False)
    assert dialogos.abrir_link("https://a.com") is True
    assert dialogos.abrir_link("file:///c:/windows/x.exe") is False
    assert dialogos.abrir_link("javascript:alert(1)") is False
    assert abertos == ["https://a.com"]


def test_midia_com_link_na_legenda_avisa_e_texto_nao_muda():
    foto = msg(texto="veja https://x.com/a", tipo=m.FOTO)
    assert m.tem_links(foto)
    assert "com link (Enter)" in m.formatar(foto, m.ESTILO_CONTEUDO_PRIMEIRO)
    sem = msg(texto="oi", tipo=m.FOTO)
    assert not m.tem_links(sem)
    assert "com link" not in m.formatar(sem, m.ESTILO_CONTEUDO_PRIMEIRO)
    txt = msg(texto="https://x.com/a")
    assert "com link" not in m.formatar(txt, m.ESTILO_CONTEUDO_PRIMEIRO)


def test_detalhes_mostram_nome_ou_telefone_nunca_o_codigo_do_recibo():
    x = msg(minha=True, texto="oi")
    recibos = [("5551988887777@s.whatsapp.net", "entregue", AGORA),
               ("99887766554433221@lid", "lida", AGORA),
               ("5551900000000@s.whatsapp.net", "lida", AGORA)]
    t = m.detalhes(x, "Grupo", recibos=recibos,
                   nomes={"5551988887777@s.whatsapp.net": "Ana Silva"})
    assert "Entregue a Ana Silva em" in t
    assert "Lida a Contato sem nome em" in t
    assert "Lida a +5551900000000 em" in t
    assert "@" not in t

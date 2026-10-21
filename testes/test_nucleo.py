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
    # datas que o Windows recusa (zero do Go, milissegundos, infinito) nao
    # derrubam nada
    for ruim in (-62135596800, -1, 10 ** 12, 10 ** 18, float("inf")):
        assert m.hora_legivel(ruim, AGORA) == ""
        assert m.texto_presenca("offline", ruim, "recentemente") ==             "visto por último recentemente"
        assert m.texto_presenca("offline", ruim) == ""


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
    assert config.Config().get("falar_novas") is False
    assert config.Config().get("som") is True


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
    assert "com 1 link (Tab)" in m.formatar(foto, m.ESTILO_CONTEUDO_PRIMEIRO)
    sem = msg(texto="oi", tipo=m.FOTO)
    assert not m.tem_links(sem)
    assert "com link" not in m.formatar(sem, m.ESTILO_CONTEUDO_PRIMEIRO)


def test_texto_com_links_e_botoes_de_endereco_avisam_com_tab():
    txt = msg(texto="veja https://x.com/a e https://y.com/b")
    assert [r for r, _ in m.itens_de_link(txt)] == [
        "Link: https://x.com/a", "Link: https://y.com/b"]
    assert "com 2 links (Tab)" in m.formatar(txt, m.ESTILO_CONTEUDO_PRIMEIRO)
    bot = m.guardar_extras(
        msg(texto="oferta https://x.com/a"),
        links=[("https://x.com/a", "aqui")],
        botoes=[("Site", "https://s.com"), ("Repetido", "https://x.com/a"),
                ("App", "tg://resolve?domain=x")])
    # o link escondido aparece com o texto visivel; o endereco repetido e o
    # que nao e http(s) ficam de fora
    assert m.itens_de_link(bot) == [("Link: aqui", "https://x.com/a"),
                                    ("Botão: Site", "https://s.com")]


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


def test_codigo_secreto_das_trancadas():
    from telezapp.nucleo import codigo_secreto as cs
    dados = cs.criar("246813579024")
    assert "246813579024" not in str(dados)                  # so o resumo
    assert cs.confere("246813579024", dados)
    assert not cs.confere("2469", dados)
    assert not cs.confere("246", dados) and not cs.confere("abcd", dados)
    assert not cs.confere("246813579024", None) and not cs.confere("246813579024", {})
    assert cs.valido("1234") and cs.valido("123456789012")
    assert not cs.valido("123") and not cs.valido("1234567890123")
    assert not cs.valido("12a4") and not cs.valido("١٢٣٤")
    assert cs.criar("246813579024")["sal"] != dados["sal"]   # sal novo a cada vez
    import pytest
    with pytest.raises(ValueError):
        cs.criar("12")


def test_anuncio_de_sequencia_configuravel():
    from telezapp.nucleo import modelos as m
    x = m.Mensagem("c", "1", "1", autor="Ana", tipo=m.VOZ, segundos=12)
    assert m.anuncio_sequencia(x, "1,5x") == (
        "Próximo áudio. Tocando mensagem de voz de Ana, 12 segundos, a 1,5x.")
    assert m.anuncio_sequencia(x, proximo=False, tipo=False, duracao=False,
                               mostrar_velocidade=False) == "De Ana."
    assert m.anuncio_sequencia(x, quem=False, duracao=False) == (
        "Próximo áudio. Tocando mensagem de voz.")
    assert m.anuncio_sequencia(x, tipo=False, quem=False, duracao=False,
                               mostrar_velocidade=False) == "Próximo áudio."
    assert m.anuncio_sequencia(x, proximo=False, tipo=False, quem=False,
                               duracao=False, mostrar_velocidade=False) == ""
    minha = m.Mensagem("c", "2", "2", minha=True, tipo=m.VOZ)
    assert m.anuncio_sequencia(minha, proximo=False) == \
        "Tocando sua mensagem de voz."


def test_privacidade_do_whatsapp_regras():
    from telezapp.nucleo import privacidade_conta as pw
    lido = {"last": "contacts", "online": "all", "status": "none",
            "readreceipts": "all", "groupadd": "contact_blacklist"}
    assert not pw.ilegivel(lido) and pw.ilegivel(None) and pw.ilegivel({})
    assert [c.nome for c in pw.desconhecidos(lido)] == ["groupadd"]
    last = pw.CAMPOS[0]
    assert pw.indice(last, "contacts") == 1 and pw.indice(last, "xyz") == -1
    # so entra o que mudou; posicao -1 ou ausente fica como esta
    escolhido = {"last": 2, "online": 0, "readreceipts": 1, "groupadd": -1}
    assert pw.mudancas(lido, escolhido) == [("last", "none"),
                                            ("readreceipts", "none")]
    pedidas = [("last", "none"), ("readreceipts", "none")]
    assert pw.nao_confirmadas(pedidas, dict(lido, last="none")) == \
        ["readreceipts"]
    assert pw.nao_confirmadas(pedidas, None) == ["last", "readreceipts"]
    assert pw.texto_status("contacts", 0) == "Meus contatos"
    assert pw.texto_status("blacklist", 3) == "Meus contatos, exceto 3 pessoas"
    assert pw.texto_status("whitelist", 1) == "Somente 1 pessoa"


def test_privacidade_do_telegram_regras():
    from telezapp.nucleo import privacidade_conta as pw
    from telezapp.provedores.telegram import valor_das_regras

    def regra(nome):
        return type(nome, (), {})()
    assert valor_das_regras([regra("PrivacyValueAllowAll")]) == "all"
    assert valor_das_regras([regra("PrivacyValueAllowContacts"),
                             regra("PrivacyValueDisallowAll")]) == "contacts"
    assert valor_das_regras([regra("PrivacyValueDisallowAll")]) == "none"
    # excecoes por pessoa: so no aplicativo, a caixa fica sem escolha
    assert valor_das_regras([regra("PrivacyValueAllowUsers"),
                             regra("PrivacyValueDisallowAll")]) is None
    assert valor_das_regras([]) is None and valor_das_regras(None) is None
    nomes = [c.nome for c in pw.campos_do("telegram")]
    assert nomes == ["last", "status", "readreceipts", "groupadd"]   # sem online
    assert pw.campos_do("telegram")[0].rotulo.endswith("visto por último e online")
    assert len(pw.campos_do("whatsapp")) == 5


def test_nova_mensagem_tipo_de_destino_e_candidatos():
    from telezapp.nucleo import modelos as m
    from telezapp.nucleo import nova_mensagem as nm
    assert nm.tipo_de_destino("@ana_99") == nm.USUARIO
    assert nm.tipo_de_destino("(51) 99999-8888") == nm.TELEFONE
    assert nm.tipo_de_destino("+55 51 99999 8888") == nm.TELEFONE
    assert nm.tipo_de_destino("Ana Souza") == nm.NOME
    assert nm.tipo_de_destino("@") == nm.NOME
    contatos = [("t1", "10", "Ana Souza", "+5551999998888")]
    conversas = [m.Conversa("t1", "10", "Ana Souza", tipo="privada"),
                 m.Conversa("t1", "20", "Ana Maria", tipo="privada"),
                 m.Conversa("t1", "30", "Anagrupo", tipo="grupo")]
    assert nm.candidatos("ana", contatos, conversas) == [
        ("10", "Ana Souza", "+5551999998888"),
        ("20", "Ana Maria", "")]                    # sem repetir, sem grupo
    assert nm.candidatos("maria", contatos, conversas) == [
        ("20", "Ana Maria", "")]
    assert nm.candidatos("+5551999998888", contatos, conversas) == [
        ("10", "Ana Souza", "+5551999998888")]
    assert nm.candidatos("99999 8888", contatos, conversas) == [
        ("10", "Ana Souza", "+5551999998888")]    # so os digitos contam
    assert len(nm.candidatos("", contatos, conversas)) == 2   # vazio: todos
    assert nm.rotulo("Ana", "+55") == "Ana, +55" and nm.rotulo("Ana") == "Ana"
    assert nm.candidatos("zzz", contatos, conversas) == []


# ------------------------------------------------- copiar por tipo de conteudo
def test_copiar_so_texto_tem_um_item():
    assert m.conteudos_copiaveis(msg(texto="oi")) == [
        ("texto", "Copiar texto", "oi")]


def test_copiar_foto_com_legenda_e_link_tem_um_item_por_tipo():
    foto = msg(tipo=m.FOTO, texto="veja https://x.com/a")
    assert m.conteudos_copiaveis(foto) == [
        ("texto", "Copiar legenda", "veja https://x.com/a"),
        ("midia", "Copiar foto", ""),
        ("link", "Copiar link", "https://x.com/a")]


def test_copiar_midia_sem_legenda_nem_link_so_a_midia():
    assert m.conteudos_copiaveis(msg(tipo=m.VOZ, texto="")) == [
        ("midia", "Copiar mensagem de voz", "")]
    assert [t for t, _, _ in m.conteudos_copiaveis(
        msg(tipo=m.DOCUMENTO))] == ["midia"]


def test_copiar_varios_links_diz_qual_e_qual():
    txt = msg(texto="https://a.com e https://b.com")
    itens = m.conteudos_copiaveis(txt)
    assert [t for t, _, _ in itens] == ["texto", "link", "link"]
    assert itens[1][2] == "https://a.com" and itens[2][2] == "https://b.com"
    assert itens[1][1] != itens[2][1]


def test_copiar_sem_nada_cai_no_texto_falado():
    apagada = m.atualizar_extras(msg(texto="x"), apagada=True)
    assert m.conteudos_copiaveis(apagada) == [
        ("texto", "Copiar texto", "mensagem apagada")]
    outro = msg(tipo=m.OUTRO, texto="")
    assert m.conteudos_copiaveis(outro)[0][0] == "texto"


# --------------------------------------------------- salvar a conversa (zip)
def test_salvar_conversa_grava_texto_e_midias(tmp_path):
    import zipfile
    from telezapp.nucleo import exportar
    foto = tmp_path / "f.jpg"
    foto.write_bytes(b"JPG")
    conv = m.Conversa("t1", "10", "Ana/Silva", "whatsapp")
    msgs = [msg(id="1", texto="oi\ntudo bem", data=AGORA),
            msg(id="2", tipo=m.FOTO, texto="olha", nome_arquivo="f.jpg",
                minha=True, data=AGORA + 5),
            msg(id="3", tipo=m.VOZ, data=AGORA + 9)]
    destino = tmp_path / "saida.zip"
    n, midias = exportar.gravar_zip(
        str(destino), conv, msgs, lambda x: str(foto) if x.id == "2" else None)
    assert (n, midias) == (3, 1)
    with zipfile.ZipFile(destino) as z:
        nomes = z.namelist()
        texto = z.read("conversa.txt").decode("utf-8-sig")
    assert any(x.startswith("midias/") and x.endswith("_f.jpg")
               for x in nomes)
    assert "Ana: oi\n    tudo bem" in texto
    assert "Você: foto, legenda: olha (midias/" in texto
    assert "mensagem de voz" in texto
    assert exportar.nome_sugerido(conv) == "Conversa com Ana_Silva.zip"


def test_salvar_conversa_com_erro_nao_deixa_arquivo(tmp_path):
    import pytest
    from telezapp.nucleo import exportar
    conv = m.Conversa("t1", "10", "Ana")
    destino = tmp_path / "x.zip"

    def quebra(x):
        raise RuntimeError("falhou")
    with pytest.raises(RuntimeError):
        exportar.gravar_zip(str(destino), conv,
                            [msg(tipo=m.FOTO)], quebra)
    assert not destino.exists()


def test_salvar_conversa_identifica_quem_enviou():
    from telezapp.nucleo import exportar as ex
    priv = m.Conversa("t1", "10", "Ana Souza", "whatsapp", "privada")
    grupo = m.Conversa("t1", "g", "Turma", "whatsapp", "grupo")
    sem_autor = msg(autor="", remetente="5551999998888@s.whatsapp.net")
    assert m.quem_enviou(msg(minha=True), priv) == "Você"
    assert m.quem_enviou(msg(autor="Bia"), grupo) == "Bia"
    assert m.quem_enviou(sem_autor, priv) == "Ana Souza"
    assert m.quem_enviou(sem_autor, grupo, lambda x: "Carlos") == "Carlos"
    assert m.quem_enviou(sem_autor, grupo) == "+5551999998888"
    # o endereco interno (@lid) nunca vai para a lista nem para a fala
    assert m.quem_enviou(msg(autor="", remetente="101198187253781@lid"),
                         grupo) == "Participante final 3781"
    assert m.quem_enviou(msg(autor=""), grupo) == "Desconhecido"


def test_mensagem_que_o_telezapp_entende_nao_diz_sem_suporte():
    assert m.conteudo(msg(tipo=m.OUTRO, texto="contato: Ana, +5551")) == \
        "contato: Ana, +5551"
    assert m.conteudo(msg(tipo=m.OUTRO, texto="localização")) == "localização"
    assert m.conteudo(msg(tipo=m.OUTRO, texto="tipo do WhatsApp: xyz")) == \
        "mensagem sem suporte ainda, tipo do WhatsApp: xyz"
    assert m.conteudo(msg(tipo=m.OUTRO, texto="")) == \
        "mensagem sem suporte ainda"


# ------------------------------------------------------------- encaminhar
def test_encaminhar_prepara_texto_midia_baixada_e_explica_o_resto(tmp_path):
    from telezapp.nucleo import encaminhar as enc
    arq = tmp_path / "f.jpg"
    arq.write_bytes(b"JPG")
    item, _ = enc.preparar(msg(texto="oi"), lambda x: None)
    assert (item.tipo, item.texto) == ("texto", "oi")
    foto = msg(tipo=m.FOTO, texto="praia")
    item, _ = enc.preparar(foto, lambda x: str(arq))
    assert (item.tipo, item.caminho, item.texto) == ("arquivo", str(arq),
                                                     "praia")
    item, motivo = enc.preparar(foto, lambda x: None)
    assert item is None and "não baixado" in motivo
    voz, _ = enc.preparar(msg(tipo=m.VOZ, texto="x"), lambda x: str(arq))
    assert voz.texto == ""                       # voz nao tem legenda
    contato, _ = enc.preparar(msg(tipo=m.OUTRO, texto="contato: Ana"),
                              lambda x: None)
    assert contato.texto == "contato: Ana"
    apagada = m.atualizar_extras(msg(texto="x"), apagada=True)
    assert enc.preparar(apagada, lambda x: None)[0] is None


def test_encaminhar_destinos_so_de_contas_conectadas_sem_repetir():
    from telezapp.nucleo import encaminhar as enc
    conversas = [m.Conversa("a", "1", "Bia"), m.Conversa("a", "2", "Ana"),
                 m.Conversa("b", "3", "Caio"),
                 m.Conversa("a", "9", "Secreta", trancada=True)]
    contatos = [("a", "1", "Bia", ""), ("a", "7", "Dora", "+55"),
                ("b", "8", "Eva", "")]
    d = enc.destinos(conversas, contatos, lambda c: c == "a")
    assert [x[2] for x in d] == ["Ana", "Bia", "Dora"]
    assert [x[2] for x in enc.filtrar(d, "bi")] == ["Bia"]
    assert len(enc.destinos(conversas, [], lambda c: True,
                            trancadas=True)) == 4


def test_texto_do_status_da_pessoa():
    agora = time.mktime((2026, 10, 19, 15, 0, 0, 0, 0, -1))
    hoje = time.mktime((2026, 10, 19, 14, 32, 0, 0, 0, -1))
    ontem = time.mktime((2026, 10, 18, 9, 5, 0, 0, 0, -1))
    antes = time.mktime((2026, 10, 12, 9, 5, 0, 0, 0, -1))
    ano_passado = time.mktime((2025, 3, 1, 9, 5, 0, 0, 0, -1))
    assert m.texto_presenca("online") == "online"
    assert m.texto_presenca("offline", hoje, agora=agora) == \
        "visto por último hoje às 14:32"
    assert m.texto_presenca("offline", ontem, agora=agora) == \
        "visto por último ontem às 09:05"
    assert m.texto_presenca("offline", antes, agora=agora) == \
        "visto por último em 12/10 às 09:05"
    assert m.texto_presenca("offline", ano_passado, agora=agora) == \
        "visto por último em 01/03/2025"
    assert m.texto_presenca("offline", aprox="recentemente") == \
        "visto por último recentemente"
    assert m.texto_presenca("offline") == ""          # escondido
    assert m.texto_presenca("digitando") == "digitando"
    assert m.texto_presenca("gravando") == "gravando áudio"
    assert m.texto_presenca("digitando", quem="Ana") == "Ana está digitando"
    assert m.texto_presenca("parou") == ""


def test_busca_de_emoji_por_nome_em_portugues():
    from telezapp.nucleo import emojis
    assert emojis.buscar("joinha")[0].simbolo == "👍"
    assert emojis.buscar("coração vermelho")[0].simbolo == "❤️"
    assert emojis.buscar("CORACAO verm")[0].simbolo == "❤️"      # sem acento
    assert emojis.buscar("rindo")[0].simbolo == "😂" or any(
        e.simbolo == "😂" for e in emojis.buscar("rindo"))
    nomes = [e.nome for e in emojis.buscar("bolo")]
    assert "bolo de aniversário" in nomes
    assert not any("símbolo" in n for n in nomes)       # so inicio de palavra
    assert emojis.buscar("zzzzzz") == []
    assert len(emojis.buscar("", 50)) == 50
    assert not any(any("\U0001F3FB" <= c <= "\U0001F3FF" for c in e.simbolo)
                   for e in emojis.todos())              # sem tons de pele
    assert emojis.nome_de("👍") == "polegar para cima"
    assert emojis.nome_de("❤") == emojis.nome_de("❤️")   # com ou sem variacao
    assert emojis.nome_de("xyz") == "xyz"
    assert all(e in [x.simbolo for x in emojis.todos()]
               for e in emojis.RAPIDOS)


def test_textos_das_chamadas_do_whatsapp():
    from telezapp.nucleo import chamadas as ch
    assert ch.texto_na_conversa(False, "tocando") == \
        "Chamada de voz recebida, tocando"
    assert ch.texto_na_conversa(True, "perdida") == "Chamada de vídeo perdida"
    assert ch.texto_na_conversa(False, "recusada") == \
        "Chamada de voz recusada"
    assert ch.texto_na_conversa(False, "atendida", 65) == \
        "Chamada de voz atendida em outro aparelho, durou 1 minuto e 5 segundos"
    assert ch.texto_na_conversa(False, "atendida") == \
        "Chamada de voz atendida em outro aparelho"
    aviso = ch.texto_do_aviso("Ana", True)
    assert aviso.startswith("Ana está te chamando por vídeo.")
    assert "atenda em outro dispositivo ou abra uma conversa" in aviso
    assert "por voz" in ch.texto_do_aviso("", False) and \
        ch.texto_do_aviso("", False).startswith("Alguém")
    assert ch.texto_do_fim("Ana", False, "perdida") == \
        "A chamada de voz de Ana terminou sem ser atendida."


def test_quem_ja_falava_mensagens_novas_continua_ouvindo_tudo(tmp_path):
    import json
    from telezapp import config
    caminho = tmp_path / "config.json"
    caminho.write_text(json.dumps({"falar_novas": True}), encoding="utf-8")
    cfg = config.Config(str(caminho))
    assert cfg.get("falar_novas_outras_conversas") is True
    assert cfg.get("falar_novas_fora_do_telezapp") is True
    caminho.write_text(json.dumps({"falar_novas": True,
                                   "falar_novas_outras_conversas": False}),
                       encoding="utf-8")
    assert config.Config(str(caminho)).get(
        "falar_novas_outras_conversas") is False        # escolha respeitada
    caminho.write_text("{}", encoding="utf-8")
    novo = config.Config(str(caminho))
    assert novo.get("falar_novas_fora_do_telezapp") is False


def test_tamanho_do_texto_da_ia_na_linha_da_mensagem():
    longa = "palavra " * 400                     # ~3200 letras
    foto = m.Mensagem("c", "v", "1", tipo=m.FOTO)
    voz = m.Mensagem("c", "v", "2", tipo=m.VOZ)
    m.atualizar_extras(foto, ia={"genero": "imagem", "texto": longa})
    m.atualizar_extras(voz, ia={"genero": "audio", "texto": longa})
    try:
        m.definir_limites_ia(0, 1000)                       # padrao
        assert "mostra tudo" not in m.trecho_da_ia(foto)    # descricao inteira
        assert longa.strip() in m.trecho_da_ia(foto)
        assert "mostra tudo" in m.trecho_da_ia(voz)
        assert len(m.trecho_da_ia(voz)) < 1100
        m.definir_limites_ia(300, 0)
        assert "mostra tudo" in m.trecho_da_ia(foto)
        assert len(m.trecho_da_ia(foto)) < 400
        assert longa.strip() in m.trecho_da_ia(voz)
    finally:
        m.definir_limites_ia(0, 1000)


def test_filtro_status_mostra_so_as_conversas_de_status():
    pessoa = m.Conversa("c", "5551@s.whatsapp.net", "Ana", "whatsapp")
    status = m.Conversa("c", "status:5551@s.whatsapp.net", "Status de Ana",
                        "whatsapp", "status", nao_lidas=2)
    assert any(t == "status" for t, _ in m.FILTROS_TIPO)
    assert m.passa_filtro(status, "status") and not m.passa_filtro(
        pessoa, "status")
    for tipo in ("todas", "nao_lidas", "pessoais", "grupos", "canais",
                 "fixadas", "silenciadas"):
        assert not m.passa_filtro(status, tipo), tipo      # fora das outras
    assert m.rotulo_conversa(status) == \
        "Status de Ana, WhatsApp, 2 não vistos"
    status.nao_lidas = 1
    assert m.rotulo_conversa(status).endswith("1 não visto")


def test_previa_de_link_na_linha_e_nos_detalhes():
    x = m.Mensagem("c", "v", "1", autor="Ana", data=1760000000,
                   texto="olha https://a.com/x")
    assert m.trecho_da_previa(x) == ""
    m.guardar_extras(x, previa=m.previa_de_link(
        "https://a.com/x", "  Título   legal ", "Uma descrição\nem duas linhas.",
        "A.com"))
    try:
        m.definir_modo_previa("completa")
        assert m.trecho_da_previa(x) == \
            "prévia do link: Título legal. Uma descrição em duas linhas"
        assert "prévia do link: Título legal" in m.formatar(
            x, m.ESTILO_AUTOR_PRIMEIRO)
        m.definir_modo_previa("titulo")
        assert m.trecho_da_previa(x) == "prévia do link: Título legal"
        m.definir_modo_previa("nenhuma")
        assert m.trecho_da_previa(x) == ""
        assert "prévia" not in m.formatar(x, m.ESTILO_AUTOR_PRIMEIRO)
        det = m.detalhes(x, "Ana")                 # nos detalhes sempre
        assert "Prévia do link: Título legal - A.com" in det
        assert "Descrição da prévia: Uma descrição em duas linhas." in det
        assert "Endereço da prévia: https://a.com/x" in det
        m.definir_modo_previa("invalido")
        assert m.MODO_PREVIA[0] == "completa"
        # a previa sobrevive a regravar os outros extras, e sem titulo nem
        # descricao nao ha previa
        m.guardar_extras(x, links=[("https://a.com/x", "https://a.com/x")])
        assert m.extras_de(x)["previa"]["titulo"] == "Título legal"
        assert m.previa_de_link("https://a.com", "", "  ") == {}
        longa = m.Mensagem("c", "v", "2", texto="x")
        m.guardar_extras(longa, previa=m.previa_de_link(
            "u", "T", "palavra " * 200))
        assert len(m.trecho_da_previa(longa)) < 440
    finally:
        m.definir_modo_previa("completa")


def test_conferir_o_que_vai_ser_publicado_como_status(tmp_path):
    from telezapp.nucleo import publicar_status as ps
    foto = tmp_path / "f.jpg"
    foto.write_bytes(b"\xff\xd8\xff" + b"0" * 50)
    doc = tmp_path / "a.pdf"
    doc.write_bytes(b"%PDF-1")
    # WhatsApp: so texto, ou foto, ou os dois
    anexo, texto, erro = ps.validar("whatsapp", "  oi  ", "")
    assert (anexo, texto, erro) == (None, "oi", "")
    anexo, texto, erro = ps.validar("whatsapp", "", str(foto))
    assert anexo.tipo == "foto" and not erro
    assert "Escreva o texto" in ps.validar("whatsapp", "  ", "")[2]
    assert "foto ou vídeo" in ps.validar("whatsapp", "x", str(doc))[2]
    assert "não foi encontrado" in ps.validar("whatsapp", "x",
                                              str(tmp_path / "nao"))[2]
    assert "passa de 700" in ps.validar("whatsapp", "a" * 701, "")[2]
    # Telegram: exige foto ou video, com legenda curta
    assert "precisa de uma foto" in ps.validar("telegram", "so texto", "")[2]
    assert not ps.validar("telegram", "legenda", str(foto))[2]
    assert "passa de 200" in ps.validar("telegram", "a" * 201, str(foto))[2]


# ------------------------------------------------ mensagens temporarias
def test_periodos_e_texto_das_temporarias():
    assert m.texto_periodo(0) == "desligadas"
    assert m.texto_periodo(86400) == "24 horas"
    assert m.texto_periodo(604800) == "7 dias"
    assert m.texto_periodo(7776000) == "90 dias"
    assert m.texto_periodo(2678400) == "1 mês"
    assert m.texto_periodo(3 * 86400) == "3 dias"
    assert m.texto_periodo(7200) == "2 horas"
    assert [s for s, _ in m.periodos_temporarias("whatsapp")] == [
        0, 86400, 604800, 7776000]
    assert [s for s, _ in m.periodos_temporarias("telegram")] == [
        0, 86400, 604800, 2678400]
    assert m.expira_em(1000, 604800) == 1000 + 604800
    assert m.expira_em(1000, 0) == 0.0 and m.expira_em(0, 60) == 0.0


def test_mensagem_temporaria_na_linha_e_nos_detalhes():
    x = m.Mensagem("c", "1", "1", data=AGORA, texto="oi", expira=AGORA + 3600)
    assert "(temporária)" in m.formatar(x, 1)
    texto = m.texto_temporaria(x, AGORA)
    assert texto.startswith("temporária, some ") and "às" in texto
    assert "Mensagem temporária, some" in m.detalhes(x, "Ana", AGORA)
    assert m.texto_temporaria(m.Mensagem("c", "1", "2"), AGORA) == ""
    assert "(temporária)" not in m.formatar(
        m.Mensagem("c", "1", "2", data=AGORA, texto="oi"), 1)
    vencida = m.Mensagem("c", "1", "3", data=AGORA, expira=AGORA - 5)
    assert "já passou do prazo" in m.texto_temporaria(vencida, AGORA)


# ------------------------------------------------ registro sem telefones
def test_mascarar_texto_troca_telefones_e_enderecos_pelo_fim():
    from telezapp import config
    mt = config.mascarar_texto
    assert mt("conversa=556136863608@s.whatsapp.net remetente="
              "119975851360270@lid") == \
        "conversa=...3608@s.whatsapp.net remetente=...0270@lid"
    # grupo: o numero antes do traco e de quem o criou
    assert mt("557791063633-1577487873@g.us/3EB09A44BBE71D332F35B5 de "
              "140844996767940:58@lid") == \
        "...3633-1577487873@g.us/3EB09A44BBE71D332F35B5 de ...7940:58@lid"
    assert mt("5551999998888.0:12@s.whatsapp.net") == \
        "...8888.0:12@s.whatsapp.net"
    assert mt("conta +5551999998888 pronta") == "conta +55...8888 pronta"
    # o que nao e telefone nem endereco fica como esta
    assert mt("id 12345678901, 1234567 ms, ip 192.168.0.10, 123@newsletter, "
              "3EB0827E0A26817AE5571B") == \
        "id 12345678901, 1234567 ms, ip 192.168.0.10, 123@newsletter, " \
        "3EB0827E0A26817AE5571B"
    assert mt(5551) == "5551"


def test_formatador_do_registro_mascara_ate_a_excecao():
    import io
    import logging
    from telezapp import config
    saida = io.StringIO()
    h = logging.StreamHandler(saida)
    h.setFormatter(config.FormatadorSemTelefones("%(levelname)s %(message)s"))
    lg = logging.getLogger("teste-mascara")
    lg.propagate = False
    lg.addHandler(h)
    try:
        try:
            raise ValueError("falhou em 5511953057252@s.whatsapp.net")
        except ValueError:
            lg.error("conversa %s e +5551999998888", "556136863608@s.whatsapp.net",
                     exc_info=True)
    finally:
        lg.removeHandler(h)
    texto = saida.getvalue()
    assert "...3608@s.whatsapp.net e +55...8888" in texto
    assert "ValueError: falhou em ...7252@s.whatsapp.net" in texto
    for numero in ("556136863608", "5511953057252", "5551999998888"):
        assert numero not in texto

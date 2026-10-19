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
    dados = cs.criar("2468")
    assert "2468" not in str(dados)                  # so o resumo
    assert cs.confere("2468", dados)
    assert not cs.confere("2469", dados)
    assert not cs.confere("246", dados) and not cs.confere("abcd", dados)
    assert not cs.confere("2468", None) and not cs.confere("2468", {})
    assert cs.valido("1234") and cs.valido("123456789012")
    assert not cs.valido("123") and not cs.valido("1234567890123")
    assert not cs.valido("12a4") and not cs.valido("١٢٣٤")
    assert cs.criar("2468")["sal"] != dados["sal"]   # sal novo a cada vez
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
    assert m.quem_enviou(msg(autor="", remetente="1234@lid"),
                          grupo) == "1234@lid"
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

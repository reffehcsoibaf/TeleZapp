# SPDX-License-Identifier: GPL-3.0-or-later
"""Formatacao escrita no texto das mensagens (sem wx)."""
from telezapp.nucleo import formatacao as f
from telezapp.nucleo import modelos as m


def anuncia(t):
    return f.aplicar(t, f.ANUNCIAR)


def tira(t):
    return f.aplicar(t, f.TIRAR)


def test_original_nao_mexe_em_nada():
    t = "**negrito** e *outro* e _itálico_ e `código`"
    assert f.aplicar(t, f.ORIGINAL) == t
    assert f.aplicar(t, "qualquer coisa") == t


def test_o_exemplo_do_markdown_com_negrito_duplo():
    t = ("Serve para **proteger a lista dos seus arquivos**. É o item "
         "\"Guardar o índice\".\n\n**O problema que resolve:** no Telegram.")
    r = anuncia(t)
    assert "negrito: proteger a lista dos seus arquivos." in r
    assert "negrito: O problema que resolve: no Telegram." in r or \
        "negrito: O problema que resolve:" in r
    assert "*" not in r
    assert "*" not in tira(t) and "proteger a lista dos seus arquivos." in tira(t)


def test_whatsapp_negrito_italico_tachado_e_codigo():
    assert anuncia("oi *tudo bem* com _você_ e ~ele~") == \
        "oi negrito: tudo bem com itálico: você e tachado: ele"
    assert anuncia("rode `pip install x` agora") == \
        "rode código: pip install x agora"
    assert tira("oi *tudo bem* com _você_ e ~ele~") == \
        "oi tudo bem com você e ele"


def test_titulo_e_itens_de_lista():
    t = "# Resumo\n- primeiro\n* segundo\n  - aninhado"
    assert anuncia(t) == "título: Resumo\nitem: primeiro\nitem: segundo\n" \
        "  item: aninhado"
    assert tira(t) == "Resumo\n- primeiro\n- segundo\n  - aninhado"


def test_nao_mexe_no_que_nao_e_formatacao():
    for t in ("nome_do_arquivo_final.txt", "só um * aqui", "a * b",
              "https://site.com/a_b_c?x=*y*", "preço: R$ 5 - 3 = 2",
              "_ solto", "a ~ b", "e-mail: ana_silva_@x.com"):
        assert anuncia(t) == t, t
        assert tira(t) == t, t


def test_codigo_protege_o_que_parece_formatacao():
    assert anuncia("use `a*b*c` e *isto*") == "use código: a*b*c e negrito: isto"
    bloco = "veja:\n```py\nx = 2 * 3 * 4\n```\nfim"
    assert anuncia(bloco) == "veja:\ncódigo: x = 2 * 3 * 4\nfim"


def test_trecho_longo_diz_onde_acaba():
    longo = " ".join(["palavra"] * 10)
    assert anuncia("*" + longo + "*") == "negrito: %s, fim do negrito" % longo
    assert anuncia("*curto aqui*") == "negrito: curto aqui"


def test_conteudo_da_mensagem_segue_a_opcao_e_a_copia_nao_muda():
    msg = m.Mensagem("t1", "1", "1", autor="Ana", texto="oi *tudo* bem",
                     data=1_700_000_000)
    try:
        m.definir_formatacao("anunciar")
        assert m.conteudo(msg) == "oi negrito: tudo bem"
        assert m.texto_visivel(msg, formatado=False) == "oi *tudo* bem"
        assert m.conteudos_copiaveis(msg)[0][2] == "oi *tudo* bem"
        m.definir_formatacao("tirar")
        assert m.conteudo(msg) == "oi tudo bem"
        m.definir_formatacao("invalido")
        assert m.conteudo(msg) == "oi *tudo* bem"
    finally:
        m.definir_formatacao("original")


def test_opcao_padrao_e_original():
    from telezapp import config
    o = next(o for o in config.OPCOES
             if o.chave == "formatacao_das_mensagens")
    assert o.padrao == "original"
    assert [v for v, _ in o.escolhas] == ["original", "anunciar", "tirar"]


def test_asterisco_entre_numeros_e_conta_de_vezes():
    assert anuncia("a conta é 2*3*4 = 24 e 5 * 3 = 15") ==         "a conta é 2 vezes 3 vezes 4 = 24 e 5 vezes 3 = 15"
    assert tira("a conta é 2*3*4 = 24") == "a conta é 2*3*4 = 24"
    assert f.aplicar("2*3", f.ORIGINAL) == "2*3"
    # negrito de verdade continua negrito, e dentro de codigo nao e conta
    assert anuncia("vale *3* vezes") == "vale negrito: 3 vezes"
    assert anuncia("use `2*3` aqui") == "use código: 2*3 aqui"

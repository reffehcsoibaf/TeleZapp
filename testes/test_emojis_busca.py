# SPDX-License-Identifier: GPL-3.0-or-later
"""Busca de emojis por sinonimos e termos equivalentes: palavras-chave do CLDR,
sinonimos a mao, plural, acento e a ordem dos resultados."""
from telezapp.nucleo import emojis
from telezapp.nucleo import emojis_cldr_pt


def achados(texto, limite=0):
    return [e.simbolo for e in emojis.buscar(texto, limite)]


def test_sinonimos_do_cldr_acham_o_emoji_que_o_nome_nao_diz():
    assert "😂" in achados("kkk")
    assert "🤣" in achados("gargalhada")
    assert "🎂" in achados("aniversario") and "🎂" in achados("aniversário")
    assert "👋" in achados("tchau")
    assert "🙏" in achados("obrigada")
    assert "🧑‍⚕️" in achados("medico") or "👨‍⚕️" in achados("médico")


def test_sinonimos_escritos_a_mao_continuam_valendo():
    assert achados("joinha", 1) == ["👍"]
    assert "🥹" in achados("saudade") and "🫂" in achados("saudade")


def test_plural_acha_o_singular():
    assert set(achados("risada")) <= set(achados("risadas"))
    assert "😂" in achados("risadas")


def test_ingles_continua_achando():
    assert "❤️" in achados("red heart")
    assert "🍕" in achados("pizza")


def test_palavras_digitadas_precisam_casar_todas():
    so_uma = set(achados("rosto"))
    duas = set(achados("rosto chorando"))
    assert duas and duas < so_uma
    assert achados("zzzzqqqq") == []


def test_a_palavra_inteira_vem_antes_do_prefixo():
    # "oi" e palavra inteira de "oi" (👋) e comeco de "oito"
    assert achados("oi", 1) == ["👋"]
    assert "✴️" in achados("oi")       # o que comeca com "oi" tambem aparece


def test_quem_casa_com_o_nome_vem_antes_de_quem_casa_so_pelo_cldr():
    lista = emojis.buscar("bolo", 0)
    assert lista[0].simbolo == "🎂"
    nomes = [e for e in lista if "bolo" in e.palavras_nome]
    so_cldr = [e for e in lista if "bolo" not in e.palavras_base]
    if nomes and so_cldr:
        assert lista.index(nomes[-1]) < lista.index(so_cldr[0])


def test_sem_texto_devolve_todos():
    assert len(emojis.buscar("", 0)) == len(emojis.todos())
    assert len(emojis.buscar("  ", 5)) == 5


def test_arquivo_do_cldr_gerado_traz_o_aviso_e_a_maioria_dos_emojis():
    assert "Unicode-3.0" in emojis_cldr_pt.__doc__
    assert "kkk" in emojis_cldr_pt.PALAVRAS["😂"].split()
    simbolos = {e.simbolo.replace(chr(0xFE0F), "") for e in emojis.todos()}
    com_palavras = len(simbolos & set(emojis_cldr_pt.PALAVRAS))
    assert com_palavras >= 0.95 * len(simbolos)


def test_sem_o_arquivo_do_cldr_a_busca_segue_com_o_resto(monkeypatch):
    monkeypatch.setattr(emojis, "_cldr", {})
    monkeypatch.setattr(emojis, "_lista", None)
    monkeypatch.setattr(emojis, "_familias", {})
    assert achados("joinha", 1) == ["👍"]
    assert "😂" in achados("rindo")


# ------------------------------------------------------------ categorias
def test_toda_categoria_tem_emojis_e_todo_emoji_tem_categoria():
    """Pedido do Wesley: categorias nos emojis. As do Unicode (emoji-test),
    na ordem do Unicode; nenhum emoji da lista fica de fora."""
    nomes = dict(emojis.categorias())
    assert list(nomes.values())[:3] == ["Carinhas e emoções",
                                        "Pessoas e corpo",
                                        "Animais e natureza"]
    assert len(nomes) == 9
    soma = 0
    for chave in nomes:
        da = emojis.da_categoria(chave)
        assert da, chave
        soma += len(da)
    assert soma == len(emojis.todos())
    assert emojis.categoria_de("😀") == "rostos"
    assert emojis.categoria_de("🐶") == "animais"
    assert emojis.categoria_de("🇧🇷") == "bandeiras"
    assert emojis.categoria_de("♻️") == "simbolos"     # com ou sem FE0F
    assert emojis.categoria_de("♻") == "simbolos"
    assert emojis.categoria_de("❤️") == "rostos"       # corações: emoção


def test_buscar_dentro_de_uma_categoria():
    sem_texto = emojis.buscar("", 0, "animais")
    assert sem_texto[0].simbolo == "🐵"        # a ordem do Unicode
    assert {emojis.categoria_de(e.simbolo) for e in sem_texto} == {"animais"}
    gatos = emojis.buscar("gato", 50, "animais")
    assert gatos and all(emojis.categoria_de(e.simbolo) == "animais"
                         for e in gatos)
    # "gato" sem categoria acha tambem de outras (rosto de gato, por ex.)
    todos = emojis.buscar("gato", 400)
    assert len(todos) > len(gatos)

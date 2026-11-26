# SPDX-License-Identifier: GPL-3.0-or-later
"""O que o aviso falado de mensagem nova diz, como o modelo usa flags e
como a lista e o modelo se sincronizam."""
from telezapp.nucleo import aviso_de_nova as an

PARTES = {"inicio": "Nova mensagem", "conversa": "Família",
          "servico": "WhatsApp", "conta": "Fábio", "autor": "Ana",
          "hora": "10:00", "conteudo": "oi"}


def test_padrao_e_o_aviso_de_antes():
    assert an.montar(None, PARTES) == "Nova mensagem em Família. Ana, 10:00, oi"
    assert an.montar(None, PARTES, aberta=True) == \
        "Nova mensagem em (sem conteúdo). Ana, 10:00, oi"


def test_flags_tem_um_nome_por_item():
    assert an.FLAGS == {"inicio": "$New", "conversa": "$conversation_out",
                        "servico": "$Service", "conta": "$Account",
                        "autor": "$Sender_Name", "hora": "$Time",
                        "conteudo": "$Content"}


def test_modelo_personalizado_e_texto_livre():
    v = an.definir_modelo(None, "Atenção: $New de $Sender_Name "
                                "em $conversation_out. $Content")
    assert an.montar(v, PARTES) == \
        "Atenção: Nova mensagem de Ana em Família. oi"
    assert an.ativos(v) == ["inicio", "conversa", "autor", "conteudo"]


def test_modelo_vazio_nao_fala():
    v = an.definir_modelo(None, "")
    assert an.montar(v, PARTES) == ""
    assert an.ativos(v) == []
    assert not an.eh_padrao(v)


def test_flag_repetida_repete_o_pedaco():
    v = an.definir_modelo(None, "$Sender_Name, $Sender_Name")
    assert an.montar(v, PARTES) == "Ana, Ana"
    assert an.flags_usadas(v["modelo"]) == ["$Sender_Name", "$Sender_Name"]


def test_pedaco_ausente_vira_aviso():
    v = an.definir_modelo(None, "$New $Content")
    assert an.montar(v, {"inicio": "Nova mensagem", "conteudo": ""}) == \
        "Nova mensagem (sem conteúdo)"
    v = an.definir_modelo(None, "$Desconhecida $New")
    assert an.montar(v, PARTES) == "$Desconhecida Nova mensagem"


def test_alternar_atualiza_a_lista_e_o_modelo():
    v = an.padrao()
    v, ativado = an.alternar(v, "hora")
    assert ativado is False
    assert "hora" in v["ocultos"] and "$Time" not in v["modelo"]
    v, ativado = an.alternar(v, "servico")
    assert ativado is True
    assert "servico" not in v["ocultos"]
    assert v["modelo"].endswith("$Service")


def test_pode_desligar_todos_os_itens():
    v = an.definir_modelo(None, "")
    assert an.ativos(v) == []
    assert an.montar(v, PARTES) == ""
    v = an.definir_modelo(None, "$New")
    v, ativado = an.alternar(v, "inicio")
    assert ativado is False
    assert v["modelo"] == "" and an.ativos(v) == []


def test_config_antiga_sem_modelo_vira_flags_dos_ativos():
    antigo = {"ordem": list(an.CHAVES),
              "ocultos": ["servico", "conta", "hora"]}
    assert an.normalizar(antigo)["modelo"] == \
        "$New $conversation_out $Sender_Name $Content"
    assert an.montar(antigo, PARTES) == "Nova mensagem Família Ana oi"
    assert an.normalizar("lixo") == an.padrao()
    assert an.eh_padrao(an.padrao())


def test_mover_muda_a_lista_nao_a_frase():
    v = an.padrao()
    v, pos = an.mover(v, "conteudo", -1)
    assert pos == 5
    assert an.montar(v, PARTES) == an.montar(None, PARTES)
    assert an.ativos(v) == ["inicio", "conversa", "autor", "conteudo", "hora"]


def test_rotulo_dos_itens():
    assert an.texto_do_item(an.padrao(), "conta") == \
        "Conta que recebeu: desativado"
    assert an.texto_do_item(an.padrao(), "autor") == \
        "Nome de quem enviou: ativado"


def test_padrao_do_config_e_o_mesmo_do_modulo():
    from telezapp import config
    assert config.PADROES["aviso_nova"] == an.padrao()


def test_backup_saneia_o_modelo_sem_perder_a_escolha():
    from telezapp.nucleo import backup
    lidas = {"aviso_nova": {"ordem": ["conteudo"],
                            "ocultos": ["conteudo"],
                            "modelo": "$Content"}}
    boas = backup.opcoes_validas(lidas)["aviso_nova"]
    assert boas["modelo"] == "$Content"
    assert boas["ocultos"] == ["conteudo", "servico", "conta"]

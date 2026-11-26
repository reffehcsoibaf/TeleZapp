# SPDX-License-Identifier: GPL-3.0-or-later
"""O que o aviso falado de mensagem nova diz, com um modelo por tipo de
conversa, e como a lista e o modelo se sincronizam."""
from telezapp.nucleo import aviso_de_nova as an

PARTES = {"inicio": "Nova mensagem", "conversa": "Família",
          "servico": "WhatsApp", "conta": "Fábio", "autor": "Ana",
          "hora": "10:00", "conteudo": "oi"}


def test_padrao_e_o_aviso_de_antes():
    assert an.montar(None, PARTES) == "Nova mensagem em Família. Ana, 10:00, oi"
    assert an.montar(None, PARTES, aberta=True) == \
        "Nova mensagem em (sem conteúdo). Ana, 10:00, oi"
    for tipo in an.TIPOS:
        assert an.montar(None, PARTES, tipo=tipo) == \
            "Nova mensagem em Família. Ana, 10:00, oi"


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
    assert an.flags_usadas(an.bloco(v)["modelo"]) == \
        ["$Sender_Name", "$Sender_Name"]


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
    bloco = an.bloco(v)
    assert "hora" in bloco["ocultos"] and "$Time" not in bloco["modelo"]
    v, ativado = an.alternar(v, "servico")
    assert ativado is True
    assert "servico" not in an.bloco(v)["ocultos"]
    assert an.bloco(v)["modelo"].endswith("$Service")


def test_pode_desligar_todos_os_itens():
    v = an.definir_modelo(None, "")
    assert an.ativos(v) == []
    assert an.montar(v, PARTES) == ""
    v = an.definir_modelo(None, "$New")
    v, ativado = an.alternar(v, "inicio")
    assert ativado is False
    assert an.bloco(v)["modelo"] == "" and an.ativos(v) == []


def test_cada_tipo_tem_seu_modelo_e_seus_ativos():
    v = an.padrao()
    v = an.definir_modelo(v, "$New: $Sender_Name", "grupo")
    v = an.definir_modelo(v, "$Content", "canal")
    v = an.definir_modelo(v, "", "privada")
    assert an.montar(v, PARTES, tipo="privada") == ""
    assert an.montar(v, PARTES, tipo="grupo") == "Nova mensagem: Ana"
    assert an.montar(v, PARTES, tipo="canal") == "oi"
    assert an.ativos(v, "grupo") == ["inicio", "autor"]
    assert an.eh_padrao(v, "privada") is False
    assert an.eh_padrao(an.padrao(), "grupo") is True


def test_config_antiga_volta_ao_padrao_nos_tres_tipos():
    antigo = {"ordem": ["conteudo"], "ocultos": ["conteudo"],
              "modelo": "$Content"}
    v = an.normalizar(antigo)
    assert v == an.padrao()
    assert an.montar(antigo, PARTES, tipo="grupo") == \
        "Nova mensagem em Família. Ana, 10:00, oi"
    assert an.normalizar("lixo") == an.padrao()
    assert an.normalizar_tipo("invalido") == "privada"


def test_mover_muda_a_lista_nao_a_frase():
    v = an.padrao()
    v, pos = an.mover(v, "conteudo", -1)
    assert pos == 5
    assert an.montar(v, PARTES) == an.montar(None, PARTES)
    assert an.ativos(v) == ["inicio", "conversa", "autor", "conteudo", "hora"]


def test_rotulo_dos_itens_e_dos_tipos():
    assert an.texto_do_item(an.padrao(), "conta") == \
        "Conta que recebeu: desativado"
    assert an.texto_do_item(an.padrao(), "autor") == \
        "Nome de quem enviou: ativado"
    assert an.rotulo_tipo("grupo") == "Grupos"


def test_padrao_do_config_e_o_mesmo_do_modulo():
    from telezapp import config
    assert config.PADROES["aviso_nova"] == an.padrao()


def test_exemplo_de_notificacao_tem_dados_de_cada_tipo():
    assert an.exemplo_de_aviso(None) == (
        "Nova mensagem em Fábio Schefer. Ana, 10:00, Mensagem de teste")
    assert an.exemplo_de_aviso(None, "grupo") == (
        "Nova mensagem em TeleZapp. Bia, 10:00, Mensagem de teste")
    assert an.exemplo_de_aviso(None, "canal") == (
        "Nova mensagem em Canal de atualizações do TeleZapp. "
        "TeleZapp, 10:00, Mensagem de teste")


def test_exemplo_usa_o_modelo_do_bloco_e_respeita_modelo_vazio():
    v = an.definir_modelo(
        None, "$Service/$Account/$Sender_Name/$Time/$Content", "grupo")
    assert an.exemplo_de_aviso(v, "grupo") == (
        "WhatsApp/Minha conta/Bia/10:00/Mensagem de teste")
    v = an.definir_modelo(v, "", "canal")
    assert an.exemplo_de_aviso(v, "canal") == ""
    assert an.exemplo_de_aviso(v, "privada") == an.exemplo_de_aviso(None)


def test_backup_saneia_os_tres_tipos():
    from telezapp.nucleo import backup
    lidas = {"aviso_nova": {"tipos": {"grupo": {
        "ordem": ["conteudo"], "ocultos": ["conteudo"],
        "modelo": "$Content"}}}}
    boas = backup.opcoes_validas(lidas)["aviso_nova"]
    assert an.bloco(boas, "grupo")["modelo"] == "$Content"
    assert an.bloco(boas, "privada") == an.bloco(an.padrao(), "privada")
    assert an.bloco(boas, "canal") == an.bloco(an.padrao(), "canal")

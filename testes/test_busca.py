# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Busca por critérios nas mensagens guardadas (núcleo, com um banco de
verdade)."""
import json
import time

import pytest

from telezapp.armazenamento.banco import Banco
from telezapp.nucleo import busca
from telezapp.nucleo import modelos as m

DIA = 86400.0
HOJE = time.mktime((2026, 10, 27, 12, 0, 0, 0, 0, -1))


def msg(conta, conversa, id_, texto="", dias=0, **k):
    return m.Mensagem(conta, conversa, str(id_), texto=texto,
                      data=HOJE - dias * DIA, **k)


def extras(**d):
    return json.dumps(d)


@pytest.fixture
def banco(tmp_path):
    b = Banco(str(tmp_path / "b.db"))
    b.salvar_conversas([
        m.Conversa("w1", "ana", "Ana Souza", "whatsapp", "privada",
                   nao_lidas=2, fixada=True),
        m.Conversa("w1", "fam", "Família", "whatsapp", "grupo",
                   silenciada_ate=-1.0),
        m.Conversa("w1", "arq", "Antiga", "whatsapp", "privada",
                   arquivada=True),
        m.Conversa("w1", "sec", "Segredo", "whatsapp", "privada",
                   trancada=True),
        m.Conversa("t1", "noticias", "Notícias", "telegram", "canal"),
        m.Conversa("t1", "joao", "João", "telegram", "privada"),
    ])
    b.salvar_mensagens([
        msg("w1", "ana", 1, "Reunião amanhã às 10h", dias=1),
        msg("w1", "ana", 2, "Combinado, obrigado!", dias=1, minha=True,
            estado="lida"),
        msg("w1", "ana", 3, "foto da reunião", dias=5, tipo=m.FOTO),
        msg("w1", "ana", 4, "", dias=2, tipo=m.VOZ, segundos=40,
            extras=extras(ouvida=True)),
        msg("w1", "ana", 5, "", dias=3, tipo=m.AUDIO, segundos=300),
        msg("w1", "fam", 6, "Almoço de domingo", dias=10, autor="Bia"),
        msg("w1", "fam", 7, "veja https://exemplo.com", dias=9, autor="Caio",
            extras=extras(links=[["https://exemplo.com", "exemplo"]])),
        msg("w1", "arq", 8, "reunião de 2024", dias=400),
        msg("w1", "sec", 9, "reunião secreta", dias=1),
        msg("t1", "noticias", 10, "Resultado da reunião do conselho",
            dias=7),
        msg("t1", "joao", 11, "reunião cancelada", dias=0),
        msg("t1", "joao", 12, "Favorita!", dias=4,
            extras=extras(favorita=True)),
        msg("w1", "ana", 13, "documento", dias=6, tipo=m.DOCUMENTO,
            nome_arquivo="Relatório Final.pdf", tamanho=3_000_000),
        msg("t1", "joao", 14, "", dias=2, tipo=m.VOZ, segundos=10,
            extras=extras(ia={"texto": "preciso falar com o dentista"})),
        msg("t1", "joao", 15, "enquete", dias=8, tipo=m.OUTRO,
            extras=extras(enquete={"pergunta": "Qual pizza?",
                                   "opcoes": ["Calabresa", "Queijo"]})),
    ])
    return b


def ids(banco, **k):
    return sorted(int(a.mensagem.id) for a in busca.buscar(
        banco, busca.Criterios(**k), agora=HOJE))


def test_sem_criterio_traz_tudo_menos_as_trancadas(banco):
    assert 9 not in ids(banco)
    assert len(ids(banco)) == 14
    assert busca.Criterios().vazio()


def test_termo_ignora_maiusculas_e_acentos_e_pede_todas_as_palavras(banco):
    assert ids(banco, termo="REUNIAO") == [1, 3, 8, 10, 11]
    assert ids(banco, termo="reunião amanhã") == [1]
    assert ids(banco, termo="amanha reuniao") == [1]       # qualquer ordem
    assert ids(banco, termo="amanha reuniao", frase_exata=True) == []
    assert ids(banco, termo="reunião amanhã", frase_exata=True) == [1]


def test_termo_acha_nome_de_arquivo_transcricao_e_enquete(banco):
    assert ids(banco, termo="relatorio final") == [13]
    assert ids(banco, termo="dentista") == [14]
    assert ids(banco, termo="calabresa") == [15]


def test_servico_e_conta(banco):
    assert ids(banco, servicos={"telegram"}) == [10, 11, 12, 14, 15]
    assert ids(banco, contas={"t1"}, termo="reuniao") == [10, 11]
    assert ids(banco, contas={"w1"}, termo="reuniao") == [1, 3, 8]


def test_tipo_e_situacao_da_conversa(banco):
    assert ids(banco, tipos_de_conversa={"grupo"}) == [6, 7]
    assert ids(banco, tipos_de_conversa={"canal"}) == [10]
    assert ids(banco, situacoes={"arquivada"}) == [8]
    assert ids(banco, situacoes={"fixada"}) == [1, 2, 3, 4, 5, 13]
    assert ids(banco, situacoes={"silenciada"}) == [6, 7]
    assert ids(banco, situacoes={"nao_lida", "fixada"}) == [
        1, 2, 3, 4, 5, 13]


def test_nome_da_conversa_sem_acento(banco):
    assert ids(banco, conversa_contem="joao") == [11, 12, 14, 15]
    assert ids(banco, conversa_contem="noticia") == [10]


def test_tipo_de_mensagem(banco):
    assert ids(banco, tipos_de_mensagem={m.VOZ}) == [4, 14]
    assert ids(banco, tipos_de_mensagem={m.VOZ, m.AUDIO}) == [4, 5, 14]
    assert ids(banco, tipos_de_mensagem={m.FOTO, m.DOCUMENTO}) == [3, 13]
    assert ids(banco, tipos_de_mensagem={"enquete"}) == [15]


def test_caracteristicas(banco):
    assert ids(banco, caracteristicas={"favorita"}) == [12]
    assert ids(banco, caracteristicas={"com_link"}) == [7]
    assert ids(banco, caracteristicas={"ouvida"}) == [4]
    assert ids(banco, caracteristicas={"nao_ouvida"}) == [5, 14]
    assert ids(banco, caracteristicas={"com_ia"}) == [14]
    assert ids(banco, caracteristicas={"com_midia"}) == [3, 4, 5, 13, 14]
    assert ids(banco, caracteristicas={"com_midia", "com_ia"}) == [14]


def test_quem_enviou(banco):
    assert ids(banco, minha=True) == [2]
    assert 2 not in ids(banco, minha=False)
    assert ids(banco, autor_contem="bia") == [6]
    assert ids(banco, autor_contem="voce") == [2]


def test_periodo(banco):
    de = HOJE - 2 * DIA
    assert ids(banco, data_de=de - 3600) == [1, 2, 4, 11, 14]
    assert ids(banco, data_ate=HOJE - 9 * DIA) == [6, 7, 8]
    assert ids(banco, data_de=HOJE - 6 * DIA - 3600,
               data_ate=HOJE - 4 * DIA + 3600) == [3, 12, 13]


def test_duracao_e_tamanho(banco):
    assert ids(banco, segundos_min=30, tipos_de_mensagem={m.VOZ,
                                                           m.AUDIO}) == [4, 5]
    assert ids(banco, segundos_max=20, tipos_de_mensagem={m.VOZ}) == [14]
    assert ids(banco, tamanho_min=1_000_000) == [13]


def test_estado_de_envio(banco):
    assert ids(banco, estados_de_envio={m.LIDA}) == [2]
    assert ids(banco, estados_de_envio={m.FALHOU}) == []


def test_varios_criterios_juntos(banco):
    assert ids(banco, termo="reuniao", servicos={"whatsapp"},
               tipos_de_mensagem={m.FOTO}) == [3]
    assert ids(banco, termo="reuniao", situacoes={"arquivada"}) == [8]


def test_trancadas_so_com_a_liberacao(banco):
    assert ids(banco, termo="secreta") == []
    assert ids(banco, termo="secreta", incluir_trancadas=True) == [9]
    assert ids(banco, situacoes={"trancada"}, incluir_trancadas=True) == [9]
    assert ids(banco, situacoes={"trancada"}) == []


def test_ordem_e_limite(banco):
    novas = busca.buscar(banco, busca.Criterios(termo="reuniao"), agora=HOJE)
    assert [int(a.mensagem.id) for a in novas] == [11, 1, 3, 10, 8]
    antigas = busca.buscar(banco, busca.Criterios(
        termo="reuniao", mais_antigas_primeiro=True), agora=HOJE)
    assert [int(a.mensagem.id) for a in antigas] == [8, 10, 3, 1, 11]
    assert len(busca.buscar(banco, busca.Criterios(termo="reuniao",
                                                   limite=2))) == 2


def test_trecho_mostra_o_termo_e_o_nome_da_conversa(banco):
    a = busca.buscar(banco, busca.Criterios(termo="dentista"))[0]
    assert "dentista" in a.trecho
    assert a.texto_da_lista().startswith("João,")


def test_ler_data_e_numero():
    ini = busca.ler_data("27/10/2026")
    fim = busca.ler_data("27/10/2026", fim_do_dia=True)
    assert fim - ini == 86399
    assert busca.ler_data("2026-10-27") == ini
    assert busca.ler_data("") is None and busca.ler_data("32/13/2026") is None
    assert busca.ler_numero("1,5") == 1.5 and busca.ler_numero("x") is None


def test_resumo_fala_o_que_foi_pedido():
    c = busca.Criterios(termo="reunião", servicos={"whatsapp"},
                        situacoes={"arquivada"}, minha=True,
                        data_de=busca.ler_data("01/10/2026"))
    r = c.resumo()
    assert "reunião" in r and "WhatsApp" in r and "arquivada" in r
    assert "enviadas por você" in r and "01/10/2026" in r
    assert busca.Criterios().resumo() == "sem critérios"

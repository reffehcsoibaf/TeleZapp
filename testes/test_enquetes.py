"""Enquetes: os dados guardados na mensagem, as contagens e o resumo."""
from telezapp.nucleo import modelos as m


def mensagem(**enquete):
    msg = m.Mensagem("w1", "5551@s.whatsapp.net", "P1", tipo=m.OUTRO,
                     texto="enquete: Qual dia?", data=1000.0)
    base = {"pergunta": "Qual dia?", "opcoes": ["Sexta", "Sábado", "Domingo"],
            "maximo": 1}
    base.update(enquete)
    m.atualizar_extras(msg, enquete=base)
    return msg


def test_mensagem_sem_enquete():
    msg = m.Mensagem("w1", "c", "1", texto="oi")
    assert m.enquete_de(msg) == {}
    assert m.resumo_enquete(msg) == ""


def test_enquete_arruma_os_dados():
    msg = mensagem(maximo=9, meus=[1, 7], votos={
        "a": {"nome": "Ana", "escolhas": [0, 5, "x"]}})
    e = m.enquete_de(msg)
    assert e["maximo"] == 3                    # no maximo o numero de opcoes
    assert e["meus"] == [1]                    # posicao que nao existe sai
    assert e["votos"]["a"]["escolhas"] == [0]
    assert e["encerrada"] is False and e["contagem"] is None


def test_contagem_vem_dos_votos_ou_do_que_o_servico_mandou():
    msg = mensagem(votos={"a": {"nome": "Ana", "escolhas": [0]},
                          "b": {"nome": "Bia", "escolhas": [0, 2]},
                          "c": {"nome": "Caio", "escolhas": []}})
    e = m.enquete_de(msg)
    assert m.contagens_da_enquete(e) == [2, 0, 1]
    assert m.votantes_da_enquete(e) == 2       # Caio tirou o voto
    assert m.quem_votou_em(e, 0) == ["Ana", "Bia"]
    pronta = m.enquete_de(mensagem(contagem=[4, 1, 0], total=5))
    assert m.contagens_da_enquete(pronta) == [4, 1, 0]
    assert m.votantes_da_enquete(pronta) == 5


def test_contagem_de_tamanho_errado_e_ignorada():
    e = m.enquete_de(mensagem(contagem=[1, 2]))
    assert e["contagem"] is None


def test_resumo_diz_opcoes_votos_e_o_meu_voto():
    msg = mensagem()
    assert m.resumo_enquete(msg) == "enquete: Qual dia?, 3 opções, nenhum voto"
    msg = mensagem(contagem=[1, 0, 0], total=1, meus=[0])
    assert m.resumo_enquete(msg) == (
        "enquete: Qual dia?, 3 opções, 1 voto, seu voto: Sexta")
    msg = mensagem(encerrada=True, contagem=[2, 1, 0], total=3)
    assert m.resumo_enquete(msg).startswith("enquete encerrada: Qual dia?")


def test_linha_da_lista_leva_o_resumo_e_a_dica():
    msg = mensagem(contagem=[1, 0, 0], total=1)
    linha = m.formatar(msg, m.ESTILO_AUTOR_PRIMEIRO)
    assert "enquete: Qual dia?, 3 opções, 1 voto" in linha
    assert "(Enter para ver e votar)" in linha


def test_guardar_extras_nao_perde_a_enquete():
    msg = mensagem()
    m.guardar_extras(msg, links=[("http://x", "x")])
    assert m.enquete_de(msg)["pergunta"] == "Qual dia?"


def test_pode_marcar_mais_respeita_o_maximo():
    e = m.enquete_de(mensagem(maximo=2))
    assert m.pode_marcar_mais(e, [0]) and not m.pode_marcar_mais(e, [0, 1])


def test_linhas_da_enquete_mostram_contagem_percentual_e_meu_voto():
    msg = mensagem(contagem=[2, 1, 0], total=3, meus=[1])
    assert m.linhas_da_enquete(m.enquete_de(msg)) == [
        "Sexta: 2 votos (67%)",
        "Sábado: 1 voto (33%), seu voto",
        "Domingo: nenhum voto (0%)"]
    assert m.linhas_da_enquete(m.enquete_de(mensagem()))[0] == \
        "Sexta: nenhum voto (0%)"

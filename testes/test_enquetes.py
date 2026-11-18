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


def test_erro_da_enquete_a_criar():
    ok = ["Sexta", "Sábado"]
    assert m.erro_da_enquete("whatsapp", "Qual dia?", ok) == ""
    assert "pergunta" in m.erro_da_enquete("whatsapp", "  ", ok)
    assert "pelo menos 2" in m.erro_da_enquete("whatsapp", "Q?", ["A"])
    assert "limite" in m.erro_da_enquete("telegram", "Q?",
                                         [str(i) for i in range(11)])
    assert m.erro_da_enquete("whatsapp", "Q?",
                             [str(i) for i in range(12)]) == ""
    assert "repetir" in m.erro_da_enquete("whatsapp", "Q?", ["A", "a"])
    assert "100" in m.erro_da_enquete("whatsapp", "Q?", ["A", "x" * 101])
    assert "255" in m.erro_da_enquete("whatsapp", "x" * 256, ok)


# ------------------------------------------- enquetes novas do WhatsApp
def _proto():
    from neonize.proto.waE2E import WAWebProtobufsE2E_pb2 as E
    return E


def _criacao(E, **campos):
    Opc = E.PollCreationMessage.Option
    return E.PollCreationMessage(
        name="Qual?", options=[Opc(optionName="A"), Opc(optionName="B"),
                               Opc(optionName="C")], **campos)


def test_whatsapp_le_a_versao_6_e_a_5():
    from telezapp.provedores import whatsapp as w
    E = _proto()
    for nome in ("pollCreationMessageV5", "pollCreationMessageV6"):
        msg = E.Message(**{nome: _criacao(E, selectableOptionsCount=2)})
        enq = w.enquete_do_whatsapp(msg)
        assert enq["pergunta"] == "Qual?" and enq["maximo"] == 2
        assert w.conteudo_de(msg)[1] == "enquete: Qual?"


def test_whatsapp_abre_o_envelope_da_versao_4():
    from telezapp.provedores import whatsapp as w
    E = _proto()
    msg = E.Message(pollCreationMessageV4=E.FutureProofMessage(
        message=E.Message(pollCreationMessage=_criacao(E))))
    interna = w.desembrulhar(msg)
    assert w.enquete_do_whatsapp(interna)["opcoes"] == ["A", "B", "C"]


def test_whatsapp_quiz_anonima_prazo_e_opcoes_novas():
    import time
    from telezapp.provedores import whatsapp as w
    E = _proto()
    fim = int(time.time()) + 3600
    msg = E.Message(pollCreationMessageV6=_criacao(
        E, pollType=E.QUIZ, hideParticipantName=True, allowAddOption=True,
        pollContentType=E.IMAGE, endTime=fim,
        correctAnswer=E.PollCreationMessage.Option(optionName="B")))
    enq = w.enquete_do_whatsapp(msg)
    assert enq["quiz"] and enq["correta"] == 1 and enq["anonima"]
    assert enq["permite_adicionar"] and enq["com_imagens"]
    assert enq["encerra_em"] == fim
    assert w.conteudo_de(msg)[1] == "quiz: Qual?"
    e = m.enquete_de(mensagem(**enq))
    assert not e["encerrada"]
    assert len(m.descricao_da_enquete(e)) == 5


def test_quiz_so_mostra_a_certa_depois_de_votar_ou_encerrar():
    base = dict(quiz=True, correta=1)
    e = m.enquete_de(mensagem(**base))
    assert not m.mostrar_resposta_certa(e)
    assert "resposta certa" not in " ".join(m.linhas_da_enquete(e))
    e = m.enquete_de(mensagem(meus=[0], **base))
    assert "resposta certa" in m.linhas_da_enquete(e)[1]
    e = m.enquete_de(mensagem(encerrada=True, **base))
    assert m.mostrar_resposta_certa(e)


def test_prazo_vencido_encerra_e_anonima_nao_mostra_quem_votou():
    msg = mensagem(encerra_em=10.0, anonima=True, votos={
        "a": {"nome": "Ana", "escolhas": [0]}})
    e = m.enquete_de(msg)
    assert e["encerrada"] is True
    assert m.quem_votou_em(e, 0) == []
    assert m.votantes_da_enquete(e) == 1


def test_whatsapp_resultado_final_da_enquete():
    from telezapp.provedores import whatsapp as w
    E = _proto()
    msg = E.Message(pollResultSnapshotMessage=E.PollResultSnapshotMessage(
        name="Qual?", pollVotes=[
            E.PollResultSnapshotMessage.PollVote(
                optionName="A", optionVoteCount=2),
            E.PollResultSnapshotMessage.PollVote(
                optionName="B", optionVoteCount=0)]))
    tipo, texto, *_ = w.conteudo_de(msg)
    assert texto == "Resultado da enquete: Qual?; A: 2 votos; B: nenhum voto"

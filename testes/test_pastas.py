from telezapp.nucleo import pastas as p

CONTAS = [("t1", "telegram"), ("w1", "whatsapp")]
DUAS = CONTAS + [("t2", "telegram")]


def test_conta_unica_segue_a_regra_da_terceira_caixa():
    assert p.conta_unica("todas", CONTAS) is None
    assert p.conta_unica("telegram", CONTAS) == "t1"
    assert p.conta_unica("whatsapp", CONTAS) == "w1"
    assert p.conta_unica("telegram", DUAS) is None        # duas contas
    assert p.conta_unica("conta:t2", DUAS) == "t2"        # conta escolhida
    assert p.conta_unica("conta:xx", DUAS) is None


def _d(id_, **k):
    base = {"id": id_, "usuario": False, "contato": False, "bot": False,
            "grupo": False, "canal": False, "silenciada": False,
            "nao_lida": False, "arquivada": False}
    base.update(k)
    return base


def _pasta(**k):
    return p.pasta_de_dados({"id": 1, "nome": "Tema", **k})


def test_incluidas_entram_sempre_e_excluidas_saem():
    ds = [_d("1", grupo=True), _d("2", grupo=True, silenciada=True),
          _d("3", grupo=True)]
    pasta = _pasta(incluir=["2"], excluir=["3"], grupos=True,
                   sem_silenciadas=True)
    assert p.membros(pasta, ds) == {"1", "2"}


def test_categorias_e_exclusoes():
    ds = [_d("c", usuario=True, contato=True),
          _d("n", usuario=True),
          _d("b", usuario=True, bot=True),
          _d("k", canal=True),
          _d("g", grupo=True, nao_lida=True),
          _d("a", grupo=True, arquivada=True)]
    assert p.membros(_pasta(contatos=True), ds) == {"c"}
    assert p.membros(_pasta(nao_contatos=True, bots=True), ds) == {"n", "b"}
    assert p.membros(_pasta(canais=True), ds) == {"k"}
    assert p.membros(_pasta(grupos=True, sem_lidas=True), ds) == {"g"}
    assert p.membros(_pasta(grupos=True, sem_arquivadas=True), ds) == {"g"}


def test_passa_sem_pasta_ou_com_pasta_que_sumiu_nao_filtra():
    assert p.passa("9", "", {"1": {"9"}})
    assert p.passa("9", "7", {"1": {"9"}})
    assert p.passa("9", "1", {"1": {"9"}})
    assert not p.passa("8", "1", {"1": {"9"}})

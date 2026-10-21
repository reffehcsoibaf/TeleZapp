# SPDX-License-Identifier: GPL-3.0-or-later
"""Gerencia de contas: so grava a conta nova depois do login."""
from telezapp import config
from telezapp.nucleo import eventos as ev
from telezapp.nucleo.contas import Contas


class ProvedorFalso:
    def __init__(self, conta):
        self.conta = conta
        self.iniciado = self.parado = False

    def iniciar(self):
        self.iniciado = True

    def parar(self):
        self.parado = True


def montar(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path))
    cfg = config.Config()
    b = ev.Barramento()
    criados = []

    def fabrica(conta):
        p = ProvedorFalso(conta)
        criados.append(p)
        return p
    contas = Contas(cfg, None, b, lambda *a: None, lambda: (1, "x"),
                    fabrica)
    return cfg, b, contas, criados


def test_conta_nova_gravada_so_apos_login(tmp_path, monkeypatch):
    cfg, b, contas, criados = montar(tmp_path, monkeypatch)
    assert contas.adicionar("telegram", "+5551999998888")
    p = criados[0]
    assert p.iniciado and cfg.contas() == []
    b.publicar(ev.ContaPronta(p.conta.id, "Fábio", "+5551999998888"))
    salvas = cfg.contas()
    assert salvas[0]["nome"] == "Fábio" and salvas[0]["servico"] == "telegram"
    assert contas.nome(p.conta.id) == "Fábio"


def test_login_cancelado_de_conta_nova(tmp_path, monkeypatch):
    cfg, b, contas, criados = montar(tmp_path, monkeypatch)
    contas.adicionar("telegram")
    p = criados[0]
    b.publicar(ev.EstadoConta(p.conta.id, ev.PRECISA_LOGIN, "cancelado"))
    assert p.parado and contas.provedor(p.conta.id) is None
    assert cfg.contas() == []


def test_contas_salvas_sao_iniciadas_e_reconectadas(tmp_path, monkeypatch):
    cfg, b, contas, criados = montar(tmp_path, monkeypatch)
    cfg.salvar_conta({"id": "telegram-1", "servico": "telegram",
                      "telefone": "+55", "nome": "Eu"})
    contas.iniciar_salvas()
    assert criados[0].iniciado and criados[0].conta.nome == "Eu"
    # conta salva que pede login de novo nao e apagada
    b.publicar(ev.EstadoConta("telegram-1", ev.PRECISA_LOGIN, "cancelado"))
    assert contas.provedor("telegram-1") is criados[0]
    assert contas.reconectar("telegram-1")
    assert criados[0].parado and criados[1].iniciado
    contas.parar_todos()
    assert criados[1].parado


def test_parear_de_novo_e_remover_apagam_a_sessao(tmp_path, monkeypatch):
    from telezapp.armazenamento.banco import Banco
    from telezapp.nucleo import contas as cm
    from telezapp.nucleo.modelos import Conversa
    cfg, b, contas, criados = montar(tmp_path, monkeypatch)
    contas.banco = Banco(str(tmp_path / "t.db"))
    sessoes = config.pasta("sessoes")
    cfg.salvar_conta({"id": "whatsapp-1", "servico": "whatsapp",
                      "nome": "Eu", "historico": "recentes"})
    contas.iniciar_salvas()
    for nome in ("whatsapp-1.db", "whatsapp-1.db-wal", "whatsapp-10.db"):
        (tmp_path / "sessoes" / nome).write_text("x")
    contas.banco.salvar_conversas([Conversa("whatsapp-1", "a@s", "A")])

    assert contas.parear_de_novo("whatsapp-1", "365")
    assert criados[0].parado and criados[1].iniciado
    import os
    assert sorted(os.listdir(sessoes)) == ["whatsapp-10.db"]
    assert contas._historico["whatsapp-1"] == "365"
    assert len(contas.banco.conversas("whatsapp-1")) == 1  # conversas ficam

    contas.remover("whatsapp-1")
    assert criados[1].parado and cfg.contas() == []
    assert contas.banco.conversas("whatsapp-1") == []
    assert contas.provedor("whatsapp-1") is None
    assert cm.apagar_sessao is not None


def test_conta_desativada_nao_conecta_mas_continua_listada(tmp_path,
                                                           monkeypatch):
    cfg, b, contas, criados = montar(tmp_path, monkeypatch)
    estados = []
    b.ouvir(lambda e: estados.append((e.conta_id, e.estado))
            if isinstance(e, ev.EstadoConta) else None)
    cfg.salvar_conta({"id": "telegram-1", "servico": "telegram", "nome": "A"})
    cfg.salvar_conta({"id": "telegram-2", "servico": "telegram", "nome": "B",
                      "ativa": False})
    contas.iniciar_salvas()
    assert [p.conta.id for p in criados] == ["telegram-1"]
    assert contas.provedor("telegram-2") is None
    assert contas.servico("telegram-2") == "telegram"   # segue conhecida
    assert not contas.esta_ativa("telegram-2") and contas.esta_ativa("telegram-1")
    assert ("telegram-2", ev.DESCONECTADA) in estados
    assert not contas.reconectar("telegram-2")          # nao liga sozinha


def test_ativar_e_desativar_conta(tmp_path, monkeypatch):
    cfg, b, contas, criados = montar(tmp_path, monkeypatch)
    cfg.salvar_conta({"id": "telegram-1", "servico": "telegram", "nome": "A"})
    contas.iniciar_salvas()
    p = criados[0]
    assert contas.desativar("telegram-1")
    assert p.parado and contas.provedor("telegram-1") is None
    assert cfg.contas()[0]["ativa"] is False and not contas.esta_ativa("telegram-1")
    assert contas.ativar("telegram-1")
    assert criados[1].iniciado and contas.provedor("telegram-1") is criados[1]
    assert cfg.contas()[0]["ativa"] is True
    assert not contas.desativar("nao-existe")


def test_renomear_conta_sobrevive_a_nova_conexao(tmp_path, monkeypatch):
    cfg, b, contas, criados = montar(tmp_path, monkeypatch)
    contas.adicionar("telegram", "+5551999998888")
    cid = criados[0].conta.id
    b.publicar(ev.ContaPronta(cid, "Fábio", "+5551999998888"))
    assert contas.renomear(cid, "  Meu   trabalho ") is True
    assert contas.nome(cid) == "Meu trabalho"
    assert cfg.contas()[0]["apelido"] == "Meu trabalho"
    assert cfg.contas()[0]["nome"] == "Meu trabalho"
    # conecta de novo: o servico informa o nome dele, o apelido continua
    b.publicar(ev.ContaPronta(cid, "Fábio Silva", "+5551999998888"))
    assert contas.nome(cid) == "Meu trabalho"
    assert cfg.contas()[0]["nome_servico"] == "Fábio Silva"
    # nome vazio volta ao nome do servico
    assert contas.renomear(cid, "") is True
    assert contas.nome(cid) == "Fábio Silva"
    assert "apelido" not in cfg.contas()[0]
    assert contas.renomear("nao-existe", "x") is False


def test_desativada_continua_desativada_apos_pronta(tmp_path, monkeypatch):
    cfg, b, contas, criados = montar(tmp_path, monkeypatch)
    contas.adicionar("telegram")
    cid = criados[0].conta.id
    b.publicar(ev.ContaPronta(cid, "Fábio", ""))
    assert contas.desativar(cid)
    b.publicar(ev.ContaPronta(cid, "Fábio", ""))
    assert cfg.contas()[0]["ativa"] is False

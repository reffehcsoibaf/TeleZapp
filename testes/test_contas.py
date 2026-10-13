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

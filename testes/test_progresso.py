# SPDX-License-Identifier: GPL-3.0-or-later
"""A janela de progresso: so a etapa e escrita e falada, nunca a porcentagem
(quem decide se a barra fala ou bipa e o NVDA)."""
from telezapp.interface.progresso import JanelaDeProgresso


class _Barra:
    def __init__(self):
        self.valores, self.pulsos = [], 0

    def SetValue(self, v):
        self.valores.append(v)

    def Pulse(self):
        self.pulsos += 1


class _Rotulo:
    def __init__(self):
        self.textos = []

    def SetLabel(self, t):
        self.textos.append(t)


class _Botao:
    def __init__(self):
        self.ativo = True

    def Enable(self, v):
        self.ativo = v


def nova(falar=None, ao_cancelar=None):
    j = JanelaDeProgresso.__new__(JanelaDeProgresso)
    j._etapa, j._falar, j._ao_cancelar = "Baixando", falar, ao_cancelar
    j._cancelada = j._fechada = False
    j.barra, j.rotulo, j.botao = _Barra(), _Rotulo(), _Botao()
    return j


def test_so_a_mudanca_de_etapa_muda_o_rotulo_e_e_falada():
    ditas = []
    j = nova(falar=ditas.append)
    for pct in (0, 10, 55, 90):
        j.atualizar(pct, "Baixando")           # mesma etapa: nada de texto
    assert j.rotulo.textos == [] and ditas == []
    assert j.barra.valores == [0, 10, 55, 90]
    j.atualizar(95, "Preparando a atualização")
    j.atualizar(99, "Preparando a atualização")
    assert j.rotulo.textos == ["Preparando a atualização"]
    assert ditas == ["Preparando a atualização"]
    # sem texto: so a barra
    j.atualizar(100)
    assert j.barra.valores[-1] == 100 and len(ditas) == 1


def test_porcentagem_fica_entre_0_e_100_e_none_faz_a_barra_andar():
    j = nova()
    j.atualizar(-5)
    j.atualizar(250)
    j.atualizar(None, "Contando")
    assert j.barra.valores == [0, 100] and j.barra.pulsos == 1


def test_janela_fechada_ignora_avancos_e_cancelar_chama_uma_vez():
    chamadas = []
    j = nova(ao_cancelar=lambda: chamadas.append(1))
    j.cancelar()
    j.cancelar()
    assert chamadas == [1] and j.cancelada and j.botao.ativo is False
    assert j.rotulo.textos == ["Cancelando..."]
    j._fechada = True
    j.atualizar(50, "Outra")
    assert j.barra.valores == []
    sem = nova()                         # sem cancelamento possivel
    sem.cancelar()
    assert not sem.cancelada


def test_atualizar_depois_que_a_janela_dona_fechou_nao_quebra():
    """Log de 05/11/2026: 'wrapped C/C++ object of type Gauge has been
    deleted' quando os detalhes fechavam com o download em andamento."""
    class Morta:
        def SetValue(self, v):
            raise RuntimeError("wrapped C/C++ object has been deleted")
    j = nova()
    j.barra = Morta()
    j.atualizar(50)                  # nao levanta
    assert j._fechada and j.aberta is False
    j.atualizar(60)                  # e as proximas sao ignoradas


def test_ocultar_pede_a_janela_principal_ou_so_esconde(monkeypatch):
    from telezapp.interface import progresso as prog
    escondida = []

    class Principal:
        def _ocultar_janela(self, janela, nome):
            escondida.append((janela, nome))

    class App:
        def __init__(self, topo):
            self.topo = topo

        def GetTopWindow(self):
            return self.topo
    j = nova()
    j.GetTitle = lambda: "Baixando as mídias"
    j.Hide = lambda: escondida.append("hide")
    monkeypatch.setattr(prog.wx, "GetApp", lambda: App(Principal()),
                        raising=False)
    j.ocultar()
    assert escondida == [(j, "Baixando as mídias")]
    monkeypatch.setattr(prog.wx, "GetApp", lambda: None, raising=False)
    j.ocultar()
    assert escondida[-1] == "hide"

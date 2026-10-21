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

# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


import pytest


@pytest.fixture(autouse=True)
def _sem_som_e_sem_fala(monkeypatch):
    """Os testes nunca tocam bipes nem falam pelo leitor de tela (o winsound
    e a fala direta do NVDA sao reais neste computador)."""
    from telezapp.acessibilidade import fala
    monkeypatch.setattr(fala, "winsound", None)
    monkeypatch.setattr(fala.Fala, "ativa", lambda self: False)
    monkeypatch.setattr(fala.Fala, "falar", lambda self, *a, **k: False)


@pytest.fixture(autouse=True)
def _leitor_de_tela_fixo(monkeypatch):
    """No modo automatico a janela pergunta ao Windows se ha leitor de tela;
    os testes nao podem depender de o NVDA estar ligado: fica sempre sim
    (a lista de sempre). Quem testa o modo visual escolhe o modo."""
    from telezapp.nucleo import aparencia
    monkeypatch.setattr(aparencia, "leitor_de_tela_ligado", lambda: True)


@pytest.fixture(autouse=True)
def _lista_sem_espera(monkeypatch):
    """Os testes mandam eventos um atras do outro e olham a lista logo em
    seguida: sem o intervalo que junta as rajadas (os testes da rajada o
    ligam). So mexe se a janela ja foi importada (com o wx falso)."""
    jm = sys.modules.get("telezapp.interface.janela")
    if jm is not None:
        monkeypatch.setattr(jm.Janela, "INTERVALO_DA_LISTA", 0)

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

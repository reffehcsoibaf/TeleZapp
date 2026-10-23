"""Abrir ao entrar no Windows (chave de teste, nunca a Run de verdade) e o
aviso entre duas aberturas do programa."""
import sys

import pytest

from telezapp.nucleo import inicializacao as ini
from telezapp.nucleo import instancia

pytestmark = pytest.mark.skipif(sys.platform != "win32",
                                reason="so no Windows")

CHAVE_TESTE = r"Software\TeleZappTeste\Run"


@pytest.fixture
def chave():
    import winreg
    yield CHAVE_TESTE
    for sub in (CHAVE_TESTE, r"Software\TeleZappTeste"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
        except OSError:
            pass


def test_ligar_e_desligar_a_inicializacao(chave):
    assert not ini.ativado(chave)
    assert ini.definir(True, chave,
                       linha='"C:/x/TeleZapp.exe" --segundo-plano')
    assert ini.ativado(chave)
    assert ini.linha_atual(chave).endswith("--segundo-plano")
    assert ini.definir(False, chave)
    assert not ini.ativado(chave)
    assert ini.definir(False, chave)           # desligar de novo nao falha


def test_o_comando_leva_o_argumento_de_segundo_plano():
    assert ini.comando().rstrip('"').endswith(ini.ARGUMENTO)


def test_segunda_abertura_aciona_a_primeira():
    sufixo = "-teste-%d" % id(object())
    assert not instancia.acionar(sufixo)        # ninguem rodando
    sinal = instancia.criar_sinal(sufixo)
    try:
        assert sinal
        assert not instancia.esperar(sinal, 10)
        assert instancia.acionar(sufixo)
        assert instancia.esperar(sinal, 1000)
        assert not instancia.esperar(sinal, 10)  # o aviso foi consumido
    finally:
        instancia.fechar(sinal)

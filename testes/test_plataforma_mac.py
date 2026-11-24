# SPDX-License-Identifier: GPL-3.0-or-later
"""As partes do Mac que rodam em qualquer sistema: segredo no Chaveiro (com
um Chaveiro de mentira), arquivo-sinal da segunda abertura, LaunchAgent e o
que a camada de plataforma devolve."""
import os
import plistlib
import sys

import pytest

from telezapp.nucleo import inicializacao, instancia, plataforma, segredo


class ChaveiroFalso:
    def __init__(self):
        self.guardado = {}

    def get_password(self, servico, usuario):
        return self.guardado.get((servico, usuario))

    def set_password(self, servico, usuario, senha):
        self.guardado[(servico, usuario)] = senha


@pytest.fixture
def chaveiro(monkeypatch):
    falso = ChaveiroFalso()
    monkeypatch.setitem(sys.modules, "keyring", falso)
    segredo.esquecer_chave_em_memoria()
    yield falso
    segredo.esquecer_chave_em_memoria()


def test_segredo_cifra_e_decifra_pelo_chaveiro(chaveiro):
    bloco = segredo.cifrar(b"chave da IA")
    assert bloco.startswith(segredo.CABECALHO)
    assert b"chave da IA" not in bloco
    assert segredo.decifrar(bloco) == b"chave da IA"
    assert (segredo.SERVICO, segredo.USUARIO) in chaveiro.guardado


def test_segredo_com_outra_chave_nao_decifra(chaveiro):
    bloco = segredo.cifrar(b"x")
    segredo.esquecer_chave_em_memoria()
    chaveiro.guardado.clear()               # o Chaveiro de outra conta
    assert segredo.decifrar(bloco) is None


def test_segredo_bloco_adulterado_ou_alheio_nao_decifra(chaveiro):
    bloco = bytearray(segredo.cifrar(b"abc"))
    bloco[-1] ^= 1
    assert segredo.decifrar(bytes(bloco)) is None
    assert segredo.decifrar(b"") is None
    assert segredo.decifrar(b"lixo qualquer") is None


def test_segredo_sem_chaveiro_cai_no_arquivo_so_do_usuario(monkeypatch,
                                                           tmp_path):
    class Quebrado:
        def get_password(self, *a):
            raise RuntimeError("sem Chaveiro")
    monkeypatch.setitem(sys.modules, "keyring", Quebrado())
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path / "dados"))
    segredo.esquecer_chave_em_memoria()
    try:
        bloco = segredo.cifrar(b"segredo")
        assert segredo.decifrar(bloco) == b"segredo"
        arquivo = segredo._arquivo_da_chave()
        assert os.path.isfile(arquivo) and os.path.getsize(arquivo) == 32
        if sys.platform != "win32":
            assert os.stat(arquivo).st_mode & 0o777 == 0o600
    finally:
        segredo.esquecer_chave_em_memoria()


def test_seguranca_e_cofre_usam_o_segredo_no_mac(chaveiro, monkeypatch):
    from telezapp.nucleo import seguranca
    from telezapp.nucleo.ia import cofre
    monkeypatch.setattr(sys, "platform", "darwin")
    blob = seguranca._dpapi(b"segredo do PIN", True)
    assert blob and seguranca._dpapi(blob, False) == b"segredo do PIN"
    blob = cofre._dpapi(b"chave", True)
    assert cofre._dpapi(blob, False) == b"chave"
    with pytest.raises(OSError):
        cofre._dpapi(b"lixo", False)


def test_sinal_da_segunda_abertura_no_mac_e_um_arquivo(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path / "dados"))
    sinal = instancia.criar_sinal()
    assert isinstance(sinal, str)
    assert instancia.esperar(sinal, 150) is False       # ninguem chamou
    assert instancia.acionar() is True
    assert instancia.esperar(sinal, 1000) is True
    assert instancia.esperar(sinal, 150) is False       # o sinal foi gasto
    instancia.fechar(sinal)


def test_iniciar_ao_entrar_no_mac_e_um_launchagent(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path)
                        if p == "~" else p)
    assert inicializacao.ativado() is False
    assert inicializacao.definir(True) is True
    assert inicializacao.ativado() is True
    with open(inicializacao._plist_mac(), "rb") as f:
        dados = plistlib.load(f)
    assert dados["RunAtLoad"] is True
    assert dados["ProgramArguments"][-1] == "--segundo-plano"
    assert "--segundo-plano" in inicializacao.linha_atual()
    assert inicializacao.definir(False) is True
    assert inicializacao.ativado() is False
    assert inicializacao.definir(False) is True         # ja estava desligado


def test_pasta_dos_dados_no_mac_fica_em_application_support(monkeypatch):
    monkeypatch.setattr(plataforma, "MAC", True)
    monkeypatch.setattr(os.path, "expanduser", lambda p: "/Users/ana"
                        if p == "~" else p)
    assert plataforma.pasta_base_dos_dados().replace("\\", "/") == \
        "/Users/ana/Library/Application Support"


def test_instalacao_do_windows_nao_se_aplica_ao_mac(monkeypatch):
    from telezapp.nucleo import instalacao
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert instalacao.pasta_do_programa() is None


def test_aviso_de_voiceover_nao_derruba_sem_pyobjc(monkeypatch):
    from telezapp.acessibilidade import fala
    f = fala.Fala()
    monkeypatch.setattr(f, "_nvda_ativo", lambda: False)
    monkeypatch.setattr(f, "_jaws", lambda: None)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "AppKit", None)    # import falha
    assert f._voiceover() is False
    assert f._leitor_ativo() == (None, None)

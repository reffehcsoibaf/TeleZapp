# SPDX-License-Identifier: GPL-3.0-or-later
"""Conferencia da copia em uso com a lista publicada na Release."""
import io
import urllib.error

import pytest

from telezapp.nucleo import copia_oficial as co


@pytest.fixture
def programa(tmp_path):
    pasta = tmp_path / "TeleZapp"
    (pasta / "_internal").mkdir(parents=True)
    (pasta / "TeleZapp.exe").write_bytes(b"programa")
    (pasta / "_internal" / "a.dll").write_bytes(b"biblioteca")
    return pasta


def _lista(programa):
    return lambda: co.ler_lista(co.gerar_lista(str(programa)))


def test_copia_igual_e_oficial_e_ignora_dados_e_marcas(programa):
    baixar = _lista(programa)
    lista = baixar()
    assert set(lista) == {"TeleZapp.exe", "_internal/a.dll"}
    (programa / "dados").mkdir()
    (programa / "dados" / "plugin.dll").write_bytes(b"dos dados")
    (programa / "sem-boas-vindas.txt").write_text("x")
    assert co.conferir_programa(str(programa), lambda: lista) == co.OFICIAL


@pytest.mark.parametrize("mexer", [
    lambda p: (p / "TeleZapp.exe").write_bytes(b"presentinho"),
    lambda p: (p / "_internal" / "a.dll").unlink(),
    lambda p: (p / "_internal" / "b.dll").write_bytes(b"a mais"),
])
def test_arquivo_alterado_faltando_ou_a_mais_nao_e_oficial(programa, mexer):
    lista = _lista(programa)()
    mexer(programa)
    assert co.conferir_programa(str(programa), lambda: lista) == co.MODIFICADA


def test_versao_nao_publicada_e_falha_de_rede_sao_coisas_diferentes(programa):
    assert co.conferir_programa(str(programa), lambda: None) == \
        co.NAO_PUBLICADA

    def sem_rede():
        raise urllib.error.URLError("sem internet")
    assert co.conferir_programa(str(programa), sem_rede) == co.SEM_CONFERIR


def test_baixar_lista_distingue_404_de_outros_erros():
    def responde(codigo):
        def abrir(pedido, tempo):
            raise urllib.error.HTTPError(pedido.full_url, codigo, "x", {},
                                         io.BytesIO())
        return abrir
    assert co.baixar_lista("2026.1.1.0", responde(404)) is None
    with pytest.raises(urllib.error.HTTPError):
        co.baixar_lista("2026.1.1.0", responde(500))
    urls = []

    class Resposta(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def abrir(pedido, tempo):
        urls.append(pedido.full_url)
        return Resposta(("a" * 64 + " *TeleZapp.exe\n").encode())
    assert co.baixar_lista("2026.1.1.0", abrir) == {"TeleZapp.exe": "a" * 64}
    assert urls[0].startswith(
        "https://github.com/reffehcsoibaf/TeleZapp/releases/download/"
        "2026.1.1.0/")


def test_lista_invalida_fica_sem_conferir(programa):
    with pytest.raises(ValueError):
        co.ler_lista("<html>pagina de erro</html>")

    def invalida():
        raise ValueError("x")
    assert co.conferir_programa(str(programa), invalida) == co.SEM_CONFERIR


def test_instalador_confere_o_proprio_arquivo(programa, tmp_path):
    exe = tmp_path / "instalador.exe"
    exe.write_bytes(b"instalador")
    lista = co.ler_lista(co.gerar_lista(str(programa), str(exe)))
    assert co.conferir_instalador(str(exe), lambda: lista) == co.OFICIAL
    # a linha do instalador nao conta como arquivo que falta no programa
    assert co.conferir_programa(str(programa), lambda: lista) == co.OFICIAL
    exe.write_bytes(b"alterado")
    assert co.conferir_instalador(str(exe), lambda: lista) == co.MODIFICADA


def test_quem_busca_atualizacoes():
    assert not co.sem_atualizacoes(co.OFICIAL)
    assert not co.sem_atualizacoes(co.SEM_CONFERIR)
    for estado in (co.MODIFICADA, co.NAO_PUBLICADA, co.CODIGO_FONTE):
        assert co.sem_atualizacoes(estado)
    assert co.nao_oficial(co.MODIFICADA) and co.nao_oficial(co.NAO_PUBLICADA)
    assert not co.nao_oficial(co.CODIGO_FONTE)
    assert co.conferir_programa() == co.CODIGO_FONTE       # nos testes

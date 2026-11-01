# SPDX-License-Identifier: GPL-3.0-or-later
"""Consulta de versao nova e montagem da Release."""
import importlib.util
import os
import urllib.error
import zipfile

import pytest

from telezapp.nucleo import atualizacao as at

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def release(tag, **k):
    return dict(tag_name=tag, body="notas " + tag, html_url="https://x/" + tag,
                prerelease=False, draft=False, **k)


def test_pega_a_versao_mais_alta_ignorando_rascunhos_e_tags_estranhas():
    dados = [release("2026.10.17.0"), release("v2026.10.18.1"),
             release("2026.10.18.0"), release("beta"),
             dict(release("2027.1.1.0"), draft=True)]
    lanc = at.mais_nova(dados)
    assert lanc.versao == "2026.10.18.1" and lanc.notas.endswith("18.1")
    assert at.mais_nova([]) is None and at.mais_nova({"message": "x"}) is None


def test_arquivo_do_dia_uma_vez_por_dia_e_so_empacotado():
    assert at.deve_baixar_do_dia(None, "2026-10-31", True)
    assert at.deve_baixar_do_dia("2026-10-30", "2026-10-31", True)
    assert not at.deve_baixar_do_dia("2026-10-31", "2026-10-31", True)
    assert not at.deve_baixar_do_dia(None, "2026-10-31", False)


def test_arquivo_do_dia_nao_manda_nada_e_falha_em_silencio(monkeypatch):
    pedidos = []

    def falha(pedido, timeout, context):
        pedidos.append(pedido)
        raise urllib.error.URLError("sem rede")
    monkeypatch.setattr(at.urllib.request, "urlopen", falha)
    at.baixar_arquivo_do_dia()
    assert pedidos[0].full_url == at.URL_DO_DIA and "?" not in at.URL_DO_DIA
    assert pedidos[0].data is None
    assert set(pedidos[0].headers) == {"User-agent"}


def test_consulta_valida_o_certificado_pelo_windows(monkeypatch):
    monkeypatch.setattr(at, "_contexto", None)
    contexto = at.contexto_ssl()
    assert type(contexto).__module__.startswith("truststore")
    assert at.contexto_ssl() is contexto
    usado = []

    def abre(pedido, timeout, context):
        usado.append(context)
        raise urllib.error.URLError("sem rede")
    monkeypatch.setattr(at.urllib.request, "urlopen", abre)
    with pytest.raises(urllib.error.URLError):
        at._buscar_json("https://x")
    assert usado == [contexto]


def test_sem_a_biblioteca_fica_a_validacao_do_python(monkeypatch):
    import builtins
    monkeypatch.setattr(at, "_contexto", None)
    importar = builtins.__import__

    def sem_truststore(nome, *a, **k):
        if nome == "truststore":
            raise ImportError(nome)
        return importar(nome, *a, **k)
    monkeypatch.setattr(builtins, "__import__", sem_truststore)
    assert at.contexto_ssl() is None


def test_compara_versoes_como_numeros():
    nova = at.Lancamento("2026.10.18.10", "", "")
    assert at.e_mais_nova(nova, "2026.10.18.9")
    assert not at.e_mais_nova(nova, "2026.10.18.10")
    assert not at.e_mais_nova(nova, "2026.11.1.0")


def test_consultar_traduz_erro_de_rede():
    def sem_rede(url):
        raise urllib.error.URLError("sem rede")
    with pytest.raises(at.ErroAtualizacao):
        at.consultar(sem_rede)
    assert at.consultar(lambda url: [release("2026.10.18.0")]).versao \
        == "2026.10.18.0"


def _publicar():
    spec = importlib.util.spec_from_file_location(
        "publicar", os.path.join(RAIZ, "ferramentas", "publicar.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_notas_da_release_trazem_aviso_novidades_e_hash():
    pub = _publicar()
    versao = pub.versao_atual()
    notas = pub.montar_notas(versao, "abc123", "TeleZapp-%s.zip" % versao)
    assert "Software experimental" in notas and "abc123" in notas
    assert "(Sem texto de novidades" not in notas
    assert "<li>" not in notas


def test_zip_da_release_tem_a_pasta_telezapp(tmp_path):
    pub = _publicar()
    pasta = tmp_path / "dist"
    (pasta / "_internal").mkdir(parents=True)
    (pasta / "TeleZapp.exe").write_bytes(b"MZ")
    (pasta / "_internal" / "x.dll").write_bytes(b"x")
    destino = tmp_path / "t.zip"
    h = pub.montar_zip(str(pasta), str(destino))
    assert len(h) == 64
    with zipfile.ZipFile(destino) as z:
        assert sorted(z.namelist()) == ["TeleZapp/TeleZapp.exe",
                                        "TeleZapp/_internal/x.dll"]
    with pytest.raises(SystemExit):
        pub.montar_zip(str(tmp_path), str(tmp_path / "u.zip"))


def _release_com_notas(tag, itens):
    corpo = ("> **Software experimental.**\n\n## Novidades da versão %s\n\n%s"
             "\n\n## Como usar\n\n1. Baixe.\n\nSHA-256 do zip: `abc`\n" % (
                 tag, "\n".join("- " + i for i in itens)))
    return dict(release(tag), body=corpo)


def test_historico_junta_as_novidades_desde_a_versao_em_uso():
    dados = [_release_com_notas("2026.10.20.0", ["C"]),
             _release_com_notas("2026.10.19.1", ["B"]),
             _release_com_notas("2026.10.19.0", ["A"]),
             _release_com_notas("2026.10.18.0", ["velho"])]
    lanc = at.mais_nova(dados, atual="2026.10.19.0")
    assert lanc.versao == "2026.10.20.0"
    assert lanc.historico == [("2026.10.20.0", "- C"),
                              ("2026.10.19.1", "- B")]
    # quem esta duas versoes atras recebe as tres
    assert [v for v, _ in at.mais_nova(dados, atual="2026.10.18.0")
            .historico] == ["2026.10.20.0", "2026.10.19.1", "2026.10.19.0"]
    # sem a secao de novidades, usa as notas inteiras
    assert at.novidades_do_corpo("so isto", "2026.1.1.0") == "so isto"
    assert at.novidades_do_corpo("", "2026.1.1.0").startswith("(sem")


def test_notas_trazem_os_hashes_que_a_pagina_confere(tmp_path):
    pub = _publicar()
    lista = tmp_path / "lista.txt"
    lista.write_text("%s *TeleZapp.exe\n%s *_internal/a.dll\n"
                     "%s *instalador/TeleZapp.exe\n" % ("a" * 64, "b" * 64,
                                                        "c" * 64))
    assert pub.hashes_da_conferencia(str(lista)) == ("c" * 64, "a" * 64)
    notas = pub.montar_notas("2026.1.1.0", "d" * 64, "TeleZapp.zip",
                             *pub.hashes_da_conferencia(str(lista)))
    assert "SHA-256 do zip: `%s`" % ("d" * 64) in notas
    assert "SHA-256 do instalador: `%s`" % ("c" * 64) in notas
    assert "pasta): `%s`" % ("a" * 64) in notas
    assert "b" * 64 not in notas


def test_notas_do_publicar_voltam_inteiras_pelo_novidades_do_corpo():
    pub = _publicar()
    versao = pub.versao_atual()
    notas = pub.montar_notas(versao, "abc123", "TeleZapp.zip")
    texto = at.novidades_do_corpo(notas, versao)
    assert "Software experimental" not in texto and "abc123" not in texto
    assert "Como usar" not in texto and texto.startswith("- ")


def test_texto_da_janela_de_atualizacao():
    from telezapp.interface.atualizacao import texto_da_atualizacao
    lanc = at.Lancamento("2026.10.20.0", "", "p", True, tamanho=3145728,
                         historico=[("2026.10.20.0", "- C"),
                                    ("2026.10.19.1", "- B")])
    t = texto_da_atualizacao(lanc, "2026.10.19.0", True, "D:/dados")
    assert t.startswith("Versão 2026.10.20.0 do TeleZapp disponível")
    assert "versão 2026.10.19.0" in t and "pré-lançamento" in t
    assert "3 MB" in t and t.index("- C") < t.index("- B")
    assert "Deseja baixar e instalar" in t
    sem = texto_da_atualizacao(lanc, "2026.10.19.0", False, "D:/dados")
    assert "Deseja baixar" not in sem and "página de download" in sem


def test_aviso_ao_abrir_repete_ate_atualizar_ou_marcar_nao_avisar():
    nova = at.Lancamento("2099.11.1.0", "", "p", False)
    assert at.deve_avisar_ao_abrir(nova, "")             # nunca marcou
    assert at.deve_avisar_ao_abrir(nova, None)
    assert at.deve_avisar_ao_abrir(nova, "")             # abriu de novo: avisa
    # marcou "nao avisar mais nesta versao": nao avisa dessa
    assert not at.deve_avisar_ao_abrir(nova, "2099.11.1.0")
    # saiu outra versao: avisa de novo
    mais_nova = at.Lancamento("2099.11.2.0", "", "p", False)
    assert at.deve_avisar_ao_abrir(mais_nova, "2099.11.1.0")
    # nada novo (ja atualizado, ou a consulta nao trouxe versao): nao avisa
    velha = at.Lancamento("2020.1.1.0", "", "p", False)
    assert not at.deve_avisar_ao_abrir(velha, "")
    assert not at.deve_avisar_ao_abrir(None, "")


def test_pergunta_depois_do_nao_diz_a_versao_e_as_duas_respostas():
    from telezapp.interface import atualizacao as janela
    t = janela.texto_da_pergunta("2026.11.1.0")
    assert "2026.11.1.0" in t and "Talvez mais tarde:" in t
    assert "Não me avise mais sobre essa versão:" in t
    assert "próxima vez que você abrir" in t and "outra versão" in t
    # os botoes da pergunta (com a tecla de acesso) sao esses dois
    assert janela.BOTAO_NAO_AVISAR == "&Não me avise mais sobre essa versão"
    assert janela.BOTAO_MAIS_TARDE == "&Talvez mais tarde"


def test_janela_de_erro_oferece_a_pagina_de_download(monkeypatch):
    import types

    from telezapp.interface import atualizacao as janela
    rotulos = []

    class Dialogo:
        resposta = None

        def __init__(self, pai, texto, titulo, estilo):
            assert texto == "falhou"
            # sem o Cancelar, o Esc nao fecha a janela
            assert estilo & janela.wx.CANCEL

        def SetOKCancelLabels(self, sim, nao):
            rotulos.append((sim, nao))

        def ShowModal(self):
            return Dialogo.resposta

        def Destroy(self):
            pass
    monkeypatch.setattr(janela, "wx", types.SimpleNamespace(
        MessageDialog=Dialogo, OK=1, CANCEL=2, ICON_WARNING=4,
        ID_OK=10, ID_CANCEL=20))
    Dialogo.resposta = janela.wx.ID_OK
    assert janela.erro_quer_a_pagina(None, "falhou")
    Dialogo.resposta = janela.wx.ID_CANCEL
    assert not janela.erro_quer_a_pagina(None, "falhou")
    assert rotulos[0] == ("&Abrir a página de download", "&Fechar")
    assert at.URL_ULTIMA.endswith("/releases/latest")


def test_motivos_da_falha_da_consulta_em_palavras():
    import socket
    import ssl
    http = urllib.error.HTTPError("u", 403, "rate limit", {}, None)
    assert "limitou as consultas" in at.motivo_da_falha(http)
    assert "erro 500" in at.motivo_da_falha(
        urllib.error.HTTPError("u", 500, "x", {}, None))
    certificado = at.motivo_da_falha(
        urllib.error.URLError(ssl.SSLCertVerificationError("falhou")))
    assert "certificado" in certificado and "instalador" in certificado
    assert "demorou" in at.motivo_da_falha(
        urllib.error.URLError(socket.timeout()))
    assert "endereço do GitHub" in at.motivo_da_falha(
        urllib.error.URLError(socket.gaierror(11001, "sem dns")))
    assert "formato inesperado" in at.motivo_da_falha(ValueError("x"))


def test_consultar_diz_o_motivo_quando_tudo_falha():
    def limite(url):
        raise urllib.error.HTTPError(url, 403, "rate limit", {}, None)

    def site_fora():
        raise urllib.error.URLError("sem rede")
    with pytest.raises(at.ErroAtualizacao) as e:
        at.consultar(limite, site_fora)
    assert "limitou as consultas" in str(e.value)


def test_consultar_usa_o_site_quando_a_api_recusa():
    def limite(url):
        raise urllib.error.HTTPError(url, 403, "rate limit", {}, None)
    achado = at.Lancamento("2026.10.24.0", "", "pag", False, "TeleZapp.zip",
                           "https://github.com/x/TeleZapp.zip",
                           "https://github.com/x/TeleZapp.zip.sha256")
    assert at.consultar(limite, lambda: achado) is achado


def test_plano_b_le_a_versao_do_endereco_da_ultima_release(monkeypatch):
    class Resposta:
        def __init__(self, url):
            self._url = url

        def geturl(self):
            return self._url

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    visto = []
    monkeypatch.setattr(at.urllib.request, "urlopen", lambda p, timeout=0,
                        context=None: (
        visto.append(p.full_url) or Resposta(
            at.SITE + "/releases/tag/2026.10.24.0")))
    lanc = at._pelo_site()
    assert visto == [at.SITE + "/releases/latest"]
    assert lanc.versao == "2026.10.24.0" and not lanc.pre
    assert lanc.url_zip == at.SITE + \
        "/releases/download/2026.10.24.0/TeleZapp.zip"
    assert lanc.url_hash == lanc.url_zip + ".sha256"
    monkeypatch.setattr(at.urllib.request, "urlopen",
                        lambda p, timeout=0, context=None:
                        Resposta(at.SITE + "/releases"))   # sem tag
    with pytest.raises(ValueError):
        at._pelo_site()

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
    nova = at.Lancamento("2026.11.1.0", "", "p", False)
    assert at.deve_avisar_ao_abrir(nova, "")             # nunca marcou
    assert at.deve_avisar_ao_abrir(nova, None)
    assert at.deve_avisar_ao_abrir(nova, "")             # abriu de novo: avisa
    # marcou "nao avisar mais nesta versao": nao avisa dessa
    assert not at.deve_avisar_ao_abrir(nova, "2026.11.1.0")
    # saiu outra versao: avisa de novo
    mais_nova = at.Lancamento("2026.11.2.0", "", "p", False)
    assert at.deve_avisar_ao_abrir(mais_nova, "2026.11.1.0")
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

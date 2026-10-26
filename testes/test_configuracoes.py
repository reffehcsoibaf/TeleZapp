# SPDX-License-Identifier: GPL-3.0-or-later
"""Modelo da janela de configuracoes (sem wx)."""
import pytest

from telezapp import config
from telezapp.nucleo.configuracoes import (CATEGORIA_BUSCA,
                                           ModeloConfiguracoes, categorias)


@pytest.fixture
def mod(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path))
    return ModeloConfiguracoes(config.Config())


def test_categorias_sem_repeticao_e_com_todas_as_opcoes(mod):
    cats = categorias()
    assert len(cats) == len(set(cats))
    todas = [o for c in cats for o in mod.opcoes(c)] + [
        o for c in cats for g in mod.grupos(c)
        for o in mod.opcoes_do_grupo(c, g)]
    assert sorted(todas, key=config.OPCOES.index) ==         sorted(config.OPCOES, key=config.OPCOES.index)
    assert len(todas) == len(config.OPCOES)
    assert cats[-3:] == ["Privacidade", "Avançado", "Atualizações"]


def test_busca_acrescenta_categoria_de_resultados(mod):
    assert CATEGORIA_BUSCA not in mod.lista_de_categorias()
    mod.busca = "velocidade audio"
    cats = mod.lista_de_categorias()
    assert cats[0] == CATEGORIA_BUSCA
    chaves = [o.chave for o in mod.opcoes(CATEGORIA_BUSCA)]
    assert "audio_velocidade" in chaves and "som" not in chaves


def test_pendentes_so_valem_ao_aplicar_e_voltar_ao_atual_desfaz(mod):
    mod.definir("estilo", 2)
    assert mod.valor("estilo") == 2
    assert mod.cfg.get("estilo") == 1
    mod.definir("estilo", 1)
    assert mod.mudancas() == []


def test_aplicar_na_ordem_das_opcoes_e_zera(mod):
    mod.definir("audio_velocidade", 2.0)
    mod.definir("audio_passo_velocidade", 0.5)
    mod.definir("status_no_titulo", False)
    feitas = []
    quais = mod.aplicar(lambda c, v: feitas.append((c, v)))
    assert [c for c, _ in feitas] == ["status_no_titulo", "audio_passo_velocidade",
                                      "audio_velocidade"]
    assert quais == [c for c, _ in feitas]
    assert mod.pendentes == {}


def test_indice_da_escolha(mod):
    o = next(o for o in config.OPCOES if o.chave == "estilo")
    assert mod.indice_da_escolha(o) == 0
    mod.definir("estilo", 3)
    assert mod.indice_da_escolha(o) == 2


def test_velocidades_seguem_o_passo_pendente(mod):
    o = next(o for o in config.OPCOES if o.chave == "audio_velocidade")
    assert len(mod.escolhas(o)) == 12
    mod.definir("audio_velocidade", 1.75)
    mod.definir("audio_passo_velocidade", 1.0)
    assert [v for v, _ in mod.escolhas(o)] == [1.0, 2.0, 3.0]
    assert mod.valor("audio_velocidade") in (1.0, 2.0)
    assert mod.indice_da_escolha(o) in (0, 1)
    mod.definir("audio_passo_velocidade", 0.5)
    assert [v for v, _ in mod.escolhas(o)][:3] == [0.5, 1.0, 1.5]


def test_falar_descricoes_e_opcao_de_leitura_ligada_por_padrao(mod):
    o = next(o for o in config.OPCOES if o.chave == "falar_descricoes")
    assert o.categoria == "Interface" and o.padrao is True
    assert mod.valor("falar_descricoes") is True
    mod.definir("falar_descricoes", False)
    assert mod.valor("falar_descricoes") is False   # vale ja na janela


def test_opcao_numerica_e_limitada_ao_intervalo(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path))
    from telezapp import config
    from telezapp.nucleo.configuracoes import ModeloConfiguracoes
    mod = ModeloConfiguracoes(config.Config())
    mod.definir("mensagens_por_conversa", 10)
    assert mod.valor("mensagens_por_conversa") == 50
    mod.definir("mensagens_por_conversa", 99999)
    assert mod.valor("mensagens_por_conversa") == 5000
    mod.definir("mensagens_por_conversa", "abc")
    assert mod.valor("mensagens_por_conversa") == 1200   # padrao: nada pendente
    assert "mensagens_por_conversa" not in mod.pendentes


# ------------------------------------------ codigo secreto das trancadas
def _modelo(tmp_path, monkeypatch, codigo=None):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path))
    from telezapp import config
    from telezapp.nucleo import codigo_secreto
    from telezapp.nucleo.configuracoes import ModeloConfiguracoes
    cfg = config.Config()
    if codigo:
        cfg.set("codigo_trancadas", codigo_secreto.criar(codigo))
    return ModeloConfiguracoes(cfg)


def _preencher(mod, atual="", novo="", repita=""):
    mod.definir_codigo("atual", atual)
    mod.definir_codigo("novo", novo)
    mod.definir_codigo("repita", repita)


def test_primeiro_codigo_exige_valor_valido_e_igual(tmp_path, monkeypatch):
    mod = _modelo(tmp_path, monkeypatch)
    assert mod.erro_codigo() == ""        # padrao ligado, nada mexido: ok
    mod.definir("trancadas_exigir_codigo", False)
    mod.definir("trancadas_exigir_codigo", True)   # volta ao padrao
    _preencher(mod, novo="12")
    assert "4 a 12" in mod.erro_codigo() or "iguais" in mod.erro_codigo()
    _preencher(mod, novo="1234", repita="1235")
    assert "iguais" in mod.erro_codigo()
    _preencher(mod, novo="1234", repita="1234")
    assert mod.erro_codigo() == ""
    guardados = []
    mod.aplicar(lambda c, v: guardados.append((c, v)))
    assert ("codigo_trancadas", "1234") in guardados


def test_mudar_ou_desligar_pede_o_codigo_atual(tmp_path, monkeypatch):
    mod = _modelo(tmp_path, monkeypatch, codigo="2468")
    _preencher(mod, novo="1357", repita="1357")      # sem o atual
    assert "código atual" in mod.erro_codigo()
    _preencher(mod, atual="0000", novo="1357", repita="1357")
    assert "código atual" in mod.erro_codigo()
    _preencher(mod, atual="2468", novo="1357", repita="1357")
    assert mod.erro_codigo() == ""
    _preencher(mod)                                   # desligar sem o atual
    mod.definir("trancadas_exigir_codigo", False)
    assert "código atual" in mod.erro_codigo()
    _preencher(mod, atual="2468")
    assert mod.erro_codigo() == ""
    aplicadas = []
    mod.aplicar(lambda c, v: aplicadas.append((c, v)))
    assert ("trancadas_exigir_codigo", False) in aplicadas
    assert ("codigo_trancadas", None) in aplicadas    # sai junto
    assert mod.codigo == {"atual": "", "novo": "", "repita": ""}


def test_nada_a_fazer_com_codigo_existente_nao_bloqueia(tmp_path, monkeypatch):
    mod = _modelo(tmp_path, monkeypatch, codigo="2468")
    mod.definir("status_no_titulo", False)                         # outra opcao qualquer
    assert mod.erro_codigo() == ""
    aplicadas = []
    mod.aplicar(lambda c, v: aplicadas.append(c))
    assert aplicadas == ["status_no_titulo"]


def test_falas_automaticas_do_audio_vem_desmarcadas():
    from telezapp import config
    for chave in ("falar_novas", "confirmar_envio", "falar_reacoes",
                  "falar_quem_toca", "seq_falar_proximo", "seq_falar_tipo",
                  "seq_falar_quem", "seq_falar_duracao",
                  "seq_falar_velocidade"):
        assert config.PADROES[chave] is False, chave


def test_mudancas_de_privacidade_vao_ao_aplicador(tmp_path, monkeypatch):
    mod = _modelo(tmp_path, monkeypatch)
    mod.priv_carregado["w1"] = {"last": "all", "online": "all",
                                "status": "all", "readreceipts": "all",
                                "groupadd": "all"}
    mod.priv_definir("w1", "last", 2)            # Ninguem
    mod.priv_definir("w1", "readreceipts", 0)    # igual ao que ja era
    assert mod.priv_mudancas() == [("w1", "last", "none")]
    recebidas = []
    mod.aplicar(lambda c, v: recebidas.append((c, v)))
    assert recebidas == [("privacidade_conta", [("w1", "last", "none")])]
    assert mod.priv_mudancas() == []             # zerou


def _registro():
    from telezapp.nucleo import atalhos as at
    r = at.Registro()
    r.registrar("a", "&Alfa\tCtrl+1", "Mensagens", "Ctrl+1")
    r.registrar("b", "&Beta", "Mensagens")
    return r


def test_categoria_atalhos_existe(mod):
    assert "Atalhos" in categorias()


def test_atalho_definir_avisa_do_conflito_e_substitui(mod):
    mod.registro = _registro()
    outro = mod.atalho_definir("b", "Ctrl+1")
    assert outro.chave == "a"
    assert mod.atalho_de("b") == "" and mod.atalho_de("a") == "Ctrl+1"
    assert mod.atalhos_pendentes is None
    assert mod.atalho_definir("b", "Ctrl+1", substituir=True) is None
    assert mod.atalho_de("b") == "Ctrl+1" and mod.atalho_de("a") == ""


def test_atalhos_so_valem_ao_aplicar_e_voltar_ao_padrao_desfaz(mod):
    mod.registro = _registro()
    assert mod.atalho_definir("b", "Ctrl+2") is None
    assert mod.atalhos_pendentes == {"b": "Ctrl+2"}
    assert mod.registro.efetivo("b") == ""           # ainda nao aplicado
    assert mod.atalho_restaurar("b") is None
    assert mod.atalhos_pendentes is None
    mod.atalho_definir("a", "")                      # tirar o atalho
    feitas = []
    mod.aplicar(lambda k, v: feitas.append((k, v)))
    assert feitas == [("atalhos", {"a": ""})]
    assert mod.registro.efetivo("a") == ""
    assert mod.atalhos_pendentes is None


def test_atalhos_restaurar_todos(mod):
    mod.registro = _registro()
    mod.atalho_definir("b", "Ctrl+2")
    mod.registro.definir_personalizados({"b": "Ctrl+2"})
    mod.atalhos_pendentes = None
    mod.atalhos_restaurar_todos()
    assert mod.atalhos_pendentes == {}
    assert mod.atalho_de("b") == ""


def test_atalhos_lista_filtra_pela_busca(mod):
    mod.registro = _registro()
    assert [a.chave for a, _ in mod.atalhos_lista("beta")] == ["b"]
    assert [a.chave for a, _ in mod.atalhos_lista("")] == ["a", "b"]


def test_interface_e_mensagens_reunem_as_categorias_antigas(mod):
    cats = categorias()
    assert "Avisos" not in cats and "Leitura" not in cats
    assert "Escrita" not in cats
    assert "Interface" in cats and "Mensagens" in cats
    assert mod.grupos("Interface") == ["Conteúdo falado"]
    falado = {o.chave for o in mod.opcoes_do_grupo("Interface",
                                                   "Conteúdo falado")}
    assert falado == {"falar_novas", "falar_novas_outras_conversas",
                      "falar_novas_fora_do_telezapp", "confirmar_envio",
                      "falar_reacoes", "falar_descricoes"}
    soltas = {o.chave for o in mod.opcoes("Interface")}
    assert soltas == {"status_no_titulo", "avisar_chamadas_whatsapp",
                      "ocultar_contatos_duplicados",
                      "digitar_na_lista"}
    assert {"ortografia_idioma", "enter_envia", "estilo",
            "previa_links"} <= {o.chave for o in mod.opcoes("Mensagens")}


def test_busca_acha_opcao_dentro_de_um_grupo(mod):
    mod.busca = "reacoes"
    assert "falar_reacoes" in [o.chave for o in mod.opcoes(CATEGORIA_BUSCA)]

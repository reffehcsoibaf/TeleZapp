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
    mod.definir("previa_links", "titulo")
    assert mod.valor("previa_links") == "titulo"
    assert mod.cfg.get("previa_links") == "completa"
    mod.definir("previa_links", "completa")
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
    o = next(o for o in config.OPCOES if o.chave == "previa_links")
    assert mod.indice_da_escolha(o) == 0
    mod.definir("previa_links", "titulo")
    assert mod.indice_da_escolha(o) == 1


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
    # nenhuma opcao usa o campo numerico hoje; o recurso fica para as proximas
    numerica = config.Opcao("numerica", "Numérica", "Mensagens", 1200, "",
                            numero=(50, 5000))
    monkeypatch.setattr(config, "OPCOES", list(config.OPCOES) + [numerica])
    cfg = config.Config()
    cfg.set("numerica", 1200)
    mod = ModeloConfiguracoes(cfg)
    mod.definir("numerica", 10)
    assert mod.valor("numerica") == 50
    mod.definir("numerica", 99999)
    assert mod.valor("numerica") == 5000
    mod.definir("numerica", "abc")
    assert mod.valor("numerica") == 1200   # padrao: nada pendente
    assert "numerica" not in mod.pendentes


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
                      "falar_reacoes", "falar_descricoes",
                      "falar_quantas_no_filtro"}
    soltas = {o.chave for o in mod.opcoes("Interface")}
    assert soltas == {"status_no_titulo", "avisar_chamadas_whatsapp",
                      "ocultar_contatos_duplicados",
                      "trazer_contatos_ao_abrir",
                      "como_me_chamar"}
    assert "prioridade_abertura" in {o.chave for o in mod.opcoes("Sistema")}
    assert "estilo" not in {o.chave for o in config.OPCOES}   # virou a lista
    assert {"ortografia_idioma", "enter_envia",
            "previa_links"} <= {o.chave for o in mod.opcoes("Mensagens")}


def test_busca_acha_opcao_dentro_de_um_grupo(mod):
    mod.busca = "reacoes"
    assert "falar_reacoes" in [o.chave for o in mod.opcoes(CATEGORIA_BUSCA)]


def _destinos(mod, texto):
    mod.busca = texto
    return mod.destinos_da_busca()


def test_busca_sem_texto_nao_tem_destinos(mod):
    assert _destinos(mod, "  ") == []


def test_busca_acha_o_que_fica_nas_janelas_das_listas(mod):
    achados = {(d.tipo, d.alvo) for d in _destinos(mod, "digitar uma letra")}
    assert achados == {("lista_conversas", "digitar"),
                       ("lista_mensagens", "digitar")}
    assert ("lista_mensagens", "so_muda") in {
        (d.tipo, d.alvo) for d in _destinos(mod, "só quando muda")}
    assert ("lista_conversas", "previa") in {
        (d.tipo, d.alvo) for d in _destinos(mod, "trecho da ultima")}
    assert ("lista_mensagens", "digitar") in {
        (d.tipo, d.alvo) for d in _destinos(mod, "escrever a mensagem")}


def test_busca_cobre_cada_item_das_telas_proprias(mod):
    from telezapp.nucleo import lista_conversas as lc
    from telezapp.nucleo import lista_mensagens as lm
    from telezapp.nucleo import pacotes_de_som as ps
    from telezapp.nucleo import privacidade_conta as pw
    from telezapp.nucleo.ia import catalogo
    casos = ([("lista_conversas", c, r) for c, r in lc.ITENS] +
             [("lista_mensagens", c, r) for c, r in lm.ITENS] +
             [("sons", c, r) for c, r in ps.eventos()] +
             [("privacidade", c.nome, c.rotulo) for c in pw.CAMPOS] +
             [("privacidade", n, r) for n, r in pw.ROTULOS_TELEGRAM.items()] +
             [("ia", t, n) for t, n in catalogo.NOMES_DE_TAREFA.items()] +
             [("provedor_ia", p.chave, p.nome)
              for p in catalogo.PROVEDORES.values()])
    for tipo, alvo, rotulo in casos:
        assert (tipo, alvo) in {(d.tipo, d.alvo)
                                for d in _destinos(mod, rotulo)}, rotulo


def test_busca_acha_os_campos_do_codigo_e_a_chave_da_ia(mod):
    assert "codigo" in {d.tipo for d in _destinos(mod, "novo código")}
    assert "provedor_ia" in {d.tipo for d in _destinos(mod, "chave gemini")}


def test_busca_acha_as_escolhas_das_opcoes(mod):
    mod.busca = "só o título"
    assert "previa_links" in [o.chave for o in mod.opcoes(CATEGORIA_BUSCA)]


def test_busca_de_atalhos_acha_a_funcao_ou_junta_muitas(mod, monkeypatch):
    from telezapp.nucleo import configuracoes as nc
    mod.registro = _registro()
    assert [(d.tipo, d.alvo) for d in _destinos(mod, "beta")
            if d.tipo == "atalhos"] == [("atalhos", "b")]
    monkeypatch.setattr(nc, "LIMITE_ATALHOS_NA_BUSCA", 1)
    juntos = [d for d in _destinos(mod, "atalhos")
              if d.tipo == "atalhos_busca"]
    assert len(juntos) == 1 and juntos[0].alvo == ""
    assert "2 funções" in juntos[0].rotulo

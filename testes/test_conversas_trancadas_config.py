# SPDX-License-Identifier: GPL-3.0-or-later
"""Em Configuracoes, Privacidade, a opcao das conversas trancadas e o codigo
secreto ficam atras do botao Conversas trancadas (com wx falso)."""
import sys
import types

from testes import wx_falso

sys.modules["wx"] = wx_falso

from telezapp import config  # noqa: E402
from telezapp.interface import configuracoes as ui  # noqa: E402
from telezapp.nucleo.configuracoes import ModeloConfiguracoes  # noqa: E402


def _modelo(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path / "dados"))
    return ModeloConfiguracoes(config.Config())


def test_privacidade_tem_o_botao_conversas_trancadas(tmp_path, monkeypatch):
    mod = _modelo(tmp_path, monkeypatch)
    assert "Conversas trancadas" in mod.grupos("Privacidade")
    soltas = {o.chave for o in mod.opcoes("Privacidade")}
    assert "trancadas_exigir_codigo" not in soltas      # saiu da tela solta
    dentro = {o.chave for o in mod.opcoes_do_grupo("Privacidade",
                                                   "Conversas trancadas")}
    assert dentro == {"trancadas_exigir_codigo"}
    # a busca continua achando a opcao
    assert "trancadas_exigir_codigo" in {
        o.chave for o in config.buscar_opcoes("trancadas")}


def test_janela_conversas_trancadas_traz_a_caixa_e_os_campos(tmp_path,
                                                             monkeypatch):
    mod = _modelo(tmp_path, monkeypatch)
    mod.definir_codigo("novo", "1234")           # digitado antes, na janela
    pai = types.SimpleNamespace(modelo=mod, fala=None, _espera=None)
    dlg = ui.DialogoGrupoOpcoes(
        pai, "Conversas trancadas",
        mod.opcoes_do_grupo("Privacidade", "Conversas trancadas"))
    assert "trancadas_exigir_codigo" in dlg.caixas
    # sem codigo guardado: so os campos do novo codigo (marcada por padrao)
    assert set(dlg.campos_codigo) == {"atual", "novo", "repita"}
    assert dlg.campos_codigo["atual"][2] is False
    # o que ja foi digitado reaparece ao reabrir a janela
    assert dlg.campos_codigo["novo"][1].GetValue() == "1234"
    # desmarcar a caixa esconde os campos novos
    dlg.caixas["trancadas_exigir_codigo"].SetValue(False)
    dlg._ao_marcar(mod.opcoes_do_grupo("Privacidade", "Conversas trancadas")[0],
                   dlg.caixas["trancadas_exigir_codigo"])
    assert mod.valor("trancadas_exigir_codigo") is False
    assert not dlg.campos_codigo["novo"][1].visivel

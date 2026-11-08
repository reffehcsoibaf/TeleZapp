# SPDX-License-Identifier: GPL-3.0-or-later
"""Em Configuracoes, Midias, as opcoes da sequencia de audio ficam atras do
botao Sequencia de audio (com wx falso)."""
import sys
import types

from testes import wx_falso

sys.modules["wx"] = wx_falso

from telezapp import config  # noqa: E402
from telezapp.interface import configuracoes as ui  # noqa: E402
from telezapp.nucleo.configuracoes import ModeloConfiguracoes  # noqa: E402

CHAVES = {"audio_sequencia", "seq_falar_proximo", "seq_falar_tipo",
          "seq_falar_quem", "seq_falar_duracao", "seq_falar_velocidade",
          "seq_falar_fim", "seq_acompanhar"}


def _modelo(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path / "dados"))
    return ModeloConfiguracoes(config.Config())


def test_midias_tem_o_botao_sequencia_de_audio(tmp_path, monkeypatch):
    mod = _modelo(tmp_path, monkeypatch)
    assert "Sequência de áudio" in mod.grupos("Mídias")
    soltas = {o.chave for o in mod.opcoes("Mídias")}
    assert not (CHAVES & soltas)               # saíram da tela solta
    assert "falar_quem_toca" not in soltas      # (agora em Reprodução de áudio)
    dentro = {o.chave for o in mod.opcoes_do_grupo("Mídias",
                                                   "Sequência de áudio")}
    assert dentro == CHAVES


def test_janela_traz_a_caixa_combinada_com_rotulo_e_as_de_marcar(
        tmp_path, monkeypatch):
    mod = _modelo(tmp_path, monkeypatch)
    pai = types.SimpleNamespace(modelo=mod, fala=None, _espera=None)
    wx_falso.criados.clear()
    dlg = ui.DialogoGrupoOpcoes(
        pai, "Sequência de áudio",
        mod.opcoes_do_grupo("Mídias", "Sequência de áudio"))
    assert set(dlg.caixas) == CHAVES
    escolha = dlg.caixas["audio_sequencia"]
    assert isinstance(escolha, wx_falso.Choice)
    # o rótulo da caixa combinada vem logo antes dela
    seq = list(wx_falso.criados)
    anterior = seq[seq.index(escolha) - 1]
    assert isinstance(anterior, wx_falso.StaticText)
    assert anterior.label.startswith("Sequência de áudios")
    assert escolha.GetSelection() == 0           # "sim", o padrão
    assert isinstance(dlg.caixas["seq_acompanhar"], wx_falso.CheckBox)

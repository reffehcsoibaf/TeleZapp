# SPDX-License-Identifier: GPL-3.0-or-later
"""A caixa de sons da pasta do pacote na tela de configuracoes (com wx falso)."""
import sys
import types

from testes import wx_falso

sys.modules["wx"] = wx_falso

from telezapp import config  # noqa: E402
from telezapp.interface.configuracoes import DialogoConfiguracoes  # noqa: E402
from telezapp.nucleo import pacotes_de_som as pk  # noqa: E402
from telezapp.nucleo.configuracoes import ModeloConfiguracoes  # noqa: E402


def _dialogo_com_sons(cfg, modelo):
    """O DialogoConfiguracoes sem montar a janela toda: so o que a tela de
    sons usa, com os controles falsos."""
    d = object.__new__(DialogoConfiguracoes)
    d.modelo = modelo
    d.fala = None
    d.lista_sons = wx_falso.ListBox()
    d.cx_arquivo_som = wx_falso.Choice()
    d.lbl_arquivo_som = wx_falso.StaticText()
    d.btn_procurar_som = wx_falso.Button()
    d.btn_excluir_pacote = wx_falso.Button()
    d.painel = types.SimpleNamespace(Layout=lambda: None)
    return d


def test_caixa_lista_os_arquivos_do_pacote_e_escolhe_o_som_do_evento(
        tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path / "dados"))
    cfg = config.Config()
    modelo = ModeloConfiguracoes(cfg)
    pacote_id, _ = pk.criar("Meu")
    pasta = tmp_path / "dados" / "sons" / "pacotes" / "Meu"
    (pasta / "a.ogg").write_bytes(b"x")
    (pasta / "b.wav").write_bytes(b"x")
    modelo.sons.selecionar(pacote_id)
    d = _dialogo_com_sons(cfg, modelo)

    d._sons_preencher_eventos()
    assert d.cx_arquivo_som.itens == ["a.ogg", "b.wav"]
    assert d.cx_arquivo_som.visivel and d.lbl_arquivo_som.visivel
    assert d.cx_arquivo_som.GetSelection() == -1      # "nova" ainda usa bip

    d.cx_arquivo_som.SetSelection(1)
    d._sons_escolher_arquivo()
    evento, _ = d._sons_evento()
    assert evento == "nova"
    assert modelo.sons.arquivo(pacote_id, "nova") == str(pasta / "b.wav")
    assert "som: b.wav" in d.lista_sons.GetString(0)

    # ao escolher outro evento, a caixa marca o arquivo que ele ja usa
    modelo.sons.escolher(pacote_id, "erro", str(pasta / "a.ogg"))
    indice_erro = [e for e, _ in pk.eventos()].index("erro")
    d.lista_sons.SetSelection(indice_erro)
    d._sons_mostrar_arquivo()
    assert d.cx_arquivo_som.GetSelection() == 0


def test_caixa_some_nos_pacotes_que_nao_se_editam(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path / "dados"))
    cfg = config.Config()
    modelo = ModeloConfiguracoes(cfg)
    modelo.sons.selecionar("telezapp")
    d = _dialogo_com_sons(cfg, modelo)

    d._sons_preencher_eventos()
    assert d.cx_arquivo_som.itens == []
    assert not d.cx_arquivo_som.visivel
    assert not d.lbl_arquivo_som.visivel
    assert not d.btn_procurar_som.visivel

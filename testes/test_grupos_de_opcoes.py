# SPDX-License-Identifier: GPL-3.0-or-later
"""Em Configuracoes, opcoes do mesmo assunto ficam atras de um botao (com wx
falso): Gravacao, Chamadas, Download, Enter, Reproducao de audio e Previa de
links."""
import sys
import types

from testes import wx_falso

sys.modules["wx"] = wx_falso

from telezapp import config  # noqa: E402
from telezapp.interface import configuracoes as ui  # noqa: E402
from telezapp.nucleo.configuracoes import ModeloConfiguracoes  # noqa: E402

GRUPOS = {
    ("Mídias", "Gravação"): {
        "gravar_som_com_microfone", "gravar_microfone_estereo",
        "gravar_som_estereo", "qualidade_gravacao_mono",
        "qualidade_gravacao_estereo", "volume_gravacao",
        "calar_avisos_ao_gravar"},
    ("Mídias", "Chamadas de voz e vídeo"): {
        "chamada_eco", "chamada_ruido", "video_camera_ao_atender",
        "chamada_retornar_sem_audio", "chamada_retorno"},
    ("Mídias", "Download de mídias"): {
        "midias_baixar", "midias_limite_auto_mb", "midias_passo_progresso",
        "midias_confirmar_mb", "barra_de_progresso"},
    ("Mídias", "Enter nas mídias"): {
        "enter_audio", "enter_imagem", "enter_video", "enter_pdf"},
    ("Mídias", "Reprodução de áudio"): {
        "audio_janela", "audio_passo_velocidade", "audio_velocidade",
        "falar_quem_toca", "falar_pulo_audio"},
    ("Mensagens", "Prévia de links"): {
        "previa_links", "previa_receber", "previa_enviar"},
}


def _modelo(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path / "dados"))
    return ModeloConfiguracoes(config.Config())


def test_cada_botao_reune_as_opcoes_do_assunto(tmp_path, monkeypatch):
    mod = _modelo(tmp_path, monkeypatch)
    for (categoria, grupo), chaves in GRUPOS.items():
        assert grupo in mod.grupos(categoria)
        dentro = {o.chave for o in mod.opcoes_do_grupo(categoria, grupo)}
        assert dentro == chaves
        soltas = {o.chave for o in mod.opcoes(categoria)}
        assert not (chaves & soltas)


def test_a_janela_do_grupo_cria_marcar_escolha_e_numero(
        tmp_path, monkeypatch):
    mod = _modelo(tmp_path, monkeypatch)
    pai = types.SimpleNamespace(modelo=mod, fala=None, _espera=None)
    dlg = ui.DialogoGrupoOpcoes(
        pai, "Gravação", mod.opcoes_do_grupo("Mídias", "Gravação"))
    assert set(dlg.caixas) == GRUPOS[("Mídias", "Gravação")]
    assert isinstance(dlg.caixas["volume_gravacao"], wx_falso.SpinCtrl)
    assert isinstance(dlg.caixas["qualidade_gravacao_mono"],
                      wx_falso.Choice)
    assert isinstance(dlg.caixas["gravar_som_estereo"], wx_falso.CheckBox)


def test_mudar_o_passo_refaz_a_lista_de_velocidades(tmp_path, monkeypatch):
    mod = _modelo(tmp_path, monkeypatch)
    pai = types.SimpleNamespace(modelo=mod, fala=None, _espera=None)
    dlg = ui.DialogoGrupoOpcoes(
        pai, "Reprodução de áudio",
        mod.opcoes_do_grupo("Mídias", "Reprodução de áudio"))
    vel = dlg.caixas["audio_velocidade"]
    antes = list(vel.itens)
    passo = dlg.caixas["audio_passo_velocidade"]
    opcao = next(o for o in config.OPCOES
                 if o.chave == "audio_passo_velocidade")
    indice = [v for v, _ in mod.escolhas(opcao)].index(1.0)
    passo.SetSelection(indice)
    dlg._ao_escolher(opcao, passo)
    assert mod.valor("audio_passo_velocidade") == 1.0
    assert list(vel.itens) != antes
    assert vel.GetSelection() >= 0

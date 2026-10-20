# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Janela que oferece a versao nova: o texto, somente leitura e com o foco,
diz a versao oferecida e as novidades desde a versao em uso; depois do texto
vem o Tab para os botoes Sim e Nao."""
import wx

from telezapp import NOME


def texto_da_atualizacao(lanc, atual, pode_instalar, pasta_dados):
    """O que a janela mostra. Pura, para poder ser testada."""
    linhas = ["Versão %s do %s disponível. Você usa a versão %s." % (
        lanc.versao, NOME, atual)]
    if lanc.pre:
        linhas.append("Esta versão é um pré-lançamento (experimental).")
    if lanc.tamanho:
        linhas.append("Tamanho do download: %.0f MB." %
                      (lanc.tamanho / 1048576))
    linhas += ["", "Novidades desde a sua versão:"]
    historico = lanc.historico or [(lanc.versao, lanc.notas or
                                    "(sem texto de novidades)")]
    for versao, notas in historico:
        linhas += ["", "Versão %s" % versao, notas]
    linhas.append("")
    if pode_instalar:
        linhas.append(
            "Se você instalar, o %s baixa o arquivo, confere o SHA-256, "
            "fecha e abre de novo já atualizado. Seus dados em %s não são "
            "afetados." % (NOME, pasta_dados))
        linhas.append("Deseja baixar e instalar agora? Use Tab para chegar "
                      "aos botões Sim e Não.")
    else:
        linhas.append(
            "Este %s não se atualiza sozinho. Abra a página de download, "
            "baixe o arquivo zip, feche o %s e troque a pasta do programa "
            "pela nova. Seus dados em %s não são afetados." % (
                NOME, NOME, pasta_dados))
    return "\n".join(linhas)


class DialogoAtualizacao(wx.Dialog):
    """`escolha` fica "instalar", "pagina" ou "nao"."""

    def __init__(self, pai, lanc, atual, pode_instalar, pasta_dados):
        super().__init__(pai, title="Versão nova do %s" % NOME,
                         size=(640, 520),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.escolha = "nao"
        rotulo = "Versão %s disponível e novidades" % lanc.versao
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(self, label=rotulo), 0, wx.ALL, 8)
        self.texto = wx.TextCtrl(
            self, value=texto_da_atualizacao(lanc, atual, pode_instalar,
                                             pasta_dados),
            name=rotulo, style=wx.TE_MULTILINE | wx.TE_READONLY)
        lay.Add(self.texto, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        linha = wx.BoxSizer(wx.HORIZONTAL)
        if pode_instalar:
            self.principal = wx.Button(self, wx.ID_YES, "&Sim")
            self.secundario = wx.Button(self, wx.ID_NO, "&Não")
            self.principal.Bind(wx.EVT_BUTTON,
                                lambda e: self._fechar("instalar"))
        else:
            self.principal = wx.Button(self, wx.ID_YES,
                                       "Abrir a página de &download")
            self.secundario = wx.Button(self, wx.ID_NO, "&Fechar")
            self.principal.Bind(wx.EVT_BUTTON,
                                lambda e: self._fechar("pagina"))
        self.secundario.Bind(wx.EVT_BUTTON, lambda e: self._fechar("nao"))
        linha.Add(self.principal, 0, wx.RIGHT, 8)
        linha.Add(self.secundario)
        lay.Add(linha, 0, wx.ALL | wx.ALIGN_RIGHT, 8)
        self.SetSizer(lay)
        self.SetEscapeId(wx.ID_NO)
        self.texto.SetInsertionPoint(0)
        self.texto.SetFocus()
        self.CentreOnParent()

    def _fechar(self, escolha):
        self.escolha = escolha
        self.EndModal(wx.ID_OK)

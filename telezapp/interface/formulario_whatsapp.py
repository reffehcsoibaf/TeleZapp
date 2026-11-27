# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela do formulario de uma empresa do WhatsApp (Flow, experimental).

A pagina da Meta roda no WebView2 e fala com o TeleZapp pela ponte de
nucleo.ponte_flows. Se a pagina nao fala nada em pouco tempo, a janela diz que
o formulario nao abriu e fecha a espera. O que a pessoa preenche nunca vai
para o registro: so os nomes dos eventos e o formato dos dados.
"""
import json
import logging
import os

import wx
import wx.html2 as webview

from telezapp import NOME, config
from telezapp.nucleo import ponte_flows as ponte

log = logging.getLogger("telezapp.flows")

ESPERA_DA_PAGINA_MS = 12000


def disponivel():
    """True se o Windows tem o WebView2."""
    try:
        return webview.WebView.IsBackendAvailable(webview.WebViewBackendEdge)
    except Exception:
        log.exception("não consegui consultar o WebView2")
        return False


class JanelaFormulario(wx.Frame):
    """`dados` e o `responseData` pronto (ponte_flows.dados_do_formulario);
    `ao_completar(payload)` recebe o que o formulario concluiu (o chamador o
    manda a empresa); `abrir_link(url)` abre um endereco; `falar(texto)`."""

    def __init__(self, pai, titulo, dados, ao_completar, abrir_link, falar):
        super().__init__(pai, title="%s - %s" % (titulo, NOME),
                         size=(520, 760))
        self.nome_do_formulario = titulo
        self._dados = dados
        self._ao_completar, self._abrir, self._falar = (
            ao_completar, abrir_link, falar)
        self._concluido = False
        self._pagina_falou = False
        self.ponte = ponte.Ponte(self)
        self.Bind(wx.EVT_CLOSE, self._ao_fechar)
        painel = wx.Panel(self)
        os.environ["WEBVIEW2_USER_DATA_FOLDER"] = config.pasta("webview")
        self.web = webview.WebView.New(painel,
                                       backend=webview.WebViewBackendEdge)
        self.web.AddScriptMessageHandler(ponte.NOME_DO_MANIPULADOR)
        self.web.AddUserScript(ponte.SCRIPT_DA_PONTE)
        self.web.Bind(webview.EVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED,
                      self._ao_mensagem)
        self.web.Bind(webview.EVT_WEBVIEW_NEWWINDOW, self._ao_nova_janela)
        self.web.Bind(webview.EVT_WEBVIEW_ERROR, self._ao_erro)
        fechar = wx.Button(painel, wx.ID_CLOSE, "Fechar o formulário")
        fechar.Bind(wx.EVT_BUTTON, lambda e: self.Close())
        caixa = wx.BoxSizer(wx.VERTICAL)
        caixa.Add(self.web, 1, wx.EXPAND)
        caixa.Add(fechar, 0, wx.ALL | wx.ALIGN_RIGHT, 4)
        painel.SetSizer(caixa)
        wx.CallLater(ESPERA_DA_PAGINA_MS, self._conferir_a_pagina)
        self.web.LoadURL(ponte.URL_DA_PAGINA)

    # ------------------------------------------------------ a pagina
    def _ao_mensagem(self, evento):
        mensagem = ponte.ler_mensagem(evento.GetString())
        if mensagem is None:
            return
        self._pagina_falou = True
        try:
            resposta = self.ponte.tratar(mensagem)
        except Exception:
            log.exception("formulário: erro ao tratar um pedido da página")
            resposta = None
        id_da_chamada = mensagem.get("callbackID")
        if resposta is ponte.Ponte.NADA or not id_da_chamada:
            return
        self.responder({"responseData": resposta, "callbackID": id_da_chamada})

    def responder(self, corpo):
        if not self:
            return
        try:
            # nunca RunScript (sincrono) aqui: dentro do tratador de
            # mensagens da pagina ele trava a janela
            self.web.RunScriptAsync(ponte.script_de_resposta(corpo))
        except Exception:
            log.exception("formulário: não consegui responder à página")

    def _conferir_a_pagina(self):
        if self and not self._pagina_falou and not self._concluido:
            log.warning("formulário: a página não falou com o TeleZapp em %d "
                        "s", ESPERA_DA_PAGINA_MS // 1000)
            self._falar("O formulário não abriu. Use o celular para "
                        "preenchê-lo.")

    def _ao_erro(self, evento):
        log.warning("formulário: erro de carregamento: %s",
                    evento.GetString()[:200])
        self._falar("Não consegui carregar o formulário.")

    def _ao_nova_janela(self, evento):
        evento.Veto()
        url = evento.GetURL()
        if url.startswith("https://"):
            self._abrir(url)

    # ------------------------------------------------- o que a ponte usa
    def carregada(self):
        # o WhatsApp Web manda o tema duas vezes: ao criar o quadro e de novo
        # quando a pagina diz que carregou
        for _ in range(2):
            self.responder({"eventName": "update_theme",
                            "payload": {"theme": "light"}})

    def dados(self):
        return self._dados

    def titulo(self, texto):
        if texto and self:
            self.SetTitle("%s - %s" % (texto, NOME))

    def fechar(self):
        wx.CallAfter(self.Close)

    def completar(self, payload):
        if self._concluido:
            return
        self._concluido = True
        log.info("formulário concluído: %s", json.dumps(
            ponte.formato(payload), ensure_ascii=False)[:300])
        self._ao_completar(payload)
        wx.CallAfter(self.Close)

    def abrir_url(self, url):
        if url.startswith("https://"):
            self._abrir(url)

    def _ao_fechar(self, evento):
        if not self._concluido:
            log.info("formulário fechado sem concluir")
        evento.Skip()

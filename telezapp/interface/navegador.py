# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Navegador interno simples: abre um link dentro do TeleZapp pelo WebView2
(Edge), em vez do navegador padrao do Windows. So a pagina, Voltar, Avancar,
Recarregar e Fechar - sem barra de endereco, porque a pessoa so chega aqui
por um link, nunca digita um endereco a mao.

O "import wx.html2" fica dentro das funcoes, nunca no topo do arquivo: um
wx falso (testes que poem sys.modules["wx"]) nao e um pacote de verdade e
quebraria so de importar este modulo, mesmo sem usar WebView nenhum."""
import logging
import os

import wx

from telezapp import NOME, config

log = logging.getLogger("telezapp.navegador")


def disponivel():
    """True se o Windows tem o WebView2."""
    try:
        import wx.html2 as webview
        return webview.WebView.IsBackendAvailable(webview.WebViewBackendEdge)
    except Exception:
        log.exception("não consegui consultar o WebView2")
        return False


class JanelaNavegador(wx.Frame):
    def __init__(self, pai, url):
        import wx.html2 as webview
        super().__init__(pai, title=NOME, size=(1000, 720))
        os.environ["WEBVIEW2_USER_DATA_FOLDER"] = config.pasta("webview")
        painel = wx.Panel(self)
        self.web = webview.WebView.New(painel, backend=webview.WebViewBackendEdge)
        self.web.Bind(webview.EVT_WEBVIEW_TITLE_CHANGED, self._ao_titulo)
        self.web.Bind(webview.EVT_WEBVIEW_NAVIGATED, self._ao_navegado)
        self.web.Bind(webview.EVT_WEBVIEW_NAVIGATING, self._ao_navegar)
        self.web.Bind(webview.EVT_WEBVIEW_LOADED, self._ao_carregar)
        self.web.Bind(webview.EVT_WEBVIEW_ERROR, self._ao_erro)
        self.web.Bind(webview.EVT_WEBVIEW_NEWWINDOW, self._ao_nova_janela)

        self._voltar = wx.Button(painel, label="&Voltar")
        self._avancar = wx.Button(painel, label="Ava&nçar")
        recarregar = wx.Button(painel, label="&Recarregar")
        fechar = wx.Button(painel, wx.ID_CLOSE, "&Fechar")
        self._voltar.Bind(wx.EVT_BUTTON, lambda e: self.web.GoBack())
        self._avancar.Bind(wx.EVT_BUTTON, lambda e: self.web.GoForward())
        recarregar.Bind(wx.EVT_BUTTON, lambda e: self.web.Reload())
        fechar.Bind(wx.EVT_BUTTON, lambda e: self.Close())
        linha = wx.BoxSizer(wx.HORIZONTAL)
        for b in (self._voltar, self._avancar, recarregar):
            linha.Add(b, 0, wx.ALL, 4)
        linha.AddStretchSpacer()
        linha.Add(fechar, 0, wx.ALL, 4)
        caixa = wx.BoxSizer(wx.VERTICAL)
        caixa.Add(linha, 0, wx.EXPAND)
        caixa.Add(self.web, 1, wx.EXPAND)
        painel.SetSizer(caixa)
        self._atualizar_botoes()
        self.web.LoadURL(url)
        self.Show()

    def _atualizar_botoes(self):
        self._voltar.Enable(self.web.CanGoBack())
        self._avancar.Enable(self.web.CanGoForward())

    def _ao_titulo(self, evt):
        titulo = evt.GetString()
        self.SetTitle("%s - %s" % (titulo, NOME) if titulo else NOME)

    def _ao_navegado(self, evt):
        self._atualizar_botoes()

    def _ao_navegar(self, evt):
        """Link do WhatsApp ou do Telegram (wa.me, tg:, whatsapp:...): usa a
        mesma abertura por dentro do TeleZapp, em vez de carregar a pagina."""
        from telezapp.nucleo import links_externos as links
        url = evt.GetURL()
        esquema = url.lower().split(":", 1)[0]
        if esquema in ("tg", "whatsapp") or links.interpretar(url):
            evt.Veto()
            from telezapp.interface import dialogos
            dialogos.abrir_link(url)

    def _ao_carregar(self, evt):
        self._atualizar_botoes()
        self.web.SetFocus()

    def _ao_erro(self, evt):
        log.warning("navegador interno: erro ao carregar (%s)",
                   evt.GetString())

    def _ao_nova_janela(self, evt):
        # link que abriria aba/janela nova: continua na mesma janela
        self.web.LoadURL(evt.GetURL())

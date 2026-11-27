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

MANIPULADOR = "telezappNavegador"
# O foco fica dentro da pagina, que e um controle do Edge: as teclas nem
# chegam ao wx (por isso o menu e o Esc da janela nao respondiam, e o Alt
# ficava com o Edge, que fazia o NVDA demorar). O script pega as duas na
# pagina e avisa o TeleZapp: Esc fecha e Alt, sozinho, abre o menu.
SCRIPT_DAS_TECLAS = """
(function () {
  var so_alt = false;
  window.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !e.altKey && !e.ctrlKey && !e.shiftKey) {
      e.preventDefault();
      window.%(m)s.postMessage('fechar');
    } else if (e.key === 'Alt') {
      so_alt = true;
      e.preventDefault();
    } else {
      so_alt = false;
    }
  }, true);
  window.addEventListener('keyup', function (e) {
    if (e.key === 'Alt') {
      e.preventDefault();
      if (so_alt) { window.%(m)s.postMessage('menu'); }
      so_alt = false;
    }
  }, true);
})();
""" % {"m": MANIPULADOR}


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
        self._url = url
        os.environ["WEBVIEW2_USER_DATA_FOLDER"] = config.pasta("webview")
        painel = wx.Panel(self)
        self.web = webview.WebView.New(painel, backend=webview.WebViewBackendEdge)
        self.web.AddScriptMessageHandler(MANIPULADOR)
        self.web.AddUserScript(SCRIPT_DAS_TECLAS)
        self.web.Bind(webview.EVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED,
                      self._ao_mensagem_da_pagina)
        self.web.Bind(webview.EVT_WEBVIEW_TITLE_CHANGED, self._ao_titulo)
        self.web.Bind(webview.EVT_WEBVIEW_NAVIGATED, self._ao_navegado)
        self.web.Bind(webview.EVT_WEBVIEW_NAVIGATING, self._ao_navegar)
        self.web.Bind(webview.EVT_WEBVIEW_LOADED, self._ao_carregar)
        self.web.Bind(webview.EVT_WEBVIEW_ERROR, self._ao_erro)
        self.web.Bind(webview.EVT_WEBVIEW_NEWWINDOW, self._ao_nova_janela)

        # Os comandos ficam no menu que o Alt abre (botoes na tela atrasavam
        # o NVDA). Dois menus iguais: o da barra (foco na janela) e o que o
        # Alt, dentro da pagina, abre solto; um mesmo menu nao serve aos dois.
        menu, self._voltar, self._avancar = self._montar_menu()
        barra = wx.MenuBar()
        barra.Append(menu, "&Navegador")
        self.SetMenuBar(barra)
        # o foco fica dentro da pagina (um controle do Edge): o Esc tambem
        # e tratado aqui, antes de chegar a ela
        self.Bind(wx.EVT_CHAR_HOOK, self._ao_tecla)
        caixa = wx.BoxSizer(wx.VERTICAL)
        caixa.Add(self.web, 1, wx.EXPAND)
        painel.SetSizer(caixa)
        self._atualizar_botoes()
        self.web.LoadURL(url)
        self.Show()

    def _montar_menu(self):
        menu = wx.Menu()
        voltar = menu.Append(wx.ID_ANY, "&Voltar	Alt+Left")
        avancar = menu.Append(wx.ID_ANY, "Ava&nçar	Alt+Right")
        recarregar = menu.Append(wx.ID_ANY, "&Recarregar	F5")
        externo = menu.Append(wx.ID_ANY, "Abrir no &navegador externo")
        menu.AppendSeparator()
        fechar = menu.Append(wx.ID_ANY, "&Fechar	Esc")
        voltar.Enable(self.web.CanGoBack())
        avancar.Enable(self.web.CanGoForward())
        self.Bind(wx.EVT_MENU, lambda e: self.web.GoBack(), voltar)
        self.Bind(wx.EVT_MENU, lambda e: self.web.GoForward(), avancar)
        self.Bind(wx.EVT_MENU, lambda e: self.web.Reload(), recarregar)
        self.Bind(wx.EVT_MENU, self._abrir_externo, externo)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), fechar)
        return menu, voltar, avancar

    def _atualizar_botoes(self):
        self._voltar.Enable(self.web.CanGoBack())
        self._avancar.Enable(self.web.CanGoForward())

    def _ao_mensagem_da_pagina(self, evt):
        acao = evt.GetString()
        if acao == "fechar":
            wx.CallAfter(self.Close)
        elif acao == "menu":
            wx.CallAfter(self._abrir_menu)

    def _abrir_menu(self):
        """O Alt dentro da pagina: o menu abre no canto da janela, no lugar
        em que o Alt o abriria."""
        menu, _, _ = self._montar_menu()
        self.PopupMenu(menu, (0, 0))
        menu.Destroy()

    def _ao_tecla(self, evt):
        if evt.GetKeyCode() == wx.WXK_ESCAPE and not evt.HasModifiers():
            self.Close()
            return
        evt.Skip()

    def _abrir_externo(self, evt):
        """A pagina que esta na tela, no navegador padrao do Windows."""
        url = self.web.GetCurrentURL() or self._url
        if url.lower().startswith(("http://", "https://")):
            wx.LaunchDefaultBrowser(url)

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

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Navegador interno simples: abre um link dentro do TeleZapp pelo WebView2
(Edge), em vez do navegador padrao do Windows. So a pagina, Voltar, Avancar,
Recarregar e Fechar - sem barra de endereco, porque a pessoa so chega aqui
por um link, nunca digita um endereco a mao.

O "import wx.html2" fica dentro das funcoes, nunca no topo do arquivo: um
wx falso (testes que poem sys.modules["wx"]) nao e um pacote de verdade e
quebraria so de importar este modulo, mesmo sem usar WebView nenhum."""
import json
import logging
import os
import re

import wx

from telezapp import NOME, config
from telezapp.nucleo import sites_navegador as sites

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

# Lembrar o que a pessoa marca e preenche, e a senha. So a pagina de cima
# (nao os quadros dentro dela). Manda ao TeleZapp so o que a PESSOA mexeu
# (evento confiavel); o que o proprio script devolve a pagina nao conta.
# O TeleZapp devolve tudo pelas duas funcoes do fim (__tzRestaurar e
# __tzPreencherSenha), depois que a pagina carrega, e elas ficam atentas
# ate 15 s a campos que a pagina monte depois.
SCRIPT_DOS_SITES = r"""
(function () {
  if (window.top !== window) { return; }
  var M = window.%(m)s;
  // so eventos da pessoa (o flag e dos testes automaticos)
  function confiavel(e) { return e.isTrusted || window.__tzTeste === true; }
  var IGNORAR = /^(password|hidden|file|submit|button|image|reset)$/i;
  var SENSIVEL = /(card|cartao|cart[aã]o|cvv|cvc|otp|token|pass|senha|cpf|iban)/i;
  function campos() {
    return Array.prototype.slice.call(
      document.querySelectorAll('input,select,textarea'));
  }
  function visivel(el) {
    return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  }
  function chave(el) {
    var t = (el.type || el.tagName || '').toLowerCase();
    var id = el.name || el.id;
    if (!id) { id = '#' + campos().indexOf(el); }
    if (t === 'radio') { return 'r:' + id; }
    if (t === 'checkbox') { return 'c:' + id + ':' + (el.value || ''); }
    return 't:' + id;
  }
  function guardavel(el) {
    var t = (el.type || '').toLowerCase();
    if (IGNORAR.test(t)) { return false; }
    var ac = (el.getAttribute('autocomplete') || '').toLowerCase();
    if (ac.indexOf('cc-') === 0 || ac === 'one-time-code') { return false; }
    return !SENSIVEL.test((el.name || '') + ' ' + (el.id || '') + ' ' + ac);
  }
  function valorDe(el) {
    var t = (el.type || '').toLowerCase();
    if (t === 'checkbox') { return el.checked ? '1' : '0'; }
    if (t === 'radio') { return el.checked ? (el.value || '') : null; }
    return el.value;
  }
  var fila = {}, relogio = null;
  function enviarCampos() {
    relogio = null;
    var f = fila; fila = {};
    M.postMessage(JSON.stringify({t: 'campos', c: f}));
  }
  function mexeu(e) {
    if (!confiavel(e)) { return; }
    var el = e.target;
    if (!el || !el.tagName || !/^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName)) { return; }
    if (!guardavel(el)) { return; }
    var v = valorDe(el);
    if (v === null) { return; }
    fila[chave(el)] = v;
    if (relogio) { clearTimeout(relogio); }
    relogio = setTimeout(enviarCampos, 800);
  }
  document.addEventListener('change', mexeu, true);
  document.addEventListener('input', mexeu, true);

  function definir(el, valor) {
    var proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype :
      el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype :
      HTMLInputElement.prototype;
    var d = Object.getOwnPropertyDescriptor(proto, 'value');
    if (d && d.set) { d.set.call(el, valor); } else { el.value = valor; }
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
  }
  function restaurar(dados) {
    campos().forEach(function (el) {
      if (el.__tzFeito || !guardavel(el)) { return; }
      var k = chave(el);
      var t = (el.type || '').toLowerCase();
      var alvo = dados[k];
      if (t === 'radio') {
        // um radio por valor: a chave e do grupo, o valor e o escolhido
        if (alvo === undefined) { return; }
        el.__tzFeito = true;
        if ((el.value || '') === alvo && !el.checked) { el.click(); }
        return;
      }
      if (alvo === undefined) { return; }
      el.__tzFeito = true;
      if (t === 'checkbox') {
        if (el.checked !== (alvo === '1')) { el.click(); }
      } else if (!el.value && alvo) {
        definir(el, alvo);
      }
    });
  }
  function atento(fazer) {
    fazer();
    var fim = Date.now() + 15000;
    var obs = new MutationObserver(function () {
      if (Date.now() > fim) { obs.disconnect(); return; }
      fazer();
    });
    obs.observe(document.documentElement, {childList: true, subtree: true});
    setTimeout(function () { obs.disconnect(); }, 15000);
  }
  window.__tzRestaurar = function (dados) { atento(function () { restaurar(dados); }); };

  // senha: depois de enviar o formulario (submit, clique em botao ou Enter)
  function campoDeSenha() {
    var s = campos().filter(function (el) {
      return (el.type || '').toLowerCase() === 'password' && visivel(el);
    });
    return s;
  }
  function campoDeUsuario(senha) {
    var todos = campos(), i = todos.indexOf(senha), achado = null;
    for (var j = 0; j < i; j++) {
      var t = (todos[j].type || 'text').toLowerCase();
      if (/^(text|email|tel|search|url)$/.test(t) && todos[j].value && visivel(todos[j])) {
        achado = todos[j];
      }
    }
    return achado;
  }
  var ultimo = '';
  function tentarSenha() {
    var s = campoDeSenha().filter(function (el) { return el.value; });
    if (s.length !== 1) { return; }   // 0: nada a guardar; 2+: troca/cadastro
    var u = campoDeUsuario(s[0]);
    var par = (u ? u.value : '') + '\u0000' + s[0].value;
    if (par === ultimo) { return; }
    ultimo = par;
    M.postMessage(JSON.stringify({t: 'senha', u: u ? u.value : '', s: s[0].value}));
  }
  document.addEventListener('submit', function (e) { if (confiavel(e)) { tentarSenha(); } }, true);
  document.addEventListener('click', function (e) {
    if (!confiavel(e)) { return; }
    var b = e.target && e.target.closest ?
      e.target.closest('button,input[type=submit],[role=button],a') : null;
    if (b) { tentarSenha(); }
  }, true);
  document.addEventListener('keydown', function (e) {
    if (confiavel(e) && e.key === 'Enter' && e.target && (e.target.type || '') === 'password') {
      tentarSenha();
    }
  }, true);

  window.__tzPreencherSenha = function (usuario, senha) {
    atento(function () {
      var s = campoDeSenha().filter(function (el) { return !el.value && !el.__tzFeito; });
      s.forEach(function (campo) {
        campo.__tzFeito = true;
        var u = null, todos = campos(), i = todos.indexOf(campo);
        for (var j = i - 1; j >= 0; j--) {
          var t = (todos[j].type || 'text').toLowerCase();
          if (/^(text|email|tel)$/.test(t) && visivel(todos[j])) { u = todos[j]; break; }
        }
        if (u && !u.value && usuario) { definir(u, usuario); }
        definir(campo, senha);
      });
    });
  };
})();
""" % {"m": MANIPULADOR}

LARGURA_CELULAR = 430
ALTURA_CELULAR = 880


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
        self._sites = sites.SitesDoNavegador(
            os.path.join(config.pasta_dados(), "navegador_sites.json"))
        self._modo = sites.COMPUTADOR
        self._tamanho_antes = None
        self._perguntando = False
        os.environ["WEBVIEW2_USER_DATA_FOLDER"] = config.pasta("webview")
        painel = wx.Panel(self)
        self.web = webview.WebView.New(painel, backend=webview.WebViewBackendEdge)
        self.web.AddScriptMessageHandler(MANIPULADOR)
        self.web.AddUserScript(SCRIPT_DAS_TECLAS)
        self.web.AddUserScript(SCRIPT_DOS_SITES)
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
        # o site ja tem uma exibicao escolhida antes: vale desde o inicio
        if self._lembra() and self._sites.exibicao(url) == sites.CELULAR:
            self._aplicar_modo(sites.CELULAR)
        self.web.LoadURL(url)
        self.Show()

    def _montar_menu(self):
        menu = wx.Menu()
        voltar = menu.Append(wx.ID_ANY, "&Voltar	Alt+Left")
        avancar = menu.Append(wx.ID_ANY, "Ava&nçar	Alt+Right")
        recarregar = menu.Append(wx.ID_ANY, "&Recarregar	F5")
        externo = menu.Append(wx.ID_ANY, "Abrir no &navegador externo")
        celular = menu.AppendCheckItem(wx.ID_ANY, "&Exibição de celular")
        celular.Check(self._modo == sites.CELULAR)
        esquecer = menu.Append(wx.ID_ANY,
                               "Esquecer os dados salvos &deste site")
        menu.AppendSeparator()
        fechar = menu.Append(wx.ID_ANY, "&Fechar	Esc")
        voltar.Enable(self.web.CanGoBack())
        avancar.Enable(self.web.CanGoForward())
        self.Bind(wx.EVT_MENU, lambda e: self.web.GoBack(), voltar)
        self.Bind(wx.EVT_MENU, lambda e: self.web.GoForward(), avancar)
        self.Bind(wx.EVT_MENU, lambda e: self.web.Reload(), recarregar)
        self.Bind(wx.EVT_MENU, self._abrir_externo, externo)
        self.Bind(wx.EVT_MENU, self._mudar_exibicao, celular)
        self.Bind(wx.EVT_MENU, self._esquecer_site, esquecer)
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
        elif acao.startswith("{"):
            try:
                dado = json.loads(acao)
            except ValueError:
                return
            if isinstance(dado, dict):
                wx.CallAfter(self._ao_dado_do_site, dado)

    # -- exibicao de celular ou de computador, lembrada por site
    def _versao_do_chrome(self):
        try:
            achou = re.search(r"Chrome/(\d+)", self.web.GetUserAgent() or "")
        except Exception:
            achou = None
        return achou.group(1) if achou else "131"

    def _aplicar_modo(self, modo):
        """Troca o agente de usuario e o tamanho da janela (a pagina olha os
        dois para decidir se e celular). Nao recarrega."""
        v = self._versao_do_chrome()
        if modo == sites.CELULAR:
            self.web.SetUserAgent(
                "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/%s.0.0.0 Mobile Safari/537.36" % v)
            if self._tamanho_antes is None:
                if self.IsMaximized():
                    self.Maximize(False)
                self._tamanho_antes = self.GetSize()
            self.SetSize((LARGURA_CELULAR, ALTURA_CELULAR))
        else:
            self.web.SetUserAgent(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/%s.0.0.0 Safari/537.36 Edg/%s.0.0.0"
                % (v, v))
            if self._tamanho_antes is not None:
                self.SetSize(self._tamanho_antes)
                self._tamanho_antes = None
        self._modo = modo

    def _mudar_exibicao(self, evt):
        novo = sites.COMPUTADOR if self._modo == sites.CELULAR \
            else sites.CELULAR
        self._aplicar_modo(novo)
        if self._lembra():
            self._sites.definir_exibicao(
                self.web.GetCurrentURL() or self._url, novo)
        self.web.Reload()

    def _lembra(self):
        """A caixa "lembrar o que foi feito em cada site" das configuracoes."""
        try:
            return bool(config.Config().get("navegador_lembrar_sites"))
        except Exception:
            return True

    # -- o que a pagina manda guardar (campos marcados e senha)
    def _ao_dado_do_site(self, dado):
        if not self._lembra():
            return
        url = self.web.GetCurrentURL() or self._url
        if dado.get("t") == "campos" and isinstance(dado.get("c"), dict):
            self._sites.guardar_campos(url, dado["c"])
        elif dado.get("t") == "senha":
            self._perguntar_senha(url, str(dado.get("u") or ""),
                                  str(dado.get("s") or ""))

    def _perguntar_senha(self, url, usuario, senha):
        if not senha or self._perguntando or self._sites.nunca_guarda(url) \
                or self._sites.mesma_senha(url, usuario, senha):
            return
        self._perguntando = True
        try:
            host = sites.host_do_site(url)
            quem = " de %s" % usuario if usuario else ""
            dlg = wx.MessageDialog(
                self, "Guardar a senha%s para %s? Ela fica cifrada neste "
                "computador e é preenchida na próxima vez." % (quem, host),
                NOME, wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION)
            dlg.SetYesNoCancelLabels("&Guardar", "&Agora não",
                                     "&Nunca neste site")
            r = dlg.ShowModal()
            dlg.Destroy()
        finally:
            self._perguntando = False
        if r == wx.ID_YES:
            self._sites.guardar_senha(url, usuario, senha)
        elif r == wx.ID_CANCEL:
            self._sites.nunca_guardar(url)

    def _devolver_dados_salvos(self):
        """Depois que a pagina carrega: o que a pessoa marcou e a senha."""
        if not self._lembra():
            return
        url = self.web.GetCurrentURL() or self._url
        try:
            campos = self._sites.campos(url)
            if campos:
                self.web.RunScriptAsync("window.__tzRestaurar && "
                                   "window.__tzRestaurar(%s);"
                                   % json.dumps(campos))
            conta = self._sites.senha_guardada(url)
            if conta:
                self.web.RunScriptAsync(
                    "window.__tzPreencherSenha && "
                    "window.__tzPreencherSenha(%s, %s);"
                    % (json.dumps(conta[0]), json.dumps(conta[1])))
        except Exception:
            log.exception("não consegui devolver os dados salvos do site")

    def _esquecer_site(self, evt):
        url = self.web.GetCurrentURL() or self._url
        if wx.MessageBox(
                "Esquecer o que foi guardado de %s (campos, senha e exibição)?"
                % sites.host_do_site(url), NOME,
                wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
            return
        self._sites.esquecer_site(url)
        if self._modo == sites.CELULAR:
            self._aplicar_modo(sites.COMPUTADOR)
            self.web.Reload()

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
        self._devolver_dados_salvos()
        self.web.SetFocus()

    def _ao_erro(self, evt):
        log.warning("navegador interno: erro ao carregar (%s)",
                   evt.GetString())

    def _ao_nova_janela(self, evt):
        # link que abriria aba/janela nova: continua na mesma janela
        self.web.LoadURL(evt.GetURL())

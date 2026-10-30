# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela que abre o aplicativo de um robo do Telegram dentro do TeleZapp.

A pagina roda no WebView2 (Edge) e fala com o Telegram pela ponte de
nucleo.ponte_web_app. Os botoes que o Telegram desenha fora da pagina (principal,
voltar...) sao botoes de verdade da janela, alcancaveis com Tab.
"""
import json
import logging
import os
import threading

import wx
import wx.html2 as webview

from telezapp import NOME, config
from telezapp.nucleo import links_externos as links
from telezapp.nucleo import ponte_web_app as ponte
from telezapp.nucleo import recursos_windows as recursos

log = logging.getLogger("telezapp.app_do_robo")


def disponivel():
    """True se o Windows tem o WebView2."""
    try:
        return webview.WebView.IsBackendAvailable(webview.WebViewBackendEdge)
    except Exception:
        log.exception("não consegui consultar o WebView2")
        return False


class JanelaAppDoRobo(wx.Frame):
    """`servico` faz o que depende do Telegram: enviar_dados(texto, dados),
    metodo(nome, params) -> texto JSON, pedir_escrita() -> bool,
    compartilhar_telefone() -> bool, pagar(slug, fim), buscar_inline(consulta).
    `ao_pagamento(credenciais)`: so na janela do formulario. `abrir_link`
    abre um endereco pelo TeleZapp; `falar` diz um texto a pessoa."""

    ROTULOS = {"voltar": "Voltar", "principal": "Botão principal",
               "secundario": "Botão secundário",
               "configuracoes": "Configurações do aplicativo"}

    def __init__(self, pai, titulo, url, servico, abrir_link, falar,
                 ao_pagamento=None):
        super().__init__(pai, title="%s - %s" % (titulo, NOME),
                         size=(900, 700))
        self.servico, self._abrir, self._falar = servico, abrir_link, falar
        self.titulo = titulo
        self.ao_pagamento = ao_pagamento   # so no formulario de pagamento
        self._confirmar_ao_fechar = False
        self._parar_qr = threading.Event()
        self._biometria_liberada = False
        # o segredo e de cada robo: nunca pelo titulo, que dois podem repetir
        self._robo = getattr(servico, "conversa_id", "") or url
        self._local_liberado = False
        self._segredos = recursos.Segredos(os.path.join(
            config.pasta("webview"), "segredos-dos-robos.json"))
        self.Bind(wx.EVT_CLOSE, self._ao_fechar)
        painel = wx.Panel(self)
        self.web = self._criar_web(painel)
        self.web.AddScriptMessageHandler(ponte.NOME_DO_MANIPULADOR)
        self.web.AddUserScript(ponte.SCRIPT_DA_PONTE)
        self.web.Bind(webview.EVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED,
                      self._ao_mensagem)
        self.web.Bind(webview.EVT_WEBVIEW_NEWWINDOW, self._ao_nova_janela)
        self.web.Bind(webview.EVT_WEBVIEW_NAVIGATING, self._ao_navegar)
        self.web.Bind(webview.EVT_WEBVIEW_LOADED, self._ao_carregar)
        self.web.Bind(webview.EVT_WEBVIEW_ERROR, self._ao_erro)
        self.botoes = {}
        linha = wx.BoxSizer(wx.HORIZONTAL)
        for chave in ("voltar", "principal", "secundario", "configuracoes"):
            b = wx.Button(painel, label=self.ROTULOS[chave])
            b.Bind(wx.EVT_BUTTON, lambda e, c=chave: self._tocar(c))
            b.Show(False)
            self.botoes[chave] = b
            linha.Add(b, 0, wx.ALL, 4)
        fechar = wx.Button(painel, wx.ID_CLOSE, "Fechar o aplicativo")
        fechar.Bind(wx.EVT_BUTTON, lambda e: self.Close())
        linha.AddStretchSpacer()
        linha.Add(fechar, 0, wx.ALL, 4)
        self._linha = linha
        caixa = wx.BoxSizer(wx.VERTICAL)
        caixa.Add(self.web, 1, wx.EXPAND)
        caixa.Add(linha, 0, wx.EXPAND)
        painel.SetSizer(caixa)
        self._painel = painel
        self.web.LoadURL(url)

    @staticmethod
    def _criar_web(pai):
        """O WebView com os dados (login dos aplicativos) na pasta do TeleZapp,
        nao ao lado do programa: a variavel e a do proprio WebView2."""
        os.environ["WEBVIEW2_USER_DATA_FOLDER"] = config.pasta("webview")
        return webview.WebView.New(pai, backend=webview.WebViewBackendEdge)

    # ------------------------------------------------------ ui da ponte
    def botao(self, chave, visivel, texto="", ativo=True):
        b = self.botoes[chave]
        rotulo = (texto or self.ROTULOS[chave]).replace("&", "&&")
        mudou = visivel and (not b.IsShown() or b.GetLabel() != rotulo)
        b.SetLabel(rotulo)
        b.Enable(bool(ativo))
        b.Show(visivel)
        self._painel.Layout()
        if mudou and chave in ("principal", "secundario"):
            self._falar("Botão disponível: %s." % (texto or self.ROTULOS[chave]))

    def fechar(self):
        self.Close()

    def tamanho(self):
        return tuple(self.web.GetClientSize())

    def abrir_link(self, url):
        self._abrir(url)

    def janelinha(self, titulo, mensagem, botoes):
        """A janela de aviso do aplicativo: devolve o id do botao escolhido."""
        escolhas = [(b.get("id", ""), b.get("text") or {
            "ok": "OK", "close": "Fechar", "cancel": "Cancelar"}.get(
                b.get("type"), "Botão")) for b in botoes] or [("", "OK")]
        dlg = wx.SingleChoiceDialog(self, mensagem, titulo or self.titulo,
                                    [r for _, r in escolhas])
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return ""
            return escolhas[dlg.GetSelection()][0]
        finally:
            dlg.Destroy()

    def enviar_dados(self, dados):
        self._em_segundo_plano(lambda: self.servico.enviar_dados(
            self.titulo, dados))
        self.Close()

    def metodo(self, req_id, nome, params):
        def trabalho():
            try:
                resposta = {"req_id": req_id, "result": json.loads(
                    self.servico.metodo(nome, params))}
            except Exception as e:
                log.info("método %s do aplicativo: %s", nome, type(e).__name__)
                resposta = {"req_id": req_id, "error": type(e).__name__}
            wx.CallAfter(self.responder, "custom_method_invoked", resposta)
        self._em_segundo_plano(trabalho)

    def pedir_escrita(self):
        r = wx.MessageBox("%s quer poder enviar mensagens para você. Permitir?"
                          % self.titulo, NOME, wx.YES_NO | wx.ICON_QUESTION,
                          self)
        if r != wx.YES:
            self.responder("write_access_requested", {"status": "cancelled"})
            return

        def trabalho():
            try:
                ok = self.servico.pedir_escrita()
            except Exception as e:
                log.info("permissão de escrita: %s", type(e).__name__)
                ok = False
            wx.CallAfter(self.responder, "write_access_requested",
                         {"status": "allowed" if ok else "cancelled"})
        self._em_segundo_plano(trabalho)

    def avisar(self, texto):
        self._falar(texto)

    def pedir_telefone(self):
        r = wx.MessageBox("%s quer o seu número de telefone. Enviar?"
                          % self.titulo, NOME,
                          wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
        if r != wx.YES:
            self.responder("phone_requested", {"status": "cancelled"})
            return

        def trabalho():
            try:
                ok = self.servico.compartilhar_telefone()
            except Exception as e:
                log.info("telefone ao aplicativo: %s", type(e).__name__)
                ok = False
            wx.CallAfter(self.responder, "phone_requested",
                         {"status": "sent" if ok else "cancelled"})
        self._em_segundo_plano(trabalho)

    def ler_area(self):
        """O texto copiado, se a pessoa deixar; sem `data`, o aplicativo sabe
        que nao veio nada."""
        r = wx.MessageBox("%s quer ler o que você copiou. Deixar?"
                          % self.titulo, NOME,
                          wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
        if r != wx.YES or not wx.TheClipboard.Open():
            return {}
        try:
            dado = wx.TextDataObject()
            return {"data": dado.GetText()} if wx.TheClipboard.GetData(dado) \
                else {}
        finally:
            wx.TheClipboard.Close()

    def ler_qr(self, texto):
        escolhas = ["De um arquivo de imagem", "Da câmera"]
        dlg = wx.SingleChoiceDialog(
            self, texto or "De onde ler o código QR?", self.titulo, escolhas)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                self.responder("scan_qr_popup_closed")
                return
            camera = dlg.GetSelection() == 1
        finally:
            dlg.Destroy()
        caminho = ""
        if not camera:
            with wx.FileDialog(self, "Imagem com o código QR", wildcard=(
                    "Imagens|*.png;*.jpg;*.jpeg;*.bmp;*.webp|Todos|*.*"),
                    style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as abrir:
                if abrir.ShowModal() != wx.ID_OK:
                    self.responder("scan_qr_popup_closed")
                    return
                caminho = abrir.GetPath()
        else:
            self._falar("Aponte a câmera para o código.")

        def trabalho():
            from telezapp.midia import qr
            try:
                lido = qr.ler_camera(parar=self._parar_qr) if camera \
                    else qr.ler_arquivo(caminho)
            except Exception as e:
                log.info("código QR: %s", type(e).__name__)
                lido = ""
            wx.CallAfter(self._qr_lido, lido)
        self._em_segundo_plano(trabalho)

    def _qr_lido(self, lido):
        if not self:
            return
        if lido:
            self.responder("qr_text_received", {"data": lido})
        else:
            self._falar("Não encontrei um código QR.")
        self.responder("scan_qr_popup_closed")

    def pagar(self, slug):
        def fim(situacao):
            self.responder("invoice_closed", {"slug": slug, "status": situacao})
        self.servico.pagar(slug, fim)

    def pagamento(self, credenciais):
        if self.ao_pagamento is not None:
            self.ao_pagamento(credenciais)
            self.Close()

    def buscar_inline(self, consulta):
        self.servico.buscar_inline(consulta)

    # ------------------------------------------------------ biometria
    def _info_biometria(self, disponivel):
        return {"available": disponivel, "type": "unknown" if disponivel else "",
                "access_requested": self._biometria_liberada,
                "access_granted": self._biometria_liberada,
                "device_id": "telezapp" if disponivel else "",
                "token_saved": self._segredos.tem(self._robo)}

    def _no_fundo(self, consultar, entregar):
        """consultar() fora da janela (chama o Windows); entregar(r) nela."""
        def trabalho():
            try:
                r = consultar()
            except Exception as e:
                log.info("recurso do aplicativo: %s", type(e).__name__)
                r = None
            wx.CallAfter(lambda: self and entregar(r))
        self._em_segundo_plano(trabalho)

    def info_da_biometria(self):
        self._no_fundo(recursos.biometria_disponivel, lambda ok: self.responder(
            "biometry_info_received", self._info_biometria(bool(ok))))

    def acesso_a_biometria(self, motivo):
        def pronto(ok):
            if not ok:
                self._falar(recursos.BIOMETRIA_AUSENTE)
            elif wx.MessageBox(
                    "%s quer usar a biometria do Windows. %s\nPermitir?" % (
                        self.titulo, motivo), NOME,
                    wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
                    self) == wx.YES:
                self._biometria_liberada = True
            self.responder("biometry_info_received",
                           self._info_biometria(bool(ok)))
        self._no_fundo(recursos.biometria_disponivel, pronto)

    def autenticar_biometria(self, motivo):
        if not self._biometria_liberada:
            self.responder("biometry_auth_requested", {"status": "failed"})
            return
        self._falar("Confirme com a biometria na janela do Windows.")

        def pronto(r):
            if r == "ausente":
                self._falar(recursos.BIOMETRIA_AUSENTE)
            if r == "ok":
                self.responder("biometry_auth_requested", {
                    "status": "authorized",
                    "token": self._segredos.ler(self._robo)})
            else:
                self.responder("biometry_auth_requested", {"status": "failed"})
        self._no_fundo(lambda: recursos.verificar_biometria(
            motivo or self.titulo), pronto)

    def guardar_segredo(self, segredo):
        """O robo so guarda ou troca o segredo depois de a pessoa liberar."""
        if not self._biometria_liberada:
            self.responder("biometry_token_updated", {"status": "failed"})
            return
        try:
            self._segredos.guardar(self._robo, segredo)
        except OSError:
            log.info("não consegui guardar o segredo do robô")
            self.responder("biometry_token_updated", {"status": "failed"})
            return
        self.responder("biometry_token_updated", {
            "status": "updated" if segredo else "removed"})

    def abrir_ajustes_da_biometria(self):
        recursos.abrir_ajustes(recursos.AJUSTES_BIOMETRIA)

    # ----------------------------------------------------- localizacao
    def _info_local(self, situacao):
        return {"available": situacao != "ausente",
                "access_requested": self._local_liberado,
                "access_granted": self._local_liberado}

    def conferir_localizacao(self):
        self._no_fundo(recursos.acesso_a_localizacao,
                       lambda s: self.responder("location_checked",
                                                self._info_local(s or "ausente")))

    def pedir_localizacao(self):
        if not self._local_liberado:
            if wx.MessageBox("%s quer saber onde você está. Permitir nesta "
                             "janela?" % self.titulo, NOME,
                             wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
                             self) != wx.YES:
                self.responder("location_requested", {"available": False})
                return
            self._local_liberado = True

        def pronto(r):
            r = r or {"situacao": "ausente"}
            if r["situacao"] != "ok":
                self._falar(recursos.LOCAL_BLOQUEADO
                            if r["situacao"] == "negado"
                            else recursos.LOCAL_AUSENTE)
                self.responder("location_requested", {"available": False})
                return
            self.responder("location_requested", {
                "available": True, "latitude": r["latitude"],
                "longitude": r["longitude"], "altitude": r["altitude"],
                "course": r["direcao"], "speed": r["velocidade"],
                "horizontal_accuracy": r["precisao"],
                "vertical_accuracy": None, "course_accuracy": None,
                "speed_accuracy": None})
        self._no_fundo(recursos.localizacao, pronto)

    def abrir_ajustes_da_localizacao(self):
        recursos.abrir_ajustes(recursos.AJUSTES_LOCAL)

    def confirmar_ao_fechar(self, ligado):
        self._confirmar_ao_fechar = ligado

    def _ao_fechar(self, evt):
        if self._confirmar_ao_fechar and evt.CanVeto() and wx.MessageBox(
                "Fechar %s? O que não foi salvo pode se perder." % self.titulo,
                NOME, wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
            evt.Veto()
            return
        self._parar_qr.set()
        evt.Skip()

    # -------------------------------------------------------- eventos
    @staticmethod
    def _em_segundo_plano(trabalho):
        threading.Thread(target=trabalho, daemon=True,
                         name="app-do-robo").start()

    def responder(self, tipo, dados=None):
        if self:
            self.web.RunScriptAsync(ponte.script_de_resposta(tipo, dados))

    def _tocar(self, chave):
        self.responder(ponte.EVENTO_DO_BOTAO[chave])

    def _ao_mensagem(self, evt):
        tipo, dados = ponte.ler_mensagem(evt.GetString())
        if tipo is None:
            return
        for resposta, conteudo in ponte.tratar(tipo, dados, self):
            self.responder(resposta, conteudo)

    def _ao_nova_janela(self, evt):
        self._abrir(evt.GetURL())

    def _ao_navegar(self, evt):
        url = evt.GetURL()
        if url.lower().startswith("tg:") or links.interpretar(url):
            evt.Veto()
            self._abrir(url)

    def _ao_carregar(self, evt):
        self._falar("Aplicativo carregado: %s." % self.titulo)
        self.web.SetFocus()

    def _ao_erro(self, evt):
        log.warning("o aplicativo não carregou: %s", evt.GetString())
        self._falar("O aplicativo não carregou.")

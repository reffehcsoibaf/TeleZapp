# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela de busca de canais do WhatsApp: procura no diretório do WhatsApp
canais que a conta ainda não segue (e mostra os que ela já segue), por texto
ou pelas listas do diretório (recomendados, em alta, populares, novos), com
filtro de categoria. Seguir pede confirmação.

A busca fala com o WhatsApp e pode demorar, por isso roda fora da janela e
avisa quando começa e quando termina. A lógica está em `nucleo.canais_whatsapp`
e no provedor; aqui só o desenho.
"""
import threading

import wx

from telezapp.interface import dialogos
from telezapp.nucleo import canais_whatsapp as cw


# quantas paginas sem canal novo seguidas a janela atravessa sozinha
PAGINAS_VAZIAS_SEGUIDAS = 8


class DialogoBuscaDeCanais(wx.Dialog):
    def __init__(self, pai, contas, buscar, seguir, falar=None, cfg=None,
                 ver=None):
        """contas: [(id, nome)] das contas do WhatsApp; buscar(conta_id,
        texto, categoria, visao, cursor="") -> Pagina (bloqueia; levanta
        RuntimeError com o motivo); seguir(conta_id, canal) -> (ok, texto)
        (bloqueia); falar(texto) fala sem esperar; ver(conta_id, canal) ->
        texto das ultimas publicacoes (bloqueia; levanta RuntimeError)."""
        super().__init__(pai, title="Buscar canais do WhatsApp",
                         size=(760, 600),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.contas = list(contas)
        self.buscar_fn, self.seguir_fn = buscar, seguir
        self.falar = falar or (lambda texto: None)
        self.cfg = cfg
        self.ver_fn = ver
        self.canais = []
        self.proximo = ""             # cursor da pagina seguinte, se houver
        self.fim = False              # o WhatsApp disse que nao tem mais
        self._pedido = None           # (conta, texto, categoria, visao)
        self.ocupada = False

        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(self, label=(
            "Procura canais no diretório do WhatsApp, inclusive os que você "
            "ainda não segue. Digite e use Enter. Sem texto, mostra a lista "
            "escolhida abaixo.")), 0, wx.ALL, 8)
        self.caixa_conta = None
        if len(self.contas) > 1:
            lay.Add(wx.StaticText(self, label="&Conta:"), 0,
                    wx.LEFT | wx.RIGHT, 8)
            self.caixa_conta = wx.Choice(
                self, choices=[nome for _, nome in self.contas],
                name="Conta")
            self.caixa_conta.SetSelection(0)
            lay.Add(self.caixa_conta, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        lay.Add(wx.StaticText(self, label="&Texto procurado:"), 0,
                wx.LEFT | wx.RIGHT, 8)
        self.termo = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER,
                                 name="Texto procurado")
        lay.Add(self.termo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        lay.Add(wx.StaticText(self, label="&Categoria:"), 0,
                wx.LEFT | wx.RIGHT, 8)
        self.categoria = wx.Choice(
            self, choices=[r for _, r in cw.CATEGORIAS], name="Categoria")
        self.categoria.SetSelection(0)
        lay.Add(self.categoria, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        lay.Add(wx.StaticText(self, label="&Lista, quando o texto está "
                              "vazio:"), 0, wx.LEFT | wx.RIGHT, 8)
        self.visao = wx.Choice(
            self, choices=[r for _, r in cw.VISOES],
            name="Lista, quando o texto está vazio")
        self.visao.SetSelection(0)
        lay.Add(self.visao, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.b_buscar = wx.Button(self, wx.ID_ANY, "&Buscar")
        lay.Add(self.b_buscar, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.rotulo = wx.StaticText(self, label="Resultados: ainda não "
                                    "buscou.")
        lay.Add(self.rotulo, 0, wx.LEFT | wx.RIGHT, 8)
        self.lista = wx.ListBox(self, name="Canais encontrados")
        lay.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)
        # os botoes de acao vem DEPOIS da lista: da lista, o Tab chega a eles
        botoes = wx.BoxSizer(wx.HORIZONTAL)
        self.b_seguir = wx.Button(self, wx.ID_ANY, "&Seguir o canal")
        self.b_ver = wx.Button(self, wx.ID_ANY, "Ver &publicações")
        self.b_mais = wx.Button(self, wx.ID_ANY, "Ver &mais")
        self.b_link = wx.Button(self, wx.ID_ANY, "Copiar o &link")
        self.b_fechar = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        for b in (self.b_seguir, self.b_ver, self.b_mais, self.b_link,
                  self.b_fechar):
            botoes.Add(b, 0, wx.RIGHT, 6)
        lay.Add(botoes, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.SetSizer(lay)
        self.b_buscar.SetDefault()
        self.b_seguir.Enable(False)
        self.b_ver.Enable(False)
        self.b_mais.Enable(False)
        self.b_link.Enable(False)

        self.b_buscar.Bind(wx.EVT_BUTTON, lambda e: self.buscar())
        self.b_mais.Bind(wx.EVT_BUTTON, lambda e: self.ver_mais())
        self.termo.Bind(wx.EVT_TEXT_ENTER, lambda e: self.buscar())
        self.b_seguir.Bind(wx.EVT_BUTTON, lambda e: self._seguir())
        self.b_link.Bind(wx.EVT_BUTTON, lambda e: self._copiar_link())
        self.b_ver.Bind(wx.EVT_BUTTON, lambda e: self._ver_publicacoes())
        self.lista.Bind(wx.EVT_LISTBOX, lambda e: self._ajustar_botoes())
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._seguir())
        self.lista.Bind(wx.EVT_CHAR_HOOK, self._tecla_da_lista)
        self.termo.SetFocus()

    # ------------------------------------------------------- busca
    def _conta_escolhida(self):
        i = self.caixa_conta.GetSelection() if self.caixa_conta else 0
        return self.contas[max(i, 0)][0]

    def buscar(self):
        if self.ocupada:
            self.falar("Já estou buscando.")
            return
        texto = self.termo.GetValue().strip()
        categoria = cw.CATEGORIAS[max(self.categoria.GetSelection(), 0)][0]
        visao = cw.VISOES[max(self.visao.GetSelection(), 0)][0]
        self._pedido = (self._conta_escolhida(), texto, categoria, visao)
        self._pedir("", "Buscando no WhatsApp.", False)

    def ver_mais(self):
        """A pagina seguinte da ultima busca, acrescentada a lista (a
        selecao fica onde esta)."""
        if self.ocupada:
            self.falar("Já estou buscando.")
            return
        if self._pedido is None:
            self.falar("Faça uma busca antes.")
            return
        if self.fim:
            self.falar("Não há mais canais.")
            return
        if not self.proximo:
            self.falar("O WhatsApp não informou a próxima página desta "
                       "lista.")
            return
        self._pedir(self.proximo, "Buscando mais canais.", True)

    def _pedir(self, cursor, aviso, acrescentar):
        conta_id, texto, categoria, visao = self._pedido
        self.ocupada = True
        for b in (self.b_buscar, self.b_seguir, self.b_mais, self.b_link):
            b.Enable(False)
        self.rotulo.SetLabel("Resultados: " + aviso.lower())
        self.falar(aviso)

        ja_vistos = {c.id for c in self.canais} if acrescentar else set()

        def trabalho():
            try:
                pagina = self.buscar_fn(conta_id, texto, categoria, visao,
                                        cursor)
                # o WhatsApp pode devolver uma pagina sem canal (a busca
                # filtra depois de paginar) e ainda mandar o cursor da
                # seguinte: segue em frente, com um teto
                usado, vazias = cursor, 0
                while pagina.proximo and pagina.proximo != usado and \
                        vazias < PAGINAS_VAZIAS_SEGUIDAS and not [
                            c for c in pagina.canais
                            if c.id not in ja_vistos]:
                    usado, vazias = pagina.proximo, vazias + 1
                    pagina = self.buscar_fn(conta_id, texto, categoria,
                                            visao, usado)
                pagina, erro = pagina, ""
            except RuntimeError as e:
                pagina, erro = None, str(e)
            except Exception:
                pagina, erro = None, "Algo deu errado na busca."
            wx.CallAfter(self._mostrar, pagina, erro, acrescentar, cursor)
        threading.Thread(target=trabalho, daemon=True,
                         name="busca-de-canais").start()

    def _mostrar(self, pagina, erro, acrescentar=False, cursor=""):
        if not self:                        # a janela ja foi fechada
            return
        self.ocupada = False
        self.b_buscar.Enable(True)
        if erro:
            if not acrescentar:
                self.canais = []
                self.proximo = ""
                self.lista.Set([])
            self.rotulo.SetLabel("Resultados: " + erro)
            self.falar(erro)
            self._ajustar_botoes()
            return
        if not acrescentar:
            self.canais = list(pagina.canais)
            self.proximo = pagina.proximo
            self.fim = False
            self.lista.Set([cw.linha(c) for c in self.canais])
            resumo = cw.resumo(len(self.canais))
            if self.canais:
                self.lista.SetSelection(0)
        else:
            vistos = {c.id for c in self.canais}
            novos = [c for c in pagina.canais if c.id not in vistos]
            primeiro = len(self.canais)
            self.canais.extend(novos)
            for c in novos:
                self.lista.Append(cw.linha(c))
            # sem canal novo, ou o mesmo cursor de volta: acabou
            self.proximo = pagina.proximo if novos and \
                pagina.proximo != cursor else ""
            # (uma pagina sem canal novo, depois das tentativas, e o fim)
            self.fim = not self.proximo
            if novos:
                self.lista.SetSelection(primeiro)
                resumo = "%d canais a mais, %d no total." % (
                    len(novos), len(self.canais)) if len(novos) > 1 else \
                    "1 canal a mais, %d no total." % len(self.canais)
            else:
                resumo = "O WhatsApp não tem mais canais."
        if self.proximo:
            resumo += " Há mais: Alt M, ou o botão Ver mais depois da lista."
        self.rotulo.SetLabel("Resultados: " + resumo)
        self.falar(resumo)
        self._ajustar_botoes()
        if self.canais:
            self.lista.SetFocus()

    # ------------------------------------------------------- escolha
    def _atual(self):
        i = self.lista.GetSelection()
        return self.canais[i] if 0 <= i < len(self.canais) else None

    def _ajustar_botoes(self):
        atual = self._atual()
        self.b_seguir.Enable(atual is not None and not atual.seguindo
                             and not self.ocupada)
        self.b_link.Enable(atual is not None and bool(atual.link))
        self.b_ver.Enable(atual is not None and self.ver_fn is not None
                          and not self.ocupada)
        # sempre ligado depois de uma busca (assim o leitor de tela o acha);
        # sem cursor ou no fim, apertar explica por que nao ha mais
        self.b_mais.Enable(self._pedido is not None and not self.fim
                           and not self.ocupada)

    def _tecla_da_lista(self, evt):
        if evt.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and \
                not (evt.AltDown() or evt.ControlDown() or evt.ShiftDown()):
            self._seguir()
            return
        evt.Skip()

    def _seguir(self):
        c = self._atual()
        if c is None:
            self.falar("Escolha um canal.")
            return
        if c.seguindo:
            self.falar("Você já segue este canal.")
            return
        if self.ocupada:
            self.falar("Espere a busca terminar.")
            return
        r = dialogos.perguntar(
            "confirmar_grupos_e_canais",
            "Seguir o canal %s? Quem administra o canal pode ver que você "
            "o segue." % (c.nome or "sem nome"), "Seguir o canal",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self, self.cfg)
        if r != wx.YES:
            return
        self.ocupada = True
        self.b_seguir.Enable(False)
        self.falar("Seguindo.")
        conta_id = self._conta_escolhida()

        def trabalho():
            try:
                ok, texto = self.seguir_fn(conta_id, c)
            except Exception:
                ok, texto = False, "Algo deu errado ao seguir o canal."
            wx.CallAfter(self._seguiu, c, ok, texto)
        threading.Thread(target=trabalho, daemon=True,
                         name="seguir-canal").start()

    def _seguiu(self, canal, ok, texto):
        if not self:
            return
        self.ocupada = False
        if ok and canal in self.canais:
            i = self.canais.index(canal)
            novo = cw.CanalWA(canal.id, canal.nome, canal.descricao,
                              canal.seguidores, canal.verificado, True,
                              canal.convite)
            self.canais[i] = novo
            self.lista.SetString(i, cw.linha(novo))
        self.falar(texto)
        self._ajustar_botoes()

    def _copiar_link(self):
        c = self._atual()
        if c is None or not c.link:
            self.falar("Este canal não tem link.")
            return
        if wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(wx.TextDataObject(c.link))
            finally:
                wx.TheClipboard.Close()
            self.falar("Link copiado.")
        else:
            self.falar("Não consegui usar a área de transferência.")

    def _ver_publicacoes(self):
        c = self._atual()
        if c is None:
            self.falar("Escolha um canal.")
            return
        if self.ocupada:
            self.falar("Espere a busca terminar.")
            return
        self.ocupada = True
        self._ajustar_botoes()
        self.falar("Lendo as publicações.")
        conta_id = self._conta_escolhida()

        def trabalho():
            try:
                texto, erro = self.ver_fn(conta_id, c), ""
            except RuntimeError as e:
                texto, erro = "", str(e)
            except Exception:
                texto, erro = "", "Algo deu errado ao ler as publicações."
            wx.CallAfter(self._publicacoes_prontas, c, texto, erro)
        threading.Thread(target=trabalho, daemon=True,
                         name="ver-canal").start()

    def _publicacoes_prontas(self, canal, texto, erro):
        if not self:
            return
        self.ocupada = False
        self._ajustar_botoes()
        if erro:
            self.falar(erro)
            return
        self.falar("Publicações prontas.")
        indice = self.lista.GetSelection()
        dialogos.mostrar_texto(
            self, "Publicações de %s" % (canal.nome or "canal"), texto,
            "Publicações do canal")
        # Esc fecha a leitura e volta para o mesmo canal da lista de
        # resultados, como na busca global do Telegram
        if self and indice >= 0:
            self.lista.SetSelection(indice)
            self.lista.SetFocus()
            self._ajustar_botoes()

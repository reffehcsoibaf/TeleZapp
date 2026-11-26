# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela do que a lista de conversas (ou a de mensagens) mostra: ativar e
desativar cada informacao e escolher a ordem em que aparecem.

Serve a janela de configuracoes (onde as mudancas ficam pendentes ate OK ou
Aplicar) e o menu Exibir (onde valem na hora): quem chama diz como ler e como
guardar o valor.
"""
import wx

from telezapp.nucleo import lista_conversas as lc


class DialogoListaConversas(wx.Dialog):
    """Lista de quatro informacoes, na ordem em que aparecem na lista de
    conversas; Enter ou Espaco ativa e desativa, e dois botoes mudam a ordem.
    Com `nucleo=lista_mensagens`, serve a lista de mensagens."""

    def __init__(self, pai, ler, gravar, fala=None, nucleo=lc,
                 titulo="Lista de conversas",
                 explicacao="O que cada conversa mostra na lista, na ordem em "
                            "que aparece. Pelo menos um item fica ativado.",
                 foco=None):
        """ler() -> valor atual; gravar(valor) guarda o novo; fala, se houver,
        diz o que mudou. `nucleo`: lista_conversas ou lista_mensagens. `foco`:
        onde comecar, como a busca das configuracoes pede (uma informacao,
        "digitar", "so_muda", "cima" ou "padrao")."""
        super().__init__(pai, title=titulo, style=wx.DEFAULT_DIALOG_STYLE)
        self.ler, self.gravar, self.fala = ler, gravar, fala
        self.lc, self.titulo = nucleo, titulo
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(self, label=explicacao), 0, wx.ALL, 10)
        lay.Add(wx.StaticText(
            self, label="&Informações (Enter ou Espaço ativa e desativa):"),
            0, wx.LEFT | wx.RIGHT, 10)
        self.lista = wx.ListBox(self, name="Informações", size=(420, 120 if nucleo is lc else 220))
        lay.Add(self.lista, 1, wx.EXPAND | wx.ALL, 10)
        self.so_muda = None
        if hasattr(nucleo, "ROTULO_SO_QUANDO_MUDA"):
            self.so_muda = wx.CheckBox(self,
                                       label=nucleo.ROTULO_SO_QUANDO_MUDA)
            self.so_muda.SetValue(nucleo.so_quando_muda(self.ler()))
            lay.Add(self.so_muda, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
            self.so_muda.Bind(wx.EVT_CHECKBOX,
                              lambda e: self.mudar_so_quando_muda())
        self.digitar = None
        if hasattr(nucleo, "ESCOLHAS_DIGITAR"):    # o aviso falado nao tem
            rotulo = "&Ao digitar uma letra nesta lista:"
            lay.Add(wx.StaticText(self, label=rotulo), 0,
                    wx.LEFT | wx.RIGHT, 10)
            self.digitar = wx.Choice(
                self, choices=[r for _, r in nucleo.ESCOLHAS_DIGITAR],
                name=rotulo.replace("&", ""))
            lay.Add(self.digitar, 0,
                    wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
            self._mostrar_digitar()
            self.digitar.Bind(wx.EVT_CHOICE, lambda e: self.mudar_digitar())
        self.modelo = None
        self.botao_flags = None
        self._sincronizando = False
        if hasattr(nucleo, "FLAGS"):       # so o aviso falado tem modelo
            rotulo = "&Modelo do aviso (flags e texto livre):"
            lay.Add(wx.StaticText(self, label=rotulo), 0,
                    wx.LEFT | wx.RIGHT, 10)
            self.modelo = wx.TextCtrl(
                self, value=self.lc.normalizar(self.ler())["modelo"],
                style=wx.TE_MULTILINE, size=(420, 80),
                name=rotulo.replace("&", ""))
            lay.Add(self.modelo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
            self.modelo.Bind(wx.EVT_TEXT, lambda e: self.mudar_modelo())
            self.botao_flags = wx.Button(self, label="Inserir &flag")
            linha_flags = wx.WrapSizer(wx.HORIZONTAL)
            linha_flags.Add(self.botao_flags, 0, wx.RIGHT | wx.BOTTOM, 8)
            lay.Add(linha_flags, 0, wx.LEFT | wx.RIGHT, 10)
            self.botao_flags.Bind(
                wx.EVT_BUTTON, lambda e: self.inserir_flag())
        linha = wx.WrapSizer(wx.HORIZONTAL)
        self.botoes = {}
        for chave, rotulo in (("cima", "Mover para &cima"),
                              ("baixo", "Mover para &baixo"),
                              ("padrao", "&Restaurar o padrão")):
            b = wx.Button(self, label=rotulo)
            self.botoes[chave] = b
            linha.Add(b, 0, wx.RIGHT | wx.BOTTOM, 8)
        lay.Add(linha, 0, wx.LEFT | wx.RIGHT, 10)
        lay.Add(wx.Button(self, wx.ID_OK, "&Fechar"), 0,
                wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetEscapeId(wx.ID_OK)
        self.SetSizerAndFit(lay)
        self.CentreOnParent()
        self.lista.Bind(wx.EVT_KEY_DOWN, self._tecla)
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.alternar())
        self.botoes["cima"].Bind(wx.EVT_BUTTON, lambda e: self.mover(-1))
        self.botoes["baixo"].Bind(wx.EVT_BUTTON, lambda e: self.mover(1))
        self.botoes["padrao"].Bind(wx.EVT_BUTTON, lambda e: self.restaurar())
        self.preencher(0)
        self.lista.SetFocus()
        if foco is not None:
            self._focar(foco)

    def _focar(self, foco):
        ordem = self.lc.normalizar(self.ler())["ordem"]
        if foco in ordem:
            self.preencher(ordem.index(foco))
        elif foco == "digitar" and self.digitar is not None:
            self.digitar.SetFocus()
        elif foco == "so_muda" and self.so_muda is not None:
            self.so_muda.SetFocus()
        elif foco == "modelo" and self.modelo is not None:
            self.modelo.SetFocus()
        elif foco == "inserir_flag" and self.botao_flags is not None:
            self.botao_flags.SetFocus()
        elif foco in self.botoes and self.botoes[foco].IsEnabled():
            self.botoes[foco].SetFocus()

    # -------------------------------------------------------------- lista
    def preencher(self, selecionar=0):
        lay = self.lc.normalizar(self.ler())
        self.lista.Set([self.lc.texto_do_item(lay, c) for c in lay["ordem"]])
        self.lista.SetSelection(min(max(selecionar, 0),
                                    len(lay["ordem"]) - 1))
        self.botoes["padrao"].Enable(not self.lc.eh_padrao(lay))

    def chave(self):
        """A informacao selecionada, ou None."""
        ordem = self.lc.normalizar(self.ler())["ordem"]
        i = self.lista.GetSelection()
        return ordem[i] if 0 <= i < len(ordem) else None

    def _dizer(self, texto):
        if self.fala is not None:
            self.fala.falar(texto, interromper=True)

    def _tecla(self, evt):
        sem_mod = not (evt.ControlDown() or evt.AltDown() or evt.ShiftDown())
        if sem_mod and evt.GetKeyCode() in (
                wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE):
            self.alternar()
            return
        evt.Skip()

    # ------------------------------------------------------------- acoes
    def alternar(self):
        chave = self.chave()
        if chave is None:
            return
        novo, ativado = self.lc.alternar(self.ler(), chave)
        if ativado is None:
            self._dizer(self.lc.MENSAGEM_DO_MINIMO)
            return
        self.gravar(novo)
        self._mostrar_modelo(novo)
        i = self.lista.GetSelection()
        self.preencher(i)
        self._dizer("ativado" if ativado else "desativado")

    def mover(self, delta):
        chave = self.chave()
        if chave is None:
            return
        novo, posicao = self.lc.mover(self.ler(), chave, delta)
        if posicao == self.lista.GetSelection():
            self._dizer("Já é o primeiro item." if delta < 0
                        else "Já é o último item.")
            return
        self.gravar(novo)
        self.preencher(posicao)
        self._dizer("%s, posição %d de %d." % (
            self.lc.ROTULOS[chave], posicao + 1, len(self.lc.CHAVES)))
        self.lista.SetFocus()

    def mudar_so_quando_muda(self):
        ligado = bool(self.so_muda.GetValue())
        self.gravar(self.lc.definir_so_quando_muda(self.ler(), ligado))
        self._dizer("Nome de quem enviou só quando muda: %s." % (
            "ativado" if ligado else "desativado"))

    def _mostrar_digitar(self):
        if self.digitar is None:
            return
        modos = [c for c, _ in self.lc.ESCOLHAS_DIGITAR]
        self.digitar.SetSelection(modos.index(self.lc.digitar(self.ler())))

    def mudar_digitar(self):
        modo = self.lc.ESCOLHAS_DIGITAR[self.digitar.GetSelection()][0]
        novo = self.lc.definir_digitar(self.ler(), modo)
        self.gravar(novo)
        self.botoes["padrao"].Enable(not self.lc.eh_padrao(novo))

    # ------------------------------------------------------------- modelo
    def _mostrar_modelo(self, valor):
        if self.modelo is not None:
            self._sincronizando = True
            self.modelo.SetValue(self.lc.normalizar(valor)["modelo"])
            self._sincronizando = False

    def mudar_modelo(self):
        """Texto digitado manda: as flags presentes ligam os itens da lista."""
        if self._sincronizando or self.modelo is None:
            return
        novo = self.lc.definir_modelo(self.ler(), self.modelo.GetValue())
        self.gravar(novo)
        self.preencher(self.lista.GetSelection())
        self.botoes["padrao"].Enable(not self.lc.eh_padrao(novo))

    def inserir_flag(self):
        """Abre um menu com as flags e insere a escolhida no cursor."""
        if self.modelo is None:
            return
        ponto = self.modelo.GetInsertionPoint()
        menu = wx.Menu()
        try:
            for chave in self.lc.CHAVES:
                flag = self.lc.FLAGS[chave]
                item = menu.Append(wx.ID_ANY, "%s — %s" % (
                    flag, self.lc.ROTULOS[chave]))
                # No Windows o comando do menu vai para a janela que abriu
                # o popup, nao para o menu: liga no dialogo, como nos outros
                # menus da interface.
                self.Bind(wx.EVT_MENU,
                          lambda e, f=flag, p=ponto: self._inserir_no_modelo(
                              f, p), item)
            self.botao_flags.PopupMenu(menu)
        finally:
            menu.Destroy()

    def _inserir_no_modelo(self, flag, ponto):
        self.modelo.SetFocus()
        self.modelo.InsertText(ponto, flag)
        self.modelo.SetInsertionPoint(ponto + len(flag))
        self.modelo.ShowPosition(ponto + len(flag))
        self.mudar_modelo()

    def restaurar(self):
        if self.so_muda is not None:
            self.so_muda.SetValue(False)
        self.gravar(self.lc.padrao())
        self._mostrar_modelo(self.ler())
        self._mostrar_digitar()
        self.preencher(0)
        self._dizer("%s no padrão." % self.titulo)
        self.lista.SetFocus()

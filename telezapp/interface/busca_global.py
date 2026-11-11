# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela da busca global no Telegram, como a do aplicativo.

Procura um texto no Telegram inteiro: pessoas, bots, grupos e canais (os da
conta e os públicos), mensagens de todas as conversas (também as que não
estão guardadas neste computador, com filtro por fotos, vídeos, arquivos,
músicas, voz ou links) e posts públicos de canais. Tudo cai numa lista só,
cada linha dizendo o que é.

Digite o texto e use Enter ou Buscar. Enter num resultado, ou Abrir, abre a
conversa (na mensagem, quando for uma mensagem). Entrar participa de um grupo
ou canal público achado.

A busca fala com o Telegram e pode demorar, por isso roda fora da janela: ela
avisa quando começa e quando termina. A lógica está em `nucleo.busca_global`
e no provedor; aqui só o desenho.
"""
import threading

import wx

from telezapp.interface import dialogos
from telezapp.nucleo import busca_global as bg


class DialogoBuscaGlobal(wx.Dialog):
    def __init__(self, pai, contas, buscar, entrar=None, falar=None,
                 nome_de_conta=None):
        """contas: [(id, nome)] das contas do Telegram; buscar(conta_id,
        texto, modo, filtro) -> ([(tipo, objeto, texto)], [avisos]) (bloqueia;
        levanta RuntimeError com o motivo); entrar(conta_id, conversa_id) ->
        (ok, texto); falar(texto) fala sem esperar."""
        super().__init__(pai, title="Busca global no Telegram",
                         size=(760, 600),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.contas = list(contas)
        self.buscar_fn = buscar
        self.entrar_fn = entrar
        self.falar = falar or (lambda texto: None)
        self.linhas = []                  # [(tipo, objeto, texto)]
        self.proximo = None               # onde continuar (opaco), se houver
        self._pedido = None               # (conta, texto, modo, filtro)
        self.fim = False
        self.escolhido = None             # (tipo, objeto), ao fechar com OK
        self.ocupada = False

        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(self, label=(
            "Procura no Telegram inteiro, como a busca do aplicativo: "
            "pessoas, grupos, canais públicos, mensagens e posts públicos. "
            "Digite e use Enter.")), 0, wx.ALL, 8)
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
        lay.Add(wx.StaticText(self, label="&Procurar em:"), 0,
                wx.LEFT | wx.RIGHT, 8)
        self.modo = wx.Choice(self, choices=[r for _, r in bg.MODOS],
                              name="Procurar em")
        self.modo.SetSelection(0)
        lay.Add(self.modo, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        lay.Add(wx.StaticText(self, label="Tipo de &conteúdo das "
                              "mensagens:"), 0, wx.LEFT | wx.RIGHT, 8)
        self.filtro = wx.Choice(self, choices=[r for _, r, _ in bg.FILTROS],
                                name="Tipo de conteúdo das mensagens")
        self.filtro.SetSelection(0)
        lay.Add(self.filtro, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.b_buscar = wx.Button(self, wx.ID_ANY, "&Buscar")
        lay.Add(self.b_buscar, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.rotulo = wx.StaticText(self, label="Resultados: ainda não "
                                    "buscou.")
        lay.Add(self.rotulo, 0, wx.LEFT | wx.RIGHT, 8)
        self.lista = wx.ListBox(self, name="Resultados da busca global")
        lay.Add(self.lista, 1, wx.EXPAND | wx.ALL, 8)
        # os botoes de acao vem DEPOIS da lista: da lista, o Tab chega a eles
        botoes = wx.BoxSizer(wx.HORIZONTAL)
        self.b_abrir = wx.Button(self, wx.ID_ANY, "&Abrir")
        self.b_entrar = wx.Button(self, wx.ID_ANY, "&Entrar no grupo ou canal")
        self.b_mais = wx.Button(self, wx.ID_ANY, "Ver &mais")
        self.b_fechar = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        for b in (self.b_abrir, self.b_entrar, self.b_mais, self.b_fechar):
            botoes.Add(b, 0, wx.RIGHT, 6)
        lay.Add(botoes, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.SetSizer(lay)
        self.b_buscar.SetDefault()
        self.b_abrir.Enable(False)
        self.b_entrar.Enable(False)
        self.b_mais.Enable(False)

        self.b_buscar.Bind(wx.EVT_BUTTON, lambda e: self.buscar())
        self.b_mais.Bind(wx.EVT_BUTTON, lambda e: self.ver_mais())
        self.termo.Bind(wx.EVT_TEXT_ENTER, lambda e: self.buscar())
        self.b_abrir.Bind(wx.EVT_BUTTON, lambda e: self._abrir())
        self.b_entrar.Bind(wx.EVT_BUTTON, lambda e: self._entrar())
        self.modo.Bind(wx.EVT_CHOICE, lambda e: self._ajustar_filtro())
        self.lista.Bind(wx.EVT_LISTBOX, lambda e: self._ajustar_botoes())
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._abrir())
        self.lista.Bind(wx.EVT_CHAR_HOOK, self._tecla_da_lista)
        self.termo.SetFocus()

    # ------------------------------------------------------- busca
    def _conta_escolhida(self):
        i = self.caixa_conta.GetSelection() if self.caixa_conta else 0
        return self.contas[max(i, 0)][0]

    def _modo(self):
        return bg.MODOS[max(self.modo.GetSelection(), 0)][0]

    def _filtro(self):
        return bg.FILTROS[max(self.filtro.GetSelection(), 0)][0]

    def _ajustar_filtro(self):
        """O tipo de conteudo so vale para mensagens."""
        self.filtro.Enable(self._modo() in ("tudo", "mensagens"))

    def buscar(self):
        texto = self.termo.GetValue().strip()
        modo = self._modo()
        filtro = self._filtro() if self.filtro.IsEnabled() else "qualquer"
        if not texto and not bg.pode_buscar_sem_texto(modo, filtro):
            self.falar("Digite o texto que quer procurar.")
            self.termo.SetFocus()
            return
        if self.ocupada:
            self.falar("Já estou buscando.")
            return
        self._pedido = (self._conta_escolhida(), texto, modo, filtro)
        self._pedir(None, "Buscando no Telegram.", False)

    def ver_mais(self):
        """A pagina seguinte de mensagens e posts da ultima busca, no fim da
        lista (pessoas, grupos e canais vem todos na primeira)."""
        if self.ocupada:
            self.falar("Já estou buscando.")
            return
        if self._pedido is None:
            self.falar("Faça uma busca antes.")
            return
        if self.fim or not self.proximo:
            self.falar("Não há mais resultados.")
            return
        self._pedir(self.proximo, "Buscando mais resultados.", True)

    def _pedir(self, cursor, aviso, acrescentar):
        conta_id, texto, modo, filtro = self._pedido
        self.ocupada = True
        for b in (self.b_buscar, self.b_abrir, self.b_entrar, self.b_mais):
            b.Enable(False)
        self.rotulo.SetLabel("Resultados: " + aviso.lower())
        self.falar(aviso)

        def trabalho():
            try:
                resposta = self.buscar_fn(conta_id, texto, modo, filtro,
                                          cursor)
                linhas, avisos = resposta[0], resposta[1]
                proximo = resposta[2] if len(resposta) > 2 else None
                erro = ""
            except RuntimeError as e:
                linhas, avisos, proximo, erro = [], [], None, str(e)
            except Exception:
                linhas, avisos, proximo, erro = (
                    [], [], None, "Algo deu errado na busca.")
            wx.CallAfter(self._mostrar, linhas, avisos, erro, proximo,
                         acrescentar)
        threading.Thread(target=trabalho, daemon=True,
                         name="busca-global").start()

    def _mostrar(self, linhas, avisos, erro, proximo=None,
                 acrescentar=False):
        if not self:                        # a janela ja foi fechada
            return
        self.ocupada = False
        self.b_buscar.Enable(True)
        if erro:
            if not acrescentar:
                self.linhas = []
                self.proximo = None
                self.lista.Set([])
            self.rotulo.SetLabel("Resultados: " + erro)
            self.falar(erro)
            self._ajustar_botoes()
            return
        if acrescentar:
            vistos = {self._chave(o) for _, o, _ in self.linhas}
            novas = [x for x in linhas if self._chave(x[1]) not in vistos]
            primeira = len(self.linhas)
            self.linhas.extend(novas)
            for _, _, t in novas:
                self.lista.Append(t)
            self.proximo = proximo if novas else None
            self.fim = not self.proximo
            if novas:
                self.lista.SetSelection(primeira)
                texto = "%d resultados a mais, %d no total." % (
                    len(novas), len(self.linhas)) if len(novas) > 1 else \
                    "1 resultado a mais, %d no total." % len(self.linhas)
            else:
                texto = "O Telegram não tem mais resultados."
        else:
            self.linhas = list(linhas)
            self.proximo = proximo
            self.fim = False
            self.lista.Set([t for _, _, t in self.linhas])
            n = len(self.linhas)
            if n == 0:
                texto = "Nada encontrado."
            else:
                texto = bg.resumo(*(sum(1 for t, _, _ in self.linhas
                                        if t == k)
                                    for k in ("chat", "mensagem",
                                              "post"))) + "."
                self.lista.SetSelection(0)
        if self.proximo:
            texto += " Há mais: Alt M, ou o botão Ver mais depois da lista."
        if avisos:
            texto += " " + " ".join(avisos)
        self.rotulo.SetLabel("Resultados: " + texto)
        self.falar(texto)
        self._ajustar_botoes()
        if self.linhas:
            self.lista.SetFocus()

    @staticmethod
    def _chave(objeto):
        """Identifica um resultado para nao repeti-lo ao acrescentar."""
        x = getattr(objeto, "mensagem", None)
        if x is not None:
            return ("m", x.conta_id, x.conversa_id, x.id)
        c = getattr(objeto, "conversa", None)
        return ("c", c.conta_id, c.id) if c is not None else id(objeto)

    # ------------------------------------------- voltar a uma busca
    def estado(self):
        """O que a pessoa tinha na janela, para voltar a ela depois de abrir
        um resultado (Esc na conversa)."""
        return {"conta": self.caixa_conta.GetSelection()
                if self.caixa_conta else 0,
                "termo": self.termo.GetValue(),
                "modo": self.modo.GetSelection(),
                "filtro": self.filtro.GetSelection(),
                "linhas": list(self.linhas),
                "escolhido": self.lista.GetSelection(),
                "proximo": self.proximo, "fim": self.fim,
                "pedido": self._pedido}

    def restaurar(self, estado):
        """Refaz a janela como estava, sem buscar de novo, com o foco no
        resultado em que a pessoa parou."""
        if self.caixa_conta and 0 <= estado["conta"] < len(self.contas):
            self.caixa_conta.SetSelection(estado["conta"])
        self.termo.SetValue(estado["termo"])
        self.modo.SetSelection(max(estado["modo"], 0))
        self.filtro.SetSelection(max(estado["filtro"], 0))
        self._ajustar_filtro()
        self.linhas = list(estado["linhas"])
        self.proximo = estado.get("proximo")
        self.fim = estado.get("fim", False)
        self._pedido = estado.get("pedido")
        self.lista.Set([t for _, _, t in self.linhas])
        n = len(self.linhas)
        if n:
            self.lista.SetSelection(
                min(max(estado["escolhido"], 0), n - 1))
            self.rotulo.SetLabel("Resultados: voltei à busca anterior, %d "
                                 "resultados." % n)
            self.lista.SetFocus()
        self._ajustar_botoes()

    # ------------------------------------------------------- escolha
    def _atual(self):
        i = self.lista.GetSelection()
        return self.linhas[i] if 0 <= i < len(self.linhas) else None

    def _ajustar_botoes(self):
        atual = self._atual()
        self.b_abrir.Enable(atual is not None)
        self.b_entrar.Enable(
            atual is not None and atual[0] == "chat"
            and atual[1].pode_entrar() and self.entrar_fn is not None)
        # sempre ligado depois de uma busca (assim o leitor de tela o acha);
        # sem mais paginas, apertar explica
        self.b_mais.Enable(self._pedido is not None and not self.fim
                           and not self.ocupada)

    def _tecla_da_lista(self, evt):
        if evt.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and \
                not (evt.AltDown() or evt.ControlDown() or evt.ShiftDown()):
            self._abrir()
            return
        evt.Skip()

    def _abrir(self):
        atual = self._atual()
        if atual is None:
            self.falar("Escolha um resultado.")
            return
        self.escolhido = (atual[0], atual[1])
        self.EndModal(wx.ID_OK)

    def _entrar(self):
        atual = self._atual()
        if atual is None or atual[0] != "chat" or \
                not atual[1].pode_entrar() or self.entrar_fn is None:
            self.falar("Escolha um grupo ou canal em que você ainda não está.")
            return
        c = atual[1].conversa
        r = dialogos.perguntar("confirmar_grupos_e_canais", 
            "Entrar em %s? Quem administra e os outros membros passam a ver "
            "que você está lá." % c.nome, "Entrar no grupo ou canal",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
        if r != wx.YES:
            return
        self.falar("Entrando.")
        ok, texto = self.entrar_fn(c.conta_id, c.id)
        if ok:
            atual[1].participa = True
            i = self.lista.GetSelection()
            self.linhas[i] = (atual[0], atual[1], atual[1].texto_da_lista())
            self.lista.SetString(i, self.linhas[i][2])
        self.falar(texto)
        self._ajustar_botoes()

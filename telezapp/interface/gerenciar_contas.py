# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela de Gerenciar contas: uma lista em que cada conta tem uma caixa de
marcar (marcada = ativada, desmarcada = desativada), e, com a conta em foco,
os botões Nova conta, Excluir e Renomear (Tab) e, depois deles, a caixa de
guardar os dados de cada conta em uma pasta separada, com o campo da pasta.
Quem muda as contas é a Janela; aqui só fica a tela."""
import wx


class DialogoContas(wx.Dialog):
    """`itens()`: [(conta_id, rotulo, ativa)]. `ao_marcar(conta_id, ativa)`,
    `ao_excluir(conta_id)` e `ao_renomear(conta_id)` devolvem True se mudou
    algo (a lista é refeita). `ao_adicionar()` abre o fluxo de criar uma
    conta nova (o login pode demorar; a lista se refaz quando o diálogo
    volta a ficar ativo). `dados`: (separar, pasta) com o que as opcoes
    dizem agora de onde ficam os dados das contas; sem ele, essa parte
    nao aparece. `valores()` devolve o que a pessoa deixou nela."""

    def __init__(self, pai, itens, ao_marcar, ao_excluir, ao_renomear,
                 ao_adicionar, dados=None):
        super().__init__(pai, title="Gerenciar contas",
                         style=wx.DEFAULT_DIALOG_STYLE)
        self._itens, self._ao_marcar = itens, ao_marcar
        self._ao_excluir, self._ao_renomear = ao_excluir, ao_renomear
        self._ao_adicionar = ao_adicionar
        self._ids = []
        lay = wx.BoxSizer(wx.VERTICAL)
        rotulo = ("Contas. Espaço marca ou desmarca: marcada fica "
                  "conectada, desmarcada não conecta (as conversas "
                  "guardadas continuam na tela). Tab leva a Nova conta, "
                  "Excluir e Renomear.")
        explicacao = wx.StaticText(self, label=rotulo)
        explicacao.Wrap(440)
        lay.Add(explicacao, 0, wx.ALL, 10)
        self.lista = wx.CheckListBox(self, choices=[], name="Contas",
                                     size=(440, 160))
        lay.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        linha = wx.BoxSizer(wx.HORIZONTAL)
        self.adicionar = wx.Button(self, label="&Nova conta...")
        self.excluir = wx.Button(self, label="&Excluir...")
        self.renomear = wx.Button(self, label="&Renomear...")
        fechar = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        for b in (self.adicionar, self.excluir, self.renomear):
            linha.Add(b, 0, wx.RIGHT, 8)
        lay.Add(linha, 0, wx.ALL, 10)
        self.separar = self.pasta = self.escolher = self.rotulo_pasta = None
        if dados is not None:
            self._criar_dados(lay, *dados)
        lay.Add(fechar, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.Bind(wx.EVT_CHECKLISTBOX, self._marcou, self.lista)
        self.Bind(wx.EVT_BUTTON, self._clicou_adicionar, self.adicionar)
        self.Bind(wx.EVT_BUTTON, self._clicou_excluir, self.excluir)
        self.Bind(wx.EVT_BUTTON, self._clicou_renomear, self.renomear)
        # a conta nova só entra na configuração quando o login termina;
        # ao voltar pra cá (dialogos do login fechados), refaz a lista
        self.Bind(wx.EVT_ACTIVATE, self._ativou)
        self._preencher(0)
        self.CentreOnParent()
        self.lista.SetFocus()

    def _criar_dados(self, lay, separar, pasta):
        """Onde ficam os dados das contas: uma caixa e, so com ela
        marcada, o campo da pasta (rotulo antes do campo, para o leitor
        de tela)."""
        self.separar = wx.CheckBox(
            self, label="&Guardar os dados de cada conta em uma pasta "
                        "separada", name="Dados de cada conta em pasta "
                                         "separada")
        self.separar.SetValue(bool(separar))
        lay.Add(self.separar, 0, wx.LEFT | wx.RIGHT, 10)
        self.rotulo_pasta = wx.StaticText(
            self, label="Pasta dos dados das &contas (vazia: a pasta "
                        "padrão do TeleZapp):")
        lay.Add(self.rotulo_pasta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.pasta = wx.TextCtrl(self, value=pasta or "", size=(440, -1),
                                 name="Pasta dos dados das contas")
        lay.Add(self.pasta, 0, wx.LEFT | wx.RIGHT, 10)
        self.escolher = wx.Button(self, label="Escolher a pas&ta...")
        lay.Add(self.escolher, 0, wx.ALL, 10)
        self.Bind(wx.EVT_CHECKBOX, self._mostrou_dados, self.separar)
        self.Bind(wx.EVT_BUTTON, self._clicou_escolher, self.escolher)
        self._mostrar_dados()

    def _mostrar_dados(self):
        visivel = self.separar.GetValue()
        for parte in (self.rotulo_pasta, self.pasta, self.escolher):
            parte.Show(visivel)
        self.Layout()
        self.Fit()

    def _mostrou_dados(self, evt):
        self._mostrar_dados()

    def _clicou_escolher(self, evt):
        dlg = wx.DirDialog(self, "Escolha a pasta dos dados das contas",
                           defaultPath=self.pasta.GetValue().strip())
        try:
            if dlg.ShowModal() == wx.ID_OK:
                self.pasta.SetValue(dlg.GetPath())
        finally:
            dlg.Destroy()

    def valores(self):
        """(separar, pasta) como a pessoa deixou; None sem essa parte."""
        if self.separar is None:
            return None
        return self.separar.GetValue(), self.pasta.GetValue().strip()

    def _preencher(self, selecionar):
        itens = self._itens()
        self._ids = [i[0] for i in itens]
        self.lista.Set([i[1] for i in itens])
        for n, (_, _, ativa) in enumerate(itens):
            self.lista.Check(n, bool(ativa))
        if itens:
            self.lista.SetSelection(max(0, min(selecionar, len(itens) - 1)))
        for b in (self.excluir, self.renomear):
            b.Enable(bool(itens))

    def _atual(self):
        n = self.lista.GetSelection()
        return (self._ids[n], n) if 0 <= n < len(self._ids) else (None, 0)

    def _marcou(self, evt):
        n = evt.GetInt()
        # a lista pode ter encolhido (conta excluida) antes do aviso chegar
        if 0 <= n < min(len(self._ids), self.lista.GetCount()):
            self._ao_marcar(self._ids[n], self.lista.IsChecked(n))
            self._preencher(n)

    def _clicou_adicionar(self, evt):
        self._ao_adicionar()
        # a conta pode já ter sido salva (Telegram conecta na hora) ou
        # ainda estar no login; _ativou refaz a lista ao voltar pra cá
        self._preencher(self.lista.GetSelection())

    def _ativou(self, evt):
        evt.Skip()
        if evt.GetActive() and not self.IsDestroyed():
            self._preencher(self.lista.GetSelection())

    def _clicou_excluir(self, evt):
        conta_id, n = self._atual()
        if conta_id and self._ao_excluir(conta_id):
            if not self._itens():
                # Sem contas: fecha sem desabilitar o botão que tem o foco
                # (o leitor de tela perderia a janela).
                self.EndModal(wx.ID_CANCEL)
                return
            self.lista.SetFocus()
            self._preencher(n)

    def _clicou_renomear(self, evt):
        conta_id, n = self._atual()
        if conta_id and self._ao_renomear(conta_id):
            self._preencher(n)

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela da busca por critérios nas mensagens guardadas.

Cada critério tem uma caixa de marcar: só vale se estiver marcada, e os
campos dele só ficam disponíveis (e entram na ordem de Tab) quando a caixa
está marcada. Os critérios marcados valem todos ao mesmo tempo. Buscar mostra
os resultados na lista de baixo; Enter, ou o botão Ver na conversa, abre a
conversa na mensagem escolhida.

O que é buscado é o que o TeleZapp guarda neste computador, não o que existe
na conta. A lógica está em `nucleo.busca`; aqui só o desenho.
"""
import wx

from telezapp.nucleo import busca
from telezapp.nucleo import modelos as m

LIMITE_DE_RESULTADOS = 500


class DialogoBusca(wx.Dialog):
    def __init__(self, pai, banco, contas, trancadas_liberadas=False,
                 anteriores=None, ao_ver=None, falar=None):
        """contas: [(id, nome)] das contas; ao_ver(achado) abre a conversa;
        falar(texto) fala sem esperar. `anteriores`: os criterios da ultima
        busca, para recomeçar dali."""
        super().__init__(pai, title="Busca por critérios",
                         size=(760, 640),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.banco, self.contas = banco, list(contas)
        self.liberadas = bool(trancadas_liberadas)
        self.ao_ver = ao_ver or (lambda achado: None)
        self.falar = falar or (lambda texto: None)
        self.achados = []
        self.escolhido = None           # o Achado aberto, ao fechar com OK
        self.criterios = None           # os criterios da ultima busca
        self.grupos = []                # (caixa, [controles])
        self._linhas = {}               # caixa -> a linha dela

        painel = wx.ScrolledWindow(self, style=wx.VSCROLL)
        painel.SetScrollRate(0, 24)
        col = wx.BoxSizer(wx.VERTICAL)
        self._painel, self._col = painel, col
        col.Add(wx.StaticText(
            painel, label="Marque os critérios que quer usar; os campos de "
            "cada um aparecem ao marcar. Todos os marcados valem juntos. "
            "A busca olha as mensagens guardadas neste computador."),
            0, wx.ALL, 8)

        # --- texto
        self.cb_termo, self.termo = self._com_texto(
            "&Texto da mensagem, legenda, nome do arquivo ou transcrição:",
            "Texto procurado")
        self.frase = wx.CheckBox(painel, label="Só &frase exata (as palavras "
                                 "juntas e na ordem)")
        self._junta(self.cb_termo, self.frase)
        # --- onde
        self.cb_servico, self.servicos = self._com_lista(
            "&Serviço:", "Serviços",
            [(s, m.SERVICOS[s]) for s in ("whatsapp", "telegram")])
        self.cb_conta, self.lista_contas = self._com_lista(
            "Co&nta:", "Contas", self.contas)
        self.cb_tipo_conv, self.tipos_conv = self._com_lista(
            "Tipo de &conversa:", "Tipos de conversa",
            busca.TIPOS_DE_CONVERSA)
        self.cb_situacao, self.situacoes = self._com_lista(
            "Situação da con&versa (todas as marcadas):",
            "Situação da conversa", self._situacoes())
        self.cb_nome_conv, self.nome_conv = self._com_texto(
            "&Nome da conversa contém:", "Nome da conversa")
        # --- mensagem
        self.cb_tipo_msg, self.tipos_msg = self._com_lista(
            "Tipo de &mensagem (qualquer das marcadas):", "Tipos de mensagem",
            busca.TIPOS_DE_MENSAGEM)
        self.cb_carac, self.caracteristicas = self._com_lista(
            "Características da mensa&gem (todas as marcadas):",
            "Características da mensagem", busca.CARACTERISTICAS)
        self.cb_quem = wx.CheckBox(painel, label="&Quem enviou:")
        rot = wx.StaticText(painel, label="Quem enviou:")
        self.quem = wx.Choice(painel, choices=[
            "Eu (mensagens que enviei)", "Outras pessoas"], name="Quem enviou")
        self.quem.SetSelection(0)
        self._soma(self.cb_quem, rot, self.quem)
        self.cb_autor, self.autor = self._com_texto(
            "Nome de quem enviou &contém:", "Nome de quem enviou")
        # --- quando
        self.cb_data = wx.CheckBox(painel, label="&Período (dia/mês/ano):")
        rot_de = wx.StaticText(painel, label="Data inicial, dia/mês/ano:")
        self.data_de = wx.TextCtrl(painel, name="Data inicial, dia/mês/ano")
        rot_ate = wx.StaticText(painel, label="Data final, dia/mês/ano:")
        self.data_ate = wx.TextCtrl(painel, name="Data final, dia/mês/ano")
        self._soma(self.cb_data, rot_de, self.data_de, rot_ate, self.data_ate)
        # --- medidas
        self.cb_duracao = wx.CheckBox(
            painel, label="&Duração de áudio, voz ou vídeo, em segundos:")
        rot_min = wx.StaticText(painel, label="Duração mínima em segundos:")
        self.seg_min = wx.TextCtrl(painel, name="Duração mínima em segundos")
        rot_max = wx.StaticText(painel, label="Duração máxima em segundos:")
        self.seg_max = wx.TextCtrl(painel, name="Duração máxima em segundos")
        self._soma(self.cb_duracao, rot_min, self.seg_min, rot_max,
                   self.seg_max)
        self.cb_tamanho = wx.CheckBox(painel,
                                      label="Tamanho do arqui&vo, em MB:")
        rot_min = wx.StaticText(painel, label="Tamanho mínimo em MB:")
        self.tam_min = wx.TextCtrl(painel, name="Tamanho mínimo em MB")
        rot_max = wx.StaticText(painel, label="Tamanho máximo em MB:")
        self.tam_max = wx.TextCtrl(painel, name="Tamanho máximo em MB")
        self._soma(self.cb_tamanho, rot_min, self.tam_min, rot_max,
                   self.tam_max)
        self.cb_envio, self.estados = self._com_lista(
            "Estado das mi&nhas mensagens enviadas:", "Estado do envio",
            busca.ESTADOS_DE_ENVIO)
        # --- ordem
        col.Add(wx.StaticText(painel, label="Ordem dos resultados:"), 0,
                wx.LEFT | wx.TOP, 8)
        self.ordem = wx.Choice(painel, choices=[
            "Mais novas primeiro", "Mais antigas primeiro"],
            name="Ordem dos resultados")
        self.ordem.SetSelection(0)
        col.Add(self.ordem, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        painel.SetSizer(col)

        self.b_buscar = wx.Button(self, wx.ID_ANY, "&Buscar")
        self.b_limpar = wx.Button(self, wx.ID_ANY, "&Limpar critérios")
        self.b_ver = wx.Button(self, wx.ID_ANY, "&Ver na conversa")
        self.b_fechar = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        self.rotulo_resultados = wx.StaticText(
            self, label="Resultados: ainda não buscou.")
        self.lista = wx.ListBox(self, name="Resultados da busca")

        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(painel, 3, wx.EXPAND)
        botoes = wx.BoxSizer(wx.HORIZONTAL)
        for b in (self.b_buscar, self.b_limpar, self.b_ver, self.b_fechar):
            botoes.Add(b, 0, wx.RIGHT, 6)
        lay.Add(botoes, 0, wx.ALL, 8)
        lay.Add(self.rotulo_resultados, 0, wx.LEFT | wx.RIGHT, 8)
        lay.Add(self.lista, 2, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(lay)
        self.b_buscar.SetDefault()

        self.b_buscar.Bind(wx.EVT_BUTTON, lambda e: self.buscar())
        self.b_limpar.Bind(wx.EVT_BUTTON, lambda e: self.limpar())
        self.b_ver.Bind(wx.EVT_BUTTON, lambda e: self._ver())
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._ver())
        self.lista.Bind(wx.EVT_CHAR_HOOK, self._tecla_da_lista)
        self.b_ver.Enable(False)
        if anteriores is not None:
            self.aplicar(anteriores)
        self.cb_termo.SetFocus()

    # ------------------------------------------------------- montagem
    def _situacoes(self):
        return [(c, r) for c, r in busca.SITUACOES
                if c != "trancada" or self.liberadas]

    def _soma(self, caixa, *controles):
        """Poe a caixa e os campos dela numa linha, e liga o liga/desliga."""
        linha = wx.WrapSizer(wx.HORIZONTAL)
        linha.Add(caixa, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        for c in controles:
            linha.Add(c, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        self._linhas[caixa] = linha
        self._col.Add(linha, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 8)
        # a caixa marcada libera os campos; os rotulos (StaticText) ficam
        reais = [c for c in controles if not isinstance(c, wx.StaticText)]
        for c in reais:
            c.Enable(False)
        self.grupos.append((caixa, reais))
        caixa.Bind(wx.EVT_CHECKBOX,
                   lambda e, cx=caixa, cs=reais: self._marcou(cx, cs))

    def _marcou(self, caixa, controles):
        marcada = caixa.GetValue()
        for c in controles:
            c.Enable(marcada)
        if marcada and controles:
            controles[0].SetFocus()

    def _junta(self, caixa, extra):
        """Poe mais um controle na linha de um criterio ja montado."""
        for cx, reais in self.grupos:
            if cx is caixa:
                reais.append(extra)
                extra.Enable(False)
                break
        self._linhas[caixa].Add(extra, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL,
                                6)

    def _com_texto(self, rotulo, nome):
        # o leitor de tela le o StaticText criado logo antes do campo
        caixa = wx.CheckBox(self._painel, label=rotulo)
        rot = wx.StaticText(self._painel, label=nome + ":")
        campo = wx.TextCtrl(self._painel, name=nome, size=(260, -1))
        self._soma(caixa, rot, campo)
        return caixa, campo

    def _com_lista(self, rotulo, nome, itens):
        """Caixa de marcar + lista de itens marcaveis. `itens`: [(valor,
        rotulo)]."""
        caixa = wx.CheckBox(self._painel, label=rotulo)
        rot = wx.StaticText(self._painel, label=nome + ":")
        lista = wx.CheckListBox(self._painel, choices=[r for _, r in itens],
                                name=nome, size=(300, 110))
        lista.valores = [v for v, _ in itens]
        self._soma(caixa, rot, lista)
        return caixa, lista

    @staticmethod
    def _marcados(lista):
        return {lista.valores[i] for i in range(len(lista.valores))
                if lista.IsChecked(i)}

    # ------------------------------------------------ criterios <-> campos
    def coletar(self):
        """Os `Criterios` que as caixas marcadas descrevem."""
        c = busca.Criterios(
            limite=LIMITE_DE_RESULTADOS, incluir_trancadas=self.liberadas,
            mais_antigas_primeiro=self.ordem.GetSelection() == 1)
        if self.cb_termo.GetValue():
            c.termo = self.termo.GetValue()
            c.frase_exata = self.frase.GetValue()
        if self.cb_servico.GetValue():
            c.servicos = self._marcados(self.servicos)
        if self.cb_conta.GetValue():
            c.contas = self._marcados(self.lista_contas)
        if self.cb_tipo_conv.GetValue():
            c.tipos_de_conversa = self._marcados(self.tipos_conv)
        if self.cb_situacao.GetValue():
            c.situacoes = self._marcados(self.situacoes)
        if self.cb_nome_conv.GetValue():
            c.conversa_contem = self.nome_conv.GetValue()
        if self.cb_tipo_msg.GetValue():
            c.tipos_de_mensagem = self._marcados(self.tipos_msg)
        if self.cb_carac.GetValue():
            c.caracteristicas = self._marcados(self.caracteristicas)
        if self.cb_quem.GetValue():
            c.minha = self.quem.GetSelection() == 0
        if self.cb_autor.GetValue():
            c.autor_contem = self.autor.GetValue()
        if self.cb_data.GetValue():
            c.data_de = busca.ler_data(self.data_de.GetValue())
            c.data_ate = busca.ler_data(self.data_ate.GetValue(), True)
        if self.cb_duracao.GetValue():
            c.segundos_min = busca.ler_numero(self.seg_min.GetValue())
            c.segundos_max = busca.ler_numero(self.seg_max.GetValue())
        if self.cb_tamanho.GetValue():
            mb = 1024 * 1024
            minimo = busca.ler_numero(self.tam_min.GetValue())
            maximo = busca.ler_numero(self.tam_max.GetValue())
            c.tamanho_min = None if minimo is None else int(minimo * mb)
            c.tamanho_max = None if maximo is None else int(maximo * mb)
        if self.cb_envio.GetValue():
            c.estados_de_envio = self._marcados(self.estados)
        return c

    def problema(self):
        """Por que os campos preenchidos nao servem, ou ''."""
        if self.cb_data.GetValue():
            for campo, nome in ((self.data_de, "De"), (self.data_ate, "Até")):
                texto = campo.GetValue().strip()
                if texto and busca.ler_data(texto) is None:
                    return ("A data \"%s\" não é válida. Escreva dia/mês/ano, "
                            "por exemplo 27/10/2026." % texto)
        for caixa, campos, nome in (
                (self.cb_duracao, (self.seg_min, self.seg_max),
                 "A duração"),
                (self.cb_tamanho, (self.tam_min, self.tam_max),
                 "O tamanho")):
            if caixa.GetValue():
                for campo in campos:
                    texto = campo.GetValue().strip()
                    if texto and busca.ler_numero(texto) is None:
                        return "%s \"%s\" não é um número." % (nome, texto)
        for caixa, lista, nome in (
                (self.cb_servico, self.servicos, "serviço"),
                (self.cb_conta, self.lista_contas, "conta"),
                (self.cb_tipo_conv, self.tipos_conv, "tipo de conversa"),
                (self.cb_situacao, self.situacoes, "situação da conversa"),
                (self.cb_tipo_msg, self.tipos_msg, "tipo de mensagem"),
                (self.cb_carac, self.caracteristicas, "característica"),
                (self.cb_envio, self.estados, "estado do envio")):
            if caixa.GetValue() and not self._marcados(lista):
                return ("Marque ao menos um item em %s, ou desmarque o "
                        "critério." % nome)
        return ""

    def aplicar(self, c):
        """Poe nos campos os criterios de `c` (a busca anterior)."""
        def ligar(caixa, ligado, controles):
            caixa.SetValue(bool(ligado))
            for x in controles:
                x.Enable(bool(ligado))

        def marcar(lista, valores):
            for i, v in enumerate(lista.valores):
                lista.Check(i, v in valores)

        ligar(self.cb_termo, c.termo.strip(), (self.termo, self.frase))
        self.termo.SetValue(c.termo)
        self.frase.SetValue(c.frase_exata)
        for caixa, lista, valores in (
                (self.cb_servico, self.servicos, c.servicos),
                (self.cb_conta, self.lista_contas, c.contas),
                (self.cb_tipo_conv, self.tipos_conv, c.tipos_de_conversa),
                (self.cb_situacao, self.situacoes, c.situacoes),
                (self.cb_tipo_msg, self.tipos_msg, c.tipos_de_mensagem),
                (self.cb_carac, self.caracteristicas, c.caracteristicas),
                (self.cb_envio, self.estados, c.estados_de_envio)):
            ligar(caixa, valores, (lista,))
            marcar(lista, valores)
        ligar(self.cb_nome_conv, c.conversa_contem.strip(), (self.nome_conv,))
        self.nome_conv.SetValue(c.conversa_contem)
        ligar(self.cb_quem, c.minha is not None, (self.quem,))
        self.quem.SetSelection(0 if c.minha is not False else 1)
        ligar(self.cb_autor, c.autor_contem.strip(), (self.autor,))
        self.autor.SetValue(c.autor_contem)
        ligar(self.cb_data, c.data_de is not None or c.data_ate is not None,
              (self.data_de, self.data_ate))
        self.ordem.SetSelection(1 if c.mais_antigas_primeiro else 0)

    def limpar(self):
        self.aplicar(busca.Criterios())
        for campo in (self.data_de, self.data_ate, self.seg_min, self.seg_max,
                      self.tam_min, self.tam_max):
            campo.SetValue("")
        for caixa in (self.cb_duracao, self.cb_tamanho):
            caixa.SetValue(False)
        for campo in (self.seg_min, self.seg_max, self.tam_min, self.tam_max):
            campo.Enable(False)
        self.achados = []
        self.lista.Set([])
        self.b_ver.Enable(False)
        self.rotulo_resultados.SetLabel("Resultados: ainda não buscou.")
        self.falar("Critérios limpos.")
        self.cb_termo.SetFocus()

    # ------------------------------------------------------- busca
    def buscar(self):
        erro = self.problema()
        if erro:
            self.falar(erro)
            wx.MessageBox(erro, "Busca por critérios", wx.OK | wx.ICON_WARNING,
                          self)
            return
        c = self.coletar()
        self.criterios = c
        if c.vazio():
            self.falar("Marque ao menos um critério para buscar.")
            return
        self.achados = busca.buscar(self.banco, c)
        nomes = dict(self.contas)
        self.lista.Set([a.texto_da_lista(lambda cid: nomes.get(cid, cid))
                        for a in self.achados])
        n = len(self.achados)
        if n == 0:
            texto = "Nada encontrado."
        else:
            texto = "%d %s%s." % (
                n, "resultado" if n == 1 else "resultados",
                " (o máximo; refine a busca)" if n >= c.limite else "")
            self.lista.SetSelection(0)
        self.rotulo_resultados.SetLabel("Resultados: " + texto)
        self.b_ver.Enable(n > 0)
        self.falar(texto)
        if n:
            self.lista.SetFocus()

    def _escolhido(self):
        i = self.lista.GetSelection()
        return self.achados[i] if 0 <= i < len(self.achados) else None

    def _tecla_da_lista(self, evt):
        if evt.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and \
                not (evt.AltDown() or evt.ControlDown() or evt.ShiftDown()):
            self._ver()
            return
        evt.Skip()

    def _ver(self):
        achado = self._escolhido()
        if achado is None:
            self.falar("Escolha um resultado.")
            return
        self.escolhido = achado
        self.EndModal(wx.ID_OK)

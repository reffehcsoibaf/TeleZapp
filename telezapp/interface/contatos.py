# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Agenda de contatos do TeleZapp: ver, adicionar, editar e remover.

Os contatos ficam so no TeleZapp (nao vao para o celular nem para a conta).
O nome dado aqui vale nas conversas, nos autores e nas mencoes. A janela so
desenha: quem guarda e o banco, e quem renomeia as conversas e quem chama
(`ao_mudar`).
"""
import threading

import wx

from telezapp.interface import colagem
from telezapp.nucleo import modelos as m

TELEFONE_DE_TESTE = "+5500000000000"


def rotulo_contato(c, servico, conta):
    """'Nome, +telefone, WhatsApp (conta)'."""
    _, _, nome, telefone = c
    partes = [nome] + ([telefone] if telefone else [])
    return "%s, %s (%s)" % (", ".join(partes), servico, conta)


def avisar_conta(prov, conversa_id, nome, telefone, falar):
    """Conta ao servico o nome dado a um contato (em segundo plano), para a
    conta reconhecer a pessoa. So fala se o servico aceitou ou se tentou e
    nao deu; provedor que nao sabe fazer isso nao diz nada."""
    if prov is None or not hasattr(prov, "salvar_contato"):
        return

    def enviar():
        try:
            ok = bool(prov.salvar_contato(conversa_id, nome, telefone))
        except Exception:
            ok = False
        if ok:
            wx.CallAfter(falar, "Contato %s salvo também na conta." % nome)
        elif getattr(prov, "ACEITA_CONTATOS", False):
            wx.CallAfter(falar, "Não consegui avisar a conta. O nome ficou "
                                "só no TeleZapp.")
    threading.Thread(target=enviar, daemon=True,
                     name="avisar-contato").start()


class DialogoContato(wx.Dialog):
    """Conta (so ao adicionar), nome e telefone de um contato."""

    def __init__(self, pai, titulo, contas, nome="", telefone="",
                 travar_conta=False, pedir_telefone=True):
        """contas: [(conta_id, rotulo)]."""
        super().__init__(pai, title=titulo, style=wx.DEFAULT_DIALOG_STYLE)
        self.contas = contas
        lay = wx.BoxSizer(wx.VERTICAL)

        def campo(rotulo, criar, expandir=0):
            # o rotulo nasce ANTES do controle: o leitor de tela usa o texto
            # que vem logo antes do controle como o nome dele
            lay.Add(wx.StaticText(self, label=rotulo), 0,
                    wx.LEFT | wx.RIGHT | wx.TOP, 10)
            ctrl = criar()
            lay.Add(ctrl, expandir, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
            return ctrl
        self.conta = campo("Conta", lambda: wx.Choice(
            self, choices=[r for _, r in contas], name="Conta"))
        self.conta.SetSelection(0)
        if travar_conta or len(contas) == 1:
            self.conta.Enable(False)
        self.nome = campo("Nome", lambda: wx.TextCtrl(
            self, value=nome, name="Nome", size=(380, -1)))
        self.telefone = None
        if pedir_telefone:
            self.telefone = campo(
                "Telefone com DDD (opcional ao editar)",
                lambda: wx.TextCtrl(self, value=telefone,
                                    name="Telefone com DDD",
                                    size=(380, -1)))
        lay.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0,
                wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.CentreOnParent()
        self.nome.SetFocus()

    def escolhido(self):
        """(conta_id, nome, telefone digitado)."""
        i = max(self.conta.GetSelection(), 0)
        tel = self.telefone.GetValue().strip() if self.telefone else ""
        return self.contas[i][0], self.nome.GetValue().strip(), tel


class GerenciadorContatos(wx.Dialog):
    """Lista de contatos com Adicionar, Editar, Remover e Trazer."""

    def __init__(self, pai, banco, contas, ao_mudar, falar):
        """contas: objeto com .lista() -> [(conta_id, servico, nome)] e
        .provedor(conta_id); ao_mudar(): chamado depois de cada mudanca."""
        super().__init__(pai, title="Contatos",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.banco, self.contas = banco, contas
        self.ao_mudar, self.falar = ao_mudar, falar
        self._itens = []
        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(wx.StaticText(
            self, label="Contatos do TeleZapp. O nome vale nas conversas, "
                        "autores e menções, só neste computador."), 0,
                wx.ALL, 10)
        self.lista = wx.ListBox(self, name="Contatos", size=(520, 260))
        lay.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        linha = wx.BoxSizer(wx.HORIZONTAL)
        self.botoes = {}
        for chave, rotulo in (("add", "&Adicionar..."),
                              ("editar", "&Editar..."),
                              ("remover", "&Remover"),
                              ("trazer", "&Trazer das contas")):
            b = wx.Button(self, label=rotulo)
            self.botoes[chave] = b
            linha.Add(b, 0, wx.RIGHT, 6)
        fechar = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        linha.Add(fechar, 0)
        lay.Add(linha, 0, wx.ALL, 10)
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.CentreOnParent()
        self.botoes["add"].Bind(wx.EVT_BUTTON, lambda e: self._adicionar())
        self.botoes["editar"].Bind(wx.EVT_BUTTON, lambda e: self._editar())
        self.botoes["remover"].Bind(wx.EVT_BUTTON, lambda e: self._remover())
        self.botoes["trazer"].Bind(wx.EVT_BUTTON, lambda e: self._trazer())
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._editar())
        self._preencher()
        self.lista.SetFocus()

    # ------------------------------------------------------------ lista
    def _contas_por_id(self):
        return {c: (s, n) for c, s, n in self.contas.lista()}

    def _preencher(self, escolher=None):
        por_id = self._contas_por_id()
        self._itens = [c for c in self.banco.contatos() if c[0] in por_id]
        self.lista.Set([
            rotulo_contato(c, m.SERVICOS.get(por_id[c[0]][0], ""),
                           por_id[c[0]][1]) for c in self._itens]
            or ["Nenhum contato ainda"])
        if self._itens:
            i = 0
            if escolher:
                for k, c in enumerate(self._itens):
                    if (c[0], c[1]) == escolher:
                        i = k
            self.lista.SetSelection(i)

    def _selecionado(self):
        i = self.lista.GetSelection()
        return self._itens[i] if 0 <= i < len(self._itens) else None

    # --------------------------------------------------------- acoes
    def _contas_que_aceitam_telefone(self):
        achadas = []
        for conta_id, servico, nome in self.contas.lista():
            prov = self.contas.provedor(conta_id)
            if prov is not None and prov.id_do_telefone(TELEFONE_DE_TESTE):
                achadas.append((conta_id, "%s (%s)" % (
                    m.SERVICOS.get(servico, servico), nome)))
        return achadas

    def _adicionar(self):
        contas = self._contas_que_aceitam_telefone()
        if not contas:
            wx.MessageBox(
                "Adicionar por telefone só funciona no WhatsApp. Para um "
                "contato do Telegram, abra a conversa com a pessoa e use "
                "Menu, Contatos, Salvar a pessoa desta conversa.",
                "Contatos", wx.OK | wx.ICON_INFORMATION, self)
            return
        dlg = DialogoContato(self, "Adicionar contato", contas)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            conta_id, nome, tel = dlg.escolhido()
        finally:
            dlg.Destroy()
        telefone = m.normalizar_telefone(tel)
        if not nome or not telefone:
            wx.MessageBox("Informe o nome e um telefone válido, com DDD.",
                          "Contatos", wx.OK | wx.ICON_WARNING, self)
            return
        id_ = self.contas.provedor(conta_id).id_do_telefone(telefone)
        self.banco.salvar_contato(conta_id, id_, nome, telefone)
        self._mudou((conta_id, id_), "Contato %s adicionado." % nome)
        avisar_conta(self.contas.provedor(conta_id), id_, nome, telefone,
                     self.falar)

    def _editar(self):
        c = self._selecionado()
        if c is None:
            return
        por_id = self._contas_por_id()
        servico, conta_nome = por_id[c[0]]
        dlg = DialogoContato(
            self, "Editar contato",
            [(c[0], "%s (%s)" % (m.SERVICOS.get(servico, servico),
                                  conta_nome))],
            nome=c[2], telefone=c[3], travar_conta=True)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            _, nome, tel = dlg.escolhido()
        finally:
            dlg.Destroy()
        if not nome:
            wx.MessageBox("O nome não pode ficar vazio.", "Contatos",
                          wx.OK | wx.ICON_WARNING, self)
            return
        telefone = m.normalizar_telefone(tel) or c[3]
        self.banco.salvar_contato(c[0], c[1], nome, telefone)
        self._mudou((c[0], c[1]), "Contato %s salvo." % nome)
        avisar_conta(self.contas.provedor(c[0]), c[1], nome, telefone,
                     self.falar)

    def _remover(self):
        c = self._selecionado()
        if c is None:
            return
        if wx.MessageBox("Remover %s dos contatos do TeleZapp? A pessoa "
                         "continua na conta; só o nome dado aqui some."
                         % c[2], "Contatos",
                         wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
                         self) != wx.YES:
            return
        self.banco.remover_contato(c[0], c[1])
        self._mudou(None, "Contato %s removido." % c[2])

    def _trazer(self):
        """Copia para a agenda os contatos que a conta do WhatsApp ja tem
        (sem trocar os que a pessoa ja nomeou aqui)."""
        novos = 0
        for conta_id, servico, _ in self.contas.lista():
            prov = self.contas.provedor(conta_id)
            if prov is None:
                continue
            try:
                contatos = prov.contatos_da_conta()
            except Exception:
                continue
            ja = {(c[0], c[1]) for c in self.banco.contatos(conta_id)}
            for id_, nome, tel in contatos:
                if (conta_id, id_) not in ja:
                    self.banco.salvar_contato(conta_id, id_, nome, tel)
                    novos += 1
        self._mudou(None, "%d contatos trazidos." % novos if novos
                    else "Nenhum contato novo para trazer.")

    def _mudou(self, escolher, aviso):
        self._preencher(escolher)
        self.ao_mudar()
        self.falar(aviso)
        self.lista.SetFocus()


def dialogo_salvar_pessoa(pai, contas, nome, telefone=""):
    """Pergunta nome e telefone ao salvar a pessoa de uma conversa; devolve
    (nome, telefone) ou None."""
    dlg = DialogoContato(pai, "Salvar contato", contas, nome=nome,
                         telefone=telefone, travar_conta=True)
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return None
        _, nome, tel = dlg.escolhido()
    finally:
        dlg.Destroy()
    return (nome, m.normalizar_telefone(tel) or "") if nome else None


class DialogoNovaMensagem(wx.Dialog):
    """Conta (so se houver mais de uma), destinatario e texto. Abaixo do
    campo Para, uma lista com os contatos e conversas que casam com o que
    foi digitado (vazio = todos)."""

    LIMITE_LISTA = 200

    def __init__(self, pai, contas, buscar):
        """contas: [(conta_id, rotulo)] das contas conectadas; buscar(
        conta_id, texto) -> [(id, nome, telefone)]."""
        super().__init__(pai, title="Nova mensagem",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.contas, self.buscar = contas, buscar
        self._achados = []
        lay = wx.BoxSizer(wx.VERTICAL)

        def campo(rotulo, criar, expandir=0):
            # o rotulo nasce ANTES do controle: o leitor de tela usa o texto
            # que vem logo antes do controle como o nome dele
            lay.Add(wx.StaticText(self, label=rotulo), 0,
                    wx.LEFT | wx.RIGHT | wx.TOP, 10)
            ctrl = criar()
            lay.Add(ctrl, expandir, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
            return ctrl
        self.conta = None
        if len(contas) > 1:
            self.conta = campo("Enviar pela conta", lambda: wx.Choice(
                self, choices=[r for _, r in contas],
                name="Enviar pela conta"))
            self.conta.SetSelection(0)
            self.conta.Bind(wx.EVT_CHOICE, lambda e: self._atualizar())
        self.para = campo(
            "Para (digite para buscar nos contatos e conversas, ou um "
            "número com DDD ou @usuário)",
            lambda: wx.TextCtrl(self, name="Para", size=(420, -1),
                                style=wx.TE_PROCESS_ENTER))
        self.para.Bind(wx.EVT_TEXT, lambda e: self._atualizar())
        self.para.Bind(wx.EVT_TEXT_ENTER, lambda e: self._ir_para_lista())
        self.lista = campo(
            "Contatos encontrados (Enter escolhe)",
            lambda: wx.ListBox(self, name="Contatos encontrados",
                               size=(420, 120)), 1)
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._escolher())
        self.anexos = []          # midias coladas em Mensagem
        self.rot_texto = wx.StaticText(self, label="Mensagem")
        lay.Add(self.rot_texto, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.texto = wx.TextCtrl(self, name="Mensagem", size=(420, 100),
                                 style=wx.TE_MULTILINE)
        lay.Add(self.texto, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.fala = getattr(pai, "fala", None)
        self.texto.Bind(wx.EVT_TEXT_PASTE, self._ao_colar)
        self.texto.Bind(wx.EVT_CHAR_HOOK, self._tecla_texto)
        botoes = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        lay.Add(botoes, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.CentreOnParent()
        self._atualizar()
        self.para.SetFocus()

    def _rotular_texto(self):
        self.rot_texto.SetLabel("Mensagem" if not self.anexos else
                                "Mensagem. %s, o texto vira legenda" %
                                colagem.descricao(self.anexos))

    def _ao_colar(self, evt):
        if self.fala is None:
            evt.Skip()
            return
        colagem.colar(evt, self.fala, self.anexos, self._rotular_texto)

    def _tecla_texto(self, evt):
        """Esc com midia colada remove a midia, em vez de fechar o dialogo."""
        if evt.GetKeyCode() == wx.WXK_ESCAPE and self.anexos:
            colagem.descartar(self.anexos)
            self._rotular_texto()
            if self.fala is not None:
                self.fala.falar("Mídia colada removida.")
            return
        evt.Skip()

    def _conta_id(self):
        i = max(self.conta.GetSelection(), 0) if self.conta else 0
        return self.contas[i][0]

    def _atualizar(self):
        self._achados = self.buscar(
            self._conta_id(), self.para.GetValue())[:self.LIMITE_LISTA]
        from telezapp.nucleo import nova_mensagem as nm
        self.lista.Set([nm.rotulo(n, t) for _, n, t in self._achados]
                       or ["Nenhum contato encontrado"])

    def _selecionado(self):
        i = self.lista.GetSelection()
        return self._achados[i] if 0 <= i < len(self._achados) else None

    def _ir_para_lista(self):
        if self._achados:
            self.lista.SetSelection(0)
            self.lista.SetFocus()

    def _escolher(self):
        """Enter ou duplo clique na lista: vai para a mensagem."""
        if self._selecionado() is not None:
            self.texto.SetFocus()

    def escolhido(self):
        """(conta_id, destino, texto, pessoa, anexos): pessoa e (id, nome)
        da lista, se uma foi escolhida, senao None (vale o texto de Para);
        anexos, as midias coladas."""
        sel = self._selecionado()
        pessoa = (sel[0], sel[1]) if sel else None
        destino = self.para.GetValue().strip() or (sel[1] if sel else "")
        return (self._conta_id(), destino, self.texto.GetValue().strip(),
                pessoa, list(self.anexos))


def dialogo_nova_mensagem(pai, contas, buscar):
    """(conta_id, destino, texto, pessoa, anexos) ou None se cancelar ou
    deixar sem destino ou sem nada para enviar (texto ou midia colada)."""
    dlg = DialogoNovaMensagem(pai, contas, buscar)
    try:
        if dlg.ShowModal() != wx.ID_OK:
            colagem.descartar(dlg.anexos)
            return None
        conta_id, destino, texto, pessoa, anexos = dlg.escolhido()
    finally:
        dlg.Destroy()
    if (destino or pessoa) and (texto or anexos):
        return conta_id, destino, texto, pessoa, anexos
    colagem.descartar(anexos)
    return None

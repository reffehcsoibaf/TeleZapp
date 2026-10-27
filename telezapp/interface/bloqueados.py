# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Bloquear e desbloquear pessoas, e a lista de quem esta bloqueado.

Quem guarda os bloqueios e o servico (WhatsApp ou Telegram): aqui so se pede
a lista, se bloqueia e se desbloqueia, sempre fora da thread da interface,
porque cada pedido espera a rede.
"""
import logging
import threading

import wx

from telezapp.nucleo import modelos as m
from telezapp.provedores.base import ErroBloqueio

log = logging.getLogger("telezapp.bloqueados")


def rotulo_bloqueado(nome, telefone, servico, conta):
    """'Nome, +telefone, WhatsApp (conta)'."""
    partes = [nome] + ([telefone] if telefone and telefone != nome else [])
    return "%s, %s (%s)" % (", ".join(partes), servico, conta)


def mudar_bloqueio(prov, conversa_id, nome, bloquear, depois):
    """Bloqueia (ou desbloqueia) em segundo plano; `depois(ok, texto)` roda
    na thread da interface."""
    def trabalho():
        try:
            prov.bloquear(conversa_id, bloquear)
            ok = True
            texto = "Contato %s %s." % (
                nome, "bloqueado" if bloquear else "desbloqueado")
        except ErroBloqueio as e:
            ok, texto = False, str(e)
        except Exception:
            log.exception("bloquear ou desbloquear")
            ok = False
            texto = "Não consegui %s." % (
                "bloquear" if bloquear else "desbloquear")
        wx.CallAfter(depois, ok, texto)
    threading.Thread(target=trabalho, daemon=True, name="bloquear").start()


def pergunta_de_bloqueio(nome, bloquear):
    if bloquear:
        return ("Bloquear %s? A pessoa não poderá mais enviar mensagens "
                "nem ligar para você. Dá para desbloquear depois em "
                "Contatos, Contatos bloqueados." % nome)
    return "Desbloquear %s?" % nome


def alternar(pai, prov, conversa_id, nome, falar, depois=lambda: None):
    """Bloqueia a pessoa se ela nao esta bloqueada e desbloqueia se esta,
    depois de perguntar. `falar(texto)` diz o andamento e o resultado;
    `depois()` roda ao fim (com ou sem sucesso)."""
    def terminou(ok, texto):
        falar(texto)
        if not ok:
            wx.MessageBox(texto, "Contatos bloqueados",
                          wx.OK | wx.ICON_WARNING, pai)
        depois()

    def perguntar(ja_bloqueada):
        bloquear = not ja_bloqueada
        if wx.MessageBox(pergunta_de_bloqueio(nome, bloquear),
                         "Contatos bloqueados",
                         wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
                         pai) != wx.YES:
            return
        mudar_bloqueio(prov, conversa_id, nome, bloquear, terminou)

    def ver():
        try:
            ja = prov.esta_bloqueado(conversa_id)
        except ErroBloqueio as e:
            wx.CallAfter(terminou, False, str(e))
            return
        except Exception:
            log.exception("ver se a pessoa esta bloqueada")
            wx.CallAfter(terminou, False,
                         "Não consegui ver se a pessoa está bloqueada.")
            return
        wx.CallAfter(perguntar, ja)
    falar("Verificando se %s está bloqueado." % nome)
    threading.Thread(target=ver, daemon=True, name="ver-bloqueio").start()


def ler_bloqueados(contas):
    """([(conta_id, id, nome, telefone)], [aviso]) de todas as contas que
    bloqueiam pessoas. Espera os servicos."""
    itens, avisos = [], []
    for conta_id, servico, nome_conta in contas.lista():
        prov = contas.provedor(conta_id)
        if prov is None or not getattr(prov, "PODE_BLOQUEAR", False):
            continue
        try:
            for id_, nome, telefone in prov.bloqueados():
                itens.append((conta_id, id_, nome, telefone))
        except ErroBloqueio as e:
            avisos.append("%s (%s): %s" % (
                m.SERVICOS.get(servico, servico), nome_conta, e))
        except Exception:
            log.exception("ler os bloqueados")
            avisos.append("%s (%s): não consegui ler a lista." % (
                m.SERVICOS.get(servico, servico), nome_conta))
    return itens, avisos


class GerenciadorBloqueados(wx.Dialog):
    """Lista de quem esta bloqueado, com Desbloquear, Bloquear e Atualizar."""

    def __init__(self, pai, contas, escolher_pessoa, falar):
        """contas: objeto com .lista() -> [(conta_id, servico, nome)] e
        .provedor(conta_id); escolher_pessoa() -> (conta_id, conversa_id,
        nome) de quem se vai bloquear, ou None se desistir."""
        super().__init__(pai, title="Contatos bloqueados",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.contas, self.escolher_pessoa, self.falar = \
            contas, escolher_pessoa, falar
        self._itens = []
        lay = wx.BoxSizer(wx.VERTICAL)
        self.estado = wx.StaticText(
            self, label="Pessoas que você bloqueou nas suas contas. Elas "
                        "não conseguem enviar mensagens nem ligar.")
        lay.Add(self.estado, 0, wx.ALL, 10)
        lay.Add(wx.StaticText(self, label="Contatos &bloqueados"), 0,
                wx.LEFT | wx.RIGHT, 10)
        self.lista = wx.ListBox(self, name="Contatos bloqueados",
                                size=(520, 260))
        lay.Add(self.lista, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        linha = wx.BoxSizer(wx.HORIZONTAL)
        self.botoes = {}
        for chave, rotulo in (("desbloquear", "&Desbloquear"),
                              ("bloquear", "&Bloquear alguém..."),
                              ("atualizar", "&Atualizar")):
            b = wx.Button(self, label=rotulo)
            self.botoes[chave] = b
            linha.Add(b, 0, wx.RIGHT, 6)
        linha.Add(wx.Button(self, wx.ID_CANCEL, "&Fechar"), 0)
        lay.Add(linha, 0, wx.ALL, 10)
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.CentreOnParent()
        self.botoes["desbloquear"].Bind(
            wx.EVT_BUTTON, lambda e: self._desbloquear())
        self.botoes["bloquear"].Bind(wx.EVT_BUTTON, lambda e: self._bloquear())
        self.botoes["atualizar"].Bind(
            wx.EVT_BUTTON, lambda e: self._carregar())
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._desbloquear())
        self.lista.Set(["Carregando a lista..."])
        self._carregar()
        self.lista.SetFocus()

    # ------------------------------------------------------------ lista
    def _carregar(self, escolher=None):
        """Pede as listas aos servicos em segundo plano."""
        def trabalho():
            itens, avisos = ler_bloqueados(self.contas)
            wx.CallAfter(self._mostrar, itens, avisos, escolher)
        self.lista.Set(["Carregando a lista..."])
        self._itens = []
        threading.Thread(target=trabalho, daemon=True,
                         name="ler-bloqueados").start()

    def _mostrar(self, itens, avisos, escolher=None):
        if not self:
            return
        por_id = {c: (s, n) for c, s, n in self.contas.lista()}
        self._itens = sorted(itens, key=lambda c: (c[2].lower(), c[0]))
        self.lista.Set([
            rotulo_bloqueado(nome, tel, m.SERVICOS.get(
                por_id.get(conta, ("", ""))[0], ""),
                por_id.get(conta, ("", conta))[1])
            for conta, _, nome, tel in self._itens]
            or ["Nenhum contato bloqueado"])
        if self._itens:
            i = 0
            for k, c in enumerate(self._itens):
                if escolher and (c[0], c[1]) == escolher:
                    i = k
            self.lista.SetSelection(i)
        resumo = ("%d contato%s bloqueado%s." % (
            len(self._itens), "" if len(self._itens) == 1 else "s",
            "" if len(self._itens) == 1 else "s")
            if self._itens else "Nenhum contato bloqueado.")
        if avisos:
            resumo += " " + " ".join(avisos)
        self.estado.SetLabel(resumo)
        self.falar(resumo)

    def _selecionado(self):
        i = self.lista.GetSelection()
        return self._itens[i] if 0 <= i < len(self._itens) else None

    # --------------------------------------------------------- acoes
    def _desbloquear(self):
        c = self._selecionado()
        if c is None:
            return
        conta_id, id_, nome, _ = c
        prov = self.contas.provedor(conta_id)
        if prov is None:
            return
        self.falar("Desbloqueando %s." % nome)
        mudar_bloqueio(prov, id_, nome, False, self._mudou)

    def _bloquear(self):
        escolha = self.escolher_pessoa()
        if escolha is None:
            return
        conta_id, id_, nome = escolha
        prov = self.contas.provedor(conta_id)
        if prov is None:
            return
        if wx.MessageBox(pergunta_de_bloqueio(nome, True),
                         "Contatos bloqueados",
                         wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
                         self) != wx.YES:
            return
        self.falar("Bloqueando %s." % nome)
        mudar_bloqueio(prov, id_, nome, True,
                       lambda ok, texto: self._mudou(ok, texto, (conta_id,
                                                                  id_)))

    def _mudou(self, ok, texto, escolher=None):
        if not self:
            return
        if not ok:
            wx.MessageBox(texto, "Contatos bloqueados",
                          wx.OK | wx.ICON_WARNING, self)
            self.falar(texto)
            return
        self._carregar(escolher)
        self.falar(texto)

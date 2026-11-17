# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela de Ajuda, Feedback: relatar um problema, sugerir algo ou tirar uma
duvida sem abrir o navegador, com um botao que ja leva os logs."""
import threading

import wx

from telezapp import NOME
from telezapp.nucleo import relatos

TIPOS = (("Relatar um problema", "problema"), ("Sugerir algo", "sugestao"),
         ("Tirar uma dúvida", "duvida"))
SOBRE_OS_LOGS = (
    "O botão Enviar com os logs já anexa os registros do programa; você não "
    "precisa procurar nenhum arquivo. Eles não guardam o texto das mensagens "
    "e mostram só o fim dos telefones, mas têm nomes de grupos e "
    "identificadores técnicos. Só quem mantém o %s lê o que você envia, e "
    "tudo é apagado depois de 90 dias. A versão do programa vai junto." % NOME)


LOGS_OBRIGATORIOS = ("Para relatar um problema, os logs são obrigatórios: "
                     "use Enviar com os logs.")


class DialogoRelato(wx.Dialog):
    def __init__(self, pai, nome="", contato="", falar=None, via=""):
        super().__init__(pai, title="Feedback do %s" % NOME, size=(620, 620),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._falar = falar or (lambda texto: None)
        self._enviando = False
        lay = wx.BoxSizer(wx.VERTICAL)

        rotulo = "O que você quer fazer?"
        lay.Add(wx.StaticText(self, label=rotulo), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.tipo = wx.Choice(self, choices=[t[0] for t in TIPOS], name=rotulo)
        self.tipo.SetSelection(0)
        lay.Add(self.tipo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        self.tipo.Bind(wx.EVT_CHOICE, lambda e: self._ao_trocar_tipo(True))

        def texto(rotulo, valor="", estilo=0):
            lay.Add(wx.StaticText(self, label=rotulo), 0,
                    wx.LEFT | wx.RIGHT | wx.TOP, 8)
            controle = wx.TextCtrl(self, value=valor, name=rotulo, style=estilo)
            lay.Add(controle, 1 if estilo else 0,
                    wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
            return controle

        self.nome = texto("Seu nome", nome)
        rotulo_via = "Retorno via"
        lay.Add(wx.StaticText(self, label=rotulo_via), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.via = wx.Choice(self, choices=[r for _, r in relatos.VIAS],
                             name=rotulo_via)
        chaves = [c for c, _ in relatos.VIAS]
        via = via if via in chaves else relatos.via_de(contato)
        self.via.SetSelection(chaves.index(via))
        lay.Add(self.via, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        self.rotulo_contato = wx.StaticText(self, label="")
        lay.Add(self.rotulo_contato, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.contato = wx.TextCtrl(self, value=contato, name="Contato")
        lay.Add(self.contato, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        self.via.Bind(wx.EVT_CHOICE, lambda e: self._ao_trocar_via())
        self._ao_trocar_via()
        self.descricao = texto(
            "Descrição (opcional com os logs): o que você fez, o que esperava "
            "e o que aconteceu", estilo=wx.TE_MULTILINE)
        self.quando = texto("Quando aconteceu? Dia e hora aproximados")
        self.sobre = texto("Sobre os logs", SOBRE_OS_LOGS,
                           wx.TE_MULTILINE | wx.TE_READONLY)

        linha = wx.BoxSizer(wx.HORIZONTAL)
        self.com_logs = wx.Button(self, label="Enviar &com os logs")
        self.sem_logs = wx.Button(self, label="Enviar &sem os logs")
        self.fechar = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        self.com_logs.Bind(wx.EVT_BUTTON, lambda e: self._enviar(True))
        self.sem_logs.Bind(wx.EVT_BUTTON, lambda e: self._enviar(False))
        for botao in (self.com_logs, self.sem_logs, self.fechar):
            linha.Add(botao, 0, wx.RIGHT, 8)
        lay.Add(linha, 0, wx.ALL | wx.ALIGN_RIGHT, 8)
        self._ao_trocar_tipo(False)
        self.SetSizer(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.Bind(wx.EVT_BUTTON, self._ao_fechar, self.fechar)
        self.Bind(wx.EVT_CLOSE, self._ao_fechar)
        self.tipo.SetFocus()
        self.CentreOnParent()

    def _tipo(self):
        return TIPOS[max(self.tipo.GetSelection(), 0)][1]

    def _ao_trocar_tipo(self, falar):
        """Relato de problema so sai com os logs: o botao sem logs fica
        desligado (o Tab passa direto) e a janela diz por que."""
        obrigatorio = relatos.logs_obrigatorios(self._tipo())
        self.sem_logs.Enable(not obrigatorio)
        self.sobre.SetValue(SOBRE_OS_LOGS + (" " + LOGS_OBRIGATORIOS
                                             if obrigatorio else ""))
        if falar and obrigatorio:
            self._falar(LOGS_OBRIGATORIOS)

    def _via(self):
        return relatos.VIAS[max(self.via.GetSelection(), 0)][0]

    def _ao_trocar_via(self):
        self.rotulo_contato.SetLabel(
            relatos.DICAS[self._via()] + " (obrigatório)")
        self.Layout()

    def _ao_fechar(self, evento):
        if not self._enviando:
            self.EndModal(wx.ID_CANCEL)

    def _botoes(self, ativos):
        for botao in (self.com_logs, self.sem_logs, self.fechar):
            botao.Enable(ativos)
        if ativos:
            self._ao_trocar_tipo(False)

    def _enviar(self, com_logs):
        if self._enviando:
            return
        if not com_logs and relatos.logs_obrigatorios(self._tipo()):
            self._avisar(LOGS_OBRIGATORIOS, wx.ICON_WARNING)
            return
        faltou = relatos.falta(self.contato.GetValue(),
                               self.descricao.GetValue(), com_logs)
        if faltou:
            frase, controle = {
                "contato": ("Escreva como falar com você.", self.contato),
                "descricao": ("Escreva a descrição, ou envie com os logs.",
                              self.descricao)}[faltou]
            self._avisar(frase, wx.ICON_WARNING)
            controle.SetFocus()
            return
        contato, erro = relatos.contato_de(self._via(),
                                           self.contato.GetValue())
        if erro:
            self._avisar(erro, wx.ICON_WARNING)
            self.contato.SetFocus()
            return
        dados = (self._tipo(), self.nome.GetValue(),
                 contato, self.descricao.GetValue(),
                 self.quando.GetValue(), com_logs)
        self._enviando = True
        self._botoes(False)
        self._falar("Enviando.")

        def trabalho():
            try:
                relatos.enviar(*dados)
                erro = ""
            except relatos.ErroRelato as e:
                erro = str(e)
            except Exception:
                relatos.log.exception("enviar o relato")
                erro = "Não consegui enviar o relato."
            wx.CallAfter(self._terminou, erro)
        threading.Thread(target=trabalho, daemon=True,
                         name="enviar-relato").start()

    def _terminou(self, erro):
        self._enviando = False
        self._botoes(True)
        if erro:
            # o que a pessoa escreveu continua na janela
            self._avisar(erro, wx.ICON_WARNING)
            self.com_logs.SetFocus()
            return
        self._avisar("Enviado. Obrigado! A resposta vai pela forma de contato "
                     "que você escreveu.", wx.ICON_INFORMATION)
        self.EndModal(wx.ID_OK)

    def _avisar(self, texto, icone):
        self._falar(texto)
        wx.MessageBox(texto, "Feedback do %s" % NOME, wx.OK | icone, self)


def mostrar_relato(pai, cfg, falar=None):
    """Abre a janela; quem enviou nao precisa escrever nome e contato de novo."""
    dlg = DialogoRelato(pai, cfg.get("relato_nome") or "",
                        cfg.get("relato_contato") or "", falar,
                        cfg.get("relato_via") or "")
    try:
        if dlg.ShowModal() == wx.ID_OK:
            cfg.set("relato_nome", dlg.nome.GetValue().strip())
            cfg.set("relato_contato", dlg.contato.GetValue().strip())
            cfg.set("relato_via", dlg._via())
    finally:
        dlg.Destroy()

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela para instalar o TeleZapp ou criar uma copia portatil. Quem faz o
trabalho e `nucleo.instalacao`."""
import contextlib
import os
import threading
import traceback

import wx

from telezapp import NOME, VERSAO, config
from telezapp.interface.progresso import JanelaDeProgresso
from telezapp.nucleo import copia_oficial
from telezapp.nucleo import instalacao as ins


class DialogoInstalacao(wx.Dialog):
    """Escolhe a pasta e as opcoes. `instalar`: True para instalar, False para
    criar a copia portatil. `levar_dados`: texto da caixa de dados (None se
    nao ha dados para levar)."""

    def __init__(self, pai, instalar, pasta_inicial, levar_dados=None):
        titulo = ("Instalar o %s" % NOME if instalar else
                  "Criar cópia portátil do %s" % NOME)
        super().__init__(pai, title=titulo, style=wx.DEFAULT_DIALOG_STYLE)
        self.instalar = instalar
        lay = wx.BoxSizer(wx.VERTICAL)
        if instalar:
            explicacao = (
                "O programa será copiado para a pasta abaixo, sem precisar "
                "de administrador, e aparecerá em Aplicativos instalados "
                "para ser desinstalado.")
            rotulo = "Pasta de instalação"
        else:
            explicacao = (
                "Será criada uma pasta %s dentro do lugar escolhido, com o "
                "programa e a pasta dados ao lado do executável: pode ser "
                "levada num pendrive e não mexe nos dados deste "
                "computador." % NOME)
            rotulo = "Criar dentro da pasta"
        texto = wx.StaticText(self, label=explicacao)
        texto.Wrap(460)
        lay.Add(texto, 0, wx.ALL, 10)
        lay.Add(wx.StaticText(self, label=rotulo), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        linha = wx.BoxSizer(wx.HORIZONTAL)
        self.pasta = wx.TextCtrl(self, value=pasta_inicial, name=rotulo,
                                 size=(360, -1))
        procurar = wx.Button(self, label="&Procurar...")
        linha.Add(self.pasta, 1, wx.RIGHT, 6)
        linha.Add(procurar)
        lay.Add(linha, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.atalho_menu = self.atalho_area = self.dados = self.abrir = None
        if instalar:
            self.atalho_menu = wx.CheckBox(
                self, label="Atalho no menu &Iniciar")
            self.atalho_menu.SetValue(True)
            self.atalho_area = wx.CheckBox(
                self, label="Atalho na área de &trabalho")
            for c in (self.atalho_menu, self.atalho_area):
                lay.Add(c, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        if levar_dados:
            self.dados = wx.CheckBox(self, label=levar_dados)
            self.dados.SetValue(True if instalar else False)
            lay.Add(self.dados, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        if instalar:
            self.abrir = wx.CheckBox(
                self, label="&Abrir o %s instalado ao terminar" % NOME)
            self.abrir.SetValue(True)
            lay.Add(self.abrir, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        botoes = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        lay.Add(botoes, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.FindWindowById(wx.ID_OK).SetLabel(
            "&Instalar" if instalar else "&Criar")
        self.SetSizerAndFit(lay)
        self.Bind(wx.EVT_BUTTON, self._procurar, procurar)
        self.Bind(wx.EVT_BUTTON, self._ok, id=wx.ID_OK)
        self.CentreOnParent()
        self.pasta.SetFocus()

    def _procurar(self, evt):
        dlg = wx.DirDialog(self, "Escolha a pasta",
                           defaultPath=self.pasta.GetValue())
        try:
            if dlg.ShowModal() == wx.ID_OK:
                self.pasta.SetValue(dlg.GetPath())
        finally:
            dlg.Destroy()

    def _ok(self, evt):
        if not self.pasta.GetValue().strip():
            wx.MessageBox("Escolha a pasta.", self.GetTitle(),
                          wx.OK | wx.ICON_WARNING, self)
            return
        if self.dados is not None and self.dados.GetValue() and \
                not self.instalar:
            r = wx.MessageBox(
                "A cópia vai levar as sessões das suas contas, que dão "
                "acesso a elas. Guarde-a com cuidado. Continuar?",
                self.GetTitle(),
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self)
            if r != wx.YES:
                return
        evt.Skip()

    def resultado(self):
        return {
            "pasta": self.pasta.GetValue().strip(),
            "atalho_menu": bool(self.atalho_menu and
                                self.atalho_menu.GetValue()),
            "atalho_area": bool(self.atalho_area and
                                self.atalho_area.GetValue()),
            "dados": bool(self.dados and self.dados.GetValue()),
            "abrir": bool(self.abrir and self.abrir.GetValue()),
        }


import logging

log = logging.getLogger("telezapp.instalacao")


def com_espera(pai, titulo, trabalho):
    """Roda `trabalho(progresso)` numa thread, com uma janela de barra de
    progresso aberta (o NVDA toca os bipes da barra). `progresso(pct, texto)`:
    pct de 0 a 100, ou None quando nao se sabe quanto falta. Devolve
    (resultado, erro): erro e o texto da excecao, se houve."""
    saida = {}
    estado = {"pct": None, "texto": ""}

    def progresso(pct, texto=""):
        estado["pct"], estado["texto"] = pct, texto or estado["texto"]

    def corpo():
        try:
            saida["r"] = trabalho(progresso)
        except Exception as e:
            log.error("%s:\n%s", titulo, traceback.format_exc())
            saida["e"] = str(e) or e.__class__.__name__
    th = threading.Thread(target=corpo, daemon=True, name="instalacao")
    th.start()
    barra = JanelaDeProgresso(pai, titulo, "Aguarde...")
    barra.mostrar()
    try:
        while th.is_alive():
            barra.atualizar(estado["pct"], estado["texto"] or None)
            wx.MilliSleep(100)
            wx.YieldIfNeeded()
        if "e" not in saida:
            barra.atualizar(100)
    finally:
        barra.fechar()
    return saida.get("r"), saida.get("e")


def _fonte_padrao(progresso=None):
    """A pasta do proprio programa em execucao."""
    return contextlib.nullcontext(ins.pasta_do_programa())


def fluxo_instalar(pai, fonte=None):
    """Pergunta, instala e conta o resultado. Devolve (exe, abrir) ou None.
    `fonte()`: gerenciador de contexto que entrega a pasta do programa a
    instalar (o instalador de um arquivo so extrai o zip embutido)."""
    portatil = ins.dados_portateis() if fonte is None else None
    fonte = fonte or _fonte_padrao
    dlg = DialogoInstalacao(
        pai, True, ins.pasta_de_instalacao_padrao(),
        "Levar os dados desta cópia (contas, conversas e mídias) para o "
        "computador" if portatil else None)
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return None
        r = dlg.resultado()
    finally:
        dlg.Destroy()
    def trabalho(progresso):
        # o instalador de um arquivo so primeiro extrai o zip embutido (40%)
        extrai = fonte is not _fonte_padrao
        with fonte(ins.faixa(progresso, 0, 40) if extrai else None) \
                as programa:
            return ins.instalar(
                programa, r["pasta"], r["atalho_menu"], r["atalho_area"],
                portatil if r["dados"] else None,
                progresso=ins.faixa(progresso, 40, 100) if extrai
                else progresso)
    res, erro = com_espera(pai, "Instalando o %s" % NOME, trabalho)
    if erro:
        wx.MessageBox("Não consegui instalar: %s" % erro, NOME,
                      wx.OK | wx.ICON_WARNING, pai)
        return None
    exe, avisos = res
    texto = "O %s foi instalado em %s." % (NOME, os.path.dirname(exe))
    if avisos:
        texto += "\n\n" + "\n".join(avisos)
    wx.MessageBox(texto, NOME, wx.OK | wx.ICON_INFORMATION, pai)
    return exe, r["abrir"]


def fluxo_criar_portatil(pai, pasta_inicial, fonte=None):
    """Pergunta, cria a copia portatil e conta o resultado. Devolve a pasta
    criada ou None. `fonte`: como em fluxo_instalar."""
    dlg = DialogoInstalacao(
        pai, False, pasta_inicial,
        "Levar os meus dados (contas, conversas e mídias) para a cópia"
        if fonte is None else None)
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return None
        r = dlg.resultado()
    finally:
        dlg.Destroy()
    dados = config.pasta_dados()
    fonte = fonte or _fonte_padrao

    def trabalho(progresso):
        extrai = fonte is not _fonte_padrao
        with fonte(ins.faixa(progresso, 0, 40) if extrai else None) \
                as programa:
            return ins.criar_portatil(
                programa, r["pasta"], dados if r["dados"] else None,
                progresso=ins.faixa(progresso, 40, 100) if extrai
                else progresso)
    alvo, erro = com_espera(pai, "Criando a cópia portátil", trabalho)
    if erro:
        wx.MessageBox("Não consegui criar a cópia: %s" % erro, NOME,
                      wx.OK | wx.ICON_WARNING, pai)
        return None
    wx.MessageBox("Cópia portátil criada em %s." % alvo, NOME,
                  wx.OK | wx.ICON_INFORMATION, pai)
    return alvo


TEXTO_DE_BOAS_VINDAS = (
    "O %s é um aplicativo para conversar pelo WhatsApp e pelo Telegram na "
    "mesma janela, feito para quem usa leitor de tela: mensagens, mídias, "
    "chamadas, status e histórias, várias contas e inteligência artificial "
    "opcional para transcrever e descrever.\n\n"
    "Versão %s. Software experimental: use por sua conta e risco. Não é um "
    "produto oficial do WhatsApp nem do Telegram.\n\n"
    "Instalar copia o programa para este computador e cria os atalhos. Uma "
    "cópia portátil leva o programa e os seus dados numa pasta, por exemplo "
    "para um pendrive. Você também pode usar sem instalar." % (NOME, VERSAO))


class DialogoBoasVindas(wx.Dialog):
    """Primeira tela de uma copia que ainda nao foi instalada."""

    def __init__(self, fonte=None):
        """`fonte`: so no instalador de um arquivo (ver fluxo_instalar); nele
        nao ha "usar sem instalar"."""
        super().__init__(None, title="Bem-vindo ao %s" % NOME,
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.fonte = fonte
        self.escolha = "fechar"
        self.exe_instalado = None
        self.abrir = False
        lay = wx.BoxSizer(wx.VERTICAL)
        texto = wx.StaticText(self, label=(
            TEXTO_DE_BOAS_VINDAS if fonte is None else
            TEXTO_DE_BOAS_VINDAS.replace(" Você também pode usar sem "
                                         "instalar.", ""))
            + "\n\n" + copia_oficial.AVISO_CANAIS)
        texto.Wrap(460)
        lay.Add(texto, 0, wx.ALL, 12)
        self.botoes = {}
        for chave, rotulo in (
                ("instalar", "&Instalar o %s" % NOME),
                ("portatil", "Criar cópia &portátil"),
                ("guia", "&Guia de uso"),
                ("usar", "&Usar sem instalar"),
                ("fechar", "&Fechar")):
            if chave == "usar" and fonte is not None:
                continue
            b = wx.Button(self, label=rotulo)
            lay.Add(b, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
            self.botoes[chave] = b
            self.Bind(wx.EVT_BUTTON, lambda e, c=chave: self._clicou(c), b)
        self.lembrar = wx.CheckBox(
            self, label="Não mostrar esta tela de novo nesta pasta")
        if fonte is None:
            lay.Add(self.lembrar, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        else:
            self.lembrar.Hide()
        self.SetSizerAndFit(lay)
        self.botoes["instalar"].SetDefault()
        self.botoes["instalar"].SetFocus()
        self.CentreOnScreen()
        self.Bind(wx.EVT_CLOSE, lambda e: self._clicou("fechar"))
        if fonte is not None:
            threading.Thread(target=self._conferir_instalador, daemon=True,
                             name="conferir-instalador").start()

    def _conferir_instalador(self):
        estado = copia_oficial.conferir_instalador()
        if copia_oficial.nao_oficial(estado):
            wx.CallAfter(self._alertar_instalador, estado)

    def _alertar_instalador(self, estado):
        wx.MessageBox(
            "%s\n\n%s\n\nSó continue se você confia em quem lhe enviou este "
            "arquivo." % (copia_oficial.TEXTOS_DO_ESTADO[estado],
                          copia_oficial.AVISO_CANAIS),
            "Instalador não oficial", wx.OK | wx.ICON_WARNING, self)

    def _clicou(self, chave):
        if chave == "instalar":
            r = fluxo_instalar(self, self.fonte)
            if r:
                self.exe_instalado, self.abrir = r
                self.escolha = "instalado"
                self.EndModal(wx.ID_OK)
        elif chave == "portatil":
            fluxo_criar_portatil(self, os.path.expanduser("~"), self.fonte)
        elif chave == "guia":
            from telezapp.interface.guia import mostrar_guia
            mostrar_guia(self)
        else:
            self.escolha = chave
            self.EndModal(wx.ID_OK)


def mostrar_boas_vindas(fonte=None):
    """Quando mostrar: executavel que nao e instalado, sem pasta `dados` ao
    lado e sem a marca `sem-boas-vindas.txt`; ou sempre, no instalador de um
    arquivo (`fonte`). Devolve "continuar" (abrir o programa), "sair" ou
    "aberto" (a versao instalada foi aberta)."""
    programa = ins.pasta_do_programa()
    if fonte is None and (
            not programa or ins.modo(programa) != "portatil" or
            ins.dados_portateis(programa) or os.path.isfile(
                os.path.join(programa, "sem-boas-vindas.txt"))):
        return "continuar"
    dlg = DialogoBoasVindas(fonte)
    try:
        dlg.ShowModal()
        escolha = dlg.escolha
        if escolha == "usar" and dlg.lembrar.GetValue():
            try:
                with open(os.path.join(programa, "sem-boas-vindas.txt"),
                          "w", encoding="utf-8") as f:
                    f.write("Não mostrar a tela de boas-vindas.\n")
            except OSError:
                pass
        if escolha == "instalado":
            if dlg.abrir:
                import subprocess
                subprocess.Popen([dlg.exe_instalado],
                                 cwd=os.path.dirname(dlg.exe_instalado))
            return "aberto"
    finally:
        dlg.Destroy()
    return "continuar" if escolha == "usar" else "sair"


def oferecer_backup(pai, cfg_dados, copiar_banco=None, pasta_inicial=""):
    """Antes de desinstalar: oferece o mesmo backup do menu (partes, senha e
    onde salvar). Devolve False se a pessoa desistiu da desinstalacao (ou se
    o backup pedido falhou), True para seguir."""
    import time
    from telezapp.interface import backup as jb
    from telezapp.nucleo import backup as bk
    r = wx.MessageBox(
        "Antes de desinstalar, quer fazer um backup dos seus dados "
        "(configurações, contas, conversas e mídias)? É o mesmo backup do "
        "menu Fazer backup e pode ser restaurado depois.", NOME,
        wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION, pai)
    if r == wx.CANCEL:
        return False
    if r != wx.YES:
        return True
    dlg = jb.DialogoBackup(pai)
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return False
        partes, senha = dlg.partes(), dlg.senha.GetValue()
    finally:
        dlg.Destroy()
    sel = wx.FileDialog(
        pai, "Salvar o backup", defaultDir=pasta_inicial or "",
        defaultFile=time.strftime("TeleZapp-backup-%Y%m%d-%H%M%S.zip"),
        wildcard="Arquivo zip|*.zip",
        style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
    try:
        if sel.ShowModal() != wx.ID_OK:
            return False
        caminho = sel.GetPath()
    finally:
        sel.Destroy()
    if not caminho.lower().endswith(".zip"):
        caminho += ".zip"
    pasta = config.pasta_dados()
    _, erro = com_espera(pai, "Fazendo o backup", lambda progresso: bk.criar(
        caminho, pasta, dict(cfg_dados), partes, senha,
        copiar_banco=copiar_banco, progresso=progresso))
    if erro:
        wx.MessageBox("Não consegui fazer o backup: %s\n\nA desinstalação "
                      "não foi feita." % erro, NOME,
                      wx.OK | wx.ICON_WARNING, pai)
        return False
    wx.MessageBox("Backup salvo em %s%s." % (
        caminho, " (com senha)" if senha else ""), NOME,
        wx.OK | wx.ICON_INFORMATION, pai)
    return True


def desinstalar_pelo_aplicativo():
    """`TeleZapp.exe --desinstalar` (Aplicativos instalados). Devolve o codigo
    de saida."""
    app = wx.App(False)       # precisa continuar referenciado
    if ins.modo() != "instalado":
        wx.MessageBox("Esta cópia do %s não é uma instalação." % NOME, NOME,
                      wx.OK | wx.ICON_INFORMATION)
        return 1
    if wx.MessageBox("Desinstalar o %s? As suas contas e conversas ficam "
                     "guardadas, a menos que você peça para apagá-las na "
                     "próxima pergunta." % NOME, NOME,
                     wx.YES_NO | wx.ICON_QUESTION) != wx.YES:
        return 0
    if not oferecer_backup(None, config.Config().dados):
        return 0
    apagar = wx.MessageBox(
        "Apagar também os seus dados (contas, sessões, conversas e mídias)? "
        "Isso não pode ser desfeito.", NOME,
        wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING) == wx.YES
    try:
        ins.desinstalar(apagar_dados=apagar)
    except Exception as e:
        wx.MessageBox("Não consegui desinstalar: %s" % e, NOME,
                      wx.OK | wx.ICON_ERROR)
        return 1
    wx.MessageBox("O %s foi desinstalado." % NOME, NOME,
                  wx.OK | wx.ICON_INFORMATION)
    return 0

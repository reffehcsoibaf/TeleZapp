# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Janelas de login e de texto, com controles nativos lidos pelo NVDA.

Cada campo tem um rotulo (StaticText antes do controle, que o NVDA le ao
focar) e o mesmo texto como nome do controle. Erros aparecem numa caixa de
mensagem do Windows antes de pedir de novo, que o NVDA le sozinho.
"""
import time

import wx

from telezapp.acessibilidade.fala import bipe
from telezapp.midia.gravador import ErroGravacao
from telezapp.midia.reprodutor import (FormatoNaoSuportado, Reprodutor,
                                       formatar_tempo)
from telezapp.provedores.base import PEDIR_CODIGO, PEDIR_SENHA, PEDIR_TELEFONE

TEXTOS_LOGIN = {
    PEDIR_TELEFONE: (
        "Conta do {servico}: número de telefone",
        "Digite o número da conta do {servico}, com DDD. Exemplo: 51 99999 "
        "8888. Para número de outro país, comece com o sinal de mais e o "
        "código do país.",
        "Número de telefone com DDD", False),
    PEDIR_CODIGO: (
        "Conta do {servico}: código de login",
        "O {servico} enviou um código de login para o aplicativo dele no seu "
        "celular (ou por SMS). Digite o código aqui.",
        "Código recebido", False),
    PEDIR_SENHA: (
        "Conta do {servico}: senha de duas etapas",
        "Esta conta tem verificação em duas etapas. Digite a senha que você "
        "criou para ela no {servico}.",
        "Senha de duas etapas", True),
}


class DialogoCampos(wx.Dialog):
    """Explicacao, um ou mais campos rotulados, OK e Cancelar."""

    def __init__(self, pai, titulo, explicacao, campos):
        """campos: lista de (rotulo, valor_inicial, senha)."""
        super().__init__(pai, title=titulo,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        lay = wx.BoxSizer(wx.VERTICAL)
        texto = wx.StaticText(self, label=explicacao)
        texto.Wrap(460)
        lay.Add(texto, 0, wx.ALL, 10)
        self.controles = []
        for rotulo, valor, senha in campos:
            lay.Add(wx.StaticText(self, label=rotulo), 0,
                    wx.LEFT | wx.RIGHT | wx.TOP, 10)
            estilo = wx.TE_PASSWORD if senha else 0
            ctrl = wx.TextCtrl(self, value=valor or "", name=rotulo,
                               style=estilo, size=(460, -1))
            lay.Add(ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
            self.controles.append(ctrl)
        botoes = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        lay.Add(botoes, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.CentreOnParent()
        if self.controles:
            self.controles[0].SetFocus()

    def valores(self):
        return [c.GetValue().strip() for c in self.controles]


def pedir_login(pai, servico, etapa, erro="", valor=""):
    """Mostra o pedido de login; devolve o texto ou None se cancelar."""
    titulo, explicacao, rotulo, senha = TEXTOS_LOGIN[etapa]
    titulo = titulo.format(servico=servico)
    explicacao = explicacao.format(servico=servico)
    if erro:
        wx.MessageBox(erro, titulo, wx.OK | wx.ICON_WARNING, pai)
    while True:
        dlg = DialogoCampos(pai, titulo, explicacao, [(rotulo, valor, senha)])
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return None
            texto = dlg.valores()[0]
        finally:
            dlg.Destroy()
        if texto:
            return texto
        wx.MessageBox("O campo %s está vazio." % rotulo, titulo,
                      wx.OK | wx.ICON_WARNING, pai)


def pedir_credenciais_telegram(pai, validar):
    """Pede api id e api hash do Telegram; (id, hash) ou None."""
    titulo = "Credenciais do aplicativo no Telegram"
    explicacao = (
        "Esta cópia do TeleZapp veio sem as credenciais do aplicativo no "
        "Telegram. Informe o api id e o api hash criados em "
        "my.telegram.org, na opção API development tools. Eles identificam "
        "o aplicativo, não a sua conta, e ficam só neste computador.")
    valores = ["", ""]
    while True:
        dlg = DialogoCampos(pai, titulo, explicacao, [
            ("api id (só números)", valores[0], False),
            ("api hash", valores[1], False)])
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return None
            valores = dlg.valores()
        finally:
            dlg.Destroy()
        if validar(*valores):
            return int(valores[0]), valores[1]
        wx.MessageBox("O api id deve ter só números e o api hash pelo menos "
                      "16 caracteres. Confira e tente de novo.", titulo,
                      wx.OK | wx.ICON_WARNING, pai)


def abrir_link(url):
    """Abre no navegador padrao; so enderecos http e https."""
    if not url.lower().startswith(("http://", "https://")):
        return False
    return wx.LaunchDefaultBrowser(url)


def rotulo_mencao(men):
    """Nome primeiro, depois o @usuario e, por ultimo, o telefone."""
    partes = []
    for p in (men.get("nome"), "@" + men["usuario"] if men.get("usuario")
              else "", men.get("telefone")):
        if p and p not in partes:
            partes.append(p)
    return ", ".join(partes) or "Contato sem nome"


def mostrar_texto(pai, titulo, texto, rotulo, links=(), botoes=(),
                  mencoes=(), acoes=(), botoes_extra=()):
    """Texto longo somente leitura, navegavel pelas setas.

    Depois do texto vem, so quando existirem, uma lista de Links, uma de
    Botoes (os que abrem um endereco) e uma de Pessoas mencionadas. Tab chega
    em cada lista, as setas passam de um item a outro; Enter ou Espaco abre
    o endereco no navegador padrao. Numa pessoa, Enter fecha a janela e a
    devolve (dicionario da mencao), para a conversa ser aberta; sem escolha,
    devolve None. Em Botoes de resposta (e Opcoes), Enter fecha a janela e
    devolve {"_acao": indice}: quem chamou confirma e envia a resposta.

    links: [(endereco, texto)]; botoes: [(rotulo, endereco)];
    mencoes: [dict com nome, usuario, telefone, id];
    acoes: [(rotulo, e_opcao_de_lista)] que podem ser tocados.
    botoes_extra: [(rotulo, funcao(janela))], botoes logo depois do texto
    (por exemplo, quem recebeu); a funcao recebe a janela, para abrir uma
    lista por cima dela ou fecha-la."""
    dlg = wx.Dialog(pai, title=titulo, size=(620, 520),
                    style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    rot = wx.StaticText(dlg, label=rotulo)
    caixa = wx.TextCtrl(dlg, value=texto, name=rotulo,
                        style=wx.TE_MULTILINE | wx.TE_READONLY)
    ok = wx.Button(dlg, wx.ID_OK, "&Fechar")
    ok.SetDefault()
    lay = wx.BoxSizer(wx.VERTICAL)
    lay.Add(rot, 0, wx.ALL, 8)
    lay.Add(caixa, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
    escolhida = [None]
    listas = []        # (ListBox, acao(indice))
    if botoes_extra:
        linha_extra = wx.WrapSizer(wx.HORIZONTAL)
        for rotulo_b, funcao in botoes_extra:
            b = wx.Button(dlg, wx.ID_ANY, rotulo_b)
            b.Bind(wx.EVT_BUTTON, lambda e, f=funcao: f(dlg))
            linha_extra.Add(b, 0, wx.RIGHT | wx.TOP, 6)
        lay.Add(linha_extra, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)

    def adicionar(rotulo_lista, itens, acao):
        r = wx.StaticText(dlg, label=rotulo_lista)
        lb = wx.ListBox(dlg, choices=itens, name=rotulo_lista)
        lb.SetSelection(0)
        lay.Add(r, 0, wx.ALL, 8)
        lay.Add(lb, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        listas.append((lb, acao))
        lb.Bind(wx.EVT_LISTBOX_DCLICK,
                lambda e, lb=lb, ac=acao: ac(lb.GetSelection()))

    def com_endereco(rotulo_item, url):
        return url if rotulo_item == url else "%s: %s" % (rotulo_item, url)

    if links:
        adicionar("Links da mensagem (%d). Enter ou Espaço abre no "
                  "navegador" % len(links),
                  [com_endereco(t, u) for u, t in links],
                  lambda i: abrir_link(links[i][0])
                  if 0 <= i < len(links) else None)
    if botoes:
        adicionar("Botões de link (%d). Enter ou Espaço abre no navegador"
                  % len(botoes),
                  [com_endereco(r_, u) for r_, u in botoes],
                  lambda i: abrir_link(botoes[i][1])
                  if 0 <= i < len(botoes) else None)
    if acoes:
        def tocar(i):
            if 0 <= i < len(acoes):
                escolhida[0] = {"_acao": i}
                dlg.EndModal(wx.ID_OK)
        adicionar("Botões de resposta e opções (%d). Enter escolhe e "
                  "pede confirmação antes de enviar" % len(acoes),
                  [("Opção: " if lista else "Botão: ") + r_
                   for r_, lista in acoes], tocar)
    if mencoes:
        def abrir_pessoa(i):
            if 0 <= i < len(mencoes):
                escolhida[0] = mencoes[i]
                dlg.EndModal(wx.ID_OK)
        adicionar("Pessoas mencionadas (%d). Enter abre uma conversa com a "
                  "pessoa" % len(mencoes),
                  [rotulo_mencao(men) for men in mencoes], abrir_pessoa)
    if listas:
        def tecla(evt):
            k = evt.GetKeyCode()
            foco = dlg.FindFocus()
            if k in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE) and \
                    not (evt.AltDown() or evt.ControlDown()
                         or evt.ShiftDown()):
                for lb, acao in listas:
                    if foco is lb:
                        acao(lb.GetSelection())
                        return
            evt.Skip()
        dlg.Bind(wx.EVT_CHAR_HOOK, tecla)
    lay.Add(ok, 0, wx.ALL | wx.ALIGN_RIGHT, 8)
    dlg.SetSizer(lay)
    dlg.SetEscapeId(wx.ID_OK)
    caixa.SetFocus()
    dlg.ShowModal()
    dlg.Destroy()
    return escolhida[0]


def gravar_voz(pai, nova_gravacao, titulo, instrucao, fala):
    """Deixa gravar, pausar, ouvir e devolve a Gravacao que a pessoa quer
    enviar, ou None se ela descartar.

    A janela abre pronta, sem gravar: o foco fica em "Gravar" e a gravacao so
    comeca quando a pessoa aperta o botao. Gravando, o foco fica em "Parar de
    gravar" (Enter), ao lado de "Pausar"; depois de parar, em "Enviar". Esc
    descarta em qualquer fase. `nova_gravacao()` devolve um Gravador novo
    (usado tambem em "Gravar de novo")."""
    dlg = wx.Dialog(pai, title=titulo, style=wx.DEFAULT_DIALOG_STYLE)
    explicacao = wx.StaticText(dlg, label=instrucao)
    explicacao.Wrap(420)
    situacao = wx.StaticText(dlg, label="Pronto para gravar.", name="Situação")
    b_gravar = wx.Button(dlg, wx.ID_ANY, "&Gravar")
    b_parar = wx.Button(dlg, wx.ID_ANY, "&Parar de gravar")
    b_pausar = wx.Button(dlg, wx.ID_ANY, "Pausa&r")
    b_enviar = wx.Button(dlg, wx.ID_OK, "&Enviar")
    b_ouvir = wx.Button(dlg, wx.ID_ANY, "&Ouvir")
    b_refazer = wx.Button(dlg, wx.ID_ANY, "Gravar de &novo")
    b_descartar = wx.Button(dlg, wx.ID_CANCEL, "&Descartar")
    lay = wx.BoxSizer(wx.VERTICAL)
    lay.Add(explicacao, 0, wx.ALL, 10)
    lay.Add(situacao, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
    linha = wx.BoxSizer(wx.HORIZONTAL)
    for b in (b_gravar, b_parar, b_pausar, b_enviar, b_ouvir, b_refazer,
              b_descartar):
        linha.Add(b, 0, wx.RIGHT, 6)
    lay.Add(linha, 0, wx.ALL, 10)
    dlg.SetSizer(lay)
    dlg.SetEscapeId(b_descartar.GetId())
    temporizador = wx.Timer(dlg)
    est = {"gravador": None, "gravacao": None, "player": None,
           "fase": "inicio"}

    def mostrar(fase):
        """fase: inicio, gravando, pausada ou pronta."""
        est["fase"] = fase
        ativa = fase in ("gravando", "pausada")
        b_gravar.Show(fase == "inicio")
        b_parar.Show(ativa)
        b_pausar.Show(ativa)
        b_pausar.SetLabel("&Continuar" if fase == "pausada" else "Pausa&r")
        for b in (b_enviar, b_ouvir, b_refazer):
            b.Show(fase == "pronta")
        dlg.Layout()
        dlg.Fit()
        foco = {"inicio": b_gravar, "gravando": b_parar,
                "pausada": b_pausar, "pronta": b_enviar}[fase]
        foco.SetFocus()
        foco.SetDefault()

    def fechar_player():
        p, est["player"] = est["player"], None
        if p is not None:
            try:
                p.fechar()
            except Exception:
                pass
        b_ouvir.SetLabel("&Ouvir")

    def comecar(_e=None):
        g = nova_gravacao()
        bipe("gravando")
        time.sleep(0.4)     # o bipe nao pode entrar na gravacao
        try:
            g.iniciar()
        except ErroGravacao as e:
            wx.MessageBox(str(e), titulo, wx.OK | wx.ICON_WARNING, dlg)
            situacao.SetLabel("Pronto para gravar.")
            mostrar("inicio")
            return False
        est["gravador"] = g
        situacao.SetLabel("Gravando: 0:00")
        mostrar("gravando")
        fala.falar("Gravando.", interromper=True)
        temporizador.Start(500)
        return True

    def pausar(_e=None):
        g = est["gravador"]
        if g is None:
            return
        if est["fase"] == "gravando":
            g.pausar()
            texto = "Pausado em %s." % formatar_tempo(g.decorrido)
            situacao.SetLabel(texto)
            mostrar("pausada")
            fala.falar(texto, interromper=True)
        elif est["fase"] == "pausada":
            g.continuar()
            situacao.SetLabel("Gravando: %s" % formatar_tempo(g.decorrido))
            mostrar("gravando")
            fala.falar("Gravando.", interromper=True)

    def parar(_e=None):
        g = est["gravador"]
        if est["fase"] not in ("gravando", "pausada") or g is None:
            return
        temporizador.Stop()
        try:
            est["gravacao"] = g.parar()
        except ErroGravacao as e:
            est["gravador"] = None
            bipe("erro")
            wx.MessageBox(str(e), titulo, wx.OK | wx.ICON_WARNING, dlg)
            dlg.EndModal(wx.ID_CANCEL)
            return
        bipe("gravacao_parada")
        r = est["gravacao"]
        texto = "Gravação pronta: %s." % formatar_tempo(r.segundos)
        if r.silenciosa:
            texto += (" Atenção: saiu quase em silêncio. Confira se o "
                      "microfone ou o som estavam ligados.")
        elif g.estourou_limite:
            texto += " A gravação chegou ao limite de tempo."
        situacao.SetLabel(texto)
        mostrar("pronta")
        fala.falar(texto, interromper=True)

    def quando_o_tempo_passa(_e=None):
        g = est["gravador"]
        if est["fase"] in ("gravando", "pausada") and g is not None:
            if not g.gravando:
                parar()        # chegou ao limite de tempo
            elif est["fase"] == "gravando":
                situacao.SetLabel("Gravando: %s" % formatar_tempo(g.decorrido))
        elif est["player"] is not None and not est["player"].tocando:
            fechar_player()

    def ouvir(_e=None):
        if est["player"] is not None:
            fechar_player()
            return
        try:
            est["player"] = Reprodutor(est["gravacao"].caminho)
            est["player"].tocar()
        except (FormatoNaoSuportado, Exception):
            est["player"] = None
            fala.falar("Não consegui tocar a gravação.", interromper=True)
            return
        b_ouvir.SetLabel("Parar de &ouvir")
        temporizador.Start(500)

    def refazer(_e=None):
        fechar_player()
        if est["gravacao"] is not None:
            _apagar(est["gravacao"].caminho)
            est["gravacao"] = None
        situacao.SetLabel("Pronto para gravar.")
        mostrar("inicio")
        fala.falar("Pronto para gravar de novo.", interromper=True)

    def descartar(_e=None):
        temporizador.Stop()
        fechar_player()
        if est["fase"] in ("gravando", "pausada") and \
                est["gravador"] is not None:
            est["gravador"].cancelar()
        elif est["gravacao"] is not None:
            _apagar(est["gravacao"].caminho)
            est["gravacao"] = None
        dlg.EndModal(wx.ID_CANCEL)

    def enviar(_e=None):
        temporizador.Stop()
        fechar_player()
        dlg.EndModal(wx.ID_OK)

    b_gravar.Bind(wx.EVT_BUTTON, comecar)
    b_parar.Bind(wx.EVT_BUTTON, parar)
    b_pausar.Bind(wx.EVT_BUTTON, pausar)
    b_ouvir.Bind(wx.EVT_BUTTON, ouvir)
    b_refazer.Bind(wx.EVT_BUTTON, refazer)
    b_descartar.Bind(wx.EVT_BUTTON, descartar)
    b_enviar.Bind(wx.EVT_BUTTON, enviar)
    dlg.Bind(wx.EVT_TIMER, quando_o_tempo_passa)
    dlg.Bind(wx.EVT_CLOSE, descartar)
    resultado = None
    try:
        mostrar("inicio")
        dlg.CentreOnParent()
        if dlg.ShowModal() == wx.ID_OK:
            resultado = est["gravacao"]
    finally:
        temporizador.Stop()
        if est["gravador"] is not None and \
                est["fase"] in ("gravando", "pausada"):
            est["gravador"].cancelar()
        dlg.Destroy()
    return resultado


def _apagar(caminho):
    import os
    try:
        os.remove(caminho)
    except OSError:
        pass


def escolher_arquivo(pai, pasta=""):
    """Janela do Windows para escolher o arquivo a enviar; None se cancelar."""
    filtros = ("Fotos, vídeos, áudios e documentos|*.*|"
               "Fotos|*.jpg;*.jpeg;*.png;*.webp|"
               "Vídeos|*.mp4;*.mov;*.m4v;*.3gp|"
               "Áudios|*.ogg;*.opus;*.mp3;*.m4a;*.wav|"
               "Todos os arquivos|*.*")
    dlg = wx.FileDialog(pai, "Escolha o arquivo para enviar",
                        defaultDir=pasta, wildcard=filtros,
                        style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return None
        return dlg.GetPath()
    finally:
        dlg.Destroy()


def escolher_acao_grupo(pai, nome, pode_sair):
    """O que fazer com a conversa de um grupo: "limpar" (apaga as mensagens e
    mantem o grupo na lista), "apagar" (tira da lista), "sair" (sai do grupo
    e mantem a conversa) ou "sair_apagar". None se cancelar. Sem `pode_sair`
    (conta desconectada ou servico que nao sai), so as duas primeiras."""
    dlg = wx.Dialog(pai, title="Apagar conversa do grupo")
    lay = wx.BoxSizer(wx.VERTICAL)
    texto = ("O que fazer com a conversa do grupo %s? Limpar conversa apaga "
             "as mensagens e as mídias daqui, e o grupo continua na lista. "
             "Apagar da lista de conversas tira o grupo da lista; ele volta "
             "se chegar mensagem nova. Sair do grupo tira a sua conta do "
             "grupo." % nome)
    lay.Add(wx.StaticText(dlg, label=texto), 0, wx.ALL, 10)
    opcoes = [("&Limpar conversa", "limpar"),
              ("&Apagar da lista de conversas", "apagar")]
    if pode_sair:
        opcoes += [("&Sair do grupo", "sair"),
                   ("Sair do grupo e apagar da &lista", "sair_apagar")]
    escolhida = []
    caixa = wx.BoxSizer(wx.VERTICAL)
    for rotulo, chave in opcoes:
        b = wx.Button(dlg, wx.ID_ANY, rotulo)
        b.Bind(wx.EVT_BUTTON,
               lambda e, c=chave: (escolhida.append(c),
                                   dlg.EndModal(wx.ID_OK)))
        caixa.Add(b, 0, wx.EXPAND | wx.BOTTOM, 6)
    caixa.Add(wx.Button(dlg, wx.ID_CANCEL, "Cancelar"), 0, wx.EXPAND)
    lay.Add(caixa, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
    dlg.SetSizerAndFit(lay)
    dlg.SetEscapeId(wx.ID_CANCEL)
    dlg.CentreOnParent()
    try:
        dlg.ShowModal()
    finally:
        dlg.Destroy()
    return escolhida[0] if escolhida else None


def escolher_destino_zip(pai, nome, pasta=""):
    """Janela do Windows para escolher onde gravar o .zip; None se cancelar."""
    dlg = wx.FileDialog(pai, "Salvar o conteúdo da conversa", defaultDir=pasta,
                        defaultFile=nome, wildcard="Arquivo zip|*.zip",
                        style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return None
        caminho = dlg.GetPath()
        return caminho if caminho.lower().endswith(".zip")             else caminho + ".zip"
    finally:
        dlg.Destroy()


def mostrar_mensagem(pai, titulo, texto, copiar):
    """O texto de uma mensagem, somente leitura, com os botoes Copiar texto
    e Fechar (Esc tambem fecha). `copiar(texto)` copia e avisa a pessoa."""
    dlg = wx.Dialog(pai, title=titulo, size=(640, 440),
                    style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    rot = wx.StaticText(dlg, label="Texto da mensagem")
    caixa = wx.TextCtrl(dlg, value=texto, name="Texto da mensagem",
                        style=wx.TE_MULTILINE | wx.TE_READONLY)
    b_copiar = wx.Button(dlg, wx.ID_ANY, "&Copiar texto")
    b_fechar = wx.Button(dlg, wx.ID_OK, "&Fechar")
    b_fechar.SetDefault()
    b_copiar.Bind(wx.EVT_BUTTON, lambda e: copiar(texto))
    linha = wx.BoxSizer(wx.HORIZONTAL)
    for b in (b_copiar, b_fechar):
        linha.Add(b, 0, wx.RIGHT, 8)
    lay = wx.BoxSizer(wx.VERTICAL)
    lay.Add(rot, 0, wx.ALL, 8)
    lay.Add(caixa, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
    lay.Add(linha, 0, wx.ALL | wx.ALIGN_RIGHT, 8)
    dlg.SetSizer(lay)
    dlg.SetEscapeId(wx.ID_OK)
    caixa.SetFocus()
    dlg.ShowModal()
    dlg.Destroy()


def mostrar_depuracao(pai, titulo, texto, copiar, salvar,
                      rotulo="Texto de depuração"):
    """Texto de depuracao somente leitura, com os botoes Copiar tudo e
    Salvar em arquivo. `copiar(texto)` e `salvar(texto)` fazem o trabalho e
    avisam a pessoa; a janela so os chama."""
    dlg = wx.Dialog(pai, title=titulo, size=(700, 560),
                    style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    rot = wx.StaticText(dlg, label=rotulo)
    caixa = wx.TextCtrl(dlg, value=texto, name=rotulo,
                        style=wx.TE_MULTILINE | wx.TE_READONLY)
    b_copiar = wx.Button(dlg, wx.ID_ANY, "&Copiar tudo")
    b_salvar = wx.Button(dlg, wx.ID_ANY, "&Salvar em arquivo")
    b_fechar = wx.Button(dlg, wx.ID_OK, "&Fechar")
    b_fechar.SetDefault()
    b_copiar.Bind(wx.EVT_BUTTON, lambda e: copiar(texto))
    b_salvar.Bind(wx.EVT_BUTTON, lambda e: salvar(texto))
    linha = wx.BoxSizer(wx.HORIZONTAL)
    for b in (b_copiar, b_salvar, b_fechar):
        linha.Add(b, 0, wx.RIGHT, 8)
    lay = wx.BoxSizer(wx.VERTICAL)
    lay.Add(rot, 0, wx.ALL, 8)
    lay.Add(caixa, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
    lay.Add(linha, 0, wx.ALL | wx.ALIGN_RIGHT, 8)
    dlg.SetSizer(lay)
    dlg.SetEscapeId(wx.ID_OK)
    caixa.SetFocus()
    dlg.ShowModal()
    dlg.Destroy()


# ------------------------------------------------------- pareamento WhatsApp
INSTRUCOES_INICIO = "Como você quer conectar o WhatsApp?"
INSTRUCOES_CODIGO = (
    "No celular, abra o WhatsApp, vá em Configurações, Dispositivos "
    "conectados, Conectar dispositivo, e escolha Conectar com número de "
    "telefone. Digite abaixo o número do WhatsApp em formato internacional: "
    "sinal de mais, código do país, DDD e número, por exemplo "
    "+55 51 99999 8888. Depois digite lá o código que o TeleZapp mostrar.")
INSTRUCOES_QR = (
    "No celular, abra o WhatsApp, vá em Configurações, Dispositivos "
    "conectados, Conectar dispositivo, e aponte a câmera para o QR Code. "
    "O QR Code abre em tela cheia; Esc volta para esta janela, e o botão "
    "Mostrar o QR em tela cheia abre de novo. O QR Code é trocado sozinho a "
    "cada 20 segundos, mais ou menos.")
BORDA_QR = 6          # margem branca em modulos (o minimo do padrao e 4)
ESCALA_JANELA = 7     # pixels por modulo na janela de pareamento


def pixels_qr(codigo, escala, borda=BORDA_QR):
    """(lado, bytes RGB) do QR: preto puro sobre branco puro, cada modulo
    com `escala` pixels inteiros (sem suavizacao, que estraga a leitura)."""
    import segno
    linhas = list(segno.make_qr(codigo, error="l").matrix_iter(border=borda))
    lado = len(linhas) * escala
    dados = bytearray()
    for linha in linhas:
        faixa = bytearray()
        for escuro in linha:
            faixa += (b"\x00\x00\x00" if escuro else b"\xff\xff\xff") * escala
        dados += bytes(faixa) * escala
    return lado, bytes(dados)


def modulos_qr(codigo, borda=BORDA_QR):
    import segno
    return len(list(segno.make_qr(codigo, error="l").matrix_iter(
        border=borda)))


def imagem_qr(codigo, escala=ESCALA_JANELA):
    lado, dados = pixels_qr(codigo, escala)
    return wx.Bitmap(wx.Image(lado, lado, dados))


def escolher_historico(pai, opcoes):
    """Pergunta quanto historico trazer; devolve a chave ou None."""
    chaves = list(opcoes)
    dlg = wx.SingleChoiceDialog(
        pai, "Escolha até onde o WhatsApp deve trazer as mensagens antigas "
        "para o TeleZapp. Isso só pode ser escolhido agora, antes de "
        "conectar. Quem decide no fim é o celular: ele pode mandar menos.",
        "Mensagens antigas para trazer", [opcoes[k][0] for k in chaves])
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return None
        return chaves[dlg.GetSelection()]
    finally:
        dlg.Destroy()


class JanelaQrCheia(wx.Frame):
    """O QR em tela cheia, fundo branco, no maior tamanho inteiro que
    couber. Esc fecha."""

    def __init__(self, pai, codigo, ao_fechar):
        super().__init__(pai, title="QR Code do WhatsApp em tela cheia. "
                         "Esc volta.")
        self.ao_fechar = ao_fechar
        self.SetBackgroundColour(wx.WHITE)
        self.painel = wx.Panel(self)
        self.painel.SetBackgroundColour(wx.WHITE)
        self.imagem = wx.StaticBitmap(self.painel, name="QR Code")
        self.aguarde = wx.StaticText(self.painel, label="Aguardando o QR "
                                     "Code do WhatsApp...")
        self.codigo = ""
        self.Bind(wx.EVT_CHAR_HOOK, self._tecla)
        self.Bind(wx.EVT_CLOSE, self._fechar)
        # o Windows informa o tamanho final da tela cheia depois de abrir:
        # redesenha sempre que o tamanho muda
        self.Bind(wx.EVT_SIZE, self._ao_redimensionar)
        self.ShowFullScreen(True)
        self.mostrar(codigo)

    def _ao_redimensionar(self, evt):
        evt.Skip()
        if self.codigo:
            wx.CallAfter(self._desenhar)

    def mostrar(self, codigo):
        if not codigo or codigo == self.codigo:
            return
        self.codigo = codigo
        self.aguarde.Show(False)
        self._desenhar()

    def limpar(self):
        """O QR mostrado deixou de valer: some ate chegar o novo."""
        self.codigo = ""
        self.imagem.Show(False)
        self.aguarde.Show(True)

    def _desenhar(self):
        if not self or not self.codigo:
            return
        self.imagem.Show(True)
        codigo = self.codigo
        largura, altura = self.GetClientSize()
        self.painel.SetSize((largura, altura))
        n = modulos_qr(codigo)
        escala = max(ESCALA_JANELA, int(min(largura, altura) * 0.92) // n)
        self.imagem.SetBitmap(imagem_qr(codigo, escala))
        lado = n * escala
        self.imagem.SetPosition(((largura - lado) // 2,
                                 (altura - lado) // 2))

    def _tecla(self, evt):
        if evt.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close()
            return
        evt.Skip()

    def _fechar(self, evt):
        self.ao_fechar()
        self.Destroy()


class DialogoCodigo(wx.Dialog):
    """So o codigo de pareamento, com o foco nele (como no WinZapp)."""

    def __init__(self, pai, codigo):
        super().__init__(pai, title="Código de pareamento do WhatsApp")
        lay = wx.BoxSizer(wx.VERTICAL)
        t = wx.StaticText(self, label=(
            "No celular, em Conectar com número de telefone, digite este "
            "código. Esta janela fecha sozinha quando o celular conectar."))
        t.Wrap(380)
        lay.Add(t, 0, wx.ALL, 10)
        lay.Add(wx.StaticText(self, label="Código de pareamento"), 0,
                wx.LEFT | wx.RIGHT, 10)
        self.campo = wx.TextCtrl(self, value=codigo, name="Código de "
                                 "pareamento", style=wx.TE_READONLY |
                                 wx.TE_CENTER, size=(380, -1))
        fonte = self.campo.GetFont()
        fonte.SetPointSize(fonte.GetPointSize() * 2)
        self.campo.SetFont(fonte)
        lay.Add(self.campo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        fechar = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        lay.Add(fechar, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.Bind(wx.EVT_BUTTON, lambda e: self.Destroy(), id=wx.ID_CANCEL)
        self.CentreOnParent()
        self.campo.SetFocus()
        self.campo.SetInsertionPoint(0)

    def trocar(self, codigo):
        self.campo.SetValue(codigo)
        self.campo.SetFocus()
        self.campo.SetInsertionPoint(0)


class DialogoPareamento(wx.Dialog):
    """Janela sem bloqueio: o QR Code e o codigo chegam enquanto ela esta
    aberta. `gerar_codigo(telefone)` pede o codigo ao provedor;
    `ao_cancelar()` e chamado se a pessoa fechar antes de concluir."""

    def __init__(self, pai, falar, gerar_codigo, ao_cancelar, telefone="",
                 som=None, reiniciar=None):
        super().__init__(pai, title="Conectar conta do WhatsApp",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.falar = falar
        self.som = som or (lambda tipo: None)
        self.gerar_codigo = gerar_codigo
        self.ao_cancelar = ao_cancelar
        self.concluido = False
        self.reiniciar = reiniciar or (lambda: None)
        self.codigo_gerado = False   # um codigo ja foi pedido nesta conexao
        self.falhas = 0
        self.qr_atual = ""
        self.tela_cheia = None
        self.janela_codigo = None
        lay = wx.BoxSizer(wx.VERTICAL)

        # --- inicio: dois botoes
        self.painel_inicio = wx.Panel(self)
        pi = wx.BoxSizer(wx.VERTICAL)
        pi.Add(wx.StaticText(self.painel_inicio, label=INSTRUCOES_INICIO), 0,
               wx.BOTTOM, 8)
        self.botao_telefone = wx.Button(
            self.painel_inicio, label="Parear com número de &telefone")
        self.botao_qr = wx.Button(self.painel_inicio,
                                  label="Parear via &QR Code")
        pi.Add(self.botao_telefone, 0, wx.EXPAND | wx.BOTTOM, 6)
        pi.Add(self.botao_qr, 0, wx.EXPAND)
        self.painel_inicio.SetSizer(pi)
        lay.Add(self.painel_inicio, 0, wx.EXPAND | wx.ALL, 10)

        # --- codigo
        self.painel_codigo = wx.Panel(self)
        pc = wx.BoxSizer(wx.VERTICAL)
        t = wx.StaticText(self.painel_codigo, label=INSTRUCOES_CODIGO)
        t.Wrap(460)
        pc.Add(t, 0, wx.BOTTOM, 8)
        pc.Add(wx.StaticText(self.painel_codigo,
                             label="Número do WhatsApp em formato "
                                   "internacional"), 0)
        self.telefone = wx.TextCtrl(self.painel_codigo, value=telefone,
                                    style=wx.TE_PROCESS_ENTER,
                                    name="Número do WhatsApp em formato "
                                         "internacional")
        pc.Add(self.telefone, 0, wx.EXPAND)
        self.botao_gerar = wx.Button(self.painel_codigo, label="&Gerar código")
        pc.Add(self.botao_gerar, 0, wx.TOP, 6)
        pc.Add(wx.StaticText(self.painel_codigo,
                             label="Código para digitar no celular"), 0,
               wx.TOP, 8)
        self.codigo = wx.TextCtrl(self.painel_codigo, value="",
                                  style=wx.TE_READONLY,
                                  name="Código para digitar no celular")
        pc.Add(self.codigo, 0, wx.EXPAND)
        self.voltar_codigo = wx.Button(self.painel_codigo, label="&Voltar")
        pc.Add(self.voltar_codigo, 0, wx.TOP, 8)
        self.painel_codigo.SetSizer(pc)
        lay.Add(self.painel_codigo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # --- QR
        self.painel_qr = wx.Panel(self)
        pq = wx.BoxSizer(wx.VERTICAL)
        t = wx.StaticText(self.painel_qr, label=INSTRUCOES_QR)
        t.Wrap(460)
        pq.Add(t, 0, wx.BOTTOM, 8)
        self.situacao_qr = wx.TextCtrl(
            self.painel_qr, value="Aguardando o QR Code do WhatsApp...",
            style=wx.TE_READONLY, name="Situação do QR Code")
        pq.Add(self.situacao_qr, 0, wx.EXPAND)
        self.botao_cheia = wx.Button(self.painel_qr,
                                     label="Mostrar o QR em &tela cheia")
        pq.Add(self.botao_cheia, 0, wx.TOP, 6)
        self.imagem = wx.StaticBitmap(self.painel_qr, name="QR Code")
        pq.Add(self.imagem, 0, wx.TOP | wx.ALIGN_CENTER, 8)
        self.voltar_qr = wx.Button(self.painel_qr, label="&Voltar")
        pq.Add(self.voltar_qr, 0, wx.TOP, 8)
        self.painel_qr.SetSizer(pq)
        lay.Add(self.painel_qr, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        cancelar = wx.Button(self, wx.ID_CANCEL, "&Cancelar")
        lay.Add(cancelar, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizer(lay)
        self.SetEscapeId(wx.ID_CANCEL)

        self.botao_telefone.Bind(wx.EVT_BUTTON,
                                 lambda e: self._ir_para("codigo"))
        self.botao_qr.Bind(wx.EVT_BUTTON, lambda e: self._ir_para("qr"))
        self.voltar_codigo.Bind(wx.EVT_BUTTON,
                                lambda e: self._ir_para("inicio"))
        self.voltar_qr.Bind(wx.EVT_BUTTON, lambda e: self._ir_para("inicio"))
        self.botao_gerar.Bind(wx.EVT_BUTTON, lambda e: self._gerar())
        self.botao_cheia.Bind(wx.EVT_BUTTON, lambda e: self._tela_cheia())
        self.telefone.Bind(wx.EVT_TEXT_ENTER, lambda e: self._gerar())
        self.Bind(wx.EVT_BUTTON, lambda e: self.Close(), id=wx.ID_CANCEL)
        self.Bind(wx.EVT_CLOSE, self._ao_fechar)
        self._ir_para("inicio")
        self.Fit()
        self.CentreOnParent()

    def _ir_para(self, pagina):
        """inicio (os dois botoes), codigo (por telefone) ou qr."""
        self.pagina = pagina
        self.painel_inicio.Show(pagina == "inicio")
        self.painel_codigo.Show(pagina == "codigo")
        self.painel_qr.Show(pagina == "qr")
        self.Layout()
        self.Fit()
        if pagina == "inicio":
            self.botao_telefone.SetFocus()
        elif pagina == "codigo":
            self.telefone.SetFocus()
        else:
            if self.codigo_gerado:
                # depois de pedir um codigo o QR antigo pode nao valer mais
                # (o WhatsApp troca a chave): recomeca a conexao
                self.falar("Pedindo um QR Code novo ao WhatsApp.")
                self.reiniciar()
            # o QR Code ja abre em tela cheia, esperando o QR se preciso
            self._tela_cheia(esperar=True)

    def avisar(self, texto):
        """Uma falha do pareamento: fala e mostra sem esperar a pessoa."""
        self.falar(texto)
        if self.pagina == "qr":
            self.situacao_qr.SetValue(texto)
        else:
            self.codigo.SetValue("")
            self.botao_gerar.Enable()

    def reiniciou(self):
        """A conexao recomecou: o QR e o codigo antigos nao valem mais."""
        self.codigo_gerado = False
        self.qr_atual = ""
        self.codigo.SetValue("")
        self.botao_gerar.Enable()
        self.situacao_qr.SetValue("Aguardando o QR Code do WhatsApp...")
        self.imagem.Show(False)
        if self.tela_cheia:
            self.tela_cheia.limpar()
        if self.janela_codigo:
            self.janela_codigo.Destroy()
            self.janela_codigo = None

    def _gerar(self):
        from telezapp.nucleo.modelos import normalizar_telefone
        numero = normalizar_telefone(self.telefone.GetValue())
        if numero is None:
            wx.MessageBox("Número inválido. Use o formato internacional: "
                          "sinal de mais, código do país, DDD e número, por "
                          "exemplo +55 51 99999 8888.", self.GetTitle(),
                          wx.OK | wx.ICON_WARNING, self)
            self.telefone.SetFocus()
            return
        self.codigo_gerado = True
        self.botao_gerar.Disable()
        self.codigo.SetValue("Gerando o código...")
        self.falar("Gerando o código. Aguarde.")
        self.gerar_codigo(numero)

    def mostrar_codigo(self, codigo, erro=""):
        self.botao_gerar.Enable()
        if erro:
            self.codigo.SetValue("")
            self.som("erro")
            wx.MessageBox(erro, self.GetTitle(), wx.OK | wx.ICON_WARNING,
                          self)
            self.telefone.SetFocus()
            return
        self.codigo.SetValue(codigo)
        self.som("pronto")
        if self.janela_codigo:
            self.janela_codigo.trocar(codigo)
        else:
            self.janela_codigo = DialogoCodigo(self, codigo)
            self.janela_codigo.Show()

    def mostrar_qr(self, codigo):
        if codigo == self.qr_atual:
            return
        primeiro = not self.qr_atual
        self.qr_atual = codigo
        self.imagem.SetBitmap(imagem_qr(codigo))
        self.imagem.Show(True)
        self.situacao_qr.SetValue("QR Code pronto. Atualizado às %s." %
                                  time.strftime("%H:%M:%S"))
        if self.tela_cheia:
            self.tela_cheia.mostrar(codigo)
        self.painel_qr.Layout()
        self.Fit()
        if self.pagina == "qr":
            self.som("pronto" if primeiro else "atualizado")
            self.falar("QR Code pronto." if primeiro
                       else "QR Code atualizado.")

    def _tela_cheia(self, esperar=False):
        if not self.qr_atual and not esperar:
            self.falar("O QR Code ainda não chegou. Aguarde.")
            return
        if self.tela_cheia:
            self.tela_cheia.Raise()
            return

        def ao_fechar():
            self.tela_cheia = None
        self.tela_cheia = JanelaQrCheia(self, self.qr_atual, ao_fechar)

    def _fechar_extras(self):
        for janela in (self.tela_cheia, self.janela_codigo):
            if janela:
                try:
                    janela.Destroy()
                except RuntimeError:
                    pass
        self.tela_cheia = self.janela_codigo = None

    def concluir(self):
        self.concluido = True
        self._fechar_extras()
        self.Destroy()

    def _ao_fechar(self, evt):
        self._fechar_extras()
        if not self.concluido:
            self.ao_cancelar()
        self.Destroy()


class DialogoAvisoDeChamada(wx.Dialog):
    """Alguem esta ligando pelo WhatsApp e o TeleZapp ainda nao atende:
    janela sem bloqueio com o aviso e os botoes OK e Conversar. O texto muda
    se a chamada acabar enquanto a janela esta aberta."""

    def __init__(self, pai, texto, ao_conversar):
        super().__init__(pai, title="Chamada do WhatsApp")
        self.ao_conversar = ao_conversar
        lay = wx.BoxSizer(wx.VERTICAL)
        self.aviso = wx.StaticText(self, label=texto)
        self.aviso.Wrap(420)
        lay.Add(self.aviso, 0, wx.ALL, 12)
        linha = wx.BoxSizer(wx.HORIZONTAL)
        self.ok = wx.Button(self, wx.ID_OK, "OK")
        self.conversar = wx.Button(self, wx.ID_ANY, "&Conversar")
        self.ok.SetDefault()
        linha.Add(self.ok, 0, wx.RIGHT, 8)
        linha.Add(self.conversar, 0)
        lay.Add(linha, 0, wx.ALL | wx.ALIGN_RIGHT, 12)
        self.SetSizerAndFit(lay)
        self.SetEscapeId(wx.ID_OK)
        self.ok.Bind(wx.EVT_BUTTON, lambda e: self.Close())
        self.conversar.Bind(wx.EVT_BUTTON, lambda e: self._conversar())
        self.CentreOnParent()
        self.ok.SetFocus()

    def atualizar(self, texto):
        self.aviso.SetLabel(texto)
        self.aviso.Wrap(420)
        self.Fit()

    def _conversar(self):
        self.Close()
        self.ao_conversar()

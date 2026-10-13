# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Janelas de login e de texto, com controles nativos lidos pelo NVDA.

Cada campo tem um rotulo (StaticText antes do controle, que o NVDA le ao
focar) e o mesmo texto como nome do controle. Erros aparecem numa caixa de
mensagem do Windows antes de pedir de novo, que o NVDA le sozinho.
"""
import time

import wx

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
        "Nesta fase de testes, o TeleZapp ainda não tem as credenciais "
        "próprias no Telegram. Informe o api id e o api hash criados em "
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


def mostrar_texto(pai, titulo, texto, rotulo):
    """Texto longo somente leitura, navegavel pelas setas."""
    dlg = wx.Dialog(pai, title=titulo, size=(620, 460),
                    style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    rot = wx.StaticText(dlg, label=rotulo)
    caixa = wx.TextCtrl(dlg, value=texto, name=rotulo,
                        style=wx.TE_MULTILINE | wx.TE_READONLY)
    ok = wx.Button(dlg, wx.ID_OK, "&Fechar")
    ok.SetDefault()
    lay = wx.BoxSizer(wx.VERTICAL)
    lay.Add(rot, 0, wx.ALL, 8)
    lay.Add(caixa, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
    lay.Add(ok, 0, wx.ALL | wx.ALIGN_RIGHT, 8)
    dlg.SetSizer(lay)
    dlg.SetEscapeId(wx.ID_OK)
    caixa.SetFocus()
    dlg.ShowModal()
    dlg.Destroy()


# ------------------------------------------------------- pareamento WhatsApp
INSTRUCOES_CODIGO = (
    "No celular, abra o WhatsApp, vá em Configurações, Dispositivos "
    "conectados, Conectar dispositivo, e escolha Conectar com número de "
    "telefone. Depois digite lá o código que o TeleZapp mostrar.")
INSTRUCOES_QR = (
    "No celular, abra o WhatsApp, vá em Configurações, Dispositivos "
    "conectados, Conectar dispositivo, e aponte a câmera para o QR Code. "
    "Para facilitar, use o botão Mostrar o QR em tela cheia. O QR Code é "
    "trocado sozinho a cada 20 segundos, mais ou menos.")
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
        self._desenhar()

    def _desenhar(self):
        if not self:
            return
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
                 som=None):
        super().__init__(pai, title="Conectar conta do WhatsApp",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.falar = falar
        self.som = som or (lambda tipo: None)
        self.gerar_codigo = gerar_codigo
        self.ao_cancelar = ao_cancelar
        self.concluido = False
        self.qr_atual = ""
        self.tela_cheia = None
        self.janela_codigo = None
        lay = wx.BoxSizer(wx.VERTICAL)

        self.modo = wx.RadioBox(
            self, label="Como conectar",
            choices=["Código digitado no celular", "QR Code"],
            majorDimension=1, style=wx.RA_SPECIFY_COLS)
        lay.Add(self.modo, 0, wx.EXPAND | wx.ALL, 10)

        # --- codigo
        self.painel_codigo = wx.Panel(self)
        pc = wx.BoxSizer(wx.VERTICAL)
        t = wx.StaticText(self.painel_codigo, label=INSTRUCOES_CODIGO)
        t.Wrap(460)
        pc.Add(t, 0, wx.BOTTOM, 8)
        pc.Add(wx.StaticText(self.painel_codigo,
                             label="Número do WhatsApp com DDD"), 0)
        self.telefone = wx.TextCtrl(self.painel_codigo, value=telefone,
                                    style=wx.TE_PROCESS_ENTER,
                                    name="Número do WhatsApp com DDD")
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
        self.painel_qr.SetSizer(pq)
        lay.Add(self.painel_qr, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        cancelar = wx.Button(self, wx.ID_CANCEL, "&Cancelar")
        lay.Add(cancelar, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizer(lay)
        self.SetEscapeId(wx.ID_CANCEL)

        self.modo.Bind(wx.EVT_RADIOBOX, lambda e: self._trocar_modo())
        self.botao_gerar.Bind(wx.EVT_BUTTON, lambda e: self._gerar())
        self.botao_cheia.Bind(wx.EVT_BUTTON, lambda e: self._tela_cheia())
        self.telefone.Bind(wx.EVT_TEXT_ENTER, lambda e: self._gerar())
        self.Bind(wx.EVT_BUTTON, lambda e: self.Close(), id=wx.ID_CANCEL)
        self.Bind(wx.EVT_CLOSE, self._ao_fechar)
        self._trocar_modo()
        self.Fit()
        self.CentreOnParent()

    def _trocar_modo(self):
        codigo = self.modo.GetSelection() == 0
        self.painel_codigo.Show(codigo)
        self.painel_qr.Show(not codigo)
        self.Layout()
        self.Fit()
        if codigo:
            self.telefone.SetFocus()
        else:
            self.situacao_qr.SetFocus()

    def _gerar(self):
        from telezapp.nucleo.modelos import normalizar_telefone
        numero = normalizar_telefone(self.telefone.GetValue())
        if numero is None:
            wx.MessageBox("Número inválido. Use DDD e número, por exemplo "
                          "51 99999 8888.", self.GetTitle(),
                          wx.OK | wx.ICON_WARNING, self)
            self.telefone.SetFocus()
            return
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
        self.situacao_qr.SetValue("QR Code pronto. Atualizado às %s." %
                                  time.strftime("%H:%M:%S"))
        if self.tela_cheia:
            self.tela_cheia.mostrar(codigo)
        self.painel_qr.Layout()
        self.Fit()
        if self.modo.GetSelection() == 1:
            self.som("pronto" if primeiro else "atualizado")
            self.falar("QR Code pronto." if primeiro
                       else "QR Code atualizado.")

    def _tela_cheia(self):
        if not self.qr_atual:
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

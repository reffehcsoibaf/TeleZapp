# -*- coding: utf-8 -*-
"""Prototipo da interface do TeleZapp (wxPython), com dados de exemplo.

Serve para avaliar, com o NVDA, a estrutura da janela, a leitura das listas,
os atalhos e os avisos de mensagem nova. Nao conecta em nenhuma conta e nao
envia nada: tudo e simulado.

Chamado pelo 3-teste-interface.bat. Escreve no mesmo log do .bat.
O log registra foco, atalhos e acoes, nunca o texto das mensagens digitadas.
"""
import os
import platform
import sys
import time
import traceback

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    BASE, "logs", "resultado-teste-interface.log")
INTERVALO_AUTOMATICO_MS = 20000
TEXTO_SEM_CONVERSA = "Nenhuma conversa aberta. Aperte Enter numa conversa."
TEXTO_SEM_MENSAGENS = "Esta conversa ainda não tem mensagens."


def log(msg):
    linha = time.strftime("%H:%M:%S") + " " + msg
    print(linha, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except OSError as e:
        print("(nao consegui gravar no log: %r)" % e, flush=True)


def _erro_nao_tratado(tipo, valor, tb):
    log("ERRO NAO TRATADO:\n" + "".join(
        traceback.format_exception(tipo, valor, tb)))


sys.excepthook = _erro_nao_tratado

try:
    import wx
    import modelo_conversas as mc
    from fala import Fala, bipe
except Exception:
    log("ERRO ao importar os modulos do prototipo:\n" + traceback.format_exc())
    sys.exit(1)

AJUDA = """\
ESTRUTURA DA JANELA
A janela tem três áreas, nesta ordem de Tab: Conversas, Mensagens e a caixa
Digite sua mensagem, seguida dos botões Enviar e Anexar.

ATALHOS
Control 1: ir para a lista de conversas
Control 2: ir para a lista de mensagens
Control 3: ir para a caixa de digitação
Control U: ir para a próxima conversa com mensagens não lidas
Control R: ouvir a última mensagem da conversa aberta
Control N: simular a chegada de uma mensagem nova
Control T: ligar ou desligar mensagens simuladas automáticas (a cada 20 s)
Control O: anexar arquivos (simulado)
Control Shift C: copiar o texto da mensagem selecionada
Control Shift R: responder à mensagem selecionada
Alt Enter: ver os detalhes e o texto completo da mensagem selecionada
Tecla Aplicativos ou Shift F10: menu da mensagem selecionada

NA LISTA DE CONVERSAS
Setas: percorrem as conversas (cada uma é lida com o número de não lidas).
Enter: abre a conversa e leva o foco para as mensagens. Se o Enter não
funcionar, use o menu Conversa, Abrir a conversa selecionada.

NA LISTA DE MENSAGENS
Setas: percorrem as mensagens.
Enter: abre ou baixa a mídia (simulado) ou mostra os detalhes de um texto.

NA CAIXA DE DIGITAÇÃO
Enter: envia. Shift Enter: nova linha.
Control V com arquivos copiados no Explorer: anexa os arquivos (simulado).

MENU EXIBIÇÃO
Escolha como cada mensagem é lida: autor e hora primeiro, conteúdo primeiro,
ou autor só quando muda. Compare e me diga qual funciona melhor.
"""


def seguro(funcao):
    """Registra no log qualquer erro de um tratador, sem derrubar a janela."""
    def interno(self, *args, **kwargs):
        try:
            return funcao(self, *args, **kwargs)
        except Exception:
            log("ERRO em %s:\n%s" % (funcao.__name__, traceback.format_exc()))
    interno.__name__ = funcao.__name__
    return interno


class Janela(wx.Frame):
    def __init__(self):
        super().__init__(None, title="TeleZapp, protótipo", size=(980, 680))
        self.fala = Fala(log)
        self.conversas = mc.dados_de_exemplo()
        self.atual = None
        self.estilo = mc.ESTILO_AUTOR_PRIMEIRO
        self.resposta_a = None
        self.contador_sim = 0
        self.opcoes = {"som": True, "falar_novas": True, "confirmar_envio": True}

        self._criar_menus()
        self._criar_controles()
        self.CreateStatusBar()
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._ao_timer, self.timer)
        self.Bind(wx.EVT_CLOSE, self._ao_fechar)
        self.Bind(wx.EVT_CHAR_HOOK, self._char_hook)

        self._preencher_conversas()
        self.lista_conv.SetSelection(0)
        self.lista_msgs.Set([TEXTO_SEM_CONVERSA])
        self.lista_msgs.SetSelection(0)
        self.Centre()
        wx.CallAfter(self._inicio)

    # ------------------------------------------------------------ montagem
    def _criar_menus(self):
        barra = wx.MenuBar()
        self.itens = {}

        def item(menu, chave, rotulo, tipo="normal"):
            if tipo == "check":
                it = menu.AppendCheckItem(wx.ID_ANY, rotulo)
            elif tipo == "radio":
                it = menu.AppendRadioItem(wx.ID_ANY, rotulo)
            else:
                it = menu.Append(wx.ID_ANY, rotulo)
            self.itens[chave] = it
            return it

        m_arq = wx.Menu()
        item(m_arq, "anexar", "&Anexar arquivos...\tCtrl+O")
        m_arq.AppendSeparator()
        item(m_arq, "sair", "&Sair\tCtrl+Q")
        barra.Append(m_arq, "&Arquivo")

        m_conv = wx.Menu()
        item(m_conv, "ir_conv", "Ir para a lista de &conversas\tCtrl+1")
        item(m_conv, "ir_msgs", "Ir para a lista de &mensagens\tCtrl+2")
        item(m_conv, "ir_caixa", "Ir para a caixa de &digitação\tCtrl+3")
        m_conv.AppendSeparator()
        item(m_conv, "abrir_conv", "&Abrir a conversa selecionada")
        item(m_conv, "proxima", "Próxima conversa &não lida\tCtrl+U")
        item(m_conv, "ler_ultima", "&Ouvir a última mensagem\tCtrl+R")
        m_conv.AppendSeparator()
        item(m_conv, "simular", "&Simular mensagem nova\tCtrl+N")
        item(m_conv, "auto", "Simular mensagens &automáticas\tCtrl+T", "check")
        barra.Append(m_conv, "&Conversa")

        m_msg = wx.Menu()
        item(m_msg, "abrir", "&Abrir ou baixar mídia (Enter na lista)")
        item(m_msg, "responder", "&Responder\tCtrl+Shift+R")
        item(m_msg, "copiar", "&Copiar texto\tCtrl+Shift+C")
        item(m_msg, "detalhes", "&Detalhes\tAlt+Enter")
        barra.Append(m_msg, "&Mensagem")

        m_exib = wx.Menu()
        for est, nome in mc.NOMES_ESTILOS.items():
            it = item(m_exib, "estilo%d" % est, nome, "radio")
            self.Bind(wx.EVT_MENU,
                      lambda e, est=est: self._mudar_estilo(est), it)
        m_exib.AppendSeparator()
        item(m_exib, "som", "&Som ao receber mensagem", "check").Check(True)
        item(m_exib, "falar_novas", "&Falar mensagens novas", "check").Check(True)
        item(m_exib, "confirmar", "Confirmar envio por &voz", "check").Check(True)
        barra.Append(m_exib, "&Exibição")

        m_aj = wx.Menu()
        item(m_aj, "ajuda", "&Teclas de atalho\tF1")
        barra.Append(m_aj, "A&juda")
        self.SetMenuBar(barra)

        ligacoes = {
            "anexar": self._anexar_dialogo, "sair": lambda e: self.Close(),
            "ir_conv": lambda e: self._ir_para(self.lista_conv, "conversas"),
            "ir_msgs": lambda e: self._ir_para(self.lista_msgs, "mensagens"),
            "ir_caixa": lambda e: self._ir_para(self.caixa, "caixa"),
            "abrir_conv": lambda e: self._abrir_conversa(
                self.lista_conv.GetSelection()),
            "proxima": self._proxima_nao_lida, "ler_ultima": self._ler_ultima,
            "simular": lambda e: self._simular(), "auto": self._alternar_auto,
            "abrir": lambda e: self._abrir_selecionada(),
            "responder": lambda e: self._responder(),
            "copiar": lambda e: self._copiar(),
            "detalhes": lambda e: self._detalhes(),
            "ajuda": lambda e: self._ajuda(),
            "som": self._opcao("som"),
            "falar_novas": self._opcao("falar_novas"),
            "confirmar": self._opcao("confirmar_envio"),
        }
        for chave, tratador in ligacoes.items():
            self.Bind(wx.EVT_MENU, tratador, self.itens[chave])
        self.itens["estilo%d" % self.estilo].Check(True)

    def _criar_controles(self):
        painel = wx.Panel(self)
        rot_conv = wx.StaticText(painel, label="Conversas")
        self.lista_conv = wx.ListBox(painel, style=wx.LB_SINGLE | wx.LB_HSCROLL,
                                     name="Conversas")
        self.rot_msgs = wx.StaticText(painel, label="Mensagens")
        self.lista_msgs = wx.ListBox(painel, style=wx.LB_SINGLE | wx.LB_HSCROLL,
                                     name="Mensagens")
        rot_caixa = wx.StaticText(painel, label="Digite sua mensagem")
        self.caixa = wx.TextCtrl(painel, style=wx.TE_MULTILINE,
                                 name="Digite sua mensagem")
        self.botao_enviar = wx.Button(painel, label="&Enviar")
        self.botao_anexar = wx.Button(painel, label="Ane&xar")

        esq = wx.BoxSizer(wx.VERTICAL)
        esq.Add(rot_conv, 0, wx.BOTTOM, 4)
        esq.Add(self.lista_conv, 1, wx.EXPAND)
        dir_ = wx.BoxSizer(wx.VERTICAL)
        dir_.Add(self.rot_msgs, 0, wx.BOTTOM, 4)
        dir_.Add(self.lista_msgs, 3, wx.EXPAND)
        dir_.Add(rot_caixa, 0, wx.TOP | wx.BOTTOM, 4)
        dir_.Add(self.caixa, 1, wx.EXPAND)
        botoes = wx.BoxSizer(wx.HORIZONTAL)
        botoes.Add(self.botao_enviar, 0, wx.RIGHT, 6)
        botoes.Add(self.botao_anexar, 0)
        dir_.Add(botoes, 0, wx.TOP, 6)
        raiz = wx.BoxSizer(wx.HORIZONTAL)
        raiz.Add(esq, 1, wx.EXPAND | wx.ALL, 8)
        raiz.Add(dir_, 2, wx.EXPAND | wx.ALL, 8)
        painel.SetSizer(raiz)

        for ctrl, nome in ((self.lista_conv, "lista de conversas"),
                           (self.lista_msgs, "lista de mensagens"),
                           (self.caixa, "caixa de digitação"),
                           (self.botao_enviar, "botão Enviar"),
                           (self.botao_anexar, "botão Anexar")):
            ctrl.Bind(wx.EVT_SET_FOCUS,
                      lambda e, n=nome: self._foco(e, n))

        self.lista_conv.Bind(wx.EVT_KEY_DOWN, self._tecla_conversas)
        self.lista_conv.Bind(wx.EVT_LISTBOX_DCLICK, self._duplo_conversas)
        self.lista_msgs.Bind(wx.EVT_KEY_DOWN, self._tecla_mensagens)
        self.lista_msgs.Bind(wx.EVT_CONTEXT_MENU, self._menu_mensagem)
        self.caixa.Bind(wx.EVT_KEY_DOWN, self._tecla_caixa)
        self.botao_enviar.Bind(wx.EVT_BUTTON, lambda e: self._enviar_texto())
        self.botao_anexar.Bind(wx.EVT_BUTTON, self._anexar_dialogo)

    # --------------------------------------------------------------- inicio
    @seguro
    def _inicio(self):
        log("wxPython %s em %s" % (wx.version(), platform.platform()))
        log("NVDA em execucao: %s%s" % (
            self.fala.nvda_ativo(),
            "" if self.fala.nvda_ativo() else " (motivo: %s)" % (
                self.fala.motivo or "NVDA fechado")))
        self.fala.falar("Protótipo do TeleZapp aberto. Use Control 1, 2 ou 3 "
                        "para mudar de área, ou F1 para ver as teclas.")
        self.lista_conv.SetFocus()

    def _nome_do_foco(self):
        foco = self.FindFocus()
        for ctrl, nome in ((self.lista_conv, "lista de conversas"),
                           (self.lista_msgs, "lista de mensagens"),
                           (self.caixa, "caixa de digitação")):
            if foco is ctrl:
                return nome
        return "outro controle"

    @seguro
    def _char_hook(self, evt):
        """Trata Enter e Control V antes dos controles, que nem sempre
        entregam essas teclas (o wxPython no Windows as usa para navegar)."""
        k = evt.GetKeyCode()
        foco = self.FindFocus()
        sem_modificador = not (evt.AltDown() or evt.ControlDown()
                               or evt.ShiftDown())
        if k in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and sem_modificador:
            log("tecla: Enter (foco: %s)" % self._nome_do_foco())
            if foco is self.lista_conv:
                self._abrir_conversa(self.lista_conv.GetSelection())
                return
            if foco is self.lista_msgs:
                self._abrir_selecionada()
                return
            if foco is self.caixa:
                self._enviar_texto()
                return
        if evt.ControlDown() and not evt.ShiftDown() and k == ord("V") \
                and foco is self.caixa:
            arquivos = self._arquivos_da_area_de_transferencia()
            if arquivos:
                log("acao: colagem de %d arquivo(s) na caixa" % len(arquivos))
                self._enviar_arquivos(arquivos)
                return
        evt.Skip()

    @seguro
    def _foco(self, evt, nome):
        log("foco: " + nome)
        evt.Skip()

    # ------------------------------------------------------------- conversas
    def _preencher_conversas(self):
        self.lista_conv.Set([mc.rotulo_conversa(c) for c in self.conversas])

    def _atualizar_rotulo(self, i):
        self.lista_conv.SetString(i, mc.rotulo_conversa(self.conversas[i]))

    @seguro
    def _tecla_conversas(self, evt):
        if evt.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._abrir_conversa(self.lista_conv.GetSelection())
            return
        evt.Skip()

    @seguro
    def _duplo_conversas(self, evt):
        self._abrir_conversa(self.lista_conv.GetSelection())

    def _abrir_conversa(self, i):
        if i is None or i < 0:
            log("aviso: Enter na lista de conversas sem item selecionado "
                "(GetSelection=%s)" % i)
            self.fala.falar("Nenhuma conversa selecionada.")
            return
        self.atual = i
        conv = self.conversas[i]
        lidas = conv.nao_lidas
        conv.nao_lidas = 0
        self._atualizar_rotulo(i)
        self.rot_msgs.SetLabel("Mensagens de " + conv.nome)
        self.SetTitle("TeleZapp, protótipo: " + conv.nome)
        self._preencher_mensagens(selecionar_ultima=True)
        self.SetStatusText("Conversa aberta: %s, %s" % (conv.nome, conv.provedor))
        log("acao: conversa aberta (indice %d, %d mensagens, %d nao lidas)" % (
            i, len(conv.mensagens), lidas))
        self.lista_msgs.SetFocus()

    def _preencher_mensagens(self, selecionar_ultima=False):
        conv = self.conversas[self.atual]
        linhas = mc.formatar_lista(conv.mensagens, self.estilo)
        antes = self.lista_msgs.GetSelection()
        if not linhas:
            self.lista_msgs.Set([TEXTO_SEM_MENSAGENS])
            self.lista_msgs.SetSelection(0)
            return
        self.lista_msgs.Set(linhas)
        if linhas:
            if selecionar_ultima or antes < 0:
                self.lista_msgs.SetSelection(len(linhas) - 1)
            else:
                self.lista_msgs.SetSelection(min(antes, len(linhas) - 1))

    def _mensagem_selecionada(self):
        if self.atual is None:
            return None
        i = self.lista_msgs.GetSelection()
        msgs = self.conversas[self.atual].mensagens
        return msgs[i] if 0 <= i < len(msgs) else None

    # --------------------------------------------------------------- atalhos
    @seguro
    def _ir_para(self, controle, nome):
        log("atalho: ir para " + nome)
        controle.SetFocus()

    @seguro
    def _proxima_nao_lida(self, evt):
        n = len(self.conversas)
        inicio = (self.lista_conv.GetSelection() + 1) if \
            self.lista_conv.GetSelection() >= 0 else 0
        for k in range(n):
            i = (inicio + k) % n
            if self.conversas[i].nao_lidas > 0:
                self.lista_conv.SetSelection(i)
                self.lista_conv.SetFocus()
                log("atalho: proxima conversa nao lida (indice %d)" % i)
                return
        self.fala.falar("Nenhuma conversa com mensagens não lidas.")
        bipe("erro")
        log("atalho: proxima nao lida, mas nao ha nenhuma")

    @seguro
    def _ler_ultima(self, evt):
        if self.atual is None:
            self.fala.falar("Nenhuma conversa aberta. Aperte Enter numa conversa.")
            return
        msgs = self.conversas[self.atual].mensagens
        if not msgs:
            self.fala.falar("A conversa não tem mensagens.")
            return
        texto = mc.formatar(msgs[-1], mc.ESTILO_AUTOR_PRIMEIRO)
        log("atalho: ouvir a ultima mensagem (tamanho %d)" % len(texto))
        if not self.fala.falar(texto, interromper=True):
            log("fala indisponivel: %s" % (self.fala.motivo or "NVDA fechado"))

    @seguro
    def _mudar_estilo(self, estilo):
        self.estilo = estilo
        log("exibicao: estilo %d (%s)" % (estilo, mc.NOMES_ESTILOS[estilo]))
        if self.atual is not None:
            self._preencher_mensagens()
        self.fala.falar("Estilo: " + mc.NOMES_ESTILOS[estilo])

    def _opcao(self, chave):
        @seguro
        def tratador(self_, evt):
            self.opcoes[chave] = evt.IsChecked()
            log("opcao %s = %s" % (chave, evt.IsChecked()))
        return lambda e: tratador(self, e)

    # ----------------------------------------------------- mensagens: acoes
    @seguro
    def _tecla_mensagens(self, evt):
        if evt.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and \
                not evt.AltDown():
            self._abrir_selecionada()
            return
        evt.Skip()

    @seguro
    def _menu_mensagem(self, evt):
        m = self._mensagem_selecionada()
        if m is None:
            return
        log("acao: menu de contexto da mensagem")
        menu = wx.Menu()
        for rotulo, tratador in (
                ("Abrir ou baixar mídia", self._abrir_selecionada),
                ("Responder", self._responder),
                ("Copiar texto", self._copiar),
                ("Detalhes", self._detalhes)):
            it = menu.Append(wx.ID_ANY, rotulo)
            self.Bind(wx.EVT_MENU, lambda e, t=tratador: t(), it)
        pos = evt.GetPosition()
        if pos == wx.DefaultPosition:
            self.lista_msgs.PopupMenu(menu, wx.Point(20, 20))
        else:
            self.lista_msgs.PopupMenu(menu, self.lista_msgs.ScreenToClient(pos))
        menu.Destroy()

    @seguro
    def _abrir_selecionada(self):
        m = self._mensagem_selecionada()
        if m is None:
            return
        if m.tipo == "texto":
            log("acao: Enter em mensagem de texto -> detalhes")
            self._detalhes()
            return
        nome = {"foto": "foto", "video": "vídeo", "voz": "mensagem de voz",
                "audio": "áudio", "documento": "documento"}[m.tipo]
        log("acao: abrir midia (%s)" % m.tipo)
        self.fala.falar("Baixando %s." % nome, interromper=True)
        if m.tipo in ("voz", "audio"):
            wx.CallLater(800, lambda: (bipe("enviada"), self.fala.falar(
                "Reproduzindo %s, simulado." % nome)))
        else:
            wx.CallLater(800, lambda: self.fala.falar(
                "%s baixado. Abriria no programa padrão, simulado." %
                nome.capitalize()))

    @seguro
    def _responder(self):
        m = self._mensagem_selecionada()
        if m is None:
            return
        self.resposta_a = m
        autor = "você" if m.minha else m.autor
        log("acao: responder (tipo %s)" % m.tipo)
        self.fala.falar("Respondendo a %s. Digite sua resposta." % autor)
        self.SetStatusText("Respondendo a " + autor)
        self.caixa.SetFocus()

    @seguro
    def _copiar(self):
        m = self._mensagem_selecionada()
        if m is None:
            return
        texto = m.texto or mc.conteudo(m)
        if wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(wx.TextDataObject(texto))
            finally:
                wx.TheClipboard.Close()
        log("acao: copiar texto (%d caracteres)" % len(texto))
        self.fala.falar("Texto copiado.")

    @seguro
    def _detalhes(self):
        m = self._mensagem_selecionada()
        if m is None:
            return
        log("acao: detalhes da mensagem (tipo %s)" % m.tipo)
        self._dialogo_texto(
            "Detalhes da mensagem",
            mc.detalhes(m, self.conversas[self.atual].nome),
            "Detalhes e texto completo")

    @seguro
    def _ajuda(self):
        log("acao: ajuda de teclas")
        self._dialogo_texto("Teclas de atalho", AJUDA, "Teclas de atalho")

    def _dialogo_texto(self, titulo, texto, rotulo):
        dlg = wx.Dialog(self, title=titulo,
                        style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
                        size=(620, 460))
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

    # ---------------------------------------------------------------- envio
    @seguro
    def _tecla_caixa(self, evt):
        k = evt.GetKeyCode()
        if k in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and not evt.ShiftDown() \
                and not evt.ControlDown():
            self._enviar_texto()
            return
        if evt.ControlDown() and k == ord("V"):
            arquivos = self._arquivos_da_area_de_transferencia()
            if arquivos:
                log("acao: colagem de %d arquivo(s) na caixa" % len(arquivos))
                self._enviar_arquivos(arquivos)
                return
        evt.Skip()

    @staticmethod
    def _arquivos_da_area_de_transferencia():
        arquivos = []
        if wx.TheClipboard.Open():
            try:
                dados = wx.FileDataObject()
                if wx.TheClipboard.GetData(dados):
                    arquivos = list(dados.GetFilenames())
            finally:
                wx.TheClipboard.Close()
        return arquivos

    def _hora(self):
        return time.strftime("%H:%M")

    def _exigir_conversa(self):
        if self.atual is None:
            self.fala.falar("Nenhuma conversa aberta. Aperte Enter numa conversa.")
            bipe("erro")
            log("aviso: tentou enviar sem conversa aberta")
            return False
        return True

    def _anexar_mensagem(self, m):
        conv = self.conversas[self.atual]
        conv.mensagens.append(m)
        self._preencher_mensagens()

    @seguro
    def _enviar_texto(self):
        if not self._exigir_conversa():
            return
        texto = self.caixa.GetValue().strip()
        if not texto:
            bipe("erro")
            log("aviso: envio com caixa vazia")
            return
        if self.resposta_a is not None:
            autor = "você" if self.resposta_a.minha else self.resposta_a.autor
            texto = "Em resposta a %s: %s" % (autor, texto)
            self.resposta_a = None
        self._anexar_mensagem(mc.Mensagem(
            "", self._hora(), "texto", texto, minha=True, estado="enviada"))
        self.caixa.Clear()
        self.SetStatusText("Mensagem enviada (simulado)")
        log("acao: texto enviado (simulado, %d caracteres)" % len(texto))
        bipe("enviada")
        if self.opcoes["confirmar_envio"]:
            self.fala.falar("Enviada.")

    @seguro
    def _anexar_dialogo(self, evt):
        if not self._exigir_conversa():
            return
        dlg = wx.FileDialog(self, "Escolha os arquivos para anexar",
                            style=wx.FD_OPEN | wx.FD_MULTIPLE | wx.FD_FILE_MUST_EXIST)
        try:
            if dlg.ShowModal() == wx.ID_OK:
                self._enviar_arquivos(dlg.GetPaths())
            else:
                log("acao: anexar cancelado")
        finally:
            dlg.Destroy()

    def _enviar_arquivos(self, caminhos):
        if not self._exigir_conversa():
            return
        for c in caminhos:
            try:
                tamanho = os.path.getsize(c)
            except OSError:
                tamanho = 0
            tipo = mc.classificar_arquivo(c)
            self._anexar_mensagem(mc.Mensagem(
                "", self._hora(), tipo, "", 0,
                os.path.basename(c), tamanho, minha=True, estado="enviada"))
            log("acao: anexo simulado (tipo %s, extensao %s, %d bytes)" % (
                tipo, os.path.splitext(c)[1].lower() or "-", tamanho))
        bipe("enviada")
        self.fala.falar("%d arquivo%s anexado%s, simulado." % (
            len(caminhos), "" if len(caminhos) == 1 else "s",
            "" if len(caminhos) == 1 else "s"))

    # ------------------------------------------------------ mensagens novas
    @seguro
    def _alternar_auto(self, evt):
        if evt.IsChecked():
            self.timer.Start(INTERVALO_AUTOMATICO_MS)
            log("opcao: mensagens simuladas automaticas LIGADAS")
            self.fala.falar("Mensagens simuladas automáticas ligadas.")
        else:
            self.timer.Stop()
            log("opcao: mensagens simuladas automaticas desligadas")
            self.fala.falar("Mensagens simuladas automáticas desligadas.")

    @seguro
    def _ao_timer(self, evt):
        self._simular()

    @seguro
    def _simular(self):
        self.contador_sim += 1
        n = self.contador_sim
        # alterna: conversa aberta (se houver) e outras conversas
        if self.atual is not None and n % 2 == 1:
            i = self.atual
        else:
            candidatas = [k for k in range(len(self.conversas))
                          if k != self.atual]
            i = candidatas[n % len(candidatas)]
        conv = self.conversas[i]
        m = mc.mensagem_simulada(conv, n, self._hora())
        conv.mensagens.append(m)
        foco = self.FindFocus()
        no_foco_msgs = foco is self.lista_msgs
        if i == self.atual:
            self._preencher_mensagens()
            resumo = mc.formatar(m, mc.ESTILO_AUTOR_PRIMEIRO)
            aviso = "Nova mensagem. " + resumo
        else:
            conv.nao_lidas += 1
            self._atualizar_rotulo(i)
            aviso = "Nova mensagem em %s. %s" % (
                conv.nome, mc.formatar(m, mc.ESTILO_AUTOR_PRIMEIRO))
        log("acao: mensagem simulada (conversa %d, tipo %s, aberta=%s, "
            "foco nas mensagens=%s)" % (i, m.tipo, i == self.atual, no_foco_msgs))
        if self.opcoes["som"]:
            bipe("nova")
        if self.opcoes["falar_novas"]:
            if not self.fala.falar(aviso):
                log("fala indisponivel: %s" % (self.fala.motivo or "NVDA fechado"))
        self.SetStatusText(aviso[:120])

    # ---------------------------------------------------------------- saida
    def _ao_fechar(self, evt):
        log("fechou a janela")
        try:
            self.timer.Stop()
        finally:
            self.Destroy()


def main():
    log("==== prototipo da interface (wxPython) ====")
    log("python %s em %s" % (sys.version.split()[0], platform.platform()))
    try:
        app = wx.App(False)
        janela = Janela()
        janela.Show()
        app.MainLoop()
        log("RESULTADO: o prototipo foi fechado normalmente")
        return 0
    except Exception:
        log("ERRO:\n" + traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())

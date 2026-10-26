# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Leitores de midia dentro do app: imagem, audio, video e texto.

Tudo abre numa janela do proprio TeleZapp, a partir do arquivo guardado na
pasta de dados do app. Documentos que o app nao sabe mostrar tem um botao
explicito para abrir com o programa do Windows.
"""
import logging
import os
import shutil

import wx

from telezapp import NOME
from telezapp.midia.reprodutor import (FormatoNaoSuportado, Reprodutor,
                                       formatar_tempo)
from telezapp.midia import velocidade as vel
from telezapp.nucleo import modelos as m

try:
    import wx.media as wxmedia
except ImportError:      # testes sem wxPython
    wxmedia = None

log = logging.getLogger("telezapp.visualizadores")

EXT_TEXTO = {".txt", ".md", ".log", ".csv", ".json", ".xml", ".ini", ".srt",
             ".html", ".htm"}
LIMITE_TEXTO = 2 * 1024 * 1024
PULO_CURTO, PULO_LONGO = 5, 30

IMAGEM, AUDIO, VIDEO, TEXTO, DOCUMENTO = ("imagem", "audio", "video",
                                           "texto", "documento")


def escolher(tipo, caminho):
    """Qual leitor abre este arquivo."""
    ext = os.path.splitext(caminho)[1].lower()
    if tipo in (m.FOTO, m.FIGURINHA) or ext in m.EXT_FOTO:
        return IMAGEM
    if tipo in (m.VOZ, m.AUDIO) or ext in m.EXT_AUDIO:
        return AUDIO
    if tipo == m.VIDEO or ext in m.EXT_VIDEO:
        return VIDEO
    try:
        pequeno = os.path.getsize(caminho) <= LIMITE_TEXTO
    except OSError:
        pequeno = False
    if ext in EXT_TEXTO and pequeno:
        return TEXTO
    return DOCUMENTO


def descricao(msg, nome_conversa=""):
    autor = "Você" if msg.minha else (msg.autor or "Desconhecido")
    partes = ["%s, %s" % (autor, m.hora_legivel(msg.data)),
              m.conteudo(msg)]
    if nome_conversa:
        partes.insert(0, "Conversa: " + nome_conversa)
    return "\n".join(p for p in partes if p)


def nome_para_salvar(msg, caminho):
    if msg.nome_arquivo:
        return msg.nome_arquivo
    nome = os.path.basename(caminho)
    return nome.split("_", 1)[1] if "_" in nome else nome


# ------------------------------------------------------------ dispatcher
def abrir(pai, msg, caminho, fala, nome_conversa="", cfg=None):
    """Mostra a midia no leitor certo; volta quando a janela fecha. `cfg`
    guarda a velocidade do audio entre uma vez e outra."""
    kind = escolher(msg.tipo, caminho)
    texto = descricao(msg, nome_conversa)
    try:
        if kind == IMAGEM:
            _imagem(pai, msg, caminho, texto, fala)
        elif kind == AUDIO:
            try:
                motor = Reprodutor(caminho)
            except FormatoNaoSuportado:
                _reproducao(pai, msg, caminho, texto, fala, None, False,
                            cfg)
            else:
                _reproducao(pai, msg, caminho, texto, fala, motor, False,
                            cfg)
        elif kind == VIDEO:
            _reproducao(pai, msg, caminho, texto, fala, None, True, cfg)
        elif kind == TEXTO:
            _texto(pai, msg, caminho, texto)
        else:
            _documento(pai, msg, caminho, texto)
    except Exception:
        log.exception("erro ao abrir a mídia")
        wx.MessageBox("Não foi possível abrir esta mídia. Os detalhes estão "
                      "no log.", NOME, wx.OK | wx.ICON_WARNING, pai)


def salvar_copia(pai, msg, caminho, fala=None):
    dlg = wx.FileDialog(pai, "Salvar a mídia em um arquivo",
                        defaultFile=nome_para_salvar(msg, caminho),
                        style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return False
        shutil.copy2(caminho, dlg.GetPath())
    finally:
        dlg.Destroy()
    if fala is not None:
        fala.falar("Cópia salva.")
    return True


def _janela(pai, titulo, descricao_, botoes_extra=(), corpo=None,
            rotulo="Descrição"):
    """Dialogo padrao: texto somente leitura com o foco (o leitor de tela
    fala o conteudo ao abrir), corpo opcional e botoes."""
    dlg = wx.Dialog(pai, title=titulo, size=(700, 520),
                    style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    caixa = wx.TextCtrl(dlg, value=descricao_, name=rotulo,
                        style=wx.TE_MULTILINE | wx.TE_READONLY)
    lay = wx.BoxSizer(wx.VERTICAL)
    lay.Add(caixa, 1, wx.EXPAND | wx.ALL, 8)
    if corpo is not None:
        lay.Add(corpo(dlg), 0, wx.ALL | wx.ALIGN_CENTER, 8)
    linha = wx.BoxSizer(wx.HORIZONTAL)
    for rotulo_botao, acao in botoes_extra:
        b = wx.Button(dlg, wx.ID_ANY, rotulo_botao)
        dlg.Bind(wx.EVT_BUTTON, lambda e, a=acao: a(dlg), b)
        linha.Add(b, 0, wx.RIGHT, 8)
    fechar = wx.Button(dlg, wx.ID_OK, "&Fechar")
    fechar.SetDefault()
    linha.Add(fechar, 0)
    lay.Add(linha, 0, wx.ALL | wx.ALIGN_RIGHT, 8)
    dlg.SetSizer(lay)
    dlg.SetEscapeId(wx.ID_OK)
    caixa.SetFocus()
    return dlg


# ---------------------------------------------------------------- imagem
def _carregar_imagem(caminho):
    img = wx.Image(caminho)
    if img.IsOk():
        return img
    try:   # formatos que o wx nao le (ex.: webp em algumas versoes)
        from PIL import Image
        im = Image.open(caminho).convert("RGB")
        return wx.Image(im.width, im.height, im.tobytes())
    except Exception:
        return None


def _imagem(pai, msg, caminho, texto, fala):
    img = _carregar_imagem(caminho)
    if img is None:
        _documento(pai, msg, caminho, texto + "\n\nEste formato de imagem "
                   "não pôde ser mostrado dentro do app.")
        return
    l, a = img.GetWidth(), img.GetHeight()
    texto += "\nImagem de %d por %d pixels." % (l, a)
    escala = min(1.0, 900.0 / l, 560.0 / a)
    if escala < 1.0:
        img = img.Scale(max(1, int(l * escala)), max(1, int(a * escala)),
                        wx.IMAGE_QUALITY_HIGH)
    dlg = _janela(
        pai, "Imagem", texto, rotulo="Imagem",
        botoes_extra=(("&Salvar em um arquivo...",
                       lambda d: salvar_copia(d, msg, caminho, fala)),),
        corpo=lambda d: wx.StaticBitmap(d, bitmap=wx.Bitmap(img)))
    dlg.ShowModal()
    dlg.Destroy()


# ----------------------------------------------------- texto e documento
def _texto(pai, msg, caminho, texto):
    with open(caminho, "rb") as f:
        bruto = f.read(LIMITE_TEXTO)
    try:
        conteudo = bruto.decode("utf-8")
    except UnicodeDecodeError:
        conteudo = bruto.decode("latin-1")
    dlg = _janela(pai, "Documento", texto + "\n\n" + conteudo,
                  rotulo="Texto do documento",
                  botoes_extra=(("&Salvar em um arquivo...",
                                 lambda d: salvar_copia(d, msg, caminho)),))
    dlg.ShowModal()
    dlg.Destroy()


def _abrir_no_windows(caminho):
    if os.name == "nt":
        os.startfile(caminho)


def _documento(pai, msg, caminho, texto):
    aviso = ("\n\nO TeleZapp não mostra este tipo de arquivo dentro do app. "
             "O botão Abrir com o programa do Windows usa o programa que o "
             "Windows tem para ele; o arquivo continua guardado na pasta do "
             "TeleZapp.")
    dlg = _janela(
        pai, "Documento", texto + aviso, rotulo="Documento",
        botoes_extra=(
            ("&Abrir com o programa do Windows",
             lambda d: _abrir_no_windows(caminho)),
            ("&Salvar em um arquivo...",
             lambda d: salvar_copia(d, msg, caminho))))
    dlg.ShowModal()
    dlg.Destroy()


# ------------------------------------------------------ audio e video
class _MotorMediaCtrl:
    """Mesma interface do Reprodutor, sobre o wx.media.MediaCtrl do Windows
    (video, e audio que a libsndfile nao abre)."""
    def __init__(self, ctrl):
        self.ctrl = ctrl
        self.terminou = False
        self._velocidade = 1.0

    @property
    def duracao(self):
        return max(0, self.ctrl.Length()) / 1000.0

    @property
    def posicao(self):
        return max(0, self.ctrl.Tell()) / 1000.0

    @property
    def tocando(self):
        return self.ctrl.GetState() == wxmedia.MEDIASTATE_PLAYING

    def tocar(self):
        self.terminou = False
        self.ctrl.Play()

    def pausar(self):
        self.ctrl.Pause()

    def alternar(self):
        if self.tocando:
            self.pausar()
        else:
            self.tocar()

    def ir_para(self, segundos):
        limite = self.duracao
        self.ctrl.Seek(int(max(0.0, min(segundos, limite)) * 1000))

    def avancar(self, delta):
        self.ir_para(self.posicao + delta)

    @property
    def velocidade(self):
        return self._velocidade

    @velocidade.setter
    def velocidade(self, valor):
        """O MediaCtrl do Windows muda o ritmo como o codec permitir (o tom
        pode acompanhar)."""
        self._velocidade = float(valor)
        try:
            self.ctrl.SetPlaybackRate(self._velocidade)
        except Exception:
            pass

    def fechar(self):
        try:
            self.ctrl.Stop()
        except Exception:
            pass


def _reproducao(pai, msg, caminho, texto, fala, motor, video, cfg=None):
    """motor: Reprodutor pronto, ou None para usar o MediaCtrl do Windows."""
    estado = {"motor": motor, "ctrl": None}
    rotulo = "Vídeo" if video else "Áudio"

    def corpo(dlg):
        if motor is not None:
            return wx.StaticText(dlg, label="")
        tam = (480, 270) if video else (1, 1)
        ctrl = wxmedia.MediaCtrl(dlg, size=tam, style=wx.SIMPLE_BORDER)
        estado["ctrl"] = ctrl
        estado["motor"] = _MotorMediaCtrl(ctrl)
        return ctrl

    dlg = _janela(
        pai, rotulo, texto, rotulo=rotulo, corpo=corpo,
        botoes_extra=())
    ctrl = estado["ctrl"]
    mo = estado["motor"]
    posicao = wx.StaticText(dlg, label="")
    botao = wx.Button(dlg, wx.ID_ANY, "&Tocar")
    barra = wx.BoxSizer(wx.HORIZONTAL)
    barra.Add(posicao, 1, wx.ALIGN_CENTER | wx.RIGHT, 8)
    barra.Add(botao, 0, wx.RIGHT, 8)
    for texto_b, delta in (("&Voltar %d s" % PULO_CURTO, -PULO_CURTO),
                           ("&Avançar %d s" % PULO_CURTO, PULO_CURTO)):
        b = wx.Button(dlg, wx.ID_ANY, texto_b)
        dlg.Bind(wx.EVT_BUTTON, lambda e, d=delta: pular(d), b)
        barra.Add(b, 0, wx.RIGHT, 8)
    inicio = wx.Button(dlg, wx.ID_ANY, "&Início")
    dlg.Bind(wx.EVT_BUTTON, lambda e: (mo.ir_para(0), dizer()), inicio)
    barra.Add(inicio, 0, wx.RIGHT, 8)
    for texto_b, direcao in (("Mais &rápido", +1), ("Mais le&nto", -1)):
        b = wx.Button(dlg, wx.ID_ANY, texto_b)
        dlg.Bind(wx.EVT_BUTTON, lambda e, d=direcao: mudar_velocidade(d), b)
        barra.Add(b, 0, wx.RIGHT, 8)
    dlg.GetSizer().Insert(2, barra, 0, wx.EXPAND | wx.ALL, 8)
    dlg.Layout()

    def passo_atual():
        return vel.passo_valido(cfg.get("audio_passo_velocidade")) \
            if cfg is not None else vel.PASSO_PADRAO

    def mudar_velocidade(direcao):
        atual = getattr(mo, "velocidade", 1.0)
        novo = vel.proxima(atual, passo_atual(), direcao)
        mo.velocidade = novo
        if cfg is not None:
            cfg.set("audio_velocidade", novo)
        atualizar_rotulo()
        fala.falar("Velocidade %s" % vel.rotulo(novo), interromper=True)

    if cfg is not None and not video:
        mo.velocidade = vel.ajustar(cfg.get("audio_velocidade"),
                                    passo_atual())

    def dizer():
        fala.falar("%s de %s" % (formatar_tempo(mo.posicao),
                                 formatar_tempo(mo.duracao)),
                   interromper=True)

    def pular(delta):
        mo.avancar(delta)
        dizer()

    def atualizar_rotulo():
        botao.SetLabel("&Pausar" if mo.tocando else "&Tocar")
        extra = ""
        if getattr(mo, "velocidade", 1.0) != 1.0:
            extra = ", " + vel.rotulo(mo.velocidade)
        posicao.SetLabel("%s de %s%s" % (formatar_tempo(mo.posicao),
                                         formatar_tempo(mo.duracao), extra))

    pausou = [False]
    tentativas = [0]
    progrediu = [False]

    def alternar(evt=None):
        pausou[0] = mo.tocando      # apertou com ele tocando: e uma pausa
        mo.alternar()
        atualizar_rotulo()
        fala.falar("Tocando" if mo.tocando else "Pausado", interromper=True)

    dlg.Bind(wx.EVT_BUTTON, alternar, botao)

    def tecla(evt):
        k = evt.GetKeyCode()
        passo = PULO_LONGO if evt.ShiftDown() else PULO_CURTO
        if k == wx.WXK_SPACE and not isinstance(dlg.FindFocus(), wx.Button):
            alternar()
        elif k == wx.WXK_LEFT:
            pular(-passo)
        elif k == wx.WXK_RIGHT:
            pular(passo)
        elif k == wx.WXK_HOME:
            mo.ir_para(0)
            dizer()
        elif k in (ord("+"), ord("="), wx.WXK_ADD, wx.WXK_NUMPAD_ADD):
            mudar_velocidade(+1)
        elif k in (ord("-"), wx.WXK_SUBTRACT, wx.WXK_NUMPAD_SUBTRACT):
            mudar_velocidade(-1)
        else:
            evt.Skip()
    dlg.Bind(wx.EVT_CHAR_HOOK, tecla)

    relogio = wx.Timer(dlg)
    anterior = {"tocando": False}

    def tique(evt):
        if ctrl is not None and not iniciou[0] and mo.duracao > 0:
            comecar()          # o aviso de "carregou" nao chegou: toca assim
        tocando = mo.tocando
        if tocando or mo.posicao > 0:
            progrediu[0] = True     # o video chegou a andar
        if ctrl is not None and progrediu[0] and not tocando and \
                not pausou[0] and not mo.terminou and mo.posicao == 0:
            mo.terminou = True      # acabou e o Windows voltou ao inicio
        if ctrl is not None and iniciou[0] and not tocando and \
                not progrediu[0] and not mo.terminou and not pausou[0] \
                and tentativas[0] < 3:
            tentativas[0] += 1      # o Windows ignorou o primeiro Play
            mo.tocar()
            tocando = True
        if anterior["tocando"] and not tocando and \
                (mo.terminou or mo.posicao >= mo.duracao > 0):
            fala.falar("Fim.", interromper=True)
        anterior["tocando"] = tocando
        atualizar_rotulo()
    dlg.Bind(wx.EVT_TIMER, tique, relogio)

    iniciou = [False]

    def comecar():
        if iniciou[0]:
            return
        iniciou[0] = True
        mo.tocar()
        anterior["tocando"] = True
        atualizar_rotulo()
        if video:
            fala.falar("Tocando", interromper=True)
        else:
            v = vel.rotulo(mo.velocidade) if mo.velocidade != 1.0 else ""
            texto = m.anuncio_reproducao(
                msg, v, detalhado=bool(cfg.get("falar_quem_toca"))
                if cfg is not None else True)
            if texto:
                fala.falar(texto, interromper=True)

    def iniciar():
        """Depois da janela aparecer: o MediaCtrl so carrega visivel."""
        if ctrl is not None:
            if not ctrl.Load(caminho):
                wx.MessageBox(
                    "O Windows não conseguiu reproduzir este arquivo dentro "
                    "do app (pode faltar o codec). Use Salvar a mídia em um arquivo, no "
                    "menu Mensagem, se quiser abri-lo em outro "
                    "programa.", NOME, wx.OK | wx.ICON_WARNING, dlg)
                dlg.EndModal(wx.ID_CANCEL)
            return
        comecar()

    if ctrl is not None:

        def carregou(evt):
            comecar()

        def acabou(evt):
            mo.terminou = True
        dlg.Bind(wxmedia.EVT_MEDIA_LOADED, carregou)
        dlg.Bind(wxmedia.EVT_MEDIA_FINISHED, acabou)
    atualizar_rotulo()
    relogio.Start(300)
    wx.CallAfter(iniciar)
    try:
        dlg.ShowModal()
    finally:
        relogio.Stop()
        mo.fechar()
        dlg.Destroy()

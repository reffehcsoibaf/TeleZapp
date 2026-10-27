# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela da chamada de voz, com controles nativos lidos pelo NVDA.

Uma janela so, que muda de estado: tocando (Atender e Recusar), chamando e
conectando (Desligar), em chamada (Silenciar, Tempo e Desligar) e
encerrada (Fechar). O que mostrar e falar vem de `nucleo.chamadas`; esta
janela so desenha. O foco sempre vai para o botao que a pessoa mais
provavelmente quer: Atender ao tocar, Desligar nos outros estados.

Esc recusa ou cancela enquanto ainda nao ha conversa; depois de conectada,
Esc nao desliga (e facil apertar sem querer): so lembra do botao.
"""
import wx

from telezapp.midia.dispositivos import parecem_o_mesmo
from telezapp.nucleo import chamadas as ch


LARGURA_VIDEO, ALTURA_VIDEO = 640, 360


class VistaVideo(wx.Panel):
    """Mostra o ultimo quadro do video do outro lado."""

    def __init__(self, pai, nome):
        super().__init__(pai, size=(LARGURA_VIDEO, ALTURA_VIDEO), name=nome)
        self.SetMinSize((LARGURA_VIDEO, ALTURA_VIDEO))
        self._imagem = None
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self._pintar)

    def mostrar(self, largura, altura, rgb):
        self._imagem = wx.Bitmap.FromBuffer(largura, altura, rgb)
        self.Refresh(False)

    def _pintar(self, _evt):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.BLACK_BRUSH)
        dc.Clear()
        if self._imagem is not None:
            larg, alt = self.GetClientSize()
            dc.DrawBitmap(self._imagem,
                          max(0, (larg - self._imagem.GetWidth()) // 2),
                          max(0, (alt - self._imagem.GetHeight()) // 2))


class DialogoChamada(wx.Dialog):
    def __init__(self, pai, chamada, acoes, falar, microfones=(), saidas=(),
                 microfone="", saida="", ao_fechar=None, cameras=(),
                 camera=""):
        """acoes: dict com atender(), recusar(), desligar(), silenciar(bool),
        tempo(), trocar(microfone, saida), camera() e trocar_camera(nome).
        `falar(texto)` fala sem interromper o que ja esta sendo dito."""
        super().__init__(pai, title="Chamada", style=wx.DEFAULT_DIALOG_STYLE)
        self.chamada = chamada
        self.acoes = acoes
        self.falar = falar
        self._ao_fechar_cb = ao_fechar
        self.situacao = wx.StaticText(self, label="", name="Situação")
        self.b_atender = wx.Button(self, wx.ID_ANY, "&Atender")
        self.b_silenciar = wx.Button(self, wx.ID_ANY, "&Silenciar o microfone")
        self.b_tempo = wx.Button(self, wx.ID_ANY, "&Tempo de chamada")
        self.b_recusar = wx.Button(self, wx.ID_ANY, "&Recusar")
        self.b_desligar = wx.Button(self, wx.ID_ANY, "&Desligar")
        self.b_fechar = wx.Button(self, wx.ID_ANY, "&Fechar")
        self.b_camera = wx.Button(self, wx.ID_ANY, "Ligar a &câmera")
        self.botoes = {
            ch.ATENDER: self.b_atender, ch.SILENCIAR: self.b_silenciar,
            ch.CAMERA: self.b_camera,
            ch.TEMPO: self.b_tempo, ch.RECUSAR: self.b_recusar,
            ch.DESLIGAR: self.b_desligar, ch.FECHAR: self.b_fechar}
        self.vista = None               # VistaVideo, criada com o 1o quadro
        self.cameras = list(cameras)
        self.rot_camera = wx.StaticText(self, label="Câ&mera:")
        self.escolha_camera = wx.Choice(self, choices=self.cameras,
                                        name="Câmera")
        if self.cameras:
            self.escolha_camera.SetSelection(next(
                (n for n, d in enumerate(self.cameras) if d == camera), 0))

        self.microfones, self.saidas = list(microfones), list(saidas)
        self.rot_mic = wx.StaticText(self, label="Mi&crofone:")
        self.escolha_mic = wx.Choice(self, choices=self.microfones,
                                     name="Microfone")
        self.rot_saida = wx.StaticText(self, label="Saída de &som:")
        self.escolha_saida = wx.Choice(self, choices=self.saidas,
                                       name="Saída de som")
        for escolha, lista, nome in ((self.escolha_mic, self.microfones,
                                      microfone),
                                     (self.escolha_saida, self.saidas,
                                      saida)):
            if lista:
                escolha.SetSelection(next(
                    (n for n, d in enumerate(lista)
                     if parecem_o_mesmo(nome, d)), 0))

        lay = wx.BoxSizer(wx.VERTICAL)
        lay.Add(self.situacao, 0, wx.ALL, 12)
        self.lay = lay
        linha = wx.BoxSizer(wx.HORIZONTAL)
        for b in self.botoes.values():
            linha.Add(b, 0, wx.RIGHT, 6)
        lay.Add(linha, 0, wx.ALL, 12)
        for rotulo, escolha in ((self.rot_mic, self.escolha_mic),
                                (self.rot_saida, self.escolha_saida)):
            lay.Add(rotulo, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
            lay.Add(escolha, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        lay.Add(self.rot_camera, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
        lay.Add(self.escolha_camera, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        self.SetSizer(lay)

        self.b_camera.Bind(wx.EVT_BUTTON, lambda e: acoes["camera"]())
        self.escolha_camera.Bind(wx.EVT_CHOICE, self._camera_escolhida)
        self.b_atender.Bind(wx.EVT_BUTTON, lambda e: acoes["atender"]())
        self.b_recusar.Bind(wx.EVT_BUTTON, lambda e: acoes["recusar"]())
        self.b_desligar.Bind(wx.EVT_BUTTON, lambda e: acoes["desligar"]())
        self.b_silenciar.Bind(wx.EVT_BUTTON, self._silenciar)
        self.b_tempo.Bind(wx.EVT_BUTTON, lambda e: acoes["tempo"]())
        self.b_fechar.Bind(wx.EVT_BUTTON, lambda e: self.fechar())
        self.escolha_mic.Bind(wx.EVT_CHOICE, self._dispositivo)
        self.escolha_saida.Bind(wx.EVT_CHOICE, self._dispositivo)
        self.Bind(wx.EVT_CHAR_HOOK, self._tecla)
        self.Bind(wx.EVT_CLOSE, self._ao_fechar)
        self.mostrar()

    # ------------------------------------------------------- desenho
    def mostrar(self):
        """Redesenha para o estado atual de `self.chamada`."""
        c = self.chamada
        a = ch.apresentar(c)
        self.SetTitle(a.titulo)
        self.situacao.SetLabel(a.situacao)
        visiveis = set(a.botoes)
        for nome, b in self.botoes.items():
            b.Show(nome in visiveis)
        self.b_silenciar.SetLabel(ch.rotulo_silenciar(c.mudo))
        self.b_camera.SetLabel(ch.rotulo_camera(c))
        mostrar_camera = c.suporta_video and bool(self.cameras) and \
            c.estado in (ch.CONECTANDO, ch.EM_CHAMADA)
        self.rot_camera.Show(mostrar_camera)
        self.escolha_camera.Show(mostrar_camera)
        mostrar_disp = c.estado in (ch.CONECTANDO, ch.EM_CHAMADA) and \
            bool(self.microfones or self.saidas)
        for w in (self.rot_mic, self.escolha_mic, self.rot_saida,
                  self.escolha_saida):
            w.Show(mostrar_disp)
        self.Layout()
        self.Fit()
        foco = self.botoes.get(a.foco)
        if foco is not None:
            foco.SetFocus()
            foco.SetDefault()
        return a

    # ------------------------------------------------------- acoes
    def _silenciar(self, _e=None):
        self.acoes["silenciar"](not self.chamada.mudo)

    def camera_escolhida(self):
        return self.escolha_camera.GetStringSelection() \
            if self.cameras else ""

    def _camera_escolhida(self, _e=None):
        self.acoes["trocar_camera"](self.camera_escolhida())

    def mostrar_quadro(self, largura, altura, rgb):
        """Um quadro do video do outro lado."""
        if self.vista is None:
            self.vista = VistaVideo(self, "Vídeo de %s" % (
                self.chamada.nome or "contato"))
            self.lay.Insert(1, self.vista, 0, wx.ALL | wx.ALIGN_CENTER, 12)
            self.Layout()
            self.Fit()
        self.vista.mostrar(largura, altura, rgb)

    def dispositivos_escolhidos(self):
        mic = self.escolha_mic.GetStringSelection() if self.microfones else ""
        saida = self.escolha_saida.GetStringSelection() \
            if self.saidas else ""
        return mic, saida

    def _dispositivo(self, _e=None):
        self.acoes["trocar"](*self.dispositivos_escolhidos())

    def _tecla(self, evt):
        if evt.GetKeyCode() == wx.WXK_ESCAPE and not (
                evt.AltDown() or evt.ControlDown() or evt.ShiftDown()):
            self._escape()
            return
        evt.Skip()

    def _escape(self):
        e = self.chamada.estado
        if e == ch.TOCANDO:
            self.acoes["recusar"]()
        elif e in (ch.CHAMANDO, ch.CONECTANDO):
            self.acoes["desligar"]()
        elif e == ch.EM_CHAMADA:
            self.falar("Em chamada. Para encerrar, use o botão Desligar.")
        else:
            self.fechar()

    def _ao_fechar(self, _evt):
        if self.chamada.ativa:
            # nao fecha com a chamada aberta: trata como Esc
            self._escape()
            return
        self.fechar()

    def fechar(self):
        cb, self._ao_fechar_cb = self._ao_fechar_cb, None
        if cb is not None:
            cb()
        self.Destroy()

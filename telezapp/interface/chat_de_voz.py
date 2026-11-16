# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela do chat de voz de grupo e da live de canal (EXPERIMENTAL).

Uma janela so, que muda de estado: entrando (Sair), dentro (Abrir o
microfone, Levantar a mao, Tempo e Sair, com a lista de participantes) e
encerrado (Fechar). O que mostrar e falar vem de `nucleo.chat_de_voz`; esta
janela so desenha. O rotulo da lista vem antes dela (ordem real das janelas
do Windows, a que o NVDA e o Tab seguem).

Esc esconde a janela com o chat de voz em andamento (sair e so pelo botao
Sair, porque Esc e facil de apertar sem querer).
"""
import wx

from telezapp.interface.chamada import VistaVideo
from telezapp.midia.dispositivos import parecem_o_mesmo
from telezapp.nucleo import chamadas as ch
from telezapp.nucleo import chat_de_voz as cv


class DialogoChatDeVoz(wx.Dialog):
    def __init__(self, pai, chat, acoes, falar, microfones=(), saidas=(),
                 microfone="", saida="", ao_fechar=None, ao_ocultar=None,
                 cameras=(), camera="", telas=(), tela="", saidas_pc=(),
                 saida_pc="", tela_com_som=True):
        """acoes: dict com sair(), falar(bool mudo), mao(bool), quem(),
        tempo() e trocar(microfone, saida). `falar(texto)` fala sem interromper."""
        super().__init__(pai, title="Chat de voz",
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.chat = chat
        self.acoes = acoes
        self.falar = falar
        self._ao_fechar_cb = ao_fechar
        self._ao_ocultar = ao_ocultar
        self._ids = []                  # id do participante de cada linha
        self.situacao = wx.StaticText(self, label="", name="Situação")
        self.rot_lista = wx.StaticText(self, label="&Participantes:")
        self.lista = wx.ListBox(self, name="Participantes")
        self.b_falar = wx.Button(self, wx.ID_ANY, "&Abrir o microfone")
        self.b_mao = wx.Button(self, wx.ID_ANY, "Levantar a &mão")
        self.b_camera = wx.Button(self, wx.ID_ANY, "Ligar a &câmera")
        self.b_tela = wx.Button(self, wx.ID_ANY, "Compartilhar a &tela")
        self.b_som_pc = wx.Button(self, wx.ID_ANY,
                                  "Compartilhar o so&m do computador")
        self.b_quem = wx.Button(self, wx.ID_ANY, "&Quem está falando")
        self.b_tempo = wx.Button(self, wx.ID_ANY, "&Tempo no chat de voz")
        self.b_sair = wx.Button(self, wx.ID_ANY, "&Sair do chat de voz")
        self.b_fechar = wx.Button(self, wx.ID_ANY, "&Fechar")
        self.b_ocultar = wx.Button(self, wx.ID_ANY, "&Ocultar a janela")
        self.vista = None               # VistaVideo, criada com o 1o quadro
        self.botoes = {cv.FALAR: self.b_falar, cv.MAO: self.b_mao,
                       cv.SOM_PC: self.b_som_pc, cv.TELA: self.b_tela,
                       cv.CAMERA: self.b_camera, cv.QUEM: self.b_quem, cv.TEMPO: self.b_tempo, cv.SAIR: self.b_sair,
                       cv.FECHAR: self.b_fechar}
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

        self.cameras, self.telas = list(cameras), list(telas)
        self.saidas_pc = list(saidas_pc)
        self.rot_camera = wx.StaticText(self, label="Câ&mera:")
        self.escolha_camera = wx.Choice(self, choices=self.cameras,
                                        name="Câmera")
        self.rot_tela = wx.StaticText(self, label="Tela a compartilhar:")
        self.escolha_tela = wx.Choice(self, choices=self.telas,
                                      name="Tela a compartilhar")
        self.cx_tela_som = wx.CheckBox(
            self, label="Ao compartilhar a tela, compartilhar também o som "
                        "do computador")
        self.cx_tela_som.SetValue(bool(tela_com_som))
        self.rot_saida_pc = wx.StaticText(
            self, label="Saída de som do computador a compartilhar:")
        self.escolha_saida_pc = wx.Choice(
            self, choices=self.saidas_pc,
            name="Saída de som do computador a compartilhar")
        for escolha, lista, nome in (
                (self.escolha_camera, self.cameras, camera),
                (self.escolha_tela, self.telas, tela),
                (self.escolha_saida_pc, self.saidas_pc, saida_pc)):
            if lista:
                escolha.SetSelection(next(
                    (n for n, d in enumerate(lista)
                     if parecem_o_mesmo(nome, d)), 0))

        lay = wx.BoxSizer(wx.VERTICAL)
        self.lay = lay
        lay.Add(self.situacao, 0, wx.ALL, 12)
        lay.Add(self.rot_lista, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
        lay.Add(self.lista, 1, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
                12)
        linha = wx.BoxSizer(wx.HORIZONTAL)
        for b in list(self.botoes.values()) + [self.b_ocultar]:
            linha.Add(b, 0, wx.RIGHT, 6)
        lay.Add(linha, 0, wx.ALL, 12)
        for rotulo, escolha in ((self.rot_mic, self.escolha_mic),
                                (self.rot_saida, self.escolha_saida),
                                (self.rot_camera, self.escolha_camera),
                                (self.rot_tela, self.escolha_tela)):
            lay.Add(rotulo, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
            lay.Add(escolha, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        lay.Add(self.cx_tela_som, 0, wx.ALL, 12)
        lay.Add(self.rot_saida_pc, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
        lay.Add(self.escolha_saida_pc, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        self.SetSizer(lay)
        self.b_camera.Bind(wx.EVT_BUTTON, lambda e: acoes["camera"]())
        self.b_tela.Bind(wx.EVT_BUTTON, lambda e: acoes["tela"]())
        self.b_som_pc.Bind(wx.EVT_BUTTON, lambda e: acoes["som_pc"]())
        self.escolha_camera.Bind(
            wx.EVT_CHOICE, lambda e: acoes["trocar_camera"](
                self.escolha_camera.GetStringSelection()))
        self.escolha_tela.Bind(
            wx.EVT_CHOICE, lambda e: acoes["trocar_tela"](
                self.escolha_tela.GetStringSelection()))
        self.cx_tela_som.Bind(
            wx.EVT_CHECKBOX,
            lambda e: acoes["tela_com_som"](self.cx_tela_som.GetValue()))
        self.escolha_saida_pc.Bind(
            wx.EVT_CHOICE, lambda e: acoes["trocar_som_pc"](
                self.escolha_saida_pc.GetStringSelection()))

        self.b_falar.Bind(wx.EVT_BUTTON, self._falar)
        self.b_mao.Bind(wx.EVT_BUTTON, self._mao)
        self.b_quem.Bind(wx.EVT_BUTTON, lambda e: acoes["quem"]())
        self.b_tempo.Bind(wx.EVT_BUTTON, lambda e: acoes["tempo"]())
        self.b_sair.Bind(wx.EVT_BUTTON, lambda e: acoes["sair"]())
        self.b_fechar.Bind(wx.EVT_BUTTON, lambda e: self.fechar())
        self.b_ocultar.Bind(wx.EVT_BUTTON, lambda e: self.ocultar())
        self.escolha_mic.Bind(wx.EVT_CHOICE, self._dispositivo)
        self.escolha_saida.Bind(wx.EVT_CHOICE, self._dispositivo)
        self.Bind(wx.EVT_CHAR_HOOK, self._tecla)
        self.Bind(wx.EVT_CLOSE, self._ao_fechar)
        self._estado_mostrado = None
        self.mostrar()

    # ------------------------------------------------------- desenho
    def _controles_com_foco(self):
        return (list(self.botoes.values())
                + [self.b_ocultar, self.lista, self.escolha_mic,
                   self.escolha_saida, self.escolha_camera,
                   self.escolha_tela, self.cx_tela_som,
                   self.escolha_saida_pc])

    def mostrar(self):
        """Redesenha para o estado atual. O foco so vai para o botao
        principal quando o ESTADO muda; ao redesenhar por outro motivo
        (alguem entrou, o microfone mudou), o foco fica onde estava, para o
        leitor de tela nao voltar ao inicio da janela."""
        c = self.chat
        foco_antes = self.FindFocus()
        a = cv.apresentar(c)
        self.SetTitle(a.titulo)
        self.situacao.SetLabel(a.situacao)
        visiveis = set(a.botoes)
        for nome, b in self.botoes.items():
            b.Show(nome in visiveis)
        self.b_ocultar.Show(bool(c.ativo))
        self.b_falar.SetLabel(cv.rotulo_falar(c.mudo))
        self.b_mao.SetLabel(cv.rotulo_mao(c.mao))
        self.b_camera.SetLabel(cv.rotulo_camera(c))
        self.b_tela.SetLabel(ch.rotulo_tela(c))
        self.b_som_pc.SetLabel(ch.rotulo_som_pc(c))
        dentro = c.estado == cv.DENTRO
        self.rot_lista.Show(dentro)
        self.lista.Show(dentro)
        if dentro:
            self._preencher_lista()
        mostrar_disp = c.estado in (cv.CONECTANDO, cv.DENTRO) and \
            bool(self.microfones or self.saidas)
        self.rot_mic.Show(mostrar_disp and not c.ouvinte)
        self.escolha_mic.Show(mostrar_disp and not c.ouvinte)
        self.rot_saida.Show(mostrar_disp)
        self.escolha_saida.Show(mostrar_disp)
        falando = dentro and not c.ouvinte
        com_camera = falando and c.suporta_video and bool(self.cameras)
        self.rot_camera.Show(com_camera)
        self.escolha_camera.Show(com_camera)
        com_tela = falando and c.suporta_tela and c.suporta_video and \
            bool(self.telas)
        self.rot_tela.Show(com_tela)
        self.escolha_tela.Show(com_tela)
        self.cx_tela_som.Show(com_tela and c.suporta_som_pc)
        com_som = falando and c.suporta_som_pc and bool(self.saidas_pc)
        self.rot_saida_pc.Show(com_som)
        self.escolha_saida_pc.Show(com_som)
        self.Layout()
        self.Fit()
        mudou_o_estado = c.estado != self._estado_mostrado
        self._estado_mostrado = c.estado
        nosso = any(foco_antes is x for x in self._controles_com_foco())
        if not mudou_o_estado and nosso and foco_antes.IsShown() \
                and foco_antes.IsEnabled():
            foco_antes.SetFocus()
            return a
        foco = self.botoes.get(a.foco)
        if foco is not None:
            foco.SetFocus()
            foco.SetDefault()
        return a

    def _preencher_lista(self):
        """Troca a lista de uma vez so e mantem o participante escolhido."""
        ordenados = cv.ordenar(self.chat.participantes)[:cv.LISTA_MAXIMA]
        ids = [p.id for p in ordenados]
        textos = [cv.rotulo(p) for p in ordenados]
        if textos == self.lista.GetStrings():
            return
        escolhido = self._ids[self.lista.GetSelection()] \
            if 0 <= self.lista.GetSelection() < len(self._ids) else None
        self.lista.Set(textos)
        self._ids = ids
        if escolhido in ids:
            self.lista.SetSelection(ids.index(escolhido))
        elif textos:
            self.lista.SetSelection(0)

    # ------------------------------------------------------- acoes
    def _falar(self, _e=None):
        self.acoes["falar"](not self.chat.mudo)

    def _mao(self, _e=None):
        self.acoes["mao"](not self.chat.mao)

    def mostrar_quadro(self, largura, altura, rgb):
        """Um quadro de video (camera ou tela) de quem aparece no chat."""
        if self.vista is None:
            self.vista = VistaVideo(self, "Vídeo de %s" % (
                self.chat.nome or "chat de voz"))
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
        if self.chat.estado == cv.ENCERRADO:
            self.fechar()
        else:
            self.ocultar()

    def ocultar(self):
        if self._ao_ocultar is not None:
            self._ao_ocultar(self)
        else:
            self.Hide()

    def _ao_fechar(self, _evt):
        if self.chat.ativo:
            self._escape()
            return
        self.fechar()

    def fechar(self):
        cb, self._ao_fechar_cb = self._ao_fechar_cb, None
        if cb is not None:
            cb()
        self.Destroy()

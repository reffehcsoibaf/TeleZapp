# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Lista de mensagens do modo visual: desenhada pelo programa, para quem le
na tela. Cada mensagem quebra em quantas linhas precisar, as minhas ficam
a direita com outra cor, o dia aparece quando muda e o estado (lida,
entregue) fica pequeno, fora do texto.

Tem a mesma interface que a janela usa do wx.ListBox (Set, Append,
SetString, GetSelection...), e os mesmos eventos (EVT_LISTBOX, teclas, menu
de contexto). Nao e lida por leitor de tela: por isso so existe no modo
visual (ver nucleo/aparencia.py)."""
import wx

from telezapp.nucleo import aparencia

# (tipo, dia, estado) de um item; o que a janela nao informou vira aviso
AVISO = ("aviso", "", "")

# cores: claras, com texto escuro (contraste acima de 7:1 em todas)
COR_FUNDO = wx.Colour(255, 255, 255)
COR_MINHA = wx.Colour(222, 236, 255)
COR_OUTRA = wx.Colour(241, 241, 241)
COR_MARCADOR = wx.Colour(255, 244, 214)
COR_TEXTO = wx.Colour(26, 26, 26)
COR_SUAVE = wx.Colour(90, 90, 90)
COR_DIA = wx.Colour(230, 230, 230)

MARGEM = 10           # entre a borda da lista e o balao
RECUO = 60            # o lado vazio, que mostra de quem e o balao
ESPACO = 6            # entre um balao e o outro
DENTRO = 8            # entre a borda do balao e o texto


class ListaVisual(wx.VListBox):

    def __init__(self, pai, name=""):
        super().__init__(pai, name=name, style=wx.BORDER_THEME)
        self._textos = []
        self._info = []
        self.SetBackgroundColour(COR_FUNDO)
        self.Bind(wx.EVT_SIZE, self._ao_redimensionar)

    # ------------------------------------------- a interface do wx.ListBox
    def definir_info(self, info):
        """[(tipo, dia, estado)] por item, na ordem: tipo "minha", "outra",
        "marcador" ou "aviso"; dia ("Hoje"...) e estado ("lida"...) podem
        ser vazios. Chamar antes de Set/Append/SetString. So o estado pode
        mudar sem o texto mudar (lida): entao redesenha aqui."""
        info = list(info)
        mudou = info[:len(self._textos)] != self._info[:len(self._textos)]
        self._info = info
        if mudou and len(info) >= len(self._textos):
            self._remedir()

    def GetCount(self):
        return len(self._textos)

    def GetString(self, i):
        return self._textos[i]

    def SetString(self, i, texto):
        self._textos[i] = texto
        self._remedir()

    def Append(self, texto):
        self._textos.append(texto)
        self._remedir()

    def Set(self, textos):
        self._textos = list(textos)
        self._remedir()

    def Clear(self):
        self.Set([])

    def SetFont(self, fonte):
        feito = super().SetFont(fonte)
        self._remedir()
        return feito

    # ------------------------------------------------------- desenho
    def _remedir(self):
        """As alturas dependem do texto e da largura: o VListBox mede de
        novo quando a contagem e reposta."""
        sel = self.GetSelection()
        self.SetItemCount(len(self._textos))
        if 0 <= sel < len(self._textos):
            self.SetSelection(sel)
        self.Refresh()

    def _ao_redimensionar(self, evt):
        evt.Skip()
        wx.CallAfter(self._remedir_se_vivo)

    def _remedir_se_vivo(self):
        if self:
            self._remedir()

    def _info_de(self, n):
        return self._info[n] if 0 <= n < len(self._info) else AVISO

    def _dia_novo(self, n):
        """O dia do item, se for diferente do ultimo dia antes dele."""
        dia = self._info_de(n)[1]
        if not dia:
            return ""
        for k in range(n - 1, -1, -1):
            anterior = self._info_de(k)[1]
            if anterior:
                return "" if anterior == dia else dia
        return dia

    def _largura_do_texto(self):
        largura = self.GetClientSize().width - 2 * MARGEM - RECUO - 2 * DENTRO
        return max(largura, 80)

    def _linhas(self, dc, n):
        return aparencia.quebrar_linhas(
            self._textos[n], self._largura_do_texto(),
            lambda trecho: dc.GetTextExtent(trecho)[0])

    def OnMeasureItem(self, n):
        if not 0 <= n < len(self._textos):
            return 20
        dc = wx.ClientDC(self)
        dc.SetFont(self.GetFont())
        altura_linha = dc.GetCharHeight()
        altura = len(self._linhas(dc, n)) * altura_linha + 2 * DENTRO
        if self._info_de(n)[2]:
            altura += altura_linha          # o estado, numa linha pequena
        if self._dia_novo(n):
            altura += altura_linha + 2 * ESPACO
        return altura + ESPACO

    def OnDrawBackground(self, dc, rect, n):
        dc.SetBrush(wx.Brush(COR_FUNDO))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(rect)

    def OnDrawItem(self, dc, rect, n):
        if not 0 <= n < len(self._textos):
            return
        tipo, _, estado = self._info_de(n)
        dc.SetFont(self.GetFont())
        altura_linha = dc.GetCharHeight()
        topo = rect.y + ESPACO // 2
        dia = self._dia_novo(n)
        if dia:
            topo = self._desenhar_dia(dc, rect, topo, dia, altura_linha)
        linhas = self._linhas(dc, n)
        largura = max([dc.GetTextExtent(x)[0] for x in linhas] +
                      [dc.GetTextExtent(estado)[0] if estado else 0])
        altura = len(linhas) * altura_linha + 2 * DENTRO + (
            altura_linha if estado else 0)
        larg_balao = largura + 2 * DENTRO
        if tipo == "minha":
            x = rect.x + rect.width - MARGEM - larg_balao
            cor = COR_MINHA
        elif tipo in ("marcador", "aviso"):
            x = rect.x + (rect.width - larg_balao) // 2
            cor = COR_MARCADOR if tipo == "marcador" else COR_FUNDO
        else:
            x = rect.x + MARGEM
            cor = COR_OUTRA
        selecionado = self.IsSelected(n)
        dc.SetBrush(wx.Brush(cor))
        dc.SetPen(wx.Pen(wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT),
                         3) if selecionado else wx.Pen(cor.ChangeLightness(85)))
        dc.DrawRoundedRectangle(x, topo, larg_balao, altura, 8)
        dc.SetTextForeground(COR_TEXTO)
        y = topo + DENTRO
        for linha in linhas:
            dc.DrawText(linha, x + DENTRO, y)
            y += altura_linha
        if estado:
            dc.SetTextForeground(COR_SUAVE)
            dc.DrawText(estado, x + larg_balao - DENTRO -
                        dc.GetTextExtent(estado)[0], y)

    def _desenhar_dia(self, dc, rect, topo, dia, altura_linha):
        largura = dc.GetTextExtent(dia)[0] + 2 * DENTRO
        x = rect.x + (rect.width - largura) // 2
        dc.SetBrush(wx.Brush(COR_DIA))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRoundedRectangle(x, topo + ESPACO, largura, altura_linha, 6)
        dc.SetTextForeground(COR_SUAVE)
        dc.DrawText(dia, x + DENTRO, topo + ESPACO)
        return topo + altura_linha + 2 * ESPACO

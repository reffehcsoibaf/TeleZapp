# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Control V com midia: arquivos copiados no Explorer e imagens (print, imagem
copiada de um site) viram anexos preparados, que esperam o Enter. Usado pela
caixa de digitar da janela e pelo dialogo de nova mensagem."""
import logging
import os
import time
import traceback

import wx

from telezapp import config
from telezapp.acessibilidade.fala import bipe
from telezapp.midia import envio
from telezapp.nucleo import modelos as m

log = logging.getLogger(__name__)


def _converter_imagem(caminho):
    """PNG temporario de um BMP ou GIF parado (formatos que os servicos nao
    tratam como foto); None se nao for o caso ou nao der (GIF animado,
    arquivo ilegivel)."""
    ext = os.path.splitext(caminho)[1].lower()
    if ext not in (".bmp", ".gif"):
        return None
    try:
        if ext == ".gif" and wx.Image.GetImageCount(
                caminho, wx.BITMAP_TYPE_GIF) > 1:
            return None
        imagem = wx.Image()
        if not imagem.LoadFile(caminho):
            return None
        destino = os.path.join(config.pasta_temporaria(), "%s-%d.png" % (
            os.path.splitext(os.path.basename(caminho))[0],
            int(time.time() * 1000)))
        return destino if imagem.SaveFile(destino, wx.BITMAP_TYPE_PNG) \
            else None
    except Exception:
        log.warning("nao consegui converter a imagem colada", exc_info=True)
        return None


def ler(fala):
    """Anexos preparados do que esta na area de transferencia; None se for so
    texto (ou nada que o TeleZapp envie); lista vazia se havia midia mas
    nenhuma pode ser enviada (a pessoa ja foi avisada)."""
    if not wx.TheClipboard.Open():
        return None
    arquivos, imagem = [], None
    try:
        if wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_FILENAME)):
            dados = wx.FileDataObject()
            if wx.TheClipboard.GetData(dados):
                arquivos = dados.GetFilenames()
        elif not wx.TheClipboard.IsSupported(
                wx.DataFormat(wx.DF_UNICODETEXT)) and \
                wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_BITMAP)):
            dados = wx.BitmapDataObject()
            if wx.TheClipboard.GetData(dados):
                imagem = dados.GetBitmap()
    finally:
        wx.TheClipboard.Close()
    origens = []                       # (caminho, temporario)
    if imagem is not None and imagem.IsOk():
        nome = time.strftime("imagem_colada_%Y%m%d_%H%M%S.png")
        caminho = os.path.join(config.pasta_temporaria(), nome)
        if not imagem.ConvertToImage().SaveFile(caminho, wx.BITMAP_TYPE_PNG):
            return None
        origens.append((caminho, True))
    origens += [(c, False) for c in arquivos]
    if not origens:
        return None
    anexos, avisos = [], []
    for caminho, temporario in origens:
        if os.path.isdir(caminho):
            avisos.append("Pastas não podem ser enviadas.")
            continue
        convertido = _converter_imagem(caminho)
        if convertido:
            caminho, temporario = convertido, True
        try:
            anexos.append(envio.preparar(caminho, temporario=temporario,
                                         colado=True))
        except envio.ErroEnvio as e:
            avisos.append("%s: %s" % (os.path.basename(caminho), e))
    sem_conversao = [a.nome for a in anexos if a.sem_conversao]
    if sem_conversao:
        wx.MessageBox(
            "O TeleZapp não consegue converter %s para um formato que o "
            "WhatsApp e o Telegram tocam. %s será enviado como documento "
            "(a pessoa baixa e abre o arquivo)." % (
                ", ".join(sem_conversao),
                "Esse arquivo" if len(sem_conversao) == 1
                else "Esses arquivos"),
            "Enviado como documento", wx.OK | wx.ICON_INFORMATION)
    if not anexos:
        bipe("erro")
        fala.falar(" ".join(avisos), interromper=True)
        return []
    if avisos:
        fala.falar(" ".join(avisos))
    return anexos


def colar(evt, fala, anexos, ao_mudar, tecla="Enter"):
    """Tratador de EVT_TEXT_PASTE: midia colada vai para `anexos` (lista) e
    `ao_mudar()` e chamado; texto segue o caminho normal da colagem."""
    try:
        novos = ler(fala)
    except Exception:
        log.error("erro ao colar:\n%s", traceback.format_exc())
        novos = None
    if novos is None:
        evt.Skip()
        return
    if not novos:
        return
    # o que a pessoa escrever antes ou depois da colagem vira legenda
    anexos.extend(novos)
    ao_mudar()
    nomes = ", ".join(m.NOMES_TIPOS[a.tipo] for a in novos)
    fala.falar("%s colado. Escreva a legenda, se quiser, e aperte %s "
               "para enviar. Esc remove." % (nomes.capitalize(), tecla),
               interromper=True)


def descartar(anexos):
    """Apaga os arquivos temporarios dos anexos e esvazia a lista."""
    for a in anexos:
        if a.temporario:
            try:
                os.remove(a.caminho)
            except OSError:
                pass
    del anexos[:]


def descricao(anexos):
    n = len(anexos)
    return "1 mídia colada" if n == 1 else "%d mídias coladas" % n

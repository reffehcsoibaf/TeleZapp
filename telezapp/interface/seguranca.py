# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janelas da seguranca ao entrar: pedir a autenticacao ao abrir, ligar
(criar o PIN do TeleZapp) e desligar. Quem decide e `nucleo.seguranca`."""
import logging

import wx

from telezapp import NOME
from telezapp.nucleo import seguranca as seg

log = logging.getLogger("telezapp.seguranca")

MARCA = "seguranca_ao_entrar"      # chave no config.json


def _pedir_pin(pai, texto, titulo="Entrar no %s" % NOME):
    dlg = wx.PasswordEntryDialog(pai, texto, titulo)
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return None
        return dlg.GetValue()
    finally:
        dlg.Destroy()


def autenticar(pai, trava, motivo="Entrar no %s" % NOME):
    """Pede o Windows Hello (neste computador, se der) ou o PIN do
    TeleZapp. True se a pessoa provou quem e."""
    if trava.deste_computador() and trava.usar_hello() and \
            seg.hello_disponivel():
        r = seg.pedir_hello(motivo)
        if r == seg.HELLO_OK:
            log.info("autenticação: Windows Hello")
            return True
        log.info("autenticação: Windows Hello %s; pedindo o PIN", r)
    texto = "Digite o PIN do %s." % NOME
    if not trava.deste_computador():
        texto = ("Este computador ainda não é conhecido pelo %s. Digite o "
                 "PIN do %s." % (NOME, NOME))
    while True:
        pin = _pedir_pin(pai, texto, motivo)
        if pin is None:
            return False
        try:
            if trava.conferir_pin(pin):
                log.info("autenticação: PIN")
                return True
        except seg.ErroSeguranca as e:
            wx.MessageBox(str(e), motivo, wx.OK | wx.ICON_WARNING, pai)
            continue
        texto = "PIN errado. Digite o PIN do %s de novo." % NOME


def verificar_ao_abrir(cfg, pasta):
    """Na abertura, antes da janela: True para seguir, False para sair."""
    trava = seg.Trava(pasta)
    if trava.adulterada(cfg.get(MARCA)):
        log.warning("seguranca ao entrar: arquivo da trava sumiu ou mudou")
        wx.MessageBox(
            "A proteção ao entrar do %s está ligada, mas o arquivo dela "
            "sumiu ou foi alterado. Por segurança, o %s não vai abrir. Se "
            "foi você, restaure um backup feito com a proteção ligada." %
            (NOME, NOME), NOME, wx.OK | wx.ICON_ERROR)
        return False
    if not trava.ligada:
        return True
    novo = not trava.deste_computador()
    if not autenticar(None, trava):
        log.info("seguranca ao entrar: a pessoa desistiu")
        return False
    if novo and seg.hello_disponivel() and wx.MessageBox(
            "Usar o Windows Hello deste computador (digital, rosto ou o PIN "
            "do Windows) para entrar nas próximas vezes?", NOME,
            wx.YES_NO | wx.ICON_QUESTION) == wx.YES:
        if trava.vincular_este_computador():
            trava.definir_hello(True)
    return True


def ligar(pai, cfg, pasta):
    """Cria o PIN do TeleZapp e liga a trava. True se ligou."""
    pin = _pedir_pin(pai, "Crie o PIN do %s (pelo menos %d caracteres). Ele "
                     "é pedido ao abrir, também se a pasta do %s for levada "
                     "para outro computador. Guarde-o: sem ele não dá para "
                     "abrir." % (NOME, seg.PIN_MINIMO, NOME),
                     "Proteção ao entrar")
    if pin is None:
        return False
    motivo = seg.pin_valido(pin)
    if motivo:
        wx.MessageBox(motivo, "Proteção ao entrar", wx.OK | wx.ICON_WARNING,
                      pai)
        return False
    if _pedir_pin(pai, "Digite o PIN de novo, para confirmar.",
                  "Proteção ao entrar") != pin:
        wx.MessageBox("Os dois PINs não são iguais. A proteção não foi "
                      "ligada.", "Proteção ao entrar",
                      wx.OK | wx.ICON_WARNING, pai)
        return False
    usar_hello = bool(cfg.get("seguranca_usar_hello"))
    trava = seg.Trava(pasta)
    try:
        trava.ligar(pin, usar_hello)
    except (seg.ErroSeguranca, OSError) as e:
        wx.MessageBox("Não consegui ligar a proteção: %s" % e,
                      "Proteção ao entrar", wx.OK | wx.ICON_WARNING, pai)
        return False
    cfg.set(MARCA, True)
    log.info("seguranca ao entrar ligada (Windows Hello: %s)", usar_hello)
    return True


def desligar(pai, cfg, pasta):
    """Pede a autenticacao e desliga. True se desligou."""
    trava = seg.Trava(pasta)
    if trava.ligada and not autenticar(pai, trava,
                                       "Desligar a proteção ao entrar"):
        return False
    trava.desligar()
    cfg.set(MARCA, False)
    log.info("seguranca ao entrar desligada")
    return True


def mudar_hello(cfg, pasta, usar):
    trava = seg.Trava(pasta)
    if trava.ligada:
        trava.definir_hello(usar)

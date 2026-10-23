# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Ponte entre o wx e o texto das combinacoes de teclas (nucleo/atalhos):
le uma combinacao de um evento de teclado e a transforma em tecla de
aceleracao do menu ou de atalho global do Windows."""
import wx

from telezapp.nucleo import atalhos as at

_NOMEADAS = {"Up": "UP", "Down": "DOWN", "Left": "LEFT", "Right": "RIGHT",
             "Home": "HOME", "End": "END", "PgUp": "PAGEUP",
             "PgDn": "PAGEDOWN", "Insert": "INSERT", "Delete": "DELETE",
             "Space": "SPACE", "Enter": "RETURN", "Esc": "ESCAPE",
             "Tab": "TAB", "Backspace": "BACK"}
_MODIFICADORES = ("SHIFT", "CONTROL", "ALT", "WINDOWS_LEFT", "WINDOWS_RIGHT",
                  "COMMAND", "RAW_CONTROL", "MENU")


def _wxk(nome, padrao=-1):
    return getattr(wx, "WXK_" + nome, padrao)


def codigo_da_tecla(nome):
    """O codigo wx (WXK_*) da tecla pelo nome canonico, ou -1."""
    if nome in at.TECLAS_F:
        return _wxk("F%d" % int(nome[1:]))
    if nome in _NOMEADAS:
        return _wxk(_NOMEADAS[nome])
    if len(nome) == 1:
        return ord(nome)
    return -1


def nome_da_tecla(codigo, unicode_=0):
    """O nome canonico da tecla de um evento, ou None se for so um
    modificador ou uma tecla desconhecida."""
    for nome in _MODIFICADORES:
        if codigo == _wxk(nome):
            return None
    for n in range(1, 13):
        if codigo == _wxk("F%d" % n):
            return "F%d" % n
    for nome, sufixo in _NOMEADAS.items():
        if codigo == _wxk(sufixo):
            return nome
    if codigo == _wxk("NUMPAD_ENTER"):
        return "Enter"
    caractere = chr(unicode_) if unicode_ and unicode_ > 32 else \
        (chr(codigo) if 32 < codigo < 127 else "")
    if caractere:
        c = caractere.upper() if caractere.isalpha() else caractere
        return c if at.normalizar(c) == c else None
    return None


def combinacao_do_evento(evt):
    """A combinacao canonica de um wx.KeyEvent, ou None enquanto so ha
    modificadores apertados."""
    nome = nome_da_tecla(evt.GetKeyCode(), evt.GetUnicodeKey())
    if nome is None:
        return None
    return at.montar(evt.ControlDown(), evt.AltDown(), evt.ShiftDown(), nome)


def entrada_de_aceleracao(canon, id_):
    """wx.AcceleratorEntry da combinacao, ligada ao item de menu `id_`."""
    ctrl, alt, shift, tecla = at.partes(canon)
    marcas = (wx.ACCEL_CTRL if ctrl else 0) | (wx.ACCEL_ALT if alt else 0) | \
        (wx.ACCEL_SHIFT if shift else 0)
    return wx.AcceleratorEntry(marcas or wx.ACCEL_NORMAL,
                               codigo_da_tecla(tecla), id_)


def para_atalho_global(canon):
    """(modificadores MOD_*, codigo virtual do Windows) para
    RegisterHotKey, ou None se a tecla nao tiver codigo virtual."""
    ctrl, alt, shift, tecla = at.partes(canon)
    mods = (wx.MOD_CONTROL if ctrl else 0) | (wx.MOD_ALT if alt else 0) | \
        (wx.MOD_SHIFT if shift else 0)
    virtual = _virtual(tecla)
    return (mods, virtual) if virtual else None


_VIRTUAIS = {"Up": 0x26, "Down": 0x28, "Left": 0x25, "Right": 0x27,
             "Home": 0x24, "End": 0x23, "PgUp": 0x21, "PgDn": 0x22,
             "Insert": 0x2D, "Delete": 0x2E, "Space": 0x20, "Enter": 0x0D,
             "Esc": 0x1B, "Tab": 0x09, "Backspace": 0x08,
             ",": 0xBC, ".": 0xBE, "-": 0xBD, "=": 0xBB, ";": 0xBA,
             "/": 0xBF, "`": 0xC0, "[": 0xDB, "\\": 0xDC, "]": 0xDD,
             "'": 0xDE}


def _virtual(tecla):
    if tecla in at.TECLAS_F:
        return 0x70 + int(tecla[1:]) - 1
    if tecla in _VIRTUAIS:
        return _VIRTUAIS[tecla]
    if len(tecla) == 1 and (tecla.isalpha() or tecla.isdigit()):
        return ord(tecla)
    return 0

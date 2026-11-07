# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Onde gravar um arquivo: direto na pasta das configuracoes ou pela janela."""
import wx

from telezapp.nucleo import pasta_salvar

_cfg = None


def definir_cfg(cfg):
    global _cfg
    _cfg = cfg


def pasta_definida():
    return (_cfg.get("pasta_salvar") or "") if _cfg is not None else ""


def guarda_direto():
    return bool(_cfg is not None and pasta_definida()
                and _cfg.get("salvar_direto"))


def escolher_pasta(pai, titulo, pasta=""):
    """Pasta onde gravar varios arquivos, ou None se a pessoa cancelar. Com
    "salvar direto" ligado, a pasta das configuracoes, sem perguntar."""
    if guarda_direto():
        try:
            import os
            os.makedirs(pasta_definida(), exist_ok=True)
            return pasta_definida()
        except OSError:
            pass
    dlg = wx.DirDialog(pai, titulo, defaultPath=pasta_definida() or pasta)
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return None
        return dlg.GetPath()
    finally:
        dlg.Destroy()


def escolher(pai, titulo, nome, wildcard="", pasta=""):
    """Caminho onde gravar, ou None se a pessoa cancelar. `pasta`: onde a janela
    comeca quando nao ha pasta definida nas configuracoes."""
    caminho = pasta_salvar.direto(pasta_definida(), guarda_direto(), nome)
    if caminho:
        return caminho
    dlg = wx.FileDialog(pai, titulo, defaultDir=pasta_definida() or pasta,
                        defaultFile=nome, wildcard=wildcard,
                        style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return None
        return dlg.GetPath()
    finally:
        dlg.Destroy()

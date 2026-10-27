# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Onde ficam as chaves dos provedores de IA.

No Windows as chaves sao cifradas com o DPAPI do usuario: so o mesmo usuario
do Windows, neste computador, consegue le-las, e elas nunca vao no log. So
vao no backup se ele tiver senha (nucleo/backup.py). Fora do Windows (so nos testes) ficam apenas ofuscadas.
"""
import base64
import ctypes
import json
import logging
import os
from ctypes import wintypes

from telezapp.nucleo.ia import catalogo as cat

log = logging.getLogger("telezapp.ia")


class _Bolha(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(dados, proteger):
    if os.name != "nt":
        return base64.b64encode(dados) if proteger else base64.b64decode(
            dados)
    entrada = _Bolha(len(dados), ctypes.cast(
        ctypes.create_string_buffer(dados, len(dados)),
        ctypes.POINTER(ctypes.c_char)))
    saida = _Bolha()
    funcao = ctypes.windll.crypt32.CryptProtectData if proteger else \
        ctypes.windll.crypt32.CryptUnprotectData
    ok = funcao(ctypes.byref(entrada), None, None, None, None, 0,
                ctypes.byref(saida))
    if not ok:
        raise OSError("DPAPI recusou")
    try:
        return ctypes.string_at(saida.pbData, saida.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(saida.pbData)


class Cofre:
    """Chaves por provedor num arquivo da pasta de dados."""

    def __init__(self, caminho):
        self.caminho = caminho

    def _ler(self):
        try:
            with open(self.caminho, encoding="utf-8") as f:
                dados = json.load(f)
            return dados if isinstance(dados, dict) else {}
        except (OSError, ValueError):
            return {}

    def _gravar(self, dados):
        tmp = self.caminho + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f)
        os.replace(tmp, self.caminho)

    def tem(self, provedor):
        return bool(self._ler().get(provedor))

    def obter(self, provedor):
        """A chave, ou "" se nao ha (ou nao deu para decifrar)."""
        bruto = self._ler().get(provedor)
        if not bruto or provedor not in cat.PROVEDORES:
            return ""
        try:
            return _dpapi(base64.b64decode(bruto), False).decode("utf-8")
        except (OSError, ValueError):
            log.warning("não consegui ler a chave de %s", provedor)
            return ""

    def guardar(self, provedor, chave):
        """Guarda a chave (vazia remove)."""
        if provedor not in cat.PROVEDORES:
            raise ValueError(provedor)
        dados = self._ler()
        chave = (chave or "").strip()
        if chave:
            dados[provedor] = base64.b64encode(
                _dpapi(chave.encode("utf-8"), True)).decode("ascii")
        else:
            dados.pop(provedor, None)
        self._gravar(dados)

    def provedores_com_chave(self):
        return [p for p in cat.PROVEDORES if self.tem(p)]

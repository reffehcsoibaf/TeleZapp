# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Windows Hello pedido com uma janela dona (IUserConsentVerifierInterop).

Um programa de area de trabalho que pede o Hello pela API comum
(`UserConsentVerifier.RequestVerificationAsync`) nao tem janela para o Windows
mostrar o aviso: ele nao aparece e a espera nunca acaba. O jeito certo e
`RequestVerificationForWindowAsync`, que recebe o HWND de uma janela do
programa. Aqui isso e feito com ctypes, sem esperar: `PedidoDeHello.estado()`
diz se ja respondeu, e quem chama (uma janela com temporizador) consulta.
"""
import ctypes
import logging
import uuid
from ctypes import POINTER, WINFUNCTYPE, byref, c_long, c_uint, c_void_p

log = logging.getLogger("telezapp.seguranca")

CLASSE = "Windows.Security.Credentials.UI.UserConsentVerifier"
IID_INTEROP = "39E050C3-4E74-441A-8DC0-B81104DF949C"
IID_OPERACAO = "FD596FFD-2318-558F-9DBE-D21DF43764A5"   # IAsyncOperation<Result>
IID_ASYNCINFO = "00000036-0000-0000-C000-000000000046"

# UserConsentVerificationResult
VERIFICADO, DISPOSITIVO_AUSENTE, NAO_CONFIGURADO, TENTATIVAS, DESATIVADO, \
    OCUPADO, CANCELADO = range(7)
# AsyncStatus
INICIADO, COMPLETO, CANCELADA, ERRO = range(4)


class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16),
                ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]


def _guid(texto):
    return _GUID.from_buffer_copy(uuid.UUID(texto).bytes_le)


def _chamar(ponteiro, indice, restype, *tipos):
    """O metodo `indice` da tabela virtual do objeto COM `ponteiro`."""
    tabela = ctypes.cast(ponteiro, POINTER(POINTER(c_void_p)))[0]
    return WINFUNCTYPE(restype, c_void_p, *tipos)(tabela[indice])


def _liberar(ponteiro):
    if ponteiro:
        _chamar(ponteiro, 2, c_uint)(ponteiro)           # IUnknown::Release


class PedidoDeHello:
    """Um pedido de Windows Hello em andamento, ligado a uma janela."""

    def __init__(self, hwnd, mensagem):
        self._op = c_void_p()
        self._info = c_void_p()
        combase = ctypes.windll.combase
        combase.RoInitialize(1)          # MTA; "ja iniciado" tambem serve
        texto = ctypes.c_void_p()
        combase.WindowsCreateString(CLASSE, len(CLASSE), byref(texto))
        fabrica = c_void_p()
        try:
            iid = _guid(IID_INTEROP)
            r = combase.RoGetActivationFactory(texto, byref(iid),
                                               byref(fabrica))
            if r < 0:
                raise OSError("RoGetActivationFactory: 0x%08X" % (r & 2**32 - 1))
            msg = ctypes.c_void_p()
            combase.WindowsCreateString(mensagem, len(mensagem), byref(msg))
            try:
                pedir = _chamar(fabrica, 6, c_long, c_void_p, c_void_p,
                                POINTER(_GUID), POINTER(c_void_p))
                iid_op = _guid(IID_OPERACAO)
                r = pedir(fabrica, hwnd, msg, byref(iid_op), byref(self._op))
                if r < 0:
                    raise OSError("RequestVerificationForWindowAsync: "
                                  "0x%08X" % (r & 2**32 - 1))
            finally:
                combase.WindowsDeleteString(msg)
            iid_info = _guid(IID_ASYNCINFO)
            consulta = _chamar(self._op, 0, c_long, POINTER(_GUID),
                               POINTER(c_void_p))
            r = consulta(self._op, byref(iid_info), byref(self._info))
            if r < 0:
                raise OSError("IAsyncInfo: 0x%08X" % (r & 2**32 - 1))
        finally:
            combase.WindowsDeleteString(texto)
            _liberar(fabrica)

    def _status(self):
        valor = c_long()
        r = _chamar(self._info, 7, c_long, POINTER(c_long))(
            self._info, byref(valor))
        return valor.value if r >= 0 else ERRO

    def estado(self):
        """None enquanto espera a pessoa; depois o resultado do Windows
        (VERIFICADO, CANCELADO...). ERRO e CANCELADA viram CANCELADO."""
        status = self._status()
        if status == INICIADO:
            return None
        if status != COMPLETO:
            return CANCELADO
        resultado = c_long()
        r = _chamar(self._op, 8, c_long, POINTER(c_long))(
            self._op, byref(resultado))
        return resultado.value if r >= 0 else CANCELADO

    def cancelar(self):
        try:
            _chamar(self._info, 9, c_long)(self._info)       # IAsyncInfo.Cancel
        except Exception:
            log.exception("nao consegui cancelar o Windows Hello")

    def fechar(self):
        _liberar(self._info)
        _liberar(self._op)
        self._info = c_void_p()
        self._op = c_void_p()

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Fala direta pelo NVDA e sons curtos.

Usa a DLL nvdaControllerClient que vem no pacote accessible-output2,
carregada por ctypes (sem importar o pacote). Sem NVDA ou sem a DLL, a fala
fica desligada e o motivo vai para o log.
"""
import ctypes
import importlib.util
import logging
import os
import struct
import threading

try:
    import winsound
except ImportError:  # fora do Windows (testes)
    winsound = None

log = logging.getLogger("telezapp.fala")


class Fala:
    def __init__(self):
        self.lib = None
        self.motivo = ""
        self._carregar()

    def _carregar(self):
        try:
            spec = importlib.util.find_spec("accessible_output2")
            if spec is None or not spec.origin:
                self.motivo = "pacote accessible_output2 não instalado"
                return
            nome = ("nvdaControllerClient64.dll"
                    if struct.calcsize("P") == 8
                    else "nvdaControllerClient32.dll")
            caminho = os.path.join(os.path.dirname(spec.origin), "lib", nome)
            if not os.path.isfile(caminho):
                self.motivo = "DLL não encontrada"
                return
            lib = ctypes.WinDLL(caminho)
            lib.nvdaController_speakText.argtypes = [ctypes.c_wchar_p]
            self.lib = lib
        except Exception as e:  # pragma: no cover - depende do Windows
            self.motivo = "erro ao carregar a DLL: %r" % e
        finally:
            if self.motivo:
                log.info("fala direta indisponível: %s", self.motivo)

    def ativa(self):
        if self.lib is None:
            return False
        try:
            return self.lib.nvdaController_testIfRunning() == 0
        except Exception:
            return False

    def falar(self, texto, interromper=False):
        if not texto or not self.ativa():
            return False
        try:
            if interromper:
                self.lib.nvdaController_cancelSpeech()
            return self.lib.nvdaController_speakText(texto) == 0
        except Exception as e:
            log.warning("erro ao falar: %r", e)
            return False


def bipe(tipo="nova"):
    """Sons curtos: nova (mensagem recebida), enviada, erro. Tocam numa
    thread a parte para nao travar a janela."""
    if winsound is None:
        return
    threading.Thread(target=_tocar, args=(tipo,), daemon=True).start()


def _tocar(tipo):
    try:
        if tipo == "nova":
            winsound.Beep(880, 90)
            winsound.Beep(1175, 120)
        elif tipo == "enviada":
            winsound.Beep(660, 80)
        else:
            winsound.Beep(300, 200)
    except Exception:
        pass

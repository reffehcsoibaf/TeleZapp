# -*- coding: utf-8 -*-
"""Fala pelo NVDA (e sons simples) para o prototipo da interface.

Usa a DLL nvdaControllerClient que vem dentro do pacote accessible-output2,
carregada direto por ctypes (sem importar o pacote, que e antigo e puxa
dependencias). Se o NVDA nao estiver aberto ou a DLL nao for achada, a fala
fica desligada e o motivo vai para o log.
"""
import ctypes
import importlib.util
import os
import struct

try:
    import winsound
except ImportError:
    winsound = None


class Fala:
    def __init__(self, log):
        self.log = log
        self.lib = None
        self.motivo = ""
        self.chamadas = 0
        self._carregar()

    def _carregar(self):
        try:
            spec = importlib.util.find_spec("accessible_output2")
            if spec is None or not spec.origin:
                self.motivo = "pacote accessible_output2 nao instalado"
                return
            nome = ("nvdaControllerClient64.dll"
                    if struct.calcsize("P") == 8
                    else "nvdaControllerClient32.dll")
            caminho = os.path.join(os.path.dirname(spec.origin), "lib", nome)
            if not os.path.isfile(caminho):
                self.motivo = "DLL nao encontrada em " + caminho
                return
            lib = ctypes.WinDLL(caminho)
            lib.nvdaController_speakText.argtypes = [ctypes.c_wchar_p]
            self.lib = lib
        except Exception as e:  # pragma: no cover - depende do Windows
            self.motivo = "erro ao carregar a DLL: %r" % e

    def nvda_ativo(self):
        if self.lib is None:
            return False
        try:
            return self.lib.nvdaController_testIfRunning() == 0
        except Exception:
            return False

    def falar(self, texto, interromper=False):
        """Fala pelo NVDA. Devolve True se a chamada foi feita."""
        if not self.nvda_ativo():
            return False
        try:
            if interromper:
                self.lib.nvdaController_cancelSpeech()
            codigo = self.lib.nvdaController_speakText(texto)
            self.chamadas += 1
            if self.chamadas <= 5 or codigo != 0:
                self.log("fala pelo NVDA: codigo=%s tamanho=%d" % (
                    codigo, len(texto)))
            return codigo == 0
        except Exception as e:
            self.log("erro ao falar pelo NVDA: %r" % e)
            return False

    def calar(self):
        if self.nvda_ativo():
            try:
                self.lib.nvdaController_cancelSpeech()
            except Exception:
                pass


def bipe(tipo="nova"):
    """Sons curtos: nova (mensagem recebida), enviada, erro."""
    if winsound is None:
        return
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

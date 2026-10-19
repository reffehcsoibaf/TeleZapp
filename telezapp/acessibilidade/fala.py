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


# O que a pessoa escolheu para cada evento (opcoes som_*): "" = som padrao,
# "desligado" ou o caminho de um arquivo de som
_sons = {}
LIMITE_SEGUNDOS_ARQUIVO = 15


# Eventos que, no som padrao, tocam o mesmo som de outro (e acompanham a
# escolha dele): a pessoa so muda se quiser diferenciar
HERDA = {"nova_aberta": "nova", "nova_grupo": "nova",
         "reconectada": "conectado", "falha_envio": "erro",
         "tarefa_pronta": "enviada"}


def tom_padrao(tipo):
    """O tipo cujo som sintetico o evento usa quando nao ha escolha."""
    while tipo in HERDA:
        tipo = HERDA[tipo]
    return tipo


def definir_sons(mapa):
    """Troca as escolhas de som: {evento: valor}."""
    _sons.clear()
    _sons.update(mapa)


def caminho_do_som(valor):
    """Arquivo de som de uma escolha: um nome vai para a pasta de sons do
    TeleZapp; um caminho completo (versoes antigas) vale como esta."""
    if not valor or valor == "desligado":
        return ""
    if os.path.isabs(valor):
        return valor
    from telezapp import config
    return os.path.join(config.pasta_sons(), valor)


def acao_do_som(tipo, valor=None):
    """("nenhum" | "arquivo" | "padrao", caminho) para o evento, pela escolha
    guardada ou pelo `valor` dado (para ouvir antes de aplicar)."""
    valor = _sons.get(tipo, "") if valor is None else valor
    if valor == "desligado":
        return "nenhum", ""
    caminho = caminho_do_som(valor)
    if caminho and os.path.isfile(caminho):
        return "arquivo", caminho
    if not valor and tipo in HERDA:
        return acao_do_som(HERDA[tipo])        # acompanha o outro evento
    return "padrao", ""       # sem som escolhido ou arquivo que sumiu


def bipe(tipo="nova", valor=None):
    """Sons curtos: nova (mensagem recebida), enviada, erro, pronto
    (codigo ou QR pronto), atualizado (QR trocado), conectado e, nas
    chamadas, toque, chamando e desligada. Cada um pode ser desligado ou
    trocado por um arquivo de som (opcoes som_*). Tocam numa thread a parte
    para nao travar a janela."""
    acao, caminho = acao_do_som(tipo, valor)
    if acao == "nenhum":
        return
    if acao == "arquivo":
        threading.Thread(target=_tocar_arquivo, args=(tipo, caminho),
                         daemon=True).start()
        return
    if winsound is None:
        return
    threading.Thread(target=_tocar, args=(tom_padrao(tipo),),
                     daemon=True).start()


def _tocar_arquivo(tipo, caminho):
    """Toca o arquivo de som (as primeiras LIMITE_SEGUNDOS_ARQUIVO); se nao
    der, cai no som padrao do evento."""
    try:
        import sounddevice as sd
        import soundfile as sf
        with sf.SoundFile(caminho) as f:
            dados = f.read(int(f.samplerate * LIMITE_SEGUNDOS_ARQUIVO),
                           dtype="float32", always_2d=True)
            taxa = f.samplerate
        sd.play(dados, taxa)
    except Exception as e:
        log.warning("não consegui tocar o som escolhido (%r); usando o "
                    "padrão", e)
        if winsound is not None:
            _tocar(tom_padrao(tipo))


def _tocar(tipo):
    try:
        if tipo == "nova":
            winsound.Beep(880, 90)
            winsound.Beep(1175, 120)
        elif tipo == "enviada":
            winsound.Beep(660, 80)
        elif tipo == "pronto":
            for f in (660, 880, 1100):
                winsound.Beep(f, 90)
        elif tipo == "atualizado":
            winsound.Beep(990, 70)
            winsound.Beep(990, 70)
        elif tipo == "conectado":
            for f in (523, 659, 784, 1047):
                winsound.Beep(f, 110)
        elif tipo == "toque":
            # chamada recebida: dois pares de notas, repetido pela janela
            for f in (784, 988, 784, 988):
                winsound.Beep(f, 120)
        elif tipo == "chamando":
            # chamada que eu fiz: um tom grave e longo, como o de espera
            winsound.Beep(425, 400)
        elif tipo == "desconectada":
            # conta que caiu: dois tons descendo, mais graves que o de chamada
            for f in (440, 330):
                winsound.Beep(f, 150)
        elif tipo == "download_pronto":
            for f in (740, 988):
                winsound.Beep(f, 70)
        elif tipo == "desligada":
            for f in (494, 392, 330):
                winsound.Beep(f, 120)
        else:
            winsound.Beep(300, 200)
    except Exception:
        pass

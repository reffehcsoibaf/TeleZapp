# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Gravacao de nota de voz: do microfone ou do som interno do computador.

O som interno e capturado por "loopback" do WASAPI: o que a placa de som
toca (o navegador, um video, a fala do leitor de tela). O microfone usa a
sounddevice, validada nos experimentos; o loopback usa a soundcard, porque a
sounddevice do Windows nao tem essa captura.

A gravacao vai direto para um WAV temporario (nada fica na memoria, entao
nao ha limite pratico de duracao) e, ao parar, vira Ogg/Opus mono de 48 kHz:
o formato de nota de voz dos dois servicos. Quem usa o Gravador so conhece
`iniciar`, `parar` e `cancelar`.
"""
import logging
import math
import os
import threading
import time
from dataclasses import dataclass

log = logging.getLogger("telezapp.gravador")

TAXA = 48000                 # taxa do Opus: a unica que o cabecalho Ogg usa
BLOCO_S = 0.1                # leitura da fonte em blocos de 100 ms
PICO_MINIMO_DB = -50.0       # abaixo disso a gravacao saiu muda
ESPERA_ABERTURA_S = 8.0

MICROFONE = "microfone"
SOM_INTERNO = "som_interno"


class ErroGravacao(Exception):
    """Falha esperada; o texto e dito a pessoa."""


@dataclass
class Gravacao:
    caminho: str            # Ogg/Opus pronto para enviar
    segundos: float
    pico_db: float

    @property
    def silenciosa(self):
        return self.pico_db < PICO_MINIMO_DB


def para_dbfs(valor):
    return 20 * math.log10(max(float(valor), 1e-6))


# ------------------------------------------------------------------ fontes
class FonteMicrofone:
    """Microfone padrao do Windows, em mono."""

    origem = MICROFONE

    def __init__(self):
        try:
            import sounddevice as sd
        except Exception as e:      # biblioteca ou driver ausentes
            raise ErroGravacao("Não consegui carregar o sistema de áudio "
                               "(%s)." % type(e).__name__)
        try:
            info = sd.query_devices(kind="input")
        except Exception:
            raise ErroGravacao(
                "Não encontrei nenhum microfone. Conecte um microfone ou "
                "ative um nas configurações de som do Windows.")
        taxa = None
        for candidata in (TAXA, int(info["default_samplerate"])):
            try:
                sd.check_input_settings(samplerate=candidata, channels=1)
                taxa = candidata
                break
            except Exception:
                continue
        if taxa is None:
            raise ErroGravacao("O microfone não aceitou nenhuma taxa de "
                               "gravação conhecida.")
        self.nome = info["name"]
        self.taxa = taxa
        self._bloco = max(256, int(taxa * BLOCO_S))
        try:
            self._fluxo = sd.InputStream(samplerate=taxa, channels=1,
                                         dtype="float32",
                                         blocksize=self._bloco)
            self._fluxo.start()
        except Exception as e:
            raise ErroGravacao(
                "Não consegui abrir o microfone (%s). Veja, nas "
                "configurações do Windows, em Privacidade e segurança, "
                "Microfone, se os aplicativos de área de trabalho podem "
                "usá-lo." % type(e).__name__)

    def ler(self):
        dados, _ = self._fluxo.read(self._bloco)
        return dados.reshape(len(dados), -1)[:, 0]

    def fechar(self):
        try:
            self._fluxo.stop()
            self._fluxo.close()
        except Exception:
            pass


class FonteSomInterno:
    """O que toca na saida de som padrao (loopback do WASAPI), em mono."""

    origem = SOM_INTERNO

    def __init__(self):
        try:
            import soundcard as sc
        except Exception as e:
            raise ErroGravacao("Não consegui carregar a captura do som do "
                               "computador (%s)." % type(e).__name__)
        try:
            saida = sc.default_speaker()
            captura = sc.get_microphone(id=str(saida.name),
                                        include_loopback=True)
        except Exception:
            raise ErroGravacao(
                "Não encontrei uma saída de som para capturar. Confira se "
                "há alto-falantes ou fones ativos nas configurações de som "
                "do Windows.")
        self.nome = saida.name
        self.taxa = TAXA
        self._bloco = int(TAXA * BLOCO_S)
        try:
            self._gravador = captura.recorder(samplerate=TAXA, channels=2,
                                              blocksize=self._bloco)
            self._gravador.__enter__()
        except Exception as e:
            raise ErroGravacao("Não consegui capturar o som do computador "
                               "(%s)." % type(e).__name__)

    def ler(self):
        dados = self._gravador.record(numframes=self._bloco)
        return dados.reshape(len(dados), -1).mean(axis=1).astype("float32")

    def fechar(self):
        try:
            self._gravador.__exit__(None, None, None)
        except Exception:
            pass


FABRICAS = {MICROFONE: FonteMicrofone, SOM_INTERNO: FonteSomInterno}


# --------------------------------------------------------------- gravador
class Gravador:
    """Uma gravacao. `fabrica_fonte()` abre a fonte (dentro da thread da
    gravacao: o COM e o PortAudio gostam de ficar numa thread so)."""

    def __init__(self, pasta, origem=MICROFONE, fabrica_fonte=None,
                 maximo_segundos=0):
        self.pasta = pasta
        self.origem = origem
        self._fabrica = fabrica_fonte or FABRICAS[origem]
        self.maximo_segundos = maximo_segundos
        self._wav = None
        self._frames = 0
        self._taxa = TAXA
        self._pico = 0.0
        self._parar = threading.Event()
        self._pausa = threading.Event()
        self._cancelado = False
        self._pronto = threading.Event()
        self._erro = None
        self._thread = None
        self.nome_dispositivo = ""
        self.estourou_limite = False

    # ---------------------------------------------------------- consulta
    @property
    def decorrido(self):
        return self._frames / float(self._taxa) if self._taxa else 0.0

    @property
    def pico_db(self):
        return para_dbfs(self._pico)

    @property
    def gravando(self):
        return self._thread is not None and self._thread.is_alive() and \
            not self._parar.is_set()

    @property
    def pausado(self):
        return self._pausa.is_set()

    # ----------------------------------------------------------- controle
    def pausar(self):
        """Deixa de gravar sem fechar a captura; `continuar()` retoma e o
        trecho da pausa nao entra na gravacao."""
        self._pausa.set()

    def continuar(self):
        self._pausa.clear()

    def iniciar(self):
        """Comeca a gravar. Levanta ErroGravacao se a fonte nao abrir."""
        if self._thread is not None:
            raise RuntimeError("a gravação já foi iniciada")
        os.makedirs(self.pasta, exist_ok=True)
        self._wav = os.path.join(self.pasta, "gravando-%d.wav" %
                                 (time.time() * 1000))
        self._thread = threading.Thread(target=self._rodar, daemon=True,
                                        name="gravador")
        self._thread.start()
        if not self._pronto.wait(ESPERA_ABERTURA_S):
            self._parar.set()
            raise ErroGravacao("A captura de áudio demorou demais para "
                               "começar.")
        if self._erro is not None:
            self._thread.join(2)
            self._limpar()
            raise self._erro

    def parar(self):
        """Termina e devolve a Gravacao (Ogg/Opus pronto)."""
        self._terminar()
        if self._frames == 0:
            self._limpar()
            raise ErroGravacao("Nada foi gravado.")
        destino = self._wav[:-4].replace("gravando-", "voz-") + ".ogg"
        try:
            converter(self._wav, destino)
        except Exception as e:
            log.exception("falha ao codificar a gravação")
            raise ErroGravacao("Não consegui salvar a gravação (%s)." %
                               type(e).__name__)
        finally:
            self._limpar()
        return Gravacao(destino, self.decorrido, self.pico_db)

    def cancelar(self):
        self._cancelado = True
        self._terminar()
        self._limpar()

    # ------------------------------------------------------------ interno
    def _terminar(self):
        self._parar.set()
        if self._thread is not None:
            self._thread.join(5)

    def _limpar(self):
        if self._wav and os.path.exists(self._wav):
            try:
                os.remove(self._wav)
            except OSError:
                pass

    def _rodar(self):
        import soundfile as sf
        fonte = None
        try:
            try:
                fonte = self._fabrica()
            except ErroGravacao as e:
                self._erro = e
                return
            except Exception as e:
                log.exception("fonte de áudio falhou")
                self._erro = ErroGravacao(
                    "Não consegui abrir a captura de áudio (%s)." %
                    type(e).__name__)
                return
            finally:
                if self._erro is not None:
                    self._pronto.set()
            self._taxa = fonte.taxa
            self.nome_dispositivo = getattr(fonte, "nome", "")
            log.info("gravando (%s) em %s a %d Hz", self.origem,
                     self.nome_dispositivo, self._taxa)
            with sf.SoundFile(self._wav, "w", samplerate=self._taxa,
                              channels=1, subtype="PCM_16") as arquivo:
                self._pronto.set()
                while not self._parar.is_set():
                    bloco = fonte.ler()
                    if len(bloco) == 0 or self._pausa.is_set():
                        continue      # na pausa a captura segue aberta
                    pico = float(abs(bloco).max())
                    if pico > self._pico:
                        self._pico = pico
                    arquivo.write(bloco)
                    self._frames += len(bloco)
                    if self.maximo_segundos and \
                            self.decorrido >= self.maximo_segundos:
                        self.estourou_limite = True
                        self._parar.set()
        except Exception as e:
            log.exception("erro durante a gravação")
            if not self._pronto.is_set():
                self._erro = ErroGravacao(
                    "A gravação falhou (%s)." % type(e).__name__)
                self._pronto.set()
        finally:
            if fonte is not None:
                fonte.fechar()
            self._pronto.set()


def _mono(bloco):
    """Junta os canais de um bloco (estereo vira a media dos dois)."""
    return bloco if bloco.ndim == 1 else bloco.mean(axis=1)


def converter(wav, destino):
    """WAV mono (qualquer taxa) -> Ogg/Opus mono de 48 kHz, em blocos, com
    interpolacao linear quando a taxa nao e 48 kHz (suficiente para voz)."""
    import numpy as np
    import soundfile as sf
    with sf.SoundFile(wav) as entrada, sf.SoundFile(
            destino, "w", samplerate=TAXA, channels=1, format="OGG",
            subtype="OPUS") as saida:
        taxa = entrada.samplerate
        if taxa == TAXA:
            for bloco in entrada.blocks(blocksize=TAXA, dtype="float32"):
                saida.write(_mono(bloco))
            return
        passo = taxa / float(TAXA)   # amostras de entrada por amostra de saida
        pos = 0.0                    # posicao da proxima saida no buffer
        resto = np.empty(0, dtype="float32")
        for bloco in entrada.blocks(blocksize=taxa, dtype="float32"):
            buf = np.concatenate([resto, _mono(bloco)])
            n = len(buf)
            if n < 2:
                resto = buf
                continue
            k = int(math.floor((n - 1 - pos) / passo)) + 1
            if k > 0:
                xs = pos + passo * np.arange(k)
                saida.write(np.interp(xs, np.arange(n), buf).astype(
                    "float32"))
                pos += passo * k
            gasto = int(pos)
            resto = buf[gasto:]
            pos -= gasto

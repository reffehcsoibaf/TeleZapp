# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Motor de audio do app: decodifica com soundfile (Ogg/Opus, MP3, WAV,
FLAC...) e toca com sounddevice, lendo o arquivo aos poucos (sem carregar
tudo na memoria). Pausa, retoma e anda para qualquer ponto.

Formatos que a libsndfile nao abre (m4a/aac, por exemplo) sao decodificados
antes pelo PyAV para um WAV temporario, que toca do mesmo jeito. Se nem assim
abrir, levanta FormatoNaoSuportado e a janela usa outro motor.
"""
import logging
import os
import tempfile
import threading

from telezapp.midia.velocidade import Esticador

log = logging.getLogger("telezapp.reprodutor")


class FormatoNaoSuportado(Exception):
    pass


def decodificar_para_wav(caminho, pasta=None):
    """Decodifica qualquer audio que o PyAV (FFmpeg) abra para um WAV de 16
    bits na pasta dada (padrao: a temporaria do sistema) e devolve o
    caminho do WAV."""
    import av
    import numpy as np
    import soundfile as sf
    entrada = av.open(caminho)
    destino = None
    try:
        fluxo = next(s for s in entrada.streams if s.type == "audio")
        taxa = fluxo.rate
        canais = 1 if fluxo.codec_context.channels == 1 else 2
        fd, destino = tempfile.mkstemp(".wav", "aac-", pasta)
        os.close(fd)
        with sf.SoundFile(destino, "w", samplerate=taxa, channels=canais,
                          subtype="PCM_16") as saida:
            conversor = av.AudioResampler(format="flt", layout=(
                "mono" if canais == 1 else "stereo"), rate=taxa)
            for quadro in entrada.decode(fluxo):
                for q in conversor.resample(quadro):
                    saida.write(q.to_ndarray().reshape(-1, canais))
            for q in conversor.resample(None):
                saida.write(q.to_ndarray().reshape(-1, canais))
        return destino
    except Exception:
        if destino:
            try:
                os.remove(destino)
            except OSError:
                pass
        raise
    finally:
        entrada.close()


class Reprodutor:
    def __init__(self, caminho, fabrica_saida=None):
        """fabrica_saida(taxa, canais, callback) -> objeto com start(),
        stop() e close() (padrao: sounddevice.OutputStream)."""
        self._wav = None
        try:
            import soundfile as sf
            try:
                self._arq = sf.SoundFile(caminho)
            except Exception:
                # m4a/aac e afins: a libsndfile nao abre; o PyAV decodifica
                from telezapp import config
                self._wav = decodificar_para_wav(caminho,
                                                 config.pasta("temp"))
                self._arq = sf.SoundFile(self._wav)
        except Exception as e:
            self._apagar_wav()
            raise FormatoNaoSuportado(str(e))
        self.taxa = self._arq.samplerate
        self.canais = self._arq.channels
        self.total = self._arq.frames
        self._fabrica = fabrica_saida or self._saida_padrao
        self._saida = None
        self._trava = threading.Lock()
        self._tocando = False
        self.terminou = False
        self._velocidade = 1.0
        self._esticador = None

    def _apagar_wav(self):
        wav, self._wav = self._wav, None
        if wav:
            try:
                os.remove(wav)
            except OSError:
                pass

    @staticmethod
    def _saida_padrao(taxa, canais, callback):
        import sounddevice as sd
        from telezapp.midia import dispositivos
        return sd.OutputStream(samplerate=taxa, channels=canais,
                               dtype="float32", callback=callback,
                               device=dispositivos.indice_da_saida())

    # ------------------------------------------------------------ estado
    @property
    def duracao(self):
        return self.total / float(self.taxa) if self.taxa else 0.0

    @property
    def posicao(self):
        with self._trava:
            return self._quadro_atual() / float(self.taxa)

    def _quadro_atual(self):
        if self._esticador is not None:
            return int(self._esticador.posicao)
        return self._arq.tell()

    @property
    def velocidade(self):
        return self._velocidade

    @velocidade.setter
    def velocidade(self, valor):
        """1,0 toca direto do arquivo; outra velocidade passa pelo esticador
        (muda o tempo, nao o tom). Vale na hora, tocando ou nao."""
        valor = float(valor)
        with self._trava:
            if valor == self._velocidade:
                return
            atual = self._quadro_atual()
            self._velocidade = valor
            if valor == 1.0:
                self._esticador = None
                self._arq.seek(min(atual, self.total))
            elif self._esticador is None:
                self._arq.seek(min(atual, self.total))
                self._esticador = Esticador(
                    self.taxa, self.canais, self._ler_arquivo, self.total,
                    inicio=min(atual, self.total))

    def _ler_arquivo(self, n):
        return self._arq.read(n, dtype="float32", always_2d=True)

    @property
    def tocando(self):
        return self._tocando

    # ---------------------------------------------------------- controles
    def tocar(self):
        with self._trava:
            if self._quadro_atual() >= self.total:
                self._arq.seek(0)
                if self._esticador is not None:
                    self._esticador.reiniciar(0)
            self.terminou = False
            self._tocando = True
        if self._saida is None:
            self._saida = self._fabrica(self.taxa, self.canais,
                                        self._callback)
            self._saida.start()

    def pausar(self):
        self._tocando = False

    def alternar(self):
        if self._tocando:
            self.pausar()
        else:
            self.tocar()

    def ir_para(self, segundos):
        with self._trava:
            quadro = int(max(0.0, min(segundos, self.duracao)) * self.taxa)
            quadro = min(quadro, self.total)
            self._arq.seek(quadro)
            if self._esticador is not None:
                self._esticador.reiniciar(quadro)
            self.terminou = False

    def avancar(self, delta):
        self.ir_para(self.posicao + delta)

    def fechar(self):
        self._tocando = False
        saida, self._saida = self._saida, None
        if saida is not None:
            try:
                saida.stop()
                saida.close()
            except Exception:
                log.exception("erro ao fechar a saída de áudio")
        with self._trava:
            try:
                self._arq.close()
            except Exception:
                pass
        self._apagar_wav()

    # ---------------------------------------------------------- callback
    def _callback(self, saida, quadros, tempo, status):
        """Roda na thread do audio: so le o arquivo e copia."""
        saida.fill(0)
        if not self._tocando:
            return
        with self._trava:
            try:
                if self._esticador is not None:
                    dados = self._esticador.produzir(quadros,
                                                     self._velocidade)
                    fim = self._esticador.terminou
                else:
                    dados = self._arq.read(quadros, dtype="float32",
                                           always_2d=True)
                    fim = (len(dados) < quadros or
                           self._arq.tell() >= self.total)
            except Exception:
                log.exception("erro no áudio")
                self._tocando = False
                return
            n = len(dados)
            if n:
                saida[:n] = dados
            if fim:
                self._tocando = False
                self.terminou = True


def formatar_tempo(segundos):
    s = int(round(segundos))
    return "%d:%02d" % divmod(s, 60) if s < 3600 else "%d:%02d:%02d" % (
        s // 3600, s % 3600 // 60, s % 60)

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Motor de audio do app: decodifica com soundfile (Ogg/Opus, MP3, WAV,
FLAC...) e toca com sounddevice, lendo o arquivo aos poucos (sem carregar
tudo na memoria). Pausa, retoma e anda para qualquer ponto.

Formatos que a libsndfile nao abre (m4a/aac, por exemplo) levantam
FormatoNaoSuportado; a janela usa outro motor nesses casos.
"""
import logging
import threading

from telezapp.midia.velocidade import Esticador

log = logging.getLogger("telezapp.reprodutor")


class FormatoNaoSuportado(Exception):
    pass


class Reprodutor:
    def __init__(self, caminho, fabrica_saida=None):
        """fabrica_saida(taxa, canais, callback) -> objeto com start(),
        stop() e close() (padrao: sounddevice.OutputStream)."""
        try:
            import soundfile as sf
            self._arq = sf.SoundFile(caminho)
        except Exception as e:
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

    @staticmethod
    def _saida_padrao(taxa, canais, callback):
        import sounddevice as sd
        return sd.OutputStream(samplerate=taxa, channels=canais,
                               dtype="float32", callback=callback)

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

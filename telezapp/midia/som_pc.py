# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""O som do computador numa chamada: captura do que toca numa saída de som
(loopback do WASAPI) em quadros de 60 ms, PCM de 16 bits, 16 kHz, mono (o
mesmo formato do microfone da chamada), e a mistura desse som com o do
microfone.

A captura roda numa thread própria e guarda os quadros numa fila pequena: a
thread do microfone da chamada nunca espera por ela (o loopback do Windows
não entrega nada enquanto nada toca). Sem quadro, entra silêncio.
"""
import collections
import logging
import threading

import numpy as np

log = logging.getLogger("telezapp.som_pc")

TAXA = 16000
AMOSTRAS = 960                    # 60 ms
BYTES_POR_QUADRO = AMOSTRAS * 2
SILENCIO = bytes(BYTES_POR_QUADRO)
QUADROS_NA_FILA = 8               # cerca de meio segundo


def misturar(a, b):
    """Soma dois quadros PCM s16le (bytes), sem estourar. Um deles vazio ou
    de outro tamanho: devolve o outro."""
    if not a:
        return bytes(b)
    if not b or len(a) != len(b):
        return bytes(a)
    soma = (np.frombuffer(a, dtype="<i2").astype("int32")
            + np.frombuffer(b, dtype="<i2").astype("int32"))
    return np.clip(soma, -32768, 32767).astype("<i2").tobytes()


def _abrir_loopback(nome_saida=""):
    """Abre a captura do som do computador. Primeiro tenta o loopback por
    processo (todo o som, menos o do TeleZapp: a voz do outro lado e os
    avisos do programa nunca entram; `exato`); sem ele, o loopback comum da
    saída `nome_saida` (vazio: a padrão do Windows), que capta também a voz
    da chamada. Devolve um objeto com `nome`, `exato`, `ler()` (um quadro,
    em bytes) e `fechar()`."""
    try:
        from telezapp.midia import som_por_processo
        return som_por_processo.abrir()
    except Exception as e:
        log.info("loopback por processo indisponível (%s); usando o "
                 "comum", e)
    import soundcard as sc
    from telezapp.midia import dispositivos
    saida = sc.default_speaker()
    if nome_saida:
        for alto_falante in sc.all_speakers():
            if dispositivos.parecem_o_mesmo(nome_saida, alto_falante.name):
                saida = alto_falante
                break
    captura = sc.get_microphone(id=str(saida.name), include_loopback=True)
    gravador = captura.recorder(samplerate=TAXA, channels=2,
                                blocksize=AMOSTRAS)
    gravador.__enter__()

    class Fonte:
        nome = saida.name
        exato = False

        @staticmethod
        def ler():
            dados = gravador.record(numframes=AMOSTRAS)
            mono = np.asarray(dados, dtype="float32").reshape(
                len(dados), -1).mean(axis=1)
            return (np.clip(mono, -1.0, 1.0) * 32767).astype("<i2").tobytes()

        @staticmethod
        def fechar():
            try:
                gravador.__exit__(None, None, None)
            except Exception:
                pass
    return Fonte()


def disponivel():
    """A captura do som do computador (soundcard) pode ser importada?"""
    try:
        import soundcard  # noqa: F401
        return True
    except Exception:
        return False


def saidas_do_computador():
    """Nomes das saídas de som, para escolher o que capturar."""
    try:
        import soundcard as sc
        nomes = []
        for s in sc.all_speakers():
            if s.name not in nomes:
                nomes.append(s.name)
        return nomes
    except Exception:
        log.exception("erro ao listar as saídas de som")
        return []


def saida_padrao():
    """O nome da saída de som padrão do Windows (vazio se não souber)."""
    try:
        import soundcard as sc
        return sc.default_speaker().name
    except Exception:
        return ""


class CapturaDoSom:
    """Captura o som do computador numa thread. `ler()` entrega o quadro
    mais antigo da fila (ou silêncio, se não há)."""

    def __init__(self, nome_saida="", abrir=None):
        self.nome_saida = nome_saida
        self._abrir = abrir or _abrir_loopback
        self._fila = collections.deque(maxlen=QUADROS_NA_FILA)
        self._parar = threading.Event()
        self._thread = None
        self.nome = ""              # a saída de fato capturada
        self.exato = False          # sem o som do TeleZapp (por processo)
        self.erro = ""
        self.quadros = 0
        self._aberto = threading.Event()

    def iniciar(self, espera_s=8.0):
        """Abre a captura na thread dela e espera ate saber se abriu (e se e
        a exata)."""
        self._thread = threading.Thread(target=self._laco,
                                        name="chamada-som-pc", daemon=True)
        self._thread.start()
        self._aberto.wait(espera_s)

    def _laco(self):
        fonte = None
        try:
            fonte = self._abrir(self.nome_saida)
            self.nome = getattr(fonte, "nome", "") or self.nome_saida
            self.exato = bool(getattr(fonte, "exato", False))
            log.info("som do computador capturado (%s%s)",
                     self.nome or "padrão do Windows",
                     ", sem o som do TeleZapp" if self.exato else "")
            self._aberto.set()
            while not self._parar.is_set():
                quadro = fonte.ler()
                if len(quadro) == BYTES_POR_QUADRO:
                    self._fila.append(quadro)
                    self.quadros += 1
        except Exception as e:
            self.erro = "%s: %s" % (type(e).__name__, e)
            if not self._parar.is_set():
                log.warning("a captura do som do computador parou: %s",
                            self.erro)
        finally:
            self._aberto.set()
            if fonte is not None:
                try:
                    fonte.fechar()
                except Exception:
                    pass

    def ler(self):
        try:
            return self._fila.popleft()
        except IndexError:
            return SILENCIO

    @property
    def viva(self):
        return self._thread is not None and self._thread.is_alive()

    def parar(self):
        self._parar.set()

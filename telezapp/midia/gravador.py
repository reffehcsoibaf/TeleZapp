# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Gravacao de nota de voz: do microfone, do som interno do computador ou dos
dois juntos.

O som interno e capturado por "loopback" do WASAPI: o que a placa de som
toca (o navegador, um video, a fala do leitor de tela). O microfone usa a
sounddevice, validada nos experimentos; o loopback usa a soundcard, porque a
sounddevice do Windows nao tem essa captura.

A gravacao vai direto para um WAV temporario (nada fica na memoria, entao
nao ha limite pratico de duracao) e, ao parar, vira Ogg/Opus de 48 kHz: o
formato de nota de voz dos dois servicos. Mono por padrao; o microfone e o
som do computador podem ser gravados em estereo (opcoes da pessoa), com a
taxa em kbps escolhida e um ganho de volume. Quem usa o Gravador so conhece
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
SOM_E_MICROFONE = "som_e_microfone"     # o som interno somado ao microfone


class ErroGravacao(Exception):
    """Falha esperada; o texto e dito a pessoa."""


@dataclass
class Gravacao:
    caminho: str            # Ogg/Opus (mono) ou M4A/AAC (estereo), pronto
    segundos: float
    pico_db: float
    # Estereo: M4A (AAC-LC, 48 kHz, moov no comeco). O iPhone nao toca
    # mensagem de voz estereo em Opus, mas toca em AAC, com o controle de
    # velocidade (o mesmo que o WinZapp faz). O Telegram so trata como
    # mensagem de voz o Opus: la o estereo vai como audio comum.
    estereo: bool = False

    def como_voz_em(self, servico):
        return not self.estereo or servico == "whatsapp"

    @property
    def silenciosa(self):
        return self.pico_db < PICO_MINIMO_DB


def para_dbfs(valor):
    return 20 * math.log10(max(float(valor), 1e-6))


# ------------------------------------------------------------------ fontes
class FonteMicrofone:
    """O microfone escolhido (ou o padrao do Windows), em mono ou, se pedido
    e o microfone tiver dois canais, em estereo."""

    origem = MICROFONE

    def __init__(self, estereo=False):
        try:
            import sounddevice as sd
        except Exception as e:      # biblioteca ou driver ausentes
            raise ErroGravacao("Não consegui carregar o sistema de áudio "
                               "(%s)." % type(e).__name__)
        from telezapp.midia import dispositivos
        dispositivo = dispositivos.indice_do_microfone()   # None = padrao
        try:
            info = sd.query_devices(dispositivo) if dispositivo is not None \
                else sd.query_devices(kind="input")
        except Exception:
            raise ErroGravacao(
                "Não encontrei nenhum microfone. Conecte um microfone ou "
                "ative um nas configurações de som do Windows.")
        taxa = None
        canais = 2 if estereo and int(
            info.get("max_input_channels", 1) or 1) >= 2 else 1
        for tentados in ((2, 1) if canais == 2 else (1,)):
            for candidata in (TAXA, int(info["default_samplerate"])):
                try:
                    sd.check_input_settings(device=dispositivo,
                                            samplerate=candidata,
                                            channels=tentados)
                    taxa, canais = candidata, tentados
                    break
                except Exception:
                    continue
            if taxa is not None:
                break
        if estereo and canais == 1:
            log.info("o microfone só grava em um canal: gravação em mono")
        self.canais = canais
        if taxa is None:
            raise ErroGravacao("O microfone não aceitou nenhuma taxa de "
                               "gravação conhecida.")
        self.nome = info["name"]
        self.taxa = taxa
        self._bloco = max(256, int(taxa * BLOCO_S))
        try:
            self._fluxo = sd.InputStream(samplerate=taxa, channels=canais,
                                         dtype="float32", device=dispositivo,
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
        dados = dados.reshape(len(dados), -1)
        return dados[:, :2] if self.canais == 2 else dados[:, 0]

    def fechar(self):
        try:
            self._fluxo.stop()
            self._fluxo.close()
        except Exception:
            pass


class FonteSomInterno:
    """O que toca na saida de som escolhida, ou na padrao (loopback do
    WASAPI), em mono ou, se pedido, em estereo."""

    origem = SOM_INTERNO

    def __init__(self, estereo=False):
        try:
            import soundcard as sc
        except Exception as e:
            raise ErroGravacao("Não consegui carregar a captura do som do "
                               "computador (%s)." % type(e).__name__)
        try:
            saida = sc.default_speaker()
            from telezapp.midia import dispositivos
            escolhida = dispositivos.saida()
            if escolhida:
                for alto_falante in sc.all_speakers():
                    if dispositivos.parecem_o_mesmo(escolhida,
                                                    alto_falante.name):
                        saida = alto_falante
                        break
            captura = sc.get_microphone(id=str(saida.name),
                                        include_loopback=True)
        except Exception:
            raise ErroGravacao(
                "Não encontrei uma saída de som para capturar. Confira se "
                "há alto-falantes ou fones ativos nas configurações de som "
                "do Windows.")
        self.nome = saida.name
        self.taxa = TAXA
        self.canais = 2 if estereo else 1
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
        dados = dados.reshape(len(dados), -1).astype("float32")
        if self.canais == 2:
            if dados.shape[1] == 1:
                return estereo_de(dados[:, 0])
            return dados[:, :2]
        return dados.mean(axis=1).astype("float32")

    def fechar(self):
        try:
            self._gravador.__exit__(None, None, None)
        except Exception:
            pass


def estereo_de(mono):
    """Bloco mono -> estereo com o mesmo som nos dois canais."""
    import numpy as np
    return np.stack([mono, mono], axis=1).astype("float32")


def misturar(som, mic, taxa_mic=TAXA):
    """Soma o bloco do microfone ao do som interno (float32). O som pode ser
    estereo: o microfone (em estereo, vira mono antes) entra igual nos dois
    canais.
    O microfone pode ter outra taxa ou um tamanho de bloco diferente: ele e
    reamostrado, por interpolacao linear, para o tamanho do bloco do som. O
    resultado e limitado a -1..1 para a soma nao estourar."""
    import numpy as np
    som = np.asarray(som, dtype="float32")
    mic = np.asarray(mic, dtype="float32")
    if len(mic) == 0:
        return som
    if mic.ndim == 2:
        mic = mic.mean(axis=1)
    if len(mic) != len(som):
        mic = np.interp(np.linspace(0, len(mic) - 1, len(som)),
                        np.arange(len(mic)), mic).astype("float32")
    if som.ndim == 2:
        mic = mic[:, None]
    return np.clip(som + mic, -1.0, 1.0).astype("float32")


class FonteMista:
    """O som interno somado ao microfone, em mono. O microfone liga e desliga
    com a gravacao em andamento (`microfone_ligado`); desligado, ele segue
    aberto e e lido e descartado, para o fluxo nao acumular e poder voltar
    na hora. Sem microfone no computador, grava so o som interno e avisa em
    `aviso`."""

    origem = SOM_E_MICROFONE

    def __init__(self, estereo=False, mic_estereo=False):
        self._som = FonteSomInterno(estereo)
        self.nome = self._som.nome
        self.taxa = TAXA
        self.canais = self._som.canais
        self.microfone_ligado = True
        self.aviso = ""
        self._mic = None
        try:
            self._mic = FonteMicrofone(mic_estereo)
        except ErroGravacao as e:
            log.warning("gravacao do som sem microfone: %s", e)
            self.aviso = str(e)
            self.microfone_ligado = False

    @property
    def microfone_disponivel(self):
        return self._mic is not None

    def ler(self):
        som = self._som.ler()
        if self._mic is None:
            return som
        mic = self._mic.ler()
        if not self.microfone_ligado:
            return som
        return misturar(som, mic, self._mic.taxa)

    def fechar(self):
        for fonte in (self._som, self._mic):
            if fonte is not None:
                fonte.fechar()


FABRICAS = {MICROFONE: FonteMicrofone, SOM_INTERNO: FonteSomInterno,
            SOM_E_MICROFONE: FonteMista}


# --------------------------------------------------------------- gravador
_ativos = set()


def gravando_agora():
    """Ha alguma gravacao capturando som (pausada tambem conta)? A janela usa
    isto para nao falar nem tocar avisos de mensagens por cima da voz."""
    return bool(_ativos)


class Gravador:
    """Uma gravacao. `fabrica_fonte()` abre a fonte (dentro da thread da
    gravacao: o COM e o PortAudio gostam de ficar numa thread so)."""

    def __init__(self, pasta, origem=MICROFONE, fabrica_fonte=None,
                 maximo_segundos=0, microfone_ligado=True,
                 estereo_microfone=False, estereo_som=False, kbps=None,
                 ganho=1.0):
        """`estereo_microfone`, `estereo_som`: gravar a fonte em dois canais
        (o som com microfone segue o do som). `kbps`: taxa total do Opus
        (None = a padrao da biblioteca). `ganho`: multiplica o volume."""
        self.pasta = pasta
        self.origem = origem
        self._microfone_ligado = microfone_ligado
        self._fonte = None
        if fabrica_fonte is None:
            if origem == MICROFONE:
                def fabrica_fonte():
                    return FonteMicrofone(estereo_microfone)
            elif origem == SOM_INTERNO:
                def fabrica_fonte():
                    return FonteSomInterno(estereo_som)
            else:
                def fabrica_fonte():
                    return FonteMista(estereo_som, estereo_microfone)
        self._fabrica = fabrica_fonte
        self.kbps = kbps        # numero, ou (mono, estereo)
        self.ganho = float(ganho or 1.0)
        self._canais = 1
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
    def canais(self):
        """1 ou 2: o que a fonte entregou (um microfone de um canal so
        grava mono mesmo com o estereo pedido)."""
        return self._canais

    @property
    def kbps_usados(self):
        """A taxa do Opus para os canais gravados (`kbps` pode ser um
        numero ou (mono, estereo))."""
        if isinstance(self.kbps, (tuple, list)):
            return self.kbps[1] if self._canais == 2 else self.kbps[0]
        return self.kbps

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

    @property
    def microfone_ligado(self):
        """So tem efeito na gravacao do som do computador com microfone."""
        return self._microfone_ligado

    @microfone_ligado.setter
    def microfone_ligado(self, ligado):
        self._microfone_ligado = bool(ligado)
        if self._fonte is not None and hasattr(self._fonte,
                                               "microfone_ligado"):
            self._fonte.microfone_ligado = bool(ligado) and getattr(
                self._fonte, "microfone_disponivel", True)

    @property
    def microfone_disponivel(self):
        """False quando a gravacao mista nao achou um microfone."""
        return getattr(self._fonte, "microfone_disponivel", True)

    @property
    def aviso(self):
        return getattr(self._fonte, "aviso", "")

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
        estereo = self._canais == 2
        destino = self._wav[:-4].replace("gravando-", "voz-") + (
            ".m4a" if estereo else ".ogg")
        try:
            if estereo:
                converter_m4a(self._wav, destino, self.kbps_usados)
            else:
                converter(self._wav, destino, self.kbps_usados)
        except Exception as e:
            log.exception("falha ao codificar a gravação")
            raise ErroGravacao("Não consegui salvar a gravação (%s)." %
                               type(e).__name__)
        finally:
            self._limpar()
        return Gravacao(destino, self.decorrido, self.pico_db, estereo)

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
            self._canais = getattr(fonte, "canais", 1)
            self._fonte = fonte
            self.microfone_ligado = self._microfone_ligado
            self.nome_dispositivo = getattr(fonte, "nome", "")
            log.info("gravando (%s) em %s a %d Hz, %s, volume %d%%%s",
                     self.origem, self.nome_dispositivo, self._taxa,
                     "estéreo" if self._canais == 2 else "mono",
                     round(self.ganho * 100),
                     ", %d kbps" % self.kbps_usados if self.kbps_usados
                     else "")
            with sf.SoundFile(self._wav, "w", samplerate=self._taxa,
                              channels=self._canais,
                              subtype="PCM_16") as arquivo:
                _ativos.add(self)
                self._pronto.set()
                while not self._parar.is_set():
                    bloco = fonte.ler()
                    if len(bloco) == 0 or self._pausa.is_set():
                        continue      # na pausa a captura segue aberta
                    if self.ganho != 1.0:
                        bloco = aplicar_ganho(bloco, self.ganho)
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
            _ativos.discard(self)
            if fonte is not None:
                fonte.fechar()
            self._pronto.set()


def converter_m4a(wav, destino, kbps=None):
    """WAV estereo -> M4A (AAC-LC, 48 kHz, dois canais, `moov` no comeco) para
    enviar como mensagem de voz: e o formato estereo que o iPhone toca como
    voz, com o controle de velocidade. O `moov` no comeco (faststart) deixa o
    iPhone comecar a tocar sem baixar tudo. Sem etiquetas nem capitulos."""
    import av
    import numpy as np
    import soundfile as sf
    with sf.SoundFile(wav) as entrada:
        saida = av.open(destino, "w", format="ipod",
                        options={"movflags": "+faststart"})
        try:
            fluxo = saida.add_stream("aac", rate=TAXA, layout="stereo")
            fluxo.bit_rate = int((kbps or 128) * 1000)
            fonte = entrada.samplerate
            for bloco in entrada.blocks(blocksize=fonte, dtype="float32"):
                if bloco.ndim == 1:
                    bloco = estereo_de(bloco)
                if fonte != TAXA:
                    n = int(round(len(bloco) * TAXA / float(fonte)))
                    xs = np.linspace(0, len(bloco) - 1, n)
                    bloco = np.stack([np.interp(xs, np.arange(len(bloco)),
                                                bloco[:, i])
                                      for i in range(2)], axis=1)
                quadro = av.AudioFrame.from_ndarray(
                    np.ascontiguousarray(bloco[:, :2].T.astype("float32")),
                    format="fltp", layout="stereo")
                quadro.sample_rate = TAXA
                for pacote in fluxo.encode(quadro):
                    saida.mux(pacote)
            for pacote in fluxo.encode(None):
                saida.mux(pacote)
        finally:
            saida.close()


def aplicar_ganho(bloco, ganho):
    """Volume da gravacao: multiplica e limita a -1..1 (sem estourar)."""
    import numpy as np
    return np.clip(bloco * ganho, -1.0, 1.0).astype("float32")


def _mono(bloco):
    """Junta os canais de um bloco (estereo vira a media dos dois)."""
    return bloco if bloco.ndim == 1 else bloco.mean(axis=1)


KBPS_MINIMO, KBPS_MAXIMO = 32, 256


def nivel_de_compressao(kbps, canais):
    """O nivel do libsndfile (0 a 1) para a taxa total pedida. Medido com o
    libsndfile 1.2.2: o Opus dele usa cerca de 6 + 250 x (1 - nivel) kbps
    por canal (0 = 256 por canal; 1 = 6)."""
    por_canal = float(kbps) / max(canais, 1)
    return min(1.0, max(0.0, 1.0 - (por_canal - 6.0) / 250.0))


def converter(wav, destino, kbps=None):
    """WAV mono ou estereo (qualquer taxa) -> Ogg/Opus de 48 kHz com os
    mesmos canais, em blocos, com interpolacao linear quando a taxa nao e
    48 kHz (suficiente para voz). `kbps`: taxa total; None = a padrao."""
    import soundfile as sf
    with sf.SoundFile(wav) as entrada:
        canais = 2 if entrada.channels >= 2 else 1
        extra = {} if not kbps else {
            "compression_level": nivel_de_compressao(kbps, canais)}

        def ajustar(bloco):
            if canais == 1:
                return _mono(bloco)
            return bloco[:, :2] if bloco.ndim == 2 else estereo_de(bloco)
        with sf.SoundFile(destino, "w", samplerate=TAXA, channels=canais,
                          format="OGG", subtype="OPUS", **extra) as saida:
            _reamostrar(entrada, saida, ajustar)


def _reamostrar(entrada, saida, ajustar):
    """Copia os blocos de `entrada` para `saida` em 48 kHz."""
    import numpy as np
    taxa = entrada.samplerate
    if taxa == TAXA:
        for bloco in entrada.blocks(blocksize=TAXA, dtype="float32"):
            saida.write(ajustar(bloco))
        return
    passo = taxa / float(TAXA)   # amostras de entrada por amostra de saida
    pos = 0.0                    # posicao da proxima saida no buffer
    resto = None
    for bloco in entrada.blocks(blocksize=taxa, dtype="float32"):
        bloco = ajustar(bloco)
        buf = bloco if resto is None else np.concatenate([resto, bloco])
        n = len(buf)
        if n < 2:
            resto = buf
            continue
        k = int(math.floor((n - 1 - pos) / passo)) + 1
        if k > 0:
            xs = pos + passo * np.arange(k)
            if buf.ndim == 1:
                novo = np.interp(xs, np.arange(n), buf)
            else:
                novo = np.stack([np.interp(xs, np.arange(n), buf[:, i])
                                 for i in range(buf.shape[1])], axis=1)
            saida.write(novo.astype("float32"))
            pos += passo * k
        gasto = int(pos)
        resto = buf[gasto:]
        pos -= gasto

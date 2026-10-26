# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Cancelamento de eco e reducao de ruido do microfone nas chamadas de voz.

Quem escuta a chamada pelo alto-falante faz o microfone captar a voz da outra
pessoa, que a ouve de volta. O TeleZapp toca o som e capta o microfone, entao
tem os dois sinais: o que foi para o alto-falante (a referencia) e o que o
microfone captou. Os dois passam pelo modulo de processamento de audio do
WebRTC (AEC3 e supressor de ruido, o motor do Chrome e do Google Meet), pelo
pacote `livekit`.

A ideia de segurar a referencia quando o eco volta muito tarde (retorno de
mesa de som, que pode levar mais de meio segundo) e do WinZapp (projeto do
Gabriel, GPL-3.0); o codigo aqui foi escrito para o fluxo do TeleZapp
(PCM de 16 kHz, mono, 16 bits). O AEC3 so acha eco ate cerca de 0,5 s depois
da referencia: acima disso a medida da correlacao entre as duas pontas
atrasa a referencia para o eco chegar uns 150 ms depois dela.

O modulo trabalha com quadros de exatamente 10 ms (160 amostras). Sem o
pacote (instalacao quebrada), o microfone segue sem tratamento: a chamada
nao falha.
"""
import logging
import threading

import numpy as np

log = logging.getLogger(__name__)

TAXA = 16000
QUADRO = TAXA // 100            # 10 ms, o unico tamanho que o modulo aceita
DECIMACAO = 2                   # a medida do eco usa 8 kHz (voz, barato)
TAXA_MEDIDA = TAXA // DECIMACAO
JANELA_S = 2.0                  # quanto som a medida olha
ATRASO_MAX_S = 1.5              # eco que volta ate 1,5 s depois
ADIANTO_MAX_S = 0.1             # a referencia pode chegar um pouco atrasada
ECO_DIRETO_MAX_MS = 350         # ate aqui o AEC3 acha o eco sozinho
ECO_ALVO_MS = 150               # acima, a referencia e segurada ate aqui
MEDIR_A_CADA = 100              # quadros de microfone (1 s)
CORRELACAO_MIN = 0.4            # eco claro; fala dos dois e silencio ficam abaixo
CONSISTENTE_MS = 20             # duas medidas seguidas devem concordar
PASSO_MIN_MS = 30
HISTERESE_MS = 50
REFERENCIA_MAX = TAXA * 2       # amostras da referencia que esperam

# Ligado pela janela a partir das opcoes `chamada_eco` e `chamada_ruido`
LIGADOS = {"eco": True, "ruido": True}


def definir(eco, ruido):
    LIGADOS["eco"], LIGADOS["ruido"] = bool(eco), bool(ruido)


def _criar_modulo(eco, ruido):
    from livekit import rtc
    return rtc.AudioProcessingModule(
        echo_cancellation=eco, noise_suppression=ruido,
        high_pass_filter=True,      # tira o ronco abaixo da voz, antes do AEC3
        auto_gain_control=False)    # o ganho do microfone e o do Windows


def _quadro(amostras):
    from livekit import rtc
    return rtc.AudioFrame(bytearray(amostras.tobytes()), TAXA, 1, QUADRO)


def _decimar(amostras):
    """16 kHz -> 8 kHz pela media de pares (filtro grosseiro, basta p/ medir)."""
    util = amostras.size - amostras.size % DECIMACAO
    return amostras[:util].astype(np.float64).reshape(
        -1, DECIMACAO).mean(axis=1)


def acoplamento(referencia, sinal, taxa=TAXA_MEDIDA,
                atraso_max_s=ATRASO_MAX_S, adianto_max_s=ADIANTO_MAX_S):
    """(coeficiente, atraso_ms): quanto de `referencia` o `sinal` traz e com
    que atraso. Os dois terminam no mesmo instante; a referencia pode ser mais
    longa (guarda o passado que a busca precisa). Coeficiente de 0 a 1: perto
    de 0,9 o sinal e quase uma copia (retorno); abaixo de 0,1 nao ha eco que
    se ouca. (0.0, None) se um dos lados esta em silencio."""
    sinal = np.asarray(sinal, dtype=np.float64)
    referencia = np.asarray(referencia, dtype=np.float64)
    n = sinal.size
    atras = int(atraso_max_s * taxa)
    adiante = int(adianto_max_s * taxa)
    if n == 0 or referencia.size < n:
        return 0.0, None
    tem = min(atras, referencia.size - n)
    ref = np.concatenate((np.zeros(atras - tem),
                          referencia[referencia.size - n - tem:],
                          np.zeros(adiante)))
    e_sinal = float(np.dot(sinal, sinal))
    if e_sinal < 1e-6 or float(np.dot(ref, ref)) < 1e-6:
        return 0.0, None
    tam = 1 << int(np.ceil(np.log2(ref.size + n)))
    corr = np.fft.irfft(np.fft.rfft(ref, tam) * np.conj(np.fft.rfft(sinal, tam)),
                        tam)
    desloc = np.arange(0, atras + adiante + 1)
    acumulada = np.concatenate(([0.0], np.cumsum(ref * ref)))
    e_janela = acumulada[desloc + n] - acumulada[desloc]
    coef = np.abs(corr[desloc]) / np.sqrt(np.maximum(e_janela, 1e-9) * e_sinal)
    coef[e_janela < 1e-6] = 0.0
    melhor = int(np.argmax(coef))
    return (round(float(min(1.0, coef[melhor])), 2),
            round((atras - melhor) * 1000 / taxa))


class CancelaEco:
    """Limpa o microfone de uma chamada. `referencia()` recebe o que foi para
    o alto-falante e `processar()` o que o microfone captou, nessa ordem de
    acontecimento; cada uma pode vir de uma thread."""

    def __init__(self, eco=True, ruido=True, fabrica=None):
        self._eco, self._ruido = bool(eco), bool(ruido)
        self._fabrica = fabrica or _criar_modulo
        self._trava = threading.Lock()
        self._indisponivel = False
        self._apm = None
        self.reiniciar()

    @property
    def disponivel(self):
        return self._apm is not None

    def reiniciar(self):
        """Esquece o caminho do eco aprendido (outra chamada, ou troca de
        dispositivo: o atraso e a resposta mudam)."""
        with self._trava:
            self._mic = np.empty(0, dtype=np.int16)
            self._ref = np.empty(0, dtype=np.int16)
            self._seguro = 0            # amostras de referencia seguradas
            self._quadros = self._quadros_ref = self._erros = 0
            self._hist_ref = np.empty(0)
            self._hist_mic = np.empty(0)
            self._hist_saida = np.empty(0)
            self._resto_ref = np.empty(0, dtype=np.int16)
            self._ultimo_atraso = None
            self._apm = None
            if self._indisponivel:
                return
            try:
                self._apm = self._fabrica(self._eco, self._ruido)
            except Exception:
                self._indisponivel = True      # uma vez basta para o log
                log.exception("processamento de áudio do WebRTC indisponível; "
                              "o microfone segue sem tratamento")

    # ---------------------------------------------------------- referencia
    def referencia(self, pcm):
        """O que foi para o alto-falante (PCM s16le, 16 kHz, mono)."""
        if self._apm is None or not self._eco:
            return
        dados = np.frombuffer(pcm, dtype="<i2")
        if not dados.size:
            return
        with self._trava:
            junto = np.concatenate((self._resto_ref, dados))
            inteiro = junto.size - junto.size % DECIMACAO
            self._resto_ref = junto[inteiro:]
            if inteiro:
                self._hist_ref = self._lembrar(
                    self._hist_ref, junto[:inteiro], JANELA_S + ATRASO_MAX_S)
            self._ref = np.concatenate((self._ref, dados))
            if self._ref.size > REFERENCIA_MAX:
                self._ref = self._ref[self._ref.size - REFERENCIA_MAX:]

    def _entregar_referencia(self):
        while self._ref.size - self._seguro >= QUADRO:
            parte, self._ref = self._ref[:QUADRO], self._ref[QUADRO:]
            try:
                self._apm.process_reverse_stream(_quadro(parte))
                self._quadros_ref += 1
            except Exception:
                self._erros += 1

    # ----------------------------------------------------------- microfone
    def processar(self, pcm):
        """O microfone sem eco e sem ruido (bytes). Sai em quadros de 10 ms:
        o que sobrar espera a proxima chamada. Sem o modulo, devolve igual."""
        if self._apm is None:
            return bytes(pcm)
        dados = np.frombuffer(pcm, dtype="<i2")
        saida = []
        with self._trava:
            self._mic = np.concatenate((self._mic, dados))
            if self._eco:
                self._entregar_referencia()
            while self._mic.size >= QUADRO:
                parte, self._mic = self._mic[:QUADRO], self._mic[QUADRO:]
                quadro = _quadro(parte)
                try:
                    self._apm.process_stream(quadro)
                    limpo = np.frombuffer(bytes(quadro.data), dtype="<i2")
                except Exception:
                    # um quadro recusado vai como captado: melhor um instante
                    # de eco que um buraco
                    self._erros += 1
                    limpo = parte
                saida.append(limpo)
                self._quadros += 1
                if self._eco:
                    self._hist_mic = self._lembrar(self._hist_mic, parte,
                                                   JANELA_S)
                    self._hist_saida = self._lembrar(self._hist_saida, limpo,
                                                     JANELA_S)
                    if self._quadros % MEDIR_A_CADA == 0 and \
                            self._hist_mic.size >= JANELA_S * TAXA_MEDIDA:
                        self._ajustar_atraso()
        return np.concatenate(saida).tobytes() if saida else b""

    def _ajustar_atraso(self):
        """Segura a referencia quando o eco volta tarde demais para o AEC3."""
        coef, atraso = acoplamento(self._hist_ref, self._hist_mic)
        if coef < CORRELACAO_MIN or atraso is None:
            self._ultimo_atraso = None
            return
        antes, self._ultimo_atraso = self._ultimo_atraso, atraso
        if antes is None or abs(atraso - antes) > CONSISTENTE_MS:
            return
        atual_ms = self._seguro * 1000 // TAXA
        # histerese: um caminho no limite nao liga e desliga a todo instante
        limite = ECO_DIRETO_MAX_MS - HISTERESE_MS if atual_ms \
            else ECO_DIRETO_MAX_MS
        alvo_ms = 0
        if atraso > limite:
            alvo_ms = max(0, (atraso - ECO_ALVO_MS) // 10 * 10)
        if abs(alvo_ms - atual_ms) < PASSO_MIN_MS:
            return
        novo = alvo_ms * TAXA // 1000
        if novo < self._seguro:
            # o que deixa de ser seguro ja foi ecoado: descarta em vez de
            # despejar de uma vez no AEC3
            fica = novo + self._ref.size - self._seguro
            self._ref = self._ref[max(0, self._ref.size - max(fica, novo)):]
        self._seguro = novo
        log.info("eco volta %s ms depois (correlação %s); referência "
                 "segurada por %s ms", atraso, coef, alvo_ms)

    @staticmethod
    def _lembrar(historia, trecho, segundos):
        historia = np.concatenate((historia, _decimar(trecho)))
        manter = int(segundos * TAXA_MEDIDA)
        return historia[-manter:] if historia.size > manter else historia

    # ------------------------------------------------------------ registro
    def diagnostico(self):
        """O que o processamento esta fazendo, para o log da chamada."""
        with self._trava:
            dados = {"motor": "webrtc" if self._apm is not None
                     else "indisponível",
                     "eco": self._eco, "ruido": self._ruido,
                     "quadros": self._quadros,
                     "quadros_referencia": self._quadros_ref,
                     "erros": self._erros,
                     "referencia_segurada_ms": self._seguro * 1000 // TAXA}
            if self._eco and self._hist_mic.size >= TAXA_MEDIDA:
                entrada, atraso = acoplamento(self._hist_ref, self._hist_mic)
                saida, _ = acoplamento(self._hist_ref, self._hist_saida)
                dados.update(eco_na_entrada=entrada, eco_atraso_ms=atraso,
                             eco_na_saida=saida)
        return dados

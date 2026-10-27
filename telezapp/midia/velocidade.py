# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Velocidade de reproducao do audio, sem mudar o tom da voz.

Duas partes:

* funcoes simples (`valores`, `ajustar`, `proxima`, `rotulo`) sobre a escala
  de velocidades: de 0,25 a 3,0, em passos de 0,25, 0,5 ou 1;
* `Esticador`: muda o tempo do som com WSOLA (sobreposicao e soma de trechos
  de 32 ms, escolhendo o ponto de corte mais parecido com o fim do trecho
  anterior). So numpy; custo baixo, serve para voz ate 3x.
"""
import numpy as np

MINIMA = 0.25
MAXIMA = 3.0
PADRAO = 1.0
PASSOS = (0.25, 0.5, 1.0)
PASSO_PADRAO = 0.25


def passo_valido(passo):
    try:
        passo = float(passo)
    except (TypeError, ValueError):
        return PASSO_PADRAO
    return passo if passo in PASSOS else PASSO_PADRAO


def valores(passo=PASSO_PADRAO):
    """Velocidades disponiveis: multiplos do passo, de MINIMA (se couber) ate
    MAXIMA. Com passo 0,25: 0,25 a 3; com 0,5: 0,5 a 3; com 1: 1 a 3."""
    passo = passo_valido(passo)
    n = int(round(MAXIMA / passo))
    return [round(passo * k, 2) for k in range(1, n + 1)
            if passo * k >= MINIMA - 1e-9]


def ajustar(velocidade, passo=PASSO_PADRAO):
    """O valor disponivel mais proximo (usado quando o passo muda)."""
    try:
        v = float(velocidade)
    except (TypeError, ValueError):
        v = PADRAO
    lista = valores(passo)
    return min(lista, key=lambda x: (abs(x - v), x))


def proxima(velocidade, passo, direcao):
    """Um degrau acima (direcao > 0) ou abaixo (< 0) do valor atual, mesmo
    que ele nao esteja na escala do passo; nos extremos, fica."""
    lista = valores(passo)
    try:
        v = float(velocidade)
    except (TypeError, ValueError):
        v = PADRAO
    if direcao > 0:
        acima = [x for x in lista if x > v + 1e-9]
        return acima[0] if acima else lista[-1]
    abaixo = [x for x in lista if x < v - 1e-9]
    return abaixo[-1] if abaixo else lista[0]


def rotulo(velocidade):
    """'1,5x', '0,25x', '2x': com virgula, como se fala em portugues."""
    texto = ("%g" % round(float(velocidade), 2)).replace(".", ",")
    return texto + "x"


class Esticador:
    """Le de `ler(n)` (n quadros seguidos do arquivo; vazio no fim) e entrega
    o som na velocidade pedida. `inicio` e o quadro do arquivo em que a
    leitura comeca; `posicao` e o quadro do arquivo que esta sendo tocado."""

    def __init__(self, taxa, canais, ler, total, inicio=0):
        self.taxa = taxa
        self.canais = canais
        self._ler = ler
        self.total = total
        self.hs = max(64, int(taxa * 0.016))     # passo de saida: 16 ms
        self.n = 2 * self.hs                     # trecho: 32 ms
        self.delta = self.hs // 2                # busca do melhor corte
        x = np.arange(self.n) / float(self.n)
        self._janela = (0.5 - 0.5 * np.cos(2 * np.pi * x)).astype(
            "float32").reshape(-1, 1)
        self.reiniciar(inicio)

    def reiniciar(self, inicio):
        """Recomeca no quadro `inicio` (o arquivo ja esta posicionado nele)."""
        self._x = np.zeros((0, self.canais), dtype="float32")
        self._x0 = int(inicio)
        self._fim_do_arquivo = False
        self._ideal = float(inicio)
        self._anterior = None
        self._cauda = np.zeros((self.hs, self.canais), dtype="float32")
        self._pronta = np.zeros((0, self.canais), dtype="float32")
        self._acabou = False

    @property
    def posicao(self):
        return min(self._ideal, float(self.total))

    @property
    def terminou(self):
        return self._acabou and len(self._pronta) == 0

    # ------------------------------------------------------------ entrada
    def _garantir(self, ate):
        while self._x0 + len(self._x) < ate and not self._fim_do_arquivo:
            falta = ate - (self._x0 + len(self._x))
            dados = self._ler(max(falta, self.n * 8))
            if dados is None or len(dados) == 0:
                self._fim_do_arquivo = True
                break
            self._x = np.concatenate([self._x, dados.astype("float32")])

    def _fatia(self, a, b):
        """Quadros [a, b) do arquivo, com zeros fora do que existe."""
        self._garantir(b)
        i, j = a - self._x0, b - self._x0
        pedaco = self._x[max(i, 0):max(j, 0)]
        if i < 0:
            pedaco = np.concatenate([
                np.zeros((min(-i, b - a), self.canais), dtype="float32"),
                pedaco])
        falta = (b - a) - len(pedaco)
        if falta > 0:
            pedaco = np.concatenate([
                pedaco, np.zeros((falta, self.canais), dtype="float32")])
        return pedaco

    def _descartar_antigos(self, velho):
        sobra = velho - self._x0 - self.n
        if sobra > self.n * 8:
            self._x = self._x[sobra:]
            self._x0 += sobra

    # -------------------------------------------------------------- saida
    def _gerar(self, velocidade):
        """Mais hs quadros de saida, ou None quando o arquivo acabou."""
        hs, n = self.hs, self.n
        if self._ideal >= self.total:
            self._acabou = True
            fim, self._cauda = self._cauda, np.zeros_like(self._cauda)
            return fim
        a = int(self._ideal)
        if self._anterior is None:
            corte = a
            self._garantir(corte + n)
            bruto = self._fatia(corte, corte + n)
            saida = bruto[:hs].copy()          # primeiro trecho: sem fade-in
            self._cauda = bruto[hs:] * self._janela[hs:]
        else:
            alvo = self._anterior + hs
            lo, hi = max(0, a - self.delta), a + self.delta
            ref = self._fatia(alvo, alvo + hs).mean(axis=1)
            reg = self._fatia(lo, hi + hs).mean(axis=1)
            corr = np.correlate(reg, ref, "valid")
            energia = np.concatenate([[0.0], np.cumsum(reg * reg)])
            tam = len(corr)
            janela_en = energia[hs:hs + tam] - energia[:tam]
            ponto = corr / np.sqrt(janela_en + 1e-6)
            corte = lo + int(np.argmax(ponto))
            quadro = self._fatia(corte, corte + n) * self._janela
            saida = self._cauda + quadro[:hs]
            self._cauda = quadro[hs:]
        self._anterior = corte
        self._ideal += hs * float(velocidade)
        self._descartar_antigos(min(corte, int(self._ideal) - self.delta))
        return saida

    def produzir(self, quantos, velocidade):
        """Ate `quantos` quadros na velocidade pedida; menos so no fim."""
        while len(self._pronta) < quantos and not self._acabou:
            pedaco = self._gerar(velocidade)
            if pedaco is not None and len(pedaco):
                self._pronta = np.concatenate([self._pronta, pedaco])
        dados, self._pronta = (self._pronta[:quantos],
                               self._pronta[quantos:])
        return dados

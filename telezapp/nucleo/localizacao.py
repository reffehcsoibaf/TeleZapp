# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Texto de uma localizacao recebida (WhatsApp e Telegram): o que a pessoa
escreveu, o nome e o endereco do lugar, as coordenadas e um link para abrir
no mapa. A mensagem so guarda texto, entao tudo vai nele. Aqui tambem fica o
acompanhamento da localizacao em tempo real do Telegram."""
import math
import time

TITULO_AO_VIVO = "localização em tempo real"
AVISO_PONTO_INICIAL = ("Este é o ponto de quando a localização foi enviada. "
                       "O movimento só aparece no celular.")
ACAO_VER = "ver_localizacao"
ROTULO_VER = "Ver localização em tempo real"
MOVIMENTO_MINIMO_M = 50     # menos que isso e so a imprecisao do GPS
RUMOS = ("norte", "nordeste", "leste", "sudeste", "sul", "sudoeste", "oeste",
         "noroeste")


def metros_entre(lat1, lon1, lat2, lon2):
    """Distancia em metros entre dois pontos (haversine)."""
    f1, f2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((f2 - f1) / 2) ** 2 + math.cos(f1) * math.cos(f2) * \
        math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(min(1.0, math.sqrt(a)))


def rumo_entre(lat1, lon1, lat2, lon2):
    """Para onde se vai do primeiro ponto ao segundo: 'norte', 'sudeste'..."""
    f1, f2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    graus = math.degrees(math.atan2(
        math.sin(dl) * math.cos(f2),
        math.cos(f1) * math.sin(f2) -
        math.sin(f1) * math.cos(f2) * math.cos(dl)))
    return RUMOS[int(round(graus / 45.0)) % 8]


def texto_distancia(metros):
    if metros < 1000:
        n = int(round(metros / 10.0)) * 10
        return "1 metro" if n == 1 else "%d metros" % n
    return ("%.1f quilômetros" % (metros / 1000.0)).replace(".", ",")


class Acompanhamento:
    """O que a janela mostra e fala de uma localizacao em tempo real. `acao`
    e o botao da mensagem: lat, lon, quando, ate (0 = sem prazo) e encerrada."""

    def __init__(self, quem, acao, relogio=time.time):
        self.quem = quem
        self.relogio = relogio
        self.acao = dict(acao)
        self.lat, self.lon = acao.get("lat"), acao.get("lon")
        self.falado = (self.lat, self.lon)
        self.ultimo_movimento = ""
        self.terminou = self._acabou()

    def _acabou(self):
        ate = self.acao.get("ate") or 0
        return bool(self.acao.get("encerrada") or (
            ate and self.relogio() >= ate))

    def atualizar(self, acao):
        """Guarda a posicao nova; devolve o que falar (pode ser nada)."""
        self.acao = dict(acao)
        if acao.get("lat") is not None:
            self.lat, self.lon = acao["lat"], acao["lon"]
        fim = self.conferir_fim()
        if fim:
            return fim
        if self.lat is None:
            return ""
        if self.falado[0] is None:
            self.falado = (self.lat, self.lon)
            return ""
        metros = metros_entre(self.falado[0], self.falado[1],
                              self.lat, self.lon)
        if metros < MOVIMENTO_MINIMO_M:
            return ""
        self.ultimo_movimento = "Andou %s para o %s." % (
            texto_distancia(metros), rumo_entre(
                self.falado[0], self.falado[1], self.lat, self.lon))
        self.falado = (self.lat, self.lon)
        return self.ultimo_movimento

    def conferir_fim(self):
        """O aviso de fim, uma vez so."""
        if self.terminou or not self._acabou():
            return ""
        self.terminou = True
        return "%s parou de compartilhar a localização." % self.quem

    def link(self):
        return link_do_mapa(self.lat, self.lon) if self.lat is not None else ""

    def texto(self):
        ate = self.acao.get("ate") or 0
        if self.terminou:
            linhas = ["Compartilhamento encerrado. Esta é a última posição "
                      "recebida."]
        elif ate:
            linhas = ["Compartilhando até %s." % time.strftime(
                "%H:%M", time.localtime(ate))]
        else:
            linhas = ["Compartilhando sem prazo para acabar."]
        if self.acao.get("quando"):
            linhas.append("Última atualização às %s." % time.strftime(
                "%H:%M:%S", time.localtime(self.acao["quando"])))
        if self.ultimo_movimento:
            linhas.append("Último movimento: " + self.ultimo_movimento)
        if self.lat is not None:
            linhas.append("Coordenadas %.5f, %.5f." % (self.lat, self.lon))
        else:
            linhas.append("Sem posição recebida.")
        return "\n".join(linhas)


def link_do_mapa(latitude, longitude):
    return "https://www.google.com/maps?q=%.6f,%.6f" % (latitude, longitude)


def descrever(latitude=0.0, longitude=0.0, nome="", endereco="",
              ao_vivo=False, legenda=""):
    """'localização: Nome, Endereço', a legenda, as coordenadas e o link.
    Em tempo real: 'localização em tempo real' e o aviso de que o ponto nao
    se move (e como chega no WhatsApp). Sem coordenadas (0, 0 e sem nome) so
    a palavra, como antes."""
    titulo = TITULO_AO_VIVO if ao_vivo else "localização"
    lugar = ", ".join(p.strip() for p in (nome, endereco) if p and p.strip())
    linhas = [titulo + (": " + lugar if lugar else "")]
    if legenda and legenda.strip():
        linhas.append(legenda.strip())
    if latitude or longitude:
        if ao_vivo:
            linhas.append(AVISO_PONTO_INICIAL)
        linhas.append("coordenadas %.5f, %.5f" % (latitude, longitude))
        linhas.append(link_do_mapa(latitude, longitude))
    return "\n".join(linhas)

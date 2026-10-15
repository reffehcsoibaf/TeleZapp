# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Logica da janela de configuracoes, sem wx (assim e testavel em qualquer
sistema): categorias, busca e valores ainda nao aplicados."""
from telezapp import config
from telezapp.midia import velocidade as vel

CATEGORIA_BUSCA = "Resultados da busca"


def categorias():
    """Categorias na ordem em que as opcoes aparecem em config.OPCOES."""
    vistas = []
    for o in config.OPCOES:
        if o.categoria not in vistas:
            vistas.append(o.categoria)
    # "Avancado" fica por ultimo: e o que quase ninguem precisa
    return sorted(vistas, key=lambda c: c == "Avançado")


class ModeloConfiguracoes:
    """Guarda o que a pessoa mudou na janela; nada vale ate aplicar()."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.pendentes = {}
        self.busca = ""

    # ------------------------------------------------------------ consulta
    def lista_de_categorias(self):
        """Com busca ativa, a primeira entrada mostra as opcoes achadas."""
        cats = categorias()
        if self.busca.strip():
            cats = [CATEGORIA_BUSCA] + cats
        return cats

    def opcoes(self, categoria):
        if categoria == CATEGORIA_BUSCA:
            return config.buscar_opcoes(self.busca)
        return [o for o in config.OPCOES if o.categoria == categoria]

    def valor(self, chave):
        if chave in self.pendentes:
            return self.pendentes[chave]
        return self.cfg.get(chave)

    # ------------------------------------------------------------- edicao
    def definir(self, chave, valor):
        """Marca o valor como pendente; voltar ao atual desfaz a mudanca.
        Trocar o passo leva a velocidade ao valor mais proximo permitido."""
        if valor == self.cfg.get(chave):
            self.pendentes.pop(chave, None)
        else:
            self.pendentes[chave] = valor
        if chave == "audio_passo_velocidade":
            atual = self.valor("audio_velocidade")
            self.definir("audio_velocidade",
                         vel.ajustar(atual, vel.passo_valido(valor)))

    def escolhas(self, opcao):
        """Escolhas da opcao; as velocidades dependem do passo pendente."""
        if opcao.chave == "audio_velocidade":
            passo = vel.passo_valido(self.valor("audio_passo_velocidade"))
            return tuple((v, vel.rotulo(v)) for v in vel.valores(passo))
        return opcao.escolhas

    def indice_da_escolha(self, opcao):
        """Posicao do valor atual entre as escolhas (0 se nao estiver)."""
        valores = [v for v, _ in self.escolhas(opcao)]
        try:
            return valores.index(self.valor(opcao.chave))
        except ValueError:
            return 0

    def mudancas(self):
        """Pendentes na ordem de config.OPCOES; o passo da velocidade vem
        antes da velocidade, que depende dele."""
        ordem = [o.chave for o in config.OPCOES]
        return [(c, self.pendentes[c]) for c in ordem if c in self.pendentes]

    def aplicar(self, aplicador):
        """Entrega cada mudanca ao aplicador(chave, valor) e zera."""
        feitas = self.mudancas()
        self.pendentes = {}
        for chave, valor in feitas:
            aplicador(chave, valor)
        return [c for c, _ in feitas]

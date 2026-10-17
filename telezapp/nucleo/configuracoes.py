# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Logica da janela de configuracoes, sem wx (assim e testavel em qualquer
sistema): categorias, busca e valores ainda nao aplicados."""
from telezapp import config
from telezapp.midia import velocidade as vel
from telezapp.nucleo import codigo_secreto as cs
from telezapp.nucleo import privacidade_conta as pw

CATEGORIA_BUSCA = "Resultados da busca"


def categorias():
    """Categorias na ordem em que as opcoes aparecem em config.OPCOES."""
    vistas = []
    for o in config.OPCOES:
        if o.categoria not in vistas:
            vistas.append(o.categoria)
    # "Avancado" quase ninguem precisa, e "Privacidade" (que consulta a
    # conta) fica na ultima posicao por enquanto
    fim = {"Avançado": 1, "Privacidade": 2}
    return sorted(vistas, key=lambda c: fim.get(c, 0))


class ModeloConfiguracoes:
    """Guarda o que a pessoa mudou na janela; nada vale ate aplicar()."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.pendentes = {}
        self.busca = ""
        # campos do codigo secreto das trancadas (nao sao uma opcao comum)
        self.codigo = {"atual": "", "novo": "", "repita": ""}
        # privacidade da conta do WhatsApp: conta -> valores lidos; conta ->
        # (campo -> posicao escolhida na caixa)
        self.priv_carregado = {}
        self.priv_escolhido = {}

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
        opcao = next((o for o in config.OPCOES if o.chave == chave), None)
        if opcao is not None and opcao.numero:
            valor = self.limitar(opcao, valor)
        if valor == self.cfg.get(chave):
            self.pendentes.pop(chave, None)
        else:
            self.pendentes[chave] = valor
        if chave == "audio_passo_velocidade":
            atual = self.valor("audio_velocidade")
            self.definir("audio_velocidade",
                         vel.ajustar(atual, vel.passo_valido(valor)))

    @staticmethod
    def limitar(opcao, valor):
        """Numero dentro de (minimo, maximo); lixo vira o padrao."""
        try:
            valor = int(valor)
        except (TypeError, ValueError):
            return opcao.padrao
        return max(opcao.numero[0], min(opcao.numero[1], valor))

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

    # ------------------------------------------ privacidade do WhatsApp
    def priv_definir(self, conta_id, campo, posicao):
        self.priv_escolhido.setdefault(conta_id, {})[campo] = posicao

    def priv_mudancas(self):
        """[(conta_id, campo, valor)] do que a pessoa mudou."""
        feitas = []
        for conta_id, escolhido in self.priv_escolhido.items():
            carregado = self.priv_carregado.get(conta_id)
            if carregado is None:
                continue
            feitas += [(conta_id, c, v)
                       for c, v in pw.mudancas(carregado, escolhido)]
        return feitas

    # ------------------------------------------------- codigo secreto
    def definir_codigo(self, campo, valor):
        self.codigo[campo] = valor

    def erro_codigo(self):
        """Por que o codigo secreto (e a exigencia dele) nao pode ser
        aplicado agora; vazio se esta tudo certo. Mudar o codigo ou desligar
        a exigencia pede o codigo atual; nao ha como redefinir sem ele."""
        guardado = self.cfg.get("codigo_trancadas")
        exigir = bool(self.valor("trancadas_exigir_codigo"))
        c = self.codigo
        mexeu = bool(c["novo"] or c["repita"])
        if guardado:
            if not (mexeu or not exigir):
                return ""
            if not cs.confere(c["atual"], guardado):
                return ("Digite o código atual para mudar o código ou "
                        "desligar a exigência.")
            if not exigir:
                return ""
        else:
            if not exigir:
                return ""
            if not (mexeu or "trancadas_exigir_codigo" in self.pendentes):
                return ""
        if c["novo"] != c["repita"]:
            return "Os dois códigos novos não são iguais."
        if not cs.valido(c["novo"]):
            return "O código novo deve ter de 4 a 12 números."
        return ""

    def acao_codigo(self):
        """None, ("definir", novo) ou ("remover", None), conforme o que a
        pessoa preencheu. So vale se erro_codigo() for vazio."""
        guardado = self.cfg.get("codigo_trancadas")
        exigir = bool(self.valor("trancadas_exigir_codigo"))
        if not exigir:
            return ("remover", None) if guardado else None
        if self.codigo["novo"]:
            return ("definir", self.codigo["novo"])
        return None

    def mudancas(self):
        """Pendentes na ordem de config.OPCOES; o passo da velocidade vem
        antes da velocidade, que depende dele."""
        ordem = [o.chave for o in config.OPCOES]
        return [(c, self.pendentes[c]) for c in ordem if c in self.pendentes]

    def aplicar(self, aplicador):
        """Entrega cada mudanca ao aplicador(chave, valor) e zera."""
        feitas = self.mudancas()
        acao = self.acao_codigo() if not self.erro_codigo() else None
        priv = self.priv_mudancas()
        self.priv_escolhido = {}
        self.pendentes = {}
        self.codigo = {"atual": "", "novo": "", "repita": ""}
        for chave, valor in feitas:
            aplicador(chave, valor)
        if acao is not None:
            aplicador("codigo_trancadas", acao[1])
            feitas.append(("codigo_trancadas", acao[1]))
        if priv:
            aplicador("privacidade_conta", priv)
            feitas.append(("privacidade_conta", priv))
        return [c for c, _ in feitas]

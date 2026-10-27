# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Logica da janela de configuracoes, sem wx (assim e testavel em qualquer
sistema): categorias, busca e valores ainda nao aplicados."""
from telezapp import config
from telezapp.midia import velocidade as vel
from telezapp.nucleo import codigo_secreto as cs
from telezapp.nucleo import lista_conversas as lc
from telezapp.nucleo.pacotes_de_som import EstadoDeSons
from telezapp.nucleo import privacidade_conta as pw

CATEGORIA_BUSCA = "Resultados da busca"


def categorias():
    """Categorias na ordem em que as opcoes aparecem em config.OPCOES."""
    vistas = []
    for o in config.OPCOES:
        if o.categoria not in vistas:
            vistas.append(o.categoria)
    if "Sons" not in vistas:
        vistas.append("Sons")       # tela propria: pacotes e eventos
    if "Atalhos" not in vistas:
        vistas.append("Atalhos")    # tela propria: funcoes e teclas
    # no fim da lista, nesta ordem: "Privacidade" (que consulta a conta),
    # "Avancado" (quase ninguem precisa) e "Atualizacoes"
    fim = {"Sistema": 1, "Privacidade": 2, "Avançado": 3,
           "Atualizações": 4}
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
        # chaves e modelos dos provedores de IA ainda nao aplicados:
        # {provedor: texto}; chave vazia = apagar a chave guardada
        self.ia_chaves = {}
        self.ia_modelos = {}
        self.ia_ordens = {}       # tarefa -> provedores ligados, em ordem
        self.sons = EstadoDeSons(cfg)    # pacote, eventos e arquivos de som
        self.registro = None      # nucleo.atalhos.Registro, dado pela janela
        self.atalhos_pendentes = None    # personalizados ainda nao aplicados
        self.lista_pendente = None       # lista de conversas ainda nao aplicada

    # ------------------------------------------------------------ consulta
    def lista_de_categorias(self):
        """Com busca ativa, a primeira entrada mostra as opcoes achadas."""
        cats = categorias()
        if self.busca.strip():
            cats = [CATEGORIA_BUSCA] + cats
        return cats

    def opcoes(self, categoria):
        """Opcoes mostradas direto na categoria; as de um grupo ficam atras
        do botao dele (ver `grupos`). A busca mostra todas, achadas onde
        estiverem."""
        if categoria == CATEGORIA_BUSCA:
            return config.buscar_opcoes(self.busca)
        return [o for o in config.OPCOES
                if o.categoria == categoria and not o.grupo]

    def grupos(self, categoria):
        """Nomes dos botoes da categoria, cada um com um grupo de opcoes."""
        vistos = []
        for o in config.OPCOES:
            if o.categoria == categoria and o.grupo and \
                    o.grupo not in vistos:
                vistos.append(o.grupo)
        return vistos

    def opcoes_do_grupo(self, categoria, grupo):
        return [o for o in config.OPCOES
                if o.categoria == categoria and o.grupo == grupo]

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

    def ia_definir_chave(self, provedor, chave):
        """Chave digitada; campo vazio = nao mexer na que esta guardada."""
        if chave.strip():
            self.ia_chaves[provedor] = chave.strip()
        else:
            self.ia_chaves.pop(provedor, None)

    def ia_apagar_chave(self, provedor):
        self.ia_chaves[provedor] = ""

    def ia_definir_modelo(self, provedor, modelo):
        atual = (self.cfg.get("ia_modelos") or {}).get(provedor, "")
        if modelo.strip() == atual:
            self.ia_modelos.pop(provedor, None)
        else:
            self.ia_modelos[provedor] = modelo.strip()

    def ia_ordem(self, tarefa):
        """Provedores ligados para a tarefa, na ordem de tentativa."""
        if tarefa in self.ia_ordens:
            return list(self.ia_ordens[tarefa])
        return list((self.cfg.get("ia_ordem") or {}).get(tarefa, []))

    def ia_definir_ordem(self, tarefa, ligados):
        if list(ligados) == list((self.cfg.get("ia_ordem") or {}).get(
                tarefa, [])):
            self.ia_ordens.pop(tarefa, None)
        else:
            self.ia_ordens[tarefa] = list(ligados)

    def ia_mudancas(self):
        """{'chaves', 'modelos', 'ordem'} do que mudou, ou None."""
        if not self.ia_chaves and not self.ia_modelos and not self.ia_ordens:
            return None
        return {"chaves": dict(self.ia_chaves),
                "modelos": dict(self.ia_modelos),
                "ordem": {t: list(v) for t, v in self.ia_ordens.items()}}

    # ----------------------------------------------------------- atalhos
    def atalhos_em_uso(self):
        """Os personalizados com o que ainda nao foi aplicado."""
        if self.atalhos_pendentes is not None:
            return self.atalhos_pendentes
        return self.registro.personalizados

    def atalhos_lista(self, busca=""):
        """[(Acao, combinacao)] das funcoes que casam com a busca."""
        pers = self.atalhos_em_uso()
        if busca.strip():
            return self.registro.buscar(busca, pers)
        return self.registro.todos(pers)

    def atalho_de(self, chave):
        return self.registro.efetivo(chave, self.atalhos_em_uso())

    def atalho_dono(self, canon, ignorar):
        """A Acao que ja usa a combinacao (fora `ignorar`), ou None."""
        return self.registro.dono(canon, ignorar, self.atalhos_em_uso())

    def atalho_definir(self, chave, canon, substituir=False):
        """Poe `canon` (""= sem atalho) na funcao. Se outra funcao ja usa a
        combinacao e `substituir` for falso, nada muda e devolve essa Acao;
        com `substituir`, a outra fica sem atalho. Devolve None quando deu
        certo."""
        pers = self.atalhos_em_uso()
        outro = self.atalho_dono(canon, chave)
        if outro is not None and not substituir:
            return outro
        if outro is not None:
            novos = self.registro.trocando(chave, canon, pers)
        else:
            novos = self.registro.com_atalho(chave, canon, pers)
        self._atalhos_guardar(novos)
        return None

    def atalho_restaurar(self, chave):
        """Volta ao padrao. Se outra funcao usa o padrao, devolve essa Acao e
        nada muda."""
        padrao = self.registro.acoes[chave].padrao
        return self.atalho_definir(chave, padrao)

    def atalhos_restaurar_todos(self):
        self._atalhos_guardar({})

    def _atalhos_guardar(self, novos):
        if novos == self.registro.personalizados:
            self.atalhos_pendentes = None
        else:
            self.atalhos_pendentes = dict(novos)

    # ------------------------------------------------ lista de conversas
    def lista_em_uso(self):
        """O que a lista de conversas mostra, com o que ainda nao foi
        aplicado."""
        if self.lista_pendente is not None:
            return self.lista_pendente
        return lc.normalizar(self.cfg.get("lista_conversas"))

    def lista_definir(self, valor):
        valor = lc.normalizar(valor)
        if valor == lc.normalizar(self.cfg.get("lista_conversas")):
            self.lista_pendente = None
        else:
            self.lista_pendente = valor

    def aplicar(self, aplicador):
        """Entrega cada mudanca ao aplicador(chave, valor) e zera."""
        feitas = self.mudancas()
        atalhos = self.atalhos_pendentes
        self.atalhos_pendentes = None
        lista = self.lista_pendente
        self.lista_pendente = None
        ia = self.ia_mudancas()
        self.ia_chaves, self.ia_modelos, self.ia_ordens = {}, {}, {}
        acao = self.acao_codigo() if not self.erro_codigo() else None
        priv = self.priv_mudancas()
        sons = self.sons.aplicar() if self.sons.mudou() else None
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
        if ia:
            aplicador("ia_credenciais", ia)
            feitas.append(("ia_credenciais", ia))
        if sons is not None:
            aplicador("sons_pacotes", sons)
            feitas.append(("sons_pacotes", sons))
        if lista is not None:
            aplicador("lista_conversas", lista)
            feitas.append(("lista_conversas", lista))
        if atalhos is not None:
            aplicador("atalhos", atalhos)
            feitas.append(("atalhos", atalhos))
            self.registro.definir_personalizados(atalhos)
        return [c for c, _ in feitas]

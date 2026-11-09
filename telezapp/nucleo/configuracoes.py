# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Logica da janela de configuracoes, sem wx (assim e testavel em qualquer
sistema): categorias, busca e valores ainda nao aplicados."""
from dataclasses import dataclass

from telezapp import config
from telezapp.midia import velocidade as vel
from telezapp.nucleo import atalhos as nucleo_atalhos
from telezapp.nucleo import codigo_secreto as cs
from telezapp.nucleo import lista_conversas as lc
from telezapp.nucleo import lista_mensagens as lm
from telezapp.nucleo import pacotes_de_som
from telezapp.nucleo.ia import catalogo
from telezapp.nucleo.pacotes_de_som import EstadoDeSons
from telezapp.nucleo import privacidade_conta as pw

CATEGORIA_BUSCA = "Resultados da busca"
# acima disto, a busca mostra um botao so para as funcoes achadas em Atalhos
LIMITE_ATALHOS_NA_BUSCA = 20


@dataclass
class Destino:
    """O que a busca acha fora de config.OPCOES: uma linha de janela propria
    ou de tela propria. A janela mostra um botao que leva a ela."""
    rotulo: str
    tipo: str        # lista_conversas, lista_mensagens, sons, atalhos, ...
    alvo: str = ""   # o item dentro do lugar
    descricao: str = ""
    termos: str = ""  # outras palavras que acham este destino


def _aviso():
    from telezapp.nucleo import aviso_de_nova
    return aviso_de_nova


def _destinos_da_lista(tipo, titulo, nucleo):
    ajuda = "Abre a janela %s neste item." % titulo
    itens = [Destino("%s: %s" % (titulo, r), tipo, c, ajuda)
             for c, r in nucleo.ITENS]
    if hasattr(nucleo, "ESCOLHAS_DIGITAR"):
        itens.append(Destino(
            "%s: ao digitar uma letra nesta lista" % titulo, tipo, "digitar",
            ajuda, " ".join(r for _, r in nucleo.ESCOLHAS_DIGITAR) +
            " caractere tecla"))
    if hasattr(nucleo, "ROTULO_SO_QUANDO_MUDA"):
        itens.append(Destino("%s: %s" % (titulo, nucleo.ROTULO_SO_QUANDO_MUDA),
                             tipo, "so_muda", ajuda))
    itens += [
        Destino("%s: mudar a ordem das informações" % titulo, tipo, "cima",
                ajuda, "mover para cima baixo"),
        Destino("%s: restaurar o padrão" % titulo, tipo, "padrao", ajuda)]
    return itens


def _destinos_da_privacidade():
    ajuda = "Leva à categoria Privacidade, neste campo da conta."
    itens = []
    for campo in pw.CAMPOS:
        itens.append(Destino(
            "Privacidade da conta: " + campo.rotulo, "privacidade", campo.nome,
            ajuda, " ".join((pw.ROTULOS_TELEGRAM.get(campo.nome, ""),
                             *[r for _, r in campo.opcoes],
                             "whatsapp telegram"))))
    itens.append(Destino("Privacidade da conta: Quem pode ver meu status",
                         "privacidade", "status", ajuda, "whatsapp"))
    return itens


def _destinos_da_ia():
    itens = []
    for tarefa in catalogo.TAREFAS:
        nomes = [n for _, n in catalogo.provedores_da_tarefa(tarefa)]
        itens.append(Destino(
            "Inteligência artificial: " + catalogo.NOMES_DE_TAREFA[tarefa],
            "ia", tarefa,
            "Leva à lista de provedores desta tarefa.",
            " ".join(nomes) + " provedores ordem tarefa ia"))
    for prov in catalogo.PROVEDORES.values():
        itens.append(Destino(
            "Inteligência artificial: configurar " + prov.nome,
            "provedor_ia", prov.chave,
            "Abre a janela deste provedor.",
            "chave modelo testar obter modelos apagar privacidade provedor "
            "ia"))
    return itens


def _destinos_dos_sons(estado):
    ajuda = "Leva à categoria Sons."
    nomes = " ".join(n for _, n in estado.pacotes())
    itens = [Destino("Sons: pacote de sons", "sons", "", ajuda,
                     nomes + " novo personalizado excluir")]
    for chave, rotulo in pacotes_de_som.eventos():
        itens.append(Destino(
            "Sons: " + rotulo, "sons", chave,
            pacotes_de_som.descricao_do_evento(chave) or ajuda,
            "evento som ouvir procurar ativar desativar"))
    return itens


def _destinos_do_codigo():
    ajuda = "Leva à opção do código secreto, em Privacidade."
    return [Destino("Privacidade: " + r, "codigo", "", ajuda,
                    "trancadas secreto")
            for r in ("Código atual", "Novo código", "Repita o novo código")]


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
        self.lista_msg_pendente = None   # lista de mensagens, idem
        self.aviso_pendente = None       # aviso de mensagem nova, idem

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
            return [o for o in config.buscar_opcoes(self.busca)
                    if self._ha_conta_para(o)]
        return [o for o in config.OPCOES
                if o.categoria == categoria and not o.grupo
                and self._ha_conta_para(o)]

    def _ha_conta_para(self, opcao):
        """Opcao de um servico so aparece com uma conta dele cadastrada e
        ativada (Gerenciar contas)."""
        if not opcao.servico:
            return True
        servicos = set(opcao.servico.split(","))   # "a,b": qualquer um
        return any(d.get("servico") in servicos
                   and d.get("ativa", True) is not False   # desativada: nao
                   for d in self.cfg.contas())

    def destinos_da_busca(self):
        """O que a busca acha fora de config.OPCOES (ver `Destino`). As funcoes
        de Atalhos sao muitas: passando do limite, viram um botao so."""
        palavras = config._sem_acento(self.busca).split()
        if not palavras:
            return []

        def casa(*textos):
            alvo = config._sem_acento(" ".join(textos))
            return all(p in alvo for p in palavras)
        achados = [d for d in (
            _destinos_da_lista("lista_conversas", "Lista de conversas", lc) +
            _destinos_da_lista("lista_mensagens", "Lista de mensagens", lm) +
            _destinos_da_lista("aviso_nova", "Aviso de mensagem nova",
                               _aviso()) +
            _destinos_dos_sons(self.sons) + _destinos_da_privacidade() +
            _destinos_do_codigo() + _destinos_da_ia())
            if casa(d.rotulo, d.descricao, d.termos)]
        return achados + self._destinos_dos_atalhos(casa)

    def _destinos_dos_atalhos(self, casa):
        if self.registro is None:
            return []
        achadas = []
        for a, canon in self.atalhos_lista():
            tecla = nucleo_atalhos.exibir(canon)
            if casa(a.rotulo, a.categoria, canon, canon.replace("+", " "),
                    tecla, "atalho atalhos tecla"):
                achadas.append((a, tecla))
        if len(achadas) > LIMITE_ATALHOS_NA_BUSCA:
            texto = " ".join(p for p in self.busca.split()
                             if not config._sem_acento(p).startswith("atalho"))
            return [Destino(
                "Atalhos: ver as %d funções achadas" % len(achadas),
                "atalhos_busca", texto,
                "Leva à categoria Atalhos, com a busca já preenchida.")]
        return [Destino("Atalhos: %s, %s: %s" % (
            a.rotulo, a.categoria, tecla or "sem atalho"), "atalhos", a.chave,
            "Leva à categoria Atalhos, nesta função.")
            for a, tecla in achadas]

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

    # Fora da redefinicao: o que protege o acesso (autenticacao ao abrir e
    # codigo das trancadas), para ninguem desligar a protecao sem a senha.
    CATEGORIAS_FORA_DA_REDEFINICAO = ("Privacidade",)

    def redefinir_padroes(self):
        """Marca, como pendente, todas as opcoes no padrao de fabrica: as
        opcoes comuns, as tres listas, os atalhos e o pacote de sons (volta
        ao da casa, com todos os eventos ativados). Nao mexe em contas,
        chaves de IA, privacidade nem nos pacotes de sons criados pela
        pessoa. Vale ao aplicar; cancelar desfaz."""
        for o in config.OPCOES:
            if o.categoria not in self.CATEGORIAS_FORA_DA_REDEFINICAO:
                self.definir(o.chave, o.padrao)
        self.lista_definir(None)
        self.lista_msg_definir(None)
        self.aviso_definir(None)
        if self.registro is not None:
            self.atalhos_restaurar_todos()
        self.sons.redefinir()

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

    def lista_msg_em_uso(self):
        """O que a lista de mensagens mostra, com o que ainda nao foi
        aplicado."""
        if self.lista_msg_pendente is not None:
            return self.lista_msg_pendente
        return lm.normalizar(self.cfg.get("lista_mensagens"))

    def lista_msg_definir(self, valor):
        valor = lm.normalizar(valor)
        if valor == lm.normalizar(self.cfg.get("lista_mensagens")):
            self.lista_msg_pendente = None
        else:
            self.lista_msg_pendente = valor

    def aviso_em_uso(self):
        """O que o aviso de mensagem nova diz, com o que ainda nao foi
        aplicado."""
        from telezapp.nucleo import aviso_de_nova as an
        if self.aviso_pendente is not None:
            return self.aviso_pendente
        return an.normalizar(self.cfg.get("aviso_nova"))

    def aviso_definir(self, valor):
        from telezapp.nucleo import aviso_de_nova as an
        valor = an.normalizar(valor)
        if valor == an.normalizar(self.cfg.get("aviso_nova")):
            self.aviso_pendente = None
        else:
            self.aviso_pendente = valor

    def aplicar(self, aplicador):
        """Entrega cada mudanca ao aplicador(chave, valor) e zera."""
        feitas = self.mudancas()
        aviso = self.aviso_pendente
        self.aviso_pendente = None
        atalhos = self.atalhos_pendentes
        self.atalhos_pendentes = None
        lista = self.lista_pendente
        self.lista_pendente = None
        lista_msg = self.lista_msg_pendente
        self.lista_msg_pendente = None
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
        if lista_msg is not None:
            aplicador("lista_mensagens", lista_msg)
            feitas.append(("lista_mensagens", lista_msg))
        if aviso is not None:
            aplicador("aviso_nova", aviso)
            feitas.append(("aviso_nova", aviso))
        if atalhos is not None:
            aplicador("atalhos", atalhos)
            feitas.append(("atalhos", atalhos))
            self.registro.definir_personalizados(atalhos)
        return [c for c, _ in feitas]

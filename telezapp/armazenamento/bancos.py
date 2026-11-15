# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""O gerente dos bancos: um banco SQLite por conta, cada um na pasta da
conta (ver config.pasta_da_conta). Sem separacao (opcao "contas_em_pastas"
desmarcada), todas as contas dividem o banco unico de sempre, na pasta
do layout antigo (a personalizada, se escolhida; senao, <dados>\\telezapp.db).

Para o resto do programa e como se fosse o Banco de sempre: os metodos que
levam conta_id despacham para o banco da conta, e os que nao (buscas e
listas de todas as contas) juntam o resultado de todos. A classe Banco em
si nao mudou: ela continua sendo um banco de uma conta so.
"""
import os
import sqlite3
import threading

from telezapp import config
from telezapp.armazenamento.banco import Banco, _numero

NOME_ARQUIVO = "conversas.db"


class Bancos:
    """A mesma interface do Banco, repartida por conta."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.depuracao = False      # modo de depuracao (guardado e repassado)
        self._bancos = {}           # conta_id -> Banco aberto
        self._trava = threading.Lock()

    # ------------------------------------------------------------ controle
    def _de(self, conta_id):
        """O banco da conta, abrindo na hora se precisar. Sem separacao,
        o banco e unico e serve a todas as contas."""
        with self._trava:
            chave = None if not config.contas_separadas() else conta_id
            b = self._bancos.get(chave)
            if b is None:
                if chave is None:
                    pasta = config.pasta_do_layout_antigo()
                    arquivo = os.path.join(pasta, "telezapp.db")
                else:
                    pasta = config.pasta_da_conta(conta_id)
                    arquivo = os.path.join(pasta, NOME_ARQUIVO)
                try:
                    os.makedirs(pasta, exist_ok=True)
                except OSError as erro:
                    raise RuntimeError(
                        "Não consegui abrir a pasta da conta %s: %s"
                        % (conta_id, erro)) from erro
                b = Banco(arquivo)
                b.depuracao = self.depuracao
                self._bancos[chave] = b
            return b

    def _todas(self):
        """[(conta_id, banco)] para o que nao filtra por conta (listas de
        todas as contas). Sem separacao, uma passada so no banco unico."""
        if not config.contas_separadas():
            return [(None, self._de(None))]
        return [(i, self._de(i)) for i in self._conhecidas()]

    def _conhecidas(self):
        """As contas conhecidas: as da configuracao e as com banco aberto."""
        with self._trava:
            ids = {c["id"] for c in self.cfg.contas() if c.get("id")}
            ids.update(self._bancos)
        return sorted(ids)

    def fechar(self, conta_id=None):
        """Fecha o banco da conta (ou de todos), para levar os dados para
        outro lugar ou encerrar. O banco volta a abrir sozinho se for
        usado de novo. Sem separacao o banco e unico: fechar o de uma
        conta o fecha para todas."""
        with self._trava:
            if conta_id is not None and not config.contas_separadas():
                conta_id = None
            ids = list(self._bancos) if conta_id is None else (
                [conta_id] if conta_id in self._bancos else [])
            bancos = [(i, self._bancos.pop(i)) for i in ids]
        for _, b in bancos:
            b.fechar()

    def apagar_conta(self, conta_id):
        """A conta foi removida: apaga o que e dela. Sem separacao, so as
        linhas dela saem do banco unico (que fica, com as das outras). Com
        separacao, fecha e apaga os arquivos (a pasta de sobras e limpada
        por Contas.remover)."""
        if not config.contas_separadas():
            self._de(conta_id).apagar_conta(conta_id)
            return
        self.fechar(conta_id)
        pasta = config.pasta_da_conta(conta_id)
        for sufixo in ("", "-wal", "-shm", "-journal"):
            try:
                os.remove(os.path.join(pasta, NOME_ARQUIVO + sufixo))
            except OSError:
                pass

    def copiar_para(self, caminho, conta_id=None):
        """Copia consistente do banco de UMA conta (para o backup). Sem
        conta, nao ha um banco so para copiar."""
        if conta_id is None:
            raise ValueError("Diga de qual conta copiar (os bancos agora "
                             "sao um por conta).")
        self._de(conta_id).copiar_para(caminho)

    # ------------------------------------------------------------ depuracao
    def guardar_depuracao(self, conta_id, conversa_id, mensagem_id, dados):
        self._de(conta_id).guardar_depuracao(conta_id, conversa_id,
                                             mensagem_id, dados)

    def depuracao_de(self, conta_id, conversa_id, mensagem_id):
        return self._de(conta_id).depuracao_de(conta_id, conversa_id,
                                               mensagem_id)

    def limpar_depuracao(self):
        for _, b in self._todas():
            b.limpar_depuracao()

    # ------------------------------------------------------------ conversas
    def _em_grupos(self, itens, chave):
        """Itens repartidos por conta (a chave e o campo que diz a conta)."""
        grupos = {}
        for item in itens:
            grupos.setdefault(chave(item), []).append(item)
        return grupos

    def salvar_conversas(self, conversas):
        for conta_id, do_grupo in self._em_grupos(
                conversas, lambda c: c.conta_id).items():
            self._de(conta_id).salvar_conversas(do_grupo)

    def conversas(self, conta_id):
        return self._de(conta_id).conversas(conta_id)

    def atualizar_conversa(self, conta_id, conversa_id, **valores):
        self._de(conta_id).atualizar_conversa(conta_id, conversa_id,
                                              **valores)

    def apagar_conversa(self, conta_id, conversa_id, data):
        return self._de(conta_id).apagar_conversa(conta_id, conversa_id, data)

    # ------------------------------------------------------------- contatos
    def contatos(self, conta_id=None):
        """[(conta_id, id, nome, telefone)], por nome; de todas as contas
        quando `conta_id` nao vem."""
        if conta_id is not None:
            return self._de(conta_id).contatos(conta_id)
        saida = []
        for i in self._conhecidas():
            saida.extend(self._de(i).contatos(i))
        return sorted(saida, key=lambda c: (c[2].lower(), c[2]))

    def salvar_contato(self, conta_id, id_, nome, telefone=""):
        self._de(conta_id).salvar_contato(conta_id, id_, nome, telefone)

    def remover_contato(self, conta_id, id_):
        self._de(conta_id).remover_contato(conta_id, id_)

    def nome_de_contato(self, conta_id, *ids):
        return self._de(conta_id).nome_de_contato(conta_id, *ids)

    # ------------------------------------------------------------ mensagens
    def salvar_mensagens(self, mensagens):
        for conta_id, do_grupo in self._em_grupos(
                mensagens, lambda x: x.conta_id).items():
            self._de(conta_id).salvar_mensagens(do_grupo)

    def data_antes_de(self, conta_id, conversa_id, data):
        return self._de(conta_id).data_antes_de(conta_id, conversa_id, data)

    def data_mais_antiga(self, conta_id, conversa_id):
        return self._de(conta_id).data_mais_antiga(conta_id, conversa_id)

    def mensagem_mais_antiga(self, conta_id, conversa_id):
        return self._de(conta_id).mensagem_mais_antiga(conta_id, conversa_id)

    def mensagens_expiradas(self, agora=None):
        saida = []
        for _, b in self._todas():
            saida.extend(b.mensagens_expiradas(agora))
        return saida

    def mensagens(self, conta_id, conversa_id, limite=100):
        return self._de(conta_id).mensagens(conta_id, conversa_id, limite)

    def mensagens_que_citam(self, conta_id, conversa_id, meus=()):
        return self._de(conta_id).mensagens_que_citam(conta_id, conversa_id,
                                                      meus)

    def contar_desde(self, conta_id, conversa_id, data):
        return self._de(conta_id).contar_desde(conta_id, conversa_id, data)

    def ultimas_mensagens(self):
        saida = {}
        for _, b in self._todas():
            saida.update(b.ultimas_mensagens())
        return saida

    def mensagens_por_id(self, conta_id, ids, conversa_id=None):
        return self._de(conta_id).mensagens_por_id(conta_id, ids,
                                                   conversa_id)

    def renomear_autor(self, conta_id, remetentes, nome):
        return self._de(conta_id).renomear_autor(conta_id, remetentes, nome)

    def renomear_autor_da_conversa(self, conta_id, conversa_id, nome):
        return self._de(conta_id).renomear_autor_da_conversa(
            conta_id, conversa_id, nome)

    def nome_do_remetente(self, conta_id, remetentes):
        return self._de(conta_id).nome_do_remetente(conta_id, remetentes)

    def contar_mensagens(self, tipo):
        return sum(b.contar_mensagens(tipo) for _, b in self._todas())

    def mensagem(self, conta_id, conversa_id, mensagem_id):
        return self._de(conta_id).mensagem(conta_id, conversa_id,
                                           mensagem_id)

    def mensagem_da_enquete(self, conta_id, poll_id):
        return self._de(conta_id).mensagem_da_enquete(conta_id, poll_id)

    def mudar_estado(self, conta_id, conversa_id, ids, estado):
        return self._de(conta_id).mudar_estado(conta_id, conversa_id, ids,
                                               estado)

    def marcar_lidas_pelo_outro(self, conta_id, conversa_id, ate_id, estado):
        self._de(conta_id).marcar_lidas_pelo_outro(conta_id, conversa_id,
                                                   ate_id, estado)

    # -------------------------------------------------------------- recibos
    def salvar_recibos(self, conta_id, conversa_id, mensagem_ids,
                       participante, tipo, data):
        self._de(conta_id).salvar_recibos(conta_id, conversa_id,
                                          mensagem_ids, participante, tipo,
                                          data)

    def recibos(self, conta_id, conversa_id, mensagem_id):
        return self._de(conta_id).recibos(conta_id, conversa_id,
                                          mensagem_id)

    # --------------------------------------------------------------- status
    def salvar_status(self, conta_id, s):
        self._de(conta_id).salvar_status(conta_id, s)

    def status(self, conta_id, limite=200):
        return self._de(conta_id).status(conta_id, limite)

    # --------------------------------------------------------------- midias
    def registrar_midia(self, conta_id, conversa_id, mensagem_id, tipo,
                        caminho, tamanho, data):
        self._de(conta_id).registrar_midia(conta_id, conversa_id,
                                           mensagem_id, tipo, caminho,
                                           tamanho, data)

    def midias(self, conta_id, conversa_id=None):
        return self._de(conta_id).midias(conta_id, conversa_id)

    def todas_midias(self):
        saida = []
        for _, b in self._todas():
            saida.extend(b.todas_midias())
        return sorted(saida, key=lambda linha: linha[-1])

    def midia(self, conta_id, conversa_id, mensagem_id):
        return self._de(conta_id).midia(conta_id, conversa_id, mensagem_id)

    def esquecer_midia(self, conta_id, conversa_id, mensagem_id):
        self._de(conta_id).esquecer_midia(conta_id, conversa_id,
                                          mensagem_id)

    def salvar_fichas(self, fichas):
        for conta_id, do_grupo in self._em_grupos(
                fichas, lambda f: f[0]).items():
            self._de(conta_id).salvar_fichas(do_grupo)

    def ficha(self, conta_id, conversa_id, mensagem_id):
        return self._de(conta_id).ficha(conta_id, conversa_id, mensagem_id)

    def salvar_posicao(self, conta_id, conversa_id, mensagem_id):
        self._de(conta_id).salvar_posicao(conta_id, conversa_id,
                                          mensagem_id)

    def posicao(self, conta_id, conversa_id):
        return self._de(conta_id).posicao(conta_id, conversa_id)

    # --------------------------------------------------------------- limpeza
    def foi_limpa(self, conta_id, conversa_id, mensagem_id):
        return self._de(conta_id).foi_limpa(conta_id, conversa_id,
                                            mensagem_id)

    def mensagens_fixadas(self, conta_id, conversa_id):
        return self._de(conta_id).mensagens_fixadas(conta_id, conversa_id)

    def favoritas(self):
        favoritas = set()
        for _, b in self._todas():
            favoritas.update(b.favoritas())
        return favoritas

    def buscar_mensagens(self, contas=(), servicos=(), tipos_de_conversa=(),
                         situacoes=(), minha=None,
                         data_de=None, data_ate=None, segundos_min=None,
                         segundos_max=None, tamanho_min=None,
                         tamanho_max=None, estados=(),
                         mais_antigas_primeiro=False, agora=None,
                         incluir_trancadas=False, limite_de_linhas=200000):
        """A mesma busca, conta por conta, com o resultado junto na ordem
        certa (a ordem SQL de cada banco)."""
        chaves = set(self._conhecidas()) & (
            {str(c) for c in contas} if contas else set(self._conhecidas()))
        achadas = []
        for conta_id in sorted(chaves):
            achadas.extend(self._de(conta_id).buscar_mensagens(
                (conta_id,) if contas else (), servicos, tipos_de_conversa,
                situacoes, minha, data_de, data_ate, segundos_min,
                segundos_max, tamanho_min, tamanho_max, estados,
                mais_antigas_primeiro, agora, incluir_trancadas,
                limite_de_linhas))
        sinal_ordenada = not mais_antigas_primeiro
        achadas.sort(key=lambda par: (par[0].data, _numero(par[0].id)),
                     reverse=sinal_ordenada)
        return achadas[:int(limite_de_linhas)]

    def conversas_com_favoritas(self):
        saida = set()
        for _, b in self._todas():
            saida.update(b.conversas_com_favoritas())
        return saida

    def mensagens_para_limpar(self, conta_id="", conversa_id="", tipos=(),
                              antes=None, minimo=0):
        if conta_id:
            return self._de(conta_id).mensagens_para_limpar(
                conta_id, conversa_id, tipos, antes, minimo)
        saida = []
        for i in self._conhecidas():
            saida.extend(self._de(i).mensagens_para_limpar(
                i, conversa_id, tipos, antes, minimo))
        return saida

    def registrar_limpeza(self, chaves, alvo):
        for conta_id, do_grupo in self._em_grupos(chaves,
                                                  lambda k: k[0]).items():
            self._de(conta_id).registrar_limpeza(do_grupo, alvo)

    def apagar_mensagens(self, chaves):
        for conta_id, do_grupo in self._em_grupos(chaves,
                                                  lambda k: k[0]).items():
            self._de(conta_id).apagar_mensagens(do_grupo)

    def apagar_fichas(self, chaves):
        for conta_id, do_grupo in self._em_grupos(chaves,
                                                  lambda k: k[0]).items():
            self._de(conta_id).apagar_fichas(do_grupo)

    def guardar_apagar_pendente(self, conta_id, conversa_id, mensagem_id,
                                minha, data, remetente):
        self._de(conta_id).guardar_apagar_pendente(
            conta_id, conversa_id, mensagem_id, minha, data, remetente)

    def apagar_pendentes(self, conta_id):
        return self._de(conta_id).apagar_pendentes(conta_id)

    def tirar_apagar_pendente(self, conta_id, conversa_id, mensagem_id):
        self._de(conta_id).tirar_apagar_pendente(conta_id, conversa_id,
                                                 mensagem_id)

    # ----------------------------------------------- mensagens agendadas
    def guardar_agendada(self, conta_id, conversa_id, texto, quando,
                         resposta_a="", mencoes="", anexo=""):
        return self._de(conta_id).guardar_agendada(
            conta_id, conversa_id, texto, quando, resposta_a, mencoes, anexo)

    def agendadas(self, conta_id, conversa_id=None):
        return self._de(conta_id).agendadas(conta_id, conversa_id)

    def agendada(self, id_, conta_id=None):
        """A agendada pelo numero; com a conta conhecida, olha so nela
        (os numeros se repetem entre as contas)."""
        if conta_id is not None:
            return self._de(conta_id).agendada(id_)
        for i in self._conhecidas():
            achada = self._de(i).agendada(id_)
            if achada is not None:
                return achada
        return None

    def agendadas_vencidas(self, conta_id, ate):
        return self._de(conta_id).agendadas_vencidas(conta_id, ate)

    def marcar_agendadas_atrasadas(self, ids, conta_id=None):
        if conta_id is not None:
            self._de(conta_id).marcar_agendadas_atrasadas(ids)
            return
        for _, b in self._todas():
            b.marcar_agendadas_atrasadas(ids)

    def mudar_agendada(self, id_, quando, conta_id=None):
        if conta_id is not None:
            self._de(conta_id).mudar_agendada(id_, quando)
            return
        for _, b in self._todas():
            b.mudar_agendada(id_, quando)

    def tirar_agendadas(self, ids, conta_id=None):
        if conta_id is not None:
            self._de(conta_id).tirar_agendadas(ids)
            return
        for _, b in self._todas():
            b.tirar_agendadas(ids)

    def esquecer_limpezas(self, conta_id):
        self._de(conta_id).esquecer_limpezas(conta_id)

    # ------------------------------------------------ conversas apagadas
    def apagada_ate(self, conta_id, conversa_id):
        return self._de(conta_id).apagada_ate(conta_id, conversa_id)

    def conversa_apagada(self, conv):
        """True se a conversa foi apagada e nao tem mensagem mais nova."""
        ate = self.apagada_ate(conv.conta_id, conv.id)
        return ate is not None and conv.data <= ate

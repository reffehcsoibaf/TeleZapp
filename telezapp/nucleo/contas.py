# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Liga, desliga e registra as contas. Cada conta tem o seu provedor.

Uma conta nova so e gravada na configuracao depois que o login termina
(evento ContaPronta); se a pessoa cancelar, nada fica para tras.
"""
import glob
import logging
import os
import time
import uuid

from telezapp import config
from telezapp.midia import armazem
from telezapp.nucleo import eventos as ev
from telezapp.nucleo.modelos import Conta

log = logging.getLogger("telezapp.contas")


class Contas:
    def __init__(self, cfg, banco, barramento, pedir, credenciais_telegram,
                 fabrica=None):
        """pedir(conta, etapa, erro) -> texto ou None (bloqueia a thread do
        provedor). credenciais_telegram() -> (api_id, api_hash) ou None."""
        self.cfg = cfg
        self.banco = banco
        self.barramento = barramento
        self.pedir = pedir
        self.credenciais_telegram = credenciais_telegram
        self.fabrica = fabrica or self._criar_provedor
        self.provedores = {}
        self.contas = {}
        self._novas = set()
        self._historico = {}      # conta_id -> opcao de historico (WhatsApp)
        barramento.ouvir(self._ao_evento)

    def _criar_provedor(self, conta):
        if conta.servico == "telegram":
            cred = self.credenciais_telegram()
            if cred is None:
                return None
            from telezapp.provedores.telegram import ProvedorTelegram
            return ProvedorTelegram(
                conta, self.barramento, self.banco,
                lambda etapa, erro: self.pedir(conta, etapa, erro), cred,
                perguntar_telefone=conta.id in self._novas)
        if conta.servico == "whatsapp":
            from telezapp.provedores.whatsapp import ProvedorWhatsApp
            return ProvedorWhatsApp(
                conta, self.barramento, self.banco,
                historico=self._historico.get(conta.id, "recentes"))
        log.warning("serviço ainda sem suporte: %s", conta.servico)
        return None

    def _ligar(self, conta):
        p = self.fabrica(conta)
        if p is None:
            return False
        self.contas[conta.id] = conta
        self.provedores[conta.id] = p
        p.iniciar()
        return True

    def esta_ativa(self, conta_id):
        """Conta ligada ao servico (a padrao). Desativada, ela so mostra o
        que ja esta guardado neste computador."""
        for dados in self.cfg.contas():
            if dados["id"] == conta_id:
                return dados.get("ativa", True) is not False
        return True

    def iniciar_salvas(self):
        for dados in self.cfg.contas():
            conta = Conta(dados["id"], dados.get("servico", "telegram"),
                          dados.get("telefone", ""), dados.get("nome", ""))
            self._historico[conta.id] = dados.get("historico", "recentes")
            if dados.get("ativa", True) is False:
                self.contas[conta.id] = conta
                self.barramento.publicar(ev.EstadoConta(
                    conta.id, ev.DESCONECTADA, "desativada"))
                log.info("conta %s desativada: não conecta", conta.id)
                continue
            if not self._ligar(conta):
                self.barramento.publicar(ev.Aviso(
                    conta.id, "Não foi possível iniciar a conta %s." % (
                        conta.nome or conta.id), True))

    def _guardar_ativa(self, conta_id, ativa):
        for dados in self.cfg.contas():
            if dados["id"] == conta_id:
                dados["ativa"] = ativa
                self.cfg.salvar_conta(dados)
                return True
        return False

    def desativar(self, conta_id):
        """Desconecta a conta e a deixa desligada ate ser ativada. As
        conversas e mensagens guardadas continuam na tela."""
        if not self._guardar_ativa(conta_id, False):
            return False
        p = self.provedores.pop(conta_id, None)
        if p is not None:
            p.parar()
        self.barramento.publicar(ev.EstadoConta(
            conta_id, ev.DESCONECTADA, "desativada"))
        log.info("conta %s desativada", conta_id)
        return True

    def ativar(self, conta_id):
        """Liga de novo uma conta desativada (conecta na hora)."""
        conta = self.contas.get(conta_id)
        if conta is None or not self._guardar_ativa(conta_id, True):
            return False
        log.info("conta %s ativada", conta_id)
        if conta_id in self.provedores:
            return True
        return self._ligar(conta)

    def adicionar(self, servico, telefone_sugerido="", historico="recentes"):
        """Comeca o login de uma conta nova. False se nao foi possivel.
        historico: quanto historico pedir ao celular (so WhatsApp)."""
        conta = Conta("%s-%s" % (servico, uuid.uuid4().hex[:8]), servico,
                      telefone_sugerido)
        self._novas.add(conta.id)
        self._historico[conta.id] = historico
        if not self._ligar(conta):
            self._novas.discard(conta.id)
            return False
        log.info("adicionando conta %s", conta.id)
        return True

    def cancelar_nova(self, conta_id):
        """A pessoa desistiu de adicionar a conta (ex.: fechou o
        pareamento): desliga e esquece. Contas salvas nao sao apagadas."""
        if conta_id not in self._novas:
            return False
        self._novas.discard(conta_id)
        p = self.provedores.pop(conta_id, None)
        self.contas.pop(conta_id, None)
        if p is not None:
            p.parar()
        log.info("conta nova cancelada")
        return True

    def eh_nova(self, conta_id):
        return conta_id in self._novas

    def servico(self, conta_id):
        c = self.contas.get(conta_id)
        return c.servico if c else ""

    def reconectar(self, conta_id):
        """Recria o provedor de uma conta salva (depois de um login
        cancelado ou de um erro)."""
        conta = self.contas.get(conta_id)
        p = self.provedores.pop(conta_id, None)
        if p is not None:
            p.parar()
        return conta is not None and self.esta_ativa(conta_id) and \
            self._ligar(conta)

    def parear_de_novo(self, conta_id, historico="recentes"):
        """WhatsApp desconectado pelo celular: apaga so a sessao e pareia de
        novo na mesma conta (as conversas guardadas continuam)."""
        conta = self.contas.get(conta_id)
        if conta is None:
            return False
        p = self.provedores.pop(conta_id, None)
        if p is not None:
            p.parar()
        apagar_sessao(conta_id)
        if self.banco is not None:
            self.banco.esquecer_limpezas(conta_id)   # pode voltar
        self._historico[conta_id] = historico
        log.info("pareando de novo a conta %s (histórico: %s)", conta_id,
                 historico)
        return self._ligar(conta)

    def reiniciar_pareamento(self, conta_id):
        """O pareamento do WhatsApp falhou: religa a conta do zero, para o
        WhatsApp mandar um QR Code novo e o codigo poder ser pedido de novo.
        Nao mexe nas conversas guardadas nem na escolha do historico."""
        conta = self.contas.get(conta_id)
        if conta is None:
            return False
        p = self.provedores.pop(conta_id, None)
        if p is not None:
            p.parar()
        apagar_sessao(conta_id)
        log.info("recomeçando o pareamento da conta %s", conta_id)
        return self._ligar(conta)

    def remover(self, conta_id):
        """Tira a conta do app: desliga, apaga a sessao, as conversas e as
        mensagens guardadas e a tira da configuracao."""
        p = self.provedores.pop(conta_id, None)
        if p is not None:
            p.parar()
        self.contas.pop(conta_id, None)
        self._novas.discard(conta_id)
        self.cfg.remover_conta(conta_id)
        if self.banco is not None:
            self.banco.apagar_conta(conta_id)
        apagar_sessao(conta_id)
        armazem.apagar_conta(conta_id)
        log.info("conta %s removida", conta_id)

    def provedor(self, conta_id):
        return self.provedores.get(conta_id)

    def nome(self, conta_id):
        c = self.contas.get(conta_id)
        return (c.nome or c.telefone or c.id) if c else conta_id

    def renomear(self, conta_id, apelido):
        """Da um nome seu a conta (vazio volta ao nome do servico). O apelido
        fica na configuracao e sobrevive a cada conexao."""
        apelido = " ".join((apelido or "").split())
        for dados in self.cfg.contas():
            if dados["id"] != conta_id:
                continue
            if apelido:
                dados["apelido"] = apelido
            else:
                dados.pop("apelido", None)
            dados["nome"] = apelido or dados.get("nome_servico") or \
                dados.get("nome", "")
            self.cfg.salvar_conta(dados)
            conta = self.contas.get(conta_id)
            if conta is not None:
                conta.nome = dados["nome"]
            return True
        return False

    def parar_todos(self):
        for p in list(self.provedores.values()):
            try:
                p.parar()
            except Exception:
                log.exception("erro ao parar provedor")

    def _ao_evento(self, e):
        if isinstance(e, ev.ContaPronta):
            conta = self.contas.get(e.conta_id)
            if conta is None:
                return
            antigo = next((d for d in self.cfg.contas()
                           if d["id"] == conta.id), {})
            apelido = antigo.get("apelido", "")
            conta.nome, conta.telefone = apelido or e.nome, e.telefone
            dados = {"id": conta.id, "servico": conta.servico,
                     "telefone": conta.telefone, "nome": conta.nome,
                     "nome_servico": e.nome}
            if apelido:
                dados["apelido"] = apelido
            if antigo.get("ativa") is False:
                dados["ativa"] = False
            if conta.servico == "whatsapp":
                dados["historico"] = self._historico.get(conta.id,
                                                         "recentes")
            self.cfg.salvar_conta(dados)
            if e.conta_id in self._novas:
                self._novas.discard(e.conta_id)
                log.info("conta %s gravada (%s)", conta.id,
                         config.mascarar_telefone(conta.telefone))
        elif isinstance(e, ev.EstadoConta) and e.estado == ev.PRECISA_LOGIN \
                and e.conta_id in self._novas:
            # login de conta nova cancelado: desliga e esquece
            self._novas.discard(e.conta_id)
            p = self.provedores.pop(e.conta_id, None)
            self.contas.pop(e.conta_id, None)
            if p is not None:
                p.parar()
            log.info("login de conta nova cancelado")


def apagar_sessao(conta_id, pasta=None):
    """Apaga os arquivos de sessao da conta (Telegram e WhatsApp)."""
    pasta = pasta or config.pasta("sessoes")
    for caminho in glob.glob(os.path.join(pasta, glob.escape(conta_id) + "*")):
        nome = os.path.basename(caminho)
        if nome == conta_id + ".db" or nome.startswith(conta_id + ".db-") \
                or nome.startswith(conta_id + ".session"):
            for tentativa in range(3):
                try:
                    os.remove(caminho)
                    break
                except OSError:
                    time.sleep(0.5)
            else:
                # no WhatsApp, a sessao desconectada ja foi limpa pela
                # propria biblioteca: o arquivo em uso nao atrapalha
                log.info("arquivo de sessão em uso, mantido: %s", nome)

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Liga, desliga e registra as contas. Cada conta tem o seu provedor.

Uma conta nova so e gravada na configuracao depois que o login termina
(evento ContaPronta); se a pessoa cancelar, nada fica para tras.
"""
import logging
import uuid

from telezapp import config
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
            return ProvedorWhatsApp(conta, self.barramento, self.banco)
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

    def iniciar_salvas(self):
        for dados in self.cfg.contas():
            conta = Conta(dados["id"], dados.get("servico", "telegram"),
                          dados.get("telefone", ""), dados.get("nome", ""))
            if not self._ligar(conta):
                self.barramento.publicar(ev.Aviso(
                    conta.id, "Não foi possível iniciar a conta %s." % (
                        conta.nome or conta.id), True))

    def adicionar(self, servico, telefone_sugerido=""):
        """Comeca o login de uma conta nova. False se nao foi possivel."""
        conta = Conta("%s-%s" % (servico, uuid.uuid4().hex[:8]), servico,
                      telefone_sugerido)
        self._novas.add(conta.id)
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
        return conta is not None and self._ligar(conta)

    def provedor(self, conta_id):
        return self.provedores.get(conta_id)

    def nome(self, conta_id):
        c = self.contas.get(conta_id)
        return (c.nome or c.telefone or c.id) if c else conta_id

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
            conta.nome, conta.telefone = e.nome, e.telefone
            self.cfg.salvar_conta({"id": conta.id, "servico": conta.servico,
                                   "telefone": conta.telefone,
                                   "nome": conta.nome})
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

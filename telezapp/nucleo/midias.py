# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Gerente de downloads de midias.

Roda os downloads em threads proprias (a interface nunca espera a rede),
registra cada arquivo baixado no banco e decide, pela opcao da pessoa, se
baixa ao receber ou so quando ela abrir.
"""
import logging
import os
import queue
import threading
import time

from telezapp.midia import armazem
from telezapp.nucleo import eventos as ev
from telezapp.provedores.base import (CelularSemResposta, DownloadCancelado,
                                       ErroMidia)

log = logging.getLogger("telezapp.midias")

PRONTA, INICIADO, EM_ANDAMENTO = "pronta", "iniciado", "em andamento"
LIMPA = "limpa"
TEXTO_LIMPA = ("Esta mídia foi limpada e só volta com um novo pareamento "
               "da conta.")


# Num lote, o celular que parou de responder faz esperar, nao falhar: de quanto
# em quanto tempo tenta de novo e depois de quanto tempo desiste (segundos)
ESPERA_PELO_CELULAR = 20
DESISTIR_DO_CELULAR = 1800
TEXTO_CELULAR_PAROU = ("O celular parou de responder. Desbloqueie o celular e "
                       "deixe o WhatsApp aberto: os downloads continuam "
                       "sozinhos quando ele voltar.")


class _Andamento:
    def __init__(self, automatica):
        self.cancelar = threading.Event()
        self.automatica = automatica


class Lote:
    """Download das midias que faltam numa conversa: conta o que baixou, o que
    nao estava mais disponivel e o que foi cancelado, e avisa o progresso e o
    fim. Os avisos vem da thread que publica o evento (a da janela no app)."""

    def __init__(self, chaves, ao_progresso=None, ao_fim=None):
        self.total = len(chaves)
        self.pendentes = set(chaves)
        self.baixadas = 0
        self.indisponiveis = 0
        self.fora_do_celular = 0
        self.sem_resposta = 0
        self.canceladas = 0
        self.celular_parado_desde = 0.0
        self.cancelado = False
        self.ao_progresso = ao_progresso
        self.ao_fim = ao_fim
        self.cancelar_chaves = None      # preenchido pelo gerente

    @property
    def feitas(self):
        return self.total - len(self.pendentes)

    def cancelar(self):
        self.cancelado = True
        if self.cancelar_chaves is not None:
            self.cancelar_chaves(list(self.pendentes))


class GerenteMidias:
    def __init__(self, cfg, banco, barramento, provedor_de, trabalhadores=2):
        """provedor_de(conta_id) -> provedor ou None."""
        self.cfg = cfg
        self.banco = banco
        self.barramento = barramento
        self.provedor_de = provedor_de
        self._fila = queue.Queue()
        self._ativos = {}            # chave da mensagem -> _Andamento
        self._lotes = []             # downloads em lote (por conversa)
        self._trava = threading.Lock()
        self._parar = threading.Event()
        self._threads = []
        for i in range(trabalhadores):
            t = threading.Thread(target=self._trabalhar, daemon=True,
                                 name="midias-%d" % i)
            t.start()
            self._threads.append(t)
        barramento.ouvir(self._ao_evento)

    # ------------------------------------------------------------ consulta
    def caminho(self, msg):
        """Arquivo ja baixado da mensagem, ou None."""
        reg = self.banco.midia(msg.conta_id, msg.conversa_id, msg.id)
        if reg is None:
            return None
        if os.path.isfile(reg[0]):
            return reg[0]
        self.banco.esquecer_midia(msg.conta_id, msg.conversa_id, msg.id)
        return None

    def baixando(self, chave):
        with self._trava:
            return chave in self._ativos

    def algum_baixando(self):
        with self._trava:
            return bool(self._ativos)

    # --------------------------------------------------------------- pedidos
    def baixar(self, msg, automatica=False):
        """PRONTA (ja existe; o evento sai na hora), INICIADO ou
        EM_ANDAMENTO."""
        if self.banco.foi_limpa(msg.conta_id, msg.conversa_id, msg.id):
            self.barramento.publicar(ev.MidiaBaixada(
                msg.conta_id, msg.conversa_id, msg.id, erro=TEXTO_LIMPA,
                automatica=automatica))
            return LIMPA
        existente = self.caminho(msg)
        if existente:
            self.barramento.publicar(ev.MidiaBaixada(
                msg.conta_id, msg.conversa_id, msg.id, existente,
                automatica=automatica))
            return PRONTA
        with self._trava:
            if msg.chave in self._ativos:
                # a pessoa pediu depois do automatico: passa a ser dela
                if not automatica:
                    self._ativos[msg.chave].automatica = False
                return EM_ANDAMENTO
            self._ativos[msg.chave] = _Andamento(automatica)
        self._fila.put(msg)
        return INICIADO

    def cancelar(self, chave):
        with self._trava:
            a = self._ativos.get(chave)
        if a is None:
            return False
        a.cancelar.set()
        return True

    def faltantes(self, mensagens):
        """As mensagens com midia baixavel que ainda nao estao neste
        computador, da mais nova para a mais antiga (sem as limpadas)."""
        achadas = []
        for x in reversed(list(mensagens)):
            if x.tipo not in armazem.BAIXAVEIS:
                continue
            if self.banco.foi_limpa(x.conta_id, x.conversa_id, x.id):
                continue
            if self.caminho(x):
                continue
            achadas.append(x)
        return achadas

    def baixar_lote(self, mensagens, ao_progresso=None, ao_fim=None):
        """Baixa de uma vez as `mensagens` (ver `faltantes`). `ao_progresso(
        feitas, total)` a cada midia resolvida; `ao_fim(lote)` no fim, com
        `baixadas`, `indisponiveis` e `canceladas`. Devolve o `Lote`."""
        lote = Lote([x.chave for x in mensagens], ao_progresso, ao_fim)
        lote.cancelar_chaves = lambda chaves: [self.cancelar(c) for c in chaves]
        if not mensagens:
            if ao_fim is not None:
                ao_fim(lote)
            return lote
        with self._trava:
            self._lotes.append(lote)
        for x in mensagens:
            self.baixar(x, automatica=True)
        return lote

    def _contar_no_lote(self, e):
        chave = (e.conta_id, e.conversa_id, e.mensagem_id)
        with self._trava:
            lote = next((l for l in self._lotes if chave in l.pendentes),
                        None)
            if lote is None:
                return
            lote.pendentes.discard(chave)
            if e.caminho:
                lote.baixadas += 1
            elif e.cancelada:
                lote.canceladas += 1
            elif e.motivo == "sem_resposta":
                lote.sem_resposta += 1
            elif e.motivo == "fora_do_celular":
                lote.fora_do_celular += 1
            else:
                lote.indisponiveis += 1
            terminou = not lote.pendentes
            if terminou:
                self._lotes.remove(lote)
        if lote.ao_progresso is not None:
            lote.ao_progresso(lote.feitas, lote.total)
        if terminou and lote.ao_fim is not None:
            lote.ao_fim(lote)

    def cancelar_todos(self):
        with self._trava:
            for a in self._ativos.values():
                a.cancelar.set()

    def parar(self):
        self._parar.set()
        self.cancelar_todos()

    # -------------------------------------------------------------- trabalho
    def _trabalhar(self):
        while not self._parar.is_set():
            try:
                msg = self._fila.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._executar(msg)
            except Exception:
                log.exception("erro no gerente de mídias")

    def _executar(self, msg):
        with self._trava:
            a = self._ativos.get(msg.chave)
        if a is None:
            return
        resultado = dict(caminho="", erro="", cancelada=False)
        ultimo = [-100]

        def progresso(p):
            if p - ultimo[0] >= 5 or p >= 100:
                ultimo[0] = p
                self.barramento.publicar(ev.ProgressoMidia(
                    msg.conta_id, msg.conversa_id, msg.id, int(p)))
        inicio = time.perf_counter()
        try:
            provedor = self.provedor_de(msg.conta_id)
            if provedor is None:
                raise ErroMidia("A conta não está ativa.")
            if a.cancelar.is_set():
                raise DownloadCancelado()
            resultado["caminho"] = self._baixar_esperando_o_celular(
                provedor, msg, progresso, a)
            self.banco.registrar_midia(
                msg.conta_id, msg.conversa_id, msg.id, msg.tipo,
                resultado["caminho"],
                os.path.getsize(resultado["caminho"]), time.time())
            log.info("mídia baixada (%s) em %.1fs", msg.tipo,
                     time.perf_counter() - inicio)
        except DownloadCancelado:
            resultado["cancelada"] = True
        except ErroMidia as e:
            resultado["erro"] = str(e)
            resultado["motivo"] = e.motivo
        except Exception:
            log.exception("erro ao baixar mídia")
            resultado["erro"] = ("Não foi possível baixar a mídia. Os "
                                 "detalhes estão no log.")
        finally:
            with self._trava:
                self._ativos.pop(msg.chave, None)
        self.barramento.publicar(ev.MidiaBaixada(
            msg.conta_id, msg.conversa_id, msg.id,
            automatica=a.automatica, **resultado))

    def _baixar_esperando_o_celular(self, provedor, msg, progresso, a):
        """Baixa. Num lote, se a midia depende do celular e ele nao responde,
        espera e tenta de novo, em vez de dar a midia por perdida; fora de um
        lote, a pessoa fica sabendo na hora."""
        esperou = False
        while True:
            try:
                caminho = provedor.baixar_arquivo(
                    msg, armazem.caminho_base(msg), progresso,
                    a.cancelar.is_set)
            except CelularSemResposta:
                self._esperar_o_celular(msg, a)
                esperou = True
                continue
            if esperou:
                self._celular_voltou(msg)
            return caminho

    def _lote_da(self, msg):
        return next((l for l in self._lotes if msg.chave in l.pendentes), None)

    def _esperar_o_celular(self, msg, a):
        agora = time.time()
        with self._trava:
            lote = self._lote_da(msg)
            if lote is None:
                primeira = False
            else:
                primeira = not lote.celular_parado_desde
                if primeira:
                    lote.celular_parado_desde = agora
        if lote is None or \
                agora - lote.celular_parado_desde > DESISTIR_DO_CELULAR:
            raise
        if primeira:
            log.info("lote de mídias esperando o celular")
            self.barramento.publicar(ev.Aviso(msg.conta_id,
                                              TEXTO_CELULAR_PAROU))
        if a.cancelar.wait(ESPERA_PELO_CELULAR) or self._parar.is_set():
            raise DownloadCancelado()

    def _celular_voltou(self, msg):
        with self._trava:
            lote = self._lote_da(msg)
            if lote is None or not lote.celular_parado_desde:
                return
            lote.celular_parado_desde = 0.0
        log.info("o celular voltou a responder: lote de mídias continua")
        self.barramento.publicar(ev.Aviso(
            msg.conta_id, "O celular voltou a responder."))

    # ------------------------------------------------------ baixar sozinho
    def _ao_evento(self, e):
        if isinstance(e, ev.MidiaBaixada):
            self._contar_no_lote(e)
            return
        if not isinstance(e, ev.MensagemNova) or e.enviada_daqui:
            return
        msg = e.mensagem
        if msg.minha or msg.tipo not in armazem.BAIXAVEIS:
            return
        if self.cfg.get("midias_baixar") != "automatico":
            return
        limite = int(self.cfg.get("midias_limite_auto_mb") or 0) * 1048576
        if msg.tamanho and msg.tamanho > limite:
            return
        self.baixar(msg, automatica=True)

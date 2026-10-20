# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
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
from telezapp.provedores.base import DownloadCancelado, ErroMidia

log = logging.getLogger("telezapp.midias")

PRONTA, INICIADO, EM_ANDAMENTO = "pronta", "iniciado", "em andamento"
LIMPA = "limpa"
TEXTO_LIMPA = ("Esta mídia foi limpada e só volta com um novo pareamento "
               "da conta.")


class _Andamento:
    def __init__(self, automatica):
        self.cancelar = threading.Event()
        self.automatica = automatica


class GerenteMidias:
    def __init__(self, cfg, banco, barramento, provedor_de, trabalhadores=2):
        """provedor_de(conta_id) -> provedor ou None."""
        self.cfg = cfg
        self.banco = banco
        self.barramento = barramento
        self.provedor_de = provedor_de
        self._fila = queue.Queue()
        self._ativos = {}            # chave da mensagem -> _Andamento
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
            resultado["caminho"] = provedor.baixar_arquivo(
                msg, armazem.caminho_base(msg), progresso,
                a.cancelar.is_set)
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

    # ------------------------------------------------------ baixar sozinho
    def _ao_evento(self, e):
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

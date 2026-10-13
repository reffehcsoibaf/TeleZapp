# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Banco local (SQLite): conversas e mensagens de todas as contas.

Serve para abrir o app ja com as conversas na tela, antes da rede responder,
e, no WhatsApp, para guardar o historico (que so chega como eventos).
Uma conexao compartilhada protegida por trava: as threads dos provedores e a
da interface podem chamar qualquer metodo.
"""
import logging
import sqlite3
import threading
from dataclasses import astuple, fields

from telezapp.nucleo.modelos import ORDEM_ESTADOS, Conversa, Mensagem

log = logging.getLogger("telezapp.banco")

VERSAO_ESQUEMA = 2

ESQUEMA = """
CREATE TABLE IF NOT EXISTS conversas (
    conta_id TEXT NOT NULL,
    id TEXT NOT NULL,
    nome TEXT NOT NULL,
    servico TEXT NOT NULL,
    tipo TEXT NOT NULL,
    nao_lidas INTEGER NOT NULL DEFAULT 0,
    data REAL NOT NULL DEFAULT 0,
    lidas_ate INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (conta_id, id)
);
CREATE TABLE IF NOT EXISTS mensagens (
    conta_id TEXT NOT NULL,
    conversa_id TEXT NOT NULL,
    id TEXT NOT NULL,
    autor TEXT NOT NULL DEFAULT '',
    minha INTEGER NOT NULL DEFAULT 0,
    data REAL NOT NULL DEFAULT 0,
    tipo TEXT NOT NULL DEFAULT 'texto',
    texto TEXT NOT NULL DEFAULT '',
    segundos INTEGER NOT NULL DEFAULT 0,
    nome_arquivo TEXT NOT NULL DEFAULT '',
    tamanho INTEGER NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT '',
    resposta_a TEXT NOT NULL DEFAULT '',
    remetente TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (conta_id, conversa_id, id)
);
CREATE INDEX IF NOT EXISTS mensagens_por_data
    ON mensagens (conta_id, conversa_id, data);
"""

_CAMPOS_CONV = [f.name for f in fields(Conversa)]
_CAMPOS_MSG = [f.name for f in fields(Mensagem)]


class Banco:
    def __init__(self, caminho):
        self.caminho = caminho
        self._trava = threading.Lock()
        self._con = sqlite3.connect(caminho, check_same_thread=False)
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA synchronous=NORMAL")
        with self._con:
            self._con.executescript(ESQUEMA)
            self._atualizar_esquema()
            self._con.execute("PRAGMA user_version=%d" % VERSAO_ESQUEMA)

    def _atualizar_esquema(self):
        """Bancos de versoes anteriores ganham as colunas novas."""
        colunas = {linha[1] for linha in self._con.execute(
            "PRAGMA table_info(mensagens)")}
        if "remetente" not in colunas:
            self._con.execute("ALTER TABLE mensagens ADD COLUMN remetente "
                              "TEXT NOT NULL DEFAULT ''")
            log.info("banco atualizado para a versão %d", VERSAO_ESQUEMA)

    def fechar(self):
        with self._trava:
            self._con.close()

    # ------------------------------------------------------------ conversas
    def salvar_conversas(self, conversas):
        sql = "INSERT OR REPLACE INTO conversas (%s) VALUES (%s)" % (
            ", ".join(_CAMPOS_CONV), ", ".join("?" * len(_CAMPOS_CONV)))
        with self._trava, self._con:
            self._con.executemany(sql, [astuple(c) for c in conversas])

    def conversas(self, conta_id):
        with self._trava:
            linhas = self._con.execute(
                "SELECT %s FROM conversas WHERE conta_id=? "
                "ORDER BY data DESC" % ", ".join(_CAMPOS_CONV),
                (conta_id,)).fetchall()
        return [Conversa(*l) for l in linhas]

    def atualizar_conversa(self, conta_id, conversa_id, **valores):
        if not valores:
            return
        partes = ", ".join("%s=?" % k for k in valores)
        with self._trava, self._con:
            self._con.execute(
                "UPDATE conversas SET %s WHERE conta_id=? AND id=?" % partes,
                (*valores.values(), conta_id, conversa_id))

    def apagar_conta(self, conta_id):
        with self._trava, self._con:
            self._con.execute("DELETE FROM conversas WHERE conta_id=?",
                              (conta_id,))
            self._con.execute("DELETE FROM mensagens WHERE conta_id=?",
                              (conta_id,))

    # ------------------------------------------------------------ mensagens
    def salvar_mensagens(self, mensagens):
        sql = "INSERT OR REPLACE INTO mensagens (%s) VALUES (%s)" % (
            ", ".join(_CAMPOS_MSG), ", ".join("?" * len(_CAMPOS_MSG)))
        with self._trava, self._con:
            self._con.executemany(
                sql, [_linha_msg(m) for m in mensagens])

    def mensagens(self, conta_id, conversa_id, limite=100):
        """As `limite` mais recentes, da mais antiga para a mais nova."""
        with self._trava:
            linhas = self._con.execute(
                "SELECT %s FROM mensagens WHERE conta_id=? AND conversa_id=? "
                "ORDER BY data DESC, CAST(id AS INTEGER) DESC LIMIT ?"
                % ", ".join(_CAMPOS_MSG),
                (conta_id, conversa_id, limite)).fetchall()
        return [_msg(l) for l in reversed(linhas)]

    def mudar_estado(self, conta_id, conversa_id, ids, estado):
        """WhatsApp: muda o estado das minhas mensagens com esses ids, sem
        voltar atras (lida nao vira entregue). Devolve os ids que mudaram."""
        nivel = ORDEM_ESTADOS.get(estado, 0)
        mudaram = []
        with self._trava, self._con:
            for i in ids:
                linha = self._con.execute(
                    "SELECT estado FROM mensagens WHERE conta_id=? AND "
                    "conversa_id=? AND id=? AND minha=1",
                    (conta_id, conversa_id, i)).fetchone()
                if linha is None or ORDEM_ESTADOS.get(linha[0], 0) >= nivel:
                    continue
                self._con.execute(
                    "UPDATE mensagens SET estado=? WHERE conta_id=? AND "
                    "conversa_id=? AND id=?", (estado, conta_id, conversa_id,
                                               i))
                mudaram.append(i)
        return mudaram

    def marcar_lidas_pelo_outro(self, conta_id, conversa_id, ate_id, estado):
        """Telegram: muda o estado das minhas mensagens com id <= ate_id."""
        with self._trava, self._con:
            self._con.execute(
                "UPDATE mensagens SET estado=? WHERE conta_id=? AND "
                "conversa_id=? AND minha=1 AND CAST(id AS INTEGER)<=?",
                (estado, conta_id, conversa_id, ate_id))


def _linha_msg(m):
    t = list(astuple(m))
    t[_CAMPOS_MSG.index("minha")] = 1 if m.minha else 0
    return t


def _msg(linha):
    m = Mensagem(*linha)
    m.minha = bool(m.minha)
    return m

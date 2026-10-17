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

VERSAO_ESQUEMA = 10

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
    arquivada INTEGER NOT NULL DEFAULT 0,
    trancada INTEGER NOT NULL DEFAULT 0,
    fixada INTEGER NOT NULL DEFAULT 0,
    silenciada_ate REAL NOT NULL DEFAULT 0,
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
    extras TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (conta_id, conversa_id, id)
);
CREATE INDEX IF NOT EXISTS mensagens_por_data
    ON mensagens (conta_id, conversa_id, data);
-- Quando cada pessoa recebeu, leu ou ouviu uma mensagem minha.
CREATE TABLE IF NOT EXISTS recibos (
    conta_id TEXT NOT NULL,
    conversa_id TEXT NOT NULL,
    mensagem_id TEXT NOT NULL,
    participante TEXT NOT NULL,
    tipo TEXT NOT NULL,
    data REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (conta_id, conversa_id, mensagem_id, participante, tipo)
);
-- Status (stories) do WhatsApp: guardados fora das conversas.
CREATE TABLE IF NOT EXISTS status (
    conta_id TEXT NOT NULL,
    id TEXT NOT NULL,
    autor_id TEXT NOT NULL DEFAULT '',
    autor TEXT NOT NULL DEFAULT '',
    minha INTEGER NOT NULL DEFAULT 0,
    data REAL NOT NULL DEFAULT 0,
    tipo TEXT NOT NULL DEFAULT 'texto',
    texto TEXT NOT NULL DEFAULT '',
    segundos INTEGER NOT NULL DEFAULT 0,
    nome_arquivo TEXT NOT NULL DEFAULT '',
    tamanho INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (conta_id, id)
);
-- WhatsApp: o que o servico exige para baixar uma midia (chaves, caminho).
CREATE TABLE IF NOT EXISTS fichas (
    conta_id TEXT NOT NULL,
    conversa_id TEXT NOT NULL,
    mensagem_id TEXT NOT NULL,
    dados BLOB NOT NULL,
    PRIMARY KEY (conta_id, conversa_id, mensagem_id)
);
-- Ponto em que a pessoa parou em cada conversa ('' = no fim da lista).
CREATE TABLE IF NOT EXISTS posicoes (
    conta_id TEXT NOT NULL,
    conversa_id TEXT NOT NULL,
    mensagem_id TEXT NOT NULL,
    PRIMARY KEY (conta_id, conversa_id)
);
-- Arquivos de midia baixados (base da limpeza de conversas).
CREATE TABLE IF NOT EXISTS midias (
    conta_id TEXT NOT NULL,
    conversa_id TEXT NOT NULL,
    mensagem_id TEXT NOT NULL,
    tipo TEXT NOT NULL,
    caminho TEXT NOT NULL,
    tamanho INTEGER NOT NULL DEFAULT 0,
    data REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (conta_id, conversa_id, mensagem_id)
);
-- Mensagens e midias limpas pela pessoa: o registro impede que voltem (por
-- historico, nova leitura ou download) ate um novo pareamento da conta.
-- alvo: 'mensagem' (a mensagem inteira) ou 'midia' (so o arquivo).
CREATE TABLE IF NOT EXISTS limpas (
    conta_id TEXT NOT NULL,
    conversa_id TEXT NOT NULL,
    mensagem_id TEXT NOT NULL,
    alvo TEXT NOT NULL,
    PRIMARY KEY (conta_id, conversa_id, mensagem_id)
);
-- Conversas apagadas pela pessoa: so voltam com mensagem mais nova que `ate`
-- (data da ultima mensagem que ela tinha), ou com um novo pareamento.
CREATE TABLE IF NOT EXISTS apagadas (
    conta_id TEXT NOT NULL,
    conversa_id TEXT NOT NULL,
    ate REAL NOT NULL,
    PRIMARY KEY (conta_id, conversa_id)
);
-- Agenda propria do TeleZapp: o nome que a pessoa deu a cada contato.
CREATE TABLE IF NOT EXISTS contatos (
    conta_id TEXT NOT NULL,
    id TEXT NOT NULL,
    nome TEXT NOT NULL,
    telefone TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (conta_id, id)
);
-- Estrutura original das mensagens, so com o modo de depuracao ligado.
CREATE TABLE IF NOT EXISTS depuracao (
    conta_id TEXT NOT NULL,
    conversa_id TEXT NOT NULL,
    mensagem_id TEXT NOT NULL,
    dados TEXT NOT NULL,
    PRIMARY KEY (conta_id, conversa_id, mensagem_id)
);
"""

MAX_DEPURACAO = 500

_CAMPOS_CONV = [f.name for f in fields(Conversa)]
_CAMPOS_MSG = [f.name for f in fields(Mensagem)]


class Banco:
    def __init__(self, caminho):
        self.caminho = caminho
        self._trava = threading.Lock()
        self.depuracao = False        # modo de depuracao (ver guardar_depuracao)
        self._agenda = None           # cache de contatos: (conta, id) -> nome
        self._limpas = None           # cache de `limpas`: chave -> alvo
        self._apagadas = None         # cache de `apagadas`: chave -> ate
        self._con = sqlite3.connect(caminho, check_same_thread=False)
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA synchronous=NORMAL")
        with self._con:
            self._con.executescript(ESQUEMA)
            self._atualizar_esquema()
            self._con.execute("PRAGMA user_version=%d" % VERSAO_ESQUEMA)

    def _atualizar_esquema(self):
        """Bancos de versoes anteriores ganham as colunas novas."""
        conv = {linha[1] for linha in self._con.execute(
            "PRAGMA table_info(conversas)")}
        if "arquivada" not in conv:
            self._con.execute("ALTER TABLE conversas ADD COLUMN arquivada "
                              "INTEGER NOT NULL DEFAULT 0")
        if "trancada" not in conv:
            self._con.execute("ALTER TABLE conversas ADD COLUMN trancada "
                              "INTEGER NOT NULL DEFAULT 0")
        if "fixada" not in conv:
            self._con.execute("ALTER TABLE conversas ADD COLUMN fixada "
                              "INTEGER NOT NULL DEFAULT 0")
        if "silenciada_ate" not in conv:
            self._con.execute("ALTER TABLE conversas ADD COLUMN "
                              "silenciada_ate REAL NOT NULL DEFAULT 0")
        colunas = {linha[1] for linha in self._con.execute(
            "PRAGMA table_info(mensagens)")}
        if "remetente" not in colunas:
            self._con.execute("ALTER TABLE mensagens ADD COLUMN remetente "
                              "TEXT NOT NULL DEFAULT ''")
            log.info("banco atualizado: coluna remetente")
        if "extras" not in colunas:
            self._con.execute("ALTER TABLE mensagens ADD COLUMN extras "
                              "TEXT NOT NULL DEFAULT ''")
            log.info("banco atualizado para a versão %d", VERSAO_ESQUEMA)

    # ------------------------------------------------------------ depuracao
    def guardar_depuracao(self, conta_id, conversa_id, mensagem_id, dados):
        """Guarda a estrutura original de uma mensagem (so com o modo de
        depuracao ligado), mantendo as MAX_DEPURACAO mais recentes."""
        if not self.depuracao:
            return
        with self._trava, self._con:
            self._con.execute(
                "INSERT OR REPLACE INTO depuracao VALUES (?,?,?,?)",
                (conta_id, conversa_id, mensagem_id, dados))
            self._con.execute(
                "DELETE FROM depuracao WHERE rowid <= "
                "(SELECT MAX(rowid) FROM depuracao) - ?", (MAX_DEPURACAO,))

    def depuracao_de(self, conta_id, conversa_id, mensagem_id):
        with self._trava:
            linha = self._con.execute(
                "SELECT dados FROM depuracao WHERE conta_id=? AND "
                "conversa_id=? AND mensagem_id=?",
                (conta_id, conversa_id, mensagem_id)).fetchone()
        return linha[0] if linha else ""

    def limpar_depuracao(self):
        with self._trava, self._con:
            self._con.execute("DELETE FROM depuracao")

    def fechar(self):
        with self._trava:
            self._con.close()

    # ------------------------------------------------------------ conversas
    def salvar_conversas(self, conversas):
        conversas = [c for c in conversas if not self.conversa_apagada(c)]
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
            for tabela in ("mensagens", "recibos", "status", "midias",
                           "fichas", "posicoes", "contatos", "limpas", "apagadas"):
                self._con.execute(
                    "DELETE FROM %s WHERE conta_id=?" % tabela, (conta_id,))
            self._agenda = None
            self._limpas = None
            self._apagadas = None

    # ------------------------------------------------------------- contatos
    def contatos(self, conta_id=None):
        """[(conta_id, id, nome, telefone)] da agenda, por nome."""
        sql = "SELECT conta_id, id, nome, telefone FROM contatos"
        args = ()
        if conta_id is not None:
            sql, args = sql + " WHERE conta_id=?", (conta_id,)
        with self._trava:
            linhas = self._con.execute(
                sql + " ORDER BY nome COLLATE NOCASE", args).fetchall()
        return [tuple(l) for l in linhas]

    def salvar_contato(self, conta_id, id_, nome, telefone=""):
        with self._trava, self._con:
            self._con.execute(
                "INSERT OR REPLACE INTO contatos VALUES (?,?,?,?)",
                (conta_id, id_, nome, telefone))
            self._agenda = None

    def remover_contato(self, conta_id, id_):
        with self._trava, self._con:
            self._con.execute(
                "DELETE FROM contatos WHERE conta_id=? AND id=?",
                (conta_id, id_))
            self._agenda = None

    def nome_de_contato(self, conta_id, *ids):
        """Nome que a pessoa deu ao contato, pelo primeiro id conhecido;
        vazio se nao houver. Usa um cache (chamado a cada nome mostrado)."""
        with self._trava:
            if self._agenda is None:
                self._agenda = {
                    (c, i): n for c, i, n in self._con.execute(
                        "SELECT conta_id, id, nome FROM contatos")}
            for i in ids:
                nome = self._agenda.get((conta_id, i))
                if nome:
                    return nome
        return ""

    # ------------------------------------------------------------ mensagens
    def salvar_mensagens(self, mensagens):
        limpas = self._mapa_limpas()
        apagadas = self._mapa_apagadas()
        mensagens = [x for x in mensagens if limpas.get(
            (x.conta_id, x.conversa_id, x.id)) != "mensagem"
            and x.data > apagadas.get((x.conta_id, x.conversa_id), -1)]
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

    def mensagens_por_id(self, conta_id, ids, conversa_id=None):
        """Mensagens guardadas com esses ids (no Telegram o id da mensagem
        e unico na conta, fora dos canais)."""
        ids = [str(i) for i in ids]
        if not ids:
            return []
        sql = ("SELECT %s FROM mensagens WHERE conta_id=? AND id IN (%s)"
               % (", ".join(_CAMPOS_MSG), ", ".join("?" * len(ids))))
        args = [conta_id, *ids]
        if conversa_id is not None:
            sql += " AND conversa_id=?"
            args.append(conversa_id)
        with self._trava:
            linhas = self._con.execute(sql, args).fetchall()
        return [_msg(l) for l in linhas]

    def nome_do_remetente(self, conta_id, remetentes):
        """Nome (autor) mais recente com que alguem dessa lista de enderecos
        aparece nas mensagens guardadas, sem contar telefones soltos."""
        remetentes = [r for r in remetentes if r]
        if not remetentes:
            return ""
        with self._trava:
            linha = self._con.execute(
                "SELECT autor FROM mensagens WHERE conta_id=? AND minha=0 "
                "AND autor<>'' AND autor NOT LIKE '+%%' AND autor NOT LIKE "
                "'%%@%%' AND remetente IN (%s) ORDER BY data DESC LIMIT 1"
                % ", ".join("?" * len(remetentes)),
                (conta_id, *remetentes)).fetchone()
        return linha[0] if linha else ""

    def mensagem(self, conta_id, conversa_id, mensagem_id):
        with self._trava:
            linha = self._con.execute(
                "SELECT %s FROM mensagens WHERE conta_id=? AND conversa_id=? "
                "AND id=?" % ", ".join(_CAMPOS_MSG),
                (conta_id, conversa_id, mensagem_id)).fetchone()
        return _msg(linha) if linha else None

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

    # -------------------------------------------------------------- recibos
    def salvar_recibos(self, conta_id, conversa_id, mensagem_ids,
                       participante, tipo, data):
        """Guarda que `participante` teve `tipo` (entregue, lida, ouvida)
        nessas mensagens. A primeira data vale; repetir nao muda."""
        with self._trava, self._con:
            self._con.executemany(
                "INSERT OR IGNORE INTO recibos VALUES (?,?,?,?,?,?)",
                [(conta_id, conversa_id, i, participante, tipo, data)
                 for i in mensagem_ids])

    def recibos(self, conta_id, conversa_id, mensagem_id):
        """[(participante, tipo, data)] em ordem de data."""
        with self._trava:
            return self._con.execute(
                "SELECT participante, tipo, data FROM recibos WHERE "
                "conta_id=? AND conversa_id=? AND mensagem_id=? "
                "ORDER BY data, participante",
                (conta_id, conversa_id, mensagem_id)).fetchall()

    # --------------------------------------------------------------- status
    def salvar_status(self, conta_id, s):
        """s: dict com id, autor_id, autor, minha, data, tipo, texto,
        segundos, nome_arquivo, tamanho."""
        with self._trava, self._con:
            self._con.execute(
                "INSERT OR REPLACE INTO status (conta_id, id, autor_id, "
                "autor, minha, data, tipo, texto, segundos, nome_arquivo, "
                "tamanho) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (conta_id, s["id"], s.get("autor_id", ""),
                 s.get("autor", ""), int(bool(s.get("minha"))),
                 s.get("data", 0), s.get("tipo", "texto"),
                 s.get("texto", ""), s.get("segundos", 0),
                 s.get("nome_arquivo", ""), s.get("tamanho", 0)))

    def status(self, conta_id, limite=200):
        """Os mais recentes primeiro."""
        with self._trava:
            linhas = self._con.execute(
                "SELECT id, autor_id, autor, minha, data, tipo, texto, "
                "segundos, nome_arquivo, tamanho FROM status WHERE "
                "conta_id=? ORDER BY data DESC LIMIT ?",
                (conta_id, limite)).fetchall()
        chaves = ("id", "autor_id", "autor", "minha", "data", "tipo",
                  "texto", "segundos", "nome_arquivo", "tamanho")
        return [dict(zip(chaves, l)) for l in linhas]

    # --------------------------------------------------------------- midias
    def registrar_midia(self, conta_id, conversa_id, mensagem_id, tipo,
                        caminho, tamanho, data):
        with self._trava, self._con:
            self._con.execute(
                "INSERT OR REPLACE INTO midias VALUES (?,?,?,?,?,?,?)",
                (conta_id, conversa_id, mensagem_id, tipo, caminho, tamanho,
                 data))

    def midias(self, conta_id, conversa_id=None):
        """[(conversa_id, mensagem_id, tipo, caminho, tamanho, data)]"""
        sql = ("SELECT conversa_id, mensagem_id, tipo, caminho, tamanho, "
               "data FROM midias WHERE conta_id=?")
        args = [conta_id]
        if conversa_id is not None:
            sql += " AND conversa_id=?"
            args.append(conversa_id)
        with self._trava:
            return self._con.execute(sql + " ORDER BY data", args).fetchall()

    def todas_midias(self):
        """[(conta_id, conversa_id, mensagem_id, tipo, caminho, tamanho,
        data)] de todas as contas."""
        with self._trava:
            return self._con.execute(
                "SELECT conta_id, conversa_id, mensagem_id, tipo, caminho, "
                "tamanho, data FROM midias ORDER BY data").fetchall()

    def midia(self, conta_id, conversa_id, mensagem_id):
        """(caminho, tamanho) da midia baixada, ou None."""
        with self._trava:
            return self._con.execute(
                "SELECT caminho, tamanho FROM midias WHERE conta_id=? AND "
                "conversa_id=? AND mensagem_id=?",
                (conta_id, conversa_id, mensagem_id)).fetchone()

    def salvar_fichas(self, fichas):
        """fichas: [(conta_id, conversa_id, mensagem_id, bytes)]"""
        with self._trava, self._con:
            self._con.executemany(
                "INSERT OR REPLACE INTO fichas VALUES (?,?,?,?)", fichas)

    def ficha(self, conta_id, conversa_id, mensagem_id):
        with self._trava:
            linha = self._con.execute(
                "SELECT dados FROM fichas WHERE conta_id=? AND "
                "conversa_id=? AND mensagem_id=?",
                (conta_id, conversa_id, mensagem_id)).fetchone()
        return bytes(linha[0]) if linha else None

    def salvar_posicao(self, conta_id, conversa_id, mensagem_id):
        """mensagem_id '' quer dizer: parou no fim da conversa."""
        with self._trava, self._con:
            self._con.execute(
                "INSERT OR REPLACE INTO posicoes VALUES (?, ?, ?)",
                (conta_id, conversa_id, mensagem_id))

    def posicao(self, conta_id, conversa_id):
        """None se a conversa nunca foi aberta; '' = fim; senao o id."""
        with self._trava:
            linha = self._con.execute(
                "SELECT mensagem_id FROM posicoes WHERE conta_id=? AND "
                "conversa_id=?", (conta_id, conversa_id)).fetchone()
        return linha[0] if linha else None

    # --------------------------------------------------------------- limpeza
    def _mapa_limpas(self):
        with self._trava:
            if self._limpas is None:
                self._limpas = {
                    (c, v, i): a for c, v, i, a in self._con.execute(
                        "SELECT conta_id, conversa_id, mensagem_id, alvo "
                        "FROM limpas")}
            return self._limpas

    def foi_limpa(self, conta_id, conversa_id, mensagem_id):
        """'mensagem', 'midia' ou None."""
        return self._mapa_limpas().get((conta_id, conversa_id, mensagem_id))

    def mensagens_para_limpar(self, conta_id="", conversa_id="", tipos=(),
                              antes=None, minimo=0):
        """[(conta_id, conversa_id, id, tipo, tamanho, data)] que passam
        pelos filtros: conta/conversa ('' = todas), tipos (() = todos), mais
        antigas que `antes` (segundos) e maiores que `minimo` bytes."""
        sql = ("SELECT conta_id, conversa_id, id, tipo, tamanho, data "
               "FROM mensagens WHERE 1=1")
        args = []
        if conta_id:
            sql += " AND conta_id=?"
            args.append(conta_id)
        if conversa_id:
            sql += " AND conversa_id=?"
            args.append(conversa_id)
        if tipos:
            sql += " AND tipo IN (%s)" % ", ".join("?" * len(tipos))
            args.extend(tipos)
        if antes is not None:
            sql += " AND data<?"
            args.append(antes)
        if minimo:
            sql += " AND tamanho>?"
            args.append(minimo)
        with self._trava:
            return self._con.execute(sql, args).fetchall()

    def registrar_limpeza(self, chaves, alvo):
        """chaves: [(conta_id, conversa_id, mensagem_id)]. 'mensagem' vale
        mais que 'midia'."""
        with self._trava, self._con:
            self._con.executemany(
                "INSERT OR REPLACE INTO limpas VALUES (?,?,?,?)",
                [(*k, alvo) for k in chaves])
            if self._limpas is not None:
                for k in chaves:
                    self._limpas[tuple(k)] = alvo

    def apagar_mensagens(self, chaves):
        """Tira as mensagens e tudo o que depende delas do banco."""
        chaves = [tuple(k) for k in chaves]
        with self._trava, self._con:
            for tabela, col in (("mensagens", "id"),
                                ("recibos", "mensagem_id"),
                                ("fichas", "mensagem_id"),
                                ("midias", "mensagem_id"),
                                ("depuracao", "mensagem_id"),
                                ("posicoes", "mensagem_id")):
                self._con.executemany(
                    "DELETE FROM %s WHERE conta_id=? AND conversa_id=? AND "
                    "%s=?" % (tabela, col), chaves)

    def apagar_fichas(self, chaves):
        with self._trava, self._con:
            self._con.executemany(
                "DELETE FROM fichas WHERE conta_id=? AND conversa_id=? AND "
                "mensagem_id=?", [tuple(k) for k in chaves])

    def esquecer_limpezas(self, conta_id):
        """Novo pareamento: o que foi limpo ou apagado pode voltar."""
        with self._trava, self._con:
            for tabela in ("limpas", "apagadas"):
                self._con.execute("DELETE FROM %s WHERE conta_id=?" % tabela,
                                  (conta_id,))
            self._limpas = None
            self._apagadas = None

    # ------------------------------------------------ conversas apagadas
    def _mapa_apagadas(self):
        with self._trava:
            if self._apagadas is None:
                self._apagadas = {
                    (c, v): ate for c, v, ate in self._con.execute(
                        "SELECT conta_id, conversa_id, ate FROM apagadas")}
            return self._apagadas

    def apagada_ate(self, conta_id, conversa_id):
        """Data da ultima mensagem da conversa apagada, ou None."""
        return self._mapa_apagadas().get((conta_id, conversa_id))

    def conversa_apagada(self, conv):
        """True se a conversa foi apagada e nao tem mensagem mais nova."""
        ate = self.apagada_ate(conv.conta_id, conv.id)
        return ate is not None and conv.data <= ate

    def apagar_conversa(self, conta_id, conversa_id, data):
        """Tira a conversa e tudo dela do banco e registra que foi apagada
        ate `data` (ou ate a mensagem mais nova que tinha)."""
        with self._trava, self._con:
            linha = self._con.execute(
                "SELECT MAX(data) FROM mensagens WHERE conta_id=? AND "
                "conversa_id=?", (conta_id, conversa_id)).fetchone()
            ate = max(data or 0, (linha[0] if linha else 0) or 0)
            for tabela, col in (("conversas", "id"),
                                ("mensagens", "conversa_id"),
                                ("recibos", "conversa_id"),
                                ("fichas", "conversa_id"),
                                ("midias", "conversa_id"),
                                ("depuracao", "conversa_id"),
                                ("posicoes", "conversa_id"),
                                ("limpas", "conversa_id")):
                self._con.execute(
                    "DELETE FROM %s WHERE conta_id=? AND %s=?" % (tabela, col),
                    (conta_id, conversa_id))
            self._con.execute(
                "INSERT OR REPLACE INTO apagadas VALUES (?,?,?)",
                (conta_id, conversa_id, ate))
            if self._apagadas is not None:
                self._apagadas[(conta_id, conversa_id)] = ate
            if self._limpas is not None:
                for k in [k for k in self._limpas
                          if k[0] == conta_id and k[1] == conversa_id]:
                    del self._limpas[k]
        return ate

    def esquecer_midia(self, conta_id, conversa_id, mensagem_id):
        with self._trava, self._con:
            self._con.execute(
                "DELETE FROM midias WHERE conta_id=? AND conversa_id=? AND "
                "mensagem_id=?", (conta_id, conversa_id, mensagem_id))


def _linha_msg(m):
    t = list(astuple(m))
    t[_CAMPOS_MSG.index("minha")] = 1 if m.minha else 0
    return t


def _msg(linha):
    m = Mensagem(*linha)
    m.minha = bool(m.minha)
    return m

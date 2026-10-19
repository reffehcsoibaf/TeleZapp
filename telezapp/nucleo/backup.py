# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Backup e restauracao: um arquivo .zip, com senha opcional (AES-256, que o
7-Zip tambem abre), com as partes que a pessoa escolher.

Partes: configuracoes (as opcoes da janela de Configuracoes e a pasta de
sons dos avisos), contas (contas,
sessoes e codigo secreto das trancadas: dao acesso as contas), conversas
(banco com mensagens e contatos) e midias (arquivos baixados).

As configuracoes se aplicam na hora. O resto so pode ser trocado com o
programa fechado: a restauracao deixa tudo numa pasta de espera e
`aplicar_pendente` faz a troca na proxima abertura, guardando o que havia em
`antes-da-restauracao`. Sem wxPython.
"""
import json
import logging
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass, field

import pyzipper

from telezapp import VERSAO, config

log = logging.getLogger("telezapp.backup")

PARTES = (
    ("configuracoes", "Configurações do TeleZapp (as opções da janela de "
                      "Configurações)"),
    ("contas", "Contas e sessões, com o código secreto das conversas "
               "trancadas (dão acesso às suas contas)"),
    ("conversas", "Conversas, mensagens e contatos guardados"),
    ("midias", "Mídias baixadas"),
)
NOMES_PARTES = dict(PARTES)

# Opcoes que um arquivo de backup nunca muda sozinho: a exigencia do codigo
# secreto (trocar o arquivo nao pode abrir as conversas trancadas) e o modo
# de depuracao (guarda dados das mensagens)
OPCOES_FORA = {"trancadas_exigir_codigo", "depuracao"}
# O que a parte "contas" leva do config.json
CHAVES_CONTAS = ("contas", "telegram_api_id", "telegram_api_hash",
                 "codigo_trancadas", "trancadas_locais",
                 "trancadas_exigir_codigo")

MANIFESTO = "manifesto.json"
ESPERA = "restauracao"          # dentro da pasta de dados
ANTES = "antes-da-restauracao"


class ErroBackup(Exception):
    """O texto e dito a pessoa."""


@dataclass
class Manifesto:
    versao: str = ""
    data: float = 0.0
    partes: list = field(default_factory=list)
    pasta_midias: str = ""      # onde estavam as midias (os caminhos no banco)


# ------------------------------------------------------------- opcoes
# Preferencias fora de config.OPCOES que tambem vao (a ordem dos provedores
# de IA e os modelos; as chaves nunca)
EXTRAS = ("ia_ordem", "ia_modelos")


def opcoes_do_backup(dados):
    """{chave: valor} das opcoes de config.OPCOES que o backup leva."""
    levadas = {o.chave: dados.get(o.chave, o.padrao) for o in config.OPCOES
               if o.chave not in OPCOES_FORA}
    for chave in EXTRAS:
        levadas[chave] = dados.get(chave, config.PADROES.get(chave, {}))
    return levadas


def opcoes_validas(lidas):
    """So as opcoes conhecidas, com valor do tipo e da faixa certos."""
    boas = {}
    if not isinstance(lidas, dict):
        return boas
    for o in config.OPCOES:
        if o.chave in OPCOES_FORA or o.chave not in lidas:
            continue
        v = lidas[o.chave]
        if o.escolhas:
            if v in [e[0] for e in o.escolhas] and not isinstance(v, bool):
                boas[o.chave] = v
        elif o.numero:
            if isinstance(v, int) and not isinstance(v, bool) and \
                    o.numero[0] <= v <= o.numero[1]:
                boas[o.chave] = v
        elif isinstance(o.padrao, bool):
            if isinstance(v, bool):
                boas[o.chave] = v
        elif isinstance(v, type(o.padrao)) and not isinstance(v, bool):
            boas[o.chave] = v
    from telezapp.nucleo.ia import catalogo
    ordem = lidas.get("ia_ordem")
    if isinstance(ordem, dict):
        boas["ia_ordem"] = {
            t: [p for p in v if p in catalogo.PROVEDORES]
            for t, v in ordem.items()
            if t in catalogo.TAREFAS and isinstance(v, list)}
    modelos = lidas.get("ia_modelos")
    if isinstance(modelos, dict):
        boas["ia_modelos"] = {p: v for p, v in modelos.items()
                              if p in catalogo.PROVEDORES
                              and isinstance(v, str)}
    return boas


# --------------------------------------------------------------- criar
def _copia_consistente(origem, destino):
    """Copia um arquivo SQLite pelo mecanismo de backup dele (seguro mesmo
    com o arquivo em uso); qualquer outro arquivo, copia comum."""
    if origem.lower().endswith((".db", ".session", ".sqlite")):
        try:
            de = sqlite3.connect("file:%s?mode=ro" % origem.replace(
                "\\", "/"), uri=True)
            para = sqlite3.connect(destino)
            try:
                de.backup(para)
            finally:
                para.close()
                de.close()
            return
        except sqlite3.Error:
            log.warning("cópia por SQLite falhou; copiando o arquivo")
    shutil.copyfile(origem, destino)


def criar(destino, pasta_dados, cfg_dados, partes, senha="",
          copiar_banco=None, progresso=None):
    """Grava o backup em `destino`. `cfg_dados`: o dicionario do config.json;
    `copiar_banco(caminho)`: grava uma copia consistente do banco (se for
    None, copia o arquivo). Devolve {parte: quantidade de arquivos}. Em erro
    apaga o arquivo parcial e deixa a excecao subir."""
    partes = [p for p, _ in PARTES if p in partes]
    if not partes:
        raise ErroBackup("Escolha pelo menos uma parte para o backup.")
    temporarios = os.path.join(pasta_dados, "temp", "backup-%d" %
                               int(time.time()))
    os.makedirs(temporarios, exist_ok=True)
    resumo = {}
    try:
        with pyzipper.AESZipFile(destino, "w", compression=pyzipper.ZIP_DEFLATED,
                                 allowZip64=True) as z:
            if senha:
                z.setpassword(senha.encode("utf-8"))
                z.setencryption(pyzipper.WZ_AES, nbits=256)
            midias = os.path.join(pasta_dados, "midias")
            manifesto = Manifesto(VERSAO, time.time(), partes, midias)
            z.writestr(MANIFESTO, json.dumps(manifesto.__dict__,
                                             ensure_ascii=False, indent=1))
            if "configuracoes" in partes:
                z.writestr("configuracoes.json", json.dumps(
                    {"opcoes": opcoes_do_backup(cfg_dados)},
                    ensure_ascii=False, indent=1))
                resumo["configuracoes"] = 1
                sons = os.path.join(pasta_dados, "sons")
                for atual, _, arquivos in os.walk(sons):
                    for a in arquivos:
                        origem = os.path.join(atual, a)
                        z.write(origem, "sons/" + os.path.relpath(
                            origem, sons).replace("\\", "/"),
                            compress_type=pyzipper.ZIP_STORED)
                        resumo["configuracoes"] += 1
            if "contas" in partes:
                z.writestr("contas.json", json.dumps(
                    {c: cfg_dados[c] for c in CHAVES_CONTAS if c in cfg_dados},
                    ensure_ascii=False, indent=1))
                n = 0
                sessoes = os.path.join(pasta_dados, "sessoes")
                for atual, _, arquivos in os.walk(sessoes):
                    for a in arquivos:
                        if a.endswith(("-wal", "-shm", ".tmp")):
                            continue
                        origem = os.path.join(atual, a)
                        copia = os.path.join(temporarios, "s%d" % n)
                        _copia_consistente(origem, copia)
                        z.write(copia, "sessoes/" + os.path.relpath(
                            origem, sessoes).replace("\\", "/"))
                        os.remove(copia)
                        n += 1
                resumo["contas"] = n
            if "conversas" in partes:
                copia = os.path.join(temporarios, "banco.db")
                if copiar_banco is not None:
                    copiar_banco(copia)
                else:
                    _copia_consistente(
                        os.path.join(pasta_dados, "telezapp.db"), copia)
                z.write(copia, "telezapp.db")
                resumo["conversas"] = 1
            if "midias" in partes:
                n = 0
                for atual, _, arquivos in os.walk(midias):
                    for a in arquivos:
                        origem = os.path.join(atual, a)
                        if a.endswith(".parte"):
                            continue
                        z.write(origem, "midias/" + os.path.relpath(
                            origem, midias).replace("\\", "/"),
                            compress_type=pyzipper.ZIP_STORED)
                        n += 1
                        if progresso and n % 50 == 0:
                            progresso(n)
                resumo["midias"] = n
    except BaseException:
        try:
            os.remove(destino)
        except OSError:
            pass
        raise
    finally:
        shutil.rmtree(temporarios, ignore_errors=True)
    return resumo


# ------------------------------------------------------------- restaurar
def precisa_de_senha(arquivo):
    try:
        with pyzipper.AESZipFile(arquivo) as z:
            return any(i.flag_bits & 0x1 for i in z.infolist())
    except (pyzipper.BadZipFile, OSError):
        raise ErroBackup("Este arquivo não é um backup do TeleZapp.")


def _abrir(arquivo, senha):
    try:
        z = pyzipper.AESZipFile(arquivo)
    except (pyzipper.BadZipFile, OSError):
        raise ErroBackup("Este arquivo não é um backup do TeleZapp.")
    if senha:
        z.setpassword(senha.encode("utf-8"))
    return z


def ler_manifesto(arquivo, senha=""):
    """O Manifesto do backup. ErroBackup se o arquivo nao serve ou a senha
    esta errada."""
    z = _abrir(arquivo, senha)
    try:
        try:
            dados = json.loads(z.read(MANIFESTO).decode("utf-8"))
        except KeyError:
            raise ErroBackup("Este arquivo não é um backup do TeleZapp.")
        except RuntimeError:
            raise ErroBackup("Senha errada." if senha else
                             "Este backup tem senha.")
        except ValueError:
            raise ErroBackup("O backup está danificado.")
    finally:
        z.close()
    if not isinstance(dados, dict) or not isinstance(dados.get("partes"),
                                                     list):
        raise ErroBackup("Este arquivo não é um backup do TeleZapp.")
    return Manifesto(str(dados.get("versao", "")),
                     float(dados.get("data") or 0),
                     [p for p in dados["partes"] if p in NOMES_PARTES],
                     str(dados.get("pasta_midias", "")))


def _extrair(z, nome, destino):
    """Extrai um item para `destino`, sem sair da pasta (zip malicioso)."""
    alvo = os.path.normpath(os.path.join(destino, *nome.split("/")))
    if not alvo.startswith(os.path.normpath(destino) + os.sep):
        raise ErroBackup("O backup tem um caminho inválido.")
    os.makedirs(os.path.dirname(alvo), exist_ok=True)
    with z.open(nome) as de, open(alvo, "wb") as para:
        shutil.copyfileobj(de, para, 1 << 20)


def restaurar(arquivo, senha, partes, pasta_dados):
    """Das `partes` escolhidas: devolve as opcoes validas (para aplicar na
    hora, ou {} se "configuracoes" nao foi escolhida) e deixa as demais na
    pasta de espera, para `aplicar_pendente` na proxima abertura. Devolve
    (opcoes, partes_em_espera)."""
    manifesto = ler_manifesto(arquivo, senha)
    escolhidas = [p for p in partes if p in manifesto.partes]
    espera = os.path.join(pasta_dados, ESPERA)
    shutil.rmtree(espera, ignore_errors=True)
    opcoes, em_espera = {}, []
    z = _abrir(arquivo, senha)
    try:
        try:
            if "configuracoes" in escolhidas:
                lidas = json.loads(z.read("configuracoes.json").decode(
                    "utf-8"))
                opcoes = opcoes_validas(lidas.get("opcoes"))
                # os sons escolhidos voltam na hora, para a pasta de sons
                for nome in z.namelist():
                    if nome.startswith("sons/") and not nome.endswith("/"):
                        _extrair(z, nome, pasta_dados)
            prefixos = {"contas": ("contas.json", "sessoes/"),
                        "conversas": ("telezapp.db",),
                        "midias": ("midias/",)}
            for parte in ("contas", "conversas", "midias"):
                if parte not in escolhidas:
                    continue
                for nome in z.namelist():
                    if nome == MANIFESTO or nome.endswith("/"):
                        continue
                    if any(nome == p or (p.endswith("/") and
                                         nome.startswith(p))
                           for p in prefixos[parte]):
                        _extrair(z, nome, espera)
                em_espera.append(parte)
        except RuntimeError:
            shutil.rmtree(espera, ignore_errors=True)
            raise ErroBackup("Senha errada." if senha else
                             "Este backup tem senha.")
        except (KeyError, ValueError, OSError, pyzipper.BadZipFile) as e:
            shutil.rmtree(espera, ignore_errors=True)
            raise ErroBackup("O backup está danificado (%s)." %
                             type(e).__name__)
    finally:
        z.close()
    if em_espera:
        with open(os.path.join(espera, MANIFESTO), "w",
                  encoding="utf-8") as f:
            json.dump({"partes": em_espera,
                       "pasta_midias": manifesto.pasta_midias}, f)
    return opcoes, em_espera


def ha_pendente(pasta_dados):
    return os.path.isfile(os.path.join(pasta_dados, ESPERA, MANIFESTO))


def _mover(origem, destino):
    if os.path.exists(origem):
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        shutil.move(origem, destino)


def aplicar_pendente(pasta_dados):
    """Chamada na abertura, antes de abrir o banco: troca o que estava em
    espera pelos dados do backup, guardando o que havia em
    `antes-da-restauracao\\<data>`. Devolve a lista de partes trocadas."""
    espera = os.path.join(pasta_dados, ESPERA)
    marca = os.path.join(espera, MANIFESTO)
    if not os.path.isfile(marca):
        return []
    with open(marca, encoding="utf-8") as f:
        info = json.load(f)
    partes = info.get("partes", [])
    antes = os.path.join(pasta_dados, ANTES, time.strftime("%Y%m%d-%H%M%S"))
    trocadas = []
    if "contas" in partes:
        _mover(os.path.join(pasta_dados, "sessoes"),
               os.path.join(antes, "sessoes"))
        _mover(os.path.join(espera, "sessoes"),
               os.path.join(pasta_dados, "sessoes"))
        os.makedirs(os.path.join(pasta_dados, "sessoes"), exist_ok=True)
        caminho = os.path.join(pasta_dados, "config.json")
        atual = {}
        if os.path.isfile(caminho):
            os.makedirs(antes, exist_ok=True)
            shutil.copyfile(caminho, os.path.join(antes, "config.json"))
            with open(caminho, encoding="utf-8") as f:
                atual = json.load(f)
        with open(os.path.join(espera, "contas.json"),
                  encoding="utf-8") as f:
            atual.update(json.load(f))
        with open(caminho + ".tmp", "w", encoding="utf-8") as f:
            json.dump(atual, f, ensure_ascii=False, indent=2)
        os.replace(caminho + ".tmp", caminho)
        trocadas.append("contas")
    if "conversas" in partes:
        for sufixo in ("", "-wal", "-shm"):
            _mover(os.path.join(pasta_dados, "telezapp.db" + sufixo),
                   os.path.join(antes, "telezapp.db" + sufixo))
        _mover(os.path.join(espera, "telezapp.db"),
               os.path.join(pasta_dados, "telezapp.db"))
        trocadas.append("conversas")
    if "midias" in partes:
        _mover(os.path.join(pasta_dados, "midias"),
               os.path.join(antes, "midias"))
        _mover(os.path.join(espera, "midias"),
               os.path.join(pasta_dados, "midias"))
        os.makedirs(os.path.join(pasta_dados, "midias"), exist_ok=True)
        trocadas.append("midias")
    if "conversas" in partes or "midias" in partes:
        _acertar_caminhos_das_midias(
            os.path.join(pasta_dados, "telezapp.db"),
            info.get("pasta_midias", ""), os.path.join(pasta_dados, "midias"))
    shutil.rmtree(espera, ignore_errors=True)
    return trocadas


def _acertar_caminhos_das_midias(banco, antigo, novo):
    """O banco guarda o caminho completo de cada midia; se o backup veio de
    outra pasta ou de outro usuario, troca o comeco do caminho."""
    if not antigo or os.path.normpath(antigo) == os.path.normpath(novo) \
            or not os.path.isfile(banco):
        return
    con = sqlite3.connect(banco)
    try:
        con.execute(
            "UPDATE midias SET caminho = ? || substr(caminho, ?) "
            "WHERE substr(caminho, 1, ?) = ?",
            (novo, len(antigo) + 1, len(antigo), antigo))
        con.commit()
    finally:
        con.close()

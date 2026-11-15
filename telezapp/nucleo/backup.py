# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Backup e restauracao: um arquivo .zip, com senha opcional (AES-256, que o
7-Zip tambem abre), com as partes que a pessoa escolher.

Partes: configuracoes (as opcoes da janela de Configuracoes, fora atalhos e
sons), atalhos (os atalhos personalizados), sons (o pacote de sons, os
eventos ligados ou desligados e a pasta de sons), contas (contas,
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
                      "Configurações, fora os atalhos e os sons)"),
    ("atalhos", "Atalhos personalizados (as teclas que você escolheu)"),
    ("sons", "Configurações de sons (o pacote escolhido, os sons ligados e "
             "desligados e os sons que você importou)"),
    ("contas", "Contas e sessões, com o código secreto das conversas "
               "trancadas (dão acesso às suas contas)"),
    ("conversas", "Conversas, mensagens e contatos guardados"),
    ("midias", "Mídias baixadas"),
)
NOMES_PARTES = dict(PARTES)

# As tres partes que moram no configuracoes.json; as demais opcoes, e as que
# nao estao aqui, sao da parte "configuracoes". Nos backups antigos
# (formato 1) tudo isso era uma parte so, "configuracoes"
PARTES_DE_OPCOES = ("configuracoes", "atalhos", "sons")
OPCOES_DE_PARTE = {"atalhos": ("atalhos", "mostrar_atalhos"),
                   "sons": ("pacote_de_sons", "sons_desativados",
                            "sons_de_conversa")}
FORMATO = 2


def parte_da_opcao(chave):
    for parte, chaves in OPCOES_DE_PARTE.items():
        if chave in chaves:
            return parte
    return "configuracoes"


# Opcoes que um arquivo de backup nunca muda sozinho: a exigencia do codigo
# secreto (trocar o arquivo nao pode abrir as conversas trancadas), o modo
# de depuracao (guarda dados das mensagens) e abrir ao entrar no Windows (e
# uma entrada do computador, com o caminho do programa dele)
# A protecao ao entrar tambem: ligar pede um PIN novo, e a marca sem o
# arquivo da trava (seguranca.json, que nunca vai no backup) trancaria a
# pessoa para fora
OPCOES_FORA = {"trancadas_exigir_codigo", "depuracao", "iniciar_com_windows",
               "seguranca_ao_entrar"}
# O que a parte "contas" leva do config.json
CHAVES_CONTAS = ("contas", "telegram_api_id", "telegram_api_hash",
                 "codigo_trancadas", "trancadas_locais",
                 "ia_automatica_conversas",
                 "trancadas_exigir_codigo")

CHAVES_IA = "ia_chaves.json"     # so em backup com senha (zip cifrado)
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
    formato: int = 1            # 2: atalhos e sons sao partes proprias
    pasta_por_conta: bool = False   # uma pasta de dados por conta


# ------------------------------------------------------------- opcoes
# Preferencias fora de config.OPCOES que tambem vao (a ordem dos provedores
# de IA e os modelos; as chaves so em backup com senha, ver CHAVES_IA)
EXTRAS = ("ia_ordem", "ia_modelos", "pacote_de_sons", "sons_desativados",
          "sons_de_conversa",
          "atalhos", "lista_conversas", "lista_mensagens", "aviso_nova",
          "participantes_silenciados")


def opcoes_do_backup(dados, partes=None):
    """{chave: valor} das opcoes de config.OPCOES que o backup leva; `partes`
    (de "configuracoes", "atalhos" e "sons") limita ao que for escolhido."""
    levadas = {o.chave: dados.get(o.chave, o.padrao) for o in config.OPCOES
               if o.chave not in OPCOES_FORA}
    for chave in EXTRAS:
        levadas[chave] = dados.get(chave, config.PADROES.get(chave, {}))
    if partes is not None:
        levadas = {c: v for c, v in levadas.items()
                   if parte_da_opcao(c) in partes}
    return levadas


def atalhos_validos(lidos):
    """O mapa de atalhos personalizados ({funcao: combinacao}, "" = sem
    atalho) com so o que serve: funcao em texto e combinacao que existe e
    pode ser atalho, na forma canonica; duas funcoes com a mesma combinacao
    ficam sem ela (a primeira vale)."""
    from telezapp.nucleo import atalhos as at
    boas, usadas = {}, set()
    for funcao, valor in lidos.items():
        if not isinstance(funcao, str) or not funcao \
                or not isinstance(valor, str):
            continue
        if valor == "":
            boas[funcao] = ""
            continue
        canon = at.normalizar(valor)
        if canon is None or at.problema(canon) or canon in usadas:
            continue
        usadas.add(canon)
        boas[funcao] = canon
    return boas


def opcoes_validas(lidas, partes=None):
    """So as opcoes conhecidas, com valor do tipo e da faixa certos; `partes`
    limita as opcoes `as partes escolhidas."""
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
    pacote = lidas.get("pacote_de_sons")
    if isinstance(pacote, str) and (pacote in ("padrao", "telezapp") or
                                    pacote.startswith("p:")):
        boas["pacote_de_sons"] = pacote
    atalhos = lidas.get("atalhos")
    if isinstance(atalhos, dict):
        boas["atalhos"] = atalhos_validos(atalhos)
    lista = lidas.get("lista_conversas")
    if isinstance(lista, dict):
        from telezapp.nucleo import lista_conversas
        boas["lista_conversas"] = lista_conversas.normalizar(lista)
    lista = lidas.get("lista_mensagens")
    if isinstance(lista, dict):
        from telezapp.nucleo import lista_mensagens
        boas["lista_mensagens"] = lista_mensagens.normalizar(lista)
    elif lidas.get("estilo") in (2, 3):
        # backup antigo: o estilo de "Como cada mensagem e lida" virou a
        # lista de mensagens
        from telezapp.nucleo import lista_mensagens
        boas["lista_mensagens"] = lista_mensagens.do_estilo(lidas["estilo"])
    if lidas.get("digitar_na_lista") == "campo":
        # backup antigo: a opcao unica virou uma escolha em cada lista
        from telezapp.nucleo import lista_conversas, lista_mensagens
        for chave, nucleo in (("lista_conversas", lista_conversas),
                              ("lista_mensagens", lista_mensagens)):
            boas[chave] = nucleo.definir_digitar(boas.get(chave), "campo")
    por_conversa = lidas.get("sons_de_conversa")
    if isinstance(por_conversa, dict):
        boas["sons_de_conversa"] = {
            c: os.path.basename(v) for c, v in por_conversa.items()
            if isinstance(c, str) and isinstance(v, str) and v}
    desativados = lidas.get("sons_desativados")
    if isinstance(desativados, dict):
        boas["sons_desativados"] = {
            p: [e for e in v if isinstance(e, str)]
            for p, v in desativados.items()
            if isinstance(p, str) and isinstance(v, list)}
    if partes is not None:
        boas = {c: v for c, v in boas.items() if parte_da_opcao(c) in partes}
    return boas


# --------------------------------------------------------------- criar
def _chaves_de_ia(pasta_dados):
    """{provedor: chave} lidas do cofre (decifradas pelo DPAPI)."""
    from telezapp.nucleo.ia.cofre import Cofre
    cofre = Cofre(os.path.join(pasta_dados, "ia_chaves.json"))
    return {p: cofre.obter(p) for p in cofre.provedores_com_chave()
            if cofre.obter(p)}


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


def _pasta_da_conta_no_disco(pasta_dados, conta_id):
    """A pasta de dados da conta para o backup: a escolhida nas opcoes
    de Sistema (com a configuracao ativa) ou a padrao na pasta de dados
    passada (que pode ser de teste, e nao a pasta de dados de verdade;
    config.pasta_da_conta consultaria o ambiente real)."""
    escolhida = config.pasta_escolhida_das_contas()
    if escolhida:
        return os.path.join(escolhida, conta_id)
    return os.path.join(pasta_dados, "contas", conta_id)


def _contas_do_backup(pasta_dados):
    """No formato novo (uma pasta de dados por conta): os ids das contas
    com pasta de dados propria (a escolhida ou a padrao). Sem separacao
    (ou sem nenhuma pasta), vazio: o backup sai no formato antigo, tudo
    na raiz da pasta de dados."""
    if not config.contas_separadas():
        return []
    ids = config.ids_das_contas()
    if ids is not None:
        return sorted(i for i in ids
                      if os.path.isdir(config.pasta_da_conta(i)))
    base = os.path.join(pasta_dados, "contas")
    if not os.path.isdir(base):
        return []
    return sorted(n for n in os.listdir(base)
                  if os.path.isdir(os.path.join(base, n)))


def _contar_arquivos(pasta, excluir=()):
    n = 0
    for _, _, arquivos in os.walk(pasta):
        n += sum(1 for a in arquivos if not a.endswith(tuple(excluir)))
    return n


def criar(destino, pasta_dados, cfg_dados, partes, senha="",
          copiar_banco=None, progresso=None, pasta_contas=None):
    """Grava o backup em `destino`. `cfg_dados`: o dicionario do config.json;
    `copiar_banco(caminho, conta_id=None)`: grava uma copia consistente
    do banco da conta (se for None, copia o arquivo). `progresso(pct, texto)`: o avanco, de 0 a 100,
    por arquivo gravado. `pasta_contas`: onde ficam o banco unico, as
    sessoes e as midias do layout antigo, quando a pasta personalizada
    esta marcada (o padrao e a propria `pasta_dados`). Devolve {parte:
    quantidade de arquivos}. Em erro apaga o arquivo parcial e deixa a
    excecao subir."""
    partes = [p for p, _ in PARTES if p in partes]
    if not partes:
        raise ErroBackup("Escolha pelo menos uma parte para o backup.")
    raiz_antiga = pasta_contas or pasta_dados
    temporarios = os.path.join(pasta_dados, "temp", "backup-%d" %
                               int(time.time()))
    os.makedirs(temporarios, exist_ok=True)
    resumo = {}
    total = 1
    grupos = [p for p in PARTES_DE_OPCOES if p in partes]
    if grupos:
        total += 1
    if "sons" in partes:
        total += _contar_arquivos(os.path.join(pasta_dados, "sons"))
    contas_no_disco = _contas_do_backup(pasta_dados)
    if "contas" in partes:
        total += 1
        for sessao in ([os.path.join(_pasta_da_conta_no_disco(
                            pasta_dados, c), "sessoes")
                        for c in contas_no_disco] or
                       [os.path.join(raiz_antiga, "sessoes")]):
            total += _contar_arquivos(sessao, ("-wal", "-shm", ".tmp"))
    if "conversas" in partes:
        total += len(contas_no_disco) or 1
    if "midias" in partes:
        for raiz in ([os.path.join(_pasta_da_conta_no_disco(
                          pasta_dados, c), "midias")
                      for c in contas_no_disco] or
                     [os.path.join(raiz_antiga, "midias")]):
            total += _contar_arquivos(raiz, (".parte",))
    feitos = [0]

    def andou(texto):
        feitos[0] += 1
        if progresso:
            progresso(min(feitos[0] * 100 // total, 99), texto)
    try:
        with pyzipper.AESZipFile(destino, "w", compression=pyzipper.ZIP_DEFLATED,
                                 allowZip64=True) as z:
            if senha:
                z.setpassword(senha.encode("utf-8"))
                z.setencryption(pyzipper.WZ_AES, nbits=256)
            midias = os.path.join(raiz_antiga, "midias")
            manifesto = Manifesto(VERSAO, time.time(), partes,
                                  pasta_dados if contas_no_disco else midias,
                                  FORMATO, bool(contas_no_disco))
            z.writestr(MANIFESTO, json.dumps(manifesto.__dict__,
                                             ensure_ascii=False, indent=1))
            if grupos:
                z.writestr("configuracoes.json", json.dumps(
                    {"opcoes": opcoes_do_backup(cfg_dados, grupos)},
                    ensure_ascii=False, indent=1))
                for parte in grupos:
                    resumo[parte] = 1
                andou("Copiando as configurações")
            if "configuracoes" in partes:
                # as chaves de IA so vao dentro de um zip cifrado: sem senha
                # ficariam legiveis para quem pegasse o arquivo
                chaves = _chaves_de_ia(pasta_dados) if senha else {}
                if chaves:
                    z.writestr(CHAVES_IA, json.dumps(chaves))
                    resumo["ia_chaves"] = len(chaves)
            if "sons" in partes:
                sons = os.path.join(pasta_dados, "sons")
                for atual, _, arquivos in os.walk(sons):
                    for a in arquivos:
                        origem = os.path.join(atual, a)
                        z.write(origem, "sons/" + os.path.relpath(
                            origem, sons).replace("\\", "/"),
                            compress_type=pyzipper.ZIP_STORED)
                        resumo["sons"] += 1
                        andou("Copiando os sons")
            if "contas" in partes:
                z.writestr("contas.json", json.dumps(
                    {c: cfg_dados[c] for c in CHAVES_CONTAS if c in cfg_dados},
                    ensure_ascii=False, indent=1))
                n = 0
                sessoes = [os.path.join(_pasta_da_conta_no_disco(
                              pasta_dados, c), "sessoes")
                           for c in contas_no_disco] or \
                    [os.path.join(raiz_antiga, "sessoes")]
                for sessao in sessoes:
                    for atual, _, arquivos in os.walk(sessao):
                        for a in arquivos:
                            if a.endswith(("-wal", "-shm", ".tmp")):
                                continue
                            origem = os.path.join(atual, a)
                            copia = os.path.join(temporarios, "s%d" % n)
                            _copia_consistente(origem, copia)
                            z.write(copia, "sessoes/" + os.path.relpath(
                                origem, sessao).replace("\\", "/"))
                            os.remove(copia)
                            n += 1
                            andou("Copiando as contas")
                resumo["contas"] = n
            if "conversas" in partes:
                resumo["conversas"] = 0
                if contas_no_disco:
                    # formato novo: um banco por conta, em contas/<id>/
                    for conta_id in contas_no_disco:
                        copia = os.path.join(temporarios,
                                             "banco-%s.db" % conta_id)
                        if copiar_banco is not None:
                            copiar_banco(copia, conta_id)
                        else:
                            _copia_consistente(
                                os.path.join(
                                    _pasta_da_conta_no_disco(pasta_dados,
                                                             conta_id),
                                    "conversas.db"), copia)
                        z.write(copia, "contas/%s/conversas.db" % conta_id)
                        os.remove(copia)
                        resumo["conversas"] += 1
                        andou("Copiando as conversas")
                else:
                    copia = os.path.join(temporarios, "banco.db")
                    if copiar_banco is not None:
                        try:
                            copiar_banco(copia)
                        except ValueError:
                            _copia_consistente(
                                os.path.join(raiz_antiga, "telezapp.db"),
                                copia)
                    else:
                        _copia_consistente(
                            os.path.join(raiz_antiga, "telezapp.db"), copia)
                    z.write(copia, "telezapp.db")
                    resumo["conversas"] = 1
                    andou("Copiando as conversas")
            if "midias" in partes:
                n = 0
                raizes = [(c, os.path.join(_pasta_da_conta_no_disco(
                                pasta_dados, c), "midias"))
                          for c in contas_no_disco] or [("", midias)]
                for conta_id, raiz in raizes:
                    no_zip = "midias/" + (conta_id + "/" if conta_id else "")
                    for atual, _, arquivos in os.walk(raiz):
                        for a in arquivos:
                            origem = os.path.join(atual, a)
                            if a.endswith(".parte"):
                                continue
                            z.write(origem, no_zip + os.path.relpath(
                                origem, raiz).replace("\\", "/"),
                                compress_type=pyzipper.ZIP_STORED)
                            n += 1
                            andou("Copiando as mídias")
                resumo["midias"] = n
    except BaseException:
        try:
            os.remove(destino)
        except OSError:
            pass
        raise
    finally:
        shutil.rmtree(temporarios, ignore_errors=True)
    if progresso:
        progresso(100, "Backup pronto")
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
                     str(dados.get("pasta_midias", "")),
                     int(dados.get("formato") or 1),
                     bool(dados.get("pasta_por_conta")))


def _extrair(z, nome, destino):
    """Extrai um item para `destino`, sem sair da pasta (zip malicioso)."""
    alvo = os.path.normpath(os.path.join(destino, *nome.split("/")))
    if not alvo.startswith(os.path.normpath(destino) + os.sep):
        raise ErroBackup("O backup tem um caminho inválido.")
    os.makedirs(os.path.dirname(alvo), exist_ok=True)
    with z.open(nome) as de, open(alvo, "wb") as para:
        shutil.copyfileobj(de, para, 1 << 20)


def _restaurar_chaves(z, pasta_dados):
    """Guarda no cofre (cifradas de novo pelo DPAPI deste usuario) as chaves
    de IA do backup. Devolve quantas."""
    from telezapp.nucleo.ia import catalogo
    from telezapp.nucleo.ia.cofre import Cofre
    try:
        lidas = json.loads(z.read(CHAVES_IA).decode("utf-8"))
    except KeyError:
        return 0
    if not isinstance(lidas, dict):
        return 0
    os.makedirs(pasta_dados, exist_ok=True)
    cofre = Cofre(os.path.join(pasta_dados, "ia_chaves.json"))
    n = 0
    for provedor, chave in lidas.items():
        if provedor in catalogo.PROVEDORES and isinstance(chave, str) \
                and chave.strip():
            cofre.guardar(provedor, chave)
            n += 1
    return n


def restaurar(arquivo, senha, partes, pasta_dados, resultado=None,
              progresso=None):
    """Das `partes` escolhidas: devolve as opcoes validas (para aplicar na
    hora, ou {} se "configuracoes" nao foi escolhida) e deixa as demais na
    pasta de espera, para `aplicar_pendente` na proxima abertura. Devolve
    (opcoes, partes_em_espera). `resultado`, se dado, recebe
    {"ia_chaves": quantas chaves de IA voltaram}. `progresso(pct, texto)`:
    o avanco da leitura do backup, de 0 a 100."""
    manifesto = ler_manifesto(arquivo, senha)
    escolhidas = [p for p in partes if p in manifesto.partes]
    espera = os.path.join(pasta_dados, ESPERA)
    shutil.rmtree(espera, ignore_errors=True)
    opcoes, em_espera = {}, []
    z = _abrir(arquivo, senha)
    try:
        try:
            grupos = [p for p in PARTES_DE_OPCOES if p in escolhidas]
            if "configuracoes" in grupos and manifesto.formato < 2:
                # backup antigo: configuracoes, atalhos e sons eram uma so
                grupos = list(PARTES_DE_OPCOES)
            if grupos:
                lidas = json.loads(z.read("configuracoes.json").decode(
                    "utf-8"))
                opcoes = opcoes_validas(lidas.get("opcoes"), grupos)
                if senha and "configuracoes" in grupos:
                    voltaram = _restaurar_chaves(z, pasta_dados)
                    if resultado is not None:
                        resultado["ia_chaves"] = voltaram
            if "sons" in grupos:
                # os sons escolhidos voltam na hora, para a pasta de sons
                for nome in z.namelist():
                    if nome.startswith("sons/") and not nome.endswith("/"):
                        _extrair(z, nome, pasta_dados)
            prefixos = {"contas": ("contas.json", "sessoes/"),
                        "conversas": ("telezapp.db", "contas/"),
                        "midias": ("midias/",)}
            def a_extrair(parte):
                return [nome for nome in z.namelist()
                        if nome != MANIFESTO and not nome.endswith("/") and
                        any(nome == p or (p.endswith("/") and
                                          nome.startswith(p))
                            for p in prefixos[parte])]
            planos = [(parte, a_extrair(parte))
                      for parte in ("contas", "conversas", "midias")
                      if parte in escolhidas]
            total = max(sum(len(n) for _, n in planos), 1)
            feitos = 0
            for parte, nomes in planos:
                for nome in nomes:
                    _extrair(z, nome, espera)
                    feitos += 1
                    if progresso:
                        progresso(min(feitos * 100 // total, 99),
                                  "Lendo o backup")
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
                       "pasta_midias": manifesto.pasta_midias,
                       "pasta_por_conta": manifesto.pasta_por_conta}, f)
    return opcoes, em_espera


AVISO_CONVERSAS_SEM_CONTAS = (
    "As conversas só aparecem junto da conta a que pertencem. Sem as contas e "
    "sessões, elas ficam guardadas, mas não aparecem em outra instalação nem "
    "depois de parear a conta de novo.")


def _contas_do_banco(caminho):
    """Os ids de conta com conversas num banco (vazio se nao abrir)."""
    con = None
    try:
        con = sqlite3.connect("file:%s?mode=ro" % caminho.replace("\\", "/"),
                              uri=True)
        return {c for c, in con.execute(
            "SELECT DISTINCT conta_id FROM conversas")}
    except sqlite3.Error:
        return set()
    finally:
        if con is not None:
            con.close()


def conversas_sem_conta(pasta_dados, contas):
    """True se os bancos em espera tem conversas de contas fora de `contas`
    (ids): depois de trocar, a lista nao as mostraria."""
    espera = os.path.join(pasta_dados, ESPERA)
    do_backup = _contas_do_banco(os.path.join(espera, "telezapp.db"))
    base = os.path.join(espera, "contas")
    if os.path.isdir(base):
        for conta_id in os.listdir(base):
            do_backup |= _contas_do_banco(
                os.path.join(base, conta_id, "conversas.db"))
    return bool(do_backup - set(contas))


def ha_pendente(pasta_dados):
    return os.path.isfile(os.path.join(pasta_dados, ESPERA, MANIFESTO))


def _mover(origem, destino):
    if os.path.exists(origem):
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        shutil.move(origem, destino)


def _pasta_da_conta_no_backup(dados, pasta_dados, conta_id):
    """A pasta de dados da conta em um momento: a escolhida no registro
    dela, ou a padrao `<pasta_dados>\\contas\\<conta_id>`."""
    escolhida = ((dados or {}).get("pasta") or "").strip()
    return escolhida or os.path.join(pasta_dados, "contas", conta_id)


def aplicar_pendente(pasta_dados, pasta_contas=None):
    """Chamada na abertura, antes de abrir o banco: troca o que estava em
    espera pelos dados do backup, guardando o que havia em
    `antes-da-restauracao\\<data>`. Devolve a lista de partes trocadas.

    No formato novo (uma pasta de dados por conta), cada conta recebe os
    dados dela na pasta que o registro dela diz; no legado, os dados sao
    trocados na raiz do layout antigo (`pasta_contas`, quando a pasta
    personalizada esta marcada; o padrao e a propria `pasta_dados`), e a
    migracao os distribui depois."""
    raiz_antiga = pasta_contas or pasta_dados
    espera = os.path.join(pasta_dados, ESPERA)
    marca = os.path.join(espera, MANIFESTO)
    if not os.path.isfile(marca):
        return []
    with open(marca, encoding="utf-8") as f:
        info = json.load(f)
    partes = info.get("partes", [])
    antes = os.path.join(pasta_dados, ANTES, time.strftime("%Y%m%d-%H%M%S"))
    trocadas = []

    def anotar(parte):
        if parte not in trocadas:
            trocadas.append(parte)

    if "contas" in partes:
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

    novo = bool(info.get("pasta_por_conta")) or \
        os.path.isdir(os.path.join(espera, "contas"))
    if not novo:
        if "contas" in partes:
            _mover(os.path.join(raiz_antiga, "sessoes"),
                   os.path.join(antes, "sessoes"))
            _mover(os.path.join(espera, "sessoes"),
                   os.path.join(raiz_antiga, "sessoes"))
            os.makedirs(os.path.join(raiz_antiga, "sessoes"), exist_ok=True)
            anotar("contas")
        if "conversas" in partes:
            for sufixo in ("", "-wal", "-shm"):
                _mover(os.path.join(raiz_antiga, "telezapp.db" + sufixo),
                       os.path.join(antes, "telezapp.db" + sufixo))
            _mover(os.path.join(espera, "telezapp.db"),
                   os.path.join(raiz_antiga, "telezapp.db"))
            anotar("conversas")
        if "midias" in partes:
            _mover(os.path.join(raiz_antiga, "midias"),
                   os.path.join(antes, "midias"))
            _mover(os.path.join(espera, "midias"),
                   os.path.join(raiz_antiga, "midias"))
            os.makedirs(os.path.join(raiz_antiga, "midias"), exist_ok=True)
            anotar("midias")
        if "conversas" in partes or "midias" in partes:
            _acertar_caminhos_das_midias(
                os.path.join(raiz_antiga, "telezapp.db"),
                info.get("pasta_midias", ""),
                os.path.join(raiz_antiga, "midias"))
    else:
        # cada conta recebe o que e dela: o banco (e as sessoes e as
        # midias), na pasta que o registro dela diz
        registros = {}
        base = os.path.join(espera, "contas")
        if os.path.isdir(base):
            for conta_id in os.listdir(base):
                if os.path.isdir(os.path.join(base, conta_id)):
                    registros[conta_id] = {}
        try:
            with open(os.path.join(espera, "contas.json"),
                      encoding="utf-8") as f:
                for dados in json.load(f).get("contas") or []:
                    if dados.get("id"):
                        registros.setdefault(dados["id"], {}).update(dados)
        except (OSError, ValueError):
            pass
        if "midias" in partes:
            raiz = os.path.join(espera, "midias")
            if os.path.isdir(raiz):
                for conta_id in os.listdir(raiz):
                    if os.path.isdir(os.path.join(raiz, conta_id)):
                        registros.setdefault(conta_id, {})
        cfg_atual = {}
        try:
            with open(os.path.join(pasta_dados, "config.json"),
                      encoding="utf-8") as f:
                cfg_atual = json.load(f)
        except (OSError, ValueError):
            pass
        for dados_lidos in cfg_atual.get("contas") or []:
            conta_id = dados_lidos.get("id")
            if conta_id in registros and \
                    not registros[conta_id].get("pasta"):
                registros[conta_id]["pasta"] = \
                    (dados_lidos.get("pasta") or "").strip()
        for conta_id, dados in registros.items():
            pasta = _pasta_da_conta_no_backup(dados, pasta_dados, conta_id)
            movidas = []
            if os.path.isdir(os.path.join(espera, "contas", conta_id)):
                os.makedirs(antes, exist_ok=True)
                _mover(pasta, os.path.join(antes, "contas", conta_id))
                _mover(os.path.join(espera, "contas", conta_id), pasta)
                movidas.append("conversas")
            # as sessoes vao juntas no zip, com o nome dizendo a conta
            sessoes = os.path.join(espera, "sessoes")
            if os.path.isdir(sessoes):
                for nome in os.listdir(sessoes):
                    if nome.startswith(conta_id + "."):
                        os.makedirs(os.path.join(pasta, "sessoes"),
                                    exist_ok=True)
                        _mover(os.path.join(sessoes, nome),
                               os.path.join(pasta, "sessoes", nome))
                        movidas.append("contas")
            if "midias" in partes and \
                    os.path.isdir(os.path.join(espera, "midias", conta_id)):
                os.makedirs(antes, exist_ok=True)
                _mover(os.path.join(pasta, "midias"),
                       os.path.join(antes, "contas", conta_id, "midias"))
                _mover(os.path.join(espera, "midias", conta_id),
                       os.path.join(pasta, "midias"))
                movidas.append("midias")
            if movidas:
                for parte in movidas:
                    anotar(parte)
                # os caminhos das midias no banco: de onde o backup era
                # para onde a conta esta agora
                _acertar_caminhos_das_midias(
                    os.path.join(pasta, "conversas.db"),
                    _pasta_da_conta_no_backup(
                        dados, info.get("pasta_midias", ""), conta_id),
                    pasta)
    shutil.rmtree(espera, ignore_errors=True)
    return trocadas


# A troca de caminhos logo depois de o banco ser copiado pode falhar por
# alguns segundos: o antivirus leva um tempo com o arquivo que acabou de
# aparecer. Sao 20 tentativas de meio segundo (10 s) antes de desistir.
ACERTO_TENTATIVAS = 20
ACERTO_ESPERA = 0.5


def _acertar_caminhos_das_midias(banco, antigo, novo, con=None):
    """O banco guarda o caminho completo de cada midia; se o backup veio de
    outra pasta ou de outro usuario, troca o comeco do caminho. Com `con`,
    a troca roda nessa conexao ja aberta (a do banco unico durante a
    migracao): abrir o arquivo de novo pode falhar por um instante, logo
    depois de o banco ter sido criado (ex.: o antivirus olhando o arquivo
    que a copia acabou de gravar)."""
    if not antigo or os.path.normpath(antigo) == os.path.normpath(novo) \
            or (con is None and not os.path.isfile(banco)):
        return

    def trocar(c):
        c.execute(
            "UPDATE midias SET caminho = ? || substr(caminho, ?) "
            "WHERE substr(caminho, 1, ?) = ?",
            (novo, len(antigo) + 1, len(antigo), antigo))
        c.commit()
    for tentativa in range(ACERTO_TENTATIVAS):  # abrir/gravar pode falhar
        try:                        # por um instante (o antivirus olhando
                                    # o arquivo recem-gravado, por exemplo)
            c = con if con is not None else sqlite3.connect(banco)
            try:
                trocar(c)
            finally:
                if con is None:
                    c.close()
            return
        except sqlite3.OperationalError as erro:
            if tentativa == ACERTO_TENTATIVAS - 1:
                raise
            log.info("não consegui trocar os caminhos em %s (%r); "
                     "tentando de novo", os.path.basename(banco), erro)
            time.sleep(ACERTO_ESPERA)

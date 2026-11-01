# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Esta copia e a que foi publicada? Cada Release traz a lista dos arquivos do
programa com o SHA-256 de cada um; aqui ela e comparada com o que esta rodando.

Protege quem recebeu uma copia alterada sem saber, e faz copias alteradas nao
buscarem atualizacoes. Nao e uma trava: quem altera o programa tambem pode tirar
esta conferencia, e um conteiner pode rodar outro codigo em volta de arquivos
intactos. Sem dependencia de wxPython."""
import hashlib
import logging
import os
import re
import sys
import urllib.error
import urllib.request

from telezapp import SITE, VERSAO
from telezapp.nucleo import instalacao
from telezapp.nucleo.atualizacao import abrir_url

log = logging.getLogger("telezapp.copia_oficial")

ARQUIVO_DA_LISTA = "TeleZapp.conferencia.txt"
NOME_DO_INSTALADOR = "instalador/TeleZapp.exe"
# arquivo a mais com uma destas extensoes roda junto com o programa
EXTENSOES_DE_CODIGO = (".exe", ".dll", ".pyd", ".py", ".pyc", ".pyz", ".bat",
                       ".cmd", ".ps1", ".vbs")

OFICIAL, MODIFICADA, NAO_PUBLICADA = "oficial", "modificada", "nao_publicada"
SEM_CONFERIR, CODIGO_FONTE = "sem_conferir", "codigo_fonte"

ENDERECO_OFICIAL = "reffehcsoibaf.github.io/TeleZapp"
AVISO_CANAIS = (
    "Os canais oficiais do TeleZapp são a página do projeto (%s) e as "
    "atualizações feitas pelo próprio programa. Cópias obtidas fora deles não "
    "são de responsabilidade de Fábio Scheffer Moraes." % ENDERECO_OFICIAL)
TEXTOS_DO_ESTADO = {
    OFICIAL: "Os arquivos do programa conferem com a versão publicada. Se "
             "você recebeu o TeleZapp de outra pessoa, confira também o "
             "instalador na página do projeto.",
    MODIFICADA: "Atenção: esta cópia é diferente da versão publicada. Ela "
                "pode ter sido alterada.",
    NAO_PUBLICADA: "Atenção: esta versão não está entre as publicadas.",
    SEM_CONFERIR: "Não consegui conferir esta cópia agora. Confira a conexão "
                  "com a internet.",
    CODIGO_FONTE: "Esta cópia roda pelo código-fonte, então não há o que "
                  "conferir.",
}


def nao_oficial(estado):
    """A conferencia achou uma copia que nao e a publicada?"""
    return estado in (MODIFICADA, NAO_PUBLICADA)


def sem_atualizacoes(estado):
    """Esta copia nao busca atualizacoes: quem alterou ou roda pelo codigo
    cuida das proprias versoes."""
    return nao_oficial(estado) or estado == CODIGO_FONTE


def texto_do_alerta(estado):
    return ("%s\n\nEsta cópia não recebe atualizações. Para ter a versão "
            "oficial, baixe de %s.\n\n%s" % (
                TEXTOS_DO_ESTADO[estado], ENDERECO_OFICIAL, AVISO_CANAIS))


def hash_do_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _arquivos_do_programa(pasta):
    """Os caminhos relativos (com /) dos arquivos da pasta, sem a de dados."""
    for atual, pastas, arquivos in os.walk(pasta):
        if os.path.samefile(atual, pasta) and \
                instalacao.PASTA_DADOS_PORTATIL in pastas:
            pastas.remove(instalacao.PASTA_DADOS_PORTATIL)
        for a in arquivos:
            yield os.path.relpath(os.path.join(atual, a),
                                  pasta).replace(os.sep, "/")


def gerar_lista(pasta, instalador=None):
    """O texto de ARQUIVO_DA_LISTA, para o empacotador."""
    linhas = ["%s *%s" % (hash_do_arquivo(os.path.join(pasta, r)), r)
              for r in sorted(_arquivos_do_programa(pasta))]
    if instalador:
        linhas.append("%s *%s" % (hash_do_arquivo(instalador),
                                  NOME_DO_INSTALADOR))
    return "\n".join(linhas) + "\n"


def ler_lista(texto):
    """{caminho: hash}; ValueError se o texto nao for uma lista."""
    lista = {}
    for linha in texto.splitlines():
        achou = re.fullmatch(r"([0-9a-f]{64}) \*(.+)", linha.strip())
        if achou:
            lista[achou.group(2)] = achou.group(1)
    if not lista:
        raise ValueError("lista de conferência vazia")
    return lista


def diferencas(pasta, lista):
    """Os arquivos que faltam, mudaram ou sobram (so os que rodariam codigo)."""
    achadas = []
    esperados = {r: h for r, h in lista.items() if r != NOME_DO_INSTALADOR}
    for r, h in esperados.items():
        caminho = os.path.join(pasta, r)
        if not os.path.isfile(caminho) or hash_do_arquivo(caminho) != h:
            achadas.append(r)
    for r in _arquivos_do_programa(pasta):
        if r not in esperados and \
                os.path.splitext(r)[1].lower() in EXTENSOES_DE_CODIGO:
            achadas.append(r)
    return achadas


def baixar_lista(versao=VERSAO, abrir=abrir_url):
    """A lista publicada com a versao; None se a versao nao foi publicada.
    Outras falhas sobem (e a copia fica sem conferir)."""
    url = "%s/releases/download/%s/%s" % (SITE, versao, ARQUIVO_DA_LISTA)
    pedido = urllib.request.Request(url, headers={
        "User-Agent": "TeleZapp/" + VERSAO})
    try:
        with abrir(pedido, 15) as r:
            return ler_lista(r.read(1 << 20).decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def _conferir(comparar, baixar):
    try:
        lista = baixar()
    except (OSError, ValueError) as e:      # URLError e HTTPError sao OSError
        log.info("cópia sem conferir: %s", type(e).__name__)
        return SEM_CONFERIR
    if lista is None:
        log.warning("cópia de uma versão não publicada: %s", VERSAO)
        return NAO_PUBLICADA
    try:
        achadas = comparar(lista)
    except OSError as e:
        log.warning("cópia sem conferir: %s", type(e).__name__)
        return SEM_CONFERIR
    if achadas:
        log.warning("cópia diferente da publicada: %d arquivos, entre eles %s",
                    len(achadas), ", ".join(sorted(achadas)[:5]))
        return MODIFICADA
    log.info("cópia conferida com a versão publicada")
    return OFICIAL


def conferir_programa(pasta=None, baixar=baixar_lista):
    """O estado da copia em uso (demora: le todos os arquivos)."""
    if not getattr(sys, "frozen", False) and pasta is None:
        return CODIGO_FONTE
    pasta = pasta or instalacao.pasta_do_programa()
    return _conferir(lambda lista: diferencas(pasta, lista), baixar)


def conferir_instalador(caminho=None, baixar=baixar_lista):
    """O mesmo, para o instalador de um arquivo que esta rodando."""
    if not getattr(sys, "frozen", False) and caminho is None:
        return CODIGO_FONTE
    caminho = caminho or sys.executable

    def comparar(lista):
        h = lista.get(NOME_DO_INSTALADOR)
        return [] if h == hash_do_arquivo(caminho) else [NOME_DO_INSTALADOR]
    return _conferir(comparar, baixar)

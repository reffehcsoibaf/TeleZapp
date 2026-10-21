# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Atualizar o TeleZapp pelo proprio programa: baixa o zip da Release, confere
o SHA-256, extrai ao lado da pasta do programa e, depois que o programa
fecha, um script troca a pasta e abre a versao nova. A pasta `dados`, a marca
de instalado e a da tela de boas-vindas passam para a pasta nova. Sem
wxPython."""
import hashlib
import logging
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
import zipfile

from telezapp import NOME, VERSAO

log = logging.getLogger("telezapp.atualizador")

EXE = "TeleZapp.exe"
MANTER = ("dados", "instalado.txt", "sem-boas-vindas.txt")
HOSTS = ("github.com", "api.github.com")


class ErroAtualizacao(Exception):
    """O texto e dito a pessoa."""


def pasta_de_espera(programa):
    return programa.rstrip("\\/") + ".atualizacao"


def pasta_antiga(programa):
    return programa.rstrip("\\/") + ".antiga"


def limpar_restos(programa):
    """Na abertura: tira as pastas que uma atualizacao anterior deixou."""
    for p in (pasta_de_espera(programa), pasta_antiga(programa)):
        shutil.rmtree(p, ignore_errors=True)


def _url_ok(url):
    p = urllib.parse.urlparse(url)
    return p.scheme == "https" and (p.hostname or "") in HOSTS


def _abrir(url, tempo=30):
    return urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent": "TeleZapp/" + VERSAO}), timeout=tempo)


def _hash_esperado(lanc, abrir):
    with abrir(lanc.url_hash) as r:
        texto = r.read(4096).decode("utf-8", "replace")
    achou = re.match(r"\s*([0-9a-fA-F]{64})\b", texto)
    if not achou:
        raise ErroAtualizacao("O arquivo de conferência da versão %s não "
                              "está no formato esperado." % lanc.versao)
    return achou.group(1).lower()


def baixar(lanc, pasta, progresso=None, abrir=_abrir, cancelado=None):
    """Baixa o zip da Release para `pasta` e confere o SHA-256. Devolve o
    caminho do zip. `progresso(feito, total)`; `cancelado()` devolve True
    quando a pessoa desistiu (o arquivo parcial e apagado)."""
    if not (lanc.url_zip and lanc.url_hash and lanc.nome_zip):
        raise ErroAtualizacao("Esta versão não tem o arquivo para "
                              "atualização automática.")
    if not (_url_ok(lanc.url_zip) and _url_ok(lanc.url_hash)):
        raise ErroAtualizacao("O endereço do download não é do GitHub.")
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, os.path.basename(lanc.nome_zip))
    try:
        esperado = _hash_esperado(lanc, abrir)
        h = hashlib.sha256()
        feito = 0
        with abrir(lanc.url_zip) as r, open(destino, "wb") as f:
            total = int(r.headers.get("Content-Length") or lanc.tamanho or 0)
            for bloco in iter(lambda: r.read(1 << 20), b""):
                if cancelado is not None and cancelado():
                    raise ErroAtualizacao("Atualização cancelada.")
                f.write(bloco)
                h.update(bloco)
                feito += len(bloco)
                if progresso:
                    progresso(feito, total)
    except ErroAtualizacao:
        try:
            os.remove(destino)
        except OSError:
            pass
        raise
    except OSError as e:
        raise ErroAtualizacao("Não consegui baixar a atualização (%s). "
                              "Tente de novo." % e)
    if h.hexdigest() != esperado:
        os.remove(destino)
        raise ErroAtualizacao("O arquivo baixado não confere com o "
                              "SHA-256 publicado, então não foi usado.")
    return destino


def extrair(arquivo_zip, pasta, progresso=None):
    """Extrai o zip em `pasta` e devolve a pasta TeleZapp de dentro dela.
    `progresso(feito, total)`: quantos itens ja foram extraidos."""
    shutil.rmtree(pasta, ignore_errors=True)
    os.makedirs(pasta)
    raiz = os.path.realpath(pasta)
    try:
        with zipfile.ZipFile(arquivo_zip) as z:
            nomes = z.namelist()
            if "TeleZapp/" + EXE not in nomes:
                raise ErroAtualizacao("O arquivo da atualização não tem o "
                                      "%s." % EXE)
            for n in nomes:
                alvo = os.path.realpath(os.path.join(pasta, n))
                if alvo != raiz and not alvo.startswith(raiz + os.sep):
                    raise ErroAtualizacao("O arquivo da atualização tem "
                                          "caminhos inválidos.")
            for i, n in enumerate(nomes, 1):
                z.extract(n, pasta)
                if progresso:
                    progresso(i, len(nomes))
    except zipfile.BadZipFile:
        raise ErroAtualizacao("O arquivo da atualização está corrompido.")
    return os.path.join(pasta, "TeleZapp")


def _bat(texto):
    return texto.replace("%", "%%")


MODELO = r"""@echo off
chcp 65001 >nul
set "P=@P@"
set "N=@N@"
set "A=@A@"
set /a t=0
:esperar
if exist "%A%" rmdir /s /q "%A%" 2>nul
move "%P%" "%A%" >nul 2>&1
if not errorlevel 1 goto trocar
set /a t+=1
if %t% geq 90 goto abrir
ping -n 2 127.0.0.1 >nul
goto esperar
:trocar
move "%N%" "%P%" >nul 2>&1
if errorlevel 1 goto desfazer
for %%K in (@MANTER@) do if exist "%A%\%%K" move "%A%\%%K" "%P%\" >nul
goto abrir
:desfazer
move "%A%" "%P%" >nul 2>&1
:abrir
start "" "%P%\@EXE@"
exit
"""


def montar_script(programa, nova, executavel=EXE):
    """O texto do script que troca a pasta depois que o programa fecha."""
    texto = MODELO
    for chave, valor in (("@P@", _bat(programa)), ("@N@", _bat(nova)),
                         ("@A@", _bat(pasta_antiga(programa))),
                         ("@MANTER@", " ".join(MANTER)),
                         ("@EXE@", executavel)):
        texto = texto.replace(chave, valor)
    return "\r\n".join(texto.splitlines()) + "\r\n"


def aplicar(programa, nova, executavel=EXE):
    """Escreve o script ao lado da pasta nova e o inicia separado. O chamador
    fecha o programa em seguida."""
    script = os.path.join(os.path.dirname(nova), "atualizar.bat")
    with open(script, "w", encoding="utf-8", newline="") as f:
        f.write(montar_script(programa, nova, executavel))
    subprocess.Popen(
        ["cmd", "/c", script], cwd=os.path.dirname(programa),
        creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0) |
                       getattr(subprocess, "DETACHED_PROCESS", 0)))
    log.info("atualização preparada: %s", nova)
    return script

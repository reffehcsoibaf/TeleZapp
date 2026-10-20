# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Instalar o TeleZapp a partir de uma copia portatil e criar copias portateis
a partir de uma instalacao (como o NVDA). Sem wxPython.

Tres modos, so no executavel (PyInstaller):
  instalado  a pasta do programa e %LOCALAPPDATA%\\Programs\\TeleZapp, sem
             precisar de administrador; os dados ficam em %APPDATA%\\TeleZapp;
  portatil   qualquer outra pasta. Se existir a pasta `dados` ao lado do
             executavel, os dados ficam nela (leva tudo num pendrive); sem
             ela, ficam em %APPDATA%\\TeleZapp como sempre;
  desenvolvimento  rodando pelo Python: nada disso se aplica.

Instalar copia a pasta do programa, cria os atalhos e a entrada em
"Aplicativos instalados" (HKCU), que chama `TeleZapp.exe --desinstalar`.
"""
import logging
import os
import shutil
import subprocess
import sys
import time

from telezapp import NOME, VERSAO, config

log = logging.getLogger("telezapp.instalacao")

EXE = "TeleZapp.exe"
PASTA_DADOS_PORTATIL = "dados"
CHAVE_DESINSTALAR = (r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
                     r"\TeleZapp")
# O que nao vai quando os dados sao levados de um lugar para outro
NAO_LEVAR = {"logs", "temp", "restauracao", "antes-da-restauracao",
             "antes-da-instalacao"}


class ErroInstalacao(Exception):
    """O texto e dito a pessoa."""


# ------------------------------------------------------------------- modo
def pasta_do_programa():
    """A pasta do executavel; None se rodando pelo Python."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return None


def pasta_de_instalacao_padrao():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Programs", NOME)


def _igual(a, b):
    return os.path.normcase(os.path.abspath(a)) == \
        os.path.normcase(os.path.abspath(b))


def modo(programa=None):
    programa = programa or pasta_do_programa()
    if not programa:
        return "desenvolvimento"
    if os.path.isfile(os.path.join(programa, "instalado.txt")):
        return "instalado"
    return "portatil"


def dados_portateis(programa=None):
    """A pasta `dados` ao lado do executavel, se existir (senao None)."""
    programa = programa or pasta_do_programa()
    if not programa:
        return None
    p = os.path.join(programa, PASTA_DADOS_PORTATIL)
    return p if os.path.isdir(p) else None


def dados_do_computador():
    """%APPDATA%\\TeleZapp, onde a versao instalada guarda os dados."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, NOME)


# ------------------------------------------------------------------ copiar
def _copiar_programa(origem, destino):
    """Copia a pasta do programa, sem a pasta `dados` nem a marca de
    instalado."""
    def ignorar(pasta, nomes):
        if _igual(pasta, origem):
            return [n for n in nomes
                    if n in (PASTA_DADOS_PORTATIL, "instalado.txt")]
        return []
    shutil.copytree(origem, destino, ignore=ignorar)


def _copiar_dados(origem, destino, progresso=None):
    """Copia os dados de um lugar para o outro (bancos pelo mecanismo do
    SQLite, que e seguro com o app aberto) e acerta os caminhos das
    midias no banco novo."""
    from telezapp.nucleo import backup as bk
    os.makedirs(destino, exist_ok=True)
    for raiz, pastas, arquivos in os.walk(origem):
        rel = os.path.relpath(raiz, origem)
        if rel == ".":
            pastas[:] = [p for p in pastas if p not in NAO_LEVAR]
        alvo = destino if rel == "." else os.path.join(destino, rel)
        os.makedirs(alvo, exist_ok=True)
        for nome in arquivos:
            if nome.endswith(("-wal", "-shm", ".tmp", ".lock")):
                continue
            de = os.path.join(raiz, nome)
            para = os.path.join(alvo, nome)
            try:
                bk._copia_consistente(de, para)
            except OSError:
                log.warning("não copiei %s", nome)
            if progresso:
                progresso()
    bk._acertar_caminhos_das_midias(
        os.path.join(destino, "telezapp.db"),
        os.path.join(origem, "midias"), os.path.join(destino, "midias"))


def _guardar_pasta(caminho, sufixo):
    """Tira uma pasta do caminho (renomeando) para dar lugar a outra."""
    novo = "%s.%s" % (caminho, sufixo)
    n = 1
    while os.path.exists(novo):
        n += 1
        novo = "%s.%s%d" % (caminho, sufixo, n)
    os.rename(caminho, novo)
    return novo


# ------------------------------------------------------------------ atalhos
def _atalho(caminho_lnk, alvo, pasta_de_trabalho):
    """Cria um .lnk pelo WScript.Shell (PowerShell, sem janela)."""
    os.makedirs(os.path.dirname(caminho_lnk), exist_ok=True)
    script = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut("
              "$env:TZ_LNK);$s.TargetPath=$env:TZ_ALVO;"
              "$s.WorkingDirectory=$env:TZ_PASTA;$s.Save()")
    env = dict(os.environ, TZ_LNK=caminho_lnk, TZ_ALVO=alvo,
               TZ_PASTA=pasta_de_trabalho)
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        env=env, capture_output=True, timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0 or not os.path.isfile(caminho_lnk):
        raise ErroInstalacao("Não consegui criar o atalho %s." %
                             os.path.basename(caminho_lnk))


def _caminhos_dos_atalhos():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    menu = os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                        "Programs", NOME + ".lnk")
    area = os.path.join(os.environ.get("USERPROFILE") or
                        os.path.expanduser("~"), "Desktop", NOME + ".lnk")
    return menu, area


def _registrar(destino):
    import winreg
    exe = os.path.join(destino, EXE)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, CHAVE_DESINSTALAR, 0,
                            winreg.KEY_SET_VALUE) as k:
        for nome, valor in (
                ("DisplayName", NOME),
                ("DisplayVersion", VERSAO),
                ("Publisher", "Contribuidores do TeleZapp"),
                ("InstallLocation", destino),
                ("DisplayIcon", exe),
                ("UninstallString", '"%s" --desinstalar' % exe)):
            winreg.SetValueEx(k, nome, 0, winreg.REG_SZ, valor)
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)


def _desregistrar():
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, CHAVE_DESINSTALAR)
    except FileNotFoundError:
        pass


# ----------------------------------------------------------------- instalar
def instalar(programa, destino=None, atalho_menu=True, atalho_area=False,
             levar_dados_de=None, fazer_atalho=_atalho,
             registrar=_registrar, progresso=None):
    """Instala a copia que esta em `programa` em `destino` (padrao:
    %LOCALAPPDATA%\\Programs\\TeleZapp). `levar_dados_de`: pasta de dados
    portatil cujo conteudo vai para %APPDATA%\\TeleZapp (o que ja havia la
    fica em `antes-da-instalacao`). Devolve o caminho do executavel novo."""
    destino = os.path.abspath(destino or pasta_de_instalacao_padrao())
    if not os.path.isfile(os.path.join(programa, EXE)):
        raise ErroInstalacao("Não achei o %s em %s." % (EXE, programa))
    if _igual(programa, destino):
        raise ErroInstalacao("Esta cópia já está nessa pasta.")
    if _igual(programa, os.path.dirname(destino)) or \
            os.path.normcase(destino).startswith(
                os.path.normcase(os.path.abspath(programa)) + os.sep):
        raise ErroInstalacao("Escolha uma pasta fora da pasta do programa.")
    nova = destino + ".nova"
    antiga = None
    try:
        if os.path.exists(nova):
            shutil.rmtree(nova)
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        if progresso:
            progresso("Copiando o programa")
        _copiar_programa(programa, nova)
        with open(os.path.join(nova, "instalado.txt"), "w",
                  encoding="utf-8") as f:
            f.write("Esta pasta é uma instalação do TeleZapp %s.\n" % VERSAO)
        if os.path.exists(destino):
            try:
                antiga = _guardar_pasta(destino, "antiga")
            except OSError:
                raise ErroInstalacao(
                    "Não consegui trocar a instalação que já existe em %s. "
                    "Feche o TeleZapp instalado e tente de novo." % destino)
        os.rename(nova, destino)
    except BaseException:
        shutil.rmtree(nova, ignore_errors=True)
        if antiga and not os.path.exists(destino):
            os.rename(antiga, destino)
            antiga = None
        raise
    if antiga:
        shutil.rmtree(antiga, ignore_errors=True)
    exe = os.path.join(destino, EXE)
    if levar_dados_de:
        if progresso:
            progresso("Levando os dados")
        alvo = dados_do_computador()
        if os.path.isdir(alvo):
            guardada = _guardar_pasta(alvo, "antes-da-instalacao-%s" %
                                      time.strftime("%Y%m%d-%H%M%S"))
            log.info("dados anteriores guardados em %s", guardada)
        _copiar_dados(levar_dados_de, alvo)
    menu, area = _caminhos_dos_atalhos()
    avisos = []
    for quer, lnk in ((atalho_menu, menu), (atalho_area, area)):
        if quer:
            try:
                fazer_atalho(lnk, exe, destino)
            except Exception as e:
                log.warning("atalho %s: %s", lnk, e)
                avisos.append(str(e))
    try:
        registrar(destino)
    except Exception as e:
        log.warning("registro de desinstalação: %s", e)
        avisos.append("Não consegui criar a entrada em Aplicativos "
                      "instalados.")
    return exe, avisos


# ------------------------------------------------------------ criar portatil
def criar_portatil(programa, pasta_destino, levar_dados_de=None,
                   progresso=None):
    """Cria `pasta_destino\\TeleZapp` com o programa e a pasta `dados` (vazia
    ou com os dados de `levar_dados_de`). Devolve o caminho da pasta."""
    if not os.path.isfile(os.path.join(programa, EXE)):
        raise ErroInstalacao("Não achei o %s em %s." % (EXE, programa))
    alvo = os.path.join(os.path.abspath(pasta_destino), NOME)
    if os.path.exists(alvo) and os.listdir(alvo):
        raise ErroInstalacao(
            "A pasta %s já existe e não está vazia. Escolha outro lugar ou "
            "apague essa pasta." % alvo)
    if os.path.normcase(alvo).startswith(
            os.path.normcase(os.path.abspath(programa)) + os.sep):
        raise ErroInstalacao("Escolha um lugar fora da pasta do programa.")
    try:
        if os.path.isdir(alvo):
            os.rmdir(alvo)
        if progresso:
            progresso("Copiando o programa")
        _copiar_programa(programa, alvo)
        dados = os.path.join(alvo, PASTA_DADOS_PORTATIL)
        os.makedirs(dados)
        if levar_dados_de:
            if progresso:
                progresso("Copiando os dados")
            _copiar_dados(levar_dados_de, dados)
    except BaseException:
        shutil.rmtree(alvo, ignore_errors=True)
        raise
    return alvo


# --------------------------------------------------------------- desinstalar
def desinstalar(programa=None, apagar_dados=False, dados=None):
    """Tira os atalhos e o registro e, se pedido, apaga os dados. A pasta do
    programa (o executavel esta em uso) e apagada por um processo separado
    logo depois que este terminar."""
    programa = programa or pasta_do_programa()
    if not programa or modo(programa) != "instalado":
        raise ErroInstalacao("Isto não é uma instalação do %s." % NOME)
    for lnk in _caminhos_dos_atalhos():
        try:
            os.remove(lnk)
        except OSError:
            pass
    try:
        _desregistrar()
    except Exception:
        log.warning("não consegui tirar a entrada de Aplicativos instalados")
    if apagar_dados:
        shutil.rmtree(dados or dados_do_computador(), ignore_errors=True)
    subprocess.Popen(
        'timeout /t 4 /nobreak >nul & rmdir /s /q "%s"' % programa,
        shell=True, creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0)
                                   | getattr(subprocess, "DETACHED_PROCESS",
                                             0)))

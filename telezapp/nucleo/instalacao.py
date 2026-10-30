# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
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
import contextlib
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
             "antes-da-instalacao", "webview", "logs-exportados"}   # o cifrado so vale neste PC


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
def faixa(progresso, inicio, fim):
    """Um `progresso(pct, texto)` que leva o avanco de 0 a 100 de uma etapa
    para a faixa [inicio, fim] do avanco total."""
    if progresso is None:
        return None

    def mapeado(pct, texto=""):
        total = None if pct is None else inicio + pct * (fim - inicio) / 100
        progresso(total, texto)
    return mapeado


def _copiar_programa(origem, destino, passo=None):
    """Copia a pasta do programa, sem a pasta `dados` nem a marca de
    instalado. `passo(feito, total)`: bytes ja copiados."""
    ignorados = (PASTA_DADOS_PORTATIL, "instalado.txt")
    arquivos, total = [], 0
    for raiz, pastas, nomes in os.walk(origem):
        if _igual(raiz, origem):
            pastas[:] = [p for p in pastas if p not in ignorados]
            nomes = [n for n in nomes if n not in ignorados]
        rel = os.path.relpath(raiz, origem)
        alvo = destino if rel == "." else os.path.join(destino, rel)
        arquivos.append((alvo, None))
        for n in nomes:
            de = os.path.join(raiz, n)
            tam = os.path.getsize(de)
            arquivos.append((os.path.join(alvo, n), de))
            total += tam
    feito = 0
    for alvo, de in arquivos:
        if de is None:
            os.makedirs(alvo, exist_ok=True)
            continue
        shutil.copy2(de, alvo)
        feito += os.path.getsize(de)
        if passo:
            passo(feito, max(total, 1))


def _copiar_dados(origem, destino, progresso=None):
    """Copia os dados de um lugar para o outro (bancos pelo mecanismo do
    SQLite, que e seguro com o app aberto) e acerta os caminhos das
    midias no banco novo."""
    from telezapp.nucleo import backup as bk
    os.makedirs(destino, exist_ok=True)
    lista = []
    for raiz, pastas, arquivos in os.walk(origem):
        rel = os.path.relpath(raiz, origem)
        if rel == ".":
            pastas[:] = [p for p in pastas if p not in NAO_LEVAR]
        alvo = destino if rel == "." else os.path.join(destino, rel)
        lista.append((alvo, None, None))
        for nome in arquivos:
            if not nome.endswith(("-wal", "-shm", ".tmp", ".lock")):
                lista.append((alvo, os.path.join(raiz, nome), nome))
    n = sum(1 for _, de, _n in lista if de)
    feitos = 0
    for alvo, de, nome in lista:
        os.makedirs(alvo, exist_ok=True)
        if de is None:
            continue
        try:
            bk._copia_consistente(de, os.path.join(alvo, nome))
        except OSError:
            log.warning("não copiei %s", nome)
        feitos += 1
        if progresso:
            progresso(feitos, max(n, 1))
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


FOLDERID_DESKTOP = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"
FOLDERID_PROGRAMS = "{A77F5D77-2E2B-44C3-A6A2-ABA601054A51}"


def _pasta_conhecida(guid):
    """Pasta especial do Windows (a area de trabalho pode estar no OneDrive
    ou em outro lugar, entao nao da para montar o caminho na mao). None se o
    Windows nao responder."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD),
                        ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]
        import uuid
        u = uuid.UUID(guid)
        g = GUID(u.time_low, u.time_mid, u.time_hi_version,
                 (ctypes.c_ubyte * 8)(*u.bytes[8:]))
        saida = ctypes.c_wchar_p()
        r = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(g), 0, None, ctypes.byref(saida))
        if r != 0 or not saida.value:
            return None
        caminho = saida.value
        ctypes.windll.ole32.CoTaskMemFree(saida)
        return caminho
    except Exception:
        log.warning("não consegui perguntar ao Windows a pasta %s", guid)
        return None


def _caminhos_dos_atalhos():
    """(atalho do menu Iniciar, atalho da area de trabalho)."""
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    programas = _pasta_conhecida(FOLDERID_PROGRAMS) or os.path.join(
        appdata, "Microsoft", "Windows", "Start Menu", "Programs")
    area = _pasta_conhecida(FOLDERID_DESKTOP) or os.path.join(
        os.environ.get("USERPROFILE") or os.path.expanduser("~"), "Desktop")
    return (os.path.join(programas, NOME + ".lnk"),
            os.path.join(area, NOME + ".lnk"))


def _registrar(destino):
    import winreg
    exe = os.path.join(destino, EXE)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, CHAVE_DESINSTALAR, 0,
                            winreg.KEY_SET_VALUE) as k:
        for nome, valor in (
                ("DisplayName", NOME),
                ("DisplayVersion", VERSAO),
                ("Publisher", "Fábio Scheffer Moraes"),
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


# ------------------------------------------------- pacote do instalador
@contextlib.contextmanager
def extrair_pacote(arquivo_zip, progresso=None):
    """Para o instalador de um arquivo so: extrai o zip do programa numa
    pasta de trabalho, entrega a pasta TeleZapp de dentro e a apaga depois.
    `progresso(pct, texto)`: o avanco da extracao, de 0 a 100."""
    from telezapp.nucleo import atualizador
    base = os.path.join(os.environ.get("LOCALAPPDATA") or
                        os.path.expanduser("~"), "TeleZapp-instalador")
    pasta = os.path.join(base, str(os.getpid()))
    try:
        try:
            yield atualizador.extrair(arquivo_zip, pasta, (
                lambda f, t: progresso(f * 100 / max(t, 1),
                                       "Extraindo o programa"))
                if progresso else None)
        except atualizador.ErroAtualizacao as e:
            raise ErroInstalacao(str(e))
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
        try:
            os.rmdir(base)
        except OSError:
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
        levando = bool(levar_dados_de)
        etapa = faixa(progresso, 0, 60 if levando else 90)
        if progresso:
            progresso(0, "Copiando o programa")
        _copiar_programa(programa, nova, (lambda f, t: etapa(
            f * 100 / t, "Copiando o programa")) if etapa else None)
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
            progresso(60, "Levando os dados")
        alvo = dados_do_computador()
        if os.path.isdir(alvo):
            guardada = _guardar_pasta(alvo, "antes-da-instalacao-%s" %
                                      time.strftime("%Y%m%d-%H%M%S"))
            log.info("dados anteriores guardados em %s", guardada)
        etapa_dados = faixa(progresso, 60, 95)
        _copiar_dados(levar_dados_de, alvo, (lambda f, t: etapa_dados(
            f * 100 / t, "Levando os dados")) if etapa_dados else None)
    if progresso:
        progresso(95, "Criando os atalhos")
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
    if progresso:
        progresso(100, "Instalado")
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
        etapa = faixa(progresso, 0, 50 if levar_dados_de else 100)
        if progresso:
            progresso(0, "Copiando o programa")
        _copiar_programa(programa, alvo, (lambda f, t: etapa(
            f * 100 / t, "Copiando o programa")) if etapa else None)
        dados = os.path.join(alvo, PASTA_DADOS_PORTATIL)
        os.makedirs(dados)
        if levar_dados_de:
            etapa_dados = faixa(progresso, 50, 100)
            if progresso:
                progresso(50, "Copiando os dados")
            _copiar_dados(levar_dados_de, dados, (
                lambda f, t: etapa_dados(f * 100 / t, "Copiando os dados"))
                if etapa_dados else None)
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
    from telezapp.nucleo import protocolos
    if not protocolos.remover():
        log.warning("não consegui tirar o registro dos links")
    if apagar_dados:
        shutil.rmtree(dados or dados_do_computador(), ignore_errors=True)
    # `timeout` volta na hora sem console; `ping` espera de verdade. Tenta ate
    # o programa soltar a pasta (ele ainda esta fechando).
    subprocess.Popen(
        'for /l %%i in (1,1,30) do (ping -n 2 127.0.0.1 >nul & '
        'rmdir /s /q "%s" 2>nul & if not exist "%s" exit)' % (
            programa, programa),
        # sem DETACHED_PROCESS: com ele o laco `for` do cmd nao roda
        shell=True, creationflags=(
            getattr(subprocess, "CREATE_NO_WINDOW", 0) |
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)))

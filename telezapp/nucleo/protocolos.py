# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""O TeleZapp como uma das opções para abrir links tg:// e whatsapp://.

So em HKCU, sem administrador. Declara as "capacidades" do programa, que o
fazem aparecer em Aplicativos padrao e na pergunta do Windows. O dono atual do
protocolo nao e trocado: a chave `tg` ou `whatsapp` so e criada se nao existir,
e quem escolhe qual programa abre e a pessoa.
"""
import os
import subprocess
import sys

from telezapp import NOME
from telezapp.nucleo import instalacao

ARGUMENTO = "--link"
PROTOCOLOS = {"tg": "Telegram", "whatsapp": "WhatsApp"}
CHAVE_APP = r"Software\TeleZapp"
CHAVE_CAPACIDADES = CHAVE_APP + r"\Capabilities"
CHAVE_REGISTRADOS = r"Software\RegisteredApplications"
CLASSES = r"Software\Classes"


def comando():
    """A linha que o Windows executa, com %1 no lugar do link."""
    programa = instalacao.pasta_do_programa()
    if programa:
        return '"%s" %s "%%1"' % (os.path.join(programa, instalacao.EXE),
                                  ARGUMENTO)
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    python = os.path.join(raiz, "venv", "Scripts", "pythonw.exe")
    return '"%s" "%s" %s "%%1"' % (
        python, os.path.join(raiz, "abrir-link.pyw"), ARGUMENTO)


def _winreg():
    if sys.platform != "win32":
        return None
    import winreg
    return winreg


def _gravar(reg, chave, valores):
    with reg.CreateKeyEx(reg.HKEY_CURRENT_USER, chave, 0,
                         reg.KEY_SET_VALUE) as k:
        for nome, valor in valores.items():
            reg.SetValueEx(k, nome, 0, reg.REG_SZ, valor)


def _existe(reg, protocolo):
    """Ja ha quem abra este protocolo (na maquina ou neste usuario)?"""
    try:
        reg.OpenKey(reg.HKEY_CLASSES_ROOT, protocolo).Close()
        return True
    except OSError:
        return False


def _classe(protocolo):
    return "TeleZapp.Url." + protocolo


def _gravar_abertura(reg, chave, descricao, linha, icone):
    _gravar(reg, chave, {"": descricao})
    _gravar(reg, chave + r"\DefaultIcon", {"": icone})
    _gravar(reg, chave + r"\shell\open\command", {"": linha})


def registrar(linha=None, base=CHAVE_APP, reg=None):
    """Declara o TeleZapp como opção. False se o Windows recusou. `base` e so
    para testes (as demais chaves ficam embaixo dela)."""
    reg = reg or _winreg()
    if reg is None:
        return False
    linha = linha or comando()
    teste = base != CHAVE_APP
    classes = base + r"\Classes" if teste else CLASSES
    capacidades = base + r"\Capabilities"
    registrados = base + r"\Registrados" if teste else CHAVE_REGISTRADOS
    icone = linha.split('"')[1] + ",0"
    try:
        _gravar(reg, capacidades, {
            "ApplicationName": NOME,
            "ApplicationDescription": "Mensagens do WhatsApp e do Telegram, "
            "feito para leitores de tela."})
        _gravar(reg, capacidades + r"\URLAssociations", {
            p: _classe(p) for p in PROTOCOLOS})
        for protocolo, servico in PROTOCOLOS.items():
            _gravar_abertura(reg, classes + "\\" + _classe(protocolo),
                             "Link do %s no %s" % (servico, NOME), linha, icone)
            if not _existe(reg, protocolo):
                chave = classes + "\\" + protocolo
                _gravar_abertura(reg, chave, "URL:%s" % servico, linha, icone)
                _gravar(reg, chave, {"URL Protocol": ""})
        _gravar(reg, registrados, {NOME: capacidades})
        return True
    except OSError:
        return False


def _apagar_arvore(reg, chave):
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, chave, 0,
                         reg.KEY_READ) as k:
            filhas = []
            i = 0
            while True:
                try:
                    filhas.append(reg.EnumKey(k, i))
                    i += 1
                except OSError:
                    break
        for filha in filhas:
            _apagar_arvore(reg, chave + "\\" + filha)
        reg.DeleteKey(reg.HKEY_CURRENT_USER, chave)
    except FileNotFoundError:
        pass


def _e_nosso(reg, chave):
    """A chave `tg` ou `whatsapp` deste usuario abre o TeleZapp?"""
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER,
                         chave + r"\shell\open\command") as k:
            return ARGUMENTO in reg.QueryValueEx(k, "")[0]
    except OSError:
        return False


def remover(base=CHAVE_APP, reg=None):
    """Tira tudo o que `registrar` criou; nao mexe no que e de outro programa."""
    reg = reg or _winreg()
    if reg is None:
        return False
    teste = base != CHAVE_APP
    classes = base + r"\Classes" if teste else CLASSES
    registrados = base + r"\Registrados" if teste else CHAVE_REGISTRADOS
    try:
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, registrados, 0,
                             reg.KEY_SET_VALUE) as k:
                reg.DeleteValue(k, NOME)
        except FileNotFoundError:
            pass
        for protocolo in PROTOCOLOS:
            _apagar_arvore(reg, classes + "\\" + _classe(protocolo))
            if _e_nosso(reg, classes + "\\" + protocolo):
                _apagar_arvore(reg, classes + "\\" + protocolo)
        _apagar_arvore(reg, base)
        return True
    except OSError:
        return False

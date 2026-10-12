# -*- coding: utf-8 -*-
"""Login do Telegram sem usar o terminal (mesmo fluxo do teste anterior).

Reaproveita a sessao salva em sessao-telegram\\teste e o arquivo
configuracao-telegram.txt. Se faltar algo, abre o Bloco de Notas.
"""
import os
import time

from acessivel import pedir_por_arquivo

BASE = os.path.dirname(os.path.abspath(__file__))
SESSAO_DIR = os.path.join(BASE, "sessao-telegram")
ARQ_CONF = os.path.join(BASE, "configuracao-telegram.txt")
ARQ_CODIGO = os.path.join(BASE, "codigo-telegram.txt")
ARQ_SENHA = os.path.join(BASE, "senha-telegram.txt")

MODELO_CONF = (
    "# Preencha depois do sinal de igual, salve com Control S e feche.\n"
    "# API_ID e API_HASH: crie em my.telegram.org, em API development tools.\n"
    "# TELEFONE: com sinal de mais e codigo do pais, exemplo +5511999999999\n"
    "API_ID=\n"
    "API_HASH=\n"
    "TELEFONE=\n")
MODELO_CODIGO = (
    "# Digite o codigo que o Telegram enviou, depois do sinal de igual.\n"
    "# Salve com Control S. O codigo chega no app do Telegram do celular.\n"
    "CODIGO=\n")
MODELO_SENHA = (
    "# Digite a senha de duas etapas do Telegram depois do sinal de igual.\n"
    "# Salve com Control S. O arquivo e apagado logo depois do uso.\n"
    "SENHA=\n")


def conf_valida(d):
    return (d.get("API_ID", "").isdigit()
            and len(d.get("API_HASH", "")) >= 16
            and d.get("TELEFONE", "").startswith("+")
            and d.get("TELEFONE", "")[1:].isdigit())


def _apagar(caminho):
    try:
        os.remove(caminho)
    except OSError:
        pass


async def conectar(log):
    """Devolve um TelegramClient conectado e autorizado, ou None."""
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError

    conf = pedir_por_arquivo(
        ARQ_CONF, MODELO_CONF, conf_valida,
        "Vou abrir o Bloco de Notas com um arquivo de configuração. "
        "Preencha o api id, o api hash e o telefone depois dos sinais de "
        "igual, salve com Control S e pode deixar o Bloco de Notas aberto. "
        "Aperte Enter para fechar este aviso.")
    if conf is None:
        log("ERRO: a configuracao nao foi preenchida a tempo")
        return None
    os.makedirs(SESSAO_DIR, exist_ok=True)
    client = TelegramClient(os.path.join(SESSAO_DIR, "teste"),
                            int(conf["API_ID"]), conf["API_HASH"])
    t = time.perf_counter()
    await client.connect()
    log("conectou aos servidores em %.2fs" % (time.perf_counter() - t))

    if await client.is_user_authorized():
        log("sessao salva reutilizada: sem novo login")
        return client

    log("sessao nova: login necessario")
    await client.send_code_request(conf["TELEFONE"])
    _apagar(ARQ_CODIGO)
    dados = pedir_por_arquivo(
        ARQ_CODIGO, MODELO_CODIGO,
        lambda d: d.get("CODIGO", "").isdigit()
        and len(d.get("CODIGO", "")) >= 4,
        "O Telegram enviou um código para o seu aplicativo no celular. "
        "Vou abrir o Bloco de Notas: digite o código depois do sinal de "
        "igual e salve com Control S. Aperte Enter para fechar este aviso.",
        timeout=300)
    if dados is None:
        log("ERRO: o codigo nao foi informado a tempo")
        _apagar(ARQ_CODIGO)
        await client.disconnect()
        return None
    codigo = dados["CODIGO"]
    _apagar(ARQ_CODIGO)
    try:
        await client.sign_in(conf["TELEFONE"], codigo)
    except SessionPasswordNeededError:
        log("a conta tem senha de duas etapas")
        _apagar(ARQ_SENHA)
        dados = pedir_por_arquivo(
            ARQ_SENHA, MODELO_SENHA,
            lambda d: len(d.get("SENHA", "")) >= 1,
            "Sua conta tem senha de duas etapas. Vou abrir o Bloco de "
            "Notas: digite a senha depois do sinal de igual e salve com "
            "Control S. Aperte Enter para fechar este aviso.", timeout=300)
        if dados is None:
            log("ERRO: a senha nao foi informada a tempo")
            _apagar(ARQ_SENHA)
            await client.disconnect()
            return None
        senha = dados["SENHA"]
        _apagar(ARQ_SENHA)
        await client.sign_in(password=senha)
    log("login concluido")
    return client

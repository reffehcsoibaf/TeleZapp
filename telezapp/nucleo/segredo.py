# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Guardar segredos (chaves de IA, o segredo do PIN) no Mac.

No Windows isso e o DPAPI (ver seguranca.py e ia/cofre.py). No Mac, uma chave
mestra aleatoria fica no Chaveiro (Keychain) do usuario e cifra os dados com
AES-GCM: so a mesma conta do Mac consegue ler. Se o Chaveiro nao estiver
disponivel (sessao sem interface, por exemplo), a chave mestra vai para um
arquivo so do usuario (permissao 600) na pasta de dados: protege menos, mas o
programa continua funcionando, e o log diz que foi isso que aconteceu.

Formato do bloco: b"TZ1" + nonce (12) + etiqueta (16) + dados cifrados.
"""
import base64
import logging
import os
import secrets

log = logging.getLogger("telezapp.segredo")

SERVICO = "TeleZapp"
USUARIO = "chave-mestra"
CABECALHO = b"TZ1"
ARQUIVO_DA_CHAVE = "chave-local"

_chave = None


def _arquivo_da_chave():
    from telezapp import config
    return os.path.join(config.pasta(), ARQUIVO_DA_CHAVE)


def _do_chaveiro():
    """A chave mestra do Chaveiro, criando se nao existir. None se falhar."""
    try:
        import keyring
        guardada = keyring.get_password(SERVICO, USUARIO)
        if guardada:
            return base64.b64decode(guardada)
        nova = secrets.token_bytes(32)
        keyring.set_password(SERVICO, USUARIO,
                             base64.b64encode(nova).decode("ascii"))
        # confere que ficou mesmo guardada, antes de cifrar com ela
        if keyring.get_password(SERVICO, USUARIO) != \
                base64.b64encode(nova).decode("ascii"):
            return None
        return nova
    except Exception as e:
        log.info("Chaveiro indisponível: %r", e)
        return None


def _do_arquivo():
    caminho = _arquivo_da_chave()
    try:
        with open(caminho, "rb") as f:
            lida = f.read()
        if len(lida) == 32:
            return lida
    except OSError:
        pass
    nova = secrets.token_bytes(32)
    try:
        descritor = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                            0o600)
        with os.fdopen(descritor, "wb") as f:
            f.write(nova)
    except OSError as e:
        log.warning("não consegui guardar a chave local: %r", e)
        return None
    log.warning("os segredos estão protegidos por um arquivo (o Chaveiro do "
                "Mac não estava disponível)")
    return nova


def chave_mestra():
    """Os 32 bytes da chave mestra, ou None se nao deu para obter."""
    global _chave
    if _chave is None:
        _chave = _do_chaveiro() or _do_arquivo()
    return _chave


def esquecer_chave_em_memoria():
    """Para os testes: faz a proxima chamada buscar a chave de novo."""
    global _chave
    _chave = None


def cifrar(dados):
    """Bloco cifrado, ou None se nao ha chave."""
    chave = chave_mestra()
    if chave is None:
        return None
    from Cryptodome.Cipher import AES
    cifra = AES.new(chave, AES.MODE_GCM)
    texto, etiqueta = cifra.encrypt_and_digest(dados)
    return CABECALHO + cifra.nonce + etiqueta + texto


def decifrar(bloco):
    """Os dados originais, ou None se o bloco nao e nosso ou nao confere."""
    if not bloco or not bloco.startswith(CABECALHO) or len(bloco) < 31:
        return None
    chave = chave_mestra()
    if chave is None:
        return None
    try:
        from Cryptodome.Cipher import AES
        nonce = bloco[3:15]
        etiqueta = bloco[15:31]
        cifra = AES.new(chave, AES.MODE_GCM, nonce=nonce)
        return cifra.decrypt_and_verify(bloco[31:], etiqueta)
    except Exception:
        log.warning("não consegui decifrar um segredo")
        return None

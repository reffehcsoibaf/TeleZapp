# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Seguranca ao entrar: pedir autenticacao ao abrir o TeleZapp. Sem wx.

Neste computador vale o Windows Hello (biometria ou o PIN do Windows), se
estiver disponivel; senao, ou se a pessoa preferir, o PIN do TeleZapp. Em
outro computador (a pasta copiada ou levada num pendrive) o Windows Hello de
la nao prova nada, entao vale so o PIN do TeleZapp.

O que fica guardado, em `seguranca.json` na pasta de dados:
  pin      sal e resumo PBKDF2 do PIN (o PIN em si nunca e gravado);
  maquina  um segredo deste computador e desta conta do Windows, cifrado
           pelo proprio Windows (DPAPI): so abre aqui, e e ele que diz se o
           Windows Hello pode ser usado.
A marca `seguranca_ao_entrar` do config.json repete que a trava esta ligada:
sem o arquivo, com a marca ligada, o TeleZapp nao abre (alguem apagou).

Limite (documentado): sem cifrar os dados, quem tem acesso aos arquivos e
sabe o que faz consegue desligar a trava editando os dois. Ela protege
contra o uso do programa por outra pessoa, nao contra a leitura dos arquivos.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time

log = logging.getLogger("telezapp.seguranca")

ARQUIVO = "seguranca.json"
ITERACOES = 200_000
PIN_MINIMO = 4
TENTATIVAS_ANTES_DE_ESPERAR = 5
ESPERA_S = 30

# resultado da verificacao do Windows Hello
HELLO_OK = "ok"
HELLO_CANCELADO = "cancelado"
HELLO_INDISPONIVEL = "indisponivel"


class ErroSeguranca(Exception):
    """O texto e dito a pessoa."""


# ------------------------------------------------------------------ PIN
def _resumo(pin, sal, iteracoes=ITERACOES):
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), sal, iteracoes)


def pin_valido(pin):
    """'' se o PIN serve; senao, o motivo."""
    pin = pin or ""
    if len(pin) < PIN_MINIMO:
        return "O PIN precisa ter pelo menos %d caracteres." % PIN_MINIMO
    return ""


# ---------------------------------------------------------------- DPAPI
def _blob(dados):
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(dados, len(dados))
    return DATA_BLOB(len(dados), ctypes.cast(buf, ctypes.POINTER(
        ctypes.c_char))), buf, DATA_BLOB


def _dpapi(dados, cifrar):
    """CryptProtectData / CryptUnprotectData da conta atual do Windows.
    None se falhar (outro computador, outra conta, ou fora do Windows)."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        entrada, _guarda, DATA_BLOB = _blob(dados)
        saida = DATA_BLOB()
        f = ctypes.windll.crypt32.CryptProtectData if cifrar else \
            ctypes.windll.crypt32.CryptUnprotectData
        ok = f(ctypes.byref(entrada), None, None, None, None, 0x1,
               ctypes.byref(saida))           # 0x1: sem interface
        if not ok:
            return None
        try:
            return ctypes.string_at(saida.pbData, saida.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(saida.pbData)
    except Exception:
        log.warning("DPAPI falhou")
        return None


# -------------------------------------------------------------- arquivo
class Trava:
    """A trava de uma pasta de dados."""

    def __init__(self, pasta, dpapi=_dpapi):
        self.caminho = os.path.join(pasta, ARQUIVO)
        self._dpapi = dpapi
        self.dados = self._ler()
        self._erros = 0
        self._esperar_ate = 0.0

    def _ler(self):
        try:
            with open(self.caminho, encoding="utf-8") as f:
                dados = json.load(f)
            return dados if isinstance(dados, dict) else {}
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            log.warning("seguranca.json ilegível")
            return {"ilegivel": True}

    def _gravar(self):
        tmp = self.caminho + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.dados, f)
        os.replace(tmp, self.caminho)

    # ------------------------------------------------------------ estado
    @property
    def ligada(self):
        return bool(self.dados.get("pin"))

    def adulterada(self, marca_no_config):
        """A configuracao diz que a trava esta ligada, mas o arquivo sumiu
        ou foi estragado: nao abrir."""
        return bool(marca_no_config) and (not self.ligada or
                                         self.dados.get("ilegivel"))

    def deste_computador(self):
        """True se a trava foi ligada (ou o PIN foi confirmado) neste
        computador e nesta conta do Windows."""
        maquina = self.dados.get("maquina")
        if not maquina:
            return False
        try:
            segredo = self._dpapi(base64.b64decode(maquina["blob"]), False)
        except Exception:
            return False
        if not segredo:
            return False
        return hmac.compare_digest(
            hashlib.sha256(segredo).hexdigest(), maquina.get("resumo", ""))

    def usar_hello(self):
        return bool(self.dados.get("hello", True))

    # ----------------------------------------------------------- mudancas
    def ligar(self, pin, usar_hello=True):
        motivo = pin_valido(pin)
        if motivo:
            raise ErroSeguranca(motivo)
        sal = secrets.token_bytes(16)
        self.dados = {"versao": 1, "hello": bool(usar_hello), "pin": {
            "sal": base64.b64encode(sal).decode(),
            "iteracoes": ITERACOES,
            "resumo": base64.b64encode(_resumo(pin, sal)).decode()}}
        self.vincular_este_computador()
        self._gravar()

    def vincular_este_computador(self):
        """Passa a aceitar o Windows Hello neste computador (depois do PIN
        certo num computador novo)."""
        segredo = secrets.token_bytes(32)
        blob = self._dpapi(segredo, True)
        if not blob:
            self.dados.pop("maquina", None)
            return False
        self.dados["maquina"] = {
            "blob": base64.b64encode(blob).decode(),
            "resumo": hashlib.sha256(segredo).hexdigest()}
        return True

    def desligar(self):
        self.dados = {}
        try:
            os.remove(self.caminho)
        except FileNotFoundError:
            pass

    def definir_hello(self, usar):
        self.dados["hello"] = bool(usar)
        self._gravar()

    def trocar_pin(self, novo):
        hello = self.usar_hello()
        self.ligar(novo, hello)

    # ----------------------------------------------------------- conferir
    def espera_restante(self):
        return max(0.0, self._esperar_ate - time.monotonic())

    def conferir_pin(self, pin):
        """True se o PIN confere. Depois de varios erros seguidos, espera um
        pouco antes de aceitar outra tentativa (ErroSeguranca)."""
        resta = self.espera_restante()
        if resta > 0:
            raise ErroSeguranca("Muitas tentativas erradas. Espere %d "
                                "segundos." % (int(resta) + 1))
        p = self.dados.get("pin") or {}
        try:
            sal = base64.b64decode(p["sal"])
            certo = base64.b64decode(p["resumo"])
            n = int(p.get("iteracoes", ITERACOES))
        except Exception:
            return False
        ok = hmac.compare_digest(_resumo(pin or "", sal, n), certo)
        if ok:
            self._erros = 0
            return True
        self._erros += 1
        if self._erros >= TENTATIVAS_ANTES_DE_ESPERAR:
            self._erros = 0
            self._esperar_ate = time.monotonic() + ESPERA_S
        return False


# --------------------------------------------------------- Windows Hello
def hello_disponivel():
    """True se este Windows tem o Windows Hello configurado."""
    try:
        import asyncio
        from winrt.windows.security.credentials.ui import (
            UserConsentVerifier, UserConsentVerifierAvailability)

        async def ver():
            return await UserConsentVerifier.check_availability_async()
        return asyncio.run(ver()) == UserConsentVerifierAvailability.AVAILABLE
    except Exception:
        log.info("Windows Hello indisponível")
        return False

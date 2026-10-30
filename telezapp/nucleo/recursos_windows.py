# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Biometria (Windows Hello) e localizacao do computador.

Sao APIs WinRT do Windows; quem as chama e um PowerShell sem janela, para nao
trazer mais uma dependencia ao programa. Sem wx. `rodar` e trocavel nos testes.
Nada aqui guarda ou registra coordenadas.
"""
import base64
import ctypes
import json
import logging
import os
import subprocess
import sys

log = logging.getLogger("telezapp.recursos")

BIOMETRIA_AUSENTE = ("Não foi identificado nenhum dispositivo de biometria "
                     "neste computador.")
LOCAL_AUSENTE = ("Não foi identificado nenhum dispositivo de localização "
                 "neste computador.")
LOCAL_BLOQUEADO = ("O Windows não deixou o TeleZapp usar a localização. Veja "
                   "em Configurações do Windows, Privacidade e segurança, "
                   "Localização.")
AJUSTES_BIOMETRIA = "ms-settings:signinoptions"
AJUSTES_LOCAL = "ms-settings:privacy-location"

_BASE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Esperar($op, $tipo, $ms) {
    $t = $asTask.MakeGenericMethod($tipo).Invoke($null, @($op))
    if (-not $t.Wait($ms)) { throw 'tempo' }
    $t.Result
}
"""
_VERIFICADOR = r"""
[void][Windows.Security.Credentials.UI.UserConsentVerifier, Windows.Security.Credentials.UI, ContentType = WindowsRuntime]
$V = [Windows.Security.Credentials.UI.UserConsentVerifier]
"""
_CONSULTAR_BIOMETRIA = _BASE + _VERIFICADOR + r"""
$r = Esperar ($V::CheckAvailabilityAsync()) ([Windows.Security.Credentials.UI.UserConsentVerifierAvailability]) 15000
Write-Output "$r"
"""
_VERIFICAR = _BASE + _VERIFICADOR + r"""
$r = Esperar ($V::RequestVerificationAsync($env:TZ_MOTIVO)) ([Windows.Security.Credentials.UI.UserConsentVerificationResult]) 120000
Write-Output "$r"
"""
_LOCALIZAR = _BASE + r"""
[void][Windows.Devices.Geolocation.Geolocator, Windows.Devices.Geolocation, ContentType = WindowsRuntime]
$G = [Windows.Devices.Geolocation.Geolocator]
$a = Esperar ($G::RequestAccessAsync()) ([Windows.Devices.Geolocation.GeolocationAccessStatus]) 15000
if ("$a" -ne 'Allowed') { Write-Output (@{acesso = "$a"} | ConvertTo-Json -Compress); exit }
$p = Esperar ((New-Object $G).GetGeopositionAsync()) ([Windows.Devices.Geolocation.Geoposition]) 30000
$c = $p.Coordinate
Write-Output (@{acesso = "$a"; latitude = $c.Point.Position.Latitude
    longitude = $c.Point.Position.Longitude; altitude = $c.Point.Position.Altitude
    precisao = $c.Accuracy; velocidade = $c.Speed; direcao = $c.Heading} | ConvertTo-Json -Compress)
"""
_ACESSO_LOCAL = _BASE + r"""
[void][Windows.Devices.Geolocation.Geolocator, Windows.Devices.Geolocation, ContentType = WindowsRuntime]
$a = Esperar ([Windows.Devices.Geolocation.Geolocator]::RequestAccessAsync()) ([Windows.Devices.Geolocation.GeolocationAccessStatus]) 15000
Write-Output "$a"
"""


def _powershell(script, ambiente=None, espera=150):
    """A ultima linha que o script escreveu; "" se falhou."""
    if sys.platform != "win32":
        return ""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            env=dict(os.environ, **(ambiente or {})), capture_output=True,
            timeout=espera, text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as e:
        log.info("recurso do Windows: %s", type(e).__name__)
        return ""
    if r.returncode != 0:
        log.info("recurso do Windows falhou (%d)", r.returncode)
        return ""
    linhas = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
    return linhas[-1] if linhas else ""


rodar = _powershell


def biometria_disponivel():
    """True se o Windows Hello esta pronto. Rosto ou digital: o Windows nao diz
    qual, e a pessoa pode ter os dois."""
    return rodar(_CONSULTAR_BIOMETRIA) == "Available"


def verificar_biometria(motivo):
    """"ok", "cancelada", "ausente" (sem dispositivo ou sem cadastro) ou
    "falha"."""
    r = rodar(_VERIFICAR, {"TZ_MOTIVO": motivo or "Confirmar no TeleZapp"})
    return {"Verified": "ok", "Canceled": "cancelada",
            "DeviceNotPresent": "ausente", "NotConfiguredForUser": "ausente",
            "DisabledByPolicy": "ausente"}.get(r, "falha")


def acesso_a_localizacao():
    """"ok", "negado" ou "ausente"."""
    return {"Allowed": "ok", "Denied": "negado"}.get(rodar(_ACESSO_LOCAL),
                                                     "ausente")


def _numero(valor):
    return valor if isinstance(valor, (int, float)) else None


def localizacao():
    """{'situacao': 'ok' | 'negado' | 'ausente', e, se ok, latitude, longitude,
    altitude, precisao, velocidade, direcao}."""
    texto = rodar(_LOCALIZAR)
    try:
        dados = json.loads(texto) if texto else {}
    except ValueError:
        dados = {}
    if dados.get("acesso") == "Denied":
        return {"situacao": "negado"}
    if _numero(dados.get("latitude")) is None or \
            _numero(dados.get("longitude")) is None:
        return {"situacao": "ausente"}
    return {"situacao": "ok", "latitude": dados["latitude"],
            "longitude": dados["longitude"],
            "altitude": _numero(dados.get("altitude")),
            "precisao": _numero(dados.get("precisao")),
            "velocidade": _numero(dados.get("velocidade")),
            "direcao": _numero(dados.get("direcao"))}


def abrir_ajustes(endereco):
    if sys.platform == "win32":
        os.startfile(endereco)


# ------------------------------------------------- segredos dos aplicativos
class _Blob(ctypes.Structure):
    _fields_ = [("tamanho", ctypes.c_uint32),
                ("dados", ctypes.POINTER(ctypes.c_char))]


def _dpapi(funcao, dados):
    entrada = ctypes.create_string_buffer(dados, len(dados))
    blob = _Blob(len(dados), ctypes.cast(entrada, ctypes.POINTER(ctypes.c_char)))
    saida = _Blob()
    if not funcao(ctypes.byref(blob), None, None, None, None, 0,
                  ctypes.byref(saida)):
        raise OSError("DPAPI")
    try:
        return ctypes.string_at(saida.dados, saida.tamanho)
    finally:
        ctypes.windll.kernel32.LocalFree(saida.dados)


class Segredos:
    """O que cada robo guarda atras da biometria, cifrado pelo Windows para
    este usuario (DPAPI). Um arquivo JSON: {robo: texto cifrado}."""

    def __init__(self, caminho):
        self.caminho = caminho

    def _ler(self):
        try:
            with open(self.caminho, encoding="utf-8") as f:
                dados = json.load(f)
            return dados if isinstance(dados, dict) else {}
        except (OSError, ValueError):
            return {}

    def _gravar(self, dados):
        with open(self.caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f)

    def tem(self, robo):
        return str(robo) in self._ler()

    def guardar(self, robo, segredo):
        """Segredo vazio apaga."""
        dados = self._ler()
        if segredo:
            dados[str(robo)] = base64.b64encode(_dpapi(
                ctypes.windll.crypt32.CryptProtectData,
                segredo.encode("utf-8"))).decode()
        else:
            dados.pop(str(robo), None)
        self._gravar(dados)

    def ler(self, robo):
        cifrado = self._ler().get(str(robo))
        if not cifrado:
            return ""
        try:
            return _dpapi(ctypes.windll.crypt32.CryptUnprotectData,
                          base64.b64decode(cifrado)).decode("utf-8")
        except (OSError, ValueError):
            log.info("segredo de robô não pôde ser lido")
            return ""

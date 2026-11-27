# SPDX-License-Identifier: GPL-3.0-or-later
"""Navegador interno com WebView2 de verdade: lembra o que foi marcado, a senha e a
exibicao de celular. Rodar na area de trabalho OCULTA:

    python testes\\rodar_oculto.py C:\\github\\TeleZapp\\venv\\Scripts\\python.exe C:\\github\\TeleZapp\\testes\\oculto_navegador_sites.py
"""
import http.server
import json
import os
import shutil
import sys
import threading
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
DADOS = os.path.join(RAIZ, "testes", "_tmp_navegador")
shutil.rmtree(DADOS, ignore_errors=True)
os.makedirs(DADOS, exist_ok=True)
os.environ["TELEZAPP_DADOS"] = DADOS

PAGINA = b"""<!doctype html><html><head><meta charset=utf-8><title>t</title></head><body>
<form id=f onsubmit="return false">
<input id=nome name=nome type=text>
<input id=aviso name=aviso type=checkbox>
<input id=u name=email type=email>
<input id=p name=pw type=password>
<button id=b type=submit>Entrar</button></form></body></html>"""


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGINA)

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:%d/login" % srv.server_port

import wx  # noqa: E402
import wx.html2  # noqa: E402

from telezapp.interface import navegador  # noqa: E402
from telezapp.nucleo import sites_navegador as sites  # noqa: E402

erros = []


def confere(cond, msg):
    print(("ok   " if cond else "FALHA"), msg)
    if not cond:
        erros.append(msg)


class Falso:                      # a pergunta "Guardar a senha?" responde Guardar
    def __init__(self, *a, **k):
        pass

    def SetYesNoCancelLabels(self, *a):
        pass

    def ShowModal(self):
        return wx.ID_YES

    def Destroy(self):
        pass


navegador.wx.MessageDialog = Falso

app = wx.App()
win = navegador.JanelaNavegador(None, URL)


laco = wx.GUIEventLoop()
wx.EventLoopBase.SetActive(laco)


def esperar(ms):
    fim = time.monotonic() + ms / 1000.0
    while time.monotonic() < fim:
        while laco.Pending():
            laco.Dispatch()
        time.sleep(0.02)


def js(codigo):
    ok, valor = win.web.RunScript(codigo)
    return valor


carregou = [False]
win.web.Bind(wx.html2.EVT_WEBVIEW_LOADED, lambda e: (carregou.__setitem__(0, True), e.Skip()))


def esperar_pagina():
    for _ in range(300):
        esperar(100)
        if carregou[0]:
            carregou[0] = False
            esperar(1200)
            return
    confere(False, "a pagina carregou")
    raise SystemExit


_orig = win._ao_dado_do_site
def _espia(d):
    print("MSG", d.get("t"), list((d.get("c") or {}).keys()), flush=True)
    _orig(d)
win._ao_dado_do_site = _espia
try:
    esperar_pagina()
    print("pagina ok", flush=True)
    # a pessoa digita, marca e entra (eventos de teste valem por causa do flag)
    js("window.__tzTeste = true;"
       "var n = document.getElementById('nome'); n.value = 'Maria';"
       "n.dispatchEvent(new Event('input', {bubbles: true}));"
       "document.getElementById('aviso').click();"
       "document.getElementById('u').value = 'eu@x.com';"
       "document.getElementById('p').value = 'segredo123';"
       "document.getElementById('b').click();")
    esperar(4000)
    print('flag', js('String(window.__tzTeste)'), js('typeof window.__tzRestaurar'), flush=True)
    st = sites.SitesDoNavegador(os.path.join(DADOS, "navegador_sites.json"))
    campos = st.campos(URL)
    confere(campos.get("t:nome") == "Maria", "campo de texto guardado: %r" % campos)
    confere(campos.get("c:aviso:on") == "1", "caixa marcada guardada: %r" % campos)
    confere("t:email" not in campos or campos["t:email"] == "eu@x.com",
            "campo de e-mail (nao sensivel) pode ser guardado")
    confere(st.senha_guardada(URL) == ("eu@x.com", "segredo123"),
            "usuario e senha guardados depois de 'Guardar'")

    # volta a pagina: tudo reaparece
    win.web.Reload()
    esperar_pagina()
    esperar(1500)
    v = json.loads(js("JSON.stringify({n: document.getElementById('nome').value,"
                      "a: document.getElementById('aviso').checked,"
                      "u: document.getElementById('u').value,"
                      "p: document.getElementById('p').value})"))
    confere(v["n"] == "Maria", "texto voltou: %r" % v)
    confere(v["a"] is True, "caixa voltou marcada")
    confere(v["u"] == "eu@x.com" and v["p"] == "segredo123", "usuario e senha preenchidos")

    # exibicao de celular
    padrao = js("navigator.userAgent")
    win._aplicar_modo(sites.CELULAR)
    win.web.Reload()
    esperar_pagina()
    ua = js("navigator.userAgent")
    largura = int(float(js("window.innerWidth")))
    confere("Mobile" in ua and "Android" in ua, "agente de celular: %s" % ua)
    confere(largura <= 460, "janela estreita (innerWidth=%d)" % largura)
    win._aplicar_modo(sites.COMPUTADOR)
    win.web.Reload()
    esperar_pagina()
    ua2 = js("navigator.userAgent")
    confere("Mobile" not in ua2 and "Windows" in ua2, "voltou ao computador: %s" % ua2)
    print("agente padrao do Edge:", padrao)
finally:
    win.Destroy()
    srv.shutdown()
    shutil.rmtree(DADOS, ignore_errors=True)
print("RESULTADO:", "FALHOU" if erros else "PASSOU")
os._exit(1 if erros else 0)

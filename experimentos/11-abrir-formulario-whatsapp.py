"""Experimento: abre a pagina da Meta no JanelaFormulario (janela oculta) e
mostra o que a pagina pediu e o texto que desenhou. Sem preencher nada."""
import functools, json, os, sys
print = functools.partial(print, flush=True)
import json, os, sys, tempfile, time, urllib.request
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
dados_dir = tempfile.mkdtemp(prefix="tz-flows-", dir=os.path.join(RAIZ, "testes", "_temp_flows"))
os.environ["TELEZAPP_DADOS"] = dados_dir
import logging, wx
logging.basicConfig(level=logging.INFO, format='%(name)s: %(message)s', stream=sys.stdout)
from telezapp.nucleo import ponte_flows as pf
from telezapp.interface import formulario_whatsapp as fw

ID = sys.argv[1] if len(sys.argv) > 1 else "1076111852117017"
flow = json.loads(urllib.request.urlopen(urllib.request.Request(
    pf.URL_DO_JSON % ID, headers={"User-Agent": "TeleZapp-teste"}), timeout=20).read())
print("json do formulario: telas=%d versao=%s" % (len(flow.get("screens", [])), flow.get("version")))
params = {"flow_token": "teste", "flow_id": ID, "flow_action": "navigate",
          "flow_action_payload": {"screen": flow["screens"][0]["id"]}, "mode": "published",
          "flow_metadata": {}}
from Cryptodome.PublicKey import RSA
pem = RSA.generate(2048).publickey().export_key().decode()
print("chave de teste: %d caracteres" % len(pem))
dados = pf.dados_do_formulario(params, flow, chave_publica=pem, nome_da_empresa="Teste", biz_jid="0@s.whatsapp.net")
app = wx.App(False)
fala = []
j = fw.JanelaFormulario(None, "Teste", dados, ao_completar=lambda p: print("COMPLETOU", pf.formato(p)),
                        abrir_link=lambda u: print("LINK", u), falar=lambda t: fala.append(t))
j.Show()
fim = time.time() + 25
def ver():
    print("eventos:", j.ponte.eventos)
    pass
def texto(e):
    print("TEXTO DA PAGINA:", repr(e.GetString())[:400])
j.web.Bind(wx.html2.EVT_WEBVIEW_SCRIPT_RESULT, texto)
for nome in ("EVT_WEBVIEW_NAVIGATING","EVT_WEBVIEW_NAVIGATED","EVT_WEBVIEW_LOADED","EVT_WEBVIEW_ERROR","EVT_WEBVIEW_TITLE_CHANGED"):
    j.web.Bind(getattr(wx.html2, nome), lambda e, n=nome: print(n, e.GetURL()[:80] if hasattr(e,'GetURL') else '', e.GetString()[:60] if hasattr(e,'GetString') else ''))
wx.CallLater(30000, ver)
wx.CallLater(45000, ver)
wx.CallLater(50000, lambda: (print("url final:", j.web.GetCurrentURL()[:80], "| titulo:", j.web.GetCurrentTitle()), print("fala:", fala), j.Destroy(), app.ExitMainLoop()))
app.MainLoop()

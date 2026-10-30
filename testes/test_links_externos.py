# SPDX-License-Identifier: GPL-3.0-or-later
"""Links do Telegram e do WhatsApp, a ponte dos aplicativos e o registro."""
import json
import sys

import pytest

from telezapp import config
from telezapp.nucleo import links_externos as le
from telezapp.nucleo import links_recebidos as lr
from telezapp.nucleo import ponte_web_app as pw
from telezapp.nucleo import protocolos


@pytest.mark.parametrize("url,usuario,start,startapp,app", [
    ("https://t.me/wallet", "wallet", None, None, ""),
    ("https://t.me/wallet/start?startapp=abc", "wallet", None, "abc", "start"),
    ("https://t.me/wallet?startapp", "wallet", None, "", ""),
    ("https://telegram.me/robo_x?start=oi", "robo_x", "oi", None, ""),
    ("tg://resolve?domain=wallet&appname=start&startapp=z", "wallet", None,
     "z", "start"),
    ("https://t.me/canalum/123", "canalum", None, None, ""),
])
def test_usuarios_do_telegram(url, usuario, start, startapp, app):
    r = le.interpretar(url)
    assert (r["servico"], r["acao"]) == ("telegram", "usuario")
    assert (r["usuario"], r["start"], r["startapp"], r["app"]) == (
        usuario, start, startapp, app)


@pytest.mark.parametrize("url", [
    "https://t.me/+AbCdEfGhIjKl", "https://t.me/joinchat/AbCdEfGhIjKl",
    "tg://join?invite=AbCdEfGhIjKl"])
def test_convites_do_telegram(url):
    r = le.interpretar(url)
    assert r["acao"] == "entrar"
    assert r["convite"]["codigo"] == "AbCdEfGhIjKl"


@pytest.mark.parametrize("url,texto", [
    ("https://wa.me/5551999998888?text=oi", "oi"),
    ("https://api.whatsapp.com/send?phone=5551999998888", ""),
    ("whatsapp://send?phone=%2B5551999998888&text=ol%C3%A1", "olá"),
])
def test_telefones_do_whatsapp(url, texto):
    r = le.interpretar(url)
    assert r["acao"] == "telefone"
    assert r["telefone"] == "5551999998888"
    assert r["texto"] == texto


def test_convite_do_whatsapp():
    r = le.interpretar("https://chat.whatsapp.com/AbCdEfGhIjKlMnOpQrStUv")
    assert r["servico"] == "whatsapp" and r["acao"] == "entrar"
    assert r["convite"]["codigo"] == "AbCdEfGhIjKlMnOpQrStUv"


@pytest.mark.parametrize("url", [
    "", "https://example.com/wallet", "https://t.me/addstickers/x",
    "https://t.me/", "tg://msg?text=oi", "whatsapp://outra", "https://wa.me/12",
    "file:///c:/x", "https://t.me/" + "a" * 5000])
def test_o_resto_segue_para_o_navegador(url):
    assert le.interpretar(url) is None


# ------------------------------------------------------------------- ponte
class Ui:
    def __init__(self):
        self.feito = []

    def __getattr__(self, nome):
        def registrar(*a):
            self.feito.append((nome,) + a)
            return "b1" if nome == "janelinha" else None
        return registrar

    def tamanho(self):
        return (800, 600)


def test_botoes_nativos_e_respostas_da_ponte():
    ui = Ui()
    pw.tratar("web_app_setup_main_button",
              {"is_visible": True, "text": "Pagar", "is_active": False}, ui)
    pw.tratar("web_app_setup_back_button", {"is_visible": True}, ui)
    assert ui.feito == [("botao", "principal", True, "Pagar", False),
                        ("botao", "voltar", True, "", True)]
    assert pw.tratar("web_app_request_theme", {}, ui)[0][0] == "theme_changed"
    assert pw.tratar("web_app_request_viewport", {}, ui)[0][1]["height"] == 600
    assert pw.tratar("web_app_open_popup", {"message": "m"}, ui) == [
        ("popup_closed", {"button_id": "b1"})]
    pw.tratar("web_app_request_phone", {}, ui)
    assert ui.feito[-1] == ("pedir_telefone",)
    pw.tratar("web_app_open_invoice", {"slug": "s"}, ui)
    assert ui.feito[-1] == ("pagar", "s")
    pw.tratar("payment_form_submit", {"credentials": {"a": 1}}, ui)
    assert ui.feito[-1] == ("pagamento", {"a": 1})
    pw.tratar("web_app_open_scan_qr_popup", {"text": "t"}, ui)
    assert ui.feito[-1] == ("ler_qr", "t")
    pw.tratar("web_app_setup_closing_behavior", {"need_confirmation": True}, ui)
    assert ui.feito[-1] == ("confirmar_ao_fechar", True)
    ui.ler_area = lambda: {"data": "x"}
    assert pw.tratar("web_app_read_text_from_clipboard", {"req_id": "1"},
                     ui) == [("clipboard_text_received",
                              {"req_id": "1", "data": "x"})]
    assert pw.tratar("web_app_desconhecido", {}, ui) == []
    pw.tratar("web_app_open_tg_link", {"path_full": "/wallet"}, ui)
    assert ui.feito[-1] == ("abrir_link", "https://t.me/wallet")


def test_mensagem_da_pagina():
    assert pw.ler_mensagem(json.dumps(["a", '{"x": 1}'])) == ("a", {"x": 1})
    assert pw.ler_mensagem(json.dumps(["a", ""])) == ("a", {})
    assert pw.ler_mensagem("lixo") == (None, {})
    assert pw.ler_mensagem("[1, 2]") == (None, {})
    assert 'receiveEvent("t", {"a": 1})' in pw.script_de_resposta("t", {"a": 1})


# ---------------------------------------------------------- links recebidos
def test_links_recebidos_saem_do_arquivo(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "pasta", lambda *p: str(tmp_path))
    assert lr.guardar("tg://resolve?domain=wallet")
    assert not lr.guardar("")
    assert not lr.guardar("a\nb")
    assert lr.retirar() == ["tg://resolve?domain=wallet"]
    assert lr.retirar() == []


# ----------------------------------------------------------------- registro
class RegFalso:
    HKEY_CURRENT_USER, HKEY_CLASSES_ROOT = "HKCU", "HKCR"
    KEY_SET_VALUE = KEY_READ = REG_SZ = 0

    def __init__(self, existentes=()):
        self.chaves = {}
        self.existentes = set(existentes)

    def CreateKeyEx(self, raiz, chave, *a):
        self.chaves.setdefault(chave, {})
        return _Ctx(chave)

    def SetValueEx(self, k, nome, _0, _t, valor):
        self.chaves[k.chave][nome] = valor

    def OpenKey(self, raiz, chave, *a):
        if raiz == "HKCR":
            if chave not in self.existentes:
                raise FileNotFoundError
            return _Ctx(chave)
        if not any(c == chave or c.startswith(chave + "\\")
                   for c in self.chaves):
            raise FileNotFoundError
        return _Ctx(chave)

    def QueryValueEx(self, k, nome):
        return self.chaves[k.chave][nome], 1

    def DeleteValue(self, k, nome):
        self.chaves[k.chave].pop(nome, None)

    def EnumKey(self, k, i):
        filhas = sorted({c[len(k.chave) + 1:].split("\\")[0]
                         for c in self.chaves
                         if c.startswith(k.chave + "\\")})
        if i >= len(filhas):
            raise OSError
        return filhas[i]

    def DeleteKey(self, raiz, chave):
        self.chaves.pop(chave, None)


class _Ctx:
    def __init__(self, chave):
        self.chave = chave

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def Close(self):
        pass


def test_registro_oferece_sem_tomar_o_lugar_de_ninguem():
    reg = RegFalso(existentes={"tg"})
    linha = '"C:\\p\\TeleZapp.exe" --link "%1"'
    assert protocolos.registrar(linha, reg=reg)
    assert reg.chaves[protocolos.CHAVE_REGISTRADOS]["TeleZapp"] == \
        protocolos.CHAVE_CAPACIDADES
    assert reg.chaves[protocolos.CHAVE_CAPACIDADES + r"\URLAssociations"] == {
        "tg": "TeleZapp.Url.tg", "whatsapp": "TeleZapp.Url.whatsapp"}
    assert reg.chaves[protocolos.CLASSES + r"\TeleZapp.Url.tg\shell\open\command"][
        ""] == linha
    # tg ja tem dono: nao criei; whatsapp nao tinha: criei
    assert protocolos.CLASSES + r"\tg" not in reg.chaves
    assert "URL Protocol" in reg.chaves[protocolos.CLASSES + r"\whatsapp"]
    assert protocolos.remover(reg=reg)
    assert reg.chaves[protocolos.CHAVE_REGISTRADOS] == {}
    assert [c for c in reg.chaves if "TeleZapp" in c or "whatsapp" in c] == []


def test_comando_leva_o_link():
    assert protocolos.comando().endswith('--link "%1"')


def test_argumento_do_link_nao_vai_para_o_log():
    if "telezapp.__main__" in sys.modules:
        principal = sys.modules["telezapp.__main__"]
    else:
        import telezapp.__main__ as principal
    assert principal._link_recebido(["--link", "tg://x"]) == "tg://x"
    assert principal._link_recebido(["--segundo-plano"]) == ""
    assert principal._argumentos_para_o_log(
        ["--segundo-plano", "--link", "whatsapp://send?phone=1"]) == [
            "--segundo-plano", "--link"]


def test_coordenadas_e_preco():
    from telezapp.nucleo import robos
    assert robos.ler_coordenadas("-30.03, -51.22") == (-30.03, -51.22)
    assert robos.ler_coordenadas("-30,03 -51,22") == (-30.03, -51.22)
    assert robos.ler_coordenadas("100, 200") is None
    assert robos.ler_coordenadas("aqui") is None
    assert robos.preco("XTR", 5) == "5 estrelas"
    assert robos.preco("XTR", 1) == "1 estrela"
    assert robos.preco("BRL", 1990) == "19.90 BRL"
    assert robos.preco("JPY", 500) == "500 JPY"


def test_dados_de_pagamento_pedidos():
    from telezapp.nucleo import robos
    pede = {"nome": True, "endereco": True}
    assert [c[0] for c in robos.campos_pedidos(pede)] == [
        "nome", "rua1", "rua2", "cidade", "estado", "pais", "cep"]
    assert robos.faltando({"email": True}, {}) == "E-mail"
    certos = {"nome": "Ana", "rua1": "R", "cidade": "C", "pais": "BR",
              "cep": "1"}
    assert robos.faltando(pede, certos) == ""
    assert "País" in robos.faltando(pede, dict(certos, pais="Brasil"))
    assert robos.faltando({}, {}) == ""


def test_dados_salvos_e_info_de_pagamento():
    from telezapp.provedores import telegram as tg
    assert tg._dados_salvos(None) == {}
    info = tg._info_de_pagamento(
        {"nome": True, "endereco": True},
        {"nome": " Ana ", "rua1": "R", "pais": "br", "cep": "1", "cidade": "C"})
    assert info.name == "Ana" and info.phone is None
    assert info.shipping_address.country_iso2 == "BR"
    assert tg._dados_salvos(info)["rua1"] == "R"


def test_biometria_e_localizacao_pelo_windows(monkeypatch):
    from telezapp.nucleo import recursos_windows as rw
    monkeypatch.setattr(rw, "rodar", lambda s, a=None: "Available")
    assert rw.biometria_disponivel() is True
    monkeypatch.setattr(rw, "rodar", lambda s, a=None: "DeviceNotPresent")
    assert rw.biometria_disponivel() is False
    assert rw.verificar_biometria("x") == "ausente"
    monkeypatch.setattr(rw, "rodar", lambda s, a=None: "Verified")
    assert rw.verificar_biometria("x") == "ok"
    monkeypatch.setattr(rw, "rodar", lambda s, a=None: "")
    assert rw.verificar_biometria("x") == "falha"
    assert rw.localizacao() == {"situacao": "ausente"}
    monkeypatch.setattr(rw, "rodar", lambda s, a=None: '{"acesso": "Denied"}')
    assert rw.localizacao() == {"situacao": "negado"}
    monkeypatch.setattr(rw, "rodar", lambda s, a=None: (
        '{"acesso": "Allowed", "latitude": 1.5, "longitude": 2, "precisao": 9}'))
    r = rw.localizacao()
    assert (r["situacao"], r["latitude"], r["precisao"]) == ("ok", 1.5, 9)
    assert "biometria" in rw.BIOMETRIA_AUSENTE
    assert "localização" in rw.LOCAL_AUSENTE


def test_ponte_de_biometria_e_localizacao():
    ui = Ui()
    pw.tratar("web_app_biometry_request_auth", {"reason": "r"}, ui)
    assert ui.feito[-1] == ("autenticar_biometria", "r")
    pw.tratar("web_app_biometry_update_token", {"token": "t"}, ui)
    assert ui.feito[-1] == ("guardar_segredo", "t")
    pw.tratar("web_app_request_location", {}, ui)
    assert ui.feito[-1] == ("pedir_localizacao",)


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI é do Windows")
def test_segredo_do_robo_fica_cifrado(tmp_path):
    from telezapp.nucleo import recursos_windows as rw
    caminho = tmp_path / "s.json"
    s = rw.Segredos(str(caminho))
    assert not s.tem("robo") and s.ler("robo") == ""
    s.guardar("robo", "segredo-123")
    assert s.tem("robo") and s.ler("robo") == "segredo-123"
    assert "segredo-123" not in caminho.read_text(encoding="utf-8")
    s.guardar("robo", "")
    assert not s.tem("robo")


def test_qr_de_um_arquivo_com_acento(tmp_path):
    import cv2
    from telezapp.midia import qr
    imagem = cv2.resize(cv2.QRCodeEncoder.create().encode("olá123"), None,
                        fx=6, fy=6, interpolation=cv2.INTER_NEAREST)
    caminho = tmp_path / "código.png"
    ok, dados = cv2.imencode(".png", imagem)
    assert ok
    caminho.write_bytes(dados.tobytes())
    assert qr.ler_arquivo(str(caminho)) == "olá123"
    vazio = tmp_path / "branco.png"
    vazio.write_bytes(cv2.imencode(".png", imagem * 0 + 255)[1].tobytes())
    assert qr.ler_arquivo(str(vazio)) == ""

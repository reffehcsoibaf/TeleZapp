# SPDX-License-Identifier: GPL-3.0-or-later
"""Por onde abrir os links: navegador interno, padrao, pergunta ou escolhido."""
import pytest

from telezapp import config
from telezapp.nucleo import navegadores

wx = pytest.importorskip("wx")


class _Cfg(dict):
    def get(self, k):
        return super().get(k, config.PADROES.get(k))

    def set(self, k, v):
        self[k] = v


@pytest.fixture
def dlg(monkeypatch):
    from telezapp.interface import dialogos
    if not hasattr(dialogos.wx, "LaunchDefaultBrowser"):
        pytest.skip("wx falso")
    abertos = []
    monkeypatch.setattr(dialogos, "abrir_por_dentro", None)
    monkeypatch.setattr(dialogos.wx, "LaunchDefaultBrowser",
                        lambda u: abertos.append(("padrao", u)) or True)
    monkeypatch.setattr(navegadores, "abrir",
                        lambda exe, u: abertos.append((exe, u)) or True)
    cfg = _Cfg()
    monkeypatch.setattr(config, "_cfg_de_contas", cfg)
    return dialogos, cfg, abertos


def test_padrao_do_windows(dlg):
    dialogos, cfg, abertos = dlg
    cfg["abrir_links_em"] = "padrao"
    assert dialogos.abrir_link("https://exemplo.com") is True
    assert abertos == [("padrao", "https://exemplo.com")]


def test_navegador_escolhido(dlg, tmp_path):
    dialogos, cfg, abertos = dlg
    exe = tmp_path / "nav.exe"
    exe.write_text("x")
    cfg["abrir_links_em"] = "escolhido"
    cfg["abrir_links_navegador"] = str(exe)
    dialogos.abrir_link("https://exemplo.com")
    assert abertos == [(str(exe), "https://exemplo.com")]


def test_escolhido_que_sumiu_cai_no_padrao_do_windows(dlg):
    dialogos, cfg, abertos = dlg
    cfg["abrir_links_em"] = "escolhido"
    cfg["abrir_links_navegador"] = "/nao/existe.exe"
    from telezapp.interface import navegador
    navegador.disponivel = lambda: False
    dialogos.abrir_link("https://exemplo.com")
    assert abertos == [("padrao", "https://exemplo.com")]


def test_perguntar_e_lembrar(dlg, monkeypatch):
    dialogos, cfg, abertos = dlg
    cfg["abrir_links_em"] = "perguntar"
    monkeypatch.setattr(dialogos, "_perguntar_destino",
                        lambda c: ("exe", "/n/x.exe"))
    dialogos.abrir_link("https://exemplo.com")
    assert abertos == [("/n/x.exe", "https://exemplo.com")]
    monkeypatch.setattr(dialogos, "_perguntar_destino", lambda c: None)
    assert dialogos.abrir_link("https://exemplo.com") == dialogos.PELO_TELEZAPP
    assert len(abertos) == 1                       # desistiu: nada abriu


def test_exe_do_comando():
    f = navegadores._exe_do_comando
    assert f('"C:/A B/chrome.exe" --x') == "C:/A B/chrome.exe"
    assert f("C:/Foo/ff.exe -url") == "C:/Foo/ff.exe"

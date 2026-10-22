"""Atalhos: a forma canonica, o que nao pode ser atalho, o registro e os
conflitos."""
from telezapp.nucleo import atalhos as at


def test_normalizar_poe_na_forma_canonica():
    assert at.normalizar("ctrl+shift+e") == "Ctrl+Shift+E"
    assert at.normalizar("Shift + Control + e") == "Ctrl+Shift+E"
    assert at.normalizar("control+alt+f5") == "Ctrl+Alt+F5"
    assert at.normalizar("Ctrl+PageUp") == "Ctrl+PgUp"
    assert at.normalizar("Ctrl+,") == "Ctrl+,"
    assert at.normalizar("F7") == "F7"
    assert at.normalizar("") is None
    assert at.normalizar("Ctrl+") is None
    assert at.normalizar("Ctrl+Shift") is None
    assert at.normalizar("Ctrl+A+B") is None
    assert at.normalizar("Ctrl+Banana") is None


def test_partes_e_montar_sao_inversos():
    for c in ("Ctrl+Shift+E", "Alt+4", "F7", "Ctrl+,", "Ctrl+Alt+PgDn"):
        assert at.montar(*at.partes(c)) == c


def test_o_que_nao_serve_de_atalho():
    assert at.problema("Ctrl+Shift+E") == ""
    assert at.problema("F7") == ""
    assert at.problema("Shift+F2") == ""
    assert at.problema("Alt+4") == ""
    assert at.problema("Enter")
    assert at.problema("Ctrl+V")
    assert at.problema("Alt+F4")
    assert at.problema("E")                 # letra solta atrapalha a digitacao
    assert at.problema("Shift+E")
    assert at.problema("Alt+E")             # abre menu
    assert at.problema(None)


def registro():
    r = at.Registro()
    r.registrar("a", "&Alfa...\tCtrl+1", "Mensagens", "Ctrl+1")
    r.registrar("b", "&Beta", "Mensagens")
    r.registrar("c", "Ga&ma", "Chamadas", "Ctrl+Shift+C")
    return r


def test_rotulo_perde_a_letra_de_acesso_e_o_atalho():
    r = registro()
    assert r.acoes["a"].rotulo == "Alfa..."
    assert r.acoes["c"].rotulo == "Gama"
    assert r.acoes["a"].padrao == "Ctrl+1"


def test_efetivo_usa_o_personalizado_ou_o_padrao():
    r = registro()
    assert r.efetivo("a") == "Ctrl+1" and r.efetivo("b") == ""
    r.definir_personalizados({"a": "ctrl+2", "c": ""})
    assert r.efetivo("a") == "Ctrl+2"
    assert r.efetivo("c") == ""            # tirado de proposito
    assert r.efetivo("b") == ""


def test_dono_acha_quem_ja_usa_a_combinacao():
    r = registro()
    assert r.dono("Ctrl+1").chave == "a"
    assert r.dono("Ctrl+1", ignorar="a") is None
    assert r.dono("Ctrl+9") is None and r.dono("") is None


def test_trocando_tira_o_atalho_de_quem_usava():
    r = registro()
    pers = r.trocando("b", "Ctrl+1")
    assert r.efetivo("b", pers) == "Ctrl+1"
    assert r.efetivo("a", pers) == ""      # perdeu o atalho
    assert r.efetivo("a") == "Ctrl+1"      # o registro nao mudou


def test_voltar_ao_padrao_nao_guarda_nada():
    r = registro()
    pers = r.com_atalho("a", "Ctrl+2")
    assert pers == {"a": "Ctrl+2"}
    assert r.com_atalho("a", "Ctrl+1", pers) == {}


def test_busca_por_funcao_categoria_ou_atalho():
    r = registro()
    assert [a.chave for a, _ in r.buscar("alfa")] == ["a"]
    assert [a.chave for a, _ in r.buscar("chamadas")] == ["c"]
    assert [a.chave for a, _ in r.buscar("ctrl shift")] == ["c"]
    assert [a.chave for a, _ in r.buscar("Ctrl+1")] == ["a"]
    assert [a.chave for a, _ in r.buscar("mensagens")] == ["a", "b"]
    assert r.buscar("zzz") == []


def test_texto_falado():
    assert at.texto_falado("Ctrl+Shift+PgUp") == "Control Shift Page Up"
    assert at.texto_falado("Ctrl+,") == "Control vírgula"
    assert at.texto_falado("") == "sem atalho"

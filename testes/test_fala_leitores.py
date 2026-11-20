"""A fala direta escolhe o leitor de telas ativo: NVDA primeiro, depois JAWS."""
from telezapp.acessibilidade import fala as modulo


# o conftest troca ativa e falar por falsos em cada teste: guardo as de verdade
_ATIVA, _FALAR = modulo.Fala.ativa, modulo.Fala.falar


class _Jaws:
    def __init__(self):
        self.ditas = []

    def SayString(self, texto, cortar):
        self.ditas.append((texto, cortar))
        return True


def _fala(monkeypatch, nvda, jaws):
    monkeypatch.setattr(modulo.Fala, "ativa", _ATIVA)
    monkeypatch.setattr(modulo.Fala, "falar", _FALAR)
    f = modulo.Fala()
    f.lib = None
    monkeypatch.setattr(f, "_nvda_ativo", lambda: nvda)
    monkeypatch.setattr(f, "_jaws", lambda: jaws)
    return f


def test_sem_nenhum_leitor_fica_em_silencio(monkeypatch):
    f = _fala(monkeypatch, False, None)
    assert not f.ativa()
    assert f.falar("oi") is False


def test_usa_o_jaws_quando_o_nvda_nao_esta_rodando(monkeypatch):
    jaws = _Jaws()
    f = _fala(monkeypatch, False, jaws)
    assert f.falar("Pronto: tudo certo", interromper=True)
    assert f.leitor == "jaws"
    texto, cortar = jaws.ditas[0]
    assert texto.strip() == "Pronto: tudo certo" and cortar is True


def test_nvda_tem_prioridade_sobre_o_jaws(monkeypatch):
    jaws = _Jaws()
    f = _fala(monkeypatch, True, jaws)

    class Lib:
        def nvdaController_speakText(self, t):
            self.dito = t
            return 0

    f.lib = Lib()
    assert f.falar("oi") and f.leitor == "nvda" and not jaws.ditas


def test_erro_no_jaws_nao_derruba_o_app(monkeypatch):
    class Quebrado:
        def SayString(self, *a):
            raise OSError("COM")

    f = _fala(monkeypatch, False, Quebrado())
    assert f.falar("oi") is False

# SPDX-License-Identifier: GPL-3.0-or-later
"""A sincronia inicial do WhatsApp (mensagens acumuladas) so acaba quando o
WhatsApp avisa o fim; uma fila grande nao rompe o silencio no meio."""
import threading

from telezapp.provedores import whatsapp


class _Relogio:
    fila = []

    def __init__(self, _s, f):
        self.f = f
        self.daemon = False

    def start(self):
        _Relogio.fila.append(self.f)


def _classe():
    for nome in dir(whatsapp):
        c = getattr(whatsapp, nome)
        if isinstance(c, type) and hasattr(c, "_vigiar_sincronia"):
            return c


def _provedor(monkeypatch, agora, geracao, recebidas):
    monkeypatch.setattr(whatsapp.threading, "Timer", _Relogio)
    monkeypatch.setattr(whatsapp.time, "monotonic", lambda: agora[0])
    _Relogio.fila = []
    p = object.__new__(_classe())
    p._trava = threading.RLock()
    p._sincronizando = True
    p._sincronia_geracao = geracao
    p._recebidas_na_sincronia = recebidas
    p._sincronia_inicio = p._sincronia_ultima = agora[0]
    p.fins = []
    p._ao_fim_sincronia = lambda c, e: p.fins.append(1)
    return p


def test_silencio_dura_ate_o_aviso_com_fila_chegando(monkeypatch):
    agora = [1000.0]
    p = _provedor(monkeypatch, agora, 1, 5)
    p._vigiar_sincronia(1)
    # 10 minutos de mensagens chegando de 20 em 20 s: nao acaba
    for _ in range(30):
        agora[0] += 20
        p._sincronia_ultima = agora[0]
        _Relogio.fila.pop()()
    assert not p.fins
    # com fila chegando, 45 s de calma NAO acabam: so o aviso do WhatsApp
    agora[0] += whatsapp.TEMPO_MAX_SINCRONIA
    _Relogio.fila.pop()()
    assert not p.fins
    # rede de seguranca (aviso perdido)
    agora[0] += whatsapp.TEMPO_OCIOSO_COM_FILA
    _Relogio.fila.pop()()
    assert p.fins == [1]


def test_sem_mensagem_nenhuma_acaba_em_45s(monkeypatch):
    agora = [1000.0]
    p = _provedor(monkeypatch, agora, 1, 0)
    p._vigiar_sincronia(1)
    agora[0] += whatsapp.TEMPO_MAX_SINCRONIA
    _Relogio.fila.pop()()
    assert p.fins == [1]


def test_vigia_velho_nao_encerra_a_conexao_nova(monkeypatch):
    agora = [1000.0]
    p = _provedor(monkeypatch, agora, 2, 0)   # 2 = a conexao nova
    p._vigiar_sincronia(1)                    # vigia da conexao antiga
    agora[0] += 500
    _Relogio.fila.pop()()
    assert not p.fins

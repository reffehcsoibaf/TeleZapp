from datetime import date, datetime

from telezapp.nucleo import agendamento as ag

AGORA = datetime(2026, 11, 11, 14, 23)       # quarta-feira


def test_data_hoje_amanha_e_com_dia_e_mes():
    hoje = AGORA.date()
    assert ag.interpretar_data("hoje", hoje) == hoje
    assert ag.interpretar_data("Amanhã", hoje) == date(2026, 11, 12)
    assert ag.interpretar_data("amanha", hoje) == date(2026, 11, 12)
    assert ag.interpretar_data("25/12/2026", hoje) == date(2026, 12, 25)
    assert ag.interpretar_data("25-12-26", hoje) == date(2026, 12, 25)
    assert ag.interpretar_data("25.12", hoje) == date(2026, 12, 25)
    # sem ano, o que ja passou vai para o ano seguinte
    assert ag.interpretar_data("10/11", hoje) == date(2027, 11, 10)
    assert ag.interpretar_data("31/02/2027", hoje) is None
    assert ag.interpretar_data("depois", hoje) == date(2026, 11, 13)
    assert ag.interpretar_data("segunda", hoje) is None
    assert ag.interpretar_data("", hoje) is None


def test_hora_em_varios_formatos():
    assert ag.interpretar_hora("14:30") == (14, 30)
    assert ag.interpretar_hora("9") == (9, 0)
    assert ag.interpretar_hora("9h") == (9, 0)
    assert ag.interpretar_hora("9h15") == (9, 15)
    assert ag.interpretar_hora("930") == (9, 30)
    assert ag.interpretar_hora("1430") == (14, 30)
    assert ag.interpretar_hora("23.59") == (23, 59)
    assert ag.interpretar_hora("24:00") is None
    assert ag.interpretar_hora("12:60") is None
    assert ag.interpretar_hora("abc") is None


def test_montar_confere_limites():
    q, erro = ag.montar("amanhã", "9", AGORA)
    assert q == datetime(2026, 11, 12, 9, 0) and erro == ""
    q, erro = ag.montar("hoje", "14:23", AGORA)         # agora mesmo
    assert q is None and "passou" in erro
    q, erro = ag.montar("hoje", "14:24", datetime(2026, 11, 11, 14, 23, 30))
    assert q is None                                    # menos de 1 minuto
    q, erro = ag.montar("hoje", "14:25", AGORA)
    assert q is not None
    q, erro = ag.montar("11/11/2027", "15:00", AGORA)
    assert q is None and "um ano" in erro
    assert "data" in ag.montar("xx", "9", AGORA)[1]
    assert "hora" in ag.montar("hoje", "xx", AGORA)[1]


def test_sugestao_e_a_proxima_hora_cheia():
    assert ag.sugestao(AGORA) == ("11/11/2026", "15:00")
    assert ag.sugestao(datetime(2026, 11, 11, 23, 40)) == (
        "12/11/2026", "00:00")


def test_descricao_e_linha():
    assert ag.descricao(datetime(2026, 11, 11, 15, 0), AGORA) == \
        "hoje às 15:00"
    assert ag.descricao(datetime(2026, 11, 12, 9, 0), AGORA) == \
        "amanhã às 09:00"
    assert ag.descricao(datetime(2026, 11, 14, 9, 0), AGORA) == \
        "sábado, 14/11/2026 às 09:00"
    assert ag.descricao(datetime(2026, 12, 25, 8, 5), AGORA) == \
        "25/12/2026 às 08:05"
    assert ag.linha("oi\n  tudo bem", datetime(2026, 11, 12, 9, 0), AGORA) \
        == "amanhã às 09:00: oi tudo bem"
    assert "(mensagem sem texto)" in ag.linha(
        "", datetime(2026, 11, 12, 9, 0), AGORA)
    assert ag.linha("x" * 300, datetime(2026, 11, 12, 9, 0), AGORA,
                    limite=10).endswith("xxxxxxxxxx...")


# ------------------------------------------------ as janelas
def _janelas():
    import sys
    from testes import wx_falso
    sys.modules["wx"] = wx_falso
    from telezapp.interface import agendadas as ja
    return ja, wx_falso


class _ThreadNaHora:
    def __init__(self, target=None, args=(), **k):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


def test_janela_de_agendar_confere_texto_data_e_hora(monkeypatch):
    ja, wx = _janelas()
    avisos = []
    monkeypatch.setattr(ja.wx, "MessageBox", lambda t, *a, **k: avisos.append(t))
    d = ja.DialogoAgendar(None, "Ana", "", agora=lambda: AGORA)
    assert d.data.GetValue() == "11/11/2026" and d.hora.GetValue() == "15:00"
    d._ok(None)                                       # sem texto
    assert avisos[-1] == "Escreva a mensagem." and d.escolhido() is None
    d.caixa.SetValue("bom dia")
    d.hora.SetValue("99")
    d._ok(None)
    assert "hora" in avisos[-1] and d.escolhido() is None
    d.data.SetValue("amanhã")
    d.hora.SetValue("9")
    d._ok(None)
    assert d.escolhido() == ("bom dia", datetime(2026, 11, 12, 9, 0))
    assert d.encerrado == wx.ID_OK


def test_janela_de_agendar_ao_mudar_o_horario_comeca_pelo_horario_atual():
    ja, _ = _janelas()
    d = ja.DialogoAgendar(None, "Ana", "texto", editar_texto=False,
                          agora=lambda: AGORA,
                          quando=datetime(2026, 12, 25, 8, 30))
    assert d.data.GetValue() == "25/12/2026" and d.hora.GetValue() == "08:30"


def test_janela_das_agendadas_lista_muda_e_cancela(monkeypatch):
    ja, wx = _janelas()
    monkeypatch.setattr(ja.threading, "Thread", _ThreadNaHora)
    itens = [{"id": 7, "texto": "primeira",
              "quando": datetime(2026, 11, 12, 9, 0)},
             {"id": 8, "texto": "segunda",
              "quando": datetime(2026, 11, 13, 9, 0)}]
    pedidos, ditas = [], []
    d = ja.DialogoAgendadas(
        None, "Ana", lambda: list(itens),
        lambda x, q: pedidos.append(("mudar", x["id"], q)) or (True, ""),
        lambda x: pedidos.append(("cancelar", x["id"])) or (True, ""),
        falar=ditas.append, agora=lambda: AGORA)
    assert ditas[-1] == "2 mensagens agendadas para Ana."
    assert d.lista.GetString(0) == "amanhã às 09:00: primeira"
    assert d.lista.GetSelection() == 0
    # cancelar pede confirmacao
    respostas = [wx.NO, wx.YES]
    monkeypatch.setattr(ja.wx, "MessageBox", lambda *a, **k: respostas.pop(0))
    d._cancelar()
    assert pedidos == []                              # disse que nao
    d._cancelar()
    assert pedidos == [("cancelar", 7)] and "Envio cancelado." in ditas
    # mudar o horario usa a janela de data e hora
    quando = datetime(2026, 11, 20, 10, 0)

    class Horario:
        def __init__(self, *a, **k):
            pass

        def ShowModal(self):
            return wx.ID_OK

        def escolhido(self):
            return "segunda", quando

        def Destroy(self):
            pass
    monkeypatch.setattr(ja, "DialogoAgendar", Horario)
    d.lista.SetSelection(1)
    d._mudar()
    assert pedidos[-1] == ("mudar", 8, quando)
    assert any(t.startswith("Horário mudado para") for t in ditas)


def test_janela_das_agendadas_sem_nenhuma_e_com_erro(monkeypatch):
    ja, _ = _janelas()
    monkeypatch.setattr(ja.threading, "Thread", _ThreadNaHora)
    ditas = []
    ja.DialogoAgendadas(None, "Ana", lambda: [], None, None,
                        falar=ditas.append)
    assert ditas[-1] == "Nenhuma mensagem agendada para Ana."

    def falha():
        raise RuntimeError("O Telegram não respondeu.")
    ja.DialogoAgendadas(None, "Ana", falha, None, None, falar=ditas.append)
    assert ditas[-1] == "O Telegram não respondeu."


def test_janela_de_agendar_do_whatsapp_explica_o_limite(monkeypatch):
    ja, wx = _janelas()
    rotulos = []
    original = wx.StaticText

    class Texto(original):
        def __init__(self, pai=None, label="", **k):
            super().__init__(pai, label=label, **k)
            rotulos.append(label)
    monkeypatch.setattr(ja.wx, "StaticText", Texto)
    ja.DialogoAgendar(None, "Ana", "oi", local=True, agora=lambda: AGORA)
    assert any("precisa estar aberto e conectado" in r and
               "pergunta o que fazer" in r for r in rotulos)
    rotulos.clear()
    ja.DialogoAgendar(None, "Ana", "oi", local=False, agora=lambda: AGORA)
    assert any("mesmo com o TeleZapp fechado" in r for r in rotulos)
    assert not any("precisa estar aberto" in r for r in rotulos)


def test_linha_de_agendada_atrasada_diz_que_nao_foi_enviada():
    t = ag.linha("oi", datetime(2026, 11, 11, 9, 0), AGORA, atrasada=True)
    assert "passou da hora, não enviada" in t

import pytest

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


# ------------------------------------------- so com numeros e setas
HOJE = datetime(2026, 11, 11, 10, 20)


@pytest.mark.parametrize("texto,esperado", [
    ("25122026", date(2026, 12, 25)),
    ("251226", date(2026, 12, 25)),
    ("2512", date(2026, 12, 25)),
    ("0512", date(2026, 12, 5)),
    ("1011", date(2027, 11, 10)),          # ja passou neste ano
    ("25", date(2026, 11, 25)),
    ("11", date(2026, 11, 11)),            # hoje
    ("5", date(2026, 12, 5)),              # dia 5 deste mes ja passou
    ("30", date(2026, 11, 30)),
    ("112", None),                         # ambiguo
    ("32122026", None),
    ("31112026", None),                    # novembro nao tem 31
])
def test_data_so_com_numeros(texto, esperado):
    assert ag.interpretar_data(texto, HOJE.date()) == esperado


def test_dia_sem_mes_pula_para_o_mes_em_que_o_dia_existe():
    assert ag.interpretar_data("31", date(2026, 11, 11)) == date(2026, 12, 31)
    assert ag.interpretar_data("30", date(2027, 1, 31)) == date(2027, 3, 30)


def test_hora_so_com_numeros_e_montar():
    assert ag.interpretar_hora("1430") == (14, 30)
    assert ag.interpretar_hora("930") == (9, 30)
    assert ag.interpretar_hora("9") == (9, 0)
    quando, erro = ag.montar("25122026", "1430", HOJE)
    assert quando == datetime(2026, 12, 25, 14, 30) and erro == ""
    assert "números" in ag.montar("abc", "1430", HOJE)[1]


def test_mudar_data_com_as_setas():
    hoje = HOJE.date()
    assert ag.mudar_data("11/11/2026", 1, False, hoje) == (
        "12/11/2026", "amanhã, quinta-feira, 12/11/2026")
    assert ag.mudar_data("12/11/2026", -1, False, hoje) == (
        "11/11/2026", "hoje, quarta-feira, 11/11/2026")
    assert ag.mudar_data("10/11/2026", 1, False, hoje)[1].startswith("hoje")
    assert ag.mudar_data("11/11/2026", 1, False, hoje)[0] == "12/11/2026"
    # amanha, em palavras
    assert ag.mudar_data("hoje", 1, False, hoje)[1].startswith("amanhã")
    # Page Up anda uma semana
    assert ag.mudar_data("11/11/2026", 1, True, hoje)[0] == "18/11/2026"
    # nunca antes de hoje nem alem de um ano
    assert ag.mudar_data("11/11/2026", -1, False, hoje)[0] == "11/11/2026"
    assert ag.mudar_data("11/11/2027", 1, True, hoje)[0] == "11/11/2027"
    # sem data valida parte de hoje
    assert ag.mudar_data("xx", 1, False, hoje)[0] == "12/11/2026"
    # digitado so com numeros tambem
    assert ag.mudar_data("2512", 1, False, hoje)[0] == "26/12/2026"


def test_mudar_hora_com_as_setas():
    agora = HOJE
    assert ag.mudar_hora("14:30", 1, False, agora) == ("14:45", "14:45")
    assert ag.mudar_hora("14:30", -1, False, agora)[0] == "14:15"
    assert ag.mudar_hora("14:10", 1, False, agora)[0] == "14:15"   # ao quarto
    assert ag.mudar_hora("14:10", -1, False, agora)[0] == "14:00"
    assert ag.mudar_hora("14:00", -1, False, agora)[0] == "13:45"
    assert ag.mudar_hora("23:50", 1, False, agora)[0] == "00:00"   # da a volta
    assert ag.mudar_hora("00:00", -1, False, agora)[0] == "23:45"
    assert ag.mudar_hora("14:30", 1, True, agora)[0] == "15:30"    # Page Up
    assert ag.mudar_hora("23:30", 1, True, agora)[0] == "00:30"
    assert ag.mudar_hora("", 1, False, agora)[0] == "10:30"        # da atual


def test_setas_na_janela_de_agendar_mudam_o_campo_e_falam(monkeypatch):
    ja, wx = _janelas()
    falas = []
    d = ja.DialogoAgendar(None, "Ana", "oi", agora=lambda: HOJE,
                          falar=falas.append)

    class Tecla:
        def __init__(self, codigo, mod=False):
            self.codigo, self.mod, self.pulou = codigo, mod, False

        def GetKeyCode(self):
            return self.codigo

        def HasAnyModifiers(self):
            return self.mod

        def Skip(self):
            self.pulou = True
    d.data.SetValue("11/11/2026")
    d._tecla_da_data(Tecla(ja.wx.WXK_UP))
    assert d.data.GetValue() == "12/11/2026"
    assert falas[-1] == "amanhã, quinta-feira, 12/11/2026"
    d.hora.SetValue("14:30")
    d._tecla_da_hora(Tecla(ja.wx.WXK_DOWN))
    assert d.hora.GetValue() == "14:15" and falas[-1] == "14:15"
    d._tecla_da_hora(Tecla(ja.wx.WXK_PAGEUP))
    assert d.hora.GetValue() == "15:15"
    outra = Tecla(65)                         # outra tecla segue normal
    d._tecla_da_data(outra)
    assert outra.pulou and d.data.GetValue() == "12/11/2026"
    com_ctrl = Tecla(ja.wx.WXK_UP, mod=True)
    d._tecla_da_hora(com_ctrl)
    assert com_ctrl.pulou and d.hora.GetValue() == "15:15"

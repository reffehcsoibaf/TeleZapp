# SPDX-License-Identifier: GPL-3.0-or-later
"""Chamadas de voz: estados e textos (nucleo), o motor do Telegram com um
py-tgcalls simulado e o comportamento da janela principal."""
import asyncio
import sys
import types

import pytest

from testes import wx_falso

sys.modules.setdefault("wx", wx_falso)

from telezapp.nucleo import chamadas as ch  # noqa: E402
from telezapp.nucleo import eventos as ev  # noqa: E402
from telezapp.provedores import chamadas_telegram as ct  # noqa: E402


# ------------------------------------------------------------- nucleo
def test_duracao_para_mostrar_e_para_falar():
    assert ch.formatar_duracao(7) == "0:07"
    assert ch.formatar_duracao(723) == "12:03"
    assert ch.formatar_duracao(3765) == "1:02:45"
    assert ch.falar_duracao(0) == "0 segundos"
    assert ch.falar_duracao(1) == "1 segundo"
    assert ch.falar_duracao(185) == "3 minutos e 5 segundos"
    assert ch.falar_duracao(3600) == "1 hora"
    assert ch.falar_duracao(3725) == "1 hora, 2 minutos e 5 segundos"


def test_tocando_foca_atender_e_recusar_com_esc():
    c = ch.Chamada("t1", "10", "Ana", entrante=True, estado=ch.TOCANDO)
    a = ch.apresentar(c)
    assert a.botoes == (ch.ATENDER, ch.RECUSAR)
    assert a.foco == ch.ATENDER
    assert "Ana" in a.titulo and "Enter atende" in a.fala
    assert a.som == "toque"


def test_chamando_e_conectando_so_tem_desligar():
    c = ch.Chamada("t1", "10", "Ana")
    a = ch.apresentar(c)
    assert (a.botoes, a.foco, a.som) == ((ch.DESLIGAR,), ch.DESLIGAR,
                                         "chamando")
    c.aplicar(ch.CONECTANDO)
    assert ch.apresentar(c).botoes == (ch.DESLIGAR,)


def test_em_chamada_ordem_de_tab_e_foco_em_desligar():
    c = ch.Chamada("t1", "10", "Ana")
    c.aplicar(ch.EM_CHAMADA)
    a = ch.apresentar(c)
    assert a.botoes == (ch.SILENCIAR, ch.TEMPO, ch.DESLIGAR)
    assert a.foco == ch.DESLIGAR
    c.mudo = True
    assert "silenciado" in ch.apresentar(c).fala
    assert ch.rotulo_silenciar(True).endswith("microfone") is True
    assert ch.rotulo_silenciar(False) != ch.rotulo_silenciar(True)


def test_tempo_corre_so_em_chamada():
    t = [100.0]
    c = ch.Chamada("t1", "10", "Ana", _agora=lambda: t[0])
    assert c.segundos() == 0
    c.aplicar(ch.EM_CHAMADA)
    t[0] = 165.0
    assert c.segundos() == 65.0
    c.aplicar(ch.ENCERRADA, ch.DESLIGADA)
    assert c.segundos() == 0


def test_aplicar_devolve_se_mudou():
    c = ch.Chamada("t1", "10", "Ana")
    assert c.aplicar(ch.CHAMANDO) is False
    assert c.aplicar(ch.EM_CHAMADA) is True
    assert c.aplicar(ch.EM_CHAMADA) is False


@pytest.mark.parametrize("entrante,motivo,trecho", [
    (False, ch.RECUSADA, "recusou"),
    (True, ch.RECUSADA, "recusada"),
    (True, ch.PERDIDA, "perdida de Ana"),
    (False, ch.OCUPADO, "ocupado"),
    (False, ch.SEM_RESPOSTA, "não atendeu"),
    (False, ch.CANCELADA, "cancelada"),
    (False, ch.DESLIGADA, "encerrada"),
])
def test_textos_de_encerramento(entrante, motivo, trecho):
    c = ch.Chamada("t1", "10", "Ana", entrante=entrante)
    c.aplicar(ch.ENCERRADA, motivo)
    a = ch.apresentar(c)
    assert trecho in a.fala
    assert a.botoes == (ch.FECHAR,) and a.foco == ch.FECHAR


def test_falha_usa_a_explicacao():
    c = ch.Chamada("t1", "10", "Ana")
    c.aplicar(ch.ENCERRADA, ch.FALHA, "Esta pessoa não permite.")
    assert ch.apresentar(c).fala == "Esta pessoa não permite."


def test_motivo_da_excecao():
    class CallDeclined(Exception):
        pass

    class CallBusy(Exception):
        pass

    class TimedOutAnswer(Exception):
        pass

    class UserPrivacyRestrictedError(Exception):
        pass

    assert ch.motivo_da_excecao(CallDeclined())[0] == ch.RECUSADA
    assert ch.motivo_da_excecao(CallBusy())[0] == ch.OCUPADO
    assert ch.motivo_da_excecao(TimedOutAnswer())[0] == ch.SEM_RESPOSTA
    motivo, erro = ch.motivo_da_excecao(UserPrivacyRestrictedError())
    assert motivo == ch.FALHA and "privacidade" in erro
    assert ch.motivo_da_excecao(ValueError())[0] == ch.FALHA


# ---------------------------------------------- motor do Telegram (falso)
class Dispositivo:
    def __init__(self, titulo):
        self.title = titulo


class AppFalso:
    """Imita o que usamos do PyTgCalls."""

    def __init__(self, cliente):
        self.cliente = cliente
        self.handlers = {}
        self.chamadas = []           # (acao, chat_id, extra)
        self.erro_play = None
        self.atender_ao_tocar = True
        self._espera = None

    def on_update(self, filtro):
        def deco(f):
            self.handlers[filtro] = f
            return f
        return deco

    async def start(self):
        self.chamadas.append(("start", 0, None))

    async def play(self, chat_id, fluxo, config=None):
        self.chamadas.append(("play", chat_id, fluxo))
        if self.erro_play is not None:
            raise self.erro_play
        if not self.atender_ao_tocar:
            self._espera = asyncio.get_running_loop().create_future()
            await self._espera

    async def record(self, chat_id, fluxo):
        self.chamadas.append(("record", chat_id, fluxo))

    async def leave_call(self, chat_id):
        self.chamadas.append(("leave", chat_id, None))
        if self._espera is not None and not self._espera.done():
            self._espera.set_exception(asyncio.CancelledError())

    async def mute(self, chat_id):
        self.chamadas.append(("mute", chat_id, None))

    async def unmute(self, chat_id):
        self.chamadas.append(("unmute", chat_id, None))


class MotorFalso:
    app = None

    def __init__(self):
        MotorFalso.app = None
        self.filters = types.SimpleNamespace(
            chat_update=lambda estado: ("chat_update", estado))
        self.ChatUpdate = types.SimpleNamespace(Status=types.SimpleNamespace(
            INCOMING_CALL="entrada", LEFT_CALL="saiu"))
        self.CallConfig = lambda timeout=60: ("config", timeout)

    def PyTgCalls(self, cliente):
        MotorFalso.app = AppFalso(cliente)
        return MotorFalso.app

    def microfones(self):
        return [Dispositivo("Padrão"), Dispositivo("Headset")]

    def saidas(self):
        return [Dispositivo("Alto-falantes"), Dispositivo("Fones")]

    def fluxo_microfone(self, d):
        return ("mic", d.title)

    def fluxo_saida(self, d):
        return ("saida", d.title)


class Sala:
    def __init__(self):
        self.eventos = []
        b = ev.Barramento()
        b.ouvir(self.eventos.append)

        async def nome_de(chat_id):
            return "Ana"
        self.chamadas = ct.ChamadasTelegram(object(), "t1", b, nome_de,
                                            motor=MotorFalso, espera_s=1)

    def estados(self):
        return [(e.estado, e.motivo) for e in self.eventos
                if isinstance(e, ev.EstadoChamada)]


def rodar(corotina):
    return asyncio.run(corotina)


def test_ligar_e_conectar_publica_chamando_e_em_chamada():
    s = Sala()

    async def cena():
        assert await s.chamadas.iniciar()
        await s.chamadas.ligar(10, "Headset", "Fones")
    rodar(cena())
    assert s.estados() == [(ch.CHAMANDO, ""), (ch.EM_CHAMADA, "")]
    acoes = MotorFalso.app.chamadas
    assert ("play", 10, ("mic", "Headset")) in acoes
    assert ("record", 10, ("saida", "Fones")) in acoes
    assert s.eventos[0].nome == "Ana" and s.eventos[0].entrante is False


def test_dispositivo_desconhecido_cai_no_primeiro():
    s = Sala()

    async def cena():
        await s.chamadas.iniciar()
        await s.chamadas.ligar(10, "Sumiu", "")
    rodar(cena())
    assert ("play", 10, ("mic", "Padrão")) in MotorFalso.app.chamadas
    assert ("record", 10, ("saida", "Alto-falantes")) in \
        MotorFalso.app.chamadas


def test_falha_ao_ligar_encerra_com_motivo():
    class CallDeclined(Exception):
        pass
    s = Sala()

    async def cena():
        await s.chamadas.iniciar()
        MotorFalso.app.erro_play = CallDeclined()
        await s.chamadas.ligar(10)
    rodar(cena())
    assert s.estados()[-1] == (ch.ENCERRADA, ch.RECUSADA)
    assert s.chamadas.chamadas == {}


def test_chamada_recebida_atender_e_desligar():
    s = Sala()

    async def cena():
        await s.chamadas.iniciar()
        app = MotorFalso.app
        recebida = app.handlers[("chat_update", "entrada")]
        await recebida(None, types.SimpleNamespace(chat_id=10))
        await s.chamadas.atender(10, "", "")
        await s.chamadas.silenciar(10, True)
        await s.chamadas.encerrar(10)
    rodar(cena())
    assert s.estados() == [
        (ch.TOCANDO, ""), (ch.CONECTANDO, ""), (ch.EM_CHAMADA, ""),
        (ch.ENCERRADA, ch.DESLIGADA)]
    assert s.eventos[0].entrante is True
    acoes = [a for a, *_ in MotorFalso.app.chamadas]
    assert "mute" in acoes and "leave" in acoes


def test_recusar_chamada_que_toca():
    s = Sala()

    async def cena():
        await s.chamadas.iniciar()
        await MotorFalso.app.handlers[("chat_update", "entrada")](
            None, types.SimpleNamespace(chat_id=10))
        await s.chamadas.encerrar(10)
    rodar(cena())
    assert s.estados()[-1] == (ch.ENCERRADA, ch.RECUSADA)
    assert ("leave", 10, None) in MotorFalso.app.chamadas


def test_chamada_perdida_quando_o_outro_desiste():
    s = Sala()

    async def cena():
        await s.chamadas.iniciar()
        app = MotorFalso.app
        await app.handlers[("chat_update", "entrada")](
            None, types.SimpleNamespace(chat_id=10))
        await app.handlers[("chat_update", "saiu")](
            None, types.SimpleNamespace(chat_id=10))
    rodar(cena())
    assert s.estados()[-1] == (ch.ENCERRADA, ch.PERDIDA)


def test_outro_lado_desliga_durante_a_chamada():
    s = Sala()

    async def cena():
        await s.chamadas.iniciar()
        await s.chamadas.ligar(10)
        await MotorFalso.app.handlers[("chat_update", "saiu")](
            None, types.SimpleNamespace(chat_id=10))
    rodar(cena())
    assert s.estados()[-1] == (ch.ENCERRADA, ch.DESLIGADA)


def test_segunda_chamada_e_recusada_sem_avisar():
    s = Sala()

    async def cena():
        await s.chamadas.iniciar()
        await s.chamadas.ligar(10)
        await MotorFalso.app.handlers[("chat_update", "entrada")](
            None, types.SimpleNamespace(chat_id=20))
    rodar(cena())
    assert ("leave", 20, None) in MotorFalso.app.chamadas
    assert all(e.conversa_id == "10" for e in s.eventos
               if isinstance(e, ev.EstadoChamada))


def test_trocar_dispositivos_no_meio_da_chamada():
    s = Sala()

    async def cena():
        await s.chamadas.iniciar()
        await s.chamadas.ligar(10, "Padrão", "Alto-falantes")
        await s.chamadas.trocar_dispositivos(10, "Headset", "")
    rodar(cena())
    plays = [x for x in MotorFalso.app.chamadas if x[0] == "play"]
    assert plays[-1] == ("play", 10, ("mic", "Headset"))


def test_sem_pytgcalls_as_chamadas_ficam_desligadas():
    def sem_biblioteca():
        raise ImportError("pytgcalls")
    s = Sala()
    s.chamadas._motor_fabrica = sem_biblioteca
    assert rodar(s.chamadas.iniciar()) is False
    assert not s.chamadas.pronta
    assert s.chamadas.dispositivos() == ([], [])
    rodar(s.chamadas.ligar(10))     # nao faz nada, nao quebra
    assert s.eventos == []


def test_dispositivos_nao_tocam_na_ntgcalls_fora_da_thread_do_provedor():
    """Listar na thread da interface derruba o processo (COM do wx contra
    o da NTgCalls): `dispositivos()` so devolve o que a thread do provedor
    ja listou."""
    s = Sala()
    chamadas_de_listagem = []

    class Contador(MotorFalso):
        def microfones(self):
            chamadas_de_listagem.append("mic")
            return super().microfones()

    s.chamadas._motor_fabrica = Contador

    async def cena():
        await s.chamadas.iniciar()
    rodar(cena())
    feitas = len(chamadas_de_listagem)
    assert feitas >= 1
    assert s.chamadas.dispositivos() == (["Padrão", "Headset"],
                                         ["Alto-falantes", "Fones"])
    assert len(chamadas_de_listagem) == feitas      # nada novo


# ------------------------------------------------------------------ video
class MotorFalsoComVideo(MotorFalso):
    def __init__(self):
        super().__init__()
        self.com_camera = True
        self.filters.stream_frame = lambda *a: ("quadros",)
        MotorFalsoComVideo.pedidos = None

    def cameras(self):
        return [Dispositivo("Câmera A"), Dispositivo("Câmera B")] \
            if self.com_camera else []

    def fluxo_com_camera(self, camera, microfone):
        return ("camera+mic", camera.title, microfone.title)

    def filtro_quadros(self):
        return ("quadros",)

    def ouvir_pedidos(self, cliente, ao_pedido):
        MotorFalsoComVideo.pedidos = ao_pedido

    def fluxo_saida(self, d, camera=False):
        return ("saida", d.title) + (("camera",) if camera else ())


def sala_com_video(com_camera=True):
    s = Sala()
    s.chamadas._motor_fabrica = MotorFalsoComVideo
    s.quadros = []
    s.chamadas.destino_video = lambda *a: s.quadros.append(a)
    return s


def quadro_bgra(largura=4, altura=2, rotacao=0):
    return types.SimpleNamespace(
        chat_id=10, frames=[types.SimpleNamespace(
            frame=bytes([10, 20, 30, 255]) * (largura * altura),
            info=types.SimpleNamespace(
                width=largura, height=altura,
                rotation=types.SimpleNamespace(value=rotacao)))])


def ultimo(s):
    return [e for e in s.eventos if isinstance(e, ev.EstadoChamada)][-1]


def test_ligar_com_video_manda_camera_e_microfone_e_recebe_a_camera():
    s = sala_com_video()

    async def cena():
        await s.chamadas.iniciar()
        await s.chamadas.ligar(10, "Headset", "Fones", video=True,
                               camera="Câmera B")
    rodar(cena())
    acoes = MotorFalso.app.chamadas
    assert ("play", 10, ("camera+mic", "Câmera B", "Headset")) in acoes
    assert ("record", 10, ("saida", "Fones", "camera")) in acoes
    e = ultimo(s)
    assert e.video and e.camera and e.suporta_video
    assert s.chamadas.cameras() == ["Câmera A", "Câmera B"]


def test_ligar_com_video_sem_camera_liga_so_a_voz_e_avisa():
    s = sala_com_video()

    async def cena():
        await s.chamadas.iniciar()
        s.chamadas.motor.com_camera = False
        s.chamadas._cameras = []
        await s.chamadas.ligar(10, "", "", video=True, camera="")
    rodar(cena())
    assert ("play", 10, ("mic", "Padrão")) in MotorFalso.app.chamadas
    assert not ultimo(s).video
    assert any(isinstance(e, ev.Aviso) and "câmera" in e.texto
               for e in s.eventos)


def test_chamada_recebida_de_video_vem_marcada_e_atende_sem_camera():
    s = sala_com_video()

    async def cena():
        await s.chamadas.iniciar()
        await MotorFalsoComVideo.pedidos(10, True)       # evento bruto
        await MotorFalso.app.handlers[("chat_update", "entrada")](
            None, types.SimpleNamespace(chat_id=10))
        assert ultimo(s).video and ultimo(s).entrante
        await s.chamadas.atender(10, "", "", camera=None)
    rodar(cena())
    acoes = MotorFalso.app.chamadas
    assert ("play", 10, ("mic", "Padrão")) in acoes           # sem camera
    assert ("record", 10, ("saida", "Alto-falantes", "camera")) in acoes
    assert not ultimo(s).camera and ultimo(s).video


def test_atender_chamada_de_video_com_camera():
    s = sala_com_video()

    async def cena():
        await s.chamadas.iniciar()
        await MotorFalso.app.handlers[("chat_update", "entrada")](
            None, types.SimpleNamespace(chat_id=10))
        await MotorFalsoComVideo.pedidos(10, True)       # chega depois
        await s.chamadas.atender(10, "", "", camera="")
    rodar(cena())
    assert ("play", 10, ("camera+mic", "Câmera A", "Padrão")) in \
        MotorFalso.app.chamadas
    assert ultimo(s).camera


def test_quadro_do_outro_lado_vai_para_a_janela_e_marca_video_remoto():
    s = sala_com_video()

    async def cena():
        await s.chamadas.iniciar()
        await s.chamadas.ligar(10, video=True, camera="")
        await s.chamadas._ao_quadro(None, quadro_bgra())
    rodar(cena())
    cid, largura, altura, rgb = s.quadros[0]
    assert (cid, largura, altura) == ("10", 4, 2)
    assert rgb[:3] == bytes([30, 20, 10])               # BGRA -> RGB
    assert ultimo(s).video_remoto


def test_quadro_girado_troca_largura_e_altura():
    s = sala_com_video()

    async def cena():
        await s.chamadas.iniciar()
        await s.chamadas.ligar(10, video=True, camera="")
        await s.chamadas._ao_quadro(None, quadro_bgra(4, 2, rotacao=90))
    rodar(cena())
    assert s.quadros[0][1:3] == (2, 4)


def test_sem_quadros_o_outro_lado_desligou_a_camera(monkeypatch):
    s = sala_com_video()
    monkeypatch.setattr(ct, "SEM_QUADROS_S", 0.05)

    async def cena():
        await s.chamadas.iniciar()
        await s.chamadas.ligar(10, video=True, camera="")
        await s.chamadas._ao_quadro(None, quadro_bgra())
        assert ultimo(s).video_remoto
        await asyncio.sleep(1.2)
    rodar(cena())
    assert not ultimo(s).video_remoto and ultimo(s).video


def test_ligar_e_desligar_a_camera_no_meio_de_uma_chamada_de_voz():
    s = sala_com_video()

    async def cena():
        await s.chamadas.iniciar()
        await s.chamadas.ligar(10, "", "")
        assert not ultimo(s).video
        await s.chamadas.ligar_camera(10, "Câmera B")
        assert ultimo(s).video and ultimo(s).camera
        await s.chamadas.desligar_camera(10)
    rodar(cena())
    plays = [x for x in MotorFalso.app.chamadas if x[0] == "play"]
    assert plays[-2] == ("play", 10, ("camera+mic", "Câmera B", "Padrão"))
    assert plays[-1] == ("play", 10, ("mic", "Padrão"))
    assert ultimo(s).video and not ultimo(s).camera


def test_formato_desconhecido_de_quadro_nao_quebra():
    s = sala_com_video()

    async def cena():
        await s.chamadas.iniciar()
        await s.chamadas.ligar(10, video=True, camera="")
        ruim = quadro_bgra()
        ruim.frames[0].frame = b"abc"
        await s.chamadas._ao_quadro(None, ruim)
    rodar(cena())
    assert s.quadros == []

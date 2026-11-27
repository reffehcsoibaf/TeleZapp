# SPDX-License-Identifier: GPL-3.0-or-later
"""Chamadas de voz do WhatsApp: o estado publicado, com uma ponte (a DLL) e
um audio de mentira."""
import queue
import time

import pytest

from telezapp.nucleo import chamadas as ch
from telezapp.nucleo import eventos as ev
from telezapp.provedores import chamadas_whatsapp as cw

QUADRO = bytes(cw.BYTES_POR_QUADRO)
CID = "5551@s.whatsapp.net"


class Barramento:
    def __init__(self):
        self.eventos = []

    def publicar(self, e):
        self.eventos.append(e)

    def estados(self):
        return [(e.estado, e.motivo) for e in self.eventos
                if isinstance(e, ev.EstadoChamada)]


class PonteFalsa:
    def __init__(self):
        self.fila = queue.Queue()
        self.ligadas = []
        self.atendidas = []
        self.desligadas = []
        self.erro_ao_ligar = ""
        self.escritos = 0
        self.recebidos = queue.Queue()
        self.fim = False
        self.acoes_de_video = []
        self.unidades_enviadas = []
        self.video_recebido = queue.Queue()
        self.ligadas_com_video = []

    def ligada(self):
        return True

    def proximo_evento(self, espera_ms=500):
        try:
            return self.fila.get(timeout=min(espera_ms, 50) / 1000)
        except queue.Empty:
            return None

    def suporta_video(self):
        return True

    def video(self, chamada, acao):
        self.acoes_de_video.append((chamada, acao))
        return True

    def escrever_video(self, chamada, unidade, duracao_ms=100):
        self.unidades_enviadas.append(unidade)
        return True

    def ler_video(self, chamada, espera_ms=500):
        if self.fim:
            return False
        try:
            return self.video_recebido.get(timeout=0.02)
        except queue.Empty:
            return None

    def ligar(self, destino, video=False):
        self.ligadas_com_video.append(video)
        self.ligadas.append(destino)
        if self.erro_ao_ligar:
            return "", "", self.erro_ao_ligar
        return "C1", "999@lid", ""

    def atender(self, chamada):
        self.atendidas.append(chamada)
        return True

    def desligar(self, chamada):
        self.desligadas.append(chamada)
        return True

    def ler_quadro(self, chamada, espera_ms=100):
        if self.fim:
            return False
        try:
            return self.recebidos.get(timeout=0.02)
        except queue.Empty:
            return None

    def escrever_quadro(self, chamada, dados):
        self.escritos += 1
        return True


class Fluxo:
    def __init__(self):
        self.escrito = []

    def read(self, n):
        time.sleep(0.005)
        return b"\x01" * cw.BYTES_POR_QUADRO, False

    def write(self, dados):
        self.escrito.append(dados)

    def stop(self):
        pass

    def close(self):
        pass


class AudioFalso:
    def __init__(self):
        self.microfones_abertos = []
        self.saidas_abertas = []
        self.saidas = []

    def listar(self):
        return ["Mic A", "Mic B"], ["Saida A"]

    def abrir_microfone(self, nome):
        self.microfones_abertos.append(nome)
        return Fluxo()

    def abrir_saida(self, nome):
        self.saidas_abertas.append(nome)
        f = Fluxo()
        self.saidas.append(f)
        return f


def esperar(cond, limite=3.0):
    fim = time.time() + limite
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture(autouse=True)
def sem_eco_por_padrao():
    """Os testes de chamada nao dependem do processamento de eco."""
    cw.midia_eco.definir(False, False, False)
    yield
    cw.midia_eco.definir(True, True, True)


@pytest.fixture
def mundo():
    ponte, barramento, audio = PonteFalsa(), Barramento(), AudioFalso()
    v = cw.ChamadasWhatsApp(
        ponte, "w1", barramento,
        conversa_do_peer=lambda peer: CID,
        nome_de=lambda cid: "Ana",
        destino_de=lambda cid: "5551",
        audio=audio, espera_s=0.3)
    v.iniciar()
    yield v, ponte, barramento, audio
    v.parar()
    ponte.fim = True


def chamada_recebida(ponte, bus, call="R1"):
    ponte.fila.put({"ev": "incoming", "call": call, "peer": "1@lid"})
    assert esperar(lambda: bus.estados())


def test_ligar_publica_chamando_e_em_chamada_com_audio(mundo):
    v, ponte, bus, audio = mundo
    v.ligar(CID, "Mic B", "Saida A")
    assert esperar(lambda: ponte.ligadas)
    assert ponte.ligadas == ["5551"]
    assert bus.estados()[0] == (ch.CHAMANDO, "")
    ponte.fila.put({"ev": "ready", "call": "C1"})
    assert esperar(lambda: (ch.EM_CHAMADA, "") in bus.estados())
    assert esperar(lambda: ponte.escritos > 3)
    ponte.recebidos.put(QUADRO)
    assert esperar(lambda: audio.saidas and audio.saidas[0].escrito)
    assert audio.microfones_abertos == ["Mic B"]
    assert audio.saidas_abertas == ["Saida A"]


def test_eco_limpa_o_microfone_e_recebe_o_que_toca_como_referencia(
        mundo, monkeypatch):
    v, ponte, bus, audio = mundo
    visto = {"ref": [], "mic": 0}

    class EcoFalso:
        def __init__(self, eco, ruido):
            visto["args"] = (eco, ruido)

        def referencia(self, pcm):
            visto["ref"].append(pcm)

        def processar(self, pcm):
            visto["mic"] += 1
            return b"" * len(pcm)

        def diagnostico(self):
            return {}

        def reiniciar(self):
            visto["reiniciou"] = True
    monkeypatch.setattr(cw.midia_eco, "CancelaEco", EcoFalso)
    cw.midia_eco.definir(True, False)
    enviados = []
    ponte.escrever_quadro = lambda c, d: enviados.append(d) or True
    chamada_recebida(ponte, bus)
    v.atender(CID, "Mic A", "Saida A")
    ponte.fila.put({"ev": "ready", "call": "R1"})
    assert esperar(lambda: len(enviados) > 2)
    assert visto["args"] == (True, False)
    assert enviados[-1] == b"" * cw.BYTES_POR_QUADRO
    ponte.recebidos.put(QUADRO)
    assert esperar(lambda: visto["ref"] == [QUADRO])
    v.trocar_dispositivos(CID, saida="Saida A")
    assert esperar(lambda: visto.get("reiniciou"))
    # mudo: segue o silencio, sem passar pelo processamento
    v.silenciar(CID, True)
    antes = visto["mic"]
    enviados.clear()
    assert esperar(lambda: len(enviados) > 2)
    assert all(d == bytes(cw.BYTES_POR_QUADRO) for d in enviados[-2:])
    assert visto["mic"] - antes <= 2


def test_falha_do_eco_manda_o_quadro_como_veio(mundo, monkeypatch):
    v, ponte, bus, _ = mundo

    class Quebrado:
        def __init__(self, eco, ruido):
            pass

        def referencia(self, pcm):
            pass

        def processar(self, pcm):
            raise RuntimeError("falhou")

        def reiniciar(self):
            pass
    monkeypatch.setattr(cw.midia_eco, "CancelaEco", Quebrado)
    cw.midia_eco.definir(True, True, False)
    enviados = []
    ponte.escrever_quadro = lambda c, d: enviados.append(d) or True
    chamada_recebida(ponte, bus)
    v.atender(CID)
    ponte.fila.put({"ev": "ready", "call": "R1"})
    assert esperar(lambda: len(enviados) > 2)
    assert enviados[-1] == b"" * cw.BYTES_POR_QUADRO     # como captado
    assert v.ligacoes[CID].eco is None


def test_falha_ao_ligar_encerra_com_a_explicacao(mundo):
    v, ponte, bus, _ = mundo
    ponte.erro_ao_ligar = "o número não está no WhatsApp"
    v.ligar(CID)
    assert esperar(lambda: bus.estados()[-1][0] == ch.ENCERRADA)
    ult = bus.eventos[-1]
    assert ult.motivo == ch.FALHA and "não está no WhatsApp" in ult.erro
    assert v.ligacoes == {}


def test_outro_lado_recusa(mundo):
    v, ponte, bus, _ = mundo
    v.espera_s = 30
    v.ligar(CID)
    assert esperar(lambda: getattr(v.ligacoes.get(CID), "call_id", "") == "C1")
    ponte.fila.put({"ev": "end", "call": "C1", "reason": "rejected"})
    assert esperar(lambda: bus.estados()[-1] == (ch.ENCERRADA, ch.RECUSADA))


def test_ninguem_atende_desliga_com_sem_resposta(mundo):
    v, ponte, bus, _ = mundo
    v.ligar(CID)
    assert esperar(lambda: ponte.desligadas == ["C1"])
    ponte.fila.put({"ev": "end", "call": "C1", "reason": "hangup"})
    assert esperar(lambda: bus.estados()[-1] == (ch.ENCERRADA,
                                                 ch.SEM_RESPOSTA))


def test_chamada_recebida_atender_e_desligar(mundo):
    v, ponte, bus, _ = mundo
    chamada_recebida(ponte, bus)
    assert bus.estados() == [(ch.TOCANDO, "")]
    assert bus.eventos[0].entrante and bus.eventos[0].nome == "Ana"
    v.atender(CID, "Mic A", "Saida A")
    assert ponte.atendidas == ["R1"]
    assert bus.estados()[-1] == (ch.CONECTANDO, "")
    ponte.fila.put({"ev": "ready", "call": "R1"})
    assert esperar(lambda: bus.estados()[-1] == (ch.EM_CHAMADA, ""))
    v.encerrar(CID)
    assert ponte.desligadas == ["R1"]
    ponte.fila.put({"ev": "end", "call": "R1", "reason": "hangup"})
    assert esperar(lambda: bus.estados()[-1] == (ch.ENCERRADA, ch.DESLIGADA))


def test_oferta_velha_nao_toca_nem_desliga(mundo):
    v, ponte, bus, _ = mundo
    v.oferta_velha = lambda chamada: chamada == "R0"
    ponte.fila.put({"ev": "incoming", "call": "R0", "peer": "1@lid"})
    ponte.fila.put({"ev": "incoming", "call": "R1", "peer": "1@lid"})
    assert esperar(lambda: bus.estados() == [(ch.TOCANDO, "")])
    assert v.ligacoes[CID].call_id == "R1"
    assert ponte.desligadas == []


def test_recusar_e_chamada_perdida(mundo):
    v, ponte, bus, _ = mundo
    chamada_recebida(ponte, bus)
    v.encerrar(CID)
    ponte.fila.put({"ev": "end", "call": "R1", "reason": "rejected"})
    assert esperar(lambda: bus.estados()[-1] == (ch.ENCERRADA, ch.RECUSADA))

    ponte.fila.put({"ev": "incoming", "call": "R2", "peer": "1@lid"})
    assert esperar(lambda: bus.estados()[-1] == (ch.TOCANDO, ""))
    ponte.fila.put({"ev": "end", "call": "R2", "reason": "timeout"})
    assert esperar(lambda: bus.estados()[-1] == (ch.ENCERRADA, ch.PERDIDA))


def test_segunda_chamada_e_recusada_sem_avisar(mundo):
    v, ponte, bus, _ = mundo
    chamada_recebida(ponte, bus)
    ponte.fila.put({"ev": "incoming", "call": "R2", "peer": "2@lid"})
    assert esperar(lambda: "R2" in ponte.desligadas)
    assert len(bus.estados()) == 1


def test_silenciar_manda_silencio(mundo):
    v, ponte, bus, audio = mundo
    chamada_recebida(ponte, bus)
    v.atender(CID)
    ponte.fila.put({"ev": "ready", "call": "R1"})
    assert esperar(lambda: ponte.escritos > 2)
    v.silenciar(CID, True)
    assert v.ligacoes[CID].chamada.mudo is True
    enviados = []
    ponte.escrever_quadro = lambda c, d: enviados.append(d) or True
    assert esperar(lambda: len(enviados) > 2)
    assert all(d == QUADRO for d in enviados)


def test_trocar_dispositivos_reabre_so_o_que_mudou(mundo):
    v, ponte, bus, audio = mundo
    chamada_recebida(ponte, bus)
    v.atender(CID, "Mic A", "Saida A")
    ponte.fila.put({"ev": "ready", "call": "R1"})
    assert esperar(lambda: audio.microfones_abertos and audio.saidas_abertas)
    v.trocar_dispositivos(CID, microfone="Mic B")
    assert esperar(lambda: audio.microfones_abertos == ["Mic A", "Mic B"])
    assert audio.saidas_abertas == ["Saida A"]


def test_falha_do_servidor_vira_explicacao(mundo):
    v, ponte, bus, _ = mundo
    chamada_recebida(ponte, bus)
    v.atender(CID)
    ponte.fila.put({"ev": "end", "call": "R1", "reason": "server:403"})
    assert esperar(lambda: bus.estados()[-1][0] == ch.ENCERRADA)
    assert "403" in bus.eventos[-1].erro


def test_dispositivos_listados(mundo):
    v, *_ = mundo
    assert v.dispositivos() == (["Mic A", "Mic B"], ["Saida A"])


def test_ponte_sem_a_dll_nao_esta_disponivel():
    class SemChamadas:
        pass
    assert cw.Ponte.disponivel(SemChamadas()) is False


def test_dispositivo_que_nao_abre_cai_no_padrao_do_windows(mundo):
    v, ponte, bus, audio = mundo
    abrir_mic, abrir_saida = audio.abrir_microfone, audio.abrir_saida

    def mic(nome):
        if nome == "Mic quebrado":
            raise OSError("não abriu")
        return abrir_mic(nome)

    def saida(nome):
        if nome == "Saida quebrada":
            raise OSError("não abriu")
        return abrir_saida(nome)
    audio.abrir_microfone, audio.abrir_saida = mic, saida
    v.ligar(CID, "Mic quebrado", "Saida quebrada")
    assert esperar(lambda: ponte.ligadas)
    ponte.fila.put({"ev": "ready", "call": "C1"})
    assert esperar(lambda: audio.microfones_abertos == [""])
    assert esperar(lambda: audio.saidas_abertas == [""])
    assert esperar(lambda: ponte.escritos > 3)       # o microfone segue


def test_erro_passageiro_no_som_nao_derruba_a_chamada(mundo):
    v, ponte, bus, audio = mundo
    abrir_mic = audio.abrir_microfone
    tentativas = []

    def mic(nome):
        tentativas.append(nome)
        if len(tentativas) == 1:
            raise OSError("dispositivo ocupado")
        return abrir_mic(nome)
    audio.abrir_microfone = mic
    v.ligar(CID)
    assert esperar(lambda: ponte.ligadas)
    ponte.fila.put({"ev": "ready", "call": "C1"})
    assert esperar(lambda: ponte.escritos > 3, 5.0)  # voltou sozinho
    assert len(tentativas) >= 2


def test_atendida_mostra_conectando_e_abre_o_som_antes_do_ready(mundo):
    v, ponte, bus, audio = mundo
    v.ligar(CID, "Mic B", "Saida A")
    assert esperar(lambda: ponte.ligadas)
    # a fase 3 da saida vem com o relay, ainda tocando: nao muda nada
    ponte.fila.put({"ev": "state", "call": "C1", "phase": 3})
    time.sleep(0.2)
    assert (ch.CONECTANDO, "") not in bus.estados() and not         audio.microfones_abertos
    ponte.fila.put({"ev": "accepted", "call": "C1"})
    assert esperar(lambda: (ch.CONECTANDO, "") in bus.estados())
    assert esperar(lambda: audio.microfones_abertos == ["Mic B"])
    ponte.fila.put({"ev": "ready", "call": "C1"})
    assert esperar(lambda: (ch.EM_CHAMADA, "") in bus.estados())
    assert audio.microfones_abertos == ["Mic B"]    # nao abriu duas vezes


def test_atendida_sem_som_do_outro_lado_encerra_explicando(mundo):
    v, ponte, bus, audio = mundo
    v.espera_audio_s = 0.3
    v.ligar(CID)
    assert esperar(lambda: ponte.ligadas)
    ponte.fila.put({"ev": "accepted", "call": "C1"})
    assert esperar(lambda: ponte.desligadas == ["C1"], 3.0)
    ponte.fila.put({"ev": "end", "call": "C1", "reason": "hangup"})
    assert esperar(lambda: (ch.ENCERRADA, ch.FALHA) in bus.estados())
    final = [e for e in bus.eventos if isinstance(e, ev.EstadoChamada)][-1]
    assert "som do outro lado não chegou" in final.erro


def test_saida_que_so_esta_tocando_nao_e_encerrada_pelo_vigia(mundo):
    v, ponte, bus, audio = mundo
    v.espera_audio_s = 0.2
    v.espera_s = 5.0                      # o tempo de tocar e outro
    v.ligar(CID)
    assert esperar(lambda: ponte.ligadas)
    ponte.fila.put({"ev": "state", "call": "C1", "phase": 3})
    time.sleep(0.6)                       # bem mais que o prazo do som
    assert not ponte.desligadas
    assert (ch.ENCERRADA, ch.FALHA) not in bus.estados()


def test_entrada_atendida_sem_som_encerra_explicando(mundo):
    v, ponte, bus, audio = mundo
    v.espera_audio_s = 0.3
    chamada_recebida(ponte, bus)
    v.atender(CID)
    assert esperar(lambda: ponte.desligadas == ["R1"], 3.0)
    ponte.fila.put({"ev": "end", "call": "R1", "reason": "hangup"})
    assert esperar(lambda: (ch.ENCERRADA, ch.FALHA) in bus.estados())


def test_entrada_sem_som_liga_de_volta_para_a_mesma_pessoa(mundo):
    v, ponte, bus, audio = mundo
    v.espera_audio_s = 0.3
    chamada_recebida(ponte, bus)
    v.atender(CID)
    assert esperar(lambda: ponte.desligadas == ["R1"], 3.0)
    ponte.fila.put({"ev": "end", "call": "R1", "reason": "hangup"})
    assert esperar(lambda: ponte.ligadas == ["5551"], 5.0)
    assert (ch.ENCERRADA, ch.FALHA) in bus.estados()
    assert esperar(lambda: (ch.CHAMANDO, "") in bus.estados())


def test_entrada_sem_som_nao_liga_de_volta_com_a_opcao_desligada(mundo):
    v, ponte, bus, audio = mundo
    cw.definir_retornar_sem_audio(False)
    try:
        v.espera_audio_s = 0.3
        chamada_recebida(ponte, bus)
        v.atender(CID)
        assert esperar(lambda: ponte.desligadas == ["R1"], 3.0)
        ponte.fila.put({"ev": "end", "call": "R1", "reason": "hangup"})
        assert esperar(lambda: (ch.ENCERRADA, ch.FALHA) in bus.estados())
        time.sleep(1.0)
        assert ponte.ligadas == []
    finally:
        cw.definir_retornar_sem_audio(True)


def test_saida_sem_som_nao_liga_de_volta_em_laco(mundo):
    v, ponte, bus, audio = mundo
    v.espera_audio_s = 0.3
    v.ligar(CID)
    assert esperar(lambda: ponte.ligadas)
    ponte.fila.put({"ev": "accepted", "call": "C1"})
    assert esperar(lambda: ponte.desligadas == ["C1"], 3.0)
    ponte.fila.put({"ev": "end", "call": "C1", "reason": "hangup"})
    time.sleep(1.0)
    assert ponte.ligadas == ["5551"]            # so a original


# ------------------------------------------------------------------ video
class VideoFalso:
    """No lugar de midia.video: sem camera nem codec de verdade."""
    QUADRO_MS = 100

    def __init__(self):
        self.cameras_abertas = []
        self.decodificados = []
        self.quadros_decodificados = [(4, 2, b"\x01" * 24)]

    def disponivel(self):
        return True

    def listar_cameras(self):
        return ["Câmera A", "Câmera B"]

    class Codificador:
        def __init__(self):
            self.chaves = 0

        def codificar(self, quadro):
            return [b"\x00\x00\x01au" + quadro]

        def pedir_quadro_chave(self):
            self.chaves += 1

        def fechar(self):
            pass

    def Decodificador(self):
        video = self

        class D:
            def decodificar(self, unidade):
                video.decodificados.append(unidade)
                return video.quadros_decodificados
        return D()

    def Camera(self, nome, ao_quadro):
        video = self

        class C:
            def iniciar(self):
                video.cameras_abertas.append(nome)
                ao_quadro(b"quadro")

            def parar(self):
                video.camera_parada = True
        return C()


@pytest.fixture
def mundo_video(mundo):
    v, ponte, bus, audio = mundo
    v.video = VideoFalso()
    quadros = []
    v.destino_video = lambda cid, l, a, rgb: quadros.append((cid, l, a, rgb))
    return v, ponte, bus, quadros


def ultimo_estado(bus):
    return [e for e in bus.eventos if isinstance(e, ev.EstadoChamada)][-1]


def test_ligar_com_video_liga_a_camera_e_manda_o_video(mundo_video):
    v, ponte, bus, _ = mundo_video
    v.ligar(CID, "", "", video=True, camera="Câmera B")
    assert esperar(lambda: ponte.ligadas)
    assert ponte.ligadas_com_video == [True]
    ponte.fila.put({"ev": "ready", "call": "C1"})
    assert esperar(lambda: v.video.cameras_abertas == ["Câmera B"])
    assert esperar(lambda: ponte.unidades_enviadas)
    e = ultimo_estado(bus)
    assert e.video and e.camera and e.suporta_video


def test_video_do_outro_lado_chega_decodificado_a_janela(mundo_video):
    v, ponte, bus, quadros = mundo_video
    v.ligar(CID, video=True)
    assert esperar(lambda: ponte.ligadas)
    ponte.fila.put({"ev": "ready", "call": "C1"})
    assert esperar(lambda: v.ligacoes[CID].recebendo_video)
    ponte.video_recebido.put(b"\x00\x00\x00\x01unidade")
    assert esperar(lambda: quadros)
    assert quadros[0] == (CID, 4, 2, b"\x01" * 24)
    assert esperar(lambda: ultimo_estado(bus).video_remoto)


def test_chamada_recebida_de_video_vem_marcada(mundo_video):
    v, ponte, bus, _ = mundo_video
    ponte.fila.put({"ev": "incoming", "call": "R1", "peer": "1@lid",
                    "video": True})
    assert esperar(lambda: bus.eventos)
    assert ultimo_estado(bus).video
    v.atender(CID, "", "", camera=None)          # atende sem camera
    ponte.fila.put({"ev": "ready", "call": "R1"})
    assert esperar(lambda: (ch.EM_CHAMADA, "") in bus.estados())
    assert esperar(lambda: v.ligacoes[CID].recebendo_video)
    assert v.video.cameras_abertas == []
    assert not ultimo_estado(bus).camera


def test_pedido_de_video_do_outro_lado_e_aceito(mundo_video):
    v, ponte, bus, _ = mundo_video
    chamada_recebida(ponte, bus, "R1")
    v.atender(CID)
    ponte.fila.put({"ev": "ready", "call": "R1"})
    assert esperar(lambda: (ch.EM_CHAMADA, "") in bus.estados())
    ponte.fila.put({"ev": "video", "call": "R1", "active": False,
                    "upgrade": True})
    assert esperar(lambda: ("R1", cw.VIDEO_ACEITAR) in ponte.acoes_de_video)
    assert esperar(lambda: ultimo_estado(bus).video)


def test_ligar_a_camera_numa_chamada_de_voz_pede_video(mundo_video):
    v, ponte, bus, _ = mundo_video
    v.ligar(CID)
    assert esperar(lambda: ponte.ligadas)
    ponte.fila.put({"ev": "ready", "call": "C1"})
    assert esperar(lambda: (ch.EM_CHAMADA, "") in bus.estados())
    v.ligar_camera(CID, "Câmera A")
    assert ("C1", cw.VIDEO_PEDIR) in ponte.acoes_de_video
    assert v.video.cameras_abertas == ["Câmera A"]
    v.desligar_camera(CID)
    assert ("C1", cw.VIDEO_DESLIGAR) in ponte.acoes_de_video
    assert not ultimo_estado(bus).camera and ultimo_estado(bus).video


def test_pedido_de_quadro_chave_chega_ao_codificador(mundo_video):
    v, ponte, bus, _ = mundo_video
    v.ligar(CID, video=True, camera="")
    assert esperar(lambda: ponte.ligadas)
    ponte.fila.put({"ev": "ready", "call": "C1"})
    assert esperar(lambda: v.ligacoes[CID].codificador is not None)
    ponte.fila.put({"ev": "keyframe", "call": "C1"})
    assert esperar(lambda: v.ligacoes[CID].codificador.chaves == 1)


def test_camera_para_quando_a_chamada_acaba(mundo_video):
    v, ponte, bus, _ = mundo_video
    v.ligar(CID, video=True, camera="")
    assert esperar(lambda: ponte.ligadas)
    ponte.fila.put({"ev": "ready", "call": "C1"})
    assert esperar(lambda: v.video.cameras_abertas)
    ponte.fila.put({"ev": "end", "call": "C1", "reason": ""})
    assert esperar(lambda: getattr(v.video, "camera_parada", False))


def test_diagnostico_do_alto_falante_registra_e_grava_pilhas(caplog):
    import logging
    from telezapp.provedores import chamadas_whatsapp as cw
    relogio = [0.0]
    d = cw._DiagnosticoDoAltoFalante("C1", agora=lambda: relogio[0])
    with caplog.at_level(logging.INFO):
        d.periodo()                       # ainda dentro dos 5 s: nada
        assert not caplog.records
        for _ in range(3):
            d.tocou(0.01, 0.02)
        d.leitura = 1.5
        relogio[0] = 6.0
        d.periodo()
    textos = [r.getMessage() for r in caplog.records]
    assert any("tocou 3 quadros" in t and "leitura=1.50s" in t
               for t in textos)
    assert any("tocou so 3 quadros" in t and "threads:" in t
               for t in textos)
    assert d.quadros == 0 and d.pilhas == 1


def test_diagnostico_do_alto_falante_sem_pilhas_quando_toca_normal(caplog):
    import logging
    from telezapp.provedores import chamadas_whatsapp as cw
    relogio = [0.0]
    d = cw._DiagnosticoDoAltoFalante("C2", agora=lambda: relogio[0])
    for _ in range(80):
        d.tocou(0.0, 0.0)
    relogio[0] = 5.5
    with caplog.at_level(logging.INFO):
        d.periodo()
    assert not any("threads:" in r.getMessage() for r in caplog.records)


# ------------------------------------- tela e som do computador na chamada
class SomFalso:
    """No lugar de midia.som_pc: sem soundcard."""
    SILENCIO = bytes(cw.BYTES_POR_QUADRO)

    def __init__(self, quadro=b"\x02\x00" * cw.AMOSTRAS):
        self.quadro = quadro
        self.capturas = []
        self.padrao = "Alto-falantes"

    def disponivel(self):
        return True

    def saidas_do_computador(self):
        return ["Alto-falantes", "Fones"]

    def saida_padrao(self):
        return self.padrao

    def misturar(self, a, b):
        from telezapp.midia import som_pc
        return som_pc.misturar(a, b)

    def CapturaDoSom(self, saida=""):
        som = self

        class C:
            def __init__(self):
                self.parada = False
                som.capturas.append((saida, self))

            def iniciar(self):
                pass

            def ler(self):
                return som.quadro

            def parar(self):
                self.parada = True
        return C()


class VideoComTela(VideoFalso):
    def __init__(self):
        super().__init__()
        self.telas_abertas = []

    def listar_telas(self):
        return [("Tela 1 (principal), 1366 por 768", (0, 0, 1366, 768)),
                ("Tela 2, 1920 por 1080", (1366, 0, 1920, 1080))]

    def Tela(self, retangulo, ao_quadro, nome="Tela"):
        video = self

        class T:
            def iniciar(self):
                video.telas_abertas.append((nome, retangulo))
                ao_quadro(b"quadro")

            def parar(self):
                video.tela_parada = True
        return T()


@pytest.fixture
def mundo_tela(mundo):
    v, ponte, bus, audio = mundo
    v.video = VideoComTela()
    v.som_pc = SomFalso()
    return v, ponte, bus


def em_chamada(v, ponte, bus):
    v.ligar(CID)
    assert esperar(lambda: ponte.ligadas)
    ponte.fila.put({"ev": "ready", "call": "C1"})
    assert esperar(lambda: (ch.EM_CHAMADA, "") in bus.estados())


def test_compartilhar_a_tela_leva_o_som_do_computador_por_padrao(mundo_tela):
    v, ponte, bus = mundo_tela
    em_chamada(v, ponte, bus)
    assert v.compartilhar_tela(CID, "Tela 2, 1920 por 1080") is True
    assert ("C1", cw.VIDEO_PEDIR) in ponte.acoes_de_video
    assert v.video.telas_abertas == [
        ("Tela 2, 1920 por 1080", (1366, 0, 1920, 1080))]
    assert ponte.unidades_enviadas
    e = ultimo_estado(bus)
    assert e.tela and e.camera and e.som_pc and e.video
    assert e.suporta_tela and e.suporta_som_pc
    v.parar_tela(CID)
    assert ("C1", cw.VIDEO_DESLIGAR) in ponte.acoes_de_video
    e = ultimo_estado(bus)
    assert not e.tela and not e.camera
    assert e.som_pc                          # o som continua ate ser parado
    v.parar_som(CID)
    assert not ultimo_estado(bus).som_pc


def test_compartilhar_a_tela_sem_som_e_a_tela_principal_por_padrao(
        mundo_tela):
    v, ponte, bus = mundo_tela
    em_chamada(v, ponte, bus)
    assert v.compartilhar_tela(CID, "", com_som=False)
    assert v.video.telas_abertas[0][0].startswith("Tela 1")
    e = ultimo_estado(bus)
    assert e.tela and not e.som_pc and v.som_pc.capturas == []


def test_camera_toma_o_lugar_da_tela_e_a_tela_o_da_camera(mundo_tela):
    v, ponte, bus = mundo_tela
    em_chamada(v, ponte, bus)
    v.ligar_camera(CID, "Câmera A")
    assert ultimo_estado(bus).camera and not ultimo_estado(bus).tela
    v.compartilhar_tela(CID, "", com_som=False)
    assert ultimo_estado(bus).tela
    assert getattr(v.video, "camera_parada", False)       # a camera saiu
    v.ligar_camera(CID, "Câmera A")
    e = ultimo_estado(bus)
    assert e.camera and not e.tela
    assert getattr(v.video, "tela_parada", False)


def test_som_do_computador_soma_ao_microfone_e_respeita_o_silenciar(
        mundo_tela):
    v, ponte, bus = mundo_tela
    enviados = []
    ponte.escrever_quadro = lambda c, d: enviados.append(d) or True
    em_chamada(v, ponte, bus)
    assert esperar(lambda: enviados)
    assert v.compartilhar_som(CID, "Fones") is True   # outra saida: sem eco
    mic = b"\x01" * cw.BYTES_POR_QUADRO     # o que o Fluxo falso entrega
    esperado = None

    def com_som():
        nonlocal esperado
        for d in enviados[-5:]:
            if d != mic:
                esperado = d
                return True
        return False
    assert esperar(com_som)
    import numpy as np
    amostras = np.frombuffer(esperado, dtype="<i2")
    assert (amostras == 0x0101 + 2).all()    # mic (0x0101) + som (2)
    v.silenciar(CID, True)
    enviados.clear()
    assert esperar(lambda: len(enviados) > 3)
    quadro = np.frombuffer(enviados[-1], dtype="<i2")
    assert (quadro == 2).all()               # microfone mudo, som segue
    v.parar_som(CID)
    assert v.som_pc.capturas[0][1].parada
    enviados.clear()
    assert esperar(lambda: len(enviados) > 3)
    assert bytes(enviados[-1]) == bytes(cw.BYTES_POR_QUADRO)   # so silencio


def test_voz_do_outro_lado_sai_do_som_captado_quando_a_saida_e_a_mesma(
        mundo_tela, monkeypatch):
    v, ponte, bus = mundo_tela
    visto = {"ref": [], "proc": 0}

    class EcoFalso:
        def __init__(self, eco, ruido):
            visto["args"] = (eco, ruido)

        def referencia(self, pcm):
            visto["ref"].append(pcm)

        def processar(self, pcm):
            visto["proc"] += 1
            return bytes(len(pcm))           # tira tudo

        def diagnostico(self):
            return {}

        def reiniciar(self):
            pass
    monkeypatch.setattr(cw.midia_eco, "CancelaEco", EcoFalso)
    em_chamada(v, ponte, bus)
    v.compartilhar_som(CID)                  # capta a saida padrao
    assert visto["args"] == (True, False)    # eco sim, ruido nao (musica)
    ponte.recebidos.put(QUADRO)
    assert esperar(lambda: visto["ref"])     # o que toca vira referencia
    assert esperar(lambda: visto["proc"] > 0)


def test_saida_diferente_da_chamada_nao_precisa_tirar_a_voz(mundo_tela):
    v, ponte, bus = mundo_tela
    em_chamada(v, ponte, bus)
    v.trocar_dispositivos(CID, "", "Fones")
    v.compartilhar_som(CID, "Alto-falantes")
    assert v.ligacoes[CID].eco_pc is None    # a voz do outro nem passa por la
    v.compartilhar_som(CID, "Fones")         # agora e a mesma saida
    assert v.ligacoes[CID].eco_pc is not None


def test_som_e_tela_param_quando_a_chamada_acaba(mundo_tela):
    v, ponte, bus = mundo_tela
    em_chamada(v, ponte, bus)
    v.compartilhar_tela(CID)
    captura = v.som_pc.capturas[0][1]
    ponte.fila.put({"ev": "end", "call": "C1", "reason": ""})
    assert esperar(lambda: captura.parada)
    assert getattr(v.video, "tela_parada", False)


def test_captura_exata_dispensa_o_tira_voz(mundo_tela, monkeypatch):
    v, ponte, bus = mundo_tela
    chamadas_eco = []

    class EcoFalso:
        def __init__(self, *a, **k):
            chamadas_eco.append(a)
    monkeypatch.setattr(cw.midia_eco, "CancelaEco", EcoFalso)
    original = v.som_pc.CapturaDoSom

    def exata(saida=""):
        c = original(saida)
        c.exato = True
        return c
    v.som_pc.CapturaDoSom = exata
    em_chamada(v, ponte, bus)
    assert v.compartilhar_som(CID) is True
    assert v.ligacoes[CID].eco_pc is None and chamadas_eco == []


def test_som_que_nao_abre_avisa_e_nao_marca_como_compartilhado(mundo_tela):
    v, ponte, bus = mundo_tela
    original = v.som_pc.CapturaDoSom

    def quebrada(saida=""):
        c = original(saida)
        c.erro = "OSError: sem saida"
        return c
    v.som_pc.CapturaDoSom = quebrada
    em_chamada(v, ponte, bus)
    assert v.compartilhar_som(CID) is False
    assert not ultimo_estado(bus).som_pc
    assert any("capturar o som" in getattr(e, "texto", "")
               for e in bus.eventos)


# ================================================= chamadas em grupo do
# WhatsApp (experimental): iniciar, receber, entrar, participantes, convidar
GRUPO_CID = "120363000000000001@g.us"


class PonteDeGrupo(PonteFalsa):
    def __init__(self):
        super().__init__()
        self.grupos = []
        self.erro_grupo = ""
        self.lobby_resposta = {"call": "G9", "groupJid": GRUPO_CID,
                               "video": False, "participants": []}
        self.entradas = []
        self.erro_entrar = ""
        self.lista = []
        self.convidados = []
        self.resposta_convite = {}

    def suporta_grupo(self):
        return True

    def suporta_em_andamento(self):
        return True

    def suporta_adicionar(self):
        return True

    def ligar_grupo(self, grupo, video=False):
        self.grupos.append((grupo, video))
        if self.erro_grupo:
            return "", self.erro_grupo
        return "G1", ""

    def lobby(self, chamada, criador):
        return self.lobby_resposta

    def entrar(self, chamada, criador, video=False):
        self.entradas.append((chamada, criador, video))
        if self.erro_entrar:
            return "", self.erro_entrar
        return chamada, ""

    def roster(self, chamada):
        return self.lista

    def adicionar(self, chamada, alvo):
        self.convidados.append((chamada, alvo))
        return self.resposta_convite.get(alvo, "invited")


@pytest.fixture
def mundo_grupo():
    ponte, barramento, audio = PonteDeGrupo(), Barramento(), AudioFalso()
    v = cw.ChamadasWhatsApp(
        ponte, "w1", barramento,
        conversa_do_peer=lambda peer: GRUPO_CID if "@g.us" in peer else CID,
        nome_de=lambda cid: "Amigos" if cid == GRUPO_CID else "Ana",
        destino_de=lambda cid: "5551", audio=audio, espera_s=0.3)
    v.grupo_ligado = lambda: True
    v.andamento_ligado = lambda: True
    v.adicionar_ligado = lambda: True
    v.nome_de_jid = lambda jid, pn="": {"1@lid": "Bia", "2@lid": "Caio",
                                        "9@lid": "Eu"}.get(jid, "")
    v.membros_de = lambda cid: ["x"] * 5
    v.iniciar()
    yield v, ponte, barramento, audio
    v.parar()
    ponte.fim = True


def test_ligar_para_um_grupo_usa_a_funcao_de_grupo_e_so_voz(mundo_grupo):
    v, ponte, bus, _ = mundo_grupo
    v.ligar(GRUPO_CID, "Mic A", "Saida A", video=True)
    assert esperar(lambda: ponte.grupos)
    assert ponte.grupos == [(GRUPO_CID, False)]        # grupo nao leva video
    assert ponte.ligadas == []
    e = [x for x in bus.eventos if isinstance(x, ev.EstadoChamada)][0]
    assert e.grupo is True and e.estado == ch.CHAMANDO and e.video is False
    assert e.nome == "Amigos" and e.suporta_video is False


def test_grupo_com_mais_de_32_nao_liga_e_diz_o_motivo(mundo_grupo):
    v, ponte, bus, _ = mundo_grupo
    v.membros_de = lambda cid: ["x"] * 33
    v.ligar(GRUPO_CID)
    avisos = [x.texto for x in bus.eventos if isinstance(x, ev.Aviso)]
    assert any("32 participantes" in a for a in avisos)
    assert ponte.grupos == [] and v.ligacoes == {}


def test_sem_a_caixa_das_chamadas_em_grupo_nao_liga(mundo_grupo):
    v, ponte, bus, _ = mundo_grupo
    v.grupo_ligado = lambda: False
    v.ligar(GRUPO_CID)
    assert ponte.grupos == [] and v.ligacoes == {}
    assert [x for x in bus.eventos if isinstance(x, ev.Aviso)]


def test_erro_ao_ligar_para_o_grupo_encerra_com_falha(mundo_grupo):
    v, ponte, bus, _ = mundo_grupo
    ponte.erro_grupo = "sem relay"
    v.ligar(GRUPO_CID)
    assert esperar(lambda: (ch.ENCERRADA, ch.FALHA) in bus.estados())


def test_chamada_em_grupo_que_chega_toca_com_o_nome_do_grupo(mundo_grupo):
    v, ponte, bus, _ = mundo_grupo
    ponte.fila.put({"ev": "offer", "call": "R7", "group": GRUPO_CID,
                    "creator": "1@lid", "video": False})
    ponte.fila.put({"ev": "incoming", "call": "R7", "peer": "1@lid",
                    "group": True})
    assert esperar(lambda: bus.estados())
    e = [x for x in bus.eventos if isinstance(x, ev.EstadoChamada)][0]
    assert (e.estado, e.grupo, e.nome, e.entrante) == (
        ch.TOCANDO, True, "Amigos", True)


def test_chamada_em_grupo_que_chega_sem_a_caixa_toca_como_antes(mundo_grupo):
    v, ponte, bus, _ = mundo_grupo
    v.grupo_ligado = lambda: False
    ponte.fila.put({"ev": "incoming", "call": "R7", "peer": "1@lid",
                    "group": True})
    assert esperar(lambda: bus.estados())
    e = [x for x in bus.eventos if isinstance(x, ev.EstadoChamada)][0]
    assert e.grupo is False and e.nome == "Ana"


def _oferta_de_grupo_recusada(v, ponte, bus, com_a_caixa):
    """Convite de grupo, toque como chamada comum (o `incoming` nao diz que
    e de grupo, como no log de 24/11), atendida e recusada com 431."""
    v.grupo_ligado = lambda: com_a_caixa
    ponte.fila.put({"ev": "offer", "call": "R5", "group": GRUPO_CID,
                    "creator": "1@lid", "video": True})
    ponte.fila.put({"ev": "incoming", "call": "R5", "peer": "1@lid",
                    "video": True})
    assert esperar(lambda: bus.estados())
    return [x.texto for x in bus.eventos if isinstance(x, ev.Aviso)]


def test_convite_de_grupo_sem_a_caixa_avisa_ao_tocar_e_explica_a_recusa(
        mundo_grupo):
    v, ponte, bus, _ = mundo_grupo
    avisos = _oferta_de_grupo_recusada(v, ponte, bus, False)
    assert any("Esta chamada é de um grupo" in a for a in avisos)
    v.atender(CID)
    ponte.fila.put({"ev": "end", "call": "R5", "reason": "server:431"})
    assert esperar(lambda: bus.estados()[-1][0] == ch.ENCERRADA)
    final = bus.eventos[-1]
    assert final.motivo == ch.FALHA
    assert "chamada em grupo" in final.erro and "431" in final.erro
    assert "Recursos experimentais" in final.erro


def test_recusa_431_de_grupo_com_a_caixa_diz_que_so_entra_por_voz(
        mundo_grupo):
    v, ponte, bus, _ = mundo_grupo
    avisos = _oferta_de_grupo_recusada(v, ponte, bus, True)
    assert not any("Esta chamada é de um grupo" in a for a in avisos)
    cid = next(iter(v.ligacoes))
    v.atender(cid)
    ponte.fila.put({"ev": "end", "call": "R5", "reason": "server:431"})
    assert esperar(lambda: bus.estados()[-1][0] == ch.ENCERRADA)
    erro = bus.eventos[-1].erro
    assert "só entra em chamadas em grupo comuns por voz" in erro


def test_recusa_do_servidor_numa_chamada_comum_continua_generica(mundo_grupo):
    v, ponte, bus, _ = mundo_grupo
    ponte.fila.put({"ev": "incoming", "call": "R6", "peer": "1@lid"})
    assert esperar(lambda: bus.estados())
    v.atender(CID)
    ponte.fila.put({"ev": "end", "call": "R6", "reason": "server:431"})
    assert esperar(lambda: bus.estados()[-1][0] == ch.ENCERRADA)
    assert bus.eventos[-1].erro == "O WhatsApp recusou a chamada (server:431)."


def test_convite_de_grupo_guarda_e_avisa_que_da_para_entrar(mundo_grupo):
    v, ponte, bus, _ = mundo_grupo
    ponte.fila.put({"ev": "offer", "call": "R7", "group": GRUPO_CID,
                    "creator": "1@lid", "video": True})
    assert esperar(lambda: [x for x in bus.eventos
                            if isinstance(x, ev.ChamadaEmAndamento)])
    e = [x for x in bus.eventos if isinstance(x, ev.ChamadaEmAndamento)][0]
    assert (e.conversa_id, e.call_id, e.ativa, e.video) == (
        GRUPO_CID, "R7", True, True)
    ponte.fila.put({"ev": "end", "call": "R7", "reason": "x"})
    assert esperar(lambda: [x for x in bus.eventos
                            if isinstance(x, ev.ChamadaEmAndamento)
                            and not x.ativa])


def test_entrar_na_chamada_em_andamento_liga_o_som(mundo_grupo):
    v, ponte, bus, audio = mundo_grupo
    ponte.fila.put({"ev": "offer", "call": "G9", "group": GRUPO_CID,
                    "creator": "1@lid", "video": False})
    assert esperar(lambda: "G9" in v._ofertas)
    v.entrar_em_andamento(GRUPO_CID, "G9", "Mic B", "Saida A")
    assert esperar(lambda: ponte.entradas)
    assert ponte.entradas == [("G9", "1@lid", False)]
    assert esperar(lambda: (ch.CONECTANDO, "") in bus.estados())
    ponte.fila.put({"ev": "ready", "call": "G9"})
    assert esperar(lambda: (ch.EM_CHAMADA, "") in bus.estados())
    assert esperar(lambda: audio.microfones_abertos == ["Mic B"])


def test_chamada_em_andamento_que_acabou_nao_entra(mundo_grupo):
    v, ponte, bus, _ = mundo_grupo
    ponte.lobby_resposta = {"over": True}
    ponte.fila.put({"ev": "offer", "call": "G9", "group": GRUPO_CID,
                    "creator": "1@lid", "video": False})
    assert esperar(lambda: "G9" in v._ofertas)
    v.entrar_em_andamento(GRUPO_CID, "G9")
    assert esperar(lambda: [x for x in bus.eventos
                            if isinstance(x, ev.Aviso)])
    assert ponte.entradas == [] and v.ligacoes == {}
    assert "G9" not in v._ofertas


def test_sem_convite_guardado_nao_entra(mundo_grupo):
    v, ponte, bus, _ = mundo_grupo
    v.entrar_em_andamento(GRUPO_CID, "G9")
    assert [x.texto for x in bus.eventos if isinstance(x, ev.Aviso)] == [
        "Não achei essa chamada em andamento."]


def test_lista_de_participantes_vem_dos_eventos_de_grupo(mundo_grupo):
    v, ponte, bus, _ = mundo_grupo
    v.ligar(GRUPO_CID)
    assert esperar(lambda: ponte.grupos)
    ponte.fila.put({"ev": "ready", "call": "G1"})
    assert esperar(lambda: (ch.EM_CHAMADA, "") in bus.estados())
    ponte.lista = [{"jid": "2@lid", "state": "invited"},
                   {"jid": "1@lid", "pn": "5511@s.whatsapp.net",
                    "state": "connected"}]
    ponte.fila.put({"ev": "group", "call": "G1", "participants": 2})
    assert esperar(lambda: [x for x in bus.eventos
                            if isinstance(x, ev.EstadoChamada)
                            and x.participantes])
    e = [x for x in bus.eventos if isinstance(x, ev.EstadoChamada)][-1]
    # quem esta na chamada primeiro; o nome vem do endereco original
    assert e.participantes[0] == ("5511@s.whatsapp.net", "Bia",
                                  "connected")
    assert e.participantes[1] == ("2@lid", "Caio", "invited")
    assert e.grupo is True and e.suporta_adicionar is True


def test_convidar_pede_a_dll_e_diz_o_resultado(mundo_grupo):
    v, ponte, bus, _ = mundo_grupo
    v.ligar(GRUPO_CID)
    assert esperar(lambda: ponte.grupos)
    ponte.fila.put({"ev": "ready", "call": "G1"})
    assert esperar(lambda: (ch.EM_CHAMADA, "") in bus.estados())
    ponte.resposta_convite = {"3@lid": "failed", "4@lid": "rang"}
    v.adicionar(GRUPO_CID, [("2@lid", "Caio"), ("3@lid", "Duda"),
                            ("4@lid", "Edu")])
    assert esperar(lambda: [x for x in bus.eventos
                            if isinstance(x, ev.ResultadoDeConvites)])
    r = [x for x in bus.eventos if isinstance(x, ev.ResultadoDeConvites)][0]
    assert r.resultados == (("Caio", "invited"), ("Duda", "failed"),
                            ("Edu", "rang"))
    assert [c[1] for c in ponte.convidados] == ["2@lid", "3@lid", "4@lid"]


def test_convidar_so_com_a_chamada_em_andamento_e_a_caixa(mundo_grupo):
    v, ponte, bus, _ = mundo_grupo
    v.adicionar(GRUPO_CID, [("2@lid", "Caio")])
    assert "em andamento" in [x.texto for x in bus.eventos
                              if isinstance(x, ev.Aviso)][-1]
    assert ponte.convidados == []


def test_botao_de_convidar_so_em_chamada_com_a_caixa(mundo_grupo):
    v, ponte, bus, _ = mundo_grupo
    c = ch.Chamada("w1", GRUPO_CID, "Amigos", False, ch.EM_CHAMADA,
                   grupo=True)
    assert v._pode_convidar(c) is True
    v.adicionar_ligado = lambda: False
    assert v._pode_convidar(c) is False
    c.estado = ch.CHAMANDO
    v.adicionar_ligado = lambda: True
    assert v._pode_convidar(c) is False


# ---------------------------------------------------------- nucleo
def test_modelo_da_chamada_em_grupo():
    c = ch.Chamada("w1", GRUPO_CID, "Amigos", True, ch.TOCANDO, grupo=True)
    a = ch.apresentar(c)
    assert "Chamada em grupo" in a.titulo and "Amigos" in a.titulo
    c.aplicar(ch.EM_CHAMADA)
    c.participantes = [("1@lid", "Bia", "connected"),
                       ("2@lid", "Caio", "invited")]
    c.suporta_adicionar = True
    a = ch.apresentar(c)
    assert ch.ADICIONAR in a.botoes and "1 pessoa na chamada" in a.situacao
    assert a.botoes.index(ch.SILENCIAR) < a.botoes.index(ch.ADICIONAR)
    c.suporta_adicionar = False
    assert ch.ADICIONAR not in ch.apresentar(c).botoes


def test_linhas_e_falas_da_lista_de_participantes():
    assert ch.rotulo_participante("Bia", ch.CONECTADO) == "Bia, na chamada"
    assert "ainda não entrou" in ch.rotulo_participante("Caio", ch.CONVIDADO)
    antes = [("1", "Bia", "connected")]
    depois = [("1", "Bia", "connected"), ("2", "Caio", "connected")]
    assert ch.fala_da_lista(antes, depois) == "Caio entrou na chamada."
    assert ch.fala_da_lista(depois, antes) == "Caio saiu da chamada."
    assert ch.fala_da_lista(antes, [("1", "Bia", "connected"),
                                    ("2", "Caio", "invited")]) == ""
    assert ch.fala_dos_convites([("Ana", "invited"), ("Bia", "failed")]) == \
        "Convidei Ana. Não consegui convidar Bia."
    assert ch.fala_dos_convites([]) == "Não consegui convidar ninguém."


def test_opcoes_das_chamadas_em_grupo_ficam_em_recursos_experimentais():
    from telezapp import config
    for chave in ("chamada_grupo_whatsapp", "chamada_em_andamento_whatsapp",
                  "chamada_adicionar_whatsapp"):
        o = next(x for x in config.OPCOES if x.chave == chave)
        assert o.categoria == config.CATEGORIA_EXPERIMENTAL
        assert o.padrao is False and o.servico == "whatsapp"
        assert "experimental" in o.descricao.lower()


# ------------------------------------- video nas chamadas em grupo (experimental)
from telezapp.midia import video as _midia_video  # noqa: E402


class VideoDeGrupo(VideoFalso):
    Mosaico = _midia_video.Mosaico


class PonteDeGrupoComVideo(PonteDeGrupo):
    def __init__(self):
        super().__init__()
        self.por_participante = queue.Queue()
        self.lobby_resposta = {"call": "G9", "groupJid": GRUPO_CID,
                               "video": True, "participants": []}

    def suporta_video_de_participantes(self):
        return True

    def ler_video_de_participante(self, chamada, espera_ms=500):
        if self.fim:
            return False
        try:
            return self.por_participante.get(timeout=0.02)
        except queue.Empty:
            return None


@pytest.fixture
def mundo_grupo_video():
    ponte, bus, audio = PonteDeGrupoComVideo(), Barramento(), AudioFalso()
    v = cw.ChamadasWhatsApp(
        ponte, "w1", bus,
        conversa_do_peer=lambda peer: GRUPO_CID if "@g.us" in peer else CID,
        nome_de=lambda cid: "Amigos" if cid == GRUPO_CID else "Ana",
        destino_de=lambda cid: "5551", audio=audio, espera_s=0.3)
    v.grupo_ligado = lambda: True
    v.andamento_ligado = lambda: True
    v.video_grupo_ligado = lambda: True
    v.membros_de = lambda cid: ["x"] * 5
    v.video = VideoDeGrupo()
    quadros = []
    v.destino_video = lambda cid, l, a, rgb: quadros.append((cid, l, a, rgb))
    v.iniciar()
    yield v, ponte, bus, quadros
    v.parar()
    ponte.fim = True


def test_a_caixa_do_video_em_grupo_e_experimental_e_desligada():
    from telezapp import config
    o = next(x for x in config.OPCOES
             if x.chave == "chamada_grupo_video_whatsapp")
    assert o.categoria == config.CATEGORIA_EXPERIMENTAL
    assert o.padrao is False and o.servico == "whatsapp"
    assert "experimental" in o.descricao.lower()


def test_sem_a_caixa_o_grupo_continua_so_com_voz(mundo_grupo_video):
    v, ponte, bus, _ = mundo_grupo_video
    v.video_grupo_ligado = lambda: False
    assert v.suporta_video_em_grupo is False
    v.ligar(GRUPO_CID, "", "", video=True)
    assert esperar(lambda: ponte.grupos)
    assert ponte.grupos == [(GRUPO_CID, False)]
    e = [x for x in bus.eventos if isinstance(x, ev.EstadoChamada)][0]
    assert e.video is False and e.suporta_video is False


def test_ligar_para_grupo_com_video_manda_video_e_liga_a_camera(
        mundo_grupo_video):
    v, ponte, bus, _ = mundo_grupo_video
    assert v.suporta_video_em_grupo is True
    v.ligar(GRUPO_CID, "", "", video=True, camera="Câmera B")
    assert esperar(lambda: ponte.grupos)
    assert ponte.grupos == [(GRUPO_CID, True)]
    e = [x for x in bus.eventos if isinstance(x, ev.EstadoChamada)][0]
    assert e.grupo and e.video and e.suporta_video and e.suporta_tela
    ponte.fila.put({"ev": "ready", "call": "G1"})
    assert esperar(lambda: v.video.cameras_abertas == ["Câmera B"])


def test_video_de_cada_participante_chega_numa_imagem_so(mundo_grupo_video):
    v, ponte, bus, quadros = mundo_grupo_video
    v.ligar(GRUPO_CID, "", "", video=True)
    assert esperar(lambda: ponte.grupos)
    ponte.fila.put({"ev": "ready", "call": "G1"})
    assert esperar(lambda: v.ligacoes[GRUPO_CID].recebendo_video)
    ponte.por_participante.put(("1@lid", b"\x00\x00\x00\x01a"))
    ponte.por_participante.put(("2@lid", b"\x00\x00\x00\x01b"))
    assert esperar(lambda: quadros)
    assert quadros[-1][0] == GRUPO_CID
    assert esperar(lambda: [x for x in bus.eventos
                            if isinstance(x, ev.EstadoChamada)][-1]
                   .video_remoto)


def test_convite_de_video_em_grupo_atendido_entra_na_chamada(
        mundo_grupo_video):
    v, ponte, bus, _ = mundo_grupo_video
    ponte.fila.put({"ev": "offer", "call": "R5", "group": GRUPO_CID,
                    "creator": "1@lid", "video": True})
    ponte.fila.put({"ev": "incoming", "call": "R5", "peer": "1@lid",
                    "video": True})
    assert esperar(lambda: bus.estados())
    tocando = [x for x in bus.eventos if isinstance(x, ev.EstadoChamada)][0]
    assert tocando.grupo and tocando.video and tocando.nome == "Amigos"
    v.atender(GRUPO_CID)
    # entra pelo caminho de quem chega numa chamada em andamento (lobby +
    # entrar), e nao pelo atendimento comum que o WhatsApp recusa com 431
    assert esperar(lambda: ponte.entradas)
    assert ponte.entradas[0][0] == "R5" and ponte.entradas[0][2] is True
    assert ponte.atendidas == []


def test_atender_grupo_sem_poder_entrar_cai_no_atendimento_comum(
        mundo_grupo_video):
    v, ponte, bus, _ = mundo_grupo_video
    v.andamento_ligado = lambda: False
    ponte.fila.put({"ev": "offer", "call": "R5", "group": GRUPO_CID,
                    "creator": "1@lid", "video": False})
    ponte.fila.put({"ev": "incoming", "call": "R5", "peer": "1@lid",
                    "group": True})
    assert esperar(lambda: bus.estados())
    v.atender(GRUPO_CID)
    assert esperar(lambda: ponte.atendidas)
    assert ponte.entradas == []


def test_atender_grupo_cuja_entrada_falha_tenta_o_atendimento_comum(
        mundo_grupo_video):
    v, ponte, bus, _ = mundo_grupo_video
    ponte.erro_entrar = "sem relay"
    ponte.fila.put({"ev": "offer", "call": "R5", "group": GRUPO_CID,
                    "creator": "1@lid", "video": False})
    ponte.fila.put({"ev": "incoming", "call": "R5", "peer": "1@lid",
                    "group": True})
    assert esperar(lambda: bus.estados())
    v.atender(GRUPO_CID)
    assert esperar(lambda: ponte.atendidas)


# ------------------------------------------------------- a ponte da DLL
class GoFalso:
    def __init__(self, respostas):
        self.respostas = respostas
        self.chamadas = []

    def __getattr__(self, nome):
        if nome not in self.respostas:
            raise AttributeError(nome)

        def f(*args):
            self.chamadas.append((nome, args))
            texto = self.respostas[nome]
            buf, cap = args[-2], args[-1]
            dados = texto.encode()
            buf.value = dados
            return len(dados)
        f.argtypes = f.restype = None
        return f


def ponte_com(respostas):
    p = cw.Ponte.__new__(cw.Ponte)
    p.uuid = b"u"
    p.go = GoFalso(respostas)
    return p


def test_ponte_liga_para_grupo_e_le_o_resultado():
    p = ponte_com({"CallGroupDial": '{"call": "G1"}'})
    assert p.suporta_grupo() and not p.suporta_em_andamento()
    assert p.ligar_grupo("123@g.us", True) == ("G1", "")
    assert p.go.chamadas[0][1][1:3] == (b"123@g.us", 1)
    p = ponte_com({"CallGroupDial": '{"error": "sem relay"}'})
    assert p.ligar_grupo("123@g.us") == ("", "sem relay")


def test_ponte_sem_as_funcoes_novas_diz_que_nao_suporta():
    p = ponte_com({})
    assert not (p.suporta_grupo() or p.suporta_em_andamento()
                or p.suporta_adicionar())


def test_ponte_lobby_roster_entrar_e_adicionar():
    p = ponte_com({
        "CallLobby": '{"over": true}',
        "CallJoinOngoing": '{"call": "G9"}',
        "CallRoster": '{"group": true, "participants": [{"jid": "1@lid", '
                      '"state": "connected"}]}',
        "CallAddParticipant": '{"rang": true}'})
    assert p.suporta_em_andamento() and p.suporta_adicionar()
    assert p.lobby("G9", "1@lid") == {"over": True}
    assert p.entrar("G9", "1@lid") == ("G9", "")
    assert p.roster("G9") == [{"jid": "1@lid", "state": "connected"}]
    assert p.adicionar("G9", "2@lid") == "rang"


# ----------------------------------------- segunda chamada (experimental)
CID2 = "5552@s.whatsapp.net"


def espera_ativa(v):
    v.espera_ligada = lambda: True
    v.conversa_do_peer = lambda peer: CID2 if peer == "2@lid" else CID


def em_espera(bus, fase=None):
    return [e for e in bus.eventos if isinstance(e, ev.ChamadaEmEspera)
            and (fase is None or e.fase == fase)]


def chamada_em_curso_e_segunda(v, ponte, bus):
    espera_ativa(v)
    chamada_recebida(ponte, bus)
    v.atender(CID)
    ponte.fila.put({"ev": "ready", "call": "R1"})
    assert esperar(lambda: (ch.EM_CHAMADA, "") in bus.estados())
    ponte.fila.put({"ev": "incoming", "call": "R2", "peer": "2@lid"})
    assert esperar(lambda: em_espera(bus, "tocando"))


def test_segunda_chamada_com_a_opcao_desligada_segue_recusada(mundo):
    v, ponte, bus, _ = mundo
    v.conversa_do_peer = lambda peer: CID2 if peer == "2@lid" else CID
    chamada_recebida(ponte, bus)
    ponte.fila.put({"ev": "incoming", "call": "R2", "peer": "2@lid"})
    assert esperar(lambda: "R2" in ponte.desligadas)
    assert not em_espera(bus)


def test_segunda_chamada_com_a_opcao_ligada_avisa_e_nao_recusa(mundo):
    v, ponte, bus, _ = mundo
    chamada_em_curso_e_segunda(v, ponte, bus)
    e = em_espera(bus, "tocando")[0]
    assert (e.conversa_id, e.nome) == (CID2, "Ana")
    assert "R2" not in ponte.desligadas and "R2" not in ponte.atendidas
    # a atual continua: so uma chamada publicada como em curso
    assert list(v.ligacoes) == [CID]


def test_recusar_a_segunda_mantem_a_atual(mundo):
    v, ponte, bus, _ = mundo
    chamada_em_curso_e_segunda(v, ponte, bus)
    v.recusar_espera(CID2)
    assert "R2" in ponte.desligadas and "R1" not in ponte.desligadas
    assert em_espera(bus, "recusada")
    assert v.ligacoes[CID].chamada.estado == ch.EM_CHAMADA


def test_quem_ligou_desistiu_avisa_e_esquece(mundo):
    v, ponte, bus, _ = mundo
    chamada_em_curso_e_segunda(v, ponte, bus)
    ponte.fila.put({"ev": "end", "call": "R2", "reason": "timeout"})
    assert esperar(lambda: em_espera(bus, "perdida"))
    assert not v._espera and v.ligacoes[CID].chamada.estado == ch.EM_CHAMADA


def test_so_uma_segunda_chamada_espera_de_cada_vez(mundo):
    v, ponte, bus, _ = mundo
    chamada_em_curso_e_segunda(v, ponte, bus)
    v.conversa_do_peer = lambda peer: "5553@s.whatsapp.net"
    ponte.fila.put({"ev": "incoming", "call": "R3", "peer": "3@lid"})
    assert esperar(lambda: "R3" in ponte.desligadas)
    assert len(em_espera(bus, "tocando")) == 1


def test_encerrar_e_aceitar_troca_de_chamada(mundo):
    import threading
    v, ponte, bus, _ = mundo
    chamada_em_curso_e_segunda(v, ponte, bus)
    t = threading.Thread(target=v.aceitar_espera,
                         args=(CID2, "Mic A", "Saida A"))
    t.start()
    assert esperar(lambda: "R1" in ponte.desligadas)
    ponte.fila.put({"ev": "end", "call": "R1", "reason": "hangup"})
    t.join(5)
    assert not t.is_alive()
    assert "R2" in ponte.atendidas
    assert list(v.ligacoes) == [CID2]
    assert (ch.ENCERRADA, ch.DESLIGADA) in bus.estados()
    assert (ch.CONECTANDO, "") in bus.estados()
    # nao passou por "tocando" para a pessoa: ja entrou atendendo
    assert bus.estados().count((ch.TOCANDO, "")) == 1


def test_atual_acaba_e_a_segunda_passa_a_tocar_como_comum(mundo):
    v, ponte, bus, _ = mundo
    chamada_em_curso_e_segunda(v, ponte, bus)
    ponte.fila.put({"ev": "end", "call": "R1", "reason": "hangup"})
    assert esperar(lambda: list(v.ligacoes) == [CID2])
    assert esperar(lambda: bus.estados()[-1] == (ch.TOCANDO, ""))
    assert not v._espera


def test_oferta_parada_ha_mais_de_90_s_nao_prende_a_linha(monkeypatch):
    """Log do Igor (23/11): oferta sem aviso de fim ficou 1h54 e as chamadas
    novas eram recusadas como 'outra aberta'."""
    import time as _t
    from telezapp.provedores import chamadas_whatsapp as cw
    from telezapp.nucleo import chamadas as ch
    ligacoes = {}

    class Ponte:
        desligadas = []

        def desligar(self, call_id):
            self.desligadas.append(call_id)
            return True

    class Falso:
        pass
    f = Falso()
    f.ponte = Ponte()
    f.ligacoes = ligacoes
    import threading
    f._trava = threading.RLock()
    mudancas = []
    f._mudar = lambda cid, estado, motivo="", erro="": (
        mudancas.append((cid, estado, motivo)), ligacoes.pop(cid, None))
    velha = cw._Ligacao(ch.Chamada("c", "a", "A", True, ch.TOCANDO), "VELHA")
    velha.criada_em = _t.monotonic() - 100
    nova = cw._Ligacao(ch.Chamada("c", "b", "B", True, ch.TOCANDO), "NOVA")
    ligacoes["a"], ligacoes["b"] = velha, nova
    cw.ChamadasWhatsApp._descartar_toques_parados(f)
    assert mudancas == [("a", ch.ENCERRADA, ch.PERDIDA)]
    assert Ponte.desligadas == ["VELHA"]
    assert "b" in ligacoes

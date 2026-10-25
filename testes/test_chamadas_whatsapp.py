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

    def ligada(self):
        return True

    def proximo_evento(self, espera_ms=500):
        try:
            return self.fila.get(timeout=min(espera_ms, 50) / 1000)
        except queue.Empty:
            return None

    def ligar(self, destino):
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
    ponte.fila.put({"ev": "state", "call": "C1", "phase": 3})
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
    ponte.fila.put({"ev": "state", "call": "C1", "phase": 3})
    assert esperar(lambda: ponte.desligadas == ["C1"], 3.0)
    ponte.fila.put({"ev": "end", "call": "C1", "reason": "hangup"})
    assert esperar(lambda: (ch.ENCERRADA, ch.FALHA) in bus.estados())
    final = [e for e in bus.eventos if isinstance(e, ev.EstadoChamada)][-1]
    assert "som do outro lado não chegou" in final.erro

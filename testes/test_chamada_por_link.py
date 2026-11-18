# SPDX-License-Identifier: GPL-3.0-or-later
"""Chamadas por link do WhatsApp (experimental): reconhecer o endereco, a
ponte da DLL, entrar (direto e pela sala de espera) e criar o link."""
import pytest

from telezapp import config
from telezapp.nucleo import chamadas as ch
from telezapp.nucleo import eventos as ev
from telezapp.nucleo import links_externos as le
from telezapp.provedores import chamadas_whatsapp as cw
from testes.test_chamadas_whatsapp import (
    AudioFalso, Barramento, CID, GoFalso, PonteFalsa, esperar, ponte_com)

LINK = "https://call.whatsapp.com/voice/bTSKe6oyskO156SxYXrhlJ"


# ------------------------------------------------------- o endereco
def test_link_de_voz_e_reconhecido():
    r = le.interpretar(LINK)
    assert r == {"servico": "whatsapp", "acao": "chamada",
                 "codigo": "bTSKe6oyskO156SxYXrhlJ", "video": False}


def test_link_de_video_e_reconhecido_como_video():
    r = le.interpretar("https://call.whatsapp.com/video/AbCdEfGhIjKlMn?x=1")
    assert (r["acao"], r["codigo"], r["video"]) == (
        "chamada", "AbCdEfGhIjKlMn", True)


@pytest.mark.parametrize("url", [
    "https://call.whatsapp.com/", "https://call.whatsapp.com/voice",
    "https://call.whatsapp.com/voice/curto",
    "https://call.whatsapp.com/outro/bTSKe6oyskO156SxYXrhlJ",
    "https://call.whatsapp.com/voice/bTSKe6oyskO156SxYXrhlJ/mais",
    "https://example.com/voice/bTSKe6oyskO156SxYXrhlJ"])
def test_o_que_nao_e_link_de_chamada_fica_de_fora(url):
    assert le.interpretar(url) is None


# ------------------------------------------------- a opcao e o texto
def test_opcao_e_experimental_e_do_whatsapp():
    o = next(x for x in config.OPCOES if x.chave == "chamada_por_link_whatsapp")
    assert o.categoria == config.CATEGORIA_EXPERIMENTAL
    assert o.padrao is False and o.servico == "whatsapp"
    assert "experimental" in o.descricao.lower()


def test_sala_de_espera_tem_texto_proprio():
    c = ch.Chamada("w1", "link:chamada", "chamada por link", False,
                   ch.ESPERANDO, grupo=True)
    a = ch.apresentar(c)
    assert "sala de espera" in a.fala and a.botoes == (ch.DESLIGAR,)
    assert c.ativa


# ------------------------------------------------------- a ponte
def test_ponte_previa_entrar_e_criar():
    p = ponte_com({
        "CallLinkPreview": '{"video": false, "approval": true, '
                           '"admin": false}',
        "CallLinkJoin": '{"call": "L1", "waiting": true}',
        "CallLinkCreate": '{"url": "https://call.whatsapp.com/voice/X", '
                          '"video": false}'})
    assert p.suporta_link()
    assert p.previa_link("tok", False)["approval"] is True
    assert p.entrar_por_link("tok", True) == {"call": "L1", "waiting": True}
    assert p.go.chamadas[-1][1][1:3] == (b"tok", 1)
    assert p.criar_link(False)["url"].endswith("/voice/X")


def test_ponte_sem_as_funcoes_de_link_diz_que_nao_suporta():
    assert not ponte_com({}).suporta_link()


# ------------------------------------------------------- entrar
class PonteDeLink(PonteFalsa):
    def __init__(self):
        super().__init__()
        self.entradas = []
        self.resposta = {"call": "L1"}
        self.previa = {"video": False, "approval": False}
        self.link = {"url": "https://call.whatsapp.com/voice/NOVO"}

    def suporta_link(self):
        return True

    def entrar_por_link(self, codigo, video):
        self.entradas.append((codigo, video))
        return self.resposta

    def previa_link(self, codigo, video):
        return self.previa

    def criar_link(self, video):
        return self.link


@pytest.fixture
def mundo():
    ponte, bus, audio = PonteDeLink(), Barramento(), AudioFalso()
    v = cw.ChamadasWhatsApp(
        ponte, "w1", bus, conversa_do_peer=lambda peer: CID,
        nome_de=lambda cid: "Ana", destino_de=lambda cid: "5551",
        audio=audio, espera_s=0.3)
    v.link_ligado = lambda: True
    v.iniciar()
    yield v, ponte, bus, audio
    v.parar()
    ponte.fim = True


def avisos(bus):
    return [x.texto for x in bus.eventos if isinstance(x, ev.Aviso)]


def test_entrar_por_link_abre_o_audio_e_publica_a_chamada(mundo):
    v, ponte, bus, audio = mundo
    v.entrar_por_link("tok", False, "Mic A", "Saida A")
    assert esperar(lambda: ponte.entradas)
    assert ponte.entradas == [("tok", False)]
    e = [x for x in bus.eventos if isinstance(x, ev.EstadoChamada)][0]
    assert e.grupo is True and e.estado == ch.CONECTANDO
    assert esperar(lambda: audio.microfones_abertos == ["Mic A"])


def test_entrar_com_aprovacao_espera_e_so_abre_o_audio_depois(mundo):
    v, ponte, bus, audio = mundo
    ponte.resposta = {"call": "L1", "waiting": True, "approval": True}
    v.entrar_por_link("tok", False, "Mic A", "Saida A")
    assert esperar(lambda: (ch.ESPERANDO, "") in bus.estados())
    assert audio.microfones_abertos == []
    ponte.fila.put({"ev": "state", "call": "L1", "phase": 6})
    assert audio.microfones_abertos == []
    ponte.fila.put({"ev": "state", "call": "L1", "phase": 3})
    assert esperar(lambda: audio.microfones_abertos == ["Mic A"])
    assert (ch.CONECTANDO, "") in bus.estados()


def test_recusado_na_sala_de_espera_encerra_com_motivo(mundo):
    v, ponte, bus, _ = mundo
    ponte.resposta = {"call": "L1", "waiting": True}
    v.entrar_por_link("tok", False)
    assert esperar(lambda: (ch.ESPERANDO, "") in bus.estados())
    ponte.fila.put({"ev": "end", "call": "L1", "reason": "denied"})
    assert esperar(lambda: (ch.ENCERRADA, ch.FALHA) in bus.estados())
    e = [x for x in bus.eventos if isinstance(x, ev.EstadoChamada)][-1]
    assert "anfitrião" in e.erro


def test_link_que_nao_vale_encerra_explicando(mundo):
    v, ponte, bus, _ = mundo
    ponte.resposta = {"error": "call link expired"}
    v.entrar_por_link("tok", False)
    assert esperar(lambda: (ch.ENCERRADA, ch.FALHA) in bus.estados())
    e = [x for x in bus.eventos if isinstance(x, ev.EstadoChamada)][-1]
    assert "não vale mais" in e.erro
    assert v.ligacoes == {}


def test_sem_a_caixa_marcada_nao_entra(mundo):
    v, ponte, bus, _ = mundo
    v.link_ligado = lambda: False
    v.entrar_por_link("tok", False)
    assert ponte.entradas == [] and v.ligacoes == {}
    assert any("Recursos experimentais" in a for a in avisos(bus))


def test_com_outra_chamada_em_andamento_avisa_e_nao_entra(mundo):
    v, ponte, bus, _ = mundo
    v.ligacoes[CID] = cw._Ligacao(ch.Chamada("w1", CID, "Ana"))
    v.entrar_por_link("tok", False)
    assert ponte.entradas == []
    assert "Já há uma chamada em andamento." in avisos(bus)


def test_o_codigo_do_link_nao_vai_para_o_log(mundo, caplog):
    v, ponte, bus, _ = mundo
    ponte.resposta = {"error": "boom tok-secreto"}
    with caplog.at_level("DEBUG"):
        v.entrar_por_link("tok-secreto", False)
        assert esperar(lambda: (ch.ENCERRADA, ch.FALHA) in bus.estados())
    assert "tok-secreto" not in caplog.text


# ------------------------------------------------- previa e criar
def test_previa_devolve_dados_ou_o_erro_em_portugues(mundo):
    v, ponte, _, _ = mundo
    ponte.previa = {"video": False, "approval": True, "admin": False}
    dados, erro = v.previa_do_link("tok")
    assert erro == "" and dados["approval"] is True
    ponte.previa = {"error": "item-not-found"}
    dados, erro = v.previa_do_link("tok")
    assert dados == {} and "não vale mais" in erro


def test_criar_link_devolve_o_endereco_ou_o_erro(mundo):
    v, ponte, _, _ = mundo
    assert v.criar_link() == ("https://call.whatsapp.com/voice/NOVO", "")
    ponte.link = {"error": "x"}
    link, erro = v.criar_link()
    assert link == "" and "Não consegui criar" in erro
    v.link_ligado = lambda: False
    assert v.criar_link()[0] == ""


# ------------------------------------------------------------ video
from testes.test_chamadas_whatsapp import VideoFalso  # noqa: E402
from telezapp.midia import video as midia_video  # noqa: E402


class VideoDeGrupoFalso(VideoFalso):
    Mosaico = midia_video.Mosaico


class PonteDeVideoDeLink(PonteDeLink):
    def __init__(self):
        super().__init__()
        self.de_participantes = []
        import queue
        self.por_participante = queue.Queue()

    def suporta_video_de_participantes(self):
        return True

    def ler_video_de_participante(self, chamada, espera_ms=500):
        import queue
        if self.fim:
            return False
        try:
            return self.por_participante.get(timeout=0.02)
        except queue.Empty:
            return None


@pytest.fixture
def mundo_video():
    ponte, bus, audio = PonteDeVideoDeLink(), Barramento(), AudioFalso()
    v = cw.ChamadasWhatsApp(
        ponte, "w1", bus, conversa_do_peer=lambda peer: CID,
        nome_de=lambda cid: "Ana", destino_de=lambda cid: "5551",
        audio=audio, espera_s=0.3)
    v.link_ligado = lambda: True
    v.video = VideoDeGrupoFalso()
    quadros = []
    v.destino_video = lambda cid, l, a, rgb: quadros.append((cid, l, a, rgb))
    v.iniciar()
    yield v, ponte, bus, quadros
    v.parar()
    ponte.fim = True


def ultimo(bus):
    return [e for e in bus.eventos if isinstance(e, ev.EstadoChamada)][-1]


def test_chamada_por_link_oferece_camera_e_tela(mundo_video):
    v, ponte, bus, _ = mundo_video
    v.entrar_por_link("tok", True, "", "")
    assert esperar(lambda: ponte.entradas)
    e = ultimo(bus)
    assert e.grupo is True and e.video is True
    assert e.suporta_video and e.suporta_tela
    # a camera sempre comeca desligada
    assert e.camera is False


def test_chamada_em_grupo_comum_continua_sem_video(mundo_video):
    v, *_ = mundo_video
    c = ch.Chamada("w1", "120@g.us", "Amigos", grupo=True)
    assert v._publicar(c) is None
    assert c.suporta_video is False and c.suporta_tela is False


def test_video_dos_participantes_chega_em_grade(mundo_video):
    v, ponte, bus, quadros = mundo_video
    v.video.quadros_decodificados = [(4, 2, b"\x01" * 24)]
    v.entrar_por_link("tok", True, "", "")
    assert esperar(lambda: ponte.entradas)
    ponte.fila.put({"ev": "ready", "call": "L1"})
    assert esperar(lambda: v.ligacoes["link:chamada"].recebendo_video)
    ponte.por_participante.put(("1@lid", b"au1"))
    assert esperar(lambda: quadros)
    assert quadros[0][1:3] == (4, 2)          # um participante: como veio
    assert esperar(lambda: ultimo(bus).video_remoto)


def test_ligar_a_camera_numa_chamada_por_link_de_voz_pede_video(mundo_video):
    v, ponte, bus, _ = mundo_video
    v.entrar_por_link("tok", False, "", "")
    assert esperar(lambda: ponte.entradas)
    ponte.fila.put({"ev": "ready", "call": "L1"})
    assert esperar(lambda: (ch.EM_CHAMADA, "") in bus.estados())
    v.ligar_camera("link:chamada", "Câmera A")
    assert esperar(lambda: v.video.cameras_abertas == ["Câmera A"])
    assert ("L1", cw.VIDEO_PEDIR) in ponte.acoes_de_video
    assert esperar(lambda: ultimo(bus).camera)


# ---------------------------------------------------------- o mosaico
def quadro(cor, larg=64, alt=36):
    return larg, alt, bytes([cor]) * (larg * alt * 3)


def test_mosaico_com_um_participante_devolve_o_quadro_como_veio():
    m = midia_video.Mosaico(intervalo_s=0)
    assert m.atualizar("a", *quadro(10)) == quadro(10)


def test_mosaico_junta_participantes_em_grade():
    m = midia_video.Mosaico(intervalo_s=0)
    m.atualizar("a", *quadro(10))
    larg, alt, rgb = m.atualizar("b", *quadro(200))
    assert (larg, alt) == (640, 180)          # 2 colunas, 1 linha
    assert len(rgb) == larg * alt * 3
    m.atualizar("c", *quadro(90))
    larg, alt, _ = m.atualizar("d", *quadro(90))
    assert (larg, alt) == (640, 360)          # 2 x 2


def test_mosaico_tira_quem_ficou_sem_mandar_quadro():
    t = [0.0]
    m = midia_video.Mosaico(validade_s=4, intervalo_s=0, agora=lambda: t[0])
    m.atualizar("a", *quadro(10))
    m.atualizar("b", *quadro(20))
    t[0] = 10
    m.atualizar("b", *quadro(20))
    assert m.participantes() == ["b"]


def test_mosaico_nao_monta_mais_rapido_que_o_intervalo():
    t = [0.0]
    m = midia_video.Mosaico(intervalo_s=0.5, agora=lambda: t[0])
    assert m.atualizar("a", *quadro(10)) is not None
    t[0] = 0.1
    assert m.atualizar("a", *quadro(11)) is None
    t[0] = 0.7
    assert m.atualizar("a", *quadro(12)) is not None


# ------------------------------------------------- a ponte e o video
def test_ponte_le_o_video_de_um_participante():
    class Go:
        def CallReadParticipantVideo(self, uuid, call, who, wcap, buf, cap,
                                     ms):
            who.value = b"1@lid"
            buf.raw = b"abc" + bytes(cap - 3)
            return 3

        def CallDialWith(self): ...
        def CallVideo(self): ...
        def CallWriteVideo(self): ...
        def CallReadVideo(self): ...

    import ctypes
    p = cw.Ponte.__new__(cw.Ponte)
    p.uuid, p.go = b"u", Go()
    p._buf_quem = ctypes.create_string_buffer(256)
    p._buf_video = ctypes.create_string_buffer(cw.BYTES_DO_VIDEO)
    assert p.suporta_video_de_participantes()
    assert p.ler_video_de_participante("L1") == ("1@lid", b"abc")


# ---------------------------------------- sala de espera, reacao e mao
class PonteDeControles(PonteDeLink):
    def __init__(self):
        super().__init__()
        self.admitidos, self.negados = [], []
        self.aprovacao, self.reacoes, self.maos = [], [], []

    def suporta_video_de_participantes(self):
        return False

    def admitir(self, chamada, quem, aceitar=True):
        (self.admitidos if aceitar else self.negados).append((chamada, quem))
        return True

    def exigir_aprovacao(self, chamada, ligado):
        self.aprovacao.append(ligado)
        return True

    def reagir(self, chamada, emoji):
        self.reacoes.append(emoji)
        return True

    def levantar_mao(self, chamada, levantada):
        self.maos.append(levantada)
        return True


@pytest.fixture
def mundo_controles():
    ponte, bus, audio = PonteDeControles(), Barramento(), AudioFalso()
    v = cw.ChamadasWhatsApp(
        ponte, "w1", bus, conversa_do_peer=lambda peer: CID,
        nome_de=lambda cid: "Ana", destino_de=lambda cid: "5551",
        audio=audio, espera_s=0.3)
    v.link_ligado = lambda: True
    v.nome_de_jid = lambda jid, pn="": {"7@lid": "Bia"}.get(jid, "")
    v.iniciar()
    v.entrar_por_link("tok", False, "", "")
    assert esperar(lambda: ponte.entradas)
    yield v, ponte, bus
    v.parar()
    ponte.fim = True


CID_LINK = "link:chamada"
SALA = {"ev": "waiting", "call": "L1", "admin": True, "enabled": True,
        "users": [{"jid": "7@lid"}]}


def test_quem_entra_na_sala_e_anunciado_ao_anfitriao(mundo_controles):
    v, ponte, bus = mundo_controles
    ponte.fila.put(dict(SALA))
    assert esperar(lambda: any("Bia quer entrar" in a for a in avisos(bus)))
    assert v.sala_de_espera(CID_LINK) == [("7@lid", "Bia")]
    assert v.sou_anfitriao(CID_LINK) and v.aprovacao_exigida(CID_LINK)
    ponte.fila.put(dict(SALA))                # o mesmo de novo: sem repetir
    esperar(lambda: False, 0.2)
    assert sum("quer entrar" in a for a in avisos(bus)) == 1


def test_quem_nao_e_anfitriao_nao_recebe_aviso_da_sala(mundo_controles):
    v, ponte, bus = mundo_controles
    ponte.fila.put(dict(SALA, admin=False))
    esperar(lambda: False, 0.2)
    assert not any("quer entrar" in a for a in avisos(bus))
    assert not v.sou_anfitriao(CID_LINK)


def test_admitir_e_recusar_pela_sala(mundo_controles):
    v, ponte, bus = mundo_controles
    v.tratar_sala_de_espera(CID_LINK, ["7@lid"], True)
    assert esperar(lambda: ponte.admitidos == [("L1", "7@lid")])
    assert esperar(lambda: any("deixei entrar 1 pessoa" in a
                               for a in avisos(bus)))
    v.tratar_sala_de_espera(CID_LINK, ["8@lid"], False)
    assert esperar(lambda: ponte.negados == [("L1", "8@lid")])


def test_aprovacao_reacao_e_mao(mundo_controles):
    v, ponte, bus = mundo_controles
    v.exigir_aprovacao(CID_LINK, True)
    v.reagir(CID_LINK, "👍")
    v.alternar_mao(CID_LINK)
    assert esperar(lambda: ponte.aprovacao == [True]
                   and ponte.reacoes == ["👍"] and ponte.maos == [True])
    v.alternar_mao(CID_LINK)
    assert esperar(lambda: ponte.maos == [True, False])
    assert any("Mão baixada" in a for a in avisos(bus))


def test_avisos_de_reacao_mao_e_tela_dos_outros(mundo_controles):
    v, ponte, bus = mundo_controles
    for e in ({"ev": "reaction", "call": "L1", "emoji": "🎉",
               "who": "7@lid"},
              {"ev": "hand", "call": "L1", "who": "7@lid", "raised": True},
              {"ev": "screen", "call": "L1", "who": "7@lid",
               "active": True}):
        ponte.fila.put(e)
    assert esperar(lambda: len(avisos(bus)) >= 3)
    textos = " ".join(avisos(bus))
    assert "Bia reagiu com 🎉" in textos
    assert "Bia levantou a mão" in textos
    assert "Bia começou a compartilhar a tela" in textos


def test_evento_da_sala_antes_do_id_da_chamada_nao_se_perde():
    ponte, bus, audio = PonteDeControles(), Barramento(), AudioFalso()
    v = cw.ChamadasWhatsApp(
        ponte, "w1", bus, conversa_do_peer=lambda peer: CID,
        nome_de=lambda cid: "Ana", destino_de=lambda cid: "5551",
        audio=audio, espera_s=0.3)
    v.link_ligado = lambda: True
    v.nome_de_jid = lambda jid, pn="": "Bia"
    v.iniciar()
    ponte.fila.put(dict(SALA))                # chega antes de a entrada voltar
    esperar(lambda: False, 0.2)
    v.entrar_por_link("tok", False, "", "")
    assert esperar(lambda: any("quer entrar" in a for a in avisos(bus)))
    v.parar()
    ponte.fim = True


def test_ponte_dos_controles_de_grupo():
    p = ponte_com({
        "CallWaitingAdmit": '{"ok": true}', "CallWaitingDeny": '{"ok": true}',
        "CallApprovalRequired": '{"ok": true}', "CallReact": '{"ok": true}',
        "CallHand": '{"error": "x"}'})
    assert p.suporta_controles_de_grupo()
    assert p.admitir("L1", "7@lid") and p.admitir("L1", "7@lid", False)
    assert p.exigir_aprovacao("L1", True) and p.reagir("L1", "👍")
    assert not p.levantar_mao("L1", True)
    assert not ponte_com({}).suporta_controles_de_grupo()


# ------------------------------- maos, historico e video de uma pessoa so
def test_lista_de_maos_levantadas_e_historico(mundo_controles):
    v, ponte, bus = mundo_controles
    ponte.fila.put({"ev": "hand", "call": "L1", "who": "7@lid",
                    "raised": True})
    assert esperar(lambda: v.maos_levantadas(CID_LINK) == ["Bia"])
    ponte.fila.put({"ev": "reaction", "call": "L1", "emoji": "🎉",
                    "who": "7@lid"})
    ponte.fila.put({"ev": "hand", "call": "L1", "who": "7@lid",
                    "raised": False})
    assert esperar(lambda: v.maos_levantadas(CID_LINK) == [])
    linhas = v.historico_da_chamada(CID_LINK)
    assert [l[6:] for l in linhas] == [
        "Bia levantou a mão.", "Bia reagiu com 🎉.", "Bia baixou a mão."]


def test_video_de_uma_pessoa_so(mundo_video):
    v, ponte, bus, quadros = mundo_video
    v.nome_de_jid = lambda jid, pn="": {"1@lid": "Bia"}.get(jid, "")
    v.entrar_por_link("tok", True, "", "")
    assert esperar(lambda: ponte.entradas)
    ponte.fila.put({"ev": "ready", "call": "L1"})
    assert esperar(lambda: v.ligacoes["link:chamada"].recebendo_video)
    ponte.por_participante.put(("1@lid", b"a"))
    ponte.por_participante.put(("2@lid", b"b"))
    assert esperar(lambda: len(v.participantes_com_video("link:chamada")) == 2)
    assert v.participantes_com_video("link:chamada") == [
        ("1@lid", "Bia"), ("2@lid", "Participante 2")]
    v.escolher_video("link:chamada", "2@lid")
    quadros.clear()
    v.video.quadros_decodificados = [(6, 2, b"\x07" * 36)]
    ponte.por_participante.put(("1@lid", b"c"))      # de outra pessoa: some
    ponte.por_participante.put(("2@lid", b"d"))
    assert esperar(lambda: quadros)
    assert all(q[1:3] == (6, 2) for q in quadros) and len(quadros) == 1
    v.escolher_video("link:chamada", None)
    esperar(lambda: False, 0.15)               # passa o intervalo da grade
    ponte.por_participante.put(("1@lid", b"e"))
    assert esperar(lambda: len(quadros) >= 2)

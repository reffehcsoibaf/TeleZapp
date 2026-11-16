# SPDX-License-Identifier: GPL-3.0-or-later
"""Chat de voz de grupo e live de canal do Telegram (recurso experimental):
modelo e textos (nucleo), provedor com um py-tgcalls simulado e a opcao da
categoria Recursos experimentais."""
import asyncio
import enum
import sys
import types

from testes import wx_falso

sys.modules.setdefault("wx", wx_falso)

from telezapp import config  # noqa: E402
from telezapp.nucleo import chat_de_voz as cv  # noqa: E402
from telezapp.nucleo import configuracoes as cfgmod  # noqa: E402
from telezapp.nucleo import eventos as ev  # noqa: E402
from telezapp.provedores import chamadas_telegram as ct  # noqa: E402
from telezapp.provedores import chat_de_voz_telegram as cvt  # noqa: E402
from testes.test_chamadas import AppFalso, Dispositivo  # noqa: E402

GRUPO = -1001234567890


# ------------------------------------------------------------- nucleo
def test_ordem_da_lista_eu_primeiro_depois_mao_depois_microfone_aberto():
    ps = [cv.Participante(1, "Zeca", mudo=True),
          cv.Participante(2, "Bia", mudo=False),
          cv.Participante(3, "Caio", mudo=True, mao=True),
          cv.Participante(4, "Eu mesmo", mudo=True, eu=True)]
    assert [p.nome for p in cv.ordenar(ps)] == [
        "Eu mesmo", "Caio", "Bia", "Zeca"]


def test_rotulo_diz_o_estado_de_cada_um():
    assert cv.rotulo(cv.Participante(1, "Ana", mudo=True)) == \
        "Ana, silenciado"
    assert cv.rotulo(cv.Participante(1, "Ana", mudo=False)) == \
        "Ana, microfone aberto"
    assert cv.rotulo(cv.Participante(1, "Ana", mao=True)) == \
        "Ana, mão levantada"
    assert cv.rotulo(cv.Participante(1, "Fábio", eu=True)) == \
        "Fábio, você, silenciado"


def test_lista_tem_limite():
    muitos = [cv.Participante(i, "P%03d" % i) for i in range(500)]
    assert len(cv.rotulos(muitos)) == cv.LISTA_MAXIMA


def test_avisos_de_entrada_so_em_chat_pequeno():
    assert cv.avisos_ligados(15) and not cv.avisos_ligados(16)
    assert cv.aviso_de_entrada("Ana", True) == "Ana entrou."
    assert cv.aviso_de_entrada("Ana", False) == "Ana saiu."
    assert cv.aviso_de_mao("Ana") == "Ana levantou a mão."


def _evento(estado, **kw):
    return ev.EstadoChatDeVoz("t1", str(GRUPO), estado, "Amigos", **kw)


def test_entrando_so_tem_sair_e_avisa_que_e_experimental():
    c = cv.ChatDeVoz("t1", str(GRUPO), "Amigos")
    a = cv.apresentar(c)
    assert a.botoes == (cv.SAIR,) and a.foco == cv.SAIR
    assert "experimental" in a.fala


def test_dentro_com_microfone_tem_falar_e_mao_e_foca_sair():
    c = cv.ChatDeVoz("t1", str(GRUPO), "Amigos")
    c.aplicar(_evento(cv.DENTRO, total=7))
    a = cv.apresentar(c)
    assert a.botoes == (cv.FALAR, cv.MAO, cv.QUEM, cv.TEMPO, cv.SAIR)
    assert a.foco == cv.SAIR and a.som == "conectado"
    assert "silenciado" in a.fala and "7 participantes" in a.fala


def test_live_so_ouve():
    c = cv.ChatDeVoz("t1", str(GRUPO), "Canal")
    c.aplicar(_evento(cv.DENTRO, ao_vivo=True, ouvinte=True, total=1))
    a = cv.apresentar(c)
    assert a.botoes == (cv.QUEM, cv.TEMPO, cv.SAIR)
    assert "só ouve" in a.fala and a.titulo.startswith("Live")


def test_encerrado_so_tem_fechar_e_diz_o_motivo():
    c = cv.ChatDeVoz("t1", str(GRUPO), "Amigos")
    c.aplicar(_evento(cv.ENCERRADO, motivo=cv.TERMINOU))
    a = cv.apresentar(c)
    assert a.botoes == (cv.FECHAR,)
    assert "terminou" in a.fala
    c.aplicar(_evento(cv.ENCERRADO, motivo=cv.REMOVIDO))
    assert "removido" in cv.texto_encerramento(c)


def test_tempo_corre_so_dentro():
    t = [10.0]
    c = cv.ChatDeVoz("t1", "1", "A", _agora=lambda: t[0])
    assert c.segundos() == 0
    c.aplicar(_evento(cv.DENTRO))
    t[0] = 75.0
    assert c.segundos() == 65.0


def test_aplicar_devolve_se_o_estado_mudou():
    c = cv.ChatDeVoz("t1", "1", "A")
    assert c.aplicar(_evento(cv.DENTRO)) is True
    assert c.aplicar(_evento(cv.DENTRO, aviso="Ana entrou.")) is False


def test_excecoes_viram_frases():
    class NoActiveGroupCall(Exception):
        pass
    assert "Não há chat de voz" in cv.motivo_da_excecao(NoActiveGroupCall())
    assert "Não consegui entrar" in cv.motivo_da_excecao(ValueError())


# ----------------------------------------------------------- opcao
def test_opcao_e_desligada_e_fica_em_recursos_experimentais():
    o = next(x for x in config.OPCOES if x.chave == "chat_de_voz_telegram")
    assert o.categoria == "Recursos experimentais" == \
        config.CATEGORIA_EXPERIMENTAL
    assert o.padrao is False and not o.grupo
    assert "experimental" in o.descricao.lower()


def test_categoria_aparece_antes_de_sistema():
    cats = cfgmod.categorias()
    assert "Recursos experimentais" in cats
    assert cats.index("Recursos experimentais") < cats.index("Sistema")


def test_aviso_so_para_recursos_experimentais():
    o = next(x for x in config.OPCOES if x.chave == "chat_de_voz_telegram")
    texto = cfgmod.aviso_experimental(o)
    assert o.rotulo in texto and "experimental" in texto
    assert "nas próximas versões" in texto
    outra = next(x for x in config.OPCOES
                 if x.categoria != config.CATEGORIA_EXPERIMENTAL)
    assert cfgmod.aviso_experimental(outra) is None


# ------------------------------------------------- provedor (py-tgcalls falso)
class Acao(enum.Flag):
    JOINED = enum.auto()
    LEFT = enum.auto()
    KICKED = enum.auto()
    UPDATED = enum.auto()


class Status(enum.Flag):
    INCOMING_CALL = enum.auto()
    KICKED = enum.auto()
    LEFT_GROUP = enum.auto()
    CLOSED_VOICE_CHAT = enum.auto()
    DISCARDED_CALL = enum.auto()
    LEFT_CALL = KICKED | LEFT_GROUP | CLOSED_VOICE_CHAT | DISCARDED_CALL


class App(AppFalso):
    def __init__(self, cliente):
        super().__init__(cliente)
        self.configs = []
        self.lista = []
        self.erro_play = None

    async def play(self, chat_id, fluxo, config=None):
        self.configs.append(config)
        await super().play(chat_id, fluxo, config)

    async def get_participants(self, chat_id):
        return self.lista


class Motor:
    app = None

    def __init__(self):
        self.filters = types.SimpleNamespace(
            chat_update=lambda s: ("chat_update", s),
            call_participant=lambda: "participantes")
        self.ChatUpdate = types.SimpleNamespace(Status=Status)
        self.AcaoParticipante = Acao
        self.GroupCallConfig = lambda auto_start=True: ("grupo", auto_start)

    def PyTgCalls(self, cliente):
        Motor.app = App(cliente)
        return Motor.app

    def filtro_participantes(self):
        return self.filters.call_participant()

    def microfones(self):
        return [Dispositivo("Padrão"), Dispositivo("Headset")]

    def saidas(self):
        return [Dispositivo("Alto-falantes"), Dispositivo("Fones")]

    def fluxo_microfone(self, d):
        return ("mic", d.title)

    def fluxo_saida(self, d, camera=False, tela=False):
        return ("saida", d.title, camera, tela) if (camera or tela) \
            else ("saida", d.title)


def part(uid, muted=True, mao=False, admin=False):
    return types.SimpleNamespace(user_id=uid, muted=muted, raised_hand=mao,
                                 muted_by_admin=admin)


def up(acao, p, chat=GRUPO):
    return types.SimpleNamespace(chat_id=chat, action=acao, participant=p)


class Sala:
    def __init__(self, info=None):
        self.eventos = []
        b = ev.Barramento()
        b.ouvir(self.eventos.append)
        nomes = {1: "Ana", 2: "Bruno", 3: "Carla", 99: "Fábio"}

        async def nome_de(chat_id):
            return nomes.get(chat_id, "Grupo")
        self.chamadas = ct.ChamadasTelegram(object(), "t1", b, nome_de,
                                            motor=Motor, espera_s=1)
        self.maos = []
        self.info = info if info is not None else cvt.Info(
            True, "Papo", total=2, chamada="call",
            nomes={1: "Ana", 99: "Fábio"},
            iniciais=[(1, True, False), (99, True, False)])

    async def iniciar(self):
        assert await self.chamadas.iniciar()
        g = self.chamadas.grupo
        sala = self

        async def buscar(chat_id):
            return sala.info

        async def meu_id():
            return 99

        async def editar_mao(s, sim):
            sala.maos.append(sim)
        g._buscar_info, g._meu_id, g._editar_mao = buscar, meu_id, editar_mao
        return g

    def estados(self):
        return [e.estado for e in self.eventos
                if isinstance(e, ev.EstadoChatDeVoz)]

    def avisos(self):
        return [e.texto for e in self.eventos if isinstance(e, ev.Aviso)]

    def ultimo(self):
        return [e for e in self.eventos
                if isinstance(e, ev.EstadoChatDeVoz)][-1]


def rodar(c):
    return asyncio.run(c)


def test_entrar_conecta_mudo_e_lista_os_participantes():
    s = Sala()

    async def cena():
        g = await s.iniciar()
        await g.entrar(GRUPO, "Headset", "Fones")
    rodar(cena())
    assert s.estados() == [cv.CONECTANDO, cv.DENTRO, cv.DENTRO][:len(
        s.estados())] and s.estados()[0] == cv.CONECTANDO
    assert s.ultimo().estado == cv.DENTRO and s.ultimo().mudo is True
    acoes = Motor.app.chamadas
    assert ("play", GRUPO, ("mic", "Headset")) in acoes
    assert ("mute", GRUPO, None) in acoes
    assert ("record", GRUPO, ("saida", "Fones")) in acoes
    assert Motor.app.configs[-1] == ("grupo", False)   # nunca cria o chat
    nomes = {p[1] for p in s.ultimo().participantes}
    assert nomes == {"Ana", "Fábio"}
    assert [p for p in s.ultimo().participantes if p[4]][0][1] == "Fábio"


def test_sem_chat_de_voz_ativo_so_avisa():
    s = Sala(cvt.Info(False))

    async def cena():
        g = await s.iniciar()
        await g.entrar(GRUPO)
    rodar(cena())
    assert s.avisos() == ["Não há chat de voz ativo nesta conversa."]
    assert s.estados() == [] and \
        not [a for a in Motor.app.chamadas if a[0] == "play"]


def test_agendado_ainda_nao_entra():
    s = Sala(cvt.Info(True, agendada=object()))

    async def cena():
        g = await s.iniciar()
        await g.entrar(GRUPO)
    rodar(cena())
    assert "agendado" in s.avisos()[0] and s.estados() == []


def test_live_entra_sem_microfone_e_sem_silenciar():
    s = Sala(cvt.Info(True, "Live", ao_vivo=True, total=40))

    async def cena():
        g = await s.iniciar()
        await g.entrar(GRUPO)
    rodar(cena())
    acoes = Motor.app.chamadas
    assert ("play", GRUPO, None) in acoes
    assert not [a for a in acoes if a[0] == "mute"]
    u = s.ultimo()
    assert u.ouvinte and u.ao_vivo and u.estado == cv.DENTRO


def test_canal_de_transmissao_tambem_so_ouve():
    s = Sala(cvt.Info(True, "Canal", transmissao=True))

    async def cena():
        g = await s.iniciar()
        await g.entrar(GRUPO)
    rodar(cena())
    assert s.ultimo().ouvinte is True


def test_nao_entra_com_uma_chamada_1_a_1_aberta():
    s = Sala()

    async def cena():
        g = await s.iniciar()
        s.chamadas.chamadas[10] = object()
        await g.entrar(GRUPO)
    rodar(cena())
    assert "Já há uma chamada" in s.avisos()[0] and s.estados() == []


def test_chamada_1_a_1_nao_liga_com_chat_de_voz_aberto():
    s = Sala()

    async def cena():
        g = await s.iniciar()
        await g.entrar(GRUPO)
        await s.chamadas.ligar(10)
    rodar(cena())
    assert not [a for a in Motor.app.chamadas
                if a[0] == "play" and a[1] == 10]


def test_falha_ao_entrar_encerra_com_a_frase():
    class NoActiveGroupCall(Exception):
        pass
    s = Sala()

    async def cena():
        g = await s.iniciar()
        Motor.app.erro_play = NoActiveGroupCall()
        await g.entrar(GRUPO)
        assert g.sessao is None
    rodar(cena())
    u = s.ultimo()
    assert (u.estado, u.motivo) == (cv.ENCERRADO, cv.FALHA)
    assert u.erro == "Não há chat de voz ativo nesta conversa."
    assert ("leave", GRUPO, None) in Motor.app.chamadas


async def _dentro(s):
    g = await s.iniciar()
    await g.entrar(GRUPO)
    return g


def test_quem_entra_e_sai_e_avisado_em_chat_pequeno():
    s = Sala()

    async def cena():
        g = await _dentro(s)
        await g.ao_participante(None, up(Acao.JOINED, part(2)))
        assert s.ultimo().aviso == "Bruno entrou."
        assert "Bruno" in {p[1] for p in s.ultimo().participantes}
        await g.ao_participante(None, up(Acao.LEFT, part(2)))
        assert s.ultimo().aviso == "Bruno saiu."
        assert "Bruno" not in {p[1] for p in s.ultimo().participantes}
    rodar(cena())


def test_entrada_propria_nao_gera_aviso():
    s = Sala()

    async def cena():
        g = await _dentro(s)
        await g.ao_participante(None, up(Acao.UPDATED, part(99, muted=True)))
        assert s.ultimo().aviso == ""
    rodar(cena())


def test_em_chat_grande_os_avisos_ficam_calados():
    s = Sala(cvt.Info(True, "Grande", total=300, chamada="c"))

    async def cena():
        g = await _dentro(s)
        await g.ao_participante(None, up(Acao.JOINED, part(2)))
        assert s.ultimo().aviso == ""
        assert s.ultimo().total >= 300
    rodar(cena())


def test_mao_levantada_de_outro_e_avisada_uma_vez():
    s = Sala()

    async def cena():
        g = await _dentro(s)
        await g.ao_participante(None, up(Acao.UPDATED, part(1, mao=True)))
        assert s.ultimo().aviso == "Ana levantou a mão."
        await g.ao_participante(None, up(Acao.UPDATED, part(1, mao=True)))
        assert s.ultimo().aviso == ""
    rodar(cena())


def test_atualizacao_de_outro_chat_e_ignorada():
    s = Sala()

    async def cena():
        g = await _dentro(s)
        antes = len(s.eventos)
        await g.ao_participante(None, up(Acao.JOINED, part(2), chat=-5))
        assert len(s.eventos) == antes
    rodar(cena())


def test_abrir_e_fechar_o_microfone():
    s = Sala()

    async def cena():
        g = await _dentro(s)
        await g.silenciar(False)
        assert s.ultimo().mudo is False
        await g.silenciar(True)
        assert s.ultimo().mudo is True
    rodar(cena())
    acoes = [a[0] for a in Motor.app.chamadas]
    assert "unmute" in acoes and acoes.count("mute") == 2


def test_administrador_nao_liberou_o_microfone():
    s = Sala()

    async def cena():
        g = await _dentro(s)
        await g.ao_participante(
            None, up(Acao.UPDATED, part(99, muted=True, admin=True)))
        await g.silenciar(False)
    rodar(cena())
    assert "administrador não liberou" in s.avisos()[-1]
    assert not [a for a in Motor.app.chamadas if a[0] == "unmute"]


def test_levantar_e_baixar_a_mao():
    s = Sala()

    async def cena():
        g = await _dentro(s)
        await g.levantar_mao(True)
        assert s.ultimo().mao is True
        await g.levantar_mao(False)
        assert s.ultimo().mao is False
    rodar(cena())
    assert s.maos == [True, False]


def test_ouvinte_nao_tem_microfone_nem_mao():
    s = Sala(cvt.Info(True, "Live", ao_vivo=True, chamada="c"))

    async def cena():
        g = await _dentro(s)
        await g.silenciar(False)
        await g.levantar_mao(True)
    rodar(cena())
    assert s.maos == []
    assert not [a for a in Motor.app.chamadas if a[0] == "unmute"]


def test_sair_encerra_e_deixa_o_chat_de_voz():
    s = Sala()

    async def cena():
        g = await _dentro(s)
        await g.sair()
        assert g.sessao is None
    rodar(cena())
    u = s.ultimo()
    assert (u.estado, u.motivo) == (cv.ENCERRADO, cv.SAIU)
    assert ("leave", GRUPO, None) in Motor.app.chamadas


def test_chat_de_voz_encerrado_pelo_dono_chega_pelo_ao_sair_da_chamada():
    s = Sala()

    async def cena():
        g = await _dentro(s)
        await s.chamadas._ao_sair(None, types.SimpleNamespace(
            chat_id=GRUPO, status=Status.CLOSED_VOICE_CHAT))
        assert g.sessao is None
    rodar(cena())
    assert (s.ultimo().estado, s.ultimo().motivo) == (cv.ENCERRADO,
                                                       cv.TERMINOU)


def test_removido_do_chat_de_voz():
    s = Sala()

    async def cena():
        g = await _dentro(s)
        assert await g.ao_sair(types.SimpleNamespace(
            chat_id=GRUPO, status=Status.KICKED)) is True
    rodar(cena())
    assert s.ultimo().motivo == cv.REMOVIDO


def test_ao_sair_de_outro_chat_nao_e_com_o_chat_de_voz():
    s = Sala()

    async def cena():
        g = await _dentro(s)
        assert await g.ao_sair(types.SimpleNamespace(
            chat_id=10, status=Status.KICKED)) is False
        assert g.sessao is not None
    rodar(cena())


def test_sem_py_tgcalls_de_grupo_o_chat_de_voz_fica_desligado():
    class MotorAntigo(Motor):
        def __init__(self):
            super().__init__()
            del self.GroupCallConfig

        filtro_participantes = None
    del MotorAntigo.filtro_participantes
    b = ev.Barramento()

    async def nome_de(i):
        return "x"
    c = ct.ChamadasTelegram(object(), "t1", b, nome_de, motor=MotorAntigo)

    async def cena():
        assert await c.iniciar()
    rodar(cena())
    assert c.grupo is None


# ================================================== fase 2: quem fala,
# avisos de inicio, marca na lista e video
def test_quem_esta_falando_vai_para_o_topo_e_a_frase_diz_quem():
    ps = [cv.Participante(1, "Zeca"), cv.Participante(2, "Bia", mudo=False),
          cv.Participante(3, "Caio", falando=True, mudo=False),
          cv.Participante(4, "Eu", eu=True, mudo=False, falando=True)]
    assert [p.nome for p in cv.ordenar(ps)] == ["Eu", "Caio", "Bia", "Zeca"]
    assert cv.rotulo(ps[2]) == "Caio, falando"
    assert cv.quem_fala(ps) == "você e Caio estão falando."
    assert cv.quem_fala([cv.Participante(1, "Ana", falando=True)]) == \
        "Ana está falando."
    assert cv.quem_fala([cv.Participante(1, "Ana")]) == \
        "Ninguém está falando agora."


def test_frases_de_inicio_e_marca_da_lista():
    assert cv.texto_de_inicio("Amigos", False) == \
        "Chat de voz começou em Amigos."
    assert cv.texto_de_inicio("Canal", True) == "Live começou em Canal."
    assert cv.marca_na_lista(True) == "live em andamento"
    assert cv.marca_na_lista(False) == "chat de voz em andamento"


def test_dentro_tem_o_botao_quem_esta_falando():
    c = cv.ChatDeVoz("t1", str(GRUPO), "Amigos")
    c.aplicar(_evento(cv.DENTRO))
    assert cv.QUEM in cv.apresentar(c).botoes


def test_linha_da_conversa_ganha_a_marca_do_chat_de_voz():
    from telezapp.nucleo import lista_conversas as lc
    from telezapp.nucleo import modelos as m
    c = m.Conversa("t1", str(GRUPO), "Amigos", "telegram", "grupo")
    assert "chat de voz em andamento" not in lc.rotulo(c)
    assert "chat de voz em andamento" in lc.rotulo(
        c, voz=cv.marca_na_lista(False))
    assert lc.rotulo(c, voz="live em andamento").count(
        "live em andamento") == 1


def _ativ(uid, ha_segundos=0, call_id=7):
    """Um UpdateGroupCallParticipants bruto com `active_date`."""
    import time as t
    from telethon.tl import types as tt
    p = types.SimpleNamespace(peer=tt.PeerUser(uid), left=False,
                              active_date=t.time() - ha_segundos)
    return types.SimpleNamespace(call=types.SimpleNamespace(id=call_id),
                                 participants=[p])


def _sala_com_chamada():
    return Sala(cvt.Info(
        True, "Papo", total=2, chamada=types.SimpleNamespace(id=7),
        iniciais=[(1, True, False), (99, True, False)],
        nomes={1: "Ana", 99: "Fábio"}))


class UpdateGroupCallParticipants:
    def __init__(self, call, participants):
        self.call, self.participants = call, participants


def _bruto(u):
    return UpdateGroupCallParticipants(u.call, u.participants)


def test_quem_falou_agora_aparece_falando_e_depois_de_3_s_para():
    s = _sala_com_chamada()

    async def cena():
        g = await _dentro(s)
        await g.ao_bruto(_bruto(_ativ(1)))
        falando = {p[1] for p in s.ultimo().participantes if p[5]}
        assert falando == {"Ana"}
        g.sessao.falando[1] -= cvt.FALANDO_S + 1       # calou faz tempo
        g._publicar()
        assert not [p for p in s.ultimo().participantes if p[5]]
    rodar(cena())


def test_atividade_antiga_ou_de_outra_chamada_nao_conta():
    s = _sala_com_chamada()

    async def cena():
        g = await _dentro(s)
        antes = len(s.eventos)
        await g.ao_bruto(_bruto(_ativ(1, ha_segundos=30)))
        await g.ao_bruto(_bruto(_ativ(1, call_id=999)))
        assert len(s.eventos) == antes
    rodar(cena())


def test_vigia_apaga_o_falando_sozinha():
    s = _sala_com_chamada()

    async def cena():
        g = await _dentro(s)
        await g.ao_bruto(_bruto(_ativ(1)))
        assert [p for p in s.ultimo().participantes if p[5]]
        g.sessao.falando[1] -= cvt.FALANDO_S + 1
        await asyncio.sleep(1.3)                  # a vigia roda a cada 1 s
        assert not [p for p in s.ultimo().participantes if p[5]]
        await g.sair()
    rodar(cena())


class UpdateNewChannelMessage:
    def __init__(self, message):
        self.message = message


class MessageActionGroupCall:
    def __init__(self, duration=None):
        self.duration = duration


class MessageService:
    def __init__(self, chat, duration=None):
        from telethon.tl import types as tt
        self.peer_id = tt.PeerChannel(abs(chat) - 1000000000000)
        self.action = MessageActionGroupCall(duration)


class UpdateGroupCall:
    def __init__(self, chat, call):
        from telethon.tl import types as tt
        self.peer = tt.PeerChannel(abs(chat) - 1000000000000)
        self.call = call


class GroupCall:
    def __init__(self, rtmp=False, agendada=None):
        self.rtmp_stream, self.schedule_date = rtmp, agendada


class GroupCallDiscarded:
    pass


def _ativos(s):
    return [e for e in s.eventos if isinstance(e, ev.ChatDeVozAtivo)]


def test_chat_de_voz_iniciado_gera_aviso_uma_vez_e_o_fim_limpa_a_marca():
    s = Sala()

    async def cena():
        g = await s.iniciar()

        async def get_entity(chat):
            return types.SimpleNamespace(broadcast=False)
        s.chamadas.cliente = types.SimpleNamespace(get_entity=get_entity)
        await g.ao_bruto(UpdateNewChannelMessage(MessageService(GRUPO)))
        await g.ao_bruto(UpdateGroupCall(GRUPO, GroupCall()))
        await g.ao_bruto(UpdateGroupCall(GRUPO, GroupCall()))     # repetido
        a = _ativos(s)
        assert [(x.ativo, x.iniciou) for x in a] == [(True, True)]
        assert a[0].conversa_id == str(GRUPO) and a[0].ao_vivo is False
        await g.ao_bruto(UpdateGroupCall(GRUPO, GroupCallDiscarded()))
        assert [(x.ativo, x.iniciou) for x in _ativos(s)][-1] == (False,
                                                                    False)
    rodar(cena())


def test_live_de_canal_e_marcada_como_ao_vivo():
    s = Sala()

    async def cena():
        g = await s.iniciar()
        await g.ao_bruto(UpdateGroupCall(GRUPO, GroupCall(rtmp=True)))
        assert _ativos(s)[-1].ao_vivo is True
    rodar(cena())


def test_chat_de_voz_agendado_nao_conta_como_em_andamento():
    s = Sala()

    async def cena():
        g = await s.iniciar()
        await g.ao_bruto(UpdateGroupCall(GRUPO,
                                         GroupCall(agendada=object())))
        assert _ativos(s) == [] or _ativos(s)[-1].ativo is False
    rodar(cena())


def test_mensagem_de_servico_com_duracao_diz_que_acabou():
    s = Sala()

    async def cena():
        g = await s.iniciar()
        await g.ao_bruto(UpdateNewChannelMessage(
            MessageService(GRUPO, duration=120)))
        assert [(x.ativo, x.iniciou) for x in _ativos(s)] == [(False, False)]
    rodar(cena())


def test_erro_num_aviso_bruto_nao_derruba():
    s = Sala()

    async def cena():
        g = await s.iniciar()
        await g.ao_bruto(types.SimpleNamespace())          # tipo qualquer
        sem_nada = UpdateGroupCall.__new__(UpdateGroupCall)  # sem atributos
        await g.ao_bruto(sem_nada)
    rodar(cena())


def _com_video(monkeypatch):
    from telezapp import config as cfg
    original = cfg.Config.get
    monkeypatch.setattr(
        cfg.Config, "get",
        lambda self, k, *a: True if k == "chat_de_voz_video"
        else original(self, k, *a))


def test_com_a_caixa_do_video_pede_camera_e_tela_na_saida(monkeypatch):
    _com_video(monkeypatch)
    s = Sala()

    async def cena():
        g = await s.iniciar()
        await g.entrar(GRUPO, "Headset", "Fones")
        assert g.aceita_quadros(GRUPO)
    rodar(cena())
    assert ("record", GRUPO, ("saida", "Fones", True, True)) in \
        Motor.app.chamadas


def test_sem_a_caixa_do_video_so_o_som_e_os_quadros_nao_passam():
    s = Sala()

    async def cena():
        g = await s.iniciar()
        await g.entrar(GRUPO, "Headset", "Fones")
        assert not g.aceita_quadros(GRUPO)
    rodar(cena())
    assert ("record", GRUPO, ("saida", "Fones")) in Motor.app.chamadas


def test_quadros_do_chat_de_voz_vao_para_a_janela_sem_marcar_chamada(
        monkeypatch):
    from testes.test_chamadas import quadro_bgra
    _com_video(monkeypatch)
    s = Sala()
    recebidos = []
    s.chamadas.destino_video = lambda *a: recebidos.append(a)

    async def cena():
        g = await s.iniciar()
        await g.entrar(GRUPO)
        q = quadro_bgra()
        q.chat_id = GRUPO
        await s.chamadas._ao_quadro(None, q)
        await s.chamadas._ao_quadro_do_grupo(None, q)
        q2 = quadro_bgra()
        q2.chat_id = -5                       # outro chat: ignorado
        await s.chamadas._ao_quadro(None, q2)
        await s.chamadas._ao_quadro_do_grupo(None, q2)
    rodar(cena())
    assert len(recebidos) == 2 and recebidos[0][0] == str(GRUPO)
    assert s.chamadas._ultimo_quadro == {}      # nao e video de chamada 1 a 1


def test_opcoes_novas_ficam_em_recursos_experimentais_desligadas():
    for chave in ("chat_de_voz_avisar_inicio", "chat_de_voz_video"):
        o = next(x for x in config.OPCOES if x.chave == chave)
        assert o.categoria == config.CATEGORIA_EXPERIMENTAL
        assert o.padrao is False and "experimental" in o.descricao.lower()


# ================================================== fase 3: iniciar um chat
# de voz e mandar camera, tela e som do computador
class MotorComVideo(Motor):
    def cameras(self):
        return [Dispositivo("Câmera A"), Dispositivo("Câmera B")]

    def fluxo_com_camera(self, camera, microfone):
        return ("camera", camera.title, microfone.title)


def sala_com_video(info=None):
    s = Sala(info)
    s.chamadas._motor_fabrica = MotorComVideo
    return s


def test_iniciar_cria_o_chat_de_voz_quando_nao_ha_e_entra_falando():
    s = Sala(cvt.Info(False))

    async def cena():
        g = await s.iniciar()
        s.info = cvt.Info(False)
        await g.entrar(GRUPO, "Headset", "Fones", criar=True)
    rodar(cena())
    assert Motor.app.configs[-1] == ("grupo", True)      # auto_start ligado
    u = s.ultimo()
    assert u.estado == cv.DENTRO and u.ouvinte is False
    assert s.avisos() == []


def test_iniciar_num_canal_de_transmissao_entra_falando_nao_so_ouvindo():
    s = Sala(cvt.Info(False, transmissao=True))

    async def cena():
        g = await s.iniciar()
        await g.entrar(GRUPO, criar=True)
    rodar(cena())
    assert s.ultimo().ouvinte is False
    assert ("play", GRUPO, ("mic", "Padrão")) in Motor.app.chamadas


def test_iniciar_quando_ja_existe_so_entra_sem_criar():
    s = Sala()

    async def cena():
        g = await s.iniciar()
        await g.entrar(GRUPO, criar=True)
    rodar(cena())
    assert Motor.app.configs[-1] == ("grupo", False)


def test_sem_pedir_para_iniciar_nunca_cria():
    s = Sala(cvt.Info(False))

    async def cena():
        g = await s.iniciar()
        await g.entrar(GRUPO)
    rodar(cena())
    assert Motor.app.configs == []
    assert s.avisos() == ["Não há chat de voz ativo nesta conversa."]


def test_so_administrador_inicia_e_a_frase_diz_isso():
    class ChatAdminRequiredError(Exception):
        pass
    s = Sala(cvt.Info(False))

    async def cena():
        g = await s.iniciar()
        Motor.app.erro_play = ChatAdminRequiredError()
        await g.entrar(GRUPO, criar=True)
    rodar(cena())
    assert s.ultimo().erro == "Só administradores podem iniciar um chat de voz aqui."
    assert cv.motivo_da_excecao(ValueError(), True) == \
        "Não consegui iniciar o chat de voz."


def test_ligar_a_camera_no_chat_de_voz_manda_a_camera_e_continua_mudo():
    s = sala_com_video()

    async def cena():
        g = await _dentro(s)
        assert s.ultimo().suporta_video is True
        await g.ligar_camera("Câmera B")
        assert s.ultimo().camera is True and s.ultimo().tela is False
        await g.desligar_camera()
        assert s.ultimo().camera is False
    rodar(cena())
    acoes = Motor.app.chamadas
    assert ("play", GRUPO, ("camera", "Câmera B", "Padrão")) in acoes
    assert [a[0] for a in acoes].count("mute") >= 2    # remutou a cada troca


def test_camera_tela_e_som_nao_valem_em_live():
    s = sala_com_video(cvt.Info(True, "Live", ao_vivo=True, chamada="c"))

    async def cena():
        g = await _dentro(s)
        assert g.sombra(GRUPO) is None
        await g.ligar_camera("Câmera A")
        await g.compartilhar_tela("", True)
        await g.compartilhar_som("")
    rodar(cena())
    assert s.avisos().count("Em uma live você só ouve.") == 3
    assert not [a for a in Motor.app.chamadas if a[0] == "play"
                and a[2] and a[2][0] == "camera"]


def test_administrador_nao_liberou_nao_manda_camera():
    s = sala_com_video()

    async def cena():
        g = await _dentro(s)
        await g.ao_participante(
            None, up(Acao.UPDATED, part(99, muted=True, admin=True)))
        await g.ligar_camera("Câmera A")
    rodar(cena())
    assert "O administrador não liberou a sua fala." in s.avisos()
    assert not [a for a in Motor.app.chamadas if a[0] == "play"
                and a[2] and a[2][0] == "camera"]


def test_o_estado_do_que_mandamos_vem_do_motor_das_chamadas():
    s = sala_com_video()

    async def cena():
        g = await _dentro(s)
        s.chamadas._tela[GRUPO] = {"nome": "Tela 1"}
        s.chamadas._cam[GRUPO] = ""
        g.marcar_midia()
        u = s.ultimo()
        # a tela vai pelo canal do video, mas nao e a camera
        assert (u.camera, u.tela, u.som_pc) == (False, True, False)
        s.chamadas._tela.pop(GRUPO)
        s.chamadas._som[GRUPO] = {}
        g.marcar_midia()
        u = s.ultimo()
        assert (u.camera, u.tela, u.som_pc) == (True, False, True)
        assert g.marcar_midia() is False                 # nada mudou
    rodar(cena())


def test_ao_sair_do_chat_de_voz_para_de_mandar_tudo():
    s = sala_com_video()

    async def cena():
        g = await _dentro(s)
        s.chamadas._cam[GRUPO] = ""
        await g.sair()
        assert GRUPO not in s.chamadas._cam
        assert GRUPO not in s.chamadas._escolhas
    rodar(cena())


def test_silenciar_com_o_som_do_computador_e_so_nosso():
    s = sala_com_video()

    async def cena():
        g = await _dentro(s)
        s.chamadas._som[GRUPO] = {}
        antes = [a[0] for a in Motor.app.chamadas]
        await g.silenciar(False)
        assert s.ultimo().mudo is False
        assert [a[0] for a in Motor.app.chamadas] == antes   # sem unmute
    rodar(cena())


def test_botoes_de_camera_tela_e_som_so_para_quem_fala():
    c = cv.ChatDeVoz("t1", str(GRUPO), "Amigos")
    c.aplicar(_evento(cv.DENTRO, suporta_video=True, suporta_tela=True,
                      suporta_som_pc=True))
    assert c.suporta_tela and cv.apresentar(c).botoes == (
        cv.FALAR, cv.MAO, cv.SOM_PC, cv.TELA, cv.CAMERA, cv.QUEM, cv.TEMPO,
        cv.SAIR)
    live = cv.ChatDeVoz("t1", "1", "Canal")
    live.aplicar(_evento(cv.DENTRO, ouvinte=True, suporta_video=True))
    assert cv.CAMERA not in cv.apresentar(live).botoes


def test_frases_do_que_mandamos():
    assert cv.rotulo_camera(types.SimpleNamespace(camera=True)) == \
        "Desligar a &câmera"
    assert cv.fala_do_que_mandamos((False, False, False),
                                   (True, False, False)) == "Câmera ligada."
    assert cv.fala_do_que_mandamos((False, False, False),
                                   (False, True, True)) == \
        "Compartilhando a tela e o som do computador."
    assert cv.fala_do_que_mandamos((True, False, False),
                                   (True, False, False)) == ""
    c = cv.ChatDeVoz("t1", "1", "A", camera=True, tela=True)
    assert cv.texto_do_que_mandamos(c) == \
        "Você está mandando a sua câmera e a tela."


def test_opcao_de_iniciar_fica_desligada_na_categoria_experimental():
    o = next(x for x in config.OPCOES if x.chave == "chat_de_voz_iniciar")
    assert o.categoria == config.CATEGORIA_EXPERIMENTAL
    assert o.padrao is False and "avisa os membros" in o.descricao

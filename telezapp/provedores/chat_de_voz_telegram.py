# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Chat de voz de grupo e live de canal do Telegram (EXPERIMENTAL).

Usa o mesmo PyTgCalls e o mesmo cliente Telethon das chamadas 1 a 1
(`chamadas_telegram.ChamadasTelegram`), na mesma thread e no mesmo asyncio do
provedor. Nada aqui toca na janela: o andamento sai como `EstadoChatDeVoz`.

Regras:
- so uma sessao por vez, e nunca junto com uma chamada 1 a 1;
- entra-se sempre com o microfone silenciado;
- live de canal (e canal de transmissao) so se ouve: sem microfone;
- nunca cria chat de voz (`auto_start=False`): so entra em um que existe.
"""
import asyncio
import dataclasses
import logging
import time
from dataclasses import dataclass, field

from telezapp import config
from telezapp.nucleo import chamadas as ch
from telezapp.nucleo import chat_de_voz as cv
from telezapp.nucleo import eventos as ev

log = logging.getLogger("telezapp.chatdevoz")

ESPERA_ENTRAR_S = 30
# Quanto tempo alguem continua "falando" depois da ultima atividade de voz
FALANDO_S = 3.0


@dataclass
class Info:
    """O que o Telegram diz do chat de voz de uma conversa."""
    ativo: bool = False
    titulo: str = ""
    ao_vivo: bool = False          # live (RTMP): so se ouve e se ve
    transmissao: bool = False      # canal de transmissao: so se ouve
    agendada: object = None        # quando comeca, se ainda nao comecou
    total: int = 0
    chamada: object = None         # InputGroupCall, para pedidos diretos
    nomes: dict = field(default_factory=dict)   # id -> nome
    iniciais: list = field(default_factory=list)  # [(id, mudo, mao)]


@dataclass
class _Sessao:
    chat_id: int
    nome: str
    ao_vivo: bool
    ouvinte: bool
    chamada: object = None
    mudo: bool = True
    mao: bool = False
    admin_mudo: bool = False     # o administrador nao liberou o microfone
    total: int = 0
    estado: str = cv.CONECTANDO
    escolhas: tuple = ("", "")
    participantes: dict = field(default_factory=dict)   # id -> Participante
    falando: dict = field(default_factory=dict)   # id -> quando falou (monotonic)
    video: bool = False            # a pessoa pediu para ver o video
    vigia: object = None           # tarefa que apaga o "falando" que passou
    visto_falando: frozenset = frozenset()
    visto_midia: tuple = (False, False, False)   # camera, tela, som do PC
    criar: bool = False            # entramos iniciando o chat de voz


class _Sombra:
    """O que as rotinas de camera, tela e som do computador, feitas para a
    chamada 1 a 1, leem de uma chamada: aqui vem da sessao do chat de voz."""

    def __init__(self, sessao, grupo):
        self._s = sessao
        self._g = grupo

    @property
    def estado(self):
        return ch.EM_CHAMADA if self._s.estado == cv.DENTRO else ch.CONECTANDO

    @property
    def mudo(self):
        return self._s.mudo

    @property
    def camera(self):
        return self._g._midia(self._s)[0]

    @property
    def tela(self):
        return self._g._midia(self._s)[1]

    @property
    def som_pc(self):
        return self._g._midia(self._s)[2]

    @property
    def video(self):
        m = self._g._midia(self._s)
        return m[0] or m[1]


class ChatDeVozTelegram:
    def __init__(self, chamadas, espera_s=ESPERA_ENTRAR_S):
        self.c = chamadas              # ChamadasTelegram
        self.espera_s = espera_s
        self.sessao = None
        self._nomes = {}               # id -> nome (de participantes)
        self._vozes = {}               # chat_id -> (ativo, ao_vivo) ja avisado
        self._eu = None                # o meu id no Telegram

    # ---------------------------------------------------------- estado
    @property
    def disponivel(self):
        m = self.c.motor
        return self.c.pronta and m is not None and \
            hasattr(m, "GroupCallConfig") and hasattr(m, "AcaoParticipante")

    @property
    def em_uso(self):
        return self.sessao is not None

    def _aviso(self, texto):
        self.c.barramento.publicar(ev.Aviso(self.c.conta_id, texto, False))

    def _publicar(self, aviso="", motivo="", erro=""):
        s = self.sessao
        if s is None:
            return
        agora = time.monotonic()
        lista = cv.ordenar([
            dataclasses.replace(p, falando=self._falando(s, p.id, agora))
            for p in s.participantes.values()])
        s.visto_falando = self._quem_fala(s, agora)
        self.c.barramento.publicar(ev.EstadoChatDeVoz(
            self.c.conta_id, str(s.chat_id), s.estado, s.nome, s.ao_vivo,
            s.ouvinte, s.mudo, s.mao,
            tuple((p.id, p.nome, p.mudo, p.mao, p.eu, p.falando)
                  for p in lista[:cv.LISTA_MAXIMA]),
            max(s.total, len(s.participantes)), aviso, motivo, erro,
            *self._midia(s),
            not s.ouvinte and bool(self.c.suporta_video),
            not s.ouvinte and bool(self.c.suporta_tela),
            not s.ouvinte and bool(self.c.suporta_som_pc)))

    # ------------------------------------------------------- consulta
    async def _buscar_info(self, chat_id):
        """Pergunta ao Telegram se a conversa tem chat de voz agora."""
        from telethon import utils
        from telethon.tl import functions, types
        cli = self.c.cliente
        ent = await cli.get_input_entity(chat_id)
        if isinstance(ent, types.InputPeerChannel):
            full = await cli(functions.channels.GetFullChannelRequest(ent))
        elif isinstance(ent, types.InputPeerChat):
            full = await cli(functions.messages.GetFullChatRequest(
                ent.chat_id))
        else:
            return Info()
        chamada = full.full_chat.call
        if chamada is None:
            return Info()
        r = await cli(functions.phone.GetGroupCallRequest(
            call=chamada, limit=cv.LISTA_MAXIMA))
        gc = r.call
        if not isinstance(gc, types.GroupCall):
            return Info()
        nomes = {}
        for u in list(r.users) + list(r.chats):
            try:
                nomes[utils.get_peer_id(u)] = utils.get_display_name(u)
            except Exception:
                pass
        entidade = await cli.get_entity(chat_id)
        return Info(
            True, gc.title or "", bool(getattr(gc, "rtmp_stream", False)),
            bool(getattr(entidade, "broadcast", False)),
            getattr(gc, "schedule_date", None), gc.participants_count or 0,
            chamada, nomes,
            [(utils.get_peer_id(p.peer), bool(p.muted),
              bool(p.raise_hand_rating)) for p in r.participants])

    async def _meu_id(self):
        if self._eu is None:
            self._eu = (await self.c.cliente.get_me()).id
        return self._eu

    async def _nome(self, uid):
        if uid in self._nomes:
            return self._nomes[uid]
        try:
            nome = await self.c.nome_de(uid)
        except Exception:
            nome = ""
        nome = nome or "Participante"
        if nome != "Participante":
            self._nomes[uid] = nome
        return nome

    # ----------------------------------------------------------- entrar
    async def entrar(self, chat_id, microfone="", saida="", criar=False):
        """Entra no chat de voz da conversa. Com `criar`, e se ainda nao ha
        um, INICIA um (avisa os membros; so administradores podem)."""
        c = self.c
        if not self.disponivel:
            self._aviso("O chat de voz não está disponível neste "
                        "computador.")
            return
        if self.sessao is not None or c.chamadas:
            self._aviso("Já há uma chamada em andamento. Saia dela antes de "
                        "entrar em um chat de voz.")
            return
        try:
            info = await self._buscar_info(chat_id)
        except Exception as e:
            log.warning("consulta do chat de voz falhou: %s: %s",
                        type(e).__name__, str(e)[:200])
            self._aviso("Não consegui consultar o chat de voz desta "
                        "conversa.")
            return
        if info is None or not info.ativo:
            if not criar:
                self._aviso("Não há chat de voz ativo nesta conversa.")
                return
            info = Info(True)                # vai ser criado ao entrar
        elif criar:
            criar = False                    # ja existe: so entra
        if info.agendada:
            self._aviso("O chat de voz está agendado e ainda não começou.")
            return
        if self.sessao is not None:        # outro pedido chegou nesse meio
            return
        try:
            nome = await c.nome_de(chat_id)
        except Exception:
            nome = ""
        ouvinte = (info.ao_vivo or info.transmissao) and not criar
        s = self.sessao = _Sessao(
            chat_id, nome or info.titulo, info.ao_vivo, ouvinte, info.chamada,
            total=info.total, escolhas=(microfone, saida), criar=criar)
        c._escolhas[chat_id] = (microfone, saida)
        self._nomes.update(info.nomes)
        eu = await self._meu_id()
        for uid, mudo, mao in info.iniciais:
            s.participantes[uid] = cv.Participante(
                uid, self._nomes.get(uid, "Participante"), mudo, mao,
                uid == eu)
        s.video = bool(config.Config().get("chat_de_voz_video"))
        log.info("chat de voz %s: entrando (%s, %d participantes, vídeo %s)",
                 chat_id, "só ouvindo" if ouvinte else "com microfone",
                 info.total, "ligado" if s.video else "desligado")
        self._publicar()
        c.atualizar_dispositivos()
        m = c.motor
        try:
            cfg = m.GroupCallConfig(auto_start=bool(criar))
            fluxo = None if ouvinte else m.fluxo_microfone(
                _escolher(m.microfones(), microfone))
            await asyncio.wait_for(c.app.play(chat_id, fluxo, cfg),
                                   self.espera_s)
            if self.sessao is not s:       # saiu nesse meio
                return
            if s.chamada is None:          # o chat de voz acabou de ser criado
                try:
                    s.chamada = (await self._buscar_info(chat_id)).chamada
                except Exception:
                    log.info("não consegui a chamada recém-criada")
            if not ouvinte:
                await self._mutar(chat_id, True)
            await c.app.record(chat_id, self._fluxo_de_saida(s, saida))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if self.sessao is not s:
                return
            log.warning("entrar no chat de voz falhou: %s: %s",
                        type(e).__name__, str(e)[:200])
            await self._encerrar(cv.FALHA, cv.motivo_da_excecao(e, criar))
            return
        s.estado = cv.DENTRO
        s.vigia = asyncio.ensure_future(self._vigiar_falando(s))
        self._publicar()
        await self._atualizar_lista(chat_id)

    async def _atualizar_lista(self, chat_id):
        """Pede a lista de participantes que a biblioteca guarda (a consulta
        inicial traz so os primeiros)."""
        s = self.sessao
        try:
            lista = await self.c.app.get_participants(chat_id)
        except Exception:
            return
        if s is None or self.sessao is not s or not lista:
            return
        eu = await self._meu_id()
        for p in lista:
            if p.user_id not in s.participantes:
                s.participantes[p.user_id] = cv.Participante(
                    p.user_id, await self._nome(p.user_id), bool(p.muted),
                    bool(p.raised_hand), p.user_id == eu)
        self._publicar()

    async def _mutar(self, chat_id, mudo):
        if mudo:
            await self.c.app.mute(chat_id)
        else:
            await self.c.app.unmute(chat_id)

    # --------------------------------------------------------- controles
    async def sair(self, chat_id=None):
        s = self.sessao
        if s is None:
            return
        log.info("chat de voz %s: saímos", s.chat_id)
        await self._encerrar(cv.SAIU)

    async def _encerrar(self, motivo, erro=""):
        s = self.sessao
        if s is None:
            return
        s.estado = cv.ENCERRADO
        if s.vigia is not None:
            s.vigia.cancel()
        self._publicar(motivo=motivo, erro=erro)
        self.sessao = None
        self.c._soltar_compartilhamento(s.chat_id)
        self.c._cam.pop(s.chat_id, None)
        self.c._escolhas.pop(s.chat_id, None)
        try:
            await self.c.app.leave_call(s.chat_id)
        except Exception as e:
            log.info("leave_call: %r", e)

    async def silenciar(self, mudo):
        s = self.sessao
        if s is None or s.estado != cv.DENTRO or s.ouvinte:
            return
        if not mudo and s.admin_mudo:
            self._aviso("O administrador não liberou o seu microfone. Use "
                        "Levantar a mão para pedir a vez.")
            return
        if s.chat_id in self.c._som:
            # o microfone entra no que montamos (som do computador): o
            # silencio e nosso, e o mute da NTgCalls calaria tudo
            s.mudo = bool(mudo)
            self._publicar()
            return
        try:
            await self._mutar(s.chat_id, mudo)
        except Exception:
            log.exception("erro ao silenciar no chat de voz")
            self._aviso("Não consegui mudar o microfone.")
            return
        s.mudo = bool(mudo)
        self._publicar()

    async def levantar_mao(self, sim):
        s = self.sessao
        if s is None or s.estado != cv.DENTRO or s.ouvinte:
            return
        try:
            await self._editar_mao(s, bool(sim))
        except Exception as e:
            log.warning("levantar a mão falhou: %s: %s", type(e).__name__,
                        str(e)[:200])
            self._aviso("Não consegui %s." % (
                "levantar a mão" if sim else "baixar a mão"))
            return
        s.mao = bool(sim)
        self._publicar()

    async def _editar_mao(self, s, sim):
        from telethon.tl import functions, types
        await self.c.cliente(functions.phone.EditGroupCallParticipantRequest(
            call=s.chamada, participant=types.InputPeerSelf(),
            raise_hand=sim))

    async def trocar_dispositivos(self, microfone="", saida=""):
        s = self.sessao
        if s is None or s.estado != cv.DENTRO:
            return
        mic, sai = s.escolhas
        mic, sai = microfone or mic, saida or sai
        s.escolhas = (mic, sai)
        self.c._escolhas[s.chat_id] = (mic, sai)
        m = self.c.motor
        try:
            if microfone and not s.ouvinte:
                await self.c.app.play(s.chat_id, m.fluxo_microfone(
                    _escolher(m.microfones(), mic)))
                if s.mudo:
                    await self._mutar(s.chat_id, True)
            if saida:
                await self.c.app.record(s.chat_id,
                                        self._fluxo_de_saida(s, sai))
        except Exception:
            log.exception("erro ao trocar de dispositivo no chat de voz")

    # --------------------------- o que mandamos: camera, tela e som do PC
    def dentro(self, chat_id):
        s = self.sessao
        return s is not None and s.chat_id == chat_id and \
            s.estado == cv.DENTRO

    def sombra(self, chat_id):
        """O adaptador que as rotinas das chamadas 1 a 1 usam (so para quem
        fala: em live nao ha o que mandar)."""
        s = self.sessao
        if s is not None and s.chat_id == chat_id and not s.ouvinte:
            return _Sombra(s, self)
        return None

    def _midia(self, s):
        """(camera, tela, som do PC) a partir do que o motor das chamadas
        guarda: a tela vai pelo canal do video, mas nao e a camera."""
        c = self.c
        tela = s.chat_id in c._tela
        camera = c._cam.get(s.chat_id) is not None and not tela
        return camera, tela, s.chat_id in c._som

    def marcar_midia(self, **_):
        """O que mandamos pode ter mudado: avisa a janela se mudou."""
        s = self.sessao
        if s is None:
            return False
        novo = self._midia(s)
        if novo == s.visto_midia:
            return False
        s.visto_midia = novo
        self._publicar()
        return True

    def fluxo_de_saida(self, saida):
        s = self.sessao
        return self._fluxo_de_saida(s, saida) if s is not None else None

    def _pode_mandar(self):
        """A sessao em que da para mandar camera, tela e som, ou None (e
        avisa o motivo)."""
        s = self.sessao
        if s is None or s.estado != cv.DENTRO:
            return None
        if s.ouvinte:
            self._aviso("Em uma live você só ouve.")
            return None
        if s.admin_mudo:
            self._aviso("O administrador não liberou a sua fala.")
            return None
        return s

    async def _remutar(self, s):
        """Trocar o fluxo de voz pode soltar o silencio da NTgCalls: reaplica
        (privacidade). Com o som do computador, o silencio e nosso."""
        if s.mudo and s.chat_id not in self.c._som and self.sessao is s:
            try:
                await self._mutar(s.chat_id, True)
            except Exception:
                log.info("não consegui silenciar de novo")

    async def ligar_camera(self, nome=""):
        s = self._pode_mandar()
        if s is not None:
            await self.c.ligar_camera(s.chat_id, nome)
            await self._remutar(s)

    async def desligar_camera(self):
        s = self._pode_mandar()
        if s is not None:
            await self.c.desligar_camera(s.chat_id)
            await self._remutar(s)

    async def compartilhar_tela(self, nome="", com_som=True):
        s = self._pode_mandar()
        if s is not None:
            await self.c.compartilhar_tela(s.chat_id, nome, com_som)
            await self._remutar(s)

    async def trocar_tela(self, nome):
        s = self._pode_mandar()
        if s is not None:
            await self.c.trocar_tela(s.chat_id, nome)

    async def parar_tela(self):
        s = self._pode_mandar()
        if s is not None:
            await self.c.parar_tela(s.chat_id)
            await self._remutar(s)

    async def compartilhar_som(self, saida=""):
        s = self._pode_mandar()
        if s is not None:
            await self.c.compartilhar_som(s.chat_id, saida)

    async def parar_som(self):
        s = self._pode_mandar()
        if s is not None:
            await self.c.parar_som(s.chat_id)

    def _fluxo_de_saida(self, s, saida):
        """O que chega: o som e, com a caixa do video marcada, a camera e a
        tela de quem aparecer."""
        m = self.c.motor
        dispositivo = _escolher(m.saidas(), saida)
        if s.video:
            return m.fluxo_saida(dispositivo, camera=True, tela=True)
        return m.fluxo_saida(dispositivo)

    def aceita_quadros(self, chat_id):
        """Os quadros de video deste chat vao para a janela?"""
        s = self.sessao
        return bool(s is not None and s.chat_id == chat_id and s.video
                    and s.estado == cv.DENTRO)

    # ------------------------------------------------- quem esta falando
    @staticmethod
    def _falando(s, uid, agora):
        visto = s.falando.get(uid)
        return visto is not None and agora - visto < FALANDO_S

    def _quem_fala(self, s, agora):
        return frozenset(uid for uid in s.falando
                         if self._falando(s, uid, agora))

    async def _vigiar_falando(self, s):
        """De segundo em segundo, tira "falando" de quem calou."""
        try:
            while self.sessao is s:
                await asyncio.sleep(1)
                if self.sessao is s and \
                        self._quem_fala(s, time.monotonic()) != s.visto_falando:
                    self._publicar()
        except asyncio.CancelledError:
            pass

    def _marcar_atividade(self, update):
        """Um `UpdateGroupCallParticipants` bruto: quem tem `active_date`
        recente falou agora. Devolve True se alguem passou a falar."""
        from telethon import utils
        s = self.sessao
        if s is None or s.chamada is None:
            return False
        if getattr(update.call, "id", None) != getattr(s.chamada, "id", -1):
            return False
        agora = time.time()
        novo = False
        for p in update.participants:
            data = getattr(p, "active_date", None)
            if data is None or getattr(p, "left", False):
                continue
            quando = data.timestamp() if hasattr(data, "timestamp") \
                else float(data)
            if agora - quando > FALANDO_S:
                continue
            uid = utils.get_peer_id(p.peer)
            if not self._falando(s, uid, time.monotonic()):
                novo = True
            s.falando[uid] = time.monotonic()
        return novo

    # ---------------------------------------- avisos de chat de voz iniciado
    async def ao_bruto(self, update):
        """Atualizacoes brutas do Telegram: quem esta falando, chat de voz
        que comeca ou acaba. Erro aqui nunca derruba o resto."""
        try:
            nome = type(update).__name__
            if nome == "UpdateGroupCallParticipants":
                if self._marcar_atividade(update):
                    self._publicar()
            elif nome == "UpdateGroupCall":
                self._avisar_chamada(update)
            elif nome in ("UpdateNewMessage", "UpdateNewChannelMessage",
                          "UpdateEditChannelMessage", "UpdateEditMessage"):
                await self._avisar_servico(update)
        except Exception:
            log.exception("atualização do chat de voz")

    def _avisar_estado(self, chat_id, ativo, ao_vivo, iniciou=False):
        """Publica `ChatDeVozAtivo` se algo mudou (ou se acabou de comecar)."""
        if not iniciou and self._vozes.get(chat_id) == (ativo, ao_vivo):
            return
        self._vozes[chat_id] = (ativo, ao_vivo)
        self.c.barramento.publicar(ev.ChatDeVozAtivo(
            self.c.conta_id, str(chat_id), ativo, ao_vivo, iniciou))

    def _avisar_chamada(self, update):
        from telethon import utils
        peer = getattr(update, "peer", None)
        if peer is None:
            return
        chamada = update.call
        ativo = type(chamada).__name__ == "GroupCall" and \
            getattr(chamada, "schedule_date", None) is None
        self._avisar_estado(utils.get_peer_id(peer), ativo,
                            bool(getattr(chamada, "rtmp_stream", False)))

    async def _avisar_servico(self, update):
        """A mensagem de servico "chat de voz iniciado" (sem duracao) e a
        mesma, editada com a duracao, quando acaba."""
        from telethon import utils
        msg = getattr(update, "message", None)
        if type(msg).__name__ != "MessageService":
            return
        acao = msg.action
        if type(acao).__name__ != "MessageActionGroupCall":
            return
        chat_id = utils.get_peer_id(msg.peer_id)
        if getattr(acao, "duration", None) is not None:
            self._avisar_estado(chat_id, False, False)
            return
        if self._vozes.get(chat_id, (False,))[0] and \
                type(update).__name__.startswith("UpdateEdit"):
            return
        try:
            ent = await self.c.cliente.get_entity(chat_id)
            ao_vivo = bool(getattr(ent, "broadcast", False))
        except Exception:
            ao_vivo = False
        self._avisar_estado(chat_id, True, ao_vivo, iniciou=True)

    def registrar_brutos(self):
        """Liga os avisos brutos do Telegram a este objeto."""
        from telethon import events
        from telethon.tl import types
        self.c.cliente.add_event_handler(self.ao_bruto, events.Raw((
            types.UpdateGroupCallParticipants, types.UpdateGroupCall,
            types.UpdateNewMessage, types.UpdateNewChannelMessage,
            types.UpdateEditMessage, types.UpdateEditChannelMessage)))

    # ------------------------------------------- eventos do motor
    async def ao_participante(self, _app, update):
        s = self.sessao
        if s is None or update.chat_id != s.chat_id:
            return
        p, a = update.participant, self.c.motor.AcaoParticipante
        uid = p.user_id
        antes = s.participantes.get(uid)
        if update.action & a.KICKED and not update.action & a.LEFT:
            # troca de aparelho do mesmo participante: vem um "entrou" depois
            s.participantes.pop(uid, None)
            return
        if update.action & a.LEFT:
            s.participantes.pop(uid, None)
            if antes is not None:
                s.total = max(0, max(s.total, len(s.participantes) + 1) - 1)
            aviso = cv.aviso_de_entrada(antes.nome if antes else "", False) \
                if antes is not None and not antes.eu else ""
            self._publicar(aviso if cv.avisos_ligados(s.total) else "")
            return
        nome = antes.nome if antes is not None and \
            antes.nome != "Participante" else await self._nome(uid)
        eu = uid == await self._meu_id()
        novo = cv.Participante(uid, nome, bool(p.muted), bool(p.raised_hand),
                               eu)
        s.participantes[uid] = novo
        aviso = ""
        if antes is None:
            s.total += 1
            if not eu:
                aviso = cv.aviso_de_entrada(nome, True)
        elif novo.mao and not antes.mao and not eu:
            aviso = cv.aviso_de_mao(nome)
        if eu:
            s.mudo, s.mao = novo.mudo, novo.mao
            s.admin_mudo = bool(getattr(p, "muted_by_admin", False))
        self._publicar(aviso if cv.avisos_ligados(s.total) else "")

    async def ao_sair(self, update):
        """Chamado quando o motor diz que saimos de um chat. Devolve True se
        era o nosso chat de voz."""
        s = self.sessao
        if s is None or update.chat_id != s.chat_id:
            return False
        st = getattr(self.c.motor.ChatUpdate, "Status", None)
        motivo = cv.TERMINOU
        if st is not None:
            for nome in ("KICKED", "LEFT_GROUP"):
                marca = getattr(st, nome, None)
                if marca is not None and update.status & marca:
                    motivo = cv.REMOVIDO
        log.info("chat de voz %s: a biblioteca avisou o fim (%s)", s.chat_id,
                 motivo)
        await self._encerrar(motivo)
        return True


def _escolher(dispositivos, nome):
    from telezapp.provedores.chamadas_telegram import _escolher as escolher
    return escolher(dispositivos, nome)

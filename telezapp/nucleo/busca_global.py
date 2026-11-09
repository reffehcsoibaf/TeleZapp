# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Busca global no Telegram: o que a busca do aplicativo acha.

Sem wx. O Telegram responde a três perguntas diferentes e a janela junta as
respostas numa lista só:

- chats: pessoas, bots, grupos e canais cujo nome ou @usuário combina, nas
  conversas da conta e também públicos de todo o Telegram;
- mensagens: o texto nas conversas da conta, inclusive as que não estão
  guardadas neste computador, com filtro por tipo de conteúdo;
- posts: o texto em posts públicos de canais, mesmo de canais que a conta
  não segue (o Telegram limita quantas buscas assim se fazem por dia).
"""
from dataclasses import dataclass, field


# o que procurar
MODOS = (
    ("tudo", "Tudo: conversas, canais, grupos, mensagens e posts públicos"),
    ("chats", "Só pessoas, bots, grupos e canais"),
    ("mensagens", "Só mensagens das minhas conversas"),
    ("posts", "Só posts públicos de canais"),
)

# tipo de conteudo das mensagens: (chave, rotulo, filtro do Telegram)
FILTROS = (
    ("qualquer", "Qualquer tipo", ""),
    ("fotos", "Fotos", "InputMessagesFilterPhotos"),
    ("videos", "Vídeos", "InputMessagesFilterVideo"),
    ("arquivos", "Arquivos", "InputMessagesFilterDocument"),
    ("musica", "Músicas", "InputMessagesFilterMusic"),
    ("voz", "Mensagens de voz", "InputMessagesFilterVoice"),
    ("links", "Links", "InputMessagesFilterUrl"),
    ("gifs", "GIFs", "InputMessagesFilterGif"),
)

ROTULO_DO_TIPO = {"privada": "Pessoa", "bot": "Bot", "grupo": "Grupo",
                  "canal": "Canal"}


def filtro_do_telegram(chave):
    """Nome do filtro do Telegram para a chave ("" = sem filtro)."""
    return next((f for k, _, f in FILTROS if k == chave), "")


def pode_buscar_sem_texto(modo, filtro):
    """So a busca de mensagens por tipo de conteudo dispensa o texto."""
    return modo == "mensagens" and filtro != "qualquer"


@dataclass
class ResultadoChat:
    """Uma pessoa, bot, grupo ou canal achado pela busca."""
    conversa: object
    usuario: str = ""
    membros: int = 0
    participa: bool = False
    bot: bool = False

    @property
    def tipo(self):
        return "bot" if self.bot else self.conversa.tipo

    def pode_entrar(self):
        """Grupo ou canal publico de que a conta ainda nao participa."""
        return self.conversa.tipo in ("grupo", "canal") and not self.participa

    def texto_da_lista(self, nome_de_conta=None):
        c = self.conversa
        partes = [ROTULO_DO_TIPO.get(self.tipo, "Conversa") + ": " + c.nome]
        if self.usuario:
            partes.append("@" + self.usuario.lstrip("@"))
        if self.membros:
            unidade = "inscritos" if c.tipo == "canal" else "membros"
            partes.append("%d %s" % (self.membros, unidade))
        partes.append("na sua lista" if self.participa else "você não participa")
        if nome_de_conta:
            partes.append("conta " + nome_de_conta(c.conta_id))
        return ", ".join(partes)


@dataclass
class ResultadoGlobal:
    chats: list = field(default_factory=list)       # [ResultadoChat]
    mensagens: list = field(default_factory=list)   # [(Mensagem, Conversa)]
    posts: list = field(default_factory=list)       # [(Mensagem, Conversa)]
    avisos: list = field(default_factory=list)      # o que nao deu para buscar

    def vazio(self):
        return not (self.chats or self.mensagens or self.posts)


def linhas(resultado, termo, nome_de_conta=None):
    """[(tipo, objeto, texto)] na ordem da lista: chats, mensagens, posts.
    tipo: "chat", "mensagem" ou "post"; objeto: ResultadoChat ou Achado."""
    from telezapp.nucleo import busca
    saida = [("chat", c, c.texto_da_lista(nome_de_conta))
             for c in resultado.chats]
    for tipo, achadas in (("mensagem", resultado.mensagens),
                          ("post", resultado.posts)):
        for x, conv in achadas:
            a = busca.achado_do_servidor(x, conv, termo)
            texto = a.texto_da_lista(nome_de_conta)
            saida.append((tipo, a, ("Post público: " + texto)
                          if tipo == "post" else texto))
    return saida


def resumo(n_chats, n_mensagens, n_posts):
    """'3 conversas, 10 mensagens' para falar ao terminar."""
    partes = []
    for n, um, varios in ((n_chats, "conversa", "conversas"),
                          (n_mensagens, "mensagem", "mensagens"),
                          (n_posts, "post público", "posts públicos")):
        if n:
            partes.append("%d %s" % (n, um if n == 1 else varios))
    return ", ".join(partes)



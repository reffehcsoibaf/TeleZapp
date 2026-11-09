# SPDX-License-Identifier: GPL-3.0-or-later
"""Busca global no Telegram: a parte sem wx."""
from telezapp.nucleo import busca_global as bg
from telezapp.nucleo import modelos as m


def test_modos_e_filtros_sao_completos():
    assert [k for k, _ in bg.MODOS] == ["tudo", "chats", "mensagens", "posts"]
    assert bg.filtro_do_telegram("fotos") == "InputMessagesFilterPhotos"
    assert bg.filtro_do_telegram("qualquer") == ""
    assert bg.pode_buscar_sem_texto("mensagens", "fotos")
    assert not bg.pode_buscar_sem_texto("mensagens", "qualquer")
    assert not bg.pode_buscar_sem_texto("chats", "fotos")


def test_todos_os_filtros_existem_na_biblioteca():
    from telethon.tl import types as T
    for _, _, nome in bg.FILTROS:
        assert not nome or hasattr(T, nome)


def test_linhas_juntam_chats_mensagens_e_posts_na_ordem():
    conv = m.Conversa("t1", "9", "Canal", "telegram", "canal")
    x = m.Mensagem("t1", "9", "1", autor="Canal", texto="receita de bolo",
                   data=1_700_000_000)
    r = bg.ResultadoGlobal(
        chats=[bg.ResultadoChat(conv, "canal", 10, True)],
        mensagens=[(x, conv)], posts=[(x, conv)])
    linhas = bg.linhas(r, "bolo")
    assert [t for t, _, _ in linhas] == ["chat", "mensagem", "post"]
    assert linhas[0][2].startswith("Canal: Canal, @canal, 10 inscritos")
    assert "bolo" in linhas[1][2]
    assert linhas[2][2].startswith("Post público: ")
    assert bg.resumo(1, 2, 0) == "1 conversa, 2 mensagens"
    assert bg.resumo(0, 0, 1) == "1 post público"
    assert bg.ResultadoGlobal().vazio()

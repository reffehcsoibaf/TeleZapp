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


class _ThreadNaHora:
    def __init__(self, target=None, **k):
        self.target = target

    def start(self):
        self.target()


def _dialogo(monkeypatch, buscar, falar=None):
    import sys
    from testes import wx_falso
    sys.modules["wx"] = wx_falso
    from telezapp.interface import busca_global as ibg
    monkeypatch.setattr(ibg.threading, "Thread", _ThreadNaHora)
    return ibg, ibg.DialogoBuscaGlobal(None, [("t1", "Tele")], buscar,
                                       falar=falar)


def _achado(id_):
    conv = m.Conversa("t1", "9", "Canal", "telegram", "canal")
    x = m.Mensagem("t1", "9", str(id_), autor="Canal", texto="bolo %s" % id_,
                   data=1_700_000_000)
    return bg_busca.achado_do_servidor(x, conv, "bolo")


from telezapp.nucleo import busca as bg_busca  # noqa: E402


def test_dialogo_ver_mais_acrescenta_mensagens_ate_acabar(monkeypatch):
    paginas = {None: ([("mensagem", _achado(1), "um"),
                       ("mensagem", _achado(2), "dois")], [], {"mensagens": "C1"}),
               "C1": ([("mensagem", _achado(2), "dois"),
                       ("mensagem", _achado(3), "tres")], [], {"mensagens": "C2"}),
               "C2": ([("mensagem", _achado(3), "tres")], [], None)}
    pedidos, ditas = [], []

    def buscar(conta, texto, modo, filtro, cursor=None):
        pedidos.append((texto, modo, cursor))
        return paginas[cursor if cursor is None else cursor["mensagens"]]
    ibg, d = _dialogo(monkeypatch, buscar, ditas.append)
    d.termo.SetValue("bolo")
    d.buscar()
    assert len(d.linhas) == 2 and d.proximo == {"mensagens": "C1"}
    assert d.b_mais.IsEnabled()
    d.termo.SetValue("outra coisa")         # nao muda o que Ver mais continua
    d.ver_mais()
    assert [t for _, _, t in d.linhas] == ["um", "dois", "tres"]
    assert pedidos[1][0] == "bolo" and pedidos[1][2] == {"mensagens": "C1"}
    assert d.lista.GetSelection() == 2
    d.ver_mais()                            # so repetidos: acabou
    assert d.fim and not d.b_mais.IsEnabled()
    assert ditas[-1] == "O Telegram não tem mais resultados."
    d.ver_mais()
    assert ditas[-1] == "Não há mais resultados."


def test_dialogo_ver_mais_antes_de_buscar_e_estado_guardam_o_cursor(
        monkeypatch):
    ditas = []
    ibg, d = _dialogo(
        monkeypatch, lambda *a: ([("mensagem", _achado(1), "um")], [],
                                 {"posts": "P1"}), ditas.append)
    d.ver_mais()
    assert ditas[-1] == "Faça uma busca antes."
    d.termo.SetValue("bolo")
    d.buscar()
    estado = d.estado()
    outro = ibg.DialogoBuscaGlobal(None, [("t1", "Tele")],
                                   lambda *a: ([], []))
    outro.restaurar(estado)
    assert outro.proximo == {"posts": "P1"} and outro._pedido is not None
    assert outro.linhas == d.linhas

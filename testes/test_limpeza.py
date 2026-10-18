"""Limpeza de midias e mensagens, conversas apagadas, fixadas e silenciadas."""
import os
import time

from telezapp.armazenamento.banco import Banco
from telezapp.nucleo import limpeza
from telezapp.nucleo import modelos as m

ANTIGA = time.time() - 40 * 86400


def _banco(tmp_path):
    b = Banco(str(tmp_path / "b.db"))
    msgs = [m.Mensagem("c", "v", str(i), texto="oi", tipo="foto" if i == 0
                       else "texto", data=ANTIGA if i < 2 else time.time())
            for i in range(4)]
    b.salvar_mensagens(msgs)
    arq = tmp_path / "f0"
    arq.write_bytes(b"x" * 100)
    b.registrar_midia("c", "v", "0", "foto", str(arq), 100, ANTIGA)
    return b, msgs, arq


def test_limpar_midias_apaga_o_arquivo_e_impede_novo_download(tmp_path):
    b, _, arq = _banco(tmp_path)
    sel = limpeza.selecionar(b, limpeza.Filtros(dias=30))
    assert (sel.quantidade, sel.bytes) == (1, 100)
    assert limpeza.apagar(b, sel) == (1, 100, 0)
    assert not arq.exists() and b.midia("c", "v", "0") is None
    assert b.foi_limpa("c", "v", "0") == "midia"
    assert len(b.mensagens("c", "v")) == 4        # as mensagens ficam


def test_limpar_mensagens_nao_voltam_ate_o_novo_pareamento(tmp_path):
    b, msgs, arq = _banco(tmp_path)
    sel = limpeza.selecionar(
        b, limpeza.Filtros(o_que=limpeza.MENSAGENS, dias=30))
    assert sel.quantidade == 2
    limpeza.apagar(b, sel)
    assert not arq.exists() and len(b.mensagens("c", "v")) == 2
    b.salvar_mensagens(msgs)                       # historico de novo
    assert len(b.mensagens("c", "v")) == 2
    b.esquecer_limpezas("c")                       # novo pareamento
    b.salvar_mensagens(msgs)
    assert len(b.mensagens("c", "v")) == 4


def test_conversa_apagada_so_volta_com_mensagem_mais_nova(tmp_path):
    b = Banco(str(tmp_path / "b.db"))
    c = m.Conversa("c", "v", "Ana", data=100.0)
    msgs = [m.Mensagem("c", "v", str(i), texto="oi", data=90.0 + i)
            for i in range(3)]
    b.salvar_conversas([c])
    b.salvar_mensagens(msgs)
    assert b.apagar_conversa("c", "v", 100.0) == 100.0
    b.salvar_conversas([c])
    b.salvar_mensagens(msgs)
    assert b.conversas("c") == [] and b.mensagens("c", "v") == []
    c.data = 200.0
    nova = m.Mensagem("c", "v", "9", texto="nova", data=200.0)
    b.salvar_conversas([c])
    b.salvar_mensagens(msgs + [nova])
    assert len(b.conversas("c")) == 1
    assert [x.id for x in b.mensagens("c", "v")] == ["9"]
    b.esquecer_limpezas("c")
    assert b.apagada_ate("c", "v") is None


def test_fixada_e_silenciada_no_rotulo_nos_filtros_e_no_banco(tmp_path):
    c = m.Conversa("c", "v", "Ana", servico="whatsapp", fixada=True,
                   silenciada_ate=-1.0)
    assert m.rotulo_conversa(c) == "Ana, WhatsApp, fixada, silenciada"
    assert m.passa_filtro(c, "fixadas") and m.passa_filtro(c, "silenciadas")
    vencida = m.Conversa("c", "w", "Bia", silenciada_ate=time.time() - 5)
    assert not vencida.silenciada()
    assert not m.passa_filtro(vencida, "silenciadas")
    b = Banco(str(tmp_path / "b.db"))
    b.salvar_conversas([c])
    lida = b.conversas("c")[0]
    assert lida.fixada and lida.silenciada_ate == -1.0
    b.fechar()


def test_limpeza_mantem_as_favoritas_e_pode_incluir_todas(tmp_path):
    b, _, arq = _banco(tmp_path)
    fav = b.mensagem("c", "v", "0")                  # a que tem a midia
    m.atualizar_extras(fav, favorita=True)
    b.salvar_mensagens([fav])
    assert b.favoritas() == {("c", "v", "0")}
    f = limpeza.Filtros(o_que=limpeza.MENSAGENS, dias=30)
    assert limpeza.selecionar(b, f).quantidade == 1          # so a "1"
    f.manter_favoritas = False
    assert limpeza.selecionar(b, f).quantidade == 2
    # a midia da favorita tambem fica
    assert limpeza.selecionar(b, limpeza.Filtros(dias=30)).quantidade == 0
    assert limpeza.selecionar(
        b, limpeza.Filtros(dias=30, manter_favoritas=False)).quantidade == 1
    assert m.formatar(fav, m.ESTILO_AUTOR_PRIMEIRO).count("(favorita)") == 1

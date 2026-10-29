# SPDX-License-Identifier: GPL-3.0-or-later
"""Armazem, gerente de downloads e download nos dois provedores."""
import os
import queue
import threading
import time
import types

import pytest

from telezapp import config
from telezapp.armazenamento.banco import Banco
from telezapp.midia import armazem
from telezapp.nucleo import eventos as ev
from telezapp.nucleo import modelos as m
from telezapp.nucleo.midias import (EM_ANDAMENTO, INICIADO, PRONTA,
                                    GerenteMidias)
from telezapp.provedores import base


@pytest.fixture(autouse=True)
def dados(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path / "dados"))
    return tmp_path / "dados"


def msg(id="M1", tipo=m.FOTO, conta="c1", conversa="55@s.whatsapp.net",
        nome="", tamanho=1000, minha=False):
    return m.Mensagem(conta, conversa, id, tipo=tipo, nome_arquivo=nome,
                      tamanho=tamanho, minha=minha, data=1.0)


# ------------------------------------------------------------- armazem
def test_caminhos_ficam_dentro_da_pasta_do_app(dados):
    x = msg(nome='re:la*t?"ório.pdf', conversa="a/b\\c@g.us")
    base_ = armazem.caminho_base(x)
    assert base_.startswith(str(dados))
    assert os.path.dirname(base_).startswith(armazem.pasta_midias())
    nome = os.path.basename(base_)
    assert not set('\\/:*?"<>|') & set(nome)
    assert armazem.caminho_base(x) == base_            # estavel
    assert armazem.pasta_da_conversa("c1", "a@x") != \
        armazem.pasta_da_conversa("c1", "b@x")


def test_extensoes():
    assert armazem.extensao("audio/ogg; codecs=opus", m.VOZ) == ".ogg"
    assert armazem.extensao("image/jpeg", m.FOTO) == ".jpg"
    assert armazem.extensao("video/mp4", m.VIDEO) == ".mp4"
    assert armazem.extensao("", m.FOTO) == ".jpg"
    assert armazem.extensao("application/pdf", m.DOCUMENTO, "a.PDF") == ".pdf"
    assert armazem.com_extensao("x/a.pdf", ".pdf") == "x/a.pdf"
    assert armazem.com_extensao("x/a", ".pdf") == "x/a.pdf"


def test_apagar_conta_remove_a_pasta(dados):
    pasta = armazem.pasta_da_conversa("c1", "x")
    open(os.path.join(pasta, "a.jpg"), "wb").write(b"123")
    assert armazem.tamanho_da_pasta("c1") == 3
    armazem.apagar_conta("c1")
    assert not os.path.exists(os.path.join(armazem.pasta_midias(), "c1"))


# -------------------------------------------------------------- gerente
class Falso:
    """Provedor que escreve um arquivo; pode travar, falhar ou ser lento."""
    def __init__(self):
        self.chamadas = []
        self.modo = "ok"
        self.liberar = threading.Event()

    def baixar_arquivo(self, msg_, base_, progresso, cancelado):
        self.chamadas.append(msg_.id)
        progresso(0)
        if self.modo == "erro":
            raise base.ErroMidia("não tem mais")
        if self.modo == "quebra":
            raise RuntimeError("bug")
        if self.modo == "lento":
            progresso(50)
            while not cancelado():
                if self.liberar.wait(0.02):
                    break
            if cancelado():
                raise base.DownloadCancelado()
        caminho = base_ + ".jpg"
        open(caminho, "wb").write(b"x" * 10)
        progresso(100)
        return caminho


@pytest.fixture
def g(tmp_path):
    fila = queue.Queue()
    barramento = ev.Barramento()
    barramento.ouvir(fila.put)
    banco = Banco(str(tmp_path / "m.db"))
    cfg = config.Config()
    falso = Falso()
    gerente = GerenteMidias(cfg, banco, barramento, lambda c: falso)
    yield types.SimpleNamespace(g=gerente, f=falso, fila=fila, banco=banco,
                                cfg=cfg, barramento=barramento)
    gerente.parar()
    banco.fechar()


def fim(fila, segundos=5):
    while True:
        e = fila.get(timeout=segundos)
        if isinstance(e, ev.MidiaBaixada):
            return e


def test_baixa_registra_e_nao_baixa_de_novo(g):
    x = msg()
    assert g.g.caminho(x) is None
    assert g.g.baixar(x) == INICIADO
    e = fim(g.fila)
    assert e.caminho and not e.erro and os.path.getsize(e.caminho) == 10
    assert g.g.caminho(x) == e.caminho
    assert g.banco.midias("c1")[0][3] == e.caminho
    assert g.g.baixar(x) == PRONTA
    assert fim(g.fila).caminho == e.caminho
    assert g.f.chamadas == ["M1"]
    # arquivo apagado a mao: o registro e esquecido
    os.remove(e.caminho)
    assert g.g.caminho(x) is None and g.banco.midias("c1") == []


def test_progresso_erro_e_falha_inesperada(g):
    progressos = []
    g.barramento.ouvir(lambda e: progressos.append(e.percentual)
                       if isinstance(e, ev.ProgressoMidia) else None)
    g.g.baixar(msg("A"))
    fim(g.fila)
    assert progressos[0] == 0 and progressos[-1] == 100
    g.f.modo = "erro"
    g.g.baixar(msg("B"))
    assert fim(g.fila).erro == "não tem mais"
    g.f.modo = "quebra"
    g.g.baixar(msg("C"))
    e = fim(g.fila)
    assert "log" in e.erro and not e.caminho
    assert not g.g.algum_baixando()


def test_cancelar(g):
    g.f.modo = "lento"
    x = msg()
    assert g.g.baixar(x) == INICIADO
    assert g.g.baixar(x) == EM_ANDAMENTO
    assert g.g.baixando(x.chave)
    assert g.g.cancelar(x.chave)
    e = fim(g.fila)
    assert e.cancelada and not e.caminho
    assert g.g.caminho(x) is None and not g.g.baixando(x.chave)
    assert not g.g.cancelar(x.chave)


def test_conta_sem_provedor(g):
    g.g.provedor_de = lambda c: None
    g.g.baixar(msg())
    assert "não está ativa" in fim(g.fila).erro


def nova(g, x, **k):
    g.barramento.publicar(ev.MensagemNova(x, **k))


def test_baixar_automatico_so_quando_configurado_e_dentro_do_limite(g):
    nova(g, msg("A"))                                   # padrao: sob demanda
    time.sleep(0.2)
    assert g.f.chamadas == []
    g.cfg.set("midias_baixar", "automatico")
    nova(g, msg("B", tamanho=30 * 1048576))             # acima de 20 MB
    nova(g, msg("C", tipo=m.TEXTO))
    nova(g, msg("D", minha=True))
    nova(g, msg("E"), enviada_daqui=True)
    time.sleep(0.2)
    assert g.f.chamadas == []
    nova(g, msg("F"), silenciosa=True)                  # na sincronia vale
    e = fim(g.fila)
    assert e.mensagem_id == "F" and e.automatica
    g.cfg.set("midias_limite_auto_mb", 50)
    nova(g, msg("G", tamanho=30 * 1048576))
    assert fim(g.fila).mensagem_id == "G"


def test_pedido_da_pessoa_assume_o_download_automatico(g):
    g.f.modo = "lento"
    x = msg()
    g.g.baixar(x, automatica=True)
    assert g.g.baixar(x) == EM_ANDAMENTO
    g.f.liberar.set()
    assert fim(g.fila).automatica is False


def test_opcoes_de_midia_no_registro():
    por_chave = {o.chave: o for o in config.OPCOES}
    assert config.PADROES["midias_baixar"] == "demanda"
    assert [v for v, _ in por_chave["midias_baixar"].escolhas] == [
        "demanda", "automatico"]
    assert [o.chave for o in config.buscar_opcoes("baixar midias")]


# ------------------------------------------------------------------ lote
def esperar_lote(lote, segundos=5):
    for _ in range(int(segundos / 0.02)):
        if not lote.pendentes:
            return
        threading.Event().wait(0.02)
    raise AssertionError("o lote nao terminou")


def test_faltantes_pula_o_que_ja_esta_no_computador_e_comeca_pelo_mais_novo(g):
    tem = msg("A")
    g.g.baixar(tem)
    fim(g.fila)
    texto = m.Mensagem("c1", "55@s.whatsapp.net", "T", tipo=m.TEXTO, data=1.0)
    achadas = g.g.faltantes([msg("B"), tem, texto, msg("C")])
    assert [x.id for x in achadas] == ["C", "B"]


def test_lote_baixa_conta_e_avisa_o_progresso_e_o_fim(g):
    progresso, fins = [], []
    lote = g.g.baixar_lote([msg("A"), msg("B")],
                           lambda f, t: progresso.append((f, t)),
                           fins.append)
    esperar_lote(lote)
    threading.Event().wait(0.1)
    assert (lote.baixadas, lote.indisponiveis, lote.canceladas) == (2, 0, 0)
    assert sorted(progresso) == [(1, 2), (2, 2)]
    assert fins == [lote]


def test_lote_conta_as_que_nao_estao_mais_disponiveis(g):
    g.f.modo = "erro"
    fins = []
    lote = g.g.baixar_lote([msg("A"), msg("B"), msg("C")], ao_fim=fins.append)
    esperar_lote(lote)
    threading.Event().wait(0.1)
    assert (lote.baixadas, lote.indisponiveis) == (0, 3) and fins == [lote]


def test_lote_vazio_termina_na_hora(g):
    fins = []
    lote = g.g.baixar_lote([], ao_fim=fins.append)
    assert fins == [lote] and lote.total == 0


def test_cancelar_o_lote_cancela_o_que_falta(g):
    g.f.modo = "lento"
    lote = g.g.baixar_lote([msg("A"), msg("B"), msg("C"), msg("D")])
    threading.Event().wait(0.2)
    lote.cancelar()
    esperar_lote(lote)
    threading.Event().wait(0.1)
    assert lote.canceladas == 4 and lote.baixadas == 0

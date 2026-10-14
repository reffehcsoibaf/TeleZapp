# SPDX-License-Identifier: GPL-3.0-or-later
"""Logica da janela principal com um wx simulado (testes/wx_falso.py)."""
import sys
import time
import types

import pytest

from testes import wx_falso

sys.modules["wx"] = wx_falso

from telezapp import config  # noqa: E402
from telezapp.armazenamento.banco import Banco  # noqa: E402
from telezapp.interface import janela as jm  # noqa: E402
from telezapp.nucleo import eventos as ev  # noqa: E402
from telezapp.nucleo import modelos as m  # noqa: E402

AGORA = time.time()


class ProvedorFalso:
    def __init__(self):
        self.pedidos = []

    def carregar_mensagens(self, cid, limite=50):
        self.pedidos.append(("carregar", cid, limite))

    def marcar_como_lida(self, cid):
        self.pedidos.append(("lida", cid))

    def enviar_texto(self, cid, texto, resposta_a=""):
        self.pedidos.append(("enviar", cid, texto, resposta_a))

    def atualizar_conversas(self):
        self.pedidos.append(("atualizar",))

    def pedir_codigo_pareamento(self, telefone):
        self.pedidos.append(("codigo", telefone))


class ContasFalsas:
    def __init__(self):
        self.p = ProvedorFalso()
        self.iniciadas = False
        self.provedores = {"t1": self.p}
        self.canceladas = []

    def adicionar(self, servico, telefone="", historico="recentes"):
        self.provedores["w-nova"] = self.p
        self.adicionadas = (servico, telefone, historico)
        return True

    def parear_de_novo(self, conta_id, historico):
        self.repareada = (conta_id, historico)
        return True

    def remover(self, conta_id):
        self.removida = conta_id

    def cancelar_nova(self, conta_id):
        self.canceladas.append(conta_id)
        return conta_id == "w-nova"

    def servico(self, conta_id):
        return "whatsapp" if conta_id.startswith("w") else "telegram"

    def provedor(self, conta_id):
        return self.p

    def nome(self, conta_id):
        return "Fábio"

    def iniciar_salvas(self):
        self.iniciadas = True

    def parar_todos(self):
        pass


class Tecla:
    def __init__(self, codigo, shift=False):
        self.codigo, self.shift, self.pulou = codigo, shift, False

    def GetKeyCode(self):
        return self.codigo

    def AltDown(self):
        return False

    def ControlDown(self):
        return False

    def ShiftDown(self):
        return self.shift

    def Skip(self):
        self.pulou = True


def conv(id, nome, nao_lidas=0, data=AGORA):
    return m.Conversa("t1", id, nome, "telegram", nao_lidas=nao_lidas,
                      data=data)


def msg(id, texto, minha=False, conversa="10", data=None):
    return m.Mensagem("t1", conversa, id, autor="Ana", minha=minha,
                      data=data or AGORA + int(id), texto=texto,
                      estado=m.ENVIADA if minha else "")


@pytest.fixture
def j(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path))
    cfg = config.Config()
    cfg.salvar_conta({"id": "t1", "servico": "telegram", "nome": "Fábio"})
    banco = Banco(str(tmp_path / "t.db"))
    b = ev.Barramento()
    janela = jm.Janela(cfg, banco, b)
    janela.contas = ContasFalsas()
    janela.comecar()
    janela.b = b
    b.publicar(ev.EstadoConta("t1", ev.CONECTADA))
    b.publicar(ev.ConversasAtualizadas("t1", [
        conv("10", "Ana", nao_lidas=2, data=AGORA - 10),
        conv("20", "Bruno", data=AGORA - 100)]))
    yield janela
    banco.fechar()


def test_lista_de_conversas(j):
    assert j.contas.iniciadas
    assert j.lista_conv.itens == ["Ana, Telegram, 2 não lidas",
                                  "Bruno, Telegram"]


def test_abrir_conversa_com_nao_lidas_poe_o_marcador(j):
    j.lista_conv.SetFocus()
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    assert j.lista_msgs.itens == [jm.TEXTO_CARREGANDO]
    assert ("carregar", "10", 50) in j.contas.p.pedidos
    assert ("lida", "10") in j.contas.p.pedidos
    assert j.lista_conv.itens[0] == "Ana, Telegram"
    assert wx_falso._foco[0] is j.lista_msgs

    j.b.publicar(ev.MensagensCarregadas("t1", "10", [
        msg("1", "antiga"), msg("2", "minha", minha=True),
        msg("3", "nova 1"), msg("4", "nova 2")]))
    itens = j.lista_msgs.itens
    assert itens[2] == "Início das mensagens não lidas: 2 mensagens"
    assert j.lista_msgs.selecionado() == itens[2]
    assert itens[3].endswith("nova 1")

    # Esc volta para as conversas e tira o marcador
    j._char_hook(Tecla(wx_falso.WXK_ESCAPE))
    assert wx_falso._foco[0] is j.lista_conv
    assert not any("Início" in x for x in j.lista_msgs.itens)


def test_enviar_trocar_pela_confirmada_e_falha(j):
    j._abrir_conversa(j.indice[("t1", "20")])
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [msg("5", "oi",
                                                          conversa="20")]))
    j.caixa.SetValue("tudo bem?")
    j.caixa.SetFocus()
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    assert j.caixa.GetValue() == ""
    assert ("enviar", "20", "tudo bem?", "") in j.contas.p.pedidos
    assert j.lista_msgs.itens[-1].endswith("tudo bem? enviando")

    enviada = msg("6", "tudo bem?", minha=True, conversa="20")
    j.b.publicar(ev.MensagemNova(enviada, j.indice[("t1", "20")],
                                 enviada_daqui=True))
    assert j.lista_msgs.itens[-1].endswith("tudo bem? enviada")
    assert not any("enviando" in x for x in j.lista_msgs.itens)

    j.caixa.SetValue("de novo")
    j._enviar_texto()
    j.b.publicar(ev.EnvioFalhou("t1", "20", "de novo", "sem conexão"))
    assert j.lista_msgs.itens[-1].endswith("de novo, falhou")
    assert j.caixa.GetValue() == "de novo"


def test_shift_enter_quebra_linha(j):
    j.caixa.SetFocus()
    t = Tecla(wx_falso.WXK_RETURN, shift=True)
    j._char_hook(t)
    assert t.pulou


def test_mensagem_nova_em_outra_conversa(j):
    j._abrir_conversa(j.indice[("t1", "20")])
    j.lista_conv.SetFocus()
    j.lista_conv.SetSelection(1)   # Bruno
    c = j.indice[("t1", "10")]
    c.nao_lidas, c.data = 3, AGORA + 50
    j.b.publicar(ev.MensagemNova(msg("9", "oi", data=AGORA + 50), c))
    assert j.lista_conv.itens[0] == "Ana, Telegram, 3 não lidas"
    # a selecao continua no Bruno, mesmo com a Ana subindo
    assert j.lista_conv.selecionado() == "Bruno, Telegram"
    assert j.status.startswith("Nova mensagem em Ana")


def test_mensagem_recebida_na_conversa_aberta_marca_lida(j):
    j._abrir_conversa(j.indice[("t1", "20")])
    j.contas.p.pedidos.clear()
    c = j.indice[("t1", "20")]
    j.b.publicar(ev.MensagemNova(msg("7", "chegou", conversa="20"), c))
    assert ("lida", "20") in j.contas.p.pedidos
    assert j.lista_msgs.itens[-1].endswith("chegou")
    assert j.lista_conv.itens[1] == "Bruno, Telegram"


def test_leitura_confirmada(j):
    j._abrir_conversa(j.indice[("t1", "20")])
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [
        msg("3", "a", minha=True, conversa="20"),
        msg("8", "b", minha=True, conversa="20")]))
    j.b.publicar(ev.LeituraConfirmada("t1", "20", 3))
    assert j.lista_msgs.itens[0].endswith("a, lida")
    assert j.lista_msgs.itens[1].endswith("b, enviada")


def test_responder_e_cancelar(j):
    j._abrir_conversa(j.indice[("t1", "20")])
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [
        msg("3", "pergunta", conversa="20")]))
    j._responder()
    assert j.rot_caixa.label.startswith("Respondendo a Ana")
    assert wx_falso._foco[0] is j.caixa
    j._char_hook(Tecla(wx_falso.WXK_ESCAPE))   # cancela so a resposta
    assert j.resposta_a is None and j.atual is not None
    assert j.caixa.visivel is True
    j._responder()
    assert j.caixa.visivel is True
    j.caixa.SetValue("sim")
    j._enviar_texto()
    assert ("enviar", "20", "sim", "3") in j.contas.p.pedidos
    assert j.caixa.visivel is True and wx_falso._foco[0] is j.caixa
    assert j.caixa.GetValue() == ""


def test_caixa_fica_visivel_com_a_conversa_aberta(j):
    assert j.lista_msgs.visivel is False and j.caixa.visivel is False
    j._mostrar_caixa()                        # sem conversa: so avisa
    assert j.caixa.visivel is False
    j._abrir_conversa(j.indice[("t1", "20")])
    assert j.lista_msgs.visivel is True and j.caixa.visivel is True
    assert j.GetTitle() == "TeleZapp: Bruno"
    j._mostrar_caixa()                        # Control E leva o foco
    assert wx_falso._foco[0] is j.caixa
    j.caixa.SetValue("rascunho")
    j._char_hook(Tecla(wx_falso.WXK_ESCAPE))  # Esc fecha a conversa
    assert j.atual is None and j.caixa.visivel is False
    assert j.lista_msgs.visivel is False
    assert j.caixa.GetValue() == ""
    j._abrir_conversa(j.indice[("t1", "20")])  # o rascunho volta
    assert j.caixa.GetValue() == "rascunho"


def test_lista_de_conversas_nao_e_refeita_sem_mudanca(j):
    antes = list(j.lista_conv.itens)
    chamadas = []
    original = j.lista_conv.Set
    j.lista_conv.Set = lambda itens: (chamadas.append(1), original(itens))
    j._preencher_conversas()
    j._preencher_conversas()
    assert chamadas == [] and j.lista_conv.itens == antes   # NVDA nao repete


def test_sincronia_interrompida_avisa_e_oferece_parear(j, monkeypatch):
    perguntas = []
    monkeypatch.setattr(jm.wx, "MessageBox",
                        lambda *a, **k: perguntas.append(a[0]) or jm.wx.NO,
                        raising=False)
    j.contas.provedores["w1"] = j.contas.p
    ditas = []
    j.fala.falar = lambda texto, interromper=False: ditas.append(texto)
    j.b.publicar(ev.ProgressoSincronia("w1", 57))
    j.b.publicar(ev.ProgressoSincronia("w1", 57, interrompida=True))
    assert "sincronia interrompida em 57%" in j.GetTitle()
    assert any("interrompida em 57%" in d for d in ditas)
    assert perguntas and "57%" in perguntas[0]
    j.b.publicar(ev.EstadoConta("w1", ev.CONECTADA))
    assert "interrompida" not in j.GetTitle()


def test_esc_fecha_a_conversa(j):
    j._abrir_conversa(j.indice[("t1", "20")])
    j._char_hook(Tecla(wx_falso.WXK_ESCAPE))
    assert j.atual is None and wx_falso._foco[0] is j.lista_conv
    assert j.lista_msgs.visivel is False and j.GetTitle() == "TeleZapp"
    assert j.lista_msgs.itens == [jm.TEXTO_SEM_CONVERSA]
    # mensagem que chega na conversa fechada conta como nao lida
    c = j.indice[("t1", "20")]
    c.nao_lidas = 1                       # o provedor soma antes de avisar
    j.b.publicar(ev.MensagemNova(msg("9", "oi", conversa="20"), c))
    assert j.lista_conv.itens[1] == "Bruno, Telegram, 1 não lida"


def test_titulo_mostra_sincronia_e_downloads(j):
    j.b.publicar(ev.ProgressoSincronia("w1", 40))
    assert j.GetTitle() == "TeleZapp - WhatsApp sincronizando 40%"
    j.b.publicar(ev.ProgressoSincronia("w1", 100))
    assert j.GetTitle() == "TeleZapp"
    j.b.publicar(ev.ProgressoMidia("t1", "10", "1", 45))
    assert j.GetTitle() == "TeleZapp - baixando mídia 45%"
    j.b.publicar(ev.ProgressoMidia("t1", "10", "2", 10))
    assert j.GetTitle() == "TeleZapp - baixando 2 mídias"
    j.b.publicar(ev.MidiaBaixada("t1", "10", "1", "/p/1.jpg"))
    j.b.publicar(ev.MidiaBaixada("t1", "10", "2", cancelada=True))
    assert j.GetTitle() == "TeleZapp"
    j.sincronia["w1"] = (30, time.time() - 120)   # celular parou de mandar
    j._atualizar_titulo()
    assert j.GetTitle() == "TeleZapp" and not j.sincronia


def test_sem_conexao_nao_envia(j):
    j._abrir_conversa(j.indice[("t1", "20")])
    j.b.publicar(ev.EstadoConta("t1", ev.DESCONECTADA))
    j.caixa.SetValue("oi")
    j._enviar_texto()
    assert not [p for p in j.contas.p.pedidos if p[0] == "enviar"]
    assert j.caixa.GetValue() == "oi"


def test_pedir_login_da_thread_do_provedor(j, monkeypatch):
    chamadas = []

    def falso(pai, servico, etapa, erro, valor):
        chamadas.append((servico, etapa, erro, valor))
        return "12345"
    monkeypatch.setattr(jm.dialogos, "pedir_login", falso)
    conta = types.SimpleNamespace(servico="telegram", telefone="+55")
    assert j.pedir(conta, "codigo", "Código incorreto.") == "12345"
    assert chamadas == [("Telegram", "codigo", "Código incorreto.", "")]


def test_primeira_vez_sem_contas(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path / "vazio"))
    cfg = config.Config()
    banco = Banco(str(tmp_path / "v.db"))
    janela = jm.Janela(cfg, banco, ev.Barramento())
    janela.contas = ContasFalsas()
    janela.comecar()
    assert janela.lista_conv.itens == [jm.TEXTO_SEM_CONTAS]
    janela._char_hook(Tecla(wx_falso.WXK_RETURN))   # nao quebra
    banco.fechar()


def test_pareamento_do_whatsapp(j):
    j.adicionar_conta("whatsapp")
    dlg = j.pareamentos["w-nova"]
    assert dlg.mostrado and dlg.modo.GetSelection() == 0
    # codigo: numero invalido nao pede nada; valido pede ao provedor
    dlg.telefone.SetValue("123")
    dlg._gerar()
    assert not [p for p in j.contas.p.pedidos if p[0] == "codigo"]
    dlg.telefone.SetValue("51 99999 8888")
    dlg._gerar()
    assert ("codigo", "+5551999998888") in j.contas.p.pedidos
    j.b.publicar(ev.CodigoPareamento("w-nova", "ABCD-EFGH"))
    assert dlg.codigo.GetValue() == "ABCD-EFGH"
    assert wx_falso._foco[0] is dlg.janela_codigo.campo
    # QR: a imagem e trocada quando chega um novo
    j.b.publicar(ev.QrPareamento("w-nova", "2@qr1"))
    assert dlg.imagem.bitmap.img.w == dlg.imagem.bitmap.img.h > 100
    assert dlg.situacao_qr.GetValue().startswith("QR Code pronto")
    # pareou: a janela fecha sozinha
    j.b.publicar(ev.ContaPronta("w-nova", "Fábio", "+5551999998888"))
    assert "w-nova" not in j.pareamentos and not dlg.vivo


def test_cancelar_pareamento(j):
    j.adicionar_conta("whatsapp")
    dlg = j.pareamentos["w-nova"]
    dlg._ao_fechar(None)
    assert j.contas.canceladas == ["w-nova"] and not j.pareamentos


def test_conta_salva_que_recusou_parear_nao_reabre_sozinha(j):
    j.b.publicar(ev.QrPareamento("w-salva", "2@a"))
    dlg = j.pareamentos["w-salva"]
    dlg._ao_fechar(None)
    j.b.publicar(ev.QrPareamento("w-salva", "2@b"))
    assert "w-salva" not in j.pareamentos
    j._reconectar()
    j.b.publicar(ev.QrPareamento("w-salva", "2@c"))
    assert "w-salva" in j.pareamentos


def test_entregue_e_lida_no_whatsapp(j):
    j._abrir_conversa(j.indice[("t1", "20")])
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [
        msg("3", "a", minha=True, conversa="20")]))
    j.b.publicar(ev.EstadosMensagens("t1", "20", ["3"], m.ENTREGUE))
    assert j.lista_msgs.itens[0].endswith("a, entregue")
    j.b.publicar(ev.EstadosMensagens("t1", "20", ["3"], m.LIDA))
    j.b.publicar(ev.EstadosMensagens("t1", "20", ["3"], m.ENTREGUE))
    assert j.lista_msgs.itens[0].endswith("a, lida")


def test_whatsapp_pergunta_o_historico_e_preenche_o_numero(j):
    j.cfg.salvar_conta({"id": "t1", "servico": "telegram",
                        "telefone": "+5551999998888", "nome": "Fábio"})
    wx_falso.escolha_lista[0] = 3          # "Último ano"
    j.adicionar_conta("whatsapp")
    assert j.contas.adicionadas == ("whatsapp", "+5551999998888", "365")
    dlg = j.pareamentos["w-nova"]
    assert dlg.telefone.GetValue() == "+5551999998888"
    wx_falso.escolha_lista[0] = 0


def test_desistir_na_escolha_do_historico(j):
    wx_falso.resposta_lista[0] = wx_falso.ID_CANCEL
    try:
        j.adicionar_conta("whatsapp")
    finally:
        wx_falso.resposta_lista[0] = wx_falso.ID_OK
    assert not j.pareamentos and not hasattr(j.contas, "adicionadas")


def test_codigo_abre_janela_propria_e_tela_cheia_do_qr(j):
    j.adicionar_conta("whatsapp")
    dlg = j.pareamentos["w-nova"]
    j.b.publicar(ev.CodigoPareamento("w-nova", "ABCD-EFGH"))
    assert dlg.janela_codigo.campo.GetValue() == "ABCD-EFGH"
    assert wx_falso._foco[0] is dlg.janela_codigo.campo
    j.b.publicar(ev.CodigoPareamento("w-nova", "WXYZ-1234"))
    assert dlg.janela_codigo.campo.GetValue() == "WXYZ-1234"
    dlg._tela_cheia()                       # sem QR ainda: nao abre
    assert dlg.tela_cheia is None
    j.b.publicar(ev.QrPareamento("w-nova", "2@" + "x" * 150))
    dlg._tela_cheia()
    cheia = dlg.tela_cheia
    assert cheia.cheia
    # o QR ocupa quase toda a altura da tela, ampliado por um inteiro
    assert cheia.imagem.bitmap.img.w >= 900
    j.b.publicar(ev.QrPareamento("w-nova", "2@" + "y" * 150))
    assert cheia.codigo == "2@" + "y" * 150
    j.b.publicar(ev.ContaPronta("w-nova", "Fábio", "+55"))
    assert not cheia.vivo and not dlg.janela_codigo


def test_desconectada_pelo_celular_oferece_parear_de_novo(j):
    wx_falso.resposta_messagebox[0] = wx_falso.YES
    try:
        j.b.publicar(ev.EstadoConta("w1", ev.PRECISA_LOGIN,
                                    "desconectada pelo celular"))
    finally:
        wx_falso.resposta_messagebox[0] = wx_falso.NO
    assert j.contas.repareada == ("w1", "recentes")
    assert "w1" in j.pareamentos


def test_remover_conta(j):
    wx_falso.resposta_messagebox[0] = wx_falso.YES
    try:
        j._remover_conta()
    finally:
        wx_falso.resposta_messagebox[0] = wx_falso.NO
    assert j.contas.removida == "t1"
    assert j.lista_conv.itens == [jm.TEXTO_SEM_CONTAS]


def test_qr_gerado_e_lido_por_um_leitor_de_qr():
    cv2 = pytest.importorskip("cv2")
    import numpy as np
    from telezapp.interface import dialogos
    # do tamanho de um QR real do WhatsApp
    codigo = "2@" + "R" * 80 + "," + "n" * 44 + "," + "i" * 44 + "," + \
        "a" * 44 + ",1"
    for escala in (dialogos.ESCALA_JANELA, 12):
        lado, px = dialogos.pixels_qr(codigo, escala)
        img = np.frombuffer(px, dtype=np.uint8).reshape(lado, lado, 3)
        texto, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
        assert texto == codigo


def test_mensagens_da_sincronia_sem_aviso_e_resumo(j):
    j.status = ""
    c = j.indice[("t1", "20")]
    j.b.publicar(ev.MensagemNova(msg("40", "offline", conversa="20"), c,
                                 silenciosa=True))
    assert not j.status.startswith("Nova mensagem")
    j.b.publicar(ev.SincronizacaoConcluida("t1", 10))
    assert j.status.startswith("10 mensagens novas chegaram no WhatsApp")


class MidiasFalsas:
    def __init__(self):
        self.baixados, self.cancelados, self.prontas = [], [], {}
        self.ativo = False

    def caminho(self, x):
        return self.prontas.get(x.chave)

    def baixar(self, x, automatica=False):
        self.baixados.append(x.id)
        self.ativo = True

    def baixando(self, chave):
        return self.ativo

    def cancelar(self, chave):
        self.cancelados.append(chave)
        self.ativo = False


def foto(id, tamanho=1000):
    return m.Mensagem("t1", "10", id, autor="Ana", tipo=m.FOTO,
                      tamanho=tamanho, data=AGORA + int(id))


@pytest.fixture
def jm_midia(j, monkeypatch):
    j.midias = MidiasFalsas()
    abertas = []
    monkeypatch.setattr(jm.visualizadores, "abrir",
                        lambda pai, x, caminho, fala, nome="": abertas.append(
                            (x.id, caminho, nome)))
    j.lista_conv.SetFocus()
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [
        msg("1", "texto"), foto("2"), foto("3", tamanho=200 * 1048576)]))
    j.abertas = abertas
    return j


def selecionar(j, id):
    j.lista_msgs.SetSelection(j.mapa.index(id))
    j.lista_msgs.SetFocus()


def test_enter_em_midia_baixa_e_abre_quando_chega(jm_midia):
    j = jm_midia
    selecionar(j, "2")
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    assert j.midias.baixados == ["2"] and j.abrindo == ("t1", "10", "2")
    j.b.publicar(ev.ProgressoMidia("t1", "10", "2", 60))
    j.b.publicar(ev.MidiaBaixada("t1", "10", "2", "/p/2.jpg"))
    assert j.abertas == [("2", "/p/2.jpg", "Ana")] and j.abrindo is None


def test_midia_ja_baixada_abre_direto_e_texto_mostra_detalhes(jm_midia):
    j = jm_midia
    j.midias.prontas[("t1", "10", "2")] = "/p/2.jpg"
    selecionar(j, "2")
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    assert j.abertas == [("2", "/p/2.jpg", "Ana")] and not j.midias.baixados
    selecionar(j, "1")                  # texto: continua mostrando detalhes
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    assert j.abertas == [("2", "/p/2.jpg", "Ana")]


def test_esc_cancela_o_download_antes_de_voltar(jm_midia):
    j = jm_midia
    selecionar(j, "2")
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    j._char_hook(Tecla(wx_falso.WXK_ESCAPE))
    assert j.midias.cancelados == [("t1", "10", "2")]
    assert wx_falso._foco[0] is j.lista_msgs          # nao saiu da lista
    j.b.publicar(ev.MidiaBaixada("t1", "10", "2", cancelada=True))
    assert j.abertas == []
    j._char_hook(Tecla(wx_falso.WXK_ESCAPE))          # agora volta
    assert wx_falso._foco[0] is j.lista_conv


def test_midia_grande_pede_confirmacao(jm_midia, monkeypatch):
    j = jm_midia
    respostas = []
    monkeypatch.setattr(jm.wx, "MessageBox",
                        lambda *a, **k: respostas.append(a[0]) or jm.wx.NO)
    selecionar(j, "3")
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    assert "200" in respostas[0] and j.midias.baixados == []


def test_erro_de_download_e_baixar_sem_abrir(jm_midia, monkeypatch):
    j = jm_midia
    avisos = []
    monkeypatch.setattr(jm.wx, "MessageBox",
                        lambda *a, **k: avisos.append(a[0]))
    selecionar(j, "2")
    j._abrir_midia()
    j.b.publicar(ev.MidiaBaixada("t1", "10", "2", erro="não tem mais"))
    assert avisos == ["não tem mais"] and j.abertas == []
    j._abrir_midia(abrir=False)
    j.b.publicar(ev.MidiaBaixada("t1", "10", "2", "/p/2.jpg"))
    assert j.abertas == []                              # so baixou


def test_menu_de_midias_muda_a_opcao(j):
    j.midias = MidiasFalsas()
    assert j.cfg.get("midias_baixar") == "demanda"
    j._mudar_baixar("automatico")
    assert j.cfg.get("midias_baixar") == "automatico"


class MotorFalso:
    criados = []

    def __init__(self, caminho):
        self.caminho, self.tocando, self.terminou = caminho, False, False
        self.fechado = False
        MotorFalso.criados.append(self)

    def tocar(self):
        self.tocando = True

    def alternar(self):
        self.tocando = not self.tocando

    def fechar(self):
        self.fechado, self.tocando = True, False


def voz(id):
    return m.Mensagem("t1", "10", id, autor="Ana", tipo=m.VOZ,
                      tamanho=1000, data=AGORA + int(id))


def test_enter_em_voz_toca_sem_janela_pausa_e_esc_para(jm_midia, monkeypatch):
    j = jm_midia
    MotorFalso.criados = []
    monkeypatch.setattr(jm, "Reprodutor", MotorFalso)
    monkeypatch.setattr(jm.wx, "CallLater", lambda *a, **k: None,
                        raising=False)
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [voz("5")]))
    j.midias.prontas[("t1", "10", "5")] = "/p/5.ogg"
    selecionar(j, "5")
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    assert j.abertas == []                     # sem janela
    motor = MotorFalso.criados[0]
    assert motor.tocando and motor.caminho == "/p/5.ogg"
    j._char_hook(Tecla(wx_falso.WXK_RETURN))   # pausa
    assert not motor.tocando and len(MotorFalso.criados) == 1
    j._char_hook(Tecla(wx_falso.WXK_RETURN))   # continua
    assert motor.tocando
    j._char_hook(Tecla(wx_falso.WXK_ESCAPE))   # para; a conversa continua
    assert motor.fechado and j.atual is not None and j.audio is None
    j._char_hook(Tecla(wx_falso.WXK_ESCAPE))   # agora fecha a conversa
    assert j.atual is None


def test_audio_com_opcao_janela_abre_o_player(jm_midia, monkeypatch):
    j = jm_midia
    j.cfg.set("audio_janela", "janela")
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [voz("5")]))
    j.midias.prontas[("t1", "10", "5")] = "/p/5.ogg"
    selecionar(j, "5")
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    assert [a[0] for a in j.abertas] == ["5"] and j.audio is None


def test_formato_que_o_app_nao_toca_abre_a_janela(jm_midia, monkeypatch):
    j = jm_midia
    monkeypatch.setattr(jm, "Reprodutor", lambda c: (_ for _ in ()).throw(
        jm.FormatoNaoSuportado("m4a")))
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [voz("5")]))
    j.midias.prontas[("t1", "10", "5")] = "/p/5.m4a"
    selecionar(j, "5")
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    assert [a[0] for a in j.abertas] == ["5"]


def test_enviar_mantem_a_selecao_na_mensagem_atual(jm_midia):
    j = jm_midia
    selecionar(j, "1")                       # mensagem antiga
    j.caixa.SetValue("oi")
    j._enviar_texto()
    assert j._chave_selecionada() == "1"
    # a confirmacao do servico tambem nao move a selecao
    j.b.publicar(ev.MensagemNova(
        msg("9", "oi", conversa="10", minha=True, data=AGORA + 99),
        j.indice[("t1", "10")], enviada_daqui=True)) \
        if "enviada_daqui" in ev.MensagemNova.__dataclass_fields__ else None
    assert j._chave_selecionada() == "1"
    assert wx_falso._foco[0] is j.caixa


def test_nada_move_a_selecao_sozinho(jm_midia):
    j = jm_midia
    for onde in ("1", "3"):                  # no meio e no fim
        selecionar(j, onde)
        antes = j._chave_selecionada()
        i = j.lista_msgs.GetSelection()
        # mensagem de outra pessoa chega com o foco na lista e fora dela
        j.caixa.SetFocus()
        c = j.indice[("t1", "10")]
        j.b.publicar(ev.MensagemNova(msg("7" + onde, "nova", conversa="10",
                                         data=AGORA + 70 + int(onde)), c))
        assert j._chave_selecionada() == antes
        assert j.lista_msgs.GetSelection() == i
        # o servidor devolve mensagens de novo (recarga)
        j.b.publicar(ev.MensagensCarregadas("t1", "10", [
            msg("1", "texto")]))
        assert j._chave_selecionada() == antes


def test_lista_de_mensagens_so_acrescenta_no_fim(jm_midia):
    j = jm_midia
    selecionar(j, "2")
    chamadas = []
    original = j.lista_msgs.Set
    j.lista_msgs.Set = lambda itens: (chamadas.append(1), original(itens))
    c = j.indice[("t1", "10")]
    j.b.publicar(ev.MensagemNova(msg("8", "nova", conversa="10",
                                     data=AGORA + 99), c))
    assert chamadas == []                  # nao refez a lista: sem anuncio
    assert j.lista_msgs.itens[-1].endswith("nova") or "nova" in \
        j.lista_msgs.itens[-1]
    assert j._chave_selecionada() == "2"


def _abrir_ana(j, n=6):
    j.lista_conv.SetFocus()
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [
        msg(str(i), "texto %d" % i, conversa="10") for i in range(1, n + 1)]))


def test_reabre_no_ponto_em_que_parou(j):
    _abrir_ana(j)
    j.lista_msgs.SetSelection(j.mapa.index("2"))
    j.selecao_automatica = False
    j._char_hook(Tecla(wx_falso.WXK_ESCAPE))          # fecha a conversa
    assert j.banco.posicao("t1", "10") == "2"
    _abrir_ana(j)
    assert j._chave_selecionada() == "2"


def test_parou_no_fim_reabre_na_ultima_mensagem(j):
    _abrir_ana(j)
    j.lista_msgs.SetSelection(j.lista_msgs.GetCount() - 1)
    j._char_hook(Tecla(wx_falso.WXK_ESCAPE))
    assert j.banco.posicao("t1", "10") == ""
    # chegaram mensagens novas enquanto estava fora
    j.indice[("t1", "10")].nao_lidas = 2
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [
        msg(str(i), "texto %d" % i, conversa="10") for i in range(1, 9)]))
    assert j._chave_selecionada() == "8"             # a ultima da conversa


def test_primeira_vez_continua_no_marcador(j):
    assert j.banco.posicao("t1", "10") is None
    _abrir_ana(j)
    assert j._chave_selecionada() == jm.MARCADOR


def test_ponto_que_sumiu_cai_no_marcador_ou_fim(j):
    j.banco.salvar_posicao("t1", "20", "999")
    j.lista_conv.SetSelection(1)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [
        msg("1", "a", conversa="20"), msg("2", "b", conversa="20")]))
    assert j._chave_selecionada() == "2"


def test_alt2_marcador_na_conversa_e_proxima_na_lista(j):
    _abrir_ana(j)
    j.lista_msgs.SetSelection(0)
    j.selecao_automatica = False
    j.caixa.SetFocus()
    j._ir_nao_lidas()
    assert j._chave_selecionada() == jm.MARCADOR
    assert wx_falso._foco[0] is j.lista_msgs
    # sem marcador: avisa
    j.marcador_id = None
    j._preencher_mensagens()
    j._ir_nao_lidas()
    # na lista de conversas: proxima com nao lidas
    j.indice[("t1", "20")].nao_lidas = 4
    j.lista_conv.SetFocus()
    j.lista_conv.SetSelection(0)
    j._ir_nao_lidas()
    assert j._conversa_selecionada().id == "20"


def test_lista_de_conversas_lembra_onde_parou(j):
    j.lista_conv.SetSelection(1)
    j._guardar_lista()
    assert j.cfg.get("ultima_conversa") == ["t1", "20"]
    j.lista_conv.SetSelection(0)
    j.comecar()
    assert j.lista_conv.GetSelection() == 1

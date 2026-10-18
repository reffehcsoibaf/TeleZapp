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

    def enviar_arquivo(self, cid, anexo, legenda=""):
        self.pedidos.append(("arquivo", cid, anexo.tipo, anexo.nome,
                             legenda))

    def responder_acao(self, msg, acao):
        self.pedidos.append(("acao", msg.id, acao["rotulo"]))

    def atualizar_conversas(self):
        self.pedidos.append(("atualizar",))

    def arquivar_conversa(self, cid, arquivar):
        self.pedidos.append(("arquivar", cid, arquivar))
        return True

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
    # o padrao e falar pouco; os testes olham o que se fala, entao ligam
    for chave in ("falar_novas", "confirmar_envio", "falar_reacoes"):
        cfg.set(chave, True)
    banco = Banco(str(tmp_path / "t.db"))
    b = ev.Barramento()
    janela = jm.Janela(cfg, banco, b)
    janela.contas = ContasFalsas()
    janela.comecar()
    janela.lista_conv.SetFocus()      # o foco inicial e a caixa de conta
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


def test_conversa_aberta_renomeada_atualiza_titulo_e_lista(j):
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    assert j.rot_msgs.GetLabel() == "Mensagens de Ana"
    j.b.publicar(ev.ConversasAtualizadas("t1", [
        conv("10", "Ana Maria", data=AGORA), conv("11", "Família")]))
    assert j.rot_msgs.GetLabel() == "Mensagens de Ana Maria"
    assert j.GetTitle() == "TeleZapp: Ana Maria"
    assert j.lista_conv.itens[0].startswith("Ana Maria")


def test_abrir_conversa_com_nao_lidas_foca_o_marcador(j):
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j.lista_conv.SetFocus()
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    assert ditas == []                              # nada falado a parte
    assert ("carregar", "10", 50) in j.contas.p.pedidos
    assert ("lida", "10") in j.contas.p.pedidos
    assert j.lista_conv.itens[0] == "Ana, Telegram"
    assert wx_falso._foco[0] is j.lista_conv        # espera o servico

    j.b.publicar(ev.MensagensCarregadas("t1", "10", [
        msg("1", "antiga"), msg("2", "minha", minha=True),
        msg("3", "nova 1"), msg("4", "nova 2")]))
    itens = j.lista_msgs.itens
    assert j.lista_msgs.selecionado() == \
        "Início das mensagens não lidas: 2 mensagens"
    assert itens[itens.index(j.lista_msgs.selecionado()) + 1].endswith(
        "nova 1")                                    # seta para baixo: 1a
    assert wx_falso._foco[0] is j.lista_msgs         # foco uma vez so
    assert ditas == []

    j._char_hook(Tecla(wx_falso.WXK_ESCAPE))         # Esc volta
    assert wx_falso._foco[0] is j.lista_conv


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
    # estes testes olham o que se fala; o padrao e falar pouco, entao liga tudo
    for chave in ("falar_quem_toca", "seq_falar_proximo", "seq_falar_tipo",
                  "seq_falar_quem", "seq_falar_duracao",
                  "seq_falar_velocidade"):
        j.cfg.set(chave, True)
    abertas = []
    monkeypatch.setattr(jm.visualizadores, "abrir",
                        lambda pai, x, caminho, fala, nome="", cfg=None: abertas.append(
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


def test_parou_no_fim_com_novas_abre_no_marcador(j):
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
    assert j._chave_selecionada() == jm.MARCADOR     # com nao lidas: marcador


def test_primeira_vez_continua_no_marcador(j):
    assert j.banco.posicao("t1", "10") is None
    _abrir_ana(j)
    assert j._chave_selecionada() == jm.MARCADOR and j.marcador_id == "5"


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


def test_foco_vem_mesmo_se_o_servico_demora(j):
    j.lista_conv.SetFocus()
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    assert wx_falso._foco[0] is j.lista_conv
    j._dar_foco_as_mensagens(j.atual)               # passou o tempo limite
    assert wx_falso._foco[0] is j.lista_msgs
    j._dar_foco_as_mensagens(j.atual)               # nao repete


def test_com_uma_so_nao_lida_abre_no_marcador_mesmo_se_parou_no_fim(j):
    j.banco.salvar_posicao("t1", "10", "")          # tinha parado no fim
    j.indice[("t1", "10")].nao_lidas = 1
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [
        msg("1", "antiga", conversa="10"), msg("2", "nova", conversa="10")]))
    assert j._chave_selecionada() == jm.MARCADOR
    assert j.lista_msgs.selecionado().startswith("Início das mensagens")


def test_sem_nao_lidas_abre_no_ponto_guardado(j):
    j.banco.salvar_posicao("t1", "20", "1")
    j.lista_conv.SetSelection(1)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [
        msg("1", "a", conversa="20"), msg("2", "b", conversa="20")]))
    assert j._chave_selecionada() == "1"


def test_parou_no_fim_sem_novas_abre_na_ultima(j):
    _abrir_ana(j)
    j.lista_msgs.SetSelection(j.lista_msgs.GetCount() - 1)
    j._char_hook(Tecla(wx_falso.WXK_ESCAPE))
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [
        msg(str(i), "texto %d" % i, conversa="10") for i in range(1, 8)]))
    assert j._chave_selecionada() == "7"


def test_resposta_mostra_a_mensagem_original(j):
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    longa = "texto muito comprido " * 10
    r = msg("4", "concordo", conversa="10")
    r.resposta_a = "3"
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [
        msg("3", longa, conversa="10"), r]))
    linha = [x for x in j.lista_msgs.itens if "concordo" in x][0]
    assert 'concordo, em resposta a Ana: "texto muito comprido' in linha
    assert linha.endswith('…"')
    assert len(linha) < 200


def test_resposta_a_mensagem_fora_da_lista_usa_o_banco(j):
    j.banco.salvar_mensagens([msg("1", "pergunta antiga", conversa="10")])
    r = msg("40", "sim", conversa="10")
    r.resposta_a = "1"
    j._mesclar(("t1", "10"), [r])
    j.atual = ("t1", "10")
    j._preencher_mensagens()
    assert any('"pergunta antiga"' in x for x in j.lista_msgs.itens)
    r.resposta_a = "999"                              # nao existe em lugar algum
    j._preencher_mensagens()
    assert any("em resposta a uma mensagem mais antiga" in x
               for x in j.lista_msgs.itens)


def _preparar_sequencia(j, monkeypatch):
    MotorFalso.criados = []
    monkeypatch.setattr(jm, "Reprodutor", MotorFalso)
    monkeypatch.setattr(jm.wx, "CallLater", lambda *a, **k: None,
                        raising=False)
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [
        voz("5"), msg("6", "texto"), voz("7"), foto("8")]))
    for i in ("5", "7"):
        j.midias.prontas[("t1", "10", i)] = "/p/%s.ogg" % i
    selecionar(j, "5")
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    return MotorFalso.criados[0]


def test_audios_tocam_em_sequencia(jm_midia, monkeypatch):
    j = jm_midia
    primeiro = _preparar_sequencia(j, monkeypatch)
    primeiro.terminou = True
    j._vigiar_audio(primeiro)                    # acabou o primeiro
    assert len(MotorFalso.criados) == 2          # pulou o texto, tocou o 7
    assert MotorFalso.criados[1].caminho == "/p/7.ogg"
    assert j._chave_selecionada() == "5"         # selecao nao se mexeu
    segundo = MotorFalso.criados[1]
    segundo.terminou = True
    j._vigiar_audio(segundo)                     # nao ha mais audios
    assert len(MotorFalso.criados) == 2 and j.audio is None


def test_sequencia_desligada_para_no_fim(jm_midia, monkeypatch):
    j = jm_midia
    j.cfg.set("audio_sequencia", "nao")
    primeiro = _preparar_sequencia(j, monkeypatch)
    primeiro.terminou = True
    j._vigiar_audio(primeiro)
    assert len(MotorFalso.criados) == 1 and j.audio is None


def test_sequencia_baixa_o_proximo_se_preciso(jm_midia, monkeypatch):
    j = jm_midia
    primeiro = _preparar_sequencia(j, monkeypatch)
    del j.midias.prontas[("t1", "10", "7")]
    primeiro.terminou = True
    j._vigiar_audio(primeiro)
    assert j.midias.baixados[-1] == "7"


def test_ir_para_a_mensagem_respondida(j):
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    r = msg("4", "concordo", conversa="10")
    r.resposta_a = "2"
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [
        msg("1", "a", conversa="10"), msg("2", "alvo", conversa="10"),
        msg("3", "b", conversa="10"), r]))
    selecionar(j, "4")
    j._ir_para_respondida()
    assert j._chave_selecionada() == "2"
    j._ir_para_respondida()                       # nao e resposta
    assert j._chave_selecionada() == "2"


def test_ir_para_respondida_fora_da_lista_busca_no_banco(j):
    j.banco.salvar_mensagens([msg("1", "velha", conversa="10")])
    r = msg("40", "sim", conversa="10")
    r.resposta_a = "1"
    j._mesclar(("t1", "10"), [r])
    j.atual = ("t1", "10")
    j._preencher_mensagens("ultima")
    j._ir_para_respondida()
    assert j._chave_selecionada() == "1"
    r.resposta_a = "999"
    j._preencher_mensagens("ultima")
    j._ir_para_respondida()                       # nao existe: avisa e fica
    assert j._chave_selecionada() == "40"


def test_esc_volta_da_mensagem_respondida(j):
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    r = msg("4", "concordo", conversa="10")
    r.resposta_a = "2"
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [
        msg("1", "a", conversa="10"), msg("2", "alvo", conversa="10"),
        msg("3", "b", conversa="10"), r]))
    selecionar(j, "4")
    j._ir_para_respondida()
    assert j._chave_selecionada() == "2"
    j._char_hook(Tecla(wx_falso.WXK_ESCAPE))      # volta para a resposta
    assert j._chave_selecionada() == "4" and j.atual is not None
    j._char_hook(Tecla(wx_falso.WXK_ESCAPE))      # agora fecha a conversa
    assert j.atual is None


def test_rotulo_da_mencao_nome_usuario_e_telefone_por_ultimo():
    from telezapp.interface import dialogos
    assert dialogos.rotulo_mencao(
        {"nome": "Ana Silva", "usuario": "ana", "telefone": "+5551999"}) == \
        "Ana Silva, @ana, +5551999"
    assert dialogos.rotulo_mencao({"nome": "+5551999",
                                   "telefone": "+5551999"}) == "+5551999"
    assert dialogos.rotulo_mencao({"usuario": "bia"}) == "@bia"
    assert dialogos.rotulo_mencao({}) == "Contato sem nome"


def test_detalhes_junta_links_do_texto_e_escondidos(j, monkeypatch):
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    x = msg("4", "veja https://a.com e aqui", conversa="10")
    m.guardar_extras(x, links=[("https://escondido.com", "aqui"),
                               ("https://a.com", "https://a.com")],
                     botoes=[("Site", "https://s.com")],
                     mencoes=[{"nome": "Bia", "id": "77"}])
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [x]))
    chamadas = []
    monkeypatch.setattr(jm.dialogos, "mostrar_texto",
                        lambda *a, **k: chamadas.append(k) or None)
    selecionar(j, "4")
    j._detalhes()
    k = chamadas[0]
    assert k["links"] == [("https://escondido.com", "aqui"),
                          ("https://a.com", "https://a.com")]
    assert k["botoes"] == [("Site", "https://s.com")]
    assert k["mencoes"] == [{"nome": "Bia", "id": "77"}]


def test_enter_na_mencao_abre_conversa_nova_no_mesmo_servico(j, monkeypatch):
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    x = msg("4", "oi @Bia", conversa="10")
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [x]))
    monkeypatch.setattr(jm.wx, "CallAfter", lambda f, *a: f(*a),
                        raising=False)
    monkeypatch.setattr(jm.dialogos, "mostrar_texto",
                        lambda *a, **k: {"nome": "Bia", "id": "77"})
    selecionar(j, "4")
    j._detalhes()
    assert j.atual == ("t1", "77")
    assert j.indice[("t1", "77")].nome == "Bia"
    assert ("carregar", "77", 50) in j.contas.p.pedidos
    # a mencao de uma conversa que ja existe so abre essa conversa
    j._fechar_conversa()
    j._abrir_conversa_da_mencao(x, {"nome": "Ana", "id": "20"})
    assert j.atual == ("t1", "20")


def test_mencao_sem_id_avisa_e_nao_abre(j):
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    x = msg("4", "oi", conversa="10")
    j._abrir_conversa_da_mencao(x, {"nome": "Bia"})
    assert j.atual is None and "Não consegui localizar" in ditas[-1]


def test_foto_com_link_na_legenda_avisa_na_lista_e_detalhes_traz_o_link(
        j, monkeypatch):
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    x = msg("5", "veja https://a.com/x", conversa="10")
    x.tipo = m.FOTO
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [x]))
    linhas = [j.lista_msgs.GetString(i)
              for i in range(j.lista_msgs.GetCount())]
    assert any("com 1 link (Tab)" in l for l in linhas), linhas
    chamadas = []
    monkeypatch.setattr(jm.dialogos, "mostrar_texto",
                        lambda *a, **k: chamadas.append(k) or None)
    selecionar(j, "5")
    j._detalhes()
    assert chamadas[0]["links"] == [("https://a.com/x", "https://a.com/x")]


def test_enter_abre_a_midia_mesmo_com_link_e_texto_abre_caixa_somente_leitura(
        j, monkeypatch):
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    x = msg("5", "veja https://a.com/x", conversa="10")
    x.tipo = m.FOTO
    sem = msg("6", "so a foto", conversa="10")
    sem.tipo = m.FOTO
    txt = msg("7", "texto inteiro da mensagem", conversa="10")
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [x, sem, txt]))
    abertas, detalhes, caixas = [], [], []
    monkeypatch.setattr(j, "_abrir_midia", lambda *a, **k: abertas.append(1))
    monkeypatch.setattr(j, "_detalhes", lambda: detalhes.append(1))
    monkeypatch.setattr(
        jm.dialogos, "mostrar_mensagem",
        lambda pai, titulo, texto, copiar: caixas.append(
            (titulo, texto, copiar)))
    selecionar(j, "5")                    # foto com link: abre a midia
    j._detalhes_ou_marcador()
    assert len(abertas) == 1 and not detalhes and not caixas
    selecionar(j, "6")
    j._detalhes_ou_marcador()
    assert len(abertas) == 2
    selecionar(j, "7")                    # so texto: caixa somente leitura
    j._detalhes_ou_marcador()
    assert len(abertas) == 2 and not detalhes
    assert caixas == [("Mensagem de Ana", "texto inteiro da mensagem",
                       j._copiar_texto)]


def test_copiar_texto_da_caixa_fala_e_vai_para_a_area_de_transferencia(
        j, monkeypatch):
    ditas, copiados = [], []

    class Area:
        def Open(self):
            return True

        def SetData(self, d):
            copiados.append(d)

        def Close(self):
            pass
    monkeypatch.setattr(jm.wx, "TheClipboard", Area(), raising=False)
    monkeypatch.setattr(jm.wx, "TextDataObject", lambda t: t, raising=False)
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j._copiar_texto("conteudo")
    assert copiados == ["conteudo"] and ditas == ["Texto copiado."]


def test_detalhes_pedem_ao_provedor_o_nome_de_quem_recebeu(j, monkeypatch):
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    x = msg("7", "oi", minha=True, conversa="10")
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [x]))
    j.banco.salvar_recibos("t1", "10", ["7"], "5551@s.whatsapp.net",
                           "entregue", AGORA)
    j.contas.p.nome_de_participante = lambda q: "Ana Silva"
    chamadas = []
    monkeypatch.setattr(jm.dialogos, "mostrar_texto",
                        lambda *a, **k: chamadas.append(a) or None)
    selecionar(j, "7")
    j._detalhes()
    assert "Entregue a Ana Silva em" in chamadas[0][2]


def _conversa_com_botoes(j):
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    x = msg("8", "Você confirma?", conversa="10")
    m.guardar_extras(x, acoes=[{"tipo": "modelo", "rotulo": "Sim & não",
                                "id": "s", "indice": 0},
                               {"tipo": "lista", "rotulo": "Particular",
                                "id": "p", "indice": 0}])
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [x, msg("9", "oi")]))
    return x


def test_botoes_da_mensagem_viram_controles_na_ordem_de_tab(j):
    _conversa_com_botoes(j)
    assert "com 2 opções (Tab)" not in j.lista_msgs.itens[0]   # botão + opção
    assert "com 2 botões (Tab)" in "".join(j.lista_msgs.itens)
    selecionar(j, "9")
    j._atualizar_botoes()
    assert not any(b.visivel for b in j.botoes_acao)
    selecionar(j, "8")
    j._atualizar_botoes()
    assert [b.label for b in j.botoes_acao if b.visivel] == \
        ["Sim && não", "Particular"]
    assert wx_falso._foco[0] is j.lista_msgs        # nada tirou o foco da lista
    selecionar(j, "9")
    j._atualizar_botoes()
    assert not any(b.visivel for b in j.botoes_acao)


def test_botao_focado_que_some_devolve_o_foco_para_a_lista(j):
    _conversa_com_botoes(j)
    selecionar(j, "8")
    j._atualizar_botoes()
    j.botoes_acao[1].SetFocus()
    selecionar(j, "9")
    j._atualizar_botoes()
    assert wx_falso._foco[0] is j.lista_msgs


def test_tocar_botao_envia_direto_sem_confirmar_e_fala_o_resultado(j):
    _conversa_com_botoes(j)
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    selecionar(j, "8")
    j._atualizar_botoes()
    antes = len(wx_falso.mensagens)
    j._tocar_botao(0)
    assert ("acao", "8", "Sim & não") in j.contas.p.pedidos
    assert len(wx_falso.mensagens) == antes          # nenhuma janela
    assert ditas == []                               # fala so o resultado
    resposta = m.Mensagem("t1", "10", "R1", minha=True, data=AGORA + 50,
                          texto="Sim & não", estado=m.ENVIADA)
    j.b.publicar(ev.MensagemNova(resposta, j.indice[("t1", "10")],
                                 enviada_daqui=True))
    assert ditas == ["Enviado: Sim & não"]
    assert j._acoes_enviadas == []


def test_falha_ao_tocar_botao_fala_o_aviso_e_limpa_a_espera(j):
    _conversa_com_botoes(j)
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    selecionar(j, "8")
    j._atualizar_botoes()
    j._tocar_botao(1)
    assert j._acoes_enviadas == [("t1", "10", "Particular")]
    j.b.publicar(ev.EnvioFalhou("t1", "10", "Particular", "erro do WhatsApp",
                                devolver_texto=False))
    assert ditas == ["Não foi possível enviar: erro do WhatsApp."]
    assert j._acoes_enviadas == [] and j.caixa.GetValue() == ""


def test_detalhes_tambem_envia_o_botao_direto(j, monkeypatch):
    _conversa_com_botoes(j)
    monkeypatch.setattr(jm.wx, "CallAfter", lambda f, *a: f(*a),
                        raising=False)
    chamadas = []
    monkeypatch.setattr(
        jm.dialogos, "mostrar_texto",
        lambda *a, **k: chamadas.append(k) or {"_acao": 0})
    selecionar(j, "8")
    j._detalhes()
    assert chamadas[0]["acoes"] == [("Sim & não", False), ("Particular", True)]
    assert ("acao", "8", "Sim & não") in j.contas.p.pedidos


def test_depurar_mensagem_abre_a_janela_com_o_texto(j, monkeypatch):
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    x = msg("9", "oi", conversa="10")
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [x]))
    chamadas = []
    monkeypatch.setattr(jm.dialogos, "mostrar_depuracao",
                        lambda *a: chamadas.append(a))
    selecionar(j, "9")
    j._depurar_mensagem()
    assert "DEPURAÇÃO DE MENSAGEM" in chamadas[0][2]
    assert "Ligue o Modo de depuração" in chamadas[0][2]


def test_modo_de_depuracao_liga_desliga_e_salva_em_arquivo(j, tmp_path,
                                                           monkeypatch):
    monkeypatch.setenv("TELEZAPP_PASTA_DEPURACAO", str(tmp_path))
    j._modo_depuracao(True)
    assert j.banco.depuracao is True and j.cfg.get("depuracao") is True
    j.banco.guardar_depuracao("t1", "10", "9", "{}")
    j._salvar_depuracao("conteudo de teste")
    arquivos = list(tmp_path.glob("telezapp_depuracao_*.txt"))
    assert len(arquivos) == 1 and \
        arquivos[0].read_text(encoding="utf-8") == "conteudo de teste"
    j._modo_depuracao(False)
    assert j.banco.depuracao is False
    assert j.banco.depuracao_de("t1", "10", "9") == ""


def test_registro_detalhado_do_whatsapp_so_grava_a_opcao(j):
    j._log_detalhado(True)
    assert j.cfg.get("log_detalhado_whatsapp") is True
    j._log_detalhado(False)
    assert j.cfg.get("log_detalhado_whatsapp") is False


# ------------------------------------------------------ anexos e gravacao
def _abrir_com_caixa(j):
    j._abrir_conversa(j.indice[("t1", "20")])
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [msg("5", "oi",
                                                          conversa="20")]))


def test_anexar_arquivo_usa_a_caixa_como_legenda(j, tmp_path, monkeypatch):
    _abrir_com_caixa(j)
    pdf = tmp_path / "relatorio.pdf"
    pdf.write_bytes(b"%PDF")
    monkeypatch.setattr(jm.dialogos, "escolher_arquivo",
                        lambda pai, pasta="": str(pdf))
    j.caixa.SetValue("o relatório")
    j._anexar_arquivo()
    assert ("arquivo", "20", m.DOCUMENTO, "relatorio.pdf",
            "o relatório") in j.contas.p.pedidos
    assert j.caixa.GetValue() == ""
    assert j.cfg.get("pasta_anexos") == str(tmp_path)
    assert "enviando" in j.lista_msgs.itens[-1]

    enviada = m.Mensagem("t1", "20", "7", minha=True, data=AGORA + 50,
                         texto="o relatório", tipo=m.DOCUMENTO,
                         nome_arquivo="relatorio.pdf", tamanho=4,
                         estado=m.ENVIADA)
    j.b.publicar(ev.MensagemNova(enviada, j.indice[("t1", "20")],
                                 enviada_daqui=True))
    assert not any("enviando" in x for x in j.lista_msgs.itens)
    assert not [x for x in j._mensagens_atuais()
                if x.id.startswith("local-")]


def test_anexar_cancelado_nao_envia(j, monkeypatch):
    _abrir_com_caixa(j)
    monkeypatch.setattr(jm.dialogos, "escolher_arquivo",
                        lambda pai, pasta="": None)
    j._anexar_arquivo()
    assert not [p for p in j.contas.p.pedidos if p[0] == "arquivo"]


def test_arquivo_invalido_e_falado(j, tmp_path):
    _abrir_com_caixa(j)
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j._enviar_arquivo(str(tmp_path / "nao-existe.pdf"))
    assert ditas == ["O arquivo não foi encontrado."]
    assert not [p for p in j.contas.p.pedidos if p[0] == "arquivo"]


def test_gravar_envia_nota_de_voz_sem_legenda(j, tmp_path, monkeypatch):
    import os
    from telezapp.midia.gravador import MICROFONE, Gravacao
    _abrir_com_caixa(j)
    ogg = tmp_path / "voz-1.ogg"
    with open(os.path.join(os.path.dirname(__file__), "amostras",
                           "voz.ogg"), "rb") as f:
        ogg.write_bytes(f.read())
    vistos = {}

    def falso(pai, nova, titulo, instrucao, fala):
        vistos["gravador"] = nova()
        vistos["titulo"] = titulo
        return Gravacao(str(ogg), 3.0, -6.0)
    monkeypatch.setattr(jm.dialogos, "gravar_voz", falso)
    j.caixa.SetValue("rascunho que fica")
    j._gravar(MICROFONE)
    assert vistos["gravador"].origem == MICROFONE
    assert vistos["gravador"].pasta == config.pasta_temporaria()
    pedido = [p for p in j.contas.p.pedidos if p[0] == "arquivo"][-1]
    assert pedido[2] == m.VOZ and pedido[4] == ""
    assert j.caixa.GetValue() == "rascunho que fica"


def test_gravar_descartado_nao_envia(j, monkeypatch):
    from telezapp.midia.gravador import SOM_INTERNO
    _abrir_com_caixa(j)
    origens = []
    monkeypatch.setattr(
        jm.dialogos, "gravar_voz",
        lambda pai, nova, *a: origens.append(nova().origem))
    j._gravar(SOM_INTERNO)
    assert origens == [SOM_INTERNO]
    assert not [p for p in j.contas.p.pedidos if p[0] == "arquivo"]


def test_falha_de_midia_marca_so_a_mensagem_local(j, tmp_path):
    _abrir_com_caixa(j)
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF")
    j.caixa.SetValue("texto da caixa")
    j.caixa.Clear()
    j._enviar_arquivo(str(pdf))
    j.caixa.SetValue("outro texto")
    j.b.publicar(ev.EnvioFalhou("t1", "20", "", "sem conexão",
                                devolver_texto=False, tipo=m.DOCUMENTO))
    assert j.lista_msgs.itens[-1].endswith("falhou")
    assert j.caixa.GetValue() == "outro texto"


def test_sem_conexao_nao_anexa(j, monkeypatch):
    _abrir_com_caixa(j)
    j.b.publicar(ev.EstadoConta("t1", ev.DESCONECTADA))
    chamado = []
    monkeypatch.setattr(jm.dialogos, "escolher_arquivo",
                        lambda *a, **k: chamado.append(1))
    j._anexar_arquivo()
    assert not chamado


# ------------------------------------------------- links por Tab
def _com_links(id_, tipo=m.TEXTO, texto="", links=(), botoes=()):
    x = m.Mensagem("t1", "20", id_, autor="Ana", data=AGORA + int(id_),
                   tipo=tipo, texto=texto)
    return m.guardar_extras(x, links=links, botoes=botoes)


def test_links_e_botoes_de_endereco_viram_botoes_na_ordem_do_tab(
        j, monkeypatch):
    j._abrir_conversa(j.indice[("t1", "20")])
    foto = _com_links("5", m.FOTO, "veja https://a.com/x",
                      botoes=[("Site oficial", "https://s.com")])
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [
        _com_links("4", texto="sem nada"), foto]))
    selecionar(j, "5")
    j._atualizar_botoes()
    visiveis = [(b.GetLabel(), b.visivel) for b in j.botoes_link
                if getattr(b, "visivel", False)]
    assert [r for r, _ in visiveis] == ["Link: https://a.com/x",
                                        "Botão: Site oficial"]
    aberto, ditas = [], []
    monkeypatch.setattr(jm.dialogos, "abrir_link",
                        lambda url: aberto.append(url) or True)
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j._abrir_botao_link(1)
    assert aberto == ["https://s.com"] and ditas == ["Abrindo no navegador."]

    selecionar(j, "4")                     # mensagem sem links: somem
    j._atualizar_botoes()
    assert not any(getattr(b, "visivel", False) for b in j.botoes_link)
    j._abrir_botao_link(0)                 # indice sem botao: nada
    assert aberto == ["https://s.com"]


def test_mencoes_viram_botoes_e_abrem_a_conversa(j, monkeypatch):
    j._abrir_conversa(j.indice[("t1", "20")])
    x = m.Mensagem("t1", "20", "6", autor="Ana", data=AGORA + 6, texto="oi @bia")
    m.guardar_extras(x, mencoes=[{"nome": "Bia", "usuario": "bia", "id": "77"}])
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [x]))
    selecionar(j, "6")
    j._atualizar_botoes()
    assert [b.GetLabel() for b in j.botoes_mencao
            if getattr(b, "visivel", False)] == ["Pessoa: Bia, @bia"]
    abertas = []
    monkeypatch.setattr(j, "_abrir_conversa_da_mencao",
                        lambda msg, p: abertas.append(p["id"]))
    j._abrir_botao_mencao(0)
    j._abrir_botao_mencao(3)               # indice sem botao: nada
    assert abertas == ["77"]


def test_link_que_nao_abre_e_avisado(j, monkeypatch):
    j._abrir_conversa(j.indice[("t1", "20")])
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [
        _com_links("5", texto="https://a.com")]))
    selecionar(j, "5")
    j._atualizar_botoes()
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    monkeypatch.setattr(jm.dialogos, "abrir_link", lambda url: False)
    j._abrir_botao_link(0)
    assert ditas == ["Não consegui abrir o link."]


# -------------------------------------------------- velocidade do audio
class MotorComVelocidade:
    def __init__(self):
        self.velocidade = 1.0
        self.terminou = False
        self.tocando = True

    def fechar(self):
        pass


def test_mais_rapido_e_mais_lento_respeitam_o_passo(j):
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    assert j._velocidade() == 1.0
    j._mudar_velocidade(+1)
    assert j.cfg.get("audio_velocidade") == 1.25
    assert ditas[-1] == "Velocidade 1,25x"
    j.cfg.set("audio_passo_velocidade", 0.5)
    j._mudar_velocidade(+1)
    assert j.cfg.get("audio_velocidade") == 1.5
    j.cfg.set("audio_passo_velocidade", 1.0)
    j._mudar_velocidade(+1)
    assert j.cfg.get("audio_velocidade") == 2.0
    j._mudar_velocidade(+1)
    j._mudar_velocidade(+1)             # 3x e o limite
    assert j.cfg.get("audio_velocidade") == 3.0
    j._aplicar_velocidade(1.0)
    assert j._velocidade() == 1.0 and ditas[-1] == "Velocidade 1x"


def test_velocidade_vale_para_o_audio_que_esta_tocando(j):
    motor = MotorComVelocidade()
    j.audio = (("t1", "10", "9"), motor)
    j._mudar_velocidade(+1)
    assert motor.velocidade == 1.25
    j._mudar_velocidade(-1)
    j._mudar_velocidade(-1)
    assert motor.velocidade == 0.75


def test_trocar_o_passo_leva_a_velocidade_ao_valor_permitido(j, monkeypatch):
    j.cfg.set("audio_velocidade", 1.75)

    def escolher(chave):
        j.cfg.set(chave, 1.0)
    monkeypatch.setattr(j, "_escolher_opcao", escolher)
    j._escolher_passo()
    assert j.cfg.get("audio_velocidade") == 2.0     # 1,75 -> 2 (o mais proximo)


def test_configuracoes_aplicam_com_os_efeitos_dos_menus(j):
    j._aplicar_opcao("estilo", 2)
    assert j.estilo == 2 and j.cfg.get("estilo") == 2
    j._aplicar_opcao("midias_baixar", "automatico")
    assert j.cfg.get("midias_baixar") == "automatico"
    j._aplicar_opcao("som", False)
    assert j.cfg.get("som") is False
    j._aplicar_opcao("depuracao", True)
    assert j.banco.depuracao is True
    j._aplicar_opcao("audio_passo_velocidade", 1.0)
    j._aplicar_opcao("audio_velocidade", 1.75)       # nao existe de 1 em 1
    assert j.cfg.get("audio_velocidade") in (1.0, 2.0)


# ------------------------------------------------------ chamadas de voz
class DialogoFalso:
    """Lugar do DialogoChamada: guarda o que a janela pediu para mostrar."""
    abertos = []

    def __init__(self, pai, chamada, acoes, falar, microfones=(),
                 saidas=(), microfone="", saida="", ao_fechar=None):
        self.chamada, self.acoes, self.falar = chamada, acoes, falar
        self.microfones, self.saidas = list(microfones), list(saidas)
        self.ao_fechar = ao_fechar
        self.mostradas = 0
        self.vivo = True
        DialogoFalso.abertos.append(self)

    def Show(self, v=True):
        pass

    def mostrar(self):
        self.mostradas += 1

    def fechar(self):
        self.vivo = False
        if self.ao_fechar:
            self.ao_fechar()


@pytest.fixture
def chamadas(j, monkeypatch):
    from telezapp.nucleo import chamadas as ch
    DialogoFalso.abertos = []
    monkeypatch.setattr(jm, "DialogoChamada", DialogoFalso)
    falas, sons = [], []
    monkeypatch.setattr(j.fala, "falar",
                        lambda t, interromper=False: falas.append(t))
    monkeypatch.setattr(jm, "bipe", lambda tipo="nova": sons.append(tipo))
    p = j.contas.p
    p.suporta_chamadas = True
    p.comandos = []
    p.dispositivos_de_audio = lambda: (["Mic A", "Mic B"], ["Saída A"])
    for nome in ("ligar", "atender_chamada", "silenciar_chamada",
                 "trocar_dispositivos"):
        setattr(p, nome, lambda *a, _n=nome: p.comandos.append((_n,) + a))
    p.encerrar_chamada = lambda cid: p.comandos.append(("encerrar", cid))
    return types.SimpleNamespace(j=j, ch=ch, falas=falas, sons=sons, p=p)


def estado(j, estado, conversa="10", entrante=False, motivo="", erro="",
           nome="Ana"):
    j.b.publicar(ev.EstadoChamada("t1", conversa, estado, nome, entrante,
                                  motivo, erro))


def test_ligar_para_a_conversa_aberta(chamadas):
    j = chamadas.j
    j.atual = ("t1", "10")
    j._ligar()
    assert chamadas.p.comandos == [("ligar", "10", "", "")]


def test_ligar_usa_os_dispositivos_escolhidos(chamadas):
    j = chamadas.j
    j.cfg.set("chamada_microfone", "Mic B")
    j.atual = ("t1", "10")
    j._ligar()
    assert chamadas.p.comandos == [("ligar", "10", "Mic B", "")]


def test_ligar_sem_conversa_avisa(chamadas, monkeypatch):
    j = chamadas.j
    j.atual = None
    monkeypatch.setattr(j, "_conversa_selecionada", lambda: None)
    j._ligar()
    assert any("Abra ou selecione" in f for f in chamadas.falas)
    assert chamadas.p.comandos == []


def test_ligar_para_grupo_nao_pode(chamadas):
    j = chamadas.j
    j.indice[("t1", "10")].tipo = "grupo"
    j.atual = ("t1", "10")
    j._ligar()
    assert any("grupos" in f for f in chamadas.falas)
    assert chamadas.p.comandos == []


def test_ligar_sem_suporte_do_servico(chamadas):
    j = chamadas.j
    chamadas.p.suporta_chamadas = False
    j.atual = ("t1", "10")
    j._ligar()
    assert any("ainda não faz chamadas" in f for f in chamadas.falas)


def test_chamada_recebida_abre_a_janela_toca_e_fala(chamadas):
    j, ch = chamadas.j, chamadas.ch
    estado(j, ch.TOCANDO, entrante=True)
    assert len(DialogoFalso.abertos) == 1
    assert chamadas.falas[-1].startswith("Chamada de Ana")
    assert "toque" in chamadas.sons
    assert j.chamada is not None and j.chamada.entrante


def test_sem_som_de_chamada_so_fala(chamadas):
    j, ch = chamadas.j, chamadas.ch
    j.cfg.set("toque_chamada", False)
    estado(j, ch.TOCANDO, entrante=True)
    assert "toque" not in chamadas.sons
    assert chamadas.falas


def test_atender_pede_ao_provedor_com_os_dispositivos(chamadas):
    j, ch = chamadas.j, chamadas.ch
    j.cfg.set("chamada_saida", "Saída A")
    estado(j, ch.TOCANDO, entrante=True)
    DialogoFalso.abertos[0].acoes["atender"]()
    assert chamadas.p.comandos == [("atender_chamada", "10", "", "Saída A")]


def test_recusar_e_desligar_encerram(chamadas):
    j, ch = chamadas.j, chamadas.ch
    estado(j, ch.TOCANDO, entrante=True)
    DialogoFalso.abertos[0].acoes["recusar"]()
    assert chamadas.p.comandos == [("encerrar", "10")]


def test_em_chamada_silenciar_fala_e_atualiza(chamadas):
    j, ch = chamadas.j, chamadas.ch
    estado(j, ch.CHAMANDO)
    estado(j, ch.EM_CHAMADA)
    assert "conectado" in chamadas.sons
    antes = DialogoFalso.abertos[0].mostradas
    j._alternar_mudo()
    assert chamadas.p.comandos[-1] == ("silenciar_chamada", "10", True)
    assert j.chamada.mudo is True
    assert chamadas.falas[-1] == "Microfone silenciado."
    assert DialogoFalso.abertos[0].mostradas > antes
    j._alternar_mudo()
    assert chamadas.falas[-1] == "Microfone ativado."


def test_mudo_antes_de_conectar_nao_faz_nada(chamadas):
    j, ch = chamadas.j, chamadas.ch
    estado(j, ch.CHAMANDO)
    j._alternar_mudo()
    assert not any(c[0] == "silenciar_chamada" for c in chamadas.p.comandos)
    assert any("durante" in f for f in chamadas.falas)


def test_tempo_da_chamada_e_falado(chamadas):
    j, ch = chamadas.j, chamadas.ch
    estado(j, ch.CHAMANDO)
    estado(j, ch.EM_CHAMADA)
    j.chamada.inicio_conexao = j.chamada._agora() - 125
    j._falar_tempo_da_chamada()
    assert chamadas.falas[-1] == "Em chamada há 2 minutos e 5 segundos."


def test_encerrada_mostra_motivo_e_libera_a_janela(chamadas):
    j, ch = chamadas.j, chamadas.ch
    estado(j, ch.CHAMANDO)
    estado(j, ch.ENCERRADA, motivo=ch.SEM_RESPOSTA)
    assert chamadas.falas[-1] == "Ana não atendeu."
    assert j.chamada is None
    assert "desligada" in chamadas.sons
    j._desligar_chamada()          # nada a desligar: so avisa
    assert chamadas.falas[-1] == "Nenhuma chamada em andamento."


def test_nova_chamada_depois_de_encerrada_abre_outra_janela(chamadas):
    j, ch = chamadas.j, chamadas.ch
    estado(j, ch.CHAMANDO)
    estado(j, ch.ENCERRADA, motivo=ch.CANCELADA)
    primeiro = DialogoFalso.abertos[0]
    estado(j, ch.TOCANDO, entrante=True)
    assert len(DialogoFalso.abertos) == 2
    assert primeiro.vivo is False


def test_fim_de_chamada_desconhecida_e_ignorado(chamadas):
    j, ch = chamadas.j, chamadas.ch
    estado(j, ch.ENCERRADA, motivo=ch.DESLIGADA)
    assert DialogoFalso.abertos == [] and chamadas.falas == []


def test_trocar_dispositivo_guarda_e_pede_ao_provedor(chamadas):
    j, ch = chamadas.j, chamadas.ch
    estado(j, ch.CHAMANDO)
    estado(j, ch.EM_CHAMADA)
    DialogoFalso.abertos[0].acoes["trocar"]("Mic B", "Saída A")
    assert j.cfg.get("chamada_microfone") == "Mic B"
    assert j.cfg.get("chamada_saida") == "Saída A"
    assert chamadas.p.comandos[-1] == (
        "trocar_dispositivos", "10", "Mic B", "Saída A")


def test_fechar_a_janela_com_chamada_pergunta(chamadas, monkeypatch):
    j, ch = chamadas.j, chamadas.ch
    estado(j, ch.CHAMANDO)
    estado(j, ch.EM_CHAMADA)
    parou = []
    j.contas.parar_todos = lambda: parou.append(True)
    wx_falso.resposta_messagebox[0] = wx_falso.NO
    j._ao_fechar(types.SimpleNamespace(Veto=lambda: parou.append("veto")))
    assert parou == ["veto"]


# ----------------------------------------- reacoes, edicoes e apagadas
def _atualizada(j, motivo, minha=True, emoji="👍", quem="Bruno",
                texto="bom dia"):
    x = msg("5", texto, minha=minha)
    j.b.publicar(ev.MensagemAtualizada("t1", "10", x, motivo, quem, emoji))
    return x


def test_reacao_a_minha_mensagem_e_falada(j, monkeypatch):
    falas = []
    monkeypatch.setattr(j.fala, "falar",
                        lambda t, interromper=False: falas.append(t))
    _atualizada(j, "reacao")
    assert falas == ["Bruno reagiu com 👍 à sua mensagem: bom dia"]


def test_reacao_pode_ser_desligada_nas_opcoes(j, monkeypatch):
    falas = []
    monkeypatch.setattr(j.fala, "falar",
                        lambda t, interromper=False: falas.append(t))
    j.cfg.set("falar_reacoes", False)
    _atualizada(j, "reacao")
    assert falas == []


def test_reacao_a_mensagem_de_outro_nao_e_falada(j, monkeypatch):
    falas = []
    monkeypatch.setattr(j.fala, "falar",
                        lambda t, interromper=False: falas.append(t))
    _atualizada(j, "reacao", minha=False)
    assert falas == []


def test_edicao_atualiza_o_cache_e_a_lista_da_conversa_aberta(j,
                                                              monkeypatch):
    falas = []
    monkeypatch.setattr(j.fala, "falar",
                        lambda t, interromper=False: falas.append(t))
    j._abrir_conversa(j.indice[("t1", "20")])
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [
        msg("4", "antes", conversa="20"),
        msg("5", "oi", minha=False, conversa="20")]))
    nova = msg("5", "oi, tudo bem?", minha=False, conversa="20")
    m.atualizar_extras(nova, editada=True)
    j.b.publicar(ev.MensagemAtualizada("t1", "20", nova, "editada"))
    assert j.cache[("t1", "20")][-1].texto == "oi, tudo bem?"
    assert any("(editada)" in t for t in j.lista_msgs.itens)
    assert falas[-1] == "Ana editou uma mensagem."


# --------------------------------------- o leitor de tela e informado
def test_anuncio_de_voz_diz_quem_enviou_e_quanto_dura():
    x = m.Mensagem("t1", "10", "1", autor="Ana", tipo=m.VOZ, segundos=12)
    assert m.anuncio_reproducao(x) == \
        "Tocando mensagem de voz de Ana, 12 segundos."
    assert m.anuncio_reproducao(x, "1,5x") == \
        "Tocando mensagem de voz de Ana, 12 segundos, a 1,5x."
    assert m.anuncio_reproducao(x, proximo=True).startswith(
        "Próximo áudio. Tocando mensagem de voz de Ana")
    minha = m.Mensagem("t1", "10", "2", minha=True, tipo=m.VOZ)
    assert m.anuncio_reproducao(minha) == "Tocando sua mensagem de voz."
    audio = m.Mensagem("t1", "10", "3", autor="Bruno", tipo=m.AUDIO,
                       segundos=75)
    assert m.anuncio_reproducao(audio) == \
        "Tocando áudio de Bruno, 1 minuto e 15 segundos."


def test_tocar_voz_sem_janela_fala_quem_enviou(jm_midia, monkeypatch):
    j = jm_midia
    falas = []
    monkeypatch.setattr(j.fala, "falar",
                        lambda t, interromper=False: falas.append(t))
    _preparar_sequencia(j, monkeypatch)
    assert falas[-1] == "Tocando mensagem de voz de Ana."


def test_sequencia_anuncia_o_proximo_numa_fala_so(jm_midia, monkeypatch):
    """Falar 'Próximo áudio' e depois 'Tocando' em duas falas fazia a
    segunda cortar a primeira, e a pessoa nao ouvia de quem era."""
    j = jm_midia
    falas = []
    monkeypatch.setattr(j.fala, "falar",
                        lambda t, interromper=False: falas.append(t))
    primeiro = _preparar_sequencia(j, monkeypatch)
    primeiro.terminou = True
    j._vigiar_audio(primeiro)
    assert falas[-1] == "Próximo áudio. Tocando mensagem de voz de Ana."
    assert falas.count("Próximo áudio") == 0


def test_voz_tocada_passa_a_dizer_ouvida_na_lista_e_fica_guardada(
        jm_midia, monkeypatch):
    j = jm_midia
    MotorFalso.criados = []
    monkeypatch.setattr(jm, "Reprodutor", MotorFalso)
    monkeypatch.setattr(jm.wx, "CallLater", lambda *a, **k: None,
                        raising=False)
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [voz("5")]))
    j.midias.prontas[("t1", "10", "5")] = "/p/5.ogg"
    antes = [t for t in j.lista_msgs.itens if "mensagem de voz" in t]
    assert antes and "ouvida" not in antes[0]
    selecionar(j, "5")
    j._char_hook(Tecla(wx_falso.WXK_RETURN))        # toca
    depois = [t for t in j.lista_msgs.itens if "mensagem de voz" in t]
    assert "ouvida" in depois[0]
    guardada = j.banco.mensagem("t1", "10", "5")
    assert m.extras_de(guardada)["ouvida"] is True
    # tocar de novo nao reescreve nada nem muda a linha
    esta = [x for x in j.cache[("t1", "10")] if x.id == "5"][0]
    j._marcar_ouvida(esta)
    assert m.conteudo(esta).count("ouvida") == 1


def _preparar_bloco(j, monkeypatch):
    """3 audios, um texto e mais 2 audios."""
    MotorFalso.criados = []
    monkeypatch.setattr(jm, "Reprodutor", MotorFalso)
    monkeypatch.setattr(jm.wx, "CallLater", lambda *a, **k: None,
                        raising=False)
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [
        voz("1"), voz("2"), voz("3"), msg("4", "texto"), voz("5"),
        voz("6")]))
    for i in "123456":
        j.midias.prontas[("t1", "10", i)] = "/p/%s.ogg" % i
    selecionar(j, "1")
    j._char_hook(Tecla(wx_falso.WXK_RETURN))


def _terminar_o_atual(j):
    motor = j.audio[1]
    motor.terminou = True
    j._vigiar_audio(motor)


def test_sequencia_em_bloco_para_na_primeira_que_nao_e_audio(jm_midia,
                                                            monkeypatch):
    j = jm_midia
    j.cfg.set("audio_sequencia", "bloco")
    _preparar_bloco(j, monkeypatch)
    for _ in range(2):
        _terminar_o_atual(j)                    # toca o 2 e o 3
    assert [c.caminho for c in MotorFalso.criados] == [
        "/p/1.ogg", "/p/2.ogg", "/p/3.ogg"]
    _terminar_o_atual(j)                        # depois do 3 vem o texto
    assert len(MotorFalso.criados) == 3 and j.audio is None


def test_sequencia_total_pula_o_texto_e_toca_o_resto(jm_midia, monkeypatch):
    j = jm_midia
    j.cfg.set("audio_sequencia", "sim")
    _preparar_bloco(j, monkeypatch)
    for _ in range(5):
        if j.audio is not None:
            _terminar_o_atual(j)
    assert [c.caminho for c in MotorFalso.criados] == [
        "/p/%s.ogg" % i for i in "12356"]       # o 4 e texto


def test_o_modo_bloco_esta_nas_escolhas_da_opcao():
    opcao = next(o for o in config.OPCOES if o.chave == "audio_sequencia")
    assert [v for v, _ in opcao.escolhas] == ["sim", "bloco", "nao"]


def test_anuncio_de_quem_toca_e_opcional(jm_midia, monkeypatch):
    j = jm_midia
    falas = []
    monkeypatch.setattr(j.fala, "falar",
                        lambda t, interromper=False: falas.append(t))
    j.cfg.set("falar_quem_toca", False)
    _preparar_sequencia(j, monkeypatch)
    assert falas[-1] == "Tocando."
    # na sequencia valem as opcoes proprias dela, nao esta
    primeiro = MotorFalso.criados[0]
    primeiro.terminou = True
    j._vigiar_audio(primeiro)
    assert falas[-1] == "Próximo áudio. Tocando mensagem de voz de Ana."


def test_o_que_falar_na_sequencia_e_configuravel(jm_midia, monkeypatch):
    j = jm_midia
    falas = []
    monkeypatch.setattr(j.fala, "falar",
                        lambda t, interromper=False: falas.append(t))
    for chave in ("seq_falar_tipo", "seq_falar_duracao"):
        j.cfg.set(chave, False)
    _preparar_sequencia(j, monkeypatch)
    primeiro = MotorFalso.criados[0]
    primeiro.terminou = True
    j._vigiar_audio(primeiro)
    assert falas[-1] == "Próximo áudio. De Ana."


def test_opcoes_de_fala_estao_no_menu_exibicao(j):
    for chave in ("falar_quem_toca", "falar_reacoes"):
        assert chave in j.itens
        assert j.itens[chave].IsChecked() if hasattr(
            j.itens[chave], "IsChecked") else True
    j._aplicar_opcao("falar_quem_toca", False)
    assert j.cfg.get("falar_quem_toca") is False


# ------------------------------------------------------------ contatos
def test_contato_da_agenda_renomeia_conversa_privada(j):
    j.banco.salvar_contato("t1", "10", "Aninha", "")
    j._renomear_pelos_contatos()
    assert j.lista_conv.itens[0].startswith("Aninha")
    j.b.publicar(ev.ConversasAtualizadas("t1", [
        conv("10", "Ana", data=AGORA), conv("20", "Bruno")]))
    assert j.lista_conv.itens[0].startswith("Aninha")   # o nome do servico
    j.banco.remover_contato("t1", "10")                  # nao volta a valer
    assert j.banco.nome_de_contato("t1", "10") == ""


def test_salvar_pessoa_da_conversa(j, monkeypatch):
    from telezapp.interface import contatos
    j.lista_conv.SetSelection(1)
    monkeypatch.setattr(contatos, "dialogo_salvar_pessoa",
                        lambda pai, contas, nome, tel="": ("Bruno S.", "+5551999998888"))
    j._salvar_pessoa()
    assert j.banco.contatos("t1") == [("t1", "20", "Bruno S.",
                                       "+5551999998888")]
    assert j.lista_conv.itens[0].startswith("Ana") or \
        any(i.startswith("Bruno S.") for i in j.lista_conv.itens)


def test_limite_de_mensagens_por_conversa(j):
    j.cfg.set("mensagens_por_conversa", 50)
    assert j._limite_memoria() == 50
    msgs = [m.Mensagem("t1", "10", str(i), autor="Ana", data=AGORA + i,
                       texto="m%d" % i) for i in range(1, 121)]
    assert len(j._mesclar(("t1", "10"), msgs)) == 50
    j._aplicar_opcao("mensagens_por_conversa", 60)
    assert len(j.cache[("t1", "10")]) == 50    # nada a cortar: ja tinha 50
    j._aplicar_opcao("mensagens_por_conversa", 50)
    j.cfg.set("mensagens_por_conversa", "lixo")
    assert j._limite_memoria() == 1200


# -------------------------------------------------------------- filtros
def _tres(j):
    j.b.publicar(ev.ConversasAtualizadas("t1", [
        conv("10", "Ana", nao_lidas=2, data=AGORA - 10),
        conv("20", "Bruno", data=AGORA - 100),
        m.Conversa("t1", "30", "Família", "telegram", "grupo",
                   data=AGORA - 200),
        m.Conversa("t1", "40", "Velha", "telegram", "privada",
                   data=AGORA - 300, arquivada=True)]))


def _nomes(j):
    return [i.split(",")[0] for i in j.lista_conv.itens]


def _tipo(j, valor):
    j.cx_tipo.SetSelection([v for v, _ in m.FILTROS_TIPO].index(valor))
    j._ao_filtro_tipo()


def test_filtro_por_tipo_e_arquivadas(j):
    _tres(j)
    assert _nomes(j) == ["Ana", "Bruno", "Família"]    # arquivada fica fora
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    _tipo(j, "grupos")
    assert _nomes(j) == ["Família"]
    assert ditas[-1] == "Grupos, Todas as contas. 1 conversa"
    _tipo(j, "nao_lidas")
    assert _nomes(j) == ["Ana"]
    _tipo(j, "pessoais")
    assert _nomes(j) == ["Ana", "Bruno"]
    _tipo(j, "arquivadas")
    assert _nomes(j) == ["Velha"]
    _tipo(j, "canais")
    assert j.lista_conv.itens == ["Nenhuma conversa neste filtro."]
    assert j.cfg.get("filtro_conversas") == "canais"
    _tipo(j, "todas")
    assert len(j.lista_conv.itens) == 3


def test_caixa_de_contas_e_filtro_por_servico_e_conta(j):
    # uma conta so do Telegram: Todas as contas e Telegram
    assert j.cx_conta.itens == ["Todas as contas", "Telegram"]
    j.cfg.salvar_conta({"id": "t2", "servico": "telegram", "nome": "Outra"})
    j.cfg.salvar_conta({"id": "w1", "servico": "whatsapp", "nome": "Zap"})
    j.b.publicar(ev.ConversasAtualizadas("w1", [
        m.Conversa("w1", "5@s.whatsapp.net", "Cris", "whatsapp",
                   data=AGORA)]))
    # com duas contas do Telegram, cada uma aparece depois do servico
    assert j.cx_conta.itens == ["Todas as contas", "Telegram",
                                "Fábio, Telegram", "Outra, Telegram",
                                "WhatsApp"]
    j.cx_conta.SetSelection(4)
    j._ao_filtro_conta()
    assert _nomes(j) == ["Cris"]
    j.cx_conta.SetSelection(2)
    j._ao_filtro_conta()
    assert "Cris" not in _nomes(j) and "Ana" in _nomes(j)
    assert j.cfg.get("filtro_conta") == "conta:t1"


def test_conversa_aberta_fica_na_lista_com_filtro(j):
    j._abrir_conversa(j.indice[("t1", "20")])
    _tipo(j, "nao_lidas")
    assert _nomes(j) == ["Ana", "Bruno"]


def test_arquivar_e_desarquivar_conversa(j):
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j.lista_conv.SetSelection(0)                  # Ana
    j._arquivar_conversa()
    assert ("arquivar", "10", True) in j.contas.p.pedidos
    assert ditas[-1] == "Conversa arquivada."
    assert "Ana" not in _nomes(j)
    assert j.banco.conversas("t1")[0].arquivada or any(
        c.arquivada for c in j.banco.conversas("t1"))
    _tipo(j, "arquivadas")
    assert _nomes(j) == ["Ana"]
    j.lista_conv.SetSelection(0)
    j._arquivar_conversa()                        # de volta
    assert ditas[-1] == "Conversa desarquivada."
    assert j.lista_conv.itens == ["Nenhuma conversa neste filtro."]
    j._arquivar_conversa()                        # sem conversa na lista
    assert ditas[-1] == "Nenhuma conversa selecionada."


# ------------------------------------------- busca e trancadas com codigo
def _com_trancada(j, codigo="2468"):
    from telezapp.nucleo import codigo_secreto
    if codigo:
        j.cfg.set("codigo_trancadas", codigo_secreto.criar(codigo))
    j.b.publicar(ev.ConversasAtualizadas("t1", [
        conv("10", "Ana", data=AGORA - 10),
        conv("20", "Bruno", data=AGORA - 100),
        m.Conversa("t1", "50", "Segredo", "telegram", "privada",
                   data=AGORA - 20, trancada=True)]))


def _digitar(j, texto):
    j.campo_busca.SetValue(texto)
    j._ao_busca()


def test_busca_de_conversas_por_nome_sem_acento(j):
    _com_trancada(j)
    _digitar(j, "BRUN")
    assert _nomes(j) == ["Bruno"]
    _digitar(j, "")
    assert _nomes(j) == ["Ana", "Bruno"]


def test_trancadas_so_com_o_codigo_secreto(j):
    _com_trancada(j)
    assert _nomes(j) == ["Ana", "Bruno"]            # escondida
    assert [v for v, _ in j._tipos_atuais][-1] == "arquivadas"
    _digitar(j, "1111")                              # codigo errado: busca
    assert not j.trancadas_liberadas
    assert j.lista_conv.itens == ["Nenhuma conversa neste filtro."]
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    _digitar(j, "2468")
    assert j.trancadas_liberadas
    assert j.campo_busca.GetValue() == ""            # o codigo some da tela
    assert [v for v, _ in j._tipos_atuais][-1] == "trancadas"
    assert j.filtro_tipo == "trancadas" and _nomes(j) == ["Segredo"]
    assert ditas[-1].startswith("Conversas trancadas liberadas.")
    _tipo(j, "todas")                     # trocar de filtro esconde de novo
    assert not j.trancadas_liberadas
    assert "trancadas" not in dict(j._tipos_atuais)
    assert _nomes(j) == ["Ana", "Bruno"]
    _digitar(j, "2468")                   # so voltam com o codigo
    assert j.trancadas_liberadas and j.filtro_tipo == "trancadas"
    j._esconder_trancadas()
    assert not j.trancadas_liberadas and j.filtro_tipo == "todas"
    assert _nomes(j) == ["Ana", "Bruno"]
    assert "trancadas" not in dict(j._tipos_atuais)
    assert j.cfg.get("filtro_conversas") != "trancadas"


def test_trancadas_sem_codigo_definido_ficam_escondidas(j):
    _com_trancada(j, codigo=None)
    _digitar(j, "2468")
    assert not j.trancadas_liberadas
    assert "trancadas" not in dict(j._tipos_atuais)


def test_opcao_desligada_mostra_trancadas_sempre(j):
    _com_trancada(j, codigo=None)
    j._aplicar_opcao("trancadas_exigir_codigo", False)
    assert "trancadas" in dict(j._tipos_atuais)
    _tipo(j, "trancadas")
    assert _nomes(j) == ["Segredo"]
    assert j.cfg.get("filtro_conversas") == "trancadas"
    j._aplicar_opcao("trancadas_exigir_codigo", True)   # volta a esconder
    assert j.filtro_tipo == "todas" and "trancadas" not in dict(j._tipos_atuais)


def test_arquivada_e_trancada_nao_avisam_mensagem_nova(j):
    _com_trancada(j)
    j.indice[("t1", "20")].arquivada = True
    ditas, bipes = [], []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    monkey = __import__("telezapp.interface.janela", fromlist=["bipe"])
    antigo = monkey.bipe
    monkey.bipe = lambda *a, **k: bipes.append(a)
    try:
        for cid in ("50", "20"):                 # trancada e arquivada
            msg = m.Mensagem("t1", cid, "9", autor="Eu sei", data=AGORA,
                             texto="conteudo reservado")
            j.b.publicar(ev.MensagemNova(msg, j.indice[("t1", cid)]))
        assert ditas == [] and bipes == []
        msg = m.Mensagem("t1", "10", "9", autor="Ana", data=AGORA, texto="oi")
        j.b.publicar(ev.MensagemNova(msg, j.indice[("t1", "10")]))
        assert ditas and bipes                   # conversa comum avisa
    finally:
        monkey.bipe = antigo



def test_aplicar_codigo_vindo_das_configuracoes_e_novo_pareamento_apaga(j):
    from telezapp.nucleo import codigo_secreto
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j._aplicar_opcao("codigo_trancadas", "2468")
    assert codigo_secreto.confere("2468", j.cfg.get("codigo_trancadas"))
    assert ditas[-1] == "Código secreto salvo."
    j._limpar_codigo_trancadas()                  # novo pareamento
    assert j.cfg.get("codigo_trancadas") is None
    assert "Defina um novo" in ditas[-1]
    j._aplicar_opcao("codigo_trancadas", None)    # desligar: ja sem codigo
    assert j.cfg.get("codigo_trancadas") is None


def test_ativar_ou_desativar_contas_pelo_menu(j, monkeypatch):
    chamadas = []
    j.contas.ativar = lambda cid: chamadas.append(("ativar", cid)) or True
    j.contas.desativar = lambda cid: chamadas.append(("desativar", cid)) or True
    j.cfg.salvar_conta({"id": "t1", "servico": "telegram", "nome": "Fábio"})

    class Dlg(wx_falso.MultiChoiceDialog):
        def ShowModal(self):
            self.novas = []                    # desmarca tudo
            return wx_falso.ID_OK
    monkeypatch.setattr(jm.wx, "MultiChoiceDialog", Dlg, raising=False)
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j._ativar_contas()
    assert chamadas == [("desativar", "t1")]
    assert ditas[-1] == "Contas: 1 desativada."


def test_fim_da_sequencia_so_se_pedido_e_com_mais_de_um_audio(jm_midia,
                                                              monkeypatch):
    j = jm_midia
    falas = []
    monkeypatch.setattr(j.fala, "falar",
                        lambda t, interromper=False: falas.append(t))
    j.cfg.set("seq_falar_fim", True)
    primeiro = _preparar_sequencia(j, monkeypatch)
    primeiro.terminou = True
    j._vigiar_audio(primeiro)                    # toca o segundo audio
    segundo = MotorFalso.criados[1]
    segundo.terminou = True
    j._vigiar_audio(segundo)                     # nao ha mais: fim
    assert falas[-1] == "Fim da sequência."
    j._fim_da_sequencia()                        # ja avisou: nao repete
    assert falas.count("Fim da sequência.") == 1


def test_fim_da_sequencia_desligado_ou_audio_sozinho_nao_fala(jm_midia,
                                                              monkeypatch):
    j = jm_midia
    falas = []
    monkeypatch.setattr(j.fala, "falar",
                        lambda t, interromper=False: falas.append(t))
    primeiro = _preparar_sequencia(j, monkeypatch)
    primeiro.terminou = True
    j._vigiar_audio(primeiro)
    MotorFalso.criados[1].terminou = True
    j._vigiar_audio(MotorFalso.criados[1])       # opcao desligada (padrao)
    assert "Fim da sequência." not in falas
    j.cfg.set("seq_falar_fim", True)
    j._seq_tocados = 0                           # so um audio tocou
    j._fim_da_sequencia()
    assert "Fim da sequência." not in falas


def test_aplicar_privacidade_do_whatsapp_confere_pela_releitura(j):
    class Prov:
        def __init__(self, aceita):
            self.aceita, self.valores = aceita, {
                "last": "all", "online": "all", "status": "all",
                "readreceipts": "all", "groupadd": "all"}
            self.feitas = []

        def definir_privacidade(self, campo, valor):
            self.feitas.append((campo, valor))
            if self.aceita:
                self.valores[campo] = valor

        def privacidade(self):
            return dict(self.valores)
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j.contas.provedores["w9"] = Prov(True)
    j._aplicar_opcao("privacidade_conta",
                     [("w9", "last", "none"), ("w9", "online", "all")])
    assert j.contas.provedores["w9"].feitas == [("last", "none"),
                                                ("online", "all")]
    assert ditas[-1] == "Privacidade: 2 mudanças salvas."
    j.contas.provedores["w8"] = Prov(False)      # aceita mas nao grava
    j._aplicar_opcao("privacidade_conta", [("w8", "readreceipts", "none")])
    assert ditas[-1].startswith("O serviço não confirmou: confirmação de leitura")


# ------------------------------------------------------- nova mensagem
def test_nova_mensagem_escolhe_conta_e_envia(j, monkeypatch):
    from telezapp.interface import contatos
    vistas = []
    monkeypatch.setattr(contatos, "dialogo_nova_mensagem",
                        lambda pai, contas, buscar: vistas.append(contas) or
                        ("t1", "bruno", "oi, tudo bem?", None))
    enviados = []
    j._enviar_texto = lambda: enviados.append((j.atual, j.caixa.GetValue()))
    j._nova_mensagem()
    assert [c for c, _ in vistas[0]] == ["t1"]           # so a conectada
    assert enviados == [(("t1", "20"), "oi, tudo bem?")]  # Bruno ja existia
    assert j.atual == ("t1", "20")


def test_nova_mensagem_para_telefone_cria_conversa_no_whatsapp(j, monkeypatch):
    from telezapp.interface import contatos
    j.cfg.salvar_conta({"id": "w1", "servico": "whatsapp", "nome": "Zap"})

    class Zap:
        def id_do_telefone(self, tel):
            return tel.lstrip("+") + "@s.whatsapp.net"
        pedidos = []

        def carregar_mensagens(self, *a, **k):
            pass

        def marcar_como_lida(self, *a):
            pass
    j.contas.provedores["w1"] = Zap()
    j.contas.provedor = lambda cid: j.contas.provedores.get(cid)
    j.b.publicar(ev.EstadoConta("w1", ev.CONECTADA))
    vistas = []
    monkeypatch.setattr(contatos, "dialogo_nova_mensagem",
                        lambda pai, contas, buscar: vistas.append(contas) or
                        ("w1", "(51) 99999-8888", "oi", None))
    enviados = []
    j._enviar_texto = lambda: enviados.append(j.atual)
    j._nova_mensagem()
    assert len(vistas[0]) == 2                  # duas contas: aparece a escolha
    assert enviados == [("w1", "5551999998888@s.whatsapp.net")]
    assert ("w1", "5551999998888@s.whatsapp.net") in j.indice


def test_nova_mensagem_sem_conta_conectada_ou_destino_desconhecido(j,
                                                                     monkeypatch):
    from telezapp.interface import contatos
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j.estados["t1"] = ev.DESCONECTADA
    j._nova_mensagem()
    assert ditas[-1] == "Nenhuma conta conectada para enviar."
    j.estados["t1"] = ev.CONECTADA
    monkeypatch.setattr(contatos, "dialogo_nova_mensagem",
                        lambda pai, contas, buscar: ("t1", "ninguem assim", "oi", None))
    j._nova_mensagem()
    assert ditas[-1].startswith("Não encontrei ninguem assim.")


def test_nova_mensagem_com_pessoa_escolhida_na_lista_nao_resolve_o_texto(
        j, monkeypatch):
    from telezapp.interface import contatos
    monkeypatch.setattr(contatos, "dialogo_nova_mensagem",
                        lambda pai, contas, buscar: (
                            "t1", "br", "oi", ("20", "Bruno")))
    enviados = []
    j._enviar_texto = lambda: enviados.append(j.atual)
    j._resolver_destino = lambda *a: (_ for _ in ()).throw(AssertionError)
    j._nova_mensagem()
    assert enviados == [("t1", "20")]


def test_mensagem_apagada_no_celular_some_da_lista_e_nao_volta(j):
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [
        msg("1", "a", conversa="10"), msg("2", "b", conversa="10"),
        msg("3", "c", conversa="10")]))
    assert "2" in j.mapa
    j.b.publicar(ev.MensagemApagadaNoCelular("t1", "10", "2"))
    assert "2" not in j.mapa and "1" in j.mapa and "3" in j.mapa
    # a mesma mensagem chegando de novo (historico) nao volta
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [
        msg("2", "b", conversa="10")]))
    assert "2" not in j.mapa


def test_apagar_mensagem_aqui_pergunta_e_avisa_a_conta(j):
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [
        msg("1", "a", conversa="10"), msg("2", "b", conversa="10")]))
    selecionar(j, "2")
    wx_falso.resposta_messagebox[0] = wx_falso.NO
    j._apagar_mensagem()
    assert "2" in j.mapa                          # disse nao: nada muda
    wx_falso.resposta_messagebox[0] = wx_falso.YES
    try:
        j._apagar_mensagem()
    finally:
        wx_falso.resposta_messagebox[0] = wx_falso.NO
    assert "2" not in j.mapa
    assert j.banco.foi_limpa("t1", "10", "2") == "mensagem"

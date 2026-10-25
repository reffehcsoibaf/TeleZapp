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

    def observar_presenca(self, cid):
        self.pedidos.append(("observar", cid))

    def responder_status(self, x, texto):
        self.pedidos.append(("status", x.id, texto))

    def parar_presenca(self, cid):
        self.pedidos.append(("parar_presenca", cid))

    def enviar_texto(self, cid, texto, resposta_a="", mencoes=None):
        self.pedidos.append(("enviar", cid, texto, resposta_a))
        if mencoes:
            self.pedidos.append(("mencoes", cid, mencoes))

    def enviar_arquivo(self, cid, anexo, legenda="", resposta_a="",
                       mencoes=None):
        self.pedidos.append(("arquivo", cid, anexo.tipo, anexo.nome,
                             legenda))
        if resposta_a or mencoes:
            self.pedidos.append(("arquivo_com", cid, resposta_a, mencoes))

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

    def reiniciar_pareamento(self, conta_id):
        self.reiniciadas = getattr(self, "reiniciadas", []) + [conta_id]
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
    def __init__(self, codigo, shift=False, ctrl=False):
        self.codigo, self.shift, self.pulou = codigo, shift, False
        self.ctrl = ctrl

    def GetKeyCode(self):
        return self.codigo

    def AltDown(self):
        return False

    def ControlDown(self):
        return self.ctrl

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
    for chave in ("falar_novas", "falar_novas_outras_conversas",
                  "falar_novas_fora_do_telezapp", "confirmar_envio",
                  "falar_reacoes"):
        cfg.set(chave, True)
    banco = Banco(str(tmp_path / "t.db"))
    b = ev.Barramento()
    cfg.set("enter_envia", True)      # os testes antigos enviam com o Enter
    janela = jm.Janela(cfg, banco, b)
    janela.contas = ContasFalsas()
    janela.comecar()
    janela.lista_conv.SetFocus()      # o foco inicial e a caixa de conta
    # no wx de verdade o Enter que a janela deixa passar chega a caixa, que
    # envia pelo EVT_TEXT_ENTER; o falso faz o mesmo aqui
    char_hook = janela._char_hook

    def char_hook_com_caixa(evt):
        char_hook(evt)
        if evt.pulou and evt.GetKeyCode() == wx_falso.WXK_RETURN and \
                janela.FindFocus() is janela.caixa and not (
                    evt.ShiftDown() or evt.ControlDown()):
            janela.caixa.ligacoes[wx_falso.EVT_TEXT_ENTER](None)
    janela._char_hook = char_hook_com_caixa
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
    # a tela comeca com os dois botoes; nada de QR em tela cheia ainda
    assert dlg.mostrado and dlg.pagina == "inicio"
    assert dlg.painel_inicio.visivel and not dlg.painel_codigo.visivel
    assert wx_falso._foco[0] is dlg.botao_telefone
    j.b.publicar(ev.QrPareamento("w-nova", "2@qr0"))
    assert dlg.tela_cheia is None
    dlg._ir_para("codigo")
    assert wx_falso._foco[0] is dlg.telefone
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


def test_excluir_conta(j):
    wx_falso.resposta_messagebox[0] = wx_falso.YES
    try:
        assert j._excluir_conta_id("t1") is True
    finally:
        wx_falso.resposta_messagebox[0] = wx_falso.NO
    assert j.contas.removida == "t1"
    assert j.lista_conv.itens == [jm.TEXTO_SEM_CONTAS]


def test_excluir_conta_pede_confirmacao(j):
    wx_falso.resposta_messagebox[0] = wx_falso.NO
    assert j._excluir_conta_id("t1") is False
    assert getattr(j.contas, "removida", None) is None
    assert j._excluir_conta_id("nao-existe") is False


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


def test_lista_de_conversas_abre_no_topo_com_o_foco(j):
    # nao lembra qual conversa estava selecionada: sempre o topo da lista
    j.lista_conv.SetSelection(1)
    j.cx_conta.SetFocus()
    j.comecar()
    assert j.lista_conv.GetSelection() == 0
    assert j.lista_conv.HasFocus()


def test_botao_sair_depois_da_busca_fecha_a_janela(j):
    assert j.botao_sair.GetLabel() == "Sair (Ctrl+Q)"
    fechou = []
    j.Close = lambda *a, **k: fechou.append(True) or True
    j.botao_sair.ligacoes[jm.wx.EVT_BUTTON](None)
    assert fechou == [True]


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


def test_anexar_pelo_botao_envia_foto_e_audio_como_documento(
        j, tmp_path, monkeypatch):
    _abrir_com_caixa(j)
    for nome in ("foto.jpg", "som.mp3"):
        arq = tmp_path / nome
        arq.write_bytes(b"x" * 10)
        monkeypatch.setattr(jm.dialogos, "escolher_arquivo",
                            lambda pai, pasta="", a=str(arq): a)
        j._anexar_arquivo()
        assert ("arquivo", "20", m.DOCUMENTO, nome, "") in \
            j.contas.p.pedidos


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

    def falso(pai, nova, titulo, instrucao, fala, microfone=None):
        vistos["gravador"] = nova()
        vistos["microfone"] = microfone
        vistos["titulo"] = titulo
        return Gravacao(str(ogg), 3.0, -6.0)
    monkeypatch.setattr(jm.dialogos, "gravar_voz", falso)
    j.caixa.SetValue("rascunho que fica")
    j._gravar(MICROFONE)
    assert vistos["gravador"].origem == MICROFONE
    assert vistos["microfone"] is None      # sem caixa de microfone
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
        lambda pai, nova, *a, microfone=None: origens.append(
            (nova().origem, microfone)))
    j._gravar(SOM_INTERNO)
    # a janela do som do computador grava o som com o microfone (a caixa
    # ja vem marcada, pela opcao) e deixa ligar e desligar o microfone
    assert origens == [("som_e_microfone", True)]
    assert not [p for p in j.contas.p.pedidos if p[0] == "arquivo"]


def test_janela_do_som_respeita_a_opcao_do_microfone(j, monkeypatch):
    from telezapp.midia.gravador import SOM_INTERNO
    _abrir_com_caixa(j)
    vistos = []
    monkeypatch.setattr(
        jm.dialogos, "gravar_voz",
        lambda pai, nova, *a, microfone=None: vistos.append(microfone))
    j.cfg.set("gravar_som_com_microfone", False)
    j._gravar(SOM_INTERNO)
    assert vistos == [False]


def test_midia_como_resposta_cita_a_mensagem(j, tmp_path):
    _abrir_com_caixa(j)
    j.resposta_a = j.cache[("t1", "20")][0]
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF")
    j._enviar_arquivo(str(pdf))
    assert ("arquivo_com", "20", "5", None) in j.contas.p.pedidos
    assert j.resposta_a is None


def test_mencao_na_legenda_e_no_texto_segue_para_o_servico(j, tmp_path):
    _abrir_com_caixa(j)
    men = {"id": "1@s.whatsapp.net", "nome": "Ana", "usuario": ""}
    j.mencoes = [men]
    j.caixa.SetValue("oi @Ana")
    j._enviar_texto()
    assert ("mencoes", "20", [men]) in j.contas.p.pedidos
    assert j.mencoes == []


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
            if getattr(b, "visivel", False)] == ["Iniciar conversa com Bia, @bia"]
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
    j._aplicar_opcao("status_no_titulo", False)
    assert j.cfg.get("status_no_titulo") is False
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
    for chave in ("falar_reacoes",):
        assert chave in j.itens
        assert j.itens[chave].IsChecked() if hasattr(
            j.itens[chave], "IsChecked") else True
    # a fala do primeiro audio mora em Configuracoes, Midias
    assert "falar_quem_toca" not in j.itens
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


def test_bloquear_pessoa_da_conversa_so_onde_o_servico_sabe(j, monkeypatch):
    from telezapp.interface import bloqueados
    conv = j.indice[("t1", "10")]
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    rotulos = lambda: [r for r, _ in j._opcoes_da_conversa(conv)]
    assert "Bloquear ou desbloquear..." not in rotulos()
    j._bloquear_pessoa(conv)
    assert ditas[-1] == "Esta conta não bloqueia pessoas por aqui."
    j.contas.p.PODE_BLOQUEAR = True
    assert "Bloquear ou desbloquear..." in rotulos()
    chamadas = []
    monkeypatch.setattr(bloqueados, "alternar",
                        lambda *a, **k: chamadas.append(a[2:4]))
    j._bloquear_pessoa(conv)
    assert chamadas == [("10", conv.nome)]


def _perfil_falso(j, monkeypatch, valores, foto=None):
    """Poe um provedor que edita o perfil e uma janela de edicao que devolve
    `valores`; devolve (provedor, lista do que a janela falou)."""
    import threading
    from telezapp.interface import perfil as janela_perfil
    p = j.contas.p
    p.PODE_EDITAR_PERFIL, p.PERFIL_SOBRENOME = True, True
    p.meu_perfil = lambda: {"nome": "Fábio", "sobrenome": "S.",
                            "recado": "Oi"}
    p.salvos = []
    feito = threading.Event()

    def salvar(mudancas, foto=None):
        p.salvos.append((mudancas, foto))
        feito.set()
        return list(mudancas) + (["foto"] if foto else []), []
    p.salvar_perfil, p.feito = salvar, feito

    class Janela:
        def __init__(self, pai, titulo, servico, atuais, sobrenome, f, nf):
            self.foto, self.nome_da_foto = foto, "foto.png"

        def ShowModal(self):
            return wx_falso.ID_OK

        def Destroy(self):
            pass

        def valores(self):
            return valores
    monkeypatch.setattr(janela_perfil, "DialogoPerfil", Janela)
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j.estados["t1"] = ev.CONECTADA
    return p, ditas


def test_editar_perfil_grava_so_o_que_mudou(j, monkeypatch):
    p, ditas = _perfil_falso(j, monkeypatch, {
        "nome": "Fábio", "sobrenome": "S.", "recado": "Livre"}, b"JPEG")
    j._perfil_lido("t1", p.meu_perfil(), "")
    assert p.feito.wait(5)
    for _ in range(100):             # o resumo e falado depois de gravar
        if "Perfil salvo: recado, foto." in ditas:
            break
        time.sleep(0.02)
    assert p.salvos == [({"recado": "Livre"}, b"JPEG")]
    assert ditas[-1] == "Perfil salvo: recado, foto."


def test_editar_perfil_sem_mudanca_nao_grava(j, monkeypatch):
    p, ditas = _perfil_falso(j, monkeypatch, {
        "nome": "Fábio ", "sobrenome": "S.", "recado": "Oi"})
    j._perfil_lido("t1", p.meu_perfil(), "")
    assert p.salvos == [] and ditas[-1] == "Nada mudou no perfil."


def test_editar_perfil_nome_vazio_avisa_e_reabre_a_janela(j, monkeypatch):
    p, ditas = _perfil_falso(j, monkeypatch, {
        "nome": "", "sobrenome": "S.", "recado": "Oi"})
    from telezapp.interface import perfil as janela_perfil
    aberturas = []
    original = janela_perfil.DialogoPerfil

    class Reabre(original):
        def __init__(self, *a):
            super().__init__(*a)
            aberturas.append(a[3])

        def ShowModal(self):
            # na segunda vez a pessoa desiste
            return wx_falso.ID_OK if len(aberturas) == 1 else                 wx_falso.ID_CANCEL
    monkeypatch.setattr(janela_perfil, "DialogoPerfil", Reabre)
    j._perfil_lido("t1", p.meu_perfil(), "")
    assert len(aberturas) == 2 and aberturas[1]["nome"] == ""
    assert "O nome não pode ficar vazio." in ditas and p.salvos == []


def test_editar_perfil_sem_conta_que_edite_ou_com_erro_de_leitura(j):
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j.estados["t1"] = ev.CONECTADA
    j._editar_perfil()
    assert ditas[-1] == "Nenhuma conta conectada edita o perfil."
    j._perfil_lido("t1", None, "A conta do WhatsApp não está conectada.")
    assert ditas[-1] == "A conta do WhatsApp não está conectada."


def test_lista_de_conversas_muda_a_ordem_e_os_itens(j):
    from telezapp.nucleo import lista_conversas as lc
    j.b.publicar(ev.ConversasAtualizadas("t1", [
        conv("10", "Ana", nao_lidas=2, data=AGORA)]))
    assert j.lista_conv.itens[0] == "Ana, Telegram, 2 não lidas"
    j._aplicar_opcao("lista_conversas", {
        "ordem": ["nao_lidas", "nome", "servico", "previa"],
        "ocultos": ["servico", "previa"]})
    assert j.lista_conv.itens[0] == "2 não lidas, Ana"
    assert j.cfg.get("lista_conversas")["ocultos"] == [
        "servico", "previa", "reacoes", "quem_reagiu"]
    assert not j.itens["lista_servico"].marcado
    assert j.itens["lista_nome"].marcado
    j.itens["lista_servico"].Check(True)       # o menu marca antes do evento
    j.fala.falar = lambda t, interromper=False: None
    j._aplicar_opcao("lista_conversas", lc.padrao())
    assert j.lista_conv.itens[0] == "Ana, Telegram, 2 não lidas"


def test_item_do_menu_da_lista_nao_deixa_tirar_o_ultimo(j):
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j._aplicar_opcao("lista_conversas", {
        "ordem": ["nome", "servico", "nao_lidas", "previa"],
        "ocultos": ["servico", "nao_lidas", "previa", "reacoes",
                    "quem_reagiu"]})
    j.itens["lista_nome"].Check(False)         # o wx desmarca sozinho
    j._alternar_item_da_lista("nome")
    assert ditas[-1] == "Pelo menos um item precisa ficar ativado."
    assert j.itens["lista_nome"].marcado   # voltou marcado
    assert j.cfg.get("lista_conversas")["ocultos"] == [
        "servico", "nao_lidas", "previa", "reacoes", "quem_reagiu"]
    j._alternar_item_da_lista("previa")
    assert ditas[-1] == "Trecho da última mensagem: ativado."
    assert "previa" not in j.cfg.get("lista_conversas")["ocultos"]


def test_trecho_da_ultima_mensagem_acompanha_a_conversa(j):
    j._aplicar_opcao("lista_conversas", {
        "ordem": ["nome", "previa", "nao_lidas", "servico"],
        "ocultos": ["servico", "nao_lidas"]})
    c = j.indice[("t1", "10")]
    c.data = AGORA + 60
    j.b.publicar(ev.MensagemNova(msg("5", "vamos almoçar?", data=AGORA + 60),
                                 c))
    assert j.lista_conv.itens[0] == "Ana, vamos almoçar?"
    # uma mais antiga que chega depois nao troca o trecho
    j._atualizar_previa(("t1", "10"), msg("1", "velha", data=AGORA + 1))
    assert j.lista_conv.itens[0] == "Ana, vamos almoçar?"
    # editada: o trecho acompanha
    editada = msg("5", "vamos jantar?", data=AGORA + 60)
    j.b.publicar(ev.MensagemAtualizada("t1", "10", editada, "editada"))
    assert j.lista_conv.itens[0] == "Ana, vamos jantar?"


def test_trechos_do_banco_entram_ao_ligar_o_item(j):
    j.banco.salvar_mensagens([msg("3", "do banco", data=AGORA + 3)])
    j._aplicar_opcao("lista_conversas", {
        "ordem": ["nome", "previa", "nao_lidas", "servico"],
        "ocultos": ["servico", "nao_lidas"]})
    for _ in range(100):             # a leitura roda em segundo plano
        if ("t1", "10") in j.previas:
            break
        time.sleep(0.02)
    assert j.lista_conv.itens[0] == "Ana, do banco"


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
    assert [v for v, _ in j._tipos_atuais][-1] == "status"
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


def test_marcar_e_desmarcar_conta_no_gerenciar_contas(j):
    chamadas = []
    j.contas.ativar = lambda cid: chamadas.append(("ativar", cid)) or True
    j.contas.desativar = lambda cid: chamadas.append(("desativar", cid)) or True
    j.cfg.salvar_conta({"id": "t1", "servico": "telegram", "nome": "Fábio"})
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    assert j._itens_de_contas() == [("t1", "Fábio, Telegram", True)]
    assert j._marcar_conta("t1", False) is True
    assert chamadas == [("desativar", "t1")]
    assert ditas[-1] == "Fábio desativada."
    assert j._marcar_conta("t1", True) is True
    assert chamadas[-1] == ("ativar", "t1")
    assert ditas[-1] == "Fábio ativada, conectando."
    assert j._marcar_conta("nao-existe", True) is False


def test_renomear_conta_vale_na_caixa_de_contas(j):
    j.cfg.salvar_conta({"id": "t1", "servico": "telegram", "nome": "Fábio"})
    guardado = []
    j.contas.renomear = lambda cid, nome: (
        guardado.append((cid, nome)),
        j.cfg.salvar_conta({"id": cid, "servico": "telegram",
                            "nome": nome}))[1] or True
    j.contas.nome = lambda cid: "Trabalho"
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    assert j._renomear_conta_id("t1", "Trabalho") is True
    assert guardado == [("t1", "Trabalho")]
    assert ditas[-1] == "Conta renomeada para Trabalho."
    assert j._itens_de_contas()[0][1] == "Trabalho, Telegram"


def test_menu_unico_com_submenus_na_ordem_pedida(j):
    barra = j.GetMenuBar().menus
    assert [r.replace("&", "") for r, _ in barra] == ["Menu"]
    raiz = barra[0][1]
    rotulos = [r.replace("&", "") for r, _ in raiz.submenus]
    assert rotulos == ["Novo", "Ir para", "Mensagens", "Conversas",
                       "Contatos", "Chamadas", "Mídias", "Exibir",
                       "Ferramentas", "Ajuda"]
    menus = {r.replace("&", ""): mn for r, mn in raiz.submenus}

    def nomes(menu):
        return [i.rotulo.split("	")[0].replace("&", "")
                for i in menu.itens]
    # Novo e o primeiro menu e junta tudo o que se cria
    assert nomes(menus["Novo"]) == [
        "Nova mensagem...", "Nova chamada...", "Nova enquete...",
        "Novo contato...", "Novo status ou história...", "Nova conta...",
        "Novo grupo...", "Novo canal...", "Nova comunidade...",
        "Entrar em um grupo por link..."]
    for antigo in ("Mensagens", "Conversas"):
        assert "Nova mensagem..." not in nomes(menus[antigo])
    # Ir para junta as idas a um lugar da janela
    assert nomes(menus["Ir para"]) == [
        "Ir para a lista de conversas", "Ir para a lista de mensagens",
        "Ir para o campo editável", "Ir para o filtro de serviço ou conta",
        "Ir para o filtro de tipo de conversa",
        "Ir para a mensagem respondida"]
    assert "Escrever mensagem" not in nomes(menus["Conversas"])
    # Contas deixou de ser um menu: o que sobrou foi para Ferramentas
    assert "Contas" not in menus
    assert nomes(menus["Ferramentas"])[:2] == [
        "Gerenciar contas...", "Reconectar as contas"]
    # o que ficava solto no Menu foi para Ferramentas
    ferramentas = nomes(menus["Ferramentas"])
    for esperado in ("Fazer backup...", "Restaurar backup...",
                     "Configurações...", "Sair"):
        assert esperado in ferramentas
    assert any(x.startswith("Instalar o") for x in ferramentas)
    assert any(x.startswith("Desinstalar o") for x in ferramentas)
    # a depuracao e um submenu de Ajuda
    assert [r.replace("&", "") for r, _ in menus["Ajuda"].submenus] == [
        "Depurar"]
    assert "Modo de depuração" in "".join(
        i.rotulo for _, sub in menus["Ajuda"].submenus for i in sub.itens)


def test_adicionar_conta_pelo_menu_escolhe_o_servico_e_segue(j, monkeypatch):
    chamadas = []
    j.adicionar_conta = lambda servico: chamadas.append(servico)
    wx_falso.escolha_lista[0] = 1               # WhatsApp
    wx_falso.resposta_lista[0] = wx_falso.ID_OK
    try:
        j._adicionar_conta_pelo_menu()
        wx_falso.escolha_lista[0] = 0           # Telegram
        j._adicionar_conta_pelo_menu()
        wx_falso.resposta_lista[0] = wx_falso.ID_CANCEL
        j._adicionar_conta_pelo_menu()          # cancelou: nada
    finally:
        wx_falso.escolha_lista[0] = 0
        wx_falso.resposta_lista[0] = wx_falso.ID_OK
    assert chamadas == ["whatsapp", "telegram"]


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
def test_nova_mensagem_escolhe_a_pessoa_e_abre_a_conversa_sem_enviar(
        j, monkeypatch):
    from telezapp.interface import contatos
    vistas = []
    monkeypatch.setattr(contatos, "dialogo_nova_mensagem",
                        lambda pai, contas, buscar: vistas.append(contas) or
                        (("t1", "bruno", None)))
    enviados = []
    j._enviar_texto = lambda: enviados.append(j.atual)
    j._nova_mensagem()
    assert [c for c, _ in vistas[0]] == ["t1"]           # so a conectada
    assert j.atual == ("t1", "20")           # Bruno ja existia: abriu
    assert enviados == []                    # escreve-se na conversa
    assert j.FindFocus() is j.caixa


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

        def observar_presenca(self, *a):
            pass
    j.contas.provedores["w1"] = Zap()
    j.contas.provedor = lambda cid: j.contas.provedores.get(cid)
    j.b.publicar(ev.EstadoConta("w1", ev.CONECTADA))
    vistas = []
    monkeypatch.setattr(contatos, "dialogo_nova_mensagem",
                        lambda pai, contas, buscar: vistas.append(contas) or
                        ("w1", "(51) 99999-8888", None))
    j._nova_mensagem()
    assert len(vistas[0]) == 2                  # duas contas: aparece a escolha
    assert j.atual == ("w1", "5551999998888@s.whatsapp.net")
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
                        lambda pai, contas, buscar: ("t1", "ninguem assim", None))
    j._nova_mensagem()
    assert ditas[-1].startswith("Não encontrei ninguem assim.")


def test_nova_mensagem_com_pessoa_escolhida_na_lista_nao_resolve_o_texto(
        j, monkeypatch):
    from telezapp.interface import contatos
    monkeypatch.setattr(contatos, "dialogo_nova_mensagem",
                        lambda pai, contas, buscar: (
                            "t1", "br", ("20", "Bruno")))
    j._resolver_destino = lambda *a: (_ for _ in ()).throw(AssertionError)
    j._nova_mensagem()
    assert j.atual == ("t1", "20")


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


def test_favoritar_mensagem_marca_na_linha_e_fica_no_banco(j):
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [
        msg("1", "a", conversa="10"), msg("2", "b", conversa="10")]))
    selecionar(j, "2")
    j._favoritar_mensagem()
    assert "(favorita)" in j.lista_msgs.itens[j.mapa.index("2")]
    assert j.banco.favoritas() == {("t1", "10", "2")}
    j._favoritar_mensagem()
    assert "(favorita)" not in j.lista_msgs.itens[j.mapa.index("2")]
    assert j.banco.favoritas() == set()


def test_resposta_cujo_original_foi_tirado_pelo_telezapp_diz_isso(j):
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    r = msg("4", "concordo", conversa="10")
    r.resposta_a = "2"
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [
        msg("3", "b", conversa="10"), r]))
    linha = lambda: j.lista_msgs.itens[j.mapa.index("4")]
    assert "mais antiga" in linha()                  # nao se sabe por que falta
    j.banco.registrar_limpeza([("t1", "10", "2")], "mensagem")
    j._preencher_mensagens()
    assert "foi limpa deste computador" in linha()
    j.banco.esquecer_limpezas("t1")                  # so resta a conversa apagada
    j.banco.apagar_conversa("t1", "10", 1)
    j._preencher_mensagens()
    assert "antes de a conversa ser apagada" in linha()


def test_midia_colada_espera_o_enter_e_o_texto_vira_legenda(j, tmp_path):
    _abrir_com_caixa(j)
    pdf = tmp_path / "relatorio.pdf"
    pdf.write_bytes(b"%PDF")
    j.anexos.append(jm.envio.preparar(str(pdf)))
    j.caixa.SetValue("antes e depois")
    j._enviar_texto()
    assert ("arquivo", "20", m.DOCUMENTO, "relatorio.pdf",
            "antes e depois") in j.contas.p.pedidos
    assert not [p for p in j.contas.p.pedidos if p[0] == "enviar"]
    assert j.anexos == [] and j.caixa.GetValue() == ""


def test_midia_colada_so_audio_manda_o_texto_a_parte(j, tmp_path):
    _abrir_com_caixa(j)
    mp3 = tmp_path / "som.mp3"
    mp3.write_bytes(b"ID3")
    j.anexos.append(jm.envio.preparar(str(mp3)))
    j.caixa.SetValue("ouça")
    j._enviar_texto()
    pedidos = j.contas.p.pedidos
    assert ("arquivo", "20", m.AUDIO, "som.mp3", "") in pedidos
    assert ("enviar", "20", "ouça", "") in pedidos


def test_esc_remove_a_midia_colada_antes_de_sair_da_conversa(j, tmp_path):
    _abrir_com_caixa(j)
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    j.anexos.append(jm.envio.preparar(str(pdf)))
    j._sair_da_caixa()
    assert j.anexos == [] and j.atual is not None


def test_delete_apaga_conversa_na_lista_de_conversas_e_mensagem_na_de_mensagens(j):
    chamadas = []
    j._apagar_conversa = lambda *a: chamadas.append("conversa")
    j._apagar_mensagem = lambda *a: chamadas.append("mensagem")
    j.lista_conv.SetFocus()
    j._char_hook(Tecla(wx_falso.WXK_DELETE))
    j.lista_msgs.SetFocus()
    j._char_hook(Tecla(wx_falso.WXK_DELETE))
    j.caixa.SetFocus()
    j._char_hook(Tecla(wx_falso.WXK_DELETE))      # na caixa e do texto
    assert chamadas == ["conversa", "mensagem"]


def test_modo_de_selecao_marca_conversas_e_age_em_todas(j):
    j.lista_conv.SetFocus()
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_SPACE))            # sem o modo: nada
    assert not j.modo_conv and not j.marc_conv
    j._char_hook(Tecla(wx_falso.WXK_SPACE, ctrl=True))
    assert j.modo_conv and len(j.marc_conv) == 1
    assert j.lista_conv.itens[0].startswith("Marcada: ")
    j.lista_conv.SetSelection(1)
    j._char_hook(Tecla(wx_falso.WXK_SPACE))
    assert len(j.marc_conv) == 2
    j._massa_conversas("fixar")
    assert all(c.fixada for c in j.indice.values())
    assert not j.modo_conv and not j.marc_conv
    assert not any(x.startswith("Marcada") for x in j.lista_conv.itens)


def test_esc_desfaz_a_selecao_de_conversas(j):
    j.lista_conv.SetFocus()
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_SPACE, ctrl=True))
    j._char_hook(Tecla(wx_falso.WXK_ESCAPE))
    assert not j.modo_conv and not j.marc_conv
    assert not j.lista_conv.itens[0].startswith("Marcada")


def test_modo_de_selecao_nas_mensagens_favorita_em_massa(j):
    _abrir_com_caixa(j)
    j.lista_msgs.SetFocus()
    j.lista_msgs.SetSelection(len(j.lista_msgs.itens) - 1)
    j._char_hook(Tecla(wx_falso.WXK_SPACE, ctrl=True))
    assert j.modo_msg and j.marc_msg == {"5"}
    assert j.lista_msgs.itens[-1].startswith("Marcada: ")
    j._massa_mensagens("favoritar")
    assert m.extras_de(j._mensagens_atuais()[-1])["favorita"]
    assert not j.modo_msg and not j.marc_msg


def test_grupo_limpar_conversa_apaga_mensagens_e_mantem_na_lista(j):
    _abrir_com_caixa(j)
    chave = ("t1", "20")
    j.banco.salvar_mensagens([m.Mensagem("t1", "20", "5", texto="oi",
                                         data=AGORA)])
    j._limpar_conversa(j.indice[chave])
    assert j.banco.mensagens("t1", "20") == []
    assert chave in j.indice


def test_grupo_sair_so_apaga_da_lista_se_o_servico_aceitou(j):
    chave = ("t1", "20")
    j._saiu_do_grupo(j.indice[chave], True, False)       # falhou
    assert chave in j.indice
    j._saiu_do_grupo(j.indice[chave], False, True)       # saiu, ficou
    assert chave in j.indice
    j._saiu_do_grupo(j.indice[chave], True, True)        # saiu e apagou
    assert chave not in j.indice


def test_grupo_apagar_pergunta_a_acao_e_encaminha(j, monkeypatch):
    conv = j.indice[("t1", "20")]
    conv.tipo = "grupo"
    chamadas = []
    j._limpar_conversa = lambda c: chamadas.append(("limpar", c.id))
    j._sair_do_grupo = lambda c, p, ap: chamadas.append(("sair", ap))
    for acao in ("limpar", "sair_apagar", None):
        monkeypatch.setattr(jm.dialogos, "escolher_acao_grupo",
                            lambda pai, nome, pode, a=acao: a)
        j._apagar_conversa(conv)
    assert chamadas == [("limpar", "20"), ("sair", True)]


def test_botao_de_contato_diz_iniciar_conversa_ou_que_nao_ha_conversa(j):
    _abrir_com_caixa(j)
    x = j._mensagem_selecionada()
    m.guardar_extras(x, mencoes=[
        {"nome": "Ana", "telefone": "+5551", "id": "5551@s.whatsapp.net"},
        {"nome": "Cao", "telefone": "11 2222-3333", "id": ""}])
    j.banco.salvar_mensagens([x])
    j._botoes_chave = None
    j._atualizar_botoes()
    rotulos = [b.GetLabel() for b in j.botoes_mencao
               if getattr(b, "visivel", False)]
    assert rotulos == ["Iniciar conversa com Ana, +5551",
                       "Contato sem conversa possível: Cao, 11 2222-3333"]


def test_encaminhar_envia_para_as_conversas_escolhidas(j, monkeypatch):
    from telezapp.interface import encaminhar as je
    _abrir_com_caixa(j)

    class Dialogo:
        def __init__(self, pai, destinos, rotulo_de, resumo):
            assert any(d[1] == "10" for d in destinos)
            assert rotulo_de(destinos[0])
            self.resumo = resumo

        def ShowModal(self):
            return jm.wx.ID_OK

        def escolhidos(self):
            return [("t1", "10", "Ana", "privada")]

        def Destroy(self):
            pass
    monkeypatch.setattr(je, "DialogoEncaminhar", Dialogo)
    j._encaminhar()
    assert ("enviar", "10", "oi", "") in j.contas.p.pedidos


def test_encaminhar_midia_nao_baixada_avisa_e_nao_abre_o_dialogo(
        j, monkeypatch):
    from telezapp.interface import encaminhar as je
    _abrir_com_caixa(j)
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [m.Mensagem(
        "t1", "20", "6", tipo=m.FOTO, data=AGORA + 100)]))
    j.lista_msgs.SetSelection(len(j.lista_msgs.itens) - 1)
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    monkeypatch.setattr(jm.wx, "MessageBox", lambda *a, **k: None)
    monkeypatch.setattr(je, "DialogoEncaminhar", lambda *a: (_ for _ in (
    )).throw(AssertionError("nao devia abrir")))
    j._encaminhar()
    assert any("Nada para encaminhar" in t for t in ditas)


def test_responder_em_particular_abre_a_conversa_da_pessoa_citando_a_mensagem(j):
    j.indice[("t1", "20")].tipo = "grupo"
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [m.Mensagem(
        "t1", "20", "5", autor="Bia", texto="oi pessoal", data=AGORA,
        remetente="5551999990000@s.whatsapp.net")]))
    j._abrir_conversa(j.indice[("t1", "20")])
    j.contas.p.pessoa_da_mensagem = lambda x: (
        "5551999990000@s.whatsapp.net", "+5551999990000", [])
    x = j._mensagens_atuais()[-1]
    assert j._pode_responder_em_particular(x)
    j._responder_em_particular(x)
    assert j.atual == ("t1", "5551999990000@s.whatsapp.net")
    assert j.indice[j.atual].nome == "Bia"
    assert j.resposta_a is x
    j.caixa.SetValue("falo aqui")
    j._enviar_texto()
    assert ("enviar", "5551999990000@s.whatsapp.net", "falo aqui", "5") \
        in j.contas.p.pedidos


def test_responder_em_particular_so_em_grupo_e_de_outra_pessoa(j):
    _abrir_com_caixa(j)                        # conversa com pessoa
    x = j._mensagens_atuais()[-1]
    j.contas.p.pessoa_da_mensagem = lambda x: ("a@s.whatsapp.net", "+1", [])
    assert not j._pode_responder_em_particular(x)


def test_sons_de_conta_caiu_e_voltou(j, monkeypatch):
    sons = []
    monkeypatch.setattr(jm, "bipe", lambda tipo, valor=None: sons.append(tipo))
    j.b.publicar(ev.EstadoConta("t1", ev.CONECTADA))
    assert sons == []                                  # conectar nao e voltar
    j.b.publicar(ev.EstadoConta("t1", ev.DESCONECTADA))
    j.b.publicar(ev.EstadoConta("t1", ev.CONECTADA))
    assert sons == ["desconectada", "reconectada"]


def test_som_da_mensagem_nova_depende_de_onde_ela_chegou(j, monkeypatch):
    sons = []
    monkeypatch.setattr(jm, "bipe", lambda tipo, valor=None: sons.append(tipo))
    j.indice[("t1", "20")].tipo = "grupo"
    nova = lambda i: m.Mensagem("t1", "20", i, autor="Bia", texto="oi",
                                data=AGORA + 50)
    j.b.publicar(ev.MensagemNova(nova("30"), j.indice[("t1", "20")]))
    j._abrir_conversa(j.indice[("t1", "20")])
    sons.clear()
    j.b.publicar(ev.MensagemNova(nova("31"), j.indice[("t1", "20")]))
    assert sons == ["nova_aberta"]
    j._fechar_conversa()
    sons.clear()
    j.b.publicar(ev.MensagemNova(nova("32"), j.indice[("t1", "20")]))
    assert sons == ["nova_grupo"]


def test_conversa_somente_leitura_nao_mostra_caixa_nem_botoes_de_envio(j):
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j.indice[("t1", "20")].somente_leitura = True
    j._abrir_conversa(j.indice[("t1", "20")])
    assert not j.caixa.visivel
    assert not any(b.visivel for b in j.botoes_envio)
    assert any("somente leitura" in t for t in ditas)
    # nada que escreva funciona
    j.caixa.SetValue("oi")
    j._enviar_texto()
    assert not [p for p in j.contas.p.pedidos if p[0] == "enviar"]
    assert j._destino_do_envio() is None
    j._mostrar_caixa()                      # nao leva o foco para a caixa


def test_conversa_que_vira_somente_leitura_esconde_a_caixa_e_volta(j):
    j._abrir_conversa(j.indice[("t1", "20")])
    assert j.caixa.visivel
    nova = m.Conversa("t1", "20", j.indice[("t1", "20")].nome,
                      somente_leitura=True)
    j.b.publicar(ev.ConversasAtualizadas("t1", [nova]))
    assert not j.caixa.visivel and not j.botao_enviar.visivel
    nova = m.Conversa("t1", "20", nova.nome)
    j.b.publicar(ev.ConversasAtualizadas("t1", [nova]))
    assert j.caixa.visivel and j.botao_enviar.visivel


def _mensagem_minha(j, texto="ola", antes=60):
    _abrir_com_caixa(j)
    x = m.Mensagem("t1", "20", "9", minha=True, texto=texto,
                   data=time.time() - antes, estado=m.ENVIADA)
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [x]))
    j.lista_msgs.SetSelection(j.mapa.index("9"))
    j.estados["t1"] = ev.CONECTADA
    j.contas.p.JANELA_EDICAO = 900
    return x


def test_editar_mensagem_poe_o_texto_na_caixa_e_enter_manda_a_edicao(j):
    pedidos = []
    j.contas.p.editar_mensagem = lambda x, t: pedidos.append((x.id, t))
    x = _mensagem_minha(j)
    j.caixa.SetValue("rascunho")
    assert j._pode_editar(x)
    j._editar_mensagem()
    assert j.editando is x and j.caixa.GetValue() == "ola"
    assert "Editando" in j.rot_caixa.GetLabel()
    j.caixa.SetValue("ola, tudo bem?")
    j._enviar_texto()
    assert pedidos == [("9", "ola, tudo bem?")]
    assert j.editando is None and j.caixa.GetValue() == "rascunho"
    assert not [p for p in j.contas.p.pedidos if p[0] == "enviar"]


def test_esc_cancela_a_edicao_e_devolve_o_rascunho(j):
    j.contas.p.editar_mensagem = lambda x, t: (_ for _ in ()).throw(
        AssertionError("nao devia editar"))
    _mensagem_minha(j)
    j.caixa.SetValue("rascunho")
    j._editar_mensagem()
    j._sair_da_caixa()
    assert j.editando is None and j.caixa.GetValue() == "rascunho"
    j._editar_mensagem()
    j._enviar_texto()                    # sem mudar nada: so cancela
    assert j.editando is None and j.caixa.GetValue() == "rascunho"


def test_nao_edita_fora_do_prazo_nem_mensagem_dos_outros_nem_vazia(j):
    x = _mensagem_minha(j, antes=3600)           # passou de 15 minutos
    assert not j._pode_editar(x)
    outra = m.Mensagem("t1", "20", "8", minha=False, texto="oi",
                       data=time.time())
    assert not j._pode_editar(outra)
    j.contas.p.editar_mensagem = lambda x, t: None
    nova = _mensagem_minha(j, antes=10)
    j._editar_mensagem()
    j.caixa.SetValue("   ")
    j._enviar_texto()
    assert j.editando is nova                    # continua editando


# ------------------------------------------------ detalhes da conversa
def _controle(j, tipo="privada", dados=None):
    from telezapp.interface.detalhes import ControleDetalhes
    from telezapp.nucleo import detalhes as det
    conv = j.indice[("t1", "20")]
    conv.tipo = tipo
    c = ControleDetalhes(j, conv)
    c.mensagens = [m.Mensagem("t1", "20", "1", tipo=m.FOTO, texto="praia",
                              autor="Ana", data=AGORA),
                   m.Mensagem("t1", "20", "2", texto="veja https://x.com/a",
                              autor="Ana", data=AGORA + 1)]
    c.est = det.estatisticas(c.mensagens, [])
    c.dados = dados
    return c


def test_detalhes_de_pessoa_mostra_dados_do_contato_e_botoes(j):
    c = _controle(j, "privada", {"telefone": "+5551999990000",
                                 "nome_no_perfil": "Ana S.",
                                 "usuario": "@ana"})
    texto = "\n".join(c._linhas())
    assert "Telefone: +5551999990000" in texto
    assert "Nome de usuário: @ana" in texto and "Nome no perfil: Ana S." in texto
    assert "Mensagens guardadas: 2." in texto and "Fotos: 1" in texto
    assert [r for r, _ in c._botoes()] == [
        "&Editar contato", "&Mídias", "&Grupos em comum"]


def test_detalhes_de_grupo_mostram_membros_e_so_admin_ve_administrar(j):
    gente = [{"id": "1@s.whatsapp.net", "nome": "Ana", "telefone": "+1",
              "admin": True, "dono": True, "eu": False},
             {"id": "2@s.whatsapp.net", "nome": "Bia", "telefone": "+2",
              "admin": False, "dono": False, "eu": True}]
    dados = {"nome": "Turma", "descricao": "Aviso", "criado_em": AGORA,
             "dono": "Ana", "anuncio": True, "trancado": False,
             "sou_admin": False, "participantes": gente}
    c = _controle(j, "grupo", dados)
    texto = "\n".join(c._linhas())
    assert "Membros: 2 (1 administrador)" in texto
    assert "Quem envia mensagens: só administradores" in texto
    assert "Você não é administrador." in texto
    assert "Criador: Ana" in texto
    rotulos = [r for r, _ in c._botoes()]
    assert rotulos == ["Ver &membros (2)", "&Mídias"]
    dados["sou_admin"] = True
    assert "&Administrar grupo" in [r for r, _ in c._botoes()]
    dados["comunidade"] = True
    assert "&Grupos da comunidade" in [r for r, _ in c._botoes()]


def test_detalhes_de_canal_e_menu_dos_itens_de_midia(j):
    c = _controle(j, "canal", {"descricao": "Sobre", "seguidores": 1200,
                               "verificado": True, "papel": "seguidor",
                               "silenciado": False,
                               "link": "https://whatsapp.com/channel/abc"})
    texto = "\n".join(c._linhas())
    assert "Seguidores: 1200" in texto and "Verificado: sim" in texto
    assert "Link: https://whatsapp.com/channel/abc" in texto
    assert "&Silenciar o canal" in [r for r, _ in c._botoes()]
    foto = c.mensagens[0]
    rotulos = [r for r, _ in c._menu_midia(foto)]
    assert rotulos[0] == "Abrir" and "Salvar em um arquivo..." in rotulos
    assert "Copiar legenda" in rotulos and "Copiar foto" in rotulos
    assert rotulos[-2:] == ["Apagar...", "Ver na conversa"]
    link = c.mensagens[1]
    rotulos = [r for r, _ in c._menu_midia(link)]
    assert rotulos[0] == "Abrir o link" and "Copiar link" in rotulos


def test_menu_do_membro_traz_os_itens_da_lista_de_conversas(j):
    c = _controle(j, "grupo", {"sou_admin": True, "participantes": []})
    j.indice[("t1", "5551@s.whatsapp.net")] = m.Conversa(
        "t1", "5551@s.whatsapp.net", "Ana", "whatsapp", "privada")
    membro = {"id": "5551@s.whatsapp.net", "nome": "Ana", "telefone": "+1",
              "admin": False, "dono": False, "eu": False}
    rotulos = [r for r, _ in c._menu_membro(membro)]
    assert rotulos[0] == "Iniciar conversa"
    for esperado in ("Detalhes da conversa", "Arquivar", "Fixar", "Silenciar",
                     "Apagar conversa...", "Salvar como contato...",
                     "Promover a administrador", "Remover do grupo..."):
        assert esperado in rotulos
    # trancar e destrancar so pelo celular: o TeleZapp nao tem o comando
    assert "Trancar" not in rotulos and "Destrancar" not in rotulos
    assert c._menu_membro(dict(membro, eu=True)) == []
    sem_admin = _controle(j, "grupo", {"sou_admin": False})
    assert "Remover do grupo..." not in [
        r for r, _ in sem_admin._menu_membro(membro)]


def test_botao_entrar_no_grupo_consulta_confirma_e_entra(j, monkeypatch):
    class Sincrono:
        def __init__(self, target=None, args=(), **k):
            self.target, self.args = target, args

        def start(self):
            if self.target is not jm.bipe and "_tocar" not in getattr(
                    self.target, "__name__", ""):
                self.target(*self.args)
    monkeypatch.setattr(jm.threading, "Thread", Sincrono)
    ditas, caixas = [], []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    monkeypatch.setattr(jm.wx, "MessageBox", lambda texto, *a, **k:
                        caixas.append(texto) or jm.wx.YES)
    entrou = []
    p = j.contas.p
    p.previa_do_convite = lambda msg, acao: {
        "nome": "Turma", "membros": 12, "descricao": "Avisos",
        "ja_participa": False}
    p.entrar_no_grupo = lambda msg, acao: entrou.append(acao["codigo"]) or (
        True, "Você entrou no grupo.")
    p.atualizar_conversas = lambda: entrou.append("atualizou")
    x = m.Mensagem("t1", "20", "5", texto="convite")
    j._tocar_acao(x, {"tipo": "entrar", "codigo": "ABC",
                      "rotulo": "Entrar no grupo Turma"})
    assert "Entrar em Turma? 12 membros. Descrição: Avisos" in caixas[0]
    assert entrou == ["ABC", "atualizou"]
    assert "Você entrou no grupo." in ditas
    # convite que nao vale mais: avisa e nao pergunta
    entrou.clear()
    caixas.clear()
    p.previa_do_convite = lambda msg, acao: {"erro": "O convite expirou."}
    j._tocar_acao(x, {"tipo": "entrar", "codigo": "ABC", "rotulo": "x"})
    assert caixas == ["O convite expirou."] and entrou == []
    # ja esta no grupo
    p.previa_do_convite = lambda msg, acao: {"nome": "Turma",
                                             "ja_participa": True}
    caixas.clear()
    j._tocar_acao(x, {"tipo": "entrar", "codigo": "ABC", "rotulo": "x"})
    assert caixas == ["Você já está em Turma."] and entrou == []


def _ia_pronta(j, monkeypatch, tmp_path, tipo=m.VOZ, nome=""):
    from telezapp.nucleo.ia import cofre as cofre_ia
    from telezapp.nucleo.ia import servico as servico_ia
    arquivo = tmp_path / "voz.ogg"
    arquivo.write_bytes(b"OggS" + b"0" * 30)

    class Sincrono:
        def __init__(self, target=None, args=(), **k):
            self.target, self.args = target, args

        def start(self):
            if "_tocar" not in getattr(self.target, "__name__", ""):
                self.target(*self.args)
    monkeypatch.setattr(jm.threading, "Thread", Sincrono)
    monkeypatch.setattr(jm.wx, "MessageBox", lambda *a, **k: jm.wx.YES)
    j.cofre_ia = cofre_ia.Cofre(str(tmp_path / "ia.json"))
    j.cofre_ia.guardar("openai", "K")
    j.cfg.set("ia_ordem", {"audio": ["openai"]})
    j.midias = types.SimpleNamespace(caminho=lambda x: str(arquivo),
                                     baixar=lambda x: None)
    chamadas = []
    monkeypatch.setattr(servico_ia, "executar", lambda *a, **k: chamadas.append(
        a) or servico_ia.Resultado("ola, tudo bem?", "OpenAI", "gpt"))
    _abrir_com_caixa(j)
    x = m.Mensagem("t1", "20", "7", tipo=tipo, nome_arquivo=nome,
                   data=AGORA + 100, autor="Ana")
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [x]))
    return x, chamadas


def test_transcrever_audio_guarda_o_texto_na_mensagem_e_mostra_na_linha(
        j, monkeypatch, tmp_path):
    x, chamadas = _ia_pronta(j, monkeypatch, tmp_path)
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    rotulos = [r for r, _ in j._opcoes_ia(x)]
    assert rotulos == ["Transcrever o áudio"]
    j._ia_processar(x)
    assert chamadas[0][0] == "audio" and chamadas[0][2] == "openai"
    assert "openai" in j.cfg.get("ia_consentimento")
    guardada = j.banco.mensagem("t1", "20", "7")
    assert m.extras_de(guardada)["ia"]["texto"] == "ola, tudo bem?"
    assert "transcrição: ola, tudo bem?" in m.formatar(
        x, m.ESTILO_AUTOR_PRIMEIRO)
    assert any(t.startswith("Transcrição: ola") for t in ditas)
    assert [r for r, _ in j._opcoes_ia(x)] == [
        "Ver a transcrição", "Transcrever o áudio de novo"]
    assert ("texto", "Copiar transcrição", "ola, tudo bem?") in \
        m.conteudos_copiaveis(x)


def test_sem_provedor_ou_sem_chave_manda_para_as_configuracoes(
        j, monkeypatch, tmp_path):
    x, chamadas = _ia_pronta(j, monkeypatch, tmp_path)
    abertas = []
    j._configuracoes = lambda categoria=None: abertas.append(categoria)
    j.cfg.set("ia_ordem", {})
    j._ia_processar(x)
    j.cfg.set("ia_ordem", {"audio": ["gemini"]})       # sem chave guardada
    j._ia_processar(x)
    assert abertas == ["Inteligência artificial"] * 2 and chamadas == []


def test_midia_nao_baixada_baixa_antes_e_processa_ao_chegar(
        j, monkeypatch, tmp_path):
    x, chamadas = _ia_pronta(j, monkeypatch, tmp_path)
    baixou = []
    j.cfg.set("ia_consentimento", ["openai"])
    j.midias = types.SimpleNamespace(caminho=lambda y: None,
                                     baixar=lambda y: baixou.append(y.id))
    j._ia_processar(x)
    assert baixou == ["7"] and x.chave in j._ia_pendentes and chamadas == []
    j.midias = types.SimpleNamespace(
        caminho=lambda y: str(tmp_path / "voz.ogg"), baixar=lambda y: None)
    j.b.publicar(ev.MidiaBaixada("t1", "20", "7", str(tmp_path / "voz.ogg")))
    assert len(chamadas) == 1 and not j._ia_pendentes


def test_generos_da_ia_e_erro_do_provedor_e_avisado(j, monkeypatch, tmp_path):
    x, _ = _ia_pronta(j, monkeypatch, tmp_path)
    assert j._genero_ia(m.Mensagem("t", "c", "1", tipo=m.FOTO)) == "imagem"
    assert j._genero_ia(m.Mensagem("t", "c", "1", tipo=m.FIGURINHA)) == \
        "figurinha"
    assert j._genero_ia(m.Mensagem("t", "c", "1", tipo=m.VIDEO)) == "video"
    assert j._genero_ia(m.Mensagem("t", "c", "1", tipo=m.DOCUMENTO,
                                   nome_arquivo="Edital.PDF")) == "pdf"
    assert j._genero_ia(m.Mensagem("t", "c", "1", tipo=m.DOCUMENTO,
                                   nome_arquivo="a.docx")) == ""
    assert j._genero_ia(m.Mensagem("t", "c", "1", tipo=m.TEXTO)) == ""
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j._ia_pronto(x, "audio", None, "O provedor recusou a chave.")
    assert ditas[-1] == "O provedor recusou a chave."
    assert not m.extras_de(x)["ia"]


def test_transcrever_e_descrever_e_o_primeiro_item_do_menu_da_mensagem(
        j, monkeypatch, tmp_path):
    x, _ = _ia_pronta(j, monkeypatch, tmp_path)
    j.lista_msgs.SetSelection(j.mapa.index("7"))
    rotulos = []

    class MenuGravador(jm.wx.Menu):
        def Append(self, id_, rotulo, *a):
            rotulos.append(rotulo)
            return super().Append(id_, rotulo)

        def Destroy(self):
            pass
    monkeypatch.setattr(jm.wx, "Menu", MenuGravador)
    monkeypatch.setattr(j.lista_msgs, "PopupMenu", lambda *a: None,
                        raising=False)
    j._menu_mensagem(types.SimpleNamespace(
        GetPosition=lambda: jm.wx.DefaultPosition))
    assert rotulos[0] == "Transcrever o áudio"
    assert "Favoritar" in rotulos and rotulos.index("Favoritar") > 0
    j._ia_processar(x)                       # agora a transcricao existe
    rotulos.clear()
    j._menu_mensagem(types.SimpleNamespace(
        GetPosition=lambda: jm.wx.DefaultPosition))
    assert rotulos[:2] == ["Ver a transcrição",
                           "Transcrever o áudio de novo"]
    # reproduzir continua no menu, mesmo com o Enter mandando transcrever
    j.cfg.set("enter_audio", "ia")
    assert rotulos[2] == "Reproduzir a mensagem de voz"
    assert rotulos[3] == "Salvar a mídia em um arquivo..."   # ja baixada
    j.midias = types.SimpleNamespace(caminho=lambda y: None,
                                     baixar=lambda y: None)
    rotulos.clear()
    j._menu_mensagem(types.SimpleNamespace(
        GetPosition=lambda: jm.wx.DefaultPosition))
    assert rotulos[2:4] == ["Reproduzir a mensagem de voz",
                            "Baixar a mídia sem abrir"]


def test_enter_na_midia_reproduz_baixa_ou_transcreve_conforme_a_opcao(
        j, monkeypatch, tmp_path):
    x, chamadas = _ia_pronta(j, monkeypatch, tmp_path)
    j.lista_msgs.SetFocus()
    j.lista_msgs.SetSelection(j.mapa.index("7"))
    feitos = []
    j._abrir_midia = lambda abrir=True, x=None: feitos.append(
        ("abrir" if abrir else "baixar", x.id))
    vistos = []
    j._ia_ver = lambda y: vistos.append(y.id)
    enter = Tecla(wx_falso.WXK_RETURN)
    j._char_hook(enter)                              # padrao: reproduzir
    j.cfg.set("enter_audio", "baixar")
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    assert feitos == [("abrir", "7"), ("baixar", "7")] and not chamadas
    j.cfg.set("enter_audio", "ia")
    j._char_hook(Tecla(wx_falso.WXK_RETURN))         # sem texto: transcreve
    assert len(chamadas) == 1 and vistos == []
    j._char_hook(Tecla(wx_falso.WXK_RETURN))         # com texto: so mostra
    assert len(chamadas) == 1 and vistos == ["7"]
    assert feitos == [("abrir", "7"), ("baixar", "7")]
    # documento que nao e PDF e foto seguem as suas proprias opcoes
    foto = m.Mensagem("t1", "20", "8", tipo=m.FOTO, data=AGORA + 200)
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [foto]))
    j.lista_msgs.SetSelection(j.mapa.index("8"))
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    assert feitos[-1] == ("abrir", "8")


def test_ia_automatica_so_nas_conversas_ligadas_e_conforme_as_opcoes(
        j, monkeypatch, tmp_path):
    _, chamadas = _ia_pronta(j, monkeypatch, tmp_path)
    j.cfg.set("ia_consentimento", ["openai"])
    c = j.indice[("t1", "20")]
    nova = m.Mensagem("t1", "20", "8", tipo=m.VOZ, data=AGORA + 200,
                      autor="Ana")
    # desligada na conversa: nada
    j.b.publicar(ev.MensagemNova(nova, c))
    assert chamadas == []
    # ligada pelo menu da conversa
    rotulos = [r for r, _ in j._opcoes_da_conversa(c)]
    assert "Ligar a transcrição e descrição automáticas" in rotulos
    j._alternar_ia_auto(c)
    assert j.cfg.get("ia_automatica_conversas") == [["t1", "20"]]
    nova2 = m.Mensagem("t1", "20", "9", tipo=m.VOZ, data=AGORA + 300,
                       autor="Ana")
    j.b.publicar(ev.MensagemNova(nova2, c))
    assert len(chamadas) == 1
    assert m.extras_de(nova2)["ia"]["texto"] == "ola, tudo bem?"
    # minha mensagem e sincronia inicial nao contam
    minha = m.Mensagem("t1", "20", "10", tipo=m.VOZ, data=AGORA + 400,
                       minha=True)
    j.b.publicar(ev.MensagemNova(minha, c))
    j.b.publicar(ev.MensagemNova(m.Mensagem(
        "t1", "20", "11", tipo=m.VOZ, data=AGORA + 500), c, silenciosa=True))
    assert len(chamadas) == 1
    # a opcao de voz desligada: nao transcreve
    j.cfg.set("ia_auto_audio", False)
    j.b.publicar(ev.MensagemNova(m.Mensagem(
        "t1", "20", "12", tipo=m.VOZ, data=AGORA + 600), c))
    assert len(chamadas) == 1
    # falha em modo automatico: sem janela nem fala
    j.cfg.set("ia_auto_audio", True)
    avisos = []
    monkeypatch.setattr(jm.wx, "MessageBox",
                        lambda *a, **k: avisos.append(a) or jm.wx.YES)
    j.fala.falar = lambda t, interromper=False: avisos.append(t)
    j._ia_pronto(nova, "audio", None, "falhou", True)
    assert avisos == []
    # desligar
    j._alternar_ia_auto(c)
    assert j.cfg.get("ia_automatica_conversas") == []


def test_ia_automatica_sem_consentimento_nao_pergunta(
        j, monkeypatch, tmp_path):
    _, chamadas = _ia_pronta(j, monkeypatch, tmp_path)
    perguntas = []
    monkeypatch.setattr(jm.wx, "MessageBox",
                        lambda *a, **k: perguntas.append(a) or jm.wx.YES)
    j.cfg.set("ia_consentimento", [])
    c = j.indice[("t1", "20")]
    j._alternar_ia_auto(c)
    j.b.publicar(ev.MensagemNova(m.Mensagem(
        "t1", "20", "9", tipo=m.VOZ, data=AGORA + 300), c))
    assert chamadas == [] and perguntas == []


def test_pareamento_por_qr_ja_abre_em_tela_cheia(j):
    j.adicionar_conta("whatsapp")
    dlg = j.pareamentos["w-nova"]
    # QR escolhido antes de o QR chegar: a tela cheia espera por ele
    dlg._ir_para("qr")
    cheia = dlg.tela_cheia
    assert cheia is not None and cheia.cheia and dlg.pagina == "qr"
    j.b.publicar(ev.QrPareamento("w-nova", "2@" + "x" * 150))
    assert cheia.codigo.startswith("2@") and cheia.imagem.bitmap.img.w >= 900
    # Esc volta a janela; Voltar leva aos dois botoes
    cheia._fechar(None)
    assert dlg.tela_cheia is None
    dlg._ir_para("inicio")
    assert dlg.painel_inicio.visivel and not dlg.painel_qr.visivel
    # QR ja pronto: escolher QR abre direto com ele
    dlg._ir_para("qr")
    assert dlg.tela_cheia.codigo.startswith("2@")


def test_codigo_recusado_ou_qr_recusado_recomeca_a_conexao(j, monkeypatch):
    class Sincrono:
        def __init__(self, target=None, args=(), **k):
            self.target = target

        def start(self):
            if "_tocar" not in getattr(self.target, "__name__", ""):
                self.target()
    monkeypatch.setattr(jm.threading, "Thread", Sincrono)
    j.adicionar_conta("whatsapp")
    dlg = j.pareamentos["w-nova"]
    dlg._ir_para("codigo")
    dlg.telefone.SetValue("+55 51 99999 8888")
    dlg._gerar()
    j.b.publicar(ev.CodigoPareamento("w-nova", "ABCD-EFGH"))
    assert dlg.codigo.GetValue() == "ABCD-EFGH" and dlg.codigo_gerado
    # o celular nao aceitou: some o codigo antigo e a conexao recomeca
    ditas = []
    dlg.falar = j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j.b.publicar(ev.PareamentoFalhou("w-nova", "codigo"))
    assert j.contas.reiniciadas == ["w-nova"]
    assert dlg.codigo.GetValue() == "" and not dlg.codigo_gerado
    assert dlg.janela_codigo is None
    assert any("não aceitou o código" in t for t in ditas)
    # o QR que valia antes nao vale mais
    j.b.publicar(ev.QrPareamento("w-nova", "2@velho"))
    j.b.publicar(ev.PareamentoFalhou("w-nova", "qr"))
    assert dlg.qr_atual == "" and len(j.contas.reiniciadas) == 2
    assert any("recusou o QR Code" in t for t in ditas)
    # insistir sem fim nao: depois de 3 falhas so avisa
    j.b.publicar(ev.PareamentoFalhou("w-nova", "qr"))
    j.b.publicar(ev.PareamentoFalhou("w-nova", "qr"))
    assert len(j.contas.reiniciadas) == 3
    assert "tente mais tarde" in ditas[-1]


def test_qr_depois_de_pedir_codigo_recomeca_a_conexao(j, monkeypatch):
    class Sincrono:
        def __init__(self, target=None, args=(), **k):
            self.target = target

        def start(self):
            if "_tocar" not in getattr(self.target, "__name__", ""):
                self.target()
    monkeypatch.setattr(jm.threading, "Thread", Sincrono)
    j.adicionar_conta("whatsapp")
    dlg = j.pareamentos["w-nova"]
    dlg._ir_para("qr")                      # sem codigo antes: nao reinicia
    assert not hasattr(j.contas, "reiniciadas")
    dlg._ir_para("codigo")
    dlg.telefone.SetValue("+55 51 99999 8888")
    dlg._gerar()
    dlg._ir_para("qr")
    assert j.contas.reiniciadas == ["w-nova"] and dlg.tela_cheia is not None


def test_status_da_pessoa_no_titulo_da_janela(j):
    j.cfg.set("status_no_titulo", True)
    j._abrir_conversa(j.indice[("t1", "20")])
    assert ("observar", "20") in j.contas.p.pedidos
    nome = j.indice[("t1", "20")].nome
    assert j.GetTitle() == "TeleZapp: " + nome
    j.b.publicar(ev.Presenca("t1", "20", "online"))
    assert j.GetTitle() == "TeleZapp: %s (online)" % nome
    j.b.publicar(ev.Presenca("t1", "20", "digitando"))
    assert j.GetTitle() == "TeleZapp: %s (digitando)" % nome
    j.b.publicar(ev.Presenca("t1", "20", "parou"))
    assert j.GetTitle().endswith("(online)")
    j.b.publicar(ev.Presenca("t1", "20", "offline",
                             quando=time.time() - 60))
    assert "visto por último hoje às" in j.GetTitle()
    # a de outra conversa nao entra
    j.b.publicar(ev.Presenca("t1", "99", "online"))
    assert "visto por último" in j.GetTitle()
    # grupo: quem digita
    j.b.publicar(ev.Presenca("t1", "20", "digitando", quem="Ana"))
    assert j.GetTitle().endswith("(Ana está digitando)")
    # o "digitando" que nunca ganhou "parou" some sozinho
    j.digitando = (j.digitando[0], time.time() - 1)
    assert "digitando" not in j._status_da_conversa()
    # opcao desligada: nada no titulo
    j.cfg.set("status_no_titulo", False)
    assert j._status_da_conversa() == ""
    # fechar a conversa avisa o provedor e limpa o status
    j.cfg.set("status_no_titulo", True)
    j._fechar_conversa()
    assert ("parar_presenca", "20") in j.contas.p.pedidos
    assert j.presenca is None and j.GetTitle() == "TeleZapp"


def test_reagir_a_mensagem_e_inserir_emoji(j, monkeypatch):
    from telezapp.interface import emojis as ui
    j._abrir_conversa(j.indice[("t1", "20")])
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [
        msg("1", "oi", conversa="20")]))
    j.lista_msgs.SetSelection(j.mapa.index("1"))
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    reagidas = []
    j.contas.p.PODE_REAGIR = True
    j.contas.p.reagir = lambda x, emoji: reagidas.append((x.id, emoji))
    j.estados["t1"] = ev.CONECTADA
    # uma das rapidas
    monkeypatch.setattr(ui, "escolher_reacao", lambda pai, atual="": "👍")
    j._reagir()
    assert reagidas == [("1", "👍")]
    assert "polegar para cima" in ditas[-1]
    # outro emoji: abre a busca completa
    monkeypatch.setattr(ui, "escolher_reacao", lambda pai, atual="": ui.OUTRO)
    monkeypatch.setattr(ui, "escolher_emoji", lambda pai, titulo="": "🎂")
    j._reagir()
    assert reagidas[-1] == ("1", "🎂")
    # desistir nao envia
    monkeypatch.setattr(ui, "escolher_reacao", lambda pai, atual="": "")
    j._reagir()
    assert len(reagidas) == 2
    # tirar a minha reacao
    x = j._mensagem_selecionada()
    m.atualizar_extras(x, reacoes=[{"id": "eu", "quem": "Você",
                                    "emoji": "🎂", "minha": True}])
    monkeypatch.setattr(ui, "escolher_reacao",
                        lambda pai, atual="": ui.TIRAR)
    j._reagir()
    assert reagidas[-1] == ("1", "") and "removida" in ditas[-1]
    # servico que nao reage
    j.contas.p.PODE_REAGIR = False
    j._reagir()
    assert "não aceita reações" in ditas[-1] and len(reagidas) == 3
    # inserir emoji na caixa
    monkeypatch.setattr(ui, "escolher_emoji", lambda pai, titulo="": "😂")
    j.caixa.SetValue("oi ")
    j._inserir_emoji()
    assert j.caixa.GetValue().endswith("😂")


def test_detalhes_de_mensagem_de_grupo_tem_botoes_de_quem_recebeu(
        j, monkeypatch):
    from telezapp.interface import detalhes as dt
    j._abrir_conversa(j.indice[("t1", "20")])
    j.indice[("t1", "20")].tipo = "grupo"
    j.contas.servico = lambda cid: "whatsapp"
    x = msg("5", "oi", conversa="20", minha=True)
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [x]))
    j.banco.salvar_recibos("t1", "20", ["5"], "5551988887777@s.whatsapp.net",
                           "entregue", 1760000100)
    j.banco.salvar_recibos("t1", "20", ["5"], "5551988887777@s.whatsapp.net",
                           "lida", 1760000200)
    j.banco.salvar_recibos("t1", "20", ["5"], "5551977776666@s.whatsapp.net",
                           "entregue", 1760000300)
    chamadas = []
    monkeypatch.setattr(jm.dialogos, "mostrar_texto",
                        lambda *a, **k: chamadas.append((a, k)) or None)
    j.lista_msgs.SetSelection(j.mapa.index("5"))
    j._detalhes()
    (args, k) = chamadas[0]
    assert "Recebida por 2 pessoas" in args[2] and "Aberta por 1 pessoa" in \
        args[2]
    rotulos = [r for r, _ in k["botoes_extra"]]
    assert rotulos == ["Recebida por 2 pessoas", "Aberta por 1 pessoa"]
    # a lista de um botao: membro, telefone, data e hora; o menu e o dos membros
    ctl = dt.ControleRecibos(j, j.indice[("t1", "20")],
                             j.banco.recibos("t1", "20", "5"),
                             {"5551988887777@s.whatsapp.net": "Ana"})
    r = ctl.rotulo("5551988887777@s.whatsapp.net", 1760000100)
    assert r.startswith("Ana, +5551988887777, ") and "/2025 " in r
    assert ctl.rotulo("5551977776666@s.whatsapp.net", 0).startswith(
        "+5551977776666, ")
    menu = ctl._membros._menu_membro(
        ctl.pessoa("5551988887777@s.whatsapp.net"))
    assert menu[0][0] == "Iniciar conversa"
    # mensagem de outra pessoa ou conversa privada: sem os botoes
    j.indice[("t1", "20")].tipo = "privada"
    chamadas.clear()
    j._detalhes()
    assert not chamadas[0][1]["botoes_extra"]


def test_aviso_de_chamada_do_whatsapp_tem_ok_e_conversar(j, monkeypatch):
    sons = []
    monkeypatch.setattr(jm, "bipe", lambda t, *a: sons.append(t))
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j.b.publicar(ev.ChamadaWhatsApp("t1", "20", "Ana", False, "tocando", "C1"))
    dlg = j.avisos_de_chamada[("t1", "C1")]
    assert sons[-1] == "toque"
    assert ditas[-1].startswith("Ana está te chamando por voz.")
    assert "atenda em outro dispositivo ou abra uma conversa" in ditas[-1]
    assert dlg.ok.GetLabel() == "OK" and "Conversar" in dlg.conversar.GetLabel()
    # a chamada acaba com a janela aberta: o texto muda
    j.b.publicar(ev.ChamadaWhatsApp("t1", "20", "Ana", False, "perdida",
                                    "C1"))
    assert "sem ser atendida" in dlg.aviso.GetLabel()
    assert "sem ser atendida" in ditas[-1]
    # Conversar abre a conversa e fecha a janela
    j.b.publicar(ev.ChamadaWhatsApp("t1", "20", "Ana", True, "tocando", "C2"))
    d2 = j.avisos_de_chamada[("t1", "C2")]
    monkeypatch.setattr(jm.wx, "CallAfter", lambda f, *a: f(*a),
                        raising=False)
    d2._conversar()
    assert j.atual == ("t1", "20")
    # opcao desligada: nao abre janela
    j.cfg.set("avisar_chamadas_whatsapp", False)
    j.b.publicar(ev.ChamadaWhatsApp("t1", "20", "Ana", False, "tocando", "C3"))
    assert ("t1", "C3") not in j.avisos_de_chamada


def test_falar_mensagens_novas_por_lugar_e_sem_depender_do_som(j, monkeypatch):
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    sons = []
    monkeypatch.setattr(jm, "bipe", lambda t, *a: sons.append(t))
    c = j.indice[("t1", "20")]
    j._abrir_conversa(c)
    ativa = [True]
    j.IsActive = lambda: ativa[0]

    def chega(id_, conversa, data):
        k = j.indice[("t1", conversa)]
        j.b.publicar(ev.MensagemNova(msg(id_, "oi", conversa=conversa,
                                         data=data), k))

    def falou(id_, conversa, data):
        ditas.clear()
        chega(id_, conversa, data)
        return any("oi" in t for t in ditas)
    for k in ("falar_novas", "falar_novas_outras_conversas",
              "falar_novas_fora_do_telezapp"):
        j.cfg.set(k, False)
    assert not falou("a1", "20", AGORA + 400)        # aberta, tudo desligado
    j.cfg.set("falar_novas", True)
    assert falou("a2", "20", AGORA + 401)             # conversa aberta
    assert not falou("a3", "10", AGORA + 402)         # outra: ainda nao
    j.cfg.set("falar_novas_outras_conversas", True)
    assert falou("a4", "10", AGORA + 403) and "Nova mensagem em" in ditas[0]
    # sem foco: so vale a opcao de fora do TeleZapp
    ativa[0] = False
    assert not falou("a5", "20", AGORA + 404)
    assert not falou("a6", "10", AGORA + 405)
    j.cfg.set("falar_novas_fora_do_telezapp", True)
    j.cfg.set("falar_novas", False)
    j.cfg.set("falar_novas_outras_conversas", False)
    assert falou("a7", "20", AGORA + 406) and falou("a8", "10", AGORA + 407)


def test_porcentagem_falada_no_download_segue_a_opcao(j):
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    chave = ("t1", "20", "7")

    def baixar(passo, percentuais):
        j.cfg.set("midias_passo_progresso", passo)
        j.abrindo, j.progresso_falado = chave, 0
        ditas.clear()
        for p in percentuais:
            j.b.publicar(ev.ProgressoMidia("t1", "20", "7", p))
        return ditas[:]
    todos = list(range(0, 101))
    assert baixar(25, todos) == ["25 por cento", "50 por cento",
                                 "75 por cento"]
    assert baixar(10, todos) == ["%d por cento" % n for n in range(10, 100, 10)]
    assert len(baixar(1, todos)) == 99
    assert baixar(0, todos) == []                      # desligado
    assert baixar(20, [3, 41, 97]) == ["40 por cento", "80 por cento"]


def test_transcricao_e_falada_inteira_manual_e_automatica(
        j, monkeypatch, tmp_path):
    x, chamadas = _ia_pronta(j, monkeypatch, tmp_path)
    longo = "palavra " * 600                       # bem acima de 1500 letras
    from telezapp.nucleo.ia import servico as servico_ia
    monkeypatch.setattr(servico_ia, "executar", lambda *a, **k: servico_ia
                        .Resultado(longo.strip(), "OpenAI", "gpt"))
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j.cfg.set("ia_consentimento", ["openai"])
    j._ia_processar(x)
    assert ditas[-1] == "Transcrição: " + longo.strip()
    # automatica: tambem inteira, mesmo com "falar mensagens novas" desligado
    j.cfg.set("falar_novas", False)
    j.cfg.set("falar_novas_outras_conversas", False)
    y = m.Mensagem("t1", "20", "8", tipo=m.VOZ, data=AGORA + 300, autor="Ana")
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [y]))
    ditas.clear()
    j._ia_pronto(y, "audio", servico_ia.Resultado(longo.strip(), "OpenAI",
                                                  "gpt"), None, True)
    assert ditas == ["Transcrição: " + longo.strip()]


def test_aplicar_pacote_de_sons_troca_os_sons_dos_eventos(j):
    from telezapp.acessibilidade import fala
    from telezapp.nucleo import pacotes_de_som as pk
    assert j.cfg.get("pacote_de_sons") == "padrao"
    assert fala.acao_do_som("nova") == ("padrao", "")
    j._aplicar_opcao("sons_pacotes", {"ativo": "telezapp",
                                      "desativados": {"telezapp": ["erro"]},
                                      "erros": []})
    assert j.cfg.get("pacote_de_sons") == "telezapp"
    assert fala.acao_do_som("nova")[0] == "arquivo"
    assert fala.acao_do_som("erro") == ("nenhum", "")
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j._aplicar_opcao("sons_pacotes", {"ativo": "padrao", "desativados": {},
                                      "erros": ["Não consegui importar x."]})
    assert fala.acao_do_som("nova") == ("padrao", "")
    assert ditas == ["Não consegui importar x."]
    assert "Sons" in __import__("telezapp.nucleo.configuracoes",
                                fromlist=["x"]).categorias()
    fala.definir_sons({})


def test_status_aparece_so_no_filtro_e_responde_em_particular(j):
    sid = "status:ana@s.whatsapp.net"
    c = m.Conversa("t1", sid, "Status de Ana", "whatsapp", "status",
                   data=AGORA + 50, nao_lidas=2)
    j.indice[c.chave] = c
    j._ordenar()
    j._preencher_conversas()
    assert "Status de Ana, WhatsApp, 2 não vistos" not in "".join(
        j.lista_conv.itens)                      # fora de "Todas"
    j.filtro_tipo = "status"
    j._ordenar()
    j._preencher_conversas()
    assert j.lista_conv.itens == ["Status de Ana, WhatsApp, 2 não vistos"]
    # menu: so abrir e apagar daqui
    assert [r for r, _ in j._opcoes_da_conversa(c)] == [
        "Abrir", "Apagar status..."]
    j._abrir_conversa(c)
    x = m.Mensagem("t1", sid, "S1", autor="Ana", texto="viajando",
                   data=AGORA + 50, remetente="ana@s.whatsapp.net")
    j.b.publicar(ev.MensagensCarregadas("t1", sid, [x]))
    j.estados["t1"] = ev.CONECTADA
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    # escrever responde ao status selecionado
    j.lista_msgs.SetSelection(j.mapa.index("S1"))
    j.caixa.SetValue("que lindo")
    j._enviar_texto()
    assert ("status", "S1", "que lindo") in j.contas.p.pedidos
    assert j.caixa.GetValue() == "" and "Resposta enviada a Ana" in ditas[-1]
    # arquivo e gravacao nao valem no status
    j._anexar_arquivo()
    assert "só dá para responder com texto" in ditas[-1]


def test_previa_de_link_recebido_so_com_a_opcao_ligada(j, monkeypatch):
    from telezapp.nucleo import previa_links as pl

    class Sincrono:
        def __init__(self, target=None, args=(), **k):
            self.target = target

        def start(self):
            if "_tocar" not in getattr(self.target, "__name__", ""):
                self.target()
    monkeypatch.setattr(jm.threading, "Thread", Sincrono)
    monkeypatch.setattr(jm.wx, "CallAfter", lambda f, *a: f(*a),
                        raising=False)
    buscados = []
    monkeypatch.setattr(pl, "buscar", lambda url: buscados.append(url) or {
        "url": url, "titulo": "Exemplo", "descricao": "D", "site": "ex.com"})
    c = j.indice[("t1", "20")]
    try:
        j.cfg.set("previa_receber", False)
        j._carregar_previa_de_links()
        j.b.publicar(ev.MensagemNova(msg("p1", "olha https://ex.com/a",
                                         conversa="20", data=AGORA + 700), c))
        assert buscados == []
        j.cfg.set("previa_receber", True)
        j._carregar_previa_de_links()
        j.b.publicar(ev.MensagemNova(msg("p2", "olha https://ex.com/a",
                                         conversa="20", data=AGORA + 701), c))
        assert buscados == ["https://ex.com/a"]
        guardada = j.banco.mensagens("t1", "20", 50)
        x = [y for y in guardada if y.id == "p2"][0]
        assert m.extras_de(x)["previa"]["titulo"] == "Exemplo"
        # mensagem minha, sem link ou que ja tem previa: nao busca
        buscados.clear()
        j.b.publicar(ev.MensagemNova(msg("p3", "sem link", conversa="20",
                                         data=AGORA + 702), c))
        j.b.publicar(ev.MensagemNova(msg("p4", "https://ex.com/b",
                                         conversa="20", minha=True,
                                         data=AGORA + 703), c))
        assert buscados == []
    finally:
        pl.definir(False, False)


def test_postar_status_escolhe_conta_e_chama_o_provedor(j, monkeypatch):
    from telezapp.interface import publicar_status as ui
    publicados = []
    j.contas.p.PODE_PUBLICAR_STATUS = True
    j.contas.p.publicar_status = lambda texto, anexo, publico: \
        publicados.append((texto, anexo, publico))
    j.estados["t1"] = ev.CONECTADA
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)

    class Dialogo:
        resultado = {"conta_id": "t1", "texto": "bom dia", "anexo": None,
                     "publico": "todos"}

        def __init__(self, pai, contas, escolher):
            Dialogo.contas = contas

        def ShowModal(self):
            return jm.wx.ID_OK

        def Destroy(self):
            pass
    monkeypatch.setattr(jm, "DialogoPublicarStatus", Dialogo)
    j._postar_status()
    assert publicados == [("bom dia", None, "todos")]
    assert Dialogo.contas[0][0] == "t1" and "Publicando" in ditas[-1]
    # sem conta conectada que publique: avisa
    j.estados["t1"] = ev.DESCONECTADA
    j._postar_status()
    assert "Nenhuma conta conectada publica status" in ditas[-1]
    assert len(publicados) == 1


def test_avanco_do_envio_no_titulo_na_barra_e_na_fala(j):
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j.cfg.set("midias_passo_progresso", 25)
    j._abrir_conversa(j.indice[("t1", "20")])
    nome = j.indice[("t1", "20")].nome
    for p in (0, 10, 30, 55, 80):
        j.b.publicar(ev.ProgressoEnvio("t1", "20", p))
    assert j.GetTitle().endswith("enviando mídia 80%")
    assert ditas == ["25 por cento", "50 por cento", "75 por cento"]
    # chegou: o titulo volta ao normal e o proximo envio fala de novo
    j.b.publicar(ev.ProgressoEnvio("t1", "20", 100))
    assert "enviando" not in j.GetTitle() and not j.progresso_envios
    ditas.clear()
    j.b.publicar(ev.ProgressoEnvio("t1", "20", 30))
    assert ditas == ["25 por cento"]
    # a falha limpa o avanco; a fala desligada nao fala, mas o titulo mostra
    j.b.publicar(ev.EnvioFalhou("t1", "20", "", "sem conexão", tipo="foto"))
    assert not j.progresso_envios
    j.cfg.set("midias_passo_progresso", 0)
    ditas.clear()
    j.b.publicar(ev.ProgressoEnvio("t1", "20", 60))
    assert ditas == [] and "enviando mídia 60%" in j.GetTitle()
    # duas conversas ao mesmo tempo
    j.b.publicar(ev.ProgressoEnvio("t1", "10", 20))
    assert j.GetTitle().endswith("enviando 2 mídias")


def test_reacao_a_mensagem_minha_toca_o_som_proprio(j, monkeypatch):
    sons = []
    monkeypatch.setattr(jm, "bipe", lambda t, *a: sons.append(t))
    j.fala.falar = lambda t, interromper=False: None
    j._abrir_conversa(j.indice[("t1", "20")])
    minha = msg("31", "oi", conversa="20", minha=True)
    outra = msg("32", "oi", conversa="20")
    m.atualizar_extras(minha, reacoes=[{"id": "x", "quem": "Ana",
                                        "emoji": "👍"}])
    j.b.publicar(ev.MensagemAtualizada("t1", "20", minha, "reacao", "Ana",
                                       "👍"))
    assert sons == ["reacao_recebida"]
    # tirar a reacao (emoji vazio), a minha propria e reacao a mensagem de
    # outra pessoa: sem som
    j.b.publicar(ev.MensagemAtualizada("t1", "20", minha, "reacao", "Ana", ""))
    j.b.publicar(ev.MensagemAtualizada("t1", "20", minha, "reacao", "Você",
                                       "❤"))
    j.b.publicar(ev.MensagemAtualizada("t1", "20", outra, "reacao", "Ana",
                                       "👍"))
    assert sons == ["reacao_recebida"]
    # conversa silenciada e fechada: nada (aberta, a pessoa esta lendo)
    j._fechar_conversa()
    j.indice[("t1", "20")].silenciada_ate = 2 ** 31 - 1
    j.b.publicar(ev.MensagemAtualizada("t1", "20", minha, "reacao", "Bia",
                                       "😂"))
    assert sons == ["reacao_recebida"]


def test_mencao_ou_resposta_num_grupo_toca_o_som_proprio(j, monkeypatch):
    sons = []
    monkeypatch.setattr(jm, "bipe", lambda t, *a: sons.append(t))
    j.fala.falar = lambda t, interromper=False: None
    grupo = m.Conversa("t1", "30", "Grupo X", "telegram", "grupo",
                       data=AGORA + 10)
    j.indice[grupo.chave] = grupo

    def chega(id_, citou=False, resposta_a="", minha=False, conv=grupo):
        x = msg(id_, "oi", conversa=conv.id, minha=minha,
                data=AGORA + 800 + int(id_))
        x.resposta_a = resposta_a
        if citou:
            m.atualizar_extras(x, citou_voce=True)
        j.b.publicar(ev.MensagemNova(x, conv))
        return x
    chega("41")                                   # grupo comum
    assert sons == ["nova_grupo"]
    sons.clear()
    chega("42", citou=True)                       # me mencionaram
    assert sons == ["mencao_ou_resposta"]         # no lugar do comum
    sons.clear()
    # responderam a uma mensagem minha (guardada)
    minha = msg("43", "minha", conversa="30", minha=True, data=AGORA + 700)
    j.b.publicar(ev.MensagensCarregadas("t1", "30", [minha]))
    sons.clear()
    chega("44", resposta_a="43")
    assert sons == ["mencao_ou_resposta"]
    sons.clear()
    chega("45", resposta_a="42")                  # resposta a mensagem alheia
    assert sons == ["nova_grupo"]
    # conversa com uma pessoa: nunca
    sons.clear()
    chega("48", citou=True, conv=j.indice[("t1", "20")])
    assert sons == ["nova"]
    # grupo silenciado e fechado: mudo
    sons.clear()
    grupo.silenciada_ate = 2 ** 31 - 1
    chega("49", citou=True)
    assert sons == []


def test_enter_chega_a_caixa_e_ela_envia_pelo_evento_de_enter(j):
    j._abrir_conversa(j.indice[("t1", "20")])
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [msg("5", "oi",
                                                          conversa="20")]))
    # a janela deixa o Enter passar (o leitor de tela o ve na caixa)
    j.caixa.SetValue("primeira")
    j.caixa.SetFocus()
    enter = Tecla(wx_falso.WXK_RETURN)
    j._char_hook(enter)
    assert enter.pulou
    assert ("enviar", "20", "primeira", "") in j.contas.p.pedidos
    # a caixa e criada com TE_PROCESS_ENTER
    assert j.caixa.estilo & wx_falso.TE_PROCESS_ENTER
    # Shift+Enter quebra a linha, sem enviar
    j.caixa.SetValue("a")
    j.caixa.SetFocus()
    t = Tecla(wx_falso.WXK_RETURN, shift=True)
    j._tecla_caixa(t)
    assert not t.pulou
    assert j.caixa.GetValue() == "a\n"
    assert ("enviar", "20", "a", "") not in j.contas.p.pedidos
    # outra tecla segue para o controle
    t = Tecla(ord("x"))
    j._tecla_caixa(t)
    assert t.pulou


# ------------------------------------------------ mensagens temporarias
def test_mensagens_temporarias_vencidas_somem_daqui(j):
    vencida = msg("1", "some", data=AGORA - 100)
    vencida.expira = time.time() - 5
    valida = msg("2", "fica", data=AGORA - 90)
    valida.expira = time.time() + 3600
    comum = msg("3", "normal", data=AGORA - 80)
    j.banco.salvar_mensagens([vencida, valida, comum])
    j.cache[("t1", "10")] = [vencida, valida, comum]
    j._apagar_expiradas(repetir=False)
    assert [x.id for x in j.banco.mensagens("t1", "10")] == ["2", "3"]
    assert [x.id for x in j.cache[("t1", "10")]] == ["2", "3"]
    assert j.banco.foi_limpa("t1", "10", "1")      # nao volta na sincronia
    # com a opcao desligada, a vencida fica
    outra = msg("4", "vencida", data=AGORA - 70)
    outra.expira = time.time() - 5
    j.banco.salvar_mensagens([outra])
    j.cfg.set("temporarias_apagar_aqui", False)
    j._apagar_expiradas(repetir=False)
    assert "4" in [x.id for x in j.banco.mensagens("t1", "10")]


def test_titulo_mostra_o_prazo_das_mensagens_temporarias(j):
    j.lista_conv.SetSelection(0)
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    assert "temporárias" not in j.GetTitle()
    j.indice[("t1", "10")].temporaria_s = 604800
    j._atualizar_titulo()
    assert "mensagens temporárias: 1 semana" in j.GetTitle()
    j.indice[("t1", "10")].temporaria_s = 0
    j._atualizar_titulo()
    assert "temporárias" not in j.GetTitle()


# ------------------------------------------------ autores e pulo no audio
def test_autores_achados_entram_na_lista_e_na_fala(j):
    anon = m.Mensagem("t1", "10", "9", autor="", minha=False,
                      data=AGORA + 9, texto="oi",
                      remetente="101198187253781@lid")
    outro = m.Mensagem("t1", "10", "8", autor="", minha=False,
                       data=AGORA + 8, texto="e eu", remetente="55@lid")
    j.cache[("t1", "10")] = [outro, anon]
    j._quem_cache[("t1", "10", "55@lid")] = "velho"
    j.b.publicar(ev.AutoresAtualizados(
        "t1", "10", {"101198187253781@lid": "Bia"}))
    assert anon.autor == "Bia" and outro.autor == ""
    assert j._quem_cache == {}        # a fala e a lista refazem o nome


def test_pular_no_audio_que_toca_ao_fundo(j):
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)

    class Motor:
        terminou = False
        posicao = 12.0
        duracao = 39.0

        def __init__(self):
            self.pulos = []

        def avancar(self, delta):
            self.pulos.append(delta)
            self.posicao += delta

    j._pular_audio(5)
    assert ditas == ["Nenhum áudio tocando."]
    motor = Motor()
    j.audio = (("t1", "10", "1"), motor)
    j._pular_audio(-5)
    j._pular_audio(30)
    assert motor.pulos == [-5, 30]
    assert ditas[-1] == "0:37 de 0:39"
    motor.terminou = True
    j._pular_audio(5)
    assert ditas[-1] == "Nenhum áudio tocando."
    j.audio = None


# ------------------------------------------------ barras de progresso
class _BarraFalsa:
    criadas = []

    def __init__(self, pai, titulo, texto="", ao_cancelar=None, falar=None):
        self.titulo, self.ao_cancelar = titulo, ao_cancelar
        self.texto, self.falar = texto, falar
        self.passos, self.fechada = [], False
        _BarraFalsa.criadas.append(self)

    def mostrar(self):
        self.mostrada = True

    def atualizar(self, percentual=None, texto=None):
        self.passos.append((percentual, texto))

    def fechar(self):
        self.fechada = True


def test_atualizar_mostra_a_barra_e_fecha_no_fim(j, monkeypatch):
    _BarraFalsa.criadas.clear()
    monkeypatch.setattr(jm, "JanelaDeProgresso", _BarraFalsa)
    monkeypatch.setattr(jm.instalacao, "pasta_do_programa",
                        lambda: r"C:\x\TeleZapp")
    monkeypatch.setattr(jm.atualizador, "pasta_de_espera",
                        lambda p: r"C:\x\TeleZapp.atualizacao")

    def baixar(lanc, pasta, progresso, abrir=None, cancelado=None):
        progresso(50, 100)
        progresso(100, 100)
        return "arquivo.zip"

    def extrair(arquivo, pasta, progresso=None):
        progresso(1, 2)
        progresso(2, 2)
        return "nova"
    aplicado = []
    monkeypatch.setattr(jm.atualizador, "baixar", baixar)
    monkeypatch.setattr(jm.atualizador, "extrair", extrair)
    monkeypatch.setattr(jm.atualizador, "aplicar",
                        lambda programa, nova: aplicado.append((programa,
                                                                nova)))
    j.Close = lambda *a, **k: True
    lanc = jm.atualizacao.Lancamento("2026.11.1.0", "", "p", False,
                                     "TeleZapp.zip", "u", "h", 100)
    j._atualizar(lanc)
    for _ in range(200):                  # o trabalho roda numa thread
        if aplicado:
            break
        time.sleep(0.02)
    barra = _BarraFalsa.criadas[0]
    assert barra.titulo.startswith("Atualizando") and barra.mostrada
    pcts = [p for p, _ in barra.passos if p is not None]
    assert pcts == sorted(pcts) and pcts[-1] == 100 and 45 in pcts
    assert barra.fechada and aplicado == [(r"C:\x\TeleZapp", "nova")]


def test_atualizar_cancelado_fecha_a_barra_sem_trocar_nada(j, monkeypatch):
    _BarraFalsa.criadas.clear()
    monkeypatch.setattr(jm, "JanelaDeProgresso", _BarraFalsa)
    monkeypatch.setattr(jm.instalacao, "pasta_do_programa",
                        lambda: r"C:\x\TeleZapp")
    monkeypatch.setattr(jm.atualizador, "pasta_de_espera",
                        lambda p: r"C:\x\TeleZapp.atualizacao")

    def baixar(lanc, pasta, progresso, abrir=None, cancelado=None):
        _BarraFalsa.criadas[0].ao_cancelar()        # a pessoa cancelou
        assert cancelado()
        raise jm.atualizador.ErroAtualizacao("Atualização cancelada.")
    aplicado, ditas = [], []
    monkeypatch.setattr(jm.atualizador, "baixar", baixar)
    monkeypatch.setattr(jm.atualizador, "aplicar",
                        lambda *a: aplicado.append(a))
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    lanc = jm.atualizacao.Lancamento("2026.11.1.0", "", "p", False,
                                     "TeleZapp.zip", "u", "h", 100)
    j._atualizar(lanc)
    for _ in range(200):
        if j._atualizando is False:
            break
        time.sleep(0.02)
    assert _BarraFalsa.criadas[0].fechada and aplicado == []
    assert ditas[-1] == "Atualização cancelada."
    assert j._atualizando is False


def test_download_pedido_so_abre_a_barra_se_demora_e_fecha_no_fim(
        j, monkeypatch):
    _BarraFalsa.criadas.clear()
    monkeypatch.setattr(jm, "JanelaDeProgresso", _BarraFalsa)
    agora = [100.0]
    monkeypatch.setattr(jm.time, "monotonic", lambda: agora[0])
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j.abrindo = ("t1", "10", "7")
    j.b.publicar(ev.ProgressoMidia("t1", "10", "7", 5))
    assert _BarraFalsa.criadas == []         # ainda nao passou de 1 segundo
    agora[0] = 101.5
    j.b.publicar(ev.ProgressoMidia("t1", "10", "7", 40))
    barra = _BarraFalsa.criadas[0]
    assert barra.titulo == "Baixando mídia" and barra.passos[-1][0] == 40
    assert callable(barra.ao_cancelar)
    j.b.publicar(ev.ProgressoMidia("t1", "10", "7", 60))
    assert barra.passos[-1][0] == 60 and len(_BarraFalsa.criadas) == 1
    assert not [d for d in ditas if "por cento" in d]   # a barra e o aviso
    j.b.publicar(ev.MidiaBaixada("t1", "10", "7", cancelada=True))
    assert barra.fechada and j._barras == {}


def test_barra_de_download_cancela_e_a_opcao_desliga(j, monkeypatch):
    _BarraFalsa.criadas.clear()
    monkeypatch.setattr(jm, "JanelaDeProgresso", _BarraFalsa)
    agora = [10.0]
    monkeypatch.setattr(jm.time, "monotonic", lambda: agora[0])
    cancelados = []
    j.midias = types.SimpleNamespace(
        baixando=lambda c: True, cancelar=lambda c: cancelados.append(c))
    j.abrindo = ("t1", "10", "7")
    j.b.publicar(ev.ProgressoMidia("t1", "10", "7", 1))
    agora[0] = 12.0
    j.b.publicar(ev.ProgressoMidia("t1", "10", "7", 30))
    _BarraFalsa.criadas[0].ao_cancelar()
    assert cancelados == [("t1", "10", "7")]
    j.b.publicar(ev.MidiaBaixada("t1", "10", "7", cancelada=True))
    # opcao desligada: nenhuma barra, o avanco so vai para o titulo e a fala
    _BarraFalsa.criadas.clear()
    j.cfg.set("barra_de_progresso", False)
    j.abrindo = ("t1", "10", "8")
    j.b.publicar(ev.ProgressoMidia("t1", "10", "8", 1))
    agora[0] = 20.0
    j.b.publicar(ev.ProgressoMidia("t1", "10", "8", 50))
    assert _BarraFalsa.criadas == []


def test_envio_grande_abre_a_barra_e_fecha_no_fim_ou_na_falha(j, monkeypatch):
    _BarraFalsa.criadas.clear()
    monkeypatch.setattr(jm, "JanelaDeProgresso", _BarraFalsa)
    agora = [50.0]
    monkeypatch.setattr(jm.time, "monotonic", lambda: agora[0])
    j.b.publicar(ev.ProgressoEnvio("t1", "20", 3))
    agora[0] = 52.0
    j.b.publicar(ev.ProgressoEnvio("t1", "20", 30))
    barra = _BarraFalsa.criadas[0]
    assert barra.titulo == "Enviando arquivo" and barra.ao_cancelar is None
    j.b.publicar(ev.ProgressoEnvio("t1", "20", 100))
    assert barra.fechada and j._barras == {}
    # outro envio que falha no meio tambem fecha a barra
    agora[0] = 60.0
    j.b.publicar(ev.ProgressoEnvio("t1", "20", 2))
    agora[0] = 62.0
    j.b.publicar(ev.ProgressoEnvio("t1", "20", 40))
    segunda = _BarraFalsa.criadas[1]
    j.b.publicar(ev.EnvioFalhou("t1", "20", "arquivo", "sem conexão",
                                devolver_texto=False, tipo=m.DOCUMENTO))
    assert segunda.fechada and j._barras == {}


class _DialogoFalso:
    resposta = None

    def __init__(self, *a, **k):
        pass

    def SetYesNoCancelLabels(self, *a):
        pass

    def ShowModal(self):
        return self.resposta

    def Destroy(self):
        pass


def _ortografia_pronta(j, monkeypatch, resposta):
    from telezapp.interface import janela as modulo
    from testes.test_ortografia import CorretorFalso
    _DialogoFalso.resposta = resposta
    monkeypatch.setattr(modulo.wx, "MessageDialog", _DialogoFalso,
                        raising=False)
    j._corretor_ort = CorretorFalso({"goistaria": ["gostaria"]})
    j.cfg.set("ortografia_ao_enviar", True)
    j._abrir_conversa(j.indice[("t1", "20")])
    j.estados["t1"] = ev.CONECTADA


def test_enviar_com_aviso_de_ortografia_pode_enviar_assim_mesmo(
        j, monkeypatch):
    _ortografia_pronta(j, monkeypatch, wx_falso.ID_NO)
    j.caixa.SetValue("eu goistaria")
    j._enviar_texto()
    assert ("enviar", "20", "eu goistaria", "") in j.contas.p.pedidos


def test_enviar_com_aviso_de_ortografia_cancelar_mantem_a_caixa(
        j, monkeypatch):
    _ortografia_pronta(j, monkeypatch, wx_falso.ID_CANCEL)
    j.caixa.SetValue("eu goistaria")
    j._enviar_texto()
    assert j.caixa.GetValue() == "eu goistaria"
    assert not any(p[0] == "enviar" for p in j.contas.p.pedidos)


def test_enviar_sem_a_opcao_nao_consulta_o_corretor(j, monkeypatch):
    _ortografia_pronta(j, monkeypatch, wx_falso.ID_CANCEL)
    j.cfg.set("ortografia_ao_enviar", False)
    j.caixa.SetValue("eu goistaria")
    j._enviar_texto()
    assert ("enviar", "20", "eu goistaria", "") in j.contas.p.pedidos


def test_menus_mostram_o_atalho_e_a_opcao_esconde(j):
    assert j.itens["ir_caixa"].rotulo.endswith("\tCtrl+E")
    assert j.atalhos.efetivo("ir_caixa") == "Ctrl+E"
    assert j.botao_enviar.GetLabel() == "&Enviar (Enter)"
    assert j.botao_anexar.GetLabel() == "Anexar e enviar arquivo (Ctrl+Shift+A)"
    j._aplicar_opcao("mostrar_atalhos", False)
    assert "\t" not in j.itens["ir_caixa"].rotulo
    assert j.botao_enviar.GetLabel() == "&Enviar"
    # os atalhos seguem valendo, pela tabela de aceleracao
    assert len(j.tabela_de_aceleracao.entradas) > 10
    j._aplicar_opcao("mostrar_atalhos", True)
    assert j.itens["ir_caixa"].rotulo.endswith("\tCtrl+E")
    assert len(j.tabela_de_aceleracao.entradas) > 10     # vale sempre


def test_atalho_personalizado_vai_ao_menu_ao_controle_e_a_config(j):
    j._aplicar_opcao("atalhos", {"ir_caixa": "Ctrl+Alt+W", "anexar": ""})
    assert j.itens["ir_caixa"].rotulo.endswith("\tCtrl+Alt+W")
    assert "\t" not in j.itens["anexar"].rotulo      # tirado de proposito
    assert j.botao_anexar.GetLabel() == "Anexar e enviar arquivo"
    assert j.cfg.get("atalhos") == {"ir_caixa": "Ctrl+Alt+W", "anexar": ""}
    assert j.atalhos.dono("Ctrl+Alt+W").chave == "ir_caixa"


def test_toda_funcao_de_menu_esta_no_registro_de_atalhos(j):
    assert set(j.itens) <= set(j.atalhos.acoes)
    assert "mostrar_janela" in j.atalhos.acoes
    # nenhum padrao repetido entre as funcoes
    usados = [c for _, c in j.atalhos.todos() if c]
    assert len(usados) == len(set(usados))


class GravadorFalso:
    criados = []

    def __init__(self, pasta, origem=None, maximo_segundos=0):
        self.pasta, self.origem = pasta, origem
        self.cancelado = False
        GravadorFalso.criados.append(self)

    pausado = False
    decorrido = 4.0
    microfone_disponivel = True

    def pausar(self):
        self.pausado = True

    def continuar(self):
        self.pausado = False

    def iniciar(self):
        pass

    def parar(self):
        from telezapp.midia.gravador import Gravacao
        return Gravacao(self.arquivo, 3.0, -6.0)

    def cancelar(self):
        self.cancelado = True


def _preparar_gravacao_rapida(j, monkeypatch, tmp_path):
    import os
    ogg = tmp_path / "voz-1.ogg"
    with open(os.path.join(os.path.dirname(__file__), "amostras",
                           "voz.ogg"), "rb") as f:
        ogg.write_bytes(f.read())
    GravadorFalso.criados = []
    GravadorFalso.arquivo = str(ogg)
    monkeypatch.setattr(jm, "Gravador", GravadorFalso)
    monkeypatch.setattr(jm.time, "sleep", lambda s: None)
    _abrir_com_caixa(j)


def test_atalho_de_gravar_inicia_e_o_segundo_aperto_envia(j, monkeypatch,
                                                           tmp_path):
    from telezapp.midia.gravador import MICROFONE
    _preparar_gravacao_rapida(j, monkeypatch, tmp_path)
    j.caixa.SetValue("rascunho que fica")
    j._gravar_rapido(MICROFONE)
    assert len(GravadorFalso.criados) == 1 and j._gravacao_rapida
    assert not [p for p in j.contas.p.pedidos if p[0] == "arquivo"]
    j._gravar_rapido(MICROFONE)              # o mesmo atalho: para e envia
    assert j._gravacao_rapida is None
    pedido = [p for p in j.contas.p.pedidos if p[0] == "arquivo"][-1]
    assert pedido[2] == m.VOZ and pedido[4] == ""
    assert j.caixa.GetValue() == "rascunho que fica"


def test_esc_descarta_a_gravacao_do_atalho(j, monkeypatch, tmp_path):
    from telezapp.midia.gravador import MICROFONE
    _preparar_gravacao_rapida(j, monkeypatch, tmp_path)
    j._gravar_rapido(MICROFONE)
    j.caixa.SetFocus()
    j._char_hook(Tecla(wx_falso.WXK_ESCAPE))
    assert j._gravacao_rapida is None
    assert GravadorFalso.criados[0].cancelado
    assert not [p for p in j.contas.p.pedidos if p[0] == "arquivo"]


def test_fechar_a_conversa_descarta_a_gravacao_do_atalho(j, monkeypatch,
                                                          tmp_path):
    from telezapp.midia.gravador import SOM_INTERNO
    _preparar_gravacao_rapida(j, monkeypatch, tmp_path)
    j._gravar_rapido(SOM_INTERNO)
    j._fechar_conversa()
    assert j._gravacao_rapida is None and GravadorFalso.criados[0].cancelado


class EventoDeFechar:
    def __init__(self, pode_vetar=True):
        self.vetado = False
        self.pode = pode_vetar

    def CanVeto(self):
        return self.pode

    def Veto(self):
        self.vetado = True


class BandejaFalsa:
    removida = False

    def RemoveIcon(self):
        self.removida = True

    def Destroy(self):
        pass


def test_fechar_com_segundo_plano_so_minimiza_a_janela(j, monkeypatch):
    from telezapp.interface import bandeja
    monkeypatch.setattr(bandeja, "criar", lambda janela: BandejaFalsa())
    j._aplicar_opcao("segundo_plano", True)
    assert isinstance(j._bandeja, BandejaFalsa)
    escondida = []
    j.Iconize = lambda v=True: escondida.append(v)
    j.fala.falar = lambda t, interromper=False: escondida.append(t)
    evento = EventoDeFechar()
    j._ao_fechar(evento)
    assert evento.vetado and escondida[0] is True
    assert "segundo plano" in escondida[1]
    assert j.vivo is not False                 # a janela nao foi destruida


def test_sair_encerra_mesmo_com_segundo_plano(j, monkeypatch):
    from telezapp.interface import bandeja
    monkeypatch.setattr(bandeja, "criar", lambda janela: BandejaFalsa())
    j._aplicar_opcao("segundo_plano", True)
    j._sair()
    assert j._saindo and j.vivo is False       # Close() foi chamado
    evento = EventoDeFechar()
    j.Hide = lambda: None
    j.Destroy = lambda: None
    j._ao_fechar(evento)
    assert not evento.vetado


def test_fechar_sem_a_opcao_encerra(j):
    j.Hide = lambda: None
    j.Destroy = lambda: None
    evento = EventoDeFechar()
    j._ao_fechar(evento)
    assert not evento.vetado


def test_fechamento_do_windows_nao_pode_ser_vetado(j, monkeypatch):
    from telezapp.interface import bandeja
    monkeypatch.setattr(bandeja, "criar", lambda janela: BandejaFalsa())
    j._aplicar_opcao("segundo_plano", True)
    j.Hide = lambda: None
    j.Destroy = lambda: None
    evento = EventoDeFechar(pode_vetar=False)
    j._ao_fechar(evento)
    assert not evento.vetado


def test_iniciar_com_windows_liga_a_entrada(j, monkeypatch):
    chamadas = []
    monkeypatch.setattr(jm.inicializacao, "definir",
                        lambda ligado, *a, **k: chamadas.append(ligado) or True)
    j._aplicar_opcao("iniciar_com_windows", True)
    j._aplicar_opcao("iniciar_com_windows", False)
    assert chamadas == [True, False]
    assert j.cfg.get("iniciar_com_windows") is False


def test_atalho_global_e_registrado_e_avisa_se_estiver_ocupado(j):
    registros, ditas = [], []
    j.RegisterHotKey = lambda id_, mods, tecla: registros.append(
        (mods, tecla)) or True
    j.UnregisterHotKey = lambda id_: None
    j._aplicar_opcao("atalhos", {"mostrar_janela": "Ctrl+Alt+Z"})
    assert registros == [(wx_falso.MOD_CONTROL | wx_falso.MOD_ALT, ord("Z"))]
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j.RegisterHotKey = lambda *a: False          # outro programa usa
    j._aplicar_opcao("atalhos", {"mostrar_janela": "Ctrl+Alt+Y"})
    assert "outro programa" in ditas[-1]


def test_menu_midias_agrupa_as_escolhas_e_o_atalho_fala_portugues(j):
    # as escolhas soltas (Só quando eu abrir...) ficam sob um titulo claro
    assert j.atalhos.acoes["baixar_demanda"].rotulo == (
        "Quando baixar as mídias: Só quando eu abrir")
    assert j.atalhos.acoes["estilo1"].rotulo.startswith(
        "Como cada mensagem é lida: ")
    assert j.itens["audio_voltar"].rotulo.endswith(
        " (Ctrl+Shift+Seta para a esquerda)")
    assert j.itens["vel_mais"].rotulo.endswith(
        " (Ctrl+Shift+Seta para cima)")
    assert j.itens["audio_voltar_mais"].rotulo.endswith(
        "	Ctrl+Shift+Page Up")
    assert "Left" not in j.itens["audio_voltar"].rotulo


def test_por_padrao_enter_quebra_a_linha_e_control_enter_envia(j):
    j.cfg.set("enter_envia", False)
    j._abrir_conversa(j.indice[("t1", "20")])
    j.estados["t1"] = ev.CONECTADA
    j.caixa.SetValue("linha um")
    j.caixa.SetFocus()
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    assert j.caixa.GetValue() == "linha um\n"
    assert not [p for p in j.contas.p.pedidos if p[0] == "enviar"]
    # o Control Enter e a funcao Enviar a mensagem digitada (do menu)
    assert j.atalhos.efetivo("enviar_msg") == "Ctrl+Enter"
    j._enviar_texto()
    assert ("enviar", "20", "linha um", "") in j.contas.p.pedidos
    j._rotular_controles()
    assert j.botao_enviar.GetLabel() == "&Enviar (Ctrl+Enter)"


def test_com_a_opcao_enter_envia_e_o_botao_diz_enter(j):
    j.cfg.set("enter_envia", False)
    j._rotular_controles()
    assert j.botao_enviar.GetLabel() == "&Enviar (Ctrl+Enter)"
    j._aplicar_opcao("enter_envia", True)
    j._rotular_controles()
    assert j.botao_enviar.GetLabel() == "&Enviar (Enter)"
    assert j._tecla_de_enviar() == "Enter"
    j.cfg.set("enter_envia", False)
    assert j._tecla_de_enviar() == "Control Enter"
    j._aplicar_opcao("atalhos", {"enviar_msg": "Ctrl+Shift+Enter"})
    assert j._tecla_de_enviar() == "Control Shift Enter"


def test_control_enter_na_caixa_envia_e_shift_enter_quebra_a_linha(j):
    j.cfg.set("enter_envia", False)
    j._abrir_conversa(j.indice[("t1", "20")])
    j.estados["t1"] = ev.CONECTADA
    j.caixa.SetValue("oi")
    j.caixa.SetFocus()
    j._tecla_caixa(Tecla(wx_falso.WXK_RETURN, shift=True))
    assert j.caixa.GetValue() == "oi\n"
    assert not [p for p in j.contas.p.pedidos if p[0] == "enviar"]
    j._tecla_caixa(Tecla(wx_falso.WXK_RETURN, ctrl=True))
    assert ("enviar", "20", "oi", "") in j.contas.p.pedidos
    # se o Control Enter for de outra funcao, ele so quebra a linha
    j._aplicar_opcao("atalhos", {"enviar_msg": "Ctrl+Shift+Enter"})
    j.caixa.SetValue("de novo")
    j._tecla_caixa(Tecla(wx_falso.WXK_RETURN, ctrl=True))
    assert j.caixa.GetValue() == "de novo\n"


def test_enter_numa_enquete_abre_a_janela_e_o_voto_vai_ao_servico(
        j, monkeypatch):
    j._abrir_conversa(j.indice[("t1", "20")])
    enquete = m.Mensagem("t1", "20", "9", tipo=m.OUTRO, data=AGORA,
                         texto="enquete: Qual dia?")
    m.atualizar_extras(enquete, enquete={
        "pergunta": "Qual dia?", "opcoes": ["Sexta", "Sábado"], "maximo": 1})
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [enquete]))
    j.lista_msgs.SetSelection(j.mapa.index("9"))
    assert "enquete: Qual dia?, 2 opções" in j.lista_msgs.itens[
        j.mapa.index("9")]
    abertas = []
    monkeypatch.setattr(jm.ui_enquete, "abrir",
                        lambda *a: abertas.append(a))
    votos, atualizacoes = [], []
    j.contas.p.PODE_VOTAR = True
    j.contas.p.votar_enquete = lambda msg, esc: votos.append(
        (msg.id, list(esc)))
    j.contas.p.atualizar_enquete = lambda msg: atualizacoes.append(msg.id)
    j.estados["t1"] = ev.CONECTADA
    j._detalhes_ou_marcador()                       # Enter na enquete
    assert len(abertas) == 1 and atualizacoes == ["9"]
    pai, obter, pode, votar, atualizar, fala = abertas[0]
    assert pode is True and obter().id == "9"
    votar([1])
    assert votos == [("9", [1])]
    atualizar()
    assert atualizacoes == ["9", "9"]
    # sem conexao: so leitura
    j.estados["t1"] = ev.DESCONECTADA
    j._abrir_enquete()
    assert abertas[-1][2] is False


def test_ver_enquete_numa_mensagem_comum_avisa(j):
    j._abrir_conversa(j.indice[("t1", "20")])
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [
        msg("1", "oi", conversa="20")]))
    j.lista_msgs.SetSelection(j.mapa.index("1"))
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j._abrir_enquete()
    assert "não é uma enquete" in ditas[-1]


def test_criar_enquete_pelo_menu_vai_ao_servico(j, monkeypatch):
    _abrir_com_caixa(j)
    pedidos = []
    j.contas.p.PODE_CRIAR_ENQUETE = True
    j.contas.p.criar_enquete = lambda *a: pedidos.append(a)
    j.estados["t1"] = ev.CONECTADA
    monkeypatch.setattr(jm.ui_nova_enquete, "pedir_enquete",
                        lambda pai, servico, fala: (
                            "Qual dia?", ["Sexta", "Sábado"], False, True))
    j._nova_enquete()
    assert pedidos == [("20", "Qual dia?", ["Sexta", "Sábado"], False, True)]
    # cancelou: nada vai
    pedidos.clear()
    monkeypatch.setattr(jm.ui_nova_enquete, "pedir_enquete",
                        lambda pai, servico, fala: None)
    j._nova_enquete()
    assert pedidos == []
    # servico que nao cria enquete
    j.contas.p.PODE_CRIAR_ENQUETE = False
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j._nova_enquete()
    assert "não cria enquetes" in ditas[-1]


def _enquete_minha(j, id_="9"):
    j._abrir_conversa(j.indice[("t1", "20")])
    enquete = m.Mensagem("t1", "20", id_, minha=True, tipo=m.OUTRO,
                         data=AGORA, texto="enquete: Q")
    m.atualizar_extras(enquete, enquete={
        "pergunta": "Q", "opcoes": ["A", "B"], "maximo": 1})
    j.b.publicar(ev.MensagensCarregadas("t1", "20", [enquete]))
    return enquete


def test_sons_dos_votos_em_enquete(j, monkeypatch):
    sons = []
    monkeypatch.setattr(jm, "bipe", lambda tipo, *a: sons.append(tipo))
    enquete = _enquete_minha(j)
    sons.clear()
    j.b.publicar(ev.MensagemAtualizada("t1", "20", enquete, "enquete", "Bia"))
    assert sons == ["voto_enquete"]
    sons.clear()
    j.b.publicar(ev.MensagemAtualizada("t1", "20", enquete, "enquete",
                                       "Você"))
    assert sons == ["voto_enviado"]
    sons.clear()                                    # sem saber quem: mudo
    j.b.publicar(ev.MensagemAtualizada("t1", "20", enquete, "enquete", ""))
    assert sons == []
    # enquete de outra pessoa: o voto de terceiros nao toca
    alheia = m.Mensagem("t1", "20", "8", tipo=m.OUTRO, data=AGORA)
    m.atualizar_extras(alheia, enquete={"pergunta": "Q", "opcoes": ["A", "B"]})
    j.b.publicar(ev.MensagemAtualizada("t1", "20", alheia, "enquete", "Bia"))
    assert sons == []


def test_sons_de_esconder_e_voltar_da_bandeja(j, monkeypatch):
    sons = []
    monkeypatch.setattr(jm, "bipe", lambda tipo, *a: sons.append(tipo))
    from testes.test_janela import BandejaFalsa
    j._bandeja = BandejaFalsa()
    j.Iconize = lambda v=True: None
    j.IsShown = lambda: False
    j.Show = lambda: None
    j.IsIconized = lambda: False
    j.Raise = lambda: None
    j._esconder_na_bandeja()
    j._mostrar_da_bandeja()
    assert sons == ["escondido", "voltou"]


def test_gravar_por_atalho_toca_o_som_de_gravando_e_o_de_parada(
        j, monkeypatch, tmp_path):
    from telezapp.midia.gravador import MICROFONE
    sons = []
    monkeypatch.setattr(jm, "bipe", lambda tipo, *a: sons.append(tipo))
    _preparar_gravacao_rapida(j, monkeypatch, tmp_path)
    j._gravar_rapido(MICROFONE)
    j._gravar_rapido(MICROFONE)
    assert sons[0] == "gravando" and "gravacao_parada" in sons
    assert "nova" not in sons          # nao e o som de mensagem recebida


def test_slots_de_atalho_das_funcoes_novas(j):
    for chave in ("gravar_pausa", "gravar_descartar", "abrir_atalhos",
                  "enviar_msg", "ver_enquete", "nova_enquete",
                  "esconder_janela", "mostrar_janela", "ortografia",
                  "gravar_mic", "gravar_som"):
        assert chave in j.atalhos.acoes, chave
    # as novas nascem sem atalho, prontas para receber um
    assert j.atalhos.efetivo("gravar_pausa") == ""
    j._aplicar_opcao("atalhos", {"gravar_pausa": "Ctrl+Alt+P"})
    assert j.itens["gravar_pausa"].rotulo.endswith("	Ctrl+Alt+P")


def test_pausar_e_descartar_a_gravacao_por_atalho(j, monkeypatch, tmp_path):
    from telezapp.midia.gravador import MICROFONE
    _preparar_gravacao_rapida(j, monkeypatch, tmp_path)
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j._pausar_gravacao_rapida()                      # sem gravar: avisa
    assert "Nenhuma gravação" in ditas[-1]
    j._gravar_rapido(MICROFONE)
    g = GravadorFalso.criados[0]
    j._pausar_gravacao_rapida()
    assert g.pausado and "pausada em 0:04" in ditas[-1]
    j._pausar_gravacao_rapida()
    assert not g.pausado and "Gravando de novo" in ditas[-1]
    j._descartar_gravacao_rapida()
    assert g.cancelado and j._gravacao_rapida is None
    assert not [p for p in j.contas.p.pedidos if p[0] == "arquivo"]


def test_restaurar_backup_aplica_o_mapa_de_atalhos_nos_menus(j):
    assert j.atalhos.efetivo("responder") == "Ctrl+Shift+R"
    j._fim_da_restauracao({"atalhos": {"responder": "Alt+R"}}, [], "")
    assert j.atalhos.efetivo("responder") == "Alt+R"
    assert j.itens["responder"].rotulo.endswith("\tAlt+R")
    assert j.cfg.get("atalhos") == {"responder": "Alt+R"}


def test_enter_envia_vem_ligado_de_fabrica(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path))
    assert config.Config().get("enter_envia") is True
    assert config.PADROES["enter_envia"] is True


# --------------------------------------- novo grupo, canal, chamada, contato
def test_novo_grupo_cria_na_conta_e_abre_a_conversa(j, monkeypatch):
    from telezapp.interface import criar_conversa as ui
    criados = []
    j.contas.p.CRIA = ("grupo", "canal")
    j.contas.p.criar_conversa = lambda tipo, nome, desc, gente, topicos: \
        criados.append((tipo, nome, desc, gente, topicos)) or (
            True, "", "20")
    j.estados["t1"] = ev.CONECTADA
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)

    class Dialogo:
        def __init__(self, pai, tipo, contas):
            Dialogo.vistos = (tipo, contas)

        def ShowModal(self):
            return jm.wx.ID_OK

        def escolhido(self):
            return "t1", "Equipe", "Sobre", ["@bia"], True

        def Destroy(self):
            pass

    class SemThread:
        def __init__(self, target=None, args=(), **k):
            self.alvo, self.args = target, args

        def start(self):
            self.alvo(*self.args)
    monkeypatch.setattr(ui, "DialogoCriarConversa", Dialogo)
    monkeypatch.setattr(jm.threading, "Thread", SemThread)
    j._nova_conversa("grupo")
    assert criados == [("grupo", "Equipe", "Sobre", ["@bia"], True)]
    assert Dialogo.vistos[0] == "grupo" and Dialogo.vistos[1][0][0] == "t1"
    assert any("Grupo Equipe criado" in t for t in ditas)
    assert j.atual == ("t1", "20")            # abriu a conversa criada
    # a conta nao cria comunidades: avisa e nao abre a janela
    j._nova_conversa("comunidade")
    assert ditas[-1] == "Nenhuma conta conectada cria comunidades."
    assert len(criados) == 1


def test_novo_grupo_que_falha_avisa_o_motivo(j, monkeypatch):
    from telezapp.interface import criar_conversa as ui
    j.contas.p.CRIA = ("grupo",)
    j.contas.p.criar_conversa = lambda *a: (False, "O Telegram recusou.", "")
    j.estados["t1"] = ev.CONECTADA
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)

    class Dialogo:
        def __init__(self, *a):
            pass

        def ShowModal(self):
            return jm.wx.ID_OK

        def escolhido(self):
            return "t1", "Equipe", "", [], False

        def Destroy(self):
            pass

    class SemThread:
        def __init__(self, target=None, args=(), **k):
            self.alvo, self.args = target, args

        def start(self):
            self.alvo(*self.args)
    monkeypatch.setattr(ui, "DialogoCriarConversa", Dialogo)
    monkeypatch.setattr(jm.threading, "Thread", SemThread)
    j._nova_conversa("grupo")
    assert ditas[-1] == "O Telegram recusou."
    assert j.atual is None


def test_nova_chamada_escolhe_a_pessoa_e_liga(j, monkeypatch):
    from telezapp.interface import contatos
    vistas = []
    ligou = []
    j._provedor_de_chamada = lambda conta_id: j.contas.p
    j.estados["t1"] = ev.CONECTADA
    monkeypatch.setattr(contatos, "dialogo_nova_chamada",
                        lambda pai, contas, buscar: vistas.append(contas) or
                        ("t1", "bruno", None))
    j._ligar_para = lambda conv: ligou.append(conv.id)
    j._nova_chamada()
    assert [c for c, _ in vistas[0]] == ["t1"]
    assert ligou == ["20"]                         # Bruno ja existia
    # ninguem faz chamadas: avisa
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j._provedor_de_chamada = lambda conta_id: None
    j._nova_chamada()
    assert ditas[-1] == "Nenhuma conta conectada faz chamadas."


def test_novo_contato_guarda_e_avisa(j, monkeypatch):
    from telezapp.interface import contatos
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    monkeypatch.setattr(contatos, "adicionar_contato",
                        lambda pai, banco, contas, falar: (
                            ("t1", "99@s.whatsapp.net"),
                            "Contato Bia adicionado."))
    renomeou = []
    j._renomear_pelos_contatos = lambda: renomeou.append(True)
    j._novo_contato()
    assert renomeou == [True] and ditas[-1] == "Contato Bia adicionado."
    monkeypatch.setattr(contatos, "adicionar_contato",
                        lambda *a: None)
    j._novo_contato()
    assert renomeou == [True]                      # cancelou: nada muda


def grupo(id, nome, nao_lidas, data):
    return m.Conversa("t1", id, nome, "telegram", "grupo",
                      nao_lidas=nao_lidas, data=data)


def test_grupo_com_topicos_fica_um_so_na_lista_e_pergunta_o_topico(j):
    j.b.publicar(ev.ConversasAtualizadas("t1", [
        conv("10", "Ana", data=AGORA - 10),
        grupo("-100", "Equipe", 0, AGORA - 5),
        grupo("-100#1", "Equipe › Geral", 2, AGORA - 5),
        grupo("-100#9", "Equipe › Avisos", 1, AGORA - 50)]))
    assert j.lista_conv.itens == ["Equipe, Telegram, 3 não lidas",
                                  "Ana, Telegram"]
    wx_falso.escolha_lista[0] = 1               # o segundo: Avisos
    try:
        j._abrir_conversa(j.indice[("t1", "-100")])
    finally:
        wx_falso.escolha_lista[0] = 0
    assert j.atual == ("t1", "-100#9")
    j._fechar_conversa()
    wx_falso.resposta_lista[0] = wx_falso.ID_CANCEL
    try:
        j._abrir_conversa(j.indice[("t1", "-100")])    # desistiu
    finally:
        wx_falso.resposta_lista[0] = wx_falso.ID_OK
    assert j.atual is None


def test_esc_no_topico_volta_para_a_lista_de_topicos_do_grupo(j):
    j.b.publicar(ev.ConversasAtualizadas("t1", [
        grupo("-100", "Equipe", 0, AGORA - 5),
        grupo("-100#1", "Equipe › Geral", 0, AGORA - 5),
        grupo("-100#9", "Equipe › Avisos", 0, AGORA - 50)]))
    wx_falso.escolha_lista[0] = 1                  # Avisos
    try:
        j._abrir_conversa(j.indice[("t1", "-100")])
        assert j.atual == ("t1", "-100#9")
        wx_falso.escolha_lista[0] = 0              # Esc: escolhe o Geral
        j._esc_da_conversa()
        assert j.atual == ("t1", "-100#1")         # outro topico, mesmo grupo
        wx_falso.resposta_lista[0] = wx_falso.ID_CANCEL
        j._esc_da_conversa()                       # Esc na lista de topicos
    finally:
        wx_falso.escolha_lista[0] = 0
        wx_falso.resposta_lista[0] = wx_falso.ID_OK
    assert j.atual is None
    assert j.lista_conv.GetSelection() == j._chaves_conv.index(("t1", "-100"))


def test_gerenciar_contatos_busca_por_nome_e_telefone(monkeypatch):
    from telezapp.interface import contatos

    class Banco:
        def contatos(self, conta_id=None):
            return [("t1", "1", "Ana Souza", "+5551999998888"),
                    ("t1", "2", "Bruno", "+5511988887777"),
                    ("t1", "3", "Édson", "")]

    class Contas:
        def lista(self):
            return [("t1", "telegram", "Fábio")]

        def provedor(self, cid):
            return None
    g = contatos.GerenciadorContatos(None, Banco(), Contas(), lambda: None,
                                     lambda t: None)
    assert len(g._itens) == 3
    g.busca.SetValue("edson")                 # sem acento nem maiuscula
    g._preencher(g._chave_selecionada())
    assert [c[2] for c in g._itens] == ["Édson"]
    g.busca.SetValue("1198888")               # parte do telefone
    g._preencher()
    assert [c[2] for c in g._itens] == ["Bruno"]
    g.busca.SetValue("zzz")
    g._preencher()
    assert g._itens == [] and g.lista.itens == ["Nenhum contato encontrado"]
    g.busca.SetValue("")
    g._preencher()
    assert len(g._itens) == 3


def test_tranca_local_de_versao_anterior_e_desfeita_ao_carregar(j):
    """O celular e quem tranca: a tranca feita aqui, de antes, e esvaziada e a
    conversa volta a destrancada; a que o celular trancou continua."""
    local = m.Conversa("t1", "5551@s.whatsapp.net", "Ana", "whatsapp",
                       "privada", trancada=True)
    celular = m.Conversa("t1", "5552@s.whatsapp.net", "Bia", "whatsapp",
                         "privada", trancada=True)
    j.cfg.set("trancadas_locais", [list(local.chave)])
    j._juntar_conversas("t1", [local, celular])
    assert not local.trancada and celular.trancada
    assert j.cfg.get("trancadas_locais") == []
    assert not hasattr(j, "_trancar_conversa")


def test_atalho_do_som_com_microfone_grava_os_dois(j, monkeypatch, tmp_path):
    from telezapp.midia.gravador import SOM_E_MICROFONE
    _preparar_gravacao_rapida(j, monkeypatch, tmp_path)
    assert "gravar_som_mic" in j.atalhos.acoes
    assert j.atalhos.efetivo("gravar_som_mic") == "Ctrl+Shift+B"
    j._gravar_rapido(SOM_E_MICROFONE)
    assert GravadorFalso.criados[0].origem == SOM_E_MICROFONE
    j._gravar_rapido(SOM_E_MICROFONE)                 # o mesmo atalho: envia
    assert j._gravacao_rapida is None
    pedido = [p for p in j.contas.p.pedidos if p[0] == "arquivo"][-1]
    assert pedido[2] == m.VOZ


def test_atalho_do_som_com_microfone_avisa_se_nao_ha_microfone(
        j, monkeypatch, tmp_path):
    from telezapp.midia.gravador import SOM_E_MICROFONE
    _preparar_gravacao_rapida(j, monkeypatch, tmp_path)
    GravadorFalso.microfone_disponivel = False
    try:
        ditas = []
        j.fala.falar = lambda t, interromper=False: ditas.append(t)
        j._gravar_rapido(SOM_E_MICROFONE)
    finally:
        GravadorFalso.microfone_disponivel = True
    assert any("Não achei um microfone" in t for t in ditas)
    j._terminar_gravacao_rapida(enviar=False)


class _DialogoDeAtualizacao:
    """A janela de versao nova de mentira: devolve o que a pessoa escolheu."""
    abertas = 0
    escolha = "nao"

    def __init__(self, pai, lanc, atual, pode, pasta):
        type(self).abertas += 1
        self.escolha = type(self).escolha

    def ShowModal(self):
        return 1

    def Destroy(self):
        pass


def _oferecer_atualizacao(j, monkeypatch, manual, nao_avisar=None):
    """Mostra a versao nova; `nao_avisar` e o que a pessoa escolhe na pergunta
    que vem depois do Nao (True: "Nao me avise mais sobre essa versao";
    False: "Talvez mais tarde"). Devolve as versoes perguntadas."""
    import telezapp.interface.atualizacao as janela_atualizacao
    monkeypatch.setattr(janela_atualizacao, "DialogoAtualizacao",
                        _DialogoDeAtualizacao)
    perguntadas = []

    def pergunta(pai, versao):
        perguntadas.append(versao)
        return bool(nao_avisar)
    monkeypatch.setattr(janela_atualizacao, "perguntar_nao_avisar", pergunta)
    lanc = jm.atualizacao.Lancamento("2099.1.1.0", "", "p", False)
    j._resultado_atualizacao(lanc, "", manual)
    return perguntadas


def test_atualizacao_talvez_mais_tarde_avisa_de_novo_ao_abrir(j, monkeypatch):
    _DialogoDeAtualizacao.abertas = 0
    _DialogoDeAtualizacao.escolha = "nao"
    assert _oferecer_atualizacao(j, monkeypatch, False,
                                 nao_avisar=False) == ["2099.1.1.0"]
    assert not j.cfg.get("atualizacao_ignorada")
    _oferecer_atualizacao(j, monkeypatch, False, nao_avisar=False)  # abriu
    assert _DialogoDeAtualizacao.abertas == 2


def test_atualizacao_nao_me_avise_mais_para_de_avisar_dessa_versao(
        j, monkeypatch):
    _DialogoDeAtualizacao.abertas = 0
    _DialogoDeAtualizacao.escolha = "nao"
    _oferecer_atualizacao(j, monkeypatch, False, nao_avisar=True)
    assert j.cfg.get("atualizacao_ignorada") == "2099.1.1.0"
    perguntadas = _oferecer_atualizacao(j, monkeypatch, False, nao_avisar=True)
    assert _DialogoDeAtualizacao.abertas == 1 and perguntadas == []  # calado
    # pedindo pela mao, a janela abre; "talvez mais tarde" volta a avisar
    _oferecer_atualizacao(j, monkeypatch, True, nao_avisar=False)
    assert _DialogoDeAtualizacao.abertas == 2
    assert not j.cfg.get("atualizacao_ignorada")
    _oferecer_atualizacao(j, monkeypatch, False, nao_avisar=False)
    assert _DialogoDeAtualizacao.abertas == 3


def test_atualizacao_so_pergunta_quando_a_escolha_e_nao(j, monkeypatch):
    _DialogoDeAtualizacao.escolha = "pagina"
    assert _oferecer_atualizacao(j, monkeypatch, False) == []
    _DialogoDeAtualizacao.escolha = "nao"


def test_slot_de_atalho_dos_dispositivos_de_som_nasce_sem_atalho(j):
    assert "dispositivos_som" in j.atalhos.acoes
    assert j.atalhos.efetivo("dispositivos_som") == ""
    j._aplicar_opcao("atalhos", {"dispositivos_som": "Ctrl+Alt+D"})
    assert j.itens["dispositivos_som"].rotulo.endswith("	Ctrl+Alt+D")


def test_escolher_dispositivos_guarda_e_vale_para_tocar_e_gravar(
        j, monkeypatch):
    from telezapp.midia import dispositivos
    monkeypatch.setattr(
        jm.ui_dispositivos, "escolher",
        lambda pai, mic, saida: ("Fone (USB)", "Alto-falantes"))
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    try:
        j._escolher_dispositivos()
        assert j.cfg.get("chamada_microfone") == "Fone (USB)"
        assert j.cfg.get("chamada_saida") == "Alto-falantes"
        assert dispositivos.microfone() == "Fone (USB)"
        assert dispositivos.saida() == "Alto-falantes"
        assert any("Alto-falantes" in t for t in ditas)
    finally:
        dispositivos.definir("", "")


def test_escolher_dispositivos_cancelado_nao_muda_nada(j, monkeypatch):
    from telezapp.midia import dispositivos
    monkeypatch.setattr(jm.ui_dispositivos, "escolher",
                        lambda pai, mic, saida: None)
    j._escolher_dispositivos()
    assert j.cfg.get("chamada_microfone") == ""
    assert dispositivos.microfone() == ""


class CharDigitado(Tecla):
    def __init__(self, lista, letra, ctrl=False):
        super().__init__(ord(letra), ctrl=ctrl)
        self.lista = lista

    def GetEventObject(self):
        return self.lista

    def GetUnicodeKey(self):
        return self.codigo


def test_digitar_na_lista_pula_pelo_padrao(j):
    assert j.cfg.get("digitar_na_lista") == "pular"
    j.atual = ("t1", "c1")
    e = CharDigitado(j.lista_msgs, "a")
    j._digitou_na_lista(e)
    assert e.pulou                      # segue para a lista do Windows
    assert j.caixa.GetValue() == ""


def test_digitar_na_lista_de_mensagens_vai_para_a_caixa(j):
    j.cfg.set("digitar_na_lista", "campo")
    j.atual = ("t1", "c1")
    e = CharDigitado(j.lista_msgs, "o")
    j._digitou_na_lista(e)
    assert not e.pulou
    assert wx_falso._foco[0] is j.caixa
    assert j.caixa.GetValue() == "o"


def test_digitar_na_lista_de_conversas_vai_para_a_busca(j):
    j.cfg.set("digitar_na_lista", "campo")
    e = CharDigitado(j.lista_conv, "m")
    j._digitou_na_lista(e)
    assert not e.pulou
    assert wx_falso._foco[0] is j.campo_busca
    assert j.campo_busca.GetValue() == "m"


def test_digitar_na_lista_sem_conversa_aberta_ou_com_control_continua_pulando(
        j):
    j.cfg.set("digitar_na_lista", "campo")
    j.atual = None
    e = CharDigitado(j.lista_msgs, "a")
    j._digitou_na_lista(e)
    assert e.pulou
    j.atual = ("t1", "c1")
    e = CharDigitado(j.lista_msgs, "a", ctrl=True)
    j._digitou_na_lista(e)
    assert e.pulou


# --------------------------------------- IA: redigir, resumir e corrigir
class CofreFalso:
    def tem(self, p):
        return True

    def obter(self, p):
        return "CHAVE"


@pytest.fixture
def ia_texto(j, monkeypatch):
    """Janela com um provedor de texto ligado e a rede trocada por um
    resultado na hora."""
    from telezapp.nucleo.ia import servico as servico_ia
    j.cofre_ia = CofreFalso()
    j.cfg.set("ia_ordem", {"texto": ["gemini"]})
    j.cfg.set("ia_consentimento_texto", ["gemini"])
    chamadas = []

    j.ia_extras = []

    def falso(operacao, texto, ordem, chave_de, modelos, contexto="",
              enviar=None, tom="natural", destino="Brazilian Portuguese"):
        chamadas.append((operacao, texto, contexto))
        j.ia_extras.append((tom, destino))
        return servico_ia.Resultado("RESPOSTA", "Google Gemini", "m")

    monkeypatch.setattr(servico_ia, "executar_texto_em_ordem", falso)
    monkeypatch.setattr(jm.wx, "CallAfter", lambda f, *a: f(*a),
                        raising=False)

    class Linha:
        def __init__(self, alvo):
            self.alvo = alvo

        def start(self):
            self.alvo()
    monkeypatch.setattr(
        jm.threading, "Thread",
        lambda target=None, args=(), **k: Linha(lambda: target(*args)))
    monkeypatch.setattr(jm, "bipe", lambda *a: None)
    j.ditas = []
    j.fala.falar = lambda t, interromper=False: j.ditas.append(t)
    return chamadas


def test_corrigir_troca_o_texto_da_caixa(j, ia_texto):
    j.caixa.SetValue("ola tudo bem")
    j._ia_corrigir()
    assert ia_texto[0][:2] == ("corrigir", "ola tudo bem")
    assert j.caixa.GetValue() == "RESPOSTA"
    assert any("Texto corrigido" in t for t in j.ditas)


def test_corrigir_nao_troca_se_a_pessoa_mexeu_na_caixa(j, ia_texto,
                                                         monkeypatch):
    j.caixa.SetValue("ola")
    mostrados = []
    monkeypatch.setattr(jm.dialogos, "mostrar_texto",
                        lambda *a, **k: mostrados.append(a))
    from telezapp.nucleo.ia import servico as servico_ia

    def mexe(operacao, texto, *a, **k):
        j.caixa.SetValue("ola, e mais coisa")
        return servico_ia.Resultado("Olá", "Google Gemini", "m")
    monkeypatch.setattr(servico_ia, "executar_texto_em_ordem", mexe)
    j._ia_corrigir()
    assert j.caixa.GetValue() == "ola, e mais coisa" and mostrados


def test_ia_de_texto_sem_texto_ou_sem_provedor_avisa(j, monkeypatch):
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j.caixa.SetValue("")
    j._ia_corrigir()
    assert any("Não há texto" in t for t in ditas)
    abertas = []
    monkeypatch.setattr(j, "_configuracoes", lambda c: abertas.append(c))
    j.caixa.SetValue("oi")
    j._ia_corrigir()
    assert abertas == ["Inteligência artificial"]


def test_ia_de_texto_pede_consentimento_uma_vez(j, ia_texto, monkeypatch):
    j.cfg.set("ia_consentimento_texto", [])
    respostas = []
    monkeypatch.setattr(jm.wx, "MessageBox",
                        lambda *a, **k: respostas.append(a) or jm.wx.NO,
                        raising=False)
    j.caixa.SetValue("oi")
    j._ia_corrigir()
    assert respostas and not ia_texto          # recusou: nada foi enviado
    monkeypatch.setattr(jm.wx, "MessageBox",
                        lambda *a, **k: jm.wx.YES, raising=False)
    j._ia_corrigir()
    assert ia_texto and j.cfg.get("ia_consentimento_texto") == ["gemini"]


def test_redigir_manda_o_final_da_conversa_como_contexto(j, ia_texto):
    j.indice[("t1", "c1")] = conv("c1", "Ana")
    j.atual = ("t1", "c1")
    j.cache[j.atual] = [
        m.Mensagem("t1", "c1", "1", autor="Ana", texto="vai à festa?",
                   data=AGORA)]
    j.caixa.SetValue("diga que sim e pergunte a hora")
    j._ia_redigir()
    operacao, texto, contexto = ia_texto[0]
    assert operacao == "redigir" and "vai à festa?" in contexto
    assert j.caixa.GetValue() == "RESPOSTA"      # rascunho: nao envia
    assert not [p for p in j.contas.p.pedidos if p[0] == "texto"]


def test_resumir_mensagem_abre_o_resumo_numa_janela(j, ia_texto, monkeypatch):
    j.indice[("t1", "c1")] = conv("c1", "Ana")
    j.atual = ("t1", "c1")
    x = m.Mensagem("t1", "c1", "1", autor="Ana", texto="um textão",
                   data=AGORA)
    monkeypatch.setattr(j, "_mensagem_selecionada", lambda: x)
    mostrados = []
    monkeypatch.setattr(jm.dialogos, "mostrar_texto",
                        lambda *a, **k: mostrados.append(a))
    j._ia_resumir_mensagem()
    assert ia_texto[0][:2] == ("resumir_mensagem", "um textão")
    assert mostrados[0][2] == "RESPOSTA"


def test_resumir_conversa_manda_as_linhas_da_conversa(j, ia_texto,
                                                       monkeypatch):
    j.indice[("t1", "c1")] = conv("c1", "Ana")
    j.atual = ("t1", "c1")
    j.cache[j.atual] = [
        m.Mensagem("t1", "c1", "1", autor="Ana", texto="oi", data=AGORA),
        m.Mensagem("t1", "c1", "2", minha=True, texto="tudo bem?",
                   data=AGORA)]
    monkeypatch.setattr(jm.dialogos, "mostrar_texto", lambda *a, **k: None)
    j._ia_resumir_conversa()
    operacao, texto, _ = ia_texto[0]
    assert operacao == "resumir_conversa"
    assert "Ana: oi" in texto and "Você: tudo bem?" in texto


def test_slots_de_atalho_da_ia_de_texto_nascem_sem_atalho(j):
    for chave in ("ia_corrigir", "ia_redigir", "ia_resumir_msg",
                  "ia_resumir_conv"):
        assert chave in j.atalhos.acoes, chave
        assert j.atalhos.efetivo(chave) == ""


def test_redigir_usa_o_tom_da_opcao_e_o_da_escolha(j, ia_texto, monkeypatch):
    j.cfg.set("ia_tom", "formal")
    j.caixa.SetValue("peça desculpas")
    j._ia_redigir()
    assert j.ia_extras[-1][0] == "formal"
    monkeypatch.setattr(j, "_escolher_da_lista",
                        lambda *a: "descontraido")
    j.caixa.SetValue("peça desculpas")
    j._ia_redigir(escolher_tom=True)
    assert j.ia_extras[-1][0] == "descontraido"
    assert j.cfg.get("ia_tom") == "formal"       # a opção não muda
    monkeypatch.setattr(j, "_escolher_da_lista", lambda *a: None)
    j.caixa.SetValue("peça desculpas")
    antes = len(ia_texto)
    j._ia_redigir(escolher_tom=True)
    assert len(ia_texto) == antes                # cancelou: nada enviado


def test_traduzir_o_texto_digitado_lembra_o_idioma(j, ia_texto, monkeypatch):
    monkeypatch.setattr(j, "_escolher_da_lista", lambda *a: "Spanish")
    j.caixa.SetValue("bom dia")
    j._ia_traduzir_caixa()
    assert ia_texto[-1][:2] == ("traduzir", "bom dia")
    assert j.ia_extras[-1][1] == "Spanish"
    assert j.caixa.GetValue() == "RESPOSTA"
    assert j.cfg.get("ia_idioma_traducao") == "Spanish"


def test_traduzir_a_mensagem_selecionada_abre_a_traducao(j, ia_texto,
                                                         monkeypatch):
    x = m.Mensagem("t1", "c1", "1", autor="Ana", texto="hello", data=AGORA)
    monkeypatch.setattr(j, "_mensagem_selecionada", lambda: x)
    monkeypatch.setattr(j, "_escolher_da_lista", lambda *a: "French")
    mostrados = []
    monkeypatch.setattr(jm.dialogos, "mostrar_texto",
                        lambda *a, **k: mostrados.append(a))
    j._ia_traduzir_mensagem()
    assert ia_texto[-1][:2] == ("traduzir", "hello")
    assert j.ia_extras[-1][1] == "French" and mostrados[0][2] == "RESPOSTA"


def test_resumir_nao_lidas_so_manda_as_nao_lidas(j, ia_texto, monkeypatch):
    j.indice[("t1", "c1")] = conv("c1", "Ana")
    j.atual = ("t1", "c1")
    j.marcador_n = 2
    j.cache[j.atual] = [
        m.Mensagem("t1", "c1", str(i), autor="Ana", texto="msg%d" % i,
                   data=AGORA) for i in range(5)]
    monkeypatch.setattr(jm.dialogos, "mostrar_texto", lambda *a, **k: None)
    j._ia_resumir_nao_lidas()
    texto = ia_texto[-1][1]
    assert "msg4" in texto and "msg3" in texto and "msg2" not in texto
    j.marcador_n = 0
    j.indice[j.atual].nao_lidas = 0
    antes = len(ia_texto)
    j._ia_resumir_nao_lidas()
    assert len(ia_texto) == antes
    assert any("Não há mensagens não lidas" in t for t in j.ditas)


def test_slots_novos_da_ia_de_texto(j):
    for chave in ("ia_redigir_tom", "ia_traduzir", "ia_traduzir_msg",
                  "ia_resumir_nao_lidas"):
        assert chave in j.atalhos.acoes and j.atalhos.efetivo(chave) == ""


def test_entrar_em_grupo_por_link_segue_o_caminho_do_botao(j, monkeypatch):
    j.contas.p.ENTRA_POR_LINK = True
    j.estados["t1"] = ev.CONECTADA
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    entradas = []
    monkeypatch.setattr(j, "_entrar_no_grupo", lambda x, acao, prov:
                        entradas.append((x, acao, prov)))
    digitado = ["https://chat.whatsapp.com/AbCdEfGhIjKl"]

    class Pergunta:
        def __init__(self, *a, **k):
            pass

        def ShowModal(self):
            return jm.wx.ID_OK

        def GetValue(self):
            return digitado[0]

        def Destroy(self):
            pass
    monkeypatch.setattr(jm.wx, "TextEntryDialog", Pergunta, raising=False)
    j._entrar_por_link()
    assert entradas == [(None, {"codigo": "AbCdEfGhIjKl"}, j.contas.p)]
    digitado[0] = "isso nao e um convite"
    j._entrar_por_link()
    assert len(entradas) == 1
    assert "não parece um link" in ditas[-1]
    # conta que nao entra por link: avisa e nem pergunta
    j.contas.p.ENTRA_POR_LINK = False
    j._entrar_por_link()
    assert ditas[-1] == "Nenhuma conta conectada entra em grupos por link."


# ------------------------------------------------- marcar a conversa como lida
def _conversas_com_nao_lidas(j):
    a, b = conv("c1", "Zelda", nao_lidas=3), conv("c2", "Bia", nao_lidas=0)
    j.indice[a.chave], j.indice[b.chave] = a, b
    j._ordenar()
    j._preencher_conversas()
    return a, b


def test_marcar_conversa_como_lida_sem_abrir(j):
    a, _ = _conversas_com_nao_lidas(j)
    j._marcar_conversa_lida(a)
    assert a.nao_lidas == 0 and j.atual is None
    assert ("lida", "c1") in j.contas.p.pedidos
    assert not any("Zelda" in t and "não lida" in t for t in j.lista_conv.itens)


def test_marcar_como_lida_quando_nao_ha_nao_lidas_so_avisa(j):
    _, b = _conversas_com_nao_lidas(j)
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    j._marcar_conversa_lida(b)
    assert ("lida", "c2") not in j.contas.p.pedidos
    assert any("não tem mensagens não lidas" in t for t in ditas)


def test_menu_de_contexto_da_conversa_tem_marcar_como_lida(j):
    a, _ = _conversas_com_nao_lidas(j)
    rotulos = [r for r, _ in j._opcoes_da_conversa(a)]
    assert "Marcar como lida" in rotulos
    assert rotulos.index("Marcar como lida") < rotulos.index("Arquivar")


def test_slot_de_atalho_de_marcar_como_lida_nasce_sem_atalho(j):
    assert "marcar_lida" in j.atalhos.acoes
    assert j.atalhos.efetivo("marcar_lida") == ""
    j._aplicar_opcao("atalhos", {"marcar_lida": "Ctrl+Alt+L"})
    assert j.itens["marcar_lida"].rotulo.endswith("	Ctrl+Alt+L")


def test_selecao_em_massa_marca_como_lidas(j):
    a, b = _conversas_com_nao_lidas(j)
    c = conv("c3", "Caio", nao_lidas=2)
    j.indice[c.chave] = c
    j._ordenar()
    j._preencher_conversas()
    j.marc_conv = {a.chave, b.chave, c.chave}
    j.modo_conv = True
    rotulos = [r for r, _ in j._opcoes_em_massa_conv()]
    assert "Marcar 3 conversas como lidas" in rotulos
    j._massa_conversas("lidas")
    assert a.nao_lidas == 0 and c.nao_lidas == 0
    assert {("lida", "c1"), ("lida", "c3")} <= set(j.contas.p.pedidos)
    assert ("lida", "c2") not in j.contas.p.pedidos


def test_menu_ajuda_abre_a_pagina_do_projeto_e_o_feedback(j, monkeypatch):
    from telezapp import PAGINA_DE_RELATOS, PAGINA_DO_PROJETO
    abertos = []
    monkeypatch.setattr(jm.webbrowser, "open", lambda url: abertos.append(url) or True)
    assert "pagina_projeto" in j.itens and "feedback" in j.itens
    assert j.atalhos.efetivo("pagina_projeto") == ""        # slots sem atalho
    assert j.atalhos.efetivo("feedback") == ""
    j._abrir_na_internet(PAGINA_DO_PROJETO)
    j._abrir_na_internet(PAGINA_DE_RELATOS)
    assert abertos == [PAGINA_DO_PROJETO, PAGINA_DE_RELATOS]
    assert "Página do projeto" in j.itens["pagina_projeto"].rotulo
    assert "Feedback" in j.itens["feedback"].rotulo
    assert PAGINA_DE_RELATOS.startswith(PAGINA_DO_PROJETO)


def test_sem_navegador_o_endereco_e_mostrado(j, monkeypatch):
    avisos = []
    monkeypatch.setattr(jm.webbrowser, "open", lambda url: False)
    monkeypatch.setattr(jm.wx, "MessageBox",
                        lambda texto, *a, **k: avisos.append(texto),
                        raising=False)
    j._abrir_na_internet("https://exemplo.test/")
    assert avisos and "https://exemplo.test/" in avisos[0]


def test_reacoes_as_minhas_mensagens_entram_na_linha_da_conversa(j):
    j._aplicar_opcao("lista_conversas", {
        "ordem": ["nome", "servico", "nao_lidas", "previa", "reacoes",
                  "quem_reagiu"],
        "ocultos": ["servico", "nao_lidas", "previa", "quem_reagiu"]})
    minha = msg("7", "oi", minha=True, data=AGORA)
    j.b.publicar(ev.MensagemAtualizada("t1", "10", minha, "reacao", "Ana",
                                       "👍"))
    assert j.lista_conv.itens[0] == "Ana, 1 reação nova à sua mensagem"
    j.b.publicar(ev.MensagemAtualizada("t1", "10", minha, "reacao", "Bia",
                                       "❤"))
    assert j.lista_conv.itens[0] == "Ana, 2 reações novas às suas mensagens"
    # a minha propria reacao e a de quem tirou nao contam
    j.b.publicar(ev.MensagemAtualizada("t1", "10", minha, "reacao", "Você",
                                       "👍"))
    j.b.publicar(ev.MensagemAtualizada("t1", "10", minha, "reacao", "Ana",
                                       ""))
    assert j.reacoes_novas[("t1", "10")] == 2
    j._abrir_conversa(j.indice[("t1", "10")])      # ver a conversa zera
    assert ("t1", "10") not in j.reacoes_novas


def test_quem_reagiu_entra_na_linha_e_zera_ao_abrir(j):
    j._aplicar_opcao("lista_conversas", {
        "ordem": ["nome", "servico", "nao_lidas", "previa", "reacoes",
                  "quem_reagiu"],
        "ocultos": ["servico", "nao_lidas", "previa", "reacoes"]})
    minha = msg("7", "oi", minha=True, data=AGORA)
    j.b.publicar(ev.MensagemAtualizada("t1", "10", minha, "reacao", "Ana",
                                       "👍"))
    assert j.lista_conv.itens[0] == "Ana, Ana reagiu com 👍"
    j.b.publicar(ev.MensagemAtualizada("t1", "10", minha, "reacao", "Ana",
                                       "❤"))                 # mudou de emoji
    j.b.publicar(ev.MensagemAtualizada("t1", "10", minha, "reacao", "Bia",
                                       "😂"))
    assert j.lista_conv.itens[0] == "Ana, Ana (❤) e Bia (😂) reagiram"
    j._abrir_conversa(j.indice[("t1", "10")])
    assert ("t1", "10") not in j.quem_reagiu


def test_voz_apagada_pelo_autor_nao_toca(jm_midia, monkeypatch):
    j = jm_midia
    MotorFalso.criados = []
    monkeypatch.setattr(jm, "Reprodutor", MotorFalso)
    apagada = voz("5")
    m.atualizar_extras(apagada, apagada=True)
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [apagada]))
    j.midias.prontas[("t1", "10", "5")] = "/p/5.ogg"      # ainda no disco
    ditas = []
    j.fala.falar = lambda t, interromper=False: ditas.append(t)
    selecionar(j, "5")
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    j._abrir_midia(x=apagada)                  # Control O tambem
    assert not MotorFalso.criados and j.abertas == []
    assert "Esta mensagem foi apagada pelo autor." in ditas
    assert j._genero_ia(apagada) == ""         # nem transcrever


def test_apagar_para_todos_para_o_audio_e_tira_o_arquivo(jm_midia,
                                                        monkeypatch):
    j = jm_midia
    MotorFalso.criados = []
    monkeypatch.setattr(jm, "Reprodutor", MotorFalso)
    monkeypatch.setattr(jm.wx, "CallLater", lambda *a, **k: None,
                        raising=False)
    j.b.publicar(ev.MensagensCarregadas("t1", "10", [voz("5")]))
    j.midias.prontas[("t1", "10", "5")] = "/p/5.ogg"
    selecionar(j, "5")
    j._char_hook(Tecla(wx_falso.WXK_RETURN))
    assert MotorFalso.criados[0].tocando
    tiradas = []
    monkeypatch.setattr(jm.limpeza, "apagar_midia_da_mensagem",
                        lambda banco, *chave: tiradas.append(chave))
    apagada = voz("5")
    m.atualizar_extras(apagada, apagada=True)
    j.b.publicar(ev.MensagemAtualizada("t1", "10", apagada, "apagada"))
    assert MotorFalso.criados[0].fechado and j.audio is None
    assert tiradas == [("t1", "10", "5")]

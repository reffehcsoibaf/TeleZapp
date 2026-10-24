# SPDX-License-Identifier: GPL-3.0-or-later
"""O que a lista de conversas mostra e a ordem: regras, janela, banco e
backup."""
import sys

from testes import wx_falso

sys.modules["wx"] = wx_falso

from telezapp.armazenamento.banco import Banco                # noqa: E402
from telezapp.interface.lista_conversas import DialogoListaConversas  # noqa
from telezapp.nucleo import backup                            # noqa: E402
from telezapp.nucleo import lista_conversas as lc             # noqa: E402
from telezapp.nucleo import modelos as m                      # noqa: E402
from telezapp.nucleo.configuracoes import ModeloConfiguracoes  # noqa: E402

TODOS = {"ordem": ["nome", "servico", "nao_lidas", "previa"], "ocultos": []}


def conv(**k):
    base = dict(conta_id="t1", id="10", nome="Ana", servico="telegram",
                nao_lidas=3)
    base.update(k)
    return m.Conversa(**base)


def msg(texto="oi", minha=False, autor="", **k):
    return m.Mensagem("t1", "10", "1", autor=autor, minha=minha, texto=texto,
                      data=1000.0, **k)


# ---------------------------------------------------------------- regras
def test_normalizar_corrige_o_que_veio_guardado():
    assert lc.normalizar(None) == {
        "ordem": ["nome", "servico", "nao_lidas", "previa"],
        "ocultos": ["previa"]}                           # o padrao
    assert lc.normalizar({"ordem": ["previa", "x", "nome", "nome"],
                          "ocultos": ["y", "previa"]}) == {
        "ordem": ["previa", "nome", "servico", "nao_lidas"],
        "ocultos": ["previa"]}
    # tudo oculto deixaria a lista vazia: voltam todos
    assert lc.normalizar({"ordem": list(lc.CHAVES),
                          "ocultos": list(lc.CHAVES)})["ocultos"] == []
    assert lc.ativos({"ordem": ["servico", "nome", "previa", "nao_lidas"],
                      "ocultos": ["nome"]}) == ["servico", "previa",
                                                "nao_lidas"]


def test_nunca_deixa_a_lista_sem_item_ativado():
    lay = {"ordem": list(lc.CHAVES), "ocultos": ["servico", "nao_lidas",
                                                  "previa"]}
    novo, ativado = lc.alternar(lay, "nome")        # o unico ativado
    assert ativado is None and novo["ocultos"] == lay["ocultos"]
    novo, ativado = lc.alternar(lay, "previa")      # ligar sempre pode
    assert ativado is True and "previa" not in novo["ocultos"]
    novo, ativado = lc.alternar(novo, "nome")       # agora ha dois
    assert ativado is False and "nome" in novo["ocultos"]
    assert lc.alternar(lay, "x")[1] is None


def test_mover_troca_de_lugar_e_para_nas_pontas():
    lay = lc.normalizar(TODOS)
    novo, pos = lc.mover(lay, "previa", -1)
    assert pos == 2 and novo["ordem"] == ["nome", "servico", "previa",
                                          "nao_lidas"]
    assert lc.mover(lay, "nome", -1) == (lay, 0)
    assert lc.mover(lay, "previa", 1) == (lay, 3)
    assert lc.eh_padrao(lc.padrao()) and not lc.eh_padrao(novo)


def test_texto_do_item_diz_se_esta_ativado():
    lay = {"ordem": list(lc.CHAVES), "ocultos": ["previa"]}
    assert lc.texto_do_item(lay, "nome") == "Nome da conversa: ativado"
    assert lc.texto_do_item(lay, "previa") == \
        "Trecho da última mensagem: desativado"


# ---------------------------------------------------------------- linha
def test_linha_padrao_e_igual_a_de_sempre():
    assert lc.rotulo(conv()) == "Ana, Telegram, 3 não lidas"
    assert lc.rotulo(conv(nao_lidas=1)) == "Ana, Telegram, 1 não lida"
    assert lc.rotulo(conv(nao_lidas=0)) == "Ana, Telegram"
    assert lc.rotulo(conv(fixada=True, silenciada_ate=-1)) == (
        "Ana, Telegram, fixada, silenciada, 3 não lidas")
    assert lc.rotulo(conv(tipo="status")) == "Ana, Telegram, 3 não vistos"
    assert m.rotulo_conversa(conv()) == "Ana, Telegram, 3 não lidas"


def test_linha_na_ordem_escolhida_e_com_o_trecho():
    lay = {"ordem": ["previa", "nao_lidas", "nome", "servico"],
           "ocultos": []}
    assert lc.rotulo(conv(), lay, "Você: oi") == (
        "Você: oi, 3 não lidas, Ana, Telegram")
    # sem trecho conhecido, o item simplesmente nao aparece
    assert lc.rotulo(conv(), lay) == "3 não lidas, Ana, Telegram"


def test_marcas_ficam_depois_do_servico_ou_do_nome():
    marcas = dict(fixada=True)
    sem_servico = {"ordem": list(lc.CHAVES), "ocultos": ["servico",
                                                         "previa"]}
    assert lc.rotulo(conv(**marcas), sem_servico) == \
        "Ana, fixada, 3 não lidas"
    so_lidas = {"ordem": list(lc.CHAVES),
                "ocultos": ["nome", "servico", "previa"]}
    assert lc.rotulo(conv(**marcas), so_lidas) == "fixada, 3 não lidas"


def test_se_os_itens_ativados_nao_tem_nada_a_mostrar_vale_o_nome():
    so_lidas = {"ordem": list(lc.CHAVES),
                "ocultos": ["nome", "servico", "previa"]}
    assert lc.rotulo(conv(nao_lidas=0), so_lidas) == "Ana"
    so_trecho = {"ordem": list(lc.CHAVES),
                 "ocultos": ["nome", "servico", "nao_lidas"]}
    assert lc.rotulo(conv(), so_trecho, "") == "Ana"


# ---------------------------------------------------------------- trecho
def test_trecho_da_ultima_mensagem():
    assert lc.previa_da_mensagem(msg("oi\ntudo bem?")) == "oi tudo bem?"
    assert lc.previa_da_mensagem(msg("oi", minha=True)) == "Você: oi"
    assert lc.previa_da_mensagem(msg("oi", autor="Bia"), grupo=True) == \
        "Bia: oi"
    assert lc.previa_da_mensagem(msg("oi", autor="Bia")) == "oi"
    assert lc.previa_da_mensagem(msg("oi"), grupo=True, quem="Caio") == \
        "Caio: oi"
    foto = msg("", tipo=m.FOTO)
    assert lc.previa_da_mensagem(foto) == "foto"
    longa = lc.previa_da_mensagem(msg("a" * 200))
    assert len(longa) == lc.TAMANHO_DA_PREVIA and longa.endswith("…")
    assert lc.previa_da_mensagem(None) == ""


# ---------------------------------------------------------------- modelo
class Cfg:
    def __init__(self, **dados):
        self.dados = dados

    def get(self, chave, padrao=None):
        return self.dados.get(chave, padrao)


def test_modelo_guarda_a_lista_pendente_ate_aplicar():
    mod = ModeloConfiguracoes(Cfg())
    assert mod.lista_em_uso() == lc.padrao()
    novo = {"ordem": ["servico", "nome", "nao_lidas", "previa"],
            "ocultos": []}
    mod.lista_definir(novo)
    assert mod.lista_em_uso() == novo
    mod.lista_definir(lc.padrao())          # voltar ao atual desfaz
    assert mod.lista_pendente is None
    mod.lista_definir(novo)
    aplicadas = []
    mod.aplicar(lambda chave, valor: aplicadas.append((chave, valor)))
    assert aplicadas == [("lista_conversas", novo)]
    assert mod.lista_pendente is None


# ---------------------------------------------------------------- backup
def test_backup_so_leva_de_volta_uma_lista_valida():
    boas = backup.opcoes_validas({"lista_conversas": {
        "ordem": ["previa", "lixo"], "ocultos": ["nome", "servico",
                                                  "nao_lidas", "previa"]}})
    assert boas["lista_conversas"]["ordem"][0] == "previa"
    assert boas["lista_conversas"]["ocultos"] == []   # nao pode ficar vazia
    assert "lista_conversas" not in backup.opcoes_validas(
        {"lista_conversas": "texto"})
    assert "lista_conversas" in backup.EXTRAS


# ----------------------------------------------------------------- banco
def test_banco_devolve_a_ultima_mensagem_de_cada_conversa(tmp_path):
    banco = Banco(str(tmp_path / "t.db"))
    try:
        for conv_id, id_, data, texto in (
                ("10", "1", 100.0, "antiga"), ("10", "2", 200.0, "nova"),
                ("20", "7", 50.0, "outra conversa"),
                ("30", "5", 90.0, "empate A"), ("30", "6", 90.0,
                                                 "empate B")):
            banco.salvar_mensagens([m.Mensagem(
                "t1", conv_id, id_, texto=texto, data=data)])
        ultimas = banco.ultimas_mensagens()
        assert {k: v.texto for k, v in ultimas.items()} == {
            ("t1", "10"): "nova", ("t1", "20"): "outra conversa",
            ("t1", "30"): "empate B"}
    finally:
        banco.fechar()


# ---------------------------------------------------------------- janela
class Fala:
    def __init__(self):
        self.ditas = []

    def falar(self, texto, interromper=False):
        self.ditas.append(texto)


class Gravador:
    def __init__(self, valor):
        self.valor = valor

    def ler(self):
        return self.valor

    def gravar(self, novo):
        self.valor = novo


def dialogo(valor=None):
    g, fala = Gravador(valor), Fala()
    return DialogoListaConversas(None, g.ler, g.gravar, fala), g, fala


def test_dialogo_ativa_desativa_e_recusa_o_ultimo():
    d, g, fala = dialogo({"ordem": list(lc.CHAVES),
                          "ocultos": ["servico", "nao_lidas", "previa"]})
    assert d.lista.itens[0] == "Nome da conversa: ativado"
    d.alternar()                                   # o unico ativado
    assert fala.ditas[-1] == lc.MENSAGEM_DO_MINIMO
    assert "nome" not in g.valor["ocultos"]
    d.lista.SetSelection(3)
    d.alternar()                                   # liga o trecho
    assert fala.ditas[-1] == "ativado"
    assert "previa" not in g.valor["ocultos"]
    assert d.lista.itens[3] == "Trecho da última mensagem: ativado"


def test_dialogo_muda_a_ordem_e_restaura_o_padrao():
    d, g, fala = dialogo(lc.padrao())
    d.lista.SetSelection(2)
    d.mover(-1)
    assert g.valor["ordem"][:3] == ["nome", "nao_lidas", "servico"]
    assert d.lista.GetSelection() == 1
    assert fala.ditas[-1] == "Quantidade de mensagens não lidas, posição 2 " \
                             "de 4."
    d.lista.SetSelection(0)
    d.mover(-1)
    assert fala.ditas[-1] == "Já é o primeiro item."
    d.restaurar()
    assert lc.eh_padrao(g.valor) and d.lista.GetSelection() == 0
    assert not d.botoes["padrao"].habilitado \
        if hasattr(d.botoes["padrao"], "habilitado") else True

# SPDX-License-Identifier: GPL-3.0-or-later
"""O que a lista de mensagens mostra e a ordem: regras, linha, janela de
escolha, migracao do estilo antigo, configuracoes e backup."""
import sys

from testes import wx_falso

sys.modules["wx"] = wx_falso

from telezapp.interface.lista_conversas import DialogoListaConversas  # noqa
from telezapp.nucleo import backup                            # noqa: E402
from telezapp.nucleo import lista_mensagens as lm             # noqa: E402
from telezapp.nucleo import modelos as m                      # noqa: E402
from telezapp.nucleo.configuracoes import ModeloConfiguracoes  # noqa: E402

AGORA = 1_800_000_000.0


def msg(texto="oi", minha=False, autor="Ana", **k):
    base = dict(autor=autor, minha=minha, texto=texto, data=AGORA)
    base.update(k)
    return m.Mensagem("t1", "10", "1", **base)


def lay(**k):
    base = {"ordem": list(lm.CHAVES), "ocultos": [],
            "autor_so_quando_muda": False}
    base.update(k)
    return base


def linha(x, itens=None, so_muda=None, anterior=None, estilo=1, **k):
    return m.formatar(x, estilo, anterior=anterior, agora=AGORA + 5,
                      itens=itens, autor_so_quando_muda=so_muda, **k)


# ---------------------------------------------------------------- regras
def test_normalizar_corrige_o_que_veio_guardado():
    assert lm.normalizar(None) == lm.PADRAO
    assert lm.PADRAO["ordem"][:3] == ["autor", "hora", "conteudo"]
    assert lm.PADRAO["ordem"][-1] == "estado"
    boa = lm.normalizar({"ordem": ["reacoes", "x", "autor", "reacoes"],
                         "ocultos": ["y", "hora"],
                         "autor_so_quando_muda": True})
    assert boa["ordem"][:2] == ["reacoes", "autor"]
    assert sorted(boa["ordem"]) == sorted(lm.CHAVES)
    assert boa["ocultos"] == ["hora"] and boa["autor_so_quando_muda"] is True
    assert lm.normalizar({"autor_so_quando_muda": "sim"})[
        "autor_so_quando_muda"] is False
    # tudo oculto deixaria a linha vazia: voltam todos
    assert lm.normalizar(lay(ocultos=list(lm.CHAVES)))["ocultos"] == []
    assert lm.eh_padrao(None) and not lm.eh_padrao(lay(ocultos=["hora"]))
    assert not lm.eh_padrao(lay(autor_so_quando_muda=True))


def test_alternar_nao_deixa_tirar_o_ultimo():
    novo, ativado = lm.alternar(None, "hora")
    assert ativado is False and novo["ocultos"] == ["hora"]
    novo, ativado = lm.alternar(novo, "hora")
    assert ativado is True and novo["ocultos"] == []
    so_um = lay(ocultos=[c for c in lm.CHAVES if c != "conteudo"])
    novo, ativado = lm.alternar(so_um, "conteudo")
    assert ativado is None and novo == lm.normalizar(so_um)
    assert lm.alternar(None, "lixo")[1] is None


def test_mover_qualquer_item_e_para_nas_pontas():
    novo, pos = lm.mover(None, "estado", -1)
    assert novo["ordem"][-2:] == ["estado", "resposta"] and pos == 8
    novo, pos = lm.mover(None, "autor", 1)
    assert novo["ordem"][:2] == ["hora", "autor"] and pos == 1
    assert lm.mover(None, "autor", -1) == (lm.padrao(), 0)
    assert lm.mover(None, "estado", 1) == (lm.padrao(), 9)


def test_ativos_e_a_opcao_do_autor():
    ativos = lm.ativos(lay(ocultos=["hora", "links"]))
    assert ativos == ["autor", "conteudo", "marcas", "previa", "ia",
                      "reacoes", "resposta", "estado"]
    assert lm.texto_do_item(lay(ocultos=["hora"]), "hora").endswith(
        "desativado")
    assert lm.texto_do_item(None, "autor") == "Nome de quem enviou: ativado"
    novo = lm.definir_so_quando_muda(None, True)
    assert lm.so_quando_muda(novo) and not lm.so_quando_muda(None)


def test_estilos_antigos_viram_a_lista_equivalente():
    assert lm.do_estilo(1) == lm.padrao() and lm.do_estilo(None) == \
        lm.padrao()
    dois = lm.do_estilo(2)
    assert dois["ordem"][-3:] == ["autor", "hora", "estado"]
    assert not dois["ocultos"] and not dois["autor_so_quando_muda"]
    tres = lm.do_estilo(3)
    assert tres["autor_so_quando_muda"] and tres["ocultos"] == ["hora"]
    assert tres["ordem"][0] == "autor" and tres["ordem"][-1] == "estado"


# ----------------------------------------------------------------- linha
def test_a_linha_padrao_e_a_de_sempre_nos_tres_estilos_antigos():
    x = msg("oi", minha=True, estado=m.LIDA)
    um = linha(x)
    assert um.startswith("Você, ") and ": oi" in um and um.endswith(m.LIDA)
    # o estilo antigo e a lista equivalente dao a mesma linha
    for estilo in (1, 2, 3):
        base = lm.do_estilo(estilo)
        assert linha(x, estilo=estilo) == linha(
            x, itens=lm.ativos(base), so_muda=base["autor_so_quando_muda"])
    dois = linha(x, estilo=2)
    assert dois.startswith("oi, Você, ") and dois.endswith(m.LIDA)
    tres = linha(x, estilo=3)
    assert tres == "Você: oi, " + m.LIDA
    # no 3, o autor so aparece quando muda
    seguinte = msg("de novo", minha=True, estado=m.LIDA)
    assert linha(seguinte, estilo=3, anterior=x) == "de novo, " + m.LIDA


def test_desligar_autor_hora_e_estado():
    x = msg("oi", minha=True, estado=m.LIDA)
    nada = lm.ativos(lay(ocultos=["autor", "hora", "estado"]))
    assert linha(x, itens=nada) == "oi"
    sem_hora = lm.ativos(lay(ocultos=["hora"]))
    assert linha(x, itens=sem_hora) == "Você: oi, " + m.LIDA
    sem_autor = lm.ativos(lay(ocultos=["autor"]))
    assert linha(msg("oi"), itens=sem_autor).endswith(": oi")
    assert not linha(msg("oi"), itens=sem_autor).startswith("Ana")


def test_so_a_hora_ou_so_o_autor_nao_deixam_dois_pontos_sobrando():
    so_hora = lm.ativos(lay(ocultos=[c for c in lm.CHAVES if c != "hora"]))
    texto = linha(msg("oi"), itens=so_hora)
    assert texto and not texto.endswith(":") and "oi" not in texto
    so_autor = lm.ativos(lay(ocultos=[c for c in lm.CHAVES if c != "autor"]))
    assert linha(msg("oi"), itens=so_autor) == "Ana"


def test_ordem_livre_inclusive_autor_hora_e_estado():
    x = msg("oi", minha=True, estado=m.LIDA)
    itens = ["conteudo", "estado", "hora", "autor"]
    assert linha(x, itens=itens) == "oi, " + m.LIDA + ", " + \
        m.hora_legivel(AGORA, AGORA + 5) + ", Você"
    # so o que esta no comeco vira cabecalho com dois pontos
    assert linha(x, itens=["hora", "conteudo", "autor"]) == (
        m.hora_legivel(AGORA, AGORA + 5) + ": oi, Você")


def test_itens_do_conteudo_somem_e_mudam_de_ordem():
    x = msg("oi")
    m.atualizar_extras(x, editada=True, favorita=True)
    assert "oi, (editada), (favorita)" in linha(x)
    sem_marcas = lm.ativos(lay(ocultos=["marcas"]))
    assert "editada" not in linha(x, itens=sem_marcas)
    assert "oi" in linha(x, itens=sem_marcas)
    so_marcas = lm.ativos(lay(ocultos=["conteudo", "autor", "hora"]))
    assert linha(x, itens=so_marcas) == "(editada), (favorita)"
    y = msg("oi")
    m.atualizar_extras(y, reacoes=[{"emoji": "👍", "quem": "Bia"}])
    texto = linha(y, itens=["reacoes", "conteudo"])
    assert texto.index("👍") < texto.index("oi")


def test_resposta_e_ia_ligam_e_desligam():
    x = msg("oi", resposta_a="9")
    assert "em resposta a Bia" in linha(x, respondida="Bia")
    sem = lm.ativos(lay(ocultos=["resposta"]))
    assert "resposta" not in linha(x, itens=sem, respondida="Bia")
    y = msg("", tipo=m.VOZ)
    m.atualizar_extras(y, ia={"genero": "audio", "texto": "bom dia",
                              "provedor": "p", "modelo": "x", "quando": 1})
    assert "transcrição: bom dia" in linha(y)
    sem_ia = lm.ativos(lay(ocultos=["ia"]))
    assert "transcrição" not in linha(y, itens=sem_ia)


# ---------------------------------------------------------------- janela
class Fala:
    def __init__(self):
        self.ditas = []

    def falar(self, texto, interromper=False):
        self.ditas.append(texto)


def _dialogo(valor):
    estado = {"v": valor}
    fala = Fala()
    dlg = DialogoListaConversas(None, lambda: estado["v"],
                                lambda v: estado.update(v=v), fala,
                                nucleo=lm, titulo="Lista de mensagens")
    return dlg, estado, fala


def test_dialogo_mostra_os_dez_itens_e_alterna():
    dlg, estado, fala = _dialogo(lm.padrao())
    assert len(dlg.lista.itens) == len(lm.CHAVES)
    assert dlg.lista.itens[1] == "Hora ou data da mensagem: ativado"
    dlg.lista.SetSelection(1)
    dlg.alternar()
    assert estado["v"]["ocultos"] == ["hora"]
    assert fala.ditas[-1] == "desativado"
    assert dlg.lista.itens[1].endswith("desativado")


def test_dialogo_move_qualquer_item_e_restaura():
    dlg, estado, fala = _dialogo(lm.padrao())
    dlg.lista.SetSelection(0)
    dlg.mover(1)                                  # autor desce
    assert estado["v"]["ordem"][:2] == ["hora", "autor"]
    assert "posição 2 de 10" in fala.ditas[-1]
    dlg.so_muda.SetValue(True)
    dlg.mudar_so_quando_muda()
    assert estado["v"]["autor_so_quando_muda"] is True
    assert fala.ditas[-1] == "Nome de quem enviou só quando muda: ativado."
    dlg.restaurar()
    assert estado["v"] == lm.padrao() and not dlg.so_muda.GetValue()
    assert fala.ditas[-1] == "Lista de mensagens no padrão."


# ---------------------------------------------------- configuracoes, backup
class Cfg:
    def __init__(self, **dados):
        self.dados = dados

    def get(self, chave, padrao=None):
        return self.dados.get(chave, padrao)


def test_modelo_guarda_a_lista_de_mensagens_pendente_ate_aplicar():
    mod = ModeloConfiguracoes(Cfg())
    assert mod.lista_msg_em_uso() == lm.padrao()
    novo = lay(ocultos=["hora"])
    mod.lista_msg_definir(novo)
    assert mod.lista_msg_em_uso() == lm.normalizar(novo)
    mod.lista_msg_definir(lm.padrao())          # voltar ao atual desfaz
    assert mod.lista_msg_pendente is None
    mod.lista_msg_definir(novo)
    aplicadas = []
    mod.aplicar(lambda chave, valor: aplicadas.append((chave, valor)))
    assert aplicadas == [("lista_mensagens", lm.normalizar(novo))]
    assert mod.lista_msg_pendente is None


def test_backup_so_leva_de_volta_uma_lista_de_mensagens_valida():
    boas = backup.opcoes_validas({"lista_mensagens": {
        "ordem": ["reacoes", "lixo"], "ocultos": ["hora", "lixo"]}})
    assert boas["lista_mensagens"]["ordem"][0] == "reacoes"
    assert boas["lista_mensagens"]["ocultos"] == ["hora"]
    assert "lista_mensagens" not in backup.opcoes_validas(
        {"lista_mensagens": "texto"})
    assert "lista_mensagens" in backup.EXTRAS


def test_backup_antigo_com_estilo_vira_a_lista_de_mensagens():
    boas = backup.opcoes_validas({"estilo": 3})
    assert boas["lista_mensagens"] == lm.do_estilo(3)
    assert "estilo" not in boas
    # o padrao nao cria nada, e uma lista nova vale mais que o estilo
    assert "lista_mensagens" not in backup.opcoes_validas({"estilo": 1})
    nova = lay(ocultos=["hora"])
    assert backup.opcoes_validas({"estilo": 3, "lista_mensagens": nova})[
        "lista_mensagens"] == lm.normalizar(nova)

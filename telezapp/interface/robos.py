# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""O que os botoes de robo do Telegram fazem na janela principal.

`j` e a janela. O que sai da conta da pessoa (telefone, localizacao, dinheiro)
so vai depois de ela confirmar, a cada vez. Consultas ao servico rodam fora da
janela.
"""
import logging
import threading

import wx

from telezapp import NOME
from telezapp.acessibilidade.fala import bipe
from telezapp.interface import dialogos
from telezapp.nucleo import recursos_windows as recursos
from telezapp.nucleo import robos as nucleo

log = logging.getLogger("telezapp.robos")

ROTULO_TIPO = {"privada": "pessoa ou robô", "grupo": "grupo", "canal": "canal"}


def _fundo(j, trabalho, pronto, falha):
    """Roda trabalho() fora da janela e pronto(resultado) nela. Se der erro,
    fala `falha`."""
    def rodar():
        try:
            r = trabalho()
        except Exception as e:
            log.warning("robô: %s", type(e).__name__)
            wx.CallAfter(_falhou, j, falha)
            return
        wx.CallAfter(pronto, r)
    threading.Thread(target=rodar, daemon=True, name="robo").start()


def _falhou(j, texto):
    bipe("erro")
    j.fala.falar(texto, interromper=True)


def _sim(j, pergunta, padrao_nao=False):
    j.fala.falar(pergunta, interromper=True)
    estilo = wx.YES_NO | wx.ICON_QUESTION | (wx.NO_DEFAULT if padrao_nao else 0)
    return wx.MessageBox(pergunta, NOME, estilo, j) == wx.YES


def _enviado(j, ok, falha="O Telegram não aceitou."):
    if ok:
        j.fala.falar("Enviado.", interromper=True)
    else:
        _falhou(j, falha)


def callback(j, x, acao, prov):
    if not acao.get("pede_senha"):
        prov.responder_acao(x, acao)
        return
    dlg = wx.PasswordEntryDialog(
        j, "O botão %s pede a senha de duas etapas do Telegram:" %
        acao.get("rotulo", ""), NOME)
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return
        senha = dlg.GetValue()
    finally:
        dlg.Destroy()
    prov.responder_acao(x, dict(acao, senha=senha))


def telefone(j, x, acao, prov):
    if not _sim(j, "Enviar o seu número de telefone para esta conversa?", True):
        return
    _fundo(j, lambda: prov.compartilhar_telefone(x.conversa_id),
           lambda ok: _enviado(j, ok), "Não consegui enviar o telefone.")


def local(j, x, acao, prov):
    enviar_localizacao(j, prov, x.conversa_id, acao.get("rotulo", ""))


def enviar_localizacao(j, prov, conversa_id, titulo=""):
    """Busca onde o computador esta e, depois de a pessoa confirmar, envia.
    Sem localizador, avisa e deixa digitar o lugar."""
    conv = j.indice.get((prov.conta.id, conversa_id))
    nome = conv.nome if conv is not None else "esta conversa"
    j.fala.falar("Buscando a localização...", interromper=True)

    def pronto(r):
        if r["situacao"] == "ok":
            precisao = (", com precisão de cerca de %d metros" % r["precisao"]
                        if r.get("precisao") else "")
            if _sim(j, "Enviar a sua localização para %s%s?" % (nome, precisao),
                    True):
                prov.enviar_localizacao(conversa_id, r["latitude"],
                                        r["longitude"])
                j.fala.falar("Enviando a localização.", interromper=True)
            return
        j.fala.falar(recursos.LOCAL_BLOQUEADO if r["situacao"] == "negado"
                     else recursos.LOCAL_AUSENTE, interromper=True)
        _local_digitado(j, prov, conversa_id, titulo)

    def falhou():
        pronto({"situacao": "ausente"})

    def rodar():
        try:
            r = recursos.localizacao()
        except Exception as e:
            log.info("localização: %s", type(e).__name__)
            wx.CallAfter(falhou)
            return
        wx.CallAfter(pronto, r)
    threading.Thread(target=rodar, daemon=True, name="localizacao").start()


def _local_digitado(j, prov, conversa_id, titulo=""):
    """Sem localizador: a pessoa ainda pode informar o lugar."""
    dlg = wx.TextEntryDialog(
        j, "Se quiser, digite a latitude e a longitude, como -30.03, -51.22. "
        "Isto será enviado à conversa:", titulo or "Localização")
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return
        coordenadas = nucleo.ler_coordenadas(dlg.GetValue())
    finally:
        dlg.Destroy()
    if coordenadas is None:
        _falhou(j, "Isso não parece latitude e longitude.")
        return
    prov.enviar_localizacao(conversa_id, *coordenadas)
    j.fala.falar("Enviando a localização.", interromper=True)


def enquete(j, x, acao, prov):
    j._nova_enquete()


def _conversas_do_tipo(j, conta_id, tipos):
    return [c for c in j.indice.values() if c.conta_id == conta_id
            and c.tipo in tipos]


def _escolher_conversa(j, conta_id, tipos, mensagem):
    conversas = sorted(_conversas_do_tipo(j, conta_id, tipos),
                       key=lambda c: c.nome.lower())
    if not conversas:
        _falhou(j, "Nenhuma conversa serve para isto.")
        return None
    return j._escolher_da_lista(
        "Escolher conversa", mensagem,
        [(c, "%s, %s" % (c.nome, ROTULO_TIPO.get(c.tipo, c.tipo)))
         for c in conversas], None)


def escolher(j, x, acao, prov):
    conv = _escolher_conversa(j, x.conta_id, [acao.get("peer", "privada")],
                              "Qual conversa enviar ao robô?")
    if conv is None:
        return
    _fundo(j, lambda: prov.enviar_conversa_ao_robo(x, acao, conv.id),
           lambda ok: _enviado(j, ok), "O robô não aceitou esta conversa.")


def inline(j, x, acao, prov):
    robo = acao.get("robo", "")
    destino = j.indice.get((x.conta_id, x.conversa_id))
    if not acao.get("mesma"):
        destino = _escolher_conversa(j, x.conta_id, ["privada", "grupo"],
                                     "Enviar o resultado para qual conversa?")
    if destino is None:
        return
    dlg = wx.TextEntryDialog(j, "O que pedir ao robô:",
                             acao.get("rotulo", "Busca no robô"),
                             acao.get("consulta", ""))
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return
        consulta = dlg.GetValue()
    finally:
        dlg.Destroy()
    buscar_inline(j, prov, destino, robo, consulta)


def buscar_inline(j, prov, destino, robo, consulta):
    def pronto(r):
        if not r["itens"]:
            _falhou(j, "O robô não trouxe resultados.")
            return
        escolhido = j._escolher_da_lista(
            "Resultados", "Qual enviar para %s?" % destino.nome, r["itens"],
            None)
        if escolhido is not None:
            _fundo(j, lambda: prov.enviar_inline(destino.id, r["consulta_id"],
                                                 escolhido),
                   lambda ok: _enviado(j, ok),
                   "Não consegui enviar o resultado.")
    _fundo(j, lambda: prov.resultados_inline(destino.id, robo, consulta),
           pronto, "O robô não respondeu à busca.")


def jogo(j, x, acao, prov):
    def pronto(url):
        j._app_do_robo_pronto(prov, x.conversa_id, acao.get("rotulo", ""), url)
    _fundo(j, lambda: prov.url_do_jogo(x), pronto, "Não consegui abrir o jogo.")


def login(j, x, acao, prov):
    def aceito(url):
        dialogos.abrir_link(url)

    def pronto(r):
        if r.get("url"):
            aceito(r["url"])
            return
        if not _sim(j, "Entrar em %s com a sua conta do Telegram?" %
                    r["dominio"], True):
            return
        escrever = r["escrita"] and _sim(
            j, "Deixar %s enviar mensagens para você?" % r["dominio"], True)
        _fundo(j, lambda: prov.aceitar_login(x, acao, escrever), aceito,
               "Não consegui entrar.")
    _fundo(j, lambda: prov.pedir_login(x, acao), pronto,
           "Não consegui consultar o login.")


def perfil(j, x, acao, prov):
    j._abrir_conversa_do_link(x.conta_id, acao.get("usuario_id", ""),
                              acao.get("rotulo", "Contato"), "")


def compra(j, x, acao, prov):
    pagar(j, prov, x.conversa_id, msg_id=x.id)


# ---------------------------------------------------------------- pagamento
def pagar(j, prov, conversa_id, msg_id="", slug="", ao_fim=None):
    """Mostra o preco e so paga se a pessoa confirmar. `ao_fim(situacao)`:
    "paid", "cancelled" ou "failed", para um aplicativo que pediu o pagamento."""
    fim = ao_fim or (lambda situacao: None)

    def falhou():
        _falhou(j, "Não consegui consultar o pagamento.")
        fim("failed")

    def pronto(f):
        if any(f["pede"].values()):
            _coletar_dados(j, prov, f, f["salvos"], lambda: confirmar(f), fim)
        else:
            confirmar(f)

    def confirmar(f):
        pergunta = ("Pagar %s por %s? É um pagamento de verdade." % (
            f["preco"], f["titulo"]))
        if f["teste"]:
            pergunta = "Pagamento de teste: %s por %s. Continuar?" % (
                f["preco"], f["titulo"])
        if not _sim(j, pergunta, True):
            fim("cancelled")
            return
        if f["estrelas"]:
            _concluir(j, prov, f, None, fim)
        elif f["url"]:
            j._abrir_formulario_de_pagamento(prov, conversa_id, f, fim)
        else:
            _falhou(j, "Este pagamento só funciona no aplicativo oficial.")
            fim("failed")

    def consultar():
        try:
            return prov.formulario_de_pagamento(conversa_id, msg_id, slug)
        except Exception as e:
            log.warning("formulário de pagamento: %s", type(e).__name__)
            return None

    def entregar(f):
        if f is None:
            falhou()
        else:
            pronto(f)
    threading.Thread(target=lambda: wx.CallAfter(entregar, consultar()),
                     daemon=True, name="pagamento").start()


class DialogoDadosDePagamento(wx.Dialog):
    """Os dados que o vendedor pediu, ja com o que o Telegram tiver salvo."""

    def __init__(self, pai, formulario, valores):
        super().__init__(pai, title="Dados para %s" % formulario["titulo"])
        self.campos = {}
        caixa = wx.BoxSizer(wx.VERTICAL)
        caixa.Add(wx.StaticText(self, label=(
            "Estes dados vão para o vendedor, pelo Telegram.")), 0, wx.ALL, 8)
        for chave, rotulo, obrigatorio in nucleo.campos_pedidos(
                formulario["pede"]):
            caixa.Add(wx.StaticText(self, label=rotulo + (
                "" if obrigatorio else " (opcional)")), 0, wx.LEFT | wx.RIGHT, 8)
            campo = wx.TextCtrl(self, value=valores.get(chave, "") or "")
            caixa.Add(campo, 0, wx.EXPAND | wx.ALL, 8)
            self.campos[chave] = campo
        self.salvar = wx.CheckBox(self, label="Guardar estes dados no Telegram")
        caixa.Add(self.salvar, 0, wx.ALL, 8)
        caixa.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0,
                  wx.ALL | wx.ALIGN_RIGHT, 8)
        self.SetSizerAndFit(caixa)

    def valores(self):
        return {c: campo.GetValue() for c, campo in self.campos.items()}


def _coletar_dados(j, prov, f, valores, seguir, fim):
    """Pede os dados e os confere no Telegram; se ele recusar, volta para a
    janela com o que foi digitado."""
    dlg = DialogoDadosDePagamento(j, f, valores)
    try:
        if dlg.ShowModal() != wx.ID_OK:
            fim("cancelled")
            return
        valores, salvar = dlg.valores(), dlg.salvar.GetValue()
    finally:
        dlg.Destroy()
    corrigir = nucleo.faltando(f["pede"], valores)
    if corrigir:
        _falhou(j, "Preencha o campo %s." % corrigir)
        _coletar_dados(j, prov, f, valores, seguir, fim)
        return

    def rodar():
        try:
            opcoes = prov.validar_dados(f, valores, salvar)
        except Exception as e:
            log.info("dados de pagamento: %s", type(e).__name__)
            wx.CallAfter(recusado)
            return
        wx.CallAfter(aceito, opcoes)

    def recusado():
        _falhou(j, "O vendedor não aceitou estes dados. Confira e tente de novo.")
        _coletar_dados(j, prov, f, valores, seguir, fim)

    def aceito(opcoes):
        if opcoes:
            escolhida = j._escolher_da_lista(
                "Entrega", "Como receber?",
                [(o, o[1]) for o in opcoes], None)
            if escolhida is None:
                fim("cancelled")
                return
            f["_envio_id"] = escolhida[0]
            f["preco"] = nucleo.preco(f["_moeda"], escolhida[2])
        seguir()
    threading.Thread(target=rodar, daemon=True, name="pagamento").start()


def _concluir(j, prov, formulario, credenciais, fim):
    def rodar():
        try:
            r = prov.pagar(formulario, credenciais)
        except Exception as e:
            log.warning("pagamento: %s", type(e).__name__)
            r = {"erro": True}
        wx.CallAfter(_pagamento_feito, j, prov, r, fim)
    threading.Thread(target=rodar, daemon=True, name="pagamento").start()


def _pagamento_feito(j, prov, r, fim):
    if r.get("verificar"):
        dialogos.abrir_link(r["verificar"])
        j.fala.falar("O pagamento pede uma verificação; siga na página aberta.",
                     interromper=True)
        fim("pending")
    elif r.get("ok"):
        j.fala.falar("Pagamento feito.", interromper=True)
        fim("paid")
    else:
        _falhou(j, "O pagamento não foi feito.")
        fim("failed")


def credenciais_do_formulario(j, prov, formulario, credenciais, fim):
    """O formulario do provedor devolveu os dados do cartao: ultima confirmacao
    antes de cobrar."""
    if _sim(j, "Confirmar o pagamento de %s por %s?" % (
            formulario["preco"], formulario["titulo"]), True):
        _concluir(j, prov, formulario, credenciais, fim)
    else:
        fim("cancelled")


TRATADORES = {"robo_callback": callback, "robo_telefone": telefone,
              "robo_local": local, "robo_enquete": enquete,
              "robo_escolher": escolher, "robo_inline": inline,
              "robo_jogo": jogo, "robo_login": login, "robo_perfil": perfil,
              "robo_compra": compra}

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Janela de detalhes da conversa: dados da pessoa, do grupo ou do canal, as
midias com filtro, os membros, os grupos em comum e as ferramentas de
administrador. `ControleDetalhes` junta a janela principal, os provedores e
o banco; as janelas daqui so desenham e chamam de volta."""
import logging
import os
import tempfile
import threading
import time
import traceback

import wx

from telezapp.nucleo import detalhes as det
from telezapp.nucleo import modelos as m

log = logging.getLogger("telezapp.detalhes")


# ------------------------------------------------------------ janelas
class DialogoTexto(wx.Dialog):
    """Texto somente leitura (setas leem) e uma fila de botoes. Esc fecha."""

    def __init__(self, pai, titulo):
        super().__init__(pai, title=titulo, size=(620, 520),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.lay = wx.BoxSizer(wx.VERTICAL)
        self.texto = wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY, name="Detalhes")
        self.lay.Add(self.texto, 1, wx.EXPAND | wx.ALL, 10)
        self.linha = wx.WrapSizer(wx.HORIZONTAL)
        self.lay.Add(self.linha, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.SetSizer(self.lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.botoes = []
        self.CentreOnParent()

    def definir(self, linhas, botoes):
        """linhas: [texto]; botoes: [(rotulo, funcao)] (o ultimo costuma ser
        Fechar, que e o proprio Esc)."""
        self.texto.SetValue("\n".join(linhas))
        self.texto.SetInsertionPoint(0)
        for b in self.botoes:
            b.Destroy()
        self.botoes = []
        self.linha.Clear()
        for rotulo, funcao in botoes:
            b = wx.Button(self, wx.ID_ANY, rotulo)
            b.Bind(wx.EVT_BUTTON, lambda e, f=funcao: f())
            self.linha.Add(b, 0, wx.RIGHT | wx.TOP, 6)
            self.botoes.append(b)
        fechar = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        self.linha.Add(fechar, 0, wx.RIGHT | wx.TOP, 6)
        self.botoes.append(fechar)
        self.Layout()


class DialogoLista(wx.Dialog):
    """Lista com filtro opcional e menu de contexto por item."""

    def __init__(self, pai, titulo, rotulo_lista, filtros=(), ao_filtrar=None,
                 ao_menu=None):
        """filtros: [(chave, rotulo)]; ao_filtrar(chave) -> [(texto, dado)];
        ao_menu(dado) -> [(rotulo, funcao)] (o primeiro item roda no Enter)."""
        super().__init__(pai, title=titulo, size=(640, 520),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.ao_filtrar, self.ao_menu = ao_filtrar, ao_menu
        self.filtros = list(filtros)
        self.itens = []
        lay = wx.BoxSizer(wx.VERTICAL)
        self.escolha = None
        if self.filtros:
            lay.Add(wx.StaticText(self, label="Tipo de conteúdo"), 0,
                    wx.LEFT | wx.RIGHT | wx.TOP, 10)
            self.escolha = wx.Choice(self, choices=[r for _, r in filtros],
                                     name="Tipo de conteúdo")
            self.escolha.SetSelection(0)
            self.escolha.Bind(wx.EVT_CHOICE, lambda e: self.recarregar())
            lay.Add(self.escolha, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        lay.Add(wx.StaticText(self, label=rotulo_lista), 0,
                wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.lista = wx.ListBox(self, style=wx.LB_SINGLE | wx.LB_HSCROLL,
                                name=rotulo_lista)
        lay.Add(self.lista, 1, wx.EXPAND | wx.ALL, 10)
        fechar = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        lay.Add(fechar, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, 10)
        self.SetSizer(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.lista.Bind(wx.EVT_CONTEXT_MENU, self._menu)
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._primeiro())
        self.Bind(wx.EVT_CHAR_HOOK, self._tecla)
        self.CentreOnParent()
        self.recarregar()

    def chave_do_filtro(self):
        if self.escolha is None:
            return None
        return self.filtros[max(self.escolha.GetSelection(), 0)][0]

    def recarregar(self, manter=True):
        anterior = self.lista.GetSelection()
        self.itens = self.ao_filtrar(self.chave_do_filtro())
        self.lista.Set([t for t, _ in self.itens] or ["Nenhum item."])
        if self.itens:
            self.lista.SetSelection(min(max(anterior, 0) if manter else 0,
                                        len(self.itens) - 1))

    def _dado(self):
        i = self.lista.GetSelection()
        return self.itens[i][1] if 0 <= i < len(self.itens) else None

    def _opcoes(self):
        dado = self._dado()
        if dado is None or self.ao_menu is None:
            return []
        return self.ao_menu(dado)

    def _primeiro(self):
        opcoes = self._opcoes()
        if opcoes:
            opcoes[0][1]()

    def _tecla(self, evt):
        if evt.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and \
                self.FindFocus() is self.lista:
            self._primeiro()
            return
        evt.Skip()

    def _menu(self, evt):
        pos = evt.GetPosition()
        if pos != wx.DefaultPosition:
            k = self.lista.HitTest(self.lista.ScreenToClient(pos))
            if k != wx.NOT_FOUND:
                self.lista.SetSelection(k)
        opcoes = self._opcoes()
        if not opcoes:
            return
        menu = wx.Menu()
        for rotulo, funcao in opcoes:
            it = menu.Append(wx.ID_ANY, rotulo)
            self.Bind(wx.EVT_MENU, lambda e, f=funcao: f(), it)
        if pos == wx.DefaultPosition:
            self.lista.PopupMenu(menu, wx.Point(20, 20))
        else:
            self.lista.PopupMenu(menu, self.lista.ScreenToClient(pos))
        menu.Destroy()


class DialogoAdministrar(wx.Dialog):
    """Ferramentas de administrador de um grupo."""

    def __init__(self, pai, ctl, dados):
        super().__init__(pai, title="Administrar grupo", size=(560, 560),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.ctl = ctl
        lay = wx.BoxSizer(wx.VERTICAL)

        def campo(rotulo, valor, multilinha=False):
            lay.Add(wx.StaticText(self, label=rotulo), 0,
                    wx.LEFT | wx.RIGHT | wx.TOP, 10)
            c = wx.TextCtrl(self, value=valor, name=rotulo,
                            style=wx.TE_MULTILINE if multilinha else 0,
                            size=(-1, 90 if multilinha else -1))
            lay.Add(c, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
            return c
        self.nome = campo("Nome do grupo", dados["nome"])
        b = wx.Button(self, label="Salvar o &nome")
        b.Bind(wx.EVT_BUTTON, lambda e: self._acao(
            "nome", self.nome.GetValue().strip()))
        lay.Add(b, 0, wx.ALL, 10)
        self.descricao = campo("Descrição do grupo", dados["descricao"], True)
        b = wx.Button(self, label="Salvar a &descrição")
        b.Bind(wx.EVT_BUTTON, lambda e: self._acao(
            "descricao", self.descricao.GetValue()))
        lay.Add(b, 0, wx.ALL, 10)
        self.anuncio = wx.CheckBox(
            self, label="Só administradores enviam &mensagens")
        self.anuncio.SetValue(bool(dados["anuncio"]))
        self.anuncio.Bind(wx.EVT_CHECKBOX, lambda e: self._acao(
            "anuncio", self.anuncio.GetValue()))
        lay.Add(self.anuncio, 0, wx.ALL, 10)
        self.trancado = wx.CheckBox(
            self, label="Só administradores &editam os dados do grupo")
        self.trancado.SetValue(bool(dados["trancado"]))
        self.trancado.Bind(wx.EVT_CHECKBOX, lambda e: self._acao(
            "trancado", self.trancado.GetValue()))
        lay.Add(self.trancado, 0, wx.LEFT | wx.RIGHT, 10)
        linha = wx.WrapSizer(wx.HORIZONTAL)
        botoes = [("&Adicionar participante...", self._adicionar),
                  ("&Link de convite e QR Code...",
                   lambda: ctl.convite(self))]
        if getattr(ctl.prov, "FOTO_DO_GRUPO", False):
            botoes.append(("Trocar a &foto do grupo...",
                           lambda: ctl.trocar_foto(self)))
        if getattr(ctl.prov, "PEDIDOS_DE_ENTRADA", False):
            botoes.append(("&Pedidos de entrada...",
                           lambda: ctl.pedidos(self)))
        botoes.append(("&Sair do grupo", self._sair))
        for rotulo, funcao in botoes:
            b = wx.Button(self, label=rotulo)
            b.Bind(wx.EVT_BUTTON, lambda e, f=funcao: f())
            linha.Add(b, 0, wx.RIGHT | wx.TOP, 6)
        lay.Add(linha, 0, wx.ALL, 10)
        lay.Add(wx.StaticText(
            self, label="Para remover, promover ou rebaixar alguém, use o "
                        "menu de contexto da lista de membros."),
                0, wx.LEFT | wx.RIGHT, 10)
        lay.Add(wx.Button(self, wx.ID_CANCEL, "&Fechar"), 0,
                wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(lay)
        self.SetEscapeId(wx.ID_CANCEL)
        self.CentreOnParent()

    def _acao(self, acao, valor=None):
        if acao == "nome" and not valor:
            wx.MessageBox("O nome não pode ficar vazio.", "Administrar grupo",
                          wx.OK | wx.ICON_WARNING, self)
            return
        self.ctl.administrar(acao, valor, self)

    def _adicionar(self):
        dlg = wx.TextEntryDialog(
            self, "Telefone da pessoa, com país e DDD (ela precisa ter a "
                  "conta no serviço) ou, no Telegram, @usuário:",
            "Adicionar participante")
        try:
            if dlg.ShowModal() == wx.ID_OK and dlg.GetValue().strip():
                self._acao("adicionar", dlg.GetValue().strip())
        finally:
            dlg.Destroy()

    def _sair(self):
        r = wx.MessageBox("Sair deste grupo?", "Sair do grupo",
                          wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
        if r == wx.YES:
            self._acao("sair")


# ------------------------------------------------------------ controle
def _quando(ts):
    return time.strftime("%d/%m/%Y", time.localtime(ts)) if ts else ""


class ControleDetalhes:
    """Os detalhes de uma conversa (pessoa, grupo ou canal)."""

    def __init__(self, jan, conv):
        self.jan, self.conv = jan, conv
        self.dados = None              # grupo, canal ou contato (do servico)
        self.mensagens = []
        self.est = None
        self.dlg = None
        self.ver = None                # mensagem a mostrar ao fechar
        self.abrir_conversa = None     # conversa a abrir ao fechar
        self.prov = jan.contas.provedor(conv.conta_id) if jan.contas \
            else None

    # --------------------------------------------------------- abertura
    def abrir(self):
        jan, conv = self.jan, self.conv
        tipo = {"privada": "Detalhes da conversa", "grupo":
                "Detalhes do grupo", "canal": "Detalhes do canal"}.get(
                    conv.tipo, "Detalhes da conversa")
        self.dlg = DialogoTexto(jan, "%s: %s" % (tipo, conv.nome))
        self.dlg.definir(self._linhas_locais() + ["", "Carregando..."],
                         self._botoes())
        threading.Thread(target=self._carregar, daemon=True,
                         name="detalhes").start()
        try:
            self.dlg.ShowModal()
        finally:
            self.dlg.Destroy()
            self.dlg = None
        if self.ver is not None:
            wx.CallAfter(jan._ver_na_conversa, self.ver)
        elif self.abrir_conversa is not None:
            wx.CallAfter(jan._abrir_conversa_de, self.abrir_conversa)

    def _carregar(self):
        jan, conv = self.jan, self.conv
        try:
            self.mensagens = jan.banco.mensagens(conv.conta_id, conv.id,
                                                 10 ** 9)
            self.est = det.estatisticas(
                self.mensagens, jan.banco.midias(conv.conta_id, conv.id))
        except Exception:
            log.error("detalhes (banco):\n%s", traceback.format_exc())
        dados = None
        try:
            if self.prov is not None and conv.tipo == "privada":
                dados = self.prov.dados_do_contato(conv.id)
            elif self.prov is not None and conv.tipo == "grupo":
                dados = self.prov.detalhes_do_grupo(conv.id)
            elif self.prov is not None and conv.tipo == "canal":
                dados = self.prov.detalhes_do_canal(conv.id)
        except Exception:
            log.error("detalhes (servico):\n%s", traceback.format_exc())
        wx.CallAfter(self._chegou, dados)

    def _chegou(self, dados):
        if self.dlg is None:
            return
        self.dados = dados
        self.dlg.definir(self._linhas(), self._botoes())
        self.jan.fala.falar("Detalhes carregados.")

    # ---------------------------------------------------------- textos
    def _linhas_locais(self):
        conv, jan = self.conv, self.jan
        servico = m.SERVICOS.get(jan.contas.servico(conv.conta_id), "")
        conta = jan.contas.nome(conv.conta_id) if jan.contas else ""
        tipo = {"privada": "Conversa com uma pessoa", "grupo": "Grupo",
                "canal": "Canal"}.get(conv.tipo, "Conversa")
        linhas = ["Nome: %s" % conv.nome, "Tipo: %s" % tipo,
                  "Conta: %s, %s" % (conta, servico)]
        if self._pode_temporarias():
            linhas.append("Mensagens temporárias: %s" % m.texto_periodo(
                self._conv_atual().temporaria_s, conv.servico))
        if conv.somente_leitura:
            linhas.append("Você não pode escrever nesta conversa.")
        return linhas

    def _linhas(self):
        conv, d = self.conv, self.dados or {}
        linhas = self._linhas_locais()
        if conv.tipo == "privada":
            salvo = self.jan.banco.nome_de_contato(conv.conta_id, conv.id)
            linhas.append("Contato salvo no TeleZapp: %s" % (
                salvo if salvo else "não"))
            for chave, rotulo in (("telefone", "Telefone"),
                                  ("usuario", "Nome de usuário"),
                                  ("nome_no_perfil", "Nome no perfil"),
                                  ("recado", "Recado")):
                if d.get(chave):
                    linhas.append("%s: %s" % (rotulo, d[chave]))
            if not d:
                linhas.append("O serviço não informou mais dados desta "
                              "pessoa agora.")
        elif conv.tipo == "grupo":
            if d:
                gente = d.get("participantes", [])
                admins = sum(1 for p in gente if p["admin"])
                if d.get("nome") and d["nome"] != conv.nome:
                    linhas.append("Nome atual: %s" % d["nome"])
                if d.get("comunidade"):
                    linhas.append("Este grupo é uma comunidade.")
                elif d.get("da_comunidade"):
                    linhas.append("Este grupo faz parte de uma comunidade.")
                if d.get("descricao"):
                    linhas.append("Descrição: %s" % d["descricao"])
                if d.get("criado_em"):
                    linhas.append("Criado em: %s" % _quando(d["criado_em"]))
                if d.get("dono"):
                    linhas.append("Criador: %s" % d["dono"])
                linhas.append("Membros: %d (%d administrador%s)" % (
                    len(gente), admins, "" if admins == 1 else "es"))
                linhas.append("Quem envia mensagens: %s" % (
                    "só administradores" if d.get("anuncio") else "todos"))
                linhas.append("Quem edita os dados do grupo: %s" % (
                    "só administradores" if d.get("trancado") else "todos"))
                linhas.append("Você %s administrador." % (
                    "é" if d.get("sou_admin") else "não é"))
            else:
                linhas.append("O serviço não informou os dados do grupo "
                              "agora (conta desconectada?).")
        elif conv.tipo == "canal":
            if d:
                if d.get("descricao"):
                    linhas.append("Descrição: %s" % d["descricao"])
                linhas.append("Seguidores: %d" % d.get("seguidores", 0))
                linhas.append("Verificado: %s" % (
                    "sim" if d.get("verificado") else "não"))
                if d.get("papel"):
                    linhas.append("Seu papel: %s" % d["papel"])
                if d.get("criado_em"):
                    linhas.append("Criado em: %s" % _quando(d["criado_em"]))
                if d.get("link"):
                    linhas.append("Link: %s" % d["link"])
                linhas.append("Som do canal: %s" % (
                    "silenciado" if d.get("silenciado") else "ligado"))
            else:
                linhas.append("O serviço não informou os dados do canal "
                              "agora.")
        linhas.append("")
        if self.est is not None:
            linhas += det.linhas_de_uso(self.est)
        else:
            linhas.append("Calculando o uso de espaço...")
        return linhas

    # ---------------------------------------------------------- botoes
    def _conv_atual(self):
        """A conversa como esta agora na lista (o prazo das mensagens
        temporarias pode ter mudado)."""
        return self.jan.indice.get(self.conv.chave, self.conv)

    def _pode_temporarias(self):
        return bool(self.prov is not None and getattr(
            self.prov, "PODE_TEMPORARIAS", False) and
            self.conv.tipo in ("privada", "grupo"))

    def temporarias(self):
        """Escolhe o prazo das mensagens temporarias da conversa."""
        conv = self._conv_atual()
        periodos = m.periodos_temporarias(
            self.jan.contas.servico(conv.conta_id))
        dlg = wx.SingleChoiceDialog(
            self.dlg, "Por quanto tempo as mensagens desta conversa ficam "
            "antes de sumir? As que já existem não mudam.",
            "Mensagens temporárias de %s" % conv.nome,
            [r for _, r in periodos])
        atual = [s for s, _ in periodos].index(conv.temporaria_s) \
            if conv.temporaria_s in [s for s, _ in periodos] else 0
        dlg.SetSelection(atual)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            segundos = periodos[dlg.GetSelection()][0]
        finally:
            dlg.Destroy()
        if segundos == conv.temporaria_s:
            return
        self.prov.definir_temporaria(conv.id, segundos)
        self.jan.fala.falar("Mudando as mensagens temporárias.",
                            interromper=True)
        wx.CallLater(2500, self._depois_de_temporarias)

    def _depois_de_temporarias(self):
        if self.dlg is not None:
            self._atualizar()

    def _botoes(self):
        conv, d = self.conv, self.dados or {}
        botoes = []
        if self._pode_temporarias():
            botoes.append(("Mensagens &temporárias...", self.temporarias))
        if conv.tipo == "privada":
            botoes.append(("&Editar contato", self.editar_contato))
            botoes.append(("&Mídias", self.midias))
            botoes.append(("&Grupos em comum", self.em_comum))
            if getattr(self.prov, "LISTA_GRUPOS_ADMIN", False):
                botoes.append(("&Adicionar a um grupo...",
                               self.adicionar_a_grupo))
        elif conv.tipo == "grupo":
            n = len(d.get("participantes", [])) if d else 0
            botoes.append(("Ver &membros%s" % (" (%d)" % n if n else ""),
                           self.membros))
            botoes.append(("&Mídias", self.midias))
            if getattr(self.prov, "FOTO_DO_GRUPO", False):
                botoes.append(("Ver a &foto do grupo", self.ver_foto))
            if d.get("comunidade"):
                botoes.append(("&Grupos da comunidade", self.subgrupos))
            if d.get("sou_admin"):
                botoes.append(("&Administrar grupo", self.administrar_grupo))
                if getattr(self.prov, "PEDIDOS_DE_ENTRADA", False):
                    botoes.append(("&Pedidos de entrada...", self.pedidos))
        else:
            botoes.append(("&Mídias", self.midias))
            if d.get("link"):
                botoes.append(("Copiar o &link", lambda: self.jan._copiar_texto(
                    d["link"])))
            if d:
                botoes.append(("Re&ativar o som do canal"
                               if d.get("silenciado") else "&Silenciar o canal",
                               self.silenciar_canal))
                botoes.append(("&Deixar de seguir", self.deixar_de_seguir))
        botoes.append(("Mensagens fa&voritas", self.favoritas))
        botoes.append(("&Limpar a conversa...", self.limpar))
        return botoes

    # ------------------------------------------------------------ acoes
    def _atualizar(self):
        """Refaz o texto depois de uma mudanca."""
        self.dados = None
        self.dlg.definir(self._linhas_locais() + ["", "Carregando..."],
                         self._botoes())
        threading.Thread(target=self._carregar, daemon=True,
                         name="detalhes").start()

    def limpar(self):
        """Abre a limpeza de mídias e mensagens so desta conversa; se algo
        saiu, os detalhes (contagens e mídias) são refeitos."""
        if self.jan._limpar_conversa_com_opcoes(self.conv):
            self._atualizar()

    def editar_contato(self):
        self.jan._salvar_pessoa(self.conv)
        self.jan._renomear_pelos_contatos()
        self.dlg.SetTitle("Detalhes da conversa: %s" % self.conv.nome)
        self._atualizar()

    def _sub(self, dlg):
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()
        if self.ver is not None or self.abrir_conversa is not None:
            self.dlg.EndModal(wx.ID_OK)       # fecha tambem os detalhes

    # ---- midias
    def midias(self):
        filtros = [(det.TODAS, "Todas")] + list(det.TIPOS_DE_MIDIA)

        def filtrar(chave):
            itens = det.midias(self.mensagens, chave or det.TODAS)
            return [(det.rotulo_do_item(x), x) for x in itens]
        dlg = DialogoLista(
            self.dlg, "Mídias de %s" % self.conv.nome,
            "Mídias (Menu abre as ações)", filtros, filtrar,
            self._menu_midia)
        self._lista_midias = dlg
        self._sub(dlg)

    def _menu_midia(self, x):
        jan = self.jan
        opcoes = []
        classes = det.classes(x)
        if x.tipo in det.BAIXAVEIS_TIPOS:
            opcoes.append(("Abrir", lambda: jan._abrir_midia(True, x)))
        elif "link" in classes:
            url = (m.itens_de_link(x) or [("", "")])[0][1]
            if url:
                opcoes.append(("Abrir o link", lambda: jan._abrir_endereco(
                    url)))
        elif "contato" in classes:
            opcoes.append(("Ver o contato", lambda: jan._mostrar_texto(x)))
        if x.tipo in det.BAIXAVEIS_TIPOS:
            opcoes.append(("Salvar em um arquivo...", lambda: jan._salvar_copia_de(x)))
        for tipo, rotulo, valor in m.conteudos_copiaveis(x):
            opcoes.append((rotulo, lambda t=tipo, v=valor:
                           jan._copiar_conteudo(x, t, v)))
        opcoes.append(("Apagar...", lambda: self._apagar(x)))
        opcoes.append(("Ver na conversa", lambda: self._ver(x)))
        return opcoes

    # ---- favoritas
    def favoritas(self):
        """Lista as mensagens favoritas da conversa, da mais nova para a
        mais antiga."""
        if not det.favoritas(self.mensagens):
            self.jan.fala.falar("Nenhuma mensagem favorita nesta conversa.",
                                interromper=True)
            wx.MessageBox("Nenhuma mensagem favorita nesta conversa.",
                          "Mensagens favoritas",
                          wx.OK | wx.ICON_INFORMATION, self.dlg)
            return

        def filtrar(_):
            return [(det.rotulo_do_item(x), x)
                    for x in det.favoritas(self.mensagens)]
        dlg = DialogoLista(
            self.dlg, "Mensagens favoritas de %s" % self.conv.nome,
            "Mensagens favoritas (Menu abre as ações)", (), filtrar,
            self._menu_favorita)
        self._lista_favoritas = dlg
        self._sub(dlg)

    def _menu_favorita(self, x):
        opcoes = [("Ver na conversa", lambda: self._ver(x)),
                  ("Desfavoritar", lambda: self._desfavoritar(x))]
        for tipo, rotulo, valor in m.conteudos_copiaveis(x):
            opcoes.append((rotulo, lambda t=tipo, v=valor:
                           self.jan._copiar_conteudo(x, t, v)))
        return opcoes

    def _desfavoritar(self, x):
        """Tira a marca (no TeleZapp e, no WhatsApp, na conta) e a mensagem
        sai da lista. Vale a copia que a janela principal ja tem aberta."""
        aberta = next((y for y in self.jan.cache.get(self.conv.chave, [])
                       if y.id == x.id), None)
        if aberta is not None:
            x = aberta
        self.jan._favoritar_mensagem(x)
        self.mensagens = [y if y.id != x.id else x for y in self.mensagens]
        lista = getattr(self, "_lista_favoritas", None)
        if lista is not None:
            try:
                lista.recarregar()
            except RuntimeError:
                pass

    def _apagar(self, x):
        self.jan._apagar_mensagem(x)
        self.mensagens = [y for y in self.mensagens if y.id != x.id]
        self.est = det.estatisticas(
            self.mensagens, self.jan.banco.midias(self.conv.conta_id,
                                                  self.conv.id))
        if getattr(self, "_lista_midias", None):
            try:
                self._lista_midias.recarregar()
            except RuntimeError:
                pass

    def _ver(self, x):
        self.ver = x
        wx.CallAfter(self._fechar_tudo)

    def _fechar_tudo(self):
        for w in wx.GetTopLevelWindows():
            if isinstance(w, (DialogoLista, DialogoAdministrar)) and \
                    w.IsModal():
                w.EndModal(wx.ID_OK)

    # ---- membros e grupos
    def membros(self):
        gente = (self.dados or {}).get("participantes", [])
        if not gente:
            self.jan.fala.falar("Não há lista de membros agora.")
            return

        def itens(_):
            def rotulo(p):
                partes = [p["nome"]]
                if p.get("usuario"):
                    partes.append(p["usuario"])
                if p.get("telefone") and p["telefone"] != p["nome"]:
                    partes.append(p["telefone"])
                if p.get("dono"):
                    partes.append("criador")
                elif p.get("admin"):
                    partes.append("administrador")
                if p.get("eu"):
                    partes.append("você")
                return ", ".join(partes)
            return [(rotulo(p), p) for p in gente]
        dlg = DialogoLista(self.dlg, "Membros de %s" % self.conv.nome,
                           "Membros (Menu abre as ações)", (), itens,
                           self._menu_membro)
        self._sub(dlg)

    def _menu_membro(self, p):
        jan, conv = self.jan, self.conv
        if p.get("eu"):
            return []

        def com_conversa(funcao):
            def rodar():
                c = jan._garantir_conversa(conv.conta_id, p["id"], p["nome"])
                funcao(c)
            return rodar
        opcoes = [("Iniciar conversa", com_conversa(
            lambda c: self._iniciar(c)))]
        for rotulo, funcao in self._opcoes_de_conversa(p):
            opcoes.append((rotulo, funcao))
        d = self.dados or {}
        if d.get("sou_admin") and not p.get("dono"):
            if p.get("admin"):
                opcoes.append(("Tirar de administrador", lambda:
                               self.administrar("rebaixar", p["id"], None)))
            else:
                opcoes.append(("Promover a administrador", lambda:
                               self.administrar("promover", p["id"], None)))
            opcoes.append(("Remover do grupo...", lambda:
                           self._remover(p)))
        return opcoes

    def _opcoes_de_conversa(self, p):
        """Os itens da lista principal de conversas, para quem e membro."""
        jan, conv = self.jan, self.conv
        chave = (conv.conta_id, p["id"])
        existente = jan.indice.get(chave)
        if existente is None:
            # sem conversa ainda: so o que nao depende dela
            return [("Salvar como contato...", lambda: jan._salvar_pessoa(
                jan._garantir_conversa(conv.conta_id, p["id"], p["nome"])))]
        return [(r, f) for r, f in jan._opcoes_da_conversa(
            existente, com_abrir=False, com_detalhes=True)]

    def _iniciar(self, c):
        self.abrir_conversa = c
        wx.CallAfter(self._fechar_tudo)

    def _remover(self, p):
        r = wx.MessageBox("Remover %s do grupo?" % p["nome"],
                          "Remover do grupo",
                          wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
                          self.dlg)
        if r == wx.YES:
            self.administrar("remover", p["id"], None)

    def subgrupos(self):
        gente = (self.dados or {}).get("subgrupos", [])
        if not gente:
            self.jan.fala.falar("Nenhum grupo listado nesta comunidade.")
            return
        self._lista_de_grupos("Grupos da comunidade", gente)

    def em_comum(self):
        self.jan.fala.falar("Procurando grupos em comum...",
                            interromper=True)

        def trabalho():
            try:
                achados = self.prov.grupos_em_comum(self.conv.id) \
                    if self.prov is not None else []
            except Exception:
                log.error("em comum:\n%s", traceback.format_exc())
                achados = []
            wx.CallAfter(self._mostrar_em_comum, achados)
        threading.Thread(target=trabalho, daemon=True,
                         name="grupos-em-comum").start()

    def _mostrar_em_comum(self, achados):
        if self.dlg is None:
            return
        if not achados:
            self.jan.fala.falar("Nenhum grupo em comum.")
            wx.MessageBox("Você e %s não têm grupos em comum." %
                          self.conv.nome, "Grupos em comum",
                          wx.OK | wx.ICON_INFORMATION, self.dlg)
            return
        self._lista_de_grupos("Grupos em comum com %s" % self.conv.nome,
                              achados)

    def _lista_de_grupos(self, titulo, achados):
        jan, conta = self.jan, self.conv.conta_id

        def itens(_):
            return [(nome, (cid, nome)) for cid, nome in achados]

        def menu(dado):
            cid, nome = dado
            conv = jan._garantir_conversa(conta, cid, nome, tipo="grupo")
            return jan._opcoes_da_conversa(conv, com_abrir=True,
                                           com_detalhes=True)
        self._sub(DialogoLista(self.dlg, titulo, "Grupos (Menu abre as "
                               "ações)", (), itens, menu))

    # ---- convite, foto, pedidos de entrada
    def _em_segundo_plano(self, nome, trabalho, depois):
        """Roda trabalho() fora da interface e entrega o resultado a
        depois(resultado) na thread da interface (None se deu erro)."""
        def rodar():
            try:
                resultado = trabalho()
            except Exception:
                log.error("%s:\n%s", nome, traceback.format_exc())
                resultado = None
            wx.CallAfter(depois, resultado)
        threading.Thread(target=rodar, daemon=True, name=nome).start()

    def convite(self, pai=None):
        """Link de convite do grupo, com QR Code."""
        jan = self.jan
        jan.fala.falar("Pedindo o link de convite...", interromper=True)

        def depois(resultado):
            if self.dlg is None:
                return
            if not resultado or not resultado[0]:
                texto = resultado[1] if resultado else "Não consegui o link."
                jan.fala.falar(texto, interromper=True)
                wx.MessageBox(texto, "Link de convite",
                              wx.OK | wx.ICON_WARNING, pai or self.dlg)
                return
            from telezapp.interface.grupo_extras import DialogoConvite
            dlg = DialogoConvite(
                pai or self.dlg, resultado[1], jan._copiar_texto,
                lambda: self.prov.administrar_grupo(
                    self.conv.id, "revogar_link"), jan.fala)
            try:
                dlg.ShowModal()
            finally:
                dlg.Destroy()
        self._em_segundo_plano(
            "convite", lambda: self.prov.administrar_grupo(
                self.conv.id, "link"), depois)

    def pedidos(self, pai=None):
        """Pedidos de entrada: aprovar ou recusar."""
        from telezapp.interface.grupo_extras import DialogoPedidos
        dlg = DialogoPedidos(pai or self.dlg, self.prov, self.conv.id,
                             self.conv.nome, self.jan.fala)
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()

    def ver_foto(self):
        """Baixa a foto do grupo e abre no programa de imagens do Windows."""
        jan = self.jan
        jan.fala.falar("Baixando a foto do grupo...", interromper=True)

        def depois(resultado):
            if not resultado or not resultado[0]:
                texto = resultado[1] if resultado else "Não consegui a foto."
                jan.fala.falar(texto, interromper=True)
                if self.dlg is not None:
                    wx.MessageBox(texto, "Foto do grupo",
                                  wx.OK | wx.ICON_INFORMATION, self.dlg)
                return
            from telezapp.nucleo import grupo as ng
            try:
                pasta = os.path.join(tempfile.gettempdir(), "TeleZapp-fotos")
                os.makedirs(pasta, exist_ok=True)
                caminho = os.path.join(pasta, "grupo-%s%s" % (
                    "".join(c for c in self.conv.id if c.isalnum()),
                    ng.extensao_da_imagem(resultado[1])))
                with open(caminho, "wb") as f:
                    f.write(resultado[1])
                if os.name != "nt":
                    jan.fala.falar(caminho)
                    return
                os.startfile(caminho)
            except OSError:
                log.error("foto do grupo:\n%s", traceback.format_exc())
                jan.fala.falar("Não consegui abrir a foto.",
                               interromper=True)
                return
            jan.fala.falar("Foto aberta.", interromper=True)
        self._em_segundo_plano(
            "foto-do-grupo", lambda: self.prov.foto_do_grupo(self.conv.id),
            depois)

    def trocar_foto(self, pai=None):
        """Escolhe uma imagem e a poe como foto do grupo."""
        from telezapp.interface.perfil import FILTRO_DE_IMAGENS
        from telezapp.nucleo import perfil as np_
        alvo = pai or self.dlg
        dlg = wx.FileDialog(alvo, "Escolher a foto do grupo",
                            wildcard=FILTRO_DE_IMAGENS,
                            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            caminho = dlg.GetPath()
        finally:
            dlg.Destroy()
        try:
            foto = np_.preparar_foto(caminho)
        except ValueError as e:
            wx.MessageBox(str(e), "Foto do grupo", wx.OK | wx.ICON_WARNING,
                          alvo)
            return
        r = wx.MessageBox("Usar %s como foto do grupo %s?" % (
            os.path.basename(caminho), self.conv.nome), "Foto do grupo",
            wx.YES_NO | wx.ICON_QUESTION, alvo)
        if r == wx.YES:
            self.administrar("foto", foto, pai)

    def adicionar_a_grupo(self):
        """Da conversa com uma pessoa: escolhe um grupo que a conta
        administra e a adiciona nele."""
        jan = self.jan
        jan.fala.falar("Procurando os grupos que você administra...",
                       interromper=True)

        def depois(grupos):
            if self.dlg is None:
                return
            if not grupos:
                jan.fala.falar("Você não administra nenhum grupo.",
                               interromper=True)
                wx.MessageBox("Você não administra nenhum grupo.",
                              "Adicionar a um grupo",
                              wx.OK | wx.ICON_INFORMATION, self.dlg)
                return
            dlg = wx.SingleChoiceDialog(
                self.dlg, "Em qual grupo adicionar %s?" % self.conv.nome,
                "Adicionar a um grupo", [nome for _, nome in grupos])
            try:
                if dlg.ShowModal() != wx.ID_OK:
                    return
                cid, nome = grupos[dlg.GetSelection()]
            finally:
                dlg.Destroy()
            self._adicionar_em(cid, nome)
        self._em_segundo_plano("grupos-admin", self.prov.grupos_que_administro,
                               depois)

    def _adicionar_em(self, cid, nome):
        jan = self.jan
        jan.fala.falar("Adicionando ao grupo...", interromper=True)
        pessoa = self.conv.id

        def depois(resultado):
            ok, texto = resultado or (False, "Não consegui adicionar.")
            if ok:
                texto = "%s foi adicionado ao grupo %s." % (
                    self.conv.nome, nome)
            jan.fala.falar(texto, interromper=True)
            if self.dlg is not None:
                wx.MessageBox(texto, "Adicionar a um grupo", wx.OK | (
                    wx.ICON_INFORMATION if ok else wx.ICON_WARNING),
                    self.dlg)
        self._em_segundo_plano(
            "adicionar-ao-grupo", lambda: self.prov.administrar_grupo(
                cid, "adicionar", pessoa), depois)

    # ---- administracao
    def administrar_grupo(self):
        if not self.dados:
            return
        self._sub(DialogoAdministrar(self.dlg, self, self.dados))

    def administrar(self, acao, valor, pai=None):
        jan = self.jan
        if self.prov is None:
            jan.fala.falar("A conta não está disponível.")
            return
        jan.fala.falar("Enviando ao serviço...", interromper=True)

        def trabalho():
            try:
                ok, texto = self.prov.administrar_grupo(self.conv.id, acao,
                                                        valor)
            except Exception as e:
                log.error("administrar:\n%s", traceback.format_exc())
                ok, texto = False, "Erro: %s" % type(e).__name__
            wx.CallAfter(self._resultado, acao, ok, texto, pai)
        threading.Thread(target=trabalho, daemon=True,
                         name="administrar").start()

    def _resultado(self, acao, ok, texto, pai):
        jan = self.jan
        jan.fala.falar(texto, interromper=True)
        alvo = pai or self.dlg
        if not ok:
            wx.MessageBox(texto, "Administrar grupo",
                          wx.OK | wx.ICON_WARNING, alvo)
        if ok and acao == "sair":
            if pai is not None:
                pai.EndModal(wx.ID_OK)
            if self.dlg is not None:
                self.dlg.EndModal(wx.ID_OK)
            return
        if ok and acao in ("nome", "descricao", "anuncio", "trancado",
                           "adicionar", "remover", "promover", "rebaixar"):
            self._atualizar()

    # ---- canal
    def silenciar_canal(self):
        silenciar = not (self.dados or {}).get("silenciado")
        self._canal("silenciar", silenciar)

    def deixar_de_seguir(self):
        r = wx.MessageBox("Deixar de seguir o canal %s?" % self.conv.nome,
                          "Deixar de seguir",
                          wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
                          self.dlg)
        if r == wx.YES:
            self._canal("deixar_de_seguir", None)

    def _canal(self, acao, valor):
        jan = self.jan
        jan.fala.falar("Enviando ao serviço...", interromper=True)

        def trabalho():
            try:
                ok, texto = self.prov.administrar_canal(self.conv.id, acao,
                                                        valor)
            except Exception as e:
                ok, texto = False, "Erro: %s" % type(e).__name__
            wx.CallAfter(self._resultado_canal, acao, ok, texto)
        threading.Thread(target=trabalho, daemon=True,
                         name="canal").start()

    def _manter_ou_apagar_canal(self):
        """Depois de deixar de seguir: manter o canal na lista ou apagar a
        conversa e as mensagens guardadas aqui."""
        jan, conv = self.jan, self.conv
        r = wx.MessageBox(
            "Você deixou de seguir o canal %s.\n\nApagar a conversa da "
            "lista e as mensagens guardadas no TeleZapp? Sim apaga; Não "
            "mantém o canal na lista." % conv.nome, "Canal deixado de seguir",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self.dlg)
        if r != wx.YES:
            return
        if conv.chave in jan.indice:
            jan._remover_conversa_local(conv)
        jan.fala.falar("Conversa apagada da lista.", interromper=True)

    def _resultado_canal(self, acao, ok, texto):
        self.jan.fala.falar(texto, interromper=True)
        if not ok:
            wx.MessageBox(texto, "Canal", wx.OK | wx.ICON_WARNING, self.dlg)
            return
        if acao == "deixar_de_seguir":
            self._manter_ou_apagar_canal()
            if self.dlg is not None:
                self.dlg.EndModal(wx.ID_OK)
            return
        if self.dlg is not None:
            self._atualizar()


class ControleRecibos(object):
    """Quem recebeu, abriu e reproduziu uma mensagem enviada a um grupo: um
    botao por assunto na janela de detalhes da mensagem, cada um abrindo a
    lista de membros com a data e a hora, e o menu de contexto dos membros."""

    def __init__(self, jan, conv, recibos, nomes):
        self.jan, self.conv = jan, conv
        self.por_tipo = m.pessoas_por_recibo(recibos)
        self.nomes = nomes or {}
        self.abrir_conversa = None
        # as acoes de um membro sao as mesmas da lista de membros do grupo
        self._membros = _MembrosDeRecibo(jan, conv, self)

    def botoes(self):
        """[(rotulo, funcao(janela))] dos assuntos que tem alguem."""
        saida = []
        for tipo, rotulo, _ in m.ROTULOS_RECIBO:
            n = len(self.por_tipo[tipo])
            if n:
                saida.append(("%s por %s" % (rotulo, m.texto_pessoas(n)),
                              lambda dlg, t=tipo: self.lista(t, dlg)))
        return saida

    def pessoa(self, quem):
        nome = self.nomes.get(quem) or m._quem_legivel(quem)
        return {"id": quem, "nome": nome}

    def rotulo(self, quem, data):
        p = self.pessoa(quem)
        partes = [p["nome"]]
        if quem.endswith("@s.whatsapp.net") and \
                p["nome"] != "+" + quem.split("@")[0]:
            partes.append("+" + quem.split("@")[0])
        partes.append(time.strftime("%d/%m/%Y %H:%M:%S",
                                    time.localtime(data)) if data else "-")
        return ", ".join(partes)

    def lista(self, tipo, dlg):
        rotulo = next(r for t, r, _ in m.ROTULOS_RECIBO if t == tipo)
        verbo = next(v for t, _, v in m.ROTULOS_RECIBO if t == tipo)
        pessoas = self.por_tipo[tipo]

        def itens(_):
            return [(self.rotulo(q, d), self.pessoa(q)) for q, d in pessoas]
        lista = DialogoLista(
            dlg, "%s por %s" % (rotulo, m.texto_pessoas(len(pessoas))),
            "Quem %s a mensagem (Menu abre as ações)" % verbo, (), itens,
            self._membros._menu_membro)
        self._membros.pai = dlg
        self._membros._sub(lista)


class _MembrosDeRecibo(object):
    """O menu de um membro, o mesmo da lista de membros do grupo."""

    def __init__(self, jan, conv, dono):
        self.jan, self.conv, self.dono = jan, conv, dono
        self.dados = None
        self.abrir_conversa = None
        self.ver = None
        self.dlg = None
        self.pai = None
        self.prov = jan.contas.provedor(conv.conta_id) if jan.contas \
            else None

    _menu_membro = ControleDetalhes._menu_membro
    _opcoes_de_conversa = ControleDetalhes._opcoes_de_conversa

    def _iniciar(self, c):
        self.abrir_conversa = c
        wx.CallAfter(self._fechar_tudo)

    def _fechar_tudo(self):
        for w in wx.GetTopLevelWindows():
            if isinstance(w, DialogoLista) and w.IsModal():
                w.EndModal(wx.ID_OK)

    def _sub(self, dlg):
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()
        if self.abrir_conversa is not None:
            self.dono.abrir_conversa = self.abrir_conversa
            if self.pai is not None:
                self.pai.EndModal(wx.ID_OK)       # fecha os detalhes tambem

    def administrar(self, *a, **k):
        pass

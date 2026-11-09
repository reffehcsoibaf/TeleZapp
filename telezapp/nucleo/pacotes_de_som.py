# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Pacotes de sons: o Padrao (bips do sistema), o TeleZapp (os arquivos que
vem com o programa) e os pacotes personalizados da pessoa, cada um numa pasta
com um arquivo por evento (`nova.ogg`, `erro.mp3`...). Sem wx, para testar.

O Padrao e os da casa (TeleZapp, Cristal, Marimba, Retro e Suave) nao se editam. Em um personalizado, o som de cada evento e
um arquivo importado para a pasta do pacote quando a pessoa aplica. Cada
evento de cada pacote pode estar ativado ou desativado.
"""
import hashlib
import os
import re
import shutil

from telezapp import config
from telezapp.acessibilidade.fala import BIP, HERDA

PADRAO, TELEZAPP = "padrao", "telezapp"
PREFIXO = "p:"                       # id de um pacote personalizado
# pacotes que vem com o programa: o TeleZapp fica em sons/ e os outros em
# sons/pacotes/<id>/ (gerados por ferramentas/gerar_sons.py)
NOMES_DA_CASA = {TELEZAPP: "TeleZapp", "cristal": "Cristal",
                 "marimba": "Marimba", "retro": "Retrô", "suave": "Suave"}
NOMES_FIXOS = {PADRAO: "Padrão: bips do sistema", **NOMES_DA_CASA}
PASTA_TELEZAPP = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "sons")


def da_casa(pacote_id):
    return pacote_id in NOMES_DA_CASA


def _pasta_da_casa(pacote_id):
    if pacote_id == TELEZAPP:
        return PASTA_TELEZAPP
    return os.path.join(PASTA_TELEZAPP, "pacotes", pacote_id)
EXTENSOES = (".ogg", ".opus", ".mp3", ".wav", ".flac")
# Num pacote personalizado sem arquivo para eles, seguem o evento de que herdam
# (HERDA), ligado ou nao, e nada muda ate a pessoa escolher um som
EVENTOS_QUE_SEGUEM = ("nova_pessoal", "nova_canal", "nova_comunidade")
# Os sons por servico (nova_pessoal_telegram...) tambem seguem o evento comum
# ate a pessoa dar um arquivo a eles
VARIANTES_POR_SERVICO = tuple(
    "%s_%s" % (_e, _s) for _e in (
        "nova_aberta", "nova_pessoal", "nova_grupo", "nova_canal",
        "nova_comunidade", "mencao_ou_resposta", "reacao_recebida",
        "voto_enquete", "toque", "desligada")
    for _s in ("whatsapp", "telegram"))
_PROIBIDOS = re.compile(r'[\\/:*?"<>|]')


def eventos():
    """[(chave, rotulo)] dos eventos que tocam um som."""
    return [(nome, rotulo) for nome, rotulo, _ in config.EVENTOS_SOM]


def descricao_do_evento(chave):
    return next((d for n, _, d in config.EVENTOS_SOM if n == chave), "")


def pasta_dos_pacotes():
    return config.pasta("sons", "pacotes")


def editavel(pacote_id):
    return pacote_id.startswith(PREFIXO)


def nome_do_pacote(pacote_id):
    if pacote_id in NOMES_FIXOS:
        return NOMES_FIXOS[pacote_id]
    return pacote_id[len(PREFIXO):]


def pasta_do_pacote(pacote_id):
    return os.path.join(pasta_dos_pacotes(), pacote_id[len(PREFIXO):])


def arquivos_da_pasta(pacote_id):
    """[(nome, caminho)] dos sons aceitos na pasta do pacote, em ordem. So os
    pacotes personalizados tem pasta editavel: os da casa devolvem []."""
    if not editavel(pacote_id):
        return []
    pasta = pasta_do_pacote(pacote_id)
    if not os.path.isdir(pasta):
        return []
    nomes = [nome for nome in os.listdir(pasta)
             if os.path.splitext(nome)[1].lower() in EXTENSOES
             and os.path.isfile(os.path.join(pasta, nome))]
    return [(nome, os.path.join(pasta, nome))
            for nome in sorted(nomes, key=str.lower)]


def listar():
    """[(id, nome)] dos pacotes que existem: os da casa e depois os
    personalizados, em ordem alfabetica."""
    achados = list(NOMES_FIXOS.items())
    raiz = pasta_dos_pacotes()
    for nome in sorted(os.listdir(raiz), key=str.lower):
        if os.path.isdir(os.path.join(raiz, nome)):
            achados.append((PREFIXO + nome, nome))
    return achados


def nome_valido(nome, existentes=()):
    """(nome limpo, erro): "" no erro se serve como nome de pacote."""
    nome = " ".join((nome or "").split())
    if not nome:
        return "", "Digite um nome para o pacote."
    if len(nome) > 40 or _PROIBIDOS.search(nome) or nome.endswith("."):
        return "", ("O nome não pode passar de 40 letras nem ter "
                    "\\ / : * ? \" < > |.")
    if nome.lower() in {n.lower() for n in existentes} or \
            nome.lower() in {n.lower() for n in NOMES_FIXOS.values()}:
        return "", "Já existe um pacote com este nome."
    return nome, ""


def arquivo_do_evento(pacote_id, evento):
    """O arquivo do evento no pacote, ou "" se nao ha."""
    if da_casa(pacote_id):
        pasta = _pasta_da_casa(pacote_id)
    elif editavel(pacote_id):
        pasta = pasta_do_pacote(pacote_id)
    else:
        return ""
    for ext in EXTENSOES:
        caminho = os.path.join(pasta, evento + ext)
        if os.path.isfile(caminho):
            return caminho
    return ""


def valor_do_evento(pacote_id, evento, desativados=()):
    """O valor que o modulo de sons entende: "desligado", o caminho do
    arquivo ou o bip do sistema."""
    if evento in desativados:
        return "desligado"
    if evento in EVENTOS_QUE_SEGUEM or evento in VARIANTES_POR_SERVICO:
        return arquivo_do_evento(pacote_id, evento)
    return arquivo_do_evento(pacote_id, evento) or BIP


def mapa(pacote_id, desativados=()):
    """{evento: valor} do pacote, para fala.definir_sons."""
    return {e: valor_do_evento(pacote_id, e, desativados)
            for e, _ in eventos()}


def evento_da_conversa(conv):
    """O som de mensagem nova numa conversa que nao esta aberta."""
    if conv.tipo == "grupo":
        return "nova_comunidade" if conv.comunidade else "nova_grupo"
    return {"canal": "nova_canal", "privada": "nova_pessoal"}.get(conv.tipo,
                                                                  "nova")


# ------------------------------------------------- som proprio de uma conversa
def _chave_da_conversa(chave):
    return "%s|%s" % chave


def arquivo_da_conversa(cfg, chave):
    """O arquivo de som proprio da conversa (conta, id), ou "" se ela nao tem
    ou se o arquivo sumiu."""
    nome = (cfg.get("sons_de_conversa") or {}).get(_chave_da_conversa(chave))
    if not nome:
        return ""
    caminho = os.path.join(config.pasta("sons", "conversas"),
                           os.path.basename(nome))
    return caminho if os.path.isfile(caminho) else ""


def definir_som_da_conversa(cfg, chave, origem):
    """Copia o arquivo para a pasta de sons (o original pode sumir) e o guarda
    como o som da conversa. OSError se nao der para copiar."""
    texto = _chave_da_conversa(chave)
    ext = os.path.splitext(origem)[1].lower() or ".wav"
    nome = hashlib.sha1(texto.encode("utf-8")).hexdigest()[:16] + ext
    destino = os.path.join(config.pasta("sons", "conversas"), nome)
    antigo = arquivo_da_conversa(cfg, chave)
    if os.path.normcase(os.path.abspath(origem)) != \
            os.path.normcase(os.path.abspath(destino)):
        shutil.copyfile(origem, destino)
    if antigo and os.path.normcase(antigo) != os.path.normcase(destino):
        _apagar(antigo)
    sons = dict(cfg.get("sons_de_conversa") or {})
    sons[texto] = nome
    cfg.set("sons_de_conversa", sons)
    return destino


def remover_som_da_conversa(cfg, chave):
    antigo = arquivo_da_conversa(cfg, chave)
    if antigo:
        _apagar(antigo)
    sons = dict(cfg.get("sons_de_conversa") or {})
    if sons.pop(_chave_da_conversa(chave), None) is not None:
        cfg.set("sons_de_conversa", sons)


def _apagar(caminho):
    try:
        os.remove(caminho)
    except OSError:
        pass


def criar(nome):
    """Cria a pasta do pacote personalizado -> (id, erro)."""
    nome, erro = nome_valido(nome, [n for _, n in listar()])
    if erro:
        return "", erro
    os.makedirs(os.path.join(pasta_dos_pacotes(), nome), exist_ok=True)
    return PREFIXO + nome, ""


def excluir(pacote_id):
    if editavel(pacote_id):
        shutil.rmtree(pasta_do_pacote(pacote_id), ignore_errors=True)


def importar_arquivo(pacote_id, evento, origem):
    """Copia o arquivo para a pasta do pacote como `<evento><extensao>`,
    trocando o que o evento tinha. Devolve o caminho novo."""
    pasta = pasta_do_pacote(pacote_id)
    os.makedirs(pasta, exist_ok=True)
    ext = os.path.splitext(origem)[1].lower() or ".wav"
    destino = os.path.join(pasta, evento + ext)
    antigo = arquivo_do_evento(pacote_id, evento)
    if os.path.normcase(os.path.abspath(origem)) != \
            os.path.normcase(os.path.abspath(destino)):
        shutil.copyfile(origem, destino)
    if antigo and os.path.normcase(antigo) != os.path.normcase(destino):
        try:
            os.remove(antigo)
        except OSError:
            pass
    return destino


# ------------------------------------------------- vindo da versao anterior
def migrar_antigos(cfg):
    """Quem escolheu um arquivo de som por evento (opcoes som_*) ganha um
    pacote personalizado chamado "Personalizado" com esses arquivos, e passa
    a usa-lo. "Sem som" vira evento desativado. Roda uma vez: as chaves
    antigas saem da configuracao."""
    antigas = {k[4:]: cfg.dados.pop(k) for k in list(cfg.dados)
               if k.startswith("som_") and k != "som"}
    if cfg.get("pacote_de_sons") not in NOMES_FIXOS and \
            not str(cfg.get("pacote_de_sons") or "").startswith(PREFIXO):
        cfg.dados["pacote_de_sons"] = PADRAO      # valor de versao antiga
    escolhas = {e: v for e, v in antigas.items()
                if v and e in dict(eventos())}
    if not escolhas:
        if antigas:
            cfg.salvar()
        return
    pacote_id, erro = criar("Personalizado")
    if erro:                                   # ja existe: usa o que tem
        pacote_id = PREFIXO + "Personalizado"
    desativados = []
    for evento, valor in escolhas.items():
        if valor == "desligado":
            desativados.append(evento)
            continue
        origem = valor if os.path.isabs(valor) else os.path.join(
            config.pasta_sons(), valor)
        if os.path.isfile(origem):
            try:
                importar_arquivo(pacote_id, evento, origem)
            except OSError:
                pass
    cfg.dados["pacote_de_sons"] = pacote_id
    cfg.dados["sons_desativados"] = {pacote_id: sorted(desativados)}
    cfg.salvar()


EVENTOS_DO_SOM_DE_MENSAGEM = ("nova", "nova_aberta", "nova_grupo",
                              "nova_pessoal", "nova_canal", "nova_comunidade")
EVENTOS_DO_SOM_DE_CHAMADA = ("toque", "chamando")


def migrar_liga_desliga(cfg):
    """As opcoes "Som ao receber mensagem" e "Som de chamada" sairam de
    Avisos (cada som se liga e desliga na tela de sons). Quem as tinha
    desligadas fica com os eventos delas desativados em todos os pacotes
    que existem. Roda uma vez: as chaves antigas saem da configuracao."""
    sem = object()
    som = cfg.dados.pop("som", sem)
    toque = cfg.dados.pop("toque_chamada", sem)
    if som is sem and toque is sem:
        return
    desligar = set()
    if som is False:
        desligar.update(EVENTOS_DO_SOM_DE_MENSAGEM)
    if toque is False:
        desligar.update(EVENTOS_DO_SOM_DE_CHAMADA)
    if desligar:
        guardado = {k: list(v) for k, v in
                    (cfg.get("sons_desativados") or {}).items()}
        for pacote in {*NOMES_FIXOS, cfg.get("pacote_de_sons")}:
            if pacote:
                guardado[pacote] = sorted(set(guardado.get(pacote, []))
                                          | desligar)
        cfg.dados["sons_desativados"] = guardado
    cfg.salvar()


def migrar_tipos_de_conversa(cfg):
    """Os sons de mensagem individual, de canal e de comunidade vieram depois:
    quem desligou o som de que eles nasceram continua sem som. Roda uma vez."""
    if cfg.dados.get("sons_por_tipo_migrados"):
        return
    guardado = {}
    for pacote, lista in (cfg.get("sons_desativados") or {}).items():
        novos = set(lista)
        for evento in EVENTOS_QUE_SEGUEM:
            if HERDA[evento] in novos:
                novos.add(evento)
        guardado[pacote] = sorted(novos)
    cfg.dados["sons_desativados"] = guardado
    cfg.dados["sons_por_tipo_migrados"] = True
    cfg.salvar()


class EstadoDeSons:
    """O que a pessoa mexeu na tela de sons e ainda nao aplicou: pacote
    escolhido, eventos ativados ou desativados, arquivos novos, pacotes a
    criar e a excluir. Nada vai para o disco antes de aplicar()."""

    def __init__(self, cfg):
        self.cfg = cfg
        atual = cfg.get("pacote_de_sons")
        self.ativo = atual if atual in dict(listar()) else PADRAO
        guardado = cfg.get("sons_desativados") or {}
        self.desativados = {p: set(v) for p, v in guardado.items()
                            if isinstance(v, list)}
        self.arquivos = {}          # pacote -> {evento: arquivo de origem}
        self.novos = []             # nomes de pacotes a criar
        self.excluidos = set()
        self.mexeu = False

    # ------------------------------------------------------------ consulta
    def pacotes(self):
        """[(id, nome)] com os pacotes novos e sem os excluidos."""
        lista = [(i, n) for i, n in listar() if i not in self.excluidos]
        lista += [(PREFIXO + n, n) for n in self.novos]
        return lista

    def ativado(self, pacote_id, evento):
        return evento not in self.desativados.get(pacote_id, ())

    def arquivo(self, pacote_id, evento):
        """O arquivo que o evento terá: o escolhido agora, o que já está no
        pacote, ou "" (bip do sistema)."""
        if not editavel(pacote_id) and not da_casa(pacote_id):
            return ""
        pendente = self.arquivos.get(pacote_id, {}).get(evento)
        if pendente:
            return pendente
        if nome_do_pacote(pacote_id) in self.novos:
            return ""                      # ainda nao existe no disco
        return arquivo_do_evento(pacote_id, evento)

    def texto_do_evento(self, pacote_id, evento, rotulo):
        """"Mensagem recebida: ativado, som: nova.ogg" para a lista."""
        partes = [rotulo[:1].upper() + rotulo[1:] + ": " + (
            "ativado" if self.ativado(pacote_id, evento) else "desativado")]
        if pacote_id != PADRAO:
            arq = self.arquivo(pacote_id, evento)
            if not arq and evento in EVENTOS_QUE_SEGUEM:
                partes.append("som: o mesmo de " + dict(eventos())[HERDA[evento]])
            else:
                partes.append("som: " + (os.path.basename(arq) if arq
                                         else "bip do sistema"))
        return ", ".join(partes)

    def valor_para_ouvir(self, pacote_id, evento):
        """O valor que fala.bipe toca para ouvir o evento agora, ativado ou
        nao."""
        arq = self.arquivo(pacote_id, evento)
        while not arq and evento in EVENTOS_QUE_SEGUEM:
            evento = HERDA[evento]
            arq = self.arquivo(pacote_id, evento)
        return arq or BIP

    def mudou(self):
        return self.mexeu

    # ------------------------------------------------------------- mudancas
    def alternar(self, pacote_id, evento):
        """Ativa ou desativa o evento -> o novo estado (True = ativado)."""
        conjunto = self.desativados.setdefault(pacote_id, set())
        if evento in conjunto:
            conjunto.discard(evento)
        else:
            conjunto.add(evento)
        self.mexeu = True
        return evento not in conjunto

    def escolher(self, pacote_id, evento, origem):
        if not editavel(pacote_id):
            return
        self.arquivos.setdefault(pacote_id, {})[evento] = origem
        self.mexeu = True

    def selecionar(self, pacote_id):
        if pacote_id != self.ativo:
            self.ativo = pacote_id
            self.mexeu = True

    def redefinir(self):
        """Pacote da casa e todos os eventos ativados, em todos os pacotes."""
        if self.ativo == PADRAO and not any(self.desativados.values()):
            return
        self.ativo = PADRAO
        self.desativados = {}
        self.mexeu = True

    def criar(self, nome):
        """-> (id, erro). O pacote so existe no disco depois de aplicar."""
        nome, erro = nome_valido(nome, [n for _, n in self.pacotes()])
        if erro:
            return "", erro
        self.novos.append(nome)
        self.mexeu = True
        return PREFIXO + nome, ""

    def excluir(self, pacote_id):
        """-> erro ("" se foi). Os dois pacotes da casa não se excluem."""
        if not editavel(pacote_id):
            return "Este pacote não pode ser excluído."
        nome = nome_do_pacote(pacote_id)
        if nome in self.novos:
            self.novos.remove(nome)
        else:
            self.excluidos.add(pacote_id)
        self.arquivos.pop(pacote_id, None)
        self.desativados.pop(pacote_id, None)
        if self.ativo == pacote_id:
            self.ativo = PADRAO
        self.mexeu = True
        return ""

    # -------------------------------------------------------------- aplicar
    def aplicar(self):
        """Exclui, cria e importa no disco, e devolve o que guardar:
        {"ativo": id, "desativados": {pacote: [eventos]}, "erros": [texto]}."""
        erros = []
        for pacote_id in self.excluidos:
            excluir(pacote_id)
        for nome in self.novos:
            _, erro = criar(nome)
            if erro and not os.path.isdir(os.path.join(
                    pasta_dos_pacotes(), nome)):
                erros.append(erro)
        for pacote_id, por_evento in self.arquivos.items():
            for evento, origem in por_evento.items():
                try:
                    importar_arquivo(pacote_id, evento, origem)
                except OSError as e:
                    erros.append("Não consegui importar %s: %s" % (
                        os.path.basename(origem), e.strerror or type(e).__name__))
        existentes = {i for i, _ in listar()}
        resultado = {
            "ativo": self.ativo if self.ativo in existentes else PADRAO,
            "desativados": {p: sorted(v) for p, v in self.desativados.items()
                            if v and p in existentes},
            "erros": erros}
        self.arquivos, self.novos, self.excluidos = {}, [], set()
        self.mexeu = False
        return resultado

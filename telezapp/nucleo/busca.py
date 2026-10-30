# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Busca por critérios nas mensagens guardadas.

Sem wx. `Criterios` junta o que a pessoa marcou na janela de busca; cada
critério só vale se estiver preenchido (vazio = não filtra). Todos os
critérios preenchidos precisam ser verdadeiros ao mesmo tempo. Dentro de uma
lista (tipos de mensagem, por exemplo), basta uma das opções.

A busca roda no banco do TeleZapp: o que está guardado, não o que existe na
conta. Os filtros de estrutura (conta, serviço, tipo, data...) vão para o SQL;
o texto (sem maiúsculas nem acentos) e as marcas guardadas em `extras` são
conferidos aqui.
"""
import time
import unicodedata
from dataclasses import dataclass, field

from telezapp.nucleo import modelos as m

# Situacao da conversa (todas as marcadas precisam valer)
SITUACOES = (
    ("arquivada", "Arquivada"),
    ("fixada", "Fixada"),
    ("silenciada", "Silenciada"),
    ("nao_lida", "Com mensagens não lidas"),
    ("trancada", "Trancada no celular"),
    ("temporaria", "Com mensagens temporárias"),
    ("somente_leitura", "Somente leitura"),
)

# Tipo de conversa
TIPOS_DE_CONVERSA = (
    ("privada", "Conversa com uma pessoa"),
    ("grupo", "Grupo"),
    ("canal", "Canal"),
)

# Tipo de conteudo da mensagem (basta uma das marcadas)
TIPOS_DE_MENSAGEM = (
    (m.TEXTO, "Texto"),
    (m.FOTO, "Foto"),
    (m.VIDEO, "Vídeo"),
    (m.VOZ, "Mensagem de voz"),
    (m.AUDIO, "Áudio"),
    (m.DOCUMENTO, "Documento"),
    (m.FIGURINHA, "Figurinha"),
    ("enquete", "Enquete"),
    (m.OUTRO, "Outros"),
)

# Caracteristicas da mensagem (todas as marcadas precisam valer)
CARACTERISTICAS = (
    ("favorita", "Favorita"),
    ("com_midia", "Com foto, vídeo, áudio, voz, documento ou figurinha"),
    ("com_link", "Com link"),
    ("com_mencao", "Com menção"),
    ("resposta", "É resposta a outra mensagem"),
    ("com_reacao", "Com reações"),
    ("cita_voce", "Cita ou responde a você"),
    ("editada", "Editada"),
    ("apagada", "Apagada pelo remetente"),
    ("ouvida", "Áudio ou voz já ouvido"),
    ("nao_ouvida", "Áudio ou voz ainda não ouvido"),
    ("com_botoes", "Com botões"),
    ("temporaria", "Mensagem temporária"),
    ("com_ia", "Com transcrição ou descrição feita por IA"),
)

# Estado de uma mensagem que eu enviei
ESTADOS_DE_ENVIO = (
    (m.ENVIADA, "Enviada"),
    (m.ENTREGUE, "Entregue"),
    (m.LIDA, "Lida"),
    (m.REPRODUZIDA, "Ouvida pela outra pessoa"),
    (m.FALHOU, "Falhou"),
)

_MIDIAS = (m.FOTO, m.VIDEO, m.VOZ, m.AUDIO, m.DOCUMENTO, m.FIGURINHA)


def normalizar(texto):
    """Minúsculas e sem acentos, para comparar."""
    base = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in base if not unicodedata.combining(c)).lower()


@dataclass
class Criterios:
    termo: str = ""
    frase_exata: bool = False      # False: todas as palavras, em qualquer ordem
    servicos: set = field(default_factory=set)        # "whatsapp", "telegram"
    contas: set = field(default_factory=set)          # ids de conta
    tipos_de_conversa: set = field(default_factory=set)
    situacoes: set = field(default_factory=set)
    conversa_contem: str = ""      # parte do nome da conversa
    tipos_de_mensagem: set = field(default_factory=set)
    caracteristicas: set = field(default_factory=set)
    minha: object = None           # True: so as minhas; False: so as dos outros
    autor_contem: str = ""         # parte do nome de quem enviou
    data_de: object = None         # timestamp do inicio do dia
    data_ate: object = None        # timestamp do FIM do dia
    segundos_min: object = None
    segundos_max: object = None
    tamanho_min: object = None     # em bytes
    tamanho_max: object = None
    estados_de_envio: set = field(default_factory=set)
    mais_antigas_primeiro: bool = False
    limite: int = 500
    incluir_trancadas: bool = False   # so com as trancadas liberadas

    def vazio(self):
        """Sem nenhum criterio preenchido?"""
        return not any((
            self.termo.strip(), self.servicos, self.contas,
            self.tipos_de_conversa, self.situacoes,
            self.conversa_contem.strip(), self.tipos_de_mensagem,
            self.caracteristicas, self.minha is not None,
            self.autor_contem.strip(), self.data_de is not None,
            self.data_ate is not None, self.segundos_min is not None,
            self.segundos_max is not None, self.tamanho_min is not None,
            self.tamanho_max is not None, self.estados_de_envio))

    def resumo(self, nome_de_conta=lambda c: c):
        """Os criterios preenchidos, em uma frase, para o leitor de tela."""
        nomes = dict(SITUACOES)
        partes = []
        if self.termo.strip():
            partes.append(("frase " if self.frase_exata else "") +
                          "“%s”" % self.termo.strip())
        if self.servicos:
            partes.append("serviço " + " ou ".join(
                m.SERVICOS.get(s, s) for s in sorted(self.servicos)))
        if self.contas:
            partes.append("conta " + " ou ".join(
                nome_de_conta(c) for c in sorted(self.contas)))
        if self.tipos_de_conversa:
            rot = dict(TIPOS_DE_CONVERSA)
            partes.append(" ou ".join(
                rot.get(t, t).lower() for t in sorted(self.tipos_de_conversa)))
        for s in sorted(self.situacoes):
            partes.append("conversa " + nomes.get(s, s).lower())
        if self.conversa_contem.strip():
            partes.append("conversa com “%s” no nome" %
                          self.conversa_contem.strip())
        if self.tipos_de_mensagem:
            rot = dict(TIPOS_DE_MENSAGEM)
            partes.append(" ou ".join(
                rot.get(t, t).lower() for t in sorted(self.tipos_de_mensagem)))
        rot = dict(CARACTERISTICAS)
        for c in sorted(self.caracteristicas):
            partes.append(rot.get(c, c).lower())
        if self.minha is True:
            partes.append("enviadas por você")
        elif self.minha is False:
            partes.append("enviadas por outras pessoas")
        if self.autor_contem.strip():
            partes.append("de quem tem “%s” no nome" %
                          self.autor_contem.strip())
        if self.data_de is not None:
            partes.append("a partir de " + _dia(self.data_de))
        if self.data_ate is not None:
            partes.append("até " + _dia(self.data_ate))
        if self.segundos_min is not None:
            partes.append("com pelo menos %d s" % self.segundos_min)
        if self.segundos_max is not None:
            partes.append("com no máximo %d s" % self.segundos_max)
        if self.tamanho_min is not None:
            partes.append("com pelo menos " + m.tamanho_legivel(
                self.tamanho_min))
        if self.tamanho_max is not None:
            partes.append("com no máximo " + m.tamanho_legivel(
                self.tamanho_max))
        rot = dict(ESTADOS_DE_ENVIO)
        for e in sorted(self.estados_de_envio):
            partes.append("minha mensagem " + rot.get(e, e).lower())
        return ", ".join(partes) if partes else "sem critérios"


def _dia(ts):
    return time.strftime("%d/%m/%Y", time.localtime(ts))


@dataclass
class Achado:
    mensagem: object
    conversa: object
    trecho: str

    def texto_da_lista(self, nome_de_conta=None):
        x = self.mensagem
        quando = time.strftime("%d/%m/%Y %H:%M", time.localtime(x.data))
        quem = m.meu_nome() if x.minha else (x.autor or self.conversa.nome)
        onde = self.conversa.nome
        conta = (" (%s)" % nome_de_conta(x.conta_id)) if nome_de_conta else ""
        return "%s, %s%s, %s: %s" % (onde, quando, conta, quem, self.trecho)


# ------------------------------------------------------- datas e medidas
def ler_data(texto, fim_do_dia=False):
    """Timestamp de 'dd/mm/aaaa' (ou 'aaaa-mm-dd'); None se vazio ou
    invalido. Com `fim_do_dia`, e o ultimo segundo do dia."""
    texto = (texto or "").strip()
    if not texto:
        return None
    for formato in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            t = time.strptime(texto, formato)
        except ValueError:
            continue
        base = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))
        return base + (86399 if fim_do_dia else 0)
    return None


def ler_numero(texto):
    """Numero (com virgula ou ponto) ou None."""
    texto = (texto or "").strip().replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


# ---------------------------------------------------------------- busca
def _tem_ia(extras):
    return bool((extras.get("ia") or {}).get("texto"))


def _caracteristica(nome, x, extras):
    if nome == "favorita":
        return extras["favorita"]
    if nome == "com_midia":
        return x.tipo in _MIDIAS
    if nome == "com_link":
        return bool(extras["links"]) or bool(extras["botoes"]) and any(
            len(b) > 1 and b[1] for b in extras["botoes"])
    if nome == "com_mencao":
        return bool(extras["mencoes"])
    if nome == "resposta":
        return bool(x.resposta_a)
    if nome == "com_reacao":
        return bool(extras["reacoes"])
    if nome == "cita_voce":
        return extras["citou_voce"]
    if nome == "editada":
        return extras["editada"]
    if nome == "apagada":
        return extras["apagada"]
    if nome == "ouvida":
        return x.tipo in (m.VOZ, m.AUDIO) and extras["ouvida"]
    if nome == "nao_ouvida":
        return x.tipo in (m.VOZ, m.AUDIO) and not extras["ouvida"]
    if nome == "com_botoes":
        return bool(extras["botoes"]) or bool(extras["acoes"])
    if nome == "temporaria":
        return x.expira > 0
    if nome == "com_ia":
        return _tem_ia(extras)
    return True


def _tipo_confere(tipos, x, extras):
    if not tipos:
        return True
    if "enquete" in tipos and extras["enquete"]:
        return True
    return x.tipo in tipos


def texto_pesquisavel(x, extras=None):
    """O que a busca do termo le numa mensagem: o texto ou a legenda, o nome
    do arquivo, a transcricao ou descricao feita por IA e as opcoes de uma
    enquete."""
    extras = extras or m.extras_de(x)
    partes = [x.texto, x.nome_arquivo, (extras.get("ia") or {}).get("texto")]
    enquete = extras["enquete"]
    if enquete:
        partes.append(str(enquete.get("pergunta") or ""))
        for o in enquete.get("opcoes") or []:
            partes.append(str(o.get("texto") if isinstance(o, dict) else o))
    return " ".join(p for p in partes if p)


def _trecho(x, extras, termo):
    """Um pedaco curto do texto em volta do termo, ou o resumo da mensagem."""
    texto = texto_pesquisavel(x, extras)
    if termo and texto:
        base, alvo = normalizar(texto), normalizar(termo)
        pos = base.find(alvo.split()[0] if alvo.split() else alvo)
        if pos >= 0 and len(base) == len(texto):
            ini = max(0, pos - 30)
            corte = texto[ini:ini + 100].replace("\n", " ")
            return ("…" if ini else "") + corte + (
                "…" if ini + 100 < len(texto) else "")
    return m.conteudo(x, com_estado=False).replace("\n", " ")[:120]


def buscar(banco, c, agora=None):
    """Lista de `Achado` das mensagens guardadas que atendem a todos os
    criterios de `c` (`Criterios`), das mais novas para as mais antigas (ou o
    contrario)."""
    agora = time.time() if agora is None else agora
    termo = normalizar(c.termo).strip()
    palavras = [termo] if c.frase_exata and termo else termo.split()
    autor = normalizar(c.autor_contem).strip()
    nome_da_conversa = normalizar(c.conversa_contem).strip()
    achados = []
    for x, conv in banco.buscar_mensagens(
            contas=c.contas, servicos=c.servicos,
            tipos_de_conversa=c.tipos_de_conversa, situacoes=c.situacoes,
            incluir_trancadas=c.incluir_trancadas, minha=c.minha, data_de=c.data_de, data_ate=c.data_ate,
            segundos_min=c.segundos_min, segundos_max=c.segundos_max,
            tamanho_min=c.tamanho_min, tamanho_max=c.tamanho_max,
            estados=c.estados_de_envio,
            mais_antigas_primeiro=c.mais_antigas_primeiro, agora=agora):
        if nome_da_conversa and nome_da_conversa not in normalizar(conv.nome):
            continue
        extras = m.extras_de(x)
        if not _tipo_confere(c.tipos_de_mensagem, x, extras):
            continue
        if any(not _caracteristica(n, x, extras) for n in c.caracteristicas):
            continue
        if autor and not any(autor in normalizar(q) for q in (
                (m.VOCE, m.meu_nome()) if x.minha
                else (x.autor or conv.nome,))):
            continue
        if palavras:
            texto = normalizar(texto_pesquisavel(x, extras))
            if any(p not in texto for p in palavras):
                continue
        achados.append(Achado(x, conv, _trecho(x, extras, termo)))
        if len(achados) >= c.limite:
            break
    return achados

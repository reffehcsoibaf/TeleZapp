# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Pasta de dados, configuracoes e registro (log).

Tudo o que da acesso as contas (sessoes) e o banco local ficam em
%APPDATA%\\TeleZapp, fora da pasta do programa e do repositorio. A variavel
de ambiente TELEZAPP_DADOS troca essa pasta (usada nos testes).

O registro nunca grava o texto das mensagens, numeros de telefone completos,
codigos ou senhas.
"""
import json
import logging
import logging.handlers
import os
import shutil
import threading
import unicodedata
from dataclasses import dataclass

from telezapp import NOME, VERSAO

log = logging.getLogger("telezapp")


def pasta_dados():
    especial = os.environ.get("TELEZAPP_DADOS")
    if especial:
        return especial
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, NOME)


def pasta(*partes):
    """Caminho dentro da pasta de dados, criando as pastas que faltam."""
    caminho = os.path.join(pasta_dados(), *partes)
    os.makedirs(caminho, exist_ok=True)
    return caminho


def configurar_registro():
    """Grava em logs\\telezapp.log (ate 5 arquivos de 1 MB)."""
    raiz = logging.getLogger("telezapp")
    if raiz.handlers:
        return os.path.join(pasta("logs"), "telezapp.log")
    arquivo = os.path.join(pasta("logs"), "telezapp.log")
    h = logging.handlers.RotatingFileHandler(
        arquivo, maxBytes=1024 * 1024, backupCount=4, encoding="utf-8")
    h.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    raiz.addHandler(h)
    raiz.setLevel(logging.INFO)
    raiz.propagate = False
    # Avisos das bibliotecas (reconexao, limites) ajudam a investigar
    # problemas. O neonize configura o log raiz ao ser importado; os dele
    # ficam so em avisos, aqui, e o nivel tambem vale para o lado em Go.
    for nome in ("telethon", "whatsmeow", "Whatsmeow", "neonize",
                 "neonize.utils.log"):
        lib = logging.getLogger(nome)
        lib.addHandler(h)
        lib.setLevel(logging.WARNING)
        lib.propagate = False
    raiz.info("==== %s %s iniciado ====", NOME, VERSAO)
    return arquivo


def mascarar_telefone(telefone):
    """+5551999998888 -> +55...8888 (para o registro)."""
    t = telefone or ""
    return t[:3] + "..." + t[-4:] if len(t) > 7 else "..."


def pasta_temporaria():
    """Arquivos temporarios do app: so aqui, nunca no %temp% do Windows."""
    return pasta("temp")


def limpar_temporarios():
    """Apaga o conteudo da pasta temporaria (na abertura e no fechamento)."""
    caminho = os.path.join(pasta_dados(), "temp")
    if os.path.isdir(caminho):
        shutil.rmtree(caminho, ignore_errors=True)


# ------------------------------------------------- opcoes de configuracao
@dataclass(frozen=True)
class Opcao:
    """Uma opcao que a pessoa pode mudar. O registro unico serve aos menus
    de hoje e a janela de configuracoes com busca (etapa 4)."""
    chave: str
    rotulo: str
    categoria: str
    padrao: object
    descricao: str
    escolhas: tuple = ()     # vazio: sim ou nao; senao (valor, rotulo)


OPCOES = (
    Opcao("som", "Som ao receber mensagem", "Avisos", True,
          "Toca um som curto quando chega uma mensagem nova."),
    Opcao("falar_novas", "Falar mensagens novas", "Avisos", True,
          "O leitor de tela fala o autor e o conteúdo de cada mensagem nova."),
    Opcao("confirmar_envio", "Confirmar envio por voz", "Avisos", True,
          "Fala Enviada depois que uma mensagem sai."),
    Opcao("estilo", "Como cada mensagem é lida", "Leitura", 1,
          "A ordem em que autor, hora e conteúdo aparecem na lista de "
          "mensagens.",
          ((1, "Autor e hora primeiro"), (2, "Conteúdo primeiro"),
           (3, "Autor só quando muda"))),
    Opcao("audio_janela", "Enter em áudio e mensagem de voz", "Mídias", "sem",
          "Só tocar começa a tocar sem abrir janela: Enter de novo pausa e "
          "continua, e Esc para. O player em janela tem avançar, voltar e "
          "posição.",
          (("sem", "Só tocar, sem janela"),
           ("janela", "Abrir a janela do player"))),
    Opcao("audio_sequencia", "Áudios em sequência", "Mídias", "sim",
          "Quando um áudio ou mensagem de voz termina (sem janela), toca o "
          "próximo áudio da conversa, baixando antes se preciso. Esc para.",
          (("sim", "Tocar os áudios em sequência"),
           ("nao", "Parar quando o áudio terminar"))),
    Opcao("midias_baixar", "Quando baixar as mídias", "Mídias", "demanda",
          "Sob demanda baixa só quando você abre a mídia. Automático baixa "
          "ao receber, até o limite escolhido.",
          (("demanda", "Só quando eu abrir"),
           ("automatico", "Automaticamente ao receber"))),
    Opcao("midias_limite_auto_mb", "Limite do download automático", "Mídias",
          20, "Mídias maiores que isto (em MB) não baixam sozinhas.",
          ((5, "5 MB"), (10, "10 MB"), (20, "20 MB"), (50, "50 MB"),
           (100, "100 MB"))),
    Opcao("midias_confirmar_mb", "Confirmar downloads grandes", "Mídias", 100,
          "Pergunta antes de baixar, a seu pedido, uma mídia maior que isto "
          "(em MB).",
          ((50, "50 MB"), (100, "100 MB"), (500, "500 MB"),
           (100000, "Nunca perguntar"))),
)


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


def buscar_opcoes(texto):
    """Opcoes cujo nome, categoria ou descricao contem todas as palavras
    buscadas (sem diferenca de acento ou maiusculas)."""
    palavras = _sem_acento(texto).split()
    achadas = []
    for o in OPCOES:
        alvo = _sem_acento(" ".join((o.rotulo, o.categoria, o.descricao)))
        if all(p in alvo for p in palavras):
            achadas.append(o)
    return achadas


PADROES = {o.chave: o.padrao for o in OPCOES}
PADROES.update({
    "contas": [],            # [{"id", "servico", "telefone", "nome"}]
    "telegram_api_id": 0,
    "telegram_api_hash": "",
})


class Config:
    """Configuracoes em config.json, gravadas de forma atomica."""

    def __init__(self, caminho=None):
        self.caminho = caminho or os.path.join(pasta(), "config.json")
        self._trava = threading.Lock()
        self.dados = dict(PADROES)
        self.dados["contas"] = []
        self._carregar()

    def _carregar(self):
        try:
            with open(self.caminho, encoding="utf-8") as f:
                lido = json.load(f)
            if isinstance(lido, dict):
                self.dados.update(lido)
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            log.warning("config.json ilegivel, usando padroes: %r", e)

    def get(self, chave):
        return self.dados.get(chave, PADROES.get(chave))

    def set(self, chave, valor):
        self.dados[chave] = valor
        self.salvar()

    def salvar(self):
        with self._trava:
            tmp = self.caminho + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.dados, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.caminho)

    # ---------------------------------------------------------------- contas
    def contas(self):
        return [dict(c) for c in self.get("contas")]

    def salvar_conta(self, conta):
        contas = [c for c in self.get("contas") if c.get("id") != conta["id"]]
        contas.append(dict(conta))
        self.set("contas", contas)

    def remover_conta(self, conta_id):
        self.set("contas", [c for c in self.get("contas")
                            if c.get("id") != conta_id])


# --------------------------------------------------- credenciais do Telegram
# O api_id e o api_hash identificam o APLICATIVO perante o Telegram (nao a
# pessoa). Quando o projeto registrar os seus, eles entram aqui e ninguem
# precisara informar nada. Enquanto estiverem vazios, o app usa os da
# configuracao (preenchidos uma vez pelo desenvolvedor).
TELEGRAM_API_ID = 0
TELEGRAM_API_HASH = ""

ARQUIVO_TESTES = r"C:\TeleZapp\configuracao-telegram.txt"


def ler_chaves(caminho):
    """Le um arquivo CHAVE=valor (ignora linhas com #)."""
    d = {}
    with open(caminho, encoding="utf-8-sig") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            k, v = linha.split("=", 1)
            d[k.strip().upper()] = v.strip()
    return d


def credenciais_validas(api_id, api_hash):
    try:
        return int(api_id) > 0 and len(str(api_hash).strip()) >= 16
    except (TypeError, ValueError):
        return False


def credenciais_telegram(config, arquivo_testes=ARQUIVO_TESTES):
    """(api_id, api_hash) ou None se ainda nao houver.

    Ordem: as embutidas no programa, as da configuracao e, por fim, as do
    arquivo dos testes de viabilidade (C:\\TeleZapp), que sao copiadas para a
    configuracao para nao precisar digita-las.
    """
    if credenciais_validas(TELEGRAM_API_ID, TELEGRAM_API_HASH):
        return int(TELEGRAM_API_ID), TELEGRAM_API_HASH
    api_id, api_hash = config.get("telegram_api_id"), config.get(
        "telegram_api_hash")
    if credenciais_validas(api_id, api_hash):
        return int(api_id), str(api_hash).strip()
    try:
        d = ler_chaves(arquivo_testes)
    except OSError:
        return None
    if credenciais_validas(d.get("API_ID"), d.get("API_HASH")):
        config.dados["telegram_api_id"] = int(d["API_ID"])
        config.dados["telegram_api_hash"] = d["API_HASH"].strip()
        config.salvar()
        log.info("credenciais do Telegram copiadas do arquivo dos testes")
        return int(d["API_ID"]), d["API_HASH"].strip()
    return None


def telefone_dos_testes(arquivo_testes=ARQUIVO_TESTES):
    """Telefone do arquivo dos testes de viabilidade, para sugerir no login."""
    try:
        return ler_chaves(arquivo_testes).get("TELEFONE", "")
    except OSError:
        return ""

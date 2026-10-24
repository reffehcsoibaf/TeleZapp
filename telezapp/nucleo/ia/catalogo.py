# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Quais provedores existem, o que cada um aceita e os limites. Uma tabela
so: a configuracao, o servico e o menu das mensagens leem dela."""
from dataclasses import dataclass

# As tarefas que a pessoa liga, cada uma com o seu provedor
AUDIO, IMAGEM, VIDEO, PDF = "audio", "imagem", "video", "pdf"
TEXTO = "texto"             # redigir, resumir e corrigir textos (sem midia)
TAREFAS = (AUDIO, IMAGEM, VIDEO, PDF, TEXTO)
NOMES_DE_TAREFA = {AUDIO: "Transcrição de voz e áudio",
                   IMAGEM: "Descrição de imagens e figurinhas",
                   VIDEO: "Descrição de vídeos",
                   PDF: "PDF em texto acessível",
                   TEXTO: "Redigir, resumir e corrigir textos"}
# O que a midia e para o provedor: figurinha e imagem
GENEROS = ("audio", "imagem", "figurinha", "video", "pdf")
TAREFA_DO_GENERO = {"audio": AUDIO, "imagem": IMAGEM, "figurinha": IMAGEM,
                    "video": VIDEO, "pdf": PDF}


@dataclass(frozen=True)
class Provedor:
    chave: str
    nome: str
    modelo: str                 # modelo padrao (a pessoa pode trocar)
    capacidades: frozenset      # audio, imagem, pdf, video
    url_chave: str
    url_privacidade: str
    modelo_transcricao: str = ""    # endpoint proprio de transcricao
    # outros modelos, na ordem, para o modo automatico: se o padrao nao
    # existir mais ou o limite do uso acabar, tenta o proximo
    alternativos: tuple = ()


PROVEDORES = {
    "gemini": Provedor(
        "gemini", "Google Gemini", "gemini-3.8-flash",
        frozenset({"texto", "audio", "imagem", "pdf", "video"}),
        "https://aistudio.google.com/api-keys",
        "https://ai.google.dev/gemini-api/terms",
        alternativos=("gemini-3.6-flash", "gemini-3.5-flash-lite")),
    "openai": Provedor(
        "openai", "OpenAI", "gpt-4.1-mini",
        frozenset({"texto", "audio", "imagem", "pdf"}),
        "https://platform.openai.com/api-keys",
        "https://developers.openai.com/api/docs/guides/your-data",
        modelo_transcricao="gpt-4o-mini-transcribe"),
    "claude": Provedor(
        "claude", "Claude (Anthropic)", "claude-haiku-5-5",
        frozenset({"texto", "imagem", "pdf"}),
        "https://console.anthropic.com/settings/keys",
        "https://www.anthropic.com/legal/privacy"),
    "groq": Provedor(
        "groq", "Groq", "qwen/qwen3.8-27b", frozenset({"texto", "audio", "imagem"}),
        "https://console.groq.com/keys", "https://groq.com/privacy-policy",
        modelo_transcricao="whisper-large-v3-turbo"),
    "openrouter": Provedor(
        "openrouter", "OpenRouter", "google/gemini-3.5-flash-lite",
        frozenset({"texto", "imagem", "pdf"}), "https://openrouter.ai/settings/keys",
        "https://openrouter.ai/privacy"),
}

# O detalhe das descricoes
PERFIS = (("curto", "Curto: um parágrafo"),
          ("medio", "Médio: dois ou três parágrafos"),
          ("detalhado", "Detalhado e organizado"))

# Maior arquivo que viaja (tudo vai embutido num pedido so)
LIMITE_BYTES = {"audio": 14 * 1024 * 1024, "imagem": 14 * 1024 * 1024,
                "figurinha": 14 * 1024 * 1024, "video": 14 * 1024 * 1024,
                "pdf": 14 * 1024 * 1024}
# Maior resposta guardada e orcamento pedido ao provedor
MAX_CARACTERES = {"audio": 50_000, "imagem": 12_000, "figurinha": 12_000,
                  "video": 12_000, "pdf": 100_000, "texto": 20_000}
MAX_TOKENS = {"audio": 8000, "imagem": 1800, "figurinha": 1200,
              "video": 2200, "pdf": 16000, "texto": 4000}
# O tom ao redigir (chave, o que a pessoa le) e os idiomas da traducao (nome
# em ingles, que vai ao provedor, e o que a pessoa le)
TONS = (("natural", "Natural, no tom da conversa"),
        ("amigavel", "Amigável e simpático"),
        ("formal", "Formal e educado"),
        ("direto", "Direto e objetivo"),
        ("descontraido", "Descontraído, com leveza"))
IDIOMAS = (("Brazilian Portuguese", "Português do Brasil"),
           ("English", "Inglês"), ("Spanish", "Espanhol"),
           ("French", "Francês"), ("German", "Alemão"),
           ("Italian", "Italiano"))
# Mais que isso do texto da pessoa ou da conversa nao viaja (fica o final)
MAX_ENTRADA_TEXTO = 24_000
MAX_RESPOSTA_BYTES = 8 * 1024 * 1024


def capacidade(genero):
    """O que o provedor precisa aceitar para esse genero de midia."""
    return "imagem" if genero == "figurinha" else genero


def video_nativo(provedor):
    """O provedor recebe o video inteiro (so o Gemini); os outros veem os
    quadros do video, como uma imagem."""
    return provedor in PROVEDORES and "video" in \
        PROVEDORES[provedor].capacidades


def aceita(provedor, genero):
    if provedor not in PROVEDORES:
        return False
    if genero == "video":
        # quem le imagens descreve o video por quadros
        return video_nativo(provedor) or "imagem" in \
            PROVEDORES[provedor].capacidades
    return capacidade(genero) in PROVEDORES[provedor].capacidades


def provedores_da_tarefa(tarefa):
    """[(chave, nome)] dos provedores que fazem a tarefa."""
    genero = {AUDIO: "audio", IMAGEM: "imagem", VIDEO: "video",
              PDF: "pdf", TEXTO: "texto"}[tarefa]
    return [(p.chave, p.nome) for p in PROVEDORES.values()
            if aceita(p.chave, genero)]


def cadeia_de_modelos(provedor, modelos):
    """Os modelos a tentar, em ordem: so o escolhido pela pessoa, ou (modo
    automatico, campo vazio) o padrao e depois os alternativos."""
    escolhido = (modelos or {}).get(provedor, "").strip()
    if escolhido:
        return [escolhido]
    p = PROVEDORES[provedor]
    return [p.modelo, *p.alternativos]


def modelo_de(provedor, modelos):
    """O modelo que vale: o escolhido pela pessoa ou o padrao."""
    escolhido = (modelos or {}).get(provedor, "").strip()
    return escolhido or PROVEDORES[provedor].modelo

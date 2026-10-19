# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Adaptadores das APIs oficiais, sem rede nem disco: `montar_pedido` diz o
que enviar e `ler_resposta` o que veio de volta. Assim o formato de cada
provedor se testa direto."""
import base64
import uuid
from typing import NamedTuple, Optional

from telezapp.nucleo.ia import catalogo as cat


class ErroIA(Exception):
    """Algo que a pessoa precisa saber (chave recusada, limite, arquivo
    grande...). `codigo` e curto; o texto e dito a pessoa."""

    def __init__(self, codigo, texto):
        super().__init__(texto)
        self.codigo, self.texto = codigo, texto


class Midia(NamedTuple):
    genero: str          # audio, imagem, figurinha, video, pdf
    mime: str
    dados: bytes
    nome: str


class Pedido(NamedTuple):
    url: str
    cabecalhos: dict
    json: Optional[dict] = None
    corpo: Optional[bytes] = None      # pedido multipart ja montado
    metodo: str = "POST"


_OPENAI = "https://api.openai.com/v1"
_GEMINI = "https://generativelanguage.googleapis.com/v1beta"
_CLAUDE = "https://api.anthropic.com/v1/messages"
_GROQ = "https://api.groq.com/openai/v1"
_OPENROUTER = "https://openrouter.ai/api/v1"
_CHAT = {"groq": _GROQ, "openrouter": _OPENROUTER}
# a Groq documenta cerca de 4 MB de imagem em base64 por pedido
LIMITE_IMAGEM_GROQ = 4_000_000


def _b64(midia):
    return base64.b64encode(midia.dados).decode("ascii")


def _url_de_dados(midia):
    return "data:%s;base64,%s" % (midia.mime, _b64(midia))


# nomes de modelo que nao servem para ler midia e escrever texto
_NAO_SERVE = ("tts", "live", "embed", "imagen", "veo", "image", "robotics",
              "lyria", "computer-use", "aqa", "native-audio", "whisper",
              "guard", "orpheus", "playai", "moderation", "realtime",
              "transcribe", "audio-preview", "dall-e", "sora", "codex",
              "search", "instruct", "davinci", "babbage")


def pedido_de_modelos(provedor, chave):
    """Pedido (GET) da lista de modelos do provedor."""
    if provedor == "gemini":
        return Pedido(_GEMINI + "/models?pageSize=1000",
                      {"x-goog-api-key": chave}, metodo="GET")
    if provedor == "openai":
        return Pedido(_OPENAI + "/models", {"Authorization": "Bearer " + chave},
                      metodo="GET")
    if provedor == "claude":
        return Pedido("https://api.anthropic.com/v1/models?limit=1000",
                      {"x-api-key": chave, "anthropic-version": "2023-06-01"},
                      metodo="GET")
    if provedor in _CHAT:
        return Pedido(_CHAT[provedor] + "/models",
                      {"Authorization": "Bearer " + chave}, metodo="GET")
    raise ErroIA("provedor", "Provedor desconhecido.")


def ler_modelos(provedor, corpo):
    """Os identificadores dos modelos que leem midia e escrevem texto, dos
    mais novos (ordem alfabetica inversa) para os mais antigos."""
    try:
        if provedor == "gemini":
            ids = [m["name"].split("/", 1)[-1] for m in corpo["models"]
                   if "generateContent" in m.get("supportedGenerationMethods",
                                                 ["generateContent"])]
        elif provedor == "openrouter":
            ids = [m["id"] for m in corpo["data"]
                   if "image" in (m.get("architecture") or {}).get(
                       "input_modalities", ["image"])]
        else:
            ids = [m["id"] for m in corpo["data"]]
    except (KeyError, TypeError, AttributeError):
        raise ErroIA("resposta", "A lista de modelos veio num formato "
                                 "inesperado.")
    ids = [i for i in ids if isinstance(i, str) and i and not any(
        n in i.lower() for n in _NAO_SERVE)]
    return sorted(set(ids), reverse=True)


def e_transcricao(provedor, midia):
    """Audio vai a um endpoint proprio de transcricao onde o provedor tem um
    (OpenAI e Groq); o Gemini recebe o audio como entrada de conversa."""
    return midia.genero == "audio" and bool(
        cat.PROVEDORES[provedor].modelo_transcricao)


def montar_pedido(provedor, modelo, chave, midia, instrucoes, pergunta,
                  perfil="medio"):
    if provedor not in cat.PROVEDORES or not cat.aceita(
            provedor, midia.genero):
        raise ErroIA("nao_aceita", "Este provedor não faz isso com este tipo "
                                   "de arquivo.")
    if midia.genero == "video" and not cat.video_nativo(provedor):
        raise ErroIA("nao_aceita", "Este provedor só vê os quadros do vídeo, "
                                   "não o arquivo.")
    if e_transcricao(provedor, midia):
        return _transcricao(provedor, chave, midia)
    tokens = cat.MAX_TOKENS[midia.genero]
    if provedor == "openai":
        if midia.genero == "pdf":
            parte = {"type": "input_file", "filename": midia.nome,
                     "file_data": _url_de_dados(midia)}
        else:
            parte = {"type": "input_image", "image_url": _url_de_dados(midia),
                     "detail": "low" if perfil == "curto" else "high"}
        return Pedido(
            _OPENAI + "/responses", {"Authorization": "Bearer " + chave},
            {"model": modelo, "store": False, "instructions": instrucoes,
             "input": [{"role": "user", "content": [
                 parte, {"type": "input_text", "text": pergunta}]}],
             "max_output_tokens": tokens})
    if provedor == "gemini":
        return Pedido(
            "%s/models/%s:generateContent" % (_GEMINI, modelo),
            {"x-goog-api-key": chave},
            {"systemInstruction": {"parts": [{"text": instrucoes}]},
             "contents": [{"role": "user", "parts": [
                 {"inline_data": {"mime_type": midia.mime,
                                  "data": _b64(midia)}},
                 {"text": pergunta}]}],
             "generationConfig": {"maxOutputTokens": tokens}})
    if provedor == "claude":
        bloco = {"type": "document" if midia.genero == "pdf" else "image",
                 "source": {"type": "base64", "media_type": midia.mime,
                            "data": _b64(midia)}}
        return Pedido(
            _CLAUDE, {"x-api-key": chave, "anthropic-version": "2023-06-01"},
            {"model": modelo, "max_tokens": tokens, "system": instrucoes,
             "messages": [{"role": "user", "content": [
                 bloco, {"type": "text", "text": pergunta}]}]})
    if provedor == "groq" and midia.genero in ("imagem", "figurinha") and \
            len(_b64(midia)) > LIMITE_IMAGEM_GROQ:
        raise ErroIA("grande", "A imagem é grande demais para a Groq.")
    # Groq e OpenRouter falam o dialeto de chat da OpenAI
    if midia.genero == "pdf":
        parte = {"type": "file", "file": {"filename": midia.nome,
                                          "file_data": _url_de_dados(midia)}}
    else:
        parte = {"type": "image_url",
                 "image_url": {"url": _url_de_dados(midia)}}
    # a Groq pede max_completion_tokens (max_tokens esta em desuso la)
    campo_tokens = ("max_completion_tokens" if provedor == "groq"
                    else "max_tokens")
    return Pedido(
        _CHAT[provedor] + "/chat/completions",
        {"Authorization": "Bearer " + chave},
        {"model": modelo, campo_tokens: tokens, "messages": [
            {"role": "system", "content": instrucoes},
            {"role": "user", "content": [
                {"type": "text", "text": pergunta}, parte]}]})


def _transcricao(provedor, chave, midia):
    """Pedido multipart. O idioma fica por conta da deteccao do modelo: forcar
    um idioma estragaria uma mensagem em outro."""
    limite = "----telezapp" + uuid.uuid4().hex
    base = _OPENAI if provedor == "openai" else _GROQ
    campos = [("model", cat.PROVEDORES[provedor].modelo_transcricao),
              ("response_format", "json")]
    partes = []
    for nome, valor in campos:
        partes.append(('--%s\r\nContent-Disposition: form-data; '
                       'name="%s"\r\n\r\n%s\r\n' % (limite, nome, valor)
                       ).encode("utf-8"))
    nome_arquivo = (midia.nome or "audio.ogg").replace('"', "_")
    partes.append(('--%s\r\nContent-Disposition: form-data; name="file"; '
                   'filename="%s"\r\nContent-Type: %s\r\n\r\n' % (
                       limite, nome_arquivo, midia.mime)).encode("utf-8"))
    partes.append(midia.dados)
    partes.append(("\r\n--%s--\r\n" % limite).encode("utf-8"))
    return Pedido(base + "/audio/transcriptions",
                  {"Authorization": "Bearer " + chave,
                   "Content-Type": "multipart/form-data; boundary=" + limite},
                  corpo=b"".join(partes))


def ler_resposta(provedor, corpo, genero):
    """O texto da resposta do provedor. ErroIA se ele recusou ou cortou."""
    limite = cat.MAX_CARACTERES[genero]
    try:
        if provedor in ("openai", "groq") and "text" in corpo and \
                "output" not in corpo and "choices" not in corpo:
            texto = corpo["text"]                    # transcricao
        elif provedor == "openai":
            if corpo.get("status") in ("incomplete", "failed", "cancelled"):
                raise ErroIA("resposta", "O provedor não terminou a resposta.")
            partes = [p for item in corpo.get("output", [])
                      if item.get("type") == "message"
                      for p in item.get("content", [])]
            if any(p.get("type") == "refusal" for p in partes):
                raise ErroIA("recusa", "O provedor recusou este conteúdo.")
            texto = "\n".join(p["text"] for p in partes
                              if p.get("type") == "output_text")
        elif provedor == "gemini":
            candidatos = corpo.get("candidates") or []
            if corpo.get("promptFeedback", {}).get("blockReason") or any(
                    c.get("finishReason") in (
                        "SAFETY", "RECITATION", "PROHIBITED_CONTENT",
                        "BLOCKLIST") for c in candidatos):
                raise ErroIA("recusa", "O provedor recusou este conteúdo.")
            if any(c.get("finishReason") == "MAX_TOKENS"
                   for c in candidatos):
                raise ErroIA("resposta", "A resposta passou do limite e foi "
                                         "cortada.")
            texto = "\n".join(
                p["text"] for c in candidatos[:1]
                for p in c.get("content", {}).get("parts", [])
                if "text" in p and not p.get("thought"))
        elif provedor == "claude":
            if corpo.get("stop_reason") == "refusal":
                raise ErroIA("recusa", "O provedor recusou este conteúdo.")
            if corpo.get("stop_reason") == "max_tokens":
                raise ErroIA("resposta", "A resposta passou do limite e foi "
                                         "cortada.")
            texto = "\n".join(b["text"] for b in corpo.get("content", [])
                              if b.get("type") == "text")
        elif provedor in _CHAT:
            escolha = corpo["choices"][0]
            msg = escolha["message"]
            if msg.get("refusal") or \
                    escolha.get("finish_reason") == "content_filter":
                raise ErroIA("recusa", "O provedor recusou este conteúdo.")
            if escolha.get("finish_reason") == "length":
                raise ErroIA("resposta", "A resposta passou do limite e foi "
                                         "cortada.")
            texto = msg.get("content")
        else:
            raise ErroIA("resposta", "Provedor desconhecido.")
    except ErroIA:
        raise
    except (KeyError, IndexError, TypeError, AttributeError):
        raise ErroIA("resposta", "A resposta do provedor veio num formato "
                                 "inesperado.")
    texto = (texto or "").strip()
    if not texto:
        raise ErroIA("vazia", "O provedor não devolveu texto (em um áudio, "
                              "talvez não haja fala).")
    return texto[:limite]

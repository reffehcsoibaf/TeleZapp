# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Faz o trabalho: le a midia, escolhe o provedor da tarefa, envia o pedido
e devolve o texto. A rede entra como parametro (`enviar`), para testar."""
import json
import logging
import mimetypes
import os
import struct
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass

from telezapp import VERSAO

from telezapp.nucleo.ia import catalogo as cat
from telezapp.nucleo.ia import prompts
from telezapp.nucleo.ia import provedores as prov
from telezapp.nucleo.ia import video as quadros_de_video
from telezapp.nucleo.ia.provedores import ErroIA, Midia

log = logging.getLogger("telezapp.ia")

TEMPO_LIMITE = 180

def _png_branco(lado):
    """Um PNG branco de lado x lado pixels (pequeno, para testar chave e
    modelo sem gastar quase nada; 1x1 e recusado por alguns modelos de
    visao)."""
    def bloco(tipo, dados):
        corpo = tipo + dados
        return struct.pack(">I", len(dados)) + corpo + struct.pack(
            ">I", zlib.crc32(corpo) & 0xFFFFFFFF)
    branco = bytes([255, 255, 255])
    linhas = b"".join(bytes([0]) + branco * lado for _ in range(lado))
    assinatura = bytes([137, 80, 78, 71, 13, 10, 26, 10])
    return (assinatura + bloco(b"IHDR", struct.pack(
        ">IIBBBBB", lado, lado, 8, 2, 0, 0, 0)) +
        bloco(b"IDAT", zlib.compress(linhas)) + bloco(b"IEND", b""))


PNG_MINIMO = _png_branco(64)


@dataclass
class Resultado:
    texto: str
    provedor: str          # nome legivel
    modelo: str
    via_quadros: bool = False   # video visto por quadros (sem a fala)


def _mime(caminho, dados, genero):
    """O tipo MIME pelo que o arquivo e (os primeiros bytes), senao pela
    extensao."""
    inicio = dados[:16]
    if inicio.startswith(b"%PDF"):
        return "application/pdf"
    if inicio.startswith(b"OggS"):
        return "audio/ogg"
    if inicio[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "image/webp"
    if inicio.startswith(b"\x89PNG"):
        return "image/png"
    if inicio.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if inicio.startswith(b"GIF8"):
        return "image/gif"
    if dados[4:8] == b"ftyp":
        return "video/mp4" if genero == "video" else "audio/mp4"
    adivinhado = mimetypes.guess_type(caminho)[0]
    if adivinhado:
        return adivinhado
    return {"audio": "audio/ogg", "imagem": "image/jpeg",
            "figurinha": "image/webp", "video": "video/mp4",
            "pdf": "application/pdf"}[genero]


def carregar_midia(caminho, genero, mime=None):
    """Midia pronta para enviar. ErroIA se o arquivo nao serve."""
    if genero not in cat.GENEROS:
        raise ErroIA("genero", "Tipo de arquivo desconhecido.")
    try:
        tamanho = os.path.getsize(caminho)
    except OSError:
        raise ErroIA("arquivo", "O arquivo não está no computador. Baixe a "
                                "mídia antes.")
    if tamanho == 0:
        raise ErroIA("arquivo", "O arquivo está vazio.")
    if tamanho > cat.LIMITE_BYTES[genero]:
        raise ErroIA("grande", "O arquivo tem %.1f MB e o limite para "
                               "enviar ao provedor é %d MB." % (
                                   tamanho / 1048576,
                                   cat.LIMITE_BYTES[genero] // 1048576))
    with open(caminho, "rb") as f:
        dados = f.read()
    return Midia(genero, mime or _mime(caminho, dados, genero), dados,
                 os.path.basename(caminho))


def enviar_pela_rede(pedido):
    """Faz o pedido HTTP e devolve o JSON da resposta. ErroIA com a causa
    em portugues se der errado."""
    if pedido.metodo == "GET":
        dados, cabecalhos = None, dict(pedido.cabecalhos)
    elif pedido.corpo is not None:
        dados, cabecalhos = pedido.corpo, dict(pedido.cabecalhos)
    else:
        dados = json.dumps(pedido.json).encode("utf-8")
        cabecalhos = dict(pedido.cabecalhos, **{
            "Content-Type": "application/json"})
    # Sem um User-Agent proprio a Groq (Cloudflare) responde 403, erro 1010,
    # ao do Python, e parece chave recusada
    cabecalhos.setdefault("User-Agent", "TeleZapp/" + VERSAO)
    req = urllib.request.Request(pedido.url, data=dados, headers=cabecalhos,
                                 method=pedido.metodo)
    try:
        with urllib.request.urlopen(req, timeout=TEMPO_LIMITE) as r:
            bruto = r.read(cat.MAX_RESPOSTA_BYTES + 1)
    except urllib.error.HTTPError as e:
        try:
            detalhe = e.read(2048).decode("utf-8", "replace")
        except Exception:
            detalhe = ""
        raise _erro_http(e.code, detalhe)
    except TimeoutError:
        raise ErroIA("tempo", "O provedor demorou demais para responder.")
    except (urllib.error.URLError, OSError):
        raise ErroIA("rede", "Não consegui falar com o provedor. Veja a "
                             "conexão com a internet.")
    if len(bruto) > cat.MAX_RESPOSTA_BYTES:
        raise ErroIA("resposta", "A resposta do provedor veio grande demais.")
    try:
        return json.loads(bruto.decode("utf-8"))
    except ValueError:
        raise ErroIA("resposta", "A resposta do provedor não é válida.")


def _motivo(detalhe):
    """A mensagem de erro que o provedor mandou, curta, para a pessoa saber
    o que ele reclamou ("" se nao veio)."""
    try:
        dados = json.loads(detalhe)
        erro = dados.get("error", dados) if isinstance(dados, dict) else {}
        msg = erro.get("message") if isinstance(erro, dict) else str(erro)
    except ValueError:
        msg = detalhe
    msg = " ".join(str(msg or "").split()).rstrip(".")
    return (": " + msg[:220] + ("..." if len(msg) > 220 else "") + ".")         if msg else "."


def _erro_http(codigo, detalhe=""):
    texto = detalhe.lower()
    motivo = _motivo(detalhe)
    chave_ruim = ("api key not valid", "invalid_api_key", "api_key_invalid")
    sem_saldo = ("insufficient_quota", "exceeded your current quota",
                 "billing", "credit balance", "insufficient credits",
                 "payment required", "out of credits")
    # o Gemini responde 400, e nao 401, a uma chave que nao vale
    if codigo in (401, 403) or any(t in texto for t in chave_ruim):
        return ErroIA("chave", "O provedor recusou a chave. Confira a chave "
                               "em Configurações, Inteligência artificial.")
    if codigo == 402 or (codigo in (400, 429) and any(
            t in texto for t in sem_saldo)):
        return ErroIA("saldo", "A conta do provedor está sem créditos ou "
                               "passou da cota%s Veja o saldo e o plano no "
                               "site do provedor." % motivo)
    if codigo == 429:
        return ErroIA("limite", "O provedor limitou o uso (muitos pedidos em "
                                "pouco tempo)%s Tente de novo daqui a "
                                "pouco." % motivo)
    if codigo == 413:
        return ErroIA("grande", "O arquivo é grande demais para este "
                                "provedor.")
    if codigo in (400, 404, 422):
        return ErroIA("pedido", "O provedor não aceitou o pedido (erro %d)%s "
                                "Confira o modelo escolhido." % (
                                    codigo, motivo))
    return ErroIA("provedor", "O provedor está com problemas (erro %d)%s "
                              "Tente de novo mais tarde." % (codigo, motivo))


def executar(genero, caminho, provedor, chave, modelo, perfil="medio",
             enviar=enviar_pela_rede, mime=None):
    """Transcreve ou descreve o arquivo. `modelo` e um nome ou uma lista, em
    ordem: se um nao existe mais ou o limite de uso dele acabou, tenta o
    proximo. Devolve o Resultado."""
    if provedor not in cat.PROVEDORES:
        raise ErroIA("provedor", "Escolha um provedor em Configurações, "
                                 "Inteligência artificial.")
    if not chave:
        raise ErroIA("chave", "Falta a chave de %s em Configurações, "
                              "Inteligência artificial." %
                     cat.PROVEDORES[provedor].nome)
    if not cat.aceita(provedor, genero):
        raise ErroIA("nao_aceita", "%s não faz isso com este tipo de "
                                   "arquivo." % cat.PROVEDORES[provedor].nome)
    quadros, instrucoes, pergunta = 0, None, None
    if genero == "video" and not _video_inteiro(provedor, caminho):
        # sem o video inteiro: os quadros espalhados, numa imagem so
        jpeg, tempos = quadros_de_video.grade_de_quadros(caminho, perfil)
        quadros = len(tempos)
        midia = Midia("imagem", "image/jpeg", jpeg, "quadros.jpg")
        instrucoes = prompts.instrucoes("video", perfil, quadros=quadros)
        pergunta = prompts.primeira_pergunta("video", quadros)
    else:
        midia = carregar_midia(caminho, genero, mime)
        instrucoes = prompts.instrucoes(genero, perfil)
        pergunta = prompts.primeira_pergunta(genero)
    modelos = [modelo] if isinstance(modelo, str) else list(modelo)
    for i, atual in enumerate(modelos):
        pedido = prov.montar_pedido(provedor, atual, chave, midia,
                                    instrucoes, pergunta, perfil)
        try:
            texto = prov.ler_resposta(provedor, enviar(pedido), genero)
        except ErroIA as e:
            if e.codigo in ("pedido", "limite") and i + 1 < len(modelos):
                log.info("modelo %s recusado (%s); tentando o próximo", atual,
                         e.codigo)
                continue
            raise
        return Resultado(texto, cat.PROVEDORES[provedor].nome, atual,
                         bool(quadros))


# O que vale tentar com o proximo provedor da ordem: a falha e deste
# provedor (chave, saldo, limite, modelo, tamanho, rede...), nao do arquivo
PROXIMO_PROVEDOR = {"chave", "saldo", "limite", "pedido", "grande", "recusa",
                    "provedor", "rede", "tempo", "resposta", "nao_aceita",
                    "vazia"}


def _video_inteiro(provedor, caminho):
    """O video vai inteiro so ao provedor que o recebe e se couber."""
    try:
        tamanho = os.path.getsize(caminho)
    except OSError:
        return True      # o erro do arquivo sai em carregar_midia
    return cat.video_nativo(provedor) and         tamanho <= cat.LIMITE_BYTES["video"]


def executar_em_ordem(genero, caminho, ordem, chave_de, modelos, perfil,
                      enviar=enviar_pela_rede, ao_tentar=None,
                      ordem_audio=()):
    """Tenta os provedores na ordem em que a pessoa os organizou, ate um
    funcionar. `chave_de(provedor)` devolve a chave ("" = sem chave, pula).
    `modelos` e o dicionario ia_modelos. Devolve o Resultado; se nenhum
    funcionou, levanta o erro do ultimo que foi tentado."""
    r = _executar_em_ordem(genero, caminho, ordem, chave_de, modelos, perfil,
                           enviar, ao_tentar)
    if genero == "video" and r.via_quadros and ordem_audio:
        r.texto += "\n\n" + _fala_do_video(
            caminho, ordem_audio, chave_de, modelos, perfil, enviar)
    return r


def _fala_do_video(caminho, ordem_audio, chave_de, modelos, perfil, enviar):
    """A fala do video, transcrita a parte: os quadros nao trazem o som.
    Texto pronto para somar a descricao."""
    try:
        t = _executar_em_ordem("audio", caminho, ordem_audio, chave_de,
                               modelos, perfil, enviar, None, "video/mp4")
    except ErroIA as e:
        if e.codigo == "vazia":
            return "Fala no vídeo: não encontrei fala."
        return "Fala no vídeo: não consegui transcrever. %s" % e.texto
    return "Fala no vídeo (%s): %s" % (t.provedor, t.texto)


def _executar_em_ordem(genero, caminho, ordem, chave_de, modelos, perfil,
                       enviar, ao_tentar, mime=None):
    ultimo = None
    tentados = 0
    for provedor in ordem:
        if provedor not in cat.PROVEDORES or not cat.aceita(provedor, genero):
            continue
        chave = chave_de(provedor)
        if not chave:
            continue
        tentados += 1
        if ao_tentar:
            ao_tentar(provedor)
        try:
            return executar(genero, caminho, provedor, chave,
                            cat.cadeia_de_modelos(provedor, modelos), perfil,
                            enviar, mime)
        except ErroIA as e:
            if e.codigo not in PROXIMO_PROVEDOR:
                raise
            log.info("%s falhou (%s); tentando o próximo da ordem", provedor,
                     e.codigo)
            ultimo = ErroIA(e.codigo, "%s: %s" % (
                cat.PROVEDORES[provedor].nome, e.texto))
    if ultimo is not None:
        raise ultimo
    raise ErroIA("provedor", "Nenhum provedor com chave está ligado para "
                             "isso. Escolha e ordene os provedores em "
                             "Configurações, Inteligência artificial.")


def preparar_texto(operacao, texto, contexto="", tom="natural",
                   destino=prompts.IDIOMA):
    """Corta o que passa do limite (fica o final, o mais recente) e monta a
    instrucao e a pergunta. Texto vazio e erro."""
    texto = (texto or "").strip()
    if not texto:
        raise ErroIA("vazia", "Não há texto para isso.")
    limite = cat.MAX_ENTRADA_TEXTO
    texto = texto[-limite:]
    sobra = limite - len(texto)
    contexto = (contexto or "").strip()
    contexto = contexto[-sobra:] if sobra > 0 else ""
    return (prompts.instrucoes_de_texto(operacao, tom=tom,
                                        destino=destino),
            prompts.pergunta_de_texto(operacao, texto, contexto))


def executar_texto(operacao, texto, provedor, chave, modelo, contexto="",
                   enviar=enviar_pela_rede, tom="natural",
                   destino=prompts.IDIOMA):
    """Corrige, redige ou resume o texto. `modelo` e um nome ou uma lista, em
    ordem, como em `executar`. Devolve o Resultado."""
    if provedor not in cat.PROVEDORES:
        raise ErroIA("provedor", "Escolha um provedor em Configurações, "
                                 "Inteligência artificial.")
    if not chave:
        raise ErroIA("chave", "Falta a chave de %s em Configurações, "
                              "Inteligência artificial." %
                     cat.PROVEDORES[provedor].nome)
    if not cat.aceita(provedor, "texto"):
        raise ErroIA("nao_aceita", "%s não faz isso com texto." %
                     cat.PROVEDORES[provedor].nome)
    instrucoes, pergunta = preparar_texto(operacao, texto, contexto, tom,
                                          destino)
    modelos = [modelo] if isinstance(modelo, str) else list(modelo)
    for i, atual in enumerate(modelos):
        pedido = prov.montar_pedido_de_texto(provedor, atual, chave,
                                             instrucoes, pergunta)
        try:
            resposta = prov.ler_resposta(provedor, enviar(pedido), "texto")
        except ErroIA as e:
            if e.codigo in ("pedido", "limite") and i + 1 < len(modelos):
                log.info("modelo %s recusado (%s); tentando o próximo", atual,
                         e.codigo)
                continue
            raise
        return Resultado(resposta, cat.PROVEDORES[provedor].nome, atual)


def executar_texto_em_ordem(operacao, texto, ordem, chave_de, modelos,
                            contexto="", enviar=enviar_pela_rede,
                            tom="natural", destino=prompts.IDIOMA):
    """Como `executar_em_ordem`, para texto: o primeiro provedor da ordem que
    tem chave e funciona."""
    preparar_texto(operacao, texto, contexto)       # texto vazio: erro logo
    ultimo = None
    for provedor in ordem:
        if provedor not in cat.PROVEDORES or not cat.aceita(provedor,
                                                            "texto"):
            continue
        chave = chave_de(provedor)
        if not chave:
            continue
        try:
            return executar_texto(
                operacao, texto, provedor, chave,
                cat.cadeia_de_modelos(provedor, modelos), contexto, enviar,
                tom, destino)
        except ErroIA as e:
            if e.codigo not in PROXIMO_PROVEDOR:
                raise
            log.info("%s falhou (%s); tentando o próximo da ordem", provedor,
                     e.codigo)
            ultimo = ErroIA(e.codigo, "%s: %s" % (
                cat.PROVEDORES[provedor].nome, e.texto))
    if ultimo is not None:
        raise ultimo
    raise ErroIA("provedor", "Nenhum provedor com chave está ligado para "
                             "isso. Escolha e ordene os provedores em "
                             "Configurações, Inteligência artificial.")


def listar_modelos(provedor, chave, enviar=enviar_pela_rede):
    """Os modelos que o provedor oferece a essa chave."""
    if not chave:
        raise ErroIA("chave", "Digite ou guarde a chave antes de obter os "
                              "modelos.")
    lista = prov.ler_modelos(provedor, enviar(
        prov.pedido_de_modelos(provedor, chave)))
    if not lista:
        raise ErroIA("vazia", "O provedor não listou nenhum modelo.")
    return lista


def testar(provedor, chave, modelo, enviar=enviar_pela_rede):
    """Pedido minimo para ver se a chave e o modelo funcionam. Devolve o
    texto da resposta ou levanta ErroIA."""
    midia = Midia("imagem", "image/png", PNG_MINIMO, "teste.png")
    pedido = prov.montar_pedido(provedor, modelo, chave, midia,
                                "Reply with the single word OK.",
                                "Reply with OK.", "curto")
    return prov.ler_resposta(provedor, enviar(pedido), "imagem")

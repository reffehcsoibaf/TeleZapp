# -*- coding: utf-8 -*-
"""Teste de viabilidade do Telegram com Telethon. Versao 2: com midia.

Chamado pelo 1-teste-telegram.bat. Escreve no mesmo log do .bat.
Nao usa o terminal para perguntas: avisos saem em caixas de mensagem e os
dados sao digitados em arquivos abertos no Bloco de Notas.
Nao grava telefone, codigo, senha, nome nem texto de mensagens no log.

Etapas: login, leitura de conversas, envio de texto, foto, video, nota de voz
e documento para Mensagens Salvas, e depois observacao de mensagens que
chegam (inclusive as proprias), baixando cada tipo de midia uma vez.
"""
import asyncio
import os
import platform
import shutil
import sys
import threading
import time
import traceback

from acessivel import aviso, pedir_por_arquivo
import amostras

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    BASE, "logs", "resultado-teste-telegram.log")
SESSAO_DIR = os.path.join(BASE, "sessao-telegram")
AMOSTRAS_DIR = os.path.join(BASE, "amostras-telegram")
DOWNLOAD_DIR = os.path.join(BASE, "downloads-telegram")
ARQ_CONF = os.path.join(BASE, "configuracao-telegram.txt")
ARQ_CODIGO = os.path.join(BASE, "codigo-telegram.txt")
ARQ_SENHA = os.path.join(BASE, "senha-telegram.txt")
LIMITE_ESPERA_SEGUNDOS = 3600  # teto de seguranca

MODELO_CONF = (
    "# Preencha depois do sinal de igual, salve com Control S e feche.\n"
    "# API_ID e API_HASH: crie em my.telegram.org, em API development tools.\n"
    "# TELEFONE: com sinal de mais e codigo do pais, exemplo +5551999999999\n"
    "API_ID=\n"
    "API_HASH=\n"
    "TELEFONE=\n")
MODELO_CODIGO = (
    "# Digite o codigo que o Telegram enviou, depois do sinal de igual.\n"
    "# Salve com Control S. O codigo chega no app do Telegram do celular.\n"
    "CODIGO=\n")
MODELO_SENHA = (
    "# Digite a senha de duas etapas do Telegram depois do sinal de igual.\n"
    "# Salve com Control S. O arquivo e apagado logo depois do uso.\n"
    "SENHA=\n")


def log(msg):
    linha = time.strftime("%H:%M:%S") + " " + msg
    print(linha, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except OSError:
        pass


def conf_valida(d):
    return (d.get("API_ID", "").isdigit()
            and len(d.get("API_HASH", "")) >= 16
            and d.get("TELEFONE", "").startswith("+")
            and d.get("TELEFONE", "")[1:].isdigit())


def apagar(caminho):
    try:
        os.remove(caminho)
    except OSError:
        pass


def tipo_midia(m):
    """Classifica a midia de uma mensagem do Telethon, ou None."""
    if m.sticker:
        return "figurinha"
    if m.photo:
        return "foto"
    if m.voice:
        return "voz"
    if m.video_note:
        return "video-redondo"
    if m.video:
        return "video"
    if m.audio:
        return "audio"
    if m.document:
        return "documento"
    return None


async def principal():
    t = time.perf_counter()
    from telethon import TelegramClient, events
    from telethon import __version__ as versao_telethon
    from telethon.errors import SessionPasswordNeededError
    log("telethon %s importado em %.2fs" % (
        versao_telethon, time.perf_counter() - t))
    try:
        import hachoir  # noqa: F401
        log("hachoir instalado: sim (o Telethon le duracao e tamanho do video)")
    except ImportError:
        log("hachoir instalado: nao (video pode sair sem duracao)")
    log("ffmpeg no PATH: %s" % ("sim" if shutil.which("ffmpeg") else "nao"))

    conf = pedir_por_arquivo(
        ARQ_CONF, MODELO_CONF, conf_valida,
        "Vou abrir o Bloco de Notas com um arquivo de configuração. "
        "Preencha o api id, o api hash e o telefone depois dos sinais de "
        "igual, salve com Control S e pode deixar o Bloco de Notas aberto. "
        "Aperte Enter para fechar este aviso.")
    if conf is None:
        log("ERRO: a configuracao nao foi preenchida a tempo")
        return
    log("configuracao lida do arquivo")

    os.makedirs(SESSAO_DIR, exist_ok=True)
    client = TelegramClient(os.path.join(SESSAO_DIR, "teste"),
                            int(conf["API_ID"]), conf["API_HASH"])

    t = time.perf_counter()
    await client.connect()
    log("conectou aos servidores em %.2fs" % (time.perf_counter() - t))

    if not await client.is_user_authorized():
        log("sessao nova: login necessario")
        t = time.perf_counter()
        await client.send_code_request(conf["TELEFONE"])
        log("codigo solicitado em %.2fs" % (time.perf_counter() - t))
        apagar(ARQ_CODIGO)
        dados = pedir_por_arquivo(
            ARQ_CODIGO, MODELO_CODIGO,
            lambda d: d.get("CODIGO", "").isdigit()
            and len(d.get("CODIGO", "")) >= 4,
            "O Telegram enviou um código para o seu aplicativo no celular. "
            "Vou abrir o Bloco de Notas: digite o código depois do sinal de "
            "igual e salve com Control S. Aperte Enter para fechar este "
            "aviso.", timeout=300)
        if dados is None:
            log("ERRO: o codigo nao foi informado a tempo")
            apagar(ARQ_CODIGO)
            await client.disconnect()
            return
        codigo = dados["CODIGO"]
        apagar(ARQ_CODIGO)
        try:
            await client.sign_in(conf["TELEFONE"], codigo)
        except SessionPasswordNeededError:
            log("a conta tem senha de duas etapas")
            apagar(ARQ_SENHA)
            dados = pedir_por_arquivo(
                ARQ_SENHA, MODELO_SENHA,
                lambda d: len(d.get("SENHA", "")) >= 1,
                "Sua conta tem senha de duas etapas. Vou abrir o Bloco de "
                "Notas: digite a senha depois do sinal de igual e salve com "
                "Control S. Aperte Enter para fechar este aviso.",
                timeout=300)
            if dados is None:
                log("ERRO: a senha nao foi informada a tempo")
                apagar(ARQ_SENHA)
                await client.disconnect()
                return
            senha = dados["SENHA"]
            apagar(ARQ_SENHA)
            await client.sign_in(password=senha)
        log("login concluido")
    else:
        log("sessao salva reutilizada: sem novo login")

    t = time.perf_counter()
    dialogos = await client.get_dialogs(limit=30)
    usuarios = grupos = canais = 0
    for d in dialogos:
        if d.is_user:
            usuarios += 1
        elif d.is_group:
            grupos += 1
        elif d.is_channel:
            canais += 1
    log("conversas lidas: %d (usuarios=%d, grupos=%d, canais=%d) em %.2fs" % (
        len(dialogos), usuarios, grupos, canais, time.perf_counter() - t))

    # ---- observador de mensagens (registrado antes dos envios) ----------
    enviados = set()
    estado = {"liberado": False}
    baixados = set()
    contagem = {}
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    @client.on(events.NewMessage())
    async def ao_receber(evento):
        m = evento.message
        meu_script = m.id in enviados
        tipo = tipo_midia(m) or ("texto" if (m.raw_text or "") else "outro")
        origem = "script" if meu_script else "externo"
        chave = (tipo, origem)
        contagem[chave] = contagem.get(chave, 0) + 1
        if evento.is_private:
            chat = "privado"
        elif evento.is_group:
            chat = "grupo"
        elif evento.is_channel:
            chat = "canal"
        else:
            chat = "outro"
        declarado = 0
        if m.file is not None and m.file.size:
            declarado = m.file.size
        log("evento: tipo=%s origem=%s chat=%s minha=%s texto=%d "
            "mime=%s declarado=%d bytes" % (
                tipo, origem, chat, evento.out, len(m.raw_text or ""),
                (m.file.mime_type if m.file is not None else "-"), declarado))
        if tipo not in ("texto", "outro") and chave not in baixados:
            baixados.add(chave)
            t0 = time.perf_counter()
            destino = os.path.join(DOWNLOAD_DIR, "baixado-%s-%s" % (
                tipo, origem))
            try:
                caminho = await client.download_media(m, file=destino)
                tamanho = os.path.getsize(caminho) if caminho else 0
                log("download de %s (%s): %d bytes em %.2fs" % (
                    tipo, origem, tamanho, time.perf_counter() - t0))
                if caminho:
                    apagar(caminho)
            except Exception:
                log("download de %s (%s) FALHOU:\n%s" % (
                    tipo, origem, traceback.format_exc()))
        if estado["liberado"] and not meu_script and not estado.get("primeira"):
            estado["primeira"] = True
            log("primeira mensagem externa em %.1fs apos o aviso" % (
                time.perf_counter() - estado["t_aviso"]))

    # ---- envios ----------------------------------------------------------
    caminhos = amostras.gerar(AMOSTRAS_DIR)

    async def enviar(rotulo, coro):
        t0 = time.perf_counter()
        try:
            msg = await coro
            enviados.add(msg.id)
            log("envio de %s: OK em %.2fs" % (rotulo, time.perf_counter() - t0))
        except Exception:
            log("envio de %s FALHOU:\n%s" % (rotulo, traceback.format_exc()))

    await enviar("texto", client.send_message(
        "me", "Teste do TeleZapp: texto"))
    await enviar("foto", client.send_file(
        "me", caminhos["foto"], caption="Teste do TeleZapp: foto"))
    await enviar("video", client.send_file(
        "me", caminhos["video"], caption="Teste do TeleZapp: video",
        supports_streaming=True))
    await enviar("nota de voz", client.send_file(
        "me", caminhos["voz"], voice_note=True))
    await enviar("documento", client.send_file(
        "me", caminhos["documento"], caption="Teste do TeleZapp: documento",
        force_document=True))

    estado["liberado"] = True
    estado["t_aviso"] = time.perf_counter()
    log("envios de amostra terminados; aguardando o usuario encerrar")
    texto_caixa = (
        "Enviei para Mensagens Salvas: texto, foto, vídeo, nota de voz e "
        "documento. Confira no celular se chegaram, se o vídeo toca e se a "
        "nota de voz aparece como áudio de voz.\n\n"
        "Agora, do celular, em Mensagens Salvas, envie uma mensagem de "
        "texto, uma foto, um vídeo, um áudio e um documento. Dica: para não "
        "precisar procurar arquivos, encaminhe para a mesma conversa a "
        "foto, o vídeo, a nota de voz e o documento que eu acabei de "
        "enviar. Se quiser, escreva também num grupo.\n\n"
        "O teste continua até você terminar. Quando acabar, aperte Enter "
        "nesta caixa para encerrar o teste.")
    loop = asyncio.get_running_loop()
    fim_do_teste = asyncio.Event()

    def caixa_de_encerramento():
        aviso(texto_caixa, titulo="Teste em andamento", bloquear=True)
        loop.call_soon_threadsafe(fim_do_teste.set)

    threading.Thread(target=caixa_de_encerramento, daemon=True).start()
    try:
        await asyncio.wait_for(fim_do_teste.wait(),
                               timeout=LIMITE_ESPERA_SEGUNDOS)
        log("usuario encerrou o teste")
    except asyncio.TimeoutError:
        log("tempo limite de seguranca atingido (%ds)" % LIMITE_ESPERA_SEGUNDOS)

    resumo = ", ".join("%s/%s=%d" % (t_, o_, n_)
                       for (t_, o_), n_ in sorted(contagem.items()))
    log("resumo dos eventos (tipo/origem=quantidade): " + (resumo or "nenhum"))
    await client.disconnect()
    log("desconectado")


def main():
    log("==== teste do Telegram (Python) v2, com midia ====")
    log("python %s em %s" % (sys.version.split()[0], platform.platform()))
    try:
        asyncio.run(principal())
        log("RESULTADO: script terminou sem erro")
        return 0
    except SystemExit as e:
        log("encerrado: %s" % e)
        return 1
    except Exception:
        log("ERRO:\n" + traceback.format_exc())
        return 1
    finally:
        shutil.rmtree(DOWNLOAD_DIR, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

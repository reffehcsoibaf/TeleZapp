# -*- coding: utf-8 -*-
"""Teste de velocidade de arquivos grandes no Telegram: quatro jeitos de enviar
e baixar o mesmo arquivo, todos com a criptografia rapida (cryptg).

Uso (chamado pelo 7-teste-telegram-velocidade.bat):
  python telegram_velocidade.py <arquivo-de-log>

Por que: o teste anterior mostrou que, com o cryptg, o Telethon manda e baixa
partes de 128 KB uma de cada vez e fica limitado pela latencia (cerca de 0,6
MB/s), enquanto o WhatsApp passou de 7 MB/s no envio e 18 MB/s no download na
mesma conexao. Variantes:
  1. padrao do Telethon: partes de 128 KB, uma por vez
  2. partes de 512 KB (o maximo permitido), uma por vez
  3. partes de 512 KB, 4 ao mesmo tempo
  4. partes de 512 KB, 8 ao mesmo tempo
Cada variante envia o arquivo para Mensagens Salvas, baixa de volta, confere
tamanho e SHA-256 e apaga a mensagem de teste.
"""
import asyncio
import os
import platform
import sys
import time
import traceback

from acessivel import sinal
import arquivos_grandes as ag
import telegram_login

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    BASE, "logs", "resultado-teste-velocidade-telegram.log")
MINIMO_MB_PARALELO = 11  # abaixo de 10 MB o Telegram usa outro tipo de envio
VARIANTES = (
    ("1 padrao: partes de 128 KB, uma por vez", "nativo", 128, 1),
    ("2 partes de 512 KB, uma por vez", "nativo512", 512, 1),
    ("3 partes de 512 KB, 4 ao mesmo tempo", "paralelo", 512, 4),
    ("4 partes de 512 KB, 8 ao mesmo tempo", "paralelo", 512, 8),
)


def log(msg):
    linha = "%s %s" % (time.strftime("%H:%M:%S"), msg)
    print(linha, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except OSError:
        pass


def progresso(rotulo):
    """Callback que registra a cada 25%."""
    estado = {"proximo": 25, "t0": time.perf_counter()}

    def cb(feito, total):
        if not total:
            return
        pct = feito * 100 // total
        while estado["proximo"] <= pct and estado["proximo"] <= 100:
            dt = time.perf_counter() - estado["t0"]
            log("    %s %d%%: %s, media %s" % (
                rotulo, estado["proximo"], ag.segundos_txt(dt),
                ag.velocidade(feito, dt)))
            estado["proximo"] += 25
    return cb


async def upload_paralelo(client, caminho, part_kb, simultaneas, cb):
    """Envia um arquivo grande em partes, varias requisicoes ao mesmo tempo."""
    from telethon import helpers
    from telethon.tl import functions, types
    tamanho = os.path.getsize(caminho)
    if tamanho <= 10 * 1024 * 1024:
        raise ValueError("envio paralelo so para arquivos acima de 10 MB")
    tam_parte = part_kb * 1024
    total = (tamanho + tam_parte - 1) // tam_parte
    file_id = helpers.generate_random_long()
    sem = asyncio.Semaphore(simultaneas)
    feitos = {"bytes": 0}
    with open(caminho, "rb") as f:
        async def enviar(i):
            async with sem:
                f.seek(i * tam_parte)
                parte = f.read(tam_parte)
                ok = await client(functions.upload.SaveBigFilePartRequest(
                    file_id, i, total, parte))
                if not ok:
                    raise RuntimeError("parte %d recusada" % i)
                feitos["bytes"] += len(parte)
                cb(feitos["bytes"], tamanho)

        tarefas = [asyncio.ensure_future(enviar(i)) for i in range(total)]
        try:
            await asyncio.gather(*tarefas)
        except BaseException:
            for t in tarefas:
                t.cancel()
            raise
    return types.InputFileBig(file_id, total, os.path.basename(caminho))


async def download_paralelo(client, mensagem, destino, part_kb, simultaneas,
                            cb):
    """Baixa um arquivo em partes, com varios trechos em andamento juntos.

    O trabalhador i baixa as partes i, i+N, i+2N... (uso de offset e stride do
    iter_download do Telethon) e grava cada uma na posicao certa do arquivo.
    """
    tamanho = mensagem.file.size
    tam_parte = part_kb * 1024
    total = (tamanho + tam_parte - 1) // tam_parte
    feitos = {"bytes": 0}
    with open(destino, "wb") as f:
        f.truncate(tamanho)
    f = open(destino, "r+b")
    try:
        async def trabalhador(i):
            limite = (total - i + simultaneas - 1) // simultaneas
            if limite <= 0:
                return
            k = 0
            async for dados in client.iter_download(
                    mensagem.media, offset=i * tam_parte,
                    stride=simultaneas * tam_parte, chunk_size=tam_parte,
                    request_size=tam_parte, limit=limite, file_size=tamanho):
                f.seek((i + k * simultaneas) * tam_parte)
                f.write(dados)
                k += 1
                feitos["bytes"] += len(dados)
                cb(feitos["bytes"], tamanho)

        tarefas = [asyncio.ensure_future(trabalhador(i))
                   for i in range(simultaneas)]
        try:
            await asyncio.gather(*tarefas)
        except BaseException:
            for t in tarefas:
                t.cancel()
            raise
    finally:
        f.close()


async def medir(client, caminho, sha, nome, modo, part_kb, n):
    tamanho = os.path.getsize(caminho)
    legenda = "Teste de velocidade do TeleZapp"
    mensagem = None
    resultado = {"nome": nome, "envio": None, "download": None,
                 "integridade": "nao medido"}
    log("---- variante %s" % nome)
    try:
        t0 = time.perf_counter()
        if modo == "nativo":
            mensagem = await client.send_file(
                "me", caminho, force_document=True, caption=legenda,
                progress_callback=progresso("envio"))
        elif modo == "nativo512":
            h = await client.upload_file(
                caminho, part_size_kb=512, file_size=tamanho,
                progress_callback=progresso("envio"))
            mensagem = await client.send_file(
                "me", h, force_document=True, caption=legenda)
        else:
            h = await upload_paralelo(client, caminho, part_kb, n,
                                      progresso("envio"))
            mensagem = await client.send_file(
                "me", h, force_document=True, caption=legenda)
        t_envio = time.perf_counter() - t0
        resultado["envio"] = ag.velocidade(tamanho, t_envio)
        log("  ENVIO: %s em %s" % (resultado["envio"],
                                   ag.segundos_txt(t_envio)))

        destino = os.path.join(ag.PASTA, "baixado-velocidade.bin")
        t0 = time.perf_counter()
        if modo == "nativo":
            await client.download_media(
                mensagem, file=destino,
                progress_callback=progresso("download"))
        elif modo == "nativo512":
            await client.download_file(
                mensagem.document, file=destino, part_size_kb=512,
                file_size=tamanho, progress_callback=progresso("download"))
        else:
            await download_paralelo(client, mensagem, destino, part_kb, n,
                                    progresso("download"))
        t_down = time.perf_counter() - t0
        resultado["download"] = ag.velocidade(tamanho, t_down)
        log("  DOWNLOAD: %s em %s" % (resultado["download"],
                                      ag.segundos_txt(t_down)))

        ok_tam = os.path.getsize(destino) == tamanho
        ok_hash = ag.sha256_arquivo(destino) == sha
        resultado["integridade"] = "OK" if (ok_tam and ok_hash) else "FALHOU"
        log("  INTEGRIDADE: tamanho igual=%s, SHA-256 igual=%s" % (
            ok_tam, ok_hash))
    except Exception:
        resultado["integridade"] = "ERRO"
        log("  FALHOU nesta variante:\n" + traceback.format_exc())
    finally:
        if mensagem is not None:
            try:
                await client.delete_messages("me", [mensagem.id])
            except Exception:
                log("  nao consegui apagar a mensagem de teste")
        sinal()
    return resultado


async def principal():
    mb = max(ag.ler_tamanho_mb(log), MINIMO_MB_PARALELO)
    try:
        import cryptg  # noqa: F401
        log("cryptg instalado: sim")
    except ImportError:
        log("AVISO: cryptg NAO instalado; as velocidades vao ser as da "
            "criptografia lenta")
    client = await telegram_login.conectar(log)
    if client is None:
        return
    resultados = []
    try:
        caminho = ag.gerar_arquivo("arquivo-velocidade-telegram.bin", mb)
        sha = ag.sha256_arquivo(caminho)
        log("arquivo de teste gerado: %d MB" % mb)
        for nome, modo, part_kb, n in VARIANTES:
            resultados.append(await medir(client, caminho, sha, nome, modo,
                                          part_kb, n))
    finally:
        await client.disconnect()
        ag.limpar()
    log("================ RESUMO (arquivo de %d MB) ================" % mb)
    for r in resultados:
        log("RESUMO %-42s envio %-11s download %-11s integridade %s" % (
            r["nome"], r["envio"] or "-", r["download"] or "-",
            r["integridade"]))


def main():
    log("==== teste de velocidade no Telegram ====")
    log("python %s em %s" % (sys.version.split()[0], platform.platform()))
    try:
        asyncio.run(principal())
        log("teste terminou sem erro")
        return 0
    except Exception:
        log("ERRO:\n" + traceback.format_exc())
        ag.limpar()
        return 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""Teste de arquivos grandes no Telegram (Telethon).

Uso (chamado pelo 5-teste-arquivos-grandes-telegram.bat):
  python telegram_grande.py <rotulo> <arquivo-de-log>

Mede, numa rodada: o tipo de criptografia que o Telethon esta usando, a
velocidade dessa criptografia sozinha (sem rede), o envio e o download de um
arquivo de dados aleatorios para Mensagens Salvas, e confere se o arquivo
baixado e identico (tamanho e SHA-256). A mensagem de teste e apagada no fim.
Tamanho do arquivo: configuracao-arquivos-grandes.txt (padrao 20 MB).
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
ROTULO = sys.argv[1] if len(sys.argv) > 1 else "X"
LOG = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    BASE, "logs", "resultado-teste-grande-telegram.log")
LIMITE_PYTHON_PURO_MB = 30
BENCH_MB = 2


def log(msg):
    linha = "%s [rodada %s] %s" % (time.strftime("%H:%M:%S"), ROTULO, msg)
    print(linha, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except OSError:
        pass


def metodo_aes():
    import telethon.crypto.aes as aes
    if getattr(aes, "cryptg", None):
        return "cryptg"
    if aes.libssl.encrypt_ige and aes.libssl.decrypt_ige:
        return "libssl"
    return "Python puro (pyaes)"


def benchmark_aes():
    """Velocidade da criptografia AES-IGE do Telethon, sem rede."""
    from telethon.crypto import AES
    dados = os.urandom(BENCH_MB * 1024 * 1024)
    chave, iv = os.urandom(32), os.urandom(32)
    t = time.perf_counter()
    cifrado = AES.encrypt_ige(dados, chave, iv)
    t_cifrar = time.perf_counter() - t
    t = time.perf_counter()
    AES.decrypt_ige(cifrado, chave, iv)
    t_decifrar = time.perf_counter() - t
    return t_cifrar, t_decifrar


def progresso(rotulo, total_bytes_ref):
    """Cria um callback que registra a cada 10%."""
    estado = {"proximo": 10, "t0": time.perf_counter()}

    def cb(feito, total):
        if not total:
            return
        pct = feito * 100 // total
        while estado["proximo"] <= pct and estado["proximo"] <= 100:
            dt = time.perf_counter() - estado["t0"]
            log("  %s %d%%: %s, velocidade media %s" % (
                rotulo, estado["proximo"], ag.segundos_txt(dt),
                ag.velocidade(feito, dt)))
            estado["proximo"] += 10
    return cb


async def principal():
    mb = ag.ler_tamanho_mb(log)
    metodo = metodo_aes()
    log("criptografia do Telethon nesta rodada: %s" % metodo)
    t_cif, t_dec = benchmark_aes()
    log("criptografia sozinha, sem rede (%d MB): cifrar %s, decifrar %s" % (
        BENCH_MB, ag.velocidade(BENCH_MB * 1048576, t_cif),
        ag.velocidade(BENCH_MB * 1048576, t_dec)))
    sinal()
    if metodo.startswith("Python") and BENCH_MB / t_cif < 0.5 \
            and mb > LIMITE_PYTHON_PURO_MB:
        log("aviso: a criptografia em Python puro e lenta; limitando esta "
            "rodada a %d MB (pedido: %d MB)" % (LIMITE_PYTHON_PURO_MB, mb))
        mb = LIMITE_PYTHON_PURO_MB

    client = await telegram_login.conectar(log)
    if client is None:
        return
    mensagem = None
    try:
        caminho = ag.gerar_arquivo("arquivo-grande-telegram.bin", mb)
        tamanho = os.path.getsize(caminho)
        sha = ag.sha256_arquivo(caminho)
        log("arquivo de teste gerado: %d MB" % mb)

        t0 = time.perf_counter()
        mensagem = await client.send_file(
            "me", caminho, force_document=True,
            caption="Teste de arquivo grande do TeleZapp",
            progress_callback=progresso("envio", tamanho))
        t_envio = time.perf_counter() - t0
        log("ENVIO concluido: %s em %s" % (
            ag.velocidade(tamanho, t_envio), ag.segundos_txt(t_envio)))
        sinal()

        destino = os.path.join(ag.PASTA, "baixado-telegram.bin")
        t0 = time.perf_counter()
        await client.download_media(
            mensagem, file=destino,
            progress_callback=progresso("download", tamanho))
        t_down = time.perf_counter() - t0
        log("DOWNLOAD concluido: %s em %s" % (
            ag.velocidade(tamanho, t_down), ag.segundos_txt(t_down)))

        mesmo_tamanho = os.path.getsize(destino) == tamanho
        mesmo_hash = ag.sha256_arquivo(destino) == sha
        log("INTEGRIDADE: tamanho igual=%s, SHA-256 igual=%s" % (
            mesmo_tamanho, mesmo_hash))
        log("RESUMO rodada %s: %s, cifrar %s, decifrar %s, arquivo %d MB, "
            "envio %s, download %s, integridade %s" % (
                ROTULO, metodo,
                ag.velocidade(BENCH_MB * 1048576, t_cif),
                ag.velocidade(BENCH_MB * 1048576, t_dec), mb,
                ag.velocidade(tamanho, t_envio),
                ag.velocidade(tamanho, t_down),
                "OK" if (mesmo_tamanho and mesmo_hash) else "FALHOU"))
        sinal()
    finally:
        if mensagem is not None:
            try:
                await client.delete_messages("me", [mensagem.id])
                log("mensagem de teste apagada de Mensagens Salvas")
            except Exception:
                log("nao consegui apagar a mensagem de teste:\n" +
                    traceback.format_exc())
        await client.disconnect()
        ag.limpar()


def main():
    log("==== teste de arquivos grandes: Telegram ====")
    log("python %s em %s" % (sys.version.split()[0], platform.platform()))
    try:
        asyncio.run(principal())
        log("rodada terminou sem erro")
        return 0
    except Exception:
        log("ERRO:\n" + traceback.format_exc())
        ag.limpar()
        return 1


if __name__ == "__main__":
    sys.exit(main())

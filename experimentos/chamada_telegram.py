# -*- coding: utf-8 -*-
"""Teste de chamada de voz 1 a 1 no Telegram com py-tgcalls (NTgCalls).

Chamado pelo 9-teste-chamada-telegram.bat. Etapas:
  1. lista microfones e alto-falantes que a NTgCalls enxerga (sem FFmpeg)
  2. entra no Telegram com a sessao dos outros testes
  3. escolhe o modo: ligar para alguem ou esperar uma chamada
  4. durante a chamada, anota os eventos e quanto demorou para conectar
  5. encerra sozinho depois de DURACAO_S segundos, ou quando a outra
     pessoa desligar

O teste so mede se a chamada de voz funciona e quanto pesa. Nao grava nem
guarda o audio da conversa. Avise a outra pessoa antes de ligar.

Nao usa o terminal: avisos em caixas de mensagem, fala pelo NVDA e bipes.
"""
import asyncio
import os
import platform
import sys
import time
import traceback

from acessivel import aviso, perguntar_sim_nao, pedir_por_arquivo
from fala import Fala, bipe

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    BASE, "logs", "resultado-teste-chamada-telegram.log")
ARQ_ALVO = os.path.join(BASE, "alvo-chamada.txt")
DURACAO_S = 45
ESPERA_ATENDER_S = 90

MODELO_ALVO = (
    "# Quem vai receber a chamada de teste.\n"
    "# Use @nome_de_usuario ou o telefone com + e codigo do pais.\n"
    "# A pessoa precisa estar nos seus contatos ou ter conversado com voce.\n"
    "ALVO=\n")


def log(msg):
    linha = time.strftime("%H:%M:%S") + " " + msg
    print(linha, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except OSError:
        pass


def _versao(pacote):
    try:
        from importlib.metadata import version
        return version(pacote)
    except Exception:
        return "?"


def listar_dispositivos(MediaDevices):
    mics = list(MediaDevices.microphone_devices())
    alto = list(MediaDevices.speaker_devices())
    log("microfones vistos pela NTgCalls: %d" % len(mics))
    for d in mics:
        log("   microfone: %s" % d.title)
    log("alto-falantes vistos pela NTgCalls: %d" % len(alto))
    for d in alto:
        log("   saida: %s" % d.title)
    return mics, alto


async def main():
    fala = Fala(log)
    log("==== TESTE DE CHAMADA DE VOZ NO TELEGRAM ====")
    log("sistema: %s %s | Python %s" % (
        platform.system(), platform.release(), platform.python_version()))
    for p in ("py-tgcalls", "ntgcalls", "telethon"):
        log("pacote %s %s" % (p, _versao(p)))

    from pytgcalls import PyTgCalls, MediaDevices, filters
    from pytgcalls.types import (ChatUpdate, MediaStream, RecordStream,
                                 AudioQuality)

    mics, alto = listar_dispositivos(MediaDevices)
    if not mics or not alto:
        log("ERRO: falta microfone ou saida de som")
        aviso("O teste precisa de um microfone e de uma saída de som no "
              "Windows. Não encontrei os dois.")
        return 2

    from telegram_login import conectar
    client = await conectar(log)
    if client is None:
        return 2
    eu = await client.get_me()
    log("conectado como id %s" % eu.id)

    ligar = perguntar_sim_nao(
        "Quer ligar para alguém agora? Sim: eu ligo para a pessoa que você "
        "indicar. Não: fico esperando uma chamada para este Telegram. "
        "Use fones de ouvido, para o som da outra pessoa não voltar pelo "
        "microfone. Avise a outra pessoa antes.")

    app = PyTgCalls(client)
    encerrou = asyncio.Event()
    estado = {"inicio": None, "conectou": None, "chat": None, "motivo": ""}
    microfone = mics[0]
    saida = alto[0]

    def fluxo_envio():
        return MediaStream(microfone, audio_parameters=AudioQuality.HIGH,
                           video_flags=MediaStream.Flags.IGNORE)

    @app.on_update(filters.chat_update(ChatUpdate.Status.LEFT_CALL))
    async def _saiu(_, update):
        estado["motivo"] = str(update.status)
        log("evento: chamada encerrada (%s)" % update.status)
        encerrou.set()

    @app.on_update(filters.chat_update(ChatUpdate.Status.INCOMING_CALL))
    async def _recebida(_, update):
        log("evento: chamada recebida de %s" % update.chat_id)
        if ligar:
            return
        estado["chat"] = update.chat_id
        bipe()
        fala.falar("Chamada recebida. Atendendo.")
        try:
            estado["inicio"] = time.perf_counter()
            await app.play(update.chat_id, fluxo_envio())
            await app.record(update.chat_id, RecordStream(audio=saida))
            estado["conectou"] = time.perf_counter()
            log("atendeu e conectou em %.2fs" % (
                estado["conectou"] - estado["inicio"]))
        except Exception as e:
            log("ERRO ao atender: %r" % e)
            log(traceback.format_exc())
            encerrou.set()

    await app.start()
    log("py-tgcalls iniciado")

    try:
        if ligar:
            dados = pedir_por_arquivo(
                ARQ_ALVO, MODELO_ALVO,
                lambda d: len(d.get("ALVO", "").strip()) >= 3,
                "Vou abrir o Bloco de Notas: digite depois do sinal de "
                "igual quem vai receber a chamada (arroba e nome de "
                "usuário, ou o telefone com mais e código do país). Salve "
                "com Control S. Aperte Enter para fechar este aviso.",
                timeout=300)
            if dados is None:
                log("ERRO: ninguem foi indicado a tempo")
                return 2
            alvo = dados["ALVO"].strip()
            ent = await client.get_entity(alvo)
            estado["chat"] = ent.id
            log("chamando %s (id %s)" % (alvo, ent.id))
            fala.falar("Chamando.")
            bipe()
            estado["inicio"] = time.perf_counter()
            try:
                await app.play(ent.id, fluxo_envio())
                await app.record(ent.id, RecordStream(audio=saida))
            except Exception as e:
                log("ERRO ao ligar: %s %r" % (type(e).__name__, e))
                log(traceback.format_exc())
                return 1
            estado["conectou"] = time.perf_counter()
            log("a outra pessoa atendeu; conectou em %.2fs" % (
                estado["conectou"] - estado["inicio"]))
        else:
            fala.falar("Esperando uma chamada. Ligue para este Telegram.")
            aviso("Estou esperando uma chamada. Ligue para este Telegram de "
                  "outro aparelho. Aperte Enter e deixe esta janela de "
                  "lado; o teste espera %d segundos." % ESPERA_ATENDER_S)
            for _ in range(ESPERA_ATENDER_S):
                if estado["conectou"] or encerrou.is_set():
                    break
                await asyncio.sleep(1)
            if not estado["conectou"]:
                log("ERRO: nenhuma chamada foi atendida a tempo")
                return 1

        bipe()
        fala.falar("Chamada em andamento. Fale e escute. O teste dura %d "
                   "segundos." % DURACAO_S)
        log("em chamada; medindo por %d s" % DURACAO_S)
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < DURACAO_S and not encerrou.is_set():
            await asyncio.sleep(5)
            try:
                uso = await app.cpu_usage()
            except Exception:
                uso = None
            log("   %3.0fs em chamada | uso de CPU da NTgCalls: %s" % (
                time.perf_counter() - t0, uso))
        log("duracao da chamada: %.1fs" % (time.perf_counter() - t0))
    finally:
        try:
            if estado["chat"] is not None:
                await app.leave_call(estado["chat"])
                log("chamada encerrada por aqui")
        except Exception as e:
            log("aviso ao encerrar: %r" % e)
        await client.disconnect()

    ok = perguntar_sim_nao(
        "A chamada terminou. Você ouviu a outra pessoa com clareza e ela "
        "ouviu você? Sim se a voz foi boa nos dois lados.")
    log("RESULTADO PELO OUVIDO: %s" % (
        "voz boa nos dois lados" if ok else "houve problema na voz"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()) or 0)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:
        log("ERRO INESPERADO:\n" + traceback.format_exc())
        sys.exit(1)

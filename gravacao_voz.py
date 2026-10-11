# -*- coding: utf-8 -*-
"""Teste de gravacao de voz pelo microfone do Windows.

Chamado pelo 8-teste-gravacao-voz.bat. Etapas:
  1. lista os dispositivos de audio e verifica o suporte a Opus
  2. grava 8 segundos do microfone padrao (voce conta de um a dez)
  3. mede o nivel do sinal (para detectar microfone mudo ou bloqueado)
  4. codifica em Ogg/Opus em cinco niveis de compressao
  5. toca o original e as cinco versoes, uma anunciando a outra
  6. se voce quiser, envia as versoes como notas de voz para o Telegram

Nao usa o terminal: avisos em caixas de mensagem, fala pelo NVDA e bipes.
"""
import asyncio
import os
import platform
import sys
import time
import traceback

from acessivel import aviso, perguntar_sim_nao
from fala import Fala, bipe
import opus_util

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    BASE, "logs", "resultado-teste-gravacao-voz.log")
PASTA = os.path.join(BASE, "gravacoes-teste")
DURACAO_S = 8
SR = 48000
PICO_MINIMO_DB = -50.0

# (letra, nome, compression_level do soundfile; None = padrao da biblioteca)
VERSOES = (
    ("A", "qualidade máxima", 0.0),
    ("B", "alta", 0.3),
    ("C", "média", 0.5),
    ("D", "padrão da biblioteca", None),
    ("E", "compressão máxima, só para comparar", 1.0),
)


def log(msg):
    linha = time.strftime("%H:%M:%S") + " " + msg
    print(linha, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except OSError:
        pass


def descrever_dispositivos(sd):
    try:
        padrao = sd.query_devices(kind="input")
        log("microfone padrao: %s (%d canal(is), %d Hz)" % (
            padrao["name"], padrao["max_input_channels"],
            padrao["default_samplerate"]))
    except Exception as e:
        log("ERRO: nao ha microfone padrao: %r" % e)
        return False
    try:
        saida = sd.query_devices(kind="output")
        log("saida padrao: %s" % saida["name"])
    except Exception as e:
        log("aviso: sem saida de audio padrao: %r" % e)
    n = 0
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            n += 1
            api = sd.query_hostapis(d["hostapi"])["name"]
            log("  entrada %d: %s | %s | %d canal(is) | %d Hz" % (
                i, d["name"], api, d["max_input_channels"],
                d["default_samplerate"]))
    log("dispositivos de entrada encontrados: %d" % n)
    return n > 0


def gravar(sd, np):
    """Grava DURACAO_S segundos no microfone padrao. Devolve (dados, taxa)."""
    info = sd.query_devices(kind="input")
    candidatas = [SR]
    padrao_hz = int(info["default_samplerate"])
    if padrao_hz not in candidatas:
        candidatas.append(padrao_hz)
    escolhida = None
    for sr in candidatas:
        try:
            sd.check_input_settings(samplerate=sr, channels=1)
            escolhida = sr
            break
        except Exception as e:
            log("taxa %d Hz nao aceita: %r" % (sr, e))
    if escolhida is None:
        raise RuntimeError("o microfone nao aceitou nenhuma taxa testada")
    log("gravando a %d Hz, 1 canal, %d segundos" % (escolhida, DURACAO_S))
    t0 = time.perf_counter()
    bruto = sd.rec(int(DURACAO_S * escolhida), samplerate=escolhida,
                   channels=1, dtype="float32")
    sd.wait()
    log("gravacao terminada em %.2fs" % (time.perf_counter() - t0))
    dados = np.asarray(bruto, dtype="float32").reshape(-1)
    return dados, escolhida


def medir_nivel(np, dados):
    pico = float(np.max(np.abs(dados))) if len(dados) else 0.0
    rms = float(np.sqrt(np.mean(np.square(dados)))) if len(dados) else 0.0
    return opus_util.para_dbfs(pico), opus_util.para_dbfs(rms)


def codificar(sf, dados, caminho, nivel):
    argumentos = {} if nivel is None else {"compression_level": nivel}
    t0 = time.perf_counter()
    with sf.SoundFile(caminho, "w", samplerate=SR, channels=1,
                      format="OGG", subtype="OPUS", **argumentos) as f:
        f.write(dados)
    return time.perf_counter() - t0


def tocar(sd, np, dados, taxa):
    sd.play(dados, taxa)
    sd.wait()


def anunciar(fala, texto, bipes):
    """Anuncia pela fala do NVDA e tambem por bipes (um por versao)."""
    for _ in range(bipes):
        bipe("enviada")
        time.sleep(0.12)
    if fala.falar(texto, interromper=True):
        time.sleep(2.6)
    else:
        time.sleep(0.6)


async def enviar_telegram(arquivos):
    """Envia as versoes como notas de voz para Mensagens Salvas."""
    import telegram_login
    from telethon.tl import types
    client = await telegram_login.conectar(log)
    if client is None:
        return False
    try:
        for letra, nome, caminho, segundos in arquivos:
            t0 = time.perf_counter()
            await client.send_file(
                "me", caminho, voice_note=True,
                attributes=[types.DocumentAttributeAudio(
                    duration=int(round(segundos)), voice=True)],
                caption="Voz %s: %s" % (letra, nome))
            log("telegram: versao %s enviada em %.2fs" % (
                letra, time.perf_counter() - t0))
    finally:
        await client.disconnect()
    return True


def principal():
    try:
        import numpy as np
        import sounddevice as sd
        import soundfile as sf
    except Exception:
        log("ERRO ao importar as bibliotecas de audio:\n" +
            traceback.format_exc())
        aviso("Não consegui carregar as bibliotecas de áudio. O log mostra "
              "o erro.", bloquear=True)
        return 1

    log("sounddevice %s | %s" % (sd.__version__, sd.get_portaudio_version()[1]))
    log("soundfile %s | libsndfile %s" % (
        sf.__version__, sf.__libsndfile_version__))
    suporta_opus = "OPUS" in sf.available_subtypes("OGG")
    log("suporte a Opus no Ogg: %s" % ("SIM" if suporta_opus else "NAO"))
    if not suporta_opus:
        aviso("Esta versão da biblioteca de áudio não sabe gravar Opus. O "
              "log tem os detalhes.", bloquear=True)
        return 2
    if not descrever_dispositivos(sd):
        aviso("Não encontrei nenhum microfone. Conecte um microfone ou "
              "ative um nas configurações de som do Windows e rode o teste "
              "de novo.", bloquear=True)
        return 3

    fala = Fala(log)
    log("NVDA em execucao: %s" % fala.nvda_ativo())
    os.makedirs(PASTA, exist_ok=True)

    aviso("Vou gravar %d segundos do seu microfone. Se puder, use fones de "
          "ouvido, para o microfone não captar a voz do NVDA. Depois do "
          "bipe longo, fale normalmente, por exemplo contando de um a dez. "
          "Quando terminar, haverá dois bipes. Aperte Enter para começar." %
          DURACAO_S, titulo="Gravação de voz", bloquear=True)
    time.sleep(2.0)
    bipe("nova")
    time.sleep(0.4)
    try:
        dados, taxa = gravar(sd, np)
    except Exception:
        log("ERRO na gravacao:\n" + traceback.format_exc())
        aviso("A gravação falhou. Verifique, nas configurações do Windows, "
              "em Privacidade e segurança, Microfone, se os aplicativos de "
              "área de trabalho podem usar o microfone. O log mostra o "
              "erro.", bloquear=True)
        return 4
    bipe("enviada")
    time.sleep(0.15)
    bipe("enviada")

    pico_db, rms_db = medir_nivel(np, dados)
    log("nivel da gravacao: pico %.1f dBFS, media (RMS) %.1f dBFS" % (
        pico_db, rms_db))
    if pico_db < PICO_MINIMO_DB:
        log("ALERTA: gravacao praticamente silenciosa")
        aviso("A gravação saiu quase em silêncio. O microfone pode estar "
              "mudo, com o volume muito baixo ou bloqueado pelo Windows. "
              "Verifique em Configurações, Privacidade e segurança, "
              "Microfone, e rode de novo.", bloquear=True)
        return 5
    if pico_db > -1.0:
        log("aviso: o sinal chegou perto do limite maximo; pode haver "
            "distorcao (fale mais longe ou diminua o volume do microfone)")

    dados = opus_util.reamostrar(np, dados, taxa, SR)
    original = os.path.join(PASTA, "voz-0-original.wav")
    sf.write(original, dados, SR, subtype="PCM_16")
    log("original salvo: %d bytes (WAV sem compressao)" % os.path.getsize(
        original))

    arquivos = []
    for letra, nome, nivel in VERSOES:
        caminho = os.path.join(PASTA, "voz-%s.ogg" % letra)
        try:
            tempo = codificar(sf, dados, caminho, nivel)
            tamanho = os.path.getsize(caminho)
            with open(caminho, "rb") as f:
                segundos = opus_util.duracao_ogg_opus(f.read())
            lido, taxa_lida = sf.read(caminho, dtype="float32")
            log("versao %s (%s, compression_level=%s): %d bytes, %.0f "
                "kbit/s, codificou em %.2fs, duracao %.2fs pelo cabecalho e "
                "%.2fs pela leitura, %d Hz" % (
                    letra, nome, nivel, tamanho,
                    tamanho * 8 / segundos / 1000, tempo, segundos,
                    len(lido) / taxa_lida, taxa_lida))
            arquivos.append((letra, nome, caminho, segundos))
        except Exception:
            log("ERRO ao codificar a versao %s:\n%s" % (
                letra, traceback.format_exc()))

    aviso("Vou tocar o original, sem compressão, e depois as versões. Cada "
          "uma é anunciada pela fala e por bipes: um bipe para a versão A, "
          "dois para a B, e assim por diante. Ouça com atenção e me diga "
          "depois qual preferiu. Aperte Enter para começar.",
          titulo="Comparação", bloquear=True)
    time.sleep(1.5)
    try:
        anunciar(fala, "Original, sem compressão.", 0)
        tocar(sd, np, dados, SR)
        time.sleep(0.8)
        for i, (letra, nome, caminho, _seg) in enumerate(arquivos, start=1):
            lido, taxa_lida = sf.read(caminho, dtype="float32")
            anunciar(fala, "Versão %s, %s." % (letra, nome), i)
            tocar(sd, np, lido, taxa_lida)
            time.sleep(0.8)
        log("reproducao concluida sem erro")
    except Exception:
        log("ERRO na reproducao:\n" + traceback.format_exc())

    if arquivos and perguntar_sim_nao(
            "Quer enviar as %d versões como notas de voz para as suas "
            "Mensagens Salvas do Telegram, para ouvir no celular também?" %
            len(arquivos), titulo="Enviar ao Telegram"):
        try:
            ok = asyncio.run(enviar_telegram(arquivos))
            if ok:
                aviso("Enviei as versões para as suas Mensagens Salvas. "
                      "Confira no celular se aparecem como mensagens de "
                      "voz, se a duração está certa e se o som está bom.",
                      bloquear=True)
        except Exception:
            log("ERRO no envio ao Telegram:\n" + traceback.format_exc())
            aviso("O envio ao Telegram falhou. O log mostra o erro.",
                  bloquear=True)
    else:
        log("envio ao Telegram: nao solicitado")
    return 0


def main():
    log("==== teste de gravacao de voz ====")
    log("python %s em %s" % (sys.version.split()[0], platform.platform()))
    try:
        return principal()
    except Exception:
        log("ERRO:\n" + traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())

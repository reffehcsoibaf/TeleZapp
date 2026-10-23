# -*- coding: utf-8 -*-
"""Teste de chamada de voz do WhatsApp com o meowcaller (fase 0).

Chamado pelo 10-teste-chamada-whatsapp.bat. Etapas:
  1. confere microfone e saida de som (sounddevice) e o programa em Go
     (10-chamada-whatsapp-meowcaller\\chamadas-teste.exe)
  2. pareia a conta de teste como aparelho conectado, se ainda nao estiver
     (o codigo de pareamento sai em caixa de mensagem e e falado pelo NVDA)
  3. pergunta se quer ligar ou esperar uma chamada
  4. liga o microfone e o alto-falante a chamada, trocando voz PCM (s16le,
     16 kHz, mono) com o programa em Go por um socket local
  5. mede quanto levou para conectar, se o audio chegou nos dois sentidos,
     quedas de som e memoria; encerra sozinho depois de DURACAO_S segundos

A voz da conversa nao e gravada pelo Python. O programa em Go grava o que
chega em chamada-<id>.wav, ao lado dele, so para conferir; apague depois.

Nao usa o terminal: avisos em caixas de mensagem, fala pelo NVDA e bipes.
"""
import math
import os
import platform
import queue
import socket
import struct
import subprocess
import sys
import threading
import time
import traceback

from acessivel import aviso, perguntar_sim_nao, pedir_por_arquivo
from fala import Fala, bipe

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    BASE, "logs", "resultado-teste-chamada-whatsapp.log")
PASTA_GO = os.path.join(BASE, "10-chamada-whatsapp-meowcaller")
EXE = os.path.join(PASTA_GO, "chamadas-teste.exe")
ARQ_CONFIG = os.path.join(BASE, "configuracao-chamada-whatsapp.txt")
ARQ_CODIGO = os.path.join(BASE, "codigo-pareamento-whatsapp.txt")
TENTATIVAS_CODIGO = 4
DURACAO_S = 45
ESPERA_S = 90
TAXA = 16000
QUADRO = 960                    # 60 ms
BYTES_QUADRO = QUADRO * 2

MODELO_CONFIG = (
    "# Dados do teste de chamada de voz do WhatsApp.\n"
    "# TELEFONE: a conta de TESTE que sera pareada como aparelho conectado,\n"
    "#   com codigo do pais e DDD, so digitos (ex.: 5551999998888).\n"
    "#   Use uma conta de teste, nao a sua principal.\n"
    "# ALVO: para quem ligar (so se escolher ligar), mesmo formato.\n"
    "TELEFONE=\n"
    "ALVO=\n")


def log(msg):
    linha = time.strftime("%H:%M:%S") + " " + msg
    print(linha, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except OSError:
        pass


def so_digitos(texto):
    return "".join(c for c in texto if c.isdigit())


def telefone_valido(dados):
    return 10 <= len(so_digitos(dados.get("TELEFONE", ""))) <= 15


def rodar_go(args, ao_linha, **extra):
    """Inicia o programa em Go e le a saida, uma linha por vez, numa thread."""
    proc = subprocess.Popen(
        [EXE] + args, cwd=PASTA_GO, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8",
        errors="replace", creationflags=getattr(
            subprocess, "CREATE_NO_WINDOW", 0), **extra)

    def ler(fluxo, origem):
        for linha in fluxo:
            linha = linha.rstrip()
            if linha:
                ao_linha(origem, linha)
    for fluxo, origem in ((proc.stdout, "go"), (proc.stderr, "go-log")):
        threading.Thread(target=ler, args=(fluxo, origem), daemon=True).start()
    return proc


# Alfabeto para soletrar: M e N, B e D, F e S etc. soam parecido na voz do
# leitor de tela, entao cada letra vai com um nome (M de Mike, N de Novembro).
NOMES_LETRAS = {
    "A": "Alfa", "B": "Bravo", "C": "Charlie", "D": "Delta", "E": "Eco",
    "F": "Foxtrot", "G": "Golfe", "H": "Hotel", "I": "Índia", "J": "Juliet",
    "K": "Quilo", "L": "Lima", "M": "Mike", "N": "Novembro", "O": "Oscar",
    "P": "Papa", "Q": "Quebec", "R": "Romeu", "S": "Sierra", "T": "Tango",
    "U": "Uniforme", "V": "Vitória", "W": "Whisky", "X": "Raio-X",
    "Y": "Yankee", "Z": "Zulu",
}


def soletrar(codigo):
    partes = []
    for c in codigo.upper():
        if c == "-":
            partes.append("traço")
        elif c in NOMES_LETRAS:
            partes.append("%s de %s" % (c, NOMES_LETRAS[c]))
        else:
            partes.append(c)
    return ", ".join(partes)


def mostrar_codigo(fala, codigo, numero=1):
    """O codigo de pareamento num arquivo aberto no Bloco de Notas (o leitor
    de tela le e da para copiar), mais a fala dele caractere por caractere,
    com o nome de cada letra para nao confundir M com N."""
    soletrado = soletrar(codigo)
    texto = (
        "CODIGO DE PAREAMENTO DO WHATSAPP\r\n\r\n%s\r\n\r\n"
        "Soletrando: %s\r\n\r\n"
        "No celular da conta de teste: WhatsApp, Aparelhos conectados, "
        "Conectar um aparelho, Conectar com numero de telefone, e digite o "
        "codigo. Ele vale por pouco tempo. Se digitar errado, o teste gera "
        "um codigo novo sozinho e abre este arquivo de novo (tentativa %d de "
        "%d). Quando o celular aceitar, o teste continua sozinho; pode "
        "fechar este Bloco de Notas.\r\n" % (
            codigo, soletrado, numero, TENTATIVAS_CODIGO))
    try:
        with open(ARQ_CODIGO, "w", encoding="utf-8", newline="") as f:
            f.write(texto)
        subprocess.Popen(["notepad.exe", ARQ_CODIGO])
    except OSError as e:
        log("aviso: nao consegui abrir o Bloco de Notas: %r" % e)
        aviso("Código de pareamento do WhatsApp: %s. Soletrando: %s." % (
            codigo, soletrado), titulo="Código do WhatsApp")
    bipe()
    fala.falar("Código de pareamento, tentativa %d: %s" % (numero, soletrado))
    log("codigo de pareamento mostrado em %s" % ARQ_CODIGO)


def parear(fala):
    """Garante que a conta esta pareada. Devolve True se esta. Se o codigo for
    digitado errado (ou vencer), gera outro sozinho, ate TENTATIVAS_CODIGO."""
    estado = {"pareado": False, "erro": "", "codigo": "", "recusado": False}
    contagem = {"n": 0}

    def ao_linha(origem, linha):
        log("   [%s] %s" % (origem, linha))
        if origem != "go":
            return
        if linha.startswith("PAREADO"):
            estado["pareado"] = True
        elif linha.startswith("CODIGO "):
            contagem["n"] += 1
            estado["codigo"] = linha.split(" ", 1)[1]
            try:
                mostrar_codigo(fala, estado["codigo"], contagem["n"])
            except Exception as e:  # nao deixar a thread morrer calada
                log("ERRO ao mostrar o codigo: %r (codigo: %s)" % (
                    e, estado["codigo"]))
        elif linha.startswith("ERRO"):
            estado["erro"] = linha[5:]
        elif "Failed to handle code pair" in linha:
            estado["recusado"] = True

    telefone = ""
    for tentativa in range(1, TENTATIVAS_CODIGO + 2):
        if tentativa == 2 and not telefone:
            dados = pedir_por_arquivo(
                ARQ_CONFIG, MODELO_CONFIG, telefone_valido,
                "Vou abrir o Bloco de Notas: digite depois de TELEFONE= o "
                "número da conta de teste, com código do país e DDD, só "
                "dígitos. Salve com Control S. Aperte Enter para fechar este "
                "aviso.", timeout=300)
            if dados is None:
                log("ERRO: o telefone nao foi informado a tempo")
                return False
            telefone = so_digitos(dados["TELEFONE"])
        estado.update(pareado=False, erro="", recusado=False)
        args = ["parear"] + (["-telefone", telefone] if telefone else [])
        proc = rodar_go(args, ao_linha)
        limite = time.time() + 300
        while proc.poll() is None and time.time() < limite:
            time.sleep(0.5)
            if estado["recusado"] and not estado["pareado"]:
                # codigo errado: espera um pouco por garantia e troca de codigo
                for _ in range(16):
                    if estado["pareado"] or proc.poll() is not None:
                        break
                    time.sleep(0.5)
                if not estado["pareado"]:
                    proc.kill()
                    break
        if proc.poll() is None:
            proc.kill()
        if estado["pareado"]:
            log("conta pareada")
            return True
        if "precisa de -telefone" in estado["erro"] and not telefone:
            continue
        if tentativa > TENTATIVAS_CODIGO:
            break
        log("codigo nao aceito (digitado errado ou vencido); gerando outro")
        bipe()
        fala.falar("O celular não aceitou o código. Vou gerar um código novo.")
        time.sleep(2)
    log("ERRO no pareamento: %s" % (estado["erro"] or "codigo nao aceito"))
    return False


class Ponte:
    """Troca voz entre o microfone/alto-falante e o programa em Go."""

    def __init__(self, conn):
        import numpy as np
        import sounddevice as sd
        self.np, self.sd, self.conn = np, sd, conn
        self.saida = queue.Queue(maxsize=50)
        self.envio = queue.Queue(maxsize=50)
        self.parar = threading.Event()
        self.c = dict(tx=0, rx=0, rx_nao_silencio=0, mic_pico=0.0,
                      rx_pico=0.0, quedas=0, descartados=0)
        self.t_primeiro_rx = None
        self.t_inicio = time.perf_counter()
        self.fluxos = []

    def _mic(self, indata, frames, tempo, status):
        if status:
            self.c["quedas"] += 1
        dados = bytes(indata)
        pico = float(self.np.abs(self.np.frombuffer(
            dados, dtype=self.np.int16)).max()) / 32768
        self.c["mic_pico"] = max(self.c["mic_pico"], pico)
        try:
            self.envio.put_nowait(dados)
        except queue.Full:
            self.c["descartados"] += 1

    def _alto_falante(self, outdata, frames, tempo, status):
        try:
            dados = self.saida.get_nowait()
        except queue.Empty:
            outdata[:] = bytes(len(outdata))
            if self.t_primeiro_rx is not None:
                self.c["quedas"] += 1
            return
        outdata[:len(dados)] = dados

    def _enviar(self):
        while not self.parar.is_set():
            try:
                dados = self.envio.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.conn.sendall(dados)
                self.c["tx"] += 1
            except OSError:
                return

    def _receber(self):
        buf = b""
        while not self.parar.is_set():
            try:
                parte = self.conn.recv(BYTES_QUADRO * 4)
            except socket.timeout:
                continue
            except OSError:
                return
            if not parte:
                return
            buf += parte
            while len(buf) >= BYTES_QUADRO:
                quadro, buf = buf[:BYTES_QUADRO], buf[BYTES_QUADRO:]
                self.c["rx"] += 1
                pico = float(self.np.abs(self.np.frombuffer(
                    quadro, dtype=self.np.int16)).max()) / 32768
                self.c["rx_pico"] = max(self.c["rx_pico"], pico)
                if pico > 0.02:
                    self.c["rx_nao_silencio"] += 1
                    if self.t_primeiro_rx is None:
                        self.t_primeiro_rx = time.perf_counter()
                try:
                    self.saida.put_nowait(quadro)
                except queue.Full:
                    try:
                        self.saida.get_nowait()
                        self.saida.put_nowait(quadro)
                    except queue.Empty:
                        pass

    def iniciar(self):
        sd = self.sd
        self.conn.settimeout(0.5)
        self.fluxos = [
            sd.RawInputStream(samplerate=TAXA, channels=1, dtype="int16",
                              blocksize=QUADRO, callback=self._mic),
            sd.RawOutputStream(samplerate=TAXA, channels=1, dtype="int16",
                               blocksize=QUADRO,
                               callback=self._alto_falante)]
        for f in self.fluxos:
            f.start()
        for alvo in (self._enviar, self._receber):
            threading.Thread(target=alvo, daemon=True).start()

    def encerrar(self):
        self.parar.set()
        for f in self.fluxos:
            try:
                f.stop()
                f.close()
            except Exception:
                pass
        try:
            self.conn.close()
        except OSError:
            pass


def main():
    fala = Fala(log)
    log("==== TESTE DE CHAMADA DE VOZ DO WHATSAPP (meowcaller) ====")
    log("sistema: %s %s | Python %s" % (
        platform.system(), platform.release(), platform.python_version()))
    try:
        import sounddevice as sd
        log("sounddevice %s" % sd.__version__)
        entrada, saida = sd.query_devices(kind="input"), sd.query_devices(
            kind="output")
        log("microfone padrao: %s" % entrada["name"])
        log("saida padrao: %s" % saida["name"])
    except Exception as e:
        log("ERRO: sem microfone ou saida de som: %r" % e)
        aviso("O teste precisa de um microfone e de uma saída de som no "
              "Windows. Não encontrei os dois.")
        return 2
    if not os.path.isfile(EXE):
        log("ERRO: nao achei %s" % EXE)
        aviso("Não encontrei o programa de chamadas "
              "(10-chamada-whatsapp-meowcaller\\chamadas-teste.exe). Ele "
              "precisa estar na pasta ao lado dos testes.")
        return 2

    if not parear(fala):
        aviso("Não consegui parear a conta de teste. Veja o arquivo de log.",
              bloquear=True)
        return 1

    ligar = perguntar_sim_nao(
        "Quer ligar para alguém agora? Sim: eu ligo para o número que você "
        "indicar. Não: fico esperando uma chamada para a conta de teste. "
        "Use fones de ouvido, para o som da outra pessoa não voltar pelo "
        "microfone. Avise a outra pessoa antes.")
    alvo = ""
    if ligar:
        dados = pedir_por_arquivo(
            ARQ_CONFIG, MODELO_CONFIG,
            lambda d: 10 <= len(so_digitos(d.get("ALVO", ""))) <= 15,
            "Vou abrir o Bloco de Notas: digite depois de ALVO= o número "
            "de quem vai receber a chamada, com código do país e DDD, só "
            "dígitos. Salve com Control S. Aperte Enter para fechar este "
            "aviso.", timeout=300)
        if dados is None:
            log("ERRO: ninguem foi indicado a tempo")
            return 2
        alvo = so_digitos(dados["ALVO"])

    servidor = socket.socket()
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(1)
    servidor.settimeout(1)
    porta = servidor.getsockname()[1]
    marcas = {}
    fim = threading.Event()

    def ao_linha(origem, linha):
        log("   [%s] %s" % (origem, linha))
        if origem != "go":
            return
        palavra = linha.split(" ", 1)[0]
        if palavra in ("CONECTADO", "PRONTO", "MEM", "RECEBIDA", "LIGANDO"):
            marcas.setdefault(palavra, linha)
        if palavra == "RECEBIDA":
            bipe()
            fala.falar("Chamada recebida. Atendendo.")
        elif palavra in ("FIM", "ERRO"):
            marcas.setdefault("FIM", linha)
            fim.set()

    args = ["ligar", "-para", alvo] if ligar else ["ouvir"]
    args += ["-segundos", str(DURACAO_S), "-espera", str(ESPERA_S),
             "-pcm", "127.0.0.1:%d" % porta]
    fala.falar("Conectando ao WhatsApp." if ligar else
               "Esperando uma chamada. Ligue para a conta de teste.")
    if not ligar:
        aviso("Estou esperando uma chamada. Ligue para a conta de teste de "
              "outro celular. Aperte Enter e deixe esta janela de lado; o "
              "teste espera %d segundos." % ESPERA_S)
    t0 = time.perf_counter()
    proc = rodar_go(args, ao_linha)
    conn = None
    ponte = None
    try:
        limite = time.time() + ESPERA_S + 60
        while conn is None and not fim.is_set() and time.time() < limite:
            if proc.poll() is not None:
                break
            try:
                conn, _ = servidor.accept()
            except socket.timeout:
                continue
        if conn is None:
            erro = marcas.get("FIM", "")
            log("ERRO: a chamada nao comecou (%s)" % (erro or "sem motivo"))
            aviso("A chamada não começou. %s\n\nO log tem os detalhes." % (
                erro[5:] if erro.startswith("ERRO ") else
                "Veja o motivo no log."), bloquear=True)
            return 1
        log("chamada iniciada; atendida/aceita apos %.1fs" % (
            time.perf_counter() - t0))
        ponte = Ponte(conn)
        ponte.iniciar()
        bipe()
        fala.falar("Chamada em andamento. Fale e escute. O teste dura %d "
                   "segundos." % DURACAO_S)
        inicio = time.perf_counter()
        while not fim.is_set() and proc.poll() is None:
            time.sleep(5)
            c = ponte.c
            log("   %3.0fs | enviados %d quadros, recebidos %d (com voz %d) "
                "| pico mic %.2f, pico recebido %.2f | quedas %d" % (
                    time.perf_counter() - inicio, c["tx"], c["rx"],
                    c["rx_nao_silencio"], c["mic_pico"], c["rx_pico"],
                    c["quedas"]))
            if time.perf_counter() - inicio > DURACAO_S + 30:
                break
        log("duracao da chamada: %.1fs" % (time.perf_counter() - inicio))
    finally:
        if ponte is not None:
            ponte.encerrar()
        if proc.poll() is None:
            time.sleep(3)
            if proc.poll() is None:
                proc.kill()
        servidor.close()

    if ponte is not None:
        c = ponte.c
        log("---- RESUMO ----")
        for k in ("CONECTADO", "PRONTO", "MEM", "FIM"):
            if k in marcas:
                log("go: %s" % marcas[k])
        log("quadros enviados (microfone): %d (%.1fs)" % (
            c["tx"], c["tx"] * QUADRO / TAXA))
        log("quadros recebidos (alto-falante): %d (%.1fs), com voz: %d" % (
            c["rx"], c["rx"] * QUADRO / TAXA, c["rx_nao_silencio"]))
        log("pico do microfone %.2f | pico do que chegou %.2f | quedas de "
            "som %d | quadros descartados %d" % (
                c["mic_pico"], c["rx_pico"], c["quedas"], c["descartados"]))
        if ponte.t_primeiro_rx:
            log("primeira voz recebida %.1fs depois de abrir a ponte" % (
                ponte.t_primeiro_rx - ponte.t_inicio))
        log("o programa em Go gravou o que chegou em %s\\chamada-*.wav" %
            PASTA_GO)
    ok = perguntar_sim_nao(
        "A chamada terminou. Você ouviu a outra pessoa com clareza e ela "
        "ouviu você? Sim se a voz foi boa nos dois lados.")
    log("RESULTADO PELO OUVIDO: %s" % (
        "voz boa nos dois lados" if ok else "houve problema na voz"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:
        log("ERRO INESPERADO:\n" + traceback.format_exc())
        sys.exit(1)

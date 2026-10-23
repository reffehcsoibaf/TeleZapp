"""Teste: chamada de voz do WhatsApp pelo MESMO cliente do neonize (DLL com o
meowcaller dentro). Uso: python teste_chamada_neonize.py <sessao.db> <numero> [segundos]
"""
import ctypes
import json
import sys
import threading
import time
import wave

import numpy as np
import sounddevice as sd

from neonize.client import NewClient
from neonize.events import ConnectedEv
from neonize._binder import gocode

banco, alvo = sys.argv[1], sys.argv[2]
segundos = int(sys.argv[3]) if len(sys.argv) > 3 else 40

gocode.CallsConfigure.argtypes = [ctypes.c_int]
gocode.CallsNextEvent.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
gocode.CallsNextEvent.restype = ctypes.c_int
gocode.CallDial.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
gocode.CallDial.restype = ctypes.c_int
gocode.CallHangup.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
gocode.CallAnswer.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
gocode.CallReadAudio.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
gocode.CallReadAudio.restype = ctypes.c_int
gocode.CallWriteAudio.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
gocode.CallWriteAudio.restype = ctypes.c_int

t0 = time.time()
def log(m):
    print("%6.1f %s" % (time.time() - t0, m), flush=True)

gocode.CallsConfigure(1)
cli = NewClient(banco)
uid = cli.uuid
conectado = threading.Event()

@cli.event(ConnectedEv)
def _(c, e):
    log("CONECTADO")
    conectado.set()

threading.Thread(target=cli.connect, daemon=True).start()

estado = {"call": None, "fim": False, "pronta": False, "env": 0, "rec": 0, "voz": 0}
wav = wave.open("chamada-neonize.wav", "wb")
wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)

def eventos():
    buf = ctypes.create_string_buffer(4096)
    while not estado["fim"]:
        n = gocode.CallsNextEvent(uid, buf, 4096, 500)
        if n > 0:
            ev = json.loads(buf.value.decode())
            log("EVENTO %s" % ev)
            if ev["ev"] == "ready":
                estado["pronta"] = True
            if ev["ev"] == "end":
                estado["fim"] = True
        elif n < 0:
            time.sleep(0.5)

def microfone():
    with sd.RawInputStream(samplerate=16000, channels=1, dtype="int16", blocksize=960) as s:
        while not estado["fim"]:
            dados, _ = s.read(960)
            if estado["call"] and estado["pronta"]:
                if gocode.CallWriteAudio(uid, estado["call"], bytes(dados), 1920) == 0:
                    estado["env"] += 1

def alto_falante():
    buf = ctypes.create_string_buffer(1920)
    with sd.RawOutputStream(samplerate=16000, channels=1, dtype="int16", blocksize=960) as s:
        while not estado["fim"]:
            if not (estado["call"] and estado["pronta"]):
                time.sleep(0.05); continue
            n = gocode.CallReadAudio(uid, estado["call"], buf, 1920, 100)
            if n == 1920:
                b = buf.raw
                estado["rec"] += 1
                if np.abs(np.frombuffer(b, dtype=np.int16)).max() > 300:
                    estado["voz"] += 1
                wav.writeframes(b)
                s.write(b)

for alvo_fn in (eventos, microfone, alto_falante):
    threading.Thread(target=alvo_fn, daemon=True).start()

if not conectado.wait(60):
    log("ERRO: nao conectou"); sys.exit(1)
time.sleep(3)
out = ctypes.create_string_buffer(1024)
n = gocode.CallDial(uid, alvo.encode(), out, 1024)
resp = json.loads(out.value.decode())
log("DIAL %s" % resp)
if "call" not in resp:
    sys.exit(1)
estado["call"] = resp["call"].encode()

limite = time.time() + 45 + segundos
fala_ate = None
while not estado["fim"] and time.time() < limite:
    time.sleep(1)
    if estado["pronta"] and fala_ate is None:
        fala_ate = time.time() + segundos
        log("PRONTA: fale agora (%d s)" % segundos)
    if fala_ate and time.time() > fala_ate:
        log("desligando")
        gocode.CallHangup(uid, estado["call"])
        fala_ate = time.time() + 999
    if int(time.time()) % 5 == 0:
        log("quadros: enviados %d recebidos %d (com voz %d)" % (estado["env"], estado["rec"], estado["voz"]))
time.sleep(2)
estado["fim"] = True
wav.close()
log("RESUMO enviados=%d recebidos=%d com_voz=%d" % (estado["env"], estado["rec"], estado["voz"]))

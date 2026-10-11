# -*- coding: utf-8 -*-
"""Programa de teste de empacotamento do TeleZapp.

Roda como script comum e, depois, empacotado pelo PyInstaller. Com o argumento
--autoteste <arquivo-de-log>, carrega cada componente que o app novo vai usar,
registra o resultado e sai com o numero de falhas (0 = tudo certo).

Componentes: wxPython (abre uma janela por instantes), neonize (WhatsApp,
inclui a DLL em Go), libmagic, Pillow, Telethon (Telegram), hachoir e a fala
pelo NVDA. Nao conecta em nenhuma conta nem usa a internet.
"""
import os
import platform
import shutil
import sys
import tempfile
import time
import traceback

T0 = time.perf_counter()
LOG = None
FALHAS = []


def log(msg):
    linha = time.strftime("%H:%M:%S") + " " + msg
    print(linha, flush=True)
    if LOG:
        try:
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(linha + "\n")
        except OSError as e:
            print("(nao consegui gravar no log: %r)" % e, flush=True)


def passo(nome):
    """Decorador: executa o passo, mede o tempo e registra OK ou FALHOU."""
    def deco(funcao):
        t = time.perf_counter()
        try:
            detalhe = funcao()
            log("OK     %-28s %.2fs%s" % (
                nome, time.perf_counter() - t,
                (" | " + str(detalhe)) if detalhe else ""))
        except Exception:
            FALHAS.append(nome)
            log("FALHOU %-28s %.2fs\n%s" % (
                nome, time.perf_counter() - t, traceback.format_exc()))
        return funcao
    return deco


def autoteste():
    congelado = bool(getattr(sys, "frozen", False))
    log("modo: %s" % ("EXECUTAVEL EMPACOTADO" if congelado else "script"))
    log("python %s em %s" % (sys.version.split()[0], platform.platform()))
    log("executavel: %s" % os.path.basename(sys.executable))
    if congelado:
        log("pasta de recursos: %s" % getattr(sys, "_MEIPASS", "?"))
    pasta_tmp = tempfile.mkdtemp(prefix="telezapp-empac-")

    @passo("wxPython (abre uma janela)")
    def _wx():
        import wx
        app = wx.App(False)
        janela = wx.Frame(None, title="Teste de empacotamento")
        janela.Show()
        wx.CallLater(600, janela.Close)
        app.MainLoop()
        return "wx " + wx.version()

    @passo("neonize + DLL em Go")
    def _neonize():
        from neonize.client import NewClient
        import neonize.events as ev
        cliente = NewClient(os.path.join(pasta_tmp, "teste.db"))
        eventos = len([n for n in dir(ev) if n.endswith("Ev")])
        return "cliente %s criado, %d eventos" % (
            type(cliente).__name__, eventos)

    @passo("protobuf do neonize")
    def _proto():
        from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
            Message, AudioMessage)
        m = Message(audioMessage=AudioMessage(seconds=2, PTT=True))
        return "serializacao %d bytes" % len(m.SerializeToString())

    @passo("libmagic (tipo de arquivo)")
    def _magic():
        import magic
        tipo = magic.from_buffer(b"%PDF-1.4\n%teste\n", mime=True)
        return "PDF reconhecido como " + tipo

    @passo("Pillow (imagens)")
    def _pillow():
        from PIL import Image
        imagem = Image.new("RGB", (32, 32), (10, 120, 200))
        caminho = os.path.join(pasta_tmp, "t.jpg")
        imagem.save(caminho, "JPEG")
        return "JPEG de %d bytes" % os.path.getsize(caminho)

    @passo("Telethon (Telegram)")
    def _telethon():
        import asyncio
        from telethon import TelegramClient, __version__
        from telethon.sessions import StringSession

        async def criar():
            TelegramClient(StringSession(), 12345, "a" * 32)
        asyncio.run(criar())
        return "telethon " + __version__

    @passo("amostras embutidas")
    def _amostras():
        import amostras
        arquivos = amostras.gerar(os.path.join(pasta_tmp, "amostras"))
        return "%d arquivos" % len(arquivos)

    @passo("hachoir (duracao de video)")
    def _hachoir():
        import amostras
        from hachoir.metadata import extractMetadata
        from hachoir.parser import createParser
        caminho = amostras.gerar(os.path.join(pasta_tmp, "h"))["video"]
        parser = createParser(caminho)
        with parser:
            md = extractMetadata(parser)
        return "duracao %.1fs" % md.get("duration").total_seconds()

    @passo("fala pelo NVDA")
    def _fala():
        from fala import Fala
        f = Fala(log)
        if f.lib is None:
            raise RuntimeError("DLL de fala nao carregou: " + f.motivo)
        if not f.nvda_ativo():
            return "DLL carregada, mas o NVDA nao esta aberto"
        ok = f.falar("Teste do executável empacotado do TeleZapp.")
        return "DLL carregada, fala %s" % ("OK" if ok else "falhou")

    shutil.rmtree(pasta_tmp, ignore_errors=True)
    total = time.perf_counter() - T0
    log("tempo total do autoteste: %.2fs" % total)
    if FALHAS:
        log("RESULTADO: %d componente(s) com falha: %s" % (
            len(FALHAS), ", ".join(FALHAS)))
    else:
        log("RESULTADO: todos os componentes funcionaram")
    return len(FALHAS)


def main():
    global LOG
    args = sys.argv[1:]
    if args and args[0] == "--autoteste":
        if len(args) > 1:
            LOG = args[1]
        return autoteste()
    print("Uso: app_empacotamento --autoteste <arquivo-de-log>")
    return 2


if __name__ == "__main__":
    sys.exit(main())

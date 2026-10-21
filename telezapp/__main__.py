# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Ponto de entrada: python -m telezapp (ou pythonw, sem terminal).

Qualquer erro grave vai para o log e aparece numa caixa de mensagem do
Windows, porque o app roda sem janela de terminal.
"""
import logging
import os
import sys
import traceback


_ARQUIVO_FALHA = None      # mantido aberto para o faulthandler


def caixa_de_erro(texto):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, texto, "TeleZapp", 0x10)
    except Exception:
        print(texto, file=sys.stderr)


def main():
    # Sem terminal (pythonw), stdout e stderr nao existem: bibliotecas que
    # escrevem neles nao podem falhar por isso.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if "--desinstalar" in sys.argv[1:]:
        from telezapp.interface.instalacao import desinstalar_pelo_aplicativo
        return desinstalar_pelo_aplicativo()
    from telezapp import NOME, VERSAO, config
    arquivo_log = config.configurar_registro()
    log = logging.getLogger("telezapp")
    log.info("%s versão %s iniciado, código em %s", NOME, VERSAO,
             os.path.dirname(os.path.abspath(__file__)))
    # Queda dentro de uma biblioteca nativa (sem erro do Python): grava em
    # logs\falha-nativa.log em que ponto do codigo cada thread estava.
    try:
        import faulthandler
        global _ARQUIVO_FALHA
        _ARQUIVO_FALHA = open(
            os.path.join(os.path.dirname(arquivo_log), "falha-nativa.log"),
            "a", encoding="utf-8")
        _ARQUIVO_FALHA.write("---- %s iniciado ----\n" % VERSAO)
        _ARQUIVO_FALHA.flush()
        faulthandler.enable(file=_ARQUIVO_FALHA, all_threads=True)
        # sem janela de terminal o stderr do processo vai para o nada: o que
        # as DLLs (a do WhatsApp, em Go) escrevem ao cair fica neste arquivo
        os.dup2(_ARQUIVO_FALHA.fileno(), 2)
    except Exception:
        log.exception("não foi possível ativar o registro de falhas nativas")
    # a marca some no fim normal; se ainda existir, a vez anterior caiu
    marca = os.path.join(os.path.dirname(arquivo_log), "sessao-aberta")
    try:
        if os.path.exists(marca):
            log.warning("a vez anterior terminou sem fechar normalmente "
                        "(queda do programa ou do Windows); veja "
                        "falha-nativa.log")
        with open(marca, "w") as f:
            f.write(str(os.getpid()))
    except OSError:
        marca = None

    def erro_nao_tratado(tipo, valor, tb):
        log.error("ERRO NÃO TRATADO:\n%s",
                  "".join(traceback.format_exception(tipo, valor, tb)))
    sys.excepthook = erro_nao_tratado

    try:
        import wx
        from telezapp.armazenamento.banco import Banco
        from telezapp.interface.janela import Janela
        from telezapp.nucleo.contas import Contas
        from telezapp.nucleo.eventos import Barramento
        from telezapp.nucleo.midias import GerenteMidias
    except Exception:
        log.error("falha ao carregar os componentes:\n%s",
                  traceback.format_exc())
        caixa_de_erro("O %s não conseguiu carregar os componentes. Rode o "
                      "iniciar-telezapp.bat de novo. Detalhes no log:\n%s"
                      % (NOME, arquivo_log))
        return 1

    app = wx.App(False)
    from telezapp.nucleo import atualizador, instalacao
    programa = instalacao.pasta_do_programa()
    if programa:
        atualizador.limpar_restos(programa)     # sobras de uma atualizacao
        from telezapp.interface.instalacao import mostrar_boas_vindas
        if mostrar_boas_vindas() != "continuar":
            return 0
    unico = wx.SingleInstanceChecker("TeleZapp-" + os.environ.get(
        "USERNAME", ""), config.pasta())
    if unico.IsAnotherRunning():
        wx.MessageBox("O %s já está aberto." % NOME, NOME,
                      wx.OK | wx.ICON_INFORMATION)
        return 0
    config.limpar_temporarios()   # sobras de uma abertura anterior
    try:
        from telezapp.nucleo import backup
        trocadas = backup.aplicar_pendente(config.pasta_dados())
        if trocadas:
            log.info("backup restaurado: %s", ", ".join(trocadas))
    except Exception:
        log.error("falha ao restaurar o backup:\n%s", traceback.format_exc())
        caixa_de_erro("O %s não conseguiu terminar de restaurar o backup. "
                      "O que havia antes está na pasta antes-da-restauracao, "
                      "dentro da pasta de dados. Detalhes no log:\n%s"
                      % (NOME, arquivo_log))

    cfg = config.Config()
    banco = Banco(os.path.join(config.pasta(), "telezapp.db"))
    barramento = Barramento(wx.CallAfter)
    janela = Janela(cfg, banco, barramento)
    janela.contas = Contas(cfg, banco, barramento, janela.pedir,
                           janela.obter_credenciais_telegram)
    janela.midias = GerenteMidias(cfg, banco, barramento,
                                  janela.contas.provedor)
    janela.Show()
    wx.CallAfter(janela.comecar)
    app.MainLoop()
    janela.midias.parar()
    banco.fechar()
    config.limpar_temporarios()
    log.info("encerrado normalmente")
    if marca:
        try:
            os.remove(marca)
        except OSError:
            pass
    # Garante o fim do processo mesmo se alguma biblioteca deixar uma
    # thread presa (tudo ja foi gravado e fechado acima).
    logging.shutdown()
    os._exit(0)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        caixa_de_erro("Erro ao iniciar o TeleZapp:\n" + traceback.format_exc())
        sys.exit(1)

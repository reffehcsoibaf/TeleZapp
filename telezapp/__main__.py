# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Ponto de entrada: python -m telezapp (ou pythonw, sem terminal).

Qualquer erro grave vai para o log e aparece numa caixa de mensagem do
Windows, porque o app roda sem janela de terminal.
"""
import logging
import os
import sys
import threading
import time
import traceback


_ARQUIVO_FALHA = None      # mantido aberto para o faulthandler
_INICIO = time.monotonic()  # as etapas da abertura contam a partir daqui


def etapa(log, nome):
    """Uma linha no log com quanto tempo a abertura levou ate aqui: mostra
    onde ela demora (antivirus lendo as DLLs, disco, rede)."""
    log.info("abertura: %s (%.1f s desde o início)", nome,
             time.monotonic() - _INICIO)


def tempo_ligado():
    """Segundos desde que o Windows foi ligado (None fora do Windows)."""
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.GetTickCount64.restype = ctypes.c_uint64
        return k.GetTickCount64() / 1000.0
    except Exception:
        return None


def escrever_marca(marca):
    """A marca de sessao aberta guarda o numero do processo e a ultima hora
    em que o programa estava vivo: se a vez seguinte achar a marca, sabe
    quando a anterior parou de dar sinal."""
    with open(marca, "w") as f:
        f.write("%d\n%d\n" % (os.getpid(), time.time()))


def _manter_marca(marca):
    while True:
        time.sleep(30)
        try:
            escrever_marca(marca)
        except OSError:
            pass


def descrever_marca(marca):
    """O que a marca da vez anterior conta: quando ela deu o ultimo sinal e
    se o Windows foi religado desde entao (quando o tempo ligado e menor que
    o intervalo, houve reinicio ou desligamento no meio)."""
    try:
        with open(marca) as f:
            partes = f.read().split()
        ultima = float(partes[1])
    except (OSError, ValueError, IndexError):
        return "A marca da vez anterior não traz a hora do último sinal."
    agora = time.time()
    intervalo = max(0.0, agora - ultima)
    texto = "O último sinal da vez anterior foi às %s (há %.0f min)." % (
        time.strftime("%H:%M:%S", time.localtime(ultima)), intervalo / 60)
    ligado = tempo_ligado()
    if ligado is not None:
        texto += " O Windows está ligado há %.0f min%s." % (
            ligado / 60, "; foi religado depois desse sinal"
            if ligado < intervalo else "; continuou ligado desde então")
    return texto


def descrever_ambiente(log):
    try:
        import platform
        from telezapp import config
        ligado = tempo_ligado()
        log.info("ambiente: %s, Python %s, %s, dados em %s, argumentos %s, "
                 "Windows ligado há %s", platform.platform(),
                 platform.python_version(),
                 "empacotado" if getattr(sys, "frozen", False) else "código",
                 config.pasta_dados(), sys.argv[1:],
                 "%.0f min" % (ligado / 60) if ligado is not None
                 else "? min")
    except Exception:
        log.exception("não consegui descrever o ambiente")


def caixa_de_erro(texto):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, texto, "TeleZapp", 0x10)
    except Exception:
        print(texto, file=sys.stderr)


def _vigiar_aviso(sinal, janela, instancia):
    """Espera uma segunda abertura pedir que a janela apareca."""
    import wx
    while True:
        if instancia.esperar(sinal, 500):
            wx.CallAfter(janela._mostrar_da_bandeja)
        if getattr(janela, "_saindo", False):
            return


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
                        "falha-nativa.log. %s", descrever_marca(marca))
        escrever_marca(marca)
        threading.Thread(target=_manter_marca, args=(marca,), daemon=True,
                         name="marca-de-sessao").start()
    except OSError:
        marca = None

    def erro_nao_tratado(tipo, valor, tb):
        log.error("ERRO NÃO TRATADO:\n%s",
                  "".join(traceback.format_exception(tipo, valor, tb)))
    sys.excepthook = erro_nao_tratado

    def erro_em_thread(args):
        if args.exc_type is SystemExit:
            return
        log.error("ERRO NÃO TRATADO na thread %s:\n%s",
                  getattr(args.thread, "name", "?"), "".join(
                      traceback.format_exception(
                          args.exc_type, args.exc_value, args.exc_traceback)))
    threading.excepthook = erro_em_thread
    descrever_ambiente(log)

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

    etapa(log, "componentes carregados")
    app = wx.App(False)
    etapa(log, "aplicativo wx criado")
    from telezapp.nucleo import atualizador, instalacao
    programa = instalacao.pasta_do_programa()
    if programa:
        atualizador.limpar_restos(programa)     # sobras de uma atualizacao
        from telezapp.interface.instalacao import mostrar_boas_vindas
        if mostrar_boas_vindas() != "continuar":
            log.info("abertura: a tela de boas-vindas não foi seguida; "
                     "saindo")
            return 0
    unico = wx.SingleInstanceChecker("TeleZapp-" + os.environ.get(
        "USERNAME", ""), config.pasta())
    if unico.IsAnotherRunning():
        # a outra abertura pode estar escondida na bandeja: pede a ela que
        # mostre a janela, em vez de dizer que ja esta aberto
        from telezapp.nucleo import instancia
        avisou = instancia.acionar()
        log.info("abertura: já há outro TeleZapp aberto; %s",
                 "pedi a ele que mostre a janela" if avisou
                 else "não consegui avisá-lo")
        if not avisou:
            wx.MessageBox("O %s já está aberto." % NOME, NOME,
                          wx.OK | wx.ICON_INFORMATION)
        return 0
    from telezapp.nucleo import instancia
    sinal = instancia.criar_sinal()
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

    try:
        cfg = config.Config()
        banco = Banco(os.path.join(config.pasta(), "telezapp.db"))
        etapa(log, "banco aberto")
        barramento = Barramento(wx.CallAfter)
        janela = Janela(cfg, banco, barramento)
        etapa(log, "janela criada")
        janela.contas = Contas(cfg, banco, barramento, janela.pedir,
                               janela.obter_credenciais_telegram)
        janela.midias = GerenteMidias(cfg, banco, barramento,
                                      janela.contas.provedor)
    except Exception:
        log.error("falha ao montar a janela:\n%s", traceback.format_exc())
        caixa_de_erro("O %s não conseguiu abrir a janela. Detalhes no log:"
                      "\n%s" % (NOME, arquivo_log))
        return 1

    def sessao_do_windows(evt):
        log.info("o Windows está encerrando a sessão do usuário "
                 "(desligar, reiniciar ou sair)")
        evt.Skip()
    app.Bind(wx.EVT_QUERY_END_SESSION, sessao_do_windows)
    app.Bind(wx.EVT_END_SESSION, sessao_do_windows)
    # aberto pelo Windows ao entrar na conta (--segundo-plano): com a opcao
    # de segundo plano ligada, abre minimizada na barra de tarefas
    minimizada = ("--segundo-plano" in sys.argv[1:]
                  and bool(cfg.get("segundo_plano")))
    if minimizada:
        janela.Iconize(True)
    janela.Show()
    etapa(log, "janela mostrada")
    if cfg.get("iniciar_com_windows"):
        from telezapp.nucleo import inicializacao
        inicializacao.definir(True)      # mantem o caminho em dia
    if sinal:
        import threading

        threading.Thread(target=_vigiar_aviso,
                         args=(sinal, janela, instancia),
                         daemon=True, name="aviso-de-abertura").start()
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

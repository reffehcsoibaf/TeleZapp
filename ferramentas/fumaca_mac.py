# SPDX-License-Identifier: GPL-3.0-or-later
"""Teste de fumaca no Mac: abre o TeleZapp de verdade (wx real, janela real),
espera a abertura, tira uma foto da tela, confere o log e fecha.

Roda no GitHub Actions (macOS) e serve a quem tem um Mac para ver se o
aplicativo abre. Nao precisa de conta: a pasta de dados e temporaria.

    python ferramentas/fumaca_mac.py [--saida PASTA] [--espera 12]

Sai com 0 se abriu sem erro; 1 se o log tem erro; 2 se nao abriu.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import threading
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default=os.path.join(RAIZ, "fumaca-saida"))
    ap.add_argument("--espera", type=float, default=12.0)
    args = ap.parse_args()
    os.makedirs(args.saida, exist_ok=True)
    dados = tempfile.mkdtemp(prefix="telezapp-fumaca-")
    os.environ["TELEZAPP_DADOS"] = dados
    relatorio = []

    def anotar(texto):
        print(texto, flush=True)
        relatorio.append(texto)

    import wx
    mainloop_original = wx.App.MainLoop

    def mainloop_com_fim(self):
        def verificar():
            # o que so a thread principal pode conferir
            try:
                from telezapp.acessibilidade import fala
                f = fala.Fala()
                anotar("VoiceOver ligado: %s" % f._voiceover())
                f._anunciar_no_voiceover("Teste de fumaça do TeleZapp", True)
                anotar("anúncio ao VoiceOver (thread principal): ok")
            except Exception as e:
                anotar("anúncio ao VoiceOver (thread principal): FALHOU %r"
                       % e)

            def de_fora():
                try:
                    from PyObjCTools import AppHelper
                    from telezapp.acessibilidade import fala
                    AppHelper.callAfter(fala.Fala._anunciar_no_voiceover,
                                        "Teste de outra thread", False)
                    anotar("anúncio ao VoiceOver (outra thread): ok")
                except Exception as e:
                    anotar("anúncio ao VoiceOver (outra thread): FALHOU %r"
                           % e)
            threading.Thread(target=de_fora).start()
            try:
                from telezapp.nucleo import segredo, plataforma
                segredo.esquecer_chave_em_memoria()
                bloco = segredo.cifrar(b"segredo de teste")
                anotar("Chaveiro: cifrar %s, decifrar %s" % (
                    "ok" if bloco else "FALHOU",
                    "ok" if segredo.decifrar(bloco) == b"segredo de teste"
                    else "FALHOU"))
                anotar("sistema: %s" % plataforma.nome_do_sistema())
            except Exception as e:
                anotar("Chaveiro: FALHOU %r" % e)
            try:
                from telezapp.nucleo import ortografia
                c = ortografia.Corretor("pt-BR")
                erros = c.verificar("Eu gosto de casaa e de livro")                     if c.disponivel else []
                anotar("corretor: disponível %s, erros achados %s, "
                       "sugestões %s" % (c.disponivel,
                                         [e.palavra for e in erros],
                                         c.sugerir("casaa") if erros else []))
            except Exception as e:
                anotar("corretor: FALHOU %r" % e)
            try:
                from telezapp.midia import video
                anotar("telas: %s" % [n for n, _ in video.listar_telas()])
            except Exception as e:
                anotar("telas: FALHOU %r" % e)

        def foto():
            alvo = os.path.join(args.saida, "janela.png")
            r = subprocess.run(["screencapture", "-x", alvo])
            anotar("foto da tela: %s" % ("ok" if r.returncode == 0
                                         else "FALHOU"))
            titulos = [(type(w).__name__, w.GetTitle()) for w in
                       wx.GetTopLevelWindows()]
            anotar("janelas abertas: %s" % titulos)

        def fechar():
            for w in list(wx.GetTopLevelWindows()):
                try:
                    if isinstance(w, wx.Dialog) and w.IsModal():
                        w.EndModal(wx.ID_CANCEL)
                except Exception:
                    pass
            wx.CallLater(800, self.ExitMainLoop)

        wx.CallLater(int(args.espera * 1000) - 3000, verificar)
        wx.CallLater(int(args.espera * 1000) - 1000, foto)
        wx.CallLater(int(args.espera * 1000), fechar)
        return mainloop_original(self)

    wx.App.MainLoop = mainloop_com_fim
    codigo = 2
    try:
        from telezapp import __main__ as principal
        # o main termina com os._exit: guarda o relatorio antes
        saida_final = os.path.join(args.saida, "resultado.txt")
        original_terminar = principal.terminar_ja

        def terminar(codigo_):
            _gravar_resultado(saida_final, relatorio, dados, args.saida,
                              codigo_)
            original_terminar(codigo_)
        principal.terminar_ja = terminar
        sys.argv = [sys.argv[0]]
        codigo = principal.main()
    finally:
        _gravar_resultado(os.path.join(args.saida, "resultado.txt"),
                          relatorio, dados, args.saida, codigo)
    return codigo


def _gravar_resultado(caminho, relatorio, dados, saida, codigo):
    log = os.path.join(dados, "logs", "telezapp.log")
    texto = ""
    erros = []
    if os.path.isfile(log):
        with open(log, encoding="utf-8", errors="replace") as f:
            texto = f.read()
        erros = [l for l in texto.splitlines()
                 if " ERROR " in l or "Traceback" in l or " WARNING " in l]
        with open(os.path.join(saida, "telezapp.log"), "w",
                  encoding="utf-8") as f:
            f.write(texto)
    abriu = "janela mostrada" in texto
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("abriu a janela: %s\n" % ("sim" if abriu else "NÃO"))
        f.write("código de saída: %s\n" % codigo)
        f.write("\n".join(relatorio) + "\n")
        f.write("\nlinhas de aviso/erro do log (%d):\n" % len(erros))
        f.write("\n".join(erros) + "\n")


if __name__ == "__main__":
    sys.exit(main())

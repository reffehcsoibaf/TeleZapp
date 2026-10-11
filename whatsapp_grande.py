# -*- coding: utf-8 -*-
"""Teste de arquivos grandes no WhatsApp (neonize).

Uso (chamado pelo 6-teste-arquivos-grandes-whatsapp.bat):
  python whatsapp_grande.py testar <arquivo-de-log>

Fluxo: conecta (reaproveitando a sessao salva), espera a palavra ping na
conversa com voce mesmo, envia um documento de dados aleatorios, e depois
espera que voce o ENCAMINHE para a mesma conversa para medir o download e
conferir a integridade (tamanho e SHA-256).
Tamanho do arquivo: configuracao-arquivos-grandes.txt (padrao 20 MB).
"""
import hashlib
import os
import platform
import sys
import threading
import time
import traceback

import whatsapp_teste as wt  # usa as mesmas posicoes de argumentos
import arquivos_grandes as ag
from acessivel import aviso, pedir_por_arquivo, sinal

log = wt.log
ESPERA_MAXIMA = 3600


def principal():
    mb = ag.ler_tamanho_mb(log)
    try:
        from neonize.client import NewClient
        import neonize.events as ev
    except Exception:
        log("ERRO ao importar neonize:\n" + traceback.format_exc())
        return 1

    os.makedirs(wt.SESSAO_DIR, exist_ok=True)
    banco = os.path.join(wt.SESSAO_DIR, "teste.db")
    sessao_existe = os.path.isfile(banco) and os.path.getsize(banco) > 0
    log("sessao salva encontrada: %s" % ("sim" if sessao_existe else "nao"))

    conf = pedir_por_arquivo(
        wt.ARQ_CONF, wt.MODELO_CONF, wt.conf_valida,
        "Vou abrir o Bloco de Notas com um arquivo de configuração. "
        "Digite o número do WhatsApp depois do sinal de igual, com código "
        "do país e DDD, só dígitos, e salve com Control S. Se a conta já "
        "foi pareada neste computador, escreva nenhum. Aperte Enter para "
        "fechar este aviso.")
    if conf is None:
        log("ERRO: a configuracao nao foi preenchida a tempo")
        return 1
    valor = conf["NUMERO"].strip().lower()
    telefone = "" if valor == "nenhum" else valor

    client = NewClient(banco)
    est = {"conectado": False, "ping": False, "enviado": False,
           "baixado": False, "avisou": False, "tamanho": 0, "sha": "",
           "t_connect": time.perf_counter()}
    trava = threading.Lock()

    def logado():
        try:
            return bool(client.is_logged_in)
        except Exception:
            return False

    def tentar_pareamento(tentativa):
        if not telefone:
            wt.sair(3, "A conta ainda não está pareada e nenhum número foi "
                       "informado. Rode o teste de novo e informe o número.")
            return False
        try:
            codigo = client.PairPhone(
                telefone, **wt.montar_argumentos(client.PairPhone))
        except Exception:
            log("pareamento, tentativa %d falhou:\n%s" % (
                tentativa, traceback.format_exc()))
            return False
        wt.falar_codigo(codigo)
        log("codigo de pareamento mostrado em caixa de mensagem")
        return True

    def controle():
        espera = 15 if sessao_existe else 4
        for _ in range(espera):
            time.sleep(1)
            if est["conectado"] or logado():
                return
        log("sem sessao ativa apos %ds: pedindo pareamento" % espera)
        for tentativa in range(1, 6):
            if est["conectado"] or logado():
                return
            if tentar_pareamento(tentativa):
                return
            time.sleep(4)
        wt.sair(5, "Não consegui gerar o código de pareamento.")

    def ao_conectar(cli, e):
        est["conectado"] = True
        log("CONECTADO em %.1fs" % (time.perf_counter() - est["t_connect"]))
        if not est["avisou"]:
            est["avisou"] = True
            aviso("Conectado ao WhatsApp. Agora, no celular, abra a conversa "
                  "com você mesmo, chamada Mensagem para você, e envie a "
                  "palavra ping. Eu vou enviar um arquivo de teste de %d "
                  "megabytes. Quando eu avisar que terminei, encaminhe esse "
                  "arquivo para a mesma conversa, para eu medir o download. "
                  "Aperte Enter para fechar este aviso." % mb)

    def teste_envio(cli, destino):
        try:
            caminho = ag.gerar_arquivo("arquivo-grande-whatsapp.bin", mb)
            est["tamanho"] = os.path.getsize(caminho)
            est["sha"] = ag.sha256_arquivo(caminho)
            log("arquivo de teste gerado: %d MB" % mb)
            t0 = time.perf_counter()
            cli.send_document(
                destino, caminho,
                caption="Teste de arquivo grande do TeleZapp",
                filename="arquivo-grande-teste.bin",
                mimetype="application/octet-stream")
            t_envio = time.perf_counter() - t0
            est["t_envio"] = t_envio
            est["enviado"] = True
            log("ENVIO concluido: %s em %s" % (
                ag.velocidade(est["tamanho"], t_envio),
                ag.segundos_txt(t_envio)))
            sinal()
            aviso("Enviei o arquivo de %d megabytes em %d segundos. Agora, "
                  "no celular, encaminhe esse arquivo para a mesma conversa, "
                  "para eu medir o download. Aguardo até trinta minutos. "
                  "Aperte Enter para fechar este aviso." % (
                      mb, round(t_envio)))
        except Exception:
            log("ENVIO FALHOU:\n" + traceback.format_exc())
            ag.limpar()
            wt.sair(5, "O envio do arquivo grande falhou. O log mostra o "
                       "erro.")

    def teste_download(cli, interna):
        try:
            t0 = time.perf_counter()
            dados = cli.download_any(interna)
            t_down = time.perf_counter() - t0
            log("DOWNLOAD concluido: %s em %s (%d bytes)" % (
                ag.velocidade(len(dados), t_down),
                ag.segundos_txt(t_down), len(dados)))
            mesmo_tamanho = len(dados) == est["tamanho"]
            mesmo_hash = hashlib.sha256(dados).hexdigest() == est["sha"]
            log("INTEGRIDADE: tamanho igual=%s, SHA-256 igual=%s" % (
                mesmo_tamanho, mesmo_hash))
            log("RESUMO WhatsApp: arquivo %d MB, envio %s, download %s, "
                "integridade %s" % (
                    mb, ag.velocidade(est["tamanho"], est["t_envio"]),
                    ag.velocidade(len(dados), t_down),
                    "OK" if (mesmo_tamanho and mesmo_hash) else "FALHOU"))
            sinal()
        except Exception:
            log("DOWNLOAD FALHOU:\n" + traceback.format_exc())
        finally:
            ag.limpar()
            wt.sair(0)

    def ao_mensagem(cli, mensagem):
        try:
            origem = mensagem.Info.MessageSource
            interna, _ = wt.desembrulhar(mensagem.Message)
            texto, _ = wt.extrair_texto(interna)
            campos = wt.nomes_campos(interna)
            if texto.strip().lower() == "ping":
                with trava:
                    if est["ping"]:
                        return
                    est["ping"] = True
                log("ping recebido; iniciando o envio do arquivo")
                threading.Thread(target=teste_envio,
                                 args=(cli, origem.Chat), daemon=True).start()
                return
            if "documentMessage" in campos and est["enviado"]:
                declarado = int(getattr(interna.documentMessage,
                                        "fileLength", 0) or 0)
                log("documento recebido: %d bytes declarados" % declarado)
                if declarado >= int(est["tamanho"] * 0.99):
                    with trava:
                        if est["baixado"]:
                            return
                        est["baixado"] = True
                    threading.Thread(target=teste_download,
                                     args=(cli, interna), daemon=True).start()
        except Exception:
            log("ERRO no tratamento da mensagem:\n" + traceback.format_exc())

    def registrar(nome, funcao):
        classe = getattr(ev, nome, None)
        if classe is None:
            return
        try:
            client.event(classe)(funcao)
        except Exception:
            log("erro ao registrar %s:\n%s" % (nome, traceback.format_exc()))

    def so_chegada(nome):
        def f(cli, e):
            log("evento: %s" % nome)
        return f

    registrar("ConnectedEv", ao_conectar)
    registrar("MessageEv", ao_mensagem)
    for nome in ("PairStatusEv", "LoggedOutEv", "DisconnectedEv",
                 "ConnectFailureEv", "StreamReplacedEv", "TemporaryBanEv",
                 "ClientOutdatedEv"):
        registrar(nome, so_chegada(nome))

    threading.Thread(target=controle, daemon=True).start()
    timer = threading.Timer(ESPERA_MAXIMA, lambda: wt.sair(
        2, "O limite de uma hora do teste foi atingido."))
    timer.daemon = True
    timer.start()

    log("conectando ao WhatsApp")
    est["t_connect"] = time.perf_counter()
    try:
        client.connect()
    except Exception:
        log("ERRO em connect():\n" + traceback.format_exc())
        return 1
    return 0


def main():
    log("==== teste de arquivos grandes: WhatsApp ====")
    log("python %s em %s" % (sys.version.split()[0], platform.platform()))
    try:
        return principal()
    except Exception:
        log("ERRO:\n" + traceback.format_exc())
        ag.limpar()
        return 1


if __name__ == "__main__":
    sys.exit(main())

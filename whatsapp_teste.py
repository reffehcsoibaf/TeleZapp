# -*- coding: utf-8 -*-
"""Teste de viabilidade do WhatsApp com neonize (ligacao Python da whatsmeow).

Versao 4 (midia sem ffmpeg). Chamado pelo 2-teste-whatsapp.bat em dois modos:
  inspecionar : so lista versao, eventos e a assinatura de PairPhone
  testar      : pareia por codigo (ou reconecta com a sessao salva), reconhece
                a palavra ping, responde pong e continua observando

Novidades da versao 2:
  - reaproveita a sessao salva (nao pede pareamento de novo)
  - abre mensagens "embrulhadas" (enviadas por outro dispositivo, efemeras)
    antes de extrair o texto
  - registra os NOMES dos campos de cada mensagem (nunca o conteudo)
  - descarta eventos repetidos e testa o download de audio e imagem
  - depois do ping, observa por mais 120 segundos (outras pessoas, grupos)

Novidades da versao 3:
  - depois do ping, envia texto, foto, video, nota de voz e documento de
    amostra para a mesma conversa (o usuario confere no celular)
  - baixa uma vez cada tipo de midia que chegar: imagem, video, audio,
    documento e figurinha
  - registra se ffmpeg e ffprobe estao no PATH (o neonize os usa para video,
    nota de voz e miniaturas)

Novidades da versao 4 (a versao 3 mostrou que, sem ffmpeg/ffprobe, o envio de
video e de nota de voz do neonize falha; o texto, a foto e o documento
funcionam):
  - o video e a nota de voz agora sao montados aqui, sem ffmpeg: a duracao vem
    do hachoir (video) ou da leitura do cabecalho Ogg/Opus (nota de voz), e o
    envio usa o upload e o send_message do proprio neonize
  - o video sai sem miniatura (a miniatura exigia o ffmpeg)

Nao usa o terminal para perguntas nem para mostrar o codigo: o codigo de
pareamento aparece numa caixa de mensagem do Windows (lida pelo leitor de
tela) e o numero e digitado num arquivo aberto no Bloco de Notas.
Nao grava numero de telefone, codigo de pareamento nem texto de mensagens
no log.
"""
import enum
import inspect
import os
import platform
import shutil
import sys
import threading
import time
import traceback

from acessivel import aviso, pedir_por_arquivo
import amostras

BASE = os.path.dirname(os.path.abspath(__file__))
MODO = sys.argv[1] if len(sys.argv) > 1 else "testar"
LOG = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    BASE, "logs", "resultado-teste-whatsapp.log")
SESSAO_DIR = os.path.join(BASE, "sessao-whatsapp")
ARQ_CONF = os.path.join(BASE, "configuracao-whatsapp.txt")
ARQ_CODIGO = os.path.join(BASE, "codigo-pareamento.txt")
AMOSTRAS_DIR = os.path.join(BASE, "amostras-whatsapp")
LIMITE_SEGUNDOS = 3600  # teto de seguranca: o teste termina quando o usuario manda
MAX_DETALHES = 40

EMBRULHOS = ("deviceSentMessage", "ephemeralMessage", "viewOnceMessage",
             "viewOnceMessageV2", "viewOnceMessageV2Extension",
             "documentWithCaptionMessage", "editedMessage")

MODELO_CONF = (
    "# Digite o numero do WhatsApp depois do sinal de igual, com codigo do\n"
    "# pais e DDD, so digitos. Exemplo: NUMERO=5551999999999\n"
    "# Se a conta ja foi pareada neste computador, escreva NUMERO=nenhum\n"
    "# Salve com Control S.\n"
    "NUMERO=\n")

CONT = {"eventos": 0, "duplicados": 0, "de_mim": 0, "de_outros": 0,
        "grupo": 0, "com_texto": 0}


def log(msg):
    linha = time.strftime("%H:%M:%S") + " " + msg
    print(linha, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except OSError:
        pass


def sair(codigo, mensagem=None):
    log("resumo dos eventos de mensagem: " + ", ".join(
        "%s=%d" % (k, v) for k, v in CONT.items()))
    log("saindo com codigo %s" % codigo)
    sys.stdout.flush()
    if mensagem:
        aviso(mensagem, bloquear=True)
    os._exit(codigo)


def conf_valida(d):
    v = d.get("NUMERO", "").strip().lower()
    return v == "nenhum" or (v.isdigit() and len(v) >= 10)


# ----------------------------------------------------------------------
# Leitura de mensagens (funcoes puras, testaveis sem WhatsApp)
# ----------------------------------------------------------------------
def nomes_campos(msg):
    """Nomes dos campos preenchidos de uma mensagem protobuf."""
    try:
        return [f.name for f, _ in msg.ListFields()]
    except Exception:
        return []


def desembrulhar(msg):
    """Abre os envelopes ate chegar na mensagem de verdade.

    Devolve (mensagem_interna, lista_de_envelopes_abertos).
    """
    abertos = []
    for _ in range(6):
        achou = False
        for nome in EMBRULHOS:
            try:
                if msg.HasField(nome):
                    interna = getattr(msg, nome).message
                    abertos.append(nome)
                    msg = interna
                    achou = True
                    break
            except Exception:
                continue
        if not achou:
            break
    return msg, abertos


def extrair_texto(msg):
    """Devolve (texto, de_onde_veio). Texto vazio se nao houver."""
    try:
        if msg.conversation:
            return msg.conversation, "conversation"
        if msg.HasField("extendedTextMessage") and \
                msg.extendedTextMessage.text:
            return msg.extendedTextMessage.text, "extendedTextMessage"
        for nome in ("imageMessage", "videoMessage", "documentMessage"):
            if msg.HasField(nome) and getattr(msg, nome).caption:
                return getattr(msg, nome).caption, nome + ".caption"
    except Exception:
        pass
    return "", ""


def duracao_ogg_opus(dados):
    """Duracao em segundos de um arquivo Ogg/Opus, lendo so o cabecalho."""
    inicio = dados.find(b"OpusHead")
    pre_skip = 0
    if inicio >= 0 and len(dados) >= inicio + 12:
        pre_skip = int.from_bytes(dados[inicio + 10:inicio + 12], "little")
    ultimo = dados.rfind(b"OggS")
    if ultimo < 0 or len(dados) < ultimo + 14:
        raise ValueError("arquivo Ogg invalido")
    granule = int.from_bytes(dados[ultimo + 6:ultimo + 14], "little",
                             signed=True)
    if granule < 0:
        raise ValueError("posicao final do Ogg invalida")
    return max(0.0, (granule - pre_skip) / 48000.0)


def info_video(caminho):
    """(segundos, largura, altura) de um video, usando o hachoir."""
    from hachoir.metadata import extractMetadata
    from hachoir.parser import createParser
    parser = createParser(caminho)
    if not parser:
        raise ValueError("formato de video nao reconhecido")
    with parser:
        md = extractMetadata(parser)
    if md is None:
        raise ValueError("sem metadados no video")
    seg = md.get("duration").total_seconds() if md.has("duration") else 0
    larg = md.get("width") if md.has("width") else 0
    alt = md.get("height") if md.has("height") else 0
    return int(round(seg)), int(larg or 0), int(alt or 0)


def montar_audio(upload, segundos, voz):
    """Mensagem de audio (ou nota de voz) a partir de um upload do neonize."""
    from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
        AudioMessage, Message)
    return Message(audioMessage=AudioMessage(
        URL=upload.url,
        seconds=segundos,
        directPath=upload.DirectPath,
        fileEncSHA256=upload.FileEncSHA256,
        fileLength=upload.FileLength,
        fileSHA256=upload.FileSHA256,
        mediaKey=upload.MediaKey,
        mimetype="audio/ogg; codecs=opus" if voz else "audio/mpeg",
        PTT=voz))


def montar_video(upload, segundos, largura, altura, legenda):
    """Mensagem de video (sem miniatura) a partir de um upload do neonize."""
    from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
        Message, VideoMessage)
    return Message(videoMessage=VideoMessage(
        URL=upload.url,
        caption=legenda,
        seconds=segundos,
        width=largura,
        height=altura,
        directPath=upload.DirectPath,
        fileEncSHA256=upload.FileEncSHA256,
        fileLength=upload.FileLength,
        fileSHA256=upload.FileSHA256,
        mediaKey=upload.MediaKey,
        mimetype="video/mp4"))


def enviar_video_sem_ffmpeg(cli, destino, caminho, legenda):
    segundos, largura, altura = info_video(caminho)
    log("video: %ds, %dx%d (lido pelo hachoir, sem ffmpeg)" % (
        segundos, largura, altura))
    with open(caminho, "rb") as f:
        dados = f.read()
    t0 = time.perf_counter()
    upload = cli.upload(dados)
    log("upload do video: %d bytes em %.2fs" % (
        len(dados), time.perf_counter() - t0))
    return cli.send_message(
        destino, montar_video(upload, segundos, largura, altura, legenda))


def enviar_voz_sem_ffmpeg(cli, destino, caminho):
    with open(caminho, "rb") as f:
        dados = f.read()
    segundos = int(round(duracao_ogg_opus(dados)))
    log("nota de voz: %ds (lido do cabecalho Ogg/Opus, sem ffmpeg)" % segundos)
    t0 = time.perf_counter()
    upload = cli.upload(dados)
    log("upload da nota de voz: %d bytes em %.2fs" % (
        len(dados), time.perf_counter() - t0))
    return cli.send_message(destino, montar_audio(upload, segundos, True))


# ----------------------------------------------------------------------
# Modo inspecionar
# ----------------------------------------------------------------------
def inspecionar():
    t = time.perf_counter()
    try:
        import neonize
        from neonize.client import NewClient
        import neonize.events as ev
    except Exception:
        log("ERRO ao importar neonize:\n" + traceback.format_exc())
        return 1
    log("neonize importado em %.2fs" % (time.perf_counter() - t))

    try:
        from importlib.metadata import version
        log("versao do neonize: " + version("neonize"))
    except Exception as e:
        log("nao consegui ler a versao: %r" % e)

    pasta = os.path.dirname(neonize.__file__)
    total = 0
    for raiz, _, arquivos in os.walk(pasta):
        for nome in arquivos:
            try:
                total += os.path.getsize(os.path.join(raiz, nome))
            except OSError:
                pass
    log("tamanho da pasta do pacote: %.1f MB" % (total / 1048576))

    eventos = sorted(n for n in dir(ev) if n.endswith("Ev"))
    log("eventos disponiveis: " + ", ".join(eventos))

    chaves = ("pair", "connect", "send_message", "reply", "logout",
              "download", "logged")
    metodos = sorted(n for n in dir(NewClient)
                     if any(k in n.lower() for k in chaves))
    log("metodos relevantes do cliente: " + ", ".join(metodos))
    return 0


# ----------------------------------------------------------------------
# Modo testar
# ----------------------------------------------------------------------
def escolher_enum(tipo):
    membros = list(tipo)
    for m in membros:
        if "CHROME" in m.name.upper():
            return m
    return membros[0]


def montar_argumentos(fn):
    """Preenche os parametros obrigatorios de PairPhone alem do telefone."""
    extras = {}
    try:
        params = list(inspect.signature(fn).parameters.values())
    except Exception as e:
        log("nao consegui ler a assinatura de PairPhone: %r" % e)
        return extras
    for p in params[1:]:
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        if p.default is not inspect.Parameter.empty:
            continue
        nome = p.name.lower()
        ann = p.annotation
        if ann is bool or "push" in nome or "notif" in nome:
            extras[p.name] = True
        elif inspect.isclass(ann) and issubclass(ann, enum.Enum):
            extras[p.name] = escolher_enum(ann)
        elif ann is str or "name" in nome or "display" in nome:
            extras[p.name] = "Chrome (Windows)"
        else:
            log("parametro obrigatorio sem valor conhecido: %s" % p.name)
            extras[p.name] = None
    return extras


def falar_codigo(codigo):
    """Mostra o codigo numa caixa de mensagem, caractere por caractere."""
    texto = str(codigo)
    soletrado = " ".join("traço" if c == "-" else c for c in texto)
    try:
        with open(ARQ_CODIGO, "w", encoding="utf-8") as f:
            f.write(texto + "\n")
    except OSError:
        pass
    aviso("Código de pareamento do WhatsApp: %s.\n\n"
          "Repetindo, caractere por caractere: %s.\n\n"
          "No celular, abra o WhatsApp, vá em Dispositivos conectados ou "
          "Aparelhos conectados, escolha conectar com número de telefone e "
          "digite o código. Ele vale por pouco tempo. O mesmo código está "
          "no arquivo codigo-pareamento.txt, na pasta do teste." % (
              texto, soletrado), titulo="Código do WhatsApp")


def testar():
    estado = {
        "conectado": False,
        "pareado_agora": False,
        "respondido": False,
        "avisou": False,
        "vistos": set(),
        "baixados": set(),
        "detalhes": 0,
        "t_connect": time.perf_counter(),
    }
    trava = threading.Lock()

    t = time.perf_counter()
    try:
        from neonize.client import NewClient
        import neonize.events as ev
    except Exception:
        log("ERRO ao importar neonize:\n" + traceback.format_exc())
        return 1
    log("neonize importado em %.2fs" % (time.perf_counter() - t))

    log("ffmpeg no PATH: %s; ffprobe no PATH: %s" % (
        "sim" if shutil.which("ffmpeg") else "nao",
        "sim" if shutil.which("ffprobe") else "nao"))

    os.makedirs(SESSAO_DIR, exist_ok=True)
    banco = os.path.join(SESSAO_DIR, "teste.db")
    sessao_existe = os.path.isfile(banco) and os.path.getsize(banco) > 0
    log("sessao salva encontrada: %s" % ("sim" if sessao_existe else "nao"))

    conf = pedir_por_arquivo(
        ARQ_CONF, MODELO_CONF, conf_valida,
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
    log("numero informado: %s" % ("sim" if telefone else "nao"))

    try:
        client = NewClient(banco)
    except Exception:
        log("ERRO ao criar o cliente:\n" + traceback.format_exc())
        return 1

    def logado():
        try:
            return bool(client.is_logged_in)
        except Exception:
            return False

    def terminar_depois(segundos, codigo, mensagem):
        timer = threading.Timer(segundos, lambda: sair(codigo, mensagem))
        timer.daemon = True
        timer.start()

    def tentar_pareamento(tentativa):
        """Devolve True se o codigo foi obtido e mostrado."""
        if not telefone:
            log("precisa parear mas nenhum numero foi informado.")
            sair(3, "A conta ainda não está pareada e nenhum número foi "
                    "informado. Rode o teste de novo e informe o número.")
            return False
        fn = getattr(client, "PairPhone", None)
        if fn is None:
            log("PairPhone nao existe no cliente")
            sair(4, "Esta versão do neonize não tem a função de "
                    "pareamento por código.")
            return False
        extras = montar_argumentos(fn)
        try:
            codigo = fn(telefone, **extras)
        except Exception:
            log("pareamento, tentativa %d falhou:\n%s" % (
                tentativa, traceback.format_exc()))
            return False
        estado["pareado_agora"] = True
        falar_codigo(codigo)
        log("codigo de pareamento obtido na tentativa %d e mostrado em "
            "caixa de mensagem" % tentativa)
        return True

    def controle():
        espera = 15 if sessao_existe else 4
        for _ in range(espera):
            time.sleep(1)
            if estado["conectado"] or logado():
                log("sessao ativa sem novo pareamento")
                return
        log("sem sessao ativa apos %ds: pedindo pareamento" % espera)
        for tentativa in range(1, 6):
            if estado["conectado"] or logado():
                return
            if tentar_pareamento(tentativa):
                return
            time.sleep(4)
        sair(5, "Não consegui gerar o código de pareamento. O log mostra "
                "o erro.")

    def ao_conectar(cli, e):
        estado["conectado"] = True
        log("CONECTADO em %.1fs (pareado agora: %s)" % (
            time.perf_counter() - estado["t_connect"],
            estado["pareado_agora"]))
        if not estado["avisou"]:
            estado["avisou"] = True
            aviso("Conectado ao WhatsApp. Agora, no celular, abra a conversa "
                  "com você mesmo, chamada Mensagem para você, e envie a "
                  "palavra ping. Eu respondo e envio de volta um texto, uma "
                  "foto, um vídeo, uma nota de voz e um documento de teste. "
                  "Depois disso, o teste espera o tempo que você precisar, "
                  "sem limite curto, até você mandar encerrar. Aperte Enter "
                  "para fechar este aviso.")

    def ao_qr(cli, e):
        log("evento QR recebido: a conta ainda nao esta pareada")

    def testar_download(cli, interna, campos):
        for campo in ("imageMessage", "videoMessage", "audioMessage",
                      "documentMessage", "stickerMessage"):
            if campo not in campos or campo in estado["baixados"]:
                continue
            estado["baixados"].add(campo)
            sub = getattr(interna, campo)
            declarado = getattr(sub, "fileLength", 0)
            mime = getattr(sub, "mimetype", "") or "-"
            t0 = time.perf_counter()
            try:
                dados = cli.download_any(interna)
                log("download de %s (mime=%s, declarado=%s bytes): %d bytes "
                    "em %.2fs" % (campo, mime, declarado,
                                  len(dados) if dados else 0,
                                  time.perf_counter() - t0))
            except Exception:
                log("download de %s falhou:\n%s" % (
                    campo, traceback.format_exc()))

    def enviar_midias(cli, destino):
        """Envia amostras para a conversa e registra o resultado de cada uma."""
        try:
            caminhos = amostras.gerar(AMOSTRAS_DIR)
        except Exception:
            log("ERRO ao gerar amostras:\n" + traceback.format_exc())
            return
        passos = (
            ("texto", lambda: cli.send_message(
                destino, "Teste do TeleZapp: texto")),
            ("foto", lambda: cli.send_image(
                destino, caminhos["foto"], caption="Teste do TeleZapp: foto")),
            ("video", lambda: enviar_video_sem_ffmpeg(
                cli, destino, caminhos["video"],
                "Teste do TeleZapp: video")),
            ("nota de voz", lambda: enviar_voz_sem_ffmpeg(
                cli, destino, caminhos["voz"])),
            ("documento", lambda: cli.send_document(
                destino, caminhos["documento"],
                caption="Teste do TeleZapp: documento",
                filename="documento-teste.pdf",
                mimetype="application/pdf")),
        )
        for rotulo, enviar in passos:
            t0 = time.perf_counter()
            try:
                enviar()
                log("envio de %s: OK em %.2fs" % (
                    rotulo, time.perf_counter() - t0))
            except Exception:
                log("envio de %s FALHOU:\n%s" % (
                    rotulo, traceback.format_exc()))
        log("envios de amostra terminados; aguardando o usuario encerrar")
        aviso("Terminei de enviar o texto, a foto, o vídeo, a nota de voz e "
              "o documento de teste. Confira no celular se chegaram, se o "
              "vídeo toca, se a nota de voz aparece como áudio de voz e se o "
              "documento abre.\n\n"
              "Agora, na mesma conversa, envie uma foto, um vídeo, um áudio "
              "e um documento. Dica: para não precisar procurar arquivos, "
              "encaminhe para a mesma conversa a foto, o vídeo, a nota de "
              "voz e o documento que eu acabei de enviar. Se quiser, peça a "
              "alguém para escrever para você ou escreva num grupo.\n\n"
              "O teste continua até você terminar. Quando acabar, aperte "
              "Enter nesta caixa para encerrar o teste.",
              titulo="Teste em andamento", bloquear=True)
        log("usuario encerrou o teste")
        sair(0)

    def ao_mensagem(cli, mensagem):
        try:
            info = mensagem.Info
            with trava:
                CONT["eventos"] += 1
                if info.ID in estado["vistos"]:
                    CONT["duplicados"] += 1
                    return
                estado["vistos"].add(info.ID)
                estado["detalhes"] += 1
                detalhar = estado["detalhes"] <= MAX_DETALHES
            origem = info.MessageSource
            minha = bool(origem.IsFromMe)
            grupo = bool(origem.IsGroup)
            CONT["de_mim" if minha else "de_outros"] += 1
            if grupo:
                CONT["grupo"] += 1
            topo = nomes_campos(mensagem.Message)
            interna, abertos = desembrulhar(mensagem.Message)
            campos = nomes_campos(interna)
            texto, via = extrair_texto(interna)
            if texto:
                CONT["com_texto"] += 1
            if detalhar:
                log("mensagem: minha=%s grupo=%s info_tipo=%s info_midia=%s "
                    "topo=%s envelopes=%s internos=%s texto_via=%s "
                    "tamanho_texto=%d" % (
                        minha, grupo, info.Type, info.MediaType,
                        ",".join(topo), ",".join(abertos),
                        ",".join(campos), via or "-", len(texto)))
            testar_download(cli, interna, campos)

            if texto.strip().lower() == "ping":
                with trava:
                    if estado["respondido"]:
                        return
                    estado["respondido"] = True
                t_resp = time.perf_counter()
                cli.reply_message("pong - teste do TeleZapp", mensagem)
                log("ping reconhecido pelo extrator; resposta enviada em "
                    "%.2fs" % (time.perf_counter() - t_resp))
                log("RESULTADO: extracao de texto, recebimento e envio "
                    "funcionaram")
                threading.Thread(
                    target=enviar_midias,
                    args=(cli, origem.Chat), daemon=True).start()
        except Exception:
            log("ERRO no tratamento da mensagem:\n" + traceback.format_exc())

    def registrar(nome, funcao):
        classe = getattr(ev, nome, None)
        if classe is None:
            log("evento %s nao existe nesta versao" % nome)
            return
        try:
            client.event(classe)(funcao)
        except Exception:
            log("erro ao registrar %s:\n%s" % (nome, traceback.format_exc()))

    def so_registrar_chegada(nome):
        def f(cli, e):
            log("evento: %s" % nome)
        return f

    registrar("ConnectedEv", ao_conectar)
    registrar("QREv", ao_qr)
    registrar("MessageEv", ao_mensagem)
    for nome in ("PairStatusEv", "LoggedOutEv", "DisconnectedEv",
                 "ConnectFailureEv", "StreamReplacedEv", "TemporaryBanEv",
                 "ClientOutdatedEv"):
        registrar(nome, so_registrar_chegada(nome))

    threading.Thread(target=controle, daemon=True).start()
    terminar_depois(LIMITE_SEGUNDOS, 2,
                    "O limite de uma hora do teste foi atingido. O log mostra "
                    "até onde o teste foi.")

    log("conectando ao WhatsApp")
    estado["t_connect"] = time.perf_counter()
    try:
        client.connect()
    except Exception:
        log("ERRO em connect():\n" + traceback.format_exc())
        return 1
    log("connect() retornou")
    return 0


def main():
    log("==== teste do WhatsApp (neonize) v4, modo %s ====" % MODO)
    log("python %s em %s" % (sys.version.split()[0], platform.platform()))
    try:
        if MODO == "inspecionar":
            return inspecionar()
        return testar()
    except Exception:
        log("ERRO:\n" + traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())

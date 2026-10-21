# -*- coding: utf-8 -*-
"""Ajudantes para testes sem depender de ler ou digitar no terminal.

- aviso(): caixa de mensagem do Windows (o leitor de tela le sozinho),
  precedida de um bipe.
- pedir_por_arquivo(): abre um arquivo no Bloco de Notas, o usuario preenche
  e salva, e o script detecta sozinho quando o conteudo fica valido.

Uso pela linha de comando (chamado pelos .bat no fim do teste):
  python acessivel.py fim telegram
  python acessivel.py fim whatsapp
"""
import ctypes
import os
import subprocess
import sys
import threading
import time

try:
    import winsound
except ImportError:
    winsound = None

MB_ICONINFORMATION = 0x40
MB_SETFOREGROUND = 0x10000
MB_TOPMOST = 0x40000


def sinal():
    """Dois bipes curtos para chamar a atencao."""
    if winsound is None:
        return
    try:
        winsound.Beep(880, 250)
        winsound.Beep(1175, 250)
    except Exception:
        pass


def _caixa(texto, titulo):
    try:
        ctypes.windll.user32.MessageBoxW(
            0, texto, titulo,
            MB_ICONINFORMATION | MB_SETFOREGROUND | MB_TOPMOST)
    except Exception:
        pass


def aviso(texto, titulo="Teste TeleZapp", bloquear=False):
    """Mostra uma caixa de mensagem. Sem bloquear, roda em outra thread."""
    sinal()
    if bloquear:
        _caixa(texto, titulo)
    else:
        threading.Thread(target=_caixa, args=(texto, titulo),
                         daemon=True).start()


MB_YESNO = 0x4
MB_ICONQUESTION = 0x20
IDYES = 6


def perguntar_sim_nao(texto, titulo="Teste TeleZapp"):
    """Pergunta sim ou nao numa caixa de mensagem. Devolve True para Sim."""
    sinal()
    try:
        resposta = ctypes.windll.user32.MessageBoxW(
            0, texto, titulo,
            MB_YESNO | MB_ICONQUESTION | MB_SETFOREGROUND | MB_TOPMOST)
    except Exception:
        return False
    return resposta == IDYES


def ler_chaves(caminho):
    """Le linhas CHAVE=valor, ignorando linhas vazias e as que comecam com #."""
    dados = {}
    try:
        with open(caminho, encoding="utf-8-sig", errors="replace") as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                chave, valor = linha.split("=", 1)
                dados[chave.strip().upper()] = valor.strip()
    except OSError:
        pass
    return dados


def pedir_por_arquivo(caminho, modelo, validar, instrucao, timeout=600):
    """Abre o arquivo no Bloco de Notas e espera ele ficar valido.

    Se o arquivo ja existir e estiver valido, devolve na hora (sem abrir nada).
    Devolve o dicionario de chaves, ou None se passar do tempo limite.
    """
    if os.path.isfile(caminho) and validar(ler_chaves(caminho)):
        return ler_chaves(caminho)
    if not os.path.isfile(caminho):
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(modelo)
    try:
        subprocess.Popen(["notepad.exe", caminho])
    except OSError:
        pass
    time.sleep(1.5)
    aviso(instrucao)
    inicio = time.time()
    anterior = None
    estaveis = 0
    while time.time() - inicio < timeout:
        time.sleep(1)
        dados = ler_chaves(caminho)
        if validar(dados):
            if dados == anterior:
                estaveis += 1
            else:
                anterior = dict(dados)
                estaveis = 0
            if estaveis >= 2:
                sinal()
                return dados
        else:
            anterior = None
            estaveis = 0
    return None


def _mensagem_final(nome, falhou=False):
    if nome == "chamada-whatsapp" and falhou:
        return (
            "O teste de chamada do WhatsApp NÃO chegou a completar uma "
            "chamada. A pasta com o arquivo de log foi aberta: envie o "
            "arquivo resultado-teste-chamada-whatsapp.log, que diz onde "
            "parou.\n\nSe a conta de teste chegou a ser pareada, apague, na "
            "pasta 10-chamada-whatsapp-meowcaller, o arquivo "
            "sessao-chamadas.db quando terminar os testes e remova o "
            "aparelho Chrome (Windows) no celular da conta de teste.")
    if nome.startswith(("grande-", "velocidade-")):
        return (
            "O teste de arquivos grandes terminou. A pasta com o arquivo de "
            "log foi aberta: envie o arquivo resultado-teste-%s.log.\n\n"
            "Se foi o teste do WhatsApp, apague da conversa o arquivo "
            "arquivo-grande-teste.bin, que ocupa espaço no celular. O "
            "Telegram apaga a mensagem de teste sozinho. Não envie as "
            "pastas sessao-telegram ou sessao-whatsapp nem os arquivos de "
            "configuração." % nome)
    if nome == "chamada-whatsapp":
        return (
            "O teste de chamada de voz do WhatsApp terminou. A pasta com o "
            "arquivo de log foi aberta: envie o arquivo "
            "resultado-teste-chamada-whatsapp.log e me diga se a voz foi "
            "boa nos dois lados, se houve cortes e se a chamada caiu."
            "\n\n"
            "Quando terminar: apague, na pasta "
            "10-chamada-whatsapp-meowcaller, o arquivo sessao-chamadas.db "
            "(dá acesso à conta de teste) e os arquivos chamada-*.wav "
            "(guardam o que a outra pessoa falou). No celular da conta de "
            "teste, remova o aparelho Chrome (Windows) em Aparelhos "
            "conectados. Não envie esses arquivos nem o arquivo "
            "configuracao-chamada-whatsapp.txt.")
    if nome == "gravacao-voz":
        return (
            "O teste de gravação de voz terminou. A pasta com o arquivo de "
            "log foi aberta: envie o arquivo resultado-teste-gravacao-voz."
            "log e me diga qual versão você preferiu, se ouviu diferença "
            "entre elas, e, se enviou ao Telegram, como as notas de voz "
            "apareceram no celular.\n\n"
            "As gravações ficaram na pasta gravacoes-teste. Pode apagá-la "
            "quando quiser.")
    if nome == "empacotamento":
        return (
            "O teste de empacotamento terminou. A pasta com o arquivo de log "
            "foi aberta: envie o arquivo resultado-teste-empacotamento.log. "
            "Me diga também se o Windows ou o antivírus mostrou algum alerta "
            "ou bloqueou algum arquivo.\n\n"
            "Quando terminar, apague as pastas empacotado, build-pyinstaller "
            "e venv-empacotamento, que ocupam bastante espaço.")
    if nome == "interface":
        return (
            "O teste da interface terminou. A pasta com o arquivo de log foi "
            "aberta: envie o arquivo resultado-teste-interface.log e me "
            "conte o que achou: como o leitor de tela leu as listas, quais "
            "estilos de leitura você preferiu e o que atrapalhou.")
    return (
        "O teste do %s terminou. A pasta com o arquivo de log foi aberta: "
        "envie o arquivo resultado-teste-%s.log.\n\n"
        "Não envie as pastas sessao-telegram ou sessao-whatsapp nem os "
        "arquivos de configuração, porque eles dão acesso à sua conta. "
        "Apague-os quando terminar os testes." % (nome, nome))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "fim":
        falhou = len(sys.argv) >= 4 and sys.argv[3] not in ("0", "")
        aviso(_mensagem_final(sys.argv[2], falhou), bloquear=True)

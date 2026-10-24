# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Prepara a Release do TeleZapp para o GitHub.

Reaproveita o que ferramentas/empacotar.py gerou em lancamento/ (se o zip
ainda nao existe, monta a partir da pasta do programa) e deixa la:

    TeleZapp.exe          o instalador de um arquivo so (gerado pelo
                          empacotar.py); e o que as pessoas baixam
    TeleZapp.zip          a pasta do programa, pronta para extrair (o nome
                          e fixo: .../releases/latest/download/TeleZapp.zip
                          sempre leva a versao mais nova)
    TeleZapp.zip.sha256   o hash para conferir o download
    notas.md                       o texto da Release (aviso de software
                                   experimental + novidades da versao)

Nada vai para o GitHub sem o --publicar. Uso:

    python ferramentas\\publicar.py                    so monta os arquivos
    python ferramentas\\publicar.py --publicar         e cria a Release comum,
                                                      a "latest" do GitHub
    python ferramentas\\publicar.py --publicar --prerelease
                                                      e cria um pre-lancamento

O executavel precisa ser gerado de novo antes, com a versao que esta em
telezapp\\__init__.py (a mesma que sai na tag). Precisa do gh (GitHub CLI)
com login feito para --publicar.
"""
import argparse
import hashlib
import html
import os
import re
import subprocess
import sys
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AVISO = (
    "> **Software experimental.** O TeleZapp está em desenvolvimento e pode "
    "ter erros, inclusive em mensagens e conversas. Use por sua conta e "
    "risco. Não é um produto oficial do WhatsApp nem do Telegram.")


def versao_atual():
    texto = open(os.path.join(RAIZ, "telezapp", "__init__.py"),
                 encoding="utf-8").read()
    achou = re.search(r'^VERSAO = "([^"]+)"', texto, re.M)
    if not achou:
        sys.exit("Não achei VERSAO em telezapp\\__init__.py.")
    return achou.group(1)


def novidades(versao):
    """Os itens da versao em novidades.html, como lista de texto."""
    caminho = os.path.join(RAIZ, "telezapp", "ajuda", "novidades.html")
    texto = open(caminho, encoding="utf-8").read()
    achou = re.search(r"<h2>Versão %s</h2>\s*<ul>(.*?)</ul>" %
                      re.escape(versao), texto, re.S)
    if not achou:
        return []
    itens = re.findall(r"<li>(.*?)</li>", achou.group(1), re.S)
    return [html.unescape(re.sub(r"<[^>]+>", "", i)).strip() for i in itens]


def montar_notas(versao, hash_zip, nome_zip):
    itens = novidades(versao)
    linhas = [AVISO, "", "## Novidades da versão %s" % versao, ""]
    linhas += ["- " + i for i in itens] or [
        "(Sem texto de novidades para esta versão.)"]
    linhas += [
        "", "## Como usar", "",
        "1. Baixe `TeleZapp.exe` e abra. A tela de boas-vindas tem os "
        "botões Instalar, Criar cópia portátil, Guia de uso e Fechar.",
        "2. Para atualizar, use Ajuda, Verificar atualizações dentro do "
        "programa: ele baixa `%s` (o mesmo programa em zip), confere o "
        "SHA-256 e troca a pasta. Os seus dados não são afetados." % nome_zip,
        "3. O zip também serve para extrair a pasta `TeleZapp` à mão e "
        "usar sem instalar.",
        "", "SHA-256 do zip: `%s`" % hash_zip, ""]
    return "\n".join(linhas)


def montar_zip(pasta, destino):
    """Zip com a pasta TeleZapp dentro; devolve o SHA-256."""
    if not os.path.isfile(os.path.join(pasta, "TeleZapp.exe")):
        sys.exit("Não achei TeleZapp.exe em %s. Gere o executável antes." %
                 pasta)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=9) as z:
        for atual, _, arquivos in os.walk(pasta):
            for a in arquivos:
                completo = os.path.join(atual, a)
                z.write(completo, os.path.join(
                    "TeleZapp", os.path.relpath(completo, pasta)))
    h = hashlib.sha256()
    with open(destino, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pasta", default=os.path.join(
        RAIZ, "build-pyinstaller", "programa", "TeleZapp"),
        help="pasta do programa, so se o zip ainda nao existe em --saida")
    ap.add_argument("--saida", default=os.path.join(RAIZ, "lancamento"))
    ap.add_argument("--publicar", action="store_true",
                    help="cria a Release no GitHub com o gh")
    ap.add_argument("--prerelease", action="store_true",
                    help="com --publicar: pre-lancamento (o padrao e a "
                         "Release comum, a latest)")
    ap.add_argument("--final", action="store_true",
                    help=argparse.SUPPRESS)      # antigo: agora e o padrao
    args = ap.parse_args()

    versao = versao_atual()
    os.makedirs(args.saida, exist_ok=True)
    nome_zip = "TeleZapp.zip"
    zip_ = os.path.join(args.saida, nome_zip)
    if os.path.isfile(zip_):          # o empacotar.py ja montou
        print("Usando %s." % zip_)
        h = hashlib.sha256()
        with open(zip_, "rb") as f:
            for bloco in iter(lambda: f.read(1 << 20), b""):
                h.update(bloco)
        hash_zip = h.hexdigest()
    else:
        print("Montando %s..." % zip_)
        hash_zip = montar_zip(args.pasta, zip_)
    instalador = os.path.join(args.saida, "TeleZapp.exe")
    if not os.path.isfile(instalador):
        sys.exit("Não achei %s. Rode ferramentas/empacotar.py antes." %
                 instalador)
    arquivo_hash = zip_ + ".sha256"
    with open(arquivo_hash, "w", encoding="utf-8") as f:
        f.write("%s *%s\n" % (hash_zip, nome_zip))
    notas = os.path.join(args.saida, "notas.md")
    with open(notas, "w", encoding="utf-8") as f:
        f.write(montar_notas(versao, hash_zip, nome_zip))
    print("Pronto: %.0f MB, SHA-256 %s" % (os.path.getsize(zip_) / 1048576,
                                            hash_zip))
    print("Confira as notas em %s antes de publicar." % notas)

    comando = ["gh", "release", "create", versao, instalador, zip_, arquivo_hash,
               "--title", "TeleZapp %s" % versao, "--notes-file", notas]
    comando.append("--prerelease" if args.prerelease else "--latest")
    if not args.publicar:
        print("Para publicar:\n  " + " ".join(comando))
        return
    sys.exit(subprocess.call(comando, cwd=RAIZ))


if __name__ == "__main__":
    main()

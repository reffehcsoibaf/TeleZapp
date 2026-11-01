# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Gera o que vai para a Release, em lancamento/:

    TeleZapp.zip        a pasta do programa (o atualizador usa este)
    TeleZapp.zip.sha256 o hash do zip
    TeleZapp.exe        o instalador de um arquivo so, com o zip dentro

Passos: PyInstaller do programa (pasta), zip da pasta, PyInstaller do
instalador com o zip embutido. Depois, `python ferramentas/publicar.py`
cria a Release com esses tres arquivos. Uso:

    python ferramentas/empacotar.py
"""
import hashlib
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "ferramentas"))
import publicar  # noqa: E402

TRABALHO = os.path.join(RAIZ, "build-pyinstaller")
SAIDA = os.path.join(RAIZ, "lancamento")


def arquivo_de_versao(pasta, descricao, original):
    """Grava o arquivo de versao do Windows (Propriedades, Detalhes) e devolve
    o caminho. A versao vem de telezapp/__init__.py (ano.mes.dia.digito)."""
    sys.path.insert(0, RAIZ)
    from telezapp import NOME, VERSAO
    v = tuple(int(x) for x in VERSAO.split("."))
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, "versao-%s.txt" % original)
    texto = """VSVersionInfo(
  ffi=FixedFileInfo(filevers=%(t)s, prodvers=%(t)s, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041604b0', [
      StringStruct('CompanyName', 'Fábio Scheffer Moraes'),
      StringStruct('FileDescription', %(d)r),
      StringStruct('FileVersion', %(v)r),
      StringStruct('InternalName', %(n)r),
      StringStruct('LegalCopyright', 'Copyright (C) 2026 Fábio Scheffer Moraes. Licença GPL-3.0-or-later.'),
      StringStruct('OriginalFilename', %(o)r),
      StringStruct('ProductName', %(n)r),
      StringStruct('ProductVersion', %(v)r),
      StringStruct('Comments', 'https://github.com/reffehcsoibaf/TeleZapp')])]),
    VarFileInfo([VarStruct('Translation', [0x0416, 1200])])
  ]
)
""" % {"t": v, "d": descricao, "v": VERSAO, "n": NOME, "o": original}
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)
    return caminho


def pyinstaller(spec, dist, work, env=None):
    subprocess.check_call(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", dist, "--workpath", work, spec],
        cwd=RAIZ, env=dict(os.environ, **(env or {})))


def gravar_credenciais():
    """Poe o api id e o api hash do Telegram do projeto no programa, para
    quem instala nao precisar criar os seus. Vem de TELEZAPP_API_ID e
    TELEZAPP_API_HASH, da configuracao deste computador ou do arquivo dos
    testes. Devolve o caminho gerado (apagado no fim) ou None."""
    sys.path.insert(0, RAIZ)
    from telezapp import config
    api_id, api_hash = os.environ.get("TELEZAPP_API_ID"), os.environ.get(
        "TELEZAPP_API_HASH")
    if config.credenciais_validas(api_id, api_hash):
        cred = (int(api_id), api_hash.strip())
    else:
        cred = config.credenciais_telegram(config.Config())
    if cred is None:
        print("AVISO: sem api id e api hash do Telegram; quem instalar "
              "vai precisar informar os seus.")
        return None
    caminho = os.path.join(RAIZ, "telezapp", "_credenciais.py")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("# Gerado por ferramentas/empacotar.py; fora do git.\n"
                "API_ID = %d\nAPI_HASH = %r\n" % cred)
    print("Credenciais do Telegram embutidas no programa.")
    return caminho


def main():
    credenciais = gravar_credenciais()
    try:
        _montar()
    finally:
        if credenciais and os.path.exists(credenciais):
            os.remove(credenciais)


def _montar():
    os.makedirs(SAIDA, exist_ok=True)
    programa = os.path.join(TRABALHO, "programa")
    print("1/3 Gerando o programa...")
    pyinstaller(os.path.join(RAIZ, "ferramentas", "empacotar",
                             "TeleZapp.spec"), programa,
                os.path.join(TRABALHO, "work-programa"),
                {"TELEZAPP_VERSAO": arquivo_de_versao(
                    TRABALHO, "TeleZapp: WhatsApp e Telegram para leitores "
                    "de tela", "TeleZapp.exe")})
    zip_ = os.path.join(SAIDA, "TeleZapp.zip")
    print("2/3 Montando %s..." % zip_)
    hash_zip = publicar.montar_zip(os.path.join(programa, "TeleZapp"), zip_)
    with open(zip_ + ".sha256", "w", encoding="utf-8") as f:
        f.write("%s *TeleZapp.zip\n" % hash_zip)
    print("3/3 Gerando o instalador...")
    pyinstaller(os.path.join(RAIZ, "ferramentas", "empacotar",
                             "Instalador.spec"), SAIDA,
                os.path.join(TRABALHO, "work-instalador"),
                {"TELEZAPP_PACOTE": zip_,
                 "TELEZAPP_VERSAO": arquivo_de_versao(
                     TRABALHO, "Instalador do TeleZapp", "TeleZapp.exe")})
    exe = os.path.join(SAIDA, "TeleZapp.exe")
    from telezapp.nucleo import copia_oficial
    with open(os.path.join(SAIDA, copia_oficial.ARQUIVO_DA_LISTA), "w",
              encoding="utf-8") as f:
        f.write(copia_oficial.gerar_lista(os.path.join(programa, "TeleZapp"),
                                          exe))
    h = hashlib.sha256(open(exe, "rb").read()).hexdigest()
    print("Pronto em %s:\n  TeleZapp.zip  %.0f MB\n  TeleZapp.exe  %.0f MB "
          "(SHA-256 %s)" % (SAIDA, os.path.getsize(zip_) / 1048576,
                            os.path.getsize(exe) / 1048576, h))


if __name__ == "__main__":
    main()

r"""Devolve ao venv do TeleZapp os 7 arquivos originais do neonize 0.5.2
(o pacote do PyPI, sem as mudancas de teste).

Uso (com o TeleZapp fechado):
    venv\Scripts\python Backup\restaurar_neonize.py [pasta do neonize]

Sem argumento, restaura em venv\Lib\site-packages\neonize. Os originais
ficam em Backup\neonize-0.5.2-original e nao sao apagados. Para voltar a DLL e
os arquivos de teste (avisos ao vivo de arquivar, trancar, fixar, apagar...):
Backup\restaurar_neonize_teste.py.
"""
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ORIGEM = os.path.join(AQUI, "neonize-0.5.2-original")
PADRAO = os.path.join(os.path.dirname(AQUI), "venv", "Lib", "site-packages",
                      "neonize")
ARQUIVOS = [
    "_binder.py",
    "client.py",
    "events.py",
    os.path.join("aioze", "events.py"),
    os.path.join("proto", "Neonize_pb2.py"),
    os.path.join("proto", "Neonize_pb2.pyi"),
    "neonize-windows-amd64.dll",
]


def restaurar(origem=ORIGEM, destino=PADRAO):
    if not os.path.isdir(destino):
        sys.exit("neonize nao encontrado: " + destino)
    for rel in ARQUIVOS:
        shutil.copy2(os.path.join(origem, rel), os.path.join(destino, rel))
        print("restaurado:", rel)


if __name__ == "__main__":
    restaurar(destino=sys.argv[1] if len(sys.argv) > 1 else PADRAO)

"""Devolve ao venv do TeleZapp os 5 arquivos originais do neonize 0.5.2.

Uso (com o TeleZapp fechado):
    venv\\Scripts\\python Backup\\restaurar_neonize.py

Os originais ficam em Backup\\neonize-0.5.2-original e nao sao apagados.
"""
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
ORIGINAIS = os.path.join(AQUI, "neonize-0.5.2-original")
VENV = os.path.join(os.path.dirname(AQUI), "venv", "Lib", "site-packages",
                    "neonize")
ARQUIVOS = [
    "events.py",
    os.path.join("aioze", "events.py"),
    os.path.join("proto", "Neonize_pb2.py"),
    os.path.join("proto", "Neonize_pb2.pyi"),
    "neonize-windows-amd64.dll",
]

if not os.path.isdir(VENV):
    sys.exit("venv nao encontrado: " + VENV)
for rel in ARQUIVOS:
    shutil.copy2(os.path.join(ORIGINAIS, rel), os.path.join(VENV, rel))
    print("restaurado:", rel)

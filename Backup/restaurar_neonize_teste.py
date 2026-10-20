r"""Poe no venv do TeleZapp os 7 arquivos do neonize 0.5.2 de TESTE: a DLL com
os avisos ao vivo (arquivar, fixar, silenciar, marcar como lida, trancar,
apagar conversa, apagar mensagem so para mim, estrela), o conserto do
DecodePatchInfo (send_app_state) e fetch_app_state / request_app_state_recovery.

Uso (com o TeleZapp fechado), por exemplo depois de recriar o venv ou de
atualizar o neonize pelo pip:
    venv\Scripts\python Backup\restaurar_neonize_teste.py [pasta do neonize]

Esta copia fica fora do git (a DLL tem uns 18 MB); confira o SHA256SUMS.txt.
Veja a memoria do projeto sobre os PRs abertos no neonize: quando eles
chegarem a uma versao oficial, esta copia deixa de ser necessaria.
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import restaurar_neonize as base  # noqa: E402

TESTE = os.path.join(base.AQUI, "neonize-0.5.2-teste")


def conferir():
    soma = os.path.join(TESTE, "SHA256SUMS.txt")
    ruins = []
    with open(soma, encoding="utf-8") as f:
        for linha in f:
            esperado, rel = linha.split(None, 1)
            rel = rel.strip()
            with open(os.path.join(TESTE, rel), "rb") as a:
                if hashlib.sha256(a.read()).hexdigest() != esperado:
                    ruins.append(rel)
    return ruins


if __name__ == "__main__":
    ruins = conferir()
    if ruins:
        sys.exit("a copia de teste esta alterada: " + ", ".join(ruins))
    base.restaurar(TESTE, sys.argv[1] if len(sys.argv) > 1 else base.PADRAO)

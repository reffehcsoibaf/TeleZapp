# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Caixas de mensagem para o iniciar-telezapp.bat (o .bat so usa ASCII, por
isso os textos com acento ficam aqui). Uso: aviso.py <chave> [caminho]"""
import ctypes
import sys

TEXTOS = {
    "instalando": (
        "O TeleZapp vai instalar os componentes de que precisa. Na primeira "
        "vez leva cerca de um minuto. Aperte Enter e aguarde: o TeleZapp "
        "abre sozinho quando terminar.", 0x40),
    "erro-ambiente": (
        "Não foi possível criar o ambiente do TeleZapp. A pasta com o log "
        "vai abrir: envie o arquivo iniciar.log.", 0x10),
    "erro-instalacao": (
        "A instalação dos componentes falhou. A pasta com o log vai abrir: "
        "envie o arquivo iniciar.log.", 0x10),
}


def main():
    chave = sys.argv[1] if len(sys.argv) > 1 else ""
    texto, icone = TEXTOS.get(chave, ("Aviso do TeleZapp: " + chave, 0x40))
    ctypes.windll.user32.MessageBoxW(None, texto, "TeleZapp", icone)


if __name__ == "__main__":
    main()

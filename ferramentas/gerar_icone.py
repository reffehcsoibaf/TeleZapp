# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Desenha o icone do TeleZapp (um teclado com fone de ouvido) e grava
telezapp/imagens/telezapp.ico e telezapp.png. Rode de novo se mudar o
desenho: venv/Scripts/python ferramentas/gerar_icone.py"""
import os

from PIL import Image, ImageDraw

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PASTA = os.path.join(RAIZ, "telezapp", "imagens")
TAMANHOS = [16, 24, 32, 48, 64, 128, 256]
VERDE = (37, 160, 90, 255)
BRANCO = (255, 255, 255, 255)
BASE = 1024                      # desenha grande e reduz, para suavizar


def desenhar():
    img = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, BASE - 1, BASE - 1), radius=210, fill=VERDE)

    # fone: arco de cabeca e duas conchas
    d.arc((190, 110, 834, 700), 180, 360, fill=BRANCO, width=64)
    d.rounded_rectangle((130, 380, 290, 650), radius=60, fill=BRANCO)
    d.rounded_rectangle((734, 380, 894, 650), radius=60, fill=BRANCO)

    # teclado: corpo branco com teclas em verde
    d.rounded_rectangle((170, 600, 854, 900), radius=60, fill=BRANCO)
    x0, y0, lado, vao = 225, 650, 66, 20
    for linha in range(3):
        n = 8 if linha != 2 else 0
        for i in range(n):
            x = x0 + i * (lado + vao)
            y = y0 + linha * (lado + vao)
            d.rounded_rectangle((x, y, x + lado, y + lado), radius=14,
                                fill=VERDE)
    # barra de espaco
    d.rounded_rectangle((x0 + 2 * (lado + vao), y0 + 2 * (lado + vao),
                         x0 + 6 * (lado + vao) - vao,
                         y0 + 2 * (lado + vao) + lado),
                        radius=14, fill=VERDE)
    return img


def main():
    os.makedirs(PASTA, exist_ok=True)
    img = desenhar()
    img.resize((256, 256), Image.LANCZOS).save(
        os.path.join(PASTA, "telezapp.png"))
    img.save(os.path.join(PASTA, "telezapp.ico"),
             sizes=[(t, t) for t in TAMANHOS])
    print("ok:", PASTA)


if __name__ == "__main__":
    main()

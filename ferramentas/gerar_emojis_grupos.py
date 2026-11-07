# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Gera telezapp/nucleo/emojis_grupos.py: a que categoria (grupo) do Unicode
cada emoji pertence, na ordem do Unicode, para a janela de emojis poder
mostrar uma categoria de cada vez (Carinhas e emoções, Animais e natureza...).

Uso (baixa o emoji-test.txt do Unicode):
    venv/Scripts/python ferramentas/gerar_emojis_grupos.py
Ou com o arquivo ja baixado:
    venv/Scripts/python ferramentas/gerar_emojis_grupos.py emoji-test.txt

O emoji-test.txt e distribuido sob a Unicode License v3 (SPDX Unicode-3.0);
o aviso fica no cabecalho do arquivo gerado. So entram os emojis completos
(fully-qualified) e sem tom de pele: os tons seguem o emoji base."""
import os
import re
import sys
import urllib.request

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SAIDA = os.path.join(RAIZ, "telezapp", "nucleo", "emojis_grupos.py")
FONTE = "https://unicode.org/Public/emoji/latest/emoji-test.txt"
TONS = tuple(chr(c) for c in range(0x1F3FB, 0x1F400))
VARIACAO = chr(0xFE0F)

# grupo do Unicode -> (chave, nome em portugues). "Component" (os tons de pele
# e cabelos soltos) nao e uma categoria para escolher.
GRUPOS = {
    "Smileys & Emotion": ("rostos", "Carinhas e emoções"),
    "People & Body": ("pessoas", "Pessoas e corpo"),
    "Animals & Nature": ("animais", "Animais e natureza"),
    "Food & Drink": ("comidas", "Comidas e bebidas"),
    "Travel & Places": ("viagens", "Viagens e lugares"),
    "Activities": ("atividades", "Atividades"),
    "Objects": ("objetos", "Objetos"),
    "Symbols": ("simbolos", "Símbolos"),
    "Flags": ("bandeiras", "Bandeiras"),
}


def ler(origem):
    if origem.startswith("http"):
        with urllib.request.urlopen(origem, timeout=60) as r:
            return r.read().decode("utf-8")
    with open(origem, encoding="utf-8") as f:
        return f.read()


def main(argv):
    texto = ler(argv[0] if argv else FONTE)
    grupo = None
    por_grupo = {chave: [] for chave, _ in GRUPOS.values()}
    for linha in texto.splitlines():
        m = re.match(r"# group: (.+)", linha)
        if m:
            grupo = GRUPOS.get(m.group(1).strip())
            continue
        if not linha or linha.startswith("#") or grupo is None:
            continue
        codigos, _, resto = linha.partition(";")
        status = resto.split("#")[0].strip()
        if status != "fully-qualified":
            continue
        simbolo = "".join(chr(int(c, 16)) for c in codigos.split())
        if any(c in TONS for c in simbolo):
            continue
        por_grupo[grupo[0]].append(simbolo.replace(VARIACAO, ""))
    cabecalho = '''# SPDX-License-Identifier: GPL-3.0-or-later
"""A categoria (grupo) do Unicode de cada emoji, na ordem do Unicode, para a
janela de emojis. GERADO por ferramentas/gerar_emojis_grupos.py a partir do
emoji-test.txt do Unicode; nao edite a mao.

Dados do Unicode Emoji (emoji-test.txt).
Copyright (c) 1991-2026 Unicode, Inc. Distribuido sob a Unicode License v3
(SPDX-License-Identifier: Unicode-3.0), em https://www.unicode.org/license.txt
"""
# (chave, nome) de cada categoria, na ordem em que aparecem
GRUPOS = (
'''
    saida = [cabecalho]
    for chave, nome in GRUPOS.values():
        saida.append("    (%r, %r),\n" % (chave, nome))
    saida.append(")\n\n# chave -> os emojis (sem o seletor de variacao U+FE0F)"
                 ", separados por espaco, na ordem do Unicode\nEMOJIS = {\n")
    total = 0
    for chave, _ in GRUPOS.values():
        saida.append("    %r: %r,\n" % (chave, " ".join(por_grupo[chave])))
        total += len(por_grupo[chave])
    saida.append("}\n")
    with open(SAIDA, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(saida))
    print("emojis com categoria:", total, "| arquivo:",
          round(os.path.getsize(SAIDA) / 1024), "KB")


if __name__ == "__main__":
    main(sys.argv[1:])

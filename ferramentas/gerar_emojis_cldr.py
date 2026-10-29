# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Gera telezapp/nucleo/emojis_cldr_pt.py: as palavras-chave em portugues do
Brasil de cada emoji (sinonimos e termos equivalentes), tiradas do CLDR do
Unicode (common/annotations/pt.xml e common/annotationsDerived/pt.xml).

Uso (baixa os dois arquivos do GitHub do CLDR):
    venv/Scripts/python ferramentas/gerar_emojis_cldr.py
Ou com arquivos ja baixados:
    venv/Scripts/python ferramentas/gerar_emojis_cldr.py pt.xml derivado.xml

O CLDR e distribuido sob a Unicode License v3 (SPDX Unicode-3.0); o aviso
fica no cabecalho do arquivo gerado. So entram os emojis completos que a
busca mostra (os de tom de pele usam as palavras do emoji sem tom)."""
import os
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SAIDA = os.path.join(RAIZ, "telezapp", "nucleo", "emojis_cldr_pt.py")
BASE = "https://raw.githubusercontent.com/unicode-org/cldr/main/common/"
FONTES = (BASE + "annotations/pt.xml", BASE + "annotationsDerived/pt.xml")
TONS = tuple(chr(c) for c in range(0x1F3FB, 0x1F400))
VARIACAO = chr(0xFE0F)


def chave(simbolo):
    return simbolo.replace(VARIACAO, "")


def ler(origem):
    if origem.startswith("http"):
        with urllib.request.urlopen(origem, timeout=60) as r:
            dados = r.read()
    else:
        with open(origem, "rb") as f:
            dados = f.read()
    return ET.fromstring(dados)


def palavras(texto):
    """As palavras de uma anotacao ("chorando de rir | rosto"), minusculas, sem
    pontuacao, sem repetir."""
    achadas = []
    for pedaco in re.split(r"[|:;,/()\u2013-]", texto):
        for w in pedaco.lower().split():
            w = w.strip("?!.'\"")
            if w and w not in achadas:
                achadas.append(w)
    return achadas


def main(argv):
    import emoji
    validos = {chave(k) for k, v in emoji.EMOJI_DATA.items()
               if v["status"] == emoji.STATUS["fully_qualified"]
               and not any(c in TONS for c in k)}
    fontes = argv or list(FONTES)
    dados = {}
    for origem in fontes:
        for nó in ler(origem).iter("annotation"):
            cp = chave(nó.get("cp") or "")
            if cp not in validos:
                continue
            junto = dados.setdefault(cp, [])
            for w in palavras(nó.text or ""):
                if w not in junto:
                    junto.append(w)
    linhas = []
    for cp in sorted(dados, key=lambda c: [ord(x) for x in c]):
        linhas.append("    %r: %r," % (cp, " ".join(dados[cp])))
    cabecalho = '''# SPDX-License-Identifier: GPL-3.0-or-later
"""Palavras-chave em portugues (Brasil) de cada emoji, para a busca: sinonimos
e termos equivalentes. GERADO por ferramentas/gerar_emojis_cldr.py a partir
do CLDR do Unicode; nao edite a mao.

Dados do Unicode CLDR (common/annotations/pt.xml e
common/annotationsDerived/pt.xml).
Copyright (c) 1991-2026 Unicode, Inc. Distribuido sob a Unicode License v3
(SPDX-License-Identifier: Unicode-3.0), em https://www.unicode.org/license.txt
"""
# emoji (sem o seletor de variacao U+FE0F) -> palavras-chave
PALAVRAS = {
'''
    with open(SAIDA, "w", encoding="utf-8", newline="\n") as f:
        f.write(cabecalho + "\n".join(linhas) + "\n}\n")
    print("emojis com palavras:", len(dados), "de", len(validos),
          "| arquivo:", round(os.path.getsize(SAIDA) / 1024), "KB")


if __name__ == "__main__":
    main(sys.argv[1:])

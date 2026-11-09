# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Formatação escrita no texto das mensagens (asteriscos, sublinhados...).

Sem wx. O WhatsApp marca o negrito com `*texto*`, o itálico com `_texto_`, o
tachado com `~texto~` e o código com crases; bots e IAs escrevem Markdown
(`**negrito**`, `# título`, `- item`). O leitor de tela lê esses símbolos sem
dizer o que significam. Aqui eles viram palavras ("negrito: texto") ou somem.

Só pares bem formados são tratados: o símbolo de abrir cola no texto e vem
depois de espaço, pontuação ou do começo; o de fechar também cola e vem antes
de espaço, pontuação ou do fim. Assim `2*3*4`, `nome_do_arquivo`, um `*`
solto e os endereços ficam como estão. O texto guardado e o que se copia não
mudam: isto só vale para o que se lê e se ouve.
"""
import re

ORIGINAL, ANUNCIAR, TIRAR = "original", "anunciar", "tirar"
MODOS = (ORIGINAL, ANUNCIAR, TIRAR)

# trechos com mais palavras que isto dizem onde acabam ("fim do negrito")
PALAVRAS_SEM_FIM = 8

_BLOCO = re.compile(r"```(?:[A-Za-z0-9_+-]*\n)?(.*?)```", re.S)
_CODIGO = re.compile(r"`([^`\n]+)`")
# endereco: fica como esta; o simbolo de fechar logo depois dele nao entra
_URL = re.compile(r"(?:https?://|www\.)\S*[^\s*_~.,;:!?)\]]")
_FORMATOS = (
    # (expressao, nome, tem o simbolo duplo)
    (re.compile(r"(?<![\w*])\*\*(?=[^\s*])([^\n]+?)(?<=[^\s*])\*\*(?![\w*])"),
     "negrito"),
    (re.compile(r"(?<![\w_])__(?=[^\s_])([^\n]+?)(?<=[^\s_])__(?![\w_])"),
     "negrito"),
    (re.compile(r"(?<![\w*])\*(?=[^\s*])([^\n*]+?)(?<=[^\s*])\*(?![\w*])"),
     "negrito"),
    (re.compile(r"(?<![\w_])_(?=[^\s_])([^\n_]+?)(?<=[^\s_])_(?![\w_])"),
     "itálico"),
    (re.compile(r"(?<![\w~])~~(?=[^\s~])([^\n]+?)(?<=[^\s~])~~(?![\w~])"),
     "tachado"),
    (re.compile(r"(?<![\w~])~(?=[^\s~])([^\n~]+?)(?<=[^\s~])~(?![\w~])"),
     "tachado"),
)
_TITULO = re.compile(r"^[ \t]*#{1,6}[ \t]+(?=\S)", re.M)
_ITEM = re.compile(r"^([ \t]*)[-*•][ \t]+(?=\S)", re.M)
# conta: 2*3 e 5 * 3 (so entre numeros); o leitor de tela diz "vezes"
_VEZES = re.compile(r"(?<=\d)[ 	]*\*[ 	]*(?=\d)")
_MARCA = "\x00%d\x00"


def tem_formatacao(texto):
    """Vale a pena tentar? (a maioria das mensagens nao tem nenhum simbolo)"""
    return bool(texto) and any(c in texto for c in "*_~`#-•")


def _palavras(trecho):
    return len(trecho.split())


def _guardar_bruto(guardados, trecho):
    guardados.append(trecho)
    return _MARCA % (len(guardados) - 1)


def aplicar(texto, modo):
    """O texto com a formatação dita (ANUNCIAR), sem os símbolos (TIRAR) ou
    como veio (ORIGINAL ou modo desconhecido)."""
    if modo not in (ANUNCIAR, TIRAR) or not tem_formatacao(texto):
        return texto
    anunciar = modo == ANUNCIAR
    guardados = []

    def guardar(rotulo, conteudo):
        # o codigo fica como esta: o que parece formatacao dentro dele nao e
        guardados.append(("código: " + conteudo.strip("\n")) if anunciar
                         else conteudo.strip("\n"))
        return _MARCA % (len(guardados) - 1)
    texto = _BLOCO.sub(lambda r: guardar("bloco", r.group(1)), texto)
    texto = _CODIGO.sub(lambda r: guardar("codigo", r.group(1)), texto)
    texto = _URL.sub(lambda r: _guardar_bruto(guardados, r.group(0)), texto)

    texto = _TITULO.sub("título: " if anunciar else "", texto)
    texto = _ITEM.sub(lambda r: r.group(1) + ("item: " if anunciar else "- "),
                      texto)
    for padrao, nome in _FORMATOS:
        def trocar(r, nome=nome):
            dentro = r.group(1)
            if not anunciar:
                return dentro
            fim = (", fim do %s" % nome) if _palavras(dentro) > \
                PALAVRAS_SEM_FIM else ""
            return "%s: %s%s" % (nome, dentro, fim)
        texto = padrao.sub(trocar, texto)
    if anunciar:
        texto = _VEZES.sub(" vezes ", texto)
    for i, parte in enumerate(guardados):
        texto = texto.replace(_MARCA % i, parte)
    return texto

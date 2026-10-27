# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Editar o proprio perfil (nome, recado e foto) no WhatsApp e no Telegram.

Sem wx, para testar em qualquer sistema. Quem fala com o servico sao os
provedores (`meu_perfil` e `salvar_perfil`).
"""

# Limites de cada servico (0 = o campo nao existe). O recado do Telegram tem
# 70 caracteres e 140 com Premium: aqui vale o maior, e quem passa de 70 sem
# Premium recebe o erro do servico, dito a pessoa.
LIMITES = {
    "whatsapp": {"nome": 25, "sobrenome": 0, "recado": 139},
    "telegram": {"nome": 64, "sobrenome": 64, "recado": 140},
}
DICA_DO_RECADO = {"whatsapp": "até 139 caracteres",
                  "telegram": "até 70 caracteres, ou 140 com Premium"}
CAMPOS = ("nome", "sobrenome", "recado")
LADO_DA_FOTO = 640            # as fotos de perfil dos dois servicos sao quadradas
ROTULOS = {"nome": "o nome", "sobrenome": "o sobrenome",
           "recado": "o recado", "foto": "a foto"}
NOMES = {"nome": "nome", "sobrenome": "sobrenome", "recado": "recado",
         "foto": "foto"}


def limites(servico):
    return LIMITES.get(servico, LIMITES["whatsapp"])


def mudancas(atual, novo):
    """So os campos de texto que a pessoa mudou: {campo: texto novo}. Textos
    sao comparados sem espaços nas pontas."""
    saida = {}
    for campo in CAMPOS:
        if campo not in novo:
            continue
        depois = (novo[campo] or "").strip()
        if depois != (atual.get(campo) or "").strip():
            saida[campo] = depois
    return saida


def validar(servico, mudadas):
    """Texto do problema ('' se esta tudo certo) nos campos que vao mudar."""
    lim = limites(servico)
    if "nome" in mudadas and not mudadas["nome"]:
        return "O nome não pode ficar vazio."
    for campo, texto in mudadas.items():
        maximo = lim.get(campo, 0)
        if maximo and len(texto) > maximo:
            return "%s passa de %d caracteres (tem %d)." % (
                ROTULOS[campo].capitalize(), maximo, len(texto))
    return ""


def resumo(feitos, erros):
    """Frase para dizer o que ficou salvo e o que nao deu."""
    partes = []
    if feitos:
        partes.append("Perfil salvo: %s." % ", ".join(
            NOMES.get(f, f) for f in feitos))
    for campo, motivo in erros:
        partes.append("Não consegui mudar %s: %s" % (
            ROTULOS.get(campo, campo), motivo))
    return " ".join(partes) or "Nada mudou."


def preparar_foto(caminho):
    """Bytes JPEG quadrados (recortados do centro, no tamanho comum dos
    servicos) da imagem em `caminho`. Levanta ValueError com o texto para a
    pessoa se o arquivo nao for uma imagem que da para ler."""
    import cv2
    import numpy as np
    try:
        dados = np.fromfile(caminho, dtype=np.uint8)
        imagem = cv2.imdecode(dados, cv2.IMREAD_COLOR)
    except OSError as e:
        raise ValueError("Não consegui abrir o arquivo.") from e
    if imagem is None:
        raise ValueError("O arquivo não é uma imagem que o TeleZapp leia "
                         "(use JPG, PNG, BMP ou WebP).")
    alto, largo = imagem.shape[:2]
    lado = min(alto, largo)
    de_cima, da_esquerda = (alto - lado) // 2, (largo - lado) // 2
    quadrada = imagem[de_cima:de_cima + lado, da_esquerda:da_esquerda + lado]
    if lado != LADO_DA_FOTO:
        quadrada = cv2.resize(
            quadrada, (LADO_DA_FOTO, LADO_DA_FOTO),
            interpolation=cv2.INTER_AREA if lado > LADO_DA_FOTO
            else cv2.INTER_CUBIC)
    ok, jpeg = cv2.imencode(".jpg", quadrada, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise ValueError("Não consegui preparar a foto.")
    return jpeg.tobytes()

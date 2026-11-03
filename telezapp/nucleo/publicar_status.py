# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Conferencia do que a pessoa quer publicar como status (WhatsApp) ou
historia (Telegram), antes de enviar. Sem wx, para testar."""
from telezapp.midia import envio
from telezapp.nucleo import modelos as m

LIMITE_TEXTO = {"whatsapp": 700, "telegram": 200}
LIMITE_MENCOES = 5
PUBLICOS = (("contatos", "Meus contatos"), ("todos", "Todos"))


def validar(servico, texto, caminho, voz=False):
    """(anexo ou None, texto limpo, erro). `erro` vazio se pode publicar.
    WhatsApp aceita texto, foto, video ou voz (`voz`: `caminho` e uma gravacao
    feita na janela); Telegram exige foto ou video."""
    texto = (texto or "").strip()
    anexo = None
    if caminho and voz:
        if servico == "telegram":
            return None, texto, ("No Telegram a história não aceita mensagem "
                                 "de voz; use uma foto ou um vídeo.")
        if texto:
            return None, texto, ("A mensagem de voz não leva texto. Apague o "
                                 "texto ou tire a gravação.")
        try:
            return envio.preparar(caminho, voz=True, temporario=True), "", ""
        except envio.ErroEnvio as e:
            return None, texto, str(e)
    if caminho:
        try:
            anexo = envio.preparar(caminho)
        except envio.ErroEnvio as e:
            return None, texto, str(e)
        if anexo.tipo not in (m.FOTO, m.VIDEO):
            return None, texto, ("Só dá para publicar foto ou vídeo. Escolha "
                                 "um arquivo JPG, PNG, WEBP, MP4 ou MOV.")
    if anexo is None and not texto:
        return None, texto, ("Escreva o texto, escolha uma foto ou vídeo ou "
                             "grave a voz.")
    if anexo is None and servico == "telegram":
        return None, texto, ("No Telegram a história precisa de uma foto ou "
                             "de um vídeo; o texto vai de legenda.")
    limite = LIMITE_TEXTO.get(servico, 700)
    if len(texto) > limite:
        return None, texto, ("O texto passa de %d letras (tem %d)." % (
            limite, len(texto)))
    return anexo, texto, ""

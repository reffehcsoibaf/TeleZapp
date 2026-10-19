# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Contribuidores do TeleZapp
"""Conferencia do que a pessoa quer publicar como status (WhatsApp) ou
historia (Telegram), antes de enviar. Sem wx, para testar."""
from telezapp.midia import envio
from telezapp.nucleo import modelos as m

LIMITE_TEXTO = {"whatsapp": 700, "telegram": 200}
PUBLICOS = (("contatos", "Meus contatos"), ("todos", "Todos"))


def validar(servico, texto, caminho):
    """(anexo ou None, texto limpo, erro). `erro` vazio se pode publicar.
    WhatsApp aceita so texto, foto ou video; Telegram exige foto ou video."""
    texto = (texto or "").strip()
    anexo = None
    if caminho:
        try:
            anexo = envio.preparar(caminho)
        except envio.ErroEnvio as e:
            return None, texto, str(e)
        if anexo.tipo not in (m.FOTO, m.VIDEO):
            return None, texto, ("Só dá para publicar foto ou vídeo. Escolha "
                                 "um arquivo JPG, PNG, WEBP, MP4 ou MOV.")
    if anexo is None and not texto:
        return None, texto, "Escreva o texto ou escolha uma foto ou vídeo."
    if anexo is None and servico == "telegram":
        return None, texto, ("No Telegram a história precisa de uma foto ou "
                             "de um vídeo; o texto vai de legenda.")
    limite = LIMITE_TEXTO.get(servico, 700)
    if len(texto) > limite:
        return None, texto, ("O texto passa de %d letras (tem %d)." % (
            limite, len(texto)))
    return anexo, texto, ""

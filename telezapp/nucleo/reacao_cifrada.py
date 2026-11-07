# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Reacao cifrada (encReactionMessage) do WhatsApp.

Em comunidades (grupo de avisos) e em outros lugares, a reacao a uma mensagem
chega cifrada com o segredo da mensagem original, que a sessao guarda
(`whatsmeow_message_secrets`). O neonize nao exporta a funcao que decifra, entao
o calculo do whatsmeow (`DecryptReaction`) e refeito aqui:

    chave = HKDF-SHA256(segredo, sal vazio,
                        info = id_original + remetente_original +
                               quem_reagiu + "Enc Reaction")  -> 32 bytes
    texto = AES-256-GCM(chave, iv, payload, dados adicionais vazios)

O texto e um ReactionMessage (protobuf).
"""
import hashlib
import hmac
import logging
import re
import sqlite3

log = logging.getLogger(__name__)

USO = b"Enc Reaction"


def sem_aparelho(jid):
    """'usuario:12@servidor' -> 'usuario@servidor' (a forma sem o aparelho
    que o whatsmeow usa na chave)."""
    return re.sub(r"(?:\.\d+)?(?::\d+)?@", "@", jid or "", count=1)


def hkdf_sha256(segredo, info, tamanho=32):
    """HKDF (RFC 5869) com SHA-256 e sal vazio (zeros)."""
    prk = hmac.new(b"\0" * 32, segredo, hashlib.sha256).digest()
    saida, bloco, n = b"", b"", 1
    while len(saida) < tamanho:
        bloco = hmac.new(prk, bloco + info + bytes([n]),
                         hashlib.sha256).digest()
        saida += bloco
        n += 1
    return saida[:tamanho]


def chave_da_reacao(segredo, id_original, remetente_original, quem_reagiu):
    info = (id_original.encode() + sem_aparelho(remetente_original).encode()
            + sem_aparelho(quem_reagiu).encode() + USO)
    return hkdf_sha256(segredo, info, 32)


def _aes_gcm_abrir(chave, iv, payload):
    from Cryptodome.Cipher import AES
    cifra = AES.new(chave, AES.MODE_GCM, nonce=iv)
    return cifra.decrypt_and_verify(payload[:-16], payload[-16:])


def decifrar(segredo, id_original, remetentes_originais, quem_reagiu, iv,
             payload):
    """O texto claro (bytes) ou None. `remetentes_originais`: os candidatos a
    autor da mensagem original (o da chave e o guardado com o segredo, que
    podem ser o telefone e o LID da mesma pessoa); `quem_reagiu`: um ou
    mais candidatos a quem reagiu (telefone ou LID)."""
    quem = [quem_reagiu] if isinstance(quem_reagiu, str) else list(quem_reagiu)
    for q in quem:
        for autor in dict.fromkeys(r for r in remetentes_originais if r):
            try:
                return _aes_gcm_abrir(
                    chave_da_reacao(segredo, id_original, autor, q), iv,
                    payload)
            except ValueError:
                continue
    return None


def segredo_guardado(caminho_sessao, id_original):
    """(segredo, remetente_guardado) da mensagem original, lido do banco da
    sessao (so leitura), ou (None, "") se a sessao nao o guardou. O ID da
    mensagem basta: e unico."""
    try:
        con = sqlite3.connect("file:%s?mode=ro" % caminho_sessao.replace(
            "\\", "/"), uri=True, timeout=5)
    except sqlite3.Error:
        return None, ""
    try:
        linha = con.execute(
            "SELECT key, sender_jid FROM whatsmeow_message_secrets "
            "WHERE message_id=? LIMIT 1", (id_original,)).fetchone()
    except sqlite3.Error:
        return None, ""
    finally:
        con.close()
    return (bytes(linha[0]), linha[1] or "") if linha else (None, "")

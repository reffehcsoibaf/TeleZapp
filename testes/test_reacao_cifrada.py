# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Reacao cifrada (encReactionMessage) do WhatsApp: a decifragem refeita em
Python e o caminho ate a reacao aparecer na mensagem."""
import os
import sqlite3

from telezapp.nucleo import modelos as m
from telezapp.nucleo import reacao_cifrada as rc
from telezapp.nucleo import eventos as ev

from testes.test_provedor_whatsapp import (E, _chave, _chegou, amb, esperar,
                                           evento, wa)  # noqa: F401


def test_hkdf_confere_com_o_vetor_3_da_rfc_5869():
    okm = rc.hkdf_sha256(bytes([0x0b] * 22), b"", 42)
    assert okm.hex() == (
        "8da4e775a563c18f715f802a063c5a31b8a11f5c5ee1879ec3454e5f3c738d2d"
        "9d201395faa4b61a96c8")


def test_sem_aparelho_tira_o_numero_do_aparelho():
    assert rc.sem_aparelho("7054@lid") == "7054@lid"
    assert rc.sem_aparelho("7054:12@lid") == "7054@lid"
    assert rc.sem_aparelho("5551.0:3@s.whatsapp.net") == \
        "5551@s.whatsapp.net"


def _cifrar(segredo, id_original, autor, quem, texto, iv=b"\1" * 12):
    from Cryptodome.Cipher import AES
    chave = rc.chave_da_reacao(segredo, id_original, autor, quem)
    cifra = AES.new(chave, AES.MODE_GCM, nonce=iv)
    claro, tag = cifra.encrypt_and_digest(texto)
    return iv, claro + tag


def test_decifrar_vai_e_volta_e_tenta_o_outro_autor():
    segredo = bytes(range(32))
    iv, carga = _cifrar(segredo, "M1", "7054@lid", "9988@lid", b"oi")
    # o primeiro candidato (telefone) falha; o segundo (LID) abre
    assert rc.decifrar(segredo, "M1", ["5551@s.whatsapp.net", "7054@lid"],
                       "9988@lid", iv, carga) == b"oi"
    assert rc.decifrar(segredo, "M1", ["outro@lid"], "9988@lid", iv,
                       carga) is None
    assert rc.decifrar(bytes(32), "M1", ["7054@lid"], "9988@lid", iv,
                       carga) is None


def _sessao(tmp_path, conta, id_original, segredo, sender):
    con = sqlite3.connect(os.path.join(str(tmp_path), conta + ".db"))
    con.execute("CREATE TABLE whatsmeow_message_secrets (our_jid TEXT, "
                "chat_jid TEXT, sender_jid TEXT, message_id TEXT, key BLOB)")
    con.execute("INSERT INTO whatsmeow_message_secrets VALUES "
                "('eu@s.whatsapp.net','c','%s','%s',?)" % (sender,
                                                           id_original),
                (segredo,))
    con.commit()
    con.close()


def test_reacao_cifrada_aparece_na_mensagem(amb, tmp_path):
    segredo = bytes(range(32))
    _chegou(amb, "M1")
    autor = "5551988887777@s.whatsapp.net"    # quem mandou a mensagem
    quem = "5551988887777@s.whatsapp.net"     # e quem reagiu (a mesma)
    _sessao(tmp_path, "w1", "M1", segredo, autor)
    from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import ReactionMessage
    claro = ReactionMessage(key=_chave("M1"), text="👍").SerializeToString()
    iv, carga = _cifrar(segredo, "M1", autor, quem, claro)
    cifrada = E.Message(encReactionMessage=E.EncReactionMessage(
        targetMessageKey=_chave("M1"), encPayload=carga, encIV=iv))
    amb.f["Message"](amb.c, evento("R1", cifrada, pushname="Bruno"))
    a = esperar(amb.fila, ev.MensagemAtualizada)
    assert (a.motivo, a.emoji) == ("reacao", "👍")
    assert [r["emoji"] for r in m.extras_de(a.mensagem)["reacoes"]] == ["👍"]


def test_reacao_cifrada_sem_segredo_e_ignorada_sem_mensagem_de_erro(amb):
    _chegou(amb, "M1")
    cifrada = E.Message(encReactionMessage=E.EncReactionMessage(
        targetMessageKey=_chave("M1"), encPayload=b"x" * 20,
        encIV=b"\1" * 12))
    amb.f["Message"](amb.c, evento("R2", cifrada))
    assert amb.banco.mensagem("w1", "5551988887777@s.whatsapp.net",
                              "R2") is None      # nao virou "nao suportada"

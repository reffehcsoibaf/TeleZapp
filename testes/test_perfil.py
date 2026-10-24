# SPDX-License-Identifier: GPL-3.0-or-later
"""Editar o proprio perfil: regras, foto e os dois provedores, com clientes
simulados."""
import asyncio
import types

import pytest

from telezapp.nucleo import perfil as np_
from telezapp.provedores import base
from telezapp.provedores import telegram as tg
from telezapp.provedores import whatsapp as wa


# --------------------------------------------------------------- regras
def test_mudancas_so_os_campos_que_mudaram():
    atual = {"nome": "Fábio", "sobrenome": "", "recado": "Oi"}
    assert np_.mudancas(atual, {"nome": " Fábio ", "recado": "Olá"}) == {
        "recado": "Olá"}
    assert np_.mudancas(atual, {"nome": "Fábio", "recado": "Oi"}) == {}
    # um campo que o formulario nao tem (sobrenome no WhatsApp) fica de fora
    assert np_.mudancas(atual, {"nome": "F"}) == {"nome": "F"}
    # apagar o recado e uma mudanca
    assert np_.mudancas(atual, {"recado": ""}) == {"recado": ""}


def test_validar_nome_vazio_e_limites_de_cada_servico():
    assert np_.validar("whatsapp", {"nome": ""}) == \
        "O nome não pode ficar vazio."
    assert np_.validar("whatsapp", {"nome": "x" * 26}).startswith(
        "O nome passa de 25")
    assert np_.validar("whatsapp", {"recado": "x" * 140}).startswith(
        "O recado passa de 139")
    assert np_.validar("telegram", {"recado": "x" * 100}) == ""   # Premium
    assert np_.validar("telegram", {"recado": "x" * 141}) != ""
    assert np_.validar("whatsapp", {"recado": ""}) == ""   # apagar vale


def test_resumo_diz_o_que_salvou_e_o_que_nao_deu():
    assert np_.resumo(["nome", "foto"], []) == "Perfil salvo: nome, foto."
    assert np_.resumo(["nome"], [("foto", "o serviço recusou.")]) == (
        "Perfil salvo: nome. Não consegui mudar a foto: o serviço recusou.")
    assert np_.resumo([], []) == "Nada mudou."


def _imagem(tmp_path, largo, alto, nome="a.png"):
    import cv2
    import numpy as np
    caminho = tmp_path / nome
    ok, dados = cv2.imencode(".png", np.full((alto, largo, 3), 120, np.uint8))
    assert ok
    dados.tofile(str(caminho))
    return str(caminho)


def test_preparar_foto_recorta_o_centro_em_quadrado_jpeg(tmp_path):
    import cv2
    import numpy as np
    for largo, alto in ((1000, 400), (300, 900), (640, 640)):
        jpeg = np_.preparar_foto(_imagem(tmp_path, largo, alto))
        assert jpeg[:2] == b"\xff\xd8"
        img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        assert img.shape[:2] == (np_.LADO_DA_FOTO, np_.LADO_DA_FOTO)


def test_preparar_foto_aceita_nome_com_acento_e_recusa_o_que_nao_e_imagem(
        tmp_path):
    assert np_.preparar_foto(_imagem(tmp_path, 100, 100, "foto é nova.png"))
    texto = tmp_path / "nota.txt"
    texto.write_text("não sou imagem")
    with pytest.raises(ValueError) as e:
        np_.preparar_foto(str(texto))
    assert "imagem" in str(e.value)
    with pytest.raises(ValueError):
        np_.preparar_foto(str(tmp_path / "nao-existe.png"))


# ------------------------------------------------------------- WhatsApp
class ClienteWhatsApp:
    def __init__(self, recusa=()):
        self.chamadas, self.recusa = [], set(recusa)

    def get_me(self):
        from neonize.proto import Neonize_pb2 as N
        return N.Device(JID=wa._jid_obj("5551999998888", "s.whatsapp.net"),
                        PushName="Fábio")

    def get_user_info(self, *jids):
        from neonize.proto import Neonize_pb2 as N
        return [N.GetUserInfoSingleReturnFunction(
            JID=jids[0], UserInfo=N.UserInfo(Status="Ocupado"))]

    def _pedido(self, nome, valor):
        if nome in self.recusa:
            raise RuntimeError("recusou")
        self.chamadas.append((nome, valor))

    def set_profile_name(self, nome):
        self._pedido("nome", nome)

    def set_status_message(self, recado):
        self._pedido("recado", recado)

    def set_profile_photo(self, foto):
        self._pedido("foto", foto)


def whatsapp(**k):
    p = wa.ProvedorWhatsApp.__new__(wa.ProvedorWhatsApp)
    p.cliente, p._conectada = ClienteWhatsApp(**k), True
    return p


def test_whatsapp_le_o_proprio_perfil():
    p = whatsapp()
    assert p.PODE_EDITAR_PERFIL and not p.PERFIL_SOBRENOME
    assert p.meu_perfil() == {"nome": "Fábio", "recado": "Ocupado"}


def test_whatsapp_salva_so_o_que_mudou_e_conta_o_que_recusou():
    p = whatsapp()
    feitos, erros = p.salvar_perfil({"recado": "Livre"}, b"JPEG")
    assert (feitos, erros) == (["recado", "foto"], [])
    assert p.cliente.chamadas == [("recado", "Livre"), ("foto", b"JPEG")]
    p = whatsapp(recusa={"foto"})
    feitos, erros = p.salvar_perfil({"nome": "Novo"}, b"JPEG")
    assert feitos == ["nome"]
    assert erros[0][0] == "foto" and "WhatsApp" in erros[0][1]


def test_whatsapp_desconectado_nao_tenta():
    p = whatsapp()
    p._conectada = False
    with pytest.raises(base.ErroPerfil):
        p.meu_perfil()
    with pytest.raises(base.ErroPerfil):
        p.salvar_perfil({"nome": "x"})


# ------------------------------------------------------------- Telegram
class ClienteTelegram:
    def __init__(self, erro=None, erro_foto=None):
        self.pedidos, self.erro, self.erro_foto = [], erro, erro_foto

    async def get_me(self):
        return types.SimpleNamespace(first_name="Fábio", last_name="S.")

    async def upload_file(self, arquivo):
        self.arquivo = (arquivo.name, arquivo.read())
        return "enviado"

    async def __call__(self, req):
        nome = type(req).__name__
        if nome == "GetFullUserRequest":
            return types.SimpleNamespace(
                full_user=types.SimpleNamespace(about="Sobre mim"))
        if nome == "UpdateProfileRequest" and self.erro:
            raise self.erro
        if nome == "UploadProfilePhotoRequest" and self.erro_foto:
            raise self.erro_foto
        self.pedidos.append(req)
        return True


def telegram(**k):
    p = tg.ProvedorTelegram.__new__(tg.ProvedorTelegram)
    p.cliente = ClienteTelegram(**k)
    p._executar = lambda corotina, espera=20: asyncio.run(corotina)
    return p


def test_telegram_le_o_proprio_perfil():
    p = telegram()
    assert p.PODE_EDITAR_PERFIL and p.PERFIL_SOBRENOME
    assert p.meu_perfil() == {"nome": "Fábio", "sobrenome": "S.",
                              "recado": "Sobre mim"}


def test_telegram_salva_texto_numa_chamada_so_e_a_foto_a_parte():
    p = telegram()
    feitos, erros = p.salvar_perfil(
        {"nome": "Novo", "recado": "Oi"}, b"JPEG")
    assert (feitos, erros) == (["nome", "recado", "foto"], [])
    atualizar, foto = p.cliente.pedidos
    assert atualizar.first_name == "Novo" and atualizar.about == "Oi"
    assert atualizar.last_name is None            # o sobrenome nao muda
    assert p.cliente.arquivo == ("foto.jpg", b"JPEG")
    assert type(foto).__name__ == "UploadProfilePhotoRequest"


def test_telegram_erros_viram_texto_para_a_pessoa():
    from telethon import errors
    p = telegram(erro=errors.AboutTooLongError(None))
    feitos, erros = p.salvar_perfil({"recado": "x" * 100})
    assert feitos == [] and erros[0][0] == "recado"
    assert "70" in erros[0][1]
    p = telegram(erro_foto=errors.PhotoInvalidError(None))
    feitos, erros = p.salvar_perfil({"nome": "Novo"}, b"x")
    assert feitos == ["nome"] and erros == [
        ("foto", "o Telegram não aceitou essa imagem.")]


def test_telegram_falha_geral_vira_erro_de_perfil():
    p = telegram()

    async def falha(req):
        raise RuntimeError("boom")
    p.cliente = falha
    with pytest.raises(base.ErroPerfil) as e:
        p.meu_perfil()
    assert "Telegram" in str(e.value)


def test_provedor_sem_perfil_diz_que_nao_sabe():
    assert not base.Provedor.PODE_EDITAR_PERFIL
    with pytest.raises(base.ErroPerfil):
        base.Provedor.meu_perfil(None)
    with pytest.raises(base.ErroPerfil):
        base.Provedor.salvar_perfil(None, {})

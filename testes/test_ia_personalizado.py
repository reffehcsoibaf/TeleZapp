# SPDX-License-Identifier: GPL-3.0-or-later
"""Provedor de IA personalizado: qualquer servico com a API de chat da OpenAI."""
import pytest

from telezapp.nucleo import configuracoes as nc
from telezapp.nucleo.ia import catalogo as cat
from telezapp.nucleo.ia import cofre
from telezapp.nucleo.ia import provedores as prov
from telezapp.nucleo.ia.provedores import ErroIA, Midia

IMG = Midia("imagem", "image/png", b"\x89PNGxxxx", "f.png")
AUDIO = Midia("audio", "audio/ogg", b"OggSxxxx", "v.ogg")
PDF = Midia("pdf", "application/pdf", b"%PDF-1", "a.pdf")
P = cat.PERSONALIZADO


@pytest.fixture(autouse=True)
def sem_url():
    prov.definir_url_personalizada("")
    yield
    prov.definir_url_personalizada("")


@pytest.mark.parametrize("entrada,saida", [
    ("https://api.deepseek.com/v1", "https://api.deepseek.com/v1"),
    ("  https://api.deepseek.com/v1/  ", "https://api.deepseek.com/v1"),
    # e comum colar o endereco inteiro
    ("https://api.x.com/v1/chat/completions", "https://api.x.com/v1"),
    ("https://api.x.com/v1/models", "https://api.x.com/v1"),
    ("http://localhost:11434/v1", "http://localhost:11434/v1"),
    ("http://127.0.0.1:1234/v1", "http://127.0.0.1:1234/v1"),
    # a chave nunca vai em texto aberto pela rede
    ("http://exemplo.com/v1", ""),
    ("http://192.168.0.5:11434/v1", ""),
    ("ftp://x.com", ""),
    ("https://usuario:senha@x.com/v1", ""),
    ("https://x.com/v1?chave=1", ""),
    ("https://x.com/v1#a", ""),
    ("https://x.com:99999/v1", ""),
    ("", ""), ("não é endereço", ""),
])
def test_endereco_valido(entrada, saida):
    assert prov.endereco_valido(entrada) == saida


def test_personalizado_faz_texto_e_imagem_mas_nao_voz_nem_pdf():
    assert cat.aceita(P, "texto") and cat.aceita(P, "imagem")
    assert cat.aceita(P, "figurinha")
    assert cat.aceita(P, "video") and not cat.video_nativo(P)  # por quadros
    assert not cat.aceita(P, "audio") and not cat.aceita(P, "pdf")
    assert P in {c for c, _ in cat.provedores_da_tarefa("imagem")}
    assert P not in {c for c, _ in cat.provedores_da_tarefa("audio")}


def test_pedido_de_imagem_vai_ao_endereco_com_o_modelo_e_a_chave():
    prov.definir_url_personalizada("https://api.x.com/v1")
    p = prov.montar_pedido(P, "meu-modelo", "CHAVE", IMG, "instr", "pergunta")
    assert p.url == "https://api.x.com/v1/chat/completions"
    assert p.cabecalhos["Authorization"] == "Bearer CHAVE"
    assert p.json["model"] == "meu-modelo" and "max_tokens" in p.json
    parte = p.json["messages"][1]["content"][1]
    assert parte["type"] == "image_url"
    assert parte["image_url"]["url"].startswith("data:image/png;base64,")


def test_pedido_de_texto_e_de_modelos():
    prov.definir_url_personalizada("http://localhost:11434/v1")
    t = prov.montar_pedido_de_texto(P, "llama", "x", "instr", "oi")
    assert t.url == "http://localhost:11434/v1/chat/completions"
    assert t.json["messages"][1] == {"role": "user", "content": "oi"}
    m = prov.pedido_de_modelos(P, prov.SEM_CHAVE)
    assert m.url == "http://localhost:11434/v1/models" and m.metodo == "GET"


def test_sem_endereco_ou_sem_modelo_o_erro_diz_o_que_falta():
    with pytest.raises(ErroIA) as e:
        prov.montar_pedido(P, "m", "c", IMG, "i", "p")
    assert e.value.codigo == "provedor" and "endereço" in e.value.texto
    prov.definir_url_personalizada("https://api.x.com/v1")
    with pytest.raises(ErroIA) as e:
        prov.montar_pedido(P, "", "c", IMG, "i", "p")
    assert e.value.codigo == "pedido" and "modelo" in e.value.texto
    with pytest.raises(ErroIA):
        prov.montar_pedido_de_texto(P, "  ", "c", "i", "p")
    # codigos que deixam o TeleZapp passar ao proximo provedor da ordem
    from telezapp.nucleo.ia import servico
    assert {"provedor", "pedido"} <= servico.PROXIMO_PROVEDOR


def test_nao_aceita_voz_nem_pdf():
    prov.definir_url_personalizada("https://api.x.com/v1")
    for midia in (AUDIO, PDF):
        with pytest.raises(ErroIA) as e:
            prov.montar_pedido(P, "m", "c", midia, "i", "p")
        assert e.value.codigo == "nao_aceita"


def test_resposta_no_formato_chat_e_lista_de_modelos():
    prov.definir_url_personalizada("https://api.x.com/v1")
    assert prov.ler_resposta(
        P, {"choices": [{"message": {"content": " ola "},
                         "finish_reason": "stop"}]}, "imagem") == "ola"
    with pytest.raises(ErroIA):                    # cortada
        prov.ler_resposta(
            P, {"choices": [{"message": {"content": "x"},
                             "finish_reason": "length"}]}, "imagem")
    assert prov.ler_modelos(P, {"data": [{"id": "llama3"}, {"id": "qwen"}]}) \
        == ["qwen", "llama3"]


def test_endereco_invalido_desliga_o_provedor():
    assert prov.definir_url_personalizada("https://api.x.com/v1")
    assert prov.definir_url_personalizada("http://exemplo.com") == ""
    with pytest.raises(ErroIA):
        prov.montar_pedido(P, "m", "c", IMG, "i", "p")


def test_chave_do_personalizado_fica_no_cofre(tmp_path):
    c = cofre.Cofre(str(tmp_path / "ia_chaves.json"))
    assert not c.tem(P)
    c.guardar(P, prov.SEM_CHAVE)
    assert c.tem(P) and c.obter(P) == prov.SEM_CHAVE
    assert P in c.provedores_com_chave()


def test_endereco_pendente_so_aparece_quando_muda(tmp_path):
    from telezapp import config
    cfg = config.Config(str(tmp_path / "config.json"))
    m = nc.ModeloConfiguracoes(cfg)
    assert m.ia_url_atual() == "" and m.ia_mudancas() is None
    m.ia_definir_url("https://api.x.com/v1")
    assert m.ia_url_atual() == "https://api.x.com/v1"
    assert m.ia_mudancas()["url"] == "https://api.x.com/v1"
    cfg.set("ia_url_personalizada", "https://api.x.com/v1")
    m.ia_definir_url("https://api.x.com/v1")        # igual ao guardado
    assert m.ia_mudancas() is None


def test_de_ponta_a_ponta_com_um_servidor_local(tmp_path):
    """Um servidor de verdade em 127.0.0.1 (como o Ollama): o caminho de rede
    do programa leva a chave, o modelo e a imagem, e le a resposta."""
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from telezapp.nucleo.ia import servico
    vistos = []

    class Falso(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _responder(self, corpo):
            dados = json.dumps(corpo).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def do_GET(self):
            vistos.append(("GET", self.path, self.headers["Authorization"]))
            self._responder({"data": [{"id": "llama3"}]})

        def do_POST(self):
            n = int(self.headers["Content-Length"])
            corpo = json.loads(self.rfile.read(n))
            vistos.append(("POST", self.path, self.headers["Authorization"],
                           corpo["model"]))
            self._responder({"choices": [{"message": {"content": "OK"},
                                          "finish_reason": "stop"}]})

    servidor = HTTPServer(("127.0.0.1", 0), Falso)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        prov.definir_url_personalizada(
            "http://127.0.0.1:%d/v1/chat/completions" % servidor.server_port)
        assert servico.listar_modelos(P, prov.SEM_CHAVE) == ["llama3"]
        assert servico.testar(P, prov.SEM_CHAVE, "llama3") == "OK"
    finally:
        servidor.shutdown()
    assert vistos[0] == ("GET", "/v1/models", "Bearer sem-chave")
    assert vistos[1] == ("POST", "/v1/chat/completions", "Bearer sem-chave",
                         "llama3")

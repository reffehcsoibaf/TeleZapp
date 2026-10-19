# SPDX-License-Identifier: GPL-3.0-or-later
"""Provedores de IA: pedidos, respostas, erros e o cofre de chaves."""
import pytest

from telezapp.nucleo.ia import catalogo as cat
from telezapp.nucleo.ia import cofre, prompts, servico
from telezapp.nucleo.ia import provedores as prov
from telezapp.nucleo.ia.provedores import ErroIA, Midia

IMG = Midia("imagem", "image/png", b"\x89PNGxxxx", "f.png")
AUDIO = Midia("audio", "audio/ogg", b"OggSxxxx", "v.ogg")
PDF = Midia("pdf", "application/pdf", b"%PDF-1", "a.pdf")
VIDEO = Midia("video", "video/mp4", b"....ftyp", "v.mp4")


def pedido(provedor, midia, modelo="m", perfil="medio"):
    return prov.montar_pedido(provedor, modelo, "CHAVE", midia, "instr",
                              "pergunta", perfil)


def test_cada_tarefa_tem_provedores_e_so_o_gemini_ve_video():
    assert [c for c, _ in cat.provedores_da_tarefa("video")] == ["gemini"]
    assert {c for c, _ in cat.provedores_da_tarefa("audio")} == {
        "gemini", "openai", "groq"}
    assert {c for c, _ in cat.provedores_da_tarefa("pdf")} == {
        "gemini", "openai", "claude", "openrouter"}
    assert cat.aceita("claude", "figurinha")
    assert not cat.aceita("claude", "audio")
    assert cat.modelo_de("openai", {"openai": " gpt-x "}) == "gpt-x"
    assert cat.modelo_de("openai", {}) == cat.PROVEDORES["openai"].modelo


def test_pedido_openai_imagem_pdf_e_transcricao_de_audio():
    p = pedido("openai", IMG, perfil="curto")
    assert p.url.endswith("/responses")
    assert p.cabecalhos["Authorization"] == "Bearer CHAVE"
    parte = p.json["input"][0]["content"][0]
    assert parte["type"] == "input_image" and parte["detail"] == "low"
    assert parte["image_url"].startswith("data:image/png;base64,")
    assert pedido("openai", PDF).json["input"][0]["content"][0]["type"] == \
        "input_file"
    t = pedido("openai", AUDIO)
    assert t.url.endswith("/audio/transcriptions") and t.json is None
    assert b'name="model"' in t.corpo and b"OggSxxxx" in t.corpo
    assert "boundary=" in t.cabecalhos["Content-Type"]


def test_pedidos_do_gemini_claude_e_chat():
    g = pedido("gemini", AUDIO, "gemini-x")
    assert g.url.endswith("/models/gemini-x:generateContent")
    assert g.cabecalhos == {"x-goog-api-key": "CHAVE"}
    partes = g.json["contents"][0]["parts"]
    assert partes[0]["inline_data"]["mime_type"] == "audio/ogg"
    video = pedido("gemini", VIDEO).json["contents"][0]["parts"][0]
    assert video["inline_data"]["mime_type"] == "video/mp4"
    c = pedido("claude", PDF)
    assert c.cabecalhos["x-api-key"] == "CHAVE"
    assert c.json["messages"][0]["content"][0]["type"] == "document"
    imagem = pedido("claude", IMG).json["messages"][0]["content"][0]
    assert imagem["type"] == "image"
    o = pedido("openrouter", IMG)
    assert o.url.endswith("/chat/completions")
    assert o.json["messages"][1]["content"][1]["type"] == "image_url"
    assert pedido("groq", AUDIO).url.startswith(
        "https://api.groq.com/openai/v1/audio/transcriptions")


def test_pedido_que_o_provedor_nao_aceita_vira_erro():
    with pytest.raises(ErroIA) as e:
        pedido("claude", AUDIO)
    assert e.value.codigo == "nao_aceita"
    with pytest.raises(ErroIA):
        pedido("openai", VIDEO)
    grande = Midia("imagem", "image/jpeg", b"x" * 4_000_000, "g.jpg")
    with pytest.raises(ErroIA) as e:
        pedido("groq", grande)
    assert e.value.codigo == "grande"


def test_leitura_das_respostas_de_cada_provedor():
    assert prov.ler_resposta("openai", {"text": " ola "}, "audio") == "ola"
    saida = {"output": [{"type": "message", "content": [
        {"type": "output_text", "text": "uma foto"}]}]}
    assert prov.ler_resposta("openai", saida, "imagem") == "uma foto"
    gemini = {"candidates": [{"content": {"parts": [
        {"text": "pensando", "thought": True}, {"text": "resposta"}]}}]}
    assert prov.ler_resposta("gemini", gemini, "imagem") == "resposta"
    claude = {"content": [{"type": "text", "text": "descricao"}]}
    assert prov.ler_resposta("claude", claude, "imagem") == "descricao"
    chat = {"choices": [{"message": {"content": "texto"},
                         "finish_reason": "stop"}]}
    assert prov.ler_resposta("groq", chat, "imagem") == "texto"
    assert prov.ler_resposta("groq", {"text": "fala"}, "audio") == "fala"
    longa = {"content": [{"type": "text", "text": "a" * 20000}]}
    assert len(prov.ler_resposta("claude", longa, "imagem")) == \
        cat.MAX_CARACTERES["imagem"]


def test_respostas_recusadas_cortadas_vazias_ou_estranhas():
    casos = [
        ("gemini", {"promptFeedback": {"blockReason": "SAFETY"}}, "recusa"),
        ("gemini", {"candidates": [{"finishReason": "MAX_TOKENS"}]},
         "resposta"),
        ("claude", {"stop_reason": "refusal"}, "recusa"),
        ("claude", {"stop_reason": "max_tokens", "content": []}, "resposta"),
        ("openai", {"status": "incomplete"}, "resposta"),
        ("openrouter", {"choices": [{"message": {"refusal": "x"}}]},
         "recusa"),
        ("claude", {"content": []}, "vazia"),
        ("openai", {"output": "bagunca"}, "resposta"),
    ]
    for provedor, corpo, codigo in casos:
        with pytest.raises(ErroIA) as e:
            prov.ler_resposta(provedor, corpo, "imagem")
        assert e.value.codigo == codigo, (provedor, corpo)


def test_executar_valida_provedor_chave_e_arquivo(tmp_path):
    arq = tmp_path / "f.png"
    arq.write_bytes(b"\x89PNG" + b"0" * 20)
    visto = []

    def enviar(p):
        visto.append(p)
        return {"content": [{"type": "text", "text": "um quadrado"}]}
    r = servico.executar("imagem", str(arq), "claude", "K", "m-x", "curto",
                         enviar)
    assert (r.texto, r.provedor, r.modelo) == (
        "um quadrado", "Claude (Anthropic)", "m-x")
    assert visto[0].json["model"] == "m-x"
    casos = (
        (("imagem", str(arq), "nenhum", "K", "m"), "provedor"),
        (("imagem", str(arq), "claude", "", "m"), "chave"),
        (("audio", str(arq), "claude", "K", "m"), "nao_aceita"),
        (("imagem", str(tmp_path / "x"), "claude", "K", "m"), "arquivo"))
    for args, codigo in casos:
        with pytest.raises(ErroIA) as e:
            servico.executar(*args, enviar=enviar)
        assert e.value.codigo == codigo
    vazio = tmp_path / "v.png"
    vazio.write_bytes(b"")
    with pytest.raises(ErroIA):
        servico.carregar_midia(str(vazio), "imagem")


def test_tipo_mime_pelo_conteudo_e_limite_de_tamanho(tmp_path, monkeypatch):
    casos = {b"%PDF-1.7": ("application/pdf", "pdf"),
             b"OggS\x00": ("audio/ogg", "audio"),
             b"RIFF\x00\x00\x00\x00WEBPVP8 ": ("image/webp", "imagem"),
             b"\xff\xd8\xff\xe0": ("image/jpeg", "imagem")}
    for i, (dados, (mime, genero)) in enumerate(casos.items()):
        arq = tmp_path / ("a%d.bin" % i)
        arq.write_bytes(dados + b"0" * 30)
        assert servico.carregar_midia(str(arq), genero).mime == mime
    monkeypatch.setitem(cat.LIMITE_BYTES, "imagem", 10)
    grande = tmp_path / "g.jpg"
    grande.write_bytes(b"\xff\xd8" + b"0" * 100)
    with pytest.raises(ErroIA) as e:
        servico.carregar_midia(str(grande), "imagem")
    assert e.value.codigo == "grande"


def test_erros_http_viram_texto_para_a_pessoa():
    assert servico._erro_http(401).codigo == "chave"
    assert servico._erro_http(429).codigo == "limite"
    cota = ('{"error": {"message": "You exceeded your current quota, please '
            'check your plan and billing details.", "type": '
            '"insufficient_quota", "code": "insufficient_quota"}}')
    e = servico._erro_http(429, cota)
    assert e.codigo == "saldo" and "sem créditos" in e.texto
    assert "exceeded your current quota" in e.texto
    assert servico._erro_http(402).codigo == "saldo"
    assert servico._erro_http(
        429, '{"error":{"message":"Rate limit reached for requests"}}'
    ).codigo == "limite"
    assert servico._erro_http(413).codigo == "grande"
    assert servico._erro_http(404).codigo == "pedido"
    assert servico._erro_http(503).codigo == "provedor"


def test_teste_de_chave_manda_um_pedido_minimo():
    visto = []

    def enviar(p):
        visto.append(p)
        return {"candidates": [{"content": {"parts": [{"text": "OK"}]}}]}
    assert servico.testar("gemini", "K", "gemini-x", enviar) == "OK"
    parte = visto[0].json["contents"][0]["parts"][0]
    assert len(parte["inline_data"]["data"]) < 400


def test_cofre_guarda_a_chave_sem_deixa_la_legivel(tmp_path):
    c = cofre.Cofre(str(tmp_path / "ia.json"))
    assert not c.tem("openai") and c.obter("openai") == ""
    c.guardar("openai", "  sk-segredo-123  ")
    assert c.tem("openai") and c.obter("openai") == "sk-segredo-123"
    assert "sk-segredo" not in (tmp_path / "ia.json").read_text()
    assert c.provedores_com_chave() == ["openai"]
    c.guardar("openai", "")
    assert not c.tem("openai")
    with pytest.raises(ValueError):
        c.guardar("desconhecido", "x")


def test_instrucoes_dizem_o_que_fazer_com_cada_genero():
    assert "transcribe" in prompts.instrucoes("audio")
    assert "[Image:" in prompts.instrucoes("pdf")
    assert "Brazilian Portuguese" in prompts.instrucoes("imagem", "curto")
    assert "over time" in prompts.instrucoes("video")


def test_modo_automatico_tenta_o_proximo_modelo_se_o_primeiro_falha(tmp_path):
    arq = tmp_path / "f.png"
    arq.write_bytes(b"\x89PNG" + b"0" * 20)
    assert cat.cadeia_de_modelos("gemini", {}) == [
        "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]
    assert cat.cadeia_de_modelos("gemini", {"gemini": " meu "}) == ["meu"]
    assert cat.cadeia_de_modelos("openai", {}) == [
        cat.PROVEDORES["openai"].modelo]
    usados = []

    def enviar(p):
        usados.append(p.url)
        if "3.8" in p.url:
            raise ErroIA("limite", "limite")
        if "3.6" in p.url:
            raise ErroIA("pedido", "modelo")
        return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
    r = servico.executar("imagem", str(arq), "gemini", "K",
                         cat.cadeia_de_modelos("gemini", {}), "curto", enviar)
    assert r.texto == "ok" and r.modelo == "gemini-3.5-flash-lite"
    assert len(usados) == 3
    # o modelo escolhido pela pessoa nao troca sozinho
    with pytest.raises(ErroIA):
        servico.executar("imagem", str(arq), "gemini", "K", ["meu"], "curto",
                         enviar=lambda p: (_ for _ in ()).throw(
                             ErroIA("limite", "limite")))
    # chave recusada nao adianta tentar outro
    chamadas = []

    def recusa(p):
        chamadas.append(1)
        raise ErroIA("chave", "chave")
    with pytest.raises(ErroIA):
        servico.executar("imagem", str(arq), "gemini", "K",
                         cat.cadeia_de_modelos("gemini", {}), "curto", recusa)
    assert len(chamadas) == 1


def test_lista_de_modelos_de_cada_provedor_sem_os_que_nao_servem():
    gemini = {"models": [
        {"name": "models/gemini-3.8-flash",
         "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.8-flash-tts",
         "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-embedding-2",
         "supportedGenerationMethods": ["embedContent"]},
        {"name": "models/gemini-3.5-flash-lite",
         "supportedGenerationMethods": ["generateContent"]}]}
    assert prov.ler_modelos("gemini", gemini) == [
        "gemini-3.8-flash", "gemini-3.5-flash-lite"]
    openai = {"data": [{"id": "gpt-4.1-mini"}, {"id": "whisper-1"},
                       {"id": "text-embedding-3-small"},
                       {"id": "gpt-4o-realtime-preview"}, {"id": "o4-mini"}]}
    assert prov.ler_modelos("openai", openai) == ["o4-mini", "gpt-4.1-mini"]
    claude = {"data": [{"id": "claude-haiku-5-5"}, {"id": "claude-sonnet-5-5"}]}
    assert prov.ler_modelos("claude", claude) == [
        "claude-sonnet-5-5", "claude-haiku-5-5"]
    groq = {"data": [{"id": "whisper-large-v3-turbo"}, {"id": "qwen/qwen3-x"},
                     {"id": "llama-guard-4"}]}
    assert prov.ler_modelos("groq", groq) == ["qwen/qwen3-x"]
    router = {"data": [
        {"id": "a/ve", "architecture": {"input_modalities": ["text", "image"]}},
        {"id": "b/so-texto", "architecture": {"input_modalities": ["text"]}}]}
    assert prov.ler_modelos("openrouter", router) == ["a/ve"]
    with pytest.raises(ErroIA):
        prov.ler_modelos("claude", {"erro": 1})


def test_pedidos_de_lista_sao_get_e_usam_a_chave_do_provedor():
    for provedor, cabecalho in (("gemini", "x-goog-api-key"),
                                ("openai", "Authorization"),
                                ("claude", "x-api-key"),
                                ("groq", "Authorization"),
                                ("openrouter", "Authorization")):
        p = prov.pedido_de_modelos(provedor, "CHAVE")
        assert p.metodo == "GET" and p.json is None and p.corpo is None
        assert "CHAVE" in p.cabecalhos[cabecalho]
    visto = []
    assert servico.listar_modelos(
        "openai", "K", lambda p: visto.append(p) or {"data": [
            {"id": "gpt-4.1-mini"}]}) == ["gpt-4.1-mini"]
    with pytest.raises(ErroIA) as e:
        servico.listar_modelos("openai", "", lambda p: {})
    assert e.value.codigo == "chave"
    with pytest.raises(ErroIA):
        servico.listar_modelos("openai", "K", lambda p: {"data": []})


def test_provedores_na_ordem_escolhida_passam_ao_proximo_se_um_falha(tmp_path):
    arq = tmp_path / "v.ogg"
    arq.write_bytes(b"OggS" + b"0" * 30)
    chamados = []

    def enviar(p):
        host = p.url.split("/")[2]
        chamados.append(host)
        if host == "api.openai.com":
            raise ErroIA("limite", "limite")
        if host == "api.groq.com":
            return {"text": "fala"}
        raise AssertionError("nao devia chegar aqui")
    chaves = {"openai": "A", "groq": "B", "gemini": "C"}
    r = servico.executar_em_ordem(
        "audio", str(arq), ["openai", "groq", "gemini"], chaves.get, {},
        "medio", enviar)
    assert r.texto == "fala" and r.provedor == "Groq"
    assert chamados == ["api.openai.com", "api.groq.com"]
    # provedor sem chave ou que nao faz a tarefa e pulado
    chamados.clear()
    r = servico.executar_em_ordem(
        "audio", str(arq), ["claude", "gemini", "groq"], {"groq": "B"}.get,
        {}, "medio", enviar)
    assert chamados == ["api.groq.com"]
    # todos falham: o erro do ultimo, com o nome do provedor
    with pytest.raises(ErroIA) as e:
        servico.executar_em_ordem(
            "audio", str(arq), ["openai"], chaves.get, {}, "medio",
            lambda p: (_ for _ in ()).throw(ErroIA("chave", "recusou")))
    assert e.value.texto == "OpenAI: recusou"
    # problema do arquivo nao vai para o proximo
    with pytest.raises(ErroIA) as e:
        servico.executar_em_ordem("audio", str(tmp_path / "nao"), ["openai",
                                  "groq"], chaves.get, {}, "medio", enviar)
    assert e.value.codigo == "arquivo"
    with pytest.raises(ErroIA) as e:
        servico.executar_em_ordem("audio", str(arq), ["claude"], chaves.get,
                                  {}, "medio", enviar)
    assert e.value.codigo == "provedor"


def test_toda_chamada_leva_um_user_agent_do_telezapp(monkeypatch):
    """Sem ele a Groq (Cloudflare) devolve 403, erro 1010, que parecia chave
    recusada."""
    vistos = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return b'{"ok": true}'

    def abre(req, timeout=None):
        vistos.append(dict(req.header_items()))
        return Resp()
    monkeypatch.setattr(servico.urllib.request, "urlopen", abre)
    for p in (prov.pedido_de_modelos("groq", "K"),
              pedido("openai", AUDIO), pedido("claude", IMG)):
        assert servico.enviar_pela_rede(p) == {"ok": True}
    assert all(h["User-agent"].startswith("TeleZapp/") for h in vistos)


def test_chave_que_o_gemini_chama_de_pedido_invalido_ainda_e_chave():
    assert servico._erro_http(
        400, '{"error": {"message": "API key not valid. Please pass a '
             'valid API key."}}').codigo == "chave"
    assert servico._erro_http(400, "").codigo == "pedido"
    assert servico._erro_http(
        401, '{"error":{"code":"invalid_api_key"}}').codigo == "chave"


def test_erro_de_modelo_mostra_o_que_o_provedor_reclamou():
    texto = servico._erro_http(
        400, '{"error":{"message":"The model `x` does not exist."}}').texto
    assert "erro 400): The model `x` does not exist. Confira" in texto
    assert servico._erro_http(404, "").texto.endswith(
        "(erro 404). Confira o modelo escolhido.")
    longo = servico._erro_http(400, '{"error":{"message":"%s"}}' % ("a" * 500))
    assert "..." in longo.texto and len(longo.texto) < 400


def test_groq_pede_max_completion_tokens_e_o_openrouter_max_tokens():
    assert "max_completion_tokens" in pedido("groq", IMG).json
    assert "max_tokens" not in pedido("groq", IMG).json
    assert "max_tokens" in pedido("openrouter", IMG).json


def test_imagem_de_teste_e_um_png_valido_e_maior_que_1_pixel():
    import struct
    png = servico.PNG_MINIMO
    assert png[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
    largura, altura = struct.unpack(">II", png[16:24])
    assert (largura, altura) == (64, 64) and len(png) < 400

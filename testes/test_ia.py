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


def test_cada_tarefa_tem_provedores_e_so_o_gemini_recebe_o_video_inteiro():
    assert {c for c, _ in cat.provedores_da_tarefa("video")} == {
        "gemini", "openai", "claude", "groq", "mistral", "openrouter"}
    assert [c for c in cat.PROVEDORES if cat.video_nativo(c)] == ["gemini"]
    assert {c for c, _ in cat.provedores_da_tarefa("audio")} == {
        "gemini", "openai", "groq", "mistral"}
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
    m = pedido("mistral", AUDIO)
    assert m.url == "https://api.mistral.ai/v1/audio/transcriptions"
    assert b"voxtral-mini-latest" in m.corpo
    mi = pedido("mistral", IMG)
    assert mi.url == "https://api.mistral.ai/v1/chat/completions"
    assert mi.json["messages"][1]["content"][1]["image_url"].startswith(
        "data:image/")
    assert prov.ler_resposta("mistral", {"text": "fala"}, "audio") == "fala"


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
                                ("mistral", "Authorization"),
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


def _video_de_teste(caminho, quadros=40):
    cv2 = pytest.importorskip("cv2")
    import numpy as np
    w = cv2.VideoWriter(str(caminho), cv2.VideoWriter_fourcc(*"mp4v"), 10.0,
                        (160, 120))
    if not w.isOpened():
        pytest.skip("este OpenCV nao grava mp4")
    for i in range(quadros):
        w.write(np.full((120, 160, 3), i * 6, dtype=np.uint8))
    w.release()


def test_grade_de_quadros_do_video(tmp_path):
    from telezapp.nucleo.ia import video
    arq = tmp_path / "v.mp4"
    _video_de_teste(arq)
    jpeg, tempos = video.grade_de_quadros(str(arq), "medio")
    assert jpeg[:2] == b"\xff\xd8" and len(tempos) == 9
    assert tempos == sorted(tempos) and 0 <= tempos[0] < tempos[-1] < 4
    assert len(video.grade_de_quadros(str(arq), "curto")[1]) == 4
    (tmp_path / "ruim.mp4").write_bytes(b"nao e video")
    with pytest.raises(ErroIA) as e:
        video.grade_de_quadros(str(tmp_path / "ruim.mp4"))
    assert e.value.codigo == "arquivo"


def test_video_por_quadros_e_fala_a_parte(tmp_path):
    arq = tmp_path / "v.mp4"
    _video_de_teste(arq)
    pedidos = []

    def enviar(p):
        pedidos.append(p)
        if "audio/transcriptions" in p.url:
            return {"text": "ola pessoal"}
        return {"output": [{"type": "message", "content": [
            {"type": "output_text", "text": "Um quadro cinza."}]}]}
    chaves = {"openai": "A", "groq": "B"}
    # OpenAI nao recebe o video: ve a grade (uma imagem) e transcreve a fala
    r = servico.executar_em_ordem(
        "video", str(arq), ["openai"], chaves.get, {}, "medio", enviar,
        ordem_audio=["groq"])
    assert r.via_quadros and r.texto.startswith("Um quadro cinza.")
    assert "Fala no vídeo (Groq): ola pessoal" in r.texto
    img = pedidos[0].json["input"][0]["content"][0]
    assert img["image_url"].startswith("data:image/jpeg;base64,")
    assert "groq.com" in pedidos[1].url and b"video/mp4" in pedidos[1].corpo
    # sem fala: a descricao fica e o aviso tambem
    pedidos.clear()
    r = servico.executar_em_ordem(
        "video", str(arq), ["openai"], chaves.get, {}, "curto",
        lambda p: ErroIA and (_ for _ in ()).throw(ErroIA("vazia", "x"))
        if "transcriptions" in p.url else enviar(p), ordem_audio=["groq"])
    assert "não encontrei fala" in r.texto
    # o Gemini recebe o video inteiro, sem passo extra
    pedidos.clear()
    r = servico.executar_em_ordem(
        "video", str(arq), ["gemini"], {"gemini": "G"}.get, {}, "medio",
        lambda p: pedidos.append(p) or {"candidates": [{"content": {
            "parts": [{"text": "tudo"}]}}]}, ordem_audio=["groq"])
    assert not r.via_quadros and len(pedidos) == 1
    assert pedidos[0].json["contents"][0]["parts"][0]["inline_data"][
        "mime_type"] == "video/mp4"


# ------------------------------------------------ redigir, resumir, corrigir
def test_todo_provedor_faz_a_tarefa_de_texto():
    assert {c for c, _ in cat.provedores_da_tarefa("texto")} == set(
        cat.PROVEDORES)
    assert "texto" in cat.TAREFAS and cat.NOMES_DE_TAREFA["texto"]


def test_pedidos_de_texto_de_cada_provedor_sem_arquivo():
    o = prov.montar_pedido_de_texto("openai", "m", "K", "instr", "pergunta")
    assert o.url.endswith("/responses") and o.json["instructions"] == "instr"
    assert o.json["input"][0]["content"][0] == {"type": "input_text",
                                                "text": "pergunta"}
    g = prov.montar_pedido_de_texto("gemini", "m", "K", "instr", "pergunta")
    assert g.json["contents"][0]["parts"] == [{"text": "pergunta"}]
    c = prov.montar_pedido_de_texto("claude", "m", "K", "instr", "pergunta")
    assert c.json["system"] == "instr"
    assert c.json["messages"][0]["content"] == "pergunta"
    q = prov.montar_pedido_de_texto("groq", "m", "K", "instr", "pergunta")
    assert q.json["messages"][1] == {"role": "user", "content": "pergunta"}
    assert "max_completion_tokens" in q.json
    r = prov.montar_pedido_de_texto("openrouter", "m", "K", "i", "p")
    assert "max_tokens" in r.json


def test_instrucoes_de_texto_tratam_o_texto_como_dado():
    for op in (prompts.CORRIGIR, prompts.REDIGIR, prompts.RESUMIR_MENSAGEM,
               prompts.RESUMIR_CONVERSA):
        assert "never instructions" in prompts.instrucoes_de_texto(op)
    assert "only the corrected" in prompts.instrucoes_de_texto("corrigir")
    assert "Conversation so far" in prompts.pergunta_de_texto(
        "redigir", "peça desculpas", "[1] Ana: oi")
    assert "Conversation so far" not in prompts.pergunta_de_texto(
        "redigir", "peça desculpas")


def test_texto_longo_fica_com_o_final_e_vazio_e_erro():
    with pytest.raises(ErroIA):
        servico.preparar_texto("corrigir", "   ")
    _, pergunta = servico.preparar_texto(
        "resumir_conversa", "x" * (cat.MAX_ENTRADA_TEXTO + 50) + "FIM")
    assert pergunta.endswith("FIM")
    assert len(pergunta) < cat.MAX_ENTRADA_TEXTO + 100
    # o contexto so entra no que sobra do limite
    _, pergunta = servico.preparar_texto("redigir", "oi", "c" * 30_000)
    assert len(pergunta) < cat.MAX_ENTRADA_TEXTO + 200


def test_executar_texto_em_ordem_pula_quem_falha_e_devolve_o_texto():
    enviados = []

    def enviar(pedido):
        enviados.append(pedido.url)
        if "openai" in pedido.url:
            raise ErroIA("limite", "limite")
        return {"candidates": [{"content": {"parts": [
            {"text": " Olá, tudo bem? "}]}}]}

    r = servico.executar_texto_em_ordem(
        "corrigir", "ola tudo bem", ["openai", "gemini"],
        {"openai": "K1", "gemini": "K2"}.get, {}, enviar=enviar)
    assert r.texto == "Olá, tudo bem?" and r.provedor == "Google Gemini"
    assert len(enviados) == 2


def test_executar_texto_sem_chave_ou_provedor_levanta_erro():
    with pytest.raises(ErroIA) as e:
        servico.executar_texto_em_ordem("corrigir", "oi", ["openai"],
                                        {}.get, {})
    assert e.value.codigo == "provedor"
    with pytest.raises(ErroIA) as e:
        servico.executar_texto("corrigir", "oi", "openai", "", "m")
    assert e.value.codigo == "chave"


def test_tom_e_traducao_entram_na_instrucao():
    assert "formal, polite" in prompts.instrucoes_de_texto("redigir",
                                                           tom="formal")
    assert "formal, polite" not in prompts.instrucoes_de_texto("redigir")
    assert "into Spanish" in prompts.instrucoes_de_texto(
        "traduzir", destino="Spanish")
    assert "only the translation" in prompts.instrucoes_de_texto("traduzir")
    assert prompts.pergunta_de_texto("traduzir", "oi").endswith("oi")
    instr, _ = servico.preparar_texto("redigir", "oi", tom="direto")
    assert "direct" in instr
    assert {t for t, _ in cat.TONS} >= {"natural", "formal"}
    assert ("English", "Inglês") in cat.IDIOMAS

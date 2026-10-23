"""Corretor ortografico: a revisao passo a passo (com um corretor falso) e,
onde o Windows tem o dicionario, o verificador de verdade."""
import sys

import pytest

from telezapp.nucleo import ortografia as ort


class CorretorFalso:
    """Marca como erro as palavras da lista `erradas`."""
    disponivel = True
    idioma = "pt-BR"

    def __init__(self, erradas):
        self.erradas = dict(erradas)      # palavra -> sugestoes
        self.adicionadas, self.ignoradas = [], []

    def verificar(self, texto):
        achados, i = [], 0
        for palavra in texto.split(" "):
            limpa = palavra.strip(".,!?")
            if limpa in self.erradas and limpa not in self.ignoradas \
                    and limpa not in self.adicionadas:
                ini = i + palavra.index(limpa)
                achados.append(ort.Erro(ini, len(limpa), limpa,
                                        ort.ACAO_SUGERIR))
            i += len(palavra) + 1
        return achados

    def sugerir(self, palavra, maximo=8):
        return list(self.erradas[palavra])

    def adicionar(self, palavra):
        self.adicionadas.append(palavra)

    def ignorar(self, palavra):
        self.ignoradas.append(palavra)


def test_trocar_um_erro_e_seguir_para_o_proximo():
    c = CorretorFalso({"goistaria": ["gostaria"], "pao": ["pão", "pano"]})
    r = ort.Revisao(c, "Eu goistaria de um pao.")
    assert r.erro.palavra == "goistaria"
    assert r.erro.sugestoes == ["gostaria"]
    r.substituir("gostaria")
    assert r.texto == "Eu gostaria de um pao."
    assert r.erro.palavra == "pao"
    r.substituir("pão")
    assert r.texto == "Eu gostaria de um pão."
    assert r.erro is None and r.trocas == 2


def test_trocar_todas_troca_todas_as_ocorrencias():
    c = CorretorFalso({"kasa": ["casa"]})
    r = ort.Revisao(c, "kasa velha, kasa nova, kasa")
    r.substituir("casa", todas=True)
    assert r.texto == "casa velha, casa nova, casa"
    assert r.erro is None and r.trocas == 3


def test_ignorar_uma_vez_pula_so_esta_ocorrencia():
    c = CorretorFalso({"zap": ["zip"]})
    r = ort.Revisao(c, "zap e zap")
    r.ignorar()
    assert r.erro.inicio == 6
    r.ignorar()
    assert r.erro is None and r.texto == "zap e zap"


def test_ignorar_todas_e_adicionar_ao_dicionario():
    c = CorretorFalso({"zap": [], "telezapp": []})
    r = ort.Revisao(c, "zap telezapp zap")
    r.ignorar(sempre=True)
    assert c.ignoradas == ["zap"] and r.erro.palavra == "telezapp"
    r.adicionar()
    assert c.adicionadas == ["telezapp"] and r.erro is None


def test_texto_sem_erro_nao_abre_revisao():
    r = ort.Revisao(CorretorFalso({}), "tudo certo")
    assert r.erro is None and r.trocas == 0


def test_corretor_indisponivel_nao_marca_nada():
    c = ort.Corretor("xx-YY")
    assert not c.disponivel
    assert c.verificar("qualquer coisa") == []
    assert c.sugerir("coisa") == []


@pytest.mark.skipif(sys.platform != "win32", reason="so no Windows")
def test_verificador_do_windows_acha_erro_depois_de_emoji():
    c = ort.Corretor("pt-BR")
    if not c.disponivel:
        pytest.skip("sem dicionario pt-BR neste Windows")
    texto = "Olá 😀 eu goistaria de um café"
    erros = c.verificar(texto)
    assert [e.palavra for e in erros] == ["goistaria"]
    assert texto[erros[0].inicio:erros[0].inicio + erros[0].tamanho] == \
        "goistaria"
    assert "gostaria" in c.sugerir("goistaria")
    assert c.verificar("Eu gostaria de um café.") == []

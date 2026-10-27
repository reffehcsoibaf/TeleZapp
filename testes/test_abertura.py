# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Os registros da abertura do programa (para achar onde ela demora ou cai)."""
import logging

from telezapp import __main__ as principal


def test_etapa_registra_o_tempo_desde_o_inicio(caplog):
    log = logging.getLogger("telezapp.teste_abertura")
    with caplog.at_level(logging.INFO, logger=log.name):
        principal.etapa(log, "janela mostrada")
    assert "abertura: janela mostrada (" in caplog.text
    assert "s desde o início)" in caplog.text


def test_ambiente_registra_sistema_python_e_pasta_de_dados(caplog):
    log = logging.getLogger("telezapp.teste_abertura")
    with caplog.at_level(logging.INFO, logger=log.name):
        principal.descrever_ambiente(log)
    assert "ambiente:" in caplog.text and "Python" in caplog.text
    assert "dados em" in caplog.text


def test_marca_de_sessao_conta_quando_foi_o_ultimo_sinal(tmp_path):
    marca = tmp_path / "sessao-aberta"
    principal.escrever_marca(str(marca))
    texto = principal.descrever_marca(str(marca))
    assert "O último sinal da vez anterior foi às" in texto
    assert "há 0 min" in texto


def test_marca_antiga_so_com_o_numero_do_processo(tmp_path):
    marca = tmp_path / "sessao-aberta"
    marca.write_text("13620")
    assert "não traz a hora" in principal.descrever_marca(str(marca))


def test_erro_nativo_do_windows_vai_para_o_arquivo(tmp_path):
    import ctypes
    import sys
    import pytest
    if sys.platform != "win32":
        pytest.skip("so no Windows")
    k = ctypes.windll.kernel32
    k.WriteFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                            ctypes.c_uint32,
                            ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
    k.GetStdHandle.restype = ctypes.c_void_p
    k.GetStdHandle.argtypes = [ctypes.c_uint32]
    k.SetStdHandle.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    caminho = tmp_path / "falha.log"
    with open(caminho, "w") as f:
        anterior = principal.redirecionar_erro_nativo(f)
        try:
            h = k.GetStdHandle(principal.STD_ERROR_HANDLE & 0xFFFFFFFF)
            escritos = ctypes.c_uint32()
            k.WriteFile(h, b"fatal error: teste\n", 19,
                        ctypes.byref(escritos), None)
        finally:
            k.SetStdHandle(principal.STD_ERROR_HANDLE & 0xFFFFFFFF,
                           anterior)
    assert "fatal error: teste" in caminho.read_text()


def test_main_nao_tem_import_local_que_esconde_um_modulo_do_topo():
    """Um `import x` dentro de main() faz de `x` variavel local da funcao
    toda: usar `x` antes dele da UnboundLocalError ao abrir o programa."""
    import ast
    import inspect
    arvore = ast.parse(inspect.getsource(principal))
    main = next(n for n in ast.walk(arvore)
                if isinstance(n, ast.FunctionDef) and n.name == "main")
    topo = {a.asname or a.name for n in arvore.body
            if isinstance(n, ast.Import) for a in n.names}
    locais = {a.asname or a.name for n in ast.walk(main)
              if isinstance(n, ast.Import) for a in n.names}
    assert not (topo & locais), topo & locais

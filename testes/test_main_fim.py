"""O fim do programa: termina o processo sem passar pelo descarregar das DLLs."""
import subprocess
import sys


def test_terminar_ja_encerra_o_processo_com_o_codigo():
    r = subprocess.run(
        [sys.executable, "-c",
         "from telezapp.__main__ import terminar_ja; print('antes', flush=True);"
         " terminar_ja(7); print('depois')"],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 7
    assert "antes" in r.stdout and "depois" not in r.stdout

"""O instalador (ferramentas/empacotar/Instalador.spec) e empacotado SEM numpy,
telethon, neonize etc. Importar qualquer modulo dele nao pode puxar esses
pacotes: em 2026.11.27.0 a `fala` importava o numpy no topo e o instalador
parava com "No module named 'numpy'"."""
import os
import subprocess
import sys

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

SCRIPT = """
import sys
EXCLUIDOS = ("telethon", "neonize", "cv2", "numpy", "soundfile",
             "sounddevice", "PIL", "emoji", "tkinter")
class Bloqueio:
    def find_spec(self, nome, caminho=None, alvo=None):
        if nome.split(".")[0] in EXCLUIDOS:
            raise ModuleNotFoundError("No module named " + repr(nome))
sys.meta_path.insert(0, Bloqueio())
sys.path.insert(0, RAIZ_)
for modulo in ("telezapp.instalador", "telezapp.interface.instalacao",
               "telezapp.interface.backup", "telezapp.interface.guia",
               "telezapp.nucleo.instalacao", "telezapp.nucleo.atualizador",
               "telezapp.nucleo.paginas", "telezapp.nucleo.copia_oficial",
               "telezapp.nucleo.backup"):
    __import__(modulo)
print("ok")
"""


def test_modulos_do_instalador_importam_sem_os_pacotes_excluidos():
    codigo = "RAIZ_ = %r\n" % RAIZ + SCRIPT
    r = subprocess.run([sys.executable, "-I", "-c", codigo],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr[-1500:]

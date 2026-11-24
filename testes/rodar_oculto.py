"""Roda um script (teste de interface com janelas) numa área de trabalho OCULTA do Windows.

As janelas do teste nascem numa "desktop" paralela, criada só para isso: não aparecem na tela da
pessoa, não roubam o foco nem ficam por cima do que ela está usando. Os eventos de tecla dos
testes são sintéticos (wx), então não dependem da tela real.

Uso:  python rodar_oculto.py <python.exe> <script.py> [argumentos...]
Saída: o que o script imprimiu (stdout e stderr juntos) e o mesmo código de saída dele.
Limite de tempo: variável de ambiente OCULTO_TIMEOUT (segundos, padrão 180).
"""
import ctypes
import os
import subprocess
import sys
import tempfile
import time
import uuid
from ctypes import wintypes

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32 = ctypes.WinDLL("user32", use_last_error=True)

GENERIC_ALL = 0x10000000
CREATE_NO_WINDOW = 0x08000000
CREATE_UNICODE_ENVIRONMENT = 0x00000400
WAIT_TIMEOUT = 0x102


class STARTUPINFO(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR), ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD), ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_void_p), ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    python, script, resto = argv[0], argv[1], argv[2:]
    limite = int(os.environ.get("OCULTO_TIMEOUT", "180"))
    nome = "oculta-" + uuid.uuid4().hex[:8]
    u32.CreateDesktopW.restype = wintypes.HANDLE
    desktop = u32.CreateDesktopW(nome, None, None, 0, GENERIC_ALL, None)
    if not desktop:
        print("Não consegui criar a área de trabalho oculta (erro %d)." % ctypes.get_last_error())
        return 3
    saida = os.path.join(tempfile.gettempdir(), "oculto-%s.txt" % nome)
    linha = subprocess.list2cmdline([python, script] + resto)
    # o cmd só serve para redirecionar a saída para um arquivo; o script roda na desktop oculta
    cmd = 'cmd.exe /c "%s > "%s" 2>&1"' % (linha, saida)
    si = STARTUPINFO()
    si.cb = ctypes.sizeof(si)
    si.lpDesktop = "winsta0\\" + nome
    pi = PROCESS_INFORMATION()
    ambiente = None
    ok = k32.CreateProcessW(None, ctypes.create_unicode_buffer(cmd), None, None, False,
                            CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT, ambiente, os.getcwd(),
                            ctypes.byref(si), ctypes.byref(pi))
    if not ok:
        print("Não consegui iniciar o script (erro %d)." % ctypes.get_last_error())
        u32.CloseDesktop(desktop)
        return 4
    codigo = wintypes.DWORD(0)
    r = k32.WaitForSingleObject(pi.hProcess, limite * 1000)
    if r == WAIT_TIMEOUT:
        k32.TerminateProcess(pi.hProcess, 1)
        k32.WaitForSingleObject(pi.hProcess, 5000)
        print("TEMPO ESGOTADO (%d s): o script foi encerrado." % limite)
        codigo.value = 124
    else:
        k32.GetExitCodeProcess(pi.hProcess, ctypes.byref(codigo))
    k32.CloseHandle(pi.hProcess)
    k32.CloseHandle(pi.hThread)
    for _ in range(20):                       # a desktop só fecha sem processos nela
        if u32.CloseDesktop(desktop):
            break
        time.sleep(0.25)
    try:
        with open(saida, "rb") as f:
            sys.stdout.flush()
            sys.stdout.buffer.write(f.read())      # bytes direto: o script pode usar qualquer codificação
            sys.stdout.buffer.flush()
        os.remove(saida)
    except OSError:
        pass
    return codigo.value


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

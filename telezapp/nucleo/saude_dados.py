# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""A saude dos dados: o banco de conversas esta inteiro? Os dados estao num
disco que pode ser tirado ou que some (pendrive, disco externo, rede)? Sem
wx. O banco usa o modo WAL, e disco removivel e o lugar onde ele mais se
danifica: desconectar sem ejetar, o disco dormir na suspensao, copiar a pasta
com o programa aberto."""
import logging
import os
import sqlite3
import sys
import time

log = logging.getLogger("telezapp.saude")

# o que a conferencia diz do disco dos dados
REMOVIVEL, USB, REDE = "removivel", "usb", "rede"

TEXTOS_DO_DISCO = {
    REMOVIVEL: "um disco removível (como um pendrive)",
    USB: "um disco externo (ligado por USB)",
    REDE: "um disco de rede",
}

AVISO_DISCO = (
    "Os dados do %(nome)s (conversas, sessões e mídias) estão em %(onde)s, "
    "na pasta:\n%(pasta)s\n\n"
    "Nesse tipo de disco o banco de conversas pode se danificar. Para evitar:\n"
    "- Feche o %(nome)s (Ferramentas, Sair) antes de ejetar ou desconectar "
    "o disco; use \"Remover com segurança\" do Windows.\n"
    "- Não deixe o computador entrar em suspensão com o %(nome)s aberto.\n"
    "- Não copie a pasta de dados com o programa aberto: para levar para "
    "outro lugar, use Backup e Restaurar.\n"
    "- Faça backup de vez em quando.\n\n"
    "Para não ver este aviso ao abrir, desmarque \"Avisar quando os dados "
    "estão em disco externo\" em Configurações, Sistema.")

AVISO_BANCO = (
    "O banco de conversas %(onde)s está com defeito (o SQLite diz: "
    "%(detalhe)s).\n\n"
    "Isso pode fazer conversas não abrirem e mensagens ou mídias faltarem. "
    "O que fazer:\n"
    "- Não apague nem mova nada na pasta de dados.\n"
    "- Feche o %(nome)s. Se os dados estão em disco externo, verifique o "
    "disco no Windows (propriedades do disco, Ferramentas, Verificar).\n"
    "- Se você tem um backup feito antes do problema, restaure-o (Backup, "
    "Restaurar).\n"
    "- Mande um relato em Ajuda, Feedback, com os logs, para eu ver se dá "
    "para recuperar as conversas.")


def conferir_banco(caminho, limite=5, abrir=sqlite3.connect):
    """(estado, detalhe, segundos). `estado` e "ok", "danificado" ou
    "inconclusivo" (nao deu para abrir agora: travado, sem arquivo). Abre
    uma conexao propria, so para ler: no modo WAL isso nao trava quem esta
    usando o banco."""
    inicio = time.time()
    if not os.path.isfile(caminho):
        return "inconclusivo", "arquivo ausente", 0.0
    con = None
    try:
        con = abrir(caminho, timeout=30)
        linhas = [str(l[0]) for l in con.execute(
            "PRAGMA quick_check(%d)" % int(limite))]
    except sqlite3.DatabaseError as erro:
        texto = str(erro)
        baixo = texto.lower()
        if any(p in baixo for p in ("malformed", "not a database",
                                    "corrupt", "disk image")):
            return "danificado", texto, time.time() - inicio
        return "inconclusivo", texto, time.time() - inicio
    except Exception as erro:
        return "inconclusivo", "%s: %s" % (type(erro).__name__, erro), \
            time.time() - inicio
    finally:
        if con is not None:
            try:
                con.close()
            except Exception:
                pass
    segundos = time.time() - inicio
    if linhas == ["ok"]:
        return "ok", "", segundos
    return "danificado", "; ".join(linhas)[:300], segundos


def tipo_do_disco(caminho, sistema=None):
    """REMOVIVEL, USB, REDE ou "" (disco interno, ou nao deu para saber).
    So no Windows. Pendrive e disco externo USB: o Windows diz "fixo" para
    muitos discos externos, entao o barramento e perguntado a parte."""
    if (sistema or sys.platform) != "win32":
        return ""
    try:
        import ctypes
        caminho = os.path.abspath(caminho)
        unc = caminho.startswith("\\\\")
        if unc:
            return REDE
        letra = os.path.splitdrive(caminho)[0]
        if not letra:
            return ""
        raiz = letra + "\\"
        tipo = ctypes.windll.kernel32.GetDriveTypeW(raiz)
        if tipo == 4:                         # DRIVE_REMOTE
            return REDE
        if tipo == 2:                         # DRIVE_REMOVABLE
            return REMOVIVEL
        if tipo != 3:                         # nao e disco fixo
            return ""
        return USB if _barramento_usb(letra) else ""
    except Exception:
        log.debug("nao deu para saber o tipo do disco", exc_info=True)
        return ""


def _barramento_usb(letra):
    """True se o disco da letra (como "E:") esta ligado por USB."""
    import ctypes
    from ctypes import wintypes
    k = ctypes.windll.kernel32
    k.CreateFileW.restype = wintypes.HANDLE
    k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                              wintypes.DWORD, wintypes.LPVOID,
                              wintypes.DWORD, wintypes.DWORD,
                              wintypes.HANDLE]
    invalido = wintypes.HANDLE(-1).value
    # acesso 0: so consulta, sem precisar de administrador
    h = k.CreateFileW("\\\\.\\" + letra, 0, 3, None, 3, 0, None)
    if h is None or h == invalido:
        return False
    try:
        consulta = (ctypes.c_ubyte * 12)()      # PropertyId=0, QueryType=0
        saida = (ctypes.c_ubyte * 1024)()
        devolvidos = wintypes.DWORD(0)
        ok = k.DeviceIoControl(
            wintypes.HANDLE(h), 0x2D1400, consulta, len(consulta), saida,
            len(saida), ctypes.byref(devolvidos), None)
        if not ok or devolvidos.value < 32:
            return False
        barramento = int.from_bytes(bytes(saida[28:32]), "little")
        return barramento == 7                  # BusTypeUsb
    finally:
        k.CloseHandle(wintypes.HANDLE(h))


def aviso_do_disco(tipo, pasta, nome):
    return AVISO_DISCO % {"nome": nome, "pasta": pasta,
                          "onde": TEXTOS_DO_DISCO[tipo]}


def aviso_do_banco(onde, detalhe, nome):
    return AVISO_BANCO % {"nome": nome, "onde": onde, "detalhe": detalhe}


# ------------------------------------------------- erro visto durante o uso
# A conferencia ao abrir pega o banco ja danificado; isto pega o que se
# danifica depois. A janela liga `ao_falhar`; so o primeiro erro por banco
# avisa, os outros so entram no log.
ao_falhar = None
_ja_avisados = set()


def e_dano_do_banco(erro):
    texto = str(erro).lower()
    return isinstance(erro, sqlite3.DatabaseError) and any(
        p in texto for p in ("malformed", "not a database", "corrupt",
                             "disk image"))


def registrar_erro_do_banco(erro, onde):
    """Chamado quando uma leitura do banco falhou por dano nele. True se
    era dano (quem chamou deve seguir sem o dado); False se era outro erro
    (quem chamou deve deixar subir)."""
    if not e_dano_do_banco(erro):
        return False
    if onde not in _ja_avisados:
        _ja_avisados.add(onde)
        log.error("banco danificado ao ler %s: %s", onde, erro)
        if ao_falhar is not None:
            try:
                ao_falhar(onde, str(erro))
            except Exception:
                log.exception("aviso de banco danificado")
    return True

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Instalar a partir da copia portatil e criar copia portatil."""
import os
import sqlite3
import sys

import pytest

from telezapp import config
from telezapp.nucleo import instalacao as ins


@pytest.fixture
def mundo(tmp_path, monkeypatch):
    for nome in ("APPDATA", "LOCALAPPDATA", "USERPROFILE"):
        pasta = tmp_path / nome
        pasta.mkdir()
        monkeypatch.setenv(nome, str(pasta))
    monkeypatch.delenv("TELEZAPP_DADOS", raising=False)
    monkeypatch.setattr(ins, "_pasta_conhecida", lambda guid: None)
    prog = tmp_path / "portatil" / "TeleZapp"
    (prog / "telezapp" / "sons").mkdir(parents=True)
    (prog / "TeleZapp.exe").write_bytes(b"exe")
    (prog / "telezapp" / "sons" / "a.ogg").write_bytes(b"som")
    return tmp_path, str(prog)


def _sem_atalhos():
    feitos = []
    return feitos, (lambda lnk, alvo, pasta: feitos.append((lnk, alvo))), \
        (lambda destino: feitos.append(("registro", destino)))


def _dados_portateis(prog):
    dados = os.path.join(prog, "dados")
    os.makedirs(os.path.join(dados, "midias", "c"))
    os.makedirs(os.path.join(dados, "logs"))
    with open(os.path.join(dados, "logs", "x.log"), "w") as f:
        f.write("log")
    with open(os.path.join(dados, "midias", "c", "foto.jpg"), "w") as f:
        f.write("foto")
    con = sqlite3.connect(os.path.join(dados, "telezapp.db"))
    con.execute("CREATE TABLE midias (caminho TEXT)")
    con.execute("INSERT INTO midias VALUES (?)",
                (os.path.join(dados, "midias", "c", "foto.jpg"),))
    con.commit()
    con.close()
    return dados


def test_modo(mundo):
    _, prog = mundo
    assert ins.modo(prog) == "portatil"
    assert ins.dados_portateis(prog) is None
    os.makedirs(os.path.join(prog, "dados"))
    assert ins.dados_portateis(prog) == os.path.join(prog, "dados")
    with open(os.path.join(prog, "instalado.txt"), "w") as f:
        f.write("x")
    assert ins.modo(prog) == "instalado"


def test_pasta_de_dados_portatil_so_no_executavel(mundo, monkeypatch):
    _, prog = mundo
    os.makedirs(os.path.join(prog, "dados"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", os.path.join(prog, "TeleZapp.exe"))
    assert config.pasta_dados() == os.path.join(prog, "dados")
    monkeypatch.setattr(sys, "frozen", False)
    assert config.pasta_dados() != os.path.join(prog, "dados")


def test_instalar_copia_marca_e_atalhos(mundo):
    tmp, prog = mundo
    os.makedirs(os.path.join(prog, "dados"))      # nao vai junto
    feitos, atalho, registro = _sem_atalhos()
    exe, avisos = ins.instalar(prog, atalho_menu=True, atalho_area=True,
                               fazer_atalho=atalho, registrar=registro)
    destino = os.path.dirname(exe)
    assert destino == os.path.join(str(tmp / "LOCALAPPDATA"), "Programs",
                                   "TeleZapp")
    assert avisos == []
    assert os.path.isfile(os.path.join(destino, "telezapp", "sons", "a.ogg"))
    assert not os.path.exists(os.path.join(destino, "dados"))
    assert ins.modo(destino) == "instalado"
    assert len([f for f in feitos if f[0].endswith(".lnk")]) == 2
    assert ("registro", destino) in feitos
    # a copia de origem continua portatil e intacta
    assert ins.modo(prog) == "portatil"


def test_atalho_vai_para_a_area_de_trabalho_do_windows(mundo, monkeypatch):
    # a area de trabalho pode estar no OneDrive, fora de USERPROFILE\Desktop
    tmp, prog = mundo
    pastas = {ins.FOLDERID_DESKTOP: str(tmp / "OneDrive" / "Área de Trabalho"),
              ins.FOLDERID_PROGRAMS: str(tmp / "Programas")}
    monkeypatch.setattr(ins, "_pasta_conhecida", lambda guid: pastas[guid])
    feitos, atalho, registro = _sem_atalhos()
    ins.instalar(prog, atalho_menu=True, atalho_area=True,
                 fazer_atalho=atalho, registrar=registro)
    lnks = sorted(f[0] for f in feitos if f[0].endswith(".lnk"))
    assert lnks == [str(tmp / "OneDrive" / "Área de Trabalho" /
                        "TeleZapp.lnk"), str(tmp / "Programas" /
                                              "TeleZapp.lnk")]


def test_reinstalar_troca_sem_deixar_sobras(mundo):
    _, prog = mundo
    _, atalho, registro = _sem_atalhos()
    exe, _ = ins.instalar(prog, fazer_atalho=atalho, registrar=registro)
    destino = os.path.dirname(exe)
    with open(os.path.join(destino, "velho.txt"), "w") as f:
        f.write("x")
    ins.instalar(prog, fazer_atalho=atalho, registrar=registro)
    assert not os.path.exists(os.path.join(destino, "velho.txt"))
    pai = os.path.dirname(destino)
    assert sorted(os.listdir(pai)) == ["TeleZapp"]


def test_instalar_recusa_pasta_dentro_do_programa(mundo):
    _, prog = mundo
    with pytest.raises(ins.ErroInstalacao):
        ins.instalar(prog, os.path.join(prog, "dentro"))
    with pytest.raises(ins.ErroInstalacao):
        ins.instalar(prog, prog)


def test_instalar_levando_os_dados(mundo):
    tmp, prog = mundo
    dados = _dados_portateis(prog)
    # ja havia dados no computador: ficam guardados
    antigo = tmp / "APPDATA" / "TeleZapp"
    antigo.mkdir()
    (antigo / "config.json").write_text("{}")
    _, atalho, registro = _sem_atalhos()
    ins.instalar(prog, levar_dados_de=dados, fazer_atalho=atalho,
                 registrar=registro)
    novo = str(antigo)
    assert os.path.isfile(os.path.join(novo, "midias", "c", "foto.jpg"))
    assert not os.path.exists(os.path.join(novo, "logs"))
    guardadas = [n for n in os.listdir(str(tmp / "APPDATA"))
                 if n.startswith("TeleZapp.antes-da-instalacao")]
    assert len(guardadas) == 1
    con = sqlite3.connect(os.path.join(novo, "telezapp.db"))
    caminho = con.execute("SELECT caminho FROM midias").fetchone()[0]
    con.close()
    assert caminho == os.path.join(novo, "midias", "c", "foto.jpg")


def test_falha_no_atalho_vira_aviso(mundo):
    _, prog = mundo

    def ruim(lnk, alvo, pasta):
        raise ins.ErroInstalacao("sem atalho")
    _, _, registro = _sem_atalhos()
    exe, avisos = ins.instalar(prog, fazer_atalho=ruim, registrar=registro)
    assert os.path.isfile(exe) and avisos == ["sem atalho"]


def test_criar_portatil_vazia_e_com_dados(mundo):
    tmp, prog = mundo
    saida = str(tmp / "pendrive")
    os.makedirs(saida)
    alvo = ins.criar_portatil(prog, saida)
    assert os.path.isdir(os.path.join(alvo, "dados"))
    assert os.listdir(os.path.join(alvo, "dados")) == []
    assert ins.dados_portateis(alvo)
    with pytest.raises(ins.ErroInstalacao):       # ja existe e tem coisas
        ins.criar_portatil(prog, saida)
    # com dados: logs e temp ficam de fora, caminhos de midia acertados
    dados = _dados_portateis(prog)
    saida2 = str(tmp / "pendrive2")
    alvo2 = ins.criar_portatil(prog, saida2, levar_dados_de=dados)
    d2 = os.path.join(alvo2, "dados")
    assert os.path.isfile(os.path.join(d2, "midias", "c", "foto.jpg"))
    assert not os.path.exists(os.path.join(d2, "logs"))
    con = sqlite3.connect(os.path.join(d2, "telezapp.db"))
    caminho = con.execute("SELECT caminho FROM midias").fetchone()[0]
    con.close()
    assert caminho == os.path.join(d2, "midias", "c", "foto.jpg")
    # a portatil nova nao carrega uma pasta dados da origem
    assert not os.path.exists(os.path.join(alvo2, "instalado.txt"))


def test_desinstalar_so_instalado(mundo):
    _, prog = mundo
    with pytest.raises(ins.ErroInstalacao):
        ins.desinstalar(prog)


# ---------------------------------------------------- backup ao desinstalar
class _Dialogo:
    def __init__(self, *a, **k):
        pass

    def ShowModal(self):
        return 5100

    def Destroy(self):
        pass

    def Pulse(self):
        pass


class JanelaFalsa:
    """No lugar da JanelaDeProgresso: guarda o que a tela mostraria."""
    criadas = []

    def __init__(self, pai, titulo, texto="", ao_cancelar=None, falar=None):
        self.titulo, self.passos, self.fechada = titulo, [], False
        JanelaFalsa.criadas.append(self)

    def mostrar(self):
        pass

    def atualizar(self, percentual=None, texto=None):
        self.passos.append((percentual, texto))

    def fechar(self):
        self.fechada = True


def _preparar_oferta(monkeypatch, tmp_path, resposta, salvar=True):
    from telezapp.interface import backup as jb
    from telezapp.interface import instalacao as ui
    destino = str(tmp_path / "saida.zip")

    class Arquivo(_Dialogo):
        def ShowModal(self):
            return 5100 if salvar else 5101

        def GetPath(self):
            return destino

    class DlgBackup(_Dialogo):
        senha = type("S", (), {"GetValue": lambda s: ""})()

        def partes(self):
            return ["configuracoes"]
    caixas = []
    monkeypatch.setattr(ui.wx, "MessageBox", lambda texto, *a, **k: (
        caixas.append(texto), resposta)[1], raising=False)
    for nome, valor in (("YES_NO", 10), ("YES", 2), ("CANCEL", 16),
                        ("ID_OK", 5100), ("ICON_QUESTION", 0),
                        ("ICON_WARNING", 0), ("ICON_INFORMATION", 0),
                        ("OK", 4), ("FD_SAVE", 0), ("FD_OVERWRITE_PROMPT", 0),
                        ("PD_APP_MODAL", 0)):
        monkeypatch.setattr(ui.wx, nome, valor, raising=False)
    monkeypatch.setattr(ui.wx, "FileDialog", Arquivo, raising=False)
    monkeypatch.setattr(ui, "JanelaDeProgresso", JanelaFalsa)
    monkeypatch.setattr(ui.wx, "MilliSleep", lambda ms: None, raising=False)
    monkeypatch.setattr(ui.wx, "YieldIfNeeded", lambda: None, raising=False)
    monkeypatch.setattr(jb, "DialogoBackup", DlgBackup)
    return ui, destino, caixas


def test_desinstalar_oferece_o_backup(mundo, monkeypatch, tmp_path):
    monkeypatch.setenv("TELEZAPP_DADOS", str(tmp_path / "dados"))
    os.makedirs(str(tmp_path / "dados"))
    ui, destino, caixas = _preparar_oferta(monkeypatch, tmp_path, 2)
    assert ui.oferecer_backup(None, {"contas": []}) is True
    assert os.path.isfile(destino)               # backup feito
    # Nao: segue sem backup; Cancelar: desiste da desinstalacao
    ui, destino2, _ = _preparar_oferta(monkeypatch, tmp_path, 8)
    assert ui.oferecer_backup(None, {}) is True
    ui, _, _ = _preparar_oferta(monkeypatch, tmp_path, 16)
    assert ui.oferecer_backup(None, {}) is False
    # Sim, mas desistiu de escolher onde salvar: nao desinstala
    ui, _, _ = _preparar_oferta(monkeypatch, tmp_path, 2, salvar=False)
    assert ui.oferecer_backup(None, {}) is False


def test_desinstalar_tira_atalhos_registro_e_pasta(mundo, monkeypatch):
    import time
    if os.name != "nt":
        pytest.skip("usa o cmd do Windows")
    tmp, prog = mundo
    lnk = tmp / "atalho.lnk"
    lnk.write_text("x")
    chamadas = []
    monkeypatch.setattr(ins, "_caminhos_dos_atalhos",
                        lambda: (str(lnk), str(tmp / "nao-existe.lnk")))
    monkeypatch.setattr(ins, "_desregistrar", lambda: chamadas.append(1))
    dados = tmp / "dados-a-apagar"
    dados.mkdir()
    (dados / "a.db").write_text("x")
    with open(os.path.join(prog, "instalado.txt"), "w") as f:
        f.write("sim")
    ins.desinstalar(prog, apagar_dados=True, dados=str(dados))
    assert not lnk.exists() and chamadas == [1] and not dados.exists()
    for _ in range(100):                  # a pasta sai em segundo plano
        if not os.path.exists(prog):
            break
        time.sleep(0.2)
    assert not os.path.exists(prog)


# ----------------------------------------------------- barra de progresso
def test_faixa_leva_o_avanco_de_uma_etapa_para_a_faixa_do_total():
    vistos = []
    f = ins.faixa(lambda pct, texto="": vistos.append((pct, texto)), 40, 100)
    f(0, "a")
    f(50, "b")
    f(100, "c")
    f(None, "d")
    assert vistos == [(40, "a"), (70, "b"), (100, "c"), (None, "d")]
    assert ins.faixa(None, 0, 10) is None


def test_instalar_e_criar_portatil_informam_o_avanco(mundo):
    tmp, prog = mundo
    dados = _dados_portateis(prog)
    _, atalho, registro = _sem_atalhos()
    vistos = []
    ins.instalar(prog, levar_dados_de=dados, fazer_atalho=atalho,
                 registrar=registro,
                 progresso=lambda pct, texto="": vistos.append((pct, texto)))
    pcts = [p for p, _ in vistos if p is not None]
    assert pcts == sorted(pcts) and pcts[0] == 0 and pcts[-1] == 100
    assert any(p and 0 < p < 60 for p in pcts)          # copiou o programa
    textos = {t for _, t in vistos}
    assert {"Copiando o programa", "Levando os dados",
            "Criando os atalhos", "Instalado"} <= textos
    vistos.clear()
    ins.criar_portatil(prog, str(tmp / "pen"), levar_dados_de=dados,
                       progresso=lambda pct, texto="": vistos.append(
                           (pct, texto)))
    pcts = [p for p, _ in vistos if p is not None]
    assert pcts == sorted(pcts) and pcts[0] == 0
    assert {"Copiando o programa", "Copiando os dados"} <= \
        {t for _, t in vistos}


def test_extrair_pacote_informa_o_avanco(mundo, tmp_path):
    import zipfile
    zip_ = tmp_path / "pacote.zip"
    with zipfile.ZipFile(zip_, "w") as z:
        z.writestr("TeleZapp/TeleZapp.exe", b"x")
        for i in range(4):
            z.writestr("TeleZapp/dados%d.txt" % i, b"y")
    vistos = []
    with ins.extrair_pacote(str(zip_), lambda pct, t: vistos.append(pct)) \
            as pasta:
        assert os.path.isfile(os.path.join(pasta, "TeleZapp.exe"))
    assert vistos == sorted(vistos) and vistos[-1] == 100

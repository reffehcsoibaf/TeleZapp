# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Fala direta pelo NVDA e sons curtos.

Usa a DLL nvdaControllerClient que vem no pacote accessible-output2,
carregada por ctypes (sem importar o pacote). Sem NVDA ou sem a DLL, a fala
fica desligada e o motivo vai para o log.
"""
import ctypes
import importlib.util
import logging
import os
import struct
import threading

try:
    import winsound
except ImportError:  # fora do Windows (testes)
    winsound = None

log = logging.getLogger("telezapp.fala")
_trava_som = threading.Lock()


class Fala:
    def __init__(self):
        self.lib = None
        self.motivo = ""
        self._carregar()

    def _carregar(self):
        try:
            spec = importlib.util.find_spec("accessible_output2")
            if spec is None or not spec.origin:
                self.motivo = "pacote accessible_output2 não instalado"
                return
            nome = ("nvdaControllerClient64.dll"
                    if struct.calcsize("P") == 8
                    else "nvdaControllerClient32.dll")
            caminho = os.path.join(os.path.dirname(spec.origin), "lib", nome)
            if not os.path.isfile(caminho):
                self.motivo = "DLL não encontrada"
                return
            lib = ctypes.WinDLL(caminho)
            lib.nvdaController_speakText.argtypes = [ctypes.c_wchar_p]
            self.lib = lib
        except Exception as e:  # pragma: no cover - depende do Windows
            self.motivo = "erro ao carregar a DLL: %r" % e
        finally:
            if self.motivo:
                log.info("fala direta indisponível: %s", self.motivo)

    def ativa(self):
        if self.lib is None:
            return False
        try:
            return self.lib.nvdaController_testIfRunning() == 0
        except Exception:
            return False

    def falar(self, texto, interromper=False):
        if not texto or not self.ativa():
            return False
        try:
            if interromper:
                self.lib.nvdaController_cancelSpeech()
            return self.lib.nvdaController_speakText(texto) == 0
        except Exception as e:
            log.warning("erro ao falar: %r", e)
            return False


# O que a pessoa escolheu para cada evento (opcoes som_*): "" = som padrao,
# "desligado" ou o caminho de um arquivo de som
_sons = {}
LIMITE_SEGUNDOS_ARQUIVO = 15


# Eventos que, no som padrao, tocam o mesmo som de outro (e acompanham a
# escolha dele): a pessoa so muda se quiser diferenciar
HERDA = {"nova_aberta": "nova", "nova_grupo": "nova",
         "reconectada": "conectado", "falha_envio": "erro",
         "tarefa_pronta": "enviada", "gravacao_parada": "enviada",
         "voto_enviado": "enviada"}


# O tom de "chamando" (eu liguei e espero atender), em milissegundos
DURACAO_TOM_DE_CHAMADA_MS = 1500


def tom_padrao(tipo):
    """O tipo cujo som sintetico o evento usa quando nao ha escolha."""
    while tipo in HERDA:
        tipo = HERDA[tipo]
    return tipo


# Sons curtos ja lidos e decodificados, para tocar sem abrir o arquivo:
# {caminho: (mtime, dados, taxa)}. Os longos (toques de chamada) ficam fora.
LIMITE_SEGUNDOS_PRE_CARGA = 2
_pre_carregados = {}
_geracao_pre_carga = 0
_thread_pre_carga = None


def definir_sons(mapa):
    """Troca as escolhas de som: {evento: valor}."""
    global _geracao_pre_carga, _thread_pre_carga
    _sons.clear()
    _sons.update(mapa)
    _geracao_pre_carga += 1
    caminhos = {c for c in (caminho_do_som(v) for v in mapa.values()) if c}
    for velho in [c for c in _pre_carregados if c not in caminhos]:
        _pre_carregados.pop(velho, None)
    if caminhos:
        _thread_pre_carga = threading.Thread(
            target=_pre_carregar, args=(sorted(caminhos), _geracao_pre_carga),
            daemon=True)
        _thread_pre_carga.start()


def _ler_som(caminho, limite_segundos):
    import soundfile as sf
    with sf.SoundFile(caminho) as f:
        if limite_segundos < LIMITE_SEGUNDOS_ARQUIVO and \
                f.frames > f.samplerate * limite_segundos:
            return None       # comprido demais para ficar na memoria
        dados = f.read(int(f.samplerate * LIMITE_SEGUNDOS_ARQUIVO),
                       dtype="float32", always_2d=True)
        return dados, f.samplerate


def _pre_carregar(caminhos, geracao):
    """Em segundo plano, deixa na memoria os sons curtos escolhidos. Se a
    escolha mudar no meio, para; quem tocar antes disso le o arquivo."""
    for caminho in caminhos:
        if geracao != _geracao_pre_carga:
            return
        try:
            mtime = os.path.getmtime(caminho)
            guardado = _pre_carregados.get(caminho)
            if guardado and guardado[0] == mtime:
                continue
            lido = _ler_som(caminho, LIMITE_SEGUNDOS_PRE_CARGA)
            if lido is not None and geracao == _geracao_pre_carga:
                _pre_carregados[caminho] = (mtime,) + lido
        except Exception as e:
            log.info("não pré-carreguei o som %s (%r)",
                     os.path.basename(caminho), e)


# Valor de "usar o bip do sistema" neste evento (o pacote Padrao, ou um
# evento sem arquivo num pacote personalizado); nao e nome de arquivo
BIP = "<bip>"


def caminho_do_som(valor):
    """Arquivo de som de uma escolha: um nome vai para a pasta de sons do
    TeleZapp; um caminho completo (versoes antigas) vale como esta."""
    if not valor or valor in ("desligado", BIP):
        return ""
    if os.path.isabs(valor):
        return valor
    from telezapp import config
    return os.path.join(config.pasta_sons(), valor)


def acao_do_som(tipo, valor=None):
    """("nenhum" | "arquivo" | "padrao", caminho) para o evento, pela escolha
    guardada ou pelo `valor` dado (para ouvir antes de aplicar)."""
    valor = _sons.get(tipo, "") if valor is None else valor
    if valor == "desligado":
        return "nenhum", ""
    if valor == BIP:
        return "padrao", ""
    caminho = caminho_do_som(valor)
    if caminho and os.path.isfile(caminho):
        return "arquivo", caminho
    if not valor and tipo in HERDA:
        return acao_do_som(HERDA[tipo])        # acompanha o outro evento
    return "padrao", ""       # sem som escolhido ou arquivo que sumiu


def bipe(tipo="nova", valor=None):
    """Sons curtos: nova (mensagem recebida), enviada, erro, pronto
    (codigo ou QR pronto), atualizado (QR trocado), conectado e, nas
    chamadas, toque, chamando e desligada. Cada um pode ser desligado ou
    trocado por um arquivo de som (opcoes som_*). Tocam numa thread a parte
    para nao travar a janela."""
    acao, caminho = acao_do_som(tipo, valor)
    if acao == "nenhum":
        return
    if acao == "arquivo":
        threading.Thread(target=_tocar_arquivo, args=(tipo, caminho),
                         daemon=True).start()
        return
    if winsound is None and _indice_dos_avisos() is None:
        return
    threading.Thread(target=_tocar, args=(tom_padrao(tipo),),
                     daemon=True).start()


def _tocar_arquivo(tipo, caminho):
    """Toca o arquivo de som (as primeiras LIMITE_SEGUNDOS_ARQUIVO); se nao
    der, cai no som padrao do evento."""
    try:
        import sounddevice as sd
        guardado = _pre_carregados.get(caminho)
        if guardado is not None and guardado[0] == os.path.getmtime(caminho):
            _, dados, taxa = guardado
        else:
            dados, taxa = _ler_som(caminho, LIMITE_SEGUNDOS_ARQUIVO)
        # sd.play para o som anterior e abre o novo: duas threads juntas
        # mexem no mesmo fluxo do PortAudio e derrubam o programa
        dispositivo = _indice_dos_avisos()
        with _trava_som:
            if dispositivo is None:
                sd.play(dados, taxa)
            else:
                sd.play(dados, taxa, device=dispositivo)
    except Exception as e:
        log.warning("não consegui tocar o som escolhido (%r); usando o "
                    "padrão", e)
        if winsound is not None:
            _tocar(tom_padrao(tipo))


# Os sons padrao, nota a nota: (frequencia em Hz, duracao em ms)
NOTAS = {
    "nova": ((880, 90), (1175, 120)),
    "enviada": ((660, 80),),
    "pronto": ((660, 90), (880, 90), (1100, 90)),
    "atualizado": ((990, 70), (990, 70)),
    "conectado": ((523, 110), (659, 110), (784, 110), (1047, 110)),
    # chamada recebida: dois pares de notas, repetido pela janela
    "toque": ((784, 120), (988, 120), (784, 120), (988, 120)),
    # chamada que eu fiz: um tom grave e longo, como o de espera de um
    # telefone (a janela repete a cada 3 s)
    "chamando": ((425, DURACAO_TOM_DE_CHAMADA_MS),),
    # conta que caiu: dois tons descendo, mais graves que o de chamada
    "desconectada": ((440, 150), (330, 150)),
    "download_pronto": ((740, 70), (988, 70)),
    "mencao_ou_resposta": ((1047, 70), (1319, 70), (1047, 70)),
    "reacao_recebida": ((1319, 55), (1568, 55)),
    "desligada": ((494, 120), (392, 120), (330, 120)),
    # curto: nao pode entrar na gravacao
    "gravando": ((784, 60), (1047, 60)),
    "voto_enquete": ((1047, 60), (1319, 60)),
    "escondido": ((784, 90), (523, 90)),
    "voltou": ((523, 90), (784, 90)),
}
NOTAS_PADRAO = ((300, 200),)
TAXA_SINTETICA = 44100


def _indice_dos_avisos():
    """O dispositivo de saida escolhido para os sons de aviso, ou None (o
    padrao do Windows)."""
    try:
        from telezapp.midia import dispositivos
        return dispositivos.indice_da_notificacao()
    except Exception:
        return None


def _onda(notas):
    """O som padrao como amostras, para tocar em um dispositivo escolhido
    (o winsound.Beep so toca no padrao do Windows)."""
    import numpy as np
    partes = []
    for freq, ms in notas:
        n = int(TAXA_SINTETICA * ms / 1000)
        t = np.arange(n) / TAXA_SINTETICA
        onda = 0.3 * np.sin(2 * np.pi * freq * t)
        rampa = min(n // 2, int(TAXA_SINTETICA * 0.004))
        if rampa:
            subida = np.linspace(0.0, 1.0, rampa)
            onda[:rampa] *= subida
            onda[n - rampa:] *= subida[::-1]
        partes.append(onda)
    return np.concatenate(partes).astype("float32")


def _tocar(tipo):
    notas = NOTAS.get(tipo, NOTAS_PADRAO)
    try:
        dispositivo = _indice_dos_avisos()
        if dispositivo is not None:
            import sounddevice as sd
            with _trava_som:
                sd.play(_onda(notas), TAXA_SINTETICA, device=dispositivo)
            return
    except Exception as e:
        log.warning("não consegui tocar o aviso no dispositivo escolhido "
                    "(%r); usando o padrão do Windows", e)
    if winsound is None:
        return
    try:
        for freq, ms in notas:
            winsound.Beep(freq, ms)
    except Exception:
        pass

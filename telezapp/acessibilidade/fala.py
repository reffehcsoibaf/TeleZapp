# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Fala direta pelo NVDA e sons curtos.

Usa a DLL nvdaControllerClient que vem no pacote accessible-output2,
carregada por ctypes (sem importar o pacote). Sem NVDA ou sem a DLL, a fala
fica desligada e o motivo vai para o log.
"""
import atexit
import ctypes
import importlib.util
import logging
import os
import struct
import threading
import time

try:
    import winsound
except ImportError:  # fora do Windows (testes)
    winsound = None

log = logging.getLogger("telezapp.fala")


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
         "nova_pessoal": "nova", "nova_canal": "nova",
         "nova_comunidade": "nova_grupo",
         "reconectada": "conectado", "falha_envio": "erro",
         "tarefa_pronta": "enviada", "gravacao_parada": "enviada",
         "voto_enviado": "enviada"}


# Eventos que a pessoa pode diferenciar por servico (WhatsApp e Telegram): a
# variante "evento_servico" herda o evento comum ate receber um som proprio
SERVICOS_DO_SOM = ("whatsapp", "telegram")
EVENTOS_POR_SERVICO = ("nova_aberta", "nova_pessoal", "nova_grupo",
                       "nova_canal", "nova_comunidade", "mencao_ou_resposta",
                       "reacao_recebida", "voto_enquete", "toque",
                       "desligada")
for _e in EVENTOS_POR_SERVICO:
    for _s in SERVICOS_DO_SOM:
        HERDA["%s_%s" % (_e, _s)] = _e


def tipo_do_servico(tipo, servico):
    """O evento do servico (nova_pessoal_telegram), se existe; senao o
    proprio evento."""
    variante = "%s_%s" % (tipo, servico)
    return variante if variante in HERDA else tipo


# O tom de "chamando" (eu liguei e espero atender) e o de controle de chamada
# do telefone: (frequencias em Hz, duracao do tom em ms, intervalo entre o
# inicio de um tom e o do seguinte em ms). Europa e o padrao; EUA e o que o
# WhatsApp Desktop usa nos Estados Unidos. A pessoa escolhe em Sons.
TONS_DE_CHAMADA = {
    "europa": ((425,), 1000, 4000),
    "eua": ((440, 480), 2000, 6000),
}
TOM_DE_CHAMADA_PADRAO = "europa"
_tom_de_chamada = TOM_DE_CHAMADA_PADRAO
INTERVALO_TOQUE_MS = 3000        # o toque de quem recebe repete mais rapido


def tom_padrao(tipo):
    """O tipo cujo som sintetico o evento usa quando nao ha escolha."""
    while tipo in HERDA and tipo not in NOTAS:
        tipo = HERDA[tipo]
    return tipo


# Sons curtos ja lidos e decodificados, para tocar sem abrir o arquivo:
# {caminho: (mtime, dados, taxa)}. Os longos (toques de chamada) ficam fora.
LIMITE_SEGUNDOS_PRE_CARGA = 2
_pre_carregados = {}
_geracao_pre_carga = 0
_thread_pre_carga = None


def definir_tom_de_chamada(tom):
    """Escolhe o tom de chamada feita (chave de TONS_DE_CHAMADA)."""
    global _tom_de_chamada
    _tom_de_chamada = tom if tom in TONS_DE_CHAMADA else TOM_DE_CHAMADA_PADRAO


def intervalo_do_tom_de_chamada():
    """Ms entre um tom e o seguinte, no tom escolhido."""
    return TONS_DE_CHAMADA[_tom_de_chamada][2]


def tocar_tom_de_chamada(tom=None):
    """Toca uma vez o tom de chamada feita, o escolhido ou o dado (para
    ouvir antes de aplicar). Numa thread a parte."""
    tom = tom if tom in TONS_DE_CHAMADA else _tom_de_chamada
    threading.Thread(target=_tocar_tom, args=(tom,), daemon=True).start()


def _tocar_tom(tom):
    freqs, ms, _ = TONS_DE_CHAMADA[tom]
    try:
        dispositivo = _indice_dos_avisos()
        if dispositivo is not None:
            _tocar_pelo_fluxo(_onda(((freqs, ms),)), TAXA_SINTETICA,
                              dispositivo)
            return
    except Exception as e:
        log.warning("não consegui tocar o tom de chamada no dispositivo "
                    "escolhido (%r); usando o padrão do Windows", e)
    if winsound is None:
        return
    try:
        winsound.Beep(freqs[0], ms)       # o Beep so faz uma frequencia
    except Exception:
        pass


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


def bipe(tipo="nova", valor=None, servico=""):
    """Sons curtos: nova (mensagem recebida), enviada, erro, pronto
    (codigo ou QR pronto), atualizado (QR trocado), conectado e, nas
    chamadas, toque, chamando e desligada. Cada um pode ser desligado ou
    trocado por um arquivo de som (opcoes som_*). Tocam numa thread a parte
    para nao travar a janela."""
    if tipo == "chamando":
        tocar_tom_de_chamada()
        return
    if servico and valor is None:
        tipo = tipo_do_servico(tipo, servico)
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
        guardado = _pre_carregados.get(caminho)
        if guardado is not None and guardado[0] == os.path.getmtime(caminho):
            _, dados, taxa = guardado
        else:
            dados, taxa = _ler_som(caminho, LIMITE_SEGUNDOS_ARQUIVO)
        # o fluxo dos avisos fica aberto: tocar so troca as amostras (abrir o
        # dispositivo a cada som era o que atrasava a reproducao)
        _tocar_pelo_fluxo(dados, taxa, _indice_dos_avisos())
    except Exception as e:
        log.warning("não consegui tocar o som escolhido (%r); usando o "
                    "padrão", e)
        if winsound is not None:
            _tocar(tom_padrao(tipo))


# Os sons padrao, nota a nota: (frequencia em Hz, duracao em ms)
NOTAS = {
    "nova": ((880, 90), (1175, 120)),
    "nova_pessoal": ((880, 90), (1319, 120)),
    "nova_canal": ((587, 110), (784, 130)),
    "nova_comunidade": ((988, 70), (784, 70), (988, 90)),
    "enviada": ((660, 80),),
    "pronto": ((660, 90), (880, 90), (1100, 90)),
    "atualizado": ((990, 70), (990, 70)),
    "conectado": ((523, 110), (659, 110), (784, 110), (1047, 110)),
    # chamada recebida: dois pares de notas, repetido pela janela
    "toque": ((784, 120), (988, 120), (784, 120), (988, 120)),
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
    "limite_da_lista": ((262, 45),),
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
        freqs = freq if isinstance(freq, (tuple, list)) else (freq,)
        onda = 0.3 * sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
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
            _tocar_pelo_fluxo(_onda(notas), TAXA_SINTETICA, dispositivo)
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


TAXA_DOS_AVISOS = TAXA_SINTETICA
CANAIS_DOS_AVISOS = 2
# sem aviso por este tempo, o fluxo fecha (o dispositivo nao fica ocupado
# a toa e o proximo aviso abre o dispositivo padrao do momento)
TEMPO_OCIOSO_DOS_AVISOS_S = 60


def _preparar_som(dados, taxa):
    """Amostras float32 de dois canais na taxa do fluxo dos avisos."""
    import numpy as np
    dados = np.asarray(dados, dtype="float32")
    if dados.ndim == 1:
        dados = dados.reshape(-1, 1)
    if dados.shape[1] == 1:
        dados = np.repeat(dados, CANAIS_DOS_AVISOS, axis=1)
    elif dados.shape[1] > CANAIS_DOS_AVISOS:
        dados = dados[:, :CANAIS_DOS_AVISOS]
    if len(dados) and taxa and taxa != TAXA_DOS_AVISOS:
        n = max(1, int(round(len(dados) * TAXA_DOS_AVISOS / float(taxa))))
        origem = np.arange(len(dados), dtype="float64")
        destino = np.linspace(0, len(dados) - 1, n)
        dados = np.stack([np.interp(destino, origem, dados[:, c])
                          for c in range(dados.shape[1])], axis=1)
    return np.ascontiguousarray(dados, dtype="float32")


class _SaidaDosAvisos:
    """Um fluxo de saida aberto uma vez para os avisos. Trocar de som so troca
    as amostras que o callback entrega: o dispositivo nao e aberto e fechado a
    cada aviso (era isso que atrasava o som)."""

    def __init__(self):
        self._trava = threading.Lock()         # fluxo e dispositivo
        self._trava_dados = threading.Lock()   # amostras que o callback toca
        self._fluxo = None
        self._dispositivo = None
        self._dados = None
        self._pos = 0
        self._ocioso = None                    # temporizador do fechamento
        self._ultimo = 0.0                     # quando tocou pela ultima vez
        self._agora = time.monotonic

    def _callback(self, outdata, frames, tempo, status):
        with self._trava_dados:
            dados, pos = self._dados, self._pos
            if dados is None or pos >= len(dados):
                outdata.fill(0)
                self._dados = None
                return
            n = min(frames, len(dados) - pos)
            outdata[:n] = dados[pos:pos + n]
            if n < frames:
                outdata[n:] = 0
            self._pos = pos + n
            if self._pos >= len(dados):
                self._dados = None

    def _abrir(self, dispositivo):
        import sounddevice as sd
        parametros = dict(
            samplerate=TAXA_DOS_AVISOS, channels=CANAIS_DOS_AVISOS,
            dtype="float32", device=dispositivo, callback=self._callback)
        try:
            fluxo = sd.OutputStream(latency="low", **parametros)
        except Exception:
            # dispositivo que nao aceita a latencia baixa: usa a padrao
            fluxo = sd.OutputStream(**parametros)
        try:
            fluxo.start()
        except Exception:
            try:
                fluxo.close()
            except Exception:
                pass
            raise
        return fluxo

    def _fechar(self):
        fluxo, self._fluxo = self._fluxo, None
        if fluxo is not None:
            try:
                fluxo.stop()
            except Exception:
                pass
            try:
                fluxo.close()
            except Exception:
                pass

    def tocar(self, dados, taxa, dispositivo=None):
        dados = _preparar_som(dados, taxa)
        with self._trava:
            if self._fluxo is not None and not getattr(
                    self._fluxo, "active", True):
                self._fechar()
            if self._fluxo is None or self._dispositivo != dispositivo:
                with self._trava_dados:
                    self._dados = None
                self._fechar()
                self._fluxo = self._abrir(dispositivo)
                self._dispositivo = dispositivo
            with self._trava_dados:
                self._dados, self._pos = dados, 0
            self._ultimo = self._agora()
            self._armar_fechamento()

    def _armar_fechamento(self):
        """(Re)arma o fechamento do fluxo para daqui a TEMPO_OCIOSO s."""
        anterior = self._ocioso
        if anterior is not None:
            anterior.cancel()
        t = threading.Timer(TEMPO_OCIOSO_DOS_AVISOS_S, self._fechar_ocioso)
        t.daemon = True
        self._ocioso = t
        t.start()

    def _fechar_ocioso(self):
        """Fecha o fluxo se faz TEMPO_OCIOSO s que nada toca."""
        with self._trava:
            if self._fluxo is None:
                return
            if self._agora() - self._ultimo < TEMPO_OCIOSO_DOS_AVISOS_S:
                return                         # tocou de novo: outro timer
            with self._trava_dados:
                if self._dados is not None:
                    return                     # ainda tocando
            self._fechar()

    def fechar(self):
        anterior, self._ocioso = self._ocioso, None
        if anterior is not None:
            anterior.cancel()
        with self._trava:
            with self._trava_dados:
                self._dados = None
            self._fechar()


_saida = None
_trava_saida = threading.Lock()


def _tocar_pelo_fluxo(dados, taxa, dispositivo=None):
    """Toca pelo fluxo dos avisos, abrindo-o so na primeira vez."""
    global _saida
    if _saida is None:
        # dois avisos ao mesmo tempo nao podem abrir dois fluxos
        with _trava_saida:
            if _saida is None:
                _saida = _SaidaDosAvisos()
    _saida.tocar(dados, taxa, dispositivo)


def fechar_sons():
    """Fecha o fluxo dos avisos (ao encerrar o programa)."""
    global _saida
    with _trava_saida:
        if _saida is not None:
            _saida.fechar()
            _saida = None


atexit.register(fechar_sons)

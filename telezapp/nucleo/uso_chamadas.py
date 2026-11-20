# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Registro de cada chamada para as informações de uso (opcionais). Sem wx.

Monta, por chamada, um registro só de categorias e números, para achar padrões
(plataforma de quem liga x resultado, grupos grandes x falha, codec, relay...).
Nunca vão: nome, telefone, id da conversa, id da chamada, nome dos relays,
país, hora exata.

De onde vêm os dados: a DLL escreve o andamento de cada chamada no registro
(módulo "whatsmeow.Client.Chamadas"); `LeitorDeChamadas` lê essas linhas e
junta o que elas dizem por id de chamada (o id fica só na memória, enquanto a
chamada existe). Quando a chamada termina, o provedor chama `concluir` com o
que só ele sabe (voz ou vídeo, grupo, link, motivo) e o registro vai para
`uso.registrar_chamada`. Ver docs/decisoes.md (19/11/2026).
"""
import logging
import re
import threading

log = logging.getLogger("telezapp.uso_chamadas")

MODULO_DA_DLL = "whatsmeow.Client.Chamadas"
MAX_EM_ANDAMENTO = 20            # chamadas acompanhadas ao mesmo tempo

_trava = threading.Lock()
_andamento = {}                  # id da chamada -> dados reunidos
_oferta_pendente = {}            # stanza da oferta, ainda sem id de chamada
_ultima = [""]                   # id da chamada mais recente

_CRIADA = re.compile(r"chamada (\w{6,64}) criada \(entrante=(true|false)")
_ATENDEU = re.compile(
    r"chamada (\w+): a outra pessoa atendeu, depois de ([\d.]+)s")
_FASE = re.compile(r"chamada (\w+): fase (\d+) depois de ([\d.]+)s")
_SOM = re.compile(
    r"chamada (\w+): som do outro lado chegou \(primeiro RTP\) depois de "
    r"([\d.]+)s")
_ENCERRADA = re.compile(
    r"chamada (\w+) encerrada \(([^)]*)\) depois de ([\d.]+)s: quadros do "
    r"outro lado=(\d+), do microfone=(\d+)")
_CODEC = re.compile(r'"call_id":"(\w+)","codec":"([\w.\-]{1,20})"')
_TENTATIVA = re.compile(
    r'"call_id":"(\w+)","relay":"[\w]+","tentativa":(\d+),"de":(\d+)')
_RELAYS = re.compile(
    r'"ofertas":"([^"]*)","escolhido":"([^"]*)","sem_fna_heuristica":'
    r'(true|false)')
_STANZA = re.compile(r'"stanza":"([^"]*)","filhos_da_oferta":"([^"]*)"')
_CONTROLE = re.compile(
    r'"controle":"offer","atributos":"([^"]*)","filhos":(\d+)')


def _registro(id_):
    """O registro em andamento da chamada (cria se preciso)."""
    r = _andamento.get(id_)
    if r is None:
        if len(_andamento) >= MAX_EM_ANDAMENTO:
            _andamento.pop(next(iter(_andamento)), None)
        r = _andamento[id_] = {}
    return r


def _aplicar_oferta(r):
    if _oferta_pendente and "plataforma" not in r:
        r.update(_oferta_pendente)
        _oferta_pendente.clear()


def _de_stanza(texto):
    """platform=android version=2.26.43.76 ... -> (plataforma, versao)."""
    d = dict(p.split("=", 1) for p in texto.split() if "=" in p)
    plat = re.sub(r"[^a-z0-9]", "", d.get("platform", "").lower())[:12]
    ver = d.get("version", "")
    return plat or "desconhecida", ver if re.fullmatch(
        r"[\d.]{1,20}", ver) else ""


def _faixa_rx(n):
    for limite, texto in ((1, "0"), (100, "1 a 99"), (1000, "100 a 999")):
        if n < limite:
            return texto
    return "1000 ou mais"


def _faixa_pessoas(n):
    for limite, texto in ((2, "0 a 1"), (3, "2"), (6, "3 a 5"),
                          (11, "6 a 10"), (21, "11 a 20")):
        if n < limite:
            return texto
    return "21 ou mais"


def tratar_linha(msg):
    """Lê uma linha do registro da DLL e guarda o que ela diz da chamada."""
    if "chamada" not in msg and "oferta" not in msg and "relay" not in msg \
            and "codec" not in msg and "controle" not in msg:
        return
    with _trava:
        m = _CRIADA.search(msg)
        if m:
            r = _registro(m.group(1))
            r["entrante"] = m.group(2) == "true"
            _ultima[0] = m.group(1)
            if r["entrante"]:
                _aplicar_oferta(r)
            return
        m = _ATENDEU.search(msg)
        if m:
            _registro(m.group(1))["t_atender_s"] = round(float(m.group(2)), 1)
            return
        m = _FASE.search(msg)
        if m:
            # na chamada recebida, a fase 3 (Connecting) e o momento em que
            # NOS atendemos; na de saida ela vem quando o relay e alocado
            if m.group(2) == "3":
                _registro(m.group(1)).setdefault(
                    "t_fase3_s", round(float(m.group(3)), 1))
            return
        m = _SOM.search(msg)
        if m:
            _registro(m.group(1))["t_som_s"] = round(float(m.group(2)), 1)
            return
        m = _ENCERRADA.search(msg)
        if m:
            r = _registro(m.group(1))
            r["motivo_dll"] = re.sub(r"[^a-z_]", "", m.group(2).lower())[:30]
            r["dur_s"] = round(float(m.group(3)), 1)
            r["rx"], r["tx"] = int(m.group(4)), int(m.group(5))
            return
        m = _CODEC.search(msg)
        if m:
            _registro(m.group(1))["codec"] = m.group(2)
            return
        m = _TENTATIVA.search(msg)
        if m:
            r = _registro(m.group(1))
            r["relay_tentativa"] = max(int(m.group(2)),
                                       r.get("relay_tentativa", 0))
            r["relays"] = max(int(m.group(3)), r.get("relays", 0))
            return
        m = _RELAYS.search(msg)
        if m:
            _aplicar_relays(_registro(_ultima[0] or "?"), m.group(1),
                            m.group(2), m.group(3) == "true")
            return
        m = _STANZA.search(msg)
        if m:
            plat, ver = _de_stanza(m.group(1))
            _oferta_pendente.clear()
            _oferta_pendente.update({"plataforma": plat, "versao_wa": ver,
                                     "itens_da_oferta": len(
                                         m.group(2).split())})
            return
        m = _CONTROLE.search(msg)
        if m:
            attrs = dict(p.split("=", 1) for p in m.group(1).split()
                         if "=" in p)
            id_ = re.sub(r"[^\w]", "", attrs.get("call-id", ""))
            if id_:
                r = _registro(id_)
                _aplicar_oferta(r)
                dc = attrs.get("device_class", "")
                if dc.isdigit():
                    r["classe"] = int(dc)
                r["itens_da_oferta"] = int(m.group(2))


def _aplicar_relays(r, ofertas, escolhido, heuristica):
    """Quantos relays vieram, em que posição de RTT ficou o escolhido e se
    algum era FNA. Os nomes dos relays não vão."""
    itens = re.findall(r"(\w+)\(fna=(\w+) tok=\d+ auth=\d+ rtt=(\d+)\)",
                       ofertas)
    if not itens:
        return
    r["relays"] = max(len(itens), r.get("relays", 0))
    ordem = sorted(int(rtt) for _, _, rtt in itens)
    for nome, _, rtt in itens:
        if nome == escolhido:
            r["relay_posicao_rtt"] = ordem.index(int(rtt)) + 1
    r["relay_fna"] = any(f == "true" for _, f, _ in itens)
    r["relay_heuristica"] = heuristica


class LeitorDeChamadas(logging.Handler):
    def emit(self, registro):
        try:
            tratar_linha(registro.getMessage())
        except Exception:
            pass


_instalado = False


def instalar():
    global _instalado
    if not _instalado:
        logging.getLogger(MODULO_DA_DLL).addHandler(LeitorDeChamadas())
        _instalado = True


def concluir(call_id, *, entrante, video, grupo, por_link, motivo,
             sem_som, pessoas=0, servico="whatsapp"):
    """Fecha o registro da chamada e o entrega ao resumo de uso. `motivo` é o
    da janela (desligada, recusada, perdida...). Devolve o registro (ou
    None, se nada foi aprendido). Nunca levanta erro."""
    try:
        with _trava:
            r = dict(_andamento.pop(call_id, {}))
            if _ultima[0] == call_id:
                _ultima[0] = ""
        rx, tx = r.pop("rx", 0), r.pop("tx", 0)
        dur = r.get("dur_s", 0)
        # o tempo do som conta desde o atendimento, nao desde o toque (senao
        # entram os segundos que a pessoa levou para atender)
        atendeu = r.get("t_fase3_s") if entrante else r.get("t_atender_s")
        if atendeu is not None:
            r["t_toque_s"] = atendeu
            if r.get("t_som_s") is not None and r["t_som_s"] >= atendeu:
                r["t_som_apos_atender_s"] = round(r["t_som_s"] - atendeu, 1)
        resultado = motivo or "desligada"
        if sem_som or (resultado == "desligada" and not rx and dur > 15
                       and not grupo):
            resultado = "sem_som"
        reg = {
            "servico": servico,
            "direcao": "entrada" if entrante else "saida",
            "tipo": "video" if video else "voz",
            "grupo": bool(grupo), "link": bool(por_link),
            "resultado": resultado,
            "rx": _faixa_rx(rx), "tx": _faixa_rx(tx),
        }
        if grupo:
            reg["pessoas"] = _faixa_pessoas(pessoas)
        for k in ("plataforma", "versao_wa", "classe", "itens_da_oferta",
                  "codec", "relays", "relay_tentativa", "relay_posicao_rtt",
                  "relay_fna", "relay_heuristica", "t_toque_s",
                  "t_som_apos_atender_s", "dur_s", "motivo_dll"):
            if k in r:
                reg[k] = r[k]
        from telezapp.nucleo import uso
        uso.registrar_chamada(reg)
        return reg
    except Exception:
        log.exception("registro da chamada para as informações de uso")
        return None

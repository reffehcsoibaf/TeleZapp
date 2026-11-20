# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Estatísticas do comportamento do programa a partir dos logs que chegam pelo
Feedback. Roda só neste computador, offline, e não guarda nada por relato: o
resultado são totais (sem nomes, telefones nem ids de conversa ou de chamada).

Uso (na pasta do projeto):
    venv\\Scripts\\python.exe ferramentas\\analisar_logs.py [pasta ...]
        [--saida C:\\logs\\estatisticas-dos-relatos.md]

Sem pastas, lê C:\\logs\\relatos. Reconhece os logs pelo conteúdo (linhas
"AAAA-MM-DD HH:MM:SS NIVEL modulo: texto"), em qualquer subpasta. Cada linha
entra uma vez só, mesmo que dois relatos tragam o mesmo trecho.

Atenção: quem manda log tem problema. Os números servem para comparar grupos
e achar padrões, nunca como taxa de falha.

As chamadas usam o mesmo leitor do resumo de uso (nucleo/uso_chamadas.py).
"""
import argparse
import collections
import hashlib
import os
import re
import statistics
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from telezapp.nucleo import uso, uso_chamadas as uc   # noqa: E402

LINHA = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) "
                   r"(DEBUG|INFO|WARNING|ERROR|CRITICAL) ([\w.]+): (.*)$")
DLL = uc.MODULO_DA_DLL
MOTIVOS = {"desligada": "desligada", "perdida": "perdida",
           "recusada": "recusada", "cancelada": "cancelada",
           "sem resposta": "sem_resposta", "ocupado": "ocupado",
           "falha": "falha"}


def e_log(caminho):
    """Um arquivo de texto com linhas de log do TeleZapp."""
    if os.path.splitext(caminho)[1].lower() in (".html", ".htm", ".py",
                                               ".md", ".json"):
        return False
    try:
        with open(caminho, encoding="utf-8", errors="replace") as f:
            return any(LINHA.match(f.readline()) for _ in range(30))
    except OSError:
        return False


def achar_logs(pastas):
    """{pasta do relato: [arquivos de log]}."""
    achados = collections.defaultdict(list)
    for pasta in pastas:
        for raiz, _, nomes in os.walk(pasta):
            for nome in nomes:
                caminho = os.path.join(raiz, nome)
                if e_log(caminho):
                    achados[raiz].append(caminho)
    return achados


def queda_do_whatsapp(texto):
    """Mesma regra de provedores.whatsapp.sinal_de_queda."""
    if "Received stream end frame" in texto or "503 stream error" in texto:
        return "servidor"
    if "Keepalive timed out" in texto:
        return "keepalive"
    if "Error reading from websocket" in texto:
        return "rede" if any(p in texto for p in (
            "read tcp", "reset", "timeout")) else "EOF"
    return ""


class Estatisticas:
    def __init__(self):
        self.vistas = set()
        self.relatos = 0
        self.linhas = 0
        self.versoes = collections.Counter()
        self.sem_fechar = 0
        self.banco = collections.Counter()
        self.lentos = collections.defaultdict(lambda: [0, 0.0])
        self.registro = collections.Counter()
        self.quedas = collections.Counter()
        self.chamadas = []

    # ---------------------------------------------------------- por relato
    def ler_relato(self, arquivos):
        linhas = []
        for caminho in arquivos:
            with open(caminho, encoding="utf-8", errors="replace") as f:
                for texto in f:
                    m = LINHA.match(texto.rstrip("\r\n"))
                    if not m:
                        continue
                    chave = hashlib.sha1(texto.encode("utf-8", "replace")
                                         ).digest()
                    if chave in self.vistas:
                        continue
                    self.vistas.add(chave)
                    linhas.append(m.groups())
        if not linhas:
            return
        self.relatos += 1
        linhas.sort(key=lambda x: x[0])        # os logs antigos primeiro
        self.linhas += len(linhas)
        versao = ""
        uc._andamento.clear()
        uc._oferta_pendente.clear()
        uso._chamadas.clear()
        video, pendente, sem_som = {}, None, set()
        for quando, nivel, modulo, msg in linhas:
            m = re.search(r"==== TeleZapp (\S+) iniciado", msg)
            if m:
                versao = m.group(1)
            if "terminou sem fechar normalmente" in msg:
                self.sem_fechar += 1
            m = re.search(r"conferência do banco \S+: (\w+) em", msg)
            if m:
                self.banco[m.group(1)] += 1
            m = re.search(r"lento: (\w+) demorou ([\d.]+) s", msg)
            if m:
                v = self.lentos[m.group(1)]
                v[0] += 1
                v[1] = max(v[1], float(m.group(2)))
            if nivel in ("WARNING", "ERROR", "CRITICAL") and modulo != DLL \
                    and not msg.startswith("lento:"):
                nome = modulo[len("telezapp."):] if modulo.startswith(
                    "telezapp.") else modulo
                self.registro[(nome, "erro" if nivel != "WARNING"
                               else "aviso")] += 1
            queda = queda_do_whatsapp(msg)
            if queda:
                self.quedas[queda] += 1
            if modulo == DLL:
                uc.tratar_linha(msg)
                m = re.search(r'"call_id":"(\w+)","video":true', msg)
                if m:
                    video[m.group(1)] = True
                m = re.search(r'"call_id":"(\w+)","message":"inbound call '
                              r'advertises video"', msg)
                if m:
                    video[m.group(1)] = True
                if "atendida, mas sem som do outro lado" in msg and \
                        uc._ultima[0]:
                    sem_som.add(uc._ultima[0])
                m = re.search(r"chamada (\w{6,64}) encerrada \(", msg)
                if m:
                    pendente = m.group(1)
            m = re.search(r"telezapp\.janela: chamada: encerrada (.+)$",
                          ("%s: %s" % (modulo, msg)).strip())
            if m and pendente:
                motivo = MOTIVOS.get(m.group(1).strip(), "")
                if motivo:
                    r = uc._andamento.get(pendente, {})
                    uc.concluir(pendente,
                                entrante=r.get("entrante", False),
                                video=video.get(pendente, False),
                                grupo=False, por_link=False, motivo=motivo,
                                sem_som=pendente in sem_som)
                pendente = None
        self.versoes[versao or "?"] += 1
        self.chamadas.extend(uso._chamadas)
        uso._chamadas.clear()

    # ------------------------------------------------------------ relatorio
    def relatorio(self):
        s = []

        def cab(t):
            s.append("\n## " + t + "\n")

        def tabela(contagem, titulo, minimo=1):
            s.append("**%s**\n" % titulo)
            for k, n in sorted(contagem.items(), key=lambda x: -x[1]):
                if n >= minimo:
                    s.append("- %s: %d" % (k, n))
            if not contagem:
                s.append("- nenhum")
            s.append("")

        s.append("# Estatísticas dos logs dos relatos")
        s.append("\nUma amostra de **suporte**: quem manda log tem problema. "
                 "Compare grupos; não leia como taxa de falha.\n")
        s.append("- Relatos com log lidos: %d" % self.relatos)
        s.append("- Linhas de log distintas: %d" % self.linhas)
        s.append("- Aberturas em que a vez anterior terminou sem fechar: %d"
                 % self.sem_fechar)
        tabela(self.versoes, "Versão do programa (última do log de cada "
                             "relato)")
        cab("Chamadas do WhatsApp (%d registros)" % len(self.chamadas))
        self._chamadas(s, tabela)
        cab("Conexão e programa")
        tabela(self.quedas, "Sinais de queda da conexão do WhatsApp, por "
                            "causa (linhas do registro)")
        tabela(self.banco, "Conferência do banco ao abrir")
        s.append("**Ações da janela acima de 0,2 s (vezes; pior tempo)**\n")
        s.append("(Ações que abrem uma janela, como menus e diálogos, "
                 "contam o tempo em que ela ficou aberta: o pior tempo delas "
                 "não diz nada.)\n")
        for k, (n, pior) in sorted(self.lentos.items(),
                                   key=lambda x: -x[1][0])[:25]:
            s.append("- %s: %d vezes, pior %.1f s" % (k, n, pior))
        if not self.lentos:
            s.append("- nenhuma")
        s.append("")
        s.append("**Avisos e erros do registro, por módulo**\n")
        for (nome, nivel), n in self.registro.most_common(30):
            s.append("- %s (%s): %d" % (nome, nivel, n))
        return "\n".join(s) + "\n"

    def _chamadas(self, s, tabela):
        cs = self.chamadas
        if not cs:
            s.append("Nenhuma chamada nos logs.\n")
            return
        rotulo = lambda c: "%s %s%s%s" % (
            "recebida" if c["direcao"] == "entrada" else "feita", c["tipo"],
            " (grupo)" if c.get("grupo") else "", "")
        tabela(collections.Counter(c["resultado"] for c in cs), "Resultado")
        tabela(collections.Counter("%s → %s" % (rotulo(c), c["resultado"])
                                   for c in cs), "Tipo × resultado")
        rec = [c for c in cs if c["direcao"] == "entrada"]
        tabela(collections.Counter(
            "%s %s → %s" % (c.get("plataforma", "?"), c.get("versao_wa", "?"),
                            c["resultado"]) for c in rec),
            "Recebidas: quem liga (plataforma e versão do WhatsApp) × "
            "resultado")
        tabela(collections.Counter(
            "classe %s → %s" % (c.get("classe", "sem"), c["resultado"])
            for c in rec), "Recebidas: classe do aparelho × resultado")
        tabela(collections.Counter(
            "%s → %s" % (c.get("codec", "?"), c["resultado"]) for c in cs),
            "Codec × resultado")
        tabela(collections.Counter(
            "tentativa %s de %s" % (c["relay_tentativa"], c.get("relays", "?"))
            for c in rec if c.get("relay_tentativa")),
            "Recebidas: tentativa de relay em que o áudio entrou")
        tabela(collections.Counter(
            "%sº menor RTT%s" % (c["relay_posicao_rtt"], " (regra sem FNA)"
                                 if c.get("relay_heuristica") else "")
            for c in rec if c.get("relay_posicao_rtt")),
            "Recebidas: posição do relay escolhido")
        por = collections.defaultdict(list)
        for c in rec:
            if c.get("t_som_apos_atender_s") is not None:
                por[c.get("plataforma", "?")].append(
                    c["t_som_apos_atender_s"])
        s.append("**Tempo entre atender e o som do outro lado chegar, por "
                 "plataforma de quem liga**\n")
        for p, v in sorted(por.items()):
            s.append("- %s: mediana %.1f s, máximo %.1f s (%d chamadas)" % (
                p, statistics.median(v), max(v), len(v)))
        if not por:
            s.append("- sem dados")
        s.append("")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pastas", nargs="*", default=[r"C:\logs\relatos"])
    ap.add_argument("--saida", default=r"C:\logs\estatisticas-dos-relatos.md")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    est = Estatisticas()
    for pasta, arquivos in sorted(achar_logs(a.pastas).items()):
        est.ler_relato(sorted(arquivos))
    texto = est.relatorio()
    os.makedirs(os.path.dirname(a.saida), exist_ok=True)
    with open(a.saida, "w", encoding="utf-8") as f:
        f.write(texto)
    print(texto)
    print("Relatório gravado em", a.saida)


if __name__ == "__main__":
    main()

def conserta(p, trocas):
    s = open(p, encoding='utf-8').read()
    for old, novo in trocas:
        assert s.count(old) == 1, old[:70]
        s = s.replace(old, novo)
    open(p, 'w', encoding='utf-8').write(s)

conserta('telezapp/nucleo/atualizacao.py', [
('''import json
import re
import urllib.error
import urllib.request
''','''import json
import logging
import re
import socket
import ssl
import urllib.error
import urllib.request
'''),
('''REPO = "reffehcsoibaf/TeleZapp"''','''log = logging.getLogger("telezapp.atualizacao")

REPO = "reffehcsoibaf/TeleZapp"'''),
('''def consultar(buscar=_buscar_json):
    """O lancamento mais novo publicado (ou None se ainda nao ha nenhum).
    ErroAtualizacao se nao der para consultar o GitHub."""
    try:
        return mais_nova(buscar(URL_LANCAMENTOS))
    except (urllib.error.URLError, OSError, ValueError):
        raise ErroAtualizacao(
            "Não consegui consultar o GitHub. Veja a conexão com a internet "
            "e tente de novo.")
''','''def motivo_da_falha(erro):
    """Por que a consulta falhou, em palavras, para a pessoa e para o log."""
    if isinstance(erro, urllib.error.HTTPError):
        if erro.code in (403, 429):
            return ("o GitHub limitou as consultas feitas a partir deste "
                    "endereço de internet; tente de novo daqui a uma hora")
        return "o GitHub respondeu com o erro %d" % erro.code
    causa = getattr(erro, "reason", erro)
    if isinstance(causa, ssl.SSLError) or "CERTIFICATE" in str(causa).upper():
        return ("o Windows não confiou no certificado do GitHub; confira a "
                "data e a hora do computador e o antivírus")
    if isinstance(causa, (socket.timeout, TimeoutError)):
        return "o GitHub demorou demais para responder"
    if isinstance(causa, socket.gaierror):
        return ("não achei o endereço do GitHub; confira a conexão com a "
                "internet e o DNS")
    if isinstance(erro, ValueError):
        return "a resposta do GitHub veio em um formato inesperado"
    return "a conexão com o GitHub falhou (%s)" % type(causa).__name__


def _pelo_site(tempo=10):
    """Plano B quando a consulta da API falha (por exemplo, pelo limite de
    consultas por endereco): o proprio site do GitHub leva da pagina da
    ultima Release comum para a pagina da versao, e dai saem os enderecos do
    zip e do hash. Sem as notas (a pessoa as ve na pagina)."""
    pedido = urllib.request.Request(
        SITE + "/releases/latest", headers={
            "User-Agent": "TeleZapp/" + VERSAO})
    with urllib.request.urlopen(pedido, timeout=tempo) as r:
        final = r.geturl()
    achou = re.search(r"/releases/tag/([^/?#]+)$", final)
    versao = achou.group(1).lstrip("vV") if achou else ""
    if como_tupla(versao) is None:
        raise ValueError("pagina da ultima versao inesperada")
    base = "%s/releases/download/%s/" % (SITE, achou.group(1))
    return Lancamento(
        versao, "", final, False, "TeleZapp.zip", base + "TeleZapp.zip",
        base + "TeleZapp.zip.sha256", 0,
        [(versao, "As novidades estão na página da versão: " + final)])


def consultar(buscar=_buscar_json, pelo_site=None):
    """O lancamento mais novo publicado (ou None se ainda nao ha nenhum).
    ErroAtualizacao se nao der para consultar o GitHub."""
    if pelo_site is None and buscar is _buscar_json:
        pelo_site = _pelo_site
    try:
        return mais_nova(buscar(URL_LANCAMENTOS))
    except (urllib.error.URLError, OSError, ValueError) as erro:
        motivo = motivo_da_falha(erro)
        log.warning("consulta da API falhou: %s (%s)", type(erro).__name__,
                    motivo)
        if pelo_site is not None:
            try:
                lanc = pelo_site()
                log.info("versao achada pelo site do GitHub: %s", lanc.versao)
                return lanc
            except (urllib.error.URLError, OSError, ValueError) as erro2:
                log.warning("consulta pelo site tambem falhou: %s",
                            type(erro2).__name__)
        raise ErroAtualizacao(
            "Não consegui consultar o GitHub: %s." % motivo)
'''),
])
conserta('ferramentas/publicar.py', [
('''    python ferramentas\\publicar.py --publicar         e cria a Release
                                                      (pre-lancamento)
    python ferramentas\\publicar.py --publicar --final  Release comum''','''    python ferramentas\\publicar.py --publicar         e cria a Release comum,
                                                      a "latest" do GitHub
    python ferramentas\\publicar.py --publicar --prerelease
                                                      e cria um pre-lancamento'''),
('''    ap.add_argument("--final", action="store_true",
                    help="com --publicar: Release comum, nao pre-lancamento")''','''    ap.add_argument("--prerelease", action="store_true",
                    help="com --publicar: pre-lancamento (o padrao e a "
                         "Release comum, a latest)")
    ap.add_argument("--final", action="store_true",
                    help=argparse.SUPPRESS)      # antigo: agora e o padrao'''),
('''    if not args.final:
        comando.append("--prerelease")''','''    comando.append("--prerelease" if args.prerelease else "--latest")'''),
])

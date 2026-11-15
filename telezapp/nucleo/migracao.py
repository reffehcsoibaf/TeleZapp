# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Os lugares onde os dados das contas ficam, e as passagens entre eles.

Com a separacao marcada (opcao "contas_em_pastas"), cada conta tem a
propria pasta (ver config.pasta_da_conta): conversas.db, sessoes\\ e
midias\\ dentro dela; a raiz das pastas das contas e a pasta de dados do
TeleZapp (\\contas) ou a pasta escolhida nas configuracoes (opcao
"contas_pasta"). Desmarcada, todas as contas dividem o layout antigo: um
banco so, as sessoes e as midias na raiz do layout antigo — a pasta
escolhida, se a personalizada estiver marcada, ou a pasta de dados
(<dados>\\telezapp.db, <dados>\\sessoes e <dados>\\midias\\<conta>).

migrar(cfg), na abertura, poe os dados no layout que as opcoes pedem:
para as pastas (do banco antigo, ou da pasta padrao para a escolhida) ou
de volta ao banco unico. Tudo pode ser interrompido: recomeca de onde
parou, e nada e apagado da origem sem conferir o destino.
"""
import logging
import os
import shutil
import sqlite3
import time

from telezapp import config
from telezapp.armazenamento.banco import Banco, TABELAS
from telezapp.armazenamento.bancos import NOME_ARQUIVO
from telezapp.midia import armazem
from telezapp.nucleo import backup

log = logging.getLogger("telezapp.migracao")

SUFIXO_ANTIGO = ".antes-da-migracao"

# Quantas vezes e quanto tempo se espera por arquivos que o provedor, que
# acabou de desligar, ainda nao soltou (Windows nao apaga arquivo em uso)
TENTATIVAS = 4
ESPERA = 0.5


def _apagar_com_espera(caminho):
    """Apaga um arquivo, esperando ele soltar. Sem erro se nao conseguir:
    o que ficou para tras e lixo que a pessoa pode apagar depois."""
    for _ in range(TENTATIVAS):
        try:
            os.remove(caminho)
            return True
        except OSError:
            time.sleep(ESPERA)
    log.info("não consegui apagar: %s", caminho)
    return False


def _rmtree_com_espera(pasta):
    """Apaga uma pasta inteira, esperando os arquivos soltarem. Sem erro
    quando algo nao sai (a exclusao e tentada de novo a cada tentativa)."""
    for _ in range(TENTATIVAS):
        shutil.rmtree(pasta, ignore_errors=True)
        if not os.path.isdir(pasta):
            return True
        time.sleep(ESPERA)
    log.info("não consegui apagar por completo: %s", pasta)
    return False


def _rmdir_com_espera(pasta):
    """Tira a pasta (que deve estar vazia), esperando soltar."""
    for _ in range(TENTATIVAS):
        try:
            os.rmdir(pasta)
            return True
        except OSError:
            time.sleep(ESPERA)
    log.info("a pasta não ficou vazia: %s", pasta)
    return False


def _copiar_arquivo(origem, destino):
    """Copia um arquivo conferindo o tamanho (a origem fica no lugar)."""
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    shutil.copy2(origem, destino)
    if os.path.getsize(origem) != os.path.getsize(destino):
        os.remove(destino)
        raise OSError("A cópia de %s não conferiu." %
                      os.path.basename(origem))


def _mover_arquivo(origem, destino):
    """Move um arquivo entre pastas (e entre unidades: copia, confere o
    tamanho e so entao apaga a origem). O que ja existir no destino e
    trocado pelo que vem da origem."""
    if os.path.isdir(destino):
        shutil.rmtree(destino, ignore_errors=True)
    elif os.path.exists(destino):
        os.remove(destino)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    try:
        os.rename(origem, destino)
        return
    except OSError:
        pass        # unidades diferentes (ou arquivo travado): copia
    _copiar_arquivo(origem, destino)
    _apagar_com_espera(origem)


def _copiar_pasta(origem, destino):
    """Copia uma pasta inteira conferindo o resultado (quantidade de
    arquivos e bytes). A origem fica no lugar."""
    if os.path.isdir(destino):
        shutil.rmtree(destino)
    elif os.path.exists(destino):
        os.remove(destino)
    os.makedirs(os.path.dirname(destino) or destino, exist_ok=True)
    for tentativa in range(TENTATIVAS):     # a copia pode achar arquivo
        try:                                # que o provedor ainda segura
            shutil.copytree(origem, destino)
            break
        except OSError as erro:
            if tentativa == TENTATIVAS - 1:
                raise
            log.info("copiar %s falhou (%r); tentando de novo",
                     os.path.basename(origem), erro)
            shutil.rmtree(destino, ignore_errors=True)
            time.sleep(ESPERA)

    def tamanho(raiz):
        n, bytes_ = 0, 0
        for pasta, _, arquivos in os.walk(raiz):
            for a in arquivos:
                n += 1
                try:
                    bytes_ += os.path.getsize(os.path.join(pasta, a))
                except OSError:
                    pass
        return n, bytes_
    if tamanho(origem) != tamanho(destino):
        shutil.rmtree(destino, ignore_errors=True)
        raise OSError("A cópia de %s não conferiu." %
                      os.path.basename(origem))


def _mover_pasta(origem, destino):
    """Move uma pasta inteira, conferindo o resultado antes de apagar a
    origem."""
    _copiar_pasta(origem, destino)
    _rmtree_com_espera(origem)


def _juntar_pasta(origem, destino, apagar=True):
    """Leva de `origem` para `destino` (mesmo layout) so o que falta. O
    que o destino ja tem fica. Com `apagar`, a origem e apagada no fim
    (o que estiver travado fica para tras)."""
    for raiz, _, arquivos in os.walk(origem):
        rel = os.path.relpath(raiz, origem)
        alvo = destino if rel == "." else os.path.join(destino, rel)
        os.makedirs(alvo, exist_ok=True)
        for a in arquivos:
            de, para = os.path.join(raiz, a), os.path.join(alvo, a)
            if os.path.exists(para):
                _apagar_com_espera(de)      # o destino ja tem: fica o dele
            else:
                _mover_arquivo(de, para)
    if apagar:
        _rmtree_com_espera(origem)


# ---------------------------------------------- o layout antigo mudando
def _mesma_pasta(a, b):
    """Os dois caminhos apontam para a mesma pasta?"""
    return os.path.normcase(os.path.abspath(a)) == \
        os.path.normcase(os.path.abspath(b))


def _raizes_conhecidas_do_layout_antigo(cfg):
    """As pastas onde o layout antigo pode estar: a de dados e a pasta
    escolhida (mesmo desmarcada, pode ter ficado de uma configuracao
    anterior)."""
    saida = []
    for pasta in (config.pasta_dados(),
                  (cfg.get("contas_pasta") or "").strip()):
        if not pasta or any(_mesma_pasta(pasta, p) for p in saida):
            continue
        saida.append(pasta)
    return saida


def _copiar_o_que_falta(origem, destino):
    """Copia de `origem` para `destino` so o que falta (o que o destino ja
    tem fica), conferindo o tamanho de cada copia. A origem fica no
    lugar."""
    for raiz, _, arquivos in os.walk(origem):
        rel = os.path.relpath(raiz, origem)
        alvo = destino if rel == "." else os.path.join(destino, rel)
        os.makedirs(alvo, exist_ok=True)
        for nome in arquivos:
            de, para = os.path.join(raiz, nome), os.path.join(alvo, nome)
            if os.path.isfile(para) and \
                    os.path.getsize(para) == os.path.getsize(de):
                continue        # ja esta la (e inteiro)
            _copiar_arquivo(de, para)


SUFIXOS_DO_BANCO = ("", "-wal", "-shm", "-journal")


def _levar_uma_raiz_antiga(origem, destino):
    """Leva o banco unico, as sessoes e as midias de `origem` para
    `destino`. Primeiro copia tudo (conferindo), depois acerta os caminhos
    das midias no banco novo e so entao apaga a origem: se algo falhar no
    meio, a origem fica inteira e a proxima abertura tenta de novo. Se as
    duas pastas ja tem banco unico, nao mexe em nada."""
    db_origem = os.path.join(origem, "telezapp.db")
    db_destino = os.path.join(destino, "telezapp.db")
    midias_origem = os.path.join(origem, "midias")
    midias_destino = os.path.join(destino, "midias")
    sessoes_origem = os.path.join(origem, "sessoes")
    sessoes_destino = os.path.join(destino, "sessoes")
    tem_db = os.path.isfile(db_origem)
    if tem_db and os.path.isfile(db_destino):
        log.warning("há um banco único em %s e outro em %s; não mexo em "
                    "nenhum dos dois", origem, destino)
        return
    mudou = False
    if os.path.isdir(midias_origem) and os.listdir(midias_origem):
        _copiar_o_que_falta(midias_origem, midias_destino)
        mudou = True
    if os.path.isdir(sessoes_origem) and os.listdir(sessoes_origem):
        _copiar_o_que_falta(sessoes_origem, sessoes_destino)
        mudou = True
    if tem_db:
        os.makedirs(destino, exist_ok=True)
        for sufixo in SUFIXOS_DO_BANCO:
            de = db_origem + sufixo
            if os.path.exists(de):
                _copiar_arquivo(de, db_destino + sufixo)
        try:
            # os caminhos guardados no banco apontam para a pasta antiga:
            # trocam para a nova antes de a origem sair
            _acertar_caminhos_da_pasta(db_destino, midias_origem,
                                       midias_destino)
        except (sqlite3.Error, OSError):
            for sufixo in SUFIXOS_DO_BANCO:
                _apagar_com_espera(db_destino + sufixo)
            raise
        mudou = True
    if not mudou:
        return
    # tudo copiado e conferido: so agora a origem sai
    for sufixo in SUFIXOS_DO_BANCO:
        _apagar_com_espera(db_origem + sufixo)
    if os.path.isdir(midias_origem):
        _rmtree_com_espera(midias_origem)
    if os.path.isdir(sessoes_origem):
        _rmtree_com_espera(sessoes_origem)


def _levar_o_layout_antigo(cfg):
    """Leva o layout antigo inteiro (o banco unico, as sessoes e as
    midias) para a pasta escolhida ou, quando a pasta personalizada e
    desmarcada, de volta para a pasta de dados. Nao derruba a abertura: o
    que falhar fica onde esta, os caminhos antigos continuam valendo e a
    proxima abertura tenta de novo."""
    destino = config.pasta_escolhida_do_layout_antigo(cfg)
    for origem in _raizes_conhecidas_do_layout_antigo(cfg):
        if _mesma_pasta(origem, destino):
            continue
        try:
            _levar_uma_raiz_antiga(origem, destino)
        except (sqlite3.Error, OSError) as erro:
            log.warning("não consegui levar os dados de %s para %s (%r); "
                        "ficam onde estão e a próxima abertura tenta de "
                        "novo", origem, destino, erro)


# ------------------------------------------------------------- a migracao
def migrar(cfg):
    """Uma vez por abertura: poe os dados das contas no layout que as
    opcoes de Sistema pedem. Devolve quantas contas mudaram de lugar."""
    config.definir_cfg(cfg)
    if config.contas_separadas():
        n = _migrar_para_pastas(cfg) + _levar_para_a_pasta_escolhida(cfg)
    else:
        # primeiro o layout antigo inteiro (banco, sessoes e midias) vai
        # para a pasta escolhida, se a pasta mudou; so entao as contas
        # voltam para o banco unico, ja no lugar certo
        _levar_o_layout_antigo(cfg)
        n = _voltar_ao_layout_antigo(cfg)
    if n:
        log.info("migracao das pastas das contas: %d conta(s)", n)
    return n


def _migrar_para_pastas(cfg):
    """Com a separacao marcada: leva cada conta do layout antigo (o banco
    compartilhado <dados>\\telezapp.db, que fica renomeado, como copia de
    seguranca) para a pasta dela. Pode ser interrompida: o que ja migrou
    e pulado, e um banco de conta que ja existia recebe as linhas que
    faltaram por cima (`copiar_conta_de`)."""
    raiz = config.pasta_do_layout_antigo()
    antigo_db = os.path.join(raiz, "telezapp.db")
    if not os.path.isfile(antigo_db):
        return 0
    antigo = Banco(antigo_db)       # tambem atualiza o esquema se faltar
    migradas = 0
    falharam = 0
    try:
        for dados in cfg.contas():
            conta_id = dados.get("id")
            if not conta_id:
                continue
            try:
                if _migrar_conta(conta_id, raiz, antigo):
                    migradas += 1
            except (sqlite3.Error, OSError) as erro:
                # nao derruba a abertura: uma conta que nao pode ser levada
                # agora fica onde esta e a proxima abertura tenta de novo
                falharam += 1
                log.warning("não consegui levar %s para a pasta dela (%r); "
                            "a próxima abertura tenta de novo", conta_id,
                            erro)
        antigo.fechar()
        if falharam:
            # nem tudo foi levado: o banco antigo fica no lugar (com as
            # linhas que sobraram) para a proxima abertura terminar; o que
            # ja foi copiado e fundido de novo sem duplicar
            log.warning("migração para as pastas incompleta: %d conta(s) "
                        "ficaram; o banco antigo fica para a próxima "
                        "abertura", falharam)
            return migradas
        for sufixo in ("", "-wal", "-shm", "-journal"):
            de = antigo_db + sufixo
            if os.path.exists(de):
                destino = de + SUFIXO_ANTIGO
                n = 1
                while os.path.exists(destino):
                    n += 1       # ja ha uma copia com esse nome: numera
                    destino = "%s-%d" % (de + SUFIXO_ANTIGO, n)
                try:
                    os.rename(de, destino)
                except OSError as erro:
                    log.warning("o banco antigo ficou no lugar (%r)", erro)
                    break
    finally:
        try:
            antigo.fechar()
        except Exception:
            pass
    return migradas


def _migrar_conta(conta_id, raiz, antigo):
    """Leva os dados de uma conta do layout compartilhado para a pasta
    dela. False se a conta ja tinha o banco na pasta (de um migrar
    interrompido ou de um restore de backup antigo: as linhas que sobraram
    no banco antigo sao fundidas nas que ja estao la)."""
    pasta = config.pasta_da_conta(conta_id)
    novo_db = os.path.join(pasta, NOME_ARQUIVO)
    ja_tem = os.path.isfile(novo_db)
    os.makedirs(os.path.join(pasta, "sessoes"), exist_ok=True)
    # sessoes: do <dados>\\sessoes para a pasta da conta, so as que faltam
    # (a sessao que a conta usa agora nunca e trocada pela de la tras)
    legado = os.path.join(raiz, "sessoes")
    if os.path.isdir(legado):
        for nome in os.listdir(legado):
            if nome == conta_id + ".db" or \
                    nome.startswith(conta_id + ".db-") or \
                    nome.startswith(conta_id + ".session"):
                destino = os.path.join(pasta, "sessoes", nome)
                if not os.path.exists(destino):
                    _mover_arquivo(os.path.join(legado, nome), destino)
    # midias: vao da raiz (<dados>\\midias\\<conta>) para a pasta da conta,
    # menos quando a conta ja tem as dela (entao as que ficaram na raiz
    # continuam validas pelos caminhos que a elas apontam)
    legado_midias = os.path.join(raiz, "midias", armazem._limpo(conta_id, 80))
    pasta_midias = os.path.join(pasta, "midias")
    vamos_mover = os.path.isdir(legado_midias) and \
        not os.path.isdir(pasta_midias)
    # linhas: copiadas (ou fundidas) do banco antigo para o banco da conta
    novo = Banco(novo_db)
    try:
        novo.copiar_conta_de(conta_id, antigo)
        # a copia pode deixar o -wal do banco da conta enorme; despeja-lo
        # para o arquivo antes da proxima escrita
        try:
            novo._con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error as erro:
            log.warning("o despejo do -wal do banco da conta falhou (%r); "
                        "seguindo", erro)
        # os caminhos das midias no banco apontam para a raiz: acerta para a
        # pasta da conta ANTES de as midias irem para la, na conexao ja
        # aberta (reabrir o arquivo novo podia falhar por um instante, como
        # no banco unico). Se a troca falhar, nada foi movido ainda e os
        # caminhos antigos continuam valendo; a proxima abertura tenta de
        # novo. Tambem acerta quando as midias ja foram numa abertura
        # anterior (a raiz nao existe mais), e nao mexe em nada quando
        # nenhuma linha aponta para a raiz (as duas pastas tem arquivos)
        if vamos_mover or not os.path.isdir(legado_midias):
            backup._acertar_caminhos_das_midias(
                novo_db, legado_midias, pasta_midias, con=novo._con)
    finally:
        novo.fechar()
    if vamos_mover:
        _mover_pasta(legado_midias, pasta_midias)
    return not ja_tem


def _acertar_caminhos_da_pasta(banco, antigo, novo):
    """Abre o banco recem-copiado, despeja o -wal e troca os caminhos das
    midias na conexao ja aberta. Se o arquivo ainda nao abre para escrever
    (o antivirus olhando o que a copia acabou de gravar, por exemplo),
    sobe a sqlite3.OperationalError: quem chama decide esperar ou deixar
    para a proxima abertura."""
    if not os.path.isfile(banco):
        return
    aberto = Banco(banco)
    try:
        try:
            aberto._con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error as erro:
            log.warning("o despejo do -wal de %s falhou (%r); seguindo",
                        os.path.basename(banco), erro)
        backup._acertar_caminhos_das_midias(banco, antigo, novo,
                                            con=aberto._con)
    finally:
        aberto.fechar()


def _levar_para_a_pasta_escolhida(cfg):
    """Com a pasta das contas personalizada: leva cada conta que esta na
    pasta padrao (<dados>\\contas) para a pasta escolhida, se la ainda
    nao esta o banco dela. O que sobrou na pasta padrao vai junto. A
    origem so e apagada depois de os caminhos das midias no banco
    apontarem para o destino; se a troca falhar (o arquivo recem-copiado
    pode ficar um instante sem abrir), a origem fica, os caminhos antigos
    continuam valendo, e a proxima abertura tenta de novo."""
    n = 0
    padrao = os.path.join(config.pasta_dados(), "contas")
    for dados in cfg.contas():
        conta_id = dados.get("id")
        if not conta_id:
            continue
        origem = os.path.join(padrao, conta_id)
        destino = config.pasta_da_conta(conta_id)
        if os.path.normcase(origem) == os.path.normcase(destino):
            continue
        banco = os.path.join(destino, NOME_ARQUIVO)
        tem_origem = os.path.isdir(origem)
        if tem_origem:
            if not os.path.isfile(banco):
                if os.path.isfile(os.path.join(origem, NOME_ARQUIVO)):
                    _copiar_pasta(origem, destino)  # a origem fica por ora
                else:
                    _juntar_pasta(origem, destino, apagar=False)
            else:
                _juntar_pasta(origem, destino, apagar=False)  # destino vence
            n += 1
        elif not os.path.isfile(banco):
            continue
        # os caminhos das midias guardados no banco apontam para a pasta
        # de origem: trocam para o destino, com o banco ja aberto (abrir
        # o arquivo de novo logo depois de copiado podia falhar por um
        # instante). A origem so e apagada depois; e a troca roda tambem
        # quando a origem ja nao existe, para consertar uma abertura
        # anterior que nao conseguiu acertar
        try:
            _acertar_caminhos_da_pasta(
                banco, os.path.join(origem, "midias"),
                os.path.join(destino, "midias"))
        except (sqlite3.Error, OSError) as erro:
            log.warning("nao consegui acertar os caminhos das midias de %s "
                        "(%r); a pasta antiga fica para a proxima abertura",
                        conta_id, erro)
            continue
        if tem_origem:
            _rmtree_com_espera(origem)
    return n


def _voltar_ao_layout_antigo(cfg):
    """Com a separacao desmarcada: devolve os dados de cada conta para o
    layout antigo (o banco unico, as sessoes e as midias na raiz do
    layout antigo: a pasta personalizada, se escolhida, ou a pasta de
    dados). O banco unico e criado se nao existe; a pasta da conta e
    apagada so quando tudo conferiu (o que ficou para tras e tentado de
    novo na proxima abertura)."""
    raiz = config.pasta_do_layout_antigo()
    os.makedirs(raiz, exist_ok=True)
    sessoes_raiz = os.path.join(raiz, "sessoes")
    midias_raiz = os.path.join(raiz, "midias")
    unicos = []
    n = 0
    unico = None
    try:
        unico = Banco(os.path.join(raiz, "telezapp.db"))
        for dados in cfg.contas():
            conta_id = dados.get("id")
            if not conta_id:
                continue
            pasta = _pasta_com_dados(conta_id, cfg)
            if pasta is None:
                continue
            try:
                if _voltar_conta(conta_id, pasta, unico, sessoes_raiz,
                                 midias_raiz):
                    n += 1
            except (sqlite3.Error, OSError) as erro:
                # nao derruba a abertura: a pasta da conta fica (os caminhos
                # antigos continuam valendo) e a proxima abertura tenta de
                # novo
                log.warning("não consegui devolver %s ao banco único (%r); "
                            "a pasta dela fica para a próxima abertura",
                            conta_id, erro)
    finally:
        try:
            if unico is not None:
                unico.fechar()
        except Exception:
            pass
    return n


def _pasta_com_dados(conta_id, cfg=None):
    """A pasta da conta que de fato tem dados: a das contas no lugar que
    as opcoes pedem agora, ou em qualquer lugar que elas ja pediram (a
    pasta configurada, mesmo desmarcada agora, pode ter as pastas das
    contas que ficaram para tras). None se nenhuma existe ou esta
    vazia."""
    vistas = set()
    configurada = (cfg.get("contas_pasta") or "").strip() if cfg else ""
    for pasta in (config.pasta_da_conta(conta_id),
                  os.path.join(config.pasta_dados(), "contas", conta_id),
                  os.path.join(config.pasta_escolhida_do_layout_antigo(cfg),
                               conta_id),
                  os.path.join(configurada, conta_id) if configurada
                  else None):
        if pasta is None:
            continue
        chave = os.path.normcase(os.path.abspath(pasta))
        if chave in vistas:
            continue
        vistas.add(chave)
        if os.path.isdir(pasta) and os.listdir(pasta):
            return pasta
    return None


def _voltar_conta(conta_id, pasta, unico, sessoes_raiz, midias_raiz):
    """Devolve os dados de uma conta ao layout antigo. False se as linhas
    nao conferiram (a pasta fica, e a copia e tentada de novo)."""
    arquivo = os.path.join(pasta, NOME_ARQUIVO)
    origem_midias = os.path.join(pasta, "midias")
    alvo_midias = os.path.join(midias_raiz, armazem._limpo(conta_id, 80))
    if os.path.isfile(arquivo):
        banco = None
        try:
            banco = Banco(arquivo)
            unico.copiar_conta_de(conta_id, banco)
            if not _linhas_conferem(conta_id, banco, unico):
                log.warning("as linhas de %s não conferiram no banco "
                            "unico; a pasta fica para a proxima", conta_id)
                return False
        finally:
            try:
                if banco is not None:
                    banco.fechar()
            except Exception:
                pass
        # a copia pode deixar o -wal do banco unico enorme (73 MB num
        # banco de 80 MB); despeja-lo para o arquivo antes da proxima
        # escrita, que era a que falhava por um instante ("unable to
        # open database file") logo depois de o banco ser criado
        try:
            unico._con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error as erro:
            log.warning("o despejo do -wal do banco unico falhou (%r); "
                        "seguindo", erro)
        # os caminhos das midias no banco unico ainda apontam para a pasta
        # da conta: trocam para <dados>\\midias\\<conta> na conexao ja aberta.
        # Se escrever falhar (o banco recem-criado pode ficar um instante
        # sem abrir para gravar, com o antivirus olhando o arquivo), a pasta
        # fica — os caminhos antigos continuam valendo — e a proxima
        # abertura tenta de novo
        try:
            backup._acertar_caminhos_das_midias(
                unico.caminho, origem_midias, alvo_midias, con=unico._con)
        except (sqlite3.Error, OSError) as erro:
            log.warning("não consegui acertar os caminhos das midias de %s "
                        "no banco único (%r); a pasta dela fica para a "
                        "próxima abertura", conta_id, erro)
            return False
    # sessoes: de volta para a pasta comum. O que a conta usava por
    # ultimo era a sessao da pasta dela (o que ficou na pasta comum ou
    # nunca saiu de la, ou e uma sessao nova sem autorizacao, criada por
    # uma abertura que nao achou a conta): o arquivo da pasta da conta
    # substitui o que estiver na frente
    pasta_sessoes = os.path.join(pasta, "sessoes")
    if os.path.isdir(pasta_sessoes):
        os.makedirs(sessoes_raiz, exist_ok=True)
        for nome in os.listdir(pasta_sessoes):
            _mover_arquivo(os.path.join(pasta_sessoes, nome),
                           os.path.join(sessoes_raiz, nome))
    # midias: para <dados>\\midias\\<conta> (as que la ja estao ficam)
    if os.path.isdir(origem_midias):
        _juntar_pasta(origem_midias, alvo_midias)
    _rmtree_com_espera(pasta)
    return True


def _linhas_conferem(conta_id, origem, destino):
    """No destino ha tantas linhas da conta (ou mais) quanto na origem?"""
    for tabela in TABELAS:
        tem = origem._con.execute(
            "SELECT COUNT(*) FROM %s WHERE conta_id=?" % tabela,
            (conta_id,)).fetchone()[0]
        ficou = destino._con.execute(
            "SELECT COUNT(*) FROM %s WHERE conta_id=?" % tabela,
            (conta_id,)).fetchone()[0]
        if ficou < tem:
            return False
    return True


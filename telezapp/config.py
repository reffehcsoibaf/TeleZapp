# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fábio Scheffer Moraes
"""Pasta de dados, configuracoes e registro (log).

Tudo o que da acesso as contas (sessoes) e o banco local ficam em
%APPDATA%\\TeleZapp, fora da pasta do programa e do repositorio. A variavel
de ambiente TELEZAPP_DADOS troca essa pasta (usada nos testes).

O registro nunca grava o texto das mensagens, numeros de telefone completos,
codigos ou senhas.
"""
import json
import logging
import logging.handlers
import os
import re
import shutil
import sys
import threading
import unicodedata
from dataclasses import dataclass

from telezapp import NOME, VERSAO

log = logging.getLogger("telezapp")


def pasta_dados():
    especial = os.environ.get("TELEZAPP_DADOS")
    if especial:
        return especial
    if getattr(sys, "frozen", False):
        # copia portatil: a pasta "dados" ao lado do executavel
        portatil = os.path.join(os.path.dirname(os.path.abspath(
            sys.executable)), "dados")
        if os.path.isdir(portatil):
            return portatil
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, NOME)


def pasta(*partes):
    """Caminho dentro da pasta de dados, criando as pastas que faltam."""
    caminho = os.path.join(pasta_dados(), *partes)
    os.makedirs(caminho, exist_ok=True)
    return caminho


def configurar_registro():
    """Grava em logs\\telezapp.log (ate 5 arquivos de 1 MB)."""
    raiz = logging.getLogger("telezapp")
    if raiz.handlers:
        return os.path.join(pasta("logs"), "telezapp.log")
    arquivo = os.path.join(pasta("logs"), "telezapp.log")
    h = logging.handlers.RotatingFileHandler(
        arquivo, maxBytes=1024 * 1024, backupCount=4, encoding="utf-8")
    h.setFormatter(FormatadorSemTelefones(
        "%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    raiz.addHandler(h)
    raiz.setLevel(logging.INFO)
    raiz.propagate = False
    # Avisos das bibliotecas (reconexao, limites) ajudam a investigar
    # problemas. O neonize configura o log raiz ao ser importado; os dele
    # ficam so em avisos, aqui, e o nivel tambem vale para o lado em Go.
    for nome in ("telethon", "whatsmeow", "Whatsmeow", "neonize",
                 "neonize.utils.log"):
        lib = logging.getLogger(nome)
        lib.addHandler(h)
        lib.setLevel(logging.WARNING)
        lib.propagate = False
    raiz.info("==== %s %s iniciado ====", NOME, VERSAO)
    return arquivo


# Enderecos do WhatsApp (5551999998888@s.whatsapp.net, 5577...-1577...@g.us,
# 1011...@lid, com ou sem parte do aparelho) e telefones com "+": o registro
# nao pode levar numero de ninguem, porque o usuario o manda ao suporte.
_ENDERECO = re.compile(
    r"(?<![\w.:-])(\d{7,})((?:[.:]\d+)*)(-\d+)?"
    r"@(s\.whatsapp\.net|c\.us|g\.us|lid|hosted\.lid|hosted)\b")
_TELEFONE_COM_MAIS = re.compile(r"(?<!\w)\+(\d{8,15})\b")


def mascarar_texto(texto):
    """Troca telefones e enderecos do WhatsApp do texto pelo fim deles:
    '5551999998888@s.whatsapp.net' -> '...8888@s.whatsapp.net'; um grupo
    '557791063633-1577487873@g.us' -> '...3633-1577487873@g.us' (o numero
    antes do traco e de quem criou o grupo); '+5551999998888' ->
    '+55...8888'. O resto do texto fica como esta."""
    def endereco(m):
        return "...%s%s%s@%s" % (m.group(1)[-4:], m.group(2),
                                 m.group(3) or "", m.group(4))

    def telefone(m):
        n = m.group(1)
        return "+%s...%s" % (n[:2], n[-4:])
    return _TELEFONE_COM_MAIS.sub(telefone, _ENDERECO.sub(endereco,
                                                          str(texto)))


class FormatadorSemTelefones(logging.Formatter):
    """O formatador do registro: passa o texto final (inclusive o de uma
    excecao) por `mascarar_texto`."""

    def format(self, record):
        return mascarar_texto(super().format(record))


def mascarar_telefone(telefone):
    """+5551999998888 -> +55...8888 (para o registro)."""
    t = telefone or ""
    return t[:3] + "..." + t[-4:] if len(t) > 7 else "..."


def pasta_depuracao():
    """Onde a depuracao grava os textos salvos: C:\\logs no Windows (a
    pasta que a pessoa ja usa para os logs), senao a pasta de logs do app."""
    especial = os.environ.get("TELEZAPP_PASTA_DEPURACAO")
    if especial:
        os.makedirs(especial, exist_ok=True)
        return especial
    if os.name == "nt":
        os.makedirs("C:\\logs", exist_ok=True)
        return "C:\\logs"
    return pasta("logs")


def pasta_temporaria():
    """Arquivos temporarios do app: so aqui, nunca no %temp% do Windows."""
    return pasta("temp")


def pasta_sons():
    """Os arquivos de som que a pessoa escolheu para os avisos."""
    return pasta("sons")


def importar_som(origem):
    """Copia o arquivo de som para a pasta de sons (se ainda nao estiver
    nela) e devolve o nome dele la dentro. Um nome ja usado por outro arquivo
    ganha um numero."""
    destino_dir = pasta_sons()
    nome = os.path.basename(origem)
    destino = os.path.join(destino_dir, nome)
    if os.path.normcase(os.path.abspath(origem)) == \
            os.path.normcase(os.path.abspath(destino)):
        return nome
    base, ext = os.path.splitext(nome)
    n = 1
    while os.path.exists(destino):
        if os.path.getsize(destino) == os.path.getsize(origem) and \
                open(destino, "rb").read() == open(origem, "rb").read():
            return os.path.basename(destino)       # ja e o mesmo arquivo
        n += 1
        nome = "%s (%d)%s" % (base, n, ext)
        destino = os.path.join(destino_dir, nome)
    shutil.copyfile(origem, destino)
    return nome


def limpar_temporarios():
    """Apaga o conteudo da pasta temporaria (na abertura e no fechamento)."""
    caminho = os.path.join(pasta_dados(), "temp")
    if os.path.isdir(caminho):
        shutil.rmtree(caminho, ignore_errors=True)


# ------------------------------------------------- opcoes de configuracao
@dataclass(frozen=True)
class Opcao:
    """Uma opcao que a pessoa pode mudar. O registro unico serve aos menus
    de hoje e a janela de configuracoes com busca (etapa 4)."""
    chave: str
    rotulo: str
    categoria: str
    padrao: object
    descricao: str
    escolhas: tuple = ()     # vazio: sim ou nao; senao (valor, rotulo)
    numero: tuple = ()       # (minimo, maximo): numero digitado, sem lista
    som: str = ""            # evento de som (ver EVENTOS_SOM): "" = outra opcao
    grupo: str = ""          # botao da categoria que abre estas opcoes juntas
    texto: bool = False      # texto digitado
    pasta: bool = False      # o texto e uma pasta: ganha o botao de escolher


OPCOES = (
    Opcao("digitar_na_lista", "Ao digitar uma letra numa lista", "Interface",
          "pular",
          "O que acontece quando você digita um caractere com o foco na lista "
          "de mensagens ou na lista de conversas. Pular para o item com a "
          "inicial é o comportamento das listas do Windows: o foco vai para "
          "o próximo item que começa com o que você digitou. Ir para o campo "
          "leva o foco ao campo de escrever a mensagem (na lista de "
          "mensagens) ou ao campo de busca de conversas (na lista de "
          "conversas) e coloca ali o que você digitou. Sem uma conversa "
          "aberta, a lista de mensagens não tem campo e continua pulando.",
          (("pular", "Pular para o item que começa com a letra"),
           ("campo", "Ir direto para o campo de texto"))),
    Opcao("prioridade_abertura", "Dar prioridade ao TeleZapp ao abrir",
          "Interface", True,
          "Ao abrir, o TeleZapp pede ao Windows prioridade acima do normal "
          "(e sai do modo de economia de energia) por cerca de meio minuto, "
          "para não esperar atrás dos outros programas que abrem junto, "
          "como ao ligar o computador. Se o TeleZapp demora a responder "
          "quando é aberto depois de outros aplicativos, deixe marcada. "
          "Vale na próxima abertura."),
    Opcao("status_no_titulo",
          "Mostrar status de presença no título da janela",
          "Interface", True,
          "Com uma conversa aberta, o título da janela mostra, depois do "
          "nome, se a pessoa está online, quando foi vista por último ou se "
          "está digitando. No WhatsApp isso exige que a sua conta fique "
          "disponível enquanto a conversa está aberta (o celular pode "
          "deixar de tocar nesse tempo) e, como no próprio WhatsApp, quem "
          "esconde o seu status também não vê o dos outros."),
    Opcao("avisar_chamadas_whatsapp", "Avisar chamadas do WhatsApp",
          "Interface", True,
          "Quando alguém liga pelo WhatsApp, abre uma janela dizendo quem "
          "está chamando e se é por voz ou por vídeo, com os botões OK e "
          "Conversar. Vale quando o TeleZapp não consegue atender a chamada "
          "(sem o componente de chamadas): atenda em outro dispositivo. "
          "Desmarcada, a chamada só fica registrada na lista de mensagens "
          "da conversa."),
    Opcao("como_me_chamar", "Como me chamar nas mensagens", "Interface", "",
          "O nome que aparece no lugar de Você quando o autor é você: nas "
          "mensagens, na lista de conversas, nas reações, nos votos, na busca "
          "e nas conversas salvas. Vale só neste computador; quem recebe não "
          "vê este nome. Vazio, fica Você.",
          texto=True),
    Opcao("falar_novas", "Falar mensagens novas na conversa aberta",
          "Interface", False,
          "O leitor de tela fala o autor e o conteúdo de cada mensagem nova "
          "da conversa que está aberta, com o TeleZapp em uso. Não depende "
          "dos sons.",
          grupo="Conteúdo falado"),
    Opcao("falar_novas_outras_conversas",
          "Falar mensagens novas de outras conversas", "Interface", False,
          "Com o TeleZapp em uso, fala o nome da conversa, o autor e o "
          "conteúdo das mensagens que chegam em outra conversa que não é a "
          "aberta (ou quando nenhuma está aberta). Não depende dos "
          "sons.",
          grupo="Conteúdo falado"),
    Opcao("falar_novas_fora_do_telezapp",
          "Falar mensagens novas fora do TeleZapp", "Interface", False,
          "Fala as mensagens novas também quando você está em outro "
          "programa ou com a janela do TeleZapp minimizada, de qualquer "
          "conversa. Não depende dos sons.",
          grupo="Conteúdo falado"),
    Opcao("confirmar_envio", "Falar mensagem enviada", "Interface", False,
          "Fala Enviada depois que uma mensagem sai.",
          grupo="Conteúdo falado"),
    Opcao("falar_reacoes", "Falar reações às minhas mensagens", "Interface",
          False,
          "Fala quem reagiu e com qual emoji quando alguém reage a uma "
          "mensagem sua. Desmarcada, a reação só aparece na mensagem.",
          grupo="Conteúdo falado"),
    Opcao("falar_quantas_no_filtro",
          "Falar quantas conversas há ao trocar de filtro", "Interface", True,
          "Ao passar pelas caixas de conta e de tipo de conversa, fala o "
          "filtro e quantas conversas há nele. Desmarcada, só o leitor de "
          "tela lê a opção escolhida.",
          grupo="Conteúdo falado"),
    Opcao("trancadas_exigir_codigo",
          "Esconder as conversas trancadas atrás de um código secreto",
          "Privacidade", True,
          "As conversas que você trancou no celular só aparecem depois que "
          "você digita, no campo de busca de conversas, o código secreto "
          "que definiu em Conversas, Código secreto das conversas "
          "trancadas. Sem código definido elas ficam escondidas. Desmarcada, "
          "o tipo Trancadas no celular aparece sempre."),
    Opcao("temporarias_apagar_aqui",
          "Apagar daqui as mensagens temporárias quando o prazo acabar",
          "Privacidade", True,
          "Nas conversas com mensagens temporárias (WhatsApp e Telegram), "
          "cada celular apaga a mensagem no prazo. Marcada, o TeleZapp "
          "também apaga daqui, com a mídia baixada, quando o prazo acaba "
          "(e confere ao abrir, para o que venceu com ele fechado). "
          "Desmarcada, as mensagens ficam guardadas aqui, marcadas como "
          "vencidas. O que o TeleZapp apaga não volta numa nova sincronia."),
    Opcao("manter_apagadas",
          "Manter as mensagens que quem enviou apagar para todos",
          "Privacidade", False,
          "Quando alguém apaga uma mensagem para todos depois de o TeleZapp "
          "tê-la recebido, o WhatsApp e o Telegram tiram o conteúdo do "
          "celular. Marcada, o TeleZapp guarda o que já tinha (texto, "
          "áudio e outras mídias baixadas) e só acrescenta \"apagada pelo "
          "autor\" na linha da mensagem. Desmarcada, ela vira Mensagem "
          "apagada e a mídia baixada é descartada. Só vale para o que "
          "chegar depois de marcar; o que já foi apagado não volta. As "
          "mensagens que você mesmo apaga continuam sendo apagadas."),
    Opcao("verificar_atualizacoes",
          "Avisar quando houver versão nova do TeleZapp", "Atualizações",
          True,
          "Ao abrir, consulta as versões publicadas no GitHub. Sem versão "
          "nova, não diz nada. Havendo, abre a janela com as novidades e você "
          "escolhe se instala. Se responder Não, o TeleZapp pergunta se você "
          "quer \"Não me avise mais sobre essa versão\" (só volta a avisar "
          "quando sair outra) ou \"Talvez mais tarde\" (a janela volta na "
          "próxima vez que abrir o TeleZapp). Só lê a lista de "
          "versões; não baixa nada sem você aceitar. O GitHub vê o endereço "
          "de internet do computador, como em qualquer site. Desmarcada, só "
          "consulta quando você pedir, em Ajuda, Verificar atualizações."),
    Opcao("atualizacoes_periodicas",
          "Buscar atualizações periodicamente com o TeleZapp aberto",
          "Atualizações", True,
          "Além de consultar ao abrir, volta a consultar de tempos em tempos "
          "enquanto o TeleZapp estiver aberto, mesmo em segundo plano. As "
          "regras são as mesmas: sem versão nova, não diz nada. Em segundo "
          "plano, o TeleZapp só avisa em voz alta, e a janela com as novidades "
          "abre quando você o trouxer de volta. Durante uma chamada, ou com "
          "outra janela aberta, ele espera."),
    Opcao("atualizacoes_intervalo", "Intervalo da busca por atualizações",
          "Atualizações", 24,
          "De quanto em quanto tempo consultar, enquanto o TeleZapp estiver "
          "aberto.",
          escolhas=((1, "1 hora"), (6, "6 horas"), (12, "12 horas"),
                    (24, "24 horas"))),
    Opcao("depuracao", "Modo de depuração", "Avançado", False,
          "Guarda, no seu computador, a estrutura original das últimas 500 "
          "mensagens do WhatsApp para o menu Depurar mostrar. Contém o texto "
          "e os telefones dessas mensagens. Ao desligar, tudo é apagado."),
    Opcao("log_detalhado_whatsapp", "Registro técnico detalhado do WhatsApp",
          "Avançado", False,
          "Grava no log cada pacote que o WhatsApp troca com o TeleZapp "
          "(sem o texto das mensagens, que vai criptografado). Serve para "
          "investigar erros de envio; deixa o log grande. Vale na próxima "
          "abertura do TeleZapp."),
    Opcao("previa_links", "Prévia dos links nas mensagens", "Mensagens",
          "completa",
          "Quando quem enviou mandou junto a prévia de um link (título e "
          "descrição), ela é lida na linha da mensagem. O TeleZapp não abre "
          "o link para montar uma prévia. Nos detalhes da mensagem (Alt "
          "Enter) a prévia aparece sempre.",
          (("completa", "Título e descrição"), ("titulo", "Só o título"),
           ("nenhuma", "Não ler a prévia"))),
    Opcao("previa_receber", "Buscar a prévia dos links recebidos",
          "Mensagens", False,
          "Quando chega uma mensagem com um link sem prévia, o TeleZapp abre "
          "a página para ler o título e a descrição. O site fica sabendo do "
          "IP deste computador e de que o link foi aberto. Só vale para "
          "mensagens que chegam com o programa aberto; endereços da rede "
          "local nunca são abertos."),
    Opcao("previa_enviar", "Gerar a prévia dos links que eu envio",
          "Mensagens", False,
          "No WhatsApp, o TeleZapp abre o primeiro link da mensagem que você "
          "envia e manda junto o título e a descrição, para quem recebe ver a "
          "prévia (o envio espera até 5 segundos). No Telegram, desmarcada, "
          "a mensagem sai sem a prévia de link. O site fica sabendo do IP "
          "deste computador.", ),
    Opcao("ortografia_idioma", "Idioma do corretor ortográfico", "Mensagens",
          "pt-BR",
          "O idioma do dicionário que Verificar ortografia (F7, menu "
          "Mensagens) usa na caixa de digitar. Os dicionários são os do "
          "Windows: se o idioma não estiver instalado, o corretor avisa. "
          "Em Configurações do Windows, Hora e idioma, Idioma e região, "
          "adicione o idioma para instalar o dicionário.",
          (("pt-BR", "Português do Brasil"), ("pt-PT", "Português de Portugal"),
           ("en-US", "Inglês dos Estados Unidos"), ("es-ES", "Espanhol"))),
    Opcao("ortografia_ao_enviar", "Avisar de erros de ortografia ao enviar",
          "Mensagens", False,
          "Ao enviar uma mensagem de texto, se o corretor achar palavras "
          "com erro, pergunta se você quer corrigir antes ou enviar assim "
          "mesmo. Desmarcada, a mensagem sai direto e você corrige quando "
          "quiser com Verificar ortografia (F7)."),
    Opcao("mostrar_atalhos", "Mostrar as teclas de atalho nos controles",
          "Atalhos", True,
          "Escreve a tecla de atalho no nome dos botões e dos itens de menu "
          "que têm uma, por exemplo \"Enviar (Enter)\" ou \"Escrever "
          "mensagem, Control E\". Desmarcada, os nomes ficam sem o atalho "
          "e os atalhos continuam funcionando. Os atalhos podem ser "
          "mudados em Configurações, Atalhos."),
    Opcao("trazer_contatos_ao_abrir",
          "Obter os contatos das contas ao abrir o TeleZapp", "Interface",
          True,
          "Ao conectar cada conta, copia para a agenda do TeleZapp os "
          "contatos que ela já tem (os salvos no celular ou só no "
          "WhatsApp), para as conversas e os autores aparecerem com o nome "
          "e não com o número. Não troca o nome de quem você já nomeou "
          "aqui. Desmarcada, só entram os contatos que você adicionar. A "
          "mesma caixa está na janela Contatos."),
    Opcao("varrer_ao_reconectar",
          "Buscar sozinho as mensagens que faltam ao reconectar", "Mensagens",
          True,
          "Quando o TeleZapp reconecta depois de ficar fechado, o WhatsApp "
          "entrega só a parte final das mensagens que chegaram nesse tempo. "
          "Com esta caixa marcada, o TeleZapp pede ao celular, uma conversa "
          "de cada vez, as mensagens que ficaram faltando antes dessas e "
          "avisa quando encontra alguma. O celular precisa estar ligado e "
          "com internet. Desmarcada, só a busca que você pede em Buscar "
          "mensagens que faltam no celular."),
    Opcao("ocultar_contatos_duplicados", "Ocultar contatos duplicados",
          "Interface", True,
          "Nas listas de contatos (Contatos e a escolha de quem recebe em "
          "Nova mensagem e Nova chamada), mostra uma vez só a pessoa que "
          "aparece repetida: com o mesmo telefone, ou com o mesmo nome "
          "quando uma das cópias não tem telefone. Duas pessoas com o mesmo "
          "nome e telefones diferentes continuam as duas. Desmarcada, a "
          "lista mostra tudo o que está guardado. O mesmo botão está na "
          "janela Contatos."),
    Opcao("segundo_plano", "Continuar em segundo plano ao fechar a janela",
          "Sistema", False,
          "Fechar a janela (o botão de fechar ou Alt F4) só a minimiza: o "
          "TeleZapp segue conectado, dando os avisos de mensagens, o botão "
          "continua na barra de tarefas e um ícone fica na área de "
          "notificação do Windows. Para voltar, use a barra de tarefas, o "
          "ícone ou o atalho de chamar o TeleZapp (Configurações, Atalhos, "
          "\"Chamar o TeleZapp\"). Para encerrar de verdade, use Sair, em "
          "Ferramentas (Control Q), o botão Sair ou o menu do ícone."),
    Opcao("abrir_links_no_telezapp",
          "Oferecer o TeleZapp para abrir links do Telegram e do WhatsApp",
          "Sistema", True,
          "Faz o TeleZapp aparecer entre as opções do Windows para abrir links "
          "tg:// e whatsapp://. Quem abre continua sendo o programa que você "
          "escolheu: troque em Configurações do Windows, Aplicativos padrão."),
    Opcao("iniciar_com_windows", "Abrir o TeleZapp ao entrar no Windows",
          "Sistema", False,
          "Abre o TeleZapp sozinho quando você entra na sua conta do "
          "Windows. Com \"Continuar em segundo plano\" ligado, ele abre "
          "minimizado na barra de tarefas, sem tirar o foco do que você "
          "está fazendo."),
    Opcao("barra_abre_comandos",
          "Barra na caixa de digitar abre os comandos do robô",
          "Mensagens", True,
          "No Telegram, uma barra digitada na caixa vazia mostra os comandos "
          "do robô da conversa. Sem robô, a barra fica como um caractere "
          "qualquer."),
    Opcao("enter_envia", "Enter na caixa de digitar envia a mensagem",
          "Mensagens", True,
          "Marcada (o padrão), Enter envia e Shift Enter quebra a linha; "
          "Control Enter também envia. Desmarcada, só Control Enter envia e "
          "Enter quebra a linha, como no Telegram Web e no Gmail. A tecla "
          "de enviar também pode ser mudada em Atalhos, na função \"Enviar "
          "a mensagem digitada\"."),
    Opcao("ocultar_telefone_sem_nome",
          "Ocultar o telefone de remetentes sem nome", "Mensagens", False,
          "Quando o TeleZapp não acha o nome de quem enviou, a mensagem começa "
          "direto pelo conteúdo, sem o número de telefone, na lista de "
          "mensagens, na fala e na lista de conversas. O telefone continua "
          "nos detalhes e nas conversas salvas.",),
    Opcao("mostrar_avisos_de_membros",
          "Mostrar os avisos de entrada e saída de membros", "Mensagens", True,
          "Nos grupos do Telegram, mostra na lista de mensagens quem entrou, "
          "saiu, foi adicionado ou removido. Esses avisos não tocam som nem são "
          "falados ao chegar. Desmarcada, ficam escondidos, mas o Telegram "
          "ainda pode contá-los como não lidas ao abrir o programa."),
    Opcao("falar_descricoes", "Falar a descrição de cada opção",
          "Interface", True,
          "Na janela de configurações, o TeleZapp fala a explicação de cada "
          "opção logo depois que você chega nela. Desmarcada, a explicação "
          "só é falada com F1.",
          grupo="Conteúdo falado"),
    Opcao("pasta_salvar", "Pasta dos arquivos salvos", "Mídias", "",
          "A pasta onde ficam os arquivos que você salva: mídias, documentos, "
          "conversas, logs e textos. Vazia, a janela de salvar decide. Não "
          "vale para o backup, que tem a pasta dele.",
          texto=True, pasta=True),
    Opcao("salvar_direto", "Guardar direto na pasta, sem perguntar", "Mídias",
          False,
          "Marcada, o arquivo vai direto para a pasta definida e o TeleZapp "
          "diz onde ficou; se já houver um com o mesmo nome, nada é "
          "sobrescrito e o novo ganha um número. Desmarcada, a janela de "
          "salvar abre em cada salvamento, começando nessa pasta. Só vale com "
          "uma pasta definida.",),
    Opcao("gravar_som_com_microfone",
          "Gravar também o microfone ao gravar o som do computador",
          "Mídias", True,
          "Na janela \"Gravar o som do computador\", a caixa \"Gravar também "
          "o microfone\" já vem marcada: o que o computador toca e o que "
          "você fala entram juntos na mesma nota de voz. Dá para ligar e "
          "desligar o microfone durante a gravação. Desmarcada, a janela "
          "grava só o som do computador. O atalho Control Shift S grava sempre "
          "só o som do computador, e o Control Shift B grava sempre o som do "
          "computador com o microfone."),
    Opcao("barra_de_progresso",
          "Janela com barra de progresso em downloads e envios longos",
          "Mídias", True,
          "Quando um download que você pediu, ou o envio de um arquivo "
          "grande, demora mais de um segundo, abre uma janela com uma barra "
          "de progresso. O leitor de tela acompanha a "
          "barra (o NVDA toca bipes que sobem do grave ao agudo conforme ela "
          "avança). O TeleZapp não fala nem escreve a "
          "porcentagem: quem decide se a barra fala, bipa, os dois ou fica "
          "quieta é a configuração de barras de progresso do próprio leitor de "
          "tela (no NVDA, Configurações, Apresentação de objetos). No "
          "download a "
          "janela tem o botão Cancelar (Esc também cancela). Com a janela "
          "aberta, a fala do avanço (Porcentagem falada no download) fica "
          "quieta. "
          "Desmarcada, o avanço só aparece no título, na barra de situação "
          "e na fala. Atualizar, instalar e fazer backup sempre mostram a "
          "barra."),
    Opcao("audio_janela", "Ao tocar um áudio ou mensagem de voz", "Mídias",
          "sem",
          "Só tocar começa a tocar sem abrir janela: Enter de novo pausa e "
          "continua, e Esc para. O player em janela tem avançar, voltar e "
          "posição.",
          (("sem", "Só tocar, sem janela"),
           ("janela", "Abrir a janela do player"))),
    Opcao("enter_audio", "O que o Enter faz numa mensagem de voz ou áudio", "Mídias",
          "abrir", "O que o Enter faz numa mensagem de voz ou áudio. "
          "Transcrever usa os provedores de Inteligência artificial e, se a "
          "transcrição já existe, só a mostra. Control O sempre reproduz e "
          "Control B sempre só baixa.",
          (("abrir", "Reproduzir (baixa antes, se preciso)"),
           ("baixar", "Só baixar"),
           ("ia", "Transcrever (ou mostrar a transcrição)"))),
    Opcao("enter_imagem", "O que o Enter faz numa foto ou figurinha", "Mídias", "abrir",
          "O que o Enter faz numa foto ou figurinha. Descrever usa os "
          "provedores de Inteligência artificial e, se a descrição já "
          "existe, só a mostra.",
          (("abrir", "Abrir (baixa antes, se preciso)"),
           ("baixar", "Só baixar"),
           ("ia", "Descrever (ou mostrar a descrição)"))),
    Opcao("enter_video", "O que o Enter faz num vídeo", "Mídias", "abrir",
          "O que o Enter faz num vídeo. Descrever usa o provedor de "
          "Inteligência artificial que aceita vídeo e, se a descrição já "
          "existe, só a mostra.",
          (("abrir", "Abrir (baixa antes, se preciso)"),
           ("baixar", "Só baixar"),
           ("ia", "Descrever (ou mostrar a descrição)"))),
    Opcao("enter_pdf", "O que o Enter faz num PDF", "Mídias", "abrir",
          "O que o Enter faz num documento PDF. Converter usa os provedores "
          "de Inteligência artificial e, se o texto já existe, só o mostra.",
          (("abrir", "Abrir (baixa antes, se preciso)"),
           ("baixar", "Só baixar"),
           ("ia", "Converter em texto acessível (ou mostrar o texto)"))),
    Opcao("audio_sequencia", "Sequência de áudios", "Mídias", "sim",
          "O que acontece quando um áudio ou mensagem de voz termina (sem "
          "janela). Todos da conversa: toca o próximo áudio, pulando as "
          "mensagens que não são áudio. Só os seguidos: toca os áudios um "
          "depois do outro e para na primeira mensagem que não for áudio, "
          "como um texto ou uma foto. Baixa antes, se preciso. Esc para.",
          (("sim", "Tocar todos os áudios da conversa em sequência"),
           ("bloco", "Tocar só os áudios seguidos, até uma mensagem que "
                     "não seja áudio"),
           ("nao", "Parar quando o áudio terminar"))),
    Opcao("audio_passo_velocidade", "Quanto a velocidade do áudio muda a cada vez", "Mídias",
          0.25,
          "De quanto em quanto a velocidade de reprodução do áudio muda "
          "quando você a aumenta ou diminui.",
          ((0.25, "De 0,25 em 0,25 (de 0,25x até 3x)"),
           (0.5, "De 0,5 em 0,5 (de 0,5x até 3x)"),
           (1.0, "De 1 em 1 (1x, 2x e 3x)"))),
    Opcao("audio_velocidade", "Velocidade do áudio", "Mídias", 1.0,
          "Velocidade de reprodução de áudios e mensagens de voz, de 0,25x a "
          "3x, sem mudar o tom da voz. Os valores disponíveis dependem do "
          "passo escolhido.",
          tuple((v, ("%g" % v).replace(".", ",") + "x") for v in (
              0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75,
              3.0))),
    Opcao("falar_quem_toca",
          "Ao tocar o primeiro áudio, falar de quem é e a duração",
          "Mídias", False,
          "Quando um áudio ou mensagem de voz começa a tocar, fala o que é, "
          "de quem e quanto dura. Desmarcada, não fala nada: o próprio áudio começa a tocar. Vale para o "
          "primeiro áudio; os que tocam depois dele, na sequência, seguem as "
          "opções \"Na sequência de áudios\" logo abaixo."),
    Opcao("seq_falar_proximo", "Na sequência de áudios, falar Próximo áudio",
          "Mídias", False,
          "A cada áudio que começa na sequência, fala Próximo áudio antes "
          "do resto. Só vale quando um áudio toca depois do outro; o "
          "primeiro segue a opção Ao tocar o primeiro áudio, falar de "
          "quem é e a duração."),
    Opcao("seq_falar_tipo",
          "Na sequência de áudios, falar se é mensagem de voz ou áudio",
          "Mídias", False,
          "Fala Tocando mensagem de voz, ou Tocando áudio, a cada áudio da "
          "sequência."),
    Opcao("seq_falar_quem", "Na sequência de áudios, falar de quem é",
          "Mídias", False,
          "Fala o nome de quem enviou cada áudio da sequência. Em áudio "
          "seu, fala seu ou sua."),
    Opcao("seq_falar_duracao", "Na sequência de áudios, falar a duração",
          "Mídias", False,
          "Fala quanto dura cada áudio da sequência, por exemplo 12 "
          "segundos."),
    Opcao("seq_falar_velocidade",
          "Na sequência de áudios, falar a velocidade",
          "Mídias", False,
          "Fala a velocidade, por exemplo a 1,5x, quando ela não é a "
          "normal. Desmarcando todas as opções da sequência, nada é falado "
          "entre um áudio e outro."),
    Opcao("seq_falar_fim", "Na sequência de áudios, falar Fim da sequência",
          "Mídias", False,
          "Quando o último áudio da sequência termina e não há outro para "
          "tocar, fala Fim da sequência. Só vale se pelo menos dois áudios "
          "tocaram em sequência; um áudio sozinho não anuncia nada. "
          "Interromper o áudio com Esc também não anuncia."),
    Opcao("seq_acompanhar", "Na sequência de áudios, o cursor acompanha o "
          "áudio que toca", "Mídias", False,
          "Quando um áudio da sequência começa a tocar, a seleção da lista de "
          "mensagens passa para ele, sem tirar o foco de onde você está. "
          "Assim, ao voltar para a lista, você já está no áudio que tocou por "
          "último. Desmarcada, a seleção fica onde você deixou. Só vale se a "
          "conversa dos áudios estiver aberta."),
    Opcao("chamada_eco", "Cancelar o eco nas chamadas de voz", "Mídias", True,
          "Quando você ouve a chamada pelo alto-falante, o microfone capta "
          "a voz da outra pessoa e ela se ouve de volta. Marcada, o TeleZapp "
          "tira esse eco do que envia, também quando ele volta atrasado "
          "por uma mesa de som com retorno. Use fone para o melhor "
          "resultado. Vale a partir da próxima chamada. Desmarque se a "
          "outra pessoa disser que sua voz sai cortada ou abafada."),
    Opcao("chamada_ruido", "Reduzir o ruído do microfone nas chamadas de "
          "voz", "Mídias", True,
          "Diminui ruídos constantes captados pelo microfone, como "
          "ventilador, ar-condicionado e chiado. Vale a partir da próxima "
          "chamada."),
    Opcao("video_camera_ao_atender", "Ligar a câmera ao atender uma chamada "
          "de vídeo", "Mídias", False,
          "Desmarcada, ao atender uma chamada de vídeo a sua câmera fica "
          "desligada: você ouve e vê a outra pessoa, mas ela não vê você, e "
          "a câmera pode ser ligada na janela da chamada. Marcada, a câmera "
          "liga junto com a chamada. Quem liga uma chamada de vídeo sempre "
          "começa com a câmera ligada."),
    Opcao("chamada_retornar_sem_audio", "Ligar de volta quando a chamada "
          "recebida ficar sem som", "Mídias", True,
          "Às vezes você atende uma chamada do WhatsApp e o som da outra "
          "pessoa não chega. Marcada, depois de 20 segundos sem som o "
          "TeleZapp encerra a chamada e liga de volta para a mesma pessoa, "
          "o que costuma funcionar. A pessoa verá a chamada cair e receberá "
          "outra. Desmarcada, o TeleZapp só encerra e avisa."),
    Opcao("chamada_retorno", "Tirar das chamadas de voz o retorno da minha "
          "voz", "Mídias", True,
          "Quando a outra pessoa usa uma mesa de som com retorno (monitor) "
          "ou ouve a chamada pelo alto-falante, a sua voz volta para você, "
          "atrasada, misturada com a dela, e você se ouve. Marcada, o "
          "TeleZapp mede se isso está acontecendo e, só então, tira esse "
          "retorno do que você ouve. Sem retorno, a voz dela passa "
          "intacta. Vale a partir da próxima chamada. A solução de verdade "
          "é do lado dela: um retorno sem a sua voz (mix-minus)."),
    Opcao("midias_baixar", "Quando baixar as mídias", "Mídias", "demanda",
          "Sob demanda baixa só quando você abre a mídia. Automático baixa "
          "ao receber, até o limite escolhido.",
          (("demanda", "Só quando eu abrir"),
           ("automatico", "Automaticamente ao receber"))),
    Opcao("midias_limite_auto_mb", "Tamanho máximo do download automático", "Mídias",
          20, "Mídias maiores que isto (em MB) não baixam sozinhas.",
          ((5, "5 MB"), (10, "10 MB"), (20, "20 MB"), (50, "50 MB"),
           (100, "100 MB"))),
    Opcao("midias_passo_progresso", "Falar o avanço do download",
          "Mídias", 25,
          "De quanto em quanto o avanço de um download pedido por você, ou "
          "de um arquivo que você envia, é falado (por exemplo, 10 por "
          "cento, 20 por cento). No WhatsApp o avanço só existe com a DLL do "
          "neonize que o TeleZapp usa; com a oficial, a mídia vai e vem "
          "inteira de uma vez, sem porcentagens no meio. A barra de situação "
          "e o título da janela mostram o avanço mesmo com a fala desligada.",
          ((25, "A cada 25%"), (20, "A cada 20%"), (10, "A cada 10%"),
           (5, "A cada 5%"), (1, "A cada 1%"), (0, "Não falar o avanço"))),
    Opcao("midias_confirmar_mb", "Perguntar antes de baixar arquivos a partir de", "Mídias", 100,
          "Pergunta antes de baixar, a seu pedido, uma mídia maior que isto "
          "(em MB).",
          ((50, "50 MB"), (100, "100 MB"), (500, "500 MB"),
           (100000, "Nunca perguntar"))),
)


# Sons dos eventos: (nome em acessibilidade.fala.bipe, rotulo, descricao).
# O valor guardado e "" (som padrao do TeleZapp), "desligado" ou o caminho de
# um arquivo de som (WAV, Ogg, MP3, FLAC...).
EVENTOS_SOM = (
    ("nova", "mensagem recebida",
     "Tocado quando chega uma mensagem nova numa conversa que não é a "
     "aberta nem um grupo."),
    ("enviada", "mensagem enviada",
     "Tocado quando uma mensagem, um arquivo ou uma tarefa em segundo plano "
     "(salvar a conversa, fazer o backup) termina bem."),
    ("erro", "erro",
     "Tocado quando algo não pôde ser feito, como um envio que falhou."),
    ("conectado", "conta conectada",
     "Tocado quando uma conta termina de conectar."),
    ("pronto", "código ou QR pronto",
     "Tocado quando o código de pareamento ou o QR Code fica pronto."),
    ("atualizado", "QR Code atualizado",
     "Tocado quando o QR Code do pareamento é trocado por um novo."),
    ("toque", "toque de chamada recebida",
     "Repetido enquanto uma chamada está tocando para você."),
    ("chamando", "tom de chamada feita",
     "Repetido enquanto você espera a outra pessoa atender."),
    ("desligada", "chamada encerrada",
     "Tocado quando uma chamada termina."),
    ("nova_aberta", "mensagem recebida na conversa aberta",
     "Tocado quando chega uma mensagem na conversa que você está vendo. "
     "Com o som padrão, toca o mesmo som de mensagem recebida (e segue a "
     "escolha dele)."),
    ("nova_grupo", "mensagem recebida num grupo",
     "Tocado quando chega uma mensagem num grupo que não está aberto. Com o "
     "som padrão, toca o mesmo som de mensagem recebida."),
    ("desconectada", "conta desconectada",
     "Tocado quando uma conta que estava conectada cai."),
    ("reconectada", "conta reconectada",
     "Tocado quando uma conta que tinha caído volta a conectar. Com o som "
     "padrão, toca o mesmo som de conta conectada."),
    ("falha_envio", "mensagem ou arquivo que não saiu",
     "Tocado quando um envio falha. Com o som padrão, toca o mesmo som de "
     "erro."),
    ("download_pronto", "download de mídia concluído",
     "Tocado quando uma mídia que você pediu para baixar termina. Os "
     "downloads automáticos não tocam."),
    ("tarefa_pronta", "backup, restauração ou conversa salva",
     "Tocado quando terminam tarefas longas, como fazer o backup, restaurar "
     "ou salvar o conteúdo de uma conversa. Com o som padrão, toca o mesmo "
     "som de mensagem enviada."),
    ("mencao_ou_resposta", "menção ou resposta a você num grupo",
     "Tocado quando chega, num grupo, uma mensagem que cita você com @ ou "
     "que responde a uma mensagem sua. Substitui o som de mensagem recebida "
     "num grupo para essa mensagem e não depende do som de mensagem "
     "recebida (desative este evento se não quiser). Não toca em grupo "
     "arquivado, trancado ou silenciado que não esteja aberto."),
    ("reacao_recebida", "reação a uma mensagem sua",
     "Tocado quando alguém reage com um emoji a uma mensagem sua (não toca "
     "em conversa arquivada, trancada ou silenciada, nem para a sua própria "
     "reação). A fala da reação continua sendo a opção Falar reações às "
     "minhas mensagens, em Interface, Conteúdo falado."),
    ("gravando", "gravação de voz iniciada",
     "Tocado quando começa a gravação de uma nota de voz ou do som do "
     "computador, pelo atalho ou pela janela de gravação. É curto, para não "
     "entrar na gravação."),
    ("gravacao_parada", "gravação de voz parada",
     "Tocado quando você para a gravação. Com o som padrão, toca o mesmo "
     "som de mensagem enviada."),
    ("voto_enquete", "voto numa enquete sua",
     "Tocado quando alguém vota numa enquete que você criou (não toca para "
     "o seu próprio voto, nem em conversa arquivada, trancada ou "
     "silenciada)."),
    ("voto_enviado", "voto seu enviado numa enquete",
     "Tocado quando o seu voto numa enquete é enviado. Com o som padrão, "
     "toca o mesmo som de mensagem enviada."),
    ("escondido", "janela escondida em segundo plano",
     "Tocado quando a janela some e o TeleZapp segue rodando em segundo "
     "plano."),
    ("voltou", "janela trazida de volta",
     "Tocado quando a janela volta do segundo plano, pelo ícone ou pelo "
     "atalho global."),
)
def _opcoes_de_ia():
    from telezapp.nucleo.ia import catalogo
    return (
        Opcao("ia_perfil", "Tamanho das descrições", "Inteligência "
              "artificial", "medio", "Quanto o provedor escreve ao descrever "
              "imagens, figurinhas e vídeos. Transcrições e PDFs sempre "
              "saem completos.", tuple(catalogo.PERFIS)),
        Opcao("ia_tom", "Tom ao redigir com a IA", "Inteligência "
              "artificial", "natural", "O tom da mensagem que a IA escreve "
              "em Mensagem, Inteligência artificial, Redigir a mensagem. "
              "Natural deixa a IA seguir o tom da conversa. O item Redigir "
              "com um tom à escolha pergunta o tom na hora, sem mudar esta "
              "opção.", tuple(catalogo.TONS)),
        Opcao("ia_linha_descricao", "Tamanho da descrição na lista de "
              "mensagens", "Inteligência artificial", 0, "Quantas letras da "
              "descrição de uma foto, figurinha ou vídeo a linha da mensagem "
              "traz, e portanto o que é falado ao passar por ela. "
              "Cortada, termina com a indicação de que o menu mostra tudo.",
              ((300, "300 letras"), (1000, "1000 letras"),
               (3000, "3000 letras"), (0, "Descrição inteira"))),
        Opcao("ia_linha_transcricao", "Tamanho da transcrição na lista de "
              "mensagens", "Inteligência artificial", 1000, "Quantas letras "
              "da transcrição de uma voz ou áudio, ou do texto de um PDF, a "
              "linha da mensagem traz. Textos longos deixam a lista pesada de "
              "ler.", ((300, "300 letras"), (1000, "1000 letras"),
                       (3000, "3000 letras"), (10000, "10000 letras"),
                       (0, "Texto inteiro"))),
        Opcao("ia_auto_audio", "Transcrever sozinho voz e áudio", "Inteligência "
              "artificial", True, "Nas conversas em que você ligou a "
              "transcrição e descrição automáticas (menu de contexto da "
              "conversa), transcreve as mensagens de voz e os áudios que "
              "chegam, usando os provedores da transcrição. A mídia é baixada "
              "sozinha. Os arquivos vão para o provedor, que pode cobrar da "
              "sua chave."),
        Opcao("ia_auto_imagem", "Descrever sozinho fotos e figurinhas",
              "Inteligência artificial", True, "Nas conversas em que você "
              "ligou a transcrição e descrição automáticas, descreve as "
              "fotos e figurinhas que chegam. A mídia é baixada sozinha."),
    )


OPCOES = OPCOES + _opcoes_de_ia()
def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


def buscar_opcoes(texto):
    """Opcoes cujo nome, categoria ou descricao contem todas as palavras
    buscadas (sem diferenca de acento ou maiusculas)."""
    palavras = _sem_acento(texto).split()
    achadas = []
    for o in OPCOES:
        alvo = _sem_acento(" ".join((o.rotulo, o.categoria, o.descricao)))
        if all(p in alvo for p in palavras):
            achadas.append(o)
    return achadas


PADROES = {o.chave: o.padrao for o in OPCOES}
PADROES.update({
    "estilo": 1,             # antigo "Como cada mensagem e lida"; so migra
    "atalhos": {},           # funcao -> combinacao escolhida ("" = sem atalho)
    "participantes_silenciados": {},  # ver nucleo/silenciados.py
    "ia_ordem": {},          # tarefa -> provedores ligados, na ordem de tentativa
    "ia_lista_modelos": {},  # provedor -> modelos que ele ofereceu
    "ia_modelos": {},        # provedor -> modelo escolhido ("" = o padrao)
    "pacote_de_sons": "padrao",   # padrao, telezapp ou p:<nome>
    "sons_desativados": {},      # pacote -> eventos sem som
    "lista_conversas": {"ordem": ["nome", "servico", "nao_lidas", "previa",
                                  "reacoes", "quem_reagiu"],
                        "ocultos": ["previa", "reacoes",
                                    "quem_reagiu"]},  # o que cada linha mostra
    "lista_mensagens": {"ordem": ["autor", "hora", "conteudo", "marcas",
                                  "links", "previa", "ia", "reacoes",
                                  "resposta", "estado"],
                        "ocultos": [],
                        "autor_so_quando_muda": False},  # a linha da mensagem
    "ia_automatica_conversas": [],  # [conta, conversa] com a IA automatica
    "ia_idioma_traducao": "English",  # ultimo idioma de destino da traducao
    "ia_consentimento_texto": [],  # provedores que podem receber seu texto
    "ia_consentimento": [],  # provedores que a pessoa autorizou a receber midia
    "contas": [],            # [{"id", "servico", "telefone", "nome"}]
    "chamada_microfone": "",     # nome do microfone usado nas chamadas
    "chamada_saida": "",         # nome da saida de som das chamadas
    "chamada_camera": "",        # nome da camera das chamadas de video
    "notificacao_saida": "",     # nome da saida dos sons de aviso do app
    "telegram_api_id": 0,
    "telegram_api_hash": "",
    "filtro_conversas": "todas",   # tipo escolhido na janela principal
    "filtro_conta": "todas",       # servico ou conta escolhido nela
})


class Config:
    """Configuracoes em config.json, gravadas de forma atomica."""

    def __init__(self, caminho=None):
        self.caminho = caminho or os.path.join(pasta(), "config.json")
        self._trava = threading.Lock()
        self.dados = dict(PADROES)
        self.dados["contas"] = []
        self._carregar()

    def _carregar(self):
        try:
            with open(self.caminho, encoding="utf-8") as f:
                lido = json.load(f)
            if isinstance(lido, dict):
                self.dados.update(lido)
                if lido.get("falar_novas") and \
                        "falar_novas_outras_conversas" not in lido:
                    # antes uma opcao so falava tudo: mantem o que a pessoa
                    # ouvia ao separar em tres
                    self.dados["falar_novas_outras_conversas"] = True
                    self.dados["falar_novas_fora_do_telezapp"] = True
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            log.warning("config.json ilegivel, usando padroes: %r", e)

    def get(self, chave):
        return self.dados.get(chave, PADROES.get(chave))

    def set(self, chave, valor):
        self.dados[chave] = valor
        self.salvar()

    def salvar(self):
        with self._trava:
            tmp = self.caminho + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.dados, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.caminho)

    # ---------------------------------------------------------------- contas
    def contas(self):
        return [dict(c) for c in self.get("contas")]

    def salvar_conta(self, conta):
        contas = [c for c in self.get("contas") if c.get("id") != conta["id"]]
        contas.append(dict(conta))
        self.set("contas", contas)

    def remover_conta(self, conta_id):
        self.set("contas", [c for c in self.get("contas")
                            if c.get("id") != conta_id])


# --------------------------------------------------- credenciais do Telegram
# O api_id e o api_hash identificam o APLICATIVO perante o Telegram (nao a
# pessoa). O executavel leva os do projeto (telezapp/_credenciais.py, gerado
# na hora de empacotar e fora do git) e ninguem precisa informar nada. Sem
# eles, o app usa os da configuracao e, por fim, pergunta uma vez.
TELEGRAM_API_ID = 0
TELEGRAM_API_HASH = ""

ARQUIVO_TESTES = r"C:\TeleZapp\configuracao-telegram.txt"


def ler_chaves(caminho):
    """Le um arquivo CHAVE=valor (ignora linhas com #)."""
    d = {}
    with open(caminho, encoding="utf-8-sig") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            k, v = linha.split("=", 1)
            d[k.strip().upper()] = v.strip()
    return d


def credenciais_validas(api_id, api_hash):
    try:
        return int(api_id) > 0 and len(str(api_hash).strip()) >= 16
    except (TypeError, ValueError):
        return False


def credenciais_embutidas():
    """(api_id, api_hash) postas no programa na hora de empacotar
    (telezapp/_credenciais.py, fora do git: ferramentas/empacotar.py a gera),
    ou None. Com elas, quem instala nao informa nada."""
    try:
        from telezapp import _credenciais
    except ImportError:
        return None
    if credenciais_validas(_credenciais.API_ID, _credenciais.API_HASH):
        return int(_credenciais.API_ID), str(_credenciais.API_HASH).strip()
    return None


def credenciais_telegram(config, arquivo_testes=ARQUIVO_TESTES):
    """(api_id, api_hash) ou None se ainda nao houver.

    Ordem: as embutidas no programa, as da configuracao e, por fim, as do
    arquivo dos testes de viabilidade (C:\\TeleZapp), que sao copiadas para a
    configuracao para nao precisar digita-las.
    """
    if credenciais_validas(TELEGRAM_API_ID, TELEGRAM_API_HASH):
        return int(TELEGRAM_API_ID), TELEGRAM_API_HASH
    embutidas = credenciais_embutidas()
    if embutidas is not None:
        return embutidas
    api_id, api_hash = config.get("telegram_api_id"), config.get(
        "telegram_api_hash")
    if credenciais_validas(api_id, api_hash):
        return int(api_id), str(api_hash).strip()
    try:
        d = ler_chaves(arquivo_testes)
    except OSError:
        return None
    if credenciais_validas(d.get("API_ID"), d.get("API_HASH")):
        config.dados["telegram_api_id"] = int(d["API_ID"])
        config.dados["telegram_api_hash"] = d["API_HASH"].strip()
        config.salvar()
        log.info("credenciais do Telegram copiadas do arquivo dos testes")
        return int(d["API_ID"]), d["API_HASH"].strip()
    return None


def telefone_dos_testes(arquivo_testes=ARQUIVO_TESTES):
    """Telefone do arquivo dos testes de viabilidade, para sugerir no login."""
    try:
        return ler_chaves(arquivo_testes).get("TELEFONE", "")
    except OSError:
        return ""

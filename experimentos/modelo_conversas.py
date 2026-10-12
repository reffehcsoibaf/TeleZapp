# -*- coding: utf-8 -*-
"""Dados de exemplo e formatacao de mensagens para o prototipo da interface.

Sem dependencia de wxPython, para poder ser testado em qualquer lugar.
"""
import os
from dataclasses import dataclass, field

# Estilos de leitura da lista de mensagens
ESTILO_AUTOR_PRIMEIRO = 1
ESTILO_CONTEUDO_PRIMEIRO = 2
ESTILO_AUTOR_SO_QUANDO_MUDA = 3

NOMES_ESTILOS = {
    ESTILO_AUTOR_PRIMEIRO: "Autor e hora primeiro",
    ESTILO_CONTEUDO_PRIMEIRO: "Conteúdo primeiro",
    ESTILO_AUTOR_SO_QUANDO_MUDA: "Autor só quando muda",
}

EXT_FOTO = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"}
EXT_VIDEO = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".3gp"}
EXT_AUDIO = {".ogg", ".opus", ".mp3", ".m4a", ".wav", ".aac", ".flac"}


@dataclass
class Mensagem:
    autor: str
    hora: str
    tipo: str = "texto"  # texto, foto, video, voz, audio, documento
    texto: str = ""
    segundos: int = 0
    nome_arquivo: str = ""
    tamanho: int = 0
    minha: bool = False
    estado: str = ""  # enviada, entregue, lida


@dataclass
class Conversa:
    nome: str
    provedor: str
    mensagens: list = field(default_factory=list)
    nao_lidas: int = 0


def tamanho_legivel(n):
    if n < 1024:
        return "%d bytes" % n
    if n < 1024 * 1024:
        return "%d KB" % round(n / 1024)
    return ("%.1f MB" % (n / 1048576)).replace(".", ",")


def duracao_legivel(seg):
    if seg < 60:
        return "%d segundos" % seg if seg != 1 else "1 segundo"
    m, s = divmod(seg, 60)
    txt = "%d minuto%s" % (m, "" if m == 1 else "s")
    if s:
        txt += " e %d segundo%s" % (s, "" if s == 1 else "s")
    return txt


def _partes(*itens):
    """Junta com virgula so as partes que existem."""
    return ", ".join(p for p in itens if p)


def conteudo(m):
    """Texto falado do conteudo de uma mensagem, sem autor nem hora."""
    legenda = ("legenda: " + m.texto) if m.texto else ""
    dur = duracao_legivel(m.segundos) if m.segundos else ""
    tam = tamanho_legivel(m.tamanho) if m.tamanho else ""
    if m.tipo == "texto":
        return m.texto
    if m.tipo == "foto":
        return _partes("foto", legenda)
    if m.tipo == "video":
        return _partes("vídeo", dur, tam, legenda)
    if m.tipo == "voz":
        return _partes("mensagem de voz", dur)
    if m.tipo == "audio":
        return _partes("áudio", dur, tam)
    if m.tipo == "documento":
        return _partes("documento", m.nome_arquivo, tam, legenda)
    return m.texto


def _juntar(cont, resto):
    """Junta duas partes sem dobrar a pontuacao: depois de ponto final,
    exclamacao ou interrogacao usa so um espaco; nos demais casos, virgula."""
    if not resto:
        return cont
    if not cont:
        return resto
    final = cont.rstrip()[-1:]
    return cont + (" " if final in ".!?…" else ", ") + resto


def formatar(m, estilo, anterior=None):
    """Uma linha da lista de mensagens, no estilo escolhido."""
    cont = conteudo(m).replace("\r", " ").replace("\n", " ")
    autor = "Você" if m.minha else m.autor
    estado = m.estado if (m.minha and m.estado) else ""
    if estilo == ESTILO_CONTEUDO_PRIMEIRO:
        return _juntar(cont, "%s, %s%s" % (
            autor, m.hora, (", " + estado) if estado else ""))
    if estilo == ESTILO_AUTOR_SO_QUANDO_MUDA:
        mudou = anterior is None or anterior.minha != m.minha or \
            anterior.autor != m.autor
        prefixo = ("%s: " % autor) if mudou else ""
        return _juntar(prefixo + cont, estado)
    return _juntar("%s, %s: %s" % (autor, m.hora, cont), estado)


def formatar_lista(mensagens, estilo):
    linhas = []
    anterior = None
    for m in mensagens:
        linhas.append(formatar(m, estilo, anterior))
        anterior = m
    return linhas


def rotulo_conversa(c):
    base = "%s, %s" % (c.nome, c.provedor)
    if c.nao_lidas == 1:
        return base + ", 1 não lida"
    if c.nao_lidas > 1:
        return base + ", %d não lidas" % c.nao_lidas
    return base


def texto_marcador(n):
    """Texto do item que marca onde comecam as mensagens nao lidas."""
    return "Início das mensagens não lidas: %d %s" % (
        n, "mensagem" if n == 1 else "mensagens")


def classificar_arquivo(caminho):
    ext = os.path.splitext(caminho)[1].lower()
    if ext in EXT_FOTO:
        return "foto"
    if ext in EXT_VIDEO:
        return "video"
    if ext in EXT_AUDIO:
        return "audio"
    return "documento"


def detalhes(m, conversa_nome):
    """Texto completo de uma mensagem, para a janela de detalhes."""
    linhas = [
        "Conversa: %s" % conversa_nome,
        "De: %s" % ("Você" if m.minha else m.autor),
        "Hora: %s" % m.hora,
        "Tipo: %s" % {"texto": "texto", "foto": "foto", "video": "vídeo",
                      "voz": "mensagem de voz", "audio": "áudio",
                      "documento": "documento"}.get(m.tipo, m.tipo),
    ]
    if m.nome_arquivo:
        linhas.append("Arquivo: %s" % m.nome_arquivo)
    if m.tamanho:
        linhas.append("Tamanho: %s" % tamanho_legivel(m.tamanho))
    if m.segundos:
        linhas.append("Duração: %s" % duracao_legivel(m.segundos))
    if m.minha and m.estado:
        linhas.append("Estado: %s" % m.estado)
    if m.texto:
        linhas.append("")
        linhas.append("Texto completo:")
        linhas.append(m.texto)
    return "\n".join(linhas)


TEXTO_LONGO = (
    "Pessoal, segue o resumo da reunião de hoje. Primeiro: o prazo da "
    "entrega foi movido para a sexta-feira da semana que vem, porque o "
    "fornecedor atrasou o material. Segundo: precisamos confirmar até "
    "amanhã quem vai levar os documentos assinados. Terceiro: a sala de "
    "reuniões muda de andar na segunda. Quarto: quem não puder comparecer "
    "avisa por aqui, sem problema nenhum. Qualquer dúvida é só chamar. "
    "Obrigada a todos pela paciência!")


def dados_de_exemplo():
    c1 = Conversa("Ana", "WhatsApp", [
        Mensagem("Ana", "08:10", "texto", "Bom dia! Tudo bem?"),
        Mensagem("Ana", "08:11", "texto", "Viu o jogo ontem? 😂⚽"),
        Mensagem("", "08:15", "texto", "Vi sim, foi demais!", minha=True,
                 estado="lida"),
        Mensagem("Ana", "08:16", "foto", "Olha a cara dele depois do gol"),
        Mensagem("Ana", "08:18", "voz", segundos=14),
        Mensagem("", "08:20", "texto", "Já te respondo, estou no ônibus.",
                 minha=True, estado="entregue"),
    ])
    c2 = Conversa("Grupo da família", "Telegram", [
        Mensagem("Mãe", "07:30", "texto", "Café da manhã pronto!"),
        Mensagem("Pai", "07:32", "foto", "Bolo de ontem"),
        Mensagem("", "07:35", "texto", "Chego mais tarde, pode começar sem "
                 "mim.", minha=True, estado="enviada"),
        Mensagem("Carlos", "07:40", "video", "Aniversário da Júlia",
                 segundos=25, tamanho=3355443),
        Mensagem("Mãe", "07:41", "voz", segundos=95),
        Mensagem("Pai", "07:42", "texto", "Já estamos à mesa."),
    ])
    c3 = Conversa("Trabalho: projeto", "WhatsApp", [
        Mensagem("Marta", "09:00", "texto", TEXTO_LONGO),
        Mensagem("Marta", "09:02", "documento", "Ata da reunião",
                 nome_arquivo="ata-reuniao.pdf", tamanho=122880),
        Mensagem("Rui", "09:05", "audio", segundos=185, tamanho=2411724),
        Mensagem("", "09:10", "texto", "Recebi, obrigado.", minha=True,
                 estado="lida"),
    ])
    c4 = Conversa("Mensagens salvas", "Telegram", [
        Mensagem("", "ontem", "texto", "Lembrar de renovar o certificado.",
                 minha=True, estado="enviada"),
        Mensagem("", "ontem", "documento", "", nome_arquivo="boleto.pdf",
                 tamanho=48200, minha=True, estado="enviada"),
    ])
    for c in (c1, c2, c3, c4):
        c.nao_lidas = 0
    c2.nao_lidas = 3
    return [c1, c2, c3, c4]


_SIMULADAS = (
    ("texto", "Você viu isso?", 0, "", 0),
    ("texto", "Ligo mais tarde, pode ser?", 0, "", 0),
    ("foto", "Chegou!", 0, "", 0),
    ("voz", "", 7, "", 0),
    ("documento", "Segue o arquivo", 0, "planilha.xlsx", 20480),
    ("video", "Olha isso", 12, "", 1572864),
    ("texto", TEXTO_LONGO, 0, "", 0),
)


def mensagem_simulada(conversa, n, hora):
    tipo, texto, seg, arq, tam = _SIMULADAS[n % len(_SIMULADAS)]
    autor = conversa.nome.split(":")[0]
    if conversa.nome == "Grupo da família":
        autor = ("Mãe", "Pai", "Carlos")[n % 3]
    if conversa.nome == "Mensagens salvas":
        autor = "Você"
    return Mensagem(autor, hora, tipo, texto, seg, arq, tam)

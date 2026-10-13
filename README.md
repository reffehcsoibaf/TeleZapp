# TeleZapp

Cliente desktop para Windows que reúne contas de **WhatsApp** e **Telegram** numa
só janela, pensado desde o início para ser usado com **leitores de tela**
(NVDA).

> **Estado:** a fase de testes de viabilidade terminou. A próxima etapa é o
> esqueleto do aplicativo. Nada aqui é um produto pronto: o código atual são
> experimentos e um protótipo de interface.

## Objetivos

- Trocar **mensagens, fotos, vídeos, áudios e documentos** (prioridade).
- Usar várias contas e os dois serviços na mesma interface, para que, se uma
  conta cair, o usuário continue no mesmo aplicativo.
- **Instalar e atualizar rápido**: sem navegador embutido, sem Node.js e sem
  `npm install` no computador do usuário.
- **Acessibilidade em primeiro lugar**: controles nativos do Windows, fala pelo
  NVDA, atalhos de teclado e nenhum fluxo que dependa de ler o terminal.

Fora do escopo por enquanto: chamadas de voz e de vídeo.

## O que já foi comprovado (Windows 11, Python 3.13)

| Área | Resultado |
|---|---|
| WhatsApp (neonize) | Pareamento por código, sessão salva, texto, foto, vídeo, nota de voz e documento, nos dois sentidos, sem FFmpeg |
| Telegram (Telethon) | Login com senha de duas etapas, mesmas mídias, e transferências de ~10 MB/s com `cryptg` e partes paralelas |
| Interface (wxPython) | Protótipo lido pelo NVDA, com fala direta, marcador de não lidas, Esc, menus e atalhos |
| Empacotamento (PyInstaller) | Executável de 95 MB com todos os componentes funcionando |
| Gravação de voz (sounddevice + soundfile) | Microfone gravado em Ogg/Opus; nota de voz de ~62 kbit/s sem perda perceptível, recebida como mensagem de voz no Telegram |

Números e detalhes: [`docs/resultados-experimentos.md`](docs/resultados-experimentos.md).
Escolhas técnicas, riscos e pendências: [`docs/decisoes.md`](docs/decisoes.md).

## Estrutura do repositório

```
docs/                  resultados medidos, decisões e segurança
experimentos/          scripts de viabilidade (cada .bat roda um teste completo)
experimentos/historico testes do projeto anterior baseado em WPPConnect/Node
```

Veja [`experimentos/README.md`](experimentos/README.md) para a lista de testes e
como rodá-los.

## Segurança

Sessões do WhatsApp e do Telegram, `api_hash`, códigos e senhas **dão acesso às
contas** e nunca devem ser enviados ao repositório. O `.gitignore` já exclui
esses arquivos; leia [`docs/seguranca.md`](docs/seguranca.md).

## Licença

O TeleZapp é software livre, distribuído sob a **GNU General Public License,
versão 3 ou posterior** (GPL-3.0-or-later). O texto completo está em
[`LICENSE`](LICENSE). As bibliotecas de terceiros e as licenças delas estão em
[`docs/licencas-de-terceiros.md`](docs/licencas-de-terceiros.md).

Copyright (C) 2026 Contribuidores do TeleZapp.

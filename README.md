# TeleZapp

Cliente desktop para Windows que reúne contas de **WhatsApp** e **Telegram** numa
só janela, pensado desde o início para ser usado com **leitores de tela**
(NVDA).

> **Estado:** etapa 1 do aplicativo: o Telegram com mensagens de texto.
> Ainda não é um produto pronto. Etapas: 1) base com o Telegram; 2) WhatsApp
> na mesma janela, com pareamento por código ou QR Code; 3) mídias (foto,
> vídeo, documento e nota de voz); 4) várias contas, avisos e configurações.

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

## Como rodar (Windows)

1. Tenha o **Python 3.13** instalado.
2. Dê duplo clique em **`iniciar-telezapp.bat`**. Na primeira vez ele cria o
   ambiente na pasta `venv` e instala os componentes (cerca de um minuto, com
   aviso numa caixa de mensagem). Depois abre o TeleZapp sem janela de
   terminal.
3. Na primeira abertura, o TeleZapp oferece adicionar uma conta do Telegram.
   O login é feito em janelas próprias: número, código recebido e, se a conta
   tiver, senha de duas etapas.

Nesta fase o TeleZapp ainda não tem as credenciais próprias no Telegram
(*api id* e *api hash*, que identificam o aplicativo, não a pessoa). Se
existir o arquivo `C:\TeleZapp\configuracao-telegram.txt` dos experimentos,
ele é aproveitado; senão, o TeleZapp pede os dois valores uma vez.

Dados (sessões, banco local, configurações) e logs ficam em
`%APPDATA%\TeleZapp`, fora desta pasta. Os logs (menu Arquivo, Abrir a pasta
de logs) não contêm texto de mensagens, telefones, códigos nem senhas.

## Estrutura do repositório

```
telezapp/              o aplicativo (pacote Python: python -m telezapp)
  config.py            pasta de dados, configurações e log
  nucleo/              modelos comuns, eventos e gerência das contas
  provedores/          o contrato comum (base.py) e cada serviço
  armazenamento/       banco local SQLite
  midia/               leitura própria de MP4 e Ogg/Opus (sem hachoir)
  interface/           janela principal e diálogos de login
  acessibilidade/      fala direta pelo NVDA
testes/                testes automáticos (python -m pytest testes)
ferramentas/           apoio ao .bat (caixas de mensagem)
iniciar-telezapp.bat   instala e abre o TeleZapp
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

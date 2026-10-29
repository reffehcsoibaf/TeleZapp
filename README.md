# TeleZapp

Cliente desktop para Windows que reúne contas de **WhatsApp** e **Telegram** numa
só janela, pensado desde o início para ser usado com **leitores de tela**.

> **Estado:** em desenvolvimento ativo (versões no formato `ano.mês.dia.dígito`,
> a atual está em `telezapp/__init__.py`). Telegram e WhatsApp já funcionam
> na mesma janela, com mídias, várias contas, configurações, backup e
> inteligência artificial opcional. Ainda não é um produto pronto: o
> executável já se instala, vira cópia portátil e se atualiza pelo próprio
> programa; falta a assinatura do executável
> (veja [`docs/decisoes.md`](docs/decisoes.md)). O que mudou em cada versão
> está em [`CHANGELOG.md`](CHANGELOG.md) (técnico) e em Ajuda, Novidades
> (para quem usa).

## Aviso

O TeleZapp é um software **experimental**, em desenvolvimento. Pode ter erros,
inclusive em mensagens e conversas. Use por sua conta e risco. Não é um
produto oficial do WhatsApp nem do Telegram, e a licença (GPL 3) não dá
garantia.

## Baixar

As versões ficam em [Releases](https://github.com/reffehcsoibaf/TeleZapp/releases).
Baixe o `TeleZapp.exe` e abra: a tela de boas-vindas tem os botões
Instalar, Criar cópia portátil, Guia de uso e Fechar. Os dados ficam em
`%APPDATA%\TeleZapp` (na portátil, na pasta `dados` ao lado do programa).
Em Ajuda, Verificar atualizações, o programa diz se há versão nova e se
atualiza sozinho; para isso cada Release traz também o `TeleZapp.zip`.
Quem mantém o projeto gera tudo com `python ferramentas\empacotar.py` e
cria a Release com `python ferramentas\publicar.py`.

## Objetivos

- Trocar **mensagens, fotos, vídeos, áudios e documentos** (prioridade).
- Usar várias contas e os dois serviços na mesma interface, para que, se uma
  conta cair, o usuário continue no mesmo aplicativo.
- **Instalar e atualizar rápido**: sem navegador embutido, sem Node.js e sem
  `npm install` no computador do usuário.
- **Acessibilidade em primeiro lugar**: controles nativos do Windows, que os
  leitores de tela já sabem ler, atalhos de teclado e nenhum fluxo que
  dependa de ler o terminal.

Chamadas: o Telegram e o WhatsApp fazem e atendem chamadas de voz. No
WhatsApp, chamadas de vídeo só são avisadas: o TeleZapp mostra quem está
ligando, registra a chamada na conversa e deixa o atendimento para outro
dispositivo.

## O que o TeleZapp faz

- **Conversas** do WhatsApp e do Telegram numa lista só, com filtros por
  serviço, conta e tipo, busca, arquivar, fixar, silenciar, trancar (com código
  secreto), modo de seleção para ações em massa e detalhes da conversa, do
  grupo ou do canal (membros, mídias, grupos em comum, administração).
- **Mensagens**: texto, fotos, vídeos, áudios, notas de voz, figurinhas,
  documentos, contatos, links e botões; responder, editar, encaminhar,
  favoritar, apagar, reagir com emoji, buscar emoji pelo nome, colar mídia
  com Control V, copiar por tipo de conteúdo e enviar arquivos grandes.
  A janela de detalhes de uma mensagem de grupo do WhatsApp mostra quem
  recebeu, abriu e reproduziu.
- **Status da pessoa** no título da janela: online, visto por último e
  digitando.
- **Status do WhatsApp e histórias do Telegram**: no filtro "Status e
  histórias", cada pessoa vira uma entrada; ver, tocar, marcar como visto,
  responder em particular e curtir, e também postar o seu (texto, foto ou
  vídeo). Quem vê o status do WhatsApp se define pelo celular.
- **Mensagens temporárias** (WhatsApp e Telegram): identifica as mensagens
  que somem, mostra o prazo, deixa ligar, mudar e desligar por conversa e
  apaga daqui quando o prazo acaba (opção, ligada).
- **Prévia de links** com o título e a descrição que quem enviou mandou
  junto; buscar a página no computador é opcional e vem desligado, porque o
  site veria o seu IP.
- **Progresso** de envios e downloads (no WhatsApp, com a DLL do neonize de
  teste que o projeto usa; veja `docs/decisoes.md`).
- **Inteligência artificial (opcional, com a sua chave)**: transcreve voz e
  áudio, descreve fotos, figurinhas e vídeos (por quadros, fora do Gemini) e
  converte PDF em texto acessível; pode agir sozinha nas conversas que você
  escolher. Os provedores são Google Gemini, OpenAI, Claude, Groq, Mistral e
  OpenRouter, e as chaves ficam cifradas neste computador.
- **Acessibilidade**: tudo com controles nativos, lidos pelo leitor de tela;
  os avisos falados do programa (mensagens novas, resultados da IA e
  semelhantes) usam hoje a fala direta do NVDA; com outros leitores, boa
  parte deles aparece na barra de situação. Atalhos, falas e sons configuráveis (inclusive fora da conversa aberta e
  fora do TeleZapp), pacotes de sons (Padrão com os bips do sistema, TeleZapp
  e personalizados) e uma janela de configurações com busca.
- **Backup e restauração** de configurações, contas, conversas e mídias (as
  partes que você escolher), com senha
  opcional.

Fora do escopo por enquanto: vídeo nas chamadas.

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

## Dependências principais

wxPython (interface), neonize (WhatsApp), Telethon e py-tgcalls (Telegram),
sounddevice, soundfile e soundcard (áudio), numpy e OpenCV (quadros de vídeo
para a IA), pyzipper (backup com senha), segno (QR Code) e o pacote `emoji`
(nomes de emojis em português). A lista exata está em `requirements.txt`, e as
licenças em [`docs/licencas-de-terceiros.md`](docs/licencas-de-terceiros.md).

## Como rodar (Windows)

1. Tenha o **Python 3.13** instalado.
2. Dê duplo clique em **`iniciar-telezapp.bat`**. Na primeira vez ele cria o
   ambiente na pasta `venv` e instala os componentes (cerca de um minuto, com
   aviso numa caixa de mensagem). Depois abre o TeleZapp sem janela de
   terminal.
3. Na primeira abertura, o TeleZapp oferece adicionar uma conta do Telegram.
   O login é feito em janelas próprias: número, código recebido e, se a conta
   tiver, senha de duas etapas.
4. Para o WhatsApp, use o menu Arquivo, Adicionar conta do WhatsApp:
   escolha até onde trazer as mensagens antigas e depois, na janela de
   conexão, "Parear com número de telefone" (digite o número em formato
   internacional, como +55 51 99999 8888, e o código no celular) ou
   "Parear via QR Code" (o QR abre em tela cheia).

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
  config.py            pasta de dados, opções e log
  nucleo/              modelos comuns, eventos, contas, backup, pacotes de sons
  nucleo/ia/           provedores de IA, chaves cifradas e vídeo por quadros
  provedores/          o contrato comum (base.py), WhatsApp e Telegram
  armazenamento/       banco local SQLite
  midia/               leitura própria de MP4 e Ogg/Opus, download, gravação
  interface/           janela principal, configurações, detalhes e diálogos
  acessibilidade/      fala direta (NVDA) e sons dos eventos
  ajuda/               guia de uso e novidades (HTML)
  sons/                pacote de sons "TeleZapp" (gerado por ferramentas/gerar_sons.py)
testes/                testes automáticos (python -m pytest testes)
ferramentas/           apoio ao .bat, publicação das Releases e geração dos sons
Backup/                neonize original e restauro da DLL de teste (a cópia de
                       teste fica só no computador, fora do git)
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

Copyright (C) 2026 Fábio Scheffer Moraes.

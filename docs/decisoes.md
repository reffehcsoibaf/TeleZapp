# Decisões e propostas

"Adotada" = escolhida pelo responsável do projeto. "Proposta" = recomendada a
partir dos experimentos, ainda a confirmar.

## Arquitetura

| # | Tema | Situação | Escolha | Por quê (evidência) |
|---|---|---|---|---|
| 1 | Linguagem | Adotada | **Python 3.13** | Familiaridade; os experimentos rodaram sem problemas |
| 2 | Interface | Proposta | **wxPython** (controles nativos) | Lido corretamente pelo NVDA no protótipo |
| 3 | WhatsApp | Proposta | **neonize** (ligação Python da whatsmeow) | Sem navegador, Node nem `npm`; transferências de 7 a 18 MB/s |
| 4 | Telegram | Proposta | **Telethon + `cryptg`**, partes de 512 KB, 4 a 8 transferências paralelas | De 0,6 para ~10 MB/s |
| 5 | Mídia sem FFmpeg | Adotada | Montar vídeo e nota de voz no próprio app. **Sem `hachoir`**: duração, largura e altura lidas por código próprio da família MP4 (MP4, MOV, M4V, 3GP). Outros formatos (MKV, AVI, WMV, WEBM...) vão como **documento**. Vídeo HEVC vai como vídeo, com aviso de que pode não tocar em todos os celulares. Conversão por FFmpeg, se vier, será opcional e baixada só por quem ativar | O FFmpeg só serve ao neonize para ler duração e fazer miniatura; os apps de celular convertem para MP4 antes de enviar, e outros formatos chegam como documento; o `hachoir` é GPL-2.0 (ver decisão 11). Ao receber, a duração e o tamanho vêm na própria mensagem |
| 6 | Nota de voz | Adotada | **Ogg/Opus mono 48 kHz, nível padrão do `soundfile` (~62 kbit/s)**, ajustável nas configurações | Exigência dos dois serviços para aparecer como mensagem de voz; no teste de microfone, nenhuma diferença perceptível entre ~260 e ~62 kbit/s, com um quarto do tamanho |
| 7 | Fala | Proposta | DLL do controlador do NVDA, carregada por `ctypes` | Fala direta funcionou (código 0) |
| 8 | Empacotamento | Proposta | **PyInstaller `--onedir`** | 95 MB; todos os componentes carregam |
| 9 | Provedores | Proposta | Uma interface comum (conectar, listar, ler, enviar, baixar, eventos), uma implementação por serviço, cada uma em sua thread | Telethon usa `asyncio`; o neonize bloqueia ao conectar |
| 10 | Histórico | Proposta | Banco local (SQLite) | O WhatsApp só entrega mensagens como eventos |
| 11 | Licença | Adotada | **GPL-3.0-or-later** | Escolha do responsável: versões derivadas devem continuar abertas. O `hachoir` (GPL-2.0) fica fora do aplicativo (decisão 5); restam licenças a conferir (pendência 1 e `docs/licencas-de-terceiros.md`) |

## Interface e acessibilidade

- Nenhum fluxo pode depender de ler o terminal ou de ver a tela.
- Tratar Enter e Esc na janela (`EVT_CHAR_HOOK`); o `ListBox` não entrega o Enter.
- Ao abrir uma conversa: foco no item "Início das mensagens não lidas" ou, se
  não houver, na última mensagem. Esc volta para a lista de conversas.
- Enter na caixa de digitação envia; Shift+Enter quebra a linha.
- Três estilos de leitura da mensagem (autor primeiro, conteúdo primeiro, autor
  só quando muda), escolhidos num menu.
- Avisos de mensagem nova: fala pelo NVDA mais som, ambos desligáveis.
- **Login em janelas próprias** (adotado): campos rotulados e erros em caixa de
  mensagem do Windows. Nada de Bloco de Notas nem terminal no aplicativo (o
  Bloco de Notas era só um recurso dos experimentos).
- **WhatsApp** (etapa 2, adotado): pareamento por código numérico **ou** QR
  Code, na mesma janela; o QR se renova sozinho e a troca é anunciada.
- Esc na caixa de digitação cancela a resposta em andamento, se houver; senão
  volta para a lista de conversas.

## Aplicativo (etapa 1)

- **Dados fora do programa**: sessões, banco (`telezapp.db`), configuração e
  logs em `%APPDATA%\TeleZapp`. Nada que dê acesso às contas fica na pasta do
  repositório.
- **Credenciais do Telegram** (`api_id`/`api_hash`) identificam o aplicativo;
  o projeto vai registrar as suas e embuti-las (`config.py`). Até lá, vêm do
  arquivo dos experimentos ou são pedidas uma vez.
- **Etapas**: 1) Telegram com texto; 2) WhatsApp; 3) mídias; 4) várias contas,
  avisos e configurações.
- **WhatsApp (etapa 2a)**: neonize fixado na versão testada (0.5.2), com
  `connect()` numa thread própria e os envios numa fila; o aparelho aparece no
  celular como "TeleZapp". Encerrar usa `stop()` (o `disconnect()` não termina
  a conexão). As conversas vêm do banco local e das mensagens que chegam.
  Conversas com endereço LID são trocadas pelo número quando o WhatsApp
  informa. O QR Code é desenhado com o `segno`, que já vem com o neonize.
- **Histórico do WhatsApp (etapa 2b)**: o celular só manda histórico logo
  depois do pareamento. Antes de parear, a pessoa escolhe até onde trazer
  (recentes, 30 dias, 6 meses, 1 ano ou tudo); o pedido vai ao celular
  (`requireFullSync` e `fullSyncDaysLimit`) e o app guarda o que vier dentro
  do período. Medido no 1º pareamento real (padrão do WhatsApp): 145
  conversas, 585 não lidas, 2.000 nomes de perfil e ~30.500 mensagens.
  Conversas de status e canais ficam de fora.
- **Pareamento acessível**: modo código primeiro, com o número já preenchido;
  o código abre numa janela só dele, com o foco no código (como no WinZapp);
  sons de pronto, atualizado e conectado. QR com margem de 6 módulos, preto
  puro sobre branco, ampliado só por números inteiros, e opção de tela cheia
  (verificado com um leitor de QR nos testes). Conta desconectada pelo
  celular: o app oferece parear de novo na mesma conta, mantendo as
  conversas. Menu Arquivo, Remover uma conta.
- **Testes automáticos** rodam fora do Windows (núcleo, banco, leitura de MP4,
  provedor do Telegram com cliente simulado e lógica da janela com um wx
  simulado). O que depende de tela, NVDA e conta real é testado no Windows.

## Riscos e pendências

1. **Licenças.** O `hachoir` declara GPL-2.0 sem "ou posterior" (conferido
   no pacote 3.4.0), incompatível com a GPL-3.0-or-later: **não entra no
   aplicativo** (decisão 5); só os experimentos antigos o usam. Falta
   conferir a licença da DLL do controlador do NVDA e das dependências Go
   embutidas na DLL do neonize (veja `docs/licencas-de-terceiros.md`).
2. **Bloqueio de contas**: nenhum dos dois serviços oferece API oficial para
   contas pessoais. O risco existe e não foi medido. A troca de conta dentro do
   mesmo app mitiga o efeito, não a causa.
3. **Dependência de terceiros**: o neonize é mantido por terceiros e acompanha a
   whatsmeow; mudanças do WhatsApp podem quebrá-lo.
4. **Distribuição**: executáveis sem assinatura costumam gerar alerta do
   SmartScreen e de antivírus em outros computadores (não testado aqui).
5. **Notas de voz gravadas no app**: qualidade padrão definida (decisão 6).
   Falta enviar uma nota gravada pelo WhatsApp. O app deve medir o nível e
   avisar quando a gravação saturar (aconteceu no teste) e listar microfones
   pela WASAPI; microfones Bluetooth limitam a voz a 8 kHz.
6. **Vídeo sem miniatura** e arquivos acima de 20 MB: ainda não avaliados.
7. **Chamadas**: fora do escopo. O neonize só avisa e recusa; uma biblioteca
   separada (meowcaller) existe, mas é jovem e não está exposta ao Python.

## Plano do projeto (lista de ideias do responsável, 13/10/2026)

Aprovado pelo responsável. As ideias foram divididas pelo efeito na base.

### Grupo 1: afeta a base, feito antes da etapa 3

- **Versão `ano.mês.dia.dígito`** (ex.: 2026.10.9.0; uma segunda versão no
  mesmo dia é 2026.10.9.1). Cabe nos metadados de versão do Windows (quatro
  números até 65535); entra no instalador, no executável portátil e na lista
  de programas instalados quando eles existirem (etapa 4).
- **Menu vertical**, como no telezapp migration: uma única entrada "Menu" na
  barra, aberta pelo Alt, com as seções como submenus.
- **Guia de uso em HTML** no estilo do NVDA, sempre com a versão atual e um
  rodapé com licença, desenvolvedores e site.
- **Dois registros de mudanças**: `novidades.html` para o usuário (da versão
  mais nova para a mais antiga, sem termos técnicos) e `CHANGELOG.md`, o
  registro técnico.
- **Rotas limpas**: dados só em `%APPDATA%\TeleZapp`; arquivos temporários
  numa subpasta própria, limpa pelo app; nada solto no `%temp%` do Windows.
- **Recibos por participante** (data e hora de entrega, leitura e
  reprodução; nos grupos, por membro), guardados desde já para a janela de
  dados da mensagem. No Telegram, em grupos, só existe "lida até tal
  mensagem".
- **Status do WhatsApp guardados** em vez de descartados, para postar,
  curtir e responder depois.
- **Registro das opções de configuração** (nome, categoria, descrição), base
  da janela de configurações com busca.
- **Mídias baixadas registradas no banco** (caminho, tamanho, data), base da
  limpeza de conversas: entra com a etapa 3.

### Grupo 2: nas etapas previstas

- **Etapa 3, mídias**: baixar, abrir e enviar foto, vídeo, documento e
  áudio; gravar nota de voz.
- **Etapa 4**: várias contas (acabamento); sons de eventos com arquivos e
  opções; janela de configurações no estilo do NVDA (categorias na vertical,
  itens por Tab, busca); backup e restauração das configurações (sem
  sessões nem senhas); ordem das informações da mensagem definida pelo
  usuário; instalador, portátil, desinstalação limpa e atualização com uma
  janela de novidades em texto somente leitura, com o foco no texto.

### Grupo 3: depois (etapa 5 em diante)

| Ideia | Viabilidade |
|---|---|
| IA multiprovedores (transcrição, descrição de imagem e vídeo, PDF acessível) | Viável |
| Limpeza de conversas com filtros e total antes de confirmar | Viável depois da etapa 3 |
| Privacidade, editar perfil, bloquear e desbloquear | Viável nos dois serviços |
| Enquetes | Viável nos dois |
| Status: postar, curtir, responder | Viável no WhatsApp, com cuidado |
| Comunidades | Viável para ver (grupos ligados) |
| Contatos | Telegram sim; WhatsApp só leitura (a agenda é do celular) |
| Listas de transmissão | Incerto: suporte limitado da whatsmeow |
| Chamadas de áudio e vídeo | Fora por enquanto: o neonize não tem; no Telegram exigiria componente pesado |

## Etapa 3a: receber e abrir mídias (14/10/2026)

Decisões do responsável: tudo roda dentro do app (como nos clientes do
gênero), as mídias ficam contidas no programa e baixar ao sincronizar ou sob
demanda é configurável.

- **Onde**: `%APPDATA%\TeleZapp\midias\<conta>\<conversa>`; apagadas com a
  conta. Nada vai para Documentos nem para o `%temp%`.
- **Quando baixar**: opção "sob demanda" (padrão) ou "automático" até um
  limite (5 a 100 MB). Mídias do histórico do WhatsApp sempre sob demanda.
- **Como abrir**: leitor próprio. Imagem em janela; áudio e voz com
  soundfile + sounddevice (validados no experimento de voz); vídeo, e áudio
  que a libsndfile não abre (m4a/aac), com o `wx.media.MediaCtrl` do Windows.
  Documentos: texto pequeno no app; os demais têm um botão explícito para o
  programa do Windows (única saída do app).
- **WhatsApp**: o download exige a mensagem original; passa-se a guardar uma
  "ficha" mínima por mídia (sem miniatura). Mídias recebidas antes não têm
  ficha e não baixam.
- **Não verificado nos testes automáticos**: o `MediaCtrl` e as janelas reais
  (só no Windows). Velocidade de reprodução e envio de arquivos ficam para a
  etapa 3b.

## Próximos passos sugeridos

1. Grupo 1 do plano acima.
2. Etapa 3b: enviar arquivos e gravar nota de voz (a 3a, receber e abrir, está pronta para teste).
3. Adicionar o aviso de licença nos arquivos e conferir as licenças pendentes.
4. Etapa 4 (ver o plano): configurações, sons, instalador, atualização e
   assinatura.
5. Testes de estabilidade e de arquivos maiores.

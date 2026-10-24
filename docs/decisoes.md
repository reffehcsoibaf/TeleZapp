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
- Na caixa de digitação, Enter envia e Shift+Enter quebra a linha; Control+Enter também envia (função `enviar_msg` dos atalhos, trocável). 22/10/2026: a opção `enter_envia` (Escrita) vem ligada; desmarcada, só Control+Enter envia e Enter quebra a linha, como no Telegram Web e no Gmail.
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
7. **Chamadas**: fora do escopo no WhatsApp (desde 19/10 o TeleZapp ao
   menos avisa e registra a chamada na conversa). O neonize só avisa e recusa; uma
   biblioteca separada (meowcaller) existe, mas é jovem e não está exposta
   ao Python. **No Telegram, em investigação (15/10/2026)**: o `py-tgcalls`
   3.0.0 (LGPL-3.0, sobre a NTgCalls, a mesma família de motor de chamada que
   os clientes oficiais usam) tem chamada 1 a 1 com Telethon e rodas prontas
   para Windows; instala em ~63 MB e lista microfone e alto-falante do
   Windows sem FFmpeg. **Teste real (15/10/2026, `9-teste-chamada-telegram.bat`)**:
   chamada de voz de 45 s, ligando do computador para um celular; atendida
   após 16,8 s de toque e **voz boa nos dois lados**, sem FFmpeg, só com o
   microfone e a saída padrão do Windows. Ambiente de ~59 MB (a NTgCalls
   sozinha tem 26 MB). **Não medido**: uso de CPU (veio vazio), latência,
   chamada recebida, vídeo, queda de rede, microfone Bluetooth. Sem janela
   nem tecla de atender/recusar/mudo: só existe o experimento.

## Plano do projeto (lista de ideias do responsável, 13/10/2026)

Aprovado pelo responsável. As ideias foram divididas pelo efeito na base.

### Grupo 1: afeta a base, feito antes da etapa 3 (CONCLUÍDO)

Todos os itens abaixo estão implementados (conferido no código em
14/10/2026, versão 2026.10.14.15). Não foram todos verificados no app real.

- [x] **Versão `ano.mês.dia.dígito`** (ex.: 2026.10.9.0; uma segunda versão no
  mesmo dia é 2026.10.9.1). Cabe nos metadados de versão do Windows (quatro
  números até 65535); entra no instalador, no executável portátil e na lista
  de programas instalados quando eles existirem (etapa 4).
  Feito: `VERSAO` e `versao_valida` em `telezapp/__init__.py`.
- [x] **Menu vertical**, como no telezapp migration: uma única entrada "Menu" na
  barra, aberta pelo Alt, com as seções como submenus.
- [x] **Guia de uso em HTML** no estilo do NVDA, sempre com a versão atual e um
  rodapé com licença, desenvolvedores e site (`ajuda/guia.html`).
- [x] **Dois registros de mudanças**: `novidades.html` para o usuário (da versão
  mais nova para a mais antiga, sem termos técnicos) e `CHANGELOG.md`, o
  registro técnico.
- [x] **Rotas limpas**: dados só em `%APPDATA%\TeleZapp`; arquivos temporários
  numa subpasta própria, limpa pelo app; nada solto no `%temp%` do Windows
  (`config.pasta_temporaria` e `limpar_temporarios`).
- [x] **Recibos por participante** (data e hora de entrega, leitura e
  reprodução; nos grupos, por membro), guardados desde já para a janela de
  dados da mensagem. No Telegram, em grupos, só existe "lida até tal
  mensagem". Feito: tabela `recibos`.
- [x] **Status do WhatsApp guardados** em vez de descartados, para postar,
  curtir e responder depois. Feito: tabela `status`. Postar, curtir e
  responder continuam no Grupo 3.
- [x] **Registro das opções de configuração** (nome, categoria, descrição), base
  da janela de configurações com busca (`config.OPCOES` e `buscar_opcoes`).
  A janela de configurações em si é da etapa 4.
- [x] **Mídias baixadas registradas no banco** (caminho, tamanho, data), base da
  limpeza de conversas: tabela `midias` e `Banco.registrar_midia`. A limpeza
  de conversas em si é do Grupo 3.

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
| Limpeza de conversas com filtros e total antes de confirmar | Feita (17/10/2026): mídias baixadas ou mensagens, com registro (`limpas`) para não voltarem; só um novo pareamento zera |
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

## Etapa 3b: enviar arquivos e gravar voz (14/10/2026)

Pedido do responsável: um botão para gravar do microfone e outro para gravar
o som interno do computador, se fosse possível.

- **Som interno é possível**: loopback do WASAPI pela biblioteca `soundcard`
  (BSD-3-Clause). A `sounddevice` do Windows não tem essa captura; a "Mixagem
  estéreo" de alguns drivers não existe em todos os computadores, então não
  serve de base. Verificado no computador de desenvolvimento: um tom de 440 Hz
  tocado nos alto-falantes foi gravado e voltou a 440 Hz. O microfone continua
  na `sounddevice`, validada no experimento de voz.
- **O som interno também grava a fala do leitor de tela** (e qualquer outro
  som). A janela de gravação avisa. Não há como excluir um programa só.
- **Formato**: Ogg/Opus mono 48 kHz, o mesmo do experimento de voz; a
  gravação vai para um WAV temporário e é convertida ao parar.
- **Ambos os botões enviam como mensagem de voz.** Enviar o som interno como
  "arquivo de áudio" (sem a forma de onda de voz) ficou para depois: o
  WhatsApp com Ogg/Opus fora do modo voz não foi testado.
- **Anexar arquivo**: foto (JPG, PNG, WEBP), vídeo (MP4/MOV/M4V/3GP), áudio e
  documento; tudo o mais vai como documento, sem recodificar. Limite de 2 GB.
  O texto da caixa vira legenda.
- **Mídia enviada** é copiada para o armazém da conversa (gravações
  temporárias são movidas) e registrada em `midias`: abre sem baixar.
- **Pendências**: citar a mensagem respondida ao enviar mídia; ~~progresso do
  envio de arquivos grandes~~ (feito em 19/10); escolher microfone e saída
  de som (hoje o padrão do Windows); cancelar um envio em andamento;
  enviar várias mídias de uma vez; miniatura de vídeo e de foto no
  WhatsApp. Nada disto foi verificado nos serviços reais, só com clientes
  simulados.

## Feito depois da etapa 3b (14 e 15/10/2026)

Detalhes técnicos de cada item em `CHANGELOG.md`. Nada abaixo foi verificado
com leitor de tela nem com os serviços reais, salvo onde indicado.

- [x] **Botões de resposta e listas do WhatsApp** (2026.10.14.10 a .15):
  tocar nos botões como `wx.Button` na ordem de Tab. Modelo
  (`templateButtonReplyMessage`) aceito e entendido no teste real;
  `buttonsResponseMessage` recusado com 479 (variantes em teste).
- [x] **Menu Depurar** (2026.10.14.11): estrutura bruta das mensagens,
  registro técnico detalhado do WhatsApp, padrão desligado.
- [x] **Links e botões de endereço pelo Tab; Enter abre mídia ou texto**
  (2026.10.15.0).
- [x] **Velocidade do áudio de 0,25x a 3x**, passo ajustável (2026.10.15.1):
  era pendência da etapa 3b. Só medido com senoides e amostra de voz.
- [x] **Janela de configurações com busca** (2026.10.15.2): parte da etapa 4,
  cobre só as opções que já existem em `config.OPCOES`.
- [x] **Nome de grupo renomeado atualizado** (2026.10.15.3 e .4): no
  Telegram e no WhatsApp, inclusive ao reconectar. Falta verificar
  `get_joined_groups` com um WhatsApp real.

## Chamadas de voz no Telegram (15/10/2026, versão 2026.10.15.5)

Decisão do responsável: seguir com as chamadas depois do experimento 9.

- **Motor**: `py-tgcalls` 3.x (NTgCalls), opcional. Sem ele, o app roda igual
  e o menu Chamada avisa que a conta não faz chamadas. Entra no
  `requirements.txt` (`py-tgcalls>=3.0,<4`).
- **Escopo**: só áudio, só Telegram, só conversas com uma pessoa. Vídeo,
  grupos e o WhatsApp ficam de fora.
- **Janela única que muda de estado** (`interface/chamada.py`), com o foco
  sempre no botão mais provável: Atender ao tocar; Desligar ao chamar,
  conectar e em chamada. Ao tocar, a fala diz "Enter atende, Escape
  recusa". O título da janela e a fala trazem o nome de quem liga.
- **Esc não desliga uma chamada conectada** (fácil de apertar sem querer):
  recusa ao tocar, cancela ao chamar ou conectar; em chamada só lembra do
  botão Desligar. Fechar o TeleZapp com chamada aberta pergunta antes.
- **Microfone e saída**: os do Windows vistos pela NTgCalls; a escolha fica
  em `chamada_microfone` e `chamada_saida` e troca no meio da chamada.
- **Sons**: toque repetido a cada 3 s (recebendo), tom de espera (chamando),
  conectado e desligada; "Som de chamada" desliga os que repetem, a fala
  continua.
- **Segunda chamada** enquanto há uma aberta é recusada sem incomodar.
- **Atalhos** com a janela principal em foco: Ctrl+Shift+L (ligar), J
  (janela da chamada), K (silenciar) e H (desligar).
- **Pendências**: chamada recebida e leitura da janela pelo NVDA ainda não
  testadas no app real; registrar a chamada (perdida, recusada, duração) na
  conversa; escolher dispositivo nas configurações; aviso de áudio em
  silêncio; empacotamento com a NTgCalls (PyInstaller) e as dependências
  Go/C++ para a conferência de licenças; vídeo e grupos.

## Versão 2026.10.18.0 (18/10/2026)

O que entrou neste dia, com as decisões que não aparecem só no código. O texto
para o usuário está em `telezapp/ajuda/novidades.html`; o técnico, em
`CHANGELOG.md`. **Nada disto foi visto ainda no app real** (só testes
automáticos): a lista do que falta testar fica na memória do projeto.

- **Mensagens**: copiar por tipo de conteúdo; colar mídia (Control V) como
  anexo que espera o Enter, com o texto da caixa de legenda (também em Nova
  mensagem); editar mensagem (F2; 15 min no WhatsApp, 48 h no Telegram);
  encaminhar por reenvio do conteúdo, sem o rótulo "Encaminhada" (decisão do
  responsável); responder em particular a mensagem de grupo; contatos
  recebidos viram botão "Iniciar conversa com" e o aviso "sem suporte" só
  fica para o que não é reconhecido; botão "Entrar no grupo" para convites de
  administrador e links (chat.whatsapp.com, t.me).
- **Conversas**: modo de seleção (Control Espaço) com ações em massa; Delete
  apaga; apagar grupo pergunta entre limpar, apagar da lista e sair do grupo;
  salvar conteúdo em .zip; conversas somente leitura escondem a caixa e os
  botões de envio; janela de detalhes (Control I) com mídias filtradas,
  membros, grupos em comum e administração de grupo (WhatsApp e Telegram) e
  de canal (WhatsApp).
- **Sincronia com o WhatsApp**: aviso de conversa lida no celular
  (`ChatMarkAsReadEv`). A marca de "ouvida" feita no celular com o TeleZapp
  fechado **não chega**: o aviso é efêmero e não há outra fonte. Rejeitada a
  aproximação "conversa lida = áudios ouvidos" (o responsável quer saber o
  que realmente ouviu).
- **Sons**: 18 eventos (16 em 18/10; a reação recebida e a menção ou resposta num grupo entraram em 19/10), cada um com som padrão, sem som ou arquivo na pasta
  `sons` (dentro da pasta de dados, no backup). Eventos novos acompanham o
  som do evento parecido enquanto não têm escolha própria.
- **Backup e restauração**: .zip com senha opcional (AES-256 por `pyzipper`);
  partes escolhidas; configurações valem na hora e o resto troca na próxima
  abertura, guardando o anterior em `antes-da-restauracao`. Depuração e
  exigência do código secreto nunca são restauradas por arquivo. As chaves de
  IA só entram em backup **com senha** (zip cifrado em AES-256; sem senha
  ficariam legíveis): vão em `ia_chaves.json` dentro do zip, decifradas do
  DPAPI na hora de gravar, e na restauração da parte de configurações voltam
  ao cofre cifradas de novo pelo DPAPI do usuário e do computador de destino
  (20/10/2026, a pedido do responsável).
- **Distribuição**: `ferramentas/publicar.py` monta zip, hash e notas;
  Ajuda, Verificar atualizações só avisa. Instalar, portátil e atualizador
  ficam para perto do lançamento (decisão do responsável). Aviso de software
  experimental no README, no guia, em Sobre e nas notas da Release. Para
  quem recebe um zip: apagar a pasta antiga antes de extrair (instrução dada
  pelo responsável, não automática).
- **Inteligência artificial**: provedores Gemini, OpenAI, Claude, Groq e
  OpenRouter (`nucleo/ia`), desenho dos adaptadores como no WinZapp
  (GPL-3). Por tarefa (voz/áudio, imagem e figurinha, vídeo, PDF) o
  responsável organiza a ordem de tentativa; se um falha, vai ao próximo.
  Chaves cifradas pelo DPAPI do Windows, fora do log e só no backup com senha; consentimento
  por provedor antes do primeiro envio. Modelos padrão vieram do catálogo do
  WinZapp (Gemini 3.8 Flash entra no gratuito; Gemini tem modo automático com
  alternativos). Aprendizados: a Groq (Cloudflare) devolve 403, erro 1010, ao
  User-Agent do Python, e a OpenAI devolve 429 `insufficient_quota` sem
  saldo; ambos pareciam "chave recusada". O Enter em mídia é configurável
  (abrir, baixar ou usar a IA). Fica para depois: arquivos acima de 14 MB
  (fora vídeo) e perguntas de acompanhamento.
  2026-10-19: vídeo fora do Gemini vai por quadros (uma grade de 4, 9 ou 12
  quadros com a hora, em uma imagem só, via OpenCV) e a fala é transcrita a
  parte; modo automático escolhido conversa por conversa (voz/áudio e
  fotos/figurinhas; vídeo e PDF nunca automáticos), por ser uma chave paga e
  haver grupos barulhentos. Ainda não visto no app real nem no exe (conferir
  se o PyInstaller leva o cv2).
- **Chamadas do WhatsApp (pesquisa, em espera)**: o neonize só tem a
  sinalização. O WhatsApp Web ganhou chamadas (jul/2026) e o WA-JS aciona a
  pilha de VoIP dele; o WinZapp já faz chamadas assim (WPPConnect + Chrome,
  áudio ligado ao Python). Plano proposto, não iniciado: experimento (Playwright
  + Edge + WA-JS, pareamento por código como segundo aparelho, medir tempo e
  memória), opcional e desligado por padrão, sem trocar o acesso atual às
  mensagens pelo WPPConnect. O responsável deixou o assunto de lado.

## Versão 2026.10.21.0 (21/10/2026): botões e listas de empresa, registro e barras de progresso

- **Resposta a botões e listas de mensagens de empresa**: o servidor do
  WhatsApp recusava (erro 479) porque o whatsmeow põe um nó `<biz>` nessas
  respostas e o WhatsApp Web não. Decisão: tirar o nó na DLL de teste do
  neonize, em vez de embrulhar a resposta em "documento com legenda" (o
  servidor aceita, mas a empresa ignora a mensagem, e o aplicativo diria
  "enviada" sem resposta). Um PR para o whatsmeow foi proposto. Sem a DLL de
  teste, as respostas voltam a dar 479 (`docs/neonize/sem-no-biz-whatsmeow-send.go.diff`).

- **Verificado ao vivo pelo responsável** (o que só os testes automáticos não mostram):
  - lista de uma empresa de energia (Equatorial, "Consulta de Débitos"): a empresa respondeu, em 21/10/2026, com a DLL de teste sem o nó `biz`;
  - barras de progresso (atualizar, instalar, backup, transferências): ficaram como ele queria (confirmado em 20/10/2026, em outra conversa);
  - não verificado ao vivo: o quick_reply nativo de mensagens interativas pelo TeleZapp (só testes automáticos; no WinZapp foi visto).

### Áudio, grupos, sons e quedas

- **M4A/AAC no player do app**: decodificar com o PyAV para WAV temporário em
  vez de mandar ao player do Windows, para entrar na sequência de áudios.
- **Abrir grupo sem esperar as menções**: a releitura de nomes (rede, ~0,3 s
  cada) vai para segundo plano; quem segue sem nome só é procurado após 10 min.
  Mensagem editada passa a mostrar o nome.
- **Sons**: uma thread por vez no PortAudio (acessos simultâneos derrubavam o
  programa); sons de até 2 s pré-carregados na RAM; espera do Enter de 40 para
  10 ms. `falha-nativa.log` recebe também o stderr das DLLs.
- **Visto no app real pelo responsável (21/10/2026)**: barras de progresso (envio
  de arquivo grande), espera de 10 ms, M4A tocando e entrando na sequência, e o
  exe novo abrindo normal. Não visto: som de envio mais rápido e atualização
  pela janela (a barra de progresso da atualização só aparece quando a 21.0
  atualizar para a versão seguinte).

### Registro e barras de progresso

- **Registro (log) que o usuário manda ao suporte**: o texto prometia nunca
  guardar telefone completo nem texto de mensagem, mas o log real trazia
  telefones (aviso "mensagem não decifrada" e avisos do whatsmeow, com
  endereços `@s.whatsapp.net`, `@lid` e `@g.us`) e os 80 primeiros
  caracteres de mensagens de empresa. Agora todo o registro passa por
  `mascarar_texto` e a estrutura das mensagens de empresa sai sem os textos.
  O que pedir: `telezapp.log` (e `.1` a `.4`) e, se o programa fechou
  sozinho, `falha-nativa.log`, mais a versão e a hora do problema. Nunca
  `sessoes`, `config.json`, `telezapp.db`, `ia_chaves.json`, backups nem o
  que o modo de depuração grava. Nomes de grupos e de contatos não são
  mascarados.

### Barras de progresso

- **Por que**: o NVDA toca bipes que sobem do grave ao agudo numa barra de
  progresso (só na janela em primeiro plano); isso diz mais ao cego do que a
  fala "20 por cento" (pedido do responsável). Avanços longos abrem uma
  janela com `wx.Gauge`: atualizar (com Cancelar), instalar, criar portátil,
  fazer e restaurar backup, download pedido (Cancelar) e envio grande. Os dois
  últimos só abrem depois de 1 s e há a opção `barra_de_progresso` para eles.
- **Cuidado**: a janela toma o foco; no envio, quem está digitando perde as
  teclas para a janela (ela não tem Enter padrão, então um Enter perdido não
  cancela nada). Por isso a opção e o atraso de 1 s.
- **Não visto no app real**: nada disso foi visto com o NVDA ligado (bipes,
  foco na volta à janela principal).

## Versão 2026.10.20.0 (20/10/2026): mensagens temporárias

- **Identificar e definir**: o WhatsApp manda o prazo em cada mensagem
  (`contextInfo.expiration`) e o ajuste da conversa em
  `ProtocolMessage.EPHEMERAL_SETTING`; o Telegram, `ttl_period` na mensagem e
  o aviso de serviço `MessageActionSetMessagesTTL`. Períodos: WhatsApp 24
  horas, 7 dias e 90 dias; Telegram 1 dia, 1 semana e 1 mês; 0 desliga. Em
  Detalhes da conversa (só conversas e grupos; canais não têm). Chats
  secretos do Telegram ficam de fora (o Telethon não os cobre).
- **Enviar**: o whatsmeow não põe o prazo sozinho, então o TeleZapp o põe em
  cada mensagem (`com_expiracao`); sem isso a mensagem enviada daqui não some
  no celular. O Telegram aplica o prazo da conversa no servidor.
- **Apagar aqui**: cada aparelho apaga no prazo; o TeleZapp apaga daqui (e a
  mídia baixada) por uma varredura ao abrir e a cada minuto, com a opção
  `temporarias_apagar_aqui` (Privacidade, ligada, decisão do responsável).
  Usa `limpeza.apagar_mensagem`, que registra para a sincronia não trazer de
  volta. Desligada, a mensagem fica e a linha diz que passou do prazo.
- **Não verificado no app real**: nada disso foi visto em conta real
  (mudar o prazo no WhatsApp, receber e enviar com prazo, a unidade que a DLL
  espera, o aviso do Telegram). O `set_disappearing_timer` do neonize não
  serve (confunde nanossegundos e milissegundos e manda a hora errada), por
  isso o TeleZapp chama a DLL direto.

## Versão 2026.10.19.1 (19/10/2026): instalar e portátil

- **Como o NVDA, sem administrador**: o executável de uma cópia portátil
  oferece "Instalar o TeleZapp neste computador..." (Menu); a instalada
  oferece "Criar cópia portátil..." e "Desinstalar". Instala em
  `%LOCALAPPDATA%\Programs\TeleZapp`, com atalhos (menu Iniciar, área de
  trabalho opcional) e entrada em Aplicativos instalados. Decidido com o
  responsável: por usuário (sem UAC), dados portáteis na pasta `dados` ao
  lado do executável.
- **Dados**: a instalada usa `%APPDATA%\TeleZapp`. A portátil usa `dados` se
  essa pasta existir; sem ela (o zip das Releases), continua em
  `%APPDATA%`. Criar a cópia portátil pode levar os dados (inclui as
  sessões, com aviso); instalar a partir de uma portátil com `dados` pode
  levá-los para o computador, guardando os de antes.
- **Download em um arquivo só**: o que as pessoas baixam é o `TeleZapp.exe`
  das Releases (instalador de um arquivo, com o programa embutido): abre
  direto nos botões Instalar, Criar cópia portátil, Guia de uso e Fechar,
  sem "usar sem instalar" (a portátil cobre esse caso). O `TeleZapp.zip`
  (nome fixo) continua nas Releases para o atualizador e para quem quiser
  extrair à mão. Sem assinatura, o SmartScreen e alguns antivírus podem
  avisar; UPX desligado para não piorar. MSI descartado: não comporta a tela
  de botões. Pendente: assinar os dois executáveis.
- **Janela da atualização e o GitHub**: a janela abre com o texto (versão
  oferecida e novidades de todas as versões desde a que está em uso)
  focado; Tab leva a Sim e Não. Para uma versão instalada hoje receber o
  aviso basta publicar uma Release com `ferramentas/publicar.py`: tag
  `ano.mes.dia.digito` maior que a em uso, `TeleZapp.zip` e
  `TeleZapp.zip.sha256` anexados e as notas com `## Novidades da versão X`
  (o `publicar.py` já faz tudo isso, a partir de `novidades.html`). Sem o
  texto de novidades no `novidades.html` a Release sai vazia.
- **Desinstalar e backup**: antes de desinstalar (menu ou Aplicativos
  instalados) o programa pergunta se quer o backup de sempre; se o backup
  falhar ou a pessoa desistir de escolher o arquivo, nada é desinstalado.
- **Tela de boas-vindas**: ao abrir o executável de uma cópia não
  instalada, sem `dados` e sem `sem-boas-vindas.txt`, aparece um texto
  curto sobre o programa e os botões Instalar, Criar cópia portátil, Guia de
  uso, Usar sem instalar (com opção de não mostrar de novo) e Fechar. O
  botão "Usar sem instalar" foi acrescentado ao pedido, senão o zip das
  Releases não abriria o programa.
- **Atualização pelo programa**: Ajuda, Verificar atualizações oferece
  "Baixar e instalar a atualização" quando a Release tem o zip e o
  `.sha256`. Baixa só de github.com por https, confere o SHA-256, extrai ao
  lado da pasta do programa (`.atualizacao`) e, depois de fechar, um `.bat`
  troca a pasta (a antiga vira `.antiga` até a nova abrir), mantendo `dados`.
  Vale para instalada e portátil. A verificação automática ao abrir só
  avisa. Para as versões antigas (sem este código) a troca continua manual.
- **Não feito**: assinatura do executável, instalar para todos os
  usuários, restauro automático se a versão nova não abrir. **Não testado
  no app real**: instalar, desinstalar, criar portátil e atualizar com o
  executável gerado e uma Release de verdade (o script de troca foi testado
  com pastas de mentira).

## Versão 2026.10.19.0 (19/10/2026)

O que entrou neste dia, com as decisões. Texto para o usuário em
`telezapp/ajuda/novidades.html`; técnico em `CHANGELOG.md`. **Visto pelo
responsável no app real** (19/10): leitura única do nome na lista de
conversas, busca das configurações (seta para baixo), presença no título,
transcrição e descrição automáticas e reações. **O resto só passou nos testes
automáticos** e entra na lista de testes pendentes. O commit do dia é feito
no fechamento, por assunto.

- **Leitor de tela**: a lista de conversas virou `ListCtrl` de uma coluna
  (como as categorias das configurações), por causa da leitura dupla do NVDA;
  a busca das configurações leva ao primeiro resultado com a seta para baixo;
  a fala das mensagens novas se separou em três opções independentes do som
  (conversa aberta, outras conversas e fora do TeleZapp; quem tinha a antiga
  ligada continua ouvindo tudo); o texto da IA é falado inteiro ao ficar
  pronto e a linha da mensagem traz a descrição inteira (transcrição até 1000
  letras, ajustável); a porcentagem falada do download é configurável (só o
  Telegram informa o avanço). A documentação passou a falar em "leitores de
  tela"; a fala direta continua sendo do NVDA e isso está dito.
- **IA**: descrição de vídeo por quadros (uma grade de 4, 9 ou 12 quadros com
  a hora, via OpenCV) para qualquer provedor que veja imagens, com a fala
  transcrita à parte; o Gemini segue recebendo o vídeo inteiro até 14 MB.
  Transcrição e descrição automáticas ao receber, **ligadas conversa por
  conversa** (voz/áudio e fotos/figurinhas; vídeo e PDF nunca), sem janelas e
  sem pedir consentimento no automático (o consentimento do provedor é dado
  uma vez, pelo menu da mensagem).
- **Pareamento do WhatsApp**: janela com dois botões (telefone, com o número
  em formato internacional, e QR Code já em tela cheia). Os erros "código não
  aceito" e "HMAC do pareamento" vêm de dentro do whatsmeow (a janela e o
  provedor não mudaram); um testador com o executável do dia anterior teve o
  mesmo, então a causa provável é instabilidade do WhatsApp. O TeleZapp agora
  detecta a falha, avisa e refaz a conexão (até 3 vezes) para vir QR e código
  novos.
- **Presença**: status da pessoa no título (online, visto por último,
  digitando). No WhatsApp isso exige que a conta fique "disponível" enquanto a
  conversa está aberta (e quem esconde o próprio status não vê o dos outros);
  ao fechar a conversa volta a "indisponível". O Telegram não recebe nada do
  TeleZapp. Opção desligável.
- **Reações e emojis**: reagir (lista curta, "Outro emoji..." e tirar) no
  WhatsApp e no Telegram, e buscar emoji pelo nome em português para escrever
  (pacote `emoji`, BSD, sem tons de pele). O Telegram passou a mostrar as
  reações recebidas.
- **Detalhes de mensagem de grupo (WhatsApp)**: resumo (enviada em, recebida,
  aberta e reproduzida por N pessoas) e um botão por item com a lista de
  membros, data e hora e o menu dos membros do grupo. O Telegram só mostra a
  hora do envio (não guarda recibo por membro).
- **Chamadas do WhatsApp**: continuam sem atendimento no TeleZapp. Ele avisa
  quem liga (janela OK e Conversar, opção desligável) e registra na conversa
  (recebida, perdida, recusada ou atendida em outro aparelho, com duração).
- **Status e histórias**: o status do WhatsApp e as histórias do Telegram
  viram uma "conversa" de tipo status por pessoa, no filtro "Status e
  histórias" (fora de "Todas"). Ver, tocar, marcar como visto, responder em
  particular (só texto) e curtir. Somem após 24 h; no WhatsApp só chegam os
  publicados com o app conectado. **Postar** status (texto, foto ou vídeo) e
  história (foto ou vídeo, com legenda; no Telegram escolhe-se contatos ou
  todos). **Decisão do responsável**: quem vê o status do WhatsApp se define
  pelo celular; o neonize só lê essa privacidade (não há setter), e a tela de
  Privacidade mostra a escolha em modo leitura.
- **Prévia de links**: usa a prévia que o remetente manda junto (padrão).
  Buscar a página no computador é opcional e **desligado por padrão**, para
  receber e para enviar, porque o site vê o IP; só abre http/https públicos,
  nunca a rede local (nem por redirecionamento), com 5 s e 400 KB. No
  Telegram, com a opção de enviar desligada, a mensagem sai sem a prévia que o
  servidor montaria.
- **Sons**: tela refeita no estilo do WinZapp (caixa de pacote, lista de
  eventos ativados ou desativados, Ouvir som e, nos personalizados, Procurar
  som). Pacotes: Padrão (bips do sistema), TeleZapp (18 sons sintetizados
  aqui, sem amostras de terceiros, por causa das licenças; estéreo, até 2 s,
  começam no primeiro instante) e personalizados (arquivos importados para
  `sons\pacotes\<nome>` ao aplicar). Os dois primeiros não se editam. As
  opções `som_*` antigas viram o pacote "Personalizado". O exe precisa levar
  `telezapp/sons` como dado (o spec local já leva; fora do git).
- **Menu de contexto de mídia**: reproduzir ou abrir, baixar e salvar cópia
  sempre aparecem, mesmo com o Enter configurado para a IA ou só baixar.
- **neonize**: o pino segue em 0.5.2. O venv usa uma DLL e arquivos de teste
  (avisos ao vivo, `send_app_state`, `fetch_app_state`); a cópia fica em
  `Backup\neonize-0.5.2-teste` (fora do git, com `SHA256SUMS.txt` e
  `Backup\restaurar_neonize_teste.py`), e `Backup\neonize-0.5.2-original`
  agora tem os 7 originais. Para atualizar: conferir se a versão nova traz os
  PRs (#227 a #232), trocar o pino, testar numa conta real e lançar um
  TeleZapp novo; sem eles, a atualização desfaz os recursos de teste.
- **Progresso de download e envio**: no Telegram para todo arquivo; no
  WhatsApp só com a DLL de teste do neonize (que ganhou download direto para o
  arquivo e upload lendo do disco, com progresso e cancelamento), usada em
  arquivos a partir de 8 MB. Com o neonize oficial volta ao comportamento
  antigo (tudo em memória, sem porcentagem). A mudança precisa de PR no
  neonize, como as outras (patch em `docs/neonize/`).
- **Menções e nomes de perfil (WhatsApp)**: o nome de perfil passou a ser
  guardado pelos dois endereços da pessoa (telefone e LID, o segundo vem em
  `SenderAlt`) e procurado também nas mensagens guardadas por todos eles;
  as menções antigas só com telefone são refeitas ao abrir o grupo. As
  listas de quem recebeu, abriu e reproduziu usam a mesma busca, sem rede.
- **Sons de reação e de menção**: dois eventos novos (reação a uma mensagem
  sua; menção ou resposta a você num grupo, que substitui o som comum de
  grupo e não depende da opção "Som ao receber mensagem"). O tom de
  "chamando" do pacote Padrão passou de 0,4 s para 1,5 s.
- **Enter e a palavra digitada**: o Enter da caixa é tratado antes do
  controle, então o NVDA não fecha a última palavra digitada e a junta com a
  primeira da próxima mensagem. Dica sem código: espaço antes do Enter (é
  tirado ao enviar). Há uma opção experimental e desligada que entrega o
  Enter ao controle antes de enviar; falta ver como o NVDA reage.
- **Ainda não visto no app real**: avisos de chamada, vídeo por quadros,
  progresso de download e envio no WhatsApp (DLL nova), os dois sons novos
  (reação e menção), a opção do Enter, nomes de perfil nas menções e nas
  listas de recibos, detalhes de grupo, busca de emojis (Control Ponto) e menu de mídia, pacotes
  de sons e a tela nova, status e histórias (ver, responder, curtir e postar),
  prévia de links, o reinício do pareamento e o executável com OpenCV, emoji e
  `telezapp/sons` (conferir o PyInstaller).

## Mídia como resposta e menção por @ (23/10/2026)

Pedido do usuário: o programa dizia que a mídia ia sem citar a mensagem respondida; agora cita. E, em grupo, digitar @ lista os membros para mencionar. Decisões: a menção fica na caixa como "@Nome" (legível pelo leitor de tela) e só vira o formato do serviço no envio; o @ só abre a lista no começo ou depois de espaço (não atrapalha e-mails); Esc na lista deixa o @ digitado. Pendente: o usuário testar com contas reais (resposta com documento e foto no WhatsApp e no Telegram; menção com e sem @usuario no Telegram).

## Versão 2026.10.23.0 (23/10/2026): menus novos, criar grupos, chamadas e enquetes

Reúne tudo o que entrou depois da 2026.10.21.0 (o detalhe técnico está no CHANGELOG): chamadas de voz do WhatsApp pela DLL de teste do neonize, corretor ortográfico, atalhos personalizáveis, gravar por atalho, segundo plano e bandeja, enquetes, menus Novo e Ir para, configurações Interface e Mensagens, criar grupo, canal e comunidade, tópicos de grupo do Telegram, estado reproduzida, correção do áudio Ogg, credenciais do Telegram embutidas e o formulário de relatos. As confirmações do responsável estão nas seções abaixo. **Ainda sem teste no app real:** criar grupo, canal e comunidade nos dois serviços, tópicos do Telegram, Nova chamada, Novo contato, a busca em Gerenciar contatos, as credenciais embutidas no executável, a tela de Atalhos e o gravar por atalho, o segundo plano, votar e quem votou no Telegram, e o estado reproduzida nas mensagens antigas.

## Segurança dos dados: só documentar por ora (23/10/2026)

- Perguntaram ao responsável sobre a segurança dos dados do WhatsApp e do
  Telegram. Hoje só as chaves de IA são cifradas (DPAPI); sessões, banco de
  mensagens e mídias ficam em arquivos comuns na pasta de dados, e o código
  secreto das trancadas só as esconde na interface.
- Decisão do responsável: **dizer isso com clareza no guia** (seção
  "Segurança e privacidade dos seus dados": o que sai do computador, o que é
  e o que não é cifrado, BitLocker e conta com senha, o que fazer se perder o
  computador, risco de restrição da conta) e **não aumentar a complexidade
  agora**. Só reabrir se muitas pessoas questionarem ou se acontecer algo.
- Se reabrir, ordem sugerida: sessão do Telegram via DPAPI (custo mínimo);
  SQLCipher no banco de mensagens, medindo antes e depois (faixa típica de 5 a
  15%, não medida aqui); sessão do WhatsApp por último, pois depende da DLL do
  neonize. Mídias ficam de fora (BitLocker cobre).

## Funções do plano original que faltavam (23/10/2026)

Conferido o plano de 13/10 contra o código. Decisões do responsável:

- **Janela de atualização**: está exatamente como planejado.
- **Listas de transmissão**: ficam quietas. Se algumas pessoas pedirem, o
  responsável avalia se implementa.
- **A fazer (vale a pena)**:
  1. **Bloquear e desbloquear contatos**, com uma **lista dos bloqueados**.
  2. **Editar o perfil** (nome, recado e foto), com a alteração indo para os
     dois serviços.
  3. **Ordem das informações**, escolhida pelo usuário, nas mensagens e
     também na lista de conversas ("é algo a ver", ou seja, a estudar o
     desenho antes).
- **Continuam fora**: chamadas de vídeo; assinatura do executável (depende de
  certificado).
- **Viabilidade** (conferida em 23/10/2026): o neonize do venv tem
  `update_blocklist`, `get_blocklist`, `set_profile_name`,
  `set_status_message` e `set_profile_photo`; o Telethon cobre o Telegram
  (`contacts.Block`, `Unblock`, `GetBlocked`, `account.UpdateProfile`,
  `photos.UploadProfilePhoto`). Falta desenhar a interface e testar ao vivo.

### Bloquear e desbloquear (23/10/2026, versão 2026.10.23.1)

- Feito nos dois serviços: `Provedor.bloqueados`, `esta_bloqueado` e `bloquear`; janela "Contatos bloqueados" (menu Contatos) e "Bloquear ou desbloquear" (menu Contatos e menu de contexto da conversa privada). Só pessoas; grupos e canais não.
- Decisões: o item da conversa **inverte o estado atual** (confere o serviço antes e pergunta), em vez de um rótulo que muda, porque o estado só se sabe indo à rede e o menu de contexto não pode esperar; na lista, Desbloquear age direto (Enter também) e Bloquear alguém pergunta antes.
- **Verificado ao vivo pelo responsável (23/10/2026):** "tudo se comportou conforme eu esperava" (dito depois de testar o bloqueio, o perfil e a lista de conversas; ele não detalhou caso a caso, então não se sabe se testou os dois serviços em cada função). Os pontos de atenção abaixo ficam como foram escritos, sem relato de problema.
- Pontos de atenção no WhatsApp (antes do teste): a lista de bloqueio pode guardar o endereço LID (o código compara pelo número e desbloqueia pelo endereço da lista) e o bloqueio por telefone novo usa o JID do número; se o serviço recusar, o erro aparece na fala e numa mensagem.
- Junto veio a correção do voto em enquete do WhatsApp (`EncodeError` do `MessageInfo`, visto no log de 23/10 às 13:27 e 13:27:50). No Telegram não há falha de voto nesse log; o relato do responsável sobre o Telegram por volta das 13h28 não bate com as linhas do log, que são do WhatsApp.

- **Voto em enquete de canal do WhatsApp: adiado (23/10/2026).** O whatsmeow só tem reação e "visto" para canais (conferido em `newsletter.go`), e o neonize não vota; o TeleZapp avisa que não vota e manda votar pelo celular. Implementar exigiria descobrir o formato do voto em canal e mexer na DLL. Só voltar ao assunto se virar demanda.

### Editar o perfil (23/10/2026, versão 2026.10.23.1)

- Feito nos dois serviços: nome, recado e foto (e o sobrenome no Telegram), em Ferramentas, "Editar o meu perfil". Envia só o que mudou e diz o que ficou salvo e o que o serviço recusou.
- Decisões: a foto é preparada pelo TeleZapp (centro em quadrado, 640 px, JPEG) para o responsável poder escolher qualquer imagem; **sem remover a foto** por ora (o neonize não tem e o Telegram pediria outra chamada); o recado do Telegram aceita até 140 no formulário (Premium) e o serviço recusa acima de 70 sem Premium, com a frase explicada.
- **Verificado ao vivo pelo responsável (23/10/2026):** "tudo se comportou conforme eu esperava" (ver a nota do bloqueio acima: ele não detalhou). Pontos de atenção (antes do teste): o `set_profile_name` do neonize grava o nome de exibição (push name) e não confirmei que o WhatsApp o mostra na hora a quem já tem a conversa aberta; ler o recado próprio no WhatsApp depende de `get_user_info` do próprio JID.

### Lista de conversas configurável (23/10/2026, versão 2026.10.23.1)

- A ordem das informações **da mensagem** já existe (estilos em Exibir, "Como cada mensagem é lida"); o que faltava era a **lista de conversas**. Quatro itens: nome da conversa, serviço, quantidade de não lidas e trecho da última mensagem. Cada um liga e desliga, com ordem escolhida pelos botões Mover para cima e para baixo.
- Onde: botão "Lista de conversas" na categoria Interface (valor pendente até OK ou Aplicar, como as outras configurações) e submenu "Lista de conversas" em Exibir (efeito imediato).
- Decisões: pelo menos um item sempre ativado (a tentativa de tirar o último é recusada e falada); **o trecho vem desligado por padrão** (a leitura da lista segue como sempre foi); fixada e silenciada aparecem sempre, depois do serviço (ou do nome); se os itens ativados não têm nada a mostrar numa conversa (sem não lidas e sem trecho, por exemplo), mostra o nome. Trecho: até 80 caracteres, "Você:" nas minhas e o autor nos grupos.
- O trecho vem do banco numa consulta só, em segundo plano, quando o item está ligado, e depois acompanha as mensagens novas, editadas e apagadas.
- **Verificado ao vivo pelo responsável (23/10/2026):** "tudo se comportou conforme eu esperava" (ver a nota do bloqueio acima). Antes disso, a janela de ordem foi aberta com o wx de verdade (sem mostrar) e funciona; falta ver com o leitor de tela e com muitas conversas (o tempo da consulta do trecho num banco grande).

### Arquivar avisa o celular (23/10/2026, versão 2026.10.23.1)

- Arquivar e desarquivar uma conversa do WhatsApp no TeleZapp nunca avisava o
  celular (a fala dizia "só no TeleZapp"; o comentário dizia que a biblioteca
  não deixava). Depois do conserto do `send_app_state` (17/10) fixar,
  silenciar e apagar passaram a avisar, mas arquivar ficou sem código. Agora
  `ProvedorWhatsApp.arquivar_conversa` manda o aviso de estado `archive`
  (coleção `regular_low`, versão 3, `ArchiveChatAction` com a hora da última
  mensagem), pelo mesmo `_enviar_estado`.
- **Verificado ao vivo pelo responsável (23/10/2026):** arquivar no celular já
  chegava ao TeleZapp; arquivar e desarquivar no TeleZapp agora "refletiu no
  celular".

### Ler no celular zera as não lidas (23/10/2026, versão 2026.10.23.1)

- Com a confirmação de leitura ligada, o celular avisa os outros aparelhos com
  um recibo de leitura comum (tipo `READ`) cujo `MessageSource.IsFromMe` é
  verdadeiro, não com `READ_SELF`. `_ao_recibo` descartava esse recibo. Agora
  `READ` e `PLAYED` com `IsFromMe` valem como "li" e "ouvi no celular".
  Descoberto no registro bruto da ponte do WinZapp (36 recibos `read` com o
  próprio identificador como participante).
- **Verificado ao vivo pelo responsável (23/10/2026):** "telezapp marcou como
  lida" depois da correção. O aviso só chega com o aparelho conectado.

### Trancar e destrancar só pelo celular (23/10/2026, versão 2026.10.23.1)

- **Decisão do responsável:** trancar e destrancar é coisa sensível para fazer
  no computador, então só vale pelo celular, no TeleZapp e no WinZapp. No
  TeleZapp a tranca só local "não faz sentido" e saiu: o comando de menu, o
  atalho, a opção da seleção em massa, o item do menu de contexto e
  `Janela._trancar_conversa`. Continua tudo que mostra o que o celular trancou:
  o tipo Trancadas, o código secreto e o aviso `ChatLockEv`
  (celular → TeleZapp, conferido: trancar e destrancar no celular chegam).
  A tranca local de versões anteriores (`trancadas_locais`) é esvaziada ao
  carregar a lista.
- No WinZapp o cofre que o Gabriel fez fica como está (tranca local).
- Descartado: avisar o celular a partir do TeleZapp. O WhatsApp guarda a tranca
  com o código secreto do celular e o aviso `lock` não tem versão conhecida.

### Estado do app sincronizado de tempos em tempos (23/10/2026, versão 2026.10.23.1)

- Pedido do responsável: "melhor sincronizado com algum atraso do que não
  sincronizar". O TeleZapp busca no WhatsApp, a cada 90 s, as coleções
  `regular_low` e `regular_high` (arquivar, fixar, silenciar, favoritar,
  trancar, ler, apagar mensagem); repara sozinho a coleção que sai de
  sincronia e, se o celular não mandar a cópia (o iPhone só manda com o
  WhatsApp aberto na tela), repete o pedido a cada 180 s por cerca de uma hora.
  A ponte do WinZapp busca a cada 60 s e a cada pedido da lista de conversas.
- **Verificado ao vivo pelo responsável (23/10/2026):** com o WhatsApp aberto
  no celular, a conversa arquivada lá se arquivou no TeleZapp; desarquivar no
  TeleZapp chegou ao celular; reproduzir uma voz no celular apareceu como
  ouvida "nos dois apps" (TeleZapp e WinZapp). Áudio ouvido não está no estado
  do app: chega como recibo ao vivo (o servidor entrega os acumulados ao
  reconectar), por isso não entra na busca periódica.

### IA para redigir, resumir e corrigir (23/10/2026, versão 2026.10.23.1)

- Pedido do responsável como último tema do dia, com a regra de que o que levasse muito tempo ficaria para a próxima versão. Feito o núcleo: corrigir e redigir na caixa, resumir mensagem e conversa. Reaproveita provedores, chaves, ordem e modelos da IA de mídia, como tarefa nova. Decisões: redigir nunca envia (só rascunho na caixa, Control Z volta); consentimento de texto separado do de mídia; o texto da conversa é tratado como dado (não como instrução ao modelo).
- Mesmo dia, segunda rodada a pedido do responsável: tom (opção `ia_tom` e item para escolher na hora), tradução (caixa e mensagem, seis idiomas) e resumo das não lidas, este só disparado manualmente.
- **Não feito / a decidir:** resumo automático, mais idiomas, ligar a redação ao atalho de enviar. **Não verificado com provedor real nem ao vivo.**

### Digitar numa lista (23/10/2026, versão 2026.10.23.1)

- Pedido do responsável: manter o pulo por inicial e permitir, por opção, ir direto ao campo de texto vizinho (caixa de mensagem; busca de conversas). Padrão: pular. **Não verificado ao vivo:** o EVT_CHAR de ListBox/ListCtrl no Windows e o foco com o leitor de tela.

### Dispositivos de som (23/10/2026, versão 2026.10.23.1)

- Pedido do responsável: um slot de atalho para definir o dispositivo de som.
  Escopo escolhido por ele: tudo (tocar, gravar e chamadas). Uma janela única,
  "Dispositivos de som", com Saída de som e Microfone, "Padrão do Windows"
  primeiro; o item de Mídias nasce sem combinação de teclas.
- A escolha usa as mesmas chaves das chamadas (`chamada_microfone`,
  `chamada_saida`) para ter uma só fonte. Nomes são comparados por prefixo
  porque a API de som padrão do Windows corta os nomes; dispositivo que sumiu
  cai no padrão em silêncio. O som do computador captura a saída escolhida.
- **Não verificado ao vivo:** ouvir um áudio, gravar e ligar com outro
  dispositivo; só os testes automáticos (sounddevice falso) e a listagem real
  da máquina (um microfone, uma saída).

### Gravar o som do computador com o microfone (23/10/2026, versão 2026.10.23.1)

- Pedido de usuários, esclarecido pelo responsável: a gravação do computador
  deve poder levar também o microfone. Janela "Gravar o som do computador"
  com a caixa "Gravar também o microfone" (padrão ligado, opção em
  Configurações, Mídias), ligável e desligável durante a gravação; atalho novo
  `gravar_som_mic` (Ctrl+Shift+B) para a gravação rápida dos dois. O
  Ctrl+Shift+S continua só com o som. Sem microfone: grava só o som e avisa.
- **Verificado ao vivo pelo responsável (23/10/2026):** gravação do som do
  computador com o microfone, pela janela e pelo atalho Control Shift B:
  "tudo uma maravilha".

### "Não avisar mais nesta versão" (23/10/2026, versão 2026.10.23.1)

- Pedido do responsável: depois do Não na janela de versão nova, uma pergunta
  separada, em vez de uma caixa de verificação na janela; a janela continua
  como era. Os botões da pergunta têm frases próprias (não "Sim" e "Não", que
  confundiam): "Não me avise mais sobre essa versão" (não avisa mais dessa
  versão ao abrir, só quando sair outra) e "Talvez mais tarde", o padrão (avisa
  de novo na próxima abertura). O aviso automático deixou de
  ser "uma vez por versão": passa a ser a cada abertura, até atualizar ou
  responder Sim. Guarda `atualizacao_ignorada` (a versão).
- Primeira versão, com uma caixa de verificação na janela, foi testada ao vivo
  com um lançador que finge a versão 2099.1.1.0 e depois trocada pela pergunta,
  como o responsável queria. **A pergunta ainda não foi vista ao vivo.**

### Banco de dados corrompido e recuperado (23/10/2026)

- Ao abrir uma cópia de teste, o TeleZapp não iniciou: `database disk image is
  malformed` em `telezapp.db` (páginas referenciadas duas vezes, linhas fora
  de ordem). Causa não provada; havia dois processos do TeleZapp abertos ao
  mesmo tempo mais cedo e registros de quedas anteriores.
- Recuperado lendo as linhas legíveis para um banco novo (integridade `ok`):
  106.584 mensagens (o índice do banco ruim dizia 109.152), 354 conversas (58
  linhas de conversa recriadas a partir das mensagens, com o nome vindo dos
  contatos), todos os recibos, contatos, status e apagadas; índice de mídias
  2.002 de 2.179. Trocado com o consentimento do responsável. Cópias do
  original ficam em `%APPDATA%\TeleZapp`: `telezapp.db.corrompido-20261023` e
  `telezapp.db.antes-da-troca` (podem ser apagadas depois de alguns dias).

## Chamadas de voz do WhatsApp: fase 0 (21/10/2026)

- Experimento em `experimentos/10-chamada-whatsapp-meowcaller/` (Go, meowcaller sobre o hypermeow) com a ponte de voz em Python (`experimentos/chamada_whatsapp.py`, microfone e alto-falante por socket local). Ainda fora do app.
- **Verificado ao vivo pelo responsável (21/10/2026, 20:38):** ligação de saída de 60 s para um celular, atendida e com "voz boa nos dois lados". Codec MLow, memória do Go entre 11 e 21 MB. Houve 111 quedas de som no resumo (concentradas no meio e no fim da chamada): a investigar.
- **Verificado ao vivo pelo responsável (21/10/2026, 21:12), com o whatsmeow do neonize:** o meowcaller, copiado com o import do hypermeow trocado por `go.mau.fi/whatsmeow` (pin `35ae40906e74`, o mesmo da DLL do neonize), compila (build, vet e testes) e fez uma ligação de saída de 50 s com "voz boa nos dois lados" (837 quadros enviados, 658 recebidos, memória do Go 15 a 25 MB). Não é preciso trocar de motor de conexão. Requisito do responsável: um único pareamento para mensagens e chamadas, então a integração será na própria DLL.
- **Verificado ao vivo pelo responsável (21/10/2026, à noite), no TeleZapp do código:** chamada de voz **feita** pelo app, com a opção "Chamadas de voz do WhatsApp (experimental)" ligada e a DLL com o meowcaller dentro (um só login), "com sucesso e qualidade". Também visto: **atender** uma chamada recebida (boa qualidade) e **recusar** (a pessoa viu "recusado"; antes da correção da DLL, que passou a usar `Reject` no lugar de `Hangup` para chamada de entrada ainda tocando, a chamada seguia tocando nos dois lados). O celular da conta seguiu tocando depois de recusar no TeleZapp, o que o responsável diz acontecer às vezes até no WhatsApp oficial: observar. Também visto: **silenciar** o microfone. Com a DLL reconstruída (a mesma das chamadas), **arquivar uma conversa no celular chegou ao vivo** ao TeleZapp. **Trancar** uma conversa no celular também chegou ao vivo; destrancar pelo TeleZapp não destrancou no celular (não se sabe se antes destrancava; o responsável aceitou assim). Não verificado no app: trocar microfone ou saída no meio (o responsável só tem um de cada, só há teste automático); trocar microfone ou saída no meio; chamada longa; vídeo e grupos.
- **Não verificado:** receber chamada, vídeo, grupos, chamada longa, o reaproveitamento do mesmo cliente da DLL (o teste usou um cliente whatsmeow próprio, com sessão separada) e a troca automática de código de pareamento quando digitado errado.

## Corretor ortográfico (22/10/2026)

- F7 na caixa de digitar (menu Mensagens): verificador do próprio Windows por ctypes, sem dependência nova; janela com palavra, frase, "Trocar por", sugestões e botões Trocar, Trocar todas, Ignorar, Ignorar todas e Adicionar ao dicionário (dicionário pessoal do Windows). Opções na categoria Escrita: idioma do corretor e aviso ao enviar (desligado por padrão).
- **Verificado ao vivo pelo responsável (22/10/2026):** ele usou o corretor no TeleZapp do código e disse que gostou da função. Testado só em português do Brasil. Testado com o NVDA, sem dificuldade em nenhuma das telas. Também testado o aviso de ortografia incorreta ao enviar. Não foram testados os outros idiomas.

- **Enter da caixa (22/10/2026):** a caixa passou a ter `TE_PROCESS_ENTER` e envia pelo `EVT_TEXT_ENTER`, como o WinZapp (o Enter chega ao controle e o leitor de tela fecha a última palavra). Sai a opção experimental `enter_chega_ao_leitor`. **Verificado ao vivo pelo responsável (22/10/2026):** parou de falar a última palavra colada com a primeira da mensagem seguinte. Foi o envio comum de mensagem, que era o principal. Shift+Enter, a edição (F2) e a resposta de status ficam só com teste automático.

## Enquetes (22/10/2026)

- Ver, votar e criar enquetes no WhatsApp e no Telegram (dados em `extras["enquete"]` da mensagem; janelas `interface/enquete.py` e `interface/nova_enquete.py`).
- **Verificado ao vivo pelo responsável (22/10/2026), no WhatsApp:** criou uma enquete pelo TeleZapp, outras pessoas votaram e os resultados atualizaram na enquete criada por ele (depois de consertar o `decrypt_poll_vote` do neonize 0.5.2, que dava TypeError); um voto dado **com o TeleZapp fechado** chegou quando ele abriu. Entrou também com outra conta no TeleZapp e a enquete chegou e funcionou como enquete recebida. No Telegram só tentou criar. Não verificado: votar e ver quem votou no Telegram.

- **Envio de áudio que não é gravação direta (22/10/2026, corrigido em 23/10/2026):** encaminhar uma voz e colar um `.ogg` apareciam como enviados e nunca chegavam. O log mostrava `audio enviado` com o tipo `audio/ogg` sem `codecs=opus`; agora o Ogg com Opus vai como áudio comum com `audio/ogg; codecs=opus`, Ogg Vorbis vai como documento e encaminhar uma voz que não é Ogg/Opus segue como arquivo. **Verificado ao vivo pelo responsável (23/10/2026):** "me parece que o envio e o encaminhamento de áudio funcionou". Não se sabe quais casos ele testou além de encaminhar e colar; não verificado: Ogg Vorbis, M4A e MP3 como áudio comum.

- **Verificado ao vivo pelo responsável (23/10/2026):** navegou pelo menu reorganizado (Novo, Ir para, Ferramentas) e pela janela de configurações nova (Interface, Mensagens e o botão Conteúdo falado), sem relatar problema. O arquivo de áudio que não chegava em 22/10 foi reenviado e **chegou ao destino como áudio**. Outros formatos (Ogg Vorbis, M4A, MP3) ele só vai testar numa oportunidade ou se um usuário relatar. **Não verificado:** criar grupo, canal e comunidade (WhatsApp e Telegram), tópicos de grupo do Telegram, Nova chamada, Novo contato e as credenciais do Telegram embutidas no executável (ainda não empacotado).

- **Formulário de relatos (23/10/2026):** `site/relatar.html` envia para o Worker `telezapp-relatos` (pasta `relatos/`, KV, relatos guardados 90 dias, leitura em `/admin` com senha, aviso por notificação do ntfy). **Verificado ao vivo pelo responsável (23/10/2026):** um relato de teste mandado direto ao Worker apareceu na lista do `/admin` e a notificação chegou ao celular. A página foi publicada (PR #25) e o envio por ela, com um log anexado, chegou ao Worker (visto por mim com um relato de teste, depois apagado); o responsável confirmou em 23/10/2026 que "tudo funcionou na página de relatos". O endereço do `/admin` com a senha ficou guardado por ele fora da pasta do projeto.

## Versão 2026.10.24.1 (24/10/2026): ferramentas de grupo do WhatsApp

- Pedido do responsável: o que o WinZapp tem em grupos e o TeleZapp não tem, feito em paralelo ("se foi possível para o TeleZapp deve ser possível para o WinZapp"). Auditoria primeiro: o TeleZapp já tinha detalhes, membros, promover/rebaixar/remover/adicionar por telefone, nome, descrição, só administradores enviam/editam, link (numa caixa de mensagem), sair, grupos em comum, criar grupo/comunidade e entrar pelo botão da mensagem. Faltavam: pedidos de entrada (listar, aprovar, recusar), foto do grupo (ver e trocar), convite com QR Code, entrar por link digitado e adicionar uma pessoa a um grupo pela conversa dela. Todos feitos. O TeleZapp não mostrava nenhuma foto de perfil, só trocava a própria.
- Não viável hoje: modo de aprovação de entrada e "só administradores adicionam membros" (o `GroupInfo` do neonize não tem os campos nem há função que os mude; exigem mexer na DLL); remover a foto do grupo (o neonize não documenta foto vazia; não tentado).
- Aprovar e recusar usam `client.update_group_request_participants`, só existente na DLL de teste `0.5.2-winzapp-teste.2` (contrato combinado com a sessão que a recompila). Sem a função, a mensagem diz que precisa da DLL de teste nova; a lista de pedidos funciona com o neonize atual. **Correção (24/10/2026):** o pacote da Release 2026.10.24.1 leva a DLL nova (o empacotador copia o neonize do `venv`; conferido no `TeleZapp.zip`: SHA-256 `51f845e3…`, com a função), então aprovar e recusar funcionam para quem baixa o exe; o aviso só aparece rodando pelo código-fonte com o neonize oficial. A primeira versão das notas da Release e das novidades dizia o contrário.
- Sem opção nova em `config.OPCOES` (nada ajustável); o item de menu "Entrar em um grupo por link" nasce sem combinação de teclas.
- **Não verificado ao vivo:** nada disto foi visto com conta real, só testes automáticos com cliente simulado. A conferir: a foto baixar e abrir; trocar a foto do grupo; o QR salvo ser lido pelo celular; o pedido de entrada aparecer com nome e telefone e, com a DLL nova, aprovar e recusar.

## Próximos passos sugeridos

1. ~~Grupo 1 do plano acima~~ (concluído).
2. ~~Etapa 3b: enviar arquivos e gravar nota de voz~~ (implementada na
   2026.10.14.16; falta testar no WhatsApp e no Telegram reais, e as
   pendências da seção acima, exceto a velocidade do áudio, já feita).
3. ~~Adicionar o aviso de licença nos arquivos~~ (SPDX presente em todos os
   `.py` do pacote); conferir ainda as licenças de terceiros pendentes.
4. Etapa 4 (ver o plano). ~~Janela de configurações~~ (2026.10.15.2),
   ~~sons de eventos~~ e ~~backup e restauração~~ (2026.10.18.0). Falta:
   ordem das informações da mensagem, instalador, portátil, desinstalação
   limpa, atualização com janela de novidades e assinatura.
   Distribuição (2026-10-18): um só zip por versão nas Releases do GitHub,
   montado por `ferramentas/publicar.py` (pré-lançamento, aviso de software
   experimental) e checagem de versão nova em Ajuda (feita, só avisa).
   Falta: instalar e criar cópia portátil dentro do app (como o NVDA),
   atualizador que troca a pasta com conferência do hash, assinatura.
5. Testes de estabilidade e de arquivos maiores. Visto pelo responsável em
   19/10/2026: download de um arquivo de quase 600 MB recebido pelo WhatsApp,
   com comportamento satisfatório; e envios repetidos, pelo WhatsApp, do zip
   do TeleZapp (cerca de 70 MB), também sem problemas. Falta testar arquivos
   maiores (o neonize baixa o arquivo inteiro na memória) e envios na
   casa de 1 GB.
6. Testar no app real o que entrou em 19/10 (lista na seção da
   versão 2026.10.19.0), gerar o executável com as dependências
   novas e conferir as licenças do OpenCV (FFmpeg, LGPL) e do
   `emoji`.

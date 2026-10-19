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
7. **Chamadas**: fora do escopo no WhatsApp. O neonize só avisa e recusa; uma
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
- **Pendências**: citar a mensagem respondida ao enviar mídia; progresso do
  envio de arquivos grandes (hoje só "enviando"); escolher microfone e saída
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
- **Sons**: 16 eventos, cada um com som padrão, sem som ou arquivo na pasta
  `sons` (dentro da pasta de dados, no backup). Eventos novos acompanham o
  som do evento parecido enquanto não têm escolha própria.
- **Backup e restauração**: .zip com senha opcional (AES-256 por `pyzipper`);
  partes escolhidas; configurações valem na hora e o resto troca na próxima
  abertura, guardando o anterior em `antes-da-restauracao`. Depuração e
  exigência do código secreto nunca são restauradas por arquivo. As chaves de
  IA nunca entram.
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
  Chaves cifradas pelo DPAPI do Windows, fora de backup e log; consentimento
  por provedor antes do primeiro envio. Modelos padrão vieram do catálogo do
  WinZapp (Gemini 3.8 Flash entra no gratuito; Gemini tem modo automático com
  alternativos). Aprendizados: a Groq (Cloudflare) devolve 403, erro 1010, ao
  User-Agent do Python, e a OpenAI devolve 429 `insufficient_quota` sem
  saldo; ambos pareciam "chave recusada". O Enter em mídia é configurável
  (abrir, baixar ou usar a IA). Fica para depois: modo automático por
  conversa, vídeo fora do Gemini (quadros), arquivos acima de 14 MB e
  perguntas de acompanhamento.
- **Chamadas do WhatsApp (pesquisa, em espera)**: o neonize só tem a
  sinalização. O WhatsApp Web ganhou chamadas (jul/2026) e o WA-JS aciona a
  pilha de VoIP dele; o WinZapp já faz chamadas assim (WPPConnect + Chrome,
  áudio ligado ao Python). Plano proposto, não iniciado: experimento (Playwright
  + Edge + WA-JS, pareamento por código como segundo aparelho, medir tempo e
  memória), opcional e desligado por padrão, sem trocar o acesso atual às
  mensagens pelo WPPConnect. O responsável deixou o assunto de lado.

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
5. Testes de estabilidade e de arquivos maiores.

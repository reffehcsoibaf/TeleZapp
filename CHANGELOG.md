# Registro técnico de mudanças

Para o usuário, veja `telezapp/ajuda/novidades.html`. Versões no formato
`ano.mês.dia.dígito`. Mais novas primeiro.

## 2026.10.15.5

Chamadas de voz 1 a 1 no Telegram (interface acessível).

- `nucleo/chamadas.py` (sem wx): estados (`CHAMANDO`, `TOCANDO`,
  `CONECTANDO`, `EM_CHAMADA`, `ENCERRADA`), motivos de encerramento,
  `Chamada` (com o tempo em chamada), `apresentar` (título, texto, fala,
  botões visíveis em ordem de Tab, foco e som de cada estado),
  `motivo_da_excecao` e as durações para mostrar e para falar.
- `provedores/chamadas_telegram.py`: `ChamadasTelegram`, sobre o py-tgcalls
  3.x (NTgCalls), na thread e no cliente Telethon do provedor. Liga, atende,
  recusa, desliga, silencia e troca microfone e saída de som no meio da
  chamada; recusa sozinha uma segunda chamada recebida. Sem o py-tgcalls as
  chamadas ficam desligadas e nada mais muda (`suporta_chamadas` falso).
  Microfone e saída são os do Windows, vistos pela NTgCalls, sem FFmpeg.
- `Provedor`: `ligar`, `atender_chamada`, `encerrar_chamada`,
  `silenciar_chamada`, `trocar_dispositivos`, `dispositivos_de_audio` e
  `suporta_chamadas`. Evento novo `EstadoChamada`.
- `interface/chamada.py`: `DialogoChamada`, uma janela só que muda de estado.
  Foco em Atender ao tocar e em Desligar nos outros estados; Esc recusa ou
  cancela, mas não desliga uma chamada já conectada.
- Janela principal: menu Chamada (Ligar Ctrl+Shift+L, Janela da chamada
  Ctrl+Shift+J, Silenciar Ctrl+Shift+K, Tempo, Desligar Ctrl+Shift+H);
  pergunta antes de fechar o TeleZapp com uma chamada aberta. Opção "Som de
  chamada" (`toque_chamada`) e dispositivos guardados em `chamada_microfone`
  e `chamada_saida`. Sons novos: `toque`, `chamando`, `desligada`.
- **Cuidado com o COM**: listar microfones e saídas pela NTgCalls na thread
  da interface derruba o processo (o wx inicia o COM no modo dele). Os
  nomes são listados só na thread do provedor (`atualizar_dispositivos`) e
  `dispositivos()` devolve o cache. Reproduzido fora do app com um
  `wx.App` e corrigido com uma thread separada.
- `__main__`: `faulthandler` grava em `logs\\falha-nativa.log` onde cada
  thread estava quando uma biblioteca nativa derruba o processo.
- Só conversas privadas do Telegram. Não há aviso de chamada perdida na
  conversa, nem vídeo, nem chamada pelo WhatsApp.
- Testado com um py-tgcalls simulado e com a janela simulada; chamada real
  de saída de 45 s medida no experimento 9 (docs/decisoes.md). **Não
  verificado**: chamada recebida, leitura pelo NVDA da janela da chamada,
  troca de dispositivo no meio da chamada e quedas de rede.

## 2026.10.15.4

- Grupo renomeado com o TeleZapp fechado (ou sem receber o aviso) continuava
  com o nome antigo: o aviso da 2026.10.15.3 só vale ao vivo. Agora o WhatsApp
  é consultado (`get_joined_groups`) no fim da sincronia ao conectar e a cada
  atualização manual das conversas (`_atualizar_nomes_de_grupos`), e os grupos
  com nome diferente são corrigidos. Grupos sem conversa local são ignorados.
  O Telegram já refazia os nomes ao conectar.
- Não verificado com um WhatsApp real: depende de `get_joined_groups` trazer
  o nome atual de todos os grupos.

## 2026.10.15.3

- Grupo renomeado não aparecia no TeleZapp: o nome só era buscado enquanto
  estava como "Grupo". WhatsApp: passa a ouvir `GroupInfoEv` (campo `Name`)
  e `JoinedGroupEv` (`GroupInfo.GroupName`, reenviado ao entrar/reconectar) e
  troca o nome da conversa já conhecida (`_renomear_grupo`). Telegram: passa a
  ouvir `events.ChatAction` e usa `new_title`. A janela atualiza o rótulo
  "Mensagens de ..." e o título quando a conversa aberta muda de nome.
- Só vale para mudanças que acontecerem com o TeleZapp aberto (ou que o
  WhatsApp reenviar ao reconectar). Não verificado com um WhatsApp real: os
  campos foram conferidos nas definições do neonize, e a entrega do evento
  `GroupInfoEv` depende do servidor.

## 2026.10.15.2

Janela de configurações (etapa 4).

- `nucleo/configuracoes.py`: `ModeloConfiguracoes`, sem wx: categorias (com
  "Avançado" por último), busca por `config.buscar_opcoes`, valores
  pendentes (voltar ao valor atual desfaz) e `aplicar`, que entrega as
  mudanças na ordem de `config.OPCOES` (o passo da velocidade antes da
  velocidade).
- `interface/configuracoes.py`: `DialogoConfiguracoes`. Busca no alto,
  categorias numa lista vertical, opções da categoria como CheckBox ou
  Choice; a descrição é falada pelo programa 0,4 s depois do foco (F1
  repete; a opção `falar_descricoes`, padrão ligada, desliga a fala
  automática), e não é um texto da janela: o NVDA lê todos os textos fixos ao
  abrir a janela. `wx.Accessible` foi tentado e derrubou o processo. OK,
  Cancelar e Aplicar. Com
  busca, a categoria "Resultados da busca" aparece primeiro.
- Janela principal: Menu, Configurações... (Ctrl+,). `_aplicar_opcao` usa os
  mesmos efeitos e avisos falados dos menus e mantém os itens de menu
  marcados. Os menus de hoje continuam.
- Cobre só as opções que já existem em `config.OPCOES`; sons de eventos,
  backup e ordem das informações entram nas próximas versões.
- Não verificado com leitor de tela: a ordem de Tab e a leitura dos
  controles foram conferidas só por teste de fumaça com o wx real.

## 2026.10.15.1

Velocidade do áudio.

- `midia/velocidade.py`: escala de 0,25x a 3x, em passos de 0,25, 0,5 ou 1
  (`valores`, `ajustar`, `proxima`, `rotulo`) e `Esticador` (WSOLA em numpy:
  trechos de 32 ms, corte escolhido por correlação normalizada; muda o
  tempo sem mudar o tom). Custo de ~1% de CPU; medido só com senoides e a
  amostra de voz, sem ouvido humano.
- `Reprodutor.velocidade`: 1,0 lê direto do arquivo; outro valor passa pelo
  esticador, vale na hora (tocando ou não); posição, `ir_para` e fim de
  arquivo acompanham. No MediaCtrl (vídeo, m4a) usa `SetPlaybackRate`, e o
  tom pode acompanhar.
- Opções `audio_passo_velocidade` (0,25 / 0,5 / 1) e `audio_velocidade`
  (padrão 1x); trocar o passo leva a velocidade ao valor mais próximo
  permitido.
- Janela: Menu, Mídias, Áudio mais rápido (Ctrl+Shift+Up), mais lento
  (Ctrl+Shift+Down), Velocidade normal (Ctrl+Shift+0), Velocidade do áudio...
  e Passo da velocidade do áudio... Vale também para o áudio que já está
  tocando. No player: botões Mais rápido e Mais lento e as teclas + e -.
- A velocidade é única (vale para todos os áudios) e fica entre sessões.

## 2026.10.15.0

Links e botões de endereço pelo Tab.

- `modelos.itens_de_link(msg)`: links do texto ou da legenda (e os escondidos
  em `extras.links`) mais os botões de endereço do Telegram (`extras.botoes`),
  só http/https, sem repetir endereço. Rótulos "Link: ..." e "Botão: ...".
- Janela: até 12 `wx.Button` (`botoes_link`) criados logo depois dos botões
  de resposta, na ordem de Tab; aparecem para a mensagem selecionada, em
  qualquer tipo (texto, foto, vídeo, áudio, documento). Enter no botão abre
  no navegador (`dialogos.abrir_link`) e fala "Abrindo no navegador.".
  `_atualizar_botoes` agora considera ações e links na mesma chave.
- `formatar`: "com N links (Tab)" para qualquer tipo (antes só mídia, "com
  link (Enter)"). A lista de links dos detalhes segue existindo, inclusive
  para além dos 12 botões.
- Enter na lista de mensagens: mídia (inclusive com link na legenda) abre a
  mídia; mensagem só de texto abre `dialogos.mostrar_mensagem` (texto somente
  leitura, Copiar texto e Fechar; Esc fecha). Os detalhes ficam só em Alt
  Enter (e no menu Mensagem). `_copiar_texto` é comum a Control Shift C e à
  caixa. Mensagem local ainda "enviando" continua abrindo os detalhes.
- Não verificado com o NVDA.

## 2026.10.14.16

Etapa 3b: enviar arquivos e gravar nota de voz.

- `midia/gravador.py`: `Gravador` (iniciar/parar/cancelar) com duas fontes.
  Microfone: sounddevice, mono, 48 kHz (ou a taxa padrão, reamostrada).
  Som interno: loopback do WASAPI pela `soundcard` (a sounddevice do Windows
  não tem loopback), downmix para mono. A fonte abre dentro da thread da
  gravação (COM e PortAudio numa thread só). Grava em WAV temporário e, ao
  parar, converte em blocos para Ogg/Opus 48 kHz mono. Sem limite de memória;
  `maximo_segundos` para sozinho. Medida: saída muda < -50 dBFS é avisada.
- `midia/envio.py`: `preparar` devolve `Anexo` (tipo, MIME, duração,
  dimensões, tamanho). MP4/MOV pelo leitor próprio (`mp4.ler`), HEVC avisa,
  MKV/AVI/BMP/HEIC/GIF vão como documento, limite de 2 GB, voz exige Ogg/Opus.
- `Provedor.enviar_arquivo(conversa_id, anexo, legenda)`. WhatsApp: foto e
  documento pelo neonize; vídeo e áudio/voz montados à mão com `upload`
  (como nos experimentos); roda numa thread própria para o upload não travar
  a fila de texto. Telegram: `send_file` (voz com `DocumentAttributeAudio`,
  vídeo com `DocumentAttributeVideo`). O arquivo enviado é copiado para o
  armazém da conversa (gravações temporárias são movidas) e registrado em
  `midias`, para abrir sem baixar. `_registrar_enviada` é o trecho comum de
  `_enviar` no WhatsApp e no Telegram.
- `EnvioFalhou.tipo`: a janela casa a mensagem local "enviando" pelo texto e
  pelo tipo (numa mídia, aceita outro tipo de mídia se o serviço classificar
  diferente).
- Janela: botões Anexar arquivo, Gravar do microfone e Gravar som do
  computador depois de Enviar (sem tecla de acesso: Alt abre o Menu); itens
  em Menu, Mídias (Ctrl+Shift+A, M, S). O texto da caixa vira legenda de
  foto, vídeo e documento. `dialogos.gravar_voz`: grava ao abrir, Parar,
  Ouvir, Enviar, Gravar de novo, Descartar (Esc).
- Mídia enviada não cita a mensagem respondida (a resposta continua
  pendente para o próximo texto). NÃO verificado no WhatsApp/Telegram reais:
  só testes com clientes simulados; o loopback foi verificado no computador
  de desenvolvimento (tom de 440 Hz tocado e recuperado a 440 Hz).
- Dependências novas: soundcard, numpy (já vinha com o neonize).

## 2026.10.14.15

- Botões de resposta viram controles de verdade (`wx.Button`, até 12, criados
  logo depois da lista de mensagens para ficarem na ordem de Tab). Aparecem só
  quando a mensagem selecionada tem botões/opções (`_atualizar_botoes`, chamado
  ao mudar a seleção e ao refazer a lista); o foco só é movido se o botão
  focado deixar de existir. A linha da mensagem ganha "com N botões (Tab)".
- Sem janela de confirmação, também no caminho pelos Detalhes. O resultado é
  falado quando chega: "Enviado: X" (a resposta aparece na conversa) ou o aviso
  de falha de sempre (`_acoes_enviadas` casa conta, conversa e rótulo).
- Variante EXPERIMENTAL tentada antes das outras para `buttonsMessage`: a
  resposta vai dentro de `documentWithCaptionMessage`. Motivo: o pacote do
  celular, como o servidor o repassou (log DEBUG de 20:29), traz `<biz>` vazio,
  sem o filho `<buttons_response/>` que o whatsmeow acrescenta ao nosso, e o
  servidor preserva filhos do `<biz>` em outras mensagens (`<buttons/>`,
  `<interactive>`). O whatsmeow só olha dentro de ViewOnce/ViewOnceV2/Ephemeral.
  NÃO verificado: se o servidor aceita, se o tipo/mediatype calculado muda e se
  a empresa entende a resposta embrulhada. O log nomeia a variante aceita.

## 2026.10.14.14

- Teste real: modelo (`templateButtonReplyMessage`) foi aceito e entendido;
  `buttonsResponseMessage` foi recusado com 479 nas três variantes, mesmo
  citando a mensagem inteira. Como o conteúdo vai criptografado, a recusa é do
  pacote (stanza), possivelmente do nó `<biz><buttons_response/>` que o
  whatsmeow acrescenta. Para ver os pacotes: opção "Registro técnico detalhado
  do WhatsApp" (menu Depurar, vale na próxima abertura), que põe o lado em Go
  em nível DEBUG (`_ligar_log_detalhado`).

## 2026.10.14.13

- Resposta de botão: o servidor devolveu 479 (formato recusado) ao enviar um
  `buttonsResponseMessage` citando só o texto. O celular cita a mensagem
  inteira (`quotedMessage.buttonsMessage` com os botões), responde na conversa
  LID e inclui `messageSecret`. Agora a mensagem com botões guarda
  `extras.original` (JSON sem miniaturas) e a resposta tenta, nesta ordem,
  "como o celular (conversa LID)", "citando a mensagem inteira" e "citação
  simples", passando à seguinte só se o erro for 479. O log diz qual variante
  foi aceita ou recusada. Só vale para mensagens que chegarem depois desta
  versão (as antigas só têm a citação simples).

## 2026.10.14.12

- Log de envio falhado agora traz o tipo, a mensagem e o traceback do erro e,
  nas respostas de botão, o tipo/id/índice do botão ("resposta de botão: ...").

## 2026.10.14.11

PR #12: menu Depurar.

- `nucleo/depuracao.py`: `texto_mensagem` e `texto_conversa`.
- Tabela `depuracao` (esquema 7) e `Banco.depuracao` (modo, `config.depuracao`,
  padrão desligado): `guardar_depuracao` mantém as 500 mais recentes;
  desligar apaga (`limpar_depuracao`).
- WhatsApp: `estrutura_bruta` (sem miniaturas nem chaves de mídia) guardada
  no caminho ao vivo e no histórico; `depurar_conversa` mostra como o nome foi
  achado. Telegram ainda sem estrutura original.
- Janela: menu Depurar (mensagem Ctrl+Shift+D, conversa, modo);
  `dialogos.mostrar_depuracao` com Copiar tudo e Salvar em arquivo
  (`config.pasta_depuracao`: C:\logs no Windows).
- `estrutura_interativa` passou a usar `_limpar`, compartilhado.

## 2026.10.14.10

PR #11: tocar nos botões de resposta e nas listas do WhatsApp.

- `extras.acoes`: `acoes_do_whatsapp` guarda botões de resposta rápida de
  modelo (`modelo`), `buttonsMessage` (`botoes`), `quick_reply` de mensagem
  interativa (`fluxo`) e linhas de `listMessage` (`lista`).
- `Provedor.responder_acao(msg, acao)`; WhatsApp monta
  `templateButtonReplyMessage` (selectedID/DisplayText/Index),
  `buttonsResponseMessage`, `listResponseMessage` ou
  `interactiveResponseMessage`, citando a mensagem original.
- Janela de detalhes: lista "Botões de resposta e opções"; Enter confirma
  ("Enviar o botão ... para ...?") e envia. `EnvioFalhou.devolver_texto`
  evita devolver o rótulo do botão à caixa de digitação.
- Não verificado no WhatsApp real: só o modelo de resposta rápida tem dados
  reais no log; `fluxo`, `lista` e `botoes` seguem o protocolo, sem teste real.
  Ainda sem toque: `single_select` do fluxo nativo, pagamento, ligar.

## 2026.10.14.9

PR #10: nome verificado de empresas.

- `_consultar_empresas`: o whatsmeow grava o nome verificado (`BusinessName`)
  no armazenamento de contatos ao rodar `get_user_info`, mas não o devolve em
  `UserInfo.VerifiedName`. Agora, depois da consulta, lê-se
  `contact.get_contact(jid).BusinessName`. O log "consulta de empresa" mostra
  quantas conversas tiveram nome.

## 2026.10.14.8

PR #9: links escondidos, botões de link e menções.

- `Mensagem.extras` (JSON: `links`, `botoes`, `mencoes`) e coluna `extras` no
  banco, esquema 6 (migração automática).
- Foto, vídeo, áudio e documento com link na legenda: a linha diz "com link
  (Enter)", o Enter abre os detalhes com os links e Ctrl+O abre a mídia (`tem_links`).
- WhatsApp: nome de conversa nunca é o código interno. `_nome_contato` resolve
  LID→número, tenta agenda > perfil > nome de empresa > telefone e, sem nada,
  "Contato sem nome" (`parece_codigo`, `SEM_NOME`). Conversas já guardadas com
  código são renomeadas na próxima mensagem. Canais (`newsletter`) viram
  conversa do tipo `canal`, com o nome vindo de `get_newsletter_info`.
- Detalhes da mensagem: recibos (entregue/lida) mostram o nome de quem recebeu
  (`Provedor.nome_de_participante`; WhatsApp usa `_nome_contato`), senão
  "+telefone" ou "Contato sem nome", nunca o JID.
- WhatsApp, mensagens de empresa: `texto_estruturado` lê botões, modelos,
  interativas (header/body/footer), listas, respostas a botões e pedidos como
  texto; `botoes_do_whatsapp` extrai botões de link (modelo e `cta_url`).
  Tipo não reconhecido continua `OUTRO`, mas o texto traz o nome do campo
  ("tipo do WhatsApp: ...") e vai para o log. Nome verificado da empresa
  (`nome_verificado`) vira nome da conversa/autor; conversas só com telefone
  tentam de novo a cada mensagem.
- WhatsApp: mensagem interativa sem texto (ex.: `payment_info`) vira "mensagem
  interativa: solicitação de pagamento"; a primeira mensagem ao vivo de uma
  conversa só com telefone grava se o perfil e o nome verificado vieram.
- Registro: a primeira linha de cada execução traz a versão e a pasta do código,
  para sabermos qual compilação gerou o log.
- WhatsApp, pelo diagnóstico do Fábio: fotos/vídeos de álbum (`associatedChildMessage`)
  e comentários (`commentMessage`) passam a aparecer (envelopes); cabeçalho
  de álbum, aviso de grupo mencionado em status e aviso de histórico são
  ignorados (controle); convite de grupo vira "convite para o grupo: nome";
  botões e opções de lista aparecem no texto ("Botões: ...", "Opções: ...").
  A consulta de nome de empresa agora também roda em lote para as conversas
  do histórico que só têm telefone (`_consultar_empresas`).
- WhatsApp: mensagens de empresa com botões/lista gravam no log o formato
  (`estrutura_interativa`, linha "mensagem interativa: ..."), sem imagens nem
  textos longos, para implementarmos o toque nos botões com dados reais.
- WhatsApp: conversa só com telefone consulta `get_user_info` (na fila) e usa
  o nome verificado da empresa, se vier; o resultado da consulta vai para o
  log ("consulta de empresa para ...").
- WhatsApp, conversa privada: remetente sem nome de perfil usa o nome da
  conversa como autor (antes: "Desconhecido").
- Telegram: entidades `MessageEntityTextUrl`/`Url` (posições em UTF-16),
  `Mention` (@usuario, resolvido com `get_entity`, com cache e no máximo 10
  buscas novas por lote) e `MentionName`; botões só de link, nos formatos novo
  (`InlineButtonTypeUrl`) e antigo (`KeyboardButtonUrl`) do Telethon.
- WhatsApp: `mentionedJID` do `ContextInfo`; nome = agenda > perfil > nome
  verificado de empresa > telefone (também em `_nome_contato`); `@número` do
  texto vira `@nome`; endereços LID viram o número quando conhecido.
- Janela de detalhes: listas Links, Botões de link e Pessoas mencionadas; na
  pessoa, Enter abre a conversa (criada vazia se não existir; passa a existir
  no primeiro envio, nos dois provedores).

## 2026.10.14.0

Etapa 3a: receber e abrir mídias.

- `midia/armazem.py`: mídias só em `%APPDATA%\TeleZapp\midias\<conta>\
  <hash da conversa>\<id>_<nome>`; apagadas com a conta.
- `nucleo/midias.py` (`GerenteMidias`): downloads em threads próprias, com
  progresso, cancelamento e registro na tabela `midias`; baixa ao receber
  conforme a opção `midias_baixar` (`demanda` ou `automatico`, limite
  `midias_limite_auto_mb`).
- Provedores: `baixar_arquivo()` no Telegram (`download_media`) e no WhatsApp
  (`download_any` com a ficha guardada); arquivo escrito como `.parte` e
  renomeado ao fim.
- Banco, esquema 4: tabela `fichas` (dados de download do WhatsApp, sem
  miniatura nem citação), gravada para mensagens novas e do histórico.
- `midia/reprodutor.py`: áudio com soundfile + sounddevice, lendo aos poucos;
  `interface/visualizadores.py`: imagem, áudio, vídeo (`wx.media.MediaCtrl`),
  texto e documento, todos em janelas do app.
- Menu: Mensagem (abrir, baixar, salvar cópia) e submenu Mídias.
- Dependências novas: soundfile, sounddevice.
- Telegram: download em partes de 512 KB, 8 em paralelo; log com a velocidade.
- Vídeo (MediaCtrl) começa a tocar sozinho mesmo sem o aviso de "carregou".
- Título da janela mostra o progresso da sincronia (`ProgressoSincronia`) e
  dos downloads.
- Janela: Esc fecha a conversa (só as conversas ficam); a caixa de digitar
  fica visível enquanto a conversa está aberta e o rascunho é guardado ao sair.
- Detalhes da mensagem: lista de links (http, https, www) que abrem no
  navegador padrão com Enter ou Espaço.
- Menu de contexto/Mensagem: Ir para a mensagem respondida (busca no banco
  se estiver fora da lista); Esc volta para a resposta.
- Respostas citam, depois do texto, um trecho da original (do banco, se fora da
  lista). Opção `audio_sequencia` (padrão sim): ao fim de um áudio sem janela
  toca o próximo áudio/voz da conversa.
- Conversa com não lidas abre sempre no marcador (mesmo com uma só); sem não
  lidas, reabre no ponto em que você parou (na última, se parou no fim). Banco na versão 5
  (tabela `posicoes`). A lista de conversas lembra a conversa selecionada.
- Atalhos: Alt+1 conversas, Alt+2 marcador de não lidas (na conversa) ou
  próxima conversa com não lidas (na lista), Alt+3 mensagens. Saem Ctrl+1,
  Ctrl+2 e Ctrl+U; Ctrl+N fica reservado para nova conversa.
- Vídeo (MediaCtrl) não repete mais: a nova tentativa de Play só vale antes
  de o vídeo andar; ao acabar e voltar ao início, marca como terminado.
- Conversa com não lidas abre com o foco no item "Início das mensagens não
  lidas" (com a contagem); seta para baixo lê a primeira. O foco só vai para a
  lista depois que a seleção está no lugar (uma fala só).
- Nada move a seleção da lista de mensagens sozinho (envio, mensagens
  novas, recargas): mensagens novas são só acrescentadas ao fim da lista.
- Opção `audio_janela`: Enter em áudio/voz toca sem janela (padrão) ou abre o
  player em janela; Enter pausa, Esc para.
- Lista de conversas só é refeita quando algo muda (o NVDA repetia o foco
  durante a sincronia).
- WhatsApp: se a conexão cair sem pedido, reconecta sozinho (esperas de 3 a
  120 s); se o histórico estava chegando, avisa "sincronia interrompida em N%"
  (título, fala) e oferece conectar de novo.

## 2026.10.13.0

- Menu único "Menu" com submenus (`wx.Menu.AppendSubMenu`); atalhos mantidos.
- `telezapp.VERSAO` passa a `ano.mês.dia.dígito`; `versao_valida()`.
- `config.OPCOES`: registro de opções (chave, rótulo, categoria, padrão,
  descrição) e `buscar_opcoes()`, base da janela de configurações.
- Pasta temporária própria (`%APPDATA%\TeleZapp\temp`), limpa ao abrir e ao
  fechar.
- Banco, esquema 3: tabelas `recibos` (por participante), `status` (status
  do WhatsApp) e `midias` (arquivos baixados).
- WhatsApp: recibos de entrega, leitura e reprodução gravados com hora;
  `status@broadcast` vai para a tabela `status`, não para as conversas.
- `nucleo/paginas.py`: guia e novidades gerados com a versão atual.

## 2026.10.12

Etapas 1 e 2 (Telegram e WhatsApp com texto, histórico e pareamento
acessível), PRs #2 a #6.

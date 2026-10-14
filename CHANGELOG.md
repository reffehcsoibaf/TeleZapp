# Registro técnico de mudanças

Para o usuário, veja `telezapp/ajuda/novidades.html`. Versões no formato
`ano.mês.dia.dígito`. Mais novas primeiro.

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

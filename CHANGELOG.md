# Registro técnico de mudanças

Para o usuário, veja `telezapp/ajuda/novidades.html`. Versões no formato
`ano.mês.dia.dígito`. Mais novas primeiro.

## 2026.10.31.1

- Emoji na janela Novo status (pedido do responsável): botão "Inserir emoji" e a tecla de `inserir_emoji`, personalizada ou não, por `EVT_CHAR_HOOK`, porque a aceleradora da janela principal não chega ao diálogo. **Sem teste com leitor de tela.**
- Avisos de entrada e saída de membros no Telegram (grupo Tiro certo abria vazio com não lidas, porque só tinha esses avisos, que `converter` descartava; confirmado no celular pelo responsável): `m.AVISO_MEMBROS`, `telegram.aviso_de_membros`, ao vivo por `ChatAction` e opção `mostrar_avisos_de_membros` (Mensagens, ligada). Sem som nem fala; ocultos, saem da lista e da prévia e descontam a não lida que chega ao vivo. Os demais avisos de serviço seguem descartados. **Não visto com um grupo real.**
- Mensagens por conversa (relato do Fabiano, WhatsApp com 1200 configuradas; reproduzido): a opção `mensagens_por_conversa` era só teto, porque `_abrir_conversa` lia no máximo `LIMITE_CACHE` (100) e pedia ao serviço só o que cobria as não lidas. Pedido do responsável: opção removida; `Banco.por_vez` (tabela `mensagens_por_vez`, padrão 100, de 50 a 5000) e botão "Mensagens por vez" nos detalhes. Home na primeira da lista (`Janela._mais_antigas`) lê mais do banco e, acabando, chama `buscar_mais_antigas`: Telegram por `offset_id`; WhatsApp com uma rodada de `request_history_sync` a partir da mais antiga (até 50) e o aviso para abrir o celular. Resposta em `ev.MaisAntigas`. **Busca no celular e no Telegram sem teste real.**
- Feedback dentro do programa (pedido do responsável): `interface/relato.py` e `nucleo/relatos.py` no lugar de abrir `relatar.html`. Tipo, nome, contato, descrição, quando; "Enviar com os logs" anexa `falha-nativa.log`, `telezapp.log` e `telezapp.log.1` até 4,8 MB, guardando o fim de cada um, e a descrição fica opcional; o clique é a autorização, e a janela explica o que os logs têm. Versão automática; nome e contato lembrados depois de enviar (`relato_nome`, `relato_contato`). O Worker aceita pedido sem `Origin` com `User-Agent` `TeleZapp/`, o que não é autenticação; o limite de 8 por dia e por endereço continua. A página segue no ar. **Sem teste com leitor de tela.**
- Guia de uso no formato do outro programa do responsável (pedido dele): `ajuda/guia.txt` com "# Assunto" no lugar de `guia.html`, `paginas.ler_assuntos` e `interface/guia.py` (lista de assuntos, texto somente leitura, Fechar). F1 e o botão da tela de boas-vindas abrem a janela; o instalador não cria mais a pasta temporária do guia. Novidades continuam em HTML, porque o `publicar.py` monta as notas delas. Texto reorganizado em 56 assuntos curtos, com "Ctrl+" no lugar de "Control", atualização descrita como ela é hoje (o programa se atualiza sozinho), sem citar outros programas, e NVDA só como "testado com". Testes conferem assuntos, marcas e se os atalhos da lista existem no menu. **Sem teste ao vivo com leitor de tela.**
- Estimativa de alcance (pedido do responsável): a consulta de versão baixa, uma vez por dia em cada cópia empacotada, o `consulta.txt` da última Release (`atualizacao.baixar_arquivo_do_dia`, chave `atualizacao_dia`). O `publicar.py` inclui o arquivo. Sem identificador, sem servidor próprio e sem interface; o `download_count` dele, dividido pelos dias desde o lançamento, dá as cópias ativas por dia, como mínimo. Só conta as cópias que já estão nesta versão ou em outra mais nova. Explicado no guia, em "Segurança e privacidade". **Sem teste ao vivo.**
- Certificado validado pelo Windows nas atualizações (relato de usuário em 30/10: "antivírus ou data" ao verificar, e o instalador baixou normal pelo navegador; causa dele não vista): `atualizacao.abrir_url` usa `truststore.SSLContext` na consulta, no plano B, no arquivo do dia e no download do `atualizador`. A validação do Python só enxerga as raízes já guardadas no Windows, sem disparar a busca de uma raiz ausente (hipótese para o caso). Sem a biblioteca, cai na validação do Python. Só o caminho de atualização muda; provedores de IA e prévias seguem como estavam. A mensagem de erro de certificado agora indica baixar o instalador pelo navegador, também no download. Quem atualiza para esta versão ainda usa a validação antiga. **Erro não reproduzido aqui.**
- Janela de erro da atualização com botão (pedido do responsável): `Janela._erro_de_atualizacao` e `interface/atualizacao.erro_quer_a_pagina`, com "Abrir a página de download" (`atualizacao.URL_ULTIMA`) e Fechar, em qualquer falha manual de consulta ou de download; cancelar não mostra janela. Busca automática continua sem reclamar. **Sem teste com leitor de tela.**

## 2026.10.31.0

- Corrigido (relato do Nuno, causa dele não confirmada): `CREATE_NO_WINDOW` com `DETACHED_PROCESS` não esconde nada, e a espera por `ping 127.0.0.1` do atualizador, de `_reiniciar` e de `_abrir_depois` abria janela visível, anunciada pelo leitor de tela. Reproduzido com as mesmas bandeiras (janela "ping -n 2 127.0.0.1"); só `CREATE_NO_WINDOW` não abre nenhuma. Quem atualiza para esta versão ainda usa o script antigo; vale da seguinte em diante. Não resolve o que prenderia a pasta na troca, se for o caso.
- Silenciar participante (pedido do responsável): `nucleo/silenciados.py` (`participantes_silenciados` no config, vai no backup), `Janela._silenciado` com os endereços da pessoa (`formas_do_endereco`, telefone e LID), `_mensagens_atuais` filtrado, então lista, seleção, marcadas e resumo de IA ficam sem elas; sem som, fala, IA automática nem prévia na lista de conversas; contador de não lidas desconta o que chega ao vivo. Reação de quem foi silenciado à minha mensagem ainda avisa. Busca, mídias dos detalhes e conversa salva continuam com as mensagens. **Sem teste ao vivo.**
- Mensagens fixadas (pedido do responsável): `fixar_mensagem` nos dois provedores (`pinInChatMessage` com `messageAddOnDurationInSecs` e até 3 por conversa, como o celular; `pin_message`/`unpin_message`), extras `fixada`, `fixada_ate` e `fixada_em`, `modelos.fixada_agora`, marca "(fixada)", `_fixar_mensagem`, itens de menu e botão "Mensagens fixadas" nos detalhes. Recebidas: `_tratar_alteracao` e `_ao_fixar` (`UpdatePinned*`). No Telegram, `fixadas_no_servico` consulta a lista real, inclusive fixadas não guardadas, que não entram no banco para não mexer na busca de mensagens antigas. No WhatsApp, só vale o que chega dali em diante; fixações de antes do pareamento e do histórico não são lidas. **Sem teste ao vivo.**
- Opção `ocultar_telefone_sem_nome` (Mensagens, desligada; pedido de usuário): `modelos.nome_visivel` tira do autor, na lista de mensagens, na fala e na lista de conversas, o que for só telefone (`e_telefone`). "Participante final 1234" e "Desconhecido" ficam. Detalhes e conversas salvas mantêm o número.
- Botão "Iniciar chamada" depois de anexar (`_iniciar_chamada`, `dialogos.escolher_tipo_chamada`): áudio ou vídeo, Esc sai; sem vídeo na conta, o botão de vídeo não aparece. Grupo, conta sem chamadas ou chamada em andamento vão para `_ligar`, que explica.
- Download pedido de documento (`m.DOCUMENTO`) abre `dialogos.documento_baixado`: Abrir, Ver na pasta, Salvar, Fechar. Vale para Enter e Control B; downloads automáticos e em lote não abrem. Documento já baixado abre direto, como antes.
- Pasta dos arquivos salvos: `pasta_salvar` e `salvar_direto` (Mídias), `interface/salvar.py` e `nucleo/pasta_salvar.py`, usados em mídias, conversa em zip, logs, texto da IA e QR do convite. Backup fora. Direto, o nome é limpo (vem de quem enviou) e nada é sobrescrito; pasta inutilizável volta à janela. Novo `Opcao.pasta`.
- Corrigido: mudar "Como me chamar" não atualizava as prévias já guardadas da lista de conversas.

## 2026.10.30.0

- Opção `como_me_chamar` (pedido de usuários, trazido pelo responsável; Interface, texto, novo campo `Opcao.texto`): `modelos.meu_nome` no lugar de "Você" como autor na lista de mensagens, prévia e autor da lista de conversas, reações, votos, busca, cópia, visualizador e conversa salva. Reações e votos continuam guardados como `m.VOCE`, que é o marcador da própria pessoa, e só a exibição troca (`nome_a_mostrar`). Frases como "Você saiu do grupo" não mudam. A busca por autor aceita "você" e o nome escolhido. **Sem teste ao vivo.**
- Opção `falar_quantas_no_filtro` (pedido do responsável; ligada, grupo Conteúdo falado): desligada, `_ao_filtro_conta` e `_ao_filtro_tipo` não falam o filtro e a quantidade; eram os únicos que falavam. **Sem teste ao vivo.**
- Enviar contatos (pedido do responsável): `enviar_contatos` nos dois provedores (`contactMessage` para um e `contactsArrayMessage` para vários, com prazo de mensagem temporária; `InputMediaContact`, um por mensagem no Telegram), `nucleo/enviar_contatos.py`, `contatos.DialogoEnviarContatos` e item "Enviar contatos..." no menu Mensagem. A lista junta a agenda de todas as contas, só com telefone e sem repetir número; quem é digitado não entra na agenda. **Sem teste ao vivo.**
- Resumo com as mídias (pedido do responsável): `nucleo/resumo_midias.py` (`planejar`, `LoteDeResumo`) e `Janela._resumir_mensagens`, em "Resumir as mensagens não lidas" e "Resumir a conversa". Pergunta com três botões, permissão de envio uma vez só, barra com Cancelar, até 50 mídias, as mais novas; áudio, imagem e figurinha (vídeo e PDF seguem a pedido). `_linhas_da_conversa` agora leva a transcrição ou descrição inteira das mídias já processadas, inclusive em "Resumir só o texto". Mídia que falhar não impede o resumo, que avisa quantas ficaram de fora. Cancelar impede os pedidos que ainda esperavam a vez (`_ia_canceladas`). **Sem teste com provedor real.**
- Guia: como sair de "janela indisponível" sem fechar o programa (Alt Tab, Alt Esc, Windows T, Esc ou Alt F4, Windows D).
- Busca periódica de versão nova (pedido do responsável): opções `atualizacoes_periodicas` (ligada) e `atualizacoes_intervalo` (1, 6, 12 ou 24 horas; padrão 24), esta habilitada só com a primeira marcada, e ambas dependentes de `verificar_atualizacoes`, para quem desligou as consultas automáticas continuar sem nenhuma. `_agendar_busca_de_versao`: com chamada, outra janela aberta ou texto na caixa, tenta em 5 minutos. A mesma versão não reabre a janela na mesma sessão. Em segundo plano, fala e deixa a janela para a volta (`_versao_pendente`), o que vale também para a consulta ao abrir. **Sem teste ao vivo.**
- Corrigido (relato): salvar os logs deixava "janela indisponível". O seletor de arquivo tinha a janela principal como dona, com a de exportar aberta por cima; ao fechar, o Windows ativava a principal desabilitada e o foco se perdia. Reproduzido com janelas reais; agora a dona é a de exportar. O mesmo em Salvar no texto da inteligência artificial.
- Ajuda, "Exportar logs..." (pedido do responsável): `nucleo/exportar_logs.py` compacta a pasta de logs em `logs-exportados` (só o último zip fica guardado; fora de `temp`, que é apagada ao abrir e fechar), e `dialogos.mostrar_logs_exportados` oferece Fechar, Copiar e Salvar. Copiar põe o arquivo na área de transferência, e colar na caixa vira anexo pelo fluxo normal.
- Segundo plano voltava ao Alt+Tab (relato): `ortografia.Corretor` punha `argtypes` em `windll.ole32.CoCreateInstance`, que é dividido pelo programa todo; depois de usar a ortografia, `segundo_plano._adicionar_botao` dava `ctypes.ArgumentError` (visto no log) e a janela voltava ao normal. Cada um usa agora o próprio `ctypes.WinDLL("ole32")`. Também: a abertura com `--segundo-plano` minimizava sem sair do Alt+Tab.
- Enviar localização (pedido do responsável): `enviar_localizacao` nos dois provedores (`locationMessage` com prazo de mensagem temporária, `InputMediaGeoPoint`), item "Enviar a minha localização..." no menu Mensagem e `robos.enviar_localizacao`, que o botão de local dos robôs também usa. Ponto fixo, sem tempo real. **Sem teste ao vivo.**
- Biometria e localização (pedido do responsável): `nucleo/recursos_windows.py` chama `UserConsentVerifier` e `Geolocator` por um PowerShell sem janela, sem dependência nova. Na ponte, `web_app_biometry_*` e `web_app_check_location`, `web_app_request_location` e `web_app_open_location_settings`; o segredo que o robô guarda atrás da biometria fica cifrado por DPAPI em `webview\segredos-dos-robos.json`. Sem dispositivo, avisos "Não foi identificado nenhum dispositivo de biometria/localização neste computador". O botão de local do robô usa o localizador, com digitação como alternativa. Coordenadas não são guardadas nem registradas. Verificado neste notebook: Windows Hello disponível e posição obtida por Wi-Fi. **Sem teste em aplicativo real.**
- Robôs, o que tinha ficado de fora: `interface/robos.py` trata telefone (`InputMediaContact`), localização digitada (`InputMediaGeoPoint`), enquete, escolher conversa (`SendBotRequestedPeerRequest`), senha de duas etapas no botão (`compute_check`), busca inline (`GetInlineBotResults`, só por lista), jogo, login em site (`RequestUrlAuth`, `AcceptUrlAuth`), perfil e compra. Pagamento (`GetPaymentForm`, `SendStarsForm`, `SendPaymentForm`): confirmação com o valor, e no cartão uma segunda antes de cobrar, com o formulário do provedor na janela própria e `payment_form_submit`; se o vendedor pede nome, telefone, e-mail ou endereço, `DialogoDadosDePagamento` (preenchida com `saved_info`) e `ValidateRequestedInfoRequest`, com escolha da entrega. Na ponte: telefone, área de transferência, QR (`midia/qr.py`, de imagem ou câmera), pagamento, inline e confirmação ao fechar. `ReplyKeyboardHide` tira o teclado; o teclado de conversa fechada vem do banco; mídia trocada na edição atualiza e esquece o arquivo; barra na caixa vazia abre os comandos (opção `barra_abre_comandos`). **Nada disto foi testado com robô real, e nenhum pagamento foi feito.** QR testado com imagem gerada.
- Chamadas: a recusa de um aparelho manda `rejected_elsewhere` aos outros, menos em `busy` e `enc`. DLL recompilada. **Sem teste ao vivo.**
- Aplicativos de robô em janela própria (pedido do responsável, em vez do navegador): `interface/app_do_robo.py` (WebView2, botões nativos para principal, secundário, voltar e configurações) e `nucleo/ponte_web_app.py` (`TelegramWebviewProxy`, plataforma `tdesktop`). Dados em `webview` na pasta de dados, fora do que se leva ao instalar. **Testado com o script oficial do Telegram numa página local (botões e ida e volta da ponte); sem teste com robô real.** Ainda não: pagamento, compartilhar telefone, ler a área de transferência, QR, biometria.
- Links: `nucleo/links_externos.py` interpreta t.me, tg://, wa.me, api.whatsapp.com, whatsapp:// e convites; `dialogos.abrir_por_dentro` faz os links do programa passarem por ele. Sem conta conectada do serviço, dentro do programa o link vai para o navegador. Texto do link só preenche a caixa; robô com `start` e aplicativo vindo de fora pedem confirmação.
- `nucleo/protocolos.py`: o TeleZapp entra nas opções de abrir tg:// e whatsapp:// (Capabilities e RegisteredApplications em HKCU), sem trocar o dono atual. Opção `abrir_links_no_telezapp`, ligada; `--link` na linha de comando; `nucleo/links_recebidos.py` passa o link para a abertura que já está rodando. **Sem teste no Windows de verdade: falta clicar num link.**
- Robôs do Telegram, botões e menu: `acoes_do_robo` transforma os botões em ações (`robo_texto`, `robo_callback`, `robo_copiar`, `robo_web`, `robo_indisponivel`); `responder_acao` no provedor (`GetBotCallbackAnswerRequest`, resposta como `Aviso`); `link_web_do_robo` (`RequestWebViewRequest`) abre aplicativos; `comandos_do_robo` passou a devolver dicionário com comandos, menu e privacidade; a janela de comandos junta tudo e o teclado da mensagem mais nova entre as 30 últimas da memória (`ReplyKeyboardHide` não é tratado: um teclado já escondido pelo robô ainda pode aparecer). `dados_do_contato` traz a descrição do robô como recado. `MAX_BOTOES_ACAO` de 12 para 30. **Sem teste ao vivo.**
- Telegram: `_ao_editada` (`events.MessageEdited`), que não existia. Mensagem editada por outros atualiza texto, links e botões e publica `MensagemAtualizada` "editada"; mudança só de reação ou visualização é ignorada. Mídia trocada na edição não é tratada. **Sem teste ao vivo.**
- Comandos de robô do Telegram: `comandos_do_robo` no provedor (`bot_info.commands`, por `GetFullUserRequest`, `GetFullChannelRequest` ou `GetFullChatRequest`; em grupo o comando leva `@robo`) e item "Comandos do robô..." no menu Conversa e no de contexto, para conversas do Telegram que não sejam canal. O `Conversa` não sabe se é robô, então o item aparece também em conversas com pessoas e responde que não há comandos. **Sem teste ao vivo.**
- Lista de conversas: item novo `autor` ("Autor da última mensagem (em grupos)") em `nucleo/lista_conversas.py`, com `autor_da_mensagem`. Em grupo, o trecho deixa de trazer "Ana: " na frente; o autor vira item próprio, então a linha passa de "Ana: texto" para "Ana, texto". Configuração salva sem o item: ele entra logo antes do trecho e segue o estado dele. Fora de grupo, o trecho continua com "Você: ".
- Chamada de saída do WhatsApp: quando um aparelho da outra pessoa atende, o TeleZapp manda um `<terminate reason="accepted_elsewhere">` para cada um dos outros aparelhos que receberam a oferta, para pararem de tocar (`dismissOtherDevices` no `engine.go` do meowcaller; diff em `docs/neonize/mc-whatsmeow-parar-outros-aparelhos.diff`). Quem manda parar é quem liga; antes o TeleZapp não mandava. Teste novo em `engine_dismiss_test.go`. **Sem teste ao vivo.** Não resolve o caso de quem liga pelo WhatsApp oficial, em que a parada depende do app dessa pessoa.

## 2026.10.29.0

- Banco de sessão do WhatsApp em WAL com espera de 30 s (`dsn_da_sessao` em `provedores/whatsapp.py`): a DLL monta `file:<nome>?_foreign_keys=on`, então o nome que damos ao `NewClient` leva `?_foreign_keys=on&_journal_mode=WAL&_busy_timeout=30000&_fim=` e o `_fim=` engole o trecho que a DLL acrescenta; sem recompilar a DLL. Motivo: dezenas de `database is locked` no pareamento de 25/10 (histórico chegando e mensagens sendo decifradas), com ligações falhando e mensagens não decifradas. Conferido com a DLL real: aparecem `-wal` e `-shm` ao abrir. O backup já usa a API de backup do SQLite e ignora `-wal`/`-shm`. **Não visto num pareamento real.**
- Gravação de mensagens com novas tentativas (`banco._com_tentativas`): se o SQLite disser "locked"/"busy" ao gravar, espera 0,5, 2 e 5 s e tenta de novo antes de desistir; a conexão do `telezapp.db` passou a esperar até 30 s por trava (`timeout=30`). Quando a gravação de uma mensagem recebida falha de vez, o id sai de `_vistas` para que um reenvio não seja ignorado como "repetida". Motivo: em computador lento uma mensagem podia se perder (relato do Vanderlei, mensagens faltando). Testado só com testes automáticos.
- Localização (WhatsApp e Telegram): antes qualquer localização virava só a palavra "localização". Agora `nucleo/localizacao.descrever` monta o texto com o nome e o endereço do lugar, a legenda, as coordenadas e o link do mapa (`https://www.google.com/maps?q=lat,lon`); em tempo real aparece "localização em tempo real". WhatsApp: `locationMessage` (nome, endereço, comentário, `isLive`) e `liveLocationMessage` (legenda). Telegram: `geo`, `venue` (título e endereço) e `MessageMediaGeoLive`. Só o início da localização em tempo real aparece; as atualizações de posição não são acompanhadas. Enviar localização não existe. Testado só com testes automáticos;
- Desligamento do Windows (relato: o TeleZapp às vezes impede): três causas pelo código. (1) No aviso de consulta (`EVT_QUERY_END_SESSION`, vetável) o `wx` fechava a janela e, com "Continuar em segundo plano" ligado, `_ao_fechar` vetava para esconder na bandeja, o que recusa o desligamento. (2) Com chamada ativa abria a pergunta "Fechar mesmo?", que segura o Windows. (3) `parar_todos` esperava até 6 s por thread, por conta, na thread da janela. Agora `__main__.sessao_do_windows` marca `janela.marcar_windows_encerrando()` (vale 60 s) e não passa o aviso de consulta adiante; `_ao_fechar` com o Windows encerrando não esconde, não pergunta e para as contas numa thread esperando no máximo 2 s. Testado só com testes automáticos; a causa real do relato não foi confirmada (falta o `telezapp.log` dele: procurar "o Windows está encerrando a sessão" e "fechando a janela").
- Busca de mensagens que faltam sem silêncio (relato: às vezes não diz nada, nem que achou nem que não): o aviso só saía quando o celular respondia, então celular desligado, sem a mensagem de referência ou resposta que falhasse na leitura deixavam tudo mudo. Agora `_pedir_historico` inicia um relógio de `ESPERA_DO_HISTORICO` (45 s) e, sem resposta, avisa "O celular não respondeu ao pedido de mensagens que faltam" (`_pedido_sem_resposta`); a resposta cancela o relógio; se a leitura da resposta quebrar, avisa "O celular respondeu, mas não consegui ler as mensagens"; uma parte atrasada da resposta com mensagens novas também avisa. O log de cada resposta agora traz quantas mensagens vieram no pacote, quantas já existiam e quantas não tinham conteúdo (base do diagnóstico do Vanderlei). Testado só com testes automáticos.
- Pareamento lento (log de 29/10): um pacote de histórico de 5000 mensagens levou 413 s para ser guardado, com milhares de linhas "sem nome verificado para uma menção". Causa: para cada @ de alguém sem nome, `_dados_mencao` consultava o WhatsApp (participantes do grupo e `get_user_info`) e o resultado sem nome não vai para o cache, então repetia a cada menção. `_enriquecer_mencoes(rede=False)` agora é usado em `guardar_historico` e no histórico sob demanda: o histórico só usa agenda, apelidos, participantes já conhecidos e mensagens guardadas. Ao vivo nada muda. Efeito colateral: menção sem nome no histórico fica com o telefone até a pessoa aparecer.
- Ajuda: nota no guia (WhatsApp) sobre a limitação do WhatsApp Business: o aplicativo entrega a aparelhos pareados só uma parte do histórico, muitas vezes a última mensagem de cada conversa, e não responde ao pedido de mensagens que faltam. Visto em 29/10 com o mesmo iPhone: a conta do WhatsApp comum trouxe tudo (57 mil mensagens numa conversa) e a do Business trouxe 147 mensagens em 4 conversas, também no WhatsApp Web oficial.
- Baixar as mídias que faltam, por conversa (pedido): botão "Baixar as mídias que faltam..." nos detalhes de pessoa, grupo e canal (WhatsApp e Telegram). `GerenteMidias.faltantes` acha as mídias baixáveis que não estão no computador (sem as limpadas), da mais nova para a mais antiga; `baixar_lote` as enfileira (as 2 threads de sempre, `automatica=True` para não abrir aviso por mídia) e o `Lote` conta baixadas, indisponíveis e canceladas, avisando o progresso e o fim. A janela explica antes (algumas podem não estar mais disponíveis nos servidores), mostra a barra com Cancelar e fecha com o resumo ("Baixei N. M não estão mais disponíveis..."), refazendo os detalhes. Não aplica o limite de tamanho do download automático. Só testes automáticos; não visto com mídias reais.
- Nome de conversa só com o telefone, completado nos detalhes (pedido): ao abrir os detalhes de uma conversa privada do WhatsApp cujo nome é só o número (ou "Contato sem nome"), `completar_nome` procura na rede, nesta ordem, o cadastro de contatos e a agenda, o nome de perfil visto nas mensagens guardadas e o nome verificado de empresa (`get_user_info`) e, por último, o nome da pessoa nas listas de participantes dos grupos (`get_joined_groups`); se achar, grava na conversa, publica `ConversasAtualizadas` (a lista se atualiza) e a janela fala "Nome encontrado: ...". No máximo uma busca por conversa a cada 10 minutos; o Telegram não precisa (sempre tem nome). O WhatsApp não tem consulta direta do nome de perfil de qualquer número: só aparece o que o celular, as mensagens ou os grupos já informam. Só testes automáticos; não visto com uma conversa real.
- Recado do contato nos detalhes (relato: não aparece): o código lê `UserInfo.Status` de `get_user_info` e a janela já o mostrava quando vinha; nunca foi visto ao vivo e não há erro no log, então o provável é o WhatsApp devolver o recado vazio. Agora `dados_do_contato` registra no log `recado do contato: N caracteres, foto sim/não` (ou que o WhatsApp não devolveu a pessoa) e a janela diz "Recado: o WhatsApp não informou (a pessoa não tem recado ou só o mostra a quem ela escolhe)" quando a consulta funcionou e veio vazia. Achado no primeiro relato real (29/10): a linha "Recado:" aparecia vazia, então o WhatsApp devolve um recado feito só de espaços ou caracteres invisíveis; `recado_visivel` trata isso como vazio (inclusive o braille em branco e similares) e o log traz as categorias Unicode dos caracteres.
- Queda ao abrir (relato do Lucas, 29/10, versão 28.0 empacotada): o `falha-nativa.log` mostra `panic: nil pointer dereference` em `main.GetContact` (`contact_store.go:94`), 4 vezes seguidas logo depois de "biblioteca do WhatsApp carregada". Reproduzido com a DLL do projeto: chamar `contact.get_contact` antes de a DLL registrar o cliente (o `clients[id]` do lado Go só existe depois do início do `connect`) derruba o processo inteiro, sem exceção em Python. Não achei qual chamada acontece tão cedo no Lucas, então a proteção é geral: `ProvedorWhatsApp._contatos()` só devolve o cadastro depois do primeiro aviso do WhatsApp (`_go_pronto`, marcado por `_vivo` em todos os avisos e no QR) e, antes disso, levanta um erro comum e grava no log uma vez `leitura de contatos antes de a DLL registrar o cliente (evitada)` com a pilha, para sabermos quem chamou. Vale para os 4 `get_contact` e o `get_all_contacts`. Efeito: antes do primeiro aviso os nomes saem do que já se sabe (agenda do TeleZapp, apelidos, telefone). Só testes automáticos.
- Gerenciar contas (log de um usuário, 28/10): `wxAssertionError: bad wxCheckListBox index` em `IsChecked` quando um aviso de marcação chegava depois de a conta ser excluída e a lista encolher; `_marcou` agora confere o tamanho real da lista. Nota sobre o `falha-nativa.log`: as linhas `Windows fatal exception: code 0x8001010d` e `0x80010108` (erros de chamada entre componentes do Windows, vistos com leitor de tela) são relatadas pelo `faulthandler` mas não derrubam o programa; só enchem o arquivo.
- Busca de mensagens que faltam agora varre o histórico para trás (pedido; o relato era mensagens de grupo faltando além das últimas 50): `buscar_mensagens_que_faltam` abre uma varredura por conversa (`_varreduras`) e cada rodada pede ~50 mensagens antes de uma âncora; a mais antiga da resposta (`_guardar_sob_demanda` devolve `(novas, resumo)`) vira a âncora da próxima, com `ESPERA_ENTRE_RODADAS` (1 s) entre elas. Para quando: o celular não devolve nada, a resposta repete a âncora, passou da mensagem mais antiga que já havia (`banco.data_mais_antiga`) sem achar nada novo, ou chegou a `RODADAS_MAXIMAS` (60, ~3000 mensagens; o aviso diz que parou no limite). Avisa só no fim ("Encontrei N mensagens que faltavam (conferi M mensagens do celular)") ou, se o celular parar de responder no meio, "Até aqui encontrei N". Uma varredura por conversa de cada vez. Só testes automáticos; não visto com um celular real.
- Busca sozinha de mensagens que faltam ao reconectar (pedido; comparando a cópia do usuário do grupo TeleZapp com o log do Vanderlei: com o programa fechado de 09:34 a 18:07 o grupo teve 59 mensagens e ele recebeu só as 21 de 16:02 em diante, porque o WhatsApp entrega só o final da fila offline): `_ao_receber` guarda por conversa a mais antiga mensagem entregue durante a sincronia (`_ancoras_da_sincronia`); em `_ao_fim_sincronia`, `_agendar_varreduras_automaticas` enfileira (até `LIMITE_AUTOMATICAS`=40, as de atividade mais recente primeiro) as conversas que têm mensagem guardada antes da âncora com folga de mais de 60 s (`banco.data_antes_de`), e `_seguir_automaticas` roda uma varredura por vez (`auto=True`), a partir dessa âncora, parando na primeira rodada sem nada novo (ou em `RODADAS_AUTOMATICAS`=20). Só avisa se achou ("Busca automática: encontrei N mensagens que faltavam em <conversa>"); falhas e falta de resposta ficam no log. Nova opção `varrer_ao_reconectar` (Configurações, Mensagens, ligada). Uma conversa sem nenhuma mensagem entregue na sincronia não dispara a busca. Só testes automáticos.
- Registro da fila offline do WhatsApp (para investigar mensagens que não chegam depois de o programa ficar fechado): o TeleZapp passou a assinar `OfflineSyncPreviewEv`, que o WhatsApp manda no começo de cada sincronia dizendo quantos itens estão na fila do aparelho, e grava `fila do WhatsApp para este aparelho: N itens (X mensagens, Y avisos, Z recibos, W mudanças do estado)`; no fim da sincronia o registro traz `N mensagens recebidas; o WhatsApp anunciou X e contou Y`. Com isso, qualquer log mostra se a fila já veio cortada do servidor (anunciou menos do que o esperado) ou se o programa deixou de guardar algo. Motivo: no grupo TeleZapp o Vanderlei (fechado de 09:34 a 18:07) recebeu 21 de 59 mensagens, com corte nítido às 16:00, enquanto a cópia do usuário recebeu 346 mensagens de 3h44 atrás; a causa do corte não está confirmada. Só testes automáticos.

## 2026.10.28.0

- Busca de emojis por sinônimos (pedido): `telezapp/nucleo/emojis_cldr_pt.py` (115 KB, gerado por `ferramentas/gerar_emojis_cldr.py` a partir de `annotations/pt.xml` e `annotationsDerived/pt.xml` do CLDR, Unicode-3.0, aviso no cabeçalho e em `docs/licencas-de-terceiros.md`) dá palavras-chave a todos os 1923 emojis da lista ("kkk", "gargalhada", "aniversário"...). `Emoji` ganhou `palavras_nome` e `palavras_base`; `buscar` ordena por palavra inteira antes de prefixo ("oi" acha 👋 antes de "oito"), depois nome, apelidos/sinônimos a mão e só-CLDR, e o plural vale (`_abre`); `SINONIMOS` ganhou saudade, abraço, aniversário etc. Sem o arquivo gerado a busca segue com o resto. Pacote `emoji` 2.16.0 (a última no PyPI) tem os mesmos 3963 emojis completos do `emoji-test.txt` do Unicode 18.0 (30/04/2026): não faltava nenhum.
- Tons de pele nos emojis (pedido; o WinZapp tem as setas): `nucleo/emojis.todos()` monta `_familias` (emoji sem tom + variantes `fully_qualified` ordenadas pelo tom, chave sem tons nem U+FE0F) e `passo_de_tom(simbolo, delta)` dá a volta nela; a lista continua com uma linha por emoji. `DialogoEmoji` (busca) e o novo `DialogoReacao` (lista curta, no lugar do `SingleChoiceDialog`) trocam o item com esquerda/direita e falam o novo emoji (`fala`); sem tons, a tecla passa. `escolher_emoji` e `escolher_reacao` ganharam `fala`; `wx_falso` ganhou `WXK_LEFT/RIGHT` e `EndModal`. Casais e famílias com dois tons entram na família (até 26 passos). Não visto ao vivo.
- Prioridade ao abrir (relato sem log: o TeleZapp fica "não respondendo" por um tempo quando aberto depois de outros aplicativos, e abre bem se for o primeiro): `prioridade.abertura(True)` põe o processo em prioridade acima do normal e fora do modo de eficiência (`SetPriorityClass` + `SetProcessInformation`) logo depois de `descrever_ambiente`, e um `threading.Timer` de `SEGUNDOS_DE_ABERTURA` (30 s) depois de "janela mostrada" a devolve ao normal (sem soltar a energia se houver chamada). Opção `prioridade_abertura` (Interface, ligada). Não resolve demora de disco, antivírus ou banco; para isso, pedir o `telezapp.log` e ver as linhas "abertura: ...". Não visto ao vivo.
- Chamada recebida que perde o som do outro lado no meio (relato da Fátima, 28/10/2026, 27.0): na chamada 984DC0.. o som do outro lado correu por 45 s e parou (685 quadros, o microfone seguiu até 1215); o log traz `unprotect: authentication failed` (seq 701, ROC 0 certo, mesmo SSRC) e `audio RTP did not match an authenticated active participant`; a ligação de volta, logo depois, trouxe 2334 quadros de cada lado. Uma terceira chamada da mesma pessoa (WhatsApp Web, `platform web`) deu a mesma mensagem aos 44 s, junto com o fim da chamada. Não é o ROC (o remendo `mc-whatsmeow-roc-resync.diff` não resolve); sobra troca de chave no meio da chamada ou formato diferente do pacote. `UnprotectAudio` (session.go) confere com uma chave só e não há caminho de troca de chave em chamada de uma pessoa (o `enc_rekey` só vale para grupo). A causa não foi achada: a DLL ganhou só diagnóstico (`docs/neonize/mc-whatsmeow-diagnostico-srtp.diff`): `logUnprotectDiag` nos dois primeiros pacotes que não autenticam (tamanho, cabeçalho, extensão e se autenticariam com outro tamanho de etiqueta ou ROC), "authentication recovered", contagem a cada 100 falhas e `controle da chamada recebido: <tag>` com os atributos de toda mensagem de controle (`onCallRaw`). Nada disso muda o que é aceito. Backup da DLL anterior em `Backup/neonize-0.5.2-chamadas-antes-do-diagnostico-srtp`; build nova em `neonize-build/saida/chamadas`, já no venv. Para a causa: pedir o `telezapp.log` de quem relatar e procurar essas linhas.
- Lista de mensagens no lugar do estilo (pedido, como na lista de conversas; "esse botão pode ir no lugar da caixa dos três modos"): `nucleo/lista_mensagens.py` (`ITENS`: autor, hora, conteudo, marcas, links, previa, ia, reacoes, resposta, estado, todos movíveis; `autor_so_quando_muda`; `do_estilo` converte os estilos 2 e 3 antigos) e a opção `lista_mensagens` (`config.PADROES`, `backup.EXTRAS`, `ModeloConfiguracoes.lista_msg_*`). A `Opcao("estilo")` e os radios de Exibir saíram; `PADROES["estilo"]` fica só para migrar (`Janela._migrar_estilo_antigo` na abertura e `backup.opcoes_validas` para backups antigos com `estilo` 2 ou 3). `modelos.formatar` monta a linha por blocos na ordem dada: autor e hora no começo viram o cabeçalho "Ana, 10:00: ...", o resto encadeia com `_juntar`; sem `itens`, vale o `estilo` (via `do_estilo`), então avisos, detalhes e os testes antigos seguem iguais. A prévia de link sozinho continua na frente do conteúdo quando os dois estão ativos. `DialogoListaConversas` serve às duas (`nucleo=`, com a caixa do nome só quando muda), botão em Configurações > Mensagens e submenu Exibir > "Lista de mensagens" (`listam_*`). Os atalhos `estilo1..3` deixam de existir. Não visto ao vivo.
- Queda ao abrir com a conta do WhatsApp já pareada (relato do José Gabriel, 28/10/2026, versões 26.1 e 27.0; o `falha-nativa.log` dele traz `panic: nil pointer dereference` em `main.GetPNFromLID` (`main.go:331`, `clients[id].Store`) duas vezes seguidas, e o `telezapp.log` termina em "biblioteca do WhatsApp carregada" nas duas): o lado em Go só registra o cliente em `clients` quando `connect()` chama `Neonize`, mas `self.cliente` já existe desde `fabrica_cliente()`; qualquer `get_pn_from_lid` / `get_lid_from_pn` nessa janela (a tela montando nomes ao abrir) derruba o processo, sem exceção em Python. Novos `_pn_do_lid` e `_lid_do_pn` só perguntam com `_conectada`; os cinco pontos de chamada usam os dois (sem conexão, o endereço LID fica como veio). Teste: `test_lid_nao_e_perguntado_antes_de_conectar`. Falta na DLL (não refeita): `GetPNFromLID` e `GetLIDFromPN` usarem `client, exists := clients[id]` como `SetPushName`. Não confirmado com ele; a 27.0 pública cai assim para quem tiver a janela de tempo.
- Descrever a foto de perfil com IA (pedido): botões "Descrever a foto do contato/grupo" nos detalhes. `ControleDetalhes._foto_em_arquivo` baixa a foto (usada por `ver_foto` e `descrever_foto`); `Janela._ia_descrever_arquivo` segue o caminho de `_ia_processar` sem mensagem (provedores de `ia_ordem["imagem"]` com chave, pedido de consentimento, `executar_em_ordem`) e `_ia_arquivo_pronto` fala o resultado e o mostra em `mostrar_texto`. Não guarda a descrição em lugar nenhum. Não visto ao vivo.
- Fotos de perfil, privacidade (preocupação do usuário: o WhatsApp oficial não deixa salvar nem capturar a foto): `nucleo/grupo.pasta_das_fotos` e `limpar_fotos_temporarias` apagam `%TEMP%\TeleZapp-fotos` ao abrir (`Janela.__init__`) e ao fechar (`_ao_fechar`); as que um visualizador segura ficam. O guia e as novidades dizem que só aparece a foto que a conta já vê e que a descrição por IA envia a imagem de terceiros a um serviço externo. Decisão em aberto: tirar o "Ver a foto" do WhatsApp e manter só a descrição.
- Menu Ajuda, "Entrar no grupo de suporte no WhatsApp..." (`grupo_suporte`, convite em `GRUPO_DE_SUPORTE`, `telezapp/__init__.py`): com conta de WhatsApp conectada segue `_entrar_no_grupo` (prévia, confirmação, entra; `_escolher_conta_para_grupo` foi extraído de `_entrar_por_link`); sem conta, abre o convite no navegador.
- "Ver a foto do contato" nos detalhes de uma conversa privada (pedido): `Provedor.foto_do_contato` e `FOTO_DO_CONTATO` (só o WhatsApp). `foto_do_grupo` e `foto_do_contato` dividem `_baixar_foto`; `ControleDetalhes.ver_foto` serve aos dois (arquivo `contato-<id>` em `TeleZapp-fotos`). Telegram também: `Provedor.foto_do_grupo`/`foto_do_contato` chamam `_baixar_foto`, que faz `get_entity` + `download_profile_photo(ent, file=bytes)` no loop do Telegram (canais não têm o botão). Sem miniaturas nas listas, de propósito. Não visto ao vivo.
- Ícone do app (pedido): um teclado com fone de ouvido sobre quadrado verde, desenhado por `ferramentas/gerar_icone.py` (Pillow, 7 tamanhos) em `telezapp/imagens/telezapp.ico` e `.png`. `bandeja.icone_do_app()` carrega o arquivo (sem ele, volta ao quadrado com T) e é usado na bandeja e na janela principal; `TeleZapp.spec` e `Instalador.spec` levam a pasta `imagens` e põem o ícone nos dois `.exe`. Decisão: nada de cores por remetente nem fotos nas listas (o `ListBox` não aceita e desenhar à mão arriscaria o leitor de tela).
- Log de mensagens recebidas do WhatsApp (relato: mensagem de grupo que aparece no celular e não no TeleZapp, sem log): `_ao_receber` agora registra "mensagem guardada" (id, conversa, grupo, tipo, sincronizando), "mensagem repetida ignorada" e "evento sem conteúdo para mostrar" também quando não há campos. Sem texto de mensagem. Achado para a busca sob demanda: o whatsmeow tem `BuildHistorySyncRequest` (até `count` mensagens imediatamente ANTES da âncora, resposta como `HistorySync` ON_DEMAND) e `BuildUnavailableMessageRequest` (reenvio de mensagem não decifrada), mas a nossa DLL só expõe o envio de pedido de par para recuperação de app state (`main.go`, ~linha 2070); falta uma função nova.
- Reenvio de mensagem não decifrada (WhatsApp): a DLL (`neonize` branch `feat/group-request-participants`, commit `53536c3`) ganhou `RequestHistorySync` e `RequestUnavailableMessage` (pedidos de par ao celular, `request_history_sync` e `request_unavailable_message` no Python; backup da anterior em `Backup/neonize-0.5.2-chamadas-antes-do-historico`). `_ao_indecifravel` agenda `_pedir_reenvio` após 20 s e de novo após 180 s (`ESPERAS_REENVIO`), só se a marca ainda for "aguardando"; a resposta chega como mensagem normal e substitui a marca. Não testado ao vivo; DLL antiga: registra no log e segue. Falta ainda a busca sob demanda "Buscar mensagens que faltam" (`request_history_sync`).
- Envio de voz, documento e mídia falhava com `MagicException: could not find any valid magic files` (relato do Lucas, 28/10/2026, versão 27.0): o libmagic abre o `magic.mgc` com o caminho em ANSI e o programa estava em `C:\Users\Lucas Aribé\...`; reproduzido copiando o pacote `magic` para uma pasta com "é". `midia/tipos_de_arquivo.consertar_caminho_do_magic` troca `magic.magic.default_magic_file` pelo caminho curto (8.3) ou, sem ele, por uma cópia em `%PUBLIC%\TeleZapp`; chamado em `_criar_cliente`. Texto enviava normalmente. Outros sinais do mesmo log, sem correção ainda: 429 `rate-overlimit` em `get_group_info` ao abrir (`_buscar_nome_grupo`, dezenas de vezes) e "a vez anterior terminou sem fechar normalmente" quatro vezes entre 10:27 e 10:32 (falta o `falha-nativa.log`).
- Backup e restauração por categoria (pedido): `PARTES` ganhou `atalhos` (`atalhos`, `mostrar_atalhos`) e `sons` (`pacote_de_sons`, `sons_desativados` e a pasta `sons/`), separadas de `configuracoes` (as demais opções e as chaves de IA). `opcoes_do_backup` e `opcoes_validas` aceitam `partes`; o manifesto tem `formato` 2 (`FORMATO`), e um backup antigo (formato 1) escolhido em "configuracoes" restaura as três juntas, como antes. Janela de backup e de restauração mostram as caixas novas (marcadas por padrão no backup, como antes era uma só); restaurar qualquer uma das três vale na hora. Testes de ida e volta de cada parte, de que configurações não leva atalhos nem sons e do backup antigo.
- Ligar de volta quando a chamada recebida fica sem som (relato do Valmir, 28/10/2026): nos logs dele 8 de 11 chamadas recebidas foram atendidas sem nenhum quadro vindo do outro lado (nem `first authenticated peer SRTCP`), e a ligação de saída logo depois funcionou todas as vezes. Causa na DLL/relay ainda em aberto (ver o relato 1 da 26.1). Paliativo: opção `chamada_retornar_sem_audio` (Mídias, ligada por padrão). Em `_vigiar_audio`, depois dos 20 s sem som numa chamada **recebida**, o TeleZapp encerra com a mensagem "Ligando de volta para a pessoa" e `_ligar_de_volta` liga para a mesma conversa (voz ou vídeo, mesmos dispositivos) assim que a anterior sai de `ligacoes`; chamada de saída nunca liga de volta (sem laço). `chamadas_whatsapp.definir_retornar_sem_audio`, ligado pela janela junto com o eco. Testes: volta, opção desligada e saída sem laço. Não visto ao vivo.
- Windows ARM sem parear de novo (relato do Nuno, 28/10/2026, versão 27.0): "failed to load neonize-windows-arm64.dll". O desvio `arquitetura_do_processo` (diz AMD64 ao `platform.machine()` durante a importação) existia só em `_criar_cliente`, mas na 27.0 `_uma_conexao` passou a importar `neonize.events` antes, e esse é o primeiro import do neonize (o pacote carrega a DLL). Novo `eventos_do_neonize()` faz esse import dentro do desvio; testes para os dois. De quebra: `caminho_do_som("<bip>")` devolve vazio (antes o pré-carregamento tentava abrir "<bip>" e registrava OSError 22 a cada abertura). O `falha-nativa.log` dele traz `0x8001010d` (RPC_E_CANTCALLOUT_ININPUTSYNCCALL) em `_ev_aviso` → fala direta do NVDA, depois do erro de conexão: aparece como erro de COM tratado pelo faulthandler; não confirmado como queda.
- Nome de grupo sem 429 (mesmo log do Lucas: 35 erros `rate-overlimit` em `get_group_info` nos primeiros 12 s): `_buscar_nome_grupo` agora só enfileira em `_fila_nomes`, servida por uma thread própria (`_trabalhar_nomes`) que pede um grupo por vez com `PASSO_NOMES_GRUPO` (1 s) entre eles e, se vier 429, espera 30 s, 60 s, 90 s e tenta de novo (`TENTATIVAS_NOME_GRUPO` = 4). Antes o id ficava em `_nomes_grupo_pedidos` e o nome nunca era buscado de novo; a fila de envios também não fica mais ocupada por isso.
- Menu Conversa, "Buscar mensagens que faltam no celular" (e no menu de contexto da conversa): `Provedor.buscar_mensagens_que_faltam` (base devolve o motivo de não fazer; WhatsApp usa `request_history_sync` com a mensagem mais nova que não seja "aguardando" como âncora e pede 50). A resposta (HistorySync ON_DEMAND, tipo 6) vai para `_historico_sob_demanda`: guarda só mensagens que faltavam ou eram marca "aguardando", sem mexer em não lidas, arquivada ou fixada e sem avisos por mensagem; publica `MensagensCarregadas` e um `Aviso` ("Encontrei N mensagens que faltavam"). Limitação do protocolo: só traz mensagens ANTERIORES à âncora, então uma mensagem mais nova que a última guardada não vem por aqui. Não testado ao vivo. Os testes não tocam mais bipes nem falam pelo NVDA (fixture autouse em `testes/conftest.py`).
- Provedor de IA Mistral (pedido): `catalogo.PROVEDORES["mistral"]` (texto, áudio e imagem; modelo `mistral-small-latest`, transcrição `voxtral-mini-latest`). Chat em `api.mistral.ai/v1/chat/completions` (imagem como `image_url` em texto, não objeto), transcrição em `/audio/transcriptions` e lista de modelos filtrada por `capabilities.vision`. Sem PDF: o envio de PDF em base64 pelo chat da Mistral não foi conferido. Vídeo vai por quadros, como nos outros. Não testado com chave real.
- Mais pacotes de sons da casa (pedido): Cristal (vidro), Marimba (madeira), Retrô (8 bits) e Suave (ataque lento), em `telezapp/sons/pacotes/<id>/`, um arquivo por evento. `pacotes_de_som` ganhou `NOMES_DA_CASA`/`da_casa` (o TeleZapp segue em `sons/`); nenhum se edita ou exclui e seus nomes são reservados. `ferramentas/gerar_sons.py` tem `PACOTES` (timbre, ataque e ritmo de cada um) e gera todos sem argumento.
- Busca por critérios (relato: o leitor de tela não dizia o que preencher em cada campo): em `interface/busca.py` cada campo e lista ganhou um `wx.StaticText` criado logo antes dele (o NVDA nomeia o campo pelo rótulo anterior na ordem de criação, não pelo `name` do wx); "De/até" e "mínimo/máximo" viraram "Data inicial/final", "Duração mínima/máxima em segundos" e "Tamanho mínimo/máximo em MB". `_junta` põe a caixa "Só frase exata" depois do campo de texto.

## 2026.10.27.0

- Opção `trazer_contatos_ao_abrir` (Interface, ligada; pedido): troca o botão "Trazer das contas" da janela Contatos por uma caixa "Obter os contatos das contas ao abrir o TeleZapp" (`GerenciadorContatos`, parâmetros `trazer_ao_abrir` e `ao_trazer_ao_abrir`; marcar também traz na hora). `nucleo/trazer_contatos.py` (`ler`, `salvar`: só entram os contatos que faltam, sem trocar nomes dados no TeleZapp). `Janela._ev_estado` chama `_trazer_contatos_da_conta` ao conectar: espera 8 s (a agenda do WhatsApp chega depois de conectar), lê numa thread e grava na tela (`wx.CallAfter`), depois `_renomear_pelos_contatos`. Só roda uma vez por conexão. Testes em `test_nucleo.py`. Não visto no app real; não confirmado que 8 s bastam para a agenda já estar sincronizada em conta recém-pareada.
- Grupos em Encaminhar e Nova mensagem (relato: "não aparecem os grupos"): causa provável, só havia grupos que já tinham conversa guardada (um grupo sem mensagem recebida não está na lista). `Provedor.grupos_da_conta()` (base vazia; WhatsApp usa `get_joined_groups` sem o pai das comunidades) e `Janela._grupos_das_contas` (cache de 2 min). `encaminhar.destinos(..., grupos=)` soma esses grupos; `encaminhar.categorias`/`do_modo`/`MODOS` e a caixa Mostrar em `DialogoEncaminhar` (tudo, só conversas, só contatos, só grupos). Nova mensagem: `nova_mensagem.MODOS`/`grupos_candidatos`, caixa Mostrar em `DialogoEscolherPessoa(com_modo=True)` (Nova chamada continua só com pessoas) e escolher um grupo abre a conversa com `tipo="grupo"`; ao encaminhar para um grupo sem conversa, a conversa criada também é de grupo (antes seria "privada"). O Telegram não implementa `grupos_da_conta` (já carrega todas as conversas). Grupo só de administradores, em que a conta não é admin, continua fora do Encaminhar (`somente_leitura`). Testes em `test_nucleo.py` e `test_janela.py`. Não visto no app real.
- Chamadas de vídeo do Telegram (pedido de 27/10/2026), pelo py-tgcalls 3.0.3, que codifica e decodifica sozinho: `chamadas_telegram.Motor` (`cameras`, `fluxo_com_camera` = `MediaStream(camera, audio_path=microfone)` com `VideoParameters(640, 360, 15)`, `fluxo_saida(.., camera)`, `filtro_quadros` = `stream_frame(INCOMING, CAMERA)`, `ouvir_pedidos`: evento bruto do Telethon `PhoneCallRequested.video`, que o py-tgcalls descarta); `ChamadasTelegram` (`ligar(.., video, camera)`, `atender(.., camera)`, `ligar_camera`/`desligar_camera` trocando as fontes com `play`, `_ao_quadro`, vigia de 3 s sem quadros = o outro lado desligou a câmera, `suporta_video`, `cameras`, `destino_video`); `ProvedorTelegram` repassa tudo; `midia/video.py`: `formato_do_quadro`/`quadro_para_rgb` (I420, BGRA ou RGB pelo tamanho) e `girar_rgb`. A janela é a mesma do WhatsApp. Testes em `test_chamadas.py` e `test_provedor_telegram.py` com um motor falso; o `Motor` real foi montado fora de uma chamada (fluxos com câmera e microfone, saída com câmera, filtro). **Não visto numa chamada de verdade**: falta confirmar o formato dos quadros recebidos (o log diz qual veio: `vídeo do Telegram: formato ...`), se o Telegram aceita passar a voz para vídeo trocando as fontes, a latência e o consumo.
- Selo de "IA" nas mensagens enviadas (novo relato de 27/10/2026: o destinatário voltou a ver o selo e os botões de avaliação): conferido que nenhuma DLL "trouxe a marca de volta". `shouldAddBotNode` (`goneonize/main.go`) é do neonize, sempre esteve nas DLLs e só é desligada por `NEONIZE_BOT_TAG=off`, que o TeleZapp definia só dentro de `ProvedorWhatsApp._uma_conexao`; a variável chega ao Go (conferido com `GetEnvironmentVariableW`). Reforço: (1) `build.ps1` troca o padrão da DLL para DESLIGADO (`return isPrivate && NEONIZE_BOT_TAG == "on"`), então o selo não depende mais da variável; (2) `provedores/whatsapp.py` define a variável ao carregar o módulo, além de a cada conexão; (3) o log diz `selo de IA nas mensagens enviadas: desligado`. Teste em `test_abertura.py`. A correção original saiu na 2026.10.24.2: quem manda com versão anterior ainda dá o selo. DLL nova em `neonize-build\saida\chamadas` (ainda não no venv, que estava em uso).
- Busca por critérios (pedido de 27/10/2026): `nucleo/busca.py` (`Criterios`, `buscar`, `Achado`, listas de opções, `ler_data`, `ler_numero`, `resumo`) sobre `Banco.buscar_mensagens` (SQL para conta, serviço, tipo e situação da conversa, quem enviou, data, duração, tamanho e estado de envio; o texto sem maiúsculas e acentos, o nome da conversa e do autor, o tipo "enquete" e as marcas de `extras` são conferidos em Python; lê texto, legenda, nome do arquivo, transcrição ou descrição de IA e opções de enquete; conversas trancadas só com `incluir_trancadas`, que a janela liga quando o código secreto foi digitado). `interface/busca.py` (`DialogoBusca`, uma caixa de marcar por critério que libera os campos dele, resultados numa lista, Enter ou Ver na conversa). Janela: botão `botao_busca` entre o campo de busca e o Sair, item de menu `busca_criterios` (sem tecla de fábrica), `_busca_por_criterios` (lembra `_ultima_busca`) e `_ver_na_conversa`. Testes em `test_busca.py` (18, com banco real) e `test_janela.py`; a janela foi montada e usada com o wx de verdade num banco temporário. Não vista no app real com NVDA.
- Queda ao abrir com mais de uma conta do WhatsApp (visto em 27/10/2026, 14:50, com tres contas; o `falha-nativa.log` novo mostrou `fatal error: concurrent map writes` em `main.Neonize`): o Python chama `Neonize()` de uma thread por conta, e o neonize escreve nos mapas globais `clients`, `StopSignal` e `eventChannel` sem trava; duas contas abrindo juntas derrubam o processo sem erro do Python. `fontes/chamadas/mapas.go` (`mapasMu`) e o `build.ps1` trocam essas escritas e os `delete` por escritas entre `Lock`/`Unlock` (docs/neonize/chamadas-mapas.go, build-chamadas.ps1). Leituras concorrentes com uma escrita continuam possíveis, mas a janela é de nanossegundos. Provavelmente é também a causa do relato do José Gabriel (abre e fecha em 1 s, funcionou depois de apagar as contas), ainda não confirmado. DLL nova instalada no venv; precisa ir no próximo executável.
- Alt+E liberado (pedido): o botão Enviar perdeu a tecla de acesso ("Enviar", sem "&") e `Alt+E` saiu das combinações reservadas de `nucleo/atalhos.py`; Control Enter (e Enter, conforme a opção) já enviam. Alt+E agora pode ser dado a qualquer função em Configurações, Atalhos. Testes em `test_atalhos.py` e `test_janela.py`.
- Retorno da nossa voz que chega do outro lado (o Valmir usa mesa de som com retorno; o usuário usa fone): `midia/eco.CancelaRetorno` é o `CancelaEco` com os papéis trocados (referência = o que enviamos, "microfone" = o que recebemos, sem redução de ruído), ligado em `_enviar` (`_avisar_retorno`) e `_receber` (`_sem_retorno`) de `chamadas_whatsapp`; só troca o som quando a medida achou eco claro (`CancelaEco.ecoando`, correlação >= 0,4), senão a voz dele passa como veio. Opção `chamada_retorno` (marcada). O log ganha `retorno da chamada: {... ativo ...}` a cada 5 s. Testes em `test_eco.py` (redução com WebRTC real, retorno de 500 ms) e `test_chamadas_whatsapp.py`. Não ouvido numa chamada real.
- Eco que volta do outro lado (relato 27/10 12:04, "eu me escutei"): o log da chamada (`eco da chamada`) ganha `eco_do_outro_lado` e `eco_do_outro_lado_atraso_ms`, a correlação entre o que ENVIAMOS e o que RECEBEMOS (`CancelaEco.diagnostico`; `_hist_saida` guarda 3,5 s). No log desse dia o eco local ficou em 0,01 a 0,15 sem atraso estável, ou seja, o retorno não vinha do nosso microfone. Teste em `test_eco.py`. Só registro; nada cancela esse eco ainda.
- Chamadas de vídeo do WhatsApp (pedido de 27/10/2026; antes ficavam fora do escopo por parecerem caras de fazer). DLL: `docs/neonize/chamadas-calls_video.go` (novo) e `chamadas-calls.go` (ganchos `ligarVideo`, `discar`, `incoming` com `video`) vêm do patch 0008 do WinZapp (GPL-3), que aplicou limpo no nosso `calls.go`; exporta `CallDialWith`, `CallGroupDial` (sem uso), `CallVideo`, `CallWriteVideo`, `CallReadVideo`, `CallInfo` e os eventos `video` e `keyframe`; `build.ps1` copia o arquivo novo. O meowcaller da nossa cópia já tinha o vídeo. Python: `midia/video.py` (`Camera` pelo DirectShow do PyAV, `Codificador` libx264 baseline 10 quadros/s com SPS/PPS em cada quadro-chave e sem os delimitadores, `Decodificador` H.264 -> RGB, `listar_cameras`, tudo sem ffmpeg externo); `chamadas_whatsapp.Ponte` (`ligar(video)`, `video`, `escrever_video`, `ler_video`) e `ChamadasWhatsApp` (`ligar(video, camera)`, `atender(camera)`, `ligar_camera`, `desligar_camera`, pedido de vídeo do outro lado aceito na hora, `destino_video`); `EstadoChamada` e `nucleo.chamadas.Chamada` ganham `video`, `camera`, `video_remoto`, `suporta_video`; janela da chamada com `VistaVideo` (640x360), botão e lista de câmeras; menu Chamadas, "Ligar com vídeo" e "Ligar ou desligar a câmera"; opção `video_camera_ao_atender` (desligada) e `chamada_camera`. Testes em `test_chamadas_whatsapp.py`, `test_janela.py`; round trip do codec e listagem da câmera conferidos à mão; a câmera real, a DLL com um par e a imagem na janela NÃO foram vistos em chamada de verdade.
- Saída dos sons de aviso (pedido): `Dispositivos de som` ganha a lista "Saída dos sons de aviso do TeleZapp" (`notificacao_saida`, vazio = padrão do Windows; `midia/dispositivos.notificacao()`/`indice_da_notificacao()`, `definir(..., notificacao=None)`, `ui_dispositivos.escolher` devolve `(mic, saida, aviso)`). `fala.bipe`: os arquivos de som vão para o dispositivo (`sd.play(device=)`) e os sons padrão, que eram `winsound.Beep` (só tocam no padrão do Windows), passam a ser sintetizados (`NOTAS`, `_onda`) e tocados no dispositivo quando há um escolhido; sem escolha, nada muda. Testes em `test_sons.py` e `test_janela.py`. Não ouvido em hardware real.
- Modo de seleção: atalhos e itens de menu de conversa (`_marcar_conversa_lida`, `_arquivar_conversa`, `_fixar_conversa`, `_silenciar_conversa`, `_apagar_conversa`) e de mensagem (`_favoritar_mensagem`, `_apagar_mensagem`, `_copiar`, `_encaminhar`) chamados sem item explícito, com a lista em foco e itens marcados, delegam a `_massa_conversas`/`_massa_mensagens` (`_em_massa_conv`, `_em_massa_msg`). Sem marcas, nada muda. Responder, editar, reagir, detalhes e abrir mídia continuam de um item só. Testes em `test_janela.py`. Não visto no app real.
- Registro da abertura (relato de abrir devagar ou fechar sozinho): `__main__` grava `ambiente:` (Windows, Python, empacotado ou código, pasta de dados, argumentos), `abertura: <etapa> (N s desde o início)` para componentes carregados, aplicativo wx, banco aberto, janela criada e janela mostrada, e o que acontece quando já há outro TeleZapp aberto; `biblioteca do WhatsApp carregada em N s` (neonize); `o Windows está encerrando a sessão`; `fechando a janela (pedido do Windows | da pessoa ou do programa)`; erro não tratado em thread (`threading.excepthook`). A saída de erro do Windows (`SetStdHandle`) passa a ir para `falha-nativa.log` e o Go roda com `GOTRACEBACK=all`: no relato de abrir e fechar em 1 s o log para logo depois do aviso do ffmpeg, ao conectar o WhatsApp já pareado, e uma falha fatal do Go escrevia só na saída de erro do Windows, que sem terminal se perde (`redirecionar_erro_nativo`). A marca `sessao-aberta` agora guarda a hora do último sinal (atualizada a cada 30 s); se a vez anterior não fechou, o aviso diz quando foi o último sinal e se o Windows foi religado depois (`tempo_ligado`, GetTickCount64; com a inicialização rápida o contador pode não zerar). Falha ao montar a janela (banco, janela, contas) agora grava o erro e mostra uma caixa, em vez de sair em silêncio. Testes em `test_abertura.py`. Não visto no app real.
- Corrigido: a janela de escolher o atalho recebia `self.fala` (objeto) onde esperava uma função e dava `'Fala' object is not callable` a cada tecla (log da 26.0); a combinação era guardada mas nada era falado. `configuracoes._atalhos_alterar` passa uma função.
- Registro para os relatos pós-26.1: `atendendo a chamada: janela visivel/minimizada/ativa`, `atalho global X registrado` / `apertado` e, na DLL das chamadas, `relay rx count` a cada 5 s por 40 s (`docs/neonize/mc-whatsmeow-relay-rx-log.diff`). Causas dos relatos (chamada recebida sem áudio; atalho global que não traz a janela) não confirmadas.

## 2026.10.26.1

- Autoria: "Contribuidores do TeleZapp" virou "Fábio Scheffer Moraes" nos cabeçalhos de copyright de todos os arquivos, no README, nos metadados do Windows (`CompanyName`, `LegalCopyright` em `ferramentas/empacotar.py`), no `Publisher` do desinstalador (`nucleo/instalacao.py`) e no rodapé do guia e das novidades ("Desenvolvido por Fábio Scheffer Moraes"). Quem já instalou continua com o Publisher antigo até reinstalar ou atualizar.
- Opção `seq_acompanhar` (Mídias, desligada): na sequência de áudios sem janela, `_tocar_proximo_audio` chama `Janela._acompanhar_audio`, que passa a seleção da lista de mensagens para o áudio que vai tocar (`selecao_automatica = False`, sem `SetFocus`), só se a conversa dos áudios está aberta. O primeiro áudio (o da tecla) não muda nada. Entra sozinha na janela de configurações por estar em `config.OPCOES`. Teste em `test_janela.py`. Não visto no app real; se o leitor de tela não ler a troca de seleção com o foco fora da lista, é o esperado (só a seleção muda).
- Gravar pelo atalho (`Janela._gravar_rapido`) não fala mais "Gravando. Aperte ... de novo para parar e enviar. Esc descarta." ao começar (pedido): só o bipe de `gravando` e a barra de status. Continua falado o aviso de que não há microfone (gravar som e microfone sem microfone), porque muda o que sai na gravação. Pausar, continuar, parar e descartar seguem falando. Teste em `test_janela.py`. Não visto no app real.
- Segundo plano fora do Alt+Tab (pedido): ao fechar com "Continuar em segundo plano" (ou pelo item do menu), a janela continuava aparecendo no Alt+Tab. Novo `interface/segundo_plano.py`: `tirar_do_alttab(hwnd)` esconde a janela, põe `WS_EX_TOOLWINDOW` (e tira `WS_EX_APPWINDOW`), mostra minimizada sem ativar e pede o botão da barra de tarefas com `ITaskbarList.AddTab` (ctypes); se o shell recusar, desfaz o estilo (melhor ficar no Alt+Tab do que sumir da barra). `Janela._tirar_do_alttab` chama depois do `Iconize`; `_mostrar_da_bandeja` (ícone, atalho global) e o evento de restaurar da barra de tarefas (`_ao_minimizar`) chamam `_voltar_ao_alttab`. Minimizar pelo botão da janela não muda. Testes só da lógica (estilos e chamadas); a mágica de verdade, botão na barra sem Alt+Tab, NÃO foi vista: o teste automático foi bloqueado e `AddTab` em janela de ferramenta é conhecido de leitura, não confirmado aqui.
- Corrigido (relato): mensagem com link de convite de grupo sem texto, só com a prévia (visto numa mensagem enviada do celular: texto vazio, "Endereço da prévia" com o link), não ganhava o botão de entrar. `nucleo/grupo.entradas_de_links` (regex e rótulos, antes em `whatsapp.py`) agora também lê o `matchedText` da `extendedTextMessage` na chegada, e `Janela._acoes_da_mensagem` soma aos botões guardados os do texto, dos links e da URL da prévia, o que vale também para mensagens já recebidas. `Janela._sem_links_de_convite` tira dos botões de link (Tab) e da lista de links dos detalhes o link que já tem botão de entrar, já que abri-lo só levaria ao navegador. Teste em `test_janela.py`. Por que o texto veio vazio não foi investigado. Não visto no app real.
- Botão de entrar também para canais do WhatsApp: `RE_CANAL_WHATSAPP` (`whatsapp.com/channel/CODIGO`) em `entradas_de_grupo` gera a ação `entrar` com `modo: "canal"` ("Seguir o canal (link)"). `previa_do_convite` chama `_previa_do_canal` (`get_newsletter_info_with_invite`: nome, seguidores, descrição; já participa se o papel é seguidor, administrador ou dono) e `entrar_no_grupo` chama `_seguir_canal` (`follow_newsletter(info.ID)`). A prévia de grupo agora devolve `tipo` (`comunidade` quando `GroupParent.IsParent`) e `_confirmar_entrada` pergunta "Entrar na comunidade X?" / "Entrar no canal X?" ("N seguidores"). Grupos e comunidades já tinham botão pelos links `chat.whatsapp.com`; o Telegram já tratava convites e `t.me/nome` (grupo ou canal). "Entrar em um grupo por link..." (menu Novo) passa a aceitar link de canal por `nucleo.grupo.acao_do_link`. O canal seguido só aparece na lista quando chega mensagem dele (não confirmado). Testes em `test_provedor_whatsapp.py` e `test_nucleo.py`. Não visto no app real.
- Detalhes da conversa: botão "Mensagens favoritas" (pessoa, grupo e canal; `ControleDetalhes.favoritas`, `nucleo.detalhes.favoritas`). Lista da mais nova para a mais antiga com o menu Ver na conversa (Enter), Desfavoritar (`_desfavoritar`, usa a cópia aberta em `jan.cache` e `_favoritar_mensagem`, então avisa a conta no WhatsApp) e copiar. Sem favoritas, fala e avisa. Teste em `test_janela.py`. Não visto no app real.
- Tipo de conversa "Com mensagens favoritas" (`FILTROS_TIPO`, depois de Fixadas): `passa_filtro(..., com_favoritas)` recebe as chaves de `Banco.conversas_com_favoritas()`, consultado em `_ordenar` só com esse filtro ativo; `_favoritar_mensagem` refaz a lista se o filtro está ativo. Arquivadas e trancadas seguem fora, como nos outros tipos. Marcas feitas no celular entram na próxima vez que a lista é refeita. Testes em `test_janela.py` e `test_nucleo.py`. Não visto no app real.

## 2026.10.26.0

- Cancelamento de eco e redução de ruído nas chamadas de voz do WhatsApp (pedido; referência: o WinZapp, que já faz isso, GPL-3.0). `midia/eco.py` (`CancelaEco`) passa o microfone por `livekit.rtc.AudioProcessingModule` (AEC3 e supressor do WebRTC, mais filtro passa-alta; sem controle automático de ganho), a 16 kHz direto (quadros de 10 ms = 160 amostras, sem reamostrar) e entrega como referência o que foi para o alto-falante. Escrito para o fluxo do TeleZapp, só a ideia de segurar a referência veio do WinZapp: o AEC3 só acha eco até ~0,5 s, então a cada 1 s `acoplamento` (correlação cruzada a 8 kHz, janela de 2 s, atraso até 1,5 s) mede o atraso do eco e, passando de 350 ms, a referência é segurada para o eco chegar ~150 ms depois dela (histerese de 50 ms; duas medidas seguidas têm de concordar em 20 ms). Em `chamadas_whatsapp.py`: `_Ligacao.eco` criado em `_iniciar_audio` (opções `chamada_eco` e `chamada_ruido`, Mídias, ligadas), `_enviar` passa o quadro por `_sem_eco` (mudo continua mandando silêncio; qualquer erro manda o quadro como veio e desliga o eco da chamada), `_receber` entrega o quadro tocado como referência, trocar microfone ou saída chama `reiniciar()`. Log a cada 5 s: eco na entrada, atraso e eco na saída. Medido com sinal sintético: 38 dB de redução com eco a 60 ms e ~60 dB com retorno a 800 ms (referência segurada 670 ms). Sem teste com voz real. Dependência nova `livekit>=1.1,<2` (a roda traz a `livekit_ffi.dll`, 25 MB), `collect_all("livekit")` no `TeleZapp.spec` (não empacotado ainda: conferir se a DLL entra), linha em `docs/licencas-de-terceiros.md`. Testes em `test_eco.py` e `test_chamadas_whatsapp.py`.
- Opção `manter_apagadas` (Privacidade, desligada): `modelos.MANTER["apagadas"]` (ligado pela janela em `_carregar_limites_ia` e em `_aplicar_opcao`). Ligada, o REVOKE do WhatsApp (`_tratar_alteracao`) e o evento de apagadas do Telegram (`_ao_mensagens_apagadas`), quando a mensagem não é minha, só põem o extra novo `apagada_pelo_autor` (o texto, links e a mídia ficam; a linha ganha "(apagada pelo autor)") e publicam `MensagemAtualizada(..., "apagada")`; `_ev_atualizada` não descarta a mídia nesse caso. Mensagem minha apagada em outro aparelho segue o caminho de antes. No Telegram o evento não diz quem apagou, então qualquer mensagem de outra pessoa apagada fica guardada. Não recupera o que já foi apagado. Testes em `test_provedor_whatsapp.py` e `test_provedor_telegram.py`. Não visto no app real.
- Resposta em particular a mensagem de grupo (WhatsApp): `Janela._original_de_grupo(x)` acha, pelo `resposta_a`, a mensagem em conversa de grupo da mesma conta (só para conversa privada; cache `_de_grupo`, limpo ao abrir conversa); `_resposta_de_grupo` monta "Ana, no grupo Turma: \"texto\"" para `formatar(respondida=...)`. `_ir_para_respondida` sem original na conversa abre o grupo (`_ir_para_mensagem_do_grupo`, `_mostrar_mensagem`) e guarda `(conversa, id)` em `volta_para`; `_voltar_da_respondida` aceita essas entradas e reabre a conversa de origem. Telegram fica de fora (não há resposta a outro chat). Teste em `test_janela.py`. Não visto no app real.
- Slot de atalho "Copiar a transcrição ou descrição" (`copiar_ia`, menu Mensagens, sem tecla de fábrica): `Janela._copiar_texto_ia` copia `extras["ia"]["texto"]` direto, avisando "Transcrição copiada." ou "Descrição copiada."; sem texto da IA, bipe de erro e "Esta mensagem não tem transcrição nem descrição.". `_copiar_texto` ganhou o parâmetro `aviso`. Teste em `test_janela.py`. Não visto no app real.
- Enter num áudio sem janela: com `falar_quem_toca` desmarcada, `anuncio_reproducao` devolve vazio (antes "Tocando." e a velocidade) e a janela/`comecar` do visualizador só fala se houver texto; na sequência continua "Próximo áudio." só quando a opção da sequência pede. Pausar e continuar com Enter continuam falando "Pausado" e "Tocando". Quem tem a opção marcada no config.json (o responsável tinha) precisa desmarcá-la. Testes em `test_janela.py`.
- Atalhos globais para chamadas: `Janela._ids_globais` (um id de `RegisterHotKey` por função em `ATALHOS_GLOBAIS`) com as funções novas `atender_global` e `recusar_global` (categoria Chamadas, sem tecla de fábrica) além de `mostrar_janela`. `Janela._ao_atalho_global` trata `EVT_HOTKEY` pelo id: `atender_global` só age com a chamada `TOCANDO` ("Nenhuma chamada tocando." senão); `recusar_global` serve também para desligar: com qualquer chamada ativa chama `_desligar_chamada` (recusa se toca, desliga se em curso), senão fala "Nenhuma chamada em andamento.". Combinação já usada por outro programa: o aviso falado diz qual função ficou sem a tecla. Teste em `test_janela.py`. Não visto no Windows real.
- Ocultar contatos duplicados (pedido): opção `ocultar_contatos_duplicados` (Interface, ligada por padrão) e caixa na janela Contatos (`GerenciadorContatos`, parâmetros `ocultar_duplicados` e `ao_ocultar`). `nova_mensagem.sem_duplicados(itens, dados)`: mesma conta e mesmo telefone (do campo ou do endereço @s.whatsapp.net) é a mesma pessoa; sem telefone (só @lid), vale o mesmo nome sem acento nem maiúsculas, mas só some se esse nome já aparece com telefone ou antes dele; nomes iguais com telefones diferentes ficam. Na janela Contatos (todas as contas juntas) usa `entre_contas=True`: o grupo é ignorado e a mesma pessoa em várias contas aparece uma vez (a que fica é a primeira por nome; Editar muda só essa cópia). Aplicado também aos resultados de `buscar` de Nova mensagem e Nova chamada. Só esconde na lista, não apaga nada do banco. Teste em `test_nucleo.py`. Não visto no app real.
- Nova mensagem e Nova chamada: com mais de uma conta, o foco começa na escolha do serviço / conta (antes ia direto para o campo Para). Com uma conta só continua no Para.
- Corrigido (relato): conversa com contato salvo mostrava mensagens da mesma pessoa com autores diferentes, uma com o nome de perfil e outra com o telefone. Causa: em conversa privada o autor é gravado na chegada da mensagem (`converter` usa `Pushname`; o telefone vinha de `conv.nome` quando ainda não havia nome) e nunca passava pelo nome do contato salvo; `_salvar_pessoa`/`_renomear_pelos_contatos` renomeavam só a conversa, não as mensagens (só `_salvar_autor`, de grupo, mexia nelas). Agora `modelos.nome_para_autor(conv)` (nome da conversa, que já prefere o contato salvo; vazio se for só telefone ou "Contato sem nome", para não apagar um nome de perfil) e `modelos.alinhar_autores`: o WhatsApp grava `nome_para_autor(conv)` nas mensagens recebidas (ao vivo, não decifradas e histórico); a janela alinha ao abrir a conversa (cache e banco, `banco.renomear_autor_da_conversa`), em cada mensagem nova (`_ev_nova`) e ao salvar/renomear contato (`_renomear_pelos_contatos`). Vale também para o Telegram, que usa o mesmo caminho da janela. Não cobre contato salvo sob um id diferente do da conversa (ex.: só pelo LID) quando `nome_de_contato` não o acha. Testes em `test_nucleo.py`.

## 2026.10.25.1

- Chamada que "simplesmente é interrompida" sem padrão (relato, e visto no log do responsável, 19:27 a 19:30): a chamada começa boa, com cerca de 16,6 quadros por segundo nos dois sentidos e o aceite automático funcionando, e de repente nada mais chega do outro lado enquanto o nosso microfone segue enviando. No log aparece uma vez `audio RTP did not match an authenticated active participant` no instante em que os quadros param (por exemplo aos 60 s, 914 para 924 quadros, e numa chamada anterior aos 12 s, 76 quadros), com o mesmo SSRC que antes autenticava. O meowcaller só registra a primeira falha. Hipótese ainda não confirmada: o estimador do ROC do SRTP (`RecvRocTracker`) perde o passo (rolagem da sequência de 16 bits, que acontece num momento aleatório porque a sequência inicial é aleatória) e todo pacote seguinte falha. Mudança em `mc-whatsmeow` (`session.go`, `srtp/e2e.go`; diff em `docs/neonize/mc-whatsmeow-roc-resync.diff`): quando a autenticação falha, `UnprotectAudio` tenta ROC+1, ROC-1 e ROC+2; o que autenticar vale (a etiqueta garante que não é pacote falso), o estimador é ressincronizado (`Resync`) e o log diz `recv roc resynchronized`. Se nenhum autenticar, registra `unprotect: authentication failed` com `seq`, `roc_estimado`, `roc_atual`, `ultima_seq` e a contagem (3 primeiras e depois a cada 200), para ver se é mesmo o ROC. Não visto ao vivo.
- Banco de sessão do WhatsApp deixa de dar `database is locked` (logs do outro lado: dezenas de erros logo após parear e até ligar falhando com `encrypt callKey ... database is locked`). A DLL abria o SQLite só com `_foreign_keys=on`: várias goroutines do whatsmeow leem e depois escrevem na mesma transação, o que trava na hora (sem esperar) em modo de diário comum. O `build.ps1` (variante chamadas; cópia em `docs/neonize/build-chamadas.ps1`) troca o DSN de `getDB` por `_foreign_keys=on&_journal_mode=WAL&_busy_timeout=30000&_synchronous=NORMAL&_txlock=immediate`. Teste isolado com o mesmo driver (12 gravadores, 150 transações cada): 1177 falhas em 5,3 s antes; 0 falhas em 0,26 s depois. O banco passa a criar `-wal` e `-shm` ao lado (o backup do TeleZapp já ignora esses). Quem já tem sessão guardada muda para WAL na primeira abertura; voltar à DLL antiga continua lendo o arquivo.
- Chamada entre dois TeleZapp (logs dos dois lados, 25/10, 21:56 a 21:59 dele): quem atendia ficava em chamada mas quem ligou seguia "chamando", sem som dos dois lados. Causa: o meowcaller atende só quando recebe o `<mute_v2>` de quem ligou (`engine.go`, `onCallRaw`), e como chamador ele nunca envia `<mute_v2>` (`BuildMuteV2` não é usado). O `<accept>` nunca saía, então o chamador não recebia o aceite (sem `sinal: ACEITE`), não trocava a chave de mídia para o aparelho que atendeu (`peer SRTCP failed authentication`) e não abria o microfone (`quadros do microfone=0`). Correção na cópia local do meowcaller (`mc-whatsmeow/engine.go`, diff em `docs/neonize/mc-whatsmeow-aceite-sem-mute.diff`): `answer()` agenda, 2 s depois do Atender, o `sendAccept` se o `<mute_v2>` não chegou (`sendAccept` só envia uma vez). Com celular como chamador nada muda, o `<mute_v2>` dele chega antes. Não resolve por si só o caso de o TeleZapp ligar para um celular; isso ainda precisa do teste com o aceite do celular. Não visto ao vivo.
- Corrigido (erro meu na primeira 25.1 de teste, visto no log de uma testadora): "Conectando" e a espera de 20 s pelo som valiam já na fase 3 do meowcaller, mas na chamada de **saída** essa fase vem quando o relay é alocado, com o outro celular ainda tocando (`engine_media.go`, `maybeStartMedia`). O TeleZapp desligava a chamada 20 s depois de ligar, antes de a pessoa atender. Agora a DLL avisa `accepted` quando o meowcaller dispara `OnPeerAccept` (o outro lado atendeu de verdade) e `ChamadasWhatsApp` só mostra Conectando, abre o som e arma a espera nesse momento; na chamada de entrada continua valendo a fase 3 (ela só vem depois do nosso Atender). A DLL também registra o que o WhatsApp mandou (`sinal: oferta/pré-aceite/ACEITE/transporte/recusada/encerrada`, com o aparelho de origem) via `AddEventHandler`, para ver se o aceite chega mesmo quando o celular conta os segundos. Testes: `test_saida_que_so_esta_tocando_nao_e_encerrada_pelo_vigia`, `test_entrada_atendida_sem_som_encerra_explicando`.
- Detalhes da conversa: botão "Limpar a conversa..." (pessoa, grupo e canal; `ControleDetalhes.limpar`). Abre `DialogoLimpeza` com `so_a_conversa=(conta, conversa, nome)`: o título traz o nome, os campos Conta e Conversa não aparecem (o filtro fica preso à conversa) e o resto é igual à limpeza geral (só mídias ou mensagens com as mídias, tipo, dias, tamanho, manter favoritas, total antes de confirmar). Depois de limpar, `Janela._limpar_conversa_com_opcoes` devolve True e os detalhes são refeitos. Não substitui "Limpar conversa" do apagar grupo (`_limpar_conversa`, que apaga tudo sem perguntar filtros). `testes/wx_falso.py` ganhou `SpinCtrl` e `CheckBox`. Testes em `test_limpeza_conversa.py` e `test_janela.py`.
- Chamada de saída do WhatsApp que a outra pessoa atende mas o som nunca começa (relatos de dois usuários: o celular do outro lado conta os segundos e o TeleZapp segue "chamando", sem som dos dois lados; quando o celular liga para o TeleZapp funciona). O meowcaller só marca a chamada como ativa (`ready`) ao decodificar o primeiro RTP vindo do relay (`engine_media.go`, "first RTP decoded"); o `peer_accept` só leva a fase `Connecting`, que a DLL já publicava como evento `state` e o Python ignorava. Agora `ChamadasWhatsApp._tratar` registra as fases no log, mostra CONECTANDO assim que o outro lado atende (`_ao_conectar`), abre microfone e alto-falante nesse momento (`_iniciar_audio`, uma vez por chamada) e vigia: sem `ready` em `ESPERA_AUDIO_S` (20 s) encerra com FALHA e a explicação `SEM_AUDIO` (rede ou firewall bloqueando o áudio). Vale também ao atender uma chamada recebida (`atender`). A causa de o som do relay não chegar não foi achada: o log do meowcaller (`peer accepted outgoing call`, `rekeyed media to answering device`, `first RTP decoded`) fica mudo porque o logger dele é `zerolog.Nop()`; para vê-lo seria preciso reconstruir a DLL passando `meowcaller.WithLogger` (feito em `instalarChamadas`). Testes em `test_chamadas_whatsapp.py`. Não visto no app real.

- DLL das chamadas (`docs/neonize/chamadas-calls.go`, recompilada em `C:\github
eonize-build`): o log do meowcaller, que era `zerolog.Nop()`, passa a ir para o log do cliente (`whatsmeow.Client.Chamadas`, nível WARN para aparecer no `telezapp.log`, prefixo `chamadas:`; mensagens repetidas só nas 8 primeiras vezes e depois a cada 200). Linhas novas do próprio `calls.go`: chamada criada, cada fase com o tempo, "som do outro lado chegou (primeiro RTP)", encerrada com o motivo, e a cada 5 s os quadros que passaram do outro lado e do microfone (`recebidos`/`enviados`), mais `ligando para…` e as falhas de ligar e atender. Telefones e endereços saem só com os 4 últimos dígitos (`mascarar`). `registrar` usa um mapa `chamadasLogs` sob `chamadasMu` (não toca no mapa `clients`, que o Go não deixa ler e escrever ao mesmo tempo). Só a DLL muda; os `.py` saem iguais. Compilou e carrega, com as mesmas exportações; nenhuma chamada real foi feita com ela.

## 2026.10.25.0

- Tipo de conversa "Menções e respostas" (`FILTROS_TIPO` "citacoes", depois de Não lidas): grupos com mensagem não lida que me menciona ou responde a uma mensagem minha. `Conversa.citacoes` (coluna nova `conversas.citacoes`, esquema 12) com `contar_nova(cita_voce)` (zera a contagem velha quando não havia nada por ler) e `tem_citacao_nao_lida()` (`min(citacoes, nao_lidas) > 0`, então não precisa zerar nos vários lugares que zeram `nao_lidas`). WhatsApp: `_responde_a_mim` marca `citou_voce` também nas respostas (antes só as menções ficavam marcadas; a resposta só era vista pela janela na hora do som) e conta no `_ao_mensagem`. Telegram: conta ao vivo e, ao atualizar as conversas, usa o maior entre o guardado e `unread_mentions_count` do diálogo (cobre as de antes). Sem retroativo no WhatsApp, a pedido. Testes em `test_nucleo.py`. Não visto no app real.
- Segundo plano: `Janela._esconder_na_bandeja` passa a `Iconize(True)` em vez de `Hide()`, então o botão fica na barra de tarefas (o ícone da bandeja continua). `_mostrar_da_bandeja` já restaurava janela minimizada. Abertura com `--segundo-plano` faz `Iconize(True)` antes de `Show()` (em vez de não mostrar), para abrir minimizada sem tomar o foco; isso não foi visto no Windows real. Menu Ferramentas: "Minimizar a janela e continuar em segundo plano". Textos da opção `segundo_plano`, do guia e das novidades ajustados. Substitui o comportamento anterior (sem opção para os dois).
- Apagar a conversa de um grupo e escolher "Apagar aqui e no celular": o aviso `deleteChat` faz o celular tirar a conta do grupo, e o diálogo não dizia isso. `Janela._apagar_conversa` agora mostra, só para `conv.tipo == "grupo"`, um segundo diálogo de alerta ("Apagar também no celular fará você sair do grupo X. Quer continuar?", Não é o padrão); Não cancela tudo, sem apagar nada. Conversas individuais ficam como estavam. Que o celular saia do grupo ao receber o `deleteChat` é o que o responsável observou; o código não chama `leave_group` nesse caminho. Não testado no app real.

- Lista de conversas: quinto item, "Reações às minhas mensagens" (`lista_conversas.ITENS` "reacoes", desligado por padrão). `Janela.reacoes_novas` (chave -> contagem, só na sessão) soma em `_ev_atualizada` cada reação de outra pessoa a uma mensagem minha em conversa que não está aberta, e zera em `_abrir_conversa`. `rotulo(c, valor, previa, reacoes)` mostra "1 reação nova à sua mensagem" / "N reações novas às suas mensagens". `normalizar` passa a pôr desligado o item novo que falta no valor guardado (quem já tinha a lista salva não vê a linha mudar). Testes em `test_lista_conversas.py` e `test_janela.py`. Não visto no app real.
- Lista de conversas: sexto item, "Quem reagiu às minhas mensagens" (`quem_reagiu`, desligado por padrão). `Janela.quem_reagiu` (chave -> [(quem, emoji)], uma entrada por pessoa, a última reação vale) é preenchida junto com `reacoes_novas` e zerada em `_abrir_conversa`. `texto_de_quem_reagiu`: "Ana reagiu com 👍", "Ana (👍) e Bia (❤) reagiram", com "e mais N" depois de três. `rotulo(..., quem_reagiu)`. Não visto no app real.
- Chamadas com o TeleZapp fora da janela (relato: atendida em segundo plano, as pessoas não se ouviam). Causa não reproduzida; hipóteses tratadas: (1) `midia/prioridade.py`: durante a chamada (`Janela._ev_chamada` → `chamada_em_curso(c.ativa)`) o processo sai do modo de eficiência/EcoQoS e do corte do relógio fino (`SetProcessInformation` `ProcessPowerThrottling`), pede `timeBeginPeriod(1)` e `SetThreadExecutionState` (o computador não suspende); as threads de som entram no grupo MMCSS "Audio" (`thread_de_audio`). Tudo em melhor esforço e só no Windows. (2) `chamadas_whatsapp`: microfone ou saída que não abre cai no padrão do Windows (`_abrir`); erro do som ou da DLL não encerra mais as threads (`LIMITE_DE_FALHAS` seguidas; antes um único `escrever_quadro` falho encerrava o envio para sempre, e uma exceção ao abrir deixava a chamada muda dos dois lados sem aviso); o log passa a dizer qual dispositivo abriu e quantos quadros foram enviados e tocados. Testes em `test_prioridade.py` e `test_chamadas_whatsapp.py`. Não visto no app real.
- Corrigido (relato): áudio ou mensagem de voz que o autor apagou para todos continuava tocando no WhatsApp. O evento de apagar (`REVOKE`) só limpava o texto e marcava `apagada`; o tipo continuava voz e o arquivo baixado ficava no disco, então Enter, Control O, a sequência de áudios e Control S ainda o abriam (só o menu de contexto olhava `apagada`). Agora `Janela._abrir_midia` recusa mensagem apagada ("Esta mensagem foi apagada pelo autor."), `_genero_ia` devolve vazio (sem transcrever ou descrever), `_tocar_proximo_audio` pula e `_salvar_midia` ignora. Ao chegar o evento (`_ev_atualizada`, motivo "apagada"), `_descartar_midia_apagada` para o áudio que toca dela e `limpeza.apagar_midia_da_mensagem` apaga o arquivo e a ficha da mídia, mantendo a mensagem marcada como apagada (sem registrar como "limpa"). No Telegram a mensagem apagada já saía inteira, com a mídia. Arquivos de mensagens apagadas antes desta versão ficam no disco, mas não abrem mais. Testes em `test_janela.py` e `test_limpeza.py`.

## 2026.10.24.2

- Corrigido: as mensagens enviadas no WhatsApp chegavam ao destinatário com o selo "IA" e botões de avaliação. O neonize põe o nó `<bot biz_bot="1"/>` em toda mensagem de conversa privada (`shouldAddBotNode`, em `goneonize/main.go`); `ProvedorWhatsApp._uma_conexao` agora define `NEONIZE_BOT_TAG=off` antes de criar o cliente, o que desliga o nó sem recompilar a DLL (a original 0.5.2 já tem a chave).
- Corrigido: Deixar de seguir e Silenciar o canal não faziam nada no Telegram. `ProvedorTelegram` não tinha `administrar_canal`, e o padrão de `Provedor` respondia que a conta não gerencia canais. Agora `_administrar_canal` usa `channels.LeaveChannelRequest` (ou `delete_dialog` fora de canais) e `account.UpdateNotifySettingsRequest`. Depois de deixar de seguir, `ControleDetalhes._manter_ou_apagar_canal` pergunta (Não é o padrão) se mantém o canal na lista ou apaga a conversa e as mensagens locais (`Janela._remover_conversa_local`). Teste com cliente simulado; não verificado com conta real.

## 2026.10.24.1

- Menu Ajuda: `pagina_projeto` (abre `PAGINA_DO_PROJETO`, o GitHub Pages do projeto) e `feedback` (abre `PAGINA_DE_RELATOS`, o formulário `site/relatar.html`), por `Janela._abrir_na_internet` (`webbrowser.open`; se não abrir, mostra o endereço). Slots de atalho sem combinação. Testes `test_menu_ajuda_abre_a_pagina_do_projeto_e_o_feedback` e `test_sem_navegador_o_endereco_e_mostrado`.
- Marcar a conversa como lida sem abri-la. `Janela._marcar_conversa_lida` (conversa em foco ou a do menu de contexto) e `_avisar_leitura`, que chama `marcar_como_lida` do provedor (o WhatsApp manda o recibo de leitura das últimas não lidas, como ao abrir) e zera `nao_lidas`; só avisa quando não há não lidas. Item "Marcar como lida" em `_opcoes_da_conversa` (antes de Arquivar), "Marcar N conversas como lidas" na seleção em massa (`_massa_conversas("lidas")`) e o slot de atalho `marcar_lida` no menu Conversas, sem combinação de fábrica. Testes `test_marcar_conversa_como_lida_*`, `test_menu_de_contexto_da_conversa_tem_marcar_como_lida`, `test_slot_de_atalho_de_marcar_como_lida_*`, `test_selecao_em_massa_marca_como_lidas`. Não visto no app real.
- Ferramentas de grupo do WhatsApp (auditoria contra o WinZapp: faltavam pedidos de entrada, foto do grupo, convite com QR Code, entrar por link digitado e adicionar uma pessoa a um grupo pela conversa dela). Provedor: `pedidos_de_entrada` (`get_group_request_participants` -> `[{id, nome, telefone, quando}]` do mais antigo ao mais novo), `responder_pedidos(cid, ids, aprovar)` (usa `client.update_group_request_participants(jid, [JID...], ParticipantRequestChange.APPROVE|REJECT)`, que só existe na DLL de teste `0.5.2-winzapp-teste.2`: sem a função (`hasattr`) a mensagem diz que precisa da DLL de teste nova; itens com `Error` na resposta são contados e a exceção vira "O WhatsApp não aceitou"), `foto_do_grupo` (`get_profile_picture` + download do endereço), `administrar_grupo(..., "foto", bytes)` (`set_group_photo`; a foto vem de `nucleo/perfil.preparar_foto`), `grupos_que_administro` (`get_joined_groups`, sem comunidades) e `administrar_grupo(..., "adicionar", "id@servidor")` (aceita o endereço da conversa, não só telefone). `_jid_do_convite` aceita `msg=None` para entrar só pelo código. Sinalizadores `PEDIDOS_DE_ENTRADA`, `FOTO_DO_GRUPO`, `LISTA_GRUPOS_ADMIN` e `ENTRA_POR_LINK` em `Provedor` (falso) e `ProvedorWhatsApp` (verdadeiro); o Telegram usa os padrões.
- Interface: `interface/grupo_extras.py` (`DialogoPedidos`, lista de seleção múltipla com Aprovar, Recusar e Atualizar; `DialogoConvite`, link, QR, copiar, salvar PNG e trocar) e `nucleo/grupo.py` (rótulos, `png_do_qr` com segno, `extensao_da_imagem`, `codigo_do_convite`). Detalhes do grupo: "Ver a foto do grupo" e, para administradores, "Pedidos de entrada"; Administrar grupo: "Link de convite e QR Code" (substitui "Link de convite" e "Revogar o link de convite", agora dentro da janela do convite), "Trocar a foto do grupo" e "Pedidos de entrada"; detalhes da conversa com uma pessoa: "Adicionar a um grupo". Menu Novo: "Entrar em um grupo por link" (`Janela._entrar_por_link`, sem atalho). Sem opção nova em `config.OPCOES`: nada aqui é ajustável. Testes: `test_grupo_extras.py`, `test_grupo_extras_janela.py` e `test_entrar_em_grupo_por_link_*` em `test_janela.py`; `wx_falso` ganhou `LB_EXTENDED`, `FD_*` e `SetName`. Não viável agora: modo de aprovação de entrada e "só administradores adicionam" (o `GroupInfo` do neonize não tem esses campos nem há função que os mude). Não verificado ao vivo.
- "Não consegui consultar o GitHub" agora diz o motivo (`atualizacao.motivo_da_falha`): limite de consultas do GitHub por endereço de internet (HTTP 403 ou 429, comum em rede compartilhada), certificado não confiável (data e hora do computador ou antivírus), tempo esgotado, DNS ou resposta inesperada; o log registra a causa. Quando a API recusa, `atualizacao._pelo_site` descobre a versão mais nova pelo endereço `releases/latest` do próprio site do GitHub (sem o limite da API) e monta os endereços do zip e do hash; as novidades dessa versão, nesse caso, só na página dela. Motivo: relato de um usuário da 2026.10.21.0 que não conseguia atualizar por Ajuda, Verificar atualizações ("não conectou ao GitHub"); a causa exata dele não foi vista.
- `ferramentas/publicar.py --publicar` cria a Release comum (`--latest`); `--prerelease` cria o pré-lançamento (antes era o contrário, com `--final`, que continua aceito e não faz nada).

## 2026.10.24.0

- Excluir conta: `DialogoContas._clicou_excluir` não desabilita mais Excluir e Renomear quando não sobra conta (fecha o diálogo antes), devolve o foco à lista quando sobra e `Janela._gerenciar_contas` põe o foco em `lista_conv` ao fechar; antes o foco ficava num botão desabilitado e o NVDA dizia "janela indisponível". Não verificado com leitor de tela.
- Atualização com "Continuar em segundo plano": `Janela._atualizacao_pronta` marca `_saindo` antes de `Close()` (senão `_ao_fechar` vetava e só escondia na bandeja, e `atualizador.aplicar` nunca rodava); desfaz a marca se a pessoa desistir de fechar.

## 2026.10.23.1

- IA de texto: tom, tradução e resumo das não lidas. `catalogo.TONS`/`IDIOMAS`; `prompts.TRADUZIR` e `_TOM` (o tom vale ao redigir); `preparar_texto`/`executar_texto`/`executar_texto_em_ordem` ganham `tom` e `destino`. Opção `ia_tom` (Inteligência artificial); `ia_idioma_traducao` guarda o último idioma. Janela: `_ia_redigir(escolher_tom=)`, `_ia_traduzir_caixa`, `_ia_traduzir_mensagem`, `_ia_resumir_nao_lidas` (usa `marcador_n` ou `nao_lidas`; só manual) e `_escolher_da_lista`; slots `ia_redigir_tom`, `ia_traduzir`, `ia_traduzir_msg`, `ia_resumir_nao_lidas`. Testes em `test_ia.py` e `test_janela.py`.
- IA para redigir, resumir e corrigir textos. Tarefa nova `texto` em `nucleo/ia/catalogo` (todos os provedores aceitam; `MAX_TOKENS`/`MAX_CARACTERES`/`MAX_ENTRADA_TEXTO`), `prompts.instrucoes_de_texto`/`pergunta_de_texto` (CORRIGIR, REDIGIR, RESUMIR_MENSAGEM, RESUMIR_CONVERSA; o texto é dado, não instrução), `provedores.montar_pedido_de_texto` (pedido só de texto nos cinco dialetos) e `servico.executar_texto`/`executar_texto_em_ordem` (mesma ordem, modelos alternativos e passagem ao próximo provedor da mídia). `Janela._ia_texto` junta ordem, chave, consentimento próprio (`ia_consentimento_texto`, separado do de mídia) e thread; corrigir e redigir trocam o texto da caixa (`SelectAll` + `WriteText`, Control Z desfaz) e, se a caixa mudou durante a espera, mostram o texto numa janela; redigir leva as últimas `MENSAGENS_DE_CONTEXTO` (12) como contexto; resumir mostra em `dialogos.mostrar_texto`. Submenu Mensagem, Inteligência artificial, com slots `ia_corrigir`, `ia_redigir`, `ia_resumir_msg` e `ia_resumir_conv` sem atalho. Testes em `test_ia.py` e `test_janela.py`. Não testado com um provedor real.
- Opção `digitar_na_lista` (Interface; `pular` padrão, `campo`): `Janela._digitou_na_lista` (EVT_CHAR das listas de conversas e mensagens) com `campo`, leva o caractere imprimível sem Control/Alt ao campo de busca (conversas) ou à caixa de mensagem (mensagens, com conversa aberta e fora do modo de seleção); senão faz `Skip` e vale a busca por inicial do Windows. Testes `test_digitar_na_lista_*`. Não verificado ao vivo com leitor de tela.
- Rótulo "Salvar cópia da mídia..." trocado por "Salvar a mídia em um arquivo..." (menu Mensagem, contexto, detalhes e visualizadores), para não confundir com copiar.
- Dispositivos de som (saída e microfone) para tocar, gravar e ligar. `midia/dispositivos.py`: a escolha vive em um estado comum (`definir`, `microfone`, `saida`; vazio = padrão do Windows), a lista vem do sounddevice na API padrão sem o "Mapeador de som" e sem repetidos (`listar`), e `parecem_o_mesmo` casa um nome cortado com o completo (o Windows corta em 31 letras; a soundcard e o NTgCalls dão o completo). `Reprodutor._saida_padrao` abre o `OutputStream` com `device=indice_da_saida()`; `FonteMicrofone` usa `indice_do_microfone()`; `FonteSomInterno` escolhe, entre `sc.all_speakers()`, a saída escolhida para o loopback; `chamadas_telegram._escolher` aceita o nome por prefixo. `interface/dispositivos.py` tem a janela (duas listas, "Padrão do Windows" primeiro) e o item de menu Mídias `dispositivos_som` é um slot de atalho sem combinação. A escolha reaproveita as chaves `chamada_microfone` e `chamada_saida`, então a janela da chamada e a nova janela mostram o mesmo; `_escolher_dispositivos` também troca ao vivo se há chamada em curso, e a janela principal chama `dispositivos.definir` ao abrir. Testes: `testes/test_dispositivos.py` e, na janela, `test_escolher_dispositivos_*` e `test_slot_de_atalho_dos_dispositivos_de_som_*`. Não testado com hardware: ouvir/gravar em outro dispositivo.
- Pergunta depois do Não na janela de versão nova, com dois botões: "Não me avise mais sobre essa versão" e "Talvez mais tarde" (a janela em si não mudou: texto somente leitura com as novidades, Sim e Não). `nucleo/atualizacao.deve_avisar_ao_abrir(lancamento, ignorada)`: ao abrir, avisa de uma versão mais nova que a instalada a cada abertura, até a pessoa atualizar ou responder Sim à pergunta; `atualizacao_ignorada` (config) guarda a versão e uma versão mais nova que ela volta a avisar. Substitui `atualizacao_avisada`, que fazia o aviso automático uma única vez por versão. `interface/atualizacao.perguntar_nao_avisar(pai, versao)` é um `wx.MessageDialog` Sim/Não com os rótulos trocados (`SetYesNoLabels`) e "Talvez mais tarde" como padrão, e `texto_da_pergunta` monta o texto; ela só é feita quando a escolha é "nao" (fechar a janela com Esc conta como Não); instalar limpa a escolha e abrir a página de download não a muda. Em Ajuda, Verificar atualizações a janela sempre abre, e escolher "Talvez mais tarde" volta a avisar. A descrição da opção `verificar_atualizacoes` foi reescrita. `test_aviso_ao_abrir_repete_ate_atualizar_ou_marcar_nao_avisar`, `test_pergunta_depois_do_nao_diz_a_versao_e_as_duas_respostas` e, na janela, `test_atualizacao_talvez_mais_tarde_*`, `test_atualizacao_nao_me_avise_mais_*` e `test_atualizacao_so_pergunta_quando_a_escolha_e_nao`.
- Gravar o som do computador junto com o microfone. `midia/gravador.py`: origem `SOM_E_MICROFONE` e `FonteMista` (loopback do WASAPI somado ao microfone: `misturar` reamostra o bloco do microfone para o do som, soma e limita a -1..1); `Gravador(microfone_ligado=)` e a propriedade `microfone_ligado`, que liga e desliga o microfone com a gravação em andamento (desligado, o fluxo segue aberto e é descartado); sem microfone a mistura grava só o som e `aviso`/`microfone_disponivel` dizem isso. `interface/dialogos.gravar_voz(microfone=)`: caixa "Gravar também o &microfone" na janela de gravação (None = sem caixa). A janela do som do computador usa `SOM_E_MICROFONE` com a caixa vinda da opção nova `gravar_som_com_microfone` (Mídias, padrão ligada); o atalho `gravar_som` (Ctrl+Shift+S) segue só com o som e o novo `gravar_som_mic` (Ctrl+Shift+B) grava os dois, sempre com o microfone. Testes: `test_misturar_*`, `test_microfone_liga_e_desliga_durante_a_gravacao`, `test_sem_microfone_a_mistura_grava_so_o_som_e_avisa` e, na janela, `test_janela_do_som_respeita_a_opcao_do_microfone`, `test_atalho_do_som_com_microfone_*`. Não testado com hardware real: a mistura do som interno com o microfone depende de uma saída de som e de um microfone no computador.
- Busca periódica do estado do app no TeleZapp. `ProvedorWhatsApp._iniciar_busca_periodica` (um laço `estado-busca-periodica`, aberto ao conectar) chama `_buscar_mudancas_de_estado` a cada 90 s: `fetch_app_state` de `regular_low` e `regular_high`, que carregam arquivar, fixar, silenciar, favoritar, trancar, ler e apagar mensagem. O que o aviso ao vivo deixar passar chega com atraso em vez de não chegar. Pula a coleção que já está em reparo, para não acumular pedidos ao celular, e não busca desconectado. A ponte do WinZapp faz o mesmo a cada 60 s e a cada list-chats. `test_busca_periodica_do_estado_pula_a_colecao_em_reparo`.
- Estado do app que o celular não devolve: o pedido de cópia (`request_app_state_recovery`) só tem resposta com o WhatsApp aberto na tela do iPhone e `_recuperar_colecao` desistia depois de 90 s (log de 23/10 19:45: `o celular não respondeu ao pedido do estado regular_low`), deixando as mudanças do celular sem chegar até o reinício. Agora, sem resposta, `_tentar_de_novo` (um laço por coleção, `estado-nova-tentativa`) confere a cada 180 s se a coleção já voltou e, se não, pede a cópia de novo, até 20 vezes (cerca de uma hora). O log diz `estado X voltou a sincronizar (tentativa N)`, `estado X recuperado com a cópia do celular` ou `desisti de recuperar o estado X`. A fala de aviso agora diz que ele tenta de novo a cada poucos minutos. `test_estado_fora_de_sincronia_tenta_de_novo_ate_o_celular_responder`.
- O estado do app (arquivar, fixar, lida...) que sai de sincronia no meio do uso é reparado sozinho. Com outro aparelho conectado também escrevendo no estado (como a ponte do WinZapp), a coleção `regular_low` do TeleZapp deu `Failed to sync app state after notification: failed to decode app state regular_low patches: failed to verify patch v29: mismatching LTHash` (log de 23/10 19:35) e as mudanças feitas no celular, como arquivar, deixaram de chegar até o próximo reinício, que é quando `_conferir_estado` rodava. O ouvinte do registro do whatsmeow (`_ouvir_falhas_do_pareamento`) agora reconhece esse erro (`colecao_fora_de_sincronia`) e chama `_reparar_em_segundo_plano`, que roda `_reparar_colecao` numa thread, no máximo uma vez a cada 120 s por coleção. `test_erro_de_estado_fora_de_sincronia_numa_notificacao_e_reconhecido` e `test_reparo_do_estado_nao_se_repete_antes_do_intervalo`.
- Trancar e destrancar conversas só pelo celular. Saíram o item de menu "Tra&ncar ou destrancar a conversa", o atalho, a opção da seleção em massa, o item do menu de contexto e `Janela._trancar_conversa`. Ficam o tipo Trancadas, o código secreto (`codigo_trancadas`, `trancadas_exigir_codigo`) e o aviso `ChatLockEv` do celular (`_ao_trancar`). `trancadas_locais`, que guardava a tranca feita aqui, é esvaziada ao carregar a lista e essas conversas voltam a destrancadas, porque o celular é quem manda.
- Ler uma conversa no celular zera as não lidas no TeleZapp mesmo com a confirmação de leitura ligada. Nesse caso o celular avisa os outros aparelhos com um recibo de leitura comum (tipo `READ`) cujo `MessageSource.IsFromMe` é verdadeiro, e `_ao_recibo` só tratava o tipo `READ_SELF`: o recibo com remetente eu caía em `if estado is None or origem.IsFromMe: return` e sumia (visto no log da ponte do WinZapp de 23/10 18:23, 36 recibos `read` com o próprio identificador como participante). Agora `READ` e `PLAYED` com `IsFromMe` valem como lida e ouvida por mim. `test_ler_no_celular_chega_como_recibo_de_leitura_meu` e `test_leitura_de_quem_recebeu_minha_mensagem_nao_zera_as_nao_lidas`.
- Arquivar e desarquivar uma conversa do WhatsApp no TeleZapp agora avisa o celular. `ProvedorWhatsApp.arquivar_conversa` manda o aviso de estado `archive` (coleção `regular_low`, versão 3, `ArchiveChatAction` com `lastMessageTimestamp` da conversa), do mesmo jeito que `fixar_conversa` e `silenciar_conversa`; antes só valia no TeleZapp (a fala dizia "só no TeleZapp"). `testes/test_provedor_whatsapp.py::test_arquivar_e_desarquivar_aqui_avisa_o_celular`.
- Bloquear e desbloquear pessoas e a lista de bloqueados. `Provedor.PODE_BLOQUEAR`, `bloqueados()` -> `[(id, nome, telefone)]`, `esta_bloqueado(conversa_id)` e `bloquear(conversa_id, bloquear=True)`; os erros vêm como `ErroBloqueio` (texto para a pessoa). WhatsApp: `get_blocklist` e `update_blocklist` do neonize; a lista pode guardar o LID, então a comparação passa pelo número (`_numero_do_jid`) e o desbloqueio usa o endereço que consta na lista. Telegram: `contacts.GetBlockedRequest` (paginado), `GetFullUserRequest(...).full_user.blocked`, `BlockRequest` e `UnblockRequest`; só ids de usuário (positivos). `interface/bloqueados.py`: `GerenciadorBloqueados` (lista das contas juntas, Desbloquear, Bloquear alguém, Atualizar) e `alternar` (confere, pergunta e inverte), sempre fora da thread da interface. Menu Contatos: "Contatos bloqueados..." e "Bloquear ou desbloquear a pessoa desta conversa..."; menu de contexto da conversa privada: "Bloquear ou desbloquear...". Testes em `testes/test_bloqueados.py` e `test_janela.py`.
- Enquete de canal do WhatsApp (`@newsletter`): `_votar_enquete` não tenta mais votar, avisa que o TeleZapp ainda não vota nelas. O log de 23/10 13:44 mostrava `BuildPollVoteError: original message secret key not found`: mensagens de canal não têm a chave secreta das enquetes comuns e o neonize não tem voto de canal.
- Lista de conversas configurável (nome, serviço, não lidas e trecho da última mensagem; ligar, desligar e ordem). `nucleo/lista_conversas.py` (sem wx): `ITENS`, `normalizar`, `ativos`, `alternar` (recusa o último ativado), `mover`, `rotulo` (fixada e silenciada vêm sempre depois do serviço, ou do nome; sem nada a mostrar vale o nome), `previa_da_mensagem` (80 caracteres, "Você:" e o autor nos grupos) e `padrao()` (trecho desligado, para a leitura de hoje não mudar). Valor guardado em `lista_conversas` (`{ordem, ocultos}`), no backup (`EXTRAS`, validado por `opcoes_validas`) e aplicado por `_aplicar_opcao`. `Banco.ultimas_mensagens()` (uma consulta; lida em segundo plano só quando o trecho está ligado) e `Janela.previas` (atualizada em `_ev_nova` e em `_ev_atualizada`). `modelos.rotulo_conversa` passa a delegar. `interface/lista_conversas.py` (`DialogoListaConversas`, usado pela janela de configurações, com valor pendente em `ModeloConfiguracoes.lista_pendente`, e pelo menu Exibir, com efeito imediato) e o botão "Lista de conversas" na categoria Interface. Menu Exibir, submenu "Lista de conversas": uma caixa por informação, "Ordem das informações..." e "Restaurar o padrão". Testes em `testes/test_lista_conversas.py` e `test_janela.py`.
- Editar o próprio perfil. `Provedor.PODE_EDITAR_PERFIL`, `PERFIL_SOBRENOME`, `meu_perfil()` -> `{nome, sobrenome, recado}` e `salvar_perfil(mudancas, foto)` -> `(feitos, [(campo, motivo)])`; `ErroPerfil` (texto para a pessoa) só quando nem tentou. WhatsApp: `get_me().PushName`, `get_user_info(eu).UserInfo.Status`, `set_profile_name`, `set_status_message` e `set_profile_photo`, um passo de cada vez para dizer qual falhou. Telegram: `GetFullUserRequest(InputUserSelf).about`, `account.UpdateProfileRequest` (só os campos que mudaram; `None` não altera) e `photos.UploadProfilePhotoRequest` com `upload_file`. `nucleo/perfil.py` (sem wx): limites por serviço, `mudancas`, `validar`, `resumo` e `preparar_foto` (OpenCV: recorta o centro em quadrado, 640 px, JPEG 90; lê nomes com acento via `np.fromfile`). `interface/perfil.py` (`DialogoPerfil`) e o fluxo em `Janela._editar_perfil` (lê em segundo plano, valida, reabre a janela com o digitado se houver problema e grava em segundo plano). Menu Ferramentas: "Editar o meu perfil...". Sem remover foto. Testes em `testes/test_perfil.py` e `test_janela.py`.
- Corrigido o voto em enquete do WhatsApp: o `MessageInfo` do `build_poll_vote` só levava `MessageSource` e `ID`, e o neonize (protobuf com campos obrigatórios) recusava com `EncodeError`. `whatsapp.info_da_mensagem` preenche todos os campos (os JIDs vazios também). O log de 23/10 13:27 mostra as duas falhas; o cliente falso dos testes não serializava, por isso não aparecia (teste novo serializa de verdade).
- Mídia e documento enviados como resposta. `Provedor.enviar_arquivo(conversa_id, anexo, legenda, resposta_a, mencoes)`: o WhatsApp monta a mídia à mão com o `ContextInfo` da citação (`_contexto_da_resposta`, tirado de `_mensagem_de_texto`, que agora o reutiliza) e o Telegram passa `reply_to`. A mensagem local já mostra a resposta; a resposta só é limpa depois do último anexo colado, e o texto que sobrar vai como mensagem de texto, ainda citando. O aviso "A mídia vai sem citar a mensagem respondida" saiu. Resposta a status continua só de texto. Não verificado nos serviços reais: só testes com clientes simulados.
- Menção (@) em grupo. `nucleo/mencoes.py` acha e troca os trechos "@Nome" do texto. Na caixa, um @ digitado no começo ou depois de espaço, numa conversa de grupo, abre `dialogos.escolher_membro` (filtro + lista); os membros vêm de `detalhes_do_grupo` (thread própria, guardados por conversa). Ao enviar, `enviar_texto` e `enviar_arquivo` recebem `mencoes=[{id, nome, usuario}]`: o WhatsApp troca "@Nome" por "@número" e põe o JID em `mentionedJID` (a mensagem guardada mantém o texto digitado); o Telegram troca por "@usuario" quando a pessoa tem e, senão, usa `InputMessageEntityMentionName`. Não verificado nos serviços reais.

## 2026.10.23.0

- Minha mensagem de voz (ou áudio) tocada por quem recebeu passa a ter o estado **reproduzida**, depois de enviada, entregue e lida: a linha da lista, lida ao passar pela mensagem, e "Estado" nos detalhes dizem o estado mais avançado (`modelos.REPRODUZIDA`, no WhatsApp pelo recibo de tipo 6 e pelo histórico). Nos detalhes de uma conversa com uma pessoa a linha do recibo diz "Reproduzida a ..." (antes "Ouvida"). Ao abrir o banco, as mensagens minhas que já tinham o recibo de reproduzida guardado (e ficaram como "lida") passam a "reproduzida" (`Banco._atualizar_esquema`, uma vez e sem custo depois). O log passa a registrar "recibo de reproduzida" e os recibos de tipo desconhecido que ignora, para investigar se o WhatsApp não mandar o recibo (a pessoa pode ter a confirmação de leitura desligada). No Telegram não há esse aviso para quem envia.
- Texto do campo "Para" (Nova mensagem e Nova chamada) e dos participantes de um grupo novo: pede o telefone no formato internacional (+55 51 99999 8888) e diz que, no Brasil, só o DDD e o número também serve. Conferido em `modelos.normalizar_telefone`: sem o `+`, com 10 ou 11 dígitos assume `+55`; com `+` vale o número como está (outros países exigem o `+`). Os participantes de grupo novo agora passam pela mesma normalização (antes o WhatsApp usava os dígitos como vieram e o Telegram punha só um `+`).
- Nova mensagem só escolhe a pessoa (`contatos.DialogoEscolherPessoa`, que a Nova chamada também usa) e abre a conversa com ela, com o foco na caixa de digitar; a janela com o campo de texto limitado saiu (junto com a colagem de mídia dentro dela). Enter no campo Para sem ninguém na lista vale o que foi digitado (telefone ou @usuário). Gerenciar contatos ganhou o campo "Buscar contato" (nome sem acento nem maiúscula, ou parte do telefone).
- Telegram sem pedir "api id" e "api hash" a quem instala. `ferramentas/empacotar.py` grava `telezapp/_credenciais.py` (fora do git) com as credenciais do projeto, tiradas de `TELEZAPP_API_ID` e `TELEZAPP_API_HASH`, da configuração deste computador ou do arquivo dos testes, empacota e apaga o arquivo. `config.credenciais_telegram` usa primeiro as embutidas (`credenciais_embutidas`), depois as da configuração e só então a janela pergunta. Sem credenciais na hora de empacotar, o script avisa. Observação: as credenciais ficam dentro do executável, como em outros clientes de código aberto; como todos compartilham o mesmo api id, o Telegram pode limitar o conjunto se alguém abusar.
- Áudio que não é gravação direta (encaminhar uma voz, colar um .ogg) aparecia como enviado e nunca chegava. No log de 22/10 os dois envios eram `audio ... 50176 bytes`: mensagem de áudio comum (`PTT` desligado) com o tipo `audio/ogg`, sem `codecs=opus`. A causa provável (não confirmada com o celular) é esse tipo: o WhatsApp aceita o envio e o destino descarta. Agora `envio.preparar` manda Ogg com Opus como áudio com `audio/ogg; codecs=opus` (também o WAV/FLAC convertido), Ogg que não é Opus (Vorbis) vai como documento, e a duração de M4A vem do cabeçalho MP4. Encaminhar uma voz que não é Ogg/Opus deixa de falhar: segue como arquivo. O log do envio passa a dizer o tipo e a duração enviados.
- Menu reorganizado. Novo primeiro submenu, **Novo**: Nova mensagem, Nova chamada, Nova enquete, Novo contato, Novo status ou história, Nova conta, Novo grupo, Novo canal e Nova comunidade (as chaves de atalho de `nova_msg`, `nova_enquete`, `postar_status` e `adicionar_conta` não mudaram; entram `nova_chamada`, `novo_contato`, `novo_grupo`, `novo_canal` e `nova_comunidade`, sem tecla). Novo submenu **Ir para**: lista de conversas, lista de mensagens, campo editável (era "Escrever mensagem", para não parecer uma mensagem nova), filtros de serviço ou conta e de tipo, e mensagem respondida. O menu **Contas** deixou de existir: Gerenciar contas e "Reconectar as contas" (era "Conectar as contas de novo") foram para o início de Ferramentas. Ordem: Novo, Ir para, Mensagens, Conversas, Contatos, Chamadas, Mídias, Exibir, Ferramentas, Ajuda. Nova chamada reaproveita a busca da Nova mensagem sem o texto (`DialogoNovaMensagem(com_texto=False)`) e Novo contato é o mesmo Adicionar de Contatos (`contatos.adicionar_contato`).
- Configurações reorganizadas. A categoria **Interface** junta "Mostrar status de presença no título da janela" (era "Mostrar o status no título da janela", renomeada para não se confundir com os status do WhatsApp), "Avisar chamadas do WhatsApp" e o botão **Conteúdo falado**, que abre uma janela com as caixas `falar_novas`, `falar_novas_outras_conversas`, `falar_novas_fora_do_telezapp`, `confirmar_envio`, `falar_reacoes` e `falar_descricoes`. Nova categoria **Mensagens**, com o que era de Leitura e de Escrita. Avisos, Leitura e Escrita deixaram de existir. `Opcao` ganhou o campo `grupo` (um botão da categoria que abre as opções juntas; a busca continua achando todas); `ModeloConfiguracoes.grupos` e `opcoes_do_grupo` alimentam o botão (`DialogoGrupoOpcoes`), e o que se marca nele vale como pendente até OK ou Aplicar.
- Criar grupo, canal e comunidade (`nucleo/criar_conversa.py`, `interface/criar_conversa.py`, `Provedor.CRIA` e `Provedor.criar_conversa`). WhatsApp: `create_group` (com `GroupParent(IsParent=True)` para a comunidade, aprovação para entrar) e `create_newsletter`; a descrição do grupo entra por `set_group_topic`; a conversa nova já é registrada e publicada. Telegram: `CreateChannelRequest` com `megagroup` (grupo, com `forum` se pedido) ou `broadcast` (canal); participantes por `InviteToChannelRequest`. Nome de até 25 letras no WhatsApp (grupo e comunidade), 128 no Telegram. Só testado com serviços simulados: falta criar de verdade nos dois serviços.
- Grupos do Telegram com tópicos. O grupo é uma conversa só na lista (data e não lidas somam os dos tópicos) e cada tópico é uma conversa `<grupo>#<tópico>` ("Grupo › Tópico", Geral = 1) que a janela esconde da lista: ao abrir o grupo, `Janela._escolher_topico` pergunta o tópico e abre a conversa dele. Esc dentro de um tópico volta para a lista de tópicos do mesmo grupo (`_esc_da_conversa`), e Esc nela fecha o grupo. `GetForumTopicsRequest` traz os tópicos, os não lidos e se o tópico está fechado (somente leitura); as mensagens vêm de `iter_messages(reply_to=tópico)`, o Geral filtra o que é de outro tópico (`topico_da_mensagem`); enviar num tópico responde ao tópico; marcar como lido usa `ReadDiscussionRequest`; mensagem nova de um tópico que ainda não existe cria a conversa. Conversas comuns não mudam. Só testado com um Telegram simulado: falta ver ao vivo num grupo com tópicos (em especial o Geral, as respostas e o marcar como lido). Criar e renomear tópicos não está feito.
- A opção `enter_envia` ("Enter na caixa de digitar envia a mensagem") passa a vir **ligada**: Enter envia, como sempre foi, Shift Enter quebra a linha e Control Enter também envia. Desmarcada, só Control Enter envia e Enter quebra a linha. Isto substitui o padrão que entrou antes (Control Enter envia, Enter quebra); o resto do que aquela mudança trouxe (função de atalho `enviar_msg`, Enter passando pelo controle) continua.
- Sons: seis eventos novos na tela de Sons (`gravando`, `gravacao_parada`, `voto_enquete`, `voto_enviado`, `escondido`, `voltou`), com bip padrão, som no pacote TeleZapp (`ferramentas/gerar_sons.py`) e ligação no código. Gravar por atalho e a janela de gravação deixam de usar os sons de mensagem recebida e enviada (agora `gravando`, curto, e `gravacao_parada`, que de fábrica toca o som de enviada); a espera antes de gravar subiu de 0,3 para 0,4 s para o bipe não entrar na gravação. O voto de alguém numa enquete sua toca `voto_enquete` (no Telegram, que não diz quem votou, quando o total de votos sobe), o seu próprio voto toca `voto_enviado`, e esconder e trazer a janela de volta tocam `escondido` e `voltou`.
- Atalhos para funções que não tinham slot: "Pausar ou continuar a gravação por atalho" (`gravar_pausa`), "Descartar a gravação por atalho" (`gravar_descartar`) e "Personalizar os atalhos..." (`abrir_atalhos`, abre Configurações na categoria Atalhos). Todas nascem sem tecla, prontas para receber uma. Pausar a gravação por atalho deixa o trecho de fora (`Gravador.pausar`).
- Backup e restauração levam o mapa de atalhos personalizados (`atalhos`, parte Configurações): na volta só entra o que serve (função em texto, combinação que existe e pode ser atalho, na forma canônica, sem repetir a mesma combinação) e os menus e botões se atualizam na hora. "Abrir o TeleZapp ao entrar no Windows" nunca vem de um backup (é uma entrada do computador, com o caminho do programa dele).
- Enquetes do WhatsApp: os votos não somavam. Visto ao vivo no log: `voto em enquete que não consegui decifrar (TypeError)`. A causa é um erro do neonize 0.5.2: `DecryptPollVote` ficou fora da lista de funções da DLL cujo retorno vira `bytes`, e `decrypt_poll_vote` levanta `TypeError: expected bytes, LP_Bytes found`. `whatsapp.consertar_decifrar_voto` põe o tratamento que faltava (uma vez por biblioteca) e o log agora diz o motivo de um voto que não decifra. Votos dados antes desta correção não voltam: foram descartados.
- Enquetes, etapa 2: criar. Mensagens, "Criar uma enquete..." abre `interface/nova_enquete.py` (pergunta, opções acrescentadas com Enter, Remover e Mover, "Permitir várias respostas" e, no Telegram, "Votos anônimos"); `modelos.erro_da_enquete` valida (2 a 12 opções no WhatsApp, 2 a 10 no Telegram, 100 letras por opção, 255 na pergunta, sem repetição). WhatsApp: `build_poll_vote_creation` com `VoteType.SINGLE` ou `MULTIPLE` (o prazo das mensagens temporárias também vale: `com_expiracao` conhece `pollCreationMessage`); Telegram: `InputMediaPoll` com `Poll`. A enquete criada volta como mensagem enviada, com as opções já guardadas, e entra na lista como qualquer outra. Falhas viram aviso. Só testado com serviços simulados: falta criar e votar ao vivo nos dois serviços (no WhatsApp, em particular, confirmar que o neonize guarda o segredo das enquetes que o próprio TeleZapp cria, para decifrar os votos dos outros).
- Enquetes, etapa 1 (ver e votar; criar fica para a etapa 2). Os dados ficam em `extras["enquete"]` da mensagem (`modelos.enquete_de`: pergunta, opções, máximo de respostas, votos por pessoa, contagem do serviço, meus votos, encerrada, anônima). A linha da lista diz "enquete: pergunta, N opções, M votos, seu voto: X (Enter para ver e votar)"; Enter (ou Mensagens, Ver e votar na enquete) abre `interface/enquete.py`: opções com contagem e porcentagem numa `wx.CheckListBox`, Votar, Tirar meu voto, Atualizar e Ver quem votou. Telegram: `enquete_do_telegram` lê a enquete e os `PollResults`, `SendVoteRequest` vota, e `UpdateMessagePoll` mantém a contagem em dia (`Banco.mensagem_da_enquete` acha a mensagem pelo número da enquete). WhatsApp: `enquete_do_whatsapp` lê a pergunta e as opções; cada voto chega como `pollUpdateMessage` e `_tratar_voto` o decifra com `decrypt_poll_vote` (o neonize guarda o segredo da enquete ao recebê-la; o voto traz o SHA-256 de cada opção marcada, que vira a posição); `build_poll_vote` monta o nosso. Votos dados com o TeleZapp fechado chegam ao reconectar, como as mensagens; enquetes anteriores ao pareamento ou sem segredo guardado não decifram. Só testado com serviços simulados: falta ver ao vivo com uma enquete de verdade nos dois serviços.
- Enviar mensagem passa a ser Control Enter por padrão, como no Telegram Web e no Gmail; Enter quebra a linha. Nova função de atalho `enviar_msg` (menu Mensagens, "Enviar a mensagem digitada", Control Enter de fábrica, trocável) e nova opção `enter_envia` (Escrita, desligada): ligada, o Enter envia como antes. O Enter continua passando pelo controle (`EVT_TEXT_ENTER` decide: `_enter_na_caixa`), para o leitor de tela fechar a palavra. O Control Enter, que o campo de texto recebe antes da tabela de aceleração, é tratado em `_tecla_caixa`. O botão Enviar e as falas (edição, mídia colada) dizem a tecla em uso. Alt M deixou de ser reservado e a barra de menu virou apenas "Menu" (Alt sozinho já abre).
- Atalhos: Alt com uma letra (por exemplo Alt R) passa a ser aceito; só Alt M (abre o menu) e Alt E (botão Enviar) ficam reservados. A janela de escolher a combinação não tem mais letras de acesso nos botões, porque Alt R apertado ali acionava o botão Remover em vez de ser lido.
- "Falar de quem é o áudio que toca" (`falar_quem_toca`) saiu de Avisos e do menu Exibir e foi para Configurações, Mídias, logo antes das opções "Na sequência de áudios", com o nome "Ao tocar o primeiro áudio, falar de quem é e a duração". O comportamento é o mesmo.
- Chamadas de voz do WhatsApp deixam de ser uma opção experimental: saiu a caixa `chamadas_whatsapp` e o meowcaller liga sozinho antes de conectar sempre que a DLL do neonize o tiver (`WhatsApp._preparar_chamadas`). Sem a DLL de teste nada muda. A opção "Avisar chamadas do WhatsApp" passa a valer só quando o TeleZapp não consegue atender. "Depois de um áudio, tocar o próximo" voltou a se chamar "Sequência de áudios" (opção e item do menu Mídias).
- Saem de Avisos as opções "Som ao receber mensagem" (`som`) e "Som de chamada" (`toque_chamada`): cada som já se liga e desliga na tela de Sons. Quem as tinha desligadas fica com os eventos correspondentes (nova, nova_aberta, nova_grupo, toque, chamando) desativados nos pacotes (`pacotes_de_som.migrar_liga_desliga`, roda uma vez). O item "Som ao receber mensagem" do menu Exibir saiu junto.
- A caixa "Mostrar as teclas de atalho nos controles" passou da categoria Leitura para o topo de Configurações, Atalhos.
- Textos mais claros nos menus e nas configurações de mídias. As escolhas soltas ganharam título: Mídias, Quando baixar as mídias (Só quando eu abrir, Automaticamente ao receber) e Exibir, Como cada mensagem é lida. Itens renomeados, por exemplo: Enter em áudio -> Ao tocar um áudio: só tocar ou abrir o player; Áudios em sequência -> Depois de um áudio, tocar o próximo; Passo da velocidade -> Quanto a velocidade muda a cada vez; Limite do download automático -> Tamanho máximo do download automático; Confirmar downloads grandes -> Perguntar antes de baixar arquivos grandes. Na lista de atalhos, as escolhas agrupadas aparecem com o título (Quando baixar as mídias: Só quando eu abrir). As teclas aparecem em português (Seta para a esquerda, Seta para a direita, Seta para cima, Seta para baixo, Espaço) nos menus, nos botões, na tela de atalhos e na fala; a combinação guardada continua no nome em inglês (`atalhos.exibir` faz a troca). Os atalhos agora sempre valem por uma `wx.AcceleratorTable`; o nome vai depois do Tab do menu e, para as setas e o Espaço, que o wx não entende em português, entre parênteses no fim do texto.
- Regra fixa de envio de arquivos: o botão e o menu de anexar mandam sempre como documento (`envio.preparar(..., como_documento=True)`), nos dois serviços; o colado com Control V (`colado=True`) segue como mídia, convertendo o que dá (BMP e GIF parado viram PNG em `colagem._converter_imagem`; WAV e FLAC viram Ogg/Opus na hora do envio no WhatsApp) e, para foto, vídeo e áudio que não dá (HEIC, GIF animado, MKV, AVI, WEBM, WMV), mostra uma janela dizendo que vai como documento (`Anexo.sem_conversao`). Encaminhar e postar status não mudaram.
- WAV e FLAC no WhatsApp: o arquivo ia como mensagem de áudio (`audio/x-wav`), que o WhatsApp não toca, e o envio aparecia como feito sem chegar ao destino. Agora, pelo botão ou menu de anexar, o arquivo vai como documento; colado na caixa (Control V, `Anexo.colado`), é convertido para Ogg/Opus e vai como áudio comum (`envio.converter_para_opus`, que junta os canais do estéreo). Os tipos MIME de M4A (antes `audio/mpeg`) e AAC (antes `audio/vnd.dlna.adts`) também foram corrigidos. No Telegram nada mudou. Não verificado com um destinatário de verdade.

- Atalhos personalizáveis (`nucleo/atalhos.py`, `interface/atalhos.py`,
  `interface/teclas.py`). Todo item de menu entra num `Registro` (padrão tirado
  do rótulo) e aceita outra combinação, guardada em `config["atalhos"]` só
  quando difere do padrão. Configurações ganha a categoria Atalhos: busca por
  função ou tecla, lista no estilo da lista de eventos de som, Alterar (janela
  em que se aperta a combinação), Remover e Restaurar o padrão/todos. Tecla
  repetida é recusada com aviso e a opção de substituir (a outra função fica
  sem atalho); Enter, Esc, Tab, Control C/V/X/A/Z/Y, Alt F4 e letras soltas não
  servem. A opção `mostrar_atalhos` (ligada) escreve o atalho no nome dos itens
  de menu e dos botões; desligada, o nome fica limpo e uma
  `wx.AcceleratorTable` mantém os atalhos valendo.
- Gravar por atalho: Control Shift M (microfone) e Control Shift S (som do
  computador) iniciam a gravação e o segundo aperto para e envia a nota de voz
  na hora, sem janela; Esc, fechar a conversa ou fechar o programa descartam.
  Os botões e os novos itens "em uma janela" do menu Mídias continuam abrindo
  a janela de gravação.
- Segundo plano: a opção `segundo_plano` faz o botão de fechar esconder a
  janela e deixa um ícone na área de notificação (`interface/bandeja.py`,
  `wx.adv.TaskBarIcon`; menu Abrir e Sair). Sair de verdade é `_sair()`
  (menu, Control Q, botão Sair, menu do ícone). A função de atalho global
  "mostrar_janela" (sem tecla de fábrica) usa `RegisterHotKey`; se outro
  programa já a usa, o TeleZapp avisa. Uma segunda abertura do programa
  aciona um evento nomeado (`nucleo/instancia.py`) em vez de dizer que já está
  aberto, e a primeira mostra a janela.
- Abrir ao entrar no Windows: a opção `iniciar_com_windows` grava a chave
  `Run` do usuário (`nucleo/inicializacao.py`) com `--segundo-plano`; com o
  segundo plano ligado a janela nem aparece. Pelo código-fonte a entrada chama
  o `iniciar-telezapp.bat`, que agora repassa os argumentos.
- Gravação de voz (`dialogos.gravar_voz`): a janela abre pronta, com o foco em "Gravar", e só começa a gravar quando a pessoa aperta o botão (antes começava sozinha). Gravando há "Pausar"/"Continuar" ao lado de "Parar de gravar"; `Gravador.pausar()`/`continuar()` mantêm a captura aberta e descartam o trecho da pausa. "Gravar de novo" volta ao início, sem começar sozinho. Só há teste automático do `Gravador`; a janela não foi vista no app real.

- Enter na caixa de digitar passa pelo controle, como no WinZapp: a caixa ganha `TE_PROCESS_ENTER` e o envio sai do `EVT_TEXT_ENTER`; o `_char_hook` só deixa o Enter seguir (`Skip`). Shift+Enter e Control+Enter quebram a linha em `_tecla_caixa`. O leitor de tela vê o Enter e fecha a última palavra digitada. Saem a opção `enter_chega_ao_leitor` (era experimental), o atraso de 10 ms e a limpeza da quebra de linha (`_enviar_depois_do_enter`). A opção "Enter na caixa fecha a palavra digitada" some das Configurações.

- Corretor ortográfico (F7, menu Mensagens, "Verificar ortografia da
  mensagem"). `nucleo/ortografia.py` usa o verificador do Windows
  (ISpellChecker, por ctypes, sem dependência nova): dicionários dos idiomas
  instalados e "Adicionar ao dicionário" grava no dicionário pessoal do
  Windows. `Revisao` percorre os erros um a um, verificando o texto de novo a
  cada troca; `interface/ortografia.py` mostra palavra, frase, campo "Trocar
  por", sugestões e os botões Trocar, Trocar todas, Ignorar, Ignorar todas e
  Adicionar. Opções (categoria Escrita): idioma do corretor e "Avisar de
  erros de ortografia ao enviar" (desligada: pergunta Corrigir, Enviar assim
  mesmo ou Cancelar). Sem o dicionário no Windows, o corretor avisa.

- Chamadas de voz do WhatsApp (experimental, opção "Chamadas de voz do
  WhatsApp (experimental)", desligada por padrão). `provedores/chamadas_whatsapp.py`
  liga o meowcaller (MIT; protocolo por engenharia reversa) que vai dentro da
  DLL de teste do neonize (`goneonize/calls.go`, receita em
  `docs/neonize/COMO-CONSTRUIR.md`): o mesmo cliente e o mesmo login das
  mensagens, sem segundo pareamento. A DLL expõe `CallsConfigure` (antes de
  conectar), `CallsNextEvent`, `CallDial`, `CallAnswer`, `CallHangup`,
  `CallReadAudio` e `CallWriteAudio` (quadros PCM s16le de 1920 bytes, 16 kHz);
  o Python liga o microfone e a saída pelo sounddevice. O estado sai como
  `EstadoChamada`, igual ao Telegram. Com a opção ligada, o aviso antigo ("só
  avisa") não aparece. Visto ao vivo só no experimento, sem o app.

## 2026.10.21.0

- Resposta a botões e listas de mensagens de empresa (erro 479). O whatsmeow
  (`send.go`, `getButtonTypeFromMessage`) acrescentava `<biz><buttons_response/>`,
  `<list_response/>` ou `<interactive_response/>` ao envio; o WhatsApp Web não
  manda esse nó nas respostas (`WAWebSendMsgCreateFanoutStanza`: o biz só existe
  para mensagens interativas nativas e no modo de privacidade), só o atributo
  `mediatype` do `enc`. A DLL de teste do neonize (`Backup
eonize-0.5.2-teste`)
  vem sem o nó (`docs/neonize/sem-no-biz-whatsmeow-send.go.diff`). Embrulhar a
  resposta em `documentWithCaptionMessage` tira o nó e o servidor aceita, mas a
  empresa ignora: o embrulho experimental de `_variantes_da_acao` foi removido.
  Visto ao vivo: lista da Equatorial. Sem a DLL de teste (neonize oficial) as
  respostas voltam a dar 479.

- Registro sem telefones nem textos. `config.mascarar_texto` troca
  `5551999998888@s.whatsapp.net`, `...@lid`, `...-1577...@g.us` e
  `+5551999998888` pelo fim (`...8888@...`, `+55...8888`; o número antes do
  traço do grupo é de quem o criou) e `FormatadorSemTelefones` passa todo o
  texto do registro, exceção incluída, por ela (o log do usuário tinha
  telefones nos avisos "mensagem não decifrada" e nos do whatsmeow).
  `forma_sem_textos` no registro "mensagem interativa:" (guardava os 80
  primeiros caracteres do texto das mensagens de empresa; agora só chaves e
  nomes de tipo).

- Barras de progresso (`interface/progresso.JanelaDeProgresso`, um `wx.Dialog`
  sem modal com `wx.Gauge`; Cancelar e Esc só quando há `ao_cancelar`; sem
  Enter padrão): o NVDA só toca os bipes da barra de uma janela em primeiro
  plano. Usada em: atualização (`Janela._atualizar`: baixar vai a 90%, extrair
  a 100%; `atualizador.baixar(.., cancelado)` apaga o parcial e
  `atualizador.extrair(.., progresso)`), `instalacao.com_espera(pai, titulo,
  trabalho(progresso))` (instalar, criar portátil, backup do desinstalar; o
  instalador de um arquivo só dá 40% à extração do zip embutido),
  `nucleo/instalacao`: `faixa`, cópia do programa e dos dados por bytes e
  arquivos (`instalar`, `criar_portatil`, `extrair_pacote` com
  `progresso(pct, texto)`), `backup.criar` e `backup.restaurar`
  (`progresso(pct, texto)` por arquivo; `Janela._barra_de_tarefa`),
  downloads pedidos e envios por arquivo (`_barra_de_transferencia`: só abre
  depois de 1 s e abaixo de 90%; fecha em `MidiaBaixada` e `_fim_do_envio`).
  Opção `barra_de_progresso` (Mídias, ligada) vale para as transferências;
  com a barra aberta, não se fala "N por cento". Nem a fala nem o rótulo
  levam a porcentagem (o NVDA decide pela configuração dele, como no
  WinZapp): `JanelaDeProgresso.atualizar` só troca o rótulo e só chama
  `falar` quando a etapa muda; os callers passam etapas ("Baixando a versão
  X", "Copiando as mídias"), sem número.

- Áudio M4A/AAC: a libsndfile não abre AAC; o `Reprodutor` decodifica com o
  PyAV para um WAV temporário e toca normalmente (entra na sequência). Se nem
  assim abrir, `FormatoNaoSuportado` e a janela usa o outro motor.
- Abrir grupo: `_rever_mencoes_do_grupo` roda em segundo plano e avisa a tela
  por `MensagemAtualizada` (motivo `mencao`); quem continua sem nome só é
  procurado de novo após 10 min (`_mencoes_tentadas`). A edição lê as menções
  do texto novo e a revisão corrige as guardadas com nome mas texto com número.
- Sons: `sd.play` de várias threads corrompia o PortAudio; há `_trava_som`.
  Sons de até 2 s são pré-carregados na RAM em segundo plano (`fala.py`,
  `_pre_carregados`, conferidos por mtime). O stderr vai para o
  `falha-nativa.log` (`os.dup2`) e a marca `sessao-aberta` avisa no log se a
  vez anterior não fechou normalmente.
- Mensagem só com link e prévia: a prévia vem antes do endereço (`_so_link`).
- Opção `enter_chega_ao_leitor`: espera de 40 para 10 ms.

## 2026.10.20.0

- Menus: o Menu único com submenus continua, em nova ordem (`_criar_menus`):
  Mensagens (Nova mensagem em primeiro), Conversas, Contatos, Chamadas,
  Contas, Mídias, Exibir, Ferramentas (backup, restaurar, configurações,
  instalar, criar portátil, desinstalar, sair) e Ajuda (com Depurar como
  submenu). Botão `botao_sair` ("Sair", sem tecla de acesso) entre a busca e
  a lista (ordem de Tab). `comecar` põe o foco na lista de conversas, no
  topo; some `ultima_conversa` e `_guardar_lista` (a posição dentro de cada
  conversa, `banco.posicao`, continua). Contas: `adicionar_conta` pelo menu abre
  `_escolher_servico_e_adicionar` (a mesma escolha da primeira conta) e
  `_gerenciar_contas` abre `interface/gerenciar_contas.DialogoContas`
  (`wx.CheckListBox`: marcada = ativa; botões Excluir e Renomear), que
  substitui Ativar ou desativar, Remover e os dois "Adicionar conta do ...".
  `Contas.renomear` grava `apelido` (e `nome_servico`) na configuração;
  `ContaPronta` não o sobrescreve. Os caminhos "Menu, X" da ajuda e das
  mensagens viraram "X" ou "Ferramentas, X". `wx_falso.MenuBar` guarda os
  menus para o teste da ordem.
- Mensagens temporárias. Modelo: `Conversa.temporaria_s` (segundos, 0 =
  desligado) e `Mensagem.expira` (timestamp); colunas novas no banco
  (esquema 11, com índice parcial `mensagens_por_expira`) e
  `Banco.mensagens_expiradas`. `modelos`: `PERIODOS_TEMPORARIAS` por serviço,
  `texto_periodo(seg, servico)`, `texto_temporaria`, `expira_em`; marca
  "(temporária)" em `formatar` e linha em `detalhes`.
  WhatsApp: `_prazo(ctx)` lê `contextInfo.expiration` em `converter` e
  `converter_historico`; `_ao_receber` guarda o prazo visto na conversa e
  `_tratar_alteracao` trata `ProtocolMessage.EPHEMERAL_SETTING`
  (`_temporaria_mudou`, com aviso); `definir_temporaria` chama
  `SetDisappearingTimer` da DLL direto (`_NewClient__client`, prazo em
  nanossegundos e hora em milissegundos: o `set_disappearing_timer` do
  neonize converte errado); `com_expiracao` põe o prazo nas mensagens que o
  TeleZapp envia (texto simples vira `extendedTextMessage`; mídia com prazo
  é montada à mão). Telegram: `prazo_da_mensagem` (`ttl_period`), prazo do
  diálogo em `_atualizar_conversas`, `MessageActionSetMessagesTTL` em
  `_ao_receber` e `definir_temporaria` (`SetHistoryTTLRequest`). Janela:
  `_apagar_expiradas` (ao abrir e a cada minuto, via
  `limpeza.apagar_mensagem`, que registra para não voltar), título, e
  Detalhes da conversa com a linha e o botão. Opção
  `temporarias_apagar_aqui` (Privacidade, ligada). Falta ver no app real.
- Correção: o status da pessoa no título quebrava com data inválida (o
  "visto por último" escondido vem como a data zero do Go, negativa, e o
  Windows recusa `time.localtime`), o que abortava abrir mídia, baixar e
  transcrever: `hora_legivel` e `_ultima_vez` aceitam só datas válidas e
  `_status_da_conversa` não deixa o título derrubar nada.
- Grupos do WhatsApp com participante só em LID: `quem_enviou` nunca devolve
  o endereço `@lid` ("Participante final NNNN" se nada acha);
  `Janela._nome_do_remetente` também pergunta ao provedor
  (`nome_de_participante`, sem rede); `conversa_aberta` de grupo enfileira
  `_completar_autores` (agenda, nomes vistos e `_aprender_do_grupo`, grava
  com `renomear_autor` e publica `ev.AutoresAtualizados`, que a janela aplica
  ao cache e à lista).
- Áudio ao fundo: `_pular_audio` (Control Shift Esquerda/Direita 5 s, Page
  Up/Down 30 s, em Menu, Mídias; fala `posição de duração`). O player em
  janela já tinha as setas.
- Envio por arquivo registra no log quantos avisos de avanço foram gerados.

- Backup com senha leva as chaves dos provedores de IA: `backup.criar` grava
  `ia_chaves.json` (`CHAVES_IA`, só com `senha` e a parte configurações) com as
  chaves lidas do `Cofre`; `restaurar(.., resultado)` as devolve ao cofre
  (`_restaurar_chaves`, só provedores conhecidos, DPAPI de novo) quando a
  parte configurações é restaurada com senha, e preenche
  `resultado["ia_chaves"]`. A janela diz quantas voltaram; o diálogo do
  backup explica a regra.

## 2026.10.19.1

Instalar a partir de uma cópia portátil e criar cópia portátil.

- Desinstalar oferece o backup: `interface.instalacao.oferecer_backup`
  (Sim/Não/Cancelar, depois `DialogoBackup`, onde salvar e `backup.criar`;
  falha ou desistência cancelam a desinstalação). Vale no menu (com
  `banco.copiar_para`) e em `--desinstalar` (cópia do arquivo pelo SQLite).
- Atalhos: as pastas do menu Iniciar e da área de trabalho vêm de
  `SHGetKnownFolderPath` (`instalacao._pasta_conhecida`), não de
  `%USERPROFILE%\Desktop`: com a área de trabalho no OneDrive o atalho
  ia para uma pasta que ninguém vê. A desinstalação apaga dos mesmos lugares.
- Instalador de um arquivo só: `telezapp/instalador.py` (entrada
  `ferramentas/empacotar/instalar.py`) abre `mostrar_boas_vindas(fonte, ..)`
  sem "usar sem instalar"; Instalar e Criar cópia portátil extraem o
  `TeleZapp.zip` embutido (`instalacao.extrair_pacote`, em
  `%LOCALAPPDATA%\TeleZapp-instalador`, apagado no fim) e usam a lógica de
  sempre. `ferramentas/empacotar.py` gera programa (spec `TeleZapp.spec`,
  agora com `upx=False`, `cv2` e `emoji`), `TeleZapp.zip` (+ `.sha256`) e o
  `TeleZapp.exe` instalador (spec `Instalador.spec`, um arquivo só);
  `publicar.py` anexa os três e as notas mandam baixar o `TeleZapp.exe`. A
  página do GitHub Pages aponta o botão para ele.
- Janela da atualização (`interface/atualizacao.DialogoAtualizacao`): texto
  somente leitura e focado com a versão oferecida, o tamanho e as novidades de
  cada versão publicada desde a em uso (`Lancamento.historico`, montado em
  `atualizacao.mais_nova` a partir de `## Novidades da versão X` das notas,
  `novidades_do_corpo`), depois Tab para Sim (baixa e instala) e Não; sem o
  zip ou fora do executável, "Abrir a página de download" e Fechar. A
  verificação ao abrir (opção `verificar_atualizacoes`) agora abre essa janela,
  uma vez por versão (`atualizacao_avisada`); antes só falava. Sai a
  pergunta extra de `_atualizar`.
- O zip da Release passou a se chamar sempre `TeleZapp.zip` (e
  `TeleZapp.zip.sha256`): `/releases/latest/download/TeleZapp.zip` aponta para
  a versão mais nova (só vale para Release que não seja pré-lançamento).
  `atualizacao._arquivos` ainda aceita o nome antigo com a versão.
- Tela de boas-vindas (`interface/instalacao.mostrar_boas_vindas`): no
  executável que não é instalado, sem pasta `dados` e sem
  `sem-boas-vindas.txt`, antes de tudo (depois do `wx.App`): Instalar, Criar
  cópia portátil, Guia de uso, Usar sem instalar (com a opção de não mostrar
  de novo) e Fechar. `fluxo_instalar` e `fluxo_criar_portatil` (também usados
  pelo menu) rodam o trabalho numa thread com `wx.ProgressDialog`.
- Atualizador (`nucleo/atualizador.py`): `atualizacao.Lancamento` ganha
  `url_zip`, `url_hash`, `nome_zip`, `tamanho` (assets
  `TeleZapp-<v>.zip` e `.sha256` do `publicar.py`). `baixar` (só https de
  github.com, confere o SHA-256), `extrair` (exige `TeleZapp/TeleZapp.exe`,
  recusa caminhos fora da pasta) e `aplicar`, que grava `atualizar.bat` ao
  lado e o roda separado: espera a pasta liberar (até 90 s), renomeia a atual
  para `.antiga`, põe a nova, devolve `dados`, `instalado.txt` e
  `sem-boas-vindas.txt` e abre o exe. Sobras (`.atualizacao`, `.antiga`) saem
  na abertura seguinte (`limpar_restos`). A janela oferece o botão em Ajuda,
  Verificar atualizações, só no executável e se a Release tem os dois
  arquivos.
- `nucleo/instalacao.py`: modos `desenvolvimento`, `portatil` e `instalado`
  (marca `instalado.txt` na pasta do programa). Instalar copia a pasta para
  `.nova`, troca a instalação anterior pelo nome (se estiver em uso, desfaz e
  avisa), cria atalhos (`WScript.Shell` por PowerShell, falha vira aviso) e a
  entrada em `HKCU\...\Uninstall\TeleZapp` com `TeleZapp.exe --desinstalar`.
  Sem administrador: `%LOCALAPPDATA%\Programs\TeleZapp`.
- Dados: `config.pasta_dados()` usa a pasta `dados` ao lado do executável
  quando existe (só congelado). Ao levar dados de um lugar para o outro,
  bancos pelo `_copia_consistente`, sem `logs`/`temp`, e
  `_acertar_caminhos_das_midias`; os dados anteriores de quem instala ficam
  em `TeleZapp.antes-da-instalacao-<data>`.
- Menu principal: Instalar, Criar cópia portátil e Desinstalar (explicam
  quando não se aplicam). `--desinstalar` abre sem janela principal; a pasta do
  programa é apagada por um `cmd` separado após 4 s.
- Testes: `testes/test_instalacao.py`.

## 2026.10.19.0

Leitura dupla do NVDA na lista de conversas, busca das configurações, vídeo
por quadros e IA automática.

- `nome_de_participante` (listas de quem recebeu, abriu ou reproduziu) usa
  `_dados_mencao(.., rede=False)`: agenda, apelido por qualquer endereço e
  mensagens guardadas, sem consultar a rede (a lista pode ser grande).
- Opção `enter_chega_ao_leitor` (desligada): no Enter da caixa o `_char_hook`
  faz `evt.Skip()` (o controle recebe o `WM_CHAR` que o NVDA usa para fechar
  a palavra digitada) e `wx.CallLater(10, _enviar_depois_do_enter)` envia o
  texto (o `strip()` tira a quebra de linha) e limpa a caixa. Padrão: Enter
  tratado no hook, que engole o `WM_CHAR`.
- Evento de som `mencao_ou_resposta` (18º). `extras["citou_voce"]`: o WhatsApp
  marca em `_ao_receber` (`_cita_voce`: `mentionedJID` com o telefone ou o LID
  de `get_me()`), o Telegram usa `message.mentioned`; `guardar_extras` mantém
  a marca. `Janela._cita_voce` soma a resposta a mensagem minha (cache ou
  banco). Em `_ev_nova` o som substitui `nova_grupo`/`nova_aberta` e não
  depende de `som`; passa pelo filtro de conversa muda. Som do TeleZapp:
  `E6`+`C6` descendo, 0,79 s; bips: 1047, 1319 e 1047 Hz.
- Tom padrão de "chamando": `fala.DURACAO_TOM_DE_CHAMADA_MS` = 1500 ms
  (antes 400); a janela repete a cada 3 s (`_repetir_toque`).
- Evento de som `reacao_recebida` (17º): `EVENTOS_SOM`, bip em `fala._tocar`
  (1319 e 1568 Hz), `ferramentas/gerar_sons.py` (`E6` e `G6`, 0,45 s) e
  `telezapp/sons/reacao_recebida.ogg`; `Janela._ev_atualizada` toca quando
  `motivo == "reacao"` numa mensagem minha, com emoji e de outra pessoa,
  depois do filtro de conversa muda.
- Menções só com telefone: `_lembrar_apelido(.., alternativo)` guarda o nome
  de perfil sob `Sender` e `SenderAlt` e `_aprender_par` registra o par
  LID/telefone de cada mensagem; `_formas_do_endereco` junta o endereço, o
  telefone, os LIDs do mapa e `get_lid_from_pn`, e `_dados_mencao` procura o
  apelido e `banco.nome_do_remetente` por todos eles. `_reavaliar_mencoes`
  (chamada em `carregar_mensagens` de grupos, até 300 por vez) refaz as
  menções que ficaram com o telefone e regrava o texto e os extras.
- Progresso de download e envio. `ev.ProgressoEnvio`; `Janela._ev_progresso_envio`
  (título "enviando mídia N%", barra de situação, fala no passo de
  `midias_passo_progresso`; some em `MensagemNova(enviada_daqui)`, falha ou
  100%). Telegram: `send_file(progress_callback=)`. WhatsApp: a DLL de teste
  ganhou `DownloadAnyToFile` (whatsmeow `DownloadToFile`, direto no disco),
  `UploadFile` (`UploadReader` com um arquivo temporário que conta o que
  escreve, 0 a 10 %, e o que lê ao enviar, 10 a 100 %), `TransferProgress` e
  `TransferCancel` (patch em `docs/neonize/transferencias-main.go.diff`;
  `_binder.py`/`client.py` do venv ganharam `download_any_to_file`,
  `upload_file`, `transfer_progress`, `transfer_cancel`, `tem_transferencias`).
  `baixar_arquivo` usa isso quando `tem_transferencias()` (progresso pelo
  tamanho do `.parte`, Esc cancela na DLL); `_enviar_arquivo` usa para
  arquivos ≥ `LIMITE_ENVIO_POR_ARQUIVO` (8 MiB), montando a mensagem de foto,
  vídeo, áudio ou documento com `_mensagem_de_midia(up=)`. Sem a DLL de teste
  tudo cai nos caminhos antigos. Não testado com uma conta real.
- Publicar status e histórias: `Provedor.PODE_PUBLICAR_STATUS` e
  `publicar_status(texto, anexo, publico)`. WhatsApp: envia para
  `status@broadcast` (texto com `ExtendedTextMessage` e fundo verde, foto com
  `send_image`, vídeo com `_mensagem_de_midia`) numa thread e guarda o status
  em "Meu status" (`_guardar_meu_status`); quem vê é a privacidade de status
  da conta. Telegram: `stories.SendStoryRequest` com `InputPeerSelf`,
  mídia enviada por `upload_file` e regra `AllowContacts`/`AllowAll`.
  `nucleo/publicar_status.validar` confere (WhatsApp: texto ≤ 700 ou foto ou
  vídeo; Telegram: foto ou vídeo, legenda ≤ 200) e
  `interface/publicar_status.DialogoPublicarStatus` é a janela; atalho
  Ctrl+Shift+U. Resultado por `ev.Aviso`. Não testado com contas reais: o
  envio ao `status@broadcast` pelo neonize e a história sem Premium são as
  dúvidas.
- Histórias do Telegram nas conversas de status (mesmo desenho do WhatsApp):
  `GetAllStoriesRequest` (até 5 páginas) em `_buscar_historias`, chamada ao
  fim de `_atualizar_conversas` e por `UpdateStory` (`_ao_historia`, no máximo
  a cada 10 s). Cada pessoa vira `Conversa(id="status:<peer>", tipo="status")`
  e cada `StoryItem` uma `Mensagem` (id = id da história, `tipo_de_historia`,
  `dados_da_midia_de_historia`); `nao_lidas` = histórias acima de
  `max_read_id`; o que sumiu do servidor sai do banco. `_carregar` lê do
  banco; `_baixar` usa `GetStoriesByIDRequest` (`_midia_da_historia`);
  `_marcar_lida` manda `ReadStoriesRequest`; `_reagir` usa
  `stories.SendReactionRequest`; `responder_status` envia `SendMessageRequest`
  com `InputReplyToStory`. Não testado com histórias reais.
- Prévia de link buscada pelo TeleZapp (`nucleo/previa_links.py`), opções
  `previa_receber` e `previa_enviar` (desligadas; `LIGADAS`/`definir`).
  `buscar(url, baixar)` só abre http/https cujo nome resolva a endereços
  globais (`endereco_publico`, também em cada redirecionamento por
  `_SoPublico`), com 5 s e 400 KB, lê `og:*`, `twitter:*`, `description` e
  `<title>` (`ler_previa`) e nunca levanta. Recebida: `Janela._previa_da_recebida`
  (só ao vivo, texto, não minha, sem prévia) busca numa thread e grava com
  `_previa_pronta`. Enviada no WhatsApp: `_previa_ao_enviar` põe `matchedText`,
  `title` e `description` no `ExtendedTextMessage` e guarda a prévia na
  mensagem. No Telegram `send_message(link_preview=LIGADAS["enviar"])`: com a
  opção desligada a mensagem sai sem a prévia que o servidor montaria.
- Prévia de link: `extras["previa"]` ({url, titulo, descricao, site}), vinda do
  `ExtendedTextMessage` (`matchedText`, `title`, `description`) no WhatsApp
  (`previa_do_whatsapp`) e do `web_preview` no Telegram (`previa_do_telegram`);
  `guardar_extras(.., previa=)` a mantém quando outros extras são regravados.
  `modelos.trecho_da_previa` entra em `formatar` conforme a opção
  `previa_links` (`MODO_PREVIA`: completa, titulo, nenhuma) e `detalhes` a
  mostra sempre. Sem buscar a página na rede. Para mensagens enviadas daqui o
  WhatsApp não ganha prévia (isso exigiria abrir o link).
- Status do WhatsApp como conversas: `PREFIXO_STATUS` (`status:<jid>`), uma
  `Conversa(tipo="status")` por autor e os status como `Mensagem`s dela
  (`_guardar_status` agora grava a ficha, para baixar a mídia; publica
  `MensagemNova(silenciosa=True)`; `nao_lidas` = não vistos).
  `_limpar_status_antigos` apaga o que passou de 25 h (na conexão e a cada
  status). `marcar_como_lida` manda o recibo ao chat `status@broadcast`
  (`_enviar_leitura`). `responder_status` envia à conversa do autor um
  `ExtendedTextMessage` com `contextInfo(remoteJID="status@broadcast")`
  (`RESPOSTA_A_STATUS` no `resposta_a`, que não vai para o banco); curtir usa
  `reactionMessage` com `MessageKey(remoteJID="status@broadcast")` enviada ao
  autor. Janela: filtro `status` em `FILTROS_TIPO` (`passa_filtro` deixa os
  status só nele; `rotulo_conversa` diz "não vistos"), menu da conversa só
  com Abrir e Apagar status, `_enviar_texto` responde ao status selecionado
  e anexos/gravação são recusados. A tabela `status` antiga ficou sem uso.
  Não testado com status reais; Telegram (histórias) é a próxima etapa.
- Pacotes de sons e tela própria de Sons. `nucleo/pacotes_de_som.py`: pacotes
  `padrao` (bips do sistema, valor `fala.BIP`), `telezapp` (arquivos de
  `telezapp/sons`, gerados por `ferramentas/gerar_sons.py`: Ogg estéreo ≤ 2 s,
  sem silêncio no início, termina em zero, pico ≈ 0,45) e `p:<nome>`
  (pastas em `sons/pacotes/<nome>` com `<evento>.<ext>`). `mapa(pacote,
  desativados)` vira o `{evento: valor}` de `fala.definir_sons` (o pacote
  Padrão usa `BIP` explícito, então um evento desativado não silencia os que
  herdam o tom dele). `EstadoDeSons` guarda o que a tela mudou (pacote,
  eventos ativados/desativados, arquivos, pacotes a criar/excluir) e só grava
  em `aplicar()`, que importa os arquivos (`importar_arquivo`, nome do evento
  + extensão) e entrega `aplicador("sons_pacotes", {ativo, desativados,
  erros})`; `Janela._aplicar_opcao` grava `pacote_de_sons` e
  `sons_desativados`. As opções `som_*` saíram de `config.OPCOES`;
  `migrar_antigos` cria o pacote "Personalizado" a partir delas.
  `DialogoConfiguracoes._criar_sons`: Choice do pacote, ListBox dos eventos
  (Enter/Espaço alternam, tratados em `_ao_tecla`), Ouvir som e, só em
  personalizados, Procurar som; Novo e Excluir pacote. O backup leva
  `pacote_de_sons` e `sons_desativados` (EXTRAS) e a pasta `sons`. O spec do
  PyInstaller precisa de `datas` com `telezapp/sons`.
- `modelos.LIMITE_IA_NA_LINHA` virou um dicionário (`descricao`: foto,
  figurinha e vídeo, padrão 0 = inteira; `transcricao`: voz, áudio e PDF,
  padrão 1000), definido por `definir_limites_ia` a partir das opções
  `ia_linha_descricao` e `ia_linha_transcricao` (`Janela._carregar_limites_ia`).
- `_ia_pronto` fala o texto da IA inteiro (sem o corte de 1500 letras); no modo
  automático fala sempre, menos em conversa muda (`_conversa_muda`), sem
  depender de `falar_novas`.
- `midias_passo_progresso` (25, 20, 10, 5, 1 ou 0 = não falar): o passo da fala
  do avanço do download em `_ev_progresso_midia`. O WhatsApp só informa 0 e
  100 (`download_any` baixa tudo na memória), então só o Telegram usa.
- Fala das mensagens novas por lugar: `falar_novas` (conversa aberta),
  `falar_novas_outras_conversas` e `falar_novas_fora_do_telezapp` (janela
  sem foco, `IsActive()` falso, qualquer conversa); `Janela._deve_falar_nova`
  decide em `_ev_nova` e no resumo da sincronia. Independentes de `som`.
  `Config._carregar` liga as duas novas uma vez para quem já tinha
  `falar_novas` e não tinha as chaves novas no arquivo.
- Avisos de chamada do WhatsApp (o TeleZapp ainda não atende): o provedor
  registra `CallOfferEv`/`CallAcceptEv`/`CallTerminateEv` (`_ao_chamada`,
  `_ao_chamada_atendida`, `_ao_chamada_encerrada`; vídeo se a árvore do pacote
  tem a tag `video`; chamadas minhas em outro aparelho e em grupo ficam de
  fora). A linha na conversa é uma `Mensagem` de tipo `OUTRO` com id
  `chamada-<callID>` e `nao_lidas += 1`, publicada silenciosa; ao fim vira
  perdida, recusada ou atendida (com duração) via `MensagemAtualizada(
  "chamada")`. `ev.ChamadaWhatsApp` leva a janela `DialogoAvisoDeChamada`
  (OK e Conversar, sem bloqueio; opção `avisar_chamadas_whatsapp`); textos
  em `nucleo/chamadas.py` (`texto_na_conversa`, `texto_do_aviso`,
  `texto_do_fim`). Não testado com chamada real.
- Detalhes de mensagem de grupo: `modelos.detalhes(.., grupo, contagens)` troca
  a lista por "Enviada em" e "Recebida/Aberta/Reproduzida por N pessoas"
  (`pessoas_por_recibo`, `ROTULOS_RECIBO`, `texto_pessoas`).
  `dialogos.mostrar_texto(.., botoes_extra=[(rotulo, funcao(janela))])` põe
  os botões depois do texto. `detalhes.ControleRecibos` monta um botão por
  assunto com gente e abre `DialogoLista` (membro, telefone, data e hora);
  `_MembrosDeRecibo` reaproveita `ControleDetalhes._menu_membro`, então o
  menu é o dos membros do grupo; "Iniciar conversa" fecha os detalhes e abre
  a conversa (`abrir_conversa`). Só WhatsApp (o Telegram não guarda recibos
  por membro).
- `Janela._opcoes_midia`: o menu de contexto da mensagem com mídia ganha
  "Reproduzir/Abrir ..." (`ROTULOS_ABRIR`) e "Salvar cópia" ou "Baixar sem
  abrir", logo depois dos itens da IA, para o Enter configurado como IA ou
  só baixar não tirar o acesso a abrir.
- Reações e emojis: `nucleo/emojis.py` (pacote `emoji`, nomes em português
  pelo `demojize(language="pt")`, sem tons de pele; busca por início de
  palavra, sem acento, com `SINONIMOS`; `RAPIDOS`). `interface/emojis.py`:
  `DialogoEmoji` (busca + lista, seta para baixo na busca vai à lista) e
  `escolher_reacao` (rápidas + "Outro emoji..." + "Tirar"). Janela:
  `_reagir` (Ctrl+Shift+G e menu de contexto) e `_inserir_emoji` (Ctrl+.).
  `Provedor.PODE_REAGIR`/`reagir(msg, emoji)`: WhatsApp monta com
  `build_reaction` (autor = eu se a mensagem é minha, senão o remetente) e
  envia; Telegram usa `SendReactionRequest` (`ReactionInvalidError` avisa).
  As duas guardam a reação em `extras["reacoes"]` com `"minha": True` e
  publicam `MensagemAtualizada(motivo="reacao", quem="Você")` (a janela não
  fala as minhas). Telegram recebe `UpdateMessageReactions` (`_ao_reacoes`:
  `recent_reactions`, ou só a contagem em grupos grandes). `emoji>=2.14` em
  `requirements.txt`.
- Status no título: `ev.Presenca(conta_id, conversa_id, estado, quando, aprox,
  quem)`; `Provedor.observar_presenca` / `parar_presenca` (chamados ao abrir e
  ao fechar a conversa, só com a opção `status_no_titulo`). WhatsApp: abrir
  envia `send_presence(AVAILABLE)` (uma vez) e `subscribe_presence` (privadas);
  fechar volta a `UNAVAILABLE`; `PresenceEv` (online/`LastSeen`) e
  `ChatPresenceEv` (digitando/gravando/parou, com o nome nos grupos) viram
  `Presenca`. Telegram: `_ler_status` lê `user.status` ao abrir e
  `events.UserUpdate` (registrado por último em `_conectar`) traz online,
  visto por último (ou "recentemente", "na última semana", "no último mês"),
  digitando, gravando e enviando. `Janela._status_da_conversa` monta o
  sufixo do título com `modelos.texto_presenca`; "digitando" expira em 10 s
  se o "parou" não vier.
- Pareamento que falhava sem aviso: o registro mostrava
  `Failed to handle code pair notification` (código) e `Failed to pair device:
  invalid device identity HMAC` (QR, a chave ADV do QR já não era a do
  cliente depois de o servidor girá-la ou de um código ter sido pedido).
  `ProvedorWhatsApp._ouvir_falhas_do_pareamento` liga um `logging.Handler` em
  `whatsmeow.Client` (só enquanto `_pareando`) que publica
  `ev.PareamentoFalhou(conta_id, "codigo"|"qr")`; a janela avisa e chama
  `Contas.reiniciar_pareamento` (para, apaga a sessão se puder e liga de novo
  num fio), no máximo 3 vezes por janela. Escolher o QR depois de gerar um
  código também reinicia (`DialogoPareamento.codigo_gerado`).
  `DialogoPareamento.reiniciou()` limpa QR, código e a tela cheia.
- `DialogoPareamento`: o `RadioBox` virou uma página inicial com dois botões
  (`botao_telefone`, `botao_qr`); `_ir_para("inicio"|"codigo"|"qr")` troca de
  página (Voltar em cada uma). A página do telefone pede formato internacional
  (o campo e a mensagem de número inválido dizem isso). Ir para "qr" abre
  `JanelaQrCheia` na hora (`_tela_cheia(esperar=True)`), com "Aguardando o QR
  Code" até o QR chegar; o QR que chega com a página inicial aberta só fica
  guardado.
- Vídeo por quadros: `catalogo.video_nativo` (só o Gemini) e `aceita(.., "video")`
  agora vale para quem lê imagens; `provedores_da_tarefa("video")` lista os cinco.
  `nucleo/ia/video.grade_de_quadros` (OpenCV, import tardio; `opencv-python-headless`
  entrou em `requirements.txt` e em `docs/licencas-de-terceiros.md`) monta um
  JPEG com 4/9/12 quadros (perfil curto/médio/detalhado) com a hora desenhada em
  cada um. `servico.executar` usa a grade quando o provedor não é nativo ou o
  vídeo passa de 14 MB (`Resultado.via_quadros`, `prompts.instrucoes(.., quadros=n)`).
  `executar_em_ordem(.., ordem_audio=)` soma "Fala no vídeo" transcrevendo o
  próprio mp4 (`mime="video/mp4"`) pelos provedores de áudio. `montar_pedido`
  recusa vídeo inteiro para quem não é nativo.
- IA automática: opção por conversa em `ia_automatica_conversas` (lista de
  `[conta, conversa]`, vai na parte "contas" do backup), alternada no menu de
  contexto da conversa (`_alternar_ia_auto`). `_ev_nova` chama `_ia_automatica`
  para mensagens recebidas (não minhas, não da sincronia). Opções `ia_auto_audio`
  e `ia_auto_imagem`. `_ia_processar(x, auto=True)`: sem janelas nem perguntas
  (sem provedor, chave ou consentimento, só retorna), baixa com
  `midias.baixar(x, automatica=True)` (`_ia_pendentes` guarda `(x, auto)`) e no
  máximo 2 pedidos ao mesmo tempo (`_ia_vagas`). `_ia_pronto(.., auto)`: erro só
  na barra de situação; resultado na barra e falado (sem interromper) se
  "Falar mensagens novas" estiver ligado e a conversa não estiver muda.

- `janela.ListaDeTextos`: `wx.ListCtrl` de uma coluna com a interface do
  `wx.ListBox` (`Set`, `Append`, `Delete`, `SetString`, `GetSelection`,
  `SetSelection`, `HitTest` que devolve só o índice). `lista_conv` passou do
  ListBox para ela, pelo mesmo motivo da lista de categorias das
  configurações: o ListBox faz o NVDA falar o item em foco duas vezes. O duplo
  clique virou `EVT_LIST_ITEM_ACTIVATED`; `testes/wx_falso.py` ganhou um
  `ListCtrl` falso.
- `DialogoConfiguracoes._ao_tecla`: seta para baixo no campo de busca foca o
  primeiro controle dos resultados (ou a lista de categorias, sem busca ou sem
  resultado).

## 2026.10.18.0

Copiar por tipo de conteúdo e colar mídia na caixa.

- `modelos.conteudos_copiaveis(msg)` lista `(tipo, rótulo, valor)` com um item
  por tipo de conteúdo (legenda/texto, mídia, cada link); sem nada, cai no
  texto falado. `_menu_mensagem` monta os itens "Copiar ..." a partir dela e
  `_copiar_conteudo` copia texto/endereço ou o arquivo baixado (`wx.FileDataObject`
  e, na foto, também `BitmapDataObject`, num `DataObjectComposite`).
  Control Shift C segue copiando `texto or conteudo`.
- Colar na caixa (`EVT_TEXT_PASTE` → `_ao_colar`): lista de arquivos do
  Explorer, ou bitmap quando não há texto na área de transferência (salvo em
  PNG na pasta temporária), vira `envio.Anexo` em `Janela.anexos`, sem enviar.
  Texto puro segue o fluxo normal (`evt.Skip()`). Enter (`_enviar_texto` →
  `_enviar_anexos`) manda cada anexo; o texto da caixa é a legenda do primeiro
  que aceita (não áudio/voz), senão vai como texto depois. Esc na caixa
  (`_sair_da_caixa`) descarta; abrir/fechar conversa também.
- A leitura da área de transferência foi para `interface/colagem.py`
  (`ler`, `colar`, `descartar`), usada pela caixa da janela e pelo campo
  Mensagem de `DialogoNovaMensagem`, que agora devolve
  `(conta_id, destino, texto, pessoa, anexos)`; `_nova_mensagem` põe os anexos
  em `Janela.anexos` antes de `_enviar_texto`. Esc no campo remove a mídia.
- Salvar o conteúdo da conversa (`_salvar_conversa`, menu de contexto da
  lista e Menu, Conversa): `nucleo/exportar.gravar_zip` grava `conversa.txt`
  (UTF-8 com BOM) e `midias/<data>_<id>_<nome>` das mídias baixadas e não
  limpas, numa thread; o aviso final vem por `wx.CallAfter`. Pasta lembrada
  em `pasta_exportar`; `dialogos.escolher_destino_zip`.
- `modelos.quem_enviou` (nome da conversa privada, agenda, nome guardado,
  telefone) substitui "Desconhecido" na lista, na fala e no arquivo salvo;
  `formatar(..., quem=)` recebe o resultado de `Janela._quem_enviou` (com
  cache, limpo ao abrir conversa ou mexer nos contatos). No estilo "autor só
  quando muda" o remetente também conta como mudança.
- Modo de seleção (Control Espaço / Espaço / Esc em `_char_hook`):
  `modo_conv`/`marc_conv` (chaves) e `modo_msg`/`marc_msg` (ids); o prefixo
  "Marcada: " entra nos rótulos (`_com_marca`) e os `_preencher_*` atualizam
  no lugar. Com marcas, os menus de contexto viram `_opcoes_em_massa_conv/msg`
  (`_massa_conversas`, `_massa_mensagens`; uma pergunta só ao apagar). A
  seleção de mensagens zera ao abrir ou fechar a conversa.
- Apagar conversa de grupo: `dialogos.escolher_acao_grupo` (limpar, apagar
  da lista, sair, sair e apagar). `_limpar_conversa` usa `limpeza` (todas as
  mensagens, favoritas incluídas) e mantém a conversa; `_sair_do_grupo` chama
  `Provedor.sair_do_grupo` (`SAI_DE_GRUPO`; WhatsApp `leave_group`, Telegram
  `delete_dialog`) numa thread e só tira da lista se deu certo.
- WhatsApp: em mensagem `IsFromMe` o `Pushname` é o da própria conta; deixa
  de ser passado a `_conversa` (as duas chamadas ao vivo), e `_conversa`
  renomeia conversa privada que ficou com o nome da conta.
- WhatsApp: `ChatMarkAsReadEv` passa a ser tratado (`_ao_marcar_lida`): zera
  `nao_lidas` se não há mensagem mais nova que a marca (`messageRange`). Os
  recibos de outro aparelho meu (lida/ouvida) agora vão para o log, para
  diagnosticar a marca de ouvida.
- Atualização: `nucleo/atualizacao.py` lê as Releases do GitHub
  (`consultar`, `mais_nova`, `e_mais_nova`); `Janela._verificar_atualizacoes`
  (Ajuda, e 8 s depois de abrir se `verificar_atualizacoes`); só avisa, não
  instala. `ferramentas/publicar.py` monta o zip, o SHA-256 e as notas
  (`lancamento/`) e, com `--publicar`, chama `gh release create`
  (pré-lançamento por padrão).
- Backup e restauração: `nucleo/backup.py` (zip com `pyzipper`, AES-256 com
  senha opcional; partes configuracoes, contas, conversas, midias;
  `criar`, `ler_manifesto`, `restaurar`, `aplicar_pendente`). Configurações
  se aplicam na hora por `_aplicar_opcao`; o resto vai para `restauracao/` e
  `__main__` chama `aplicar_pendente` antes de abrir o banco, guardando o
  anterior em `antes-da-restauracao/`, e acerta os caminhos de `midias`.
  `Banco.copiar_para` usa a API de backup do SQLite. `OPCOES_FORA`
  (depuração e exigência do código) nunca são restauradas. Nova dependência:
  `pyzipper`. Telas em `interface/backup.py`. Ao terminar, `_reiniciar`
  fecha a janela e um `cmd` separado (`timeout` + `start`) abre outra instância.
- Sons dos eventos: `config.EVENTOS_SOM` gera as opções `som_<evento>`
  (categoria Sons, `Opcao.som`); valor "" (padrão), "desligado" ou caminho.
  `fala.definir_sons`/`acao_do_som`/`bipe(tipo, valor=None)`; arquivo toca
  por `soundfile` + `sounddevice` (`_tocar_arquivo`, 15 s no máximo) e cai
  no beep se falhar. O valor é o nome do arquivo em `config.pasta_sons()`
  (`importar_som` copia para lá); caminho completo antigo ainda vale. A pasta
  `sons/` vai na parte configuracoes do backup e volta na hora; arquivo que
  sumiu cai no beep. Menu Ajuda, Abrir a pasta de sons. `DialogoConfiguracoes._criar_som` (caixa + Ouvir);
  `Janela._carregar_sons` ao abrir e ao mudar uma opção `som_*`.
- Contatos recebidos: `whatsapp.telefones_do_vcard` e `contatos_da_mensagem`
  (um item por TEL, `waid=` dá o id) entram em `mencoes` (nome, telefone, id)
  nos dois caminhos de conversão; o texto traz o telefone. Telegram:
  `msg.contact` gera o mesmo item e o telefone no texto.
- `modelos.conteudo`: tipo `OUTRO` com texto descritivo (contato, enquete...)
  mostra só o texto; "mensagem sem suporte ainda" só para o não reconhecido
  (texto vazio ou "tipo do WhatsApp: ...").
- Encaminhar: `nucleo/encaminhar.py` (`preparar` → `Item` texto ou arquivo,
  `destinos`, `filtrar`); `interface/encaminhar.py` (`DialogoEncaminhar`,
  CheckListBox com busca e marcas persistentes); `Janela._encaminhar`
  (Ctrl+Shift+E, menu de contexto e modo de seleção) reenvia por
  `enviar_texto`/`enviar_arquivo` da conta de cada destino. Não usa o
  encaminhamento nativo (sem o rótulo "Encaminhada"); mídia só se baixada.
- Responder em particular: `Janela._responder_em_particular` abre/cria a
  conversa privada de `pessoa_da_mensagem` e põe a mensagem do grupo em
  `resposta_a`; `_mensagem_de_texto` do WhatsApp, quando a citada está em
  outra conversa, copia texto/autor dela e põe `contextInfo.remoteJID`.
  Só onde o provedor sabe achar o telefone (WhatsApp).
- Mais eventos de som: `nova_aberta`, `nova_grupo`, `desconectada`,
  `reconectada`, `falha_envio`, `download_pronto`, `tarefa_pronta`
  (`config.EVENTOS_SOM`). `fala.HERDA` faz o evento tocar o som (e seguir a
  escolha) de outro quando não tem escolha própria (`tom_padrao`,
  `acao_do_som` recursivo). `_ev_estado` guarda `_caiu` para só tocar
  "reconectada" depois de uma queda.
- Conversas somente leitura: `Conversa.somente_leitura` (coluna nova no
  banco). WhatsApp: canais sempre; grupos por `_conferir_escrita` (anúncio
  sem ser admin, ou 403 = saí) ao abrir (`conversa_aberta`) e ao mudar o
  grupo. Telegram: `somente_leitura_do_telegram(entidade)`. Janela:
  `_mostrar_conversa(True, False)`, `_somente_leitura()` barra
  responder/enviar/anexar, `_ev_conversas` reage à mudança, e
  `encaminhar.destinos` as ignora.
- Editar mensagem: `Provedor.JANELA_EDICAO`/`editar_mensagem` (WhatsApp:
  `edit_message` do neonize com `_mensagem_de_texto`, mantendo a citação;
  Telegram: `edit_message`); sucesso vira `MensagemAtualizada("editada")`,
  falha vira `Aviso`. Janela: `_pode_editar`, `_editar_mensagem` (F2),
  `_salvar_edicao`, `_cancelar_edicao`, rótulo "Editando sua mensagem";
  a caixa guarda o rascunho enquanto edita.
- Detalhes da conversa: `nucleo/detalhes.py` (`classes`, `midias`,
  `estatisticas`, `linhas_de_uso`; filtros foto/vídeo/link/documento/
  figurinha/contato/voz/áudio); `interface/detalhes.py` (`ControleDetalhes`,
  `DialogoTexto`, `DialogoLista`, `DialogoAdministrar`); `Janela`:
  `_detalhes_da_conversa` (Ctrl+I), `_opcoes_da_conversa` (itens do menu
  compartilhados com membros e grupos em comum), `_garantir_conversa`,
  `_ver_na_conversa`. Provedores: `dados_do_contato`, `detalhes_do_grupo`,
  `detalhes_do_canal`, `grupos_em_comum`, `administrar_grupo`,
  `administrar_canal`. Telegram: `_administrar` (nome, descrição, direitos
  padrão do grupo, adicionar, remover, promover, link, sair).
  `administrar_canal` só no WhatsApp.
- Entrar em grupos: ações do tipo `entrar` em `extras["acoes"]`
  (`whatsapp.entradas_de_grupo`: `groupInviteMessage` e links
  chat.whatsapp.com; `telegram.entradas_do_telegram`: t.me/+, joinchat e
  t.me/nome). `Janela._tocar_acao` desvia para `_entrar_no_grupo` (prévia
  em thread, confirmação, `entrar_no_grupo`). Provedores:
  `previa_do_convite` e `entrar_no_grupo` (neonize `join_group_with_invite`/
  `with_link`, `get_group_info_from_*`; Telethon `CheckChatInvite`,
  `ImportChatInvite`, `JoinChannel`).
- Provedores de IA: pacote `nucleo/ia` (`catalogo`: provedores, capacidades,
  limites; `prompts`; `provedores`: `montar_pedido`/`ler_resposta` puros para
  Gemini, OpenAI, Claude, Groq e OpenRouter, transcrição multipart na OpenAI
  e Groq; `servico`: `executar`, `testar`, HTTP por urllib; `cofre`: chaves
  cifradas com DPAPI em `ia_chaves.json`, fora do backup). Opções
  `ia_audio/imagem/video/pdf/perfil` e `ia_modelos`/`ia_consentimento` em
  `Config`. Janela: `_opcoes_ia`, `_ia_processar` (consentimento, download
  prévio por `_ia_pendentes`, thread), `_ia_pronto` (grava `extras["ia"]`),
  `_ia_ver`; `modelos.trecho_da_ia` na linha e `conteudos_copiaveis`.
  Configurações: bloco de chaves/modelos em `_criar_ia`, `_IaParaConfig`.
  Ordem de tentativa: `ia_ordem` (tarefa → provedores ligados, em ordem;
  substitui as opções `ia_audio/imagem/video/pdf`), `servico.executar_em_ordem`
  (passa ao próximo em `PROXIMO_PROVEDOR`), lista de modelos por GET
  (`pedido_de_modelos`, `ler_modelos`, `listar_modelos`, cache
  `ia_lista_modelos`), `cadeia_de_modelos` (automático) e a caixa combinada
  de modelos em `_criar_ia`. `ia_ordem` e `ia_modelos` entram no backup.
  `servico.enviar_pela_rede` manda `User-Agent: TeleZapp/<versão>` (a Groq,
  atrás da Cloudflare, dava 403 erro 1010 ao User-Agent do Python e parecia
  chave recusada) e `_erro_http` lê o corpo (o Gemini responde 400 a chave
  inválida).
  A tela de IA ficou com a ordem das tarefas e um botão por provedor que abre
  `DialogoProvedorIA` (chave, combo de modelo, Obter modelos, Testar).
  Opções `enter_audio/imagem/video/pdf` (abrir, baixar ou ia) em
  `Janela._enter_na_midia`; `_opcoes_ia` é o primeiro item de `_menu_mensagem`.
  Fica para depois: modo automático por conversa, vídeo para outros
  provedores (quadros), arquivos acima de 14 MB, perguntas de acompanhamento.
- `_enviar_arquivo` foi dividido: `_enviar_anexo` recebe o anexo já preparado.
- `_rotular_caixa` monta o rótulo da caixa (resposta e mídias coladas).

## 2026.10.17.0

Foco inicial na conta.

- `Janela.comecar` põe o foco em `cx_conta` (antes `lista_conv`) ao abrir.
- `_preencher_conversas` atualiza a lista no lugar (`SetString`/`Append`/
  `Delete`) e só repõe a seleção se o índice mudou, em vez de `Set()` a cada
  mudança de ordem: o NVDA repetia o nome da conversa durante as atualizações.
- Menu de contexto na lista de conversas (`_menu_conversa`, botão direito ou
  tecla Menu/Shift+F10): Abrir, Arquivar/Desarquivar, Salvar como contato
  (só pessoas) e Depurar conversa (só com a depuração ligada). Age sobre a
  conversa selecionada; `_arquivar_conversa`, `_salvar_pessoa` e
  `_depurar_conversa` aceitam `conv`.
- Trancar pelo TeleZapp (`_trancar_conversa`; Menu, Conversa, e no menu de
  contexto): marca `Conversa.trancada` só no TeleZapp, como o arquivar do
  WhatsApp. As trancadas por aqui ficam em `trancadas_locais` na config e são
  reaplicadas em `_juntar_conversas` (o Telegram recria as conversas a cada
  leitura). Destrancar tira da lista; uma trancada no celular destrancada aqui
  só vale até o celular mudar. Se o celular destranca uma conversa trancada
  aqui, ela continua trancada aqui até ser destrancada aqui.
- Limpeza de mídias e mensagens (Menu, Mídias, Limpar mídias e mensagens):
  `nucleo/limpeza.py` (`Filtros`, `selecionar`, `apagar`), `interface/limpeza.py`
  (`DialogoLimpeza`). Escolhe entre só as mídias baixadas ou as mensagens
  (com as mídias delas); filtros: conta, conversa, tipo (inclui texto), idade
  em dias e tamanho mínimo. Mostra a contagem e o espaço e só apaga depois do
  Sim.
- Registro do que foi limpo: tabela `limpas` (`alvo` 'mensagem' ou 'midia'),
  `Banco.registrar_limpeza`, `foi_limpa`, `apagar_mensagens`, `apagar_fichas`,
  `mensagens_para_limpar`, `todas_midias`. `salvar_mensagens` e
  `Janela._mesclar`/`_ev_nova` descartam mensagens limpas; `GerenteMidias.baixar`
  e `_abrir_midia` recusam mídias limpas (`TEXTO_LIMPA`); a ficha de download
  do WhatsApp é apagada. Só um novo pareamento
  (`Contas.parear_de_novo` -> `esquecer_limpezas`) ou remover a conta
  (`apagar_conta`) zera o registro.
- Apagar conversa (menu de contexto da lista, `Janela._apagar_conversa`,
  `Banco.apagar_conversa`, `armazem.apagar_conversa`): tira do banco a
  conversa, mensagens, recibos, fichas, mídias (arquivos e pasta) e posição, e
  registra em `apagadas` a data da última mensagem (`ate`). Conversas e
  mensagens com `data <= ate` são descartadas em `salvar_conversas`,
  `salvar_mensagens`, `_juntar_conversas`, `_mesclar` e `_ev_nova`; a
  conversa volta quando chega mensagem mais nova. Novo pareamento
  (`esquecer_limpezas`) e remover a conta zeram o registro. Só local: a
  conta não é afetada.
- Conversa apagada no celular (WhatsApp): o whatsmeow emite `events.DeleteChat`
  na sincronia de estado, mas o neonize não o repassava. A DLL de teste ganhou
  o evento 51 (`ChatDeleteEv`, mensagem `ChatDelete` no proto, `case
  *events.DeleteChat` em `goneonize/main.go`, `neonize/events.py` e
  `aioze/events.py`). `WhatsApp._ao_apagar_conversa` tira a conversa do
  provedor e publica `ev.ConversaApagadaNoCelular`; `Janela._ev_conversa_apagada`
  apaga aqui como em "Apagar conversa" (`_remover_conversa_local`), mas só se a
  conversa não tem mensagem mais nova que o aviso (margem de 5 s).
- Apagar no TeleZapp e no celular (WhatsApp): "Apagar conversa..." pergunta
  "Apagar aqui e no celular", "Apagar só aqui" ou "Cancelar" quando a conta
  está conectada (`Provedor.APAGA_NA_CONTA`). `WhatsApp.apagar_conversa` monta o
  aviso de estado `deleteChat` (REGULAR_HIGH, versão 6, faixa de mensagens até a
  última guardada, apagando também as mídias do celular: índice "1") e o manda com
  `send_app_state`, numa thread; o resultado é falado. Exigiu corrigir a DLL
  de teste: `DecodePatchInfo` do neonize comparava ponteiros de enum
  (`PatchInfo_X.Enum()`) e nunca casava, deixando o tipo do patch vazio, e não
  tratava REGULAR_HIGH/REGULAR_LOW. Corrigido em `utils/decoder.go` (branch
  `fix/patchinfo-type` do worktree neonize-fix). O Telegram não entra: apagar
  o diálogo lá sai de grupos e canais.
- Conversas fixadas e silenciadas: `Conversa.fixada` e `silenciada_ate` (0 com
  som, -1 para sempre, senão o timestamp; `Conversa.silenciada()`), colunas
  novas no banco (esquema 10). Fixadas vão para o topo (`_ordenar`) e o
  rótulo ganha ", fixada" e ", silenciada"; tipos novos Fixadas e Silenciadas
  em `FILTROS_TIPO`; conversa silenciada fechada não avisa mensagem nova
  (`_conversa_muda`). WhatsApp: histórico (`pinned`, `muteEndTime`), avisos
  ao vivo `ChatPinEv`/`ChatMuteEv` (DLL de teste, eventos 47 e 48) e a
  conferência de 60 s agora lê Arquivada, Fixada e MutedUntil do armazém numa
  consulta só (`_ajustes_no_celular`). Telegram: `d.pinned` e
  `notify_settings.mute_until` (sem aviso ao vivo; vale a cada leitura).
- Fixar e silenciar pelo TeleZapp (Menu, Conversa, e no menu de contexto):
  `Janela._fixar_conversa` e `_silenciar_conversa` (8 horas, 1 semana ou
  sempre) mudam aqui na hora e avisam a conta numa thread
  (`fixar_conversa`/`silenciar_conversa` nos provedores). WhatsApp manda
  `pin_v1` (versão 5, REGULAR_LOW) e `mute` (versão 2, REGULAR_HIGH) com
  `send_app_state`; Telegram usa `ToggleDialogPinRequest` e
  `UpdateNotifySettingsRequest`. Se o serviço não aceita, a fala avisa que
  ficou só no TeleZapp.
- Voz ouvida nos dois sentidos: `Janela._marcar_ouvida` agora chama
  `Provedor.marcar_ouvida`. WhatsApp manda o recibo `PLAYED` (ou `PLAYED_SELF`
  com a confirmação de leitura desligada, para só os próprios aparelhos
  saberem) com `mark_read`; Telegram usa `messages.ReadMessageContents`
  (`channels.` nos canais). Do celular para cá, o WhatsApp já tratava o
  recibo `played-self`; o Telegram ganhou o aviso ao vivo
  (`UpdateReadMessagesContents` e a versão de canal, `_ao_conteudo_lido`,
  `Banco.mensagens_por_id`), que antes só valia ao carregar a conversa.
- Mensagem do WhatsApp que não deu para decifrar (`UndecryptableMessageEv`,
  `WhatsApp._ao_indecifravel`): registra o aviso no log (id, conversa,
  remetente, modo) e deixa no lugar da mensagem uma marca do tipo
  `AGUARDANDO` ("mensagem ainda não recebida"), sem alerta. O whatsmeow pede de
  novo ao remetente; quando a de verdade chega, com o mesmo id, ela substitui
  a marca (`INSERT OR REPLACE` e o cache por id). Eventos que só trazem
  controle e eram ignorados sem rastro agora deixam uma linha no log.
- Apagar mensagem nos dois sentidos (Menu, Mensagem, e menu de contexto da
  lista de mensagens): `Janela._apagar_mensagem` pergunta e tira a mensagem
  daqui na hora (`limpeza.apagar_mensagem`: apaga a mídia, a mensagem e
  registra em `limpas`, então não volta por histórico nem nova leitura). As
  minhas têm "Apagar para todos" (`revoke_message`) ou "só para mim"; as dos
  outros, só "para mim" (aviso de estado `deleteMessageForMe`, versão 3,
  REGULAR_HIGH, com a mídia). Telegram: `delete_messages(revoke=...)`. Do
  celular para cá: a DLL de teste ganhou o evento 52 (`MessageDeleteForMeEv`,
  `events.DeleteForMe`) e o Telegram usa `events.MessageDeleted`; ambos
  publicam `ev.MensagemApagadaNoCelular` (`Janela._ev_mensagem_apagada`).
  "Apagar para todos" feito pelo remetente continua aparecendo como "mensagem
  apagada", como no WhatsApp.
- Tipos do WhatsApp que apareciam como "mensagem sem suporte ainda":
  `ptvMessage` (mensagem de vídeo: vira vídeo e baixa pela ficha como
  `videoMessage`), `contactsArrayMessage` ("N contatos: nomes"),
  `eventMessage` ("evento: nome, início, fim, local, link, descrição" ou
  "evento cancelado"), `productMessage` ("produto: título, preço, link") e
  `secretEncryptedMessage` (edição cifrada de evento ou enquete: passa a ser só
  controle, `SO_CONTROLE`, em vez de uma linha vazia). As mensagens antigas
  que já estavam guardadas como "tipo do WhatsApp: ..." não mudam.
- Contato do TeleZapp reconhecido pelo WhatsApp: `WhatsApp.salvar_contato`
  manda o aviso de estado `contact` (coleção `critical_unblock_low`, versão 2)
  com `ContactAction(fullName, firstName, pnJID, lidJID quando conhecido,
  saveOnPrimaryAddressbook=False)`, o mesmo do WhatsApp Web ao adicionar um
  contato: o celular reconhece a pessoa e nada é gravado na agenda do
  aparelho. Chamado ao adicionar e editar contatos e ao salvar a pessoa da
  conversa (`contatos.avisar_conta`, em segundo plano). "Trazer das contas"
  não devolve nada à conta, e remover um contato do TeleZapp não o remove do
  WhatsApp. O Telegram fica de fora.
- Salvar quem enviou a mensagem como contato (Menu, Contatos, e menu de
  contexto da lista de mensagens, nas mensagens recebidas com remetente):
  `Janela._salvar_autor`, `Provedor.pessoa_da_mensagem` (o endereço LID do
  remetente vira o telefone) e `Banco.renomear_autor`, que põe o nome nas
  mensagens já guardadas e no cache. Também avisa a conta
  (`contatos.avisar_conta`). Só no WhatsApp: o Telegram não guarda o remetente.
- Mensagens favoritas: chave `favorita` nos extras (`extras_de`), "(favorita)"
  na linha, `Janela._favoritar_mensagem` (Menu, Mensagem, Ctrl+Shift+F, e menu
  de contexto). No WhatsApp vai e vem com a conta: aviso de estado `star`
  (versão 2, REGULAR_HIGH) e o evento 53 da DLL de teste (`MessageStarEv`,
  `events.Star`), mais `WebMessageInfo.starred` no histórico. No Telegram vale
  só no TeleZapp (`Provedor.FAVORITA_NA_CONTA`).
- Limpeza: caixa "Manter as mensagens favoritas" (ligada por padrão,
  `Filtros.manter_favoritas`, `Banco.favoritas`): as favoritas e as mídias
  delas ficam fora de `selecionar`.
- Estado do aplicativo fora de sincronia (`mismatching LTHash`): depois de
  mandar avisos de estado daqui, as coleções `regular_high` e
  `critical_unblock_low` ficaram sem aplicar os avisos do celular (favoritar,
  desfavoritar...) e recusavam os daqui (409). A DLL de teste ganhou
  `FetchAppState` (`NewClient.fetch_app_state(nome, full_sync)`, nova no
  `_binder.py` e no `client.py`). `WhatsApp._conferir_estado` roda ao
  conectar: sincroniza cada coleção e, se ela não bate, baixa de novo;
  `_enviar_estado` faz o mesmo e repete o envio uma vez quando o WhatsApp
  recusa por conflito. Na sincronia completa só os estados (arquivada,
  fixada, silenciada, favorita) são aplicados: apagar conversa e apagar
  mensagem do celular só valem ao vivo (`FromFullSync` é ignorado).
- Causa do `mismatching LTHash`: o celular reescreve registros antigos do
  estado (troca de endereço telefone/LID, nova chave) e o whatsmeow não
  consegue conferir o patch, mesmo com a coleção baixada do zero
  (tulir/whatsmeow#858; ferramenta de diagnóstico em
  `goneonize/cmd/diag`, que mostra as mutações do patch que falha). O
  caminho oficial é pedir ao celular uma cópia nova: a DLL de teste ganhou
  `RequestAppStateRecovery` (`NewClient.request_app_state_recovery`), que o
  `_recuperar_colecao` usa depois do download completo e espera até 90 s
  (`ESPERA_DA_RECUPERACAO`). O iPhone responde na hora com o WhatsApp
  aberto; senão a pessoa é avisada para abri-lo e o TeleZapp tenta de novo ao
  reconectar. A reparação roda numa thread própria (`_conferir_estado`).
- Resposta cujo original o próprio TeleZapp tirou: a linha diz "em resposta a
  uma mensagem que foi limpa deste computador" ou "de antes de a conversa ser
  apagada", e "Ir para a mensagem respondida" explica o motivo
  (`Janela._motivo_do_original_ausente`), em vez de "mais antiga". Mais
  envelopes do WhatsApp abertos (`EMBRULHOS`: menção a todos, spoiler,
  pergunta...).
- Configurações > Privacidade: a leitura da conta (`privacidade.ler`, que vai ao
  serviço) roda em thread (`_trocar_conta_priv`, `_priv_lido`); a categoria
  abre na hora com as caixas apagadas e "Lendo a privacidade da conta...".
  O resultado fica em cache enquanto a janela está aberta.
  A categoria Privacidade passou para a última posição da lista
  (`nucleo/configuracoes.categorias`), depois de Avançado.

## 2026.10.16.9

Nova mensagem, contatos do Telegram e rótulos para o NVDA.

- Nova mensagem (Ctrl+N): `DialogoNovaMensagem` (a conta só aparece se há 2+
  conectadas), `nucleo/nova_mensagem.py` (`tipo_de_destino`, `candidatos`),
  provedor `resolver_destinatario` (Telegram: `get_entity`) e
  `id_do_telefone` (WhatsApp). Abaixo do campo Para, lista de contatos e
  conversas que filtra enquanto se digita (nome ou dígitos do telefone).
- Contatos do Telegram: `contatos_da_conta` lê `contacts.GetContacts` (sem
  bots nem apagados); o botão do gerenciador passa a ser "Trazer das contas".
- Janelas novas criam o rótulo ANTES do controle (o NVDA usa o texto anterior
  como nome do campo): `DialogoContato` e `DialogoNovaMensagem`.

## 2026.10.16.8

Privacidade das contas.

- Privacidade do WhatsApp e do Telegram em Configurações > Privacidade
  (`nucleo/privacidade_conta.py`; provedor `privacidade()`,
  `definir_privacidade()`, `privacidade_status()`): visto por último, online,
  recado (`status` no whatsmeow), confirmação de leitura e quem adiciona a
  grupos; aplicar relê e confere. Status (stories) só leitura: o whatsmeow
  só tem `GetStatusPrivacy`.
- Telegram: `GetPrivacy/SetPrivacy` com as chaves StatusTimestamp, About e
  ChatInvite, e `GlobalPrivacySettings.hide_read_marks`; `valor_das_regras`,
  `ErroPrivacidade`.

## 2026.10.16.7

Contas ativáveis.

- `ativa` (padrão verdadeiro) no registro da conta; `Contas.ativar/
  desativar/esta_ativa`; `iniciar_salvas` e `reconectar` pulam as
  desativadas (continuam em `Contas.contas`, para o serviço ser conhecido);
  menu Contas > Ativar ou desativar contas (`wx.MultiChoiceDialog`).

## 2026.10.16.6

Fala configurável na sequência de áudios.

- `modelos.anuncio_sequencia` e as opções `seq_falar_proximo/tipo/quem/
  duracao/velocidade/fim` (Mídias; o fim vem de `_fim_da_sequencia`, só com
  2+ áudios na sequência). Na sequência elas substituem `falar_quem_toca`,
  que fica só para o 1º áudio.
- Padrão de falar pouco: `falar_novas`, `confirmar_envio`, `falar_reacoes`,
  `falar_quem_toca` e `seq_falar_*` vêm desmarcadas (quem já salvou mantém).

## 2026.10.16.5

Conversas trancadas, busca e código secreto.

- `Conversa.trancada` (WhatsApp "Trancar conversa"; coluna nova): vem do
  `locked` das conversas do pacote de histórico. Fora de todos os tipos, só
  no tipo `trancadas`. O neonize 0.5.2 não repassa o `lockChatAction` e o
  whatsmeow não o guarda (`chat_settings` só tem mudo, fixada e arquivada):
  sem estado ao vivo, a menos do neonize de teste (ver `Backup/`).
- Busca de conversas (`campo_busca`, `modelos.casa_busca`) e código secreto
  das trancadas (`nucleo/codigo_secreto.py`: PBKDF2 com sal, só o resumo no
  config). Digitar o código na busca libera o tipo Trancadas (no fim da
  caixa de tipos); trocar de filtro, Ctrl+Shift+T, minimizar ou reabrir
  escondem. Opção `trancadas_exigir_codigo` (Privacidade, padrão ligada);
  sem código definido elas ficam escondidas. O código é definido em
  Configurações > Privacidade (`ModeloConfiguracoes.erro_codigo/
  acao_codigo`); mudar ou desligar pede o código atual e não há
  redefinição: parear o WhatsApp de novo apaga o código
  (`_limpar_codigo_trancadas`).
- Arquivadas e trancadas (fechadas) não avisam: `_conversa_muda` em
  `_ev_nova` e `_ev_atualizada` (sem som, fala nem texto na barra).

## 2026.10.16.4

Filtros da lista e conversas arquivadas.

- Filtros da lista de conversas: duas caixas acima da lista (`cx_conta`:
  todas, serviço e, com 2+ contas do serviço, cada conta; `cx_tipo`: todas,
  não lidas, pessoais, grupos, canais, arquivadas). `modelos.passa_filtro`,
  `opcoes_de_conta`, `FILTROS_TIPO`; valores `filtro_conversas` (tipo) e
  `filtro_conta` (só no config). Alt+4/Alt+5. `Janela.conversas` é só o que
  passa (mais a aberta); sem nenhuma, a lista avisa.
- `Conversa.arquivada` (coluna nova no banco). Telegram: duas buscas
  (`folder=0` e `folder=1`, a principal não traz as arquivadas) e
  `arquivar_conversa` (`edit_folder`); item de menu Arquivar/desarquivar
  (`_arquivar_conversa`; WhatsApp: só local). WhatsApp: o neonize não repassa
  o aviso de arquivar, mas o whatsmeow grava o estado em `chat_settings`;
  `_conferir_arquivadas` lê `chat_settings.get_chat_settings` a cada 60 s,
  no F5 e depois de um pacote de histórico (a 1ª leitura de cada conversa
  vale; depois só uma mudança do celular conta). Arquivadas só aparecem no
  tipo Arquivadas.

## 2026.10.16.3

Mensagens carregadas por conversa e listas de transmissão.

- Opção `mensagens_por_conversa` (Leitura, 50 a 5000, padrão 1200): vira o
  `LIMITE_MEMORIA` da janela (`_limite_memoria`). `Opcao.numero` é novo:
  opção numérica digitada (wx.SpinCtrl na janela de configurações; o modelo
  limita ao intervalo).
- Listas de transmissão do WhatsApp (`@broadcast`) deixam de aparecer como
  conversa; mensagens recebidas por lista vão para a conversa de quem as
  enviou; o envio para uma lista avisa que não é aceito
  (`ListaDeTransmissao`).

## 2026.10.16.2

Agenda de contatos própria.

- Tabela `contatos` no banco (`salvar_contato`, `remover_contato`,
  `contatos`, `nome_de_contato` com cache). `interface/contatos.py` tem o
  gerenciador (Adicionar, Editar, Remover, Trazer das contas) e o diálogo
  "Salvar a pessoa desta conversa". O nome vale nas conversas privadas
  (`_juntar_conversas`) e no `_nome_contato` do WhatsApp; Telegram: só nas
  conversas. Nada é gravado na conta (local).
- Provedor: `contatos_da_conta()` (WhatsApp lê `get_all_contacts`) e
  `id_do_telefone()`.

## 2026.10.16.1

Menções como botões e nomes melhores nas menções.

- Menções viram botões "Pessoa: nome" na ordem do Tab. Nome da menção:
  agenda, pushname visto nas mensagens, participantes do grupo
  (`_aprender_do_grupo`, 1 consulta por grupo a cada 10 min), autor
  guardado no banco (`nome_do_remetente`) e nome verificado de empresa.

## 2026.10.16.0

Edições, mensagens apagadas e reações do WhatsApp deixam de ser descartadas.

- Eram `protocolMessage` e `reactionMessage`, tratadas como "só controle".
  `_tratar_alteracao` (antes de `converter`) aplica a mudança à mensagem já
  guardada e publica `MensagemAtualizada` (`reacao`, `editada`, `apagada`).
- Reação: uma por pessoa (trocar de emoji substitui; texto vazio tira).
  Guardada em `extras.reacoes` com o jid de quem reagiu. A linha da mensagem
  ganha "reações: 👍 de Ana" (até 3; com mais, a contagem); os detalhes
  listam todas. Reação a mensagem minha é falada (opção `falar_reacoes`).
- Edição: troca o texto e marca `extras.editada`; a linha ganha "(editada)".
- Apagar para todos: limpa o texto e os links, marca `extras.apagada` e a
  mensagem passa a ser lida como "mensagem apagada". A mídia já baixada
  continua no armazém.
- `modelos.atualizar_extras` muda só as chaves dadas, sem perder links nem
  botões. Mensagem que não está guardada (anterior ao TeleZapp) é ignorada.
- Áudio e mensagem de voz: ao começar a tocar, o leitor de tela fala o que é
  e de quem ("Tocando mensagem de voz de Ana, 12 segundos", mais "a 1,5x"
  fora da velocidade normal), no tocar sem janela e no player em janela
  (`modelos.anuncio_reproducao`). Na sequência de áudios, "Próximo áudio" e
  o anúncio saem numa fala só: antes eram duas e a segunda cortava a
  primeira (cada fala interrompe a anterior), então não se ouvia de quem era.
- O anúncio de quem é o áudio que toca é opcional: opção
  `falar_quem_toca` (padrão ligada), no menu Exibição e em Configurações,
  Avisos. Desligada, fala só "Tocando" (e a velocidade, se não for a normal).
  `falar_reacoes` também entrou no menu Exibição, junto das outras.
- Voz e áudio recebidos já tocados: a linha da mensagem diz "ouvida" ao
  andar pela lista ("mensagem de voz, 12 segundos, ouvida"). Marcado
  (`extras.ouvida`, `Janela._marcar_ouvida`) quando começa a tocar no
  TeleZapp, com ou sem janela, e guardado no banco. Também chega de fora: no
  WhatsApp, o recibo `PLAYED_SELF` (toquei no celular) vira
  `MensagemAtualizada(motivo="ouvida")`; no Telegram, `media_unread` falso ao
  receber. Não entra em citações nem em mensagens minhas; mensagens antigas
  sem informação não dizem "não ouvida".
- Áudios em sequência ganhou um terceiro modo, `bloco`: toca os áudios
  seguidos e para na primeira mensagem que não for áudio (3 áudios, um
  texto, 2 áudios: toca os 3 e para). `sim` continua tocando todos da
  conversa, pulando o que não é áudio, e é o padrão; `nao` toca um só.
- Ainda de fora: votos de enquete (cifrados com a chave da enquete) e o
  histórico de edições (só o texto mais novo fica).
- Telegram não foi mexido: o Telethon entrega reações e edições por outros
  eventos, que ainda não são tratados.
- Não verificado com um WhatsApp real: os eventos foram montados a partir
  das definições do neonize.

## 2026.10.15.6

Mensagens de grupo que o TeleZapp não mostrava.

- Causa: quando alguém fala num grupo depois de trocar a chave de envio (o
  que acontece a cada tanto tempo, ao entrar gente ou trocar de aparelho), o
  pacote traz duas partes cifradas, a chave (`pkmsg` ou `msg`) e o conteúdo
  (`skmsg`), e o whatsmeow entrega **dois eventos com o mesmo ID**: primeiro
  só a chave, depois o texto. `_ao_receber` marcava o ID como visto antes de
  saber se havia conteúdo, e descartava o segundo evento, o do texto.
- Nos logs de 14/10: das 292 mensagens que chegaram, os pacotes com uma só
  parte (`skmsg`) foram todos guardados (285 de 285) e os de duas partes
  nenhum (0 de 27). No grupo WinZapp havia 92 respostas a mensagens que o
  TeleZapp nunca guardou.
- Agora o ID só entra em `_vistas` depois que `converter` devolve uma
  mensagem. O evento repetido com conteúdo continua sendo ignorado.
- Mensagens perdidas antes desta versão não voltam sozinhas (o WhatsApp não
  as reenvia). Reações, votos e edições continuam sem aparecer.

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

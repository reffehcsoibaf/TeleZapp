# Registro técnico de mudanças

Para o usuário, veja `telezapp/ajuda/novidades.html`. Versões no formato
`ano.mês.dia.dígito`. Mais novas primeiro.

## Próxima versão (ainda sem número: segue o dia do lançamento)

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

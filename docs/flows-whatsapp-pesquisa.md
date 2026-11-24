# Formulários do WhatsApp (Flows): o que já sabemos

Pesquisa de 24/11/2026, feita no WhatsApp Web da conta de teste (sem preencher nenhum formulário e sem ler conteúdo de conversas). Objetivo: o botão de formulário de mensagens de empresa funcionar no TeleZapp como no WhatsApp e no WhatsApp Web.

## O caso

Mensagem de empresa (`interactiveMessage` com `nativeFlowMessage`) com um botão de ação `galaxy_message`. Parâmetros do botão (`buttonParamsJSON`), só as chaves: `flow_token`, `flow_id`, `flow_cta` (o rótulo do botão), entre outras. Vistos: "Iniciar atendimento" (Sicoob Judiciário, pede CPF ou CNPJ na primeira tela) e "CLIQUE AQUI" (Grupo Guanabara, "Pesquisar - Origem", duas etapas com campo de cidade).

Estado no TeleZapp (branch `log-acoes-interativas`): o botão aparece como ação `formulario` com o rótulo de `flow_cta`, e ativar fala que o formulário só abre no celular.

## Como o WhatsApp Web abre o formulário

1. A tela do formulário **não é do WhatsApp Web**: é uma página da Meta, `https://flows.whatsapp.net/flows-v2/wa-web/`, carregada num quadro (iframe `flows-iframe`) dentro de um painel lateral. As origens aceitas pela ponte terminam em `whatsapp.net`.
2. O WhatsApp Web só faz a ponte. A página do formulário manda `postMessage` com `{eventName, payload, callbackID}` e o WhatsApp Web responde com o mesmo `callbackID`. Eventos vistos, na ordem:
   - `WAExtensionsClose`
   - `flows-iframe-loaded` (a página avisa que carregou)
   - `WAExtensionsGetFlowData` (pede os dados do formulário; o WhatsApp Web os busca)
   - `WAExtensionsGetClientAbProps` (configurações do cliente, objeto com ~14 chaves; as chaves são números)
   - `WAExtensionsConfigureNavBar` (`title`, `is_first_screen`, `is_hidden`)
   - `WAExtensionsDataChannelExchange` (`data`, `screen`): troca de dados com a empresa
   - `WAMLogger`, `WAQPLLogger.annotate` e `WAQPLLogger.end` (telemetria; podem ser ignorados)
   - `WAExtensionsNavigate` (`extension_s...`, truncado)
3. Os dados do formulário vêm de uma consulta GraphQL do WhatsApp, `xwa_extensions_get_flow_data` (operação `WAWebGalaxyFlowsDrawerGetFlowDataQuery`, id `40083220921276114`, variável `request`). O whatsmeow já faz consultas desse tipo (MEX): foi o que usamos para buscar canais.
4. Módulos do WhatsApp Web relacionados (nomes): `WAWebGalaxyFlowBridgeApi` (a ponte), `WAWebGalaxyFlowsDrawerUtils` (URL, id do iframe, `getFlowInitDataPayload`, `getPublicKeyFromFetchedData`), `WAWebGalaxyFlowsUtils` (`fetchFlowJSON`, `isFlowInitWithoutDataChannel`...), `WAWebGalaxyFlowsSessionsCache`, `WAWebGalaxyFlowsIdentityFetcher`, `WAWebGalaxyFlowsUnifiedEncryptionVerifier`, `WAWebGalaxyFlowMessageInteractiveResponseMessageParser`. A existência de `isFlowInitWithoutDataChannel` indica que há formulários sem troca de dados com a empresa (estáticos) e outros com.

## O que o protocolo (protobuf) já tem

- `PeerDataOperationRequestMessage.galaxyFlowAction` (`type`: `NOTIFY_LAUNCH` ou `DOWNLOAD_RESPONSES`, `flowID`, `stanzaID`...) e `flowResponsesCsvBundle` na resposta: isso é do lado de **quem é dono do formulário** (baixar as respostas), não da troca de dados de quem preenche. Hipótese anterior de que o canal de dados passava pelo celular: **não confirmada**.
- `InteractiveResponseMessage.nativeFlowResponseMessage` (`name`, `paramsJSON`, `version`): é a resposta final, que o celular manda à empresa ao concluir (já usada para `quick_reply`).
- O whatsmeow não tem nada de Flow além desses tipos.

## O que falta descobrir

1. Como é montada a variável `request` da consulta `xwa_extensions_get_flow_data` (qual campo leva o `flow_id`, o `flow_token`, a versão).
2. Como o WhatsApp Web faz o `WAExtensionsDataChannelExchange`: para onde vai e como é criptografado (há chave pública do formulário e `UnifiedEncryptionVerifier`).
3. O formato exato do que a ponte devolve em cada evento (`GetFlowData`, `GetClientAbProps`, `ConfigureNavBar`) e o que o formulário envia ao concluir (`WAExtensionsNavigate`/conclusão) até virar `nativeFlowResponseMessage`.
4. Se a página `flows.whatsapp.net` carrega fora de um quadro do WhatsApp Web: ela pode conferir a origem de quem a hospeda (`window.parent`).

## Plano

1. **Prova de conceito:** abrir a primeira tela do formulário numa janela do TeleZapp (navegador embutido, como na janela dos robôs do Telegram) com uma ponte mínima, só para ver se a página carrega e quais respostas ela pede.
2. **DLL:** consulta `xwa_extensions_get_flow_data` e, se for o caso, o canal de dados.
3. **Concluir:** receber o resultado do formulário e mandar o `nativeFlowResponseMessage` à empresa, como o celular.
4. Caixa em Recursos experimentais, desligada por padrão. Se a Meta mudar o protocolo, o recurso pode quebrar sem aviso.

## Cuidados

- Nada disso foi testado com formulário preenchido: os formulários pedem dados pessoais (CPF/CNPJ), e a pesquisa parou na primeira tela.
- Registrar nas respostas só nomes e formatos; nunca guardar valores de formulários.

## Atualização (24/11, noite): o que a implementação descobriu

- O quadro do WhatsApp Web não tem parâmetros: `https://flows.whatsapp.net/flows-v2/wa-web/`. A página recusa ser exibida em quadro de outro domínio (ícone de página quebrada), mas abre como página principal.
- Os dados do formulário não vêm de uma só fonte: o JSON é `GET https://web.whatsapp.com/flows/json/<flow_id>` (público, sem cookie); a chave pública do endpoint vem da consulta MEX `xwa_extensions_get_flow_data` (id `40083220921276114`, variável `{request: {extensions: {biz_jid, flow_id}}}`, resposta `extensions_flow_data[0].extensions.metadata.endpoint_public_key.key`); o resto está nos parâmetros do botão (`flow_token`, `flow_id`, `flow_cta`, `flow_action`, `flow_action_payload`, `flow_metadata` com `www_proxy_secret` e `flow_token_signature`, `mode`).
- `responseData` de `WAExtensionsGetFlowData`, valores que o WhatsApp Web usa: `response_viewer` "CONSUMER", `biz_platform` 4, `entry_point_conversation_initiated` -1, `flow_entry_point` 0, `extension_status` "PUBLISHED", `is_template` false, `is_flow_interactive` true, `biz_logo` uma URL de imagem, `flow_action_payload` **em base64**.
- Eventos da ponte (`WAFlowsWebBridgeEventNames`): `WAExtensionsGetFlowData`, `WAExtensionsComplete`, `WAExtensionsGetClientAbProps`, `WAExtensionsNavigate`, `WAExtensionsClose`, `WAFlowsExternalNavigation`, `WAFlowsOpenURL`, `WAExtensionsConfigureNavBar`, `WAExtensionsVibrate`, `WAExtensionsSetDraggable`, `WAFlowsShowOverlay`, `WAFlowsShowNativeInputDialogComponent`, `WAQPLLogger.*`, `WAMLogger`, `WAExtensionsSpamReport`, `WAExtensionsReportItem`, `WAExtensionsLearnMore`...
- O pedido de dados repete 3 vezes e depois vem `GetClientAbProps`; `DataChannelExchange` com `data: {}` na primeira tela foi respondido com nulo no WhatsApp Web (formulário estático).
- O formato do que `WAExtensionsComplete` entrega e como vira a resposta à empresa ainda não foi visto: exigiria concluir um formulário (dados pessoais). O TeleZapp registra o formato (sem valores) na primeira vez.

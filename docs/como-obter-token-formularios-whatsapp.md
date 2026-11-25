# Como obter o token para formulários de empresa (Flows)

Alguns formulários de empresa no WhatsApp (botão "Iniciar atendimento",
"CLIQUE AQUI" etc.) trocam dados com a empresa a cada tela. Para isso, o
WhatsApp exige o "token do aplicativo" do WhatsApp Web, que o TeleZapp não
traz embutido (veja `docs/flows-whatsapp-pesquisa.md`). Quem quiser usar
esses formulários precisa pegar o próprio token, na própria sessão já
logada, e colar na opção "Token do aplicativo para formulários que
consultam a empresa" (Configurações, Experimental).

Sem esse token, o TeleZapp continua funcionando: os formulários que não
trocam dados com a empresa abrem normalmente, e os que trocam avisam que
precisam ser preenchidos no celular, em vez de dar erro.

## Passo a passo

1. Abra `web.whatsapp.com` no Chrome, já logado com o WhatsApp da conta que
   você usa no TeleZapp.
2. Abra o Console do navegador: `Ctrl+Shift+J`. Isso já abre direto na aba
   Console (não precisa achar a aba Network, que é mais difícil de ler
   pelo leitor de tela).
3. Clique no campo de texto do Console (o cursor do NVDA deve anunciar algo
   como "editar"). Abra o arquivo `ferramentas/extrair-token-flows-whatsapp.js`
   deste repositório, copie o conteúdo inteiro e cole no campo.
4. Na primeira vez, o Chrome pode bloquear a colagem e pedir para digitar
   uma palavra (algo como "permitir colagem") antes de deixar colar de
   novo. Siga o que ele pedir e cole outra vez.
5. Aperte Enter. Vai aparecer um aviso (alert, que o NVDA lê na hora)
   dizendo que o script está ativo.
6. Abra a conversa com uma empresa que manda formulário (por exemplo, uma
   das que já mandaram para você) e clique no botão do formulário dela.
   Não precisa preencher nada: o pedido do token acontece ao abrir a
   primeira tela.
7. Se aquele formulário for do tipo que troca dados com a empresa, aparece
   outro aviso: "Token copiado!". O token já está na área de transferência
   nesse momento.
8. Cole (Ctrl+V) na opção "Token do aplicativo para formulários que
   consultam a empresa", em Configurações, Experimental, do TeleZapp, e
   salve.

Se nenhum aviso de "Token copiado" aparecer depois de clicar no botão,
pode ser que aquele formulário específico não troque dados com a empresa
(não precisa do token) ou que o WhatsApp Web não tenha pedido o token
daquela vez; tente outro formulário ou feche e abra a conversa de novo.

## Cuidados

- O script só observa pedidos que o próprio WhatsApp Web já faz; não manda
  nada a mais, não lê o conteúdo de conversas nem preenche formulários.
- O token fica só no seu computador, gravado nas configurações do
  TeleZapp, como qualquer outra opção.
- Não cole esse token em nenhum outro lugar, nem o compartilhe: ele dá
  acesso ao WhatsApp Web da sua conta.

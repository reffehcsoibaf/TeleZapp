# Segurança

## O que nunca vai para o repositório

- **Sessões** (`sessao-whatsapp/`, `sessao-telegram/`, arquivos `*.session`,
  `*.db`): quem tiver esses arquivos usa a conta sem senha.
- **Credenciais**: `api_id` e `api_hash` do Telegram, telefone, códigos de login,
  senha de duas etapas (`configuracao-*.txt`, `codigo-*.txt`, `senha-*.txt`).
- **Tokens do GitHub** e qualquer chave. Nunca em arquivos, em commits, em
  mensagens de commit nem em issues e pull requests.
- **Logs** (`logs/`): não devem ter dados pessoais, mas ficam fora por padrão.

O `.gitignore` já cobre esses casos. Antes de cada commit, vale rodar
`git status` e conferir o que será enviado.

## Se algo vazar

| O quê | O que fazer |
|---|---|
| Sessão do WhatsApp | No celular: WhatsApp, Dispositivos conectados, remover o aparelho |
| Sessão do Telegram | No app: Configurações, Dispositivos, encerrar a sessão |
| `api_hash` do Telegram | Criar nova aplicação em my.telegram.org |
| Token do GitHub | Configurações do GitHub, Developer settings, revogar o token |

## Risco de bloqueio de contas

Clientes não oficiais de WhatsApp e Telegram podem levar a restrições ou
bloqueio da conta. Use contas de teste nos experimentos e leia os termos de uso
dos serviços antes de distribuir o aplicativo.

## Tokens de acesso ao repositório

Prefira tokens **granulares**, restritos a este repositório, com as permissões
mínimas (conteúdo e pull requests), validade curta e revogação ao fim do uso.

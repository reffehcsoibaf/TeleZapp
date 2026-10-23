# Relatos pelo formulário da página

`site/relatar.html` envia o relato (nome, contato, descrição, quando
aconteceu, versão e os logs) para um Cloudflare Worker, `worker.js`, que o
guarda no KV por 90 dias. Quem lê é só o responsável, em `/admin`.

## Publicar (uma vez)

Precisa do Node e de uma conta Cloudflare (o plano grátis serve; o KV não
exige cartão, ao contrário do R2).

```bash
cd relatos
npx wrangler login
npx wrangler kv namespace create RELATOS
```

1. Copie o `id` que o último comando mostrar para `wrangler.toml`
   (`id = "..."`).
2. Troque `SEU-USUARIO` em `wrangler.toml` e em `site/relatar.html` (a
   constante `ENDERECO`) pelo subdomínio `workers.dev` da sua conta (o
   `wrangler deploy` mostra o endereço completo).
3. Crie os segredos:

```bash
npx wrangler secret put ADMIN_TOKEN     # senha para abrir /admin (longa e aleatória)
npx wrangler secret put SAL             # texto aleatório, usado no limite por pessoa
# opcional, aviso no Telegram a cada relato novo:
npx wrangler secret put TG_TOKEN        # token do bot
npx wrangler secret put TG_CHAT         # seu chat id
```

4. Publique: `npx wrangler deploy`.
5. Ler os relatos: `https://<endereço do Worker>/admin?t=<ADMIN_TOKEN>`.

## O que ele faz e não faz

- Só aceita envios vindos de `https://reffehcsoibaf.github.io` e, no máximo,
  8 relatos por dia por endereço de rede (guardado só como um resumo
  irreversível).
- Logs: até 5 MB no total, só com a autorização marcada. Apagados do KV
  depois de 90 dias (`DIAS_GUARDADO`).
- Não há proteção forte contra robôs (só um campo-isca e o limite diário). Se
  chegar lixo, acrescente o Turnstile da Cloudflare.
- O token do `/admin` vai no endereço (`?t=`): não o compartilhe.

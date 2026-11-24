# TeleZapp para Mac: como testar

Esta é uma versão de teste do TeleZapp para Mac. Ela ainda não é assinada pela Apple, então o Mac pede uma confirmação na primeira vez. O objetivo do teste é descobrir o que não funciona no Mac, principalmente com o VoiceOver. Qualquer detalhe ajuda, até o que parecer pequeno.

## 1. Qual arquivo baixar

Abra o menu Apple, escolha "Sobre este Mac" e veja o item "Chip" ou "Processador".

- Se aparecer "Apple M1", "M2", "M3", "M4" ou parecido: baixe `TeleZapp-mac-apple-silicon.zip`.
- Se aparecer "Intel": baixe `TeleZapp-mac-intel.zip`.

O Mac precisa estar com o macOS 11 (Big Sur) ou mais novo.

## 2. Instalar e abrir

1. Dê dois cliques no arquivo .zip. Aparece o `TeleZapp.app`.
2. Arraste o `TeleZapp.app` para a pasta Aplicativos.
3. Na primeira vez, não dê dois cliques. Vá até o TeleZapp na pasta Aplicativos, abra o menu de ações (botão direito; com o VoiceOver, Control+Option+Shift+M) e escolha "Abrir". Na pergunta que aparecer, escolha "Abrir" de novo.
4. Se o Mac disser que o app está danificado ou não deixar abrir, abra o Terminal e rode este comando, depois tente de novo:

```
xattr -dr com.apple.quarantine /Applications/TeleZapp.app
```

Outra saída: Ajustes do Sistema, Privacidade e Segurança, e o botão "Abrir mesmo assim" perto do aviso sobre o TeleZapp.

Depois da primeira vez, abre normalmente.

## 3. Permissões

O Mac vai perguntar sobre microfone, câmera, notificações e rede local. Permita o que for usar. Sem o microfone não dá para gravar voz nem fazer chamadas.

## 4. VoiceOver

O TeleZapp fala pelo VoiceOver quando ele está ligado (Command+F5 liga e desliga). Com o VoiceOver desligado o TeleZapp não fala nada.

- O menu do TeleZapp fica na barra de menus do Mac (a de cima da tela). Com o VoiceOver, Control+Option+M vai até ela.
- No Windows o TeleZapp usa Alt e Ctrl nos atalhos. No Mac, o "Ctrl" dos atalhos vira Command. Os atalhos com Alt (Option no Mac) podem conflitar com o VoiceOver ou escrever símbolos. Anote quais não funcionaram. Dá para trocar qualquer atalho em Configurações, Atalhos, ou apertando Shift+F1.

## 5. O que ainda não existe no Mac

Estas partes são do Windows e nesta versão não funcionam ou não aparecem:

- Compartilhar o som do computador numa chamada.
- Entrar com Touch ID (a proteção ao entrar usa só o PIN do TeleZapp).
- Atualizar o programa sozinho (avise-me quando sair versão nova).
- Continuar em segundo plano e o ícone da bandeja podem se comportar de outro jeito (o Mac usa o Dock e a barra de menus). Conte o que acontecer.

## 6. O que testar

Marque o que funcionou e o que não funcionou:

1. O TeleZapp abre e o VoiceOver lê a janela principal.
2. Adicionar uma conta do Telegram (código) e uma do WhatsApp (QR ou código de pareamento).
3. A lista de conversas: setas, Enter para abrir, o VoiceOver lendo cada item.
4. Ler mensagens, responder, enviar texto.
5. Enviar uma foto e um arquivo. Receber e abrir.
6. Gravar uma mensagem de voz (veja o atalho no menu Mídias). Ouvir antes de enviar.
7. Tocar uma mensagem de voz recebida.
8. Sons de aviso (mensagem nova, enviada, erro) e se a fala não fica por cima do som.
9. Uma chamada de voz (ligar e receber), se der.
10. Configurações: abrir, mudar uma opção, fechar.
11. Proteção ao entrar com PIN (Configurações, Privacidade).
12. Corretor ortográfico ao escrever uma mensagem.
13. Abrir um link do Telegram (tg://) ou do WhatsApp clicado em outro app.
14. Fechar e abrir de novo: as contas continuam conectadas.

## 7. Como mandar o retorno

Conte o que fez, o que esperava e o que aconteceu. Se der erro, mande os logs:

- No TeleZapp: menu Ajuda, "Abrir a pasta de logs". Mande o arquivo `telezapp.log` e o `falha-nativa.log`.
- Ou pelo Finder: menu Ir, "Ir para a pasta", e digite `~/Library/Application Support/TeleZapp/logs`.
- Se o programa nem abrir, o Mac costuma guardar um relatório em Console, Relatórios de Falhas; mande o do TeleZapp.

Nos logs o número de telefone aparece cortado. Mesmo assim, olhe o arquivo antes de mandar, se preferir.

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
| 5 | Mídia sem FFmpeg | Proposta | Montar vídeo e nota de voz no próprio app (duração lida do arquivo) | O FFmpeg só serve ao neonize para ler duração e fazer miniatura |
| 6 | Nota de voz | Proposta | **Ogg/Opus**, com qualidade ajustável | Exigência dos dois serviços para aparecer como mensagem de voz |
| 7 | Fala | Proposta | DLL do controlador do NVDA, carregada por `ctypes` | Fala direta funcionou (código 0) |
| 8 | Empacotamento | Proposta | **PyInstaller `--onedir`** | 95 MB; todos os componentes carregam |
| 9 | Provedores | Proposta | Uma interface comum (conectar, listar, ler, enviar, baixar, eventos), uma implementação por serviço, cada uma em sua thread | Telethon usa `asyncio`; o neonize bloqueia ao conectar |
| 10 | Histórico | Proposta | Banco local (SQLite) | O WhatsApp só entrega mensagens como eventos |
| 11 | Licença | Adotada | **GPL-3.0-or-later** | Escolha do responsável: versões derivadas devem continuar abertas. As dependências em uso são compatíveis, exceto o `hachoir` (ver pendência 1 e `docs/licencas-de-terceiros.md`) |

## Interface e acessibilidade

- Nenhum fluxo pode depender de ler o terminal ou de ver a tela.
- Tratar Enter e Esc na janela (`EVT_CHAR_HOOK`); o `ListBox` não entrega o Enter.
- Ao abrir uma conversa: foco no item "Início das mensagens não lidas" ou, se
  não houver, na última mensagem. Esc volta para a lista de conversas.
- Enter na caixa de digitação envia; Shift+Enter quebra a linha.
- Três estilos de leitura da mensagem (autor primeiro, conteúdo primeiro, autor
  só quando muda), escolhidos num menu.
- Avisos de mensagem nova: fala pelo NVDA mais som, ambos desligáveis.

## Riscos e pendências

1. **`hachoir` e a GPL-3.0.** A licença do projeto é a GPL-3.0-or-later
   (adotada). O `hachoir` (leitura da duração de vídeo) declara **GPL-2.0**
   nos metadados do pacote; se for "somente 2.0", ele **não pode** ser
   combinado com código GPL-3.0. Proposta: substituí-lo por uma leitura
   própria da duração do MP4 antes de qualquer distribuição. Também falta
   conferir a licença da DLL do controlador do NVDA e das dependências Go
   embutidas na DLL do neonize (veja `docs/licencas-de-terceiros.md`).
2. **Bloqueio de contas**: nenhum dos dois serviços oferece API oficial para
   contas pessoais. O risco existe e não foi medido. A troca de conta dentro do
   mesmo app mitiga o efeito, não a causa.
3. **Dependência de terceiros**: o neonize é mantido por terceiros e acompanha a
   whatsmeow; mudanças do WhatsApp podem quebrá-lo.
4. **Distribuição**: executáveis sem assinatura costumam gerar alerta do
   SmartScreen e de antivírus em outros computadores (não testado aqui).
5. **Notas de voz gravadas no app**: falta o resultado do teste de microfone e
   a escolha da qualidade padrão.
6. **Vídeo sem miniatura** e arquivos acima de 20 MB: ainda não avaliados.
7. **Chamadas**: fora do escopo. O neonize só avisa e recusa; uma biblioteca
   separada (meowcaller) existe, mas é jovem e não está exposta ao Python.

## Próximos passos sugeridos

1. Resultado do teste de gravação de voz e escolha da qualidade padrão.
2. Esqueleto do aplicativo: camada de provedores, banco local, interface.
3. Substituir o `hachoir`, adicionar o aviso de licença nos arquivos e conferir as licenças pendentes.
4. Instalador, atualização (trocar só o que mudou) e assinatura.
5. Testes de estabilidade e de arquivos maiores.

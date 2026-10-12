# Resultados dos experimentos

Ambiente: Windows 11 (build 10.0.26300), Python 3.13.15, NVDA em execução,
outubro de 2026. Um único computador; cada medida vem de **uma execução**, salvo
quando há faixa. Os testes de WhatsApp e Telegram usaram contas pessoais de teste.

## 1. Projeto anterior (WPPConnect em Node.js)

Medido para entender por que a instalação era lenta.

| Cenário | Tempo | Pacotes |
|---|---|---|
| `npm install` da biblioteca, sem baixar o Chromium, cache vazio | 42 s | 250 |
| idem, **com** download do Chromium, cache cheio | 32 s | 250 |
| idem, sem Chromium, cache cheio | 14 s | 250 |
| Clone do repositório + `npm install` (inclui compilação) | 93 s | 944 |

Leitura do código do WinZapp: o servidor é o `wppconnect-server`, clonado numa
versão fixa; os patches são aplicados **dentro do `node_modules`** depois do
`npm install`; a instalação completa apaga o `node_modules` e a pasta do Chrome e
refaz tudo. O Chromium pesa menos do que o resto.

## 2. WhatsApp com neonize 0.5.2 (sem navegador)

| Item | Resultado |
|---|---|
| Instalação (`pip`, 21 pacotes, com cache) | 18 a 30 s; pacote do neonize: 21,6 MB |
| Importação | 0,5 a 1,4 s |
| Pareamento | Por **código numérico** (sem QR); sessão salva reconecta em 1,1 a 1,2 s |
| Envio (arquivos pequenos) | texto 0,15 a 0,18 s; foto 0,9 a 1,05 s; vídeo 0,74 a 1,78 s; nota de voz 0,42 a 0,59 s; documento 0,39 a 0,58 s |
| Download | 0,01 a 0,40 s, sempre com o tamanho exato |
| FFmpeg | **Não é necessário**: vídeo e nota de voz são montados pelo próprio teste (duração lida do cabeçalho); o vídeo sai sem miniatura |

Observações: mensagens enviadas pelo próprio programa não voltam como evento;
ao conectar chegam eventos de protocolo (sem texto) e mensagens pendentes; é
preciso abrir "envelopes" (mensagem de outro dispositivo, efêmera) antes de ler
o texto. Vídeo tocou e nota de voz apareceu como **mensagem de voz** no celular.

## 3. Telegram com Telethon 1.45.0

| Item | Resultado |
|---|---|
| Instalação | 5 a 10 s (pacote leve, só Python) |
| Conexão | 0,8 a 2,5 s; sessão salva reaproveitada |
| Login | Código e senha de duas etapas por arquivo no Bloco de Notas |
| Envio | texto 0,15 s; foto 0,5 a 0,6 s; vídeo 0,63 a 0,71 s; nota de voz 0,38 a 0,42 s; documento 0,30 a 0,37 s |
| Recebimento | Texto de grupo, foto, vídeo, voz e documento, com download correto |
| Mensagens enviadas pelo programa | Não voltam como evento |

## 4. Interface (wxPython 4.3.1 sobre wxWidgets 3.3.3)

- Instalação: 6,7 a 9,4 s (pacote de 18,5 MB).
- **Fala direta pelo NVDA** funciona (DLL do controlador do NVDA, carregada por
  `ctypes`; código de retorno 0).
- Rótulos por `wx.StaticText` antes do controle são lidos ("Conversas lista",
  "Digite sua mensagem multilinha").
- **O Enter não chega ao tratador de teclas de um `wx.ListBox`** dentro de um
  painel no Windows; a solução foi tratar Enter e Esc na janela
  (`EVT_CHAR_HOOK`) antes dos controles.
- Mensagens longas são lidas inteiras na lista; Alt+Enter abre o texto completo.
- Menus mostram os atalhos; Shift+F10 abre o menu da mensagem.

## 5. Empacotamento (PyInstaller 6.22.3, `--onedir`)

| Item | Resultado |
|---|---|
| Geração | 66 s |
| Tamanho | **95,0 MB em 285 arquivos** (sem compactar) |
| Maiores | DLL do neonize 16,7 MB; executável 15,4 MB; wxPython ~19 MB; módulo AVIF do Pillow 7,5 MB (dispensável) |
| Autoteste do executável | 3,1 s na 1ª execução, 1,7 s na 2ª (abre janela e carrega tudo) |
| Componentes | wxPython, neonize e DLL em Go, protobuf, libmagic, Pillow, Telethon, hachoir e fala NVDA: **todos funcionaram** |
| Antivírus | Executável gerado localmente não foi bloqueado. **Não testado** em outros computadores |

## 6. Arquivos grandes (20 MB de dados aleatórios, integridade SHA-256 confirmada em todos)

Criptografia isolada do Telethon (2 MB, sem rede): Python puro 0,37 MB/s (cifrar)
e 0,41 MB/s (decifrar); com `cryptg` 431 e 576 MB/s.

| Cenário | Envio | Download |
|---|---|---|
| Telegram, sem `cryptg` | 0,21 MB/s | 0,21 MB/s |
| Telegram, com `cryptg`, padrão (partes de 128 KB, uma por vez) | 0,66 a 0,70 MB/s | 0,56 a 0,59 MB/s |
| Telegram, partes de 512 KB, uma por vez | 2,32 MB/s | 2,07 MB/s |
| Telegram, partes de 512 KB, 4 em paralelo | 7,85 MB/s | 8,41 MB/s |
| Telegram, partes de 512 KB, 8 em paralelo | 10,95 MB/s | 10,44 MB/s |
| WhatsApp (neonize) | 7,32 MB/s | 18,31 MB/s |

Causa da lentidão do Telethon: partes pequenas enviadas **uma de cada vez**,
limitadas pela latência de ~190 a 220 ms por requisição (lido no código-fonte do
Telethon e confirmado pelas medidas).

## 7. Gravação de voz

Teste preparado (`experimentos/8-teste-gravacao-voz.bat`); **resultados pendentes**.
Medido só em ambiente Linux: o `soundfile` grava Ogg/Opus mono de 48 kHz e o
nível de compressão controla o tamanho (padrão ~62 kbit/s, 0,5 ~134 kbit/s,
0,0 ~260 kbit/s; mesmo sinal em FLAC: 526 kbit/s).

## Não testado

Estabilidade por horas, grupos grandes, histórico, miniaturas de vídeo,
arquivos acima de 20 MB, várias transferências simultâneas, instalador e
atualização, alerta do SmartScreen em outros computadores, e o comportamento do
bloqueio de contas por clientes não oficiais.

# Experimentos de viabilidade

Cada arquivo `.bat` roda **um teste completo**: cria um ambiente virtual próprio
(`venv-*`), instala o que precisa, executa e grava um log em `logs/`. No fim,
abre a pasta do log e mostra uma caixa de mensagem. Requisitos: Windows,
Python 3.13 (o comando `py -3.13` ou `python`) e, para a fala, o NVDA aberto.

**Nenhum teste exige ler ou digitar no terminal.** Avisos saem em caixas de
mensagem do Windows (que o leitor de tela lê), dados pedidos ao usuário são
digitados num arquivo aberto no Bloco de Notas, e o progresso é marcado por
bipes e pelo log.

Todos os arquivos desta pasta devem ficar **juntos, na mesma pasta**: os `.bat`
procuram os `.py` ao lado deles.

## Testes

| Teste | Scripts | O que mede | Conta necessária |
|---|---|---|---|
| `1-teste-telegram.bat` | `telegram_teste.py` | Login, conversas, envio e recebimento de texto, foto, vídeo, nota de voz e documento | Telegram |
| `2-teste-whatsapp.bat` | `whatsapp_teste.py` | Pareamento por código, sessão salva, mensagens e mídias, vídeo e nota de voz sem FFmpeg | WhatsApp |
| `3-teste-interface.bat` | `prototipo_interface.py`, `modelo_conversas.py`, `fala.py` | Protótipo da interface com dados de exemplo, lido pelo NVDA | nenhuma |
| `4-teste-empacotamento.bat` | `app_empacotamento.py`, `medir_pasta.py` | Gera o executável com PyInstaller e roda um autoteste | nenhuma |
| `5-teste-arquivos-grandes-telegram.bat` | `telegram_grande.py` | Envio e download de arquivo grande, com e sem `cryptg` | Telegram |
| `6-teste-arquivos-grandes-whatsapp.bat` | `whatsapp_grande.py` | Envio e download de arquivo grande | WhatsApp |
| `7-teste-telegram-velocidade.bat` | `telegram_velocidade.py` | Quatro jeitos de transferir: partes de 128 e 512 KB, em série e em paralelo | Telegram |
| `8-teste-gravacao-voz.bat` | `gravacao_voz.py`, `opus_util.py` | Gravação pelo microfone, cinco níveis de compressão Opus, reprodução e envio ao Telegram | Telegram (opcional) |

Em `historico/` ficam dois testes do projeto anterior (WPPConnect com Node), que
medem o tempo de instalação e foram a origem desta investigação.

## Módulos compartilhados

- `acessivel.py`: caixas de mensagem do Windows, pergunta Sim/Não, bipes e
  entrada de dados por arquivo no Bloco de Notas.
- `fala.py`: fala direta pelo NVDA (carrega a DLL do controlador do NVDA).
- `amostras.py`: foto, vídeo, nota de voz e PDF de exemplo, embutidos em base64.
- `arquivos_grandes.py`: geração de arquivos de teste, hash e velocidade.
- `telegram_login.py`: login do Telegram sem terminal.
- `opus_util.py`: duração de arquivos Ogg/Opus e reamostragem simples.

## Arquivos que os testes criam (não vão para o Git)

`venv-*`, `logs/`, `sessao-telegram/`, `sessao-whatsapp/`,
`configuracao-*.txt`, `codigo-*.txt`, `senha-*.txt`, `empacotado/`,
`build-pyinstaller/`, `gravacoes-teste/`, `arquivos-grandes/`, entre outros.
As pastas `sessao-*` e os arquivos de configuração dão acesso às contas: apague
tudo isso quando terminar os testes e remova o aparelho conectado no WhatsApp e
a sessão no Telegram. Veja [`../docs/seguranca.md`](../docs/seguranca.md).

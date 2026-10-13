# Licenças de terceiros

Levantamento feito em outubro de 2026 nos **metadados dos pacotes** e nos
cabeçalhos dos arquivos. Não é parecer jurídico. O TeleZapp usa a
**GPL-3.0-or-later** (arquivo `LICENSE`).

## Bibliotecas usadas nos experimentos

| Biblioteca | Para quê | Licença | Combina com a GPL-3.0? |
|---|---|---|---|
| neonize 0.5.2 | WhatsApp (ligação Python) | Apache-2.0 | Sim (Apache-2.0 pode entrar em projeto GPL-3.0) |
| segno 1.6 | Desenho do QR Code do pareamento (já vem com o neonize) | BSD (classificação do pacote) | Sim |
| whatsmeow (embutida na DLL do neonize) | Protocolo do WhatsApp | MPL-2.0 (cabeçalho dos arquivos) | Sim, pela cláusula de "licença secundária" da MPL-2.0, salvo aviso em contrário nos arquivos; os cabeçalhos vistos não trazem esse aviso |
| Telethon 1.45.0 | Telegram | MIT | Sim |
| rsa, pyaes (do Telethon) | Criptografia em Python | Apache-2.0, MIT | Sim |
| cryptg 0.6.0 | AES rápido para o Telethon | CC0 | Sim |
| wxPython 4.3.1 | Interface | wxWindows Library License | Sim (permite distribuir programas sob outras licenças) |
| soundfile 0.14.0 | Gravar e ler Ogg/Opus | BSD-3-Clause | Sim |
| sounddevice 0.5.6 | Microfone e reprodução | MIT | Sim |
| numpy | Áudio | BSD-3-Clause (e outras permissivas) | Sim |
| protobuf | Mensagens do WhatsApp | BSD-3-Clause | Sim |
| accessible-output2 (só a DLL) | Fala pelo NVDA | MIT (pela classificação do pacote; o campo de licença diz UNKNOWN) | Sim, mas a DLL é do NVDA: ver pendências |
| PyInstaller 6.22.3 (ferramenta) | Gera o executável | GPL-2.0-ou-posterior com exceção que permite distribuir programas de qualquer licença | Sim: o executável gerado não herda a GPL do PyInstaller |
| hachoir 3.4.0 | Duração de vídeo (só nos experimentos) | **GPL-2.0** | **Não**: fica fora do aplicativo (ver abaixo) |

## Pendências

1. **hachoir (resolvido por exclusão).** O pacote 3.4.0 declara "GNU GPL v2",
   traz o texto da GPL versão 2 e nenhum arquivo diz "ou qualquer versão
   posterior": é tratado como GPL-2.0 *somente*, incompatível com a GPL-3.0.
   Decisão: o aplicativo **não usa** o hachoir; a duração e o tamanho dos
   vídeos são lidos por código próprio (família MP4). Os experimentos antigos
   continuam a usá-lo, mas não são distribuídos.
2. **DLL de fala do NVDA** (`nvdaControllerClient`, que vem dentro do
   accessible-output2): não conferi a licença do controlador do NVDA. Verificar
   antes de distribuir junto do aplicativo.
3. **Dependências Go dentro da DLL do neonize.** A whatsmeow é MPL-2.0, mas a DLL
   embute outros módulos Go cujas licenças não foram auditadas.
4. **Pillow e python-magic-bin** (usados pelo neonize): não verificados.

## Obrigações ao distribuir um executável

- Incluir o texto da GPL-3.0 e o aviso de copyright do TeleZapp.
- Manter os avisos de licença das bibliotecas de terceiros (incluir um arquivo
  de avisos no pacote).
- Para a whatsmeow (MPL-2.0): deixar acessível o código-fonte dos arquivos MPL
  (apontar o repositório da whatsmeow e a versão usada).
- Para o TeleZapp (GPL-3.0): oferecer o código-fonte correspondente a quem
  receber o executável (este repositório cumpre isso, desde que a versão
  distribuída esteja nele).

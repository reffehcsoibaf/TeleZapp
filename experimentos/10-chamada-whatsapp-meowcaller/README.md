# Fase 0: chamadas do WhatsApp com o meowcaller

Programa em Go (`chamadas-teste.exe`, compilado de `main.go`) usado pelo teste
`..\10-teste-chamada-whatsapp.bat`. Veja o README da pasta de cima para rodar.

Ele testa o [meowcaller](https://github.com/purpshell/meowcaller). A versao
atual do meowcaller nao usa o whatsmeow oficial: recebe o cliente do fork
`github.com/polymorfa/hypermeow` (MPL-2.0), por isso este programa o usa.

Pareia como aparelho conectado (codigo de telefone), atende ou faz uma chamada
de audio e troca a voz com o Python por um socket local (PCM s16le, 16 kHz,
mono): o desenho que uma DLL no TeleZapp teria. Sem `-pcm`, toca um tom de
440 Hz por 3 s. O que chega tambem vai para `chamada-<id>.wav`.

Para recompilar (precisa do Go 1.27): `go build -o chamadas-teste.exe .`

A sessao fica em `sessao-chamadas.db`. Para desfazer: apague o arquivo e remova
o aparelho no celular da conta de teste.

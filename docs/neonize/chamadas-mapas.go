package main

import "sync"

// mapasMu serializa as escritas nos mapas globais do neonize (clients,
// StopSignal e eventChannel). O Python chama Neonize() de uma thread por
// conta; com mais de uma conta do WhatsApp abrindo ao mesmo tempo, duas
// escritas no mesmo mapa derrubam o processo inteiro com
// "fatal error: concurrent map writes" (visto em 27/10/2026, com tres contas).
// O build.ps1 troca as escritas de main.go por escritas entre mapasMu.Lock() e
// mapasMu.Unlock().
var mapasMu sync.Mutex

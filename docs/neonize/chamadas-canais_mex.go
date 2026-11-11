package main

/*
#include <stdlib.h>
*/
import "C"

import (
	"context"
	"encoding/json"
	"time"
)

// Consulta MEX (GraphQL do WhatsApp) generica, para o TeleZapp buscar canais no
// diretorio do WhatsApp: o whatsmeow so tem seguir, ler por convite e listar os
// seguidos. As consultas e os ids vem do WhatsApp Web (lidos por CDP), como na
// ponte neonize do WinZapp (patch 0005, SendMexIQ). O TeleZapp chama pelo ctypes.
//
// Resposta (JSON, texto C a liberar com FreeString):
//   {"ok": true, "dados": <data do GraphQL>}  ou  {"ok": false, "erro": "..."}.
type respostaMex struct {
	Ok    bool            `json:"ok"`
	Dados json.RawMessage `json:"dados,omitempty"`
	Erro  string          `json:"erro,omitempty"`
}

func textoMex(r respostaMex) *C.char {
	b, err := json.Marshal(r)
	if err != nil {
		return C.CString(`{"ok":false,"erro":"resposta invalida"}`)
	}
	return C.CString(string(b))
}

//export NewsletterMex
func NewsletterMex(id *C.char, queryID *C.char, variables *C.char, timeoutMs C.int) *C.char {
	cli := clientFor(C.GoString(id))
	if cli == nil {
		return textoMex(respostaMex{Erro: "client not found"})
	}
	var vars map[string]any
	if err := json.Unmarshal([]byte(C.GoString(variables)), &vars); err != nil {
		return textoMex(respostaMex{Erro: "variaveis invalidas: " + err.Error()})
	}
	espera := time.Duration(int(timeoutMs)) * time.Millisecond
	if espera <= 0 || espera > 2*time.Minute {
		espera = 30 * time.Second
	}
	ctx, cancel := context.WithTimeout(context.Background(), espera)
	defer cancel()
	dados, err := cli.DangerousInternals().SendMexIQ(ctx, C.GoString(queryID), vars)
	if err != nil {
		return textoMex(respostaMex{Erro: err.Error(), Dados: dados})
	}
	return textoMex(respostaMex{Ok: true, Dados: dados})
}

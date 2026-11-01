package main

/*
#include <stdlib.h>
*/
import "C"

import (
	"context"
	"errors"
	"sync"
	"time"

	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/proto/waMmsRetry"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
)

// Pede ao celular que envie de novo ao servidor uma midia que expirou. A resposta
// chega depois, como evento; quem pede fica perguntando (MediaRetryWait), com esperas
// curtas, para poder cancelar. Respostas: "ok:<caminho novo>", "sem_midia" (o
// celular nao tem o arquivo) ou "erro:<motivo>"; "" = ainda sem resposta.
type pedidoMidia struct {
	resposta chan string
	remover  func()
}

var (
	pedidosMidiaMu sync.Mutex
	pedidosMidia   = map[string]*pedidoMidia{}
)

func respostaDaMidia(evt *events.MediaRetry, chave []byte) string {
	dados, err := whatsmeow.DecryptMediaRetryNotification(evt, chave)
	if errors.Is(err, whatsmeow.ErrMediaNotAvailableOnPhone) {
		return "sem_midia"
	}
	if err != nil {
		return "erro:" + err.Error()
	}
	switch dados.GetResult() {
	case waMmsRetry.MediaRetryNotification_SUCCESS:
		if dados.GetDirectPath() == "" {
			return "erro:resposta sem caminho"
		}
		return "ok:" + dados.GetDirectPath()
	case waMmsRetry.MediaRetryNotification_NOT_FOUND:
		return "sem_midia"
	}
	return "erro:" + dados.GetResult().String()
}

func tirarPedidoMidia(chave string) *pedidoMidia {
	pedidosMidiaMu.Lock()
	defer pedidosMidiaMu.Unlock()
	p := pedidosMidia[chave]
	delete(pedidosMidia, chave)
	return p
}

//export MediaRetryStart
func MediaRetryStart(id *C.char, chat *C.char, sender *C.char, msgID *C.char, fromMe C.int, mediaKey *C.uchar, keySize C.int) *C.char {
	cli := clients[C.GoString(id)]
	if cli == nil {
		return C.CString("client not found")
	}
	chatJID, err := types.ParseJID(C.GoString(chat))
	if err != nil {
		return C.CString(err.Error())
	}
	senderJID, err := types.ParseJID(C.GoString(sender))
	if err != nil {
		return C.CString(err.Error())
	}
	idMsg := types.MessageID(C.GoString(msgID))
	chave := getByteByAddr(mediaKey, keySize)
	nome := C.GoString(id) + "|" + string(idMsg)
	if p := tirarPedidoMidia(nome); p != nil {
		p.remover()
	}
	p := &pedidoMidia{resposta: make(chan string, 1)}
	ouvinte := cli.AddEventHandler(func(evento any) {
		if v, ok := evento.(*events.MediaRetry); ok && v.MessageID == idMsg {
			select {
			case p.resposta <- respostaDaMidia(v, chave):
			default:
			}
		}
	})
	p.remover = func() { cli.RemoveEventHandler(ouvinte) }
	pedidosMidiaMu.Lock()
	pedidosMidia[nome] = p
	pedidosMidiaMu.Unlock()
	info := &types.MessageInfo{
		MessageSource: types.MessageSource{
			Chat: chatJID, Sender: senderJID, IsFromMe: fromMe != 0,
			IsGroup: chatJID.Server == types.GroupServer,
		},
		ID: idMsg,
	}
	if err := cli.SendMediaRetryReceipt(context.Background(), info, chave); err != nil {
		if p := tirarPedidoMidia(nome); p != nil {
			p.remover()
		}
		return C.CString(err.Error())
	}
	return C.CString("")
}

//export MediaRetryWait
func MediaRetryWait(id *C.char, msgID *C.char, ms C.int) *C.char {
	nome := C.GoString(id) + "|" + C.GoString(msgID)
	pedidosMidiaMu.Lock()
	p := pedidosMidia[nome]
	pedidosMidiaMu.Unlock()
	if p == nil {
		return C.CString("erro:pedido desconhecido")
	}
	select {
	case resposta := <-p.resposta:
		if q := tirarPedidoMidia(nome); q != nil {
			q.remover()
		}
		return C.CString(resposta)
	case <-time.After(time.Duration(ms) * time.Millisecond):
		return C.CString("")
	}
}

//export MediaRetryCancel
func MediaRetryCancel(id *C.char, msgID *C.char) {
	if p := tirarPedidoMidia(C.GoString(id) + "|" + C.GoString(msgID)); p != nil {
		p.remover()
	}
}

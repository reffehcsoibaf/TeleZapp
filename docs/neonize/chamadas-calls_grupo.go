package main

/*
   #include <stdlib.h>
   #include <stdint.h>
*/
import "C"

// Chamadas em grupo em andamento e convidar gente, como o Entrar e o
// Adicionar participante do WhatsApp Web (portado do WinZapp, neonize 0011 e
// 0014): perguntar ao servidor como esta uma chamada de que esta conta nao
// participa (a consulta do lobby), entrar nela pelo id, ler quem esta numa
// chamada e convidar mais gente. O meowcaller faz a sinalizacao; aqui so o
// JSON.
//
// Evento novo (CallsNextEvent): {"ev": "offer", "call", "group", "creator",
// "video"} a cada convite para uma chamada em grupo que chega, tocando ou
// nao: e o que permite entrar nela depois, enquanto ela dura.

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/purpshell/meowcaller"
	"go.mau.fi/whatsmeow/types"
)

type participanteJSON struct {
	JID   string `json:"jid"`
	PN    string `json:"pn,omitempty"`
	State string `json:"state"`
	Hand  bool   `json:"hand,omitempty"`
}

func participantesJSON(g meowcaller.GroupCallState) []participanteJSON {
	lista := make([]participanteJSON, 0, len(g.Participants))
	for _, p := range g.Participants {
		item := participanteJSON{JID: p.JID.ToNonAD().String(), State: p.State,
			Hand: p.HandRaised}
		if !p.PN.IsEmpty() {
			item.PN = p.PN.ToNonAD().String()
		}
		lista = append(lista, item)
	}
	return lista
}

func clienteDeChamadas(cliente string) *meowcaller.Client {
	chamadasMu.Lock()
	defer chamadasMu.Unlock()
	return chamadasCliente[cliente]
}

func erroJSON(e error, buf *C.char, cap C.int) C.int {
	b, _ := json.Marshal(map[string]any{"error": e.Error()})
	return escreverTexto(string(b), buf, cap)
}

// CallLobby pergunta ao servidor como esta a chamada `call` criada por
// `creator`: {"call", "groupJid", "video", "participants": [{"jid", "pn",
// "state"}]}, {"over": true} quando o servidor ja nao a tem, ou {"error"}.
//
//export CallLobby
func CallLobby(id *C.char, call *C.char, creator *C.char, buf *C.char, cap C.int) C.int {
	mc := clienteDeChamadas(C.GoString(id))
	if mc == nil {
		return erroJSON(fmt.Errorf("chamadas desligadas neste cliente"), buf, cap)
	}
	criador, err := types.ParseJID(C.GoString(creator))
	if err != nil {
		return erroJSON(err, buf, cap)
	}
	ctx, cancelar := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancelar()
	o, err := mc.QueryOngoingGroupCall(ctx, C.GoString(call), criador)
	if err != nil {
		return erroJSON(err, buf, cap)
	}
	if o == nil {
		return escreverTexto(`{"over":true}`, buf, cap)
	}
	b, _ := json.Marshal(map[string]any{
		"call": o.CallID, "groupJid": o.GroupJID.String(), "video": o.Video,
		"participants": participantesJSON(o.State)})
	return escreverTexto(string(b), buf, cap)
}

// CallJoinOngoing entra na chamada em grupo `call` que ja esta acontecendo:
// {"call": id} ou {"error"}. O audio e ligado como numa chamada feita daqui.
//
//export CallJoinOngoing
func CallJoinOngoing(id *C.char, call *C.char, creator *C.char, video C.int, buf *C.char, cap C.int) C.int {
	cliente := C.GoString(id)
	mc := clienteDeChamadas(cliente)
	if mc == nil {
		return erroJSON(fmt.Errorf("chamadas desligadas neste cliente"), buf, cap)
	}
	criador, err := types.ParseJID(C.GoString(creator))
	if err != nil {
		return erroJSON(err, buf, cap)
	}
	ctx, cancelar := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancelar()
	registrar(cliente, "entrando numa chamada em grupo em andamento (video=%v)", video != 0)
	c, err := mc.JoinOngoingGroupCall(ctx, C.GoString(call), criador, video != 0)
	if err != nil {
		registrar(cliente, "a entrada na chamada em grupo falhou: %v", err)
		return erroJSON(err, buf, cap)
	}
	ligarChamada(cliente, c, false)
	b, _ := json.Marshal(map[string]any{"call": c.ID()})
	return escreverTexto(string(b), buf, cap)
}

// CallRoster: {"group", "participants": [{"jid", "pn", "state"}]} da chamada
// em que este cliente esta. Devolve o tamanho, ou -2 sem chamada.
//
//export CallRoster
func CallRoster(id *C.char, call *C.char, buf *C.char, cap C.int) C.int {
	a := buscarChamada(C.GoString(id), C.GoString(call))
	if a == nil {
		return erroSemChamada
	}
	g, grupo := a.call.GroupState()
	b, _ := json.Marshal(map[string]any{"group": grupo, "participants": participantesJSON(g)})
	return escreverTexto(string(b), buf, cap)
}

// CallAddParticipant convida `target` (numero ou LID) para a chamada `call`
// em que este cliente esta, como o "Adicionar participante" do WhatsApp Web.
// Quem ja esta na lista da chamada e ainda nao entrou e chamado de novo,
// como o "Tocar" de la. {"ok": true}, {"rang": true} ou {"error"}.
//
//export CallAddParticipant
func CallAddParticipant(id *C.char, call *C.char, target *C.char, buf *C.char, cap C.int) C.int {
	cliente := C.GoString(id)
	a := buscarChamada(cliente, C.GoString(call))
	if a == nil {
		return erroJSON(fmt.Errorf("call not found"), buf, cap)
	}
	ctx, cancelar := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancelar()
	alvo := C.GoString(target)
	err := a.call.AddParticipant(ctx, alvo)
	if err != nil && strings.Contains(err.Error(), "already in the call roster") {
		if err = a.call.RingParticipant(ctx, alvo); err == nil {
			registrar(cliente, "participante da chamada chamado de novo")
			return escreverTexto(`{"rang":true}`, buf, cap)
		}
	}
	if err != nil {
		registrar(cliente, "adicionar participante falhou: %v", err)
		return erroJSON(err, buf, cap)
	}
	registrar(cliente, "participante convidado para a chamada")
	return escreverTexto(`{"ok":true}`, buf, cap)
}

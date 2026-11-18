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

// ---- Chamadas por link (call.whatsapp.com/voice|video/TOKEN) ----
//
// O meowcaller ja sabe consultar, entrar e criar o link; aqui so o JSON.
// `link` e o endereco inteiro ou so o codigo; `video` diz qual dos dois
// formatos (/voice/ ou /video/) o endereco tinha.

// CallLinkPreview consulta o link sem entrar: {"video", "approval", "admin",
// "creator", "creatorPn"} ou {"error"}.
//
//export CallLinkPreview
func CallLinkPreview(id *C.char, link *C.char, video C.int, buf *C.char, cap C.int) C.int {
	mc := clienteDeChamadas(C.GoString(id))
	if mc == nil {
		return erroJSON(fmt.Errorf("chamadas desligadas neste cliente"), buf, cap)
	}
	ctx, cancelar := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancelar()
	p, err := mc.PreviewCallLink(ctx, C.GoString(link), meowcaller.CallLinkOptions{Video: video != 0})
	if err != nil {
		return erroJSON(err, buf, cap)
	}
	item := map[string]any{"video": p.Video, "approval": p.ApprovalRequired,
		"admin": p.IsAdmin}
	if !p.Creator.IsEmpty() {
		item["creator"] = p.Creator.ToNonAD().String()
	}
	if !p.CreatorPhoneNumber.IsEmpty() {
		item["creatorPn"] = p.CreatorPhoneNumber.ToNonAD().String()
	}
	b, _ := json.Marshal(item)
	return escreverTexto(string(b), buf, cap)
}

// CallLinkJoin entra na chamada do link, ou na sala de espera quando o
// anfitriao precisa aprovar: {"call", "waiting", "approval", "admin"} ou
// {"error"}. O audio e ligado como numa chamada feita daqui; na sala de
// espera o evento "state" traz a fase 6 e, ao ser aceito, a fase seguinte.
//
//export CallLinkJoin
func CallLinkJoin(id *C.char, link *C.char, video C.int, buf *C.char, cap C.int) C.int {
	cliente := C.GoString(id)
	mc := clienteDeChamadas(cliente)
	if mc == nil {
		return erroJSON(fmt.Errorf("chamadas desligadas neste cliente"), buf, cap)
	}
	ctx, cancelar := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancelar()
	registrar(cliente, "entrando numa chamada por link (video=%v)", video != 0)
	c, err := mc.JoinCallLink(ctx, C.GoString(link), meowcaller.CallLinkOptions{Video: video != 0})
	if err != nil {
		registrar(cliente, "a entrada na chamada por link falhou: %v", err)
		return erroJSON(err, buf, cap)
	}
	ligarChamada(cliente, c, false)
	item := map[string]any{"call": c.ID()}
	if s, ok := c.WaitingRoomState(); ok {
		item["waiting"] = s.InWaitingRoom
		item["approval"] = s.Enabled
		item["admin"] = s.IsAdmin
		registrar(cliente, "chamada por link: sala de espera=%v, aprovacao=%v, admin=%v",
			s.InWaitingRoom, s.Enabled, s.IsAdmin)
	}
	b, _ := json.Marshal(item)
	return escreverTexto(string(b), buf, cap)
}

// CallLinkCreate cria um link de chamada que pode ser reutilizado:
// {"url", "video"} ou {"error"}.
//
//export CallLinkCreate
func CallLinkCreate(id *C.char, video C.int, buf *C.char, cap C.int) C.int {
	cliente := C.GoString(id)
	mc := clienteDeChamadas(cliente)
	if mc == nil {
		return erroJSON(fmt.Errorf("chamadas desligadas neste cliente"), buf, cap)
	}
	ctx, cancelar := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancelar()
	l, err := mc.CreateCallLink(ctx, meowcaller.CallLinkOptions{Video: video != 0})
	if err != nil {
		registrar(cliente, "criar o link de chamada falhou: %v", err)
		return erroJSON(err, buf, cap)
	}
	registrar(cliente, "link de chamada criado (video=%v)", l.Video)
	b, _ := json.Marshal(map[string]any{"url": l.URL, "video": l.Video})
	return escreverTexto(string(b), buf, cap)
}

// ---- Sala de espera, reacoes e mao levantada de chamadas em grupo/por link ----
//
// Eventos novos (CallsNextEvent), todos com "call":
//   {"ev": "waiting", "admin", "enabled", "inRoom", "users": [{"jid","pn"}]}
//       a sala de espera mudou (ate 20 pessoas);
//   {"ev": "reaction", "emoji", "who", "removed"}
//   {"ev": "hand", "who", "raised"}
//   {"ev": "screen", "who", "active"}

func ligarControlesDeGrupo(cliente string, c *meowcaller.Call) {
	id := c.ID()
	c.OnWaitingRoomState(func(s meowcaller.WaitingRoomState) {
		usuarios := []participanteJSON{}
		for i, u := range s.Users {
			if i >= 20 {
				break
			}
			item := participanteJSON{JID: u.JID.ToNonAD().String(), State: u.State}
			if !u.PN.IsEmpty() {
				item.PN = u.PN.ToNonAD().String()
			}
			usuarios = append(usuarios, item)
		}
		emitirEvento(cliente, map[string]any{"ev": "waiting", "call": id,
			"admin": s.IsAdmin, "enabled": s.Enabled, "inRoom": s.InWaitingRoom,
			"users": usuarios})
	})
	c.OnReaction(func(r meowcaller.CallReaction) {
		emitirEvento(cliente, map[string]any{"ev": "reaction", "call": id,
			"emoji": r.Emoji, "who": r.Sender.ToNonAD().String(), "removed": r.Removed})
	})
	c.OnHandRaise(func(s meowcaller.HandRaiseState) {
		emitirEvento(cliente, map[string]any{"ev": "hand", "call": id,
			"who": s.Participant.ToNonAD().String(), "raised": s.Raised})
	})
	c.OnScreenShare(func(s meowcaller.ScreenShareState) {
		emitirEvento(cliente, map[string]any{"ev": "screen", "call": id,
			"who": s.Participant.ToNonAD().String(), "active": s.Active})
	})
}

func controleDeSala(id *C.char, call *C.char, user *C.char, admitir bool, buf *C.char, cap C.int) C.int {
	cliente := C.GoString(id)
	a := buscarChamada(cliente, C.GoString(call))
	if a == nil {
		return erroJSON(fmt.Errorf("call not found"), buf, cap)
	}
	ctx, cancelar := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancelar()
	var err error
	if admitir {
		err = a.call.AdmitParticipant(ctx, C.GoString(user))
	} else {
		err = a.call.DenyParticipant(ctx, C.GoString(user))
	}
	if err != nil {
		registrar(cliente, "sala de espera (admitir=%v) falhou: %v", admitir, err)
		return erroJSON(err, buf, cap)
	}
	registrar(cliente, "sala de espera: participante tratado (admitir=%v)", admitir)
	return escreverTexto(`{"ok":true}`, buf, cap)
}

// CallWaitingAdmit deixa `user` entrar na chamada por link.
//
//export CallWaitingAdmit
func CallWaitingAdmit(id *C.char, call *C.char, user *C.char, buf *C.char, cap C.int) C.int {
	return controleDeSala(id, call, user, true, buf, cap)
}

// CallWaitingDeny recusa a entrada de `user`.
//
//export CallWaitingDeny
func CallWaitingDeny(id *C.char, call *C.char, user *C.char, buf *C.char, cap C.int) C.int {
	return controleDeSala(id, call, user, false, buf, cap)
}

// CallApprovalRequired liga (1) ou desliga (0) a aprovacao para entrar.
//
//export CallApprovalRequired
func CallApprovalRequired(id *C.char, call *C.char, enabled C.int, buf *C.char, cap C.int) C.int {
	cliente := C.GoString(id)
	a := buscarChamada(cliente, C.GoString(call))
	if a == nil {
		return erroJSON(fmt.Errorf("call not found"), buf, cap)
	}
	ctx, cancelar := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancelar()
	if err := a.call.SetApprovalRequired(ctx, enabled != 0); err != nil {
		registrar(cliente, "aprovacao para entrar falhou: %v", err)
		return erroJSON(err, buf, cap)
	}
	return escreverTexto(`{"ok":true}`, buf, cap)
}

// CallReact manda uma reacao (emoji; vazio tira a nossa).
//
//export CallReact
func CallReact(id *C.char, call *C.char, emoji *C.char, buf *C.char, cap C.int) C.int {
	a := buscarChamada(C.GoString(id), C.GoString(call))
	if a == nil {
		return erroJSON(fmt.Errorf("call not found"), buf, cap)
	}
	if err := a.call.SendReaction(C.GoString(emoji)); err != nil {
		return erroJSON(err, buf, cap)
	}
	return escreverTexto(`{"ok":true}`, buf, cap)
}

// CallHand levanta (1) ou baixa (0) a mao.
//
//export CallHand
func CallHand(id *C.char, call *C.char, raised C.int, buf *C.char, cap C.int) C.int {
	a := buscarChamada(C.GoString(id), C.GoString(call))
	if a == nil {
		return erroJSON(fmt.Errorf("call not found"), buf, cap)
	}
	if err := a.call.SetHandRaised(raised != 0); err != nil {
		return erroJSON(err, buf, cap)
	}
	return escreverTexto(`{"ok":true}`, buf, cap)
}

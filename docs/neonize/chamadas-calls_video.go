package main

/*
   #include <stdlib.h>
   #include <stdint.h>
*/
import "C"

// Video e chamadas em grupo pelo meowcaller, no mesmo estilo do audio
// (calls.go): sem protobuf nem callbacks.
//
// O video e H.264 em unidades de acesso Annex-B (os NAL de um quadro, com os
// codigos de inicio); o meowcaller nao codifica nem decodifica pixels, so os
// leva pelo relay. Quem chama codifica a camera e decodifica o que chega.
//
// Eventos novos (CallsNextEvent): {"ev": "video", "call", "active",
// "upgrade", "orientation", "raw"} a cada <video> do outro lado;
// {"ev": "keyframe", "call"} quando o outro lado pede um quadro-chave;
// {"ev": "group", "call", "participants"} quando a lista de uma chamada em
// grupo muda. "incoming" traz tambem "video" e "group".

import (
	"context"
	"encoding/json"
	"fmt"
	"time"
	"unsafe"

	"github.com/purpshell/meowcaller"
)

const (
	videoNaFila = 30 // 3 s de video a 10 quadros por segundo

	// CallVideo: o que fazer com o video da chamada
	videoPedir    = 1 // pedir para passar a chamada de voz para video
	videoAceitar  = 2 // aceitar o pedido do outro lado
	videoParar    = 3 // parar o nosso video
	videoLigar    = 4 // ligar a camera de novo (estado 1)
	videoDesligar = 5 // desligar a camera sem sair do video (estado 0)
)

// ligarVideo anexa a fila de video e os avisos de video e de grupo a uma chamada.
func ligarVideo(cliente string, c *meowcaller.Call, a *chamadaAtiva) {
	id := c.ID()
	c.ReceiveVideo(meowcaller.VideoSinkFunc(func(au []byte) {
		if a.videoRecebidos.Add(1) == 1 {
			registrar(cliente, "chamada %s: primeiro quadro de video do outro lado (%d bytes)", id, len(au))
		}
		b := append([]byte(nil), au...)
		select {
		case a.video <- b:
		default: // fila cheia: descarta o mais antigo
			select {
			case <-a.video:
			default:
			}
			select {
			case a.video <- b:
			default:
			}
		}
	}))
	c.OnVideoState(func(v meowcaller.VideoState) {
		registrar(cliente, "chamada %s: video do outro lado ativo=%v pedido=%v estado=%d", id, v.Active, v.Upgrade, v.Raw)
		emitirEvento(cliente, map[string]any{"ev": "video", "call": id, "active": v.Active,
			"upgrade": v.Upgrade, "orientation": v.Orientation, "raw": v.Raw})
	})
	c.OnVideoKeyframeRequest(func() {
		emitirEvento(cliente, map[string]any{"ev": "keyframe", "call": id})
	})
	c.OnGroupState(func(g meowcaller.GroupCallState) {
		emitirEvento(cliente, map[string]any{"ev": "group", "call": id, "participants": len(g.Participants)})
	})
}

// CallDialWith liga para um numero, de voz (video=0) ou de video (1). O
// resultado e o de CallDial.
//
//export CallDialWith
func CallDialWith(id *C.char, target *C.char, video C.int, buf *C.char, cap C.int) C.int {
	return discar(C.GoString(id), C.GoString(target), video != 0, buf, cap)
}

// CallGroupDial liga para todos os membros de um grupo (o endereco @g.us ou
// so o numero do grupo), de voz ou de video, e escreve em buf o JSON
// {"call": id} ou {"error": texto}.
//
//export CallGroupDial
func CallGroupDial(id *C.char, group *C.char, video C.int, buf *C.char, cap C.int) C.int {
	cliente := C.GoString(id)
	chamadasMu.Lock()
	mc := chamadasCliente[cliente]
	chamadasMu.Unlock()
	erro := func(e error) C.int {
		b, _ := json.Marshal(map[string]any{"error": e.Error()})
		return escreverTexto(string(b), buf, cap)
	}
	if mc == nil {
		return erro(fmt.Errorf("chamadas desligadas neste cliente"))
	}
	ctx, cancelar := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancelar()
	grupo := C.GoString(group)
	registrar(cliente, "ligando para o grupo %s (video=%v)", grupo, video != 0)
	c, err := mc.GroupCallByIDWithOptions(ctx, grupo, meowcaller.GroupCallOptions{Video: video != 0})
	if err != nil {
		registrar(cliente, "a ligacao para o grupo falhou: %v", err)
		return erro(err)
	}
	ligarChamada(cliente, c, false)
	b, _ := json.Marshal(map[string]any{"call": c.ID()})
	return escreverTexto(string(b), buf, cap)
}

// CallVideo muda o video da chamada (videoPedir ... videoDesligar). 0 = ok,
// -1 o meowcaller recusou, -2 sem chamada, -4 acao desconhecida.
//
//export CallVideo
func CallVideo(id *C.char, call *C.char, action C.int) C.int {
	a := buscarChamada(C.GoString(id), C.GoString(call))
	if a == nil {
		return erroSemChamada
	}
	var err error
	switch int(action) {
	case videoPedir:
		err = a.call.StartVideo()
	case videoAceitar:
		err = a.call.AcceptVideo()
	case videoParar:
		err = a.call.StopVideo()
	case videoLigar:
		err = a.call.SetVideoEnabled(true)
	case videoDesligar:
		err = a.call.SetVideoEnabled(false)
	default:
		return erroTamanho
	}
	if err != nil {
		registrar(C.GoString(id), "video %d da chamada %s falhou: %v", int(action), C.GoString(call), err)
		return -1
	}
	return 0
}

// CallWriteVideo manda uma unidade de acesso H.264 (Annex-B) da nossa camera,
// que dura durationMs (0 = o passo padrao). 0 = ok, -1 sem video ativo ainda,
// -2 sem chamada.
//
//export CallWriteVideo
func CallWriteVideo(id *C.char, call *C.char, buf *C.uchar, n C.int, durationMs C.int) C.int {
	a := buscarChamada(C.GoString(id), C.GoString(call))
	if a == nil {
		return erroSemChamada
	}
	if n <= 0 {
		return erroTamanho
	}
	au := C.GoBytes(unsafe.Pointer(buf), n)
	if err := a.call.SendVideoWithDuration(au, time.Duration(durationMs)*time.Millisecond); err != nil {
		return -1
	}
	return 0
}

// CallReadVideo entrega uma unidade de acesso do outro lado, esperando ate
// timeoutMs. Devolve o tamanho, 0 (nada), -2 (chamada acabou) ou -4 (buffer
// pequeno: a unidade e descartada).
//
//export CallReadVideo
func CallReadVideo(id *C.char, call *C.char, buf *C.uchar, cap C.int, timeoutMs C.int) C.int {
	a := buscarChamada(C.GoString(id), C.GoString(call))
	if a == nil {
		return erroSemChamada
	}
	select {
	case b := <-a.video:
		if len(b) > int(cap) {
			return erroTamanho
		}
		copy(unsafe.Slice((*byte)(unsafe.Pointer(buf)), int(cap)), b)
		return C.int(len(b))
	case <-a.fim:
		return erroSemChamada
	case <-time.After(time.Duration(timeoutMs) * time.Millisecond):
		return erroTempoLimite
	}
}

// CallInfo escreve em buf o JSON {"video", "sendingVideo", "receivingVideo",
// "group", "participants"} da chamada. Devolve o tamanho, ou -2 sem chamada.
//
//export CallInfo
func CallInfo(id *C.char, call *C.char, buf *C.char, cap C.int) C.int {
	a := buscarChamada(C.GoString(id), C.GoString(call))
	if a == nil {
		return erroSemChamada
	}
	g, grupo := a.call.GroupState()
	b, _ := json.Marshal(map[string]any{
		"video": a.call.IsVideo(), "sendingVideo": a.call.IsSendingVideo(),
		"receivingVideo": a.call.IsReceivingVideo(), "group": grupo,
		"participants": len(g.Participants)})
	return escreverTexto(string(b), buf, cap)
}

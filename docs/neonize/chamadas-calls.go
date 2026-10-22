package main

/*
   #include <stdlib.h>
   #include <stdint.h>
*/
import "C"

// Chamadas de voz do WhatsApp pelo mesmo cliente whatsmeow que ja cuida das
// mensagens (um unico pareamento). Usa o meowcaller (MIT,
// https://github.com/purpshell/meowcaller), que cuida do protocolo de
// chamada, do relay e do codec MLow.
//
// Sem protobuf nem callbacks: o Python pergunta por eventos (JSON, uma linha
// por evento) e troca audio PCM s16le, 16 kHz, mono, em quadros de 960
// amostras (60 ms), por duas funcoes bloqueantes com tempo limite.
//
// Ordem de uso: CallsConfigure(1) antes de Neonize() (o meowcaller precisa
// estar instalado antes de o cliente conectar); depois CallsNextEvent em laco,
// CallDial, CallAnswer, CallHangup, CallReadAudio e CallWriteAudio.

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"sync"
	"time"
	"unsafe"

	"github.com/purpshell/meowcaller"
)

const (
	bytesPorQuadro  = meowcaller.FrameSamples * 2
	quadrosNaFila   = 50 // 3 s de audio de cada lado
	esperaFonteMs   = 150
	eventosNaFila   = 256
	erroSemChamada  = -2
	erroSemCliente  = -3
	erroTamanho     = -4
	erroTempoLimite = 0
)

var (
	chamadasQuer bool

	chamadasMu      sync.Mutex
	chamadasCliente = map[string]*meowcaller.Client{}
	chamadasEventos = map[string]chan string{}
	chamadasAtivas  = map[string]*chamadaAtiva{} // chave: id do cliente + "|" + id da chamada
)

// chamadaAtiva liga uma chamada do meowcaller as filas de audio do Python.
type chamadaAtiva struct {
	call *meowcaller.Call
	// entrada: o que chega do outro lado (rumo ao alto-falante).
	entrada chan []byte
	// saida: o que o microfone manda (rumo ao outro lado).
	saida chan []byte
	fim   chan struct{}
	uma   sync.Once
}

func (c *chamadaAtiva) encerrar() { c.uma.Do(func() { close(c.fim) }) }

// ReadFrame e chamado pelo meowcaller a cada 60 ms; sem audio do Python a
// tempo, entrega silencio para o ritmo do envio nao parar.
func (c *chamadaAtiva) ReadFrame() ([]float32, error) {
	f := make([]float32, meowcaller.FrameSamples)
	select {
	case b := <-c.saida:
		for i := range f {
			f[i] = float32(int16(uint16(b[i*2])|uint16(b[i*2+1])<<8)) / 32768
		}
	case <-time.After(esperaFonteMs * time.Millisecond):
	case <-c.fim:
		return nil, fmt.Errorf("chamada encerrada")
	}
	return f, nil
}

func (c *chamadaAtiva) WriteFrame(frame []float32) error {
	b := make([]byte, len(frame)*2)
	for i, v := range frame {
		if v > 1 {
			v = 1
		} else if v < -1 {
			v = -1
		}
		s := uint16(int16(v * 32767))
		b[i*2] = byte(s)
		b[i*2+1] = byte(s >> 8)
	}
	select {
	case c.entrada <- b:
	default: // fila cheia: descarta o mais antigo para nao atrasar a voz
		select {
		case <-c.entrada:
		default:
		}
		select {
		case c.entrada <- b:
		default:
		}
	}
	return nil
}

func (c *chamadaAtiva) Close() error { return nil }

func chaveChamada(cliente, chamada string) string { return cliente + "|" + chamada }

func emitirEvento(cliente string, ev map[string]any) {
	chamadasMu.Lock()
	fila := chamadasEventos[cliente]
	chamadasMu.Unlock()
	if fila == nil {
		return
	}
	b, _ := json.Marshal(ev)
	select {
	case fila <- string(b):
	default: // ninguem esta lendo: perde o evento mais antigo
		select {
		case <-fila:
		default:
		}
		select {
		case fila <- string(b):
		default:
		}
	}
}

// ligarChamada anexa o audio e os avisos a uma chamada nova (de entrada ou de saida).
func ligarChamada(cliente string, c *meowcaller.Call) *chamadaAtiva {
	a := &chamadaAtiva{
		call:    c,
		entrada: make(chan []byte, quadrosNaFila),
		saida:   make(chan []byte, quadrosNaFila),
		fim:     make(chan struct{}),
	}
	id := c.ID()
	chamadasMu.Lock()
	chamadasAtivas[chaveChamada(cliente, id)] = a
	chamadasMu.Unlock()
	c.Receive(a)
	c.Play(a)
	c.OnStateChange(func(p meowcaller.CallPhase) {
		emitirEvento(cliente, map[string]any{"ev": "state", "call": id, "phase": int(p)})
	})
	c.OnReady(func() {
		emitirEvento(cliente, map[string]any{"ev": "ready", "call": id})
	})
	c.OnEnd(func(motivo string) {
		a.encerrar()
		chamadasMu.Lock()
		delete(chamadasAtivas, chaveChamada(cliente, id))
		chamadasMu.Unlock()
		emitirEvento(cliente, map[string]any{"ev": "end", "call": id, "reason": motivo})
	})
	return a
}

// instalarChamadas e chamado por Neonize() logo depois de criar o cliente e
// antes de conectar.
func instalarChamadas(id string) {
	if !chamadasQuer {
		return
	}
	cli := clients[id]
	if cli == nil {
		return
	}
	mc := meowcaller.NewClient(cli)
	chamadasMu.Lock()
	chamadasCliente[id] = mc
	chamadasEventos[id] = make(chan string, eventosNaFila)
	chamadasMu.Unlock()
	mc.OnIncomingCall(func(c *meowcaller.Call) {
		ligarChamada(id, c)
		emitirEvento(id, map[string]any{"ev": "incoming", "call": c.ID(), "peer": c.Peer()})
	})
}

func removerChamadas(id string) {
	chamadasMu.Lock()
	defer chamadasMu.Unlock()
	delete(chamadasCliente, id)
	delete(chamadasEventos, id)
	for k, a := range chamadasAtivas {
		if strings.HasPrefix(k, id+"|") {
			a.encerrar()
			delete(chamadasAtivas, k)
		}
	}
}

func escreverTexto(s string, buf *C.char, cap C.int) C.int {
	b := []byte(s)
	if len(b)+1 > int(cap) {
		return erroTamanho
	}
	dst := unsafe.Slice((*byte)(unsafe.Pointer(buf)), int(cap))
	copy(dst, b)
	dst[len(b)] = 0
	return C.int(len(b))
}

func buscarChamada(cliente, chamada string) *chamadaAtiva {
	chamadasMu.Lock()
	defer chamadasMu.Unlock()
	return chamadasAtivas[chaveChamada(cliente, chamada)]
}

// variantesNumero: no Brasil muitas contas antigas nao tem o 9 depois do DDD.
func variantesNumero(numero string) []string {
	v := []string{numero}
	if strings.HasPrefix(numero, "55") {
		if len(numero) == 13 && numero[4] == '9' {
			v = append(v, numero[:4]+numero[5:])
		} else if len(numero) == 12 {
			v = append(v, numero[:4]+"9"+numero[4:])
		}
	}
	return v
}

//export CallsConfigure
func CallsConfigure(enabled C.int) {
	chamadasQuer = enabled != 0
}

// CallsEnabled diz se este build tem chamadas e se estao ligadas (1) ou nao (0).
//
//export CallsEnabled
func CallsEnabled(id *C.char) C.int {
	chamadasMu.Lock()
	defer chamadasMu.Unlock()
	if chamadasCliente[C.GoString(id)] != nil {
		return 1
	}
	return 0
}

// CallsNextEvent espera ate timeoutMs por um evento e o escreve como JSON em
// buf. Devolve o tamanho (0 = nenhum evento), -2 sem fila, -4 buffer pequeno.
//
//export CallsNextEvent
func CallsNextEvent(id *C.char, buf *C.char, cap C.int, timeoutMs C.int) C.int {
	chamadasMu.Lock()
	fila := chamadasEventos[C.GoString(id)]
	chamadasMu.Unlock()
	if fila == nil {
		return erroSemChamada
	}
	select {
	case s := <-fila:
		return escreverTexto(s, buf, cap)
	case <-time.After(time.Duration(timeoutMs) * time.Millisecond):
		return erroTempoLimite
	}
}

// CallDial liga para um numero (so digitos, com DDI) e escreve em buf o JSON
// {"call": id} ou {"error": texto}. Devolve o tamanho escrito.
//
//export CallDial
func CallDial(id *C.char, target *C.char, buf *C.char, cap C.int) C.int {
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
	cli := clients[cliente]
	if cli == nil {
		return erro(fmt.Errorf("cliente nao encontrado"))
	}
	ctx, cancelar := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancelar()
	numero := C.GoString(target)
	destino := numero
	if strings.Contains(numero, "@") {
		// ja e um endereco (ex.: 123@lid): nao ha o que resolver
	} else if resp, err := cli.IsOnWhatsApp(ctx, variantesNumero(numero)); err == nil {
		for _, r := range resp {
			if !r.IsIn {
				continue
			}
			if !r.PhoneNumber.IsEmpty() && r.PhoneNumber.User != "" {
				destino = r.PhoneNumber.User
			} else {
				destino = r.JID.User
			}
			break
		}
	}
	c, err := mc.Call(ctx, destino)
	if err != nil {
		return erro(err)
	}
	ligarChamada(cliente, c)
	b, _ := json.Marshal(map[string]any{"call": c.ID(), "peer": c.Peer()})
	return escreverTexto(string(b), buf, cap)
}

// CallAnswer atende uma chamada recebida. 0 = ok.
//
//export CallAnswer
func CallAnswer(id *C.char, call *C.char) C.int {
	a := buscarChamada(C.GoString(id), C.GoString(call))
	if a == nil {
		return erroSemChamada
	}
	if err := a.call.Answer(); err != nil {
		return -1
	}
	return 0
}

// CallHangup desliga (ou recusa, se ainda tocando). 0 = ok.
//
//export CallHangup
func CallHangup(id *C.char, call *C.char) C.int {
	a := buscarChamada(C.GoString(id), C.GoString(call))
	if a == nil {
		return erroSemChamada
	}
	if err := a.call.Hangup(); err != nil {
		return -1
	}
	return 0
}

// CallReadAudio entrega um quadro (1920 bytes, PCM s16le) do que chegou do
// outro lado, esperando ate timeoutMs. Devolve 1920, 0 (nada), -2 (chamada
// acabou) ou -4 (buffer pequeno).
//
//export CallReadAudio
func CallReadAudio(id *C.char, call *C.char, buf *C.uchar, cap C.int, timeoutMs C.int) C.int {
	a := buscarChamada(C.GoString(id), C.GoString(call))
	if a == nil {
		return erroSemChamada
	}
	if int(cap) < bytesPorQuadro {
		return erroTamanho
	}
	select {
	case b := <-a.entrada:
		copy(unsafe.Slice((*byte)(unsafe.Pointer(buf)), int(cap)), b)
		return C.int(len(b))
	case <-a.fim:
		return erroSemChamada
	case <-time.After(time.Duration(timeoutMs) * time.Millisecond):
		return erroTempoLimite
	}
}

// CallWriteAudio recebe um quadro de 1920 bytes (PCM s16le) do microfone.
// 0 = ok, -2 chamada acabou, -4 tamanho errado.
//
//export CallWriteAudio
func CallWriteAudio(id *C.char, call *C.char, buf *C.uchar, n C.int) C.int {
	a := buscarChamada(C.GoString(id), C.GoString(call))
	if a == nil {
		return erroSemChamada
	}
	if int(n) != bytesPorQuadro {
		return erroTamanho
	}
	b := make([]byte, bytesPorQuadro)
	copy(b, unsafe.Slice((*byte)(unsafe.Pointer(buf)), bytesPorQuadro))
	select {
	case a.saida <- b:
	default: // fila cheia: descarta o mais antigo
		select {
		case <-a.saida:
		default:
		}
		select {
		case a.saida <- b:
		default:
		}
	}
	return 0
}

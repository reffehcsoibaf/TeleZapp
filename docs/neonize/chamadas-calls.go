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
	"regexp"
	"strings"
	"sync"
	"sync/atomic"
	"time"
	"unsafe"

	"github.com/purpshell/meowcaller"
	"github.com/rs/zerolog"
	waLog "go.mau.fi/whatsmeow/util/log"
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
	chamadasLogs    = map[string]waLog.Logger{} // log do cliente, para registrar()
	chamadasAtivas  = map[string]*chamadaAtiva{} // chave: id do cliente + "|" + id da chamada
)

// O log vai em relatos: telefones e enderecos aparecem so com os 4 ultimos
// digitos.
var reEndereco = regexp.MustCompile(`\d{5,}((?::\d+)?@[A-Za-z.]+)`)

func mascarar(s string) string {
	return reEndereco.ReplaceAllStringFunc(s, func(m string) string {
		i := strings.IndexAny(m, ":@")
		numero := m[:i]
		return "..." + numero[len(numero)-4:] + m[i:]
	})
}

func mascararNumero(s string) string {
	if strings.Contains(s, "@") || len(s) <= 4 {
		return mascarar(s)
	}
	return "..." + s[len(s)-4:]
}

// logChamadas leva o que o meowcaller escreve (zerolog, JSON) para o log do
// cliente, que chega ao Python. Sai tudo como aviso (WARN) com o prefixo
// "chamadas:", porque o Python so grava avisos do whatsmeow por padrao. Uma
// mensagem que se repete aparece nas 8 primeiras vezes e depois a cada 200.
type logChamadas struct {
	log    waLog.Logger
	mu     sync.Mutex
	vistos map[string]int
}

func (w *logChamadas) Write(p []byte) (int, error) {
	linha := strings.TrimSpace(string(p))
	var campos map[string]any
	chave := linha
	if json.Unmarshal(p, &campos) == nil {
		chave = fmt.Sprint(campos["level"], "|", campos["message"])
	}
	w.mu.Lock()
	w.vistos[chave]++
	n := w.vistos[chave]
	w.mu.Unlock()
	if n <= 8 || n%200 == 0 {
		w.log.Warnf("chamadas: meowcaller %s", mascarar(linha))
	}
	return len(p), nil
}

// registrar escreve uma linha de diagnostico das chamadas no log do cliente.
func registrar(cliente, formato string, args ...any) {
	chamadasMu.Lock()
	l := chamadasLogs[cliente]
	chamadasMu.Unlock()
	if l == nil {
		return
	}
	l.Warnf("chamadas: %s", mascarar(fmt.Sprintf(formato, args...)))
}

// chamadaAtiva liga uma chamada do meowcaller as filas de audio do Python.
type chamadaAtiva struct {
	call *meowcaller.Call
	// entrante: a chamada veio de fora; atendida: ja atendemos. Recusar uma
	// chamada que ainda toca usa Reject (o terminate do Hangup nao a derruba).
	entrante bool
	atendida atomic.Bool
	// entrada: o que chega do outro lado (rumo ao alto-falante).
	entrada chan []byte
	// saida: o que o microfone manda (rumo ao outro lado).
	saida chan []byte
	fim   chan struct{}
	uma   sync.Once
	// quadros que passaram, para o log dizer se o som chegou ou saiu
	recebidos atomic.Int64 // do outro lado (WriteFrame)
	enviados  atomic.Int64 // do nosso microfone (ReadFrame)
}

func (c *chamadaAtiva) encerrar() { c.uma.Do(func() { close(c.fim) }) }

// ReadFrame e chamado pelo meowcaller a cada 60 ms; sem audio do Python a
// tempo, entrega silencio para o ritmo do envio nao parar.
func (c *chamadaAtiva) ReadFrame() ([]float32, error) {
	f := make([]float32, meowcaller.FrameSamples)
	select {
	case b := <-c.saida:
		c.enviados.Add(1)
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
	c.recebidos.Add(1)
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
func ligarChamada(cliente string, c *meowcaller.Call, entrante bool) *chamadaAtiva {
	a := &chamadaAtiva{
		call:     c,
		entrante: entrante,
		entrada:  make(chan []byte, quadrosNaFila),
		saida:    make(chan []byte, quadrosNaFila),
		fim:      make(chan struct{}),
	}
	id := c.ID()
	chamadasMu.Lock()
	chamadasAtivas[chaveChamada(cliente, id)] = a
	chamadasMu.Unlock()
	c.Receive(a)
	c.Play(a)
	inicio := time.Now()
	go func() { // a cada 5 s: quantos quadros ja passaram
		t := time.NewTicker(5 * time.Second)
		defer t.Stop()
		for {
			select {
			case <-a.fim:
				return
			case <-t.C:
				registrar(cliente, "chamada %s, %.0fs: quadros do outro lado=%d, do microfone=%d",
					id, time.Since(inicio).Seconds(), a.recebidos.Load(), a.enviados.Load())
			}
		}
	}()
	registrar(cliente, "chamada %s criada (entrante=%v, com=%s)", id, entrante, c.Peer())
	c.OnStateChange(func(p meowcaller.CallPhase) {
		registrar(cliente, "chamada %s: fase %d depois de %.1fs", id, int(p), time.Since(inicio).Seconds())
		emitirEvento(cliente, map[string]any{"ev": "state", "call": id, "phase": int(p)})
	})
	c.OnReady(func() {
		registrar(cliente, "chamada %s: som do outro lado chegou (primeiro RTP) depois de %.1fs", id, time.Since(inicio).Seconds())
		emitirEvento(cliente, map[string]any{"ev": "ready", "call": id})
	})
	c.OnEnd(func(motivo string) {
		registrar(cliente, "chamada %s encerrada (%s) depois de %.1fs: quadros do outro lado=%d, do microfone=%d",
			id, motivo, time.Since(inicio).Seconds(), a.recebidos.Load(), a.enviados.Load())
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
	registro := &logChamadas{log: cli.Log.Sub("Chamadas"), vistos: map[string]int{}}
	chamadasMu.Lock()
	chamadasLogs[id] = registro.log
	chamadasMu.Unlock()
	logger := zerolog.New(registro).Level(zerolog.InfoLevel)
	mc := meowcaller.NewClient(cli, meowcaller.WithLogger(logger))
	chamadasMu.Lock()
	chamadasCliente[id] = mc
	chamadasEventos[id] = make(chan string, eventosNaFila)
	chamadasMu.Unlock()
	mc.OnIncomingCall(func(c *meowcaller.Call) {
		ligarChamada(id, c, true)
		emitirEvento(id, map[string]any{"ev": "incoming", "call": c.ID(), "peer": c.Peer()})
	})
}

func removerChamadas(id string) {
	chamadasMu.Lock()
	defer chamadasMu.Unlock()
	delete(chamadasCliente, id)
	delete(chamadasEventos, id)
	delete(chamadasLogs, id)
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
	registrar(cliente, "ligando para %s (pedido: %s)", mascararNumero(destino), mascararNumero(numero))
	c, err := mc.Call(ctx, destino)
	if err != nil {
		registrar(cliente, "a ligacao para %s falhou: %v", mascararNumero(destino), err)
		return erro(err)
	}
	ligarChamada(cliente, c, false)
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
		registrar(C.GoString(id), "atender %s falhou: %v", C.GoString(call), err)
		return -1
	}
	a.atendida.Store(true)
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
	var err error
	if a.entrante && !a.atendida.Load() {
		err = a.call.Reject()
	} else {
		err = a.call.Hangup()
	}
	if err != nil {
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

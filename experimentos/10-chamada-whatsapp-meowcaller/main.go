// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Contribuidores do TeleZapp

// Fase 0 das chamadas do WhatsApp: um programa separado do TeleZapp que testa
// o meowcaller (https://github.com/purpshell/meowcaller). A versao atual do
// meowcaller recebe o cliente do fork hypermeow
// (github.com/polymorfa/hypermeow) e nao o whatsmeow oficial; por isso este
// programa usa o hypermeow.
//
// Ele entra na conta como um aparelho conectado a mais (pareamento por codigo
// de telefone) e atende ou faz uma chamada de audio. O audio pode ser:
//   - um tom de 440 Hz de 3 s (sem -pcm), com o que chega gravado em WAV; ou
//   - a voz real, quando o chamada_whatsapp.py passa -pcm host:porta: o Python
//     liga o microfone e o alto-falante e troca PCM s16le, 16 kHz, mono com
//     este programa por um socket local (o desenho que uma DLL teria).
//
// A saida de texto e uma linha por fato, para o Python ler:
//
//	CODIGO <codigo>  PAREADO  CONECTADO <ms>  ESPERANDO  RECEBIDA <jid>
//	ESTADO <fase>  PRONTO <ms>  FIM <motivo>  ERRO <texto>  MEM <MB>
//
// Uso (veja o .bat do teste):
//
//	chamadas-teste parear -telefone 5551999998888
//	chamadas-teste ouvir  [-segundos 45] [-espera 90] [-pcm 127.0.0.1:1234]
//	chamadas-teste ligar  -para 5551999998888 [-segundos 45] [-pcm ...]
//
// A sessao fica em sessao-chamadas.db, ao lado do programa.
package main

import (
	"context"
	"encoding/binary"
	"flag"
	"fmt"
	"io"
	"math"
	"net"
	"os"
	"os/signal"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"

	whatsmeow "github.com/polymorfa/hypermeow"
	"github.com/polymorfa/hypermeow/store/sqlstore"
	"github.com/polymorfa/hypermeow/types/events"
	waLog "github.com/polymorfa/hypermeow/util/log"
	"github.com/purpshell/meowcaller"
	"github.com/rs/zerolog"
	_ "modernc.org/sqlite"
)

func linha(formato string, args ...any) {
	fmt.Printf(formato+"\n", args...)
}

func memoria() float64 {
	var m runtime.MemStats
	runtime.ReadMemStats(&m)
	return float64(m.Sys) / 1048576
}

// tom gera um seno de 440 Hz em quadros de 60 ms (16 kHz, mono, float32).
type tom struct {
	fase    float64
	quadros int
	maximo  int
}

func (t *tom) ReadFrame() ([]float32, error) {
	if t.quadros >= t.maximo {
		return nil, io.EOF
	}
	t.quadros++
	f := make([]float32, meowcaller.FrameSamples)
	for i := range f {
		f[i] = float32(0.2 * math.Sin(t.fase))
		t.fase += 2 * math.Pi * 440 / float64(meowcaller.SampleRate)
	}
	return f, nil
}

func (t *tom) Close() error { return nil }

// fonteSocket le quadros PCM s16le do Python; sem dados a tempo, entrega
// silencio para o ritmo do envio nao parar.
type fonteSocket struct {
	conn  net.Conn
	bruto []byte
}

func (s *fonteSocket) ReadFrame() ([]float32, error) {
	if s.bruto == nil {
		s.bruto = make([]byte, meowcaller.FrameSamples*2)
	}
	_ = s.conn.SetReadDeadline(time.Now().Add(150 * time.Millisecond))
	n, err := io.ReadFull(s.conn, s.bruto)
	f := make([]float32, meowcaller.FrameSamples)
	if err != nil {
		if ne, ok := err.(net.Error); ok && ne.Timeout() {
			return f, nil // silencio
		}
		if n == 0 {
			return nil, io.EOF
		}
		return f, nil
	}
	for i := range f {
		f[i] = float32(int16(binary.LittleEndian.Uint16(s.bruto[i*2:]))) / 32768
	}
	return f, nil
}

func (s *fonteSocket) Close() error { return nil }

// destinoSocket manda o que chega, em PCM s16le, para o Python.
type destinoSocket struct {
	conn  net.Conn
	bruto []byte
}

func (d *destinoSocket) WriteFrame(frame []float32) error {
	if len(d.bruto) != len(frame)*2 {
		d.bruto = make([]byte, len(frame)*2)
	}
	for i, v := range frame {
		if v > 1 {
			v = 1
		} else if v < -1 {
			v = -1
		}
		binary.LittleEndian.PutUint16(d.bruto[i*2:], uint16(int16(v*32767)))
	}
	_ = d.conn.SetWriteDeadline(time.Now().Add(200 * time.Millisecond))
	_, err := d.conn.Write(d.bruto)
	if err != nil {
		return nil // o Python pode ter fechado; a chamada segue
	}
	return nil
}

func (d *destinoSocket) Close() error { return nil }

// duplo entrega cada quadro a dois destinos.
type duplo struct{ a, b meowcaller.AudioSink }

func (d duplo) WriteFrame(f []float32) error {
	_ = d.a.WriteFrame(f)
	return d.b.WriteFrame(f)
}
func (d duplo) Close() error { _ = d.a.Close(); return d.b.Close() }

func abrir(ctx context.Context) (*whatsmeow.Client, error) {
	exe, _ := os.Executable()
	base := filepath.Dir(exe)
	if _, err := os.Stat(filepath.Join(".", "go.mod")); err == nil {
		base = "." // rodando com go run
	}
	banco := filepath.Join(base, "sessao-chamadas.db")
	logger := waLog.Stdout("whatsmeow", "WARN", false)
	container, err := sqlstore.New(ctx, "sqlite",
		"file:"+filepath.ToSlash(banco)+"?_pragma=foreign_keys(1)&_pragma=busy_timeout(10000)", logger)
	if err != nil {
		return nil, err
	}
	aparelho, err := container.GetFirstDevice(ctx)
	if err != nil {
		return nil, err
	}
	return whatsmeow.NewClient(aparelho, logger), nil
}

func parear(ctx context.Context, cli *whatsmeow.Client, telefone string) error {
	if cli.Store.ID != nil {
		linha("PAREADO %s", cli.Store.ID.String())
		return nil
	}
	if telefone == "" {
		return fmt.Errorf("precisa de -telefone")
	}
	canal, err := cli.GetQRChannel(ctx)
	if err != nil {
		return err
	}
	if err := cli.Connect(); err != nil {
		return err
	}
	pedido := false
	for evt := range canal {
		switch evt.Event {
		case "code":
			if !pedido {
				pedido = true
				codigo, err := cli.PairPhone(ctx, telefone, true,
					whatsmeow.PairClientChrome, "Chrome (Windows)")
				if err != nil {
					return err
				}
				linha("CODIGO %s", codigo)
			}
		case "success":
			linha("PAREADO")
			return nil
		case "timeout", "err-client-outdated", "err-scan-without-multidevice":
			return fmt.Errorf("pareamento falhou: %s", evt.Event)
		}
	}
	return fmt.Errorf("pareamento terminou sem sucesso")
}

// variantes do numero: no Brasil muitas contas antigas nao tem o 9 depois do
// DDD (ou o numero foi digitado sem ele), entao tenta as duas formas.
func variantes(numero string) []string {
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

// resolver pergunta ao WhatsApp qual forma do numero esta registrada.
func resolver(ctx context.Context, cli *whatsmeow.Client, numero string) (string, error) {
	tentativas := variantes(numero)
	resp, err := cli.IsOnWhatsApp(ctx, tentativas)
	if err != nil {
		return "", fmt.Errorf("a consulta ao WhatsApp falhou: %w", err)
	}
	for _, r := range resp {
		if !r.IsIn {
			continue
		}
		if !r.PhoneNumber.IsEmpty() && r.PhoneNumber.User != "" {
			return r.PhoneNumber.User, nil
		}
		return r.JID.User, nil
	}
	return "", fmt.Errorf("o numero %s nao esta no WhatsApp (tentei: %s)",
		numero, strings.Join(tentativas, ", "))
}

// cuidar liga o audio da chamada e vigia o fim.
func cuidar(c *meowcaller.Call, segundos int, pcm string, fim chan<- struct{}) {
	inicio := time.Now()
	desde := func() int64 { return time.Since(inicio).Milliseconds() }
	id := strings.ReplaceAll(c.ID(), "/", "_")
	wav, errWav := meowcaller.WAVRecorder(fmt.Sprintf("chamada-%s.wav", id))
	var uma sync.Once
	terminar := func(motivo string) {
		uma.Do(func() {
			linha("FIM %s", motivo)
			linha("MEM %.0f", memoria())
			close(fim)
		})
	}
	if pcm != "" {
		conn, err := net.DialTimeout("tcp", pcm, 5*time.Second)
		if err != nil {
			linha("ERRO nao consegui falar com o Python em %s: %v", pcm, err)
			_ = c.Hangup()
			terminar("sem ponte de audio")
			return
		}
		var destino meowcaller.AudioSink = &destinoSocket{conn: conn}
		if errWav == nil {
			destino = duplo{a: wav, b: destino}
		}
		c.Receive(destino)
		c.Play(&fonteSocket{conn: conn})
	} else {
		if errWav == nil {
			c.Receive(wav)
		}
		c.Play(&tom{maximo: 50}) // 3 s
	}
	c.OnStateChange(func(p meowcaller.CallPhase) { linha("ESTADO %v %d", p, desde()) })
	c.OnReady(func() {
		linha("PRONTO %d", desde())
		linha("MEM %.0f", memoria())
		go func() {
			time.Sleep(time.Duration(segundos) * time.Second)
			_ = c.Hangup()
		}()
	})
	c.OnEnd(func(motivo string) { terminar(motivo) })
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println("uso: chamadas-teste parear|ouvir|ligar [opcoes]")
		os.Exit(2)
	}
	modo := os.Args[1]
	fl := flag.NewFlagSet(modo, flag.ExitOnError)
	telefone := fl.String("telefone", "", "numero com DDI, so digitos (parear)")
	para := fl.String("para", "", "numero com DDI, so digitos (ligar)")
	segundos := fl.Int("segundos", 45, "quanto tempo ficar na chamada")
	espera := fl.Int("espera", 90, "quanto esperar uma chamada (ouvir)")
	pcm := fl.String("pcm", "", "host:porta do Python para a voz (PCM s16le 16 kHz mono)")
	_ = fl.Parse(os.Args[2:])

	ctx, cancelar := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancelar()
	cli, err := abrir(ctx)
	if err != nil {
		linha("ERRO %v", err)
		os.Exit(1)
	}
	defer cli.Disconnect()

	switch modo {
	case "parear":
		if err := parear(ctx, cli, *telefone); err != nil {
			linha("ERRO %v", err)
			os.Exit(1)
		}
		time.Sleep(5 * time.Second) // deixa o aparelho terminar de sincronizar
		return
	case "ouvir", "ligar":
	default:
		linha("ERRO modo desconhecido: %s", modo)
		os.Exit(2)
	}

	if cli.Store.ID == nil {
		linha("ERRO ainda nao pareado: rode primeiro o modo parear")
		os.Exit(1)
	}
	log := zerolog.New(zerolog.ConsoleWriter{Out: os.Stderr}).Level(zerolog.InfoLevel)
	chamadas := meowcaller.NewClient(cli, meowcaller.WithLogger(log))
	fim := make(chan struct{})
	conectou := time.Now()
	cli.AddEventHandler(func(e any) {
		if _, ok := e.(*events.Connected); ok {
			linha("CONECTADO %d", time.Since(conectou).Milliseconds())
			linha("MEM %.0f", memoria())
		}
	})
	if err := cli.Connect(); err != nil {
		linha("ERRO ao conectar: %v", err)
		os.Exit(1)
	}

	limite := time.After(time.Duration(*espera+*segundos+30) * time.Second)
	if modo == "ouvir" {
		chamadas.OnIncomingCall(func(c *meowcaller.Call) {
			linha("RECEBIDA %s", c.Peer())
			cuidar(c, *segundos, *pcm, fim)
			if err := c.Answer(); err != nil {
				linha("ERRO ao atender: %v", err)
			}
		})
		linha("ESPERANDO")
		limite = time.After(time.Duration(*espera+*segundos+30) * time.Second)
	} else {
		if *para == "" {
			linha("ERRO informe -para")
			os.Exit(2)
		}
		time.Sleep(3 * time.Second) // espera a conexao firmar
		destino, err := resolver(ctx, cli, *para)
		if err != nil {
			linha("ERRO %v", err)
			os.Exit(1)
		}
		linha("RESOLVIDO %s", destino)
		c, err := chamadas.Call(ctx, destino)
		if err != nil {
			linha("ERRO ao ligar: %v", err)
			os.Exit(1)
		}
		cuidar(c, *segundos, *pcm, fim)
		linha("LIGANDO %s", *para)
	}
	select {
	case <-fim:
		time.Sleep(2 * time.Second)
	case <-limite:
		linha("FIM tempo esgotado")
	case <-ctx.Done():
	}
}

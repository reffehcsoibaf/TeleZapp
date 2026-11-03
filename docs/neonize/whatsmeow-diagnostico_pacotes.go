package whatsmeow

import (
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	waBinary "go.mau.fi/whatsmeow/binary"
)

// Diagnostico do TeleZapp, so com a variavel TELEZAPP_PACOTES apontando para um
// arquivo: uma linha por pacote recebido, com os tipos e os enderecos mascarados.
// Nunca o conteudo. Serve para ver o que chega durante um teste curto.
var (
	pacotesUmaVez sync.Once
	pacotesMu     sync.Mutex
	pacotesSaida  *os.File
)

func mascararEndereco(valor any) string {
	texto := fmt.Sprint(valor)
	usuario, servidor, tem := strings.Cut(texto, "@")
	if !tem {
		return "?"
	}
	if len(usuario) > 4 {
		usuario = usuario[len(usuario)-4:]
	}
	return "..." + usuario + "@" + servidor
}

func atributosDoPacote(node *waBinary.Node) string {
	var partes []string
	for _, nome := range []string{"type", "mediatype", "category", "edit", "offline", "v"} {
		if valor, tem := node.Attrs[nome]; tem {
			partes = append(partes, fmt.Sprintf("%s=%v", nome, valor))
		}
	}
	return strings.Join(partes, " ")
}

func registrarPacote(node *waBinary.Node) {
	pacotesUmaVez.Do(func() {
		if caminho := os.Getenv("TELEZAPP_PACOTES"); caminho != "" {
			pacotesSaida, _ = os.OpenFile(caminho, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o600)
		}
	})
	if pacotesSaida == nil {
		return
	}
	var filhos []string
	for _, filho := range node.GetChildren() {
		filhos = append(filhos, strings.TrimSpace(filho.Tag+" "+atributosDoPacote(&filho)))
	}
	linha := fmt.Sprintf("%s %s %s de=%s por=%s filhos=[%s]\n", time.Now().Format("15:04:05"),
		node.Tag, atributosDoPacote(node), mascararEndereco(node.Attrs["from"]),
		mascararEndereco(node.Attrs["participant"]), strings.Join(filhos, "; "))
	pacotesMu.Lock()
	defer pacotesMu.Unlock()
	_, _ = pacotesSaida.WriteString(linha)
}

package main

/*
#include <stdlib.h>
*/
import "C"

import (
	"context"
	"fmt"
	"strings"

	"go.mau.fi/whatsmeow"
	waBinary "go.mau.fi/whatsmeow/binary"
	"go.mau.fi/whatsmeow/proto/waCommon"
	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/types"
	"google.golang.org/protobuf/proto"
)

// Publica um status mencionando pessoas, em duas partes: o status vai para quem ja o ve e
// para as mencionadas, com <meta><mentioned_users> listando-as; depois cada uma recebe, na
// conversa privada, um statusMentionMessage com a chave do status. O formato nao esta na
// documentacao do WhatsApp: vem de clientes da comunidade (forks do Baileys).
// Resposta: "ok:<id>:<segundos>:<avisos que falharam>" ou "erro:<motivo>".

//export StatusComMencoes
func StatusComMencoes(id *C.char, mensagem *C.uchar, tamanho C.int, pessoas *C.char) *C.char {
	cli := clients[C.GoString(id)]
	if cli == nil {
		return C.CString("erro:client not found")
	}
	var msg waE2E.Message
	if err := proto.Unmarshal(getByteByAddr(mensagem, tamanho), &msg); err != nil {
		return C.CString("erro:" + err.Error())
	}
	ctx := context.Background()
	var mencionadas []types.JID
	var nos []waBinary.Node
	for _, texto := range strings.Split(C.GoString(pessoas), ",") {
		jid, err := types.ParseJID(strings.TrimSpace(texto))
		if err != nil || jid.IsEmpty() {
			continue
		}
		if jid.Server == types.HiddenUserServer {
			if pn, err := cli.Store.LIDs.GetPNForLID(ctx, jid); err == nil && !pn.IsEmpty() {
				jid = pn
			}
		}
		jid = jid.ToNonAD()
		mencionadas = append(mencionadas, jid)
		nos = append(nos, waBinary.Node{Tag: "to", Attrs: waBinary.Attrs{"jid": jid}})
	}
	if len(mencionadas) == 0 {
		return C.CString("erro:ninguem para mencionar")
	}
	meta := []waBinary.Node{{Tag: "meta", Content: []waBinary.Node{
		{Tag: "mentioned_users", Content: nos}}}}
	resp, err := cli.SendMessage(ctx, types.StatusBroadcastJID, &msg, whatsmeow.SendRequestExtra{
		AdditionalNodes: &meta, StatusRecipients: mencionadas})
	if err != nil {
		return C.CString("erro:" + err.Error())
	}
	falhas := 0
	for _, jid := range mencionadas {
		aviso := &waE2E.Message{StatusMentionMessage: &waE2E.FutureProofMessage{
			Message: &waE2E.Message{ProtocolMessage: &waE2E.ProtocolMessage{
				Key: &waCommon.MessageKey{
					RemoteJID: proto.String(types.StatusBroadcastJID.String()),
					FromMe:    proto.Bool(true),
					ID:        proto.String(resp.ID),
				},
				Type: waE2E.ProtocolMessage_STATUS_MENTION_MESSAGE.Enum(),
			}},
		}}
		marca := []waBinary.Node{{Tag: "meta", Attrs: waBinary.Attrs{"is_status_mention": "true"}}}
		if _, err := cli.SendMessage(ctx, jid, aviso, whatsmeow.SendRequestExtra{AdditionalNodes: &marca}); err != nil {
			cli.Log.Warnf("Falhou o aviso de mencao no status: %v", err)
			falhas++
		}
	}
	return C.CString(fmt.Sprintf("ok:%s:%d:%d", resp.ID, resp.Timestamp.Unix(), falhas))
}

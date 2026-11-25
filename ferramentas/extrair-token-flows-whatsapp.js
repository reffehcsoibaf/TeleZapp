// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Fábio Scheffer Moraes
//
// Script para COLAR no Console do navegador (F12) dentro do
// web.whatsapp.com, para obter sozinho o "token do aplicativo" que o
// TeleZapp pede na opção "Token do aplicativo para formulários que
// consultam a empresa" (Configurações, Experimental). O TeleZapp não
// chega a abrir o navegador nem a ler isso por você: é você quem roda,
// na sua própria sessão já logada, e só você vê o token.
//
// Como usar (veja docs/como-obter-token-formularios-whatsapp.md para o
// passo a passo completo):
//   1. Abra o web.whatsapp.com já logado.
//   2. Abra o Console do navegador (Ctrl+Shift+J no Chrome).
//   3. Cole este arquivo inteiro no campo do Console e aperte Enter.
//   4. Abra a conversa com uma empresa que manda formulário e clique no
//      botão dela (ex.: "Iniciar atendimento"). Não precisa preencher nada.
//   5. Um aviso (alert) diz quando o token foi copiado para a área de
//      transferência. Cole (Ctrl+V) na opção do TeleZapp.
//
// O script só olha o corpo das requisições que o próprio WhatsApp Web já
// manda; não manda nada a mais, não lê conversas nem preenche formulários.
(function () {
    if (window.__tzTokenHook) {
        alert("Já estava ativo nesta aba.");
        return;
    }
    window.__tzTokenHook = true;

    function achar(corpo) {
        try {
            var dados = typeof corpo === "string" ? JSON.parse(corpo) : corpo;
            if (dados && dados.access_token && dados.doc_id) {
                navigator.clipboard.writeText(dados.access_token).then(
                    function () {
                        alert("Token copiado! Cole (Ctrl+V) na opção "
                            + "\"Token do aplicativo para formulários que "
                            + "consultam a empresa\", em Configurações, "
                            + "Experimental, do TeleZapp.");
                    },
                    function () {
                        alert("Token encontrado, mas não consegui copiar "
                            + "para a área de transferência. Veja no "
                            + "console (aba Console): " + dados.access_token);
                    });
            }
        } catch (e) { /* corpo que nao e JSON do que procuramos: ignora */ }
    }

    var origFetch = window.fetch;
    window.fetch = function (url, opcoes) {
        if (opcoes && opcoes.body) achar(opcoes.body);
        return origFetch.apply(this, arguments);
    };

    var origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function (corpo) {
        if (corpo) achar(corpo);
        return origSend.apply(this, arguments);
    };

    alert("Script ativo. Agora abra a conversa com a empresa e clique no "
        + "botão do formulário (ex.: \"Iniciar atendimento\"). Quando o "
        + "token for encontrado, aparece outro aviso.");
})();

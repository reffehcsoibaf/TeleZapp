// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Contribuidores do TeleZapp
//
// Recebe os relatos do formulario da pagina do TeleZapp (site/relatar.html),
// guarda cada um no KV por 90 dias e deixa o responsavel le-los em /admin.
// Veja relatos/LEIAME.md para publicar.

const ORIGEM = "https://reffehcsoibaf.github.io";
const DIAS_GUARDADO = 90;
const LIMITE_LOG = 5 * 1024 * 1024;       // todos os logs juntos
const LIMITE_TEXTO = 8000;
const POR_DIA_E_POR_PESSOA = 8;
const TIPOS = { problema: "Problema", sugestao: "Sugestão", duvida: "Dúvida" };

function cors(extra = {}) {
  return {
    "Access-Control-Allow-Origin": ORIGEM,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Vary": "Origin",
    ...extra,
  };
}

function json(corpo, status = 200) {
  return new Response(JSON.stringify(corpo), {
    status,
    headers: cors({ "Content-Type": "application/json; charset=utf-8" }),
  });
}

function html(texto, status = 200) {
  return new Response(texto, {
    status,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Robots-Tag": "noindex",
    },
  });
}

function esc(t) {
  return String(t ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function resumo(texto) {
  const dados = new TextEncoder().encode(texto);
  const h = await crypto.subtle.digest("SHA-256", dados);
  return [...new Uint8Array(h)].slice(0, 8)
    .map((b) => b.toString(16).padStart(2, "0")).join("");
}

function igual(a, b) {
  if (!a || !b || a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (url.pathname === "/relato") return relato(req, env);
    if (url.pathname.startsWith("/admin")) return admin(req, env, url);
    return new Response("TeleZapp: recebimento de relatos.", { status: 200 });
  },
};

async function relato(req, env) {
  if (req.method === "OPTIONS") return new Response(null, { headers: cors() });
  if (req.method !== "POST") return json({ erro: "Use POST." }, 405);
  if (req.headers.get("Origin") !== ORIGEM) {
    return json({ erro: "Origem não permitida." }, 403);
  }
  let f;
  try {
    f = await req.formData();
  } catch {
    return json({ erro: "Não consegui ler o formulário." }, 400);
  }
  if (f.get("site")) return json({ ok: true });           // isca para robos

  // no maximo POR_DIA_E_POR_PESSOA relatos por dia por endereco de rede
  const ip = req.headers.get("CF-Connecting-IP") || "?";
  const dia = new Date().toISOString().slice(0, 10);
  const chaveLimite = "lim:" + dia + ":" + await resumo(ip + (env.SAL || ""));
  const n = parseInt((await env.RELATOS.get(chaveLimite)) || "0", 10);
  if (n >= POR_DIA_E_POR_PESSOA) {
    return json({ erro: "Muitos envios hoje. Tente amanhã." }, 429);
  }

  const tipo = TIPOS[f.get("tipo")] ? f.get("tipo") : "problema";
  const campo = (nome, max) => String(f.get(nome) || "").trim().slice(0, max);
  const relato = {
    tipo,
    nome: campo("nome", 200),
    contato: campo("contato", 300),
    descricao: campo("descricao", LIMITE_TEXTO),
    quando: campo("quando", 500),
    versao: campo("versao", 50),
    recebido: new Date().toISOString(),
    logs: [],
  };
  if (!relato.descricao) return json({ erro: "Escreva a descrição." }, 400);
  if (!relato.contato) {
    return json({ erro: "Informe uma forma de contato." }, 400);
  }

  let total = 0;
  for (const arq of f.getAll("log")) {
    if (typeof arq === "string" || !arq.size) continue;
    total += arq.size;
    if (total > LIMITE_LOG) {
      return json({ erro: "Os logs passam de 5 MB juntos. Mande só o telezapp.log." }, 413);
    }
    relato.logs.push({ nome: String(arq.name).slice(0, 100), texto: await arq.text() });
  }
  if (relato.logs.length && f.get("consentimento") !== "sim") {
    return json({ erro: "Marque a autorização para enviar os logs." }, 400);
  }

  const id = Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 7);
  await env.RELATOS.put("r:" + id, JSON.stringify(relato), {
    expirationTtl: DIAS_GUARDADO * 86400,
    metadata: {
      tipo, nome: relato.nome, contato: relato.contato,
      recebido: relato.recebido, logs: relato.logs.length,
      inicio: relato.descricao.slice(0, 120),
    },
  });
  await env.RELATOS.put(chaveLimite, String(n + 1), { expirationTtl: 2 * 86400 });
  await avisar(env, id, relato);
  return json({ ok: true, id });
}

// aviso opcional pelo Telegram (segredos TG_TOKEN e TG_CHAT)
async function avisar(env, id, r) {
  if (!env.TG_TOKEN || !env.TG_CHAT) return;
  try {
    const texto = "Novo relato no TeleZapp (" + TIPOS[r.tipo] + ")\n" +
      "De: " + (r.nome || "sem nome") + "\n" + r.descricao.slice(0, 300) +
      (r.logs.length ? "\n(com " + r.logs.length + " log)" : "") +
      "\n" + env.ENDERECO_ADMIN + "/admin/ver?id=" + id;
    await fetch("https://api.telegram.org/bot" + env.TG_TOKEN + "/sendMessage", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: env.TG_CHAT, text: texto }),
    });
  } catch { /* o aviso e um extra: o relato ja esta guardado */ }
}

async function admin(req, env, url) {
  const dado = url.searchParams.get("t") || "";
  if (!igual(dado, env.ADMIN_TOKEN || "")) {
    return html("<p>Acesso negado.</p>", 403);
  }
  const t = encodeURIComponent(dado);
  if (url.pathname === "/admin" || url.pathname === "/admin/") {
    const lista = await env.RELATOS.list({ prefix: "r:" });
    const itens = lista.keys.sort((a, b) => (b.name > a.name ? 1 : -1)).map((k) => {
      const m = k.metadata || {};
      return `<li><a href="/admin/ver?id=${esc(k.name.slice(2))}&t=${t}">` +
        `${esc(m.recebido || "")} ${esc(TIPOS[m.tipo] || "")}, ${esc(m.nome || "sem nome")}</a>` +
        `${m.logs ? " (com log)" : ""}: ${esc(m.inicio || "")}</li>`;
    });
    return html(`<!doctype html><meta charset="utf-8"><title>Relatos do TeleZapp</title>` +
      `<h1>Relatos do TeleZapp</h1><ul>${itens.join("") || "<li>Nenhum relato.</li>"}</ul>`);
  }
  const id = url.searchParams.get("id") || "";
  const bruto = await env.RELATOS.get("r:" + id);
  if (!bruto) return html("<p>Relato não encontrado (ou já apagado).</p>", 404);
  const r = JSON.parse(bruto);
  if (url.pathname === "/admin/log") {
    const i = parseInt(url.searchParams.get("n") || "0", 10);
    const log = r.logs[i];
    if (!log) return html("<p>Log não encontrado.</p>", 404);
    return new Response(log.texto, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Disposition": `attachment; filename="${log.nome.replace(/[^\w.-]/g, "_")}"`,
        "Cache-Control": "no-store",
      },
    });
  }
  const logs = r.logs.map((l, i) =>
    `<li><a href="/admin/log?id=${esc(id)}&n=${i}&t=${t}">${esc(l.nome)}</a> ` +
    `(${Math.round(l.texto.length / 1024)} KB)</li>`).join("");
  return html(`<!doctype html><meta charset="utf-8"><title>Relato</title>` +
    `<p><a href="/admin?t=${t}">Voltar à lista</a></p>` +
    `<h1>${esc(TIPOS[r.tipo])}</h1><dl>` +
    `<dt>Recebido</dt><dd>${esc(r.recebido)}</dd>` +
    `<dt>Nome</dt><dd>${esc(r.nome)}</dd>` +
    `<dt>Contato</dt><dd>${esc(r.contato)}</dd>` +
    `<dt>Versão do TeleZapp</dt><dd>${esc(r.versao)}</dd>` +
    `<dt>Quando aconteceu</dt><dd>${esc(r.quando)}</dd>` +
    `<dt>Descrição</dt><dd style="white-space:pre-wrap">${esc(r.descricao)}</dd>` +
    `<dt>Logs</dt><dd><ul>${logs || "<li>Nenhum.</li>"}</ul></dd></dl>`);
}

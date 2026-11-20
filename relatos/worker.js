// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Fábio Scheffer Moraes
//
// Recebe os relatos
// da janela de Feedback do programa (telezapp/nucleo/relatos.py), guarda cada um no KV por 90 dias e deixa o responsavel le-los em /admin.
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

// o que abre um relato pelo link do aviso, sem revelar a senha do /admin
function assinatura(env, id) {
  return env.ADMIN_TOKEN ? resumo("relato:" + id + ":" + env.ADMIN_TOKEN) : "";
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (url.pathname === "/relato") return relato(req, env);
    if (url.pathname === "/uso") return uso(req, env);
    if (url.pathname.startsWith("/admin")) return admin(req, env, url);
    return new Response("TeleZapp: recebimento de relatos.", { status: 200 });
  },
};

async function relato(req, env) {
  if (req.method === "OPTIONS") return new Response(null, { headers: cors() });
  if (req.method !== "POST") return json({ erro: "Use POST." }, 405);
  // o programa (Ajuda, Feedback) nao e um navegador: vem sem Origin. Isso nao
  // e uma senha; quem barra abuso e o limite por dia
  const origem = req.headers.get("Origin");
  const doPrograma = !origem &&
    (req.headers.get("User-Agent") || "").startsWith("TeleZapp/");
  if (origem !== ORIGEM && !doPrograma) {
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

// aviso opcional por um bot do Telegram (segredos TG_TOKEN e TG_CHAT). O ntfy.sh
// gratis foi abandonado: recusava os Workers por cota diaria (HTTP 429).
async function avisar(env, id, r) {
  if (!env.TG_TOKEN || !env.TG_CHAT) return;
  try {
    const texto = "Novo relato no TeleZapp (" + TIPOS[r.tipo] + ")\n" +
      "De: " + (r.nome || "sem nome") + "\n" + r.descricao.slice(0, 300) +
      (r.logs.length ? "\n(com " + r.logs.length + " log)" : "") +
      "\n" + env.ENDERECO_ADMIN + "/admin/ver?id=" + id +
      "&a=" + await assinatura(env, id);
    const resposta = await fetch("https://api.telegram.org/bot" + env.TG_TOKEN + "/sendMessage", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // sem previa: o Telegram nao precisa visitar o link
      body: JSON.stringify({
        chat_id: env.TG_CHAT, text: texto,
        link_preview_options: { is_disabled: true },
      }),
    });
    if (!resposta.ok) console.log("Telegram recusou: HTTP " + resposta.status);
  } catch (e) {
    // o aviso e um extra: o relato ja esta guardado
    console.log("Telegram falhou: " + e.name);
  }
}

// ---- uso do programa (opcional, so numeros) ---------------------------------
// O programa (telezapp/nucleo/uso.py) manda no maximo um resumo por dia, so de
// quem marcou "Compartilhar informacoes de uso". Aqui o resumo e reconstruido
// campo a campo (o que nao estiver na lista e descartado), nunca guardado como
// veio. Nao ha texto livre: so versoes, contagens, tempos e nomes de recursos.
const DIAS_USO = 180;
const POR_DIA_E_POR_REDE_USO = 30;

function numero(v, max) {
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 && n <= max ? Math.round(n * 1000) / 1000 : 0;
}

function mapa(obj, maxChaves, valor) {
  const saida = {};
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return saida;
  for (const [k, v] of Object.entries(obj).slice(0, maxChaves)) {
    if (!/^[a-zA-Z0-9_]{1,60}$/.test(k)) continue;
    saida[k] = valor(v);
  }
  return saida;
}

function limparUso(b) {
  if (!b || typeof b !== "object") return null;
  if (!/^\d{4}\.\d{1,2}\.\d{1,2}\.\d{1,2}$/.test(String(b.versao || ""))) return null;
  if (!/^[0-9a-f]{32}$/.test(String(b.id || ""))) return null;
  const texto = (v, max) => String(v ?? "").replace(/[^\w .,+()\-]/g, "").slice(0, max);
  // uma chamada: so categorias e numeros (telezapp/nucleo/uso_chamadas.py)
  const chamada = (c) => {
    c = c && typeof c === "object" ? c : {};
    return {
      servico: texto(c.servico, 12), direcao: texto(c.direcao, 8),
      tipo: texto(c.tipo, 8), grupo: c.grupo === true, link: c.link === true,
      resultado: texto(c.resultado, 20), rx: texto(c.rx, 20), tx: texto(c.tx, 20),
      pessoas: texto(c.pessoas, 20), plataforma: texto(c.plataforma, 12),
      versao_wa: texto(c.versao_wa, 20), classe: numero(c.classe, 99999),
      itens_da_oferta: numero(c.itens_da_oferta, 100), codec: texto(c.codec, 20),
      relays: numero(c.relays, 50), relay_tentativa: numero(c.relay_tentativa, 50),
      relay_posicao_rtt: numero(c.relay_posicao_rtt, 50),
      relay_fna: c.relay_fna === true, relay_heuristica: c.relay_heuristica === true,
      t_toque_s: numero(c.t_toque_s, 36000),
      t_som_apos_atender_s: numero(c.t_som_apos_atender_s, 36000),
      dur_s: numero(c.dur_s, 36000), motivo_dll: texto(c.motivo_dll, 30),
    };
  };
  return {
    chamadas: (Array.isArray(b.chamadas) ? b.chamadas : []).slice(0, 10).map(chamada),
    versao: String(b.versao),
    id: String(b.id),
    sistema: texto(b.sistema, 60),
    empacotado: b.empacotado === true,
    leitor: texto(b.leitor, 12),
    contas: mapa(b.contas, 4, (v) => numero(v, 1000)),
    conversas: texto(b.conversas, 20),
    experimentais: (Array.isArray(b.experimentais) ? b.experimentais : [])
      .map((x) => String(x))
      .filter((x) => /^[a-z0-9_]{1,60}$/.test(x)).slice(0, 40),
    abertura_s: numero(b.abertura_s, 3600),
    tempos: mapa(b.tempos, 20, (v) => numero(v, 3600)),
    lentos: mapa(b.lentos, 40, (v) => ({
      n: numero(v && v.n, 1e6), max_s: numero(v && v.max_s, 3600) })),
    erros: mapa(b.erros, 40, (v) => numero(v, 1e6)),
    ambiente: {
      python: texto(b.ambiente && b.ambiente.python, 12),
      arquitetura: texto(b.ambiente && b.ambiente.arquitetura, 12),
      cpus: numero(b.ambiente && b.ambiente.cpus, 1024),
      wx: texto(b.ambiente && b.ambiente.wx, 12),
      neonize: texto(b.ambiente && b.ambiente.neonize, 12),
      telethon: texto(b.ambiente && b.ambiente.telethon, 12),
    },
    quedas: mapa(b.quedas, 8, (v) => numero(v, 1e6)),
    causas_de_queda: mapa(b.causas_de_queda, 8, (v) => numero(v, 1e6)),
    registro: mapa(b.registro, 40, (v) => numero(v, 1e7)),
    banco: {
      estado: texto(b.banco && b.banco.estado, 20),
      s: numero(b.banco && b.banco.s, 3600),
      tamanho: texto(b.banco && b.banco.tamanho, 20),
    },
    disco: texto(b.disco, 20),
    fechou_sem_fechar: b.fechou_sem_fechar === true,
  };
}

async function uso(req, env) {
  if (req.method !== "POST") return json({ erro: "Use POST." }, 405);
  // so o programa (como no /relato); isso nao e senha, quem barra abuso e o
  // limite por dia e a reconstrucao dos campos
  if (req.headers.get("Origin") ||
      !(req.headers.get("User-Agent") || "").startsWith("TeleZapp/")) {
    return json({ erro: "Origem não permitida." }, 403);
  }
  const bruto = await req.text();
  if (bruto.length > 16000) return json({ erro: "Grande demais." }, 413);
  let corpo;
  try { corpo = JSON.parse(bruto); } catch { return json({ erro: "JSON inválido." }, 400); }
  const dados = limparUso(corpo);
  if (!dados) return json({ erro: "Formato inválido." }, 400);

  const ip = req.headers.get("CF-Connecting-IP") || "?";
  const dia = new Date().toISOString().slice(0, 10);
  const chaveLimite = "lim-uso:" + dia + ":" + await resumo(ip + (env.SAL || ""));
  const n = parseInt((await env.RELATOS.get(chaveLimite)) || "0", 10);
  if (n >= POR_DIA_E_POR_REDE_USO) return json({ erro: "Muitos envios hoje." }, 429);
  await env.RELATOS.put(chaveLimite, String(n + 1), { expirationTtl: 2 * 86400 });

  // um resumo por aparelho por dia: reenviar no mesmo dia substitui
  dados.dia = dia;
  await env.RELATOS.put("u:" + dia + ":" + dados.id, JSON.stringify(dados), {
    expirationTtl: DIAS_USO * 86400,
  });
  return json({ ok: true });
}

function mediana(v) {
  const o = [...v].sort((a, b) => a - b);
  return o.length ? o[Math.floor(o.length / 2)] : 0;
}

// chamadas: cruza os campos de todos os registros (cada resumo traz ate 10,
// com as que tiveram problema na frente: nao e a taxa real de falha)
function secaoChamadas(registros) {
  const todas = registros.flatMap((r) => (r.chamadas || []).map((c) => ({ ...c, _id: r.id })));
  if (!todas.length) return "<h2>Chamadas</h2><p>Nenhuma.</p>";
  const cruzar = (titulo, f) => {
    const c = {};
    for (const x of todas) {
      const k = f(x);
      (c[k] ||= { n: 0, aparelhos: new Set() });
      c[k].n++; c[k].aparelhos.add(x._id);
    }
    return `<h3>${esc(titulo)}</h3><ul>` + Object.entries(c).sort((a, b) => b[1].n - a[1].n)
      .map(([k, v]) => `<li>${esc(k)}: ${v.n} (${v.aparelhos.size} aparelhos)</li>`).join("") + "</ul>";
  };
  const som = {};
  for (const x of todas) if (x.t_som_apos_atender_s !== undefined && x.t_toque_s !== undefined) (som[x.plataforma || "?"] ||= []).push(x.t_som_apos_atender_s);
  const linhasSom = Object.entries(som).map(([p, v]) =>
    `<li>${esc(p)}: mediana ${mediana(v)} s, máximo ${Math.max(...v)} s (${v.length} chamadas)</li>`).join("");
  return `<h2>Chamadas (${todas.length} registros)</h2>` +
    `<p>Cada aparelho manda até 10 por dia, com as que tiveram problema na frente: use para comparar grupos, não como taxa de falha.</p>` +
    cruzar("Resultado", (x) => x.resultado) +
    cruzar("Tipo e direção × resultado", (x) => `${x.servico} ${x.direcao} ${x.tipo}${x.grupo ? " grupo" : ""}${x.link ? " link" : ""} → ${x.resultado}`) +
    cruzar("Quem liga (plataforma) × resultado, nas recebidas", (x) => x.direcao === "entrada" ? `${x.plataforma || "?"} → ${x.resultado}` : "(saída)") +
    cruzar("Versão do WhatsApp de quem liga × resultado", (x) => x.versao_wa ? `${x.plataforma} ${x.versao_wa} → ${x.resultado}` : "(sem versão)") +
    cruzar("Classe do aparelho × resultado", (x) => x.classe ? `${x.classe} → ${x.resultado}` : "(sem classe)") +
    cruzar("Codec × resultado", (x) => x.codec ? `${x.codec} → ${x.resultado}` : "(sem codec)") +
    cruzar("Grupo: pessoas × resultado", (x) => x.grupo ? `${x.pessoas} → ${x.resultado}` : "(não é grupo)") +
    cruzar("Tentativa de relay que funcionou", (x) => x.relay_tentativa ? `tentativa ${x.relay_tentativa} de ${x.relays}` : "(sem tentativas)") +
    cruzar("Posição do relay escolhido por RTT", (x) => x.relay_posicao_rtt ? `${x.relay_posicao_rtt}º de ${x.relays}${x.relay_heuristica ? " (regra sem FNA)" : ""}` : "(sem dado)") +
    `<h3>Tempo entre atender e o som do outro lado chegar, por plataforma</h3><ul>${linhasSom || "<li>Nada.</li>"}</ul>`;
}

async function adminUso(env, t) {
  const dias = parseInt(t.dias, 10) || 14;
  const desde = new Date(Date.now() - dias * 86400000).toISOString().slice(0, 10);
  const registros = [];
  let cursor;
  let cortado = false;
  // o plano gratis limita as operacoes por pedido: le no maximo MAX_LIDOS
  // resumos (os mais novos primeiro, pois a chave comeca pela data)
  const MAX_LIDOS = 40;
  const nomes = [];
  do {
    const lista = await env.RELATOS.list({ prefix: "u:", cursor });
    for (const k of lista.keys) if (k.name.slice(2, 12) >= desde) nomes.push(k.name);
    cursor = lista.list_complete ? undefined : lista.cursor;
  } while (cursor);
  nomes.sort().reverse();
  if (nomes.length > MAX_LIDOS) cortado = true;
  for (const nome of nomes.slice(0, MAX_LIDOS)) {
    const v = await env.RELATOS.get(nome);
    if (v) registros.push(JSON.parse(v));
  }
  const aparelhos = new Set(registros.map((r) => r.id));
  const por = (campo) => {
    const c = {};
    for (const r of registros) c[r[campo]] = (c[r[campo]] || 0) + 1;
    return Object.entries(c).sort((a, b) => b[1] - a[1]);
  };
  const lista = (pares) => "<ul>" + pares.map(([k, v]) =>
    `<li>${esc(k)}: ${esc(v)}</li>`).join("") + "</ul>";
  const lentos = {};
  const tempos = {};
  const experimentais = {};
  const quedas = {};
  const causas = {};
  const registro = {};
  const quedasDoPrograma = new Set();
  const bancosRuins = new Set();
  for (const r of registros) {
    for (const [nome, v] of Object.entries(r.lentos || {})) {
      (lentos[nome] ||= { n: 0, maximos: [], aparelhos: new Set() });
      lentos[nome].n += v.n; lentos[nome].maximos.push(v.max_s); lentos[nome].aparelhos.add(r.id);
    }
    for (const [nome, v] of Object.entries(r.tempos || {})) (tempos[nome] ||= []).push(v);
    if (r.abertura_s) (tempos.abertura ||= []).push(r.abertura_s);
    for (const x of r.experimentais || []) experimentais[x] = (experimentais[x] || 0) + 1;
    for (const [g, alvo] of [["quedas", quedas], ["causas_de_queda", causas], ["registro", registro]]) {
      for (const [nome, v] of Object.entries(r[g] || {})) {
        (alvo[nome] ||= { n: 0, aparelhos: new Set() });
        alvo[nome].n += v; alvo[nome].aparelhos.add(r.id);
      }
    }
    if (r.fechou_sem_fechar) quedasDoPrograma.add(r.id);
    if (r.banco && r.banco.estado && r.banco.estado !== "ok") bancosRuins.add(r.id);
  }
  const linhasContagem = (o) => Object.entries(o).sort((a, b) => b[1].n - a[1].n).map(([nome, v]) =>
    `<li>${esc(nome)}: ${v.n} em ${v.aparelhos.size} aparelhos</li>`).join("") || "<li>Nada.</li>";
  const porSub = (campo, sub) => {
    const c = {};
    for (const r of registros) { const k = (r[campo] && r[campo][sub]) || "?"; c[k] = (c[k] || 0) + 1; }
    return Object.entries(c).sort((a, b) => b[1] - a[1]);
  };
  const linhasLentos = Object.entries(lentos).sort((a, b) => b[1].n - a[1].n).map(([nome, v]) =>
    `<li>${esc(nome)}: ${v.n} vezes em ${v.aparelhos.size} aparelhos; pior tempo mediano ${mediana(v.maximos)} s, máximo ${Math.max(...v.maximos)} s</li>`);
  const linhasTempos = Object.entries(tempos).map(([nome, v]) =>
    `<li>${esc(nome)}: mediana ${mediana(v)} s, máximo ${Math.max(...v)} s (${v.length} envios)</li>`);
  return html(`<!doctype html><meta charset="utf-8"><title>Uso do TeleZapp</title>` +
    `<h1>Uso do TeleZapp, últimos ${dias} dias</h1>` +
    `<p>${aparelhos.size} aparelhos, ${registros.length} resumos.` +
    `${cortado ? " Só os " + MAX_LIDOS + " mais novos (de " + nomes.length + ")." : ""}</p>` +
    `<h2>Versões</h2>${lista(por("versao"))}` +
    `<h2>Sistemas</h2>${lista(por("sistema"))}` +
    `<h2>Leitores de tela</h2>${lista(por("leitor"))}` +
    `<h2>Quantidade de conversas</h2>${lista(por("conversas"))}` +
    `<h2>Tempos</h2><ul>${linhasTempos.join("") || "<li>Nada.</li>"}</ul>` +
    `<h2>Tratadores lentos (acima de 0,2 s)</h2><ul>${linhasLentos.join("") || "<li>Nada.</li>"}</ul>` +
    `<h2>Recursos experimentais ligados</h2>${lista(Object.entries(experimentais).sort((a, b) => b[1] - a[1]))}` +
    `<h2>Quedas de conexão, por serviço</h2><ul>${linhasContagem(quedas)}</ul>` +
    `<h2>Causa das quedas do WhatsApp</h2><ul>${linhasContagem(causas)}</ul>` +
    `<h2>Avisos e erros do registro, por módulo</h2><ul>${linhasContagem(registro)}</ul>` +
    `<h2>Programa fechado sem terminar na vez anterior</h2><p>${quedasDoPrograma.size} aparelhos.</p>` +
    `<h2>Banco ao abrir</h2>${lista(porSub("banco", "estado"))}` +
    `<p>${bancosRuins.size} aparelhos com banco que não estava ok.</p>` +
    `<h2>Tamanho do banco</h2>${lista(porSub("banco", "tamanho"))}` +
    `<h2>Disco dos dados</h2>${lista(por("disco"))}` +
    `<h2>Python</h2>${lista(porSub("ambiente", "python"))}` +
    `<h2>neonize</h2>${lista(porSub("ambiente", "neonize"))}` +
    `<h2>wxPython</h2>${lista(porSub("ambiente", "wx"))}` +
    `<h2>Processador</h2>${lista(porSub("ambiente", "arquitetura"))}` +
    secaoChamadas(registros));
}

async function admin(req, env, url) {
  const dado = url.searchParams.get("t") || "";
  const comSenha = igual(dado, env.ADMIN_TOKEN || "");
  // o link do aviso abre so aquele relato e os logs dele, nunca a lista
  const dadoA = url.searchParams.get("a") || "";
  const idPedido = url.searchParams.get("id") || "";
  const assinado = !comSenha && idPedido &&
    (url.pathname === "/admin/ver" || url.pathname === "/admin/log") &&
    igual(dadoA, await assinatura(env, idPedido));
  if (!comSenha && !assinado) {
    return html("<p>Acesso negado.</p>", 403);
  }
  const t = encodeURIComponent(dado);
  const acesso = comSenha ? "t=" + t : "a=" + encodeURIComponent(dadoA);
  if (url.pathname === "/admin/uso") {
    if (!comSenha) return html("<p>Acesso negado.</p>", 403);
    return adminUso(env, { dias: url.searchParams.get("dias") });
  }
  if (url.pathname === "/admin" || url.pathname === "/admin/") {
    const lista = await env.RELATOS.list({ prefix: "r:" });
    const itens = lista.keys.sort((a, b) => (b.name > a.name ? 1 : -1)).map((k) => {
      const m = k.metadata || {};
      return `<li><a href="/admin/ver?id=${esc(k.name.slice(2))}&t=${t}">` +
        `${esc(m.recebido || "")} ${esc(TIPOS[m.tipo] || "")}, ${esc(m.nome || "sem nome")}</a>` +
        `${m.logs ? " (com log)" : ""}: ${esc(m.inicio || "")}</li>`;
    });
    return html(`<!doctype html><meta charset="utf-8"><title>Relatos do TeleZapp</title>` +
      `<h1>Relatos do TeleZapp</h1><p><a href="/admin/uso?${acesso}">Uso do programa</a></p><ul>${itens.join("") || "<li>Nenhum relato.</li>"}</ul>`);
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
    `<li><a href="/admin/log?id=${esc(id)}&n=${i}&${acesso}">${esc(l.nome)}</a> ` +
    `(${Math.round(l.texto.length / 1024)} KB)</li>`).join("");
  return html(`<!doctype html><meta charset="utf-8"><title>Relato</title>` +
    (comSenha ? `<p><a href="/admin?t=${t}">Voltar à lista</a></p>` : "") +
    `<h1>${esc(TIPOS[r.tipo])}</h1><dl>` +
    `<dt>Recebido</dt><dd>${esc(r.recebido)}</dd>` +
    `<dt>Nome</dt><dd>${esc(r.nome)}</dd>` +
    `<dt>Contato</dt><dd>${esc(r.contato)}</dd>` +
    `<dt>Versão do TeleZapp</dt><dd>${esc(r.versao)}</dd>` +
    `<dt>Quando aconteceu</dt><dd>${esc(r.quando)}</dd>` +
    `<dt>Descrição</dt><dd style="white-space:pre-wrap">${esc(r.descricao)}</dd>` +
    `<dt>Logs</dt><dd><ul>${logs || "<li>Nenhum.</li>"}</ul></dd></dl>`);
}

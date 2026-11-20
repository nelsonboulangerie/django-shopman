import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { galleryQueue } from "./galleryCards.mjs";

// Backend hermético da matriz visual do Gestor. Sem Django, sem dados vivos:
// as fixtures abaixo foram CAPTURADAS do backend real (seed Nelson) e o mock só
// reescreve os campos de relógio para o painel não nascer "desatualizado".
// O estado é trocado por GET /__visual/scenario?set=<normal|empty|dense|error|gallery>.

const here = dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.MOCK_PORT || 28793);
const readFixture = (name) => JSON.parse(readFileSync(join(here, "fixtures", name), "utf8"));

const baseQueue = readFixture("orders-board.json");
const baseAlerts = readFixture("alerts.json");
const baseAttention = readFixture("channel-attention.json");
const baseRailCounts = readFixture("rail-counts.json");
// Respostas GET gravadas do Django real (seed Nelson, sintético) para as telas que a
// galeria não cobre: Ajustes, Histórico, Catálogo, Canais, Clientes, Postos e o detalhe
// do pedido. Casa pelo caminho com a query e, sem ela, só pelo caminho.
const recorded = readFixture("recorded-django.json");
function recordedFor(url) {
  const exact = recorded[url.pathname + url.search];
  if (exact) return exact;
  const key = Object.keys(recorded).find((k) => k.split("?")[0] === url.pathname);
  return key ? recorded[key] : null;
}
function catalogPayload(url) {
  const source = recordedFor(url);
  if (!source) return null;
  const body = JSON.parse(JSON.stringify(source));
  body.matrix.order = url.searchParams.get("order") || "name";
  body.matrix.date_from = url.searchParams.get("date_from") || "";
  body.matrix.date_to = url.searchParams.get("date_to") || "";
  if (scenario === "validity") {
    for (const row of body.matrix.rows) for (const cell of row.cells) {
      if (cell.in_listing) {
        cell.valid_from = "2026-10-20";
        cell.valid_until = "2026-10-22";
      }
    }
  }
  if (url.searchParams.get("archived") === "true") {
    const archived = body.matrix?.rows?.slice(0, 1) || [];
    for (const row of archived) row.is_active = false;
    body.matrix.rows = archived;
    body.matrix.total = archived.length;
    body.matrix.has_next = false;
  }
  return body;
}
// Tabelão de produtos: as linhas do catálogo gravado com uma classificação fiscal
// de exemplo (as revisões são fictícias; o mock não grava).
function productSheetPayload() {
  const rows = recordedFor(new URL("http://mock/api/v1/backstage/catalog/?collection"))?.matrix?.rows || [];
  return {
    rows: rows.map((row, index) => ({
      sku: row.sku,
      is_active: row.is_active,
      name: row.name,
      short_description: index % 3 ? "" : "Massa de fermentação natural, casca crocante.",
      base_price_q: row.base_price_q,
      unit: index === 2 ? "kg" : "un",
      fiscal: index === 1
        ? { profile: "", ncm: "", cest: "", origin: "0" }
        : { profile: "standard", ncm: "19059090", cest: "", origin: "0" },
      fiscal_warnings: [],
      revisions: {},
    })),
    fiscal_profiles: [
      { key: "standard", name: "Sem substituição tributária", requires_cest: false },
      { key: "tax_substitution", name: "Com substituição tributária (ST)", requires_cest: true },
    ],
    fiscal_origins: [
      { key: "0", name: "0 · Nacional" },
      { key: "1", name: "1 · Estrangeira, importação direta" },
    ],
  };
}
// Detalhe de produto do Catálogo: o payload real do backend de teste (produto "Pão"),
// com SKU e nome do produto pedido. A foto "padronizada" volta igual e "guardada"
// devolve uma URL fixa: o mock não processa imagem.
const productDetailTemplate = readFixture("catalog-product-detail.json");
function productDetailPayload(sku) {
  const row = recordedFor(new URL("http://mock/api/v1/backstage/catalog/?collection"))?.matrix?.rows?.find((item) => item.sku === sku);
  const body = JSON.parse(JSON.stringify(productDetailTemplate));
  body.product = { ...body.product, sku, name: row?.name || body.product.name, image_url: row?.image_url || "" };
  return body;
}
const detailTemplate = recorded["/api/v1/backstage/orders/IFOOD-261006-W01/"];
/** O detalhe de um pedido da galeria: o detalhe real gravado, com os dados do card. */
function galleryDetail(ref) {
  const card = [].concat(...Object.values(queuePayload().queue).filter(Array.isArray)).find((c) => c && c.ref === ref);
  if (!card || !detailTemplate) return null;
  const body = JSON.parse(JSON.stringify(detailTemplate));
  body.order = { ...body.order, ...card, ref, items: body.order.items, timeline: body.order.timeline };
  return body;
}

let scenario = "normal";
// Conferência das sacolas (MOCK_VOLUMES=1): o G96 (pronto, retirada) com 3 sacolas
// declaradas, e a bipada do leitor respondida como o servidor responde. Fora da
// flag, o painel não muda.
const VOLUMES = process.env.MOCK_VOLUMES === "1";
const DECLARED = VOLUMES ? { "PDV-261006-G96": 3, "WEB-261006-W29": 2 } : {};
const checkedBags = new Map();
function volumeCheck(body) {
  const match = String(body.code || "").toUpperCase().match(/^VP-(.+)-(\d{1,2})-(\d{1,2})-[A-Z2-7]{8}$/);
  if (!match) return { outcome: "unknown", message: "Este código não é de uma Via Pedido desta loja." };
  const [, ref, k, n] = match;
  const expected = String(body.expected_ref || "").toUpperCase();
  const total = DECLARED[ref] || 1;
  const base = { order_ref: ref, expected_ref: expected, volume: Number(k), volumes: Number(n) };
  if (expected && expected !== ref) return { ...base, outcome: "other_order", message: "", checked: 0, total: 0, complete: false };
  const done = checkedBags.get(ref) || new Set();
  const repeated = done.has(Number(k));
  done.add(Number(k));
  checkedBags.set(ref, done);
  return { ...base, outcome: repeated ? "repeated" : "checked", message: "", checked: done.size, total, complete: done.size >= total };
}
function withVolumes(card) {
  if (!card || typeof card !== "object" || !(card.ref in DECLARED)) return card;
  const done = checkedBags.get(card.ref);
  return { ...card, volumes: DECLARED[card.ref], volumes_checked: done ? done.size : 0, volumes_to_check: DECLARED[card.ref] };
}
const LOCK_PEOPLE = [
  { id: 1, username: "ana", name: "Ana Paula" },
  { id: 2, username: "bruno", name: "Bruno" },
  { id: 3, username: "carla", name: "Carla Mendes" },
  { id: 4, username: "diego", name: "Diego" },
  { id: 5, username: "elaine", name: "Elaine Cristina Souza" },
];
// "Visto" do aviso com prazo no cenário gallery: o mock lembra quem já viu.
const acknowledged = new Set();

function urgentAlert() {
  const pk = 900;
  const respondBy = new Date(Date.now() + 7 * 60_000).toISOString();
  const actions = [{
    ref: `open-context:${pk}`, kind: "open_alert_context", label: "Responder", priority: 10,
    enabled: true, reason: "", method: "GET", href: "/WEB-261007-I15#ifood-negotiations",
    payload_schema: "", expected_rev: null, idempotency: { required: false, key_scope: "" },
    confirmation: { required: false, reason_required: false, title: "", confirm_label: "Abrir" },
    approval_requirement: null, source_alert_ref: String(pk), source_alert_effect: "keeps_open", proof: "",
  }];
  if (!acknowledged.has(pk)) actions.push({
    ref: `acknowledge:${pk}`, kind: "acknowledge_alert", label: "Visto", priority: 20, enabled: true,
    reason: "", method: "POST", href: `/api/v1/backstage/alerts/${pk}/ack/`,
    payload_schema: "AlertAckMutationRequest", expected_rev: 0,
    idempotency: { required: true, key_scope: `backstage.alert-ack:${pk}` },
    confirmation: { required: false, reason_required: false, title: "", confirm_label: "Confirmar" },
    approval_requirement: null, source_alert_ref: String(pk), source_alert_effect: "acknowledges", proof: "",
  });
  return {
    pk, rev: 0, type: "ifood_negotiation_open", type_label: "iFood: negociação esperando resposta",
    severity: "error", severity_label: "Erro", audience: "orders",
    message: "Pedido I15 · sem resposta, o iFood cancela.",
    deadline_kind: "external", origin_label: "iFood", origin_icon: "i-lucide-bike",
    subject: "Cliente pediu cancelamento",
    order_ref: "WEB-261007-I15", created_at_display: "agora", respond_by_iso: respondBy, actions,
  };
}

// O "vou verificar" da Concierge (WP-07): a pergunta que ela levou à equipe. O cartão
// nasce com o prazo prometido ao cliente e chega como aviso de tela no topo; em
// `concierge-late`, a promessa já venceu e a janela interrompe a tela.
const verification = { answered: false, takenOver: false, promoted: false, answerText: "" };
// A hora como a casa escreve ("16h12", "9h"), no fuso da loja.
function clock(date) {
  const parts = new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo", hour: "numeric", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(date);
  const hour = parts.find((p) => p.type === "hour").value;
  const minute = parts.find((p) => p.type === "minute").value;
  return minute === "00" ? `${Number(hour)}h` : `${Number(hour)}h${minute}`;
}

function verificationAlert(late) {
  const pk = 950;
  const base = `/api/v1/backstage/alerts/${pk}/concierge-verification`;
  const gesture = (kind, label, priority, path, schema) => ({
    ref: `${kind}:${pk}`, kind, label, priority, enabled: true, reason: "", method: "POST",
    href: `${base}/${path}/`, payload_schema: schema, expected_rev: null,
    idempotency: { required: false, key_scope: "" },
    confirmation: { required: false, reason_required: false, title: "", confirm_label: label },
    approval_requirement: null, source_alert_ref: String(pk), source_alert_effect: "resolves", proof: "",
  });
  const actions = [
    gesture("answer_concierge_verification", "Responder ao cliente", 1, "answer", "ConciergeVerificationAnswerRequest"),
    gesture("take_over_conversation", "Assumir a conversa", 2, "take-over", ""),
  ];
  if (!acknowledged.has(pk)) actions.push({
    ref: `acknowledge:${pk}`, kind: "acknowledge_alert", label: "Visto", priority: 20, enabled: true,
    reason: "", method: "POST", href: `/api/v1/backstage/alerts/${pk}/ack/`,
    payload_schema: "AlertAckMutationRequest", expected_rev: 0,
    idempotency: { required: true, key_scope: `backstage.alert-ack:${pk}` },
    confirmation: { required: false, reason_required: false, title: "", confirm_label: "Confirmar" },
    approval_requirement: null, source_alert_ref: String(pk), source_alert_effect: "acknowledges", proof: "",
  });
  // O cartão nasce com o prazo prometido ao cliente (10 min); `late`: a promessa venceu.
  const createdAt = new Date(Date.now() - (late ? 13 : 3) * 60_000);
  const promised = new Date(createdAt.getTime() + 10 * 60_000);
  return {
    pk, rev: 0, type: "concierge_verify", type_label: "WhatsApp: cliente espera a resposta da equipe",
    severity: "warning", severity_label: "Aviso", audience: "orders",
    message: `“amanhã vai ter pão de forma? queria para entregar”\nPrometemos responder até ${clock(promised)}.`,
    order_ref: "", created_at_display: `hoje às ${clock(createdAt)}`,
    origin_label: "WhatsApp", origin_icon: "i-lucide-message-circle",
    subject: "Ana espera a resposta da equipe",
    respond_by_iso: promised.toISOString(), deadline_kind: "house",
    actions,
  };
}

// A Concierge atendendo sem modelo (dono, 19/11/2026): um aviso por causa, cor de erro,
// também no topo da tela (`on_screen`).
function noModelAlert() {
  return {
    pk: 960, rev: 0, type: "concierge_no_model", type_label: "WhatsApp: Concierge sem modelo",
    severity: "error", severity_label: "Erro", audience: "orders",
    message: "A Concierge está atendendo sem modelo: responde o simples e manda para a equipe o que não entende. Causa: a conexão de IA da leitura está sem chave.",
    order_ref: "", created_at_display: "hoje às 21h10",
    origin_label: "WhatsApp", origin_icon: "i-lucide-message-circle", subject: "Concierge sem modelo",
    on_screen: true, respond_by_iso: "", deadline_kind: "",
    actions: [{
      ref: "open_alert_context:960", kind: "open_alert_context", label: "Abrir conexões de IA", priority: 10,
      enabled: true, reason: "", method: "GET", href: "https://admin.boulangerie.com.br/admin/shop/aiconnection/",
      payload_schema: "", expected_rev: null, idempotency: { required: false, key_scope: "" },
      confirmation: { required: false, reason_required: false, title: "", confirm_label: "" },
      approval_requirement: null, source_alert_ref: "960", source_alert_effect: "context", proof: "",
    }, ...(acknowledged.has(960) ? [] : [{
      ref: "acknowledge:960", kind: "acknowledge_alert", label: "Visto", priority: 20, enabled: true,
      reason: "", method: "POST", href: "/api/v1/backstage/alerts/960/ack/",
      payload_schema: "AlertAckMutationRequest", expected_rev: 0,
      idempotency: { required: true, key_scope: "backstage.alert-ack:960" },
      confirmation: { required: false, reason_required: false, title: "", confirm_label: "Confirmar" },
      approval_requirement: null, source_alert_ref: "960", source_alert_effect: "acknowledges", proof: "",
    }])],
  };
}

function alertsPayload() {
  const payload = JSON.parse(JSON.stringify(baseAlerts));
  if (scenario === "concierge-no-model") {
    payload.alerts = [noModelAlert(), ...payload.alerts];
    payload.counts.active += 1;
  }
  if ((scenario === "concierge" || scenario === "concierge-late") && !verification.answered && !verification.takenOver) {
    payload.alerts = [verificationAlert(scenario === "concierge-late"), ...payload.alerts];
    payload.counts.active += 1;
  }
  if (scenario === "gallery") {
    payload.alerts = [urgentAlert(), ...payload.alerts];
    payload.counts.active += 1;
  }
  return payload;
}

function dayInSaoPaulo(offsetDays) {
  const at = new Date(Date.now() + offsetDays * 86400000);
  return at.toLocaleDateString("en-CA", { timeZone: "America/Sao_Paulo" });
}

function queuePayload() {
  const payload = JSON.parse(JSON.stringify(baseQueue));
  const q = payload.queue;
  payload.generated_at = new Date().toISOString();
  q.service_day = dayInSaoPaulo(0);
  q.service_day_ends_at = dayInSaoPaulo(1) + "T00:00:00-03:00";
  if (VOLUMES) {
    for (const key of Object.keys(q)) if (Array.isArray(q[key])) q[key] = q[key].map(withVolumes);
  }
  if (scenario === "empty") {
    const emptyKeys = ["intake", "prep", "expedition_pickup", "expedition_delivery",
      "expedition_delivery_transit", "preorders", "equipment_out", "equipment_available",
      "ifood_negotiation_orders"];
    for (const key of emptyKeys) q[key] = [];
    q.preparing_count = 0; q.expedition_delivery_count = 0;
    q.expedition_count = 0; q.total_count = 0; q.preorders_count = 0;
  }
  if (scenario === "gallery") {
    const gallery = galleryQueue(q.prep[0]);
    Object.assign(q, gallery);
    q.preparing_count = gallery.prep.length;
    q.expedition_delivery_count = gallery.expedition_delivery.length;
    q.expedition_count = gallery.expedition_pickup.length + gallery.expedition_delivery.length;
    q.preorders_count = gallery.preorders.length;
    q.total_count = Object.values(gallery).reduce((sum, list) => sum + list.length, 0);
  }
  if (scenario === "dense") {
    const base = q.prep[0] || q.expedition_pickup[0];
    const dense = [];
    for (let index = 0; index < 12; index += 1) {
      const card = JSON.parse(JSON.stringify(base));
      card.ref = "DENSE-" + String(index + 1).padStart(2, "0");
      card.channel_display_id = String(500 + index);
      dense.push(card);
    }
    q.prep = dense; q.preparing_count = dense.length; q.total_count = dense.length;
  }
  return payload;
}

function send(res, status, payload) {
  const body = JSON.stringify(payload);
  res.statusCode = status;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.setHeader("content-length", Buffer.byteLength(body));
  res.setHeader("x-api-version", "1.0");
  res.end(body);
}

createServer((req, res) => {
  const url = new URL(req.url || "/", "http://127.0.0.1:" + port);
  const path = url.pathname;

  if (path === "/__visual/scenario") {
    const next = url.searchParams.get("set");
    if (next) { scenario = next; acknowledged.clear(); checkedBags.clear(); verification.answered = false; verification.takenOver = false; verification.promoted = false; verification.answerText = ""; }
    send(res, 200, { scenario });
    return;
  }
  if (path === "/__visual/health") { send(res, 200, { ok: true }); return; }
  // A trava do operador (kit): `lock` = ninguém operando; `lock-forced` = o gerente
  // redefiniu o PIN e a troca é obrigatória. Destrave e troca sempre recusam: o
  // spec mede a geometria da tela de PIN, inclusive com a recusa.
  if (scenario.startsWith("lock")) {
    if (path === "/api/v1/backstage/operator/session/") {
      const forced = scenario === "lock-forced";
      send(res, 200, {
        station: "GESTOR-1", workstation: null,
        operator: forced ? LOCK_PEOPLE[0] : null,
        locked: true, pin_must_change: forced, authorized: false,
      });
      return;
    }
    if (path === "/api/v1/backstage/operator/eligible/") {
      send(res, 200, { operators: LOCK_PEOPLE });
      return;
    }
    if (req.method === "POST" && path.startsWith("/api/v1/backstage/operator/")) {
      send(res, 403, { detail: "PIN incorreto. Restam 4 tentativas.", field: null, errors: {} });
      return;
    }
  }
  if (path === "/api/v1/backstage/operator/session/") {
    send(res, 200, {
      station: "GESTOR-1", workstation: null,
      operator: { id: 1, username: "admin", name: "Admin" },
      locked: false, pin_must_change: false, authorized: true,
    });
    return;
  }
  if (path === "/api/v1/backstage/orders/board-layout/") {
    send(res, 200, { station: "GESTOR-1", columns: null });
    return;
  }
  if (req.method === "POST" && path.indexOf("ERR07") >= 0) {
    send(res, 409, { detail: "O pedido mudou em outra estação. Atualize e tente de novo.", field: null, errors: {} });
    return;
  }
  if (req.method === "POST" && path === "/api/v1/backstage/orders/volume-check/") {
    let raw = "";
    req.on("data", (chunk) => { raw += chunk; });
    req.on("end", () => {
      let body;
      try { body = JSON.parse(raw || "{}"); } catch { body = {}; }
      send(res, 200, volumeCheck(body));
    });
    return;
  }
  if (path === "/api/v1/backstage/orders/") {
    if (scenario === "error") {
      send(res, 500, { detail: "Falha simulada da matriz visual." });
      return;
    }
    send(res, 200, queuePayload());
    return;
  }
  // A projeção da Central (dados fictícios), para os outros apps do trocador.
  if (path === "/api/v1/backstage/hub/") { send(res, 200, { hub: { tiles: [{"ref":"pos","label":"PDV","icon":"shopping-basket","url":"http://localhost:3002/","kind":"launch","description":"","status_attention":"1 encomenda na próxima hora","status_summary":"Caixa aberto","status_positive":"","next_item":null},{"ref":"kds","label":"Cozinha","icon":"chef-hat","url":"http://localhost:3003/","kind":"launch","description":"","status_attention":"1 atrasado","status_summary":"3 em preparo","status_positive":"","next_item":null},{"ref":"gestor","label":"Gestor de pedidos","icon":"square-kanban","url":"http://localhost:3004/","kind":"launch","description":"","status_attention":"","status_summary":"","status_positive":"","next_item":null},{"ref":"production","label":"Produção","icon":"croissant","url":"http://localhost:3005/","kind":"launch","description":"","status_attention":"","status_summary":"5 lotes hoje","status_positive":"","next_item":null},{"ref":"purchase","label":"Compras","icon":"package","url":"http://localhost:3008/","kind":"launch","description":"","status_attention":"2 entregas para receber","status_summary":"","status_positive":"","next_item":null},{"ref":"marketing","label":"Marketing","icon":"megaphone","url":"http://localhost:3006/","kind":"launch","description":"","status_attention":"1 anúncio para decidir","status_summary":"","status_positive":"","next_item":null},{"ref":"bi","label":"B.I.","icon":"chart-no-axes-combined","url":"http://localhost:3007/","kind":"launch","description":"","status_attention":"","status_summary":"Vendas de ontem","status_positive":"","next_item":null}] } }); return; }
  if (path === "/api/v1/backstage/orders/rail-counts/") { send(res, 200, baseRailCounts); return; }
  if (path === "/api/v1/backstage/alerts/") { send(res, 200, alertsPayload()); return; }
  const verifyMatch = path.match(/^\/api\/v1\/backstage\/alerts\/950\/concierge-verification\/(answer|take-over)\/$/);
  if (req.method === "POST" && verifyMatch) {
    let raw = "";
    req.on("data", (chunk) => { raw += chunk; });
    req.on("end", () => {
      let body;
      try { body = JSON.parse(raw || "{}"); } catch { body = {}; }
      if (verifyMatch[1] === "take-over") {
        verification.takenOver = true;
        send(res, 200, { ok: true, pk: 950, sent_text: "Alguém da equipe continua com você por aqui." });
        return;
      }
      const text = String(body.text || "").trim();
      if (/janela/i.test(text)) {
        send(res, 409, {
          detail: "A janela de 24 horas do WhatsApp fechou: a resposta não sai mais por aqui. Assuma a conversa.",
          error: { code: "window_closed", text: `A equipe confirmou: ${text}` },
        });
        return;
      }
      verification.answered = true;
      verification.answerText = text;
      send(res, 200, {
        ok: true, pk: 950, sent_text: `A equipe confirmou: ${text}`,
        promote_href: "/api/v1/backstage/alerts/950/concierge-verification/promote-faq/",
      });
    });
    return;
  }
  // WP-15: a resposta vira rascunho de pergunta frequente; a que cita um dia traz o aviso.
  if (req.method === "POST" && path === "/api/v1/backstage/alerts/950/concierge-verification/promote-faq/") {
    const dated = /(^|\s)(hoje|amanh[ãa])(\s|[.,!?]|$)/i.test(verification.answerText || "");
    send(res, 200, {
      ok: true, pk: 950, already: Boolean(verification.promoted),
      admin_url: "https://admin.boulangerie.com.br/admin/shop/faqentry/12/change/",
      warning: dated
        ? `A resposta cita um dia ou uma data: “${(verification.answerText.split(/(?<=[.!?])\s+/)[0] || "").replace(/[.!?]$/, "")}”. Confira se ela vale sempre antes de publicar.`
        : "",
    });
    verification.promoted = true;
    return;
  }
  const ackMatch = path.match(/^\/api\/v1\/backstage\/alerts\/(\d+)\/ack\/$/);
  if (req.method === "POST" && ackMatch) {
    acknowledged.add(Number(ackMatch[1]));
    send(res, 200, { ok: true, pk: Number(ackMatch[1]) });
    return;
  }
  if (path === "/api/v1/backstage/channels/attention/") { send(res, 200, baseAttention); return; }
  if (path.indexOf("/events/") >= 0 || path.indexOf("/sse/") >= 0) { res.statusCode = 204; res.end(); return; }
  if (req.method === "GET" && path === "/api/v1/backstage/catalog/products/sheet/") {
    send(res, 200, productSheetPayload());
    return;
  }
  if (req.method === "POST" && (path === "/api/v1/backstage/catalog/product/photo/" || path === "/api/v1/backstage/catalog/product/photo/upload/")) {
    let raw = "";
    req.on("data", (chunk) => { raw += chunk; });
    req.on("end", () => {
      let body;
      try { body = JSON.parse(raw || "{}"); } catch { body = {}; }
      send(res, 200, path.endsWith("/upload/")
        ? { url: "https://media.example.com/produtos/foto-padronizada.jpg", name: "foto-padronizada.jpg" }
        : { image: body.image || "" });
    });
    return;
  }
  const productDetail = req.method === "GET" && path.match(/^\/api\/v1\/backstage\/catalog\/product\/([^/]+)\/$/);
  if (productDetail && !["create", "duplicate", "draft", "import"].includes(productDetail[1])) {
    send(res, 200, productDetailPayload(decodeURIComponent(productDetail[1])));
    return;
  }
  if (req.method === "GET") {
    const detail = path.match(/^\/api\/v1\/backstage\/orders\/([A-Z0-9-]+)\/$/);
    const catalog = path === "/api/v1/backstage/catalog/" ? catalogPayload(url) : null;
    const body = catalog || (detail && !recorded[path] && galleryDetail(detail[1])) || recordedFor(url);
    if (body) { send(res, 200, body); return; }
  }
  send(res, 200, {});
}).listen(port, "127.0.0.1", () => {
  console.log("[orders-visual-mock] listening on http://127.0.0.1:" + port);
});

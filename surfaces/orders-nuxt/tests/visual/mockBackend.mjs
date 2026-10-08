import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { galleryQueue } from "./galleryCards.mjs";

// Backend hermético da matriz visual do Gestor. Sem Django, sem dados vivos:
// as fixtures abaixo foram CAPTURADAS do backend real (seed Nelson) e o mock só
// reescreve os campos de relógio para o quadro não nascer "desatualizado".
// O estado é trocado por GET /__visual/scenario?set=<normal|empty|dense|error|gallery>.

const here = dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.MOCK_PORT || 38793);
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

function alertsPayload() {
  const payload = JSON.parse(JSON.stringify(baseAlerts));
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
    if (next) { scenario = next; acknowledged.clear(); }
    send(res, 200, { scenario });
    return;
  }
  if (path === "/__visual/health") { send(res, 200, { ok: true }); return; }
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
  if (path === "/api/v1/backstage/orders/") {
    if (scenario === "error") {
      send(res, 500, { detail: "Falha simulada da matriz visual." });
      return;
    }
    send(res, 200, queuePayload());
    return;
  }
  if (path === "/api/v1/backstage/orders/rail-counts/") { send(res, 200, baseRailCounts); return; }
  if (path === "/api/v1/backstage/alerts/") { send(res, 200, alertsPayload()); return; }
  const ackMatch = path.match(/^\/api\/v1\/backstage\/alerts\/(\d+)\/ack\/$/);
  if (req.method === "POST" && ackMatch) {
    acknowledged.add(Number(ackMatch[1]));
    send(res, 200, { ok: true, pk: Number(ackMatch[1]) });
    return;
  }
  if (path === "/api/v1/backstage/channels/attention/") { send(res, 200, baseAttention); return; }
  if (path.indexOf("/events/") >= 0 || path.indexOf("/sse/") >= 0) { res.statusCode = 204; res.end(); return; }
  if (req.method === "GET") {
    const detail = path.match(/^\/api\/v1\/backstage\/orders\/([A-Z0-9-]+)\/$/);
    const body = (detail && !recorded[path] && galleryDetail(detail[1])) || recordedFor(url);
    if (body) { send(res, 200, body); return; }
  }
  send(res, 200, {});
}).listen(port, "127.0.0.1", () => {
  console.log("[orders-visual-mock] listening on http://127.0.0.1:" + port);
});

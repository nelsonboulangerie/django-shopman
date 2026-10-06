import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

// Backend hermético da matriz visual do Gestor. Sem Django, sem dados vivos:
// as fixtures abaixo foram CAPTURADAS do backend real (seed Nelson) e o mock só
// reescreve os campos de relógio para o quadro não nascer "desatualizado".
// O estado é trocado por GET /__visual/scenario?set=<normal|empty|dense|error>.

const here = dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.MOCK_PORT || 38793);
const readFixture = (name) => JSON.parse(readFileSync(join(here, "fixtures", name), "utf8"));

const baseQueue = readFixture("orders-board.json");
const baseAlerts = readFixture("alerts.json");
const baseAttention = readFixture("channel-attention.json");
const baseRailCounts = readFixture("rail-counts.json");

let scenario = "normal";

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
    if (next) scenario = next;
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
  if (path === "/api/v1/backstage/orders/") {
    if (scenario === "error") {
      send(res, 500, { detail: "Falha simulada da matriz visual." });
      return;
    }
    send(res, 200, queuePayload());
    return;
  }
  if (path === "/api/v1/backstage/orders/rail-counts/") { send(res, 200, baseRailCounts); return; }
  if (path === "/api/v1/backstage/alerts/") { send(res, 200, baseAlerts); return; }
  if (path === "/api/v1/backstage/channels/attention/") { send(res, 200, baseAttention); return; }
  if (path.indexOf("/events/") >= 0 || path.indexOf("/sse/") >= 0) { res.statusCode = 204; res.end(); return; }
  send(res, 200, {});
}).listen(port, "127.0.0.1", () => {
  console.log("[orders-visual-mock] listening on http://127.0.0.1:" + port);
});

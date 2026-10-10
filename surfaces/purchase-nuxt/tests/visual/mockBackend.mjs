import { createServer } from "node:http";

import { countFixture, purchaseFixture, receivingFixture } from "./fixtures.mjs";

// Backend hermético do Compras: a matriz visual (`playwright.visual.config.ts`) e a
// prévia de quem muda a tela usam o MESMO mock. Sem Django, sem dado vivo: o
// cadastro é sintético (padaria de exemplo), com nome comprido de propósito para
// provar que o texto da casa quebra em vez de cortar.
//
// O estado se troca por GET /__visual/scenario?set=<normal|empty|error|receiving>:
//   normal     a base cheia, sem entrada aberta;
//   receiving  a base cheia e uma NF lida, em conferência (o "Receber" do celular);
//   empty      a base sem insumo nem fornecedor;
//   error      a leitura da base falha (500).
// Os POSTs respondem `ok` com a mesma projeção: a tela anda, nada é gravado.

const port = Number(process.env.MOCK_PORT || 35031);
let scenario = process.env.PURCHASE_MOCK_SCENARIO || "normal";

function projection() {
  if (scenario === "empty") {
    return {
      materials: [],
      suppliers: [],
      conversions: [],
      costs: [],
      purchaseRequestStatuses: {},
      activeReceipt: { mode: "invoice", supplierRef: "", invoiceInput: "", note: "", lines: [] },
      receiptHistory: [],
    };
  }
  return scenario === "receiving" ? receivingFixture() : purchaseFixture();
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
  if (path === "/__visual/health") {
    send(res, 200, { ok: true });
    return;
  }
  if (path === "/api/v1/backstage/operator/session/") {
    send(res, 200, {
      station: "COMPRAS-1",
      workstation: null,
      operator: { id: 1, username: "compras", name: "Compras" },
      locked: false,
      pin_must_change: false,
      authorized: true,
    });
    return;
  }
  if (path === "/api/v1/backstage/purchase/") {
    if (scenario === "error") {
      send(res, 500, { detail: "Falha simulada da matriz visual.", field: null, errors: {} });
      return;
    }
    send(res, 200, { purchase: projection() });
    return;
  }
  if (path === "/api/v1/backstage/purchase/count/") {
    send(res, 200, { count: scenario === "empty" ? { items: [] } : countFixture() });
    return;
  }
  if (req.method === "POST" && path.startsWith("/api/v1/backstage/purchase/")) {
    if (path.endsWith("receipts/scan-invoice/")) scenario = "receiving";
    if (path.endsWith("receipts/confirm/") || path.endsWith("receipts/reject/")) scenario = "normal";
    send(res, 200, { ok: true, purchase: projection(), message: "Feito (prévia, nada foi gravado)." });
    return;
  }
  if (path.indexOf("/events/") >= 0 || path.indexOf("/sse/") >= 0) {
    res.statusCode = 204;
    res.end();
    return;
  }
  send(res, 200, {});
}).listen(port, "127.0.0.1", () => {
  console.log("[purchase-visual-mock] listening on http://127.0.0.1:" + port + " (" + scenario + ")");
});

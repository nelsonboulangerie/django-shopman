// Mock backend mínimo p/ os e2e do KDS, backend-independente. Ramifica pelo COOKIE que o
// BFF encaminha (djangoProxy repassa o header cookie ao Django):
//   · com `e2e_session=authed` → sessão de operador AUTENTICADA + estações + board vazio;
//   · sem o cookie → 403 nos endpoints de operador (device não autenticado → gate de login).
// O board público do cliente (/kds/cliente/) responde 200 SEMPRE (o `/pickup` é público,
// como o menuboard do Produção). Login/lock/ações reais rodam contra o Django (reviewer local).
//
// PRÉVIA (`KDS_MOCK_FIXTURE=preview`): toda requisição entra autenticada (sem cookie) e as
// estações `bancada` (preparo) e `expedicao` servem os quadros de previewFixtures.mjs,
// com iniciar/finalizar/expedir mudando o quadro. Serve para VER os cards sem Django.
import { createServer } from "node:http";
import { createPreviewState } from "./previewFixtures.mjs";

const port = Number(process.env.MOCK_PORT || 8798);
const preview = process.env.KDS_MOCK_FIXTURE === "preview" ? createPreviewState() : null;

// Uma identidade: `locked` é literalmente "não há operador". O mock dizia
// `operator: null, locked: false` — combinação que o servidor não produz, e que
// só fazia sentido quando existia um interruptor para desligar o gate.
const SESSION_AUTHED = {
  station: "balcao",
  operator: { id: 1, username: "admin", name: "Admin" },
  locked: false,
  pin_must_change: false,
};

const INDEX = {
  instances: [
    { ref: "bancada", name: "Bancada", type: "prep", type_display: "Preparo", active_count: 0 },
  ],
};

const BOARD = {
  board: {
    instance_ref: "bancada",
    instance_name: "Bancada",
    instance_type: "prep",
    is_expedition: false,
    tickets: [],
    counts: { pending: 0, in_progress: 0, total: 0 },
    cancelled_tickets: [],
    recent_done: [],
  },
};

// Board público do cliente — o /pickup renderiza sem sessão de operador.
const CUSTOMER = {
  status: {
    preparing: [{ ref: "WEB-0007", status: "preparing", status_label: "Preparando", updated_at_display: "08:00" }],
    ready: [{ ref: "WEB-0006", status: "ready", status_label: "Pronto", updated_at_display: "07:58" }],
    updated_at_display: "08:00",
  },
};

function json(res, status, body) {
  res.statusCode = status;
  res.end(JSON.stringify(body));
}

const server = createServer((req, res) => {
  res.setHeader("content-type", "application/json");
  res.setHeader("set-cookie", "csrftoken=e2e-mock; Path=/");
  const url = req.url || "";
  const authed = Boolean(preview) || (req.headers.cookie || "").includes("e2e_session=authed");

  // Público — sempre 200, com ou sem sessão de operador.
  if (/\/kds\/cliente\/?(\?|$)/.test(url)) return json(res, 200, CUSTOMER);

  // Sessão do dispositivo: 403 = não autenticado → o gate de login aparece.
  if (/\/operator\/session\/?(\?|$)/.test(url)) {
    return authed ? json(res, 200, SESSION_AUTHED) : json(res, 403, { detail: "Autenticação necessária." });
  }

  if (!authed) return json(res, 403, { detail: "Autenticação necessária." });

  if (/\/operator\/eligible\/?(\?|$)/.test(url)) return json(res, 200, { operators: [] });
  if (preview) {
    if (req.method === "POST" && preview.write(url)) return json(res, 200, {});
    const station = url.match(/\/kds\/([^/?]+)\/?(\?|$)/);
    if (station && station[1] !== "cliente") return json(res, 200, preview.board(station[1]));
    if (/\/kds\/?(\?|$)/.test(url)) return json(res, 200, preview.index());
  }
  if (/\/kds\/[^/]+\/?(\?|$)/.test(url)) return json(res, 200, BOARD); // /kds/<ref>/
  if (/\/kds\/?(\?|$)/.test(url)) return json(res, 200, INDEX); // índice de estações
  return json(res, 200, {});
});

server.listen(port, "127.0.0.1", () => {
  // eslint-disable-next-line no-console
  console.log(`[kds-mock] listening on http://127.0.0.1:${port}`);
});

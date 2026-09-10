// Mock backend mínimo p/ os e2e do Produção, backend-independente. Ramifica pelo COOKIE que
// o BFF encaminha (djangoProxy repassa o header cookie ao Django):
//   · com `e2e_session=authed` → sessão de operador AUTENTICADA + boards vazios (o shell
//     passa dos gates e as telas de operador renderizam o estado vazio acolhedor);
//   · sem o cookie → 403 nos endpoints de operador (device não autenticado → o gate de
//     login aparece), espelhando o Django real ("quando não autenticado, o endpoint 403a").
// Não há fixture de storefront: o menuboard paralelo foi aposentado e qualquer
// consulta a /storefront/ deve ficar evidente como 404 do mock.
// Login efetivo, lock (Opção C) e ações reais rodam contra o Django real (reviewer local).
import { createServer } from "node:http";

const port = Number(process.env.MOCK_PORT || 8797);

// Uma identidade: `locked` é literalmente "não há operador". O mock dizia
// `operator: null, locked: false` — combinação que o servidor não produz, e que
// só fazia sentido quando existia um interruptor para desligar o gate.
const SESSION_AUTHED = {
  station: "balcao",
  operator: { id: 1, username: "admin", name: "Admin" },
  locked: false,
  pin_must_change: false,
};

const ACCESS = {
  can_view_suggested: true,
  can_view_planned: true,
  can_edit_planned: true,
  can_view_started: true,
  can_edit_started: true,
  can_view_finished: true,
  can_edit_finished: true,
};

const BOARD = {
  board: {
    selected_date: "2026-07-06",
    selected_date_display: "domingo, 6 de julho",
    selected_position_ref: "",
    access: ACCESS,
    base_recipes: [],
    matrix_rows: [],
    counts: { planned: 0, started: 0, finished: 0, planned_qty: "0", started_qty: "0", finished_qty: "0" },
  },
};

const FORECAST = { forecast: { selected_date: "2026-07-06", selected_date_display: "domingo, 6 de julho", rows: [] } };
const KDS = { kds: { cards: [], total_count: 0, late_count: 0 } };
const MISE = { mise_en_place: { selected_date: "2026-07-06", lines: [] } };
const ALERTS = { alerts: [], counts: { active: 0, critical: 0 } };

function json(res, status, body) {
  res.statusCode = status;
  res.end(JSON.stringify(body));
}

const server = createServer((req, res) => {
  res.setHeader("content-type", "application/json");
  res.setHeader("set-cookie", "csrftoken=e2e-mock; Path=/");
  // O BFF deve preservar Vary e substituir qualquer cache público por private/no-store.
  res.setHeader("vary", "Accept-Language");
  res.setHeader("cache-control", "public, max-age=3600");
  const url = req.url || "";
  const authed = (req.headers.cookie || "").includes("e2e_session=authed");

  if (/\/storefront\//.test(url)) return json(res, 404, { detail: "Storefront fora do Produção." });

  // Sessão do dispositivo: 403 = device não autenticado → o gate de login aparece.
  if (/\/operator\/session\/?(\?|$)/.test(url)) {
    return authed ? json(res, 200, SESSION_AUTHED) : json(res, 403, { detail: "Autenticação necessária." });
  }

  // Demais endpoints de operador exigem a sessão autenticada.
  if (!authed) return json(res, 403, { detail: "Autenticação necessária." });

  if (/\/operator\/eligible\/?(\?|$)/.test(url)) return json(res, 200, { operators: [] });
  if (/\/production\/forecast\/?(\?|$)/.test(url)) return json(res, 200, FORECAST);
  if (/\/production\/kds\/?(\?|$)/.test(url)) return json(res, 200, KDS);
  if (/\/production\/mise-en-place\/?(\?|$)/.test(url)) return json(res, 200, MISE);
  if (/\/production\/?(\?|$)/.test(url)) return json(res, 200, BOARD);
  if (/\/alerts\/?(\?|$)/.test(url)) return json(res, 200, ALERTS);
  return json(res, 200, {});
});

server.listen(port, "127.0.0.1", () => {
  // eslint-disable-next-line no-console
  console.log(`[producao-mock] listening on http://127.0.0.1:${port}`);
});

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

const SESSION_LOCKED = {
  station: "balcao",
  operator: null,
  locked: true,
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

const LONG_COPY_BOARD = {
  board: {
    ...BOARD.board,
    matrix_rows: [
      {
        recipe_pk: 91,
        output_sku: "PAO-FERMENTACAO-NATURAL-12345",
        recipe_name: "Pão de fermentação natural com castanhas brasileiras",
        base_usages: [],
        suggestion: {
          recipe_pk: 91,
          recipe_ref: "pao-fermentacao-natural-castanhas",
          recipe_name: "Pão de fermentação natural com castanhas brasileiras",
          base_usages: [],
          output_sku: "PAO-FERMENTACAO-NATURAL-12345",
          quantity: "12345,75",
          committed: "9876,5",
          avg_demand: "12000,25",
          confidence: "Alta",
          sample_size: 30,
          high_demand_applied: true,
          explanation_parts: [
            "Demanda comprometida de 9.876,5 unidades para encomendas confirmadas",
          ],
        },
        planned_orders: [],
        started_orders: [],
        finished_orders: [],
        planned_qty: "12345,75",
        started_qty: "0",
        finished_qty: "0",
        loss_qty: "0",
      },
    ],
  },
};

const FORECAST = {
  forecast: {
    selected_date: "2026-07-06",
    selected_date_display: "domingo, 6 de julho",
    generated_at_display: "12:00",
    rows: [
      {
        ref: "WO-ATRASADA",
        output_sku: "PAO-FRANCES",
        recipe_name: "Pão francês",
        qty: "40",
        eta_display: "06:30",
        eta_is_actual: false,
        status: "delayed",
        status_label: "ATRASADO",
        history_days: 30,
      },
    ],
    access: ACCESS,
    actions: [],
  },
};
const KDS = { kds: { cards: [], total_count: 0, late_count: 0 } };
const MISE = { mise_en_place: { selected_date: "2026-07-06", lines: [] } };
const ALERTS = { alerts: [], counts: { active: 0, critical: 0 } };
const QC = {
  qc: {
    selected_date: "2026-07-06",
    selected_date_display: "domingo, 6 de julho",
    orders: [
      {
        pk: 42,
        ref: "WO-0042",
        rev: 3,
        recipe_name: "Pão francês",
        output_sku: "PAO-FRANCES",
        position_ref: "forno-1",
        status: "started",
        planned_qty: "40",
        started_qty: "40",
        started_at_display: "06:30",
        elapsed_minutes: 20,
        can_close: true,
        closed: false,
        can_correct: false,
        quality_reviewed: false,
        partition: [],
        correction_count: 0,
        last_correction_at_display: "",
        committed_qty: "12",
        full_price_qty: "0",
        discounted_qty: "0",
        loss_qty: "0",
      },
    ],
    closed_count: 0,
    total_count: 1,
    grades: [
      { ref: "standard", label: "Normal", rank: 30, markdown_percent: 0, is_default: true },
    ],
    defects: [],
    recipes: [],
    previous_open_count: 0,
    previous_open_date: "",
    access: ACCESS,
    actions: [{ ref: "finish:42", enabled: true, expected_rev: 3, proof: "finish-proof" }],
    generated_at: "2099-01-01T11:59:00Z",
    source_revision: "qc:1",
    fresh_until: "2099-01-01T12:01:00Z",
    contract_version: 1,
  },
};

const REPORTS = {
  reports: {
    filters: {
      report_kind: "history",
      date_from: "2026-07-01",
      date_to: "2026-07-06",
    },
    history_rows: [
      {
        ref: "WO-0042",
        date: "06/07/2026",
        recipe_name: "Pão francês",
        position_ref: "forno-1",
        qty_planned: "40",
        qty_started: "40",
        qty_finished: "38",
        qty_loss: "2",
        yield_rate: "95%",
        operator_ref: "admin",
        duration_minutes: "60",
      },
    ],
    operator_rows: [],
    waste_rows: [],
    quality_rows: [],
    available_recipes: [{ ref: "pao-frances", name: "Pão francês" }],
    available_positions: [{ ref: "forno-1", name: "Forno 1" }],
  },
  pagination: {
    total: 2,
    page_size: 1,
    from: 1,
    to: 1,
    sort: "default",
    next_cursor: "cursor-e2e-seguinte",
    previous_cursor: "",
  },
};

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
  const cookie = req.headers.cookie || "";
  const authed = cookie.includes("e2e_session=authed");
  const locked = cookie.includes("e2e_session=locked");
  const longCopy = (req.headers.cookie || "").includes("e2e_scenario=long-copy");
  const populatedReports = cookie.includes("e2e_scenario=reports-populated");

  if (/\/storefront\//.test(url)) return json(res, 404, { detail: "Storefront fora do Produção." });

  // Sessão do dispositivo: 403 = device não autenticado → o gate de login aparece.
  if (/\/operator\/session\/?(\?|$)/.test(url)) {
    if (authed) return json(res, 200, SESSION_AUTHED);
    if (locked) return json(res, 200, SESSION_LOCKED);
    return json(res, 403, { detail: "Autenticação necessária." });
  }

  // Demais endpoints de operador exigem a sessão autenticada.
  if (!authed && !locked) return json(res, 403, { detail: "Autenticação necessária." });

  // A lista mínima para o diálogo de identificação continua disponível. Todo
  // dado operacional — leitura OU mutação — é negado enquanto a estação está
  // travada, como no permission boundary real.
  if (/\/operator\/eligible\/?(\?|$)/.test(url)) return json(res, 200, { operators: [] });
  if (locked) {
    return json(res, 403, {
      detail: "Estação travada.",
      error: { code: "station_locked" },
    });
  }
  if (/\/production\/forecast\/?(\?|$)/.test(url)) return json(res, 200, FORECAST);
  if (/\/production\/kds\/?(\?|$)/.test(url)) return json(res, 200, KDS);
  if (/\/production\/qc\/?(\?|$)/.test(url)) return json(res, 200, QC);
  if (/\/production\/mise-en-place\/?(\?|$)/.test(url)) return json(res, 200, MISE);
  if (
    /\/production\/reports\/?\?/.test(url) &&
    url.includes("format=csv") &&
    populatedReports
  ) {
    res.setHeader("content-type", "text/csv; charset=utf-8");
    return setTimeout(() => res.end("OP;Ficha técnica\nWO-0042;Pão francês\n"), 1_000);
  }
  if (/\/production\/reports\/?(\?|$)/.test(url) && populatedReports) {
    return json(res, 200, REPORTS);
  }
  if (/\/production\/?(\?|$)/.test(url)) return json(res, 200, longCopy ? LONG_COPY_BOARD : BOARD);
  if (/\/alerts\/?(\?|$)/.test(url)) return json(res, 200, ALERTS);
  return json(res, 200, {});
});

server.listen(port, "127.0.0.1", () => {
  // eslint-disable-next-line no-console
  console.log(`[producao-mock] listening on http://127.0.0.1:${port}`);
});

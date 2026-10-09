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
  // A antessala responde sobre a capability da superfície (OperatorSessionView): o
  // shell só monta as telas com `authorized`.
  authorized: true,
};

const SESSION_LOCKED = {
  station: "balcao",
  operator: null,
  locked: true,
  pin_must_change: false,
  authorized: false,
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
          projected: "12000",
          margin: "-9530,75",
          safety_percent: 10,
          same_weekday: true,
          season_label: "",
          season_fallback: false,
          current_season_label: "",
          soldout_days: 0,
          waste_percent: 0,
          waste_discounted: false,
          material_shortages: [],
          fits_quantity: "",
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
        quality_exception: false,
        closed_by: "",
        closed_at_display: "",
        typical_loss_qty: "",
        alert_waiting_count: null,
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

// ── Cenário POVOADO (prévia e capturas): receitas, planejados e lotes ─────────────────
// Liga por cookie `e2e_scenario=populated` ou, para a prévia em túnel (quem abre o link
// não tem cookie), por `MOCK_SCENARIO=populated`, que também trata toda chamada como
// sessão autenticada. Os e2e seguem no board vazio: o cenário só existe quando pedido.
const ACCESS_FULL = {
  ...ACCESS,
  can_manage_all: true,
  can_edit_suggested: true,
  can_view_unsold: true,
  can_edit_unsold: true,
  can_view_plan: true,
};

const STATUS_LABEL = { planned: "Planejado", started: "Em produção", finished: "Finalizado" };

function workOrder(pk, recipe, status, qty) {
  return {
    pk,
    ref: `WO-${String(pk).padStart(4, "0")}`,
    rev: 1,
    recipe_pk: recipe.pk,
    recipe_ref: recipe.ref,
    recipe_name: recipe.name,
    base_usages: [],
    output_sku: recipe.sku,
    status,
    status_label: STATUS_LABEL[status],
    tone: status === "finished" ? "success" : "info",
    planned_qty: qty,
    started_qty: status === "planned" ? "" : qty,
    finished_qty: status === "finished" ? qty : "",
    yield_rate: status === "finished" ? "100%" : "",
    loss: "0",
    operator_ref: "admin",
    position_ref: "forno",
    target_date_display: "domingo, 6 de julho",
    started_at_display: status === "planned" ? "" : "06:30",
    created_at_display: "05/07 18:00",
    progress_pct: status === "finished" ? 100 : status === "started" ? 50 : 0,
    committed_qty: "0",
    order_commitments: [],
    can_void: status === "planned",
    position_name: "Forno",
    created_at_time: "18:00",
  };
}

function suggestionFor(recipe, quantity) {
  return {
    recipe_pk: recipe.pk,
    recipe_ref: recipe.ref,
    recipe_name: recipe.name,
    base_usages: [],
    output_sku: recipe.sku,
    quantity,
    committed: "0",
    avg_demand: quantity,
    confidence: "Alta",
    sample_size: 8,
    high_demand_applied: false,
    projected: quantity,
    margin: "0",
    safety_percent: 10,
    same_weekday: true,
    season_label: "",
    soldout_days: 0,
    waste_percent: 0,
    waste_discounted: false,
    material_shortages: [],
    fits_quantity: "",
    season_fallback: false,
    current_season_label: "",
    recent_days: [],
    bi_notes: [],
  };
}

const RECIPES = [
  { pk: 1, ref: "pao-frances", sku: "PAO-FRANCES", name: "Pão francês", kind: "bread", kind_label: "Pão" },
  { pk: 2, ref: "baguete-tradicional", sku: "BAGUETE", name: "Baguete tradicional", kind: "bread", kind_label: "Pão" },
  { pk: 3, ref: "croissant-manteiga", sku: "CROISSANT", name: "Croissant de manteiga", kind: "viennoiserie", kind_label: "Viennoiserie" },
  { pk: 4, ref: "pain-au-chocolat", sku: "PAIN-CHOCO", name: "Pain au chocolat", kind: "viennoiserie", kind_label: "Viennoiserie" },
  { pk: 5, ref: "levain-campagne", sku: "CAMPAGNE", name: "Pão de campanha (levain)", kind: "bread", kind_label: "Pão" },
  { pk: 6, ref: "brioche", sku: "BRIOCHE", name: "Brioche", kind: "enriched", kind_label: "Massa enriquecida" },
];
const [FRANCES, BAGUETE, CROISSANT, CHOCO, CAMPAGNE, BRIOCHE] = RECIPES;

function matrixRow(recipe, { suggest, planned = [], started = [], finished = [] }) {
  const sum = (orders) => String(orders.reduce((total, order) => total + Number(order.planned_qty), 0));
  return {
    recipe_pk: recipe.pk,
    output_sku: recipe.sku,
    recipe_name: recipe.name,
    base_usages: [],
    suggestion: suggest ? suggestionFor(recipe, suggest) : null,
    planned_orders: planned,
    started_orders: started,
    finished_orders: finished,
    planned_qty: sum([...planned, ...started, ...finished]),
    started_qty: sum([...started, ...finished]),
    finished_qty: sum(finished),
    loss_qty: "0",
    output_unit: "un",
  };
}

const POPULATED_ROWS = [
  matrixRow(FRANCES, { suggest: "120", planned: [workOrder(101, FRANCES, "planned", "120")] }),
  matrixRow(BAGUETE, {
    suggest: "40",
    planned: [workOrder(102, BAGUETE, "planned", "24"), workOrder(103, BAGUETE, "planned", "16")],
  }),
  matrixRow(CROISSANT, { suggest: "60", started: [workOrder(104, CROISSANT, "started", "60")] }),
  matrixRow(CHOCO, { suggest: "36", finished: [workOrder(105, CHOCO, "finished", "36")] }),
  matrixRow(CAMPAGNE, { suggest: "12" }),
  matrixRow(BRIOCHE, { suggest: "18", planned: [workOrder(106, BRIOCHE, "planned", "18")] }),
];
const POPULATED_ORDERS = POPULATED_ROWS.flatMap((row) => [
  ...row.planned_orders,
  ...row.started_orders,
  ...row.finished_orders,
]);

const BOARD_POPULATED = {
  board: {
    ...BOARD.board,
    selected_operator_ref: "",
    selected_base_recipe: "",
    access: ACCESS_FULL,
    work_orders: POPULATED_ORDERS,
    planned_queue: POPULATED_ORDERS.filter((order) => order.status === "planned"),
    started_queue: POPULATED_ORDERS.filter((order) => order.status === "started"),
    finished_queue: POPULATED_ORDERS.filter((order) => order.status === "finished"),
    recipes: RECIPES.map(({ pk, ref, name }) => ({ pk, ref, name })),
    positions: [{ pk: 7, ref: "forno", name: "Forno", is_default: true }],
    default_position_pk: 7,
    suggestions: POPULATED_ROWS.map((row) => row.suggestion).filter(Boolean),
    matrix_rows: POPULATED_ROWS,
    matrix_groups: [],
    actions: [],
    purchase_url: "",
    day_context: null,
    counts: {
      total: POPULATED_ORDERS.length,
      planned: 4,
      started: 1,
      finished: 1,
      void: 0,
      planned_qty: "214",
      started_qty: "60",
      finished_qty: "36",
      loss_qty: "0",
    },
  },
};

function qcOrder(pk, recipe, extra) {
  return {
    ...QC.qc.orders[0],
    pk,
    ref: `WO-${String(pk).padStart(4, "0")}`,
    recipe_name: recipe.name,
    output_sku: recipe.sku,
    position_ref: "forno",
    position_name: "Forno",
    ...extra,
  };
}

const QC_POPULATED = {
  qc: {
    ...QC.qc,
    orders: [
      qcOrder(104, CROISSANT, { planned_qty: "60", started_qty: "60", started_at_display: "06:10", elapsed_minutes: 42 }),
      qcOrder(107, FRANCES, { planned_qty: "80", started_qty: "80", started_at_display: "05:40", elapsed_minutes: 70 }),
      qcOrder(108, BAGUETE, { planned_qty: "24", started_qty: "24", started_at_display: "06:20", elapsed_minutes: 30 }),
      qcOrder(105, CHOCO, {
        status: "finished",
        planned_qty: "36",
        started_qty: "36",
        can_close: false,
        closed: true,
        full_price_qty: "34",
        loss_qty: "2",
        closed_by: "admin",
        closed_at_display: "07:15",
      }),
    ],
    closed_count: 1,
    total_count: 4,
    grades: [
      { ref: "excellent", label: "Ótimo", rank: 40, markdown_percent: 0, is_default: false },
      { ref: "standard", label: "Normal", rank: 30, markdown_percent: 0, is_default: true },
      { ref: "fair", label: "Razoável", rank: 20, markdown_percent: 20, is_default: false },
    ],
    defects: [
      { ref: "shape", label: "Formato", hint: "Fora do padrão visual", forces_discard: false },
      { ref: "burned", label: "Queimado", hint: "Sem condição de venda", forces_discard: true },
    ],
    recipes: RECIPES.map(({ pk, ref, name }) => ({ pk, ref, name })),
    previous_open_count: 2,
    previous_open_date: "2026-07-05",
    access: ACCESS_FULL,
    actions: [104, 107, 108].map((pk) => ({
      ref: `finish:${pk}`,
      enabled: true,
      expected_rev: 3,
      proof: `finish-proof-${pk}`,
    })),
  },
};

const RECIPE_ACCESS = { can_view: true, can_edit: true, capture_available: false };
const RECIPE_CARDS = RECIPES.map((recipe, index) => ({
  ref: recipe.ref,
  name: recipe.name,
  kind: recipe.kind,
  kind_label: recipe.kind_label,
  output_sku: recipe.sku,
  output_name: recipe.name,
  has_ficha: index !== 5,
  current_version_number: index === 5 ? null : 2,
  version_count: index === 5 ? 1 : 2,
  draft_count: index === 5 ? 1 : 0,
  anchor_kind: "flour",
  hydration_display: recipe.kind === "bread" ? "68%" : "",
  updated_at_display: "04/07/2026",
  is_archived: false,
  is_favorite: index === 0,
  rating_display: index < 3 ? "4,5" : "",
  rating_count: index < 3 ? 6 : 0,
}));
const RECIPE_BOOK = {
  book: {
    entries: RECIPE_CARDS,
    kinds: [
      { value: "bread", label: "Pão" },
      { value: "viennoiserie", label: "Viennoiserie" },
      { value: "enriched", label: "Massa enriquecida" },
    ],
    count: RECIPE_CARDS.length,
  },
  access: RECIPE_ACCESS,
};

function lensItem(sku, name, role, roleLabel, grams, pct, anchor) {
  return {
    sku,
    name,
    role,
    role_label: roleLabel,
    quantity_display: `${grams} g`,
    quantity_g: String(grams),
    unit: "g",
    pct_display: pct,
    is_anchor: anchor,
    matched: true,
  };
}
const LENS = {
  is_bakery: true,
  anchor_kind: "flour",
  anchor_label: "Farinha",
  basis_display: "1.000 g de farinha",
  standardized: true,
  anchor_total_display: "1.000 g",
  total_mass_display: "1.700 g",
  items: [
    lensItem("FARINHA-T65", "Farinha T65", "flour", "Farinha", 1000, "100%", true),
    lensItem("AGUA", "Água", "liquid", "Líquido", 660, "66%", false),
    lensItem("SAL", "Sal", "salt", "Sal", 20, "2%", false),
    lensItem("FERMENTO", "Fermento biológico", "leavening", "Fermento", 20, "2%", false),
  ],
  final_mix: [],
  final_mix_differs: false,
  bom: [],
  bom_differs: false,
  parts: [],
  metrics: [
    {
      code: "hydration",
      label: "Hidratação",
      value_display: "66%",
      low_display: "60%",
      high_display: "75%",
      max_display: "",
      tone: "ok",
      note: "",
    },
  ],
  warnings: [],
};

function recipeVersion(number, status, statusLabel) {
  return {
    id: number,
    number,
    status,
    status_label: statusLabel,
    label: number === 2 ? "Mais hidratada" : "Primeira",
    yield_quantity: "28",
    yield_unit: "un",
    yield_display: "28 un",
    source_kind: "manual",
    source_label: "Escrita à mão",
    created_by: "admin",
    created_at_display: number === 2 ? "04/07/2026" : "01/06/2026",
    published_at_display: status === "draft" ? "" : number === 2 ? "04/07/2026" : "01/06/2026",
    notes: "",
    steps: [
      { name: "Misturar", instructions: "Misturar até o ponto de véu.", target_seconds: 600, target_display: "10 min", temperature_celsius: null, note: "" },
      { name: "Assar", instructions: "Forno com vapor.", target_seconds: 1200, target_display: "20 min", temperature_celsius: 230, note: "" },
    ],
    lens: LENS,
    formula: {},
    origin: {},
  };
}

function recipeDetail(card) {
  return {
    entry: {
      ref: card.ref,
      name: card.name,
      kind: card.kind,
      kind_label: card.kind_label,
      output_sku: card.output_sku,
      output_name: card.output_name,
      notes: "",
      is_archived: false,
      current_version_number: card.current_version_number,
      ficha_ref: card.has_ficha ? card.ref : "",
      execution_in_sync: true,
      is_favorite: card.is_favorite,
      versions: card.current_version_number
        ? [recipeVersion(2, "published", "Publicada"), recipeVersion(1, "superseded", "Substituída")]
        : [recipeVersion(1, "draft", "Rascunho")],
      usage: {
        date_from: "2026-06-06",
        date_to: "2026-07-06",
        bake_loss_basis: "",
        caveats: [],
        versions: [],
        unversioned: null,
      },
      external_references: [],
      rating_criteria: [{ id: 1, name: "Crosta", description: "Cor e crocância" }],
      ratings: [],
    },
    access: RECIPE_ACCESS,
  };
}

/** A resposta do cenário povoado para esta URL, ou `null` para seguir o mock de base. */
function populatedResponse(url) {
  if (/\/production\/qc\/?(\?|$)/.test(url)) return QC_POPULATED;
  const detail = url.match(/\/recipes\/([\w-]+)\/?(\?|$)/);
  const card = detail && RECIPE_CARDS.find((entry) => entry.ref === detail[1]);
  if (card) return recipeDetail(card);
  if (/\/recipes\/access\/?(\?|$)/.test(url)) return { access: RECIPE_ACCESS };
  if (/\/recipes\/?(\?|$)/.test(url)) return RECIPE_BOOK;
  if (/\/production\/?(\?|$)/.test(url)) return BOARD_POPULATED;
  return null;
}

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
  const previewScenario = process.env.MOCK_SCENARIO === "populated";
  const authed = previewScenario || cookie.includes("e2e_session=authed");
  const locked = cookie.includes("e2e_session=locked");
  const longCopy = (req.headers.cookie || "").includes("e2e_scenario=long-copy");
  const populatedReports = cookie.includes("e2e_scenario=reports-populated");
  const populated = previewScenario || cookie.includes("e2e_scenario=populated");

  if (/\/storefront\//.test(url)) return json(res, 404, { detail: "Storefront fora do Produção." });

  // Sessão do dispositivo: 403 = device não autenticado → o gate de login aparece.
  //
  // ⚠️ São DUAS antessalas, e a diferença é trava de servidor, não arrumação de
  // rota. Desde a #827 a Produção pergunta em `/production/session/`: a conta de
  // uma estação AUTÔNOMA (painel de parede, sem ninguém para digitar PIN) só é
  // resolvida sob o prefixo da Produção, porque o cookie de estação vale no
  // domínio inteiro e esse corte é o que impede a conta do painel de virar
  // operador no PDV da aba ao lado. A compartilhada segue valendo para os apps
  // atendidos.
  //
  // O dublê precisa responder às DUAS. Conhecendo só a compartilhada, a pergunta
  // da Produção atravessava este bloco e caía no 403 genérico de estação travada
  // logo abaixo: a tela lia "erro", não "travado", e a tela de PIN nunca subia.
  if (/\/(operator|production)\/session\/?(\?|$)/.test(url)) {
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
  const populatedBody = populated ? populatedResponse(url) : null;
  if (populatedBody) return json(res, 200, populatedBody);
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

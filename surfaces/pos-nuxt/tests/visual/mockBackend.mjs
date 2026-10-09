import { createServer } from "node:http";

const port = Number(process.env.MOCK_PORT || 38792);

const card = (overrides = {}) => ({
  ref: "NB-1042",
  channel_display_id: "1042",
  customer_name: "Ana Souza",
  channel_ref: "web",
  channel_label: "Loja online",
  fulfillment_type: "pickup",
  fulfillment_label: "Retirada",
  commitment_date: "2026-09-29",
  commitment_date_display: "hoje",
  window_label: "12h às 13h",
  window_start: "12:00",
  status: "accepted",
  situation: "to_pay",
  situation_label: "A receber",
  payment_state: "to_receive",
  total_q: 8600,
  total_display: "R$ 86,00",
  balance_q: 8600,
  balance_display: "R$ 86,00",
  items_summary: "1× Kit brunch · 2× Croissant",
  items_count: 3,
  ticket_printed: false,
  ...overrides,
});

const orders = [
  card(),
  card({
    ref: "NB-1043",
    customer_name: "Bruno Lima",
    fulfillment_type: "delivery",
    fulfillment_label: "Entrega",
    window_label: "14h às 15h",
    window_start: "14:00",
    situation: "paid",
    situation_label: "Pago",
    payment_state: "paid",
    total_q: 12400,
    total_display: "R$ 124,00",
    balance_q: 0,
    balance_display: "R$ 0,00",
    items_summary: "2× Kibixinha · 1× Suco",
    ticket_printed: true,
  }),
  card({
    ref: "IFOOD-8821",
    customer_name: "Carla · final 4412",
    channel_ref: "ifood",
    channel_label: "iFood",
    fulfillment_type: "delivery",
    fulfillment_label: "Entrega",
    commitment_date: "2026-09-30",
    commitment_date_display: "amanhã",
    window_label: "11h às 12h",
    window_start: "11:00",
    situation: "check_payment",
    situation_label: "Conferir pagamento",
    payment_state: "check",
    total_q: 5900,
    total_display: "R$ 59,00",
    balance_q: null,
    balance_display: "",
    items_summary: "1× Cesta café da manhã",
  }),
];

const days = ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]
  .map((date, index) => {
    const dayOrders = index === 1 ? orders.slice(0, 2) : index === 2 ? orders.slice(2) : [];
    const total = dayOrders.reduce((sum, item) => sum + item.total_q, 0);
    const receive = dayOrders.reduce((sum, item) => sum + (item.balance_q || 0), 0);
    return {
      date,
      date_display: date,
      weekday_display: ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"][index],
      day_display: ["28/09", "29/09", "30/09", "01/10", "02/10", "03/10", "04/10"][index],
      is_today: index === 1,
      orders_count: dayOrders.length,
      total_q: total,
      total_display: `R$ ${(total / 100).toFixed(2).replace(".", ",")}`,
      to_receive_q: receive,
      to_receive_display: `R$ ${(receive / 100).toFixed(2).replace(".", ",")}`,
      orders: dayOrders,
    };
  });

const preorderList = {
  ok: true,
  date_from: "2026-09-28",
  date_to: "2026-10-04",
  today: "2026-09-29",
  max_batch: 200,
  count: orders.length,
  total_q: 26900,
  total_display: "R$ 269,00",
  to_receive_q: 8600,
  to_receive_display: "R$ 86,00",
  days,
};

const pos = {
  products: [],
  collections: [],
  payment_methods: [],
  fulfillment_options: [],
  payment_collections: [],
  checkout: { intent_version: 1, capabilities: { cash_management: { enabled: true } } },
  actions: [],
  has_open_cash_session: true,
  cash_runtime: {},
  terminal_ref: "CAIXA-1",
  terminal_label: "Caixa 1",
  terminal_default_fulfillment_type: "pickup",
  terminal_health_status: "ready",
  terminal_components: [],
  favorite_collection_refs: [],
  delivery_minimum_q: 0,
  delivery_minimum_display: "",
  fiscal_status: "ready",
  fiscal_label: "",
  fiscal_message: "",
  danfe_screen_allowed: false,
  operators: [],
  auto_lock_seconds: 0,
};

// Cenário da prévia (`MOCK_SCENARIO=sale`): o balcão com comandas em uso, produtos e
// uma comanda que abre com itens, para ver a venda inteira (barra da venda, comanda,
// folha de baixo no celular) sem backend. Sem a variável, o mock é o de sempre e as
// fotos das Encomendas não mudam.
const SALE = process.env.MOCK_SCENARIO === "sale";
const brl = (q) => `R$ ${(q / 100).toFixed(2).replace(".", ",")}`;
const PRODUCTS = [
  ["PAO-FRANCES", "Pão francês", 90, "paes"],
  ["CROISSANT", "Croissant", 1150, "viennoiserie"],
  ["PAIN-CHOC", "Pain au chocolat", 1290, "viennoiserie"],
  ["BRIOCHE", "Brioche de manteiga", 1490, "viennoiserie"],
  ["BAGUETE", "Baguete tradicional", 1390, "paes"],
  ["CAFE-COADO", "Café coado", 690, "bebidas"],
  ["CAPPUCCINO", "Cappuccino", 1290, "bebidas"],
  ["SUCO-LARANJA", "Suco de laranja", 1190, "bebidas"],
].map(([sku, name, price_q, collection_ref]) => ({
  sku, name, price_q, price_display: brl(price_q), collection_ref,
  collection_color: "", collection_icon: "", image_url: "", kitchen_station: "",
}));
if (SALE) {
  Object.assign(pos, {
    products: PRODUCTS,
    collections: [
      { ref: "paes", name: "Pães" },
      { ref: "viennoiserie", name: "Viennoiserie" },
      { ref: "bebidas", name: "Bebidas" },
    ],
    payment_methods: [
      { ref: "cash", label: "Dinheiro" },
      { ref: "pix", label: "Pix" },
      { ref: "card", label: "Cartão" },
    ],
    fulfillment_options: [
      { ref: "pickup", label: "Retirada", description: "", requires_address: false },
      { ref: "delivery", label: "Entrega", description: "", requires_address: true },
    ],
    actions: [],
  });
}
const SALE_ITEMS = [
  { line_id: "L-aaaa0001", sku: "CROISSANT", name: "Croissant", price_q: 1150, qty: 2, notes: "" },
  { line_id: "L-aaaa0002", sku: "PAIN-CHOC", name: "Pain au chocolat", price_q: 1290, qty: 1, notes: "" },
  { line_id: "L-aaaa0003", sku: "CAFE-COADO", name: "Café coado", price_q: 690, qty: 2, notes: "" },
];
const tab = (ref, overrides = {}) => ({
  ref, display_ref: ref, session_key: `S-${ref}`, state: "empty", status_label: "Livre",
  status_class: "", customer_name: "", customer_phone: "", item_count: 0, line_count: 0,
  total_display: "", last_touched_display: "", items_preview: "", ...overrides,
});
const TABS = SALE
  ? [
      tab("12", {
        state: "in_use", status_label: "Em uso", customer_name: "Ana Souza", item_count: 5, line_count: 3,
        total_display: brl(5960), last_touched_display: "há 2 min", items_preview: "2 Croissant · 1 Pain au chocolat · 2 Café coado",
        opened_at_display: "09:41",
      }),
      tab("14", { state: "in_use", status_label: "Em uso", item_count: 1, line_count: 1, total_display: brl(1290), items_preview: "1 Cappuccino", opened_at_display: "10:02" }),
      tab("15"), tab("16"), tab("17"), tab("18"),
    ]
  : [];
function tabPayload(ref) {
  const inUse = ref === "12";
  return {
    revision: "rev-1", sales_mode: "counter", session_key: `S-${ref}`, tab_session_key: `S-${ref}`,
    tab_ref: ref, tab_display: ref, tab_number: ref, opened_at_display: "09:41", seating_spot_ref: "", edit_of: "",
    items: inUse ? SALE_ITEMS : [], customer_phone: "", customer_name: inUse ? "Ana Souza" : "", customer_ref: "",
    customer_tax_id: "", customer_email: "", fulfillment_type: "", delivery_address: "",
    delivery_address_structured: {}, delivery_date: "", delivery_time_slot: "", delivery_fee_override_q: null,
  };
}
function review(body) {
  const items = Array.isArray(body?.items) ? body.items : [];
  const subtotal = items.reduce((sum, item) => sum + Number(item.unit_price_q || 0) * Number(item.qty || 0), 0);
  return {
    intent_version: "1", tab_ref: body?.tab_ref || "", subtotal_q: subtotal, subtotal_display: brl(subtotal),
    discount_q: 0, discount_display: brl(0), line_discount_q: 0, line_discount_display: brl(0),
    order_discount_q: 0, order_discount_display: brl(0), delivery_fee_q: 0, delivery_fee_display: brl(0),
    total_q: subtotal, total_display: brl(subtotal), payment_method: "", payment_collection: "",
    tender_total_q: 0, tender_total_display: brl(0), tender_count: 0, tendered_q: 0, tendered_amount_display: brl(0),
    change_q: 0, change_display: brl(0), requires_manager_approval: false, manager_approval_threshold_q: 0,
    approval_reasons: [], lines: [],
  };
}
function readBody(req) {
  return new Promise((resolve) => {
    let raw = "";
    req.on("data", (chunk) => { raw += chunk; });
    req.on("end", () => {
      try { resolve(JSON.parse(raw || "{}")); } catch { resolve({}); }
    });
  });
}

function send(res, status, payload) {
  const body = JSON.stringify(payload);
  res.statusCode = status;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.setHeader("content-length", Buffer.byteLength(body));
  res.setHeader("set-cookie", "csrftoken=visual-csrf; Path=/; SameSite=Lax");
  res.setHeader("x-api-version", "1.0");
  res.end(body);
}

// O detalhe da primeira encomenda: o contrato do `OperatorOrderDetail` no
// contexto "pos", com itens e histórico bastantes para a página rolar.
const preorderDetail = {
  ref: "NB-1042", status: "accepted", status_label: "Aceito", context: "pos",
  actions: [{ ref: "comment", label: "Comentar", enabled: true, reason: "", payload_schema: { base_revision: "rev-c" } }],
  channel_ref: "web", channel_icon: "language", total_display: "R$ 86,00",
  customer_name: "Ana Souza", customer_ref: "C-1", customer_phone: "(43) 99988-7766",
  customer_phone_uri: "tel:+5543999887766", customer_whatsapp_url: "https://wa.me/5543999887766",
  customer_email: "ana.souza.com.um.endereco.comprido@exemplo.com.br",
  customer_relay_phone: "", customer_relay_code: "", customer_relay_expires_at: "",
  fulfillment_type: "pickup", fulfillment_label: "Retirada", schedule_label: "Hoje · 12h às 13h",
  delivery_address: "", delivery_instructions: "", payment_method_label: "Dinheiro na retirada",
  payment_status_label: "Pendente", payment_link_notice: "", test_order_notice: "",
  is_gift: false, gift_recipient_name: "", gift_recipient_phone: "", gift_message: "", gift_hide_values: false,
  customer_profile: null, fiscal_status_label: "", fiscal_links: [],
  items: Array.from({ length: 12 }, (_, i) => ({
    sku: `SKU-${i}`, name: i === 0 ? "Kit brunch para dois com croissant, geleia e suco" : `Croissant ${i}`,
    qty: "1", unit_price_display: "R$ 7,00", total_display: "R$ 7,00",
  })),
  customer_note: "Sem açúcar no suco, por favor.", kitchen_note: "", timeline: [
    { event_type: "created", label: "Pedido criado", timestamp_display: "29/09 às 09:12", actor: "Loja online", detail: "" },
  ],
  counter: {
    card: card(), ticket_printed: false, revision: "rev-1", actor_id: 7,
    hand_over: {
      allowed: true, needs_payment: true, amount_q: 8600, amount_display: "R$ 86,00",
      suggested_method: "cash", block_reason: "", digital_charge_notice: "",
    },
    cancel: { allowed: true, requires_approval: false, block_reason: "" },
    reschedule: { allowed: true, block_reason: "", date: "2026-09-29", slot: "slot-12", skus: ["SKU-0"], revision: "rev-s" },
    edit: { allowed: true, block_reason: "", cancel_and_redo: false, revision: "rev-e" },
  },
  managers: [],
  cancellation_presets: [],
};

// PDV › Ajustes (`/api/v1/backstage/pos/settings/`): as quatro abas leem a mesma
// resposta. Sem ela o mock devolvia `{}` e Impressoras caía em erro de página.
const settings = {
  terminal_ref: "CAIXA-1",
  terminal_label: "Caixa 1",
  printers: [
    { terminal_ref: "CAIXA-1", label: "Caixa 1", location: "Balcão", roll_width_mm: 80, cut_mode: "partial", stations: ["Bebidas"] },
    { terminal_ref: "CAIXA-2", label: "Caixa 2", location: "Salão", roll_width_mm: 58, cut_mode: "full", stations: [] },
  ],
  roll_widths: [58, 80],
  cut_modes: [
    { value: "partial", label: "Parcial" },
    { value: "full", label: "Total" },
    { value: "none", label: "Sem corte" },
  ],
  card_machines: [
    { ref: "MAQ-1", label: "Maquininha 1", identification: "SN 0041", active: true, with_order: "" },
    { ref: "MAQ-2", label: "Maquininha 2", identification: "SN 0042", active: true, with_order: "1043" },
    { ref: "MAQ-3", label: "Maquininha 3", identification: "SN 0043", active: false, with_order: "" },
  ],
  kitchen_stations: [
    { ref: "forno", name: "Forno", type: "prep", type_label: "Preparo", collections: ["Salgados"], print_terminal: "", auto_fire: true },
    { ref: "bebidas", name: "Bebidas", type: "prep", type_label: "Preparo", collections: ["Cafés", "Sucos"], print_terminal: "Caixa 1", auto_fire: false },
  ],
  shortcuts: {
    favorite_collection_refs: ["cafes", "paes"],
    collections: [
      { ref: "cafes", name: "Cafés" },
      { ref: "paes", name: "Pães" },
      { ref: "doces", name: "Doces" },
      { ref: "salgados", name: "Salgados" },
      { ref: "sucos", name: "Sucos" },
    ],
  },
};

// PDV › Ajustes › Salão (`/api/v1/backstage/pos/seating/`): duas áreas, uma mesa extra.
const seatingSpot = (ref, label, area, shape, seats, x, y, counts = true) => ({
  ref, label, short_label: "", area, kind: "table", shape, seats, counts_in_capacity: counts,
  plan_x: x, plan_y: y, rotation: 0, since: null, since_label: "sempre", born_today: false,
});
const seating = {
  today: "2026-09-29",
  today_label: "29/09",
  revision: "rev-salao-1",
  spots: [
    seatingSpot("M1", "Mesa 1", "Salão", "round", 2, 80, 80),
    seatingSpot("M2", "Mesa 2", "Salão", "square", 4, 220, 80),
    seatingSpot("M3", "Mesa 3", "Salão", "long", 6, 380, 80),
    seatingSpot("M4", "Mesa 4", "Varanda", "square", 4, 80, 260),
    seatingSpot("M5", "Mesa 5", "Varanda", "round", 2, 220, 260, false),
    seatingSpot("B1", "Banqueta 1", "Balcão", "stool", 1, 380, 260),
  ],
  totals: { capacity_seats: 17, capacity_spots: 5, extra_seats: 2 },
  shapes: [
    { value: "round", label: "Redonda" },
    { value: "square", label: "Quadrada" },
    { value: "long", label: "Comprida" },
    { value: "stool", label: "Banqueta" },
  ],
  max_seats: 12,
  history: [
    { id: 1, at: "2026-09-28T10:00:00Z", at_label: "28/09 10:00", who: "Ana", ref: "M5", action: "update", summary: "Mesa 5 virou extra de dia cheio", before: null, after: null },
  ],
  open_tabs: { M2: { session_key: "s-12", tab_ref: "12", tab_display: "Comanda 12" } },
  fixtures: [],
  fixture_kinds: [
    { value: "showcase", label: "Vitrine e caixa" },
    { value: "entrance", label: "Entrada" },
  ],
};

createServer((req, res) => {
  const url = new URL(req.url || "/", `http://127.0.0.1:${port}`);
  const path = url.pathname;

  if (path === "/api/v1/backstage/operator/session/") {
    send(res, 200, {
      station: "CAIXA-1",
      operator: { id: 7, username: "ana", name: "Ana" },
      locked: false,
      pin_must_change: false,
      authorized: true,
    });
    return;
  }
  if (path === "/api/v1/backstage/pos/") {
    send(res, 200, { pos, shift: null, tabs: TABS, operator: { id: 7, name: "Ana" } });
    return;
  }
  if (SALE) {
    const open = path.match(/^\/api\/v1\/backstage\/pos\/tabs\/([^/]+)\/open\/$/);
    if (open) {
      send(res, 200, tabPayload(decodeURIComponent(open[1])));
      return;
    }
    if (path === "/api/v1/backstage/pos/tabs/save/") {
      void readBody(req).then((body) => send(res, 200, { ...tabPayload(body?.tab_ref || "12"), items: body?.items || [] }));
      return;
    }
    if (path === "/api/v1/backstage/pos/sale/review/") {
      void readBody(req).then((body) => send(res, 200, { ok: true, review: review(body) }));
      return;
    }
  }
  if (path === "/api/v1/backstage/pos/preorders/search/") {
    send(res, 200, {
      ok: true,
      query: url.searchParams.get("q") || "Ana",
      today: "2026-09-29",
      include_completed: false,
      completed_days: 30,
      open_count: 1,
      open: [orders[0]],
      completed_count: 0,
      completed: [],
    });
    return;
  }
  // O detalhe de uma encomenda (S5: o painel do Balcão nos cinco tamanhos).
  if (path === "/api/v1/backstage/pos/preorders/NB-1042/") {
    send(res, 200, { order: preorderDetail, generated_at: "2026-09-29T12:00:00Z", contract_version: 1 });
    return;
  }
  if (path === "/api/v1/backstage/pos/preorders/") {
    send(res, 200, preorderList);
    return;
  }
  if (path === "/api/v1/backstage/pos/settings/") {
    send(res, 200, settings);
    return;
  }
  if (path === "/api/v1/backstage/pos/seating/") {
    send(res, 200, seating);
    return;
  }
  if (path.includes("/events/")) {
    res.statusCode = 204;
    res.end();
    return;
  }
  send(res, 200, {});
}).listen(port, "127.0.0.1", () => {
  console.log(`[pos-visual-mock] listening on http://127.0.0.1:${port}`);
});

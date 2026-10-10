import { createServer } from "node:http";

const port = Number(process.env.MOCK_PORT || 38792);

// O DIA do mock. A prévia roda no relógio de verdade (o Período da tela parte da data
// do dispositivo, e o mock tem de responder pelo mesmo período: "Semana · 05/10 a
// 11/10" com os cartões de 28/09 mentia). Os retratos fixam o dia (`MOCK_TODAY` no
// `playwright.visual.config.ts`, com o relógio do navegador parado no mesmo dia).
const localIso = (date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const TODAY = /^\d{4}-\d{2}-\d{2}$/.test(process.env.MOCK_TODAY || "") ? process.env.MOCK_TODAY : localIso(new Date());
const dateOf = (iso) => {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d, 12);
};
const addDays = (iso, n) => {
  const date = dateOf(iso);
  date.setDate(date.getDate() + n);
  return localIso(date);
};
const mondayOf = (iso) => addDays(iso, -((dateOf(iso).getDay() + 6) % 7));
const ddmm = (iso) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
const TOMORROW = addDays(TODAY, 1);

const card = (overrides = {}) => ({
  ref: "NB-1042",
  // Só o iFood tem número de canal, e só quando o ref não o carrega
  // (`_channel_display_id`): na loja online é vazio, senão a linha diria "iFood #1042".
  channel_display_id: "",
  customer_name: "Ana Souza",
  channel_ref: "web",
  channel_label: "Loja online",
  fulfillment_type: "pickup",
  fulfillment_label: "Retirada",
  commitment_date: TODAY,
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
    commitment_date: TOMORROW,
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

// O período pedido, como o servidor lê (`parse_range`): `?week=2026-W41` (a semana ISO,
// de segunda a domingo) ou `date_from`/`date_to`; sem nada, a semana de hoje.
function weekMonday(raw) {
  const match = /^(\d{4})-W(\d{2})$/.exec(raw || "");
  if (!match) return "";
  const jan4 = localIso(new Date(Number(match[1]), 0, 4, 12));
  return addDays(mondayOf(jan4), (Number(match[2]) - 1) * 7);
}
function requestedRange(params) {
  const monday = weekMonday(params.get("week"));
  if (monday) return [monday, addDays(monday, 6)];
  const iso = /^\d{4}-\d{2}-\d{2}$/;
  const from = params.get("date_from");
  const to = params.get("date_to");
  if (iso.test(from || "")) return [from, iso.test(to || "") && to >= from ? to : from];
  return [mondayOf(TODAY), addDays(mondayOf(TODAY), 6)];
}
const WEEKDAYS = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
function preorderList(params) {
  const [dateFrom, dateTo] = requestedRange(params);
  const days = [];
  for (let date = dateFrom; date <= dateTo && days.length < 62; date = addDays(date, 1)) {
    const dayOrders = orders.filter((order) => order.commitment_date === date);
    const total = dayOrders.reduce((sum, item) => sum + item.total_q, 0);
    const receive = dayOrders.reduce((sum, item) => sum + (item.balance_q || 0), 0);
    days.push({
      date,
      date_display: date,
      weekday_display: WEEKDAYS[dateOf(date).getDay()],
      day_display: ddmm(date),
      is_today: date === TODAY,
      orders_count: dayOrders.length,
      total_q: total,
      total_display: brl(total),
      to_receive_q: receive,
      to_receive_display: brl(receive),
      orders: dayOrders,
    });
  }
  const shown = days.flatMap((day) => day.orders);
  const total = shown.reduce((sum, item) => sum + item.total_q, 0);
  const receive = shown.reduce((sum, item) => sum + (item.balance_q || 0), 0);
  return {
    ok: true,
    date_from: dateFrom,
    date_to: dateTo,
    today: TODAY,
    max_batch: 200,
    count: shown.length,
    total_q: total,
    total_display: brl(total),
    to_receive_q: receive,
    to_receive_display: brl(receive),
    days,
  };
}

const pos = {
  // O dia da LOJA (`pos.delivery_today`): as Encomendas abrem nele, não no relógio do navegador.
  delivery_today: TODAY,
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
  // Nomes compridos de verdade (o cartão reserva duas linhas e corta a terceira; a
  // comanda quebra a linha) e itens que vão à cozinha (o "Enviar à cozinha" acende).
  ["CROQUE-MONSIEUR", "Croque Monsieur com salada verde e molho de mostarda Dijon", 3890, "cozinha", "Cozinha"],
  ["QUICHE", "Quiche Lorraine", 2490, "cozinha", "Cozinha"],
  ["TARTINE", "Tartine de cogumelos", 3290, "cozinha", "Cozinha"],
].map(([sku, name, price_q, collection_ref, kitchen_station = ""]) => ({
  sku, name, price_q, price_display: brl(price_q), collection_ref,
  collection_color: "", collection_icon: "", image_url: "", kitchen_station,
}));
if (SALE) {
  Object.assign(pos, {
    products: PRODUCTS,
    collections: [
      { ref: "paes", name: "Pães" },
      { ref: "viennoiserie", name: "Viennoiserie" },
      { ref: "bebidas", name: "Bebidas" },
      { ref: "cozinha", name: "Pratos da cozinha" },
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
    actions: [
      { ref: "fire_tab", kind: "mutation", label: "Enviar à cozinha", enabled: true, reason: "", method: "POST", href: "/api/v1/backstage/pos/tabs/fire/" },
      { ref: "unfire_tab", kind: "mutation", label: "Cancelar envio à cozinha", enabled: true, reason: "", method: "POST", href: "/api/v1/backstage/pos/tabs/unfire/" },
    ],
  });
}
// `MOCK_DIRECT=1`: o balcão vende SEM comanda (venda de balcão direta) e recebe
// na maquininha. É o cenário da venda sem conexão (WP-PDV-SEM-CONEXAO): só a venda
// direta segue sem rede. Sem a variável, nada muda nos retratos.
const DIRECT = SALE && process.env.MOCK_DIRECT === "1";
if (DIRECT) {
  pos.checkout.capabilities.tab_lifecycle = { requires_open_tab_for_cart: false, requires_tab_before_save: false };
  pos.payment_methods = [
    { ref: "cash", label: "Dinheiro" },
    { ref: "pix", label: "Pix" },
    { ref: "credit", label: "Crédito" },
    { ref: "debit", label: "Débito" },
  ];
  pos.payment_collections = [
    { ref: "terminal", label: "No caixa", description: "", fulfillment_types: ["pickup", "delivery"], payment_method_refs: ["cash", "pix", "credit", "debit"] },
  ];
}
// Os fechamentos recebidos, para o e2e conferir o que a fila reenviou
// (`GET /__mock/closes`). A chave é o `client_request_id`: repetir devolve o
// mesmo pedido, como o servidor de verdade.
const CLOSES = [];
const ORDER_BY_KEY = new Map();

// O caixa do cenário da venda: turno aberto, que audita, com uma pendência de cada
// natureza, para a Sessão de caixa, o Fim do dia e o Relatório terem o que mostrar.
// `MOCK_DAY_CLOSED=1` serve o dia já fechado (o quadro do dia, com as tabelas).
const DAY_CLOSED = process.env.MOCK_DAY_CLOSED === "1";
if (SALE) {
  pos.checkout.capabilities.cash_management = {
    enabled: true,
    movement_kinds: ["sangria", "suprimento"],
    movement_reasons: { sangria: ["Cofre", "Pagamento a fornecedor"], suprimento: ["Troco do cofre"] },
    change_denominations: [
      { q: 1000, label: "10", shape: "note" }, { q: 500, label: "5", shape: "note" },
      { q: 100, label: "1", shape: "coin" }, { q: 50, label: "0,50", shape: "coin" },
    ],
  };
  pos.cash_runtime = {
    has_open_shift: true, shift_id: 31, terminal_ref: "CAIXA-1", terminal_label: "Caixa 1",
    operator_username: "ana", opened_at: "2026-09-29T07:02:00-03:00", status: "open",
    can_audit_cash: true, default_float_q: 20000, default_float_display: "R$ 200,00",
    pending_change_requests: [
      { ref: "CR-1", amount_q: 10000, amount_display: "R$ 100,00", denominations: [1000, 500], note: "", requested_by: "Ana", requested_at: "2026-09-29T10:12:00-03:00" },
    ],
    pending_cash_refunds: [],
    pending_card_machine_refunds: [],
    account_balances: [
      { customer_ref: "C-9", customer_name: "Carlos Mendes", balance_q: 4200, balance_display: "R$ 42,00", intents: 2, oldest_at: "" },
    ],
  };
}
const reading = (overrides = {}) => ({
  shift_id: 31, status: "open", terminal_ref: "CAIXA-1", terminal_label: "Caixa 1", operator: "Ana",
  opened_at: "2026-09-29T07:02:00-03:00", closed_at: "", opening_amount_q: 20000, opening_amount_display: "200,00",
  counted_amount_q: null, counted_amount_display: "",
  movements: [
    { entry_id: 91, kind: "sangria", kind_label: "Saída de caixa", amount_q: 30000, amount_display: "300,00", reason: "Cofre", created_by: "Ana", created_at: "" },
    { entry_id: 92, kind: "suprimento", kind_label: "Entrada de caixa", amount_q: 5000, amount_display: "50,00", reason: "Troco do cofre", created_by: "Ana", created_at: "" },
  ],
  movements_in_q: 5000, movements_in_display: "50,00", movements_out_q: 30000, movements_out_display: "300,00",
  sales_count: 42, sales_total_q: 186450, sales_total_display: "1.864,50",
  sales_by_method: [
    { method: "cash", method_label: "Dinheiro", orders_count: 18, amount_q: 61200, amount_display: "612,00" },
    { method: "pix", method_label: "Pix", orders_count: 15, amount_q: 70350, amount_display: "703,50" },
    { method: "card", method_label: "Cartão", orders_count: 9, amount_q: 54900, amount_display: "549,00" },
  ],
  notes: "",
  ...overrides,
});
const cashReport = {
  date: "2026-09-29", date_display: "29/09/2026", has_open_shift: true,
  x_reading: reading(),
  z_readings: [reading({ shift_id: 30, status: "closed", operator: "Bruno", opened_at: "2026-09-28T13:00:00-03:00", closed_at: "2026-09-28T21:04:00-03:00", counted_amount_q: 48210, counted_amount_display: "482,10", movements: [], notes: "Nota de 50 rasgada separada." })],
  has_closed_shifts: true,
  day_totals: {
    shifts_count: 1, sales_count: 37, sales_total_q: 151230, sales_total_display: "1.512,30",
    counted_total_q: 48210, counted_total_display: "482,10",
    sales_by_method: [
      { method: "cash", method_label: "Dinheiro", orders_count: 16, amount_q: 48210, amount_display: "482,10" },
      { method: "pix", method_label: "Pix", orders_count: 21, amount_q: 103020, amount_display: "1.030,20" },
    ],
  },
};
const dayClosing = {
  today: "2026-09-29", today_display: "29/09", operator_display: "Ana · gerência",
  items: [
    ["BAGUETE", "Baguete tradicional", "keep"], ["BRIOCHE", "Brioche de manteiga", "mixed"],
    ["CROISSANT", "Croissant", "expired"], ["PAIN-CHOC", "Pain au chocolat", "expired"], ["PAO-FRANCES", "Pão francês", "keep"],
  ].map(([sku, name, classification]) => ({ sku, name, classification })),
  has_items: true, already_closed: DAY_CLOSED,
  existing_closing_display: DAY_CLOSED ? "Fechado às 19:40 por Ana" : "",
  production_summary: DAY_CLOSED ? {
    CROISSANT: { recipe_ref: "r-cro", output_sku: "CROISSANT", planned: 120, finished: 118, loss: 2 },
    BAGUETE: { recipe_ref: "r-bag", output_sku: "BAGUETE", planned: 60, finished: 60, loss: 0 },
  } : undefined,
  reconciliation_errors: DAY_CLOSED ? [{ sku: "PAIN-CHOC", sold_qty: 40, available_qty: 37, deficit_qty: 3 }] : [],
  pending_production: [{
    ref: "WO-042", output_sku: "BAGUETE", recipe_name: "Baguete", status: "started", status_label: "Iniciada",
    quantity: "80", target_date: "2026-09-28", target_date_display: "28/09", is_overdue: true,
  }],
  has_pending_production: true,
  upcoming_preorders: [{ date: "2026-09-30", date_display: "30/09", orders_count: 3 }, { date: "2026-10-01", date_display: "01/10", orders_count: 1 }],
  has_upcoming_preorders: true,
  pending_episodes: [], episode_options: [], has_pending_episodes: false,
};
const SALE_ITEMS = [
  { line_id: "L-aaaa0001", sku: "CROISSANT", name: "Croissant", price_q: 1150, qty: 2, notes: "" },
  { line_id: "L-aaaa0002", sku: "PAIN-CHOC", name: "Pain au chocolat", price_q: 1290, qty: 1, notes: "" },
  { line_id: "L-aaaa0003", sku: "CAFE-COADO", name: "Café coado", price_q: 690, qty: 2, notes: "" },
];
// A comanda CHEIA (13): nove linhas, nomes compridos, uma já na cozinha e três que
// esperam o envio. É o retrato da coluna da comanda apertada (pedido do dono, 10/10).
const FULL_ITEMS = [
  { line_id: "L-bbbb0001", sku: "CROQUE-MONSIEUR", name: "Croque Monsieur com salada verde e molho de mostarda Dijon", price_q: 3890, qty: 1, notes: "Sem mostarda", fired: true, fired_qty: 1, kitchen_status: "in_progress" },
  { line_id: "L-bbbb0002", sku: "CROISSANT", name: "Croissant", price_q: 1150, qty: 2, notes: "" },
  { line_id: "L-bbbb0003", sku: "PAIN-CHOC", name: "Pain au chocolat", price_q: 1290, qty: 1, notes: "" },
  { line_id: "L-bbbb0004", sku: "CAFE-COADO", name: "Café coado", price_q: 690, qty: 2, notes: "" },
  { line_id: "L-bbbb0005", sku: "QUICHE", name: "Quiche Lorraine", price_q: 2490, qty: 1, notes: "" },
  { line_id: "L-bbbb0006", sku: "CAPPUCCINO", name: "Cappuccino", price_q: 1290, qty: 1, notes: "" },
  { line_id: "L-bbbb0007", sku: "TARTINE", name: "Tartine de cogumelos", price_q: 3290, qty: 1, notes: "" },
  { line_id: "L-bbbb0008", sku: "SUCO-LARANJA", name: "Suco de laranja", price_q: 1190, qty: 1, notes: "" },
  { line_id: "L-bbbb0009", sku: "CROQUE-MONSIEUR", name: "Croque Monsieur com salada verde e molho de mostarda Dijon", price_q: 3890, qty: 1, notes: "" },
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
      tab("13", {
        state: "in_use", status_label: "Em uso", customer_name: "Roberto Albuquerque", item_count: 11, line_count: 9,
        total_display: brl(FULL_ITEMS.reduce((sum, item) => sum + item.price_q * item.qty, 0)), last_touched_display: "agora",
        items_preview: "1 Croque Monsieur · 2 Croissant · 1 Pain au chocolat", opened_at_display: "09:55",
      }),
      tab("15"), tab("16"), tab("17"), tab("18"),
    ]
  : [];
// O que a prévia salvou em cada comanda volta na reabertura (ir ao pagamento relê a
// comanda): sem isto, a venda de uma comanda livre chegava vazia ao pagamento.
const SAVED_ITEMS = new Map();
function tabPayload(ref) {
  const inUse = ref === "12";
  const full = ref === "13";
  const saved = SAVED_ITEMS.get(ref);
  return {
    revision: "rev-1", sales_mode: "counter", session_key: `S-${ref}`, tab_session_key: `S-${ref}`,
    tab_ref: ref, tab_display: ref, tab_number: ref, opened_at_display: "09:41", seating_spot_ref: "", edit_of: "",
    items: saved ?? (inUse ? SALE_ITEMS : full ? FULL_ITEMS : []), customer_phone: "",
    // Cliente com cadastro (`customer_ref`): nome sem ref é RASCUNHO de cliente, e a
    // tela segura o salvamento ("Não salvo") até alguém concluir o cadastro.
    customer_name: inUse ? "Ana Souza" : full ? "Roberto Albuquerque" : "",
    customer_ref: inUse ? "C-1" : full ? "C-13" : "",
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
    { event_type: "created", label: "Pedido criado", timestamp_display: `${ddmm(TODAY)} às 09:12`, actor: "Loja online", detail: "" },
  ],
  counter: {
    card: card(), ticket_printed: false, revision: "rev-1", actor_id: 7,
    hand_over: {
      allowed: true, needs_payment: true, amount_q: 8600, amount_display: "R$ 86,00",
      suggested_method: "cash", block_reason: "", digital_charge_notice: "",
    },
    cancel: { allowed: true, requires_approval: false, block_reason: "" },
    reschedule: { allowed: true, block_reason: "", date: TODAY, slot: "slot-12", skus: ["SKU-0"], revision: "rev-s" },
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

  if (path === "/__mock/closes") {
    send(res, 200, { closes: CLOSES });
    return;
  }
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
  if (SALE && path === "/api/v1/backstage/closing/") {
    send(res, 200, { closing: dayClosing });
    return;
  }
  if (SALE && path === "/api/v1/backstage/pos/cash/report/") {
    send(res, 200, { report: cashReport });
    return;
  }
  if (SALE) {
    const open = path.match(/^\/api\/v1\/backstage\/pos\/tabs\/([^/]+)\/open\/$/);
    if (open) {
      send(res, 200, tabPayload(decodeURIComponent(open[1])));
      return;
    }
    if (path === "/api/v1/backstage/pos/tabs/save/") {
      void readBody(req).then((body) => {
        const ref = body?.tab_ref || "12";
        // O estado da cozinha (enviado, preparando) é do servidor: salvar não o apaga.
        const before = SAVED_ITEMS.get(ref) ?? tabPayload(ref).items;
        const items = (body?.items || []).map((item) => ({
          ...(before.find((prev) => prev.line_id === item.line_id) || {}),
          line_id: item.line_id, sku: item.sku, name: item.name, qty: item.qty, price_q: item.unit_price_q, notes: item.notes || "",
        }));
        SAVED_ITEMS.set(ref, items);
        send(res, 200, { ...tabPayload(ref), items });
      });
      return;
    }
    if (path === "/api/v1/backstage/pos/sale/review/") {
      void readBody(req).then((body) => send(res, 200, { ok: true, review: review(body) }));
      return;
    }
    // Pagar fecha a venda: o pedido nasce. Com `MOCK_CLOSE=uncertain` a resposta não
    // prova o pedido, e a trava contra cobrança duplicada acende (o aviso do
    // cabeçalho e a caixa "Conferir a venda").
    if (path === "/api/v1/backstage/pos/sale/close/") {
      void readBody(req).then((body) => {
        if (process.env.MOCK_CLOSE === "uncertain") return send(res, 200, {});
        SAVED_ITEMS.delete(body?.tab_ref || "");
        CLOSES.push(body);
        const key = String(body?.client_request_id || "");
        if (key && !ORDER_BY_KEY.has(key)) ORDER_BY_KEY.set(key, `NB-${2001 + ORDER_BY_KEY.size}`);
        const orderRef = ORDER_BY_KEY.get(key) || "NB-2001";
        send(res, 200, { ok: true, order_ref: orderRef, tab_ref: body?.tab_ref || "12", fiscal_expected: false });
      });
      return;
    }
  }
  if (path === "/api/v1/backstage/pos/preorders/search/") {
    send(res, 200, {
      ok: true,
      query: url.searchParams.get("q") || "Ana",
      today: TODAY,
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
    send(res, 200, { order: preorderDetail, generated_at: `${TODAY}T12:00:00Z`, contract_version: 1 });
    return;
  }
  if (path === "/api/v1/backstage/pos/preorders/") {
    send(res, 200, preorderList(url.searchParams));
    return;
  }
  // Os favoritos do balcão: na prévia (`sale`), um fixado no fim da faixa de filtros
  // rápidos das Encomendas; sem a variável, nenhum (as fotos não mudam).
  if (path === "/api/v1/backstage/saved-views/") {
    const views = SALE && url.searchParams.get("screen") === "preorders"
      ? [{ id: 1, surface: "pos", screen: "preorders", name: "Entregas a receber", query: { filters: { fulfillment: ["delivery"], pay: ["to_receive"] } }, pinned: true }]
      : [];
    send(res, 200, { views });
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

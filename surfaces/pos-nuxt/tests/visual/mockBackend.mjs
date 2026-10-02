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
    send(res, 200, { pos, shift: null, tabs: [], operator: { id: 7, name: "Ana" } });
    return;
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
  if (path.includes("/events/")) {
    res.statusCode = 204;
    res.end();
    return;
  }
  send(res, 200, {});
}).listen(port, "127.0.0.1", () => {
  console.log(`[pos-visual-mock] listening on http://127.0.0.1:${port}`);
});

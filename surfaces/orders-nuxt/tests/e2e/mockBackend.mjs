// Mock backend mínimo p/ os e2e do Gestor: sessão de operador AUTENTICADA (sem lock) +
// uma fila com um card, para o board renderizar. Não simula permissões/ações reais — o
// login efetivo, o lock (Opção C) e as ações rodam contra o Django real (reviewer local).
import { createServer } from "node:http";

const port = Number(process.env.MOCK_PORT || 8796);

// Sessão autenticada e destravada → o shell passa dos gates e mostra o board.
// Uma identidade: `locked` é literalmente "não há operador", então um mock com
// `operator: null, locked: false` descreve um estado que o servidor não produz.
const SESSION = { station: "balcao", operator: { id: 1, username: "admin", name: "Admin" }, locked: false, pin_must_change: false };

const CARD = {
  ref: "WEB-20260625-0007",
  status: "accepted",
  revisions: { advance: "fixture-base" },
  actions: [{ ref: "advance", kind: "mutation", label: "Iniciar preparo", priority: "primary", enabled: true, reason: "", href: "", method: "POST", payload_schema: { target_status: "preparing", base_revision: "fixture-base" }, idempotency: "required", confirmation: {} }],
  status_label: "Aceito",
  status_color: "",
  channel_ref: "web",
  channel_icon: "language",
  customer_name: "Ana",
  created_at_display: "08:00",
  created_at_iso: "",
  server_now_iso: "",
  elapsed_seconds: 30,
  timer_class: "timer-ok",
  items_summary: "2× Pão · 1× Café",
  items_count: 3,
  total_display: "R$ 15,00",
  fulfillment_icon: "storefront",
  fulfillment_label: "Retirada",
  fulfillment_type: "pickup",
  can_confirm: false,
  can_advance: true,
  next_status: "preparing",
  next_action_label: "Iniciar preparo",
  payment_method: "cash",
  payment_method_label: "Dinheiro",
    ifood_cancellation_notice: "",
    ifood_payment_summary: [],
    ifood_operation_summary: [],
    ifood_negotiations: [],
  payment_status: "pending",
  payment_pending: true,
  can_settle_delivery_cash: false,
  fiscal_status_label: "",
  fiscal_status: "",
  has_kitchen_note: false,
  has_customer_note: false,
  is_gift: false,
  gift_has_recipient: false,
  assigned_operator: "",
  awaiting_work_orders: [],
  confirmation_deadline_iso: "",
  confirmation_action: "confirm",
  // A Fila (V4-G4): o fato humano que o pedido espera e a meta da etapa.
  attention: "start",
  attention_since_iso: new Date(Date.now() - 3 * 60_000).toISOString(),
  goal_minutes: 5,
  goal_label: "meta 5",
};

const QUEUE = {
  queue: {
    intake: [],
    preparing_count: 3,
    prep: [CARD, {
      ...CARD,
      ref: "WEB-BLOCKED",
      customer_name: "Pagamento pendente",
      items_summary: "0.5× Pesado",
      total_display: "R$ 3,00",
      actions: [{ ...CARD.actions[0], enabled: false, label: "Aguardando pagamento", reason: "O pagamento ainda não foi capturado." }],
      can_advance: false,
      next_status: "",
      payment_method: "link",
      advance_block_label: "Aguardando pagamento",
      advance_block_reason: "O pagamento ainda não foi capturado.",
      attention: "blocked",
      attention_since_iso: new Date(Date.now() - 8 * 60_000).toISOString(),
    }, {
      ...CARD,
      ref: "IFOOD-SCHEDULED",
      channel_ref: "ifood",
      fulfillment_type: "delivery",
      fulfillment_label: "Entrega",
      fulfillment_icon: "truck",
      channel_icon: "restaurant",
      customer_name: "Pedido iFood agendado",
      items_summary: "1× Pão de teste",
      total_display: "R$ 16,00",
      payment_method: "external",
      payment_method_label: "iFood",
      payment_status: "paid",
      payment_pending: false,
      ifood_payment_summary: ["Pago no iFood: R$ 16,00"],
      ifood_operation_summary: ["Entrega por entregador iFood", "Pedido agendado no iFood", "Início do preparo: 14/09/2026 às 15:15", "Início da janela: 14/09/2026 às 16:00", "Fim da janela: 14/09/2026 às 16:30"],
      actions: [{ ...CARD.actions[0], enabled: false, label: "Aguardando horário iFood", reason: "O horário de preparo do iFood ainda não permite avançar." }],
      can_advance: false,
      next_status: "",
      advance_block_label: "Aguardando horário iFood",
      advance_block_reason: "O horário de preparo do iFood ainda não permite avançar.",
      attention: "",
      attention_since_iso: "",
      goal_minutes: 0,
      goal_label: "",
    }],
    expedition_pickup: [],
    expedition_delivery: [],
    expedition_delivery_transit: [],
    expedition_delivery_count: 0,
    expedition_count: 0,
    total_count: 3,
    ifood_negotiation_orders: [],
    awareness: {
      system_actions: [{ order_ref: "WEB-20260625-0003", verb: "Aceito", reason: "prazo de confirmação", at_iso: new Date().toISOString(), at_display: "21:52", undo_action: "", undo_until_iso: "" }],
      system_window_minutes: 15,
      menu_outages: [{ sku: "BICHON", name: "Bichon au Citron", reason: "sold_out", line: "Bichon au Citron esgotado", detail: "fora de Loja online e iFood desde 21:40" }],
      menu_outages_more: 0,
      menu_channels: [{ ref: "ifood", name: "iFood", active: true, line: "iFood recebendo pedidos", focus_path: "/feeds?focus=ifood" }],
      can_open_channels: false,
    },
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

  if (/\/operator\/session\/?(\?|$)/.test(url)) return json(res, 200, SESSION);
  if (/\/operator\/eligible\/?(\?|$)/.test(url)) return json(res, 200, { operators: [] });
  if (/\/orders\/?(\?|$)/.test(url)) return json(res, 200, QUEUE);
  if (/\/alerts\/?(\?|$)/.test(url)) return json(res, 200, { alerts: [], counts: { active: 0, critical: 0 } });
  return json(res, 200, {});
});

server.listen(port, "127.0.0.1", () => {
  // eslint-disable-next-line no-console
  console.log(`[gestor-mock] listening on http://127.0.0.1:${port}`);
});

// Mock backend mínimo p/ os e2e do Gestor: sessão de operador AUTENTICADA (sem lock) +
// uma fila com um card, para o board renderizar. Não simula permissões/ações reais — o
// login efetivo, o lock (Opção C) e as ações rodam contra o Django real (reviewer local).
import { createServer } from "node:http";

const port = Number(process.env.MOCK_PORT || 8796);

// Sessão autenticada e destravada → o shell passa dos gates e mostra o board.
// Uma identidade: `locked` é literalmente "não há operador", então um mock com
// `operator: null, locked: false` descreve um estado que o servidor não produz.
const SESSION = {
  station: "balcao",
  operator: { id: 1, username: "admin", name: "Admin" },
  locked: false,
  pin_must_change: false,
  authorized: true,
  surface_role: "orders",
  landing_path: "/",
};

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
      ref: "WEB-20260625-0008",
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
      ref: "IFOOD-260914-1515",
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
    }, {
      // Em preparo de verdade: o único que conta em "Seguem sozinhos: 1 na cozinha".
      // O iFood agendado acima espera o horário e NÃO foi para a cozinha (GES-13).
      ...CARD,
      ref: "WEB-20260625-0009",
      status: "preparing",
      status_label: "Em preparo",
      customer_name: "Bia",
      items_summary: "3× Croissant",
      total_display: "R$ 24,00",
      items_count: 3,
      actions: [{ ...CARD.actions[0], label: "Marcar pronto", payload_schema: { target_status: "ready", base_revision: "fixture-base" } }],
      next_status: "ready",
      next_action_label: "Marcar pronto",
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
    total_count: 4,
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

// O detalhe de um pedido da fila: o card + o que só o detalhe traz. Sem isto o
// `/<ref>` recebia `{}` e a e2e não alcançava o resumo do iFood, que mora no detalhe.
const DETAIL_EXTRA = {
  customer_phone: "", customer_phone_uri: "", customer_whatsapp_url: "", customer_email: "", customer_ref: "",
  delivery_address: "", delivery_instructions: "",
  items: [{ sku: "PAO", name: "Pão", qty: "1", unit_price_display: "R$ 16,00", total_display: "R$ 16,00" }],
  timeline: [], kitchen_note: "", customer_note: "", fiscal_links: [], equipment_options: [], equipment_out: [],
  kitchen_note_tags: [], customer_profile: null,
  can_cancel: true, cancel_requires_approval: false,
  // A lista única de motivos de recusar e cancelar (`shop/services/cancel_reasons.py`).
  cancel_reasons: [
    { key: "out_of_stock", label: "Acabou um item", customer_text: "Um dos itens acabou e não conseguimos preparar o pedido completo.", offered_on_ifood: true },
    { key: "cannot_deliver", label: "Não dá para entregar", customer_text: "Não conseguimos fazer a entrega no endereço e no horário do pedido.", offered_on_ifood: true },
    { key: "high_demand", label: "Muitos pedidos agora", customer_text: "Estamos com muitos pedidos agora e não conseguiríamos preparar o seu no horário.", offered_on_ifood: true },
    { key: "duplicate_order", label: "Pedido repetido", customer_text: "Recebemos este mesmo pedido duas vezes e seguimos só com o outro.", offered_on_ifood: true },
    { key: "customer_request", label: "O cliente pediu", customer_text: "Conforme sua solicitação.", offered_on_ifood: false },
    { key: "payment_not_confirmed", label: "Pagamento não confirmado", customer_text: "Não recebemos a confirmação do pagamento a tempo.", offered_on_ifood: false },
    { key: "store_closing", label: "A loja vai fechar", customer_text: "Precisamos encerrar o atendimento antes do horário do seu pedido.", offered_on_ifood: true },
    { key: "other", label: "Outro motivo", customer_text: "Sentimos muito pelo imprevisto.", offered_on_ifood: true },
  ],
};

// A seção Entregas: três entregas aguardando e duas corridas na rua (A a caminho da
// loja, B em rota). Sem chave do Google Maps: o mapa é o desenho próprio. O número da
// corrida escolhe a cor; o que a tela escreve é a LETRA (`letter`); a URL leva a chave.
const minutesAgo = (n) => new Date(Date.now() - n * 60_000).toISOString();
const minutesAhead = (n) => new Date(Date.now() + n * 60_000).toISOString();
const ORIGIN = { latitude: -23.3273, longitude: -51.1762 };
function deliveryStop(ref, customer, place, dLat, dLng, extra = {}) {
  return {
    ref, code: ref.slice(-3), customer, place, address: `Rua das Entregas, 100, ${place}`,
    latitude: ORIGIN.latitude + dLat, longitude: ORIGIN.longitude + dLng,
    stage: "Pronto", volumes: 1, done: false, change_out_suggested_q: 0, needs_machine: false,
    change_label: "", group_refusal: "", error: "", dispatch_action: null, ...extra,
  };
}
const RIDE_BASE = {
  driver: null, position: null, called_by: "Admin", pickup_eta_at: "", arrived_pickup_at: "",
  picked_up_at: "", delivery_eta_at: "", tracking_url: "", cost_display: "", bags: 0, undeclared: [],
  back_action: null, back_lines: [], cancel_action: null,
};
const DELIVERIES = {
  origin: ORIGIN,
  waiting: [
    deliveryStop("WEB-20261116-0A47", "Ana", "Gleba Palhano", 0.006, 0.004),
    deliveryStop("WEB-20261116-0C03", "Caio", "Gleba Palhano", 0.008, 0.007, { change_label: "Troco para R$ 50,00", change_out_suggested_q: 2000 }),
    deliveryStop("WEB-20261116-0D12", "Dora", "Centro", -0.007, 0.01, { stage: "Em preparo" }),
  ],
  rides: [
    {
      ...RIDE_BASE,
      key: "776753357", number: 1, letter: "A", state: "coming", status_label: "A caminho da loja",
      stops: [deliveryStop("WEB-20261116-0B12", "Bia", "Jardim Higienópolis", -0.004, -0.008, { volumes: 2 })],
      driver: { name: "Diego", phone: "(43) 99999-0001", vehicle: "Moto prata · ABC1D23" },
      position: { latitude: ORIGIN.latitude + 0.003, longitude: ORIGIN.longitude - 0.003 },
      called_at: minutesAgo(9), pickup_eta_at: minutesAhead(4), cost_display: "R$ 9,00", bags: 2,
      // Link só em corrida de uma parada: com várias, o servidor não prova de quem é.
      tracking_url: "https://rastreio.example/776753357",
      lead_ref: "WEB-20261116-0B12",
    },
    {
      ...RIDE_BASE,
      key: "776753358", number: 2, letter: "B", state: "route", status_label: "Em rota",
      stops: [
        deliveryStop("WEB-20261116-0E02", "Edu", "Aeroporto", 0.004, -0.012, { done: true }),
        deliveryStop("WEB-20261116-0F09", "Flora", "Aeroporto", 0.009, -0.015),
      ],
      driver: { name: "Marina", phone: "(43) 99999-0002", vehicle: "Moto preta · XYZ9K88" },
      position: { latitude: ORIGIN.latitude + 0.006, longitude: ORIGIN.longitude - 0.013 },
      called_at: minutesAgo(28), picked_up_at: minutesAgo(12), delivery_eta_at: minutesAhead(11),
      cost_display: "R$ 14,50",
      lead_ref: "WEB-20261116-0E02",
    },
  ],
  max_stops: 4,
  // Os números livres vêm do servidor: 1 e 2 estão na rua, sobram 3 a 26 (C a Z).
  free_numbers: Array.from({ length: 24 }, (_, i) => i + 3),
  next_number: 3,
  machines: [],
  courier_on: true,
  maps_key: "",
};

function queueCard(ref) {
  return Object.values(QUEUE.queue).flat().find((card) => card && typeof card === "object" && card.ref === ref);
}

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
  if (/\/backstage\/deliveries\/?(\?|$)/.test(url)) return json(res, 200, DELIVERIES);
  if (/\/orders\/?(\?|$)/.test(url)) return json(res, 200, QUEUE);
  const detail = url.match(/\/orders\/([A-Z0-9-]+)\/?(\?|$)/);
  if (detail) {
    const card = queueCard(detail[1]);
    return card ? json(res, 200, { order: { ...card, ...DETAIL_EXTRA } }) : json(res, 404, { detail: "Pedido não encontrado." });
  }
  if (/\/alerts\/?(\?|$)/.test(url)) return json(res, 200, { alerts: [], counts: { active: 0, critical: 0 } });
  return json(res, 200, {});
});

server.listen(port, "127.0.0.1", () => {
  // eslint-disable-next-line no-console
  console.log(`[gestor-mock] listening on http://127.0.0.1:${port}`);
});

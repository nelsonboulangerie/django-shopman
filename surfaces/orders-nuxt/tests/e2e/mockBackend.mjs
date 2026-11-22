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
  actions: [{ ref: "advance", kind: "mutation", label: "Iniciar preparo", priority: "primary", enabled: true, reason: "", href: "", method: "POST", payload_schema: { target_status: "preparing", base_revision: "fixture-base" }, idempotency: "required", confirmation: {} }],
  status_label: "Aceito",
  channel_ref: "web",
  channel_name: "Loja online",
  channel_icon: "language",
  customer_name: "Ana",
  created_at_iso: "",
  server_now_iso: "",
  elapsed_seconds: 30,
  timer_class: "timer-ok",
  items_summary: "2× Pão · 1× Café",
  items_count: 3,
  total_display: "R$ 15,00",
  fulfillment_label: "Retirada",
  fulfillment_type: "pickup",
  can_confirm: false,
  can_advance: true,
  next_status: "preparing",
  payment_method: "cash",
  payment_method_label: "Dinheiro",
    ifood_cancellation_notice: "",
    ifood_payment_summary: [],
    ifood_operation_summary: [],
    ifood_negotiations: [],
  payment_status: "pending",
  payment_pending: true,
  can_settle_delivery_cash: false,
  fiscal_status: "",
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
  goal_label: "meta 5 min",
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
      channel_name: "iFood",
      fulfillment_type: "delivery",
      fulfillment_label: "Entrega",
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
/**
 * "O que falta neste pedido" (WP-G05): o servidor de verdade manda a lista pronta
 * (`projections/order_pending.py`). Aqui ela sai dos mesmos campos do cartão: o avanço
 * travado vira a linha do bloqueio, com o nome e o motivo.
 */
function pendingFor(card) {
  if (!card.advance_block_label && !card.advance_block_reason) return [];
  return [{
    key: card.payment_pending ? "payment" : "advance",
    tone: "info",
    label: String(card.advance_block_label || "").replace(/…$/, ""),
    reason: card.advance_block_reason || "",
    actions: [],
  }];
}

const DETAIL_EXTRA = {
  customer_phone: "", customer_phone_uri: "", customer_whatsapp_url: "", customer_email: "", customer_ref: "",
  delivery_address: "", delivery_instructions: "", fiscal_status_label: "",
  revisions: { advance: "fixture-base" },
  items: [{ sku: "PAO", name: "Pão", qty: "1", unit_price_display: "R$ 16,00", total_display: "R$ 16,00" }],
  timeline: [], kitchen_note: "", customer_note: "", fiscal_links: [], equipment_options: [],
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

// ── Entregas: cancelar a corrida da TaOn (`deliveriesCancel.spec.ts`) ─────────
// Só para quem pede: o cookie `e2e_deliveries=cancel` liga o cenário, e as outras
// specs seguem vendo a seção Entregas vazia. Quatro corridas, uma por estado do
// cancelamento, com as MESMAS frases que o servidor manda
// (`order_queue.courier_cancel_confirmation`, `courier.cancel_state`).
const CANCEL_REASONS = [
  { id: 12, label: "O entregador não está vindo" },
  { id: 37, label: "Está demorando demais" },
  { id: 40, label: "Não consegui falar com o entregador" },
];
const RIDE_LETTERS = { 1: "A", 2: "B", 3: "C", 4: "D" };
/** ride key → { state: "" | pending | failed, sent: reason_id | null } (muda com o POST). */
const cancelState = new Map();

function names(codes) {
  return codes.length === 1 ? `${codes[0]} volta` : `${codes.slice(0, -1).join(", ")} e ${codes.at(-1)} voltam`;
}

function cancelAction(number, codes, accepted) {
  const ride = `a corrida ${RIDE_LETTERS[number]}`;
  const consequence = `${names(codes)} para Aguardando.`;
  return {
    ref: "courier-cancel", kind: "mutation", label: "Cancelar corrida", priority: "secondary", enabled: true, reason: "",
    href: "", method: "POST", idempotency: "required",
    payload_schema: { base_revision: `ride-${number}`, expected_actor_id: 1 },
    confirmation: {
      required: true,
      description: `Cancelar ${ride}? ${consequence}`,
      confirm_label: `Cancelar ${ride}`,
      ...(accepted ? { reason_question: `Por que cancelar ${ride}?`, consequence, reasons: CANCEL_REASONS } : {}),
    },
  };
}

const RIDE_FIXTURES = [
  { number: 1, key: "776753301", accepted: false, initial: "", stops: [["WEB-261116-A05", "Ana Lima", "Centro"], ["WEB-261116-C12", "Caio Souza", "Gleba Palhano"]] },
  { number: 2, key: "776753302", accepted: true, initial: "", stops: [["WEB-261116-B07", "Bia Ramos", "Bela Suíça"]] },
  { number: 3, key: "776753303", accepted: false, initial: "pending", stops: [["WEB-261116-D14", "Davi Prado", "Centro"]] },
  { number: 4, key: "776753304", accepted: true, initial: "failed", stops: [["WEB-261116-E02", "Elis Nunes", "Jardim Shangri-lá"], ["WEB-261116-F09", "Fábio Reis", "Centro"]] },
];

function rideCancel(fixture) {
  const state = cancelState.get(fixture.key)?.state ?? fixture.initial;
  const letter = RIDE_LETTERS[fixture.number];
  const message = state === "pending" ? "Pedido de cancelamento enviado. Esperando a TaOn confirmar."
    : state === "failed" ? `A TaOn não cancelou a corrida ${letter}. Cancele pela central da TaOn.` : "";
  return { state, message, canCancel: state !== "pending" };
}

function cancelStop([ref, customer, place], index) {
  return {
    ref, code: ref.split("-").at(-1), customer, place, address: `Rua das Flores, ${120 + index} · ${place}`,
    latitude: -23.31 - index * 0.006, longitude: -51.16 - index * 0.004, stage: "Pronto", volumes: 1, done: false,
    change_out_suggested_q: 0, needs_machine: false, change_label: "", group_refusal: "", error: "", dispatch_action: null,
  };
}

function deliveriesProjection() {
  const called = new Date(Date.now() - 4 * 60_000).toISOString();
  return {
    origin: { latitude: -23.3405, longitude: -51.158 },
    waiting: [],
    max_stops: 4,
    machines: [],
    courier_on: true,
    maps_key: "",
    rides: RIDE_FIXTURES.map((fixture) => {
      const cancel = rideCancel(fixture);
      const stops = fixture.stops.map(cancelStop);
      return {
        key: fixture.key, number: fixture.number, letter: RIDE_LETTERS[fixture.number],
        state: fixture.accepted ? "coming" : "searching",
        status_label: fixture.accepted ? "Entregador a caminho da loja" : "Procurando entregador",
        stops,
        driver: fixture.accepted ? { name: "Diego", phone: "(43) 99999-0000", vehicle: "Honda CG · ABC1D23" } : null,
        position: null, called_at: called, called_by: "ana",
        pickup_eta_at: fixture.accepted ? new Date(Date.now() + 6 * 60_000).toISOString() : "",
        arrived_pickup_at: "", picked_up_at: "", delivery_eta_at: "", tracking_url: "", cost_display: "R$ 12,50",
        bags: stops.length, undeclared: [], lead_ref: stops[0].ref, back_action: null, back_lines: [],
        cancel_action: cancel.canCancel ? cancelAction(fixture.number, stops.map((stop) => stop.code), fixture.accepted) : null,
        cancel_state: cancel.state, cancel_message: cancel.message,
      };
    }),
  };
}

/**
 * #2500 (cookie `e2e_custody=on`): a TaOn retomou a corrida A do pedido R05, que
 * constava como encerrada; o troco e a maquininha tinham voltado para a casa. O
 * "Separar de novo" (`courier-custody`) grava o corpo e a corrida deixa de pedir.
 */
const CUSTODY_REF = "WEB-261116-R05";
const custodyState = { body: null };
function custodyOrder() {
  const separated = custodyState.body !== null;
  return {
    ...CARD, ...DETAIL_EXTRA, ref: CUSTODY_REF, status: "ready", status_label: "Pronto", customer_name: "Rita Moraes",
    fulfillment_type: "delivery", fulfillment_label: "Entrega",
    payment_method: "cash", payment_method_label: "Dinheiro na entrega", payment_status: "pending", payment_pending: true,
    can_advance: false, next_status: "",
    equipment_options: [
      { ref: "card_machine:3", label: "Azul", enabled: true, reason: "", order_ref: "" },
      { ref: "card_machine:4", label: "Preta", enabled: false, reason: "Saiu com o pedido A12", order_ref: "WEB-261116-A12" },
    ],
    actions: [{
      ref: "courier-custody", kind: "mutation", label: "Separar de novo", priority: "secondary", enabled: !separated,
      reason: separated ? "Esta corrida não pede o troco nem a maquininha agora." : "", href: "", method: "POST",
      idempotency: "required", payload_schema: { base_revision: "custody-1", expected_actor_id: 1 },
    }],
    courier: {
      provider: "machine", status: "D", ride_state: "searching", service_name: "TaOn", status_label: "Procurando entregador",
      active: true, driver: null, tracking_url: "", confirmation_code: "", estimate_display: "R$ 12,50 · 18 min · 4,2 km",
      final_value_display: "", requested_at: new Date(Date.now() - 9 * 60_000).toISOString(), dispatched_at: "", finished_at: "",
      attempts_count: 0, position: null, error: null, can_quote: false, can_dispatch: false, can_dispatch_again: false,
      can_cancel: true, cancel_state: { state: "", message: "", at: "" }, reminder: null,
      custody: { change_out_suggested_q: 0, needs_machine: false, recorded: separated },
      charge_outdated: null,
      custody_to_separate: separated ? null : { change_out_suggested_q: 2600, needs_machine: true },
    },
  };
}

/** O detalhe de um pedido que está numa corrida do cenário, com o bloco da corrida. */
function rideOrder(ref) {
  const fixture = RIDE_FIXTURES.find((item) => item.stops.some(([stopRef]) => stopRef === ref));
  if (!fixture) return null;
  const [, customer] = fixture.stops.find(([stopRef]) => stopRef === ref);
  const cancel = rideCancel(fixture);
  const codes = fixture.stops.map(([stopRef]) => stopRef.split("-").at(-1));
  return {
    ...CARD, ...DETAIL_EXTRA, ref, status: "ready", status_label: "Pronto", customer_name: customer,
    fulfillment_type: "delivery", fulfillment_label: "Entrega",
    payment_method: "pix", payment_method_label: "Pix", payment_status: "paid", payment_pending: false,
    can_advance: false, next_status: "",
    actions: [{ ...cancelAction(fixture.number, codes, fixture.accepted), enabled: cancel.canCancel }],
    courier: {
      provider: "machine", status: fixture.accepted ? "A" : "D",
      ride_state: fixture.accepted ? "assigned" : "searching", service_name: "TaOn",
      status_label: fixture.accepted ? "Entregador a caminho da loja" : "Procurando entregador",
      active: true,
      driver: fixture.accepted ? { name: "Diego", phone: "(43) 99999-0000", vehicle_plate: "ABC1D23", vehicle_model: "Honda CG" } : null,
      tracking_url: "", confirmation_code: "", estimate_display: "R$ 12,50 · 18 min · 4,2 km", final_value_display: "",
      requested_at: new Date(Date.now() - 4 * 60_000).toISOString(), dispatched_at: "", finished_at: "", attempts_count: 0,
      position: null, error: null, can_quote: false, can_dispatch: false, can_dispatch_again: false,
      can_cancel: cancel.canCancel,
      cancel_state: { state: cancel.state, message: cancel.message, at: cancel.state ? new Date().toISOString() : "" },
      reminder: null, custody: { change_out_suggested_q: 0, needs_machine: false, recorded: false },
      charge_outdated: null,
    },
  };
}

// ── Promessa em risco: o diálogo "Resolver" (`promiseResolve.spec.ts`, WP-G08) ──────
// Só para quem pede: o cookie `e2e_promise` põe na fila um pedido com a promessa em
// risco, e as outras specs seguem vendo a fila de sempre. O aviso leva as ações no
// formato novo (`promise.actions`: "Resolver", `kind: "dialog"`, sem `href`); as saídas
// antigas moram no diálogo, que lê `orders/<ref>/promise-resolution/` com as quatro
// famílias de escolha (trocar, remarcar, tirar o item, cancelar). A forma é a do
// servidor: `conclude` sempre com as cinco chaves (`kind`, `label`, `href`, `items`,
// `payload_schema`), e a escolha fechada com o motivo e o resto vazio. As frases são as
// que o servidor manda: a tela não escreve nenhuma delas.
//   - `e2e_promise=risk`: tudo aberto, com WhatsApp;
//   - `e2e_promise=closed`: trocar, remarcar e tirar fechados (com o motivo), sem
//     WhatsApp no pedido; só cancelar segue aberto.
const PROMISE_REF = "WEB-2611-G8G-N75";
const PROMISE_PDV = "https://pdv.example.test";
const PROMISE_FACT = "Faltam 4x Focaccia Cebola, Bacon e Tomilho. O lote de hoje foi cancelado.";
const PROMISE_HELLO =
  "Oi, Nelson! Aqui é da Nelson Boulangerie 💛 A Focaccia Cebola, Bacon e Tomilho do seu pedido N75 não vai ficar pronta hoje, e sinto muito por isso.";
const PROMISE_MESSAGES = {
  swap: `${PROMISE_HELLO} Posso trocar por Campagne Passas & Castanhas? Me avisa e eu ajusto por aqui ✨`,
  swapFendu: `${PROMISE_HELLO} Posso trocar por Fendu? Me avisa e eu ajusto por aqui ✨`,
  reschedule: `${PROMISE_HELLO} Posso remarcar o seu pedido para outro dia? Me diz qual fica melhor para você ✨`,
  remove: `${PROMISE_HELLO} Posso tirar esse item do pedido e devolver R$ 44,00 pelo Pix? Me avisa e eu ajusto por aqui ✨`,
  cancel: `${PROMISE_HELLO} Se preferir, cancelo o pedido e devolvo R$ 72,00 pelo Pix. Me avisa como fica melhor ✨`,
};
const promiseWhatsapp = (message) => `https://wa.me/5543999990000?text=${encodeURIComponent(message)}`;
const PROMISE_EDIT_ITEMS = [{ line_id: "line-2", sku: "CROISSANT", qty: "2" }];
/** O que a rota de edição exige: a revisão que o servidor leu e quem a tela leu. */
const PROMISE_EDIT_PAYLOAD = { base_revision: "edit-fixture", expected_actor_id: 1 };
const PROMISE_EDIT_REFUSED = "Pedido em preparo não pode ser editado.";
/** O que a spec confere: o que foi gravado e se a promessa ainda está em risco. */
const promiseState = { resolved: false, edits: [] };

const RESOLVE_ACTION = {
  ref: "resolve", kind: "dialog", label: "Resolver", priority: "primary", enabled: true, reason: "", href: "",
  method: "", payload_schema: {}, idempotency: "none", confirmation: {},
};
const PROMISE = {
  state: "at_risk", label: "Promessa em risco", blocks_start: false, since_iso: "", next_step: "",
  recommended_action: "resolve", actions: [RESOLVE_ACTION],
  items: [{
    sku: "FOCACCIA-CBT", name: "Focaccia Cebola, Bacon e Tomilho", reservation: "lost", cause: "batch_cancelled",
    at_risk: true, qty: "4", missing_qty: "4", label: "Faltam 4x Focaccia Cebola, Bacon e Tomilho",
    detail: "O lote de hoje foi cancelado.", batch_date: "2026-11-19", batch_status: "void", batch_ready_at_iso: "",
    work_order_refs: ["WO-1"], next_step: "",
    alternatives: [
      { sku: "CAMPAGNE-PC", name: "Campagne Passas & Castanhas", available_display: "6 disponíveis hoje" },
      { sku: "FENDU", name: "Fendu", available_display: "3 disponíveis hoje" },
    ],
  }],
};

function promiseCard() {
  const risky = !promiseState.resolved;
  return {
    ...CARD,
    ref: PROMISE_REF,
    customer_name: "Nelson Dias",
    items_summary: "4× Focaccia Cebola, Bacon e Tomilho · 2× Croissant",
    items_count: 6,
    total_display: "R$ 72,00",
    payment_method: "pix",
    payment_method_label: "Pix",
    payment_status: "paid",
    payment_pending: false,
    attention: risky ? "promise" : "start",
    attention_since_iso: new Date(Date.now() - 6 * 60_000).toISOString(),
    promise: risky ? PROMISE : null,
  };
}

/** `conclude` com as cinco chaves, sempre. */
function promiseConclude(kind, label, extra = {}) {
  return { kind, label, href: "", items: [], payload_schema: {}, ...extra };
}

function promiseChoice(key, kind, label, detail, message, conclude, extra = {}) {
  return {
    key, kind, label, detail, enabled: true, reason: "", message, whatsapp_url: promiseWhatsapp(message), conclude,
    requires_manager_approval: false, ...extra,
  };
}

/** Escolha fechada, como o servidor a manda: o motivo, e o resto vazio. */
function promiseClosed(choice, reason) {
  return {
    ...choice, enabled: false, reason, message: "", whatsapp_url: "",
    conclude: { ...choice.conclude, href: "", items: [] },
  };
}

function promiseResolution(variant) {
  const swapHref = `${PROMISE_PDV}/preorders/${PROMISE_REF}?swap=FOCACCIA-CBT`;
  const open = [
    promiseChoice("swap:FOCACCIA-CBT:CAMPAGNE-PC", "swap", "Trocar por Campagne Passas & Castanhas", "6 disponíveis hoje",
      PROMISE_MESSAGES.swap, promiseConclude("link", "Trocar no PDV", { href: swapHref })),
    promiseChoice("swap:FOCACCIA-CBT:FENDU", "swap", "Trocar por Fendu", "3 disponíveis hoje",
      PROMISE_MESSAGES.swapFendu, promiseConclude("link", "Trocar no PDV", { href: swapHref })),
    // O nome do contrato termina em "fornada"; a trava de vocabulário do kit reprova a
    // palavra nos apps de operador (o objeto na tela é "lote"). Ver `tests/support/promiseResolution.ts`.
    promiseChoice("reschedule", "reschedule", "Remarcar para outro dia ou outro lote", "",
      PROMISE_MESSAGES.reschedule, promiseConclude("link", "Remarcar no PDV", { href: `${PROMISE_PDV}/preorders/${PROMISE_REF}` })),
    promiseChoice("remove", "remove", "Tirar só o item que falta e devolver a diferença", "R$ 44,00 serão estornados ao Pix do cliente.",
      PROMISE_MESSAGES.remove, promiseConclude("edit", "Tirar o item", { items: PROMISE_EDIT_ITEMS, payload_schema: PROMISE_EDIT_PAYLOAD })),
    // Pedido pago: o gerente é do diálogo de cancelar, que este só abre.
    promiseChoice("cancel", "cancel", "Cancelar o pedido inteiro", "R$ 72,00 serão estornados ao Pix do cliente.",
      PROMISE_MESSAGES.cancel, promiseConclude("cancel", "Cancelar pedido"), { requires_manager_approval: true }),
  ];
  const closed = variant === "closed";
  const choices = closed
    ? [
        promiseClosed(open[0], PROMISE_EDIT_REFUSED),
        promiseClosed(open[1], PROMISE_EDIT_REFUSED),
        promiseClosed(open[2], "Pedido em preparo não pode ser remarcado."),
        promiseClosed(open[3], PROMISE_EDIT_REFUSED),
        { ...open[4], whatsapp_url: "" },
      ]
    : open;
  return {
    order_ref: PROMISE_REF,
    code: "N75",
    customer_name: "Nelson Dias",
    facts: [PROMISE_FACT],
    contact: closed ? { enabled: false, reason: "Este pedido não tem WhatsApp do cliente." } : { enabled: true, reason: "" },
    notice: {
      enabled: true,
      kind: "item_missing",
      label: "Faltou um item",
      note: 'Primeiro, avise o cliente com o aviso "Faltou um item". Quando ele responder, mande a proposta da escolha.',
      reason: "",
      line_ids: ["L1"],
    },
    choices,
  };
}

/** O detalhe do pedido em risco: a linha da promessa na faixa, com o mesmo "Resolver". */
function promiseOrder() {
  const card = promiseCard();
  const risky = !promiseState.resolved;
  return {
    ...card, ...DETAIL_EXTRA,
    customer_whatsapp_url: "https://wa.me/5543999990000",
    items: [
      { sku: "FOCACCIA-CBT", name: "Focaccia Cebola, Bacon e Tomilho", qty: "4", unit_price_display: "R$ 11,00", total_display: "R$ 44,00" },
      { sku: "CROISSANT", name: "Croissant", qty: "2", unit_price_display: "R$ 14,00", total_display: "R$ 28,00" },
    ].slice(risky ? 0 : 1),
    cancel_money_effect: "R$ 72,00 serão estornados ao Pix do cliente.",
    managers: [{ username: "ana", name: "Ana" }],
    revisions: { ...CARD.revisions, edit: "edit-fixture" },
    pending: risky
      ? [{
          key: "promise", tone: "error", label: "Promessa em risco", reason: PROMISE_FACT, next_step: "",
          actions: [{ ref: "resolve", label: "Resolver", enabled: true, reason: "", href: "", priority: "primary" }],
        }]
      : [],
  };
}

function readBody(req) {
  return new Promise((resolve) => {
    let raw = "";
    req.on("data", (chunk) => (raw += chunk));
    req.on("end", () => {
      try { resolve(JSON.parse(raw || "{}")); } catch { resolve({}); }
    });
  });
}

// A seção Entregas: três entregas aguardando e duas corridas na rua (A a caminho da
// loja, B em rota). Sem chave do Google Maps: o mapa é o desenho próprio. O número da
// corrida escolhe a cor; o que a tela escreve é a LETRA (`letter`); a URL leva a chave.
const minutesAgo = (n) => new Date(Date.now() - n * 60_000).toISOString();
const minutesAhead = (n) => new Date(Date.now() + n * 60_000).toISOString();
const secondsAgo = (n) => new Date(Date.now() - n * 1000).toISOString();
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
      // Posição de agora (F7b): a moto cheia, sem etiqueta. A hora é lida a cada resposta.
      position: { latitude: ORIGIN.latitude + 0.003, longitude: ORIGIN.longitude - 0.003, get at() { return secondsAgo(5); }, source_label: "pela TaOn" },
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
        deliveryStop("WEB-20261116-0F09", "Flora", "Aeroporto", 0.009, -0.015, { tracking_url: "https://rastreio.example/776753358/flora" }),
      ],
      driver: { name: "Marina", phone: "(43) 99999-0002", vehicle: "Moto preta · XYZ9K88" },
      // Posição velha (F7b): sem aviso há 3 min, a moto esmaece e diz desde quando.
      position: { latitude: ORIGIN.latitude + 0.006, longitude: ORIGIN.longitude - 0.013, get at() { return minutesAgo(3); }, source_label: "pela TaOn" },
      called_at: minutesAgo(28), picked_up_at: minutesAgo(12), delivery_eta_at: minutesAhead(11),
      cost_display: "R$ 14,50", cost_label: "Valor pago à TaOn",
      fee_display: "Frete cobrado R$ 12,00", balance_display: "Falta R$ 2,50",
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
  // A corrida em grupo pelo protocolo de intenção: quem a tela leu e a revisão de cada um.
  group_action: {
    ref: "courier-ride", kind: "mutation", label: "Chamar corrida", enabled: true, reason: "",
    method: "POST", idempotency: "required", confirmation: {},
    payload_schema: {
      expected_actor_id: 1,
      base_revisions: { "WEB-20261116-0A47": "r-a47", "WEB-20261116-0C03": "r-c03", "WEB-20261116-0D12": "r-d12" },
    },
  },
  // O plano da casa (`ride_plan`, F5): A47 e C03, prontos e vizinhos, cotados e mais
  // baratos juntos. D12 está em preparo e nunca entra.
  ride_plan: {
    suggestions: [{
      key: "WEB-20261116-0A47+WEB-20261116-0C03",
      refs: ["WEB-20261116-0A47", "WEB-20261116-0C03"], codes: ["A47", "C03"], places: "Gleba Palhano",
      quoted: true, suggested: true, late_code: "C03", late_minutes: 6,
      together_q: 1650, minutes: 24, km: 5.7, with_return: false, separate_q: 2500, saving_q: 850,
    }],
    service: "taon", service_reason: "default",
    service_options: [{ ref: "taon", name: "TaOn", kind: "machine", is_default: true }],
  },
};
/** #2736 (cookie `e2e_close=on`): a corrida A está aberta há muito tempo, antes da coleta. */
const CLOSE_HERE_ACTION = {
  ref: "courier-close-here", kind: "mutation", label: "Encerrar aqui", enabled: true, reason: "",
  method: "POST", idempotency: "required",
  confirmation: {
    required: true,
    description: "A TaOn não encerrou a corrida A. Encerre aqui só se souber o que aconteceu.",
    outcomes: [
      { key: "delivered", label: "Foi entregue", consequence: "O pedido fica entregue. O troco fica para o gesto “Entregador voltou”." },
      { key: "returned", label: "Voltou para a loja", consequence: "O pedido volta para Aguardando. O troco volta para a gaveta." },
    ],
  },
  payload_schema: { base_revision: "r-b12", expected_actor_id: 1 },
};
const closePosts = [];
/** As corridas que acabaram sem levar os pedidos (#2737), no topo de Aguardando. */
const FAILED_RIDES = [
  {
    key: "776753390", message: "Ninguém aceitou a corrida C (14h20).",
    refs: ["WEB-20261116-0A47", "WEB-20261116-0C03"], codes: ["A47", "C03"], places: "Gleba Palhano", number: 3,
  },
  {
    key: "776753391", message: "A TaOn cancelou a corrida (14h05).",
    refs: ["WEB-20261116-0D12"], codes: ["D12"], places: "Centro", number: null,
  },
];
/** As corridas em grupo que a tela chamou (`POST /orders/courier-ride/`), na ordem. */
const ridePosts = [];

// A F10 (`deliveriesFiscal.spec.ts`, cookie `e2e_f10`): `fiscal` põe a NFC-e não
// autorizada na parada de Flora (corrida B) e a DANFE por imprimir na de Bia (corrida
// A), com os MESMOS campos do cartão; `countfail` faz o selo receber `waiting: null`.
// Sem o cookie, o selo conta as três de Aguardando e nenhuma parada tem aviso.
function f10Deliveries() {
  const patch = (stop) => {
    if (stop.ref === "WEB-20261116-0F09") return { ...stop, fiscal_status: "failed", danfe_state: "", danfe_problem: "" };
    if (stop.ref === "WEB-20261116-0B12") {
      return {
        ...stop, fiscal_status: "authorized", danfe_state: "not_printed",
        danfe_problem: "A impressora de Balcão recusou a DANFE. Confira o papel e imprima de novo.",
      };
    }
    return stop;
  };
  return { ...DELIVERIES, rides: DELIVERIES.rides.map((ride) => ({ ...ride, stops: ride.stops.map(patch) })) };
}

// A prévia da F4a (`MOCK_F4A=1`): o que a página passou a saber igual ao Painel.
// Uma chamada sem resposta em Aguardando, a corrida que a TaOn parou de informar
// com a cobrança de uma parada para trás, a que ninguém aceitou há 12 min e a que
// voltou (o "Entregador voltou" abre a conferência).
const AGAIN = {
  ref: "courier-dispatch-again", kind: "mutation", label: "Chamar de novo", enabled: true, reason: "",
  method: "POST", idempotency: "required",
  confirmation: { required: true, description: "A TaOn não respondeu à última chamada. Veja na central se a corrida abriu antes de chamar de novo." },
  payload_schema: { base_revision: "r1", expected_actor_id: 1 },
};
const BACK = { ...AGAIN, ref: "courier-back", label: "Entregador voltou", confirmation: { required: true } };
function f4aDeliveries() {
  return {
    ...DELIVERIES,
    waiting: [
      ...DELIVERIES.waiting,
      deliveryStop("WEB-20261116-0G07", "Gabi", "Centro", -0.009, 0.004, {
        error: "A TaOn não respondeu à última chamada. Veja na central se a corrida abriu.",
        group_refusal: "O pedido G07 tem uma chamada sem resposta da TaOn. Confira na central antes.",
        dispatch_again_action: AGAIN,
      }),
    ],
    rides: [
      {
        ...DELIVERIES.rides[0],
        sync_since: minutesAgo(7),
        stops: [deliveryStop("WEB-20261116-0B12", "Bia", "Jardim Higienópolis", -0.004, -0.008, {
          volumes: 2,
          charge_outdated: { sent: "Cobrar R$ 50,00 em dinheiro · troco para R$ 100,00", current: "Cobrar R$ 58,00 em dinheiro · troco para R$ 100,00", collected: false },
        })],
      },
      DELIVERIES.rides[1],
      {
        ...RIDE_BASE,
        key: "776753359", number: 3, letter: "C", state: "late", status_label: "Ninguém aceitou ainda",
        stops: [deliveryStop("WEB-20261116-0H11", "Hugo", "Bela Suíça", -0.002, 0.012)],
        called_at: minutesAgo(12), lead_ref: "WEB-20261116-0H11",
      },
      {
        ...RIDE_BASE,
        key: "776753360", number: 4, letter: "D", state: "back", status_label: "Tudo entregue",
        stops: [deliveryStop("WEB-20261116-0J05", "Jo", "Centro", -0.006, 0.006, { done: true })],
        driver: { name: "Rui", phone: "(43) 99999-0003", vehicle: "Moto vermelha · RUI2B34" },
        called_at: minutesAgo(50), lead_ref: "WEB-20261116-0J05",
        back_action: BACK, back_lines: ["R$ 58,00 em dinheiro", "Maquininha Azul"],
      },
    ],
    free_numbers: Array.from({ length: 22 }, (_, i) => i + 5),
    next_number: 5,
  };
}

function queueCard(ref) {
  return Object.values(QUEUE.queue).flat().find((card) => card && typeof card === "object" && card.ref === ref);
}

// F4b: a coluna Editando com duas entregas de cartão e duas maquininhas livres (uma
// por corrida), para a tela e as capturas.
function f4bDeliveries() {
  return {
    ...DELIVERIES,
    waiting: [
      ...DELIVERIES.waiting,
      deliveryStop("WEB-20261116-0G15", "Gil", "Centro", -0.009, 0.006, { needs_machine: true, change_label: "Cartão na porta" }),
      deliveryStop("WEB-20261116-0H20", "Helô", "Aeroporto", 0.006, -0.011, { needs_machine: true, change_label: "Cartão na porta" }),
    ],
    machines: [
      { ref: "machine:azul", label: "Maquininha azul" },
      { ref: "machine:verde", label: "Maquininha verde" },
    ],
  };
}

// A cotação da corrida em edição: uma parada R$ 12,50, cada parada a mais na mesma
// corrida R$ 4,00 (o adapter mock do servidor). Com 2 ou mais, a comparação.
function rideQuote(url) {
  const asked = new URL(url, "http://mock").searchParams.getAll("refs");
  if (!asked.length) return null;
  // Como o servidor: as paradas na ordem da rota (vizinho mais próximo a partir da loja).
  const known = new Map(f4bDeliveries().waiting.map((stop) => [stop.ref, stop]));
  const left = [...asked];
  const refs = [];
  let here = [ORIGIN.latitude, ORIGIN.longitude];
  const distance = (ref) => {
    const stop = known.get(ref);
    return stop ? (stop.latitude - here[0]) ** 2 + (stop.longitude - here[1]) ** 2 : Infinity;
  };
  while (left.length) {
    const next = left.reduce((best, ref) => (distance(ref) < distance(best) ? ref : best), left[0]);
    left.splice(left.indexOf(next), 1);
    refs.push(next);
    const stop = known.get(next);
    if (stop) here = [stop.latitude, stop.longitude];
  }
  const value_q = 1250 + 400 * (refs.length - 1);
  const minutes = 18 + 6 * (refs.length - 1);
  const km = (4.2 + 1.5 * (refs.length - 1)).toFixed(1).replace(".", ",");
  const money = (q) => `R$ ${Math.floor(q / 100)},${String(q % 100).padStart(2, "0")}`;
  const compare = refs.length > 1 ? { separate_value_q: 1250 * refs.length, saving_q: 1250 * refs.length - value_q } : {};
  return {
    estimate: {
      value_q, minutes, km: Number(km.replace(",", ".")), with_return: false, stops: refs, ...compare,
      display: `${money(value_q)} · ${minutes} min · ${km} km`,
      route: refs.map((ref) => ref.slice(-3)).join(" → "),
    },
  };
}

// M3 (#2526): os entregadores da casa. Só com o cookie `e2e_crew=on` alguém da casa
// existe; sem ele, o serviço da casa está desligado e a tela é a de antes. Diego está
// na escala; Rui não. As paradas ganham a ação `courier-dispatch` (a revisão que a tela
// leu), que é de onde sai a intenção de enviar à casa.
// Cada arquivo de spec tem o seu estado (cookie `e2e_ns`): os workers da suíte rodam
// arquivos em paralelo contra este mesmo mock, e o `beforeEach` que limpa o estado de um
// arquivo não pode apagar a corrida que outro acabou de enviar (fila, 21/11/2026, #2991).
const houseStores = new Map();
function houseStore(req) {
  const ns = (req.headers.cookie || "").match(/(?:^|;\s*)e2e_ns=([\w-]+)(?:;|$)/)?.[1] ?? "";
  if (!houseStores.has(ns))
    houseStores.set(ns, {
      crewState: { diego: true, rui: false },
      housePosts: [],
      houseState: { departed: false, delivered: [], claimed: true, gestures: [] },
    });
  return houseStores.get(ns);
}
// Apontados para o estado do arquivo que fez o pedido, no começo de cada pedido e de
// novo em cada resposta assíncrona (outro pedido pode ter trocado o apontamento).
let crewState, housePosts, houseState;
function useHouseStore(store) {
  ({ crewState, housePosts, houseState } = store);
}
function crewBody(url, mode = "on") {
  const refs = new URL(url, "http://mock").searchParams.getAll("refs");
  const value = (q) => (refs.length ? `R$ ${Math.floor(q / 100)},${String(q % 100).padStart(2, "0")}` : "");
  const row = (ref, name, base) => {
    const valueQ = refs.length && crewState[ref] ? base + 300 * (refs.length - 1) : null;
    return { ref, name, on_shift: crewState[ref], state: "free", state_label: "Livre", value_q: valueQ,
      value: valueQ === null ? "" : value(valueQ),
      // M4: o acerto do dia; Diego já fechou duas rotas hoje.
      to_pay_today: ref === "diego" ? "A pagar a Diego hoje: R$ 27,00 (2 corridas)" : "" };
  };
  return {
    active: true, service: { ref: "casa", name: "Entregadores da casa" }, default: { ref: "taon", name: "TaOn" },
    couriers: mode === "many"
      // M3c: cinco na escala (o último chip vira "Outro da casa"); Caio está na rua e volta 12h50.
      ? [["ana", "Ana", 1100], ["bruno", "Bruno", 1150], ["caio", "Caio", 1300], ["diego", "Diego", 1200], ["eva", "Eva", 1250]]
        .map(([ref, name, base]) => {
          const valueQ = refs.length ? base + 300 * (refs.length - 1) : null;
          const busy = ref === "caio";
          return { ref, name, on_shift: true, state: busy ? "busy" : "free", state_label: busy ? "Volta 12h50" : "Livre",
            back_at: null, value_q: valueQ, value: valueQ === null ? "" : value(valueQ) };
        })
      : [row("diego", "Diego", 1200), row("rui", "Rui", 1400)],
  };
}
const DISPATCH = (ref) => ({
  ref: "courier-dispatch", kind: "mutation", label: "Chamar sozinho", priority: "", enabled: true, reason: "",
  href: "", method: "POST", idempotency: "required", confirmation: { required: true },
  payload_schema: { base_revision: `r-${ref.slice(-3).toLowerCase()}`, expected_actor_id: 1 },
});
function crewDeliveries() {
  return { ...DELIVERIES, waiting: DELIVERIES.waiting.map((stop) => ({ ...stop, dispatch_action: DISPATCH(stop.ref) })) };
}

// M3b (#2898): a corrida da casa na lista de Corridas, com o cookie `e2e_house=on`. A
// corrida C é do Diego (A47 ∙ C03); os gestos do balcão mudam o estado do mock: "Despachar a corrida C"
// põe a rota na rua, "A47 entregue" risca a parada. A corrida A (TaOn) segue igual.
const HOUSE_STOPS = [
  ["WEB-20261116-0A47", "Ana", "Gleba Palhano", 0.006, 0.004, 2, "Troco para R$ 50,00"],
  ["WEB-20261116-0C03", "Caio", "Gleba Palhano", 0.008, 0.007, 1, ""],
];
const houseAction = (ref, label, confirmation) => ({
  ref, kind: "mutation", label, priority: "", enabled: true, reason: "", href: "", method: "POST",
  idempotency: "required", confirmation: confirmation ? { required: true, description: confirmation } : { required: false },
  payload_schema: { base_revision: `house-${houseState.departed}-${houseState.delivered.length}`, expected_actor_id: 1 },
});
function houseRide() {
  const stops = HOUSE_STOPS.map(([ref, customer, place, dLat, dLng, volumes, change]) =>
    deliveryStop(ref, customer, place, dLat, dLng, { volumes, change_label: change, done: houseState.delivered.includes(ref) }));
  const open = stops.filter((stop) => !stop.done);
  const moment = houseState.departed ? `Diego na rua · ${houseState.delivered.length} de 2 entregues` : "Diego leva";
  return {
    ...RIDE_BASE,
    key: "CASA-7F3A2B", number: 3, letter: "C", state: houseState.departed ? "route" : "coming",
    status_label: houseState.departed ? "Em rota" : "Entregador a caminho da loja",
    stops, called_at: minutesAgo(4), lead_ref: stops[0].ref, cost_display: "R$ 15,00",
    driver: { name: "Diego", phone: "(43) 99999-0000", vehicle: "Moto prata · ABC1D23", photo_url: "" },
    house: {
      courier_ref: "diego", courier_name: "Diego", moment,
      hint: houseState.departed ? "Entregador da casa · R$ 15,00" : "Entregador da casa · R$ 15,00 · Abriu o link às 12h31",
      delivered: houseState.delivered.length, total: 2, link_claimed: houseState.claimed,
      depart_action: houseState.departed ? null
        : houseAction("house-depart", "Despachar a corrida C", "Diego saiu com os pedidos? Os clientes recebem o aviso de saída."),
      deliver_actions: houseState.departed ? open.map((stop) => ({
        ref: stop.ref, code: stop.code,
        action: houseAction("house-deliver", `${stop.code} entregue`, `Marcar ${stop.code} como entregue? O cliente recebe o aviso agora.`),
      })) : [],
      resend_action: houseAction("house-resend", "Reenviar o link"),
      release_action: houseState.claimed
        ? houseAction("house-release", "Soltar o link", "Soltar o link do celular em que está preso? O próximo celular que confirmar fica com ele.")
        : null,
    },
  };
}
// M3d (#2937): a fila com os dois pedidos da corrida da casa (A47 e C03) e um pedido de
// entrega solto (E21) na Saída. A corrida vira UM cartão; o E21 segue como era.
function exitCard(ref, customer, extra = {}) {
  return {
    ...CARD, ref, customer_name: customer, status: "ready", status_label: "Pronto", fulfillment_type: "delivery",
    fulfillment_label: "Entrega", actions: [], can_advance: false, next_status: "", attention: "", attention_since_iso: "",
    goal_minutes: 0, goal_label: "", payment_status: "paid", payment_pending: false, ...extra,
  };
}
function houseQueue() {
  const delivery = [
    exitCard("WEB-20261116-0A47", "Ana"),
    exitCard("WEB-20261116-0C03", "Caio"),
    exitCard("WEB-20261116-0E21", "Edu"),
  ];
  return { ...QUEUE, queue: { ...QUEUE.queue, expedition_delivery: delivery, expedition_delivery_count: 3, expedition_count: 3, total_count: QUEUE.queue.total_count + 3 } };
}

function houseDeliveries() {
  const keep = new Set(HOUSE_STOPS.map(([ref]) => ref));
  return {
    ...DELIVERIES,
    waiting: DELIVERIES.waiting.filter((stop) => !keep.has(stop.ref)),
    rides: [...DELIVERIES.rides.map((ride) => ({ ...ride, house: null })), houseRide()],
    free_numbers: DELIVERIES.free_numbers.filter((n) => n !== 3),
    ride_plan: { ...DELIVERIES.ride_plan, suggestions: [] },
  };
}

// #2876: o cartão Pronto chama o entregador ali mesmo. Com o cookie `e2e_call=on`, a
// Saída tem A47 e C03 prontos (os mesmos de Aguardando, onde a casa sugere juntá-los)
// e o B08 de retirada; a contagem leve diz que A47 e C03 dá para chamar. O detalhe de
// A47 traz o painel do entregador. As chamadas de um pedido ficam em `callPosts`.
const callPosts = [];
const CALL_REFS = ["WEB-20261116-0A47", "WEB-20261116-0C03"];
function callQueue() {
  const delivery = [
    exitCard("WEB-20261116-0A47", "Ana", { actions: [{ ...CARD.actions[0], label: "Despachar A47", payload_schema: { target_status: "dispatched", base_revision: "r" } }], can_advance: true, next_status: "dispatched", items_summary: "2× Baguete · 1× Pain au chocolat", total_display: "R$ 58,00", delivery_address: "Gleba Palhano" }),
    exitCard("WEB-20261116-0C03", "Caio", { actions: [{ ...CARD.actions[0], label: "Despachar C03", payload_schema: { target_status: "dispatched", base_revision: "r" } }], can_advance: true, next_status: "dispatched", items_summary: "1× Campagne · 6× Croissant", total_display: "R$ 74,50", delivery_address: "Gleba Palhano" }),
  ];
  const pickup = [exitCard("WEB-20261116-0B08", "Carla", { fulfillment_type: "pickup", fulfillment_label: "Retirada", items_summary: "1× Bolo de laranja", total_display: "R$ 42,00" })];
  return {
    ...QUEUE,
    queue: {
      ...QUEUE.queue, expedition_pickup: pickup, expedition_delivery: delivery, expedition_delivery_count: 2,
      expedition_count: 3, total_count: QUEUE.queue.total_count + 3, ride_suggestions: 1,
      ride_candidates: [{ ref: CALL_REFS[0] }, { ref: CALL_REFS[1] }],
    },
  };
}
function callDetail(ref) {
  const card = callQueue().queue.expedition_delivery.find((item) => item.ref === ref);
  if (!card) return null;
  const dispatch = { ...DISPATCH(ref), label: "Chamar entregador", confirmation: { required: true, description: `Chamar um entregador da TaOn para o pedido ${ref.slice(-3)}? A corrida é cobrada da casa.` } };
  return {
    ...card, ...DETAIL_EXTRA, pending: [], delivery_address: "Rua das Entregas, 100, Gleba Palhano",
    actions: [...card.actions, dispatch],
    courier: {
      provider: "machine", status: "", ride_state: "", service_name: "TaOn", status_label: "", active: false, driver: null, tracking_url: "", confirmation_code: "",
      estimate_display: "", final_value_display: "", attempts_count: 0, position: null, error: null, can_quote: false,
      can_dispatch: true, not_today: "", can_dispatch_again: false, can_cancel: false, cancel_state: null, reminder: null,
      custody: { change_out_suggested_q: 0, needs_machine: false, recorded: false },
      charge_outdated: null,
    },
  };
}

function json(res, status, body) {
  res.statusCode = status;
  res.end(JSON.stringify(body));
}

const server = createServer((req, res) => {
  const store = houseStore(req);
  useHouseStore(store);
  res.setHeader("content-type", "application/json");
  res.setHeader("set-cookie", "csrftoken=e2e-mock; Path=/");
  const url = req.url || "";

  if (/\/operator\/session\/?(\?|$)/.test(url)) return json(res, 200, SESSION);
  if (/\/operator\/eligible\/?(\?|$)/.test(url)) return json(res, 200, { operators: [] });
  const cancelScenario = /(?:^|;\s*)e2e_deliveries=cancel(?:;|$)/.test(req.headers.cookie || "");
  if (cancelScenario && /\/deliveries\/?(\?|$)/.test(url)) return json(res, 200, deliveriesProjection());
  const crewMode = (req.headers.cookie || "").match(/(?:^|;\s*)e2e_crew=(on|many|alone)(?:;|$)/)?.[1] ?? "";
  const crewScenario = Boolean(crewMode);
  const houseScenario = /(?:^|;\s*)e2e_house=on(?:;|$)/.test(req.headers.cookie || "");
  if (/\/e2e\/deliveries\/house-ride\/?(\?|$)/.test(url)) {
    if (req.method === "DELETE") Object.assign(houseState, { departed: false, delivered: [], claimed: true, gestures: [] });
    return json(res, 200, houseState);
  }
  // A via impressa da rota (#2406): nesta estação do e2e não há impressora, e o servidor
  // recusa ANTES de compor, para não carimbar uma primeira via que não saiu.
  if (/\/deliveries\/couriers\/rides\/[A-Z0-9-]+\/slip\/?(\?|$)/.test(url) && req.method === "POST") {
    houseState.gestures.push({ gesture: "slip", ref: "", base_revision: "" });
    return json(res, 409, { detail: "Este dispositivo não tem impressora. A via sai no dispositivo que tem impressora.",
      agent: { can_print: false, agent_url: "" } });
  }
  const houseGesture = url.match(/\/deliveries\/couriers\/rides\/([A-Z0-9-]+)\/(depart|deliver|resend|release)\/?(\?|$)/);
  if (houseGesture) {
    if (req.method !== "POST") return json(res, 202, { outcome: "unknown" });
    return void readBody(req).then((body) => {
      useHouseStore(store);
      const gesture = houseGesture[2];
      houseState.gestures.push({ gesture, ref: body.ref ?? "", base_revision: body.base_revision });
      let detail = "";
      if (gesture === "depart") {
        houseState.departed = true;
        detail = "Rota C: Diego saiu para entrega.";
      } else if (gesture === "deliver") {
        houseState.delivered.push(body.ref);
        detail = `${String(body.ref).slice(-3)} entregue.`;
      } else if (gesture === "release") {
        houseState.claimed = false;
        detail = "Link de Diego solto. O próximo celular que confirmar fica com ele.";
      } else {
        const text = "Corrida para você: Rota C. Abra o link no seu celular: https://loja.test/rota/tok7";
        return json(res, 200, { ok: true, outcome: "applied", detail: "Rota C reenviada para Diego.",
          link_url: "https://loja.test/rota/tok7", whatsapp_url: `https://wa.me/5543999990000?text=${encodeURIComponent(text)}` });
      }
      json(res, 200, { ok: true, outcome: "applied", detail });
    });
  }
  if (houseScenario && /\/backstage\/deliveries\/?(\?|$)/.test(url)) return json(res, 200, houseDeliveries());
  if (/\/e2e\/deliveries\/house\/?(\?|$)/.test(url)) {
    if (req.method === "DELETE") {
      housePosts.length = 0;
      Object.assign(crewState, { diego: true, rui: false });
    }
    return json(res, 200, { rides: housePosts, shift: crewState });
  }
  const shiftPost = url.match(/\/deliveries\/couriers\/([a-z]+)\/shift\/?(\?|$)/);
  if (shiftPost && req.method === "POST") {
    return void readBody(req).then((body) => {
      useHouseStore(store);
      crewState[shiftPost[1]] = Boolean(body.on_shift);
      json(res, 200, crewBody(""));
    });
  }
  if (/\/deliveries\/couriers\/ride\/?(\?|$)/.test(url)) {
    if (req.method !== "POST") return json(res, 202, { outcome: "unknown" });
    return void readBody(req).then((body) => {
      useHouseStore(store);
      housePosts.push(body);
      const name = body.courier === "rui" ? "Rui" : "Diego";
      const many = body.refs.length > 1;
      const label = many ? "Rota C" : `Pedido ${body.refs[0].slice(-3)}`;
      const link = `https://loja.test/rota/tok${housePosts.length}`;
      const text = `Corrida para você: ${label}. Abra o link no seu celular: ${link}`;
      json(res, 200, { ok: true, outcome: "applied", refs: body.refs, ride_ref: `CASA-${housePosts.length}`,
        link_url: link, whatsapp_url: `https://wa.me/5543999990000?text=${encodeURIComponent(text)}`,
        detail: `${label} ${many ? "enviada" : "enviado"} para ${name}.`, ride_number: body.ride_number ?? 3,
        ride_letter: "C" });
    });
  }
  if (/\/deliveries\/couriers\/?(\?|$)/.test(url)) {
    return json(res, 200, crewScenario ? crewBody(url, crewMode) : { active: false, service: null, default: { ref: "taon", name: "TaOn" }, couriers: [] });
  }
  // M3c: `e2e_crew=alone` é a loja só com os entregadores da casa (TaOn desligada);
  // `e2e_crew=nobody` é sem TaOn e sem casa: a página só informa.
  if (/(?:^|;\s*)e2e_crew=nobody(?:;|$)/.test(req.headers.cookie || "") && /\/backstage\/deliveries\/?(\?|$)/.test(url))
    return json(res, 200, { ...DELIVERIES, courier_on: false, house_on: false });
  if (crewScenario && /\/backstage\/deliveries\/?(\?|$)/.test(url))
    return json(res, 200, { ...crewDeliveries(), ...(crewMode === "alone" ? { courier_on: false, house_on: true, ride_plan: { ...DELIVERIES.ride_plan, suggestions: [] } } : { house_on: true }) });
  const f10Scenario = (req.headers.cookie || "").match(/(?:^|;\s*)e2e_f10=(fiscal|countfail)(?:;|$)/)?.[1] ?? "";
  const callScenario = /(?:^|;\s*)e2e_call=on(?:;|$)/.test(req.headers.cookie || "");
  if (/\/backstage\/deliveries\/count\/?(\?|$)/.test(url)) {
    return json(res, 200, {
      waiting: f10Scenario === "countfail" ? null : DELIVERIES.waiting.length,
      call_refs: callScenario ? CALL_REFS : [],
    });
  }
  if (callScenario && /\/backstage\/deliveries\/?(\?|$)/.test(url)) return json(res, 200, crewDeliveries());
  if (/\/e2e\/call\/?(\?|$)/.test(url)) {
    if (req.method === "DELETE") callPosts.length = 0;
    return json(res, 200, { calls: callPosts, rides: ridePosts });
  }
  const dispatchPost = url.match(/\/orders\/([A-Z0-9-]+)\/courier-dispatch\/?(\?|$)/);
  if (callScenario && dispatchPost) {
    if (req.method !== "POST") return json(res, 200, { outcome: "not_found" });
    return void readBody(req).then((body) => {
      callPosts.push({ ref: dispatchPost[1], ...body });
      json(res, 200, { outcome: "applied", status: "queued", directive_id: callPosts.length });
    });
  }
  if (callScenario && /\/orders\/?(\?|$)/.test(url)) return json(res, 200, callQueue());
  const callOrder = callScenario ? url.match(/\/orders\/([A-Z0-9-]+)\/?(\?|$)/) : null;
  if (callOrder && callDetail(callOrder[1])) return json(res, 200, { order: callDetail(callOrder[1]) });
  if (f10Scenario === "fiscal" && /\/backstage\/deliveries\/?(\?|$)/.test(url)) return json(res, 200, f10Deliveries());
  if (/(?:^|;\s*)e2e_close=on(?:;|$)/.test(req.headers.cookie || "") && /\/backstage\/deliveries\/?(\?|$)/.test(url))
    return json(res, 200, { ...DELIVERIES, rides: DELIVERIES.rides.map((ride) => ride.letter === "A"
      ? { ...ride, open_too_long: true, close_here_action: CLOSE_HERE_ACTION } : ride) });
  if (/\/e2e\/close-here\/?(\?|$)/.test(url)) {
    if (req.method === "DELETE") closePosts.length = 0;
    return json(res, 200, { posts: closePosts });
  }
  const closePost = url.match(/\/orders\/([A-Z0-9-]+)\/courier-close-here\/?(\?|$)/);
  if (closePost && req.method === "POST") {
    return void readBody(req).then((body) => {
      closePosts.push({ ref: closePost[1], ...body });
      json(res, 200, { outcome: "applied", closed: [closePost[1]], order: null });
    });
  }
  // #2737 (cookie `e2e_failed=on`): a corrida C de A47 e C03 voltou porque ninguém
  // aceitou, e a de D12 a TaOn cancelou (a letra dela já é de outra corrida).
  if (/(?:^|;\s*)e2e_failed=on(?:;|$)/.test(req.headers.cookie || "") && /\/backstage\/deliveries\/?(\?|$)/.test(url))
    return json(res, 200, { ...DELIVERIES, failed_rides: FAILED_RIDES });
  if (/\/backstage\/deliveries\/?(\?|$)/.test(url))
    return json(res, 200, process.env.MOCK_F4B ? f4bDeliveries() : process.env.MOCK_F4A ? f4aDeliveries() : DELIVERIES);
  if (/\/orders\/courier-ride\/quote\/?(\?|$)/.test(url)) return json(res, 200, rideQuote(url) ?? { estimate: null, detail: "Escolha de 1 a 4 pedidos." });
  if (/\/e2e\/deliveries\/rides\/?(\?|$)/.test(url)) {
    if (req.method === "DELETE") ridePosts.length = 0;
    return json(res, 200, { rides: ridePosts });
  }
  if (/\/orders\/courier-ride\/?(\?|$)/.test(url)) {
    if (req.method !== "POST") return json(res, 200, { outcome: "not_found" });
    return void readBody(req).then((body) => {
      ridePosts.push(body);
      json(res, 200, { outcome: "applied", refs: body.refs, directive_id: ridePosts.length, status: "queued",
        ride_number: body.ride_number ?? null, ride_letter: "" });
    });
  }
  const promiseVariant = (req.headers.cookie || "").match(/(?:^|;\s*)e2e_promise=(risk|closed)(?:;|$)/)?.[1] ?? "";
  const promiseScenario = Boolean(promiseVariant);
  if (promiseScenario && /\/e2e\/promise\/reset\/?(\?|$)/.test(url)) {
    promiseState.resolved = false;
    promiseState.edits = [];
    return json(res, 200, { ok: true });
  }
  if (promiseScenario && /\/e2e\/promise\/state\/?(\?|$)/.test(url)) return json(res, 200, promiseState);
  if (promiseScenario && /\/orders\/?(\?|$)/.test(url)) {
    return json(res, 200, {
      queue: { ...QUEUE.queue, prep: [promiseCard(), ...QUEUE.queue.prep], total_count: QUEUE.queue.total_count + 1 },
    });
  }
  if (promiseScenario && url.includes(`/orders/${PROMISE_REF}/`)) {
    // A leitura do diálogo: 409 quando o pedido já não está em risco.
    if (/\/promise-resolution\/?(\?|$)/.test(url)) {
      return promiseState.resolved
        ? json(res, 409, { detail: "Este pedido não tem mais promessa em risco." })
        : json(res, 200, promiseResolution(promiseVariant));
    }
    if (/\/edit\/?(\?|$)/.test(url)) {
      if (req.method !== "POST") return json(res, 202, { outcome: "unknown", detail: "Ainda não há resultado confirmado para esta intenção." });
      return void readBody(req).then((body) => {
        // A rota exige a revisão e quem a tela leu: sem elas, recusa (como o servidor).
        if (!body.base_revision || body.expected_actor_id !== SESSION.operator.id)
          return json(res, 400, { detail: "Esta tela está desatualizada. Atualize o pedido e tente de novo.", code: "intention_required" });
        promiseState.edits.push({ items: body.items, base_revision: body.base_revision, expected_actor_id: body.expected_actor_id });
        promiseState.resolved = true;
        json(res, 200, { ok: true, ref: PROMISE_REF, outcome: "applied", changed: true, revision: "edit-fixture-2", order: promiseOrder() });
      });
    }
    if (new RegExp(`/orders/${PROMISE_REF}/?(\\?|$)`).test(url)) return json(res, 200, { order: promiseOrder() });
  }
  if (houseScenario && /\/orders\/?(\?|$)/.test(url)) return json(res, 200, houseQueue());
  if (/\/orders\/?(\?|$)/.test(url)) return json(res, 200, QUEUE);
  if (cancelScenario && /\/e2e\/deliveries\/reset\/?(\?|$)/.test(url)) {
    cancelState.clear();
    return json(res, 200, { ok: true });
  }
  if (cancelScenario && /\/e2e\/deliveries\/sent\/?(\?|$)/.test(url)) {
    return json(res, 200, { sent: [...cancelState.entries()].map(([key, value]) => ({ key, reason_id: value.sent })) });
  }
  const custodyScenario = /(?:^|;\s*)e2e_custody=on(?:;|$)/.test(req.headers.cookie || "");
  if (custodyScenario && /\/e2e\/custody\/?(\?|$)/.test(url)) {
    if (req.method === "DELETE") custodyState.body = null;
    return json(res, 200, { body: custodyState.body });
  }
  if (custodyScenario && new RegExp(`/orders/${CUSTODY_REF}/courier-custody/?(\\?|$)`).test(url)) {
    if (req.method !== "POST") return json(res, 200, { outcome: custodyState.body ? "applied" : "not_found" });
    return void readBody(req).then((body) => {
      custodyState.body = { change_out: body.change_out ?? null, equipment: body.equipment ?? [] };
      json(res, 200, { outcome: "applied", order: custodyOrder() });
    });
  }
  if (custodyScenario && new RegExp(`/orders/${CUSTODY_REF}/?(\\?|$)`).test(url)) return json(res, 200, { order: custodyOrder() });
  const rideCancelPost = url.match(/\/orders\/([A-Z0-9-]+)\/courier-cancel\/?(\?|$)/);
  if (cancelScenario && rideCancelPost) {
    const fixture = RIDE_FIXTURES.find((item) => item.stops.some(([ref]) => ref === rideCancelPost[1]));
    if (!fixture) return json(res, 404, { detail: "Pedido não encontrado." });
    if (req.method !== "POST") return json(res, 200, { outcome: cancelState.has(fixture.key) ? "applied" : "not_found" });
    return void readBody(req).then((body) => {
      cancelState.set(fixture.key, { state: "pending", sent: body.reason_id ?? null });
      json(res, 200, { outcome: "applied", status: "queued", directive_id: fixture.number, order: rideOrder(rideCancelPost[1]) });
    });
  }
  const detail = url.match(/\/orders\/([A-Z0-9-]+)\/?(\?|$)/);
  if (detail) {
    const inRide = cancelScenario ? rideOrder(detail[1]) : null;
    if (inRide) return json(res, 200, { order: inRide });
    const card = queueCard(detail[1]);
    return card
      ? json(res, 200, { order: { ...card, ...DETAIL_EXTRA, pending: pendingFor(card) } })
      : json(res, 404, { detail: "Pedido não encontrado." });
  }
  if (/\/alerts\/?(\?|$)/.test(url)) return json(res, 200, { alerts: [], counts: { active: 0, critical: 0 } });
  return json(res, 200, {});
});

server.listen(port, "127.0.0.1", () => {
  // eslint-disable-next-line no-console
  console.log(`[gestor-mock] listening on http://127.0.0.1:${port}`);
});

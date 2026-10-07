// Cenário `gallery` do mock visual: um cartão por combinação de estado que o
// quadro sabe desenhar. As fixtures capturadas do seed só trazem preparo
// bloqueado; aqui cada cartão parte de um deles e troca apenas os campos que a
// projeção real preencheria naquele estado (mesmos nomes do contrato gerado).
// Serve para inspeção visual, não para afirmar regra de domínio.

const iso = (offsetSeconds) => new Date(Date.now() + offsetSeconds * 1000).toISOString();

function action(ref, label, over = {}) {
  return {
    ref, label, enabled: true, reason: "", priority: "primary", kind: "mutation", href: "",
    method: "POST", payload_schema: { expected_actor_id: 1, base_revision: "gallery" },
    idempotency: "required", confirmation: {}, ...over,
  };
}

const menu = [
  action("volumes", "Declarar volumes", { priority: "secondary" }),
  action("assign", "Atender", { priority: "secondary" }),
];

function station(over) {
  return {
    station_ref: "cafes", station_name: "Cafés", prints: true, state: "in_progress",
    state_label: "em preparo", paper_label: "", paper_failed: false, cancelled_items: 0,
    can_mark_ready: false, recall_ticket_pk: null, ...over,
  };
}

export function galleryQueue(base) {
  const make = (suffix, over) => ({
    ...JSON.parse(JSON.stringify(base)),
    ref: `WEB-261007-${suffix}`,
    server_now_iso: iso(0),
    created_at_iso: iso(-600),
    elapsed_seconds: 600,
    timer_class: "timer-ok",
    advance_block_reason: "",
    advance_block_label: "",
    payment_status: "captured",
    payment_pending: false,
    payment_tone: "success",
    payment_status_label: "Pago",
    can_advance: true,
    undo: null,
    kitchen: null,
    awaiting_work_orders: [],
    confirmation_deadline_iso: "",
    attention: "",
    attention_since_iso: iso(-420),
    goal_minutes: 10,
    goal_label: "meta 10",
    ...over,
  });

  const intake = [
    make("N01", { attention: "confirm",
      status: "new", status_label: "Novo", can_confirm: true, customer_name: "Ana Paula Rodrigues",
      items_summary: "2x Croissant · 1x Pain au chocolat · 1x Café coado", items_count: 4,
      confirmation_deadline_iso: iso(140), confirmation_action: "confirm",
      actions: [action("confirm", "Aceitar"), action("reject", "Recusar", { priority: "danger" }), ...menu],
    }),
    make("I02", { attention: "confirm",
      status: "new", status_label: "Novo", can_confirm: true, channel_ref: "ifood",
      channel_display_id: "8841", customer_name: "Bruno",
      test_order_label: "Pedido de teste do iFood",
      test_order_notice: "Homologação: não produza nem entregue. Aceite ou recuse para o iFood registrar.",
      ifood_schedule_label: "Agendado pelo iFood para 18:30",
      ifood_pickup_code: "4821",
      confirmation_deadline_iso: iso(40), confirmation_action: "cancel",
      payment_method_label: "Pago no iFood", payment_tone: "success",
      actions: [action("confirm", "Aceitar"), action("reject", "Recusar", { priority: "danger" })],
    }),
  ];

  const prep = [
    make("B03", { attention: "blocked", attention_since_iso: iso(-1500), advance_block_label: "Pix pendente",
      status: "accepted", status_label: "Aceito", payment_status: "pending", payment_pending: true,
      payment_tone: "warning", payment_method_label: "Pix",
      advance_block_reason: "Pagamento ainda não foi confirmado. O pedido só avança depois que o dinheiro entra.",
      actions: [action("advance", "Iniciar preparo", { enabled: false, reason: "Pix pendente" }), ...menu],
    }),
    make("K04", { attention: "station",
      status: "preparing", status_label: "Em preparo", customer_name: "Carla",
      items_summary: "1x Quiche lorraine · 2x Cappuccino · 1x Suco de laranja", items_count: 4,
      has_customer_note: true, is_gift: true, assigned_operator: "Admin",
      kitchen: { order_pk: 4, missing_label: "Faltam Bebidas e Salgados", stations: [
        station({ station_ref: "cafes", station_name: "Cafés", state: "done", state_label: "pronto" }),
        station({ station_ref: "bebidas", station_name: "Bebidas", prints: true, paper_label: "Papel impresso", can_mark_ready: true }),
        station({ station_ref: "salgados", station_name: "Salgados", paper_failed: true, paper_label: "Papel não saiu na impressora", state: "pending", state_label: "na fila", cancelled_items: 1 }),
      ] },
      actions: [action("advance", "Marcar pronto", { priority: "menu" }), ...menu],
    }),
    make("A05", { attention: "handoff",
      status: "ready", status_label: "Pronto", customer_name: "Diego",
      ready_at_iso: iso(-30),
      kitchen: { order_pk: 5, missing_label: "", stations: [
        station({ station_name: "Cafés", state: "done", state_label: "pronto", recall_ticket_pk: 51 }),
      ] },
      undo: { kind: "auto_ready", label: "Pronto · automático", detail: "Cozinha concluiu às 14:59",
        undo_until_iso: iso(95), action_ref: "undo-ready", held_effect: "Aviso de pronto ao cliente" },
      actions: [action("undo-ready", "Desfazer", { priority: "secondary" }), action("advance", "Entregar a Diego"), ...menu],
    }),
    make("W06", { attention: "start",
      status: "accepted", status_label: "Aceito", customer_name: "Elisa",
      waitlist_label: "Esperando o lote das 16:00", waitlist_state: "confirming",
      awaiting_work_orders: [
        { ref: "WO-101", output_sku: "BAGUETE", status_label: "no forno", progress_pct: 60 },
        { ref: "WO-102", output_sku: "CROISSANT-MANTEIGA-TRADICIONAL", status_label: "fermentando", progress_pct: 20 },
      ],
      fiscal_status: "failed", fiscal_status_label: "NFC-e rejeitada",
      actions: [action("advance", "Iniciar preparo"), ...menu],
    }),
    make("ERR07", { attention: "start",
      status: "accepted", status_label: "Aceito", customer_name: "Fábio (ação falha)",
      actions: [action("advance", "Iniciar preparo"), ...menu],
    }),
  ];

  const expedition_pickup = [
    make("P08", { attention: "handoff", goal_label: "no balcão",
      status: "ready", status_label: "Pronto", customer_name: "Gabriela", ready_at_iso: iso(-120),
      payment_method: "cash", payment_method_label: "Dinheiro na retirada", payment_tone: "neutral",
      can_settle_delivery_cash: true,
      actions: [action("advance", "Entregar a Gabriela"), action("settle-delivery-cash", "Receber", { priority: "secondary" }), ...menu],
    }),
    make("H09", {
      status: "completed", status_label: "Entregue", customer_name: "Heitor", ready_at_iso: iso(-300),
      undo: { kind: "handoff", label: "Entregue às 15:00", detail: "O aviso ao cliente sai quando o prazo acabar.",
        undo_until_iso: iso(25), action_ref: "undo-handoff", held_effect: "Aviso ao cliente e fim do pedido" },
      actions: [action("undo-handoff", "Desfazer", { priority: "secondary" })],
    }),
  ];

  const expedition_delivery = [
    make("D10", { attention: "dispatch", attention_since_iso: iso(-780),
      status: "ready", status_label: "Pronto", customer_name: "Isabela Monteiro de Albuquerque",
      fulfillment_type: "delivery", fulfillment_label: "Entrega", fulfillment_icon: "delivery",
      delivery_address: "Rua Professor João Cândido, 1234, apto 1802, bloco B, Jardim Higienópolis, Londrina",
      change_label: "Troco para R$ 50,00: levar R$ 24,00", payment_method: "cash",
      payment_method_label: "Dinheiro na entrega", payment_tone: "neutral",
      danfe_printable: true, danfe_printed: false, danfe_state: "not_printed",
      danfe_problem: "A impressora do despacho não respondeu. Confira o papel e imprima de novo.",
      dispatch_needs_machine: true, volumes: 2, ready_at_iso: iso(-60),
      actions: [action("advance", "Despachar"), ...menu],
    }),
    make("D11", { attention: "dispatch",
      status: "ready", status_label: "Pronto", customer_name: "João",
      fulfillment_type: "delivery", fulfillment_label: "Entrega", fulfillment_icon: "delivery",
      delivery_address: "Av. Higienópolis, 900", danfe_printable: true, danfe_printed: true,
      danfe_state: "printed", equipment_back_pending: true, can_settle_delivery_cash: true,
      payment_method: "card", payment_method_label: "Cartão na entrega", payment_tone: "warning",
      actions: [action("advance", "Despachar"), action("settle-delivery-cash", "Acertar", { priority: "secondary" }),
        action("reject", "Cancelar", { priority: "danger" }), ...menu],
    }),
  ];

  const expedition_delivery_transit = [
    make("T12", { attention: "courier_back",
      status: "dispatched", status_label: "Saiu", customer_name: "Karina",
      fulfillment_type: "delivery", fulfillment_label: "Entrega", fulfillment_icon: "delivery",
      delivery_address: "Rua Pará, 456", dispatched_at_iso: iso(-900),
      courier_status_label: "Entregador a 5 min do cliente",
      equipment_label: "Maquininha Stone 2", trip_with: ["WEB-261007-T13"],
      change_label: "Troco de R$ 24,00 precisa voltar", change_back_pending: true,
      actions: [action("courier-back", "Entregador voltou"), ...menu],
    }),
  ];

  const preorders = [
    make("S14", {
      status: "accepted", status_label: "Aceito", customer_name: "Lucas",
      is_preorder: true, commitment_date: iso(86400).slice(0, 10), commitment_date_display: "amanhã, 08:00",
      actions: [action("advance", "Iniciar preparo"), ...menu],
    }),
  ];

  const ifood_negotiation_orders = [
    make("I15", {
      status: "preparing", status_label: "Em preparo", channel_ref: "ifood", channel_display_id: "9921",
      customer_name: "Marina",
      ifood_negotiations: [{ id: "neg-1", kind: "cancellation", label: "Cliente pediu cancelamento", deadline_iso: iso(300) }],
      ifood_cancellation_notice: "O cliente pediu cancelamento no iFood. Responda até 15:10.",
      ifood_remote_ahead_label: "No iFood este pedido já aparece como pronto.",
      actions: [action("advance", "Marcar pronto"), ...menu],
    }),
  ];

  return { intake, prep, expedition_pickup, expedition_delivery, expedition_delivery_transit, preorders, ifood_negotiation_orders };
}

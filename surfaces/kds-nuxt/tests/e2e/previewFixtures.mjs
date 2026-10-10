// Quadros de PRÉVIA do KDS: pedidos representativos para ver os cards sem o Django.
// Servidos pelo mockBackend quando `KDS_MOCK_FIXTURE=preview` (ver tests/e2e/README).
// Cobrem o que muda o desenho do card: pedido curto, pedido longo com observação por
// item + nota de cozinha + aviso de estoque, atrasado (entrega), iFood, adicional de
// uma comanda, comanda antiga riscada e o pedido de teste da homologação do iFood.
// A estação `cafes` mostra a MUDANÇA COM ALARDE (dono, 10/10/2026): item cancelado num
// pedido que continua, quantidade e observação novas, comanda que virou pedido e um
// pedido que caiu inteiro, cada um no próprio card até a ciência.
// Os valores de tempo são FIXOS (o KDS não conta sozinho: quem diz o tempo é a
// projection), então a mesma prévia sai igual toda vez.

const TODAY = "2026-09-21";

function ticket(overrides) {
  return {
    channel_icon: "language",
    customer_name: "",
    fulfillment_icon: "storefront",
    created_at_display: "08:00",
    elapsed_seconds: 120,
    target_seconds: 900,
    timer_class: "timer-ok",
    items: [],
    status: "pending",
    previous_tab_ref: "",
    is_scheduled: false,
    is_expedition: false,
    status_label: "Na fila",
    is_cancelled: false,
    cancelled_at_display: "",
    completed_at_display: "",
    kitchen_note: "",
    customer_note: "",
    test_order_label: "",
    changes: [],
    change_ticket_pks: [],
    ...overrides,
  };
}

function item(qty, name, extra = {}) {
  return { sku: name.toUpperCase().replace(/\W+/g, "-"), name, qty, notes: "", stock_warning: "", ...extra };
}

export const PREP_TICKETS = [
  ticket({
    pk: 101,
    order_ref: "WEB-260921-0131",
    customer_name: "Rafael Souza",
    fulfillment_icon: "local_shipping",
    elapsed_seconds: 1520,
    timer_class: "timer-late",
    status: "in_progress",
    status_label: "Em preparo",
    items: [item("3", "Pão de queijo"), item("1", "Café coado grande")],
  }),
  ticket({
    pk: 102,
    order_ref: "BAL-260921-0138",
    channel_icon: "storefront",
    customer_name: "Mariana Albuquerque",
    elapsed_seconds: 640,
    timer_class: "timer-warning",
    status: "in_progress",
    status_label: "Em preparo",
    kitchen_note: "Alergia a castanhas: separar utensílios.",
    customer_note: "Pão bem tostado, por favor.",
    items: [
      item("1", "Sanduíche de presunto cru e brie no pão de fermentação natural", {
        notes: "sem rúcula · mostarda à parte",
      }),
      item("2", "Quiche lorraine", { notes: "aquecer" }),
      item("1", "Tartine de abacate", { stock_warning: "Restam 2 abacates no estoque" }),
    ],
  }),
  ticket({
    pk: 103,
    order_ref: "IFD-260921-4821",
    channel_icon: "fastfood",
    customer_name: "Juliana (iFood)",
    fulfillment_icon: "local_shipping",
    elapsed_seconds: 300,
    items: [item("2", "Croissant de manteiga"), item("1", "Pain au chocolat")],
  }),
  ticket({
    pk: 104,
    order_ref: "WEB-260921-0142",
    customer_name: "Ana",
    elapsed_seconds: 45,
    items: [item("2", "Croissant de manteiga")],
  }),
  ticket({
    pk: 105,
    order_ref: "BAL-260921-0127",
    channel_icon: "storefront",
    customer_name: "12",
    previous_tab_ref: "12",
    elapsed_seconds: 200,
    items: [item("1", "Croque monsieur", { notes: "bem gratinado" })],
  }),
  ticket({
    pk: 106,
    order_ref: "BAL-260921-0138",
    channel_icon: "storefront",
    customer_name: "Mariana Albuquerque",
    elapsed_seconds: 60,
    items: [item("1", "Suco de laranja 300 ml")],
  }),
  ticket({
    pk: 107,
    order_ref: "IFD-260921-9001",
    channel_icon: "fastfood",
    customer_name: "PEDIDO DE TESTE",
    fulfillment_icon: "local_shipping",
    elapsed_seconds: 90,
    test_order_label: "Pedido de teste do iFood",
    items: [item("1", "Baguete tradicional (NÃO ENTREGAR)")],
  }),
];

/** A estação dos alarmes: o que mudou depois de chegar à cozinha. */
export const CHANGED_TICKETS = [
  ticket({
    seen: true,
    pk: 201,
    order_ref: "BAL-261010-0151",
    channel_icon: "storefront",
    elapsed_seconds: 410,
    status: "in_progress",
    status_label: "Em preparo",
    items: [item("2", "Cappuccino"), item("1", "Croissant de manteiga")],
    changes: [{ kind: "cancelled", text: "Cancelado: 1× Pão de queijo" }],
    change_ticket_pks: [301],
  }),
  ticket({
    seen: true,
    pk: 203,
    order_ref: "WEB-261010-0160",
    elapsed_seconds: 95,
    items: [item("1", "Pão de queijo"), item("1", "Tapioca", { notes: "sem glúten" })],
    changes: [
      { kind: "qty", text: "Pão de queijo: agora 1, eram 3" },
      { kind: "note", text: "Observação nova em Tapioca: sem glúten" },
    ],
    change_ticket_pks: [302, 303],
  }),
  ticket({
    seen: true,
    pk: 202,
    order_ref: "BAL-261010-0152",
    channel_icon: "storefront",
    previous_tab_ref: "Mesa 5",
    elapsed_seconds: 240,
    items: [item("1", "Croque monsieur")],
    changes: [{ kind: "moved", text: "Era a comanda Mesa 5" }],
  }),
  ticket({
    seen: true,
    pk: 204,
    order_ref: "WEB-261010-0161",
    elapsed_seconds: 60,
    items: [item("2", "Café coado grande")],
  }),
];

export const CANCELLED_TICKETS = [
  ticket({
    seen: true,
    pk: 205,
    order_ref: "IFD-261010-4830",
    channel_icon: "fastfood",
    fulfillment_icon: "local_shipping",
    status: "cancelled",
    status_label: "Cancelado",
    is_cancelled: true,
    cancelled_at_display: "08:22",
    elapsed_seconds: 300,
    items: [item("1", "Croque monsieur"), item("2", "Suco de laranja 300 ml")],
  }),
];

export const PREVIEW_INDEX = {
  instances: [
    { ref: "bancada", name: "Bancada", type: "prep", type_display: "Preparo", active_count: PREP_TICKETS.length },
    // As outras estações da casa, como o seed as cria: a navegação da Cozinha lista
    // cada uma pelo nome, e a Saída vira o atalho para o Gestor.
    { ref: "cafes", name: "Cafés", type: "prep", type_display: "Preparo", active_count: CHANGED_TICKETS.length },
    { ref: "lanches", name: "Lanches", type: "prep", type_display: "Preparo", active_count: 0 },
    { ref: "encomendas", name: "Encomendas", type: "picking", type_display: "Separação", active_count: 1 },
    { ref: "saida", name: "Saída", type: "expedition", type_display: "Saída", active_count: 3 },
  ],
};

function boardFor(ref, tickets, name, cancelled = []) {
  return {
    board: {
      instance_ref: ref,
      instance_name: name,
      instance_type: "prep",
      is_expedition: false,
      tickets,
      counts: {
        pending: tickets.filter((t) => t.status === "pending").length,
        in_progress: tickets.filter((t) => t.status === "in_progress").length,
        total: tickets.length,
      },
      service_date: TODAY,
      service_date_display: "Hoje",
      today: TODAY,
      available_dates: [TODAY],
      cancelled_tickets: cancelled,
      recent_done: [],
    },
  };
}

/** Estado vivo da prévia: iniciar e Pronto mudam o quadro, para que dê
 *  para tocar nos botões e ver o card responder. Reiniciar o mock volta ao começo. */
export function createPreviewState() {
  const prep = PREP_TICKETS.map((t) => ({ ...t }));
  const changed = CHANGED_TICKETS.map((t) => ({ ...t }));
  const cancelled = CANCELLED_TICKETS.map((t) => ({ ...t }));
  return {
    index: () => PREVIEW_INDEX,
    /** Volta ao começo (a matriz visual chama antes de cada caso: um caso que dá
     *  ciência num card não pode apagar o alarme da captura seguinte). */
    reset() {
      prep.splice(0, prep.length, ...PREP_TICKETS.map((t) => ({ ...t })));
      changed.splice(0, changed.length, ...CHANGED_TICKETS.map((t) => ({ ...t })));
      cancelled.splice(0, cancelled.length, ...CANCELLED_TICKETS.map((t) => ({ ...t })));
    },
    board(ref) {
      const name = PREVIEW_INDEX.instances.find((inst) => inst.ref === ref)?.name || ref;
      if (ref === "cafes") return boardFor(ref, changed, name, cancelled);
      return boardFor(ref, ref === "bancada" ? prep : [], name);
    },
    /** Aplica um POST de escrita; devolve true se reconheceu a rota. */
    write(url) {
      // A ciência da mudança: o card vivo perde a caixa vermelha; o cancelado sai.
      const seen = url.match(/\/kds\/tickets\/(\d+)\/(changes\/seen|acknowledge)\/?/);
      if (seen) {
        const pk = Number(seen[1]);
        const i = changed.findIndex((t) => t.pk === pk);
        if (i >= 0) changed[i] = { ...changed[i], changes: [], change_ticket_pks: [] };
        const c = cancelled.findIndex((t) => t.pk === pk);
        if (c >= 0) cancelled.splice(c, 1);
        return true;
      }
      const m = url.match(/\/kds\/tickets\/(\d+)\/(start|done)\/?/);
      if (m) {
        const pk = Number(m[1]);
        for (const list of [prep, changed]) {
          const i = list.findIndex((t) => t.pk === pk);
          if (i >= 0 && m[2] === "start") list[i] = { ...list[i], status: "in_progress", status_label: "Em preparo" };
          if (i >= 0 && m[2] === "done") list.splice(i, 1);
        }
        return true;
      }
      return false;
    },
  };
}

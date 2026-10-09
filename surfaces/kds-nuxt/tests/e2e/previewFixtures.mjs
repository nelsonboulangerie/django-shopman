// Quadros de PRÉVIA do KDS: pedidos representativos para ver os cards sem o Django.
// Servidos pelo mockBackend quando `KDS_MOCK_FIXTURE=preview` (ver tests/e2e/README).
// Cobrem o que muda o desenho do card: pedido curto, pedido longo com observação por
// item + nota de cozinha + aviso de estoque, atrasado (entrega), iFood, adicional de
// uma comanda, comanda antiga riscada e o pedido de teste da homologação do iFood.
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
    kitchen_note: "Alergia a castanhas — separar utensílios.",
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
    items: [item("1", "Baguete tradicional — NÃO ENTREGAR")],
  }),
];

export const PREVIEW_INDEX = {
  instances: [
    { ref: "bancada", name: "Bancada", type: "prep", type_display: "Preparo", active_count: PREP_TICKETS.length },
    // As outras estações da casa, como o seed as cria: a navegação da Cozinha lista
    // cada uma pelo nome, e a Saída vira o atalho para o Gestor.
    { ref: "cafes", name: "Cafés", type: "prep", type_display: "Preparo", active_count: 2 },
    { ref: "lanches", name: "Lanches", type: "prep", type_display: "Preparo", active_count: 0 },
    { ref: "encomendas", name: "Encomendas", type: "picking", type_display: "Separação", active_count: 1 },
    { ref: "saida", name: "Saída", type: "expedition", type_display: "Saída", active_count: 3 },
  ],
};

function boardFor(ref, tickets, name) {
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
      cancelled_tickets: [],
      recent_done: [],
    },
  };
}

/** Estado vivo da prévia: iniciar e Pronto mudam o quadro, para que dê
 *  para tocar nos botões e ver o card responder. Reiniciar o mock volta ao começo. */
export function createPreviewState() {
  const prep = PREP_TICKETS.map((t) => ({ ...t }));
  return {
    index: () => PREVIEW_INDEX,
    board(ref) {
      const name = PREVIEW_INDEX.instances.find((inst) => inst.ref === ref)?.name || ref;
      return boardFor(ref, ref === "bancada" ? prep : [], name);
    },
    /** Aplica um POST de escrita; devolve true se reconheceu a rota. */
    write(url) {
      const m = url.match(/\/kds\/tickets\/(\d+)\/(start|done)\/?/);
      if (m) {
        const pk = Number(m[1]);
        const i = prep.findIndex((t) => t.pk === pk);
        if (i >= 0 && m[2] === "start") prep[i] = { ...prep[i], status: "in_progress", status_label: "Em preparo" };
        if (i >= 0 && m[2] === "done") prep.splice(i, 1);
        return true;
      }
      return false;
    },
  };
}

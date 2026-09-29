import { mockNuxtImport, mountSuspended, registerEndpoint } from "@nuxt/test-utils/runtime";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, reactive, ref } from "vue";

import DetailPage from "~/pages/preorders/[ref].vue";
import PreordersPage from "~/pages/preorders/index.vue";
import type { PreorderCard, PreorderDetail, PreorderListResponse, PreorderSearchResponse } from "~/types/preorders";

import { makeProjection } from "../composables/_posSaleHarness";

// A tela única das Encomendas (busca no topo, Dia | Semana, filtros, "Imprimir N
// vias") e o detalhe — que imprime a Via Pedido e oferece cada gesto (entregar,
// editar, reagendar, cancelar) só quando o servidor diz que pode.

const printOne = vi.fn().mockResolvedValue(true);
const printBatch = vi.fn().mockResolvedValue(true);
const call = vi.fn();
const kick = vi.fn().mockResolvedValue(true);

mockNuxtImport("usePosTerminal", () => async () => ({
  pos: computed(() => makeProjection({ has_open_cash_session: true })),
  pending: ref(false),
  refresh: vi.fn().mockResolvedValue(undefined),
}));
mockNuxtImport("useOperatorLock", () => () => ({ operator: ref({ name: "Ana" }), lock: vi.fn() }));
mockNuxtImport("usePosAction", () => () => ({ call }));
mockNuxtImport("useCounterAgent", () => () => ({ kick }));
mockNuxtImport("usePosOrderTickets", () => () => ({
  printOne,
  printBatch,
  printing: ref(false),
  printingRef: ref(""),
  hasPrinter: ref(true),
  printerUnavailableReason: ref(""),
}));
const navigate = vi.fn().mockResolvedValue(undefined);
mockNuxtImport("navigateTo", () => (...args: unknown[]) => navigate(...args));
// A rota é REATIVA: a tela guarda o estado na query, e o `replace` do router é
// o que muda a tela.
const route = reactive({ params: { ref: "NB-7" }, query: {} as Record<string, string>, path: "/preorders" });
const replace = vi.fn((to: { query: Record<string, string> }) => {
  route.query = { ...to.query };
  return Promise.resolve();
});
mockNuxtImport("useRoute", () => () => route);
mockNuxtImport("useRouter", () => () => ({
  replace,
  afterEach: vi.fn(),
  beforeResolve: vi.fn(),
}));

function card(partial: Partial<PreorderCard> = {}): PreorderCard {
  return {
    ref: "NB-7", channel_display_id: "", customer_name: "Ana Souza", channel_ref: "web",
    channel_label: "Loja online", fulfillment_type: "pickup", fulfillment_label: "Retirada",
    commitment_date: "2026-09-26", commitment_date_display: "hoje", window_label: "9h às 10h",
    window_start: "09:00", status: "accepted", situation: "to_pay", situation_label: "A pagar",
    payment_state: "to_receive",
    total_q: 3600, total_display: "R$ 36,00", balance_q: 3600, balance_display: "R$ 36,00",
    items_summary: "2x Pão", items_count: 2, ticket_printed: false, ...partial,
  };
}

let week: PreorderListResponse;
let detail: PreorderDetail;
let found: PreorderSearchResponse;
const searched = vi.fn();

registerEndpoint("/api/v1/backstage/pos/preorders/", () => week);
registerEndpoint("/api/v1/backstage/pos/preorders/search/", (event) => {
  searched(event.path);
  return found;
});
registerEndpoint("/api/v1/backstage/pos/preorders/NB-7/", () => ({
  order: detail,
  generated_at: "2026-09-26T12:00:00Z",
  contract_version: 1,
}));
registerEndpoint("/api/v1/backstage/pos/schedule/", () => ({
  ok: true, today: "2026-09-26", date: "2026-09-26", max_preorder_days: 30,
  available_dates: ["2026-09-26", "2026-09-27", "2026-09-28"],
  windows: [{ ref: "slot-09", label: "A partir das 9h" }], earliest_window_ref: "slot-09",
  ready_at: "", bottleneck_name: "", grid: "canonical", is_today: true, readiness_unavailable: false,
}));

const mounted: VueWrapper[] = [];
async function mount(page: unknown) {
  clearNuxtData();
  const wrapper = await mountSuspended(page as never, {
    global: { stubs: { PosFunctionRail: true, RailToggle: true, MoreBelow: true } },
  });
  mounted.push(wrapper as unknown as VueWrapper);
  await flushPromises();
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  week = {
    ok: true, date_from: "2026-09-26", date_to: "2026-10-02", today: "2026-09-26", max_batch: 200,
    count: 2, total_q: 6000, total_display: "R$ 60,00", to_receive_q: 3600, to_receive_display: "R$ 36,00",
    days: Array.from({ length: 7 }, (_, i) => ({
      date: `2026-09-${26 + i}`,
      date_display: "", weekday_display: ["sáb", "dom", "seg", "ter", "qua", "qui", "sex"][i]!,
      day_display: `${26 + i}/09`, is_today: i === 0,
      orders_count: i === 0 ? 2 : 0, total_q: i === 0 ? 6000 : 0,
      total_display: i === 0 ? "R$ 60,00" : "R$ 0,00",
      to_receive_q: i === 0 ? 3600 : 0, to_receive_display: i === 0 ? "R$ 36,00" : "R$ 0,00",
      orders: i === 0 ? [card(), card({ ref: "NB-8", customer_name: "Bia", fulfillment_type: "delivery", fulfillment_label: "Entrega", window_label: "14h às 15h", window_start: "14:00", total_q: 2400, total_display: "R$ 24,00", situation: "paid", situation_label: "Pago", payment_state: "paid", balance_q: 0, balance_display: "R$ 0,00", ticket_printed: true })] : [],
    })),
  };
  detail = {
    ref: "NB-7", status: "accepted", status_label: "Aceito", context: "pos",
    actions: [{ ref: "comment", label: "Comentar", enabled: true, reason: "", payload_schema: { base_revision: "rev-comment" } }],
    channel_ref: "web", channel_icon: "language", total_display: "R$ 36,00",
    customer_name: "Ana Souza", customer_ref: "C-1", customer_phone: "(43) 99988-7766",
    customer_phone_uri: "tel:+5543999887766", customer_whatsapp_url: "https://wa.me/5543999887766",
    customer_email: "", customer_relay_phone: "", customer_relay_code: "", customer_relay_expires_at: "",
    fulfillment_type: "pickup", fulfillment_label: "Retirada", schedule_label: "Hoje · 9h às 10h",
    delivery_address: "", delivery_instructions: "", payment_method_label: "Dinheiro na retirada",
    payment_status_label: "Pendente", payment_link_notice: "", test_order_notice: "",
    is_gift: false, gift_recipient_name: "", gift_recipient_phone: "", gift_message: "", gift_hide_values: false,
    customer_profile: null, fiscal_status_label: "", fiscal_links: [],
    items: [{ sku: "PAO", name: "Pão", qty: "2", unit_price_display: "R$ 18,00", total_display: "R$ 36,00" }],
    customer_note: "Sem açúcar", kitchen_note: "Separar antes das 9h", timeline: [],
    counter: {
      card: card(), ticket_printed: false, revision: "rev-1", actor_id: 7,
      hand_over: {
        allowed: true, needs_payment: true, amount_q: 3600, amount_display: "R$ 36,00",
        suggested_method: "cash", block_reason: "", digital_charge_notice: "",
      },
      cancel: { allowed: true, requires_approval: false, block_reason: "" },
      reschedule: {
        allowed: true, block_reason: "", date: "2026-09-26", slot: "slot-09",
        skus: ["PAO"], revision: "rev-schedule",
      },
      edit: { allowed: true, block_reason: "", cancel_and_redo: false, revision: "rev-edit" },
    },
    managers: [{ username: "gerente", name: "Gerente" }],
  };
  found = {
    ok: true, query: "ana", today: "2026-09-26", include_completed: false, completed_days: 30,
    open_count: 1, open: [card()], completed_count: 0, completed: [],
  };
  printOne.mockClear();
  printBatch.mockClear();
  replace.mockClear();
  searched.mockClear();
  call.mockReset();
  call.mockResolvedValue({ ok: true, received_q: 3600, status: "completed" });
  kick.mockClear();
  navigate.mockClear();
  route.query = {};
});
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  document.body.innerHTML = "";
});

describe("Detalhe — só lê e imprime a Via Pedido", () => {
  it("mostra quem, quanto falta, os itens e a observação do cliente", async () => {
    const wrapper = await mount(DetailPage);
    const text = wrapper.text();
    expect(text).toContain("Ana Souza");
    expect(wrapper.find("[data-order-detail]").attributes("data-order-context")).toBe("pos");
    expect(wrapper.find("[data-preorder-situation]").text()).toBe("A pagar");
    expect(wrapper.find("[data-preorder-money]").text()).toBe("R$ 36,00 a receber");
    expect(wrapper.find("[data-order-items]").text()).toContain("Pão");
    expect(text).toContain("Sem açúcar");
    expect(wrapper.find("[data-kitchen-note]").text()).toContain("Separar antes das 9h");
  });

  it("imprime a Via Pedido pela impressão individual que já existe", async () => {
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-preorder-print]").trigger("click");
    await flushPromises();
    expect(printOne).toHaveBeenCalledWith("NB-7");
  });

  it("⚠️ nenhum botão morto: Editar só existe quando o servidor diz que pode", async () => {
    detail.counter.edit = {
      ...detail.counter.edit,
      allowed: false,
      block_reason: "Esta encomenda já está pronta: não dá mais para editar.",
    };
    const wrapper = await mount(DetailPage);
    const buttons = wrapper.findAll("button").map((b) => b.text());
    expect(buttons.some((label) => label.includes("Editar"))).toBe(false);
  });
});

const body = () => document.body;
async function settle() {
  await flushPromises();
  await flushPromises();
}

describe("Detalhe — receber e entregar", () => {
  it("com saldo, o botão diz o gesto inteiro com o valor", async () => {
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-preorder-hand-over]").text()).toBe("Receber R$ 36,00 e entregar");
  });

  it("dinheiro com troco: o diálogo mostra o troco e manda a nota e a forma", async () => {
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-preorder-hand-over]").trigger("click");
    await settle();
    const received = body().querySelector<HTMLInputElement>("[data-preorder-received]")!;
    received.value = "50";
    received.dispatchEvent(new Event("input"));
    await settle();
    expect(body().querySelector("[data-preorder-change]")!.textContent!.replace(/\s/g, " ")).toContain("Troco: R$ 14,00");

    body().querySelector<HTMLButtonElement>("[data-preorder-hand-over-confirm]")!.click();
    await settle();

    expect(call).toHaveBeenCalledTimes(1);
    const [path, options] = call.mock.calls[0]!;
    expect(path).toBe("/api/v1/backstage/pos/preorders/NB-7/hand-over/");
    expect(options.body).toMatchObject({
      base_revision: "rev-1",
      tenders: [{ method: "cash", amount_q: 3600 }],
      cash_tendered_q: 5000,
    });
    expect(options.body.client_request_id).toBeTruthy();
    expect(kick).toHaveBeenCalledWith("preorder_cash");
  });

  it("dinheiro que não cobre o valor não deixa confirmar", async () => {
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-preorder-hand-over]").trigger("click");
    await settle();
    const received = body().querySelector<HTMLInputElement>("[data-preorder-received]")!;
    received.value = "20";
    received.dispatchEvent(new Event("input"));
    await settle();
    expect(body().querySelector("[data-preorder-change]")!.textContent!.replace(/\s/g, " ")).toContain("não cobre R$ 36,00");
    expect(body().querySelector<HTMLButtonElement>("[data-preorder-hand-over-confirm]")!.disabled).toBe(true);
  });

  it("já paga: o gesto é só Entregar, e não manda forma nenhuma", async () => {
    detail.counter.hand_over = {
      ...detail.counter.hand_over,
      needs_payment: false,
      amount_q: 0,
      amount_display: "R$ 0,00",
    };
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-preorder-hand-over]").text()).toBe("Entregar");
    await wrapper.find("[data-preorder-hand-over]").trigger("click");
    await settle();
    body().querySelector<HTMLButtonElement>("[data-preorder-hand-over-confirm]")!.click();
    await settle();
    expect(call.mock.calls[0]![1].body.tenders).toBeUndefined();
    expect(kick).not.toHaveBeenCalled();
  });

  it("Pix pendente: o diálogo diz que a cobrança do cliente será cancelada antes de receber", async () => {
    detail.counter.hand_over = {
      ...detail.counter.hand_over,
      suggested_method: "",
      digital_charge_notice: "O Pix enviado ao cliente será cancelado.",
    };
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-preorder-hand-over]").text()).toBe("Receber R$ 36,00 e entregar");
    await wrapper.find("[data-preorder-hand-over]").trigger("click");
    await settle();
    expect(body().querySelector("[data-preorder-digital-charge-notice]")!.textContent).toContain(
      "O Pix enviado ao cliente será cancelado.",
    );
    body().querySelector<HTMLButtonElement>("[data-preorder-hand-over-confirm]")!.click();
    await settle();
    expect(call.mock.calls[0]![1].body.tenders).toEqual([{ method: "cash", amount_q: 3600 }]);
  });

  it("o cliente acabou de pagar online: aviso na página e só Entregar", async () => {
    detail.counter.hand_over = {
      ...detail.counter.hand_over,
      digital_charge_notice: "O link de pagamento enviado ao cliente será cancelado.",
    };
    call.mockRejectedValueOnce({
      status: 409,
      data: {
        detail: "O cliente acabou de pagar online. Não receba no balcão: só entregue a encomenda.",
        error: { code: "preorder_paid_online" },
      },
    });
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-preorder-hand-over]").trigger("click");
    await settle();
    // O servidor registrou o pagamento: a leitura seguinte diz que não há saldo.
    detail.counter.hand_over = {
      ...detail.counter.hand_over,
      needs_payment: false,
      amount_q: 0,
      amount_display: "R$ 0,00",
      digital_charge_notice: "",
    };
    body().querySelector<HTMLButtonElement>("[data-preorder-hand-over-confirm]")!.click();
    await settle();

    expect(body().querySelector("[data-preorder-hand-over-dialog]")).toBeNull();
    expect(wrapper.find("[data-preorder-paid-online]").text()).toContain("acabou de pagar online");
    expect(wrapper.find("[data-preorder-hand-over]").text()).toBe("Entregar");
    expect(kick).not.toHaveBeenCalled();
  });

  it("quando não pode entregar, diz por quê em vez de mostrar botão apagado", async () => {
    detail.counter.hand_over = {
      ...detail.counter.hand_over,
      allowed: false,
      block_reason: "Esta encomenda ainda não está pronta (Em preparo).",
    };
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-preorder-hand-over]").exists()).toBe(false);
    expect(wrapper.find("[data-preorder-hand-over-blocked]").text()).toContain("ainda não está pronta");
  });
});

describe("Detalhe — as seções do Gestor, no balcão", () => {
  it("cliente e nota fiscal aparecem como no Gestor, quando o servidor manda", async () => {
    detail.customer_profile = {
      orders_label: "12 pedidos", last_order_display: "há 3 dias", average_ticket_display: "",
      favorite_product: "", segment_label: "", segment_tone: "", notes: "",
      dietary_restrictions: "Sem lactose", birthday_display: "", is_birthday_today: false,
    };
    detail.fiscal_status_label = "NFC-e autorizada";
    detail.fiscal_links = [{ label: "DANFE", href: "/danfe/NB-7" }];
    const wrapper = await mount(DetailPage);

    expect(wrapper.find("[data-customer-history]").text()).toBe("12 pedidos · última compra há 3 dias");
    expect(wrapper.find("[data-customer-restrictions]").text()).toBe("Sem lactose");
    expect(wrapper.find("[data-order-fiscal]").text()).toContain("NFC-e autorizada");
  });

  it("comenta no histórico pela rota do Gestor, com a base que o servidor mandou", async () => {
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-order-comment] textarea").setValue("Cliente vem às 9h30");
    await wrapper.find("[data-order-comment-submit]").trigger("click");
    await flushPromises();

    const [path, options] = call.mock.calls[0]!;
    expect(path).toBe("/api/v1/backstage/orders/NB-7/comment/");
    expect(options.body).toMatchObject({ note: "Cliente vem às 9h30", base_revision: "rev-comment" });
    expect(options.body.idempotency_key).toBeTruthy();
  });

  it("sem a ação de comentar, o balcão não ganha o campo", async () => {
    detail.actions = [];
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-order-comment]").exists()).toBe(false);
  });

  it("a volta leva ao recorte da lista de onde o operador veio", async () => {
    const wrapper = await mount(DetailPage);
    // Depois de montar: o `mountSuspended` passa pelo `router.replace` (o mock),
    // que zera a query antes de a página existir.
    route.query = { back: "/preorders?mode=week&date=2026-09-26&payment=to_receive" };
    await wrapper.find("[data-preorder-back]").trigger("click");
    expect(navigate).toHaveBeenCalledWith("/preorders?mode=week&date=2026-09-26&payment=to_receive");
  });

  it("uma volta para fora da seção é ignorada (não vira redirecionamento aberto)", async () => {
    const wrapper = await mount(DetailPage);
    route.query = { back: "https://exemplo.com/preorders" };
    await wrapper.find("[data-preorder-back]").trigger("click");
    expect(navigate).not.toHaveBeenCalledWith("https://exemplo.com/preorders");
  });
});

describe("Detalhe — cancelar", () => {
  it("cancela pela rota do Gestor, com a revisão e quem está identificado", async () => {
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-preorder-cancel]").trigger("click");
    await settle();
    const reason = body().querySelector<HTMLInputElement>("[data-preorder-cancel-reason]")!;
    reason.value = "Cliente desistiu";
    reason.dispatchEvent(new Event("input"));
    await settle();
    body().querySelector<HTMLButtonElement>("[data-preorder-cancel-confirm]")!.click();
    await settle();

    const [path, options] = call.mock.calls[0]!;
    expect(path).toBe("/api/v1/backstage/orders/NB-7/cancel/");
    expect(options.body).toMatchObject({ reason: "Cliente desistiu", base_revision: "rev-1", expected_actor_id: 7 });
    expect(options.body.idempotency_key).toBeTruthy();
  });

  it("encomenda paga: o servidor pede gerente e o PIN sobe; assinado, o gesto se repete com a assinatura", async () => {
    call.mockRejectedValueOnce({ status: 403, data: { detail: "Precisa de gerente.", error: { code: "manager_approval_required" } } });
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-preorder-cancel]").trigger("click");
    await settle();
    body().querySelector<HTMLButtonElement>("[data-preorder-cancel-confirm]")!.click();
    await settle();

    const auth = wrapper.findComponent({ name: "OperatorManagerAuth" });
    expect(auth.props("open")).toBe(true);
    auth.vm.$emit("authorize", "gerente", "1234");
    await settle();

    expect(call).toHaveBeenCalledTimes(2);
    expect(call.mock.calls[1]![1].body.manager_approval).toEqual({ username: "gerente", pin: "1234" });
    // Mesma tentativa, mesma chave: a primeira foi recusada antes de gravar.
    expect(call.mock.calls[1]![1].body.idempotency_key).toBe(call.mock.calls[0]![1].body.idempotency_key);
  });

  it("sem permissão para cancelar, não há botão", async () => {
    detail.counter.cancel = {
      allowed: false,
      requires_approval: false,
      block_reason: "Pedido do iFood: cancele pelo Gestor de pedidos.",
    };
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-preorder-cancel]").exists()).toBe(false);
  });
});

const refsIn = (wrapper: { findAll: (s: string) => { attributes: (n: string) => string | undefined }[] }) =>
  wrapper.findAll("[data-preorder]").map((c) => c.attributes("data-preorder"));

async function typeSearch(wrapper: Awaited<ReturnType<typeof mount>>, value: string) {
  await wrapper.find("[data-preorders-search]").setValue(value);
  await new Promise((resolve) => setTimeout(resolve, 300));
  await flushPromises();
  await flushPromises();
}

describe("Encomendas — a semana no centro", () => {
  it("abre na semana: sete colunas, a conta do dia no topo, o dia vazio por extenso", async () => {
    const wrapper = await mount(PreordersPage);
    const columns = wrapper.find("[data-week-grid]").findAll("[data-week-day]");
    expect(columns).toHaveLength(7);
    expect(columns[0]!.find("[data-week-day-total]").text()).toBe("2 encomendas · R$ 60,00");
    expect(columns[0]!.find("[data-week-day-to-receive]").text()).toBe("A receber R$ 36,00");
    expect(columns[1]!.find("[data-week-day-total]").text()).toBe("Nenhuma encomenda");
    expect(columns[1]!.find("[data-week-day-to-receive]").exists()).toBe(false);
    // Área estreita: o mesmo conteúdo, em lista por dia.
    expect(wrapper.find("[data-week-list]").findAll("[data-preorder]")).toHaveLength(2);
    expect(wrapper.find("[data-preorders-summary]").text()).toBe("2 encomendas · R$ 60,00 · A receber: R$ 36,00");
  });

  it("o card da grade: saldo em destaque ou 'pago', e o sinal da Via Pedido impressa", async () => {
    const wrapper = await mount(PreordersPage);
    const grid = wrapper.find("[data-week-grid]");
    expect(grid.find('[data-preorder="NB-7"] [data-preorder-money]').text()).toBe("R$ 36,00 a receber");
    expect(grid.find('[data-preorder="NB-8"] [data-preorder-money]').text()).toBe("pago");
    expect(grid.find('[data-preorder="NB-8"] [data-preorder-printed]').exists()).toBe(true);
    expect(grid.find('[data-preorder="NB-7"] [data-preorder-printed]').exists()).toBe(false);
    expect(grid.find('[data-preorder="NB-7"]').attributes("href")).toBe("/preorders/NB-7");
  });

  it("tocar no dia da grade abre o modo Dia naquela data", async () => {
    const wrapper = await mount(PreordersPage);
    await wrapper.find("[data-week-grid]").findAll("[data-week-day-open]")[0]!.trigger("click");
    expect(route.query).toEqual({ mode: "day", date: "2026-09-26" });
  });

  it("‹ › anda de semana em semana, e a volta para hoje aparece fora da semana de hoje", async () => {
    const wrapper = await mount(PreordersPage);
    expect(wrapper.find("[data-period-today]").exists()).toBe(false);
    await wrapper.find("[data-period-next]").trigger("click");
    await flushPromises();
    expect(route.query.date).toBeTruthy();
    expect(wrapper.find("[data-period-today]").exists()).toBe(true);
    expect(wrapper.find("[data-period-next]").attributes("aria-label")).toBe("Próxima semana");
  });

  it("semana sem nada diz por extenso — zero não é código", async () => {
    week = { ...week, count: 0, days: week.days.map((d) => ({ ...d, orders: [], orders_count: 0 })) };
    const wrapper = await mount(PreordersPage);
    expect(wrapper.find("[data-preorders-empty]").text()).toBe("Nenhuma encomenda nesta semana.");
    expect(wrapper.find("[data-preorders-print]").exists()).toBe(false);
  });
});

describe("Encomendas — o dia", () => {
  it("o modo Dia agrupa pela janela, com a linha inteira", async () => {
    const wrapper = await mount(PreordersPage);
    await wrapper.find("[data-week-grid]").findAll("[data-week-day-open]")[0]!.trigger("click");
    await flushPromises();
    const windows = wrapper.find("[data-preorders-day]").findAll("[data-preorders-window]");
    expect(windows.map((w) => w.find("h2").text())).toEqual(["9h às 10h", "14h às 15h"]);
    expect(wrapper.find("[data-period-next]").attributes("aria-label")).toBe("Próximo dia");
  });
});

describe("Encomendas — filtros e 'Imprimir N vias'", () => {
  it("chips combináveis com contagem; o filtro vai para a URL e muda a lista", async () => {
    const wrapper = await mount(PreordersPage);
    const payChips = wrapper.find('[data-preorders-filter="pay"]').findAll("[data-preorders-filter-chip]");
    expect(payChips.map((c) => c.attributes("aria-label"))).toEqual([
      "Pagamento, Todas: 2", "Pagamento, A receber: 1", "Pagamento, Pagas: 1",
    ]);
    await wrapper.find('[data-preorders-filter-chip="fulfillment:delivery"]').trigger("click");
    await flushPromises();
    expect(route.query).toEqual({ fulfillment: "delivery" });
    expect(refsIn(wrapper.find("[data-week-grid]"))).toEqual(["NB-8"]);
  });

  it("'Falta imprimir' mostra só o que não saiu, e o botão imprime exatamente o visível", async () => {
    const wrapper = await mount(PreordersPage);
    await wrapper.find('[data-preorders-filter-chip="print:pending"]').trigger("click");
    await flushPromises();
    expect(refsIn(wrapper.find("[data-week-grid]"))).toEqual(["NB-7"]);
    const button = wrapper.find("[data-preorders-print]");
    expect(button.text()).toBe("Imprimir 1 via");
    await button.trigger("click");
    await flushPromises();
    expect(printBatch).toHaveBeenCalledWith({ date_from: "2026-09-26", date_to: "2026-10-02", refs: ["NB-7"] });
  });

  it("filtro que esvazia a semana diz o que não há e oferece mostrar todas", async () => {
    const wrapper = await mount(PreordersPage);
    route.query.pay = "on_account";
    await flushPromises();
    expect(wrapper.find("[data-preorders-filter-empty]").text()).toContain("Nenhuma encomenda com estes filtros nesta semana.");
    expect(wrapper.find("[data-preorders-print]").text()).toBe("Nenhuma via para imprimir");
  });

  it("pagamento a conferir ganha aviso próprio", async () => {
    week.days[0]!.orders.push(card({ ref: "NB-9", payment_state: "check", balance_q: null, situation: "check_payment" }));
    const wrapper = await mount(PreordersPage);
    expect(wrapper.find("[data-preorders-check-notice]").text()).toContain("1 encomenda está com o pagamento a conferir");
  });
});

describe("Encomendas — Cliente veio buscar", () => {
  it("o campo está no topo, com a frase que diz o que se pode procurar", async () => {
    const wrapper = await mount(PreordersPage);
    const field = wrapper.find("[data-preorders-search]");
    expect(field.attributes("placeholder")).toBe("Cliente veio buscar? Nome, telefone, CPF, endereço ou número");
    expect(wrapper.find("[data-preorders-include-completed]").attributes("aria-checked")).toBe("false");
  });

  it("digitar troca o período pelo resultado em aberto, e a busca vai para a URL", async () => {
    const wrapper = await mount(PreordersPage);
    await typeSearch(wrapper, "Ana");
    expect(route.query).toEqual({ q: "Ana" });
    expect(wrapper.find("[data-week-grid]").exists()).toBe(false);
    expect(refsIn(wrapper.find('[data-preorders-results="open"]'))).toEqual(["NB-7"]);
    expect(wrapper.find('[data-preorders-results="completed"]').exists()).toBe(false);
  });

  it("nada em aberto: a tela oferece as concluídas, e um toque liga o filtro", async () => {
    found = { ...found, open_count: 0, open: [] };
    const wrapper = await mount(PreordersPage);
    await typeSearch(wrapper, "Ana");
    const empty = wrapper.find("[data-preorders-open-empty]");
    expect(empty.text()).toContain("Nenhuma encomenda em aberto para “Ana”.");
    await empty.find("[data-preorders-offer-completed]").trigger("click");
    expect(route.query).toEqual({ q: "Ana", completed: "1" });
  });

  it("com as concluídas, elas vêm numa seção SEPARADA, abaixo das em aberto", async () => {
    found = {
      ...found, include_completed: true, completed_count: 1,
      completed: [card({ ref: "NB-1", situation: "delivered", situation_label: "Entregue" })],
    };
    const wrapper = await mount(PreordersPage);
    await typeSearch(wrapper, "Ana");
    await wrapper.find("[data-preorders-include-completed]").trigger("click");
    await flushPromises();
    expect(refsIn(wrapper.find('[data-preorders-results="open"]'))).toEqual(["NB-7"]);
    const completed = wrapper.find('[data-preorders-results="completed"]');
    expect(completed.find("h2").text()).toBe("1 concluída nos últimos 30 dias");
    expect(refsIn(completed)).toEqual(["NB-1"]);
  });

  it("um resultado só: Enter abre o detalhe", async () => {
    const wrapper = await mount(PreordersPage);
    await typeSearch(wrapper, "Ana");
    await wrapper.find("[data-preorders-search]").trigger("keydown", { key: "Enter" });
    expect(navigate).toHaveBeenCalledWith("/preorders/NB-7");
  });
});

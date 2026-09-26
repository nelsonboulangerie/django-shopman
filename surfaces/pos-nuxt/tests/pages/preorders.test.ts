import { mockNuxtImport, mountSuspended, registerEndpoint } from "@nuxt/test-utils/runtime";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";

import DetailPage from "~/pages/preorders/[ref].vue";
import HomePage from "~/pages/preorders/index.vue";
import TodayPage from "~/pages/preorders/today.vue";
import WeekPage from "~/pages/preorders/week.vue";
import type { PreorderCard, PreorderDetailResponse, PreorderListResponse } from "~/types/preorders";

import { makeProjection } from "../composables/_posSaleHarness";

// As telas da seção Encomendas: a grade semanal (sete colunas com a conta do
// dia, lista por dia na tela estreita) e o detalhe read-only — que imprime a
// Via Pedido e NÃO tem botão para o que ainda não existe (E3–E6).

const printOne = vi.fn().mockResolvedValue(true);
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
  printingRef: ref(""),
  hasPrinter: ref(true),
  printerUnavailableReason: ref(""),
}));
let routeQuery: Record<string, string> = {};
mockNuxtImport("useRoute", () => () => ({ params: { ref: "NB-7" }, query: routeQuery, path: "/preorders/NB-7" }));

function card(partial: Partial<PreorderCard> = {}): PreorderCard {
  return {
    ref: "NB-7", channel_display_id: "", customer_name: "Ana Souza", channel_ref: "web",
    channel_label: "Loja online", fulfillment_type: "pickup", fulfillment_label: "Retirada",
    commitment_date: "2026-09-26", commitment_date_display: "hoje", window_label: "9h às 10h",
    window_start: "09:00", status: "accepted", situation: "to_pay", situation_label: "A pagar",
    payment_state: "to_receive",
    total_q: 3600, total_display: "R$ 36,00", balance_q: 3600, balance_display: "R$ 36,00",
    items_summary: "2x Pão", items_count: 2, ...partial,
  };
}

let week: PreorderListResponse;
let detail: PreorderDetailResponse;

registerEndpoint("/api/v1/backstage/pos/preorders/", () => week);
registerEndpoint("/api/v1/backstage/pos/preorders/NB-7/", () => detail);
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
    ok: true, date_from: "2026-09-26", date_to: "2026-10-02", today: "2026-09-26", query: "",
    count: 2, total_q: 6000, total_display: "R$ 60,00", to_receive_q: 3600, to_receive_display: "R$ 36,00",
    days: Array.from({ length: 7 }, (_, i) => ({
      date: `2026-09-${26 + i}`,
      date_display: "", weekday_display: ["sáb", "dom", "seg", "ter", "qua", "qui", "sex"][i]!,
      day_display: `${26 + i}/09`, is_today: i === 0,
      orders_count: i === 0 ? 2 : 0, total_q: i === 0 ? 6000 : 0,
      total_display: i === 0 ? "R$ 60,00" : "R$ 0,00",
      to_receive_q: i === 0 ? 3600 : 0, to_receive_display: i === 0 ? "R$ 36,00" : "R$ 0,00",
      orders: i === 0 ? [card(), card({ ref: "NB-8", customer_name: "Bia", total_q: 2400, total_display: "R$ 24,00", situation: "paid", situation_label: "Pago", payment_state: "paid", balance_q: 0, balance_display: "R$ 0,00" })] : [],
    })),
  };
  detail = {
    ok: true, card: card(), items: [{ name: "Pão", qty_display: "2", line_total_display: "R$ 36,00" }],
    payment_method_label: "Dinheiro na retirada", delivery_address: "", delivery_instructions: "",
    customer_note: "Sem açúcar", customer_phone: "(43) 99988-7766", customer_phone_uri: "tel:+5543999887766",
    customer_relay_phone: "", customer_relay_code: "", ticket_printed: false,
    revision: "rev-1", actor_id: 7,
    hand_over: {
      allowed: true, needs_payment: true, amount_q: 3600, amount_display: "R$ 36,00",
      suggested_method: "cash", block_reason: "",
    },
    cancel: { allowed: true, requires_approval: false, block_reason: "" },
    reschedule: { allowed: true, block_reason: "", date: "2026-09-26", slot: "slot-09", skus: ["PAO"] },
    managers: [{ username: "gerente", name: "Gerente" }],
  };
  printOne.mockClear();
  call.mockReset();
  call.mockResolvedValue({ ok: true, received_q: 3600, status: "completed" });
  kick.mockClear();
  routeQuery = {};
});
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  document.body.innerHTML = "";
});

describe("Semana — a grade", () => {
  it("sete colunas, a conta do dia no topo, e o dia vazio dito por extenso", async () => {
    const wrapper = await mount(WeekPage);
    const grid = wrapper.find("[data-week-grid]");
    const columns = grid.findAll("[data-week-day]");
    expect(columns).toHaveLength(7);
    expect(columns[0]!.find("[data-week-day-total]").text()).toBe("2 encomendas · R$ 60,00");
    expect(columns[1]!.find("[data-week-day-total]").text()).toBe("Nenhuma encomenda");
    expect(columns[0]!.findAll("[data-preorder]").map((c) => c.attributes("data-preorder"))).toEqual(["NB-7", "NB-8"]);
    // Tela estreita: o mesmo conteúdo, em lista por dia.
    expect(wrapper.find("[data-week-list]").findAll("[data-preorder]")).toHaveLength(2);
  });

  it("a encomenda leva ao detalhe", async () => {
    const wrapper = await mount(WeekPage);
    expect(wrapper.find('[data-preorder="NB-7"]').attributes("href")).toBe("/preorders/NB-7");
  });

  it("anda de semana em semana e oferece a volta para hoje", async () => {
    const wrapper = await mount(WeekPage);
    expect(wrapper.find("[data-week-today]").exists()).toBe(false);
    await wrapper.find("[data-week-next]").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-week-today]").exists()).toBe(true);
  });
});

describe("Detalhe — só lê e imprime a Via Pedido", () => {
  it("mostra quem, quanto falta, os itens e a observação do cliente", async () => {
    const wrapper = await mount(DetailPage);
    const text = wrapper.text();
    expect(text).toContain("Ana Souza");
    expect(wrapper.find("[data-preorder-situation]").text()).toBe("A pagar");
    expect(wrapper.find("[data-preorder-money]").text()).toBe("R$ 36,00 a receber");
    expect(text).toContain("2x Pão");
    expect(text).toContain("Sem açúcar");
    expect(text).toContain("(43) 99988-7766");
  });

  it("imprime a Via Pedido pela impressão individual que já existe", async () => {
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-preorder-print]").trigger("click");
    await flushPromises();
    expect(printOne).toHaveBeenCalledWith("NB-7");
  });

  it("⚠️ nenhum botão morto: editar ainda não existe no PDV", async () => {
    const wrapper = await mount(DetailPage);
    const buttons = wrapper.findAll("button").map((b) => b.text());
    for (const word of ["Editar"]) {
      expect(buttons.some((label) => label.includes(word))).toBe(false);
    }
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
    detail.hand_over = { ...detail.hand_over, needs_payment: false, amount_q: 0, amount_display: "R$ 0,00" };
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-preorder-hand-over]").text()).toBe("Entregar");
    await wrapper.find("[data-preorder-hand-over]").trigger("click");
    await settle();
    body().querySelector<HTMLButtonElement>("[data-preorder-hand-over-confirm]")!.click();
    await settle();
    expect(call.mock.calls[0]![1].body.tenders).toBeUndefined();
    expect(kick).not.toHaveBeenCalled();
  });

  it("quando não pode entregar, diz por quê em vez de mostrar botão apagado", async () => {
    detail.hand_over = { ...detail.hand_over, allowed: false, block_reason: "Esta encomenda ainda não está pronta (Em preparo)." };
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-preorder-hand-over]").exists()).toBe(false);
    expect(wrapper.find("[data-preorder-hand-over-blocked]").text()).toContain("ainda não está pronta");
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
    detail.cancel = { allowed: false, requires_approval: false, block_reason: "Pedido do iFood: cancele pelo Gestor de pedidos." };
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-preorder-cancel]").exists()).toBe(false);
  });
});

describe("A casa — a porta da barra lateral", () => {
  it("'Cliente veio buscar' vem primeiro, com o foco no campo", async () => {
    const wrapper = await mount(HomePage);
    const field = wrapper.find("[data-preorders-search]");
    expect(wrapper.find("[data-preorders-search-block]").text()).toContain("Cliente veio buscar");
    expect(field.exists()).toBe(true);
  });

  it("o que falta receber hoje e na semana, cada total levando à lista já filtrada", async () => {
    const wrapper = await mount(HomePage);
    const today = wrapper.find("[data-preorders-to-receive-today]");
    const week = wrapper.find("[data-preorders-to-receive-week]");
    expect(today.text()).toContain("A receber: R$ 36,00");
    expect(today.attributes("href")).toBe("/preorders/today?pay=to_receive");
    expect(week.text()).toContain("A receber: R$ 36,00");
    expect(week.attributes("href")).toBe("/preorders/week?pay=to_receive");
  });

  it("os cards Hoje (com as de hoje por entregar), Semana e Via Pedido – painel", async () => {
    const wrapper = await mount(HomePage);
    const tiles = wrapper.find("[data-preorders-tiles]").findAll("[data-session-tile]");
    expect(tiles.map((t) => t.attributes("data-session-tile"))).toEqual(["preorders:today", "preorders:week", "preorders:panel"]);
    expect(tiles[0]!.find("[data-session-tile-badge]").text()).toBe("2");
  });

  it("sem nada a receber, a frase inteira — zero não é código", async () => {
    week.to_receive_q = 0;
    week.days[0]!.to_receive_q = 0;
    const wrapper = await mount(HomePage);
    expect(wrapper.find("[data-preorders-to-receive-today]").text()).toContain("Nada a receber");
  });

  it("pagamento a conferir ganha aviso próprio na casa", async () => {
    week.days[0]!.orders.push(card({ ref: "NB-9", payment_state: "check", balance_q: null, situation: "check_payment" }));
    const wrapper = await mount(HomePage);
    expect(wrapper.find("[data-preorders-check-notice]").text()).toContain("1 encomenda está com o pagamento a conferir");
  });

  it("digitar troca os cards pelo resultado da busca", async () => {
    const wrapper = await mount(HomePage);
    await wrapper.find("[data-preorders-search]").setValue("Ana");
    await new Promise((resolve) => setTimeout(resolve, 300));
    await flushPromises();
    await flushPromises();
    expect(wrapper.find("[data-preorders-tiles]").exists()).toBe(false);
    expect(wrapper.find("[data-preorders-results]").findAll("[data-preorder]")).toHaveLength(2);
  });
});

describe("Hoje — o que falta receber × o que já está pago", () => {
  it("filtros de um toque com a contagem, e o total a receber do dia", async () => {
    const wrapper = await mount(TodayPage);
    expect(wrapper.find("[data-preorders-to-receive]").text()).toBe("A receber: R$ 36,00");
    const chips = wrapper.findAll("[data-preorders-filter-chip]");
    expect(chips.map((c) => c.attributes("aria-label"))).toEqual(["Todas: 2", "A receber: 1", "Pagas: 1"]);

    await wrapper.find('[data-preorders-filter-chip="to_receive"]').trigger("click");
    expect(wrapper.findAll("[data-preorder]").map((c) => c.attributes("data-preorder"))).toEqual(["NB-7"]);
    await wrapper.find('[data-preorders-filter-chip="paid"]').trigger("click");
    expect(wrapper.findAll("[data-preorder]").map((c) => c.attributes("data-preorder"))).toEqual(["NB-8"]);
  });

  it("o saldo a cobrar ganha destaque na linha; o pago fica discreto", async () => {
    const wrapper = await mount(TodayPage);
    expect(wrapper.find('[data-preorder="NB-7"] [data-preorder-money]').attributes("data-preorder-money")).toBe("to-receive");
    expect(wrapper.find('[data-preorder="NB-8"] [data-preorder-money]').attributes("data-preorder-money")).toBe("settled");
  });

  it("o filtro chega pela URL (vindo da casa)", async () => {
    routeQuery = { pay: "to_receive" };
    const wrapper = await mount(TodayPage);
    expect(wrapper.findAll("[data-preorder]").map((c) => c.attributes("data-preorder"))).toEqual(["NB-7"]);
  });

  it("filtro sem resultado diz o que não há", async () => {
    week.days[0]!.orders = week.days[0]!.orders.filter((c) => c.payment_state === "paid");
    routeQuery = { pay: "to_receive" };
    const wrapper = await mount(TodayPage);
    expect(wrapper.find("[data-preorders-filter-empty]").text()).toBe("Nenhuma encomenda a receber neste período.");
  });

  it("conta da casa: chip próprio, fora de A receber e de Pagas", async () => {
    week.days[0]!.orders.push(card({ ref: "NB-10", payment_state: "on_account", balance_q: 0, situation: "on_account" }));
    const wrapper = await mount(TodayPage);
    const chips = wrapper.findAll("[data-preorders-filter-chip]").map((c) => c.attributes("aria-label"));
    expect(chips).toEqual(["Todas: 3", "A receber: 1", "Pagas: 1", "Na conta da casa: 1"]);
  });
});

describe("Semana — o a receber de cada dia", () => {
  it("a coluna diz o a receber ao lado do total; o dia sem saldo não diz nada", async () => {
    const wrapper = await mount(WeekPage);
    const columns = wrapper.find("[data-week-grid]").findAll("[data-week-day]");
    expect(columns[0]!.find("[data-week-day-to-receive]").text()).toBe("A receber R$ 36,00");
    expect(columns[1]!.find("[data-week-day-to-receive]").exists()).toBe(false);
    expect(wrapper.find("[data-preorders-to-receive]").text()).toBe("A receber: R$ 36,00");
  });

  it("o filtro esconde encomendas e mantém a conta do dia", async () => {
    const wrapper = await mount(WeekPage);
    await wrapper.find('[data-preorders-filter-chip="paid"]').trigger("click");
    const column = wrapper.find("[data-week-grid]").findAll("[data-week-day]")[0]!;
    expect(column.findAll("[data-preorder]").map((c) => c.attributes("data-preorder"))).toEqual(["NB-8"]);
    expect(column.find("[data-week-day-total]").text()).toBe("2 encomendas · R$ 60,00");
  });
});

describe("Detalhe — reagendar", () => {
  it("escolher outro dia chama a rota do Gestor com a data, a revisão e quem está identificado", async () => {
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-preorder-reschedule]").trigger("click");
    await settle();
    await settle();
    body().querySelector<HTMLButtonElement>('[data-reschedule-date="2026-09-28"]')!.click();
    await settle();
    body().querySelector<HTMLButtonElement>("[data-preorder-reschedule-confirm]")!.click();
    await settle();

    const [path, options] = call.mock.calls[0]!;
    expect(path).toBe("/api/v1/backstage/orders/NB-7/reschedule/");
    expect(options.body).toMatchObject({ date: "2026-09-28", slot: "", base_revision: "rev-1", expected_actor_id: 7 });
    expect(options.body.idempotency_key).toBeTruthy();
  });

  it("sem mudar nada, não dá para confirmar", async () => {
    const wrapper = await mount(DetailPage);
    await wrapper.find("[data-preorder-reschedule]").trigger("click");
    await settle();
    expect(body().querySelector<HTMLButtonElement>("[data-preorder-reschedule-confirm]")!.disabled).toBe(true);
  });

  it("quando o servidor diz que não reagenda, não há botão", async () => {
    detail.reschedule = { ...detail.reschedule, allowed: false, block_reason: "Este pedido já está pronto: a data não muda mais." };
    const wrapper = await mount(DetailPage);
    expect(wrapper.find("[data-preorder-reschedule]").exists()).toBe(false);
  });
});

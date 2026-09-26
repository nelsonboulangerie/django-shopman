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

mockNuxtImport("usePosTerminal", () => async () => ({
  pos: computed(() => makeProjection({ has_open_cash_session: true })),
  pending: ref(false),
  refresh: vi.fn().mockResolvedValue(undefined),
}));
mockNuxtImport("useOperatorLock", () => () => ({ operator: ref({ name: "Ana" }), lock: vi.fn() }));
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
  };
  printOne.mockClear();
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

  it("⚠️ nenhum botão morto: receber, reagendar, editar e cancelar chegam nos próximos WPs", async () => {
    const wrapper = await mount(DetailPage);
    const buttons = wrapper.findAll("button").map((b) => b.text());
    for (const word of ["Receber", "Reagendar", "Editar", "Cancelar"]) {
      expect(buttons.some((label) => label.includes(word))).toBe(false);
    }
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

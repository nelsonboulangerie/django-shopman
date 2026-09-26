import { mockNuxtImport, mountSuspended, registerEndpoint } from "@nuxt/test-utils/runtime";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";

import DetailPage from "~/pages/preorders/[ref].vue";
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
mockNuxtImport("useRoute", () => () => ({ params: { ref: "NB-7" }, query: {}, path: "/preorders/NB-7" }));

function card(partial: Partial<PreorderCard> = {}): PreorderCard {
  return {
    ref: "NB-7", channel_display_id: "", customer_name: "Ana Souza", channel_ref: "web",
    channel_label: "Loja online", fulfillment_type: "pickup", fulfillment_label: "Retirada",
    commitment_date: "2026-09-26", commitment_date_display: "hoje", window_label: "9h às 10h",
    window_start: "09:00", status: "accepted", situation: "to_pay", situation_label: "A pagar",
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
    count: 2, total_q: 6000, total_display: "R$ 60,00",
    days: Array.from({ length: 7 }, (_, i) => ({
      date: `2026-09-${26 + i}`,
      date_display: "", weekday_display: ["sáb", "dom", "seg", "ter", "qua", "qui", "sex"][i]!,
      day_display: `${26 + i}/09`, is_today: i === 0,
      orders_count: i === 0 ? 2 : 0, total_q: i === 0 ? 6000 : 0,
      total_display: i === 0 ? "R$ 60,00" : "R$ 0,00",
      orders: i === 0 ? [card(), card({ ref: "NB-8", customer_name: "Bia", total_q: 2400, total_display: "R$ 24,00", situation: "paid", situation_label: "Pago", balance_q: 0, balance_display: "R$ 0,00" })] : [],
    })),
  };
  detail = {
    ok: true, card: card(), items: [{ name: "Pão", qty_display: "2", line_total_display: "R$ 36,00" }],
    payment_method_label: "Dinheiro na retirada", delivery_address: "", delivery_instructions: "",
    customer_note: "Sem açúcar", customer_phone: "(43) 99988-7766", customer_phone_uri: "tel:+5543999887766",
    customer_relay_phone: "", customer_relay_code: "", ticket_printed: false,
  };
  printOne.mockClear();
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

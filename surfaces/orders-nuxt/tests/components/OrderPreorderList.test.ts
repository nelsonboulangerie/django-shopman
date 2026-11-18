// WP-G03: a lista de Encomendas do Gestor, montada. Cada linha diz quando, como, o
// pagamento e a produção; o atalho abre AQUELA encomenda no PDV; quem veio do aviso do
// aceite acha a linha de relance.
import { describe, expect, it, vi } from "vitest";
import { computed } from "vue";
import { mount } from "@vue/test-utils";

import OrderPreorderList from "../../app/components/OrderPreorderList.vue";
import type { PreorderGroup } from "../../app/presentation/board";
import type { OrderCardProjection } from "../../app/types/orders";

vi.stubGlobal("computed", computed);
const posUrl = { value: "https://pdv.exemplo" };
vi.stubGlobal("useRuntimeConfig", () => ({ public: { posUrl: posUrl.value } }));

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "NB-261116-C73",
    customer_name: "Clara Teste",
    items_summary: "1x Pain de Campagne",
    total_display: "R$ 18,70",
    schedule_label: "Amanhã · A partir das 15h",
    fulfillment_label: "Retirada",
    payment_method_label: "Pix",
    payment_status_label: "Pago",
    payment_pending: false,
    attention: "",
    awaiting_work_orders: [],
    ...over,
  } as OrderCardProjection;
}

const groups = (...cards: OrderCardProjection[]): PreorderGroup[] => [
  { date: "2026-11-19", label: "amanhã", cards },
];

const stubs = {
  NuxtLink: { props: ["to"], template: '<a :href="to"><slot /></a>' },
  OperatorCountChip: { props: ["count"], template: "<span data-count>{{ count }}</span>" },
};
const mountList = (props: Record<string, unknown>) =>
  mount(OrderPreorderList, { props, global: { stubs } });

describe("OrderPreorderList: a linha responde", () => {
  it("diz o dia, a janela, como recebe e o pagamento", () => {
    const w = mountList({ groups: groups(card()), count: 1 });
    const row = w.get('[data-preorder-row="NB-261116-C73"]');

    expect(row.get("[data-preorder-when]").text()).toBe("Amanhã · A partir das 15h");
    expect(row.get("[data-preorder-how]").text()).toBe("Retirada");
    expect(row.get("[data-preorder-payment]").text()).toBe("Pix · Pago");
    expect(row.text()).toContain("C73");
    expect(row.text()).toContain("1x Pain de Campagne");
  });

  it("quem espera o pagamento lê isso com nome, e não \"Precisa de você\"", () => {
    const w = mountList({
      groups: groups(card({ attention: "blocked", payment_pending: true, payment_status_label: "Pendente" })),
      count: 1,
    });

    expect(w.get("[data-preorder-payment]").text()).toBe("Aguardando pagamento · Pix");
    expect(w.find("[data-preorder-needs-you]").exists()).toBe(false);
    expect(w.text()).not.toContain("Precisa de você");
  });

  it("a linha abre o pedido no Gestor", () => {
    const w = mountList({ groups: groups(card()), count: 1 });

    expect(w.get('[data-preorder-row="NB-261116-C73"] a').attributes("href")).toBe("/NB-261116-C73");
  });
});

describe("OrderPreorderList: \"Remarcar no PDV\"", () => {
  it("abre aquela encomenda no PDV, não a lista geral", () => {
    const w = mountList({ groups: groups(card()), count: 1 });
    const button = w.get('[data-preorder-reschedule=""]');

    expect(button.text()).toContain("Remarcar no PDV");
    expect(button.html()).toContain("https://pdv.exemplo/preorders/NB-261116-C73");
    // A lista geral continua no cabeçalho.
    expect(w.get("[data-preorders-open]").html()).toContain("https://pdv.exemplo/preorders");
  });

  it("no celular o botão vai para a direita, sem a seta, com o mesmo nome", () => {
    const w = mountList({ groups: groups(card()), count: 1 });
    const narrow = w.get('[data-preorder-reschedule="narrow"]');

    expect(narrow.text()).toContain("Remarcar no PDV");
    expect(narrow.classes()).toEqual(expect.arrayContaining(["ms-auto", "sm:hidden"]));
    expect(narrow.html()).toContain("https://pdv.exemplo/preorders/NB-261116-C73");
  });

  it("o grupo começa com maiúscula", () => {
    const w = mountList({ groups: groups(card()), count: 1 });

    expect(w.get("h3").text()).toBe("Amanhã");
  });

  it("sem o endereço do PDV, nenhum atalho aparece", () => {
    posUrl.value = "";
    const w = mountList({ groups: groups(card()), count: 1 });
    posUrl.value = "https://pdv.exemplo";

    expect(w.find("[data-preorder-reschedule]").exists()).toBe(false);
    expect(w.find("[data-preorders-open]").exists()).toBe(false);
  });
});

describe("OrderPreorderList: a encomenda recém-aceita", () => {
  it("a linha dela é o alvo do próximo foco e fica marcada", () => {
    const other = card({ ref: "NB-261116-D10", customer_name: "Davi" });
    const w = mountList({
      groups: groups(card(), other),
      count: 2,
      highlightRef: "NB-261116-C73",
    });
    const row = w.get('[data-preorder-row="NB-261116-C73"]');

    expect(row.attributes("data-focus-target")).toBe("preorder:NB-261116-C73");
    expect(row.attributes("aria-current")).toBe("true");
    expect(w.get('[data-preorder-row="NB-261116-D10"]').attributes("aria-current")).toBeUndefined();
  });
});

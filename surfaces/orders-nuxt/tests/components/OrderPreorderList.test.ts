// WP-G03: a lista de Encomendas do Gestor, montada. Cada linha diz quando, como, o
// pagamento e a produção; o atalho abre AQUELA encomenda no PDV; quem veio do aviso do
// aceite acha a linha de relance.
import { describe, expect, it, vi } from "vitest";
import { computed } from "vue";
import { mount } from "@vue/test-utils";

import OrderPreorderList from "../../app/components/OrderPreorderList.vue";
import type { PreorderGroup } from "../../app/presentation/board";
import { coverageByDate } from "../../app/presentation/preorderCoverage";
import type { OrderCardProjection } from "../../app/types/orders";
import { coveredDay, day } from "../support/preorderCoverage";

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
  Icon: { props: ["name"], template: '<i :data-icon="name" />' },
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

// WP-G10: a agenda com cobertura. O cabeçalho de cada dia diz se a Produção cobre as
// encomendas dele; a cobertura é outra leitura, e a lista não depende dela.
describe("OrderPreorderList: a cobertura de cada dia", () => {
  const twoDays = (): PreorderGroup[] => [
    { date: "2026-11-19", label: "amanhã", cards: [card()] },
    { date: "2026-11-21", label: "sáb, 21/11", cards: [card({ ref: "NB-261116-D10" })] },
  ];
  const coverage = () => coverageByDate({ days: [coveredDay(), day()] });

  it("cada dia recebe a cobertura da data dele", () => {
    const w = mountList({ groups: twoDays(), count: 2, coverage: coverage() });
    const tomorrow = w.get('[data-preorder-day="2026-11-19"]');
    const saturday = w.get('[data-preorder-day="2026-11-21"]');

    expect(tomorrow.get("h3").text()).toBe("Amanhã");
    expect(tomorrow.get("[data-coverage-headline]").text()).toBe("A produção cobre as encomendas.");
    expect(saturday.get("h3").text()).toBe("Sáb, 21/11");
    expect(saturday.get("[data-coverage-headline]").text()).toBe(
      "Faltam 6 Baguete de tradição. Sem lote para Ciabatta.",
    );
    expect(saturday.get('[data-coverage-production="header"]').attributes("href")).toBe(
      "https://producao.exemplo/plan?date=2026-11-21",
    );
  });

  it("dia sem cobertura lida fica só com o nome, e as linhas seguem iguais", () => {
    const w = mountList({ groups: twoDays(), count: 2, coverage: coverageByDate({ days: [day()] }) });

    expect(w.findAll("h3").map((h) => h.text())).toEqual(["Amanhã", "Sáb, 21/11"]);
    expect(w.findAll("[data-coverage-headline]")).toHaveLength(1);
    expect(w.findAll("[data-preorder-row]")).toHaveLength(2);
  });

  it("sem a leitura (ou antes dela) a lista é a de sempre, sem aviso", () => {
    const w = mountList({ groups: twoDays(), count: 2 });

    expect(w.find("[data-coverage-headline]").exists()).toBe(false);
    expect(w.find("[data-coverage-failed]").exists()).toBe(false);
    expect(w.findAll("[data-preorder-row]")).toHaveLength(2);
  });

  it("a leitura falhou: a lista segue inteira e a seção oferece tentar de novo", async () => {
    const w = mountList({ groups: twoDays(), count: 2, coverage: {}, coverageFailed: true });
    const failed = w.get("[data-coverage-failed]");

    expect(failed.text()).toContain("Não foi possível ler se a produção cobre as encomendas.");
    expect(w.findAll("[data-preorder-row]")).toHaveLength(2);
    expect(w.find("[data-coverage-headline]").exists()).toBe(false);

    const retry = failed.get("[data-coverage-retry]");
    expect(retry.text()).toBe("Tentar de novo");
    await retry.trigger("click");
    expect(w.emitted("retry-coverage")).toHaveLength(1);
  });

  it("enquanto relê, o \"Tentar de novo\" fica pendente", () => {
    const w = mountList({
      groups: twoDays(),
      count: 2,
      coverage: {},
      coverageFailed: true,
      coverageReading: true,
    });

    expect(w.get("[data-coverage-retry]").attributes("disabled")).toBeDefined();
  });
});

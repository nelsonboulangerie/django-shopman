import { mountSuspended } from "@nuxt/test-utils/runtime";
import { describe, expect, it } from "vitest";

import OperatorMetric from "../../app/components/OperatorMetric.vue";
import type { MetricDelta } from "../../app/presentation/metric";

// A receita do Kitchen Sink virada peça (PR-K2): NuxtCard com title/description,
// a figura, e o delta pronto da presentation num NuxtBadge.
const drop: MetricDelta = {
  text: "queda de 23% vs período anterior (3.384)",
  tone: "negative",
  percent: "23%",
  direction: "down",
  caption: "vs período anterior (3.384)",
};

describe("OperatorMetric", () => {
  it("título e recorte são a anatomia do NuxtCard, não rótulo escrito à mão", async () => {
    const wrapper = await mountSuspended(OperatorMetric, {
      props: { title: "Faturamento", description: "Vendas confirmadas", value: "R$ 8.420,00" },
    });
    expect(wrapper.get('[data-slot="title"]').text()).toBe("Faturamento");
    expect(wrapper.get('[data-slot="description"]').text()).toBe("Vendas confirmadas");
    expect(wrapper.get("[data-metric-value]").text()).toBe("R$ 8.420,00");
    expect(wrapper.get("[data-metric-value]").classes()).toContain("op-figure");
    expect(wrapper.find("[data-metric-delta]").exists()).toBe(false);
  });

  it("o delta pronto vira pílula no tom do piorou, com o contra o quê ao lado e a frase para o leitor de tela", async () => {
    const wrapper = await mountSuspended(OperatorMetric, {
      props: { title: "Pedidos", value: "2.606", unit: "pedidos", delta: drop },
    });
    const line = wrapper.get("[data-metric-delta]");
    expect(line.get(".sr-only").text()).toBe(drop.text);
    expect(line.text()).toContain("23%");
    expect(line.text()).toContain("vs período anterior (3.384)");
    // O tom é a cor do selo; a variante (soft) é do tema, não da peça.
    expect(line.html()).toMatch(/\b(?:bg|text)-error\b/);
    expect(wrapper.get("[data-metric-value]").text()).toBe("2.606 pedidos");
  });

  it("sem base de comparação, a pílula some e a frase fica", async () => {
    const caption = "sem período anterior para comparar";
    const wrapper = await mountSuspended(OperatorMetric, {
      props: {
        title: "Pedidos",
        value: "12",
        delta: { text: caption, tone: "neutral", percent: "", direction: "none", caption },
      },
    });
    const line = wrapper.get("[data-metric-delta]");
    expect(line.findAll('[aria-hidden="true"]').map((node) => node.text())).toEqual([caption]);
  });

  it("veredito pinta a figura; statement diz a resposta em uma frase", async () => {
    const verdict = await mountSuspended(OperatorMetric, {
      props: { title: "Faltou", value: "3 produtos", tone: "error" },
    });
    expect(verdict.get("[data-metric-value] span").classes()).toContain("text-error");

    const answer = await mountSuspended(OperatorMetric, {
      props: {
        title: "A resposta",
        value: "Faltou pão de queijo em 3 dos 7 dias.",
        size: "statement",
      },
    });
    expect(answer.get("[data-metric-value]").classes()).toContain("op-title");
    expect(answer.get("[data-metric-value]").classes()).not.toContain("op-figure");
  });

  it("ícone mora no título do Card, sem roubar o nome", async () => {
    const wrapper = await mountSuspended(OperatorMetric, {
      props: { title: "Ticket médio", value: "R$ 32,10", icon: "i-lucide-receipt" },
    });
    expect(wrapper.get('[data-slot="title"]').text()).toBe("Ticket médio");
  });
});

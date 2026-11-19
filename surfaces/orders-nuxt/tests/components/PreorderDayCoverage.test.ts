// WP-G10: o cabeçalho de um dia da lista de Encomendas, montado. Ao lado do nome do dia,
// a frase do servidor; a um toque, o prometido ao lado do planejado por produto; e
// "Abrir a Produção" naquele dia.
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import PreorderDayCoverage from "../../app/components/PreorderDayCoverage.vue";
import { dayCoverage } from "../../app/presentation/preorderCoverage";
import type { PreorderCoverageDayProjection } from "../../app/types/orders";
import { coveredDay, day, fromStock, madeToOrder } from "../support/preorderCoverage";

const stubs = { Icon: { props: ["name"], template: '<i :data-icon="name" />' } };
const mountDay = (
  source: PreorderCoverageDayProjection | null,
  label = "Sáb, 21/11",
) =>
  mount(PreorderDayCoverage, {
    props: { label, coverage: source ? dayCoverage(source) : null },
    global: { stubs },
  });

describe("PreorderDayCoverage: o cabeçalho do dia", () => {
  it("sem a leitura da cobertura sobra só o nome do dia", () => {
    const w = mountDay(null, "Amanhã");

    expect(w.get("h3").text()).toBe("Amanhã");
    expect(w.find("[data-coverage-headline]").exists()).toBe(false);
    expect(w.find("[data-coverage-toggle]").exists()).toBe(false);
    expect(w.find("[data-coverage-production]").exists()).toBe(false);
  });

  it("o dia que falta diz a frase do servidor, com cor e ícone de aviso", () => {
    const w = mountDay(day());
    const headline = w.get("[data-coverage-headline]");

    expect(w.get("h3").text()).toBe("Sáb, 21/11");
    expect(headline.text()).toBe("Faltam 6 Baguete de tradição. Sem lote para Ciabatta.");
    expect(headline.attributes("data-coverage-tone")).toBe("attention");
    expect(headline.classes()).toContain("text-warning");
    expect(headline.find('[data-icon="lucide:triangle-alert"]').exists()).toBe(true);
  });

  it("falta para amanhã é de agora: vermelho", () => {
    const headline = mountDay(day({ days_ahead: 1 })).get("[data-coverage-headline]");

    expect(headline.attributes("data-coverage-tone")).toBe("urgent");
    expect(headline.classes()).toContain("text-error");
  });

  it("o dia coberto é discreto: sem cor, sem ícone, sem atalho à vista", () => {
    const w = mountDay(coveredDay(), "Amanhã");
    const headline = w.get("[data-coverage-headline]");

    expect(headline.text()).toBe("A produção cobre as encomendas.");
    expect(headline.attributes("data-coverage-tone")).toBe("quiet");
    expect(headline.classes()).toContain("text-muted");
    expect(headline.classes()).not.toContain("text-warning");
    expect(headline.classes()).not.toContain("text-error");
    expect(headline.find("[data-icon]").exists()).toBe(false);
    expect(w.find('[data-coverage-production="header"]').exists()).toBe(false);
  });

  it("o dia que não depende de lote não mostra nada de falta", () => {
    const w = mountDay(
      day({
        state: "not_batch_based",
        headline: "Nenhum item depende de lote.",
        products: [madeToOrder(), fromStock()],
      }),
    );

    expect(w.get("[data-coverage-headline]").text()).toBe("Nenhum item depende de lote.");
    expect(w.get("[data-coverage-headline]").attributes("data-coverage-tone")).toBe("quiet");
    expect(w.html()).not.toContain("text-warning");
    expect(w.html()).not.toContain("text-error");
  });
});

describe("PreorderDayCoverage: o detalhe do dia, a um toque", () => {
  it("nasce recolhido; o gesto diz o que abre e para qual dia", () => {
    const w = mountDay(day());
    const toggle = w.get("[data-coverage-toggle]");

    expect(w.find("[data-coverage-detail]").exists()).toBe(false);
    expect(toggle.text()).toBe("Ver por produto");
    expect(toggle.attributes("aria-expanded")).toBe("false");
    expect(toggle.attributes("aria-label")).toBe("Ver por produto: Sáb, 21/11");
  });

  it("um toque abre; outro recolhe", async () => {
    const w = mountDay(day());
    await w.get("[data-coverage-toggle]").trigger("click");
    const toggle = w.get("[data-coverage-toggle]");

    expect(toggle.text()).toBe("Recolher");
    expect(toggle.attributes("aria-expanded")).toBe("true");
    expect(toggle.attributes("aria-controls")).toBe("preorder-coverage-2026-11-21");
    expect(w.get("[data-coverage-detail]").attributes("id")).toBe("preorder-coverage-2026-11-21");

    await toggle.trigger("click");
    expect(w.find("[data-coverage-detail]").exists()).toBe(false);
  });

  it("por produto, o prometido ao lado do planejado, na ordem do servidor", async () => {
    const w = mountDay(day());
    await w.get("[data-coverage-toggle]").trigger("click");
    const rows = w.findAll("[data-coverage-product]");

    expect(rows.map((row) => row.attributes("data-coverage-product"))).toEqual([
      "BAGUETE",
      "CIABATTA",
      "CAMPAGNE",
      "CAFE",
      "GELEIA",
    ]);
    const baguete = rows[0]!;
    expect(baguete.text()).toContain("Baguete de tradição");
    expect(baguete.get("[data-coverage-promised]").text()).toBe("Prometido16x");
    expect(baguete.get("[data-coverage-planned]").text()).toBe("Planejado10x");
    expect(baguete.get("[data-coverage-label]").text()).toBe("Faltam 6 Baguete de tradição");
    expect(baguete.get("[data-coverage-label]").classes()).toContain("text-warning");
    // A conta por extenso repetiria os dois números ao lado.
    expect(baguete.find("[data-coverage-why]").exists()).toBe(false);
  });

  it("sem lote: o zero planejado, a frase e o porquê", async () => {
    const w = mountDay(day());
    await w.get("[data-coverage-toggle]").trigger("click");
    const ciabatta = w.get('[data-coverage-product="CIABATTA"]');

    expect(ciabatta.get("[data-coverage-planned]").text()).toBe("Planejado0x");
    expect(ciabatta.get("[data-coverage-label]").text()).toBe("Sem lote para Ciabatta");
    expect(ciabatta.get("[data-coverage-why]").text()).toBe("Nenhum lote planejado para o dia.");
  });

  it("feito na hora e revenda aparecem sem cor de falta e sem planejado", async () => {
    const w = mountDay(day());
    await w.get("[data-coverage-toggle]").trigger("click");

    for (const [sku, why] of [
      ["CAFE", "Feito na hora: não depende de lote."],
      ["GELEIA", "Sai do estoque: a casa não produz este item."],
    ] as const) {
      const row = w.get(`[data-coverage-product="${sku}"]`);
      expect(row.find("[data-coverage-planned]").exists()).toBe(false);
      expect(row.find("[data-coverage-label]").exists()).toBe(false);
      expect(row.get("[data-coverage-why]").text()).toBe(why);
      expect(row.html()).not.toContain("text-warning");
      expect(row.html()).not.toContain("text-error");
    }
  });

  it("o produto coberto fica só com os números", async () => {
    const w = mountDay(day());
    await w.get("[data-coverage-toggle]").trigger("click");
    const campagne = w.get('[data-coverage-product="CAMPAGNE"]');

    expect(campagne.get("[data-coverage-promised]").text()).toBe("Prometido4x");
    expect(campagne.get("[data-coverage-planned]").text()).toBe("Planejado12x");
    expect(campagne.find("[data-coverage-label]").exists()).toBe(false);
    expect(campagne.find("[data-coverage-why]").exists()).toBe(false);
  });

  it("dia sem produto na conta não oferece o detalhe", () => {
    const w = mountDay(day({ state: "not_batch_based", headline: "Nenhum item depende de lote.", products: [] }));

    expect(w.find("[data-coverage-toggle]").exists()).toBe(false);
  });
});

describe("PreorderDayCoverage: \"Abrir a Produção\" naquele dia", () => {
  it("no dia que pede alguém, o atalho está no cabeçalho, com o nome do servidor", () => {
    const w = mountDay(day());
    const link = w.get('[data-coverage-production="header"]');

    expect(link.text()).toBe("Abrir a Produção");
    expect(link.attributes("href")).toBe("https://producao.exemplo/plan?date=2026-11-21");
    expect(link.attributes("aria-label")).toBe("Abrir a Produção: Sáb, 21/11");
    // Fora do app instalado, segue na mesma aba (`useOperatorAppLink`).
    expect(link.attributes("target")).toBe("_self");
  });

  it("aberto o detalhe, o atalho não se repete", async () => {
    const w = mountDay(day());
    await w.get("[data-coverage-toggle]").trigger("click");

    expect(w.findAll("[data-coverage-production]")).toHaveLength(1);
  });

  it("no dia coberto, o atalho mora dentro do detalhe", async () => {
    const w = mountDay(coveredDay(), "Amanhã");
    expect(w.find("[data-coverage-production]").exists()).toBe(false);
    await w.get("[data-coverage-toggle]").trigger("click");
    const link = w.get('[data-coverage-production="detail"]');

    expect(link.text()).toBe("Abrir a Produção");
    expect(link.attributes("href")).toBe("https://producao.exemplo/plan?date=2026-11-19");
  });

  it("sem endereço da Produção, nenhum atalho", async () => {
    const w = mountDay(day({ production_url: "", production_label: "" }));
    await w.get("[data-coverage-toggle]").trigger("click");

    expect(w.find("[data-coverage-production]").exists()).toBe(false);
    expect(w.text()).not.toContain("Abrir a Produção");
  });
});

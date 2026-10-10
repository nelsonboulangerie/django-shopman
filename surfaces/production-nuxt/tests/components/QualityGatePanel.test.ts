import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { mount } from "@vue/test-utils";

import QualityGatePanel from "../../app/components/QualityGatePanel.vue";
import type {
  QCGradeProjection,
  QCOrderCardProjection,
} from "../../app/types/production";
import { nuxtUiStubs } from "../support/nuxtUiStubs";

const GRADES: QCGradeProjection[] = [
  { ref: "standard", label: "Padrão", rank: 30, markdown_percent: 0, is_default: true },
];

function card(
  pk: number,
  overrides: Partial<QCOrderCardProjection> = {},
): QCOrderCardProjection {
  return {
    pk,
    ref: `WO-${pk}`,
    rev: 1,
    recipe_name: `Receita ${pk}`,
    output_sku: `SKU-${pk}`,
    position_ref: "",
    status: "finished",
    planned_qty: "10",
    started_qty: "10",
    started_at_display: "",
    elapsed_minutes: 0,
    can_close: false,
    closed: true,
    can_correct: true,
    quality_reviewed: false,
    partition: [{ quantity: "10", quality_grade_ref: "standard", quality_defect_ref: "", loss: false }],
    correction_count: 0,
    last_correction_at_display: "",
    committed_qty: "",
    full_price_qty: "10",
    discounted_qty: "0",
    loss_qty: "0",
    quality_exception: false,
    closed_by: "Rafael",
    closed_at_display: "07:00",
    typical_loss_qty: "",
    alert_waiting_count: 2,
    ...overrides,
  };
}

function mountPanel(orders: QCOrderCardProjection[], props: Record<string, unknown> = {}) {
  return mount(QualityGatePanel, {
    props: {
      orders,
      grades: GRADES,
      defects: [],
      isToday: true,
      batchAvailable: true,
      submitting: false,
      reviewAvailable: () => true,
      correctionAvailable: () => true,
      ...props,
    },
    global: { stubs: { Icon: true, ...nuxtUiStubs } },
  });
}

beforeEach(() => {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
});
afterEach(() => vi.unstubAllGlobals());

const ORDERS = () => [
  ...[1, 2, 3, 4, 5, 6].map((pk) => card(pk, { output_sku: pk <= 4 ? `SKU-${pk}` : "SKU-1" })),
  card(7, {
    recipe_name: "Croissant",
    full_price_qty: "8",
    loss_qty: "2",
    partition: [
      { quantity: "8", quality_grade_ref: "standard", quality_defect_ref: "", loss: false },
      { quantity: "2", quality_grade_ref: "", quality_defect_ref: "overbaked", loss: true },
    ],
    quality_exception: true,
  }),
  card(8, { closed: false, status: "started" }),
  card(9, { quality_reviewed: true, recipe_name: "Brioche revisado" }),
];

describe("QualityGatePanel — qualidade em lote", () => {
  it("junta os lotes sem exceção num cartão com a soma, a consequência e um ato", async () => {
    const wrapper = mountPanel(ORDERS());
    const clean = wrapper.find("[data-quality-clean]");

    expect(clean.text()).toContain("6 lotes de hoje sem exceção");
    expect(clean.text()).toContain("60 peças, todas no padrão · perda 0 · desconto 0");
    expect(clean.text()).toContain("+2");
    expect(wrapper.find("[data-quality-closers]").text()).toContain("Rafael");
    // 4 produtos com fila de 2 pessoas cada (o SKU-1 repetido conta uma vez).
    expect(wrapper.find("[data-quality-released]").text()).toContain(
      "até 8 clientes avisados",
    );
    expect(wrapper.find("[data-quality-released]").text()).toContain("“Me avise” de 4 produtos");
    const confirm = wrapper.find("[data-quality-confirm-batch]");
    expect(confirm.text()).toContain("6 lotes, nenhuma exceção · Confirmar");
    expect(clean.text()).toContain("Fica registrado com seu nome.");

    await confirm.trigger("click");
    expect(wrapper.emitted("confirm-batch")).toHaveLength(1);
  });

  it("mostra todos os lotes limpos só quando pedido", async () => {
    const wrapper = mountPanel(ORDERS());
    expect(wrapper.find("[data-quality-clean]").text()).not.toContain("Receita 6");
    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("Ver os 6 lotes"))!
      .trigger("click");
    expect(wrapper.find("[data-quality-clean]").text()).toContain("Receita 6");
  });

  it("deixa as exceções à parte, uma a uma, com duas saídas", async () => {
    const wrapper = mountPanel(ORDERS());
    const exceptions = wrapper.findAll("[data-quality-exception]");

    expect(exceptions).toHaveLength(1);
    expect(exceptions[0]!.text()).toContain("Croissant");
    expect(exceptions[0]!.text()).toContain("Perda 2");
    expect(exceptions[0]!.text()).toContain("fechado por Rafael 07:00");

    const buttons = exceptions[0]!.findAll("button");
    await buttons.find((button) => button.text().includes("Confirmar assim"))!.trigger("click");
    await buttons.find((button) => button.text().includes("Corrigir"))!.trigger("click");
    expect(wrapper.emitted("confirm-one")?.[0]?.[0]).toMatchObject({ pk: 7 });
    expect(wrapper.emitted("correct")?.[0]?.[0]).toMatchObject({ pk: 7 });
  });

  it("deixa fora do portão o lote não fechado, com atalho para o Fechamento", async () => {
    const wrapper = mountPanel(ORDERS());
    const open = wrapper.find("[data-quality-open]");

    expect(open.text()).toContain("1 lote ainda no forno ou sem fechar. Entra aqui depois do Fechamento.");
    await open.find("button").trigger("click");
    expect(wrapper.emitted("go-close")).toHaveLength(1);
  });

  it("separa os confirmados numa aba própria", async () => {
    const wrapper = mountPanel(ORDERS());
    expect(wrapper.text()).not.toContain("Brioche revisado");

    await wrapper
      .findAll('[role="tab"]')
      .find((tab) => tab.text().includes("Confirmados"))!
      .trigger("click");

    expect(wrapper.find("[data-quality-reviewed]").text()).toContain("Brioche revisado");
  });

  it("a troca do painel conta cada vista; a exceção leva o selo de aviso", () => {
    const wrapper = mountPanel(ORDERS());
    const tabs = wrapper.findAll('[role="tab"]').map((tab) => tab.text());

    expect(tabs).toEqual(["Para confirmar 7", "Confirmados 1"]);
    const badge = wrapper.find("[data-quality-exception] [data-quality-exception-badge]");
    expect(badge.attributes("data-color")).toBe("warning");
    expect(badge.text()).not.toBe("");
  });

  it("não oferece o ato sem permissão e cala a fila que não pôde ser lida", () => {
    const wrapper = mountPanel(
      [card(1, { alert_waiting_count: null })],
      { batchAvailable: false, isToday: false },
    );

    expect(wrapper.find("[data-quality-clean]").text()).toContain("1 lote sem exceção");
    expect(wrapper.find("[data-quality-confirm-batch]").attributes("disabled")).toBeDefined();
    expect(wrapper.find("[data-quality-released]").exists()).toBe(false);
  });
});

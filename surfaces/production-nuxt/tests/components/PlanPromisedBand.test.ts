// WP-F13: a faixa do pedido à Produção no topo do Planejamento.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed } from "vue";
import { mount } from "@vue/test-utils";

import PlanPromisedBand from "../../app/components/PlanPromisedBand.vue";
import { unbackedOrders } from "../../app/presentation/production";
import type {
  ProductionMatrixRowProjection,
  PromisedOrderProjection,
} from "../../app/types/production";
import { nuxtUiStubs } from "../support/nuxtUiStubs";

const TODAY = "2026-11-28";

function order(over: Partial<PromisedOrderProjection> = {}): PromisedOrderProjection {
  return {
    ref: "PDV-281126-A1",
    customer_first_name: "Clara",
    due_time: "09:00",
    fulfillment_type: "pickup",
    qty: "12",
    status: "confirmed",
    status_label: "Confirmado",
    ...over,
  };
}

function croissant(orders: PromisedOrderProjection[]): ProductionMatrixRowProjection {
  const ordered = orders.reduce((sum, o) => sum + Number(o.qty), 0);
  return {
    output_sku: "CRO",
    recipe_pk: 1,
    recipe_name: "Croissant",
    output_unit: "un",
    planned_orders: [],
    started_orders: [],
    finished_orders: [],
    promised: {
      date: "2026-11-29",
      planned_qty: "0",
      ordered_qty: String(ordered),
      free_qty: "0",
      over_plan_qty: String(ordered),
      orders,
    },
  } as unknown as ProductionMatrixRowProjection;
}

function mountBand(rows: ProductionMatrixRowProjection[], over: { canPlan?: boolean; busySku?: string | null } = {}) {
  return mount(PlanPromisedBand, {
    props: {
      items: unbackedOrders(rows),
      today: TODAY,
      canPlan: over.canPlan ?? true,
      busySku: over.busySku ?? null,
    },
    global: { stubs: { ...nuxtUiStubs, Icon: true } },
  });
}

describe("PlanPromisedBand", () => {
  beforeEach(() => vi.stubGlobal("computed", computed));
  afterEach(() => vi.unstubAllGlobals());

  it("diz o que está encomendado sem lote, quem e quando, e o gesto de planejar", async () => {
    const w = mountBand([croissant([order()])]);
    expect(w.get("[data-plan-promised-text]").text().replace(/\s+/g, " ")).toBe(
      "Encomendado sem lote: Croissant 12",
    );
    expect(w.get("[data-plan-promised-who]").text()).toBe("Clara · amanhã 9h");
    expect(w.get("[data-plan-promised-plan]").text()).toBe("Planejar 12");

    await w.get("[data-plan-promised-plan]").trigger("click");
    expect(w.emitted("plan")?.[0]?.[0]).toMatchObject({ targetQty: "12", kind: "no-lot" });
    await w.get("[data-plan-promised-orders]").trigger("click");
    expect(w.emitted("orders")).toHaveLength(1);
  });

  it("não tem recusar: a Produção só planeja (D-042), e sem permissão nem isso", () => {
    const w = mountBand([croissant([order()])], { canPlan: false });
    expect(w.find("[data-plan-promised-plan]").exists()).toBe(false);
    expect(w.text()).not.toMatch(/recusar|aceitar/i);
  });

  it("vários pedidos: dois nomes e o resto contado; horas diferentes viram faixa", () => {
    const w = mountBand([
      croissant([
        order({ ref: "A", customer_first_name: "Marina", due_time: "08:30", qty: "2" }),
        order({ ref: "B", customer_first_name: "Bruno", due_time: "11:00", qty: "4" }),
        order({ ref: "C", customer_first_name: "", due_time: "10:00", qty: "1" }),
      ]),
    ]);
    expect(w.get("[data-plan-promised-who]").text()).toBe(
      "Marina, Bruno e mais 1 · amanhã, das 8h30 às 11h",
    );
  });

  it("quem encomendou duas vezes aparece uma vez", () => {
    const w = mountBand([
      croissant([order({ ref: "A", qty: "12" }), order({ ref: "B", qty: "12" })]),
    ]);
    expect(w.get("[data-plan-promised-who]").text()).toBe("Clara · amanhã 9h");
  });

  it("planejando: o botão diz isso e nenhum outro dispara", () => {
    const w = mountBand([croissant([order()])], { busySku: "CRO" });
    const button = w.get("[data-plan-promised-plan]");
    expect(button.text()).toBe("Planejando…");
    expect(button.attributes("disabled")).toBeDefined();
  });

  it("com linha no dia que já conta as encomendas: o fato e Ir para a linha, sem Planejar", async () => {
    const row = croissant([order()]);
    (row as { suggestion: unknown }).suggestion = { quantity: "196" };
    const w = mountBand([row]);
    expect(w.get("[data-plan-promised-text]").text().replace(/\s+/g, " ")).toBe(
      "Croissant: 12 encomendadas, já contadas na sugestão de 196",
    );
    expect(w.find("[data-plan-promised-plan]").exists()).toBe(false);
    await w.get("[data-plan-promised-line]").trigger("click");
    expect(w.emitted("line")).toHaveLength(1);
    expect(w.emitted("plan")).toBeUndefined();
  });

  it("sem nada a cobrir, a faixa não existe", () => {
    expect(mountBand([]).find("[data-plan-promised-band]").exists()).toBe(false);
  });
});

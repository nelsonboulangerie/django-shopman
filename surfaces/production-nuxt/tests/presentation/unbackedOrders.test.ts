// WP-F13 (P1-04): o pedido à Produção. A encomenda da data que o plano não cobre
// ganha um lugar no topo do Planejamento, pela régua das reservas (`promised`,
// WP-F08): "Encomendado sem lote: Croissant 12" com "Planejar 12". A Produção só
// planeja (D-042, item 2).
import { describe, expect, it } from "vitest";

import { bandOrders, unbackedOrders } from "~/presentation/production";
import type {
  ProductionMatrixRowProjection,
  ProductionPromisedProjection,
  PromisedOrderProjection,
} from "~/types/production";

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

function promised(over: Partial<ProductionPromisedProjection> = {}): ProductionPromisedProjection {
  return {
    date: "2026-11-29",
    planned_qty: "0",
    ordered_qty: "12",
    free_qty: "0",
    over_plan_qty: "12",
    orders: [order()],
    ...over,
  };
}

function row(over: Partial<ProductionMatrixRowProjection> = {}): ProductionMatrixRowProjection {
  return {
    output_sku: "CRO",
    recipe_pk: 1,
    recipe_name: "Croissant",
    output_unit: "un",
    planned_orders: [],
    started_orders: [],
    finished_orders: [],
    suggestion: null,
    promised: null,
    ...over,
  } as unknown as ProductionMatrixRowProjection;
}

describe("unbackedOrders: o que o plano da data não cobre", () => {
  it('sem lote: "Encomendado sem lote: Croissant 12" e "Planejar 12"', () => {
    const [item, ...rest] = unbackedOrders([row({ promised: promised() })]);
    expect(rest).toHaveLength(0);
    expect(item).toMatchObject({
      kind: "no-lot",
      missing: 12,
      targetQty: "12",
      headline: "Encomendado sem lote",
      subject: "Croissant 12",
      actionLabel: "Planejar 12",
    });
  });

  it('acima do plano: diz só o que falta, e o gesto é "Planejar mais 3" (o total vai ao servidor)', () => {
    const [item] = unbackedOrders([
      row({ promised: promised({ planned_qty: "12", ordered_qty: "15", over_plan_qty: "3", free_qty: "0" }) }),
    ]);
    expect(item).toMatchObject({
      kind: "over-plan",
      subject: "Croissant 3",
      actionLabel: "Planejar mais 3",
      targetQty: "15",
    });
  });

  it("plano que cobre as encomendas, plano sem pedido e produto sem régua ficam de fora", () => {
    expect(
      unbackedOrders([
        row({ promised: promised({ planned_qty: "42", over_plan_qty: "0", free_qty: "30" }) }),
        row({ output_sku: "BG", promised: promised({ planned_qty: "20", ordered_qty: "0", over_plan_qty: "0", orders: [] }) }),
        row({ output_sku: "PC" }),
      ]),
    ).toEqual([]);
  });

  // Decisão da coordenação (28/11): coberta numa linha do dia (a sugestão já conta as
  // encomendas), a encomenda não vai para a faixa; o chip da linha basta. Dois "Planejar"
  // com números diferentes para o mesmo produto eram armadilha.
  it("coberta pela sugestão da linha do dia: fora da faixa", () => {
    const suggestion = { quantity: "196" } as ProductionMatrixRowProjection["suggestion"];
    const items = unbackedOrders([row({ recipe_name: "Croissant Manteiga", suggestion, promised: promised() })]);
    expect(items[0]).toMatchObject({ kind: "no-lot", coveredBy: "196", subject: "Croissant Manteiga 12" });
    expect(bandOrders(items)).toEqual([]);
  });

  it("sugestão abaixo do encomendado, ou sem sugestão, a faixa planeja o que falta", () => {
    const low = { quantity: "8" } as ProductionMatrixRowProjection["suggestion"];
    const items = unbackedOrders([row({ suggestion: low, promised: promised() })]);
    expect(items[0]).toMatchObject({ coveredBy: "", actionLabel: "Planejar 12" });
    expect(bandOrders(items)).toHaveLength(1);
    expect(unbackedOrders([row({ promised: promised() })])[0]!.actionLabel).toBe("Planejar 12");
  });

  it("acima do plano, com lote no dia, segue Planejar mais (a linha já está planejada)", () => {
    const suggestion = { quantity: "196" } as ProductionMatrixRowProjection["suggestion"];
    const [item] = unbackedOrders([
      row({
        suggestion,
        planned_orders: [{ pk: 1 }] as unknown as ProductionMatrixRowProjection["planned_orders"],
        promised: promised({ planned_qty: "12", ordered_qty: "15", over_plan_qty: "3" }),
      }),
    ]);
    expect(item).toMatchObject({ kind: "over-plan", coveredBy: "", actionLabel: "Planejar mais 3" });
    expect(bandOrders([item!])).toHaveLength(1);
  });

  it("peso diz a unidade; vários produtos em ordem alfabética", () => {
    const items = unbackedOrders([
      row({ output_sku: "PCAMP", recipe_name: "Pain de Campagne", output_unit: "kg", promised: promised({ over_plan_qty: "1.5", ordered_qty: "1.5" }) }),
      row({ output_sku: "BG", recipe_name: "Baguete", promised: promised({ over_plan_qty: "3", ordered_qty: "3" }) }),
    ]);
    expect(items.map((item) => [item.subject, item.actionLabel, item.targetQty])).toEqual([
      ["Baguete 3", "Planejar 3", "3"],
      ["Pain de Campagne 1,5 kg", "Planejar 1,5 kg", "1.5"],
    ]);
  });
});

// WP-F10 (P1-02, P1-20, P1-04): o que a Produção diz sobre encomenda sai da régua
// das reservas (`promised`, WP-F08), com nome e hora. Medido em 23/11: o lote de HOJE
// dizia "7 un. para 9h" com a encomenda de AMANHÃ, a lista mostrava
// "PDV-261123-B72 · Aceito · 3 un.", e o conjunto do Planejamento dizia "sem
// encomenda" para produto com demanda na data, mas sem lote.
import { describe, expect, it } from "vitest";

import { isCleanRow, isManualRow, rowHasCaveat } from "~/presentation/planningRows";
import {
  orderedLabel,
  promisedChipLabel,
  promisedDay,
  promisedGap,
  promisedOrderLine,
  rowOrderedUnits,
} from "~/presentation/production";
import type {
  ProductionMatrixRowProjection,
  ProductionPromisedProjection,
  PromisedOrderProjection,
} from "~/types/production";

const TODAY = "2026-11-26";
const TOMORROW = "2026-11-27";

function order(over: Partial<PromisedOrderProjection> = {}): PromisedOrderProjection {
  return {
    ref: "NB-261126-B57",
    customer_first_name: "Clara",
    due_time: "09:00",
    fulfillment_type: "pickup",
    qty: "1",
    status: "confirmed",
    status_label: "Confirmado",
    ...over,
  };
}

function promised(over: Partial<ProductionPromisedProjection> = {}): ProductionPromisedProjection {
  return {
    date: TOMORROW,
    planned_qty: "42",
    ordered_qty: "1",
    free_qty: "41",
    over_plan_qty: "0",
    orders: [order()],
    ...over,
  };
}

function row(over: Partial<ProductionMatrixRowProjection> = {}): ProductionMatrixRowProjection {
  return {
    output_sku: "CROISSANT",
    recipe_pk: 1,
    recipe_name: "Croissant Manteiga",
    output_unit: "un",
    planned_qty: "0",
    started_qty: "0",
    finished_qty: "0",
    planned_orders: [],
    started_orders: [],
    finished_orders: [],
    suggestion: null,
    promised: null,
    ...over,
  } as unknown as ProductionMatrixRowProjection;
}

describe("o chip: unidades e quando, pela régua das reservas", () => {
  it('lote de amanhã com a encomenda de amanhã: "1 un. · amanhã 9h"', () => {
    expect(promisedChipLabel(row({ promised: promised() }), TODAY)).toBe("1 un. · amanhã 9h");
  });

  it("sem encomenda na data não há chip (o lote de hoje não herda a de amanhã)", () => {
    expect(promisedChipLabel(row(), TODAY)).toBe("");
    expect(rowOrderedUnits(row())).toBe(0);
    // Plano sem pedido: a régua publica o planejado, e o chip continua calado.
    const planOnly = promised({ date: TODAY, ordered_qty: "0", orders: [] });
    expect(promisedChipLabel(row({ promised: planOnly }), TODAY)).toBe("");
  });

  it("nunca cola o total na hora do primeiro pedido", () => {
    const spread = promised({
      ordered_qty: "7",
      orders: [
        order({ ref: "A", due_time: "08:30", qty: "4" }),
        order({ ref: "B", due_time: "11:00", qty: "3" }),
      ],
    });
    const label = promisedChipLabel(row({ promised: spread }), TODAY);
    expect(label).toBe("7 un. · amanhã, das 8h30 às 11h");
    expect(label).not.toMatch(/para 8h30|amanhã 8h30$/);

    // Um pedido sem hora: a faixa mentiria sobre ele, o chip diz só o dia.
    const untimed = promised({
      ordered_qty: "5",
      orders: [order({ ref: "A", qty: "4" }), order({ ref: "B", due_time: "", qty: "1" })],
    });
    expect(promisedChipLabel(row({ promised: untimed }), TODAY)).toBe("5 un. · amanhã");
  });

  it("o dia: hoje, amanhã e, mais longe, o dia da semana com a data", () => {
    expect(promisedDay(TODAY, TODAY)).toBe("hoje");
    expect(promisedDay(TOMORROW, TODAY)).toBe("amanhã");
    expect(promisedDay("2026-11-28", TODAY)).toBe("sáb 28/11");
  });

  it("produto vendido por peso diz a unidade de peso", () => {
    const kg = promised({ ordered_qty: "1.5", orders: [order({ qty: "1.5" })] });
    expect(promisedChipLabel(row({ promised: kg, output_unit: "kg" }), TODAY)).toBe(
      "1,5 kg · amanhã 9h",
    );
  });
});

describe("a lista: primeiro nome, modo, hora e quantidade", () => {
  it('"Clara · retirada · 9h · 1 un."', () => {
    expect(promisedOrderLine(order(), "un")).toBe("Clara · retirada · 9h · 1 un.");
  });

  it("sem nome, o código do pedido; sem hora ou sem modo, a parte some", () => {
    expect(
      promisedOrderLine(order({ customer_first_name: "", due_time: "", fulfillment_type: "delivery" }), "un"),
    ).toBe("NB-261126-B57 · entrega · 1 un.");
    expect(promisedOrderLine(order({ fulfillment_type: "" }), "un")).toBe("Clara · 9h · 1 un.");
  });

  it("concorda em gênero e número", () => {
    expect(orderedLabel(1, "un")).toBe("1 un. encomendada");
    expect(orderedLabel(6, "un")).toBe("6 un. encomendadas");
    expect(orderedLabel("1.2", "kg")).toBe("1,2 kg encomendados");
  });

  it("o que o plano não cobre, em uma frase", () => {
    expect(promisedGap(promised(), "un")).toBe("");
    expect(promisedGap(promised({ planned_qty: "4", ordered_qty: "7", over_plan_qty: "3" }), "un")).toBe(
      "O plano da data fica 3 un. abaixo das encomendas.",
    );
    expect(promisedGap(promised({ planned_qty: "0", over_plan_qty: "1" }), "un")).toBe(
      "Nenhum lote planejado para esta data.",
    );
  });
});

describe('o Planejamento só diz "sem encomenda" sem demanda na data (P1-04)', () => {
  const suggested = {
    quantity: "12",
    material_shortages: [],
    waste_discounted: false,
    soldout_days: 0,
    sample_size: 0,
  } as unknown as ProductionMatrixRowProjection["suggestion"];

  it("encomenda na data sem lote tira a linha do conjunto sem ressalva", () => {
    const withDemand = row({
      suggestion: suggested,
      promised: promised({ planned_qty: "0", free_qty: "0", over_plan_qty: "1" }),
    });
    expect(rowHasCaveat(withDemand)).toBe(true);
    expect(isCleanRow(withDemand)).toBe(false);
    expect(isManualRow(row({ promised: promised({ planned_qty: "0" }) }))).toBe(false);
  });

  it("sem demanda na data, a linha pode ir para o conjunto", () => {
    expect(isCleanRow(row({ suggestion: suggested }))).toBe(true);
  });
});

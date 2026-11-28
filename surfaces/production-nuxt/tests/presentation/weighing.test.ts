import { describe, expect, it } from "vitest";
import {
  blindLabelsFromPrintDocument,
  operationalTargetDisplay,
  preparationLabelsFromPrintDocument,
  keepNumberWithUnit,
  projectedQuantityDisplay,
  stockFacts,
  weighingLabels,
  weighingRows,
} from "~/presentation/weighing";
import type { ProductionLabelPrintDocument } from "~/types/productionPrinting";

describe("apresentação da balança", () => {
  it("não recalcula o alvo operacional emitido pelo servidor", () => {
    expect(operationalTargetDisplay("102 g", "101 g")).toBe("102\u00a0g");
    expect(operationalTargetDisplay(undefined, "101 g")).toBe("101\u00a0g");
  });

  it("não inventa conversão de volume nem de contagem", () => {
    expect(projectedQuantityDisplay("700 ml")).toBe("700\u00a0ml");
    expect(projectedQuantityDisplay("12 un.")).toBe("12\u00a0un.");
  });

  it("formata a alternativa futura em kg com três casas exatas", () => {
    expect(projectedQuantityDisplay("1,25 kg")).toBe("1,250\u00a0kg");
    expect(projectedQuantityDisplay("2 kg")).toBe("2,000\u00a0kg");
  });

  it("deriva a etiqueta cega somente do documento congelado e do alvo operacional", () => {
    const document: ProductionLabelPrintDocument = {
      mode: "blind",
      selected_date: "2026-09-10",
      tickets: [
        {
          ticket_ref: "frozen:flour",
          blind_code: "Z9",
          made_display: "10/09",
          expiry_display: "11/09",
          ingredients: [
            {
              name: "Farinha congelada",
              sku: "FARINHA-FROZEN",
              quantity_display: "101 g",
              target_display: "102 g",
              annotation: "(≈ 2 un.)",
            },
          ],
        },
      ],
    };

    expect(blindLabelsFromPrintDocument(document)).toEqual([
      {
        code: "Z9",
        ingredient: "Farinha congelada",
        sku: "FARINHA-FROZEN",
        weight: "102\u00a0g",
        annotation: "(≈ 2\u00a0un.)",
        date: "10/09",
        key: "frozen:flour-FARINHA-FROZEN-0-0",
      },
    ]);
    expect(preparationLabelsFromPrintDocument(document)).toEqual([]);
  });

  it("deriva a etiqueta explícita sem depender da projection viva", () => {
    const document: ProductionLabelPrintDocument = {
      mode: "explicit",
      selected_date: "2026-09-10",
      tickets: [
        {
          ticket_ref: "prep-1",
          blind_code: "D8",
          made_display: "10/09",
          expiry_display: "11/09",
          name: "Massa congelada",
          output_sku: "MASSA-FROZEN",
          output_quantity_display: "12 un.",
          total_weight_display: "2.000 g",
          sources_display: "12 pães",
        },
      ],
    };

    expect(preparationLabelsFromPrintDocument(document)).toEqual([
      {
        ticket_ref: "prep-1",
        name: "Massa congelada",
        output_sku: "MASSA-FROZEN",
        output_quantity_display: "12 un.",
        total_weight_display: "2.000 g",
        sources_display: "12 pães",
        blind_code: "D8",
        made_display: "10/09",
        expiry_display: "11/09",
      },
    ]);
    expect(blindLabelsFromPrintDocument(document)).toEqual([]);
  });
});

describe("linhas da balança e etiquetas: a mesma lista (P1-26)", () => {
  const ticket = {
    ticket_ref: "prep-massa",
    blind_code: "D8",
    ingredients: [
      {
        sku: "MASSA-VELHA-TRADICAO",
        name: "Massa velha de Tradição",
        target_display: "344 g",
        quantity_display: "344 g",
        annotation: "",
      },
      {
        sku: "FARINHA-T55",
        name: "Farinha T55",
        target_display: "800 g",
        quantity_display: "800 g",
        annotation: "",
      },
      {
        sku: "OVO",
        name: "Ovo",
        target_display: "350 g",
        quantity_display: "350 g",
        annotation: "≈ 7 ovos",
      },
    ],
  };

  it("pesa a ficha como o servidor mandou; a massa velha é um ingrediente da lista", () => {
    const rows = weighingRows(ticket);
    expect(rows.map((row) => [row.name, row.target, row.annotation, row.quantity])).toEqual([
      // O alvo e a ajuda saem com número e unidade presos (#3656); a quantidade que
      // prende a marca fica como o servidor mandou.
      ["Massa velha de Tradição", "344\u00a0g", "", "344 g"],
      ["Farinha T55", "800\u00a0g", "", "800 g"],
      ["Ovo", "350\u00a0g", "≈ 7\u00a0ovos", "350 g"],
    ]);
  });

  it("a etiqueta traz o mesmo peso da tela, linha a linha", () => {
    const labels = weighingLabels([ticket], (t) => t.ticket_ref, "06/07");
    expect(labels.map((label) => [label.ingredient, label.weight])).toEqual(
      weighingRows(ticket).map((row) => [row.name, row.target]),
    );
    expect(labels.every((label) => label.code === "D8" && label.date === "06/07")).toBe(true);
    expect(new Set(labels.map((label) => label.key)).size).toBe(labels.length);
  });
});

describe("número e unidade nunca se separam (#3656)", () => {
  it("prende cada número à unidade com espaço não separável", () => {
    expect(keepNumberWithUnit("7200 g")).toBe("7200\u00a0g");
    expect(keepNumberWithUnit("(≈ 0,132 litros)")).toBe("(≈ 0,132\u00a0litros)");
    expect(keepNumberWithUnit("+ 176 g de margem")).toBe("+ 176\u00a0g de margem");
    expect(keepNumberWithUnit("")).toBe("");
    expect(keepNumberWithUnit(undefined)).toBe("");
  });

  it("toda quantidade formatada sai presa, inclusive em kg", () => {
    expect(projectedQuantityDisplay("7200 g")).toBe("7200\u00a0g");
    expect(projectedQuantityDisplay("1,25 kg")).not.toMatch(/\d kg/);
  });
});

describe("saldo e falta na Preparação", () => {
  const base = { is_subrecipe: false, is_short: false, available_display: "", missing_display: "" };

  it("a falta diz quanto falta", () => {
    expect(
      stockFacts({ ...base, is_short: true, available_display: "700 g", missing_display: "300 g" }),
    ).toEqual({ available: "700\u00a0g", shortage: "Faltam 300\u00a0g" });
  });

  it("sem falta, só o saldo", () => {
    expect(stockFacts({ ...base, available_display: "5000 g" })).toEqual({ available: "5000\u00a0g", shortage: "" });
  });

  it("pré-preparo nunca mostra saldo nem falta", () => {
    expect(
      stockFacts({
        is_subrecipe: true,
        is_short: true,
        available_display: "0 g",
        missing_display: "300 g",
      }),
    ).toEqual({ available: "", shortage: "" });
  });
});

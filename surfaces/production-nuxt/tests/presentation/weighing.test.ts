import { describe, expect, it } from "vitest";
import {
  blindLabelsFromPrintDocument,
  operationalTargetDisplay,
  preparationLabelsFromPrintDocument,
  projectedQuantityDisplay,
  weighingRows,
} from "~/presentation/weighing";
import type { ProductionLabelPrintDocument } from "~/types/productionPrinting";

describe("apresentação da balança", () => {
  it("não recalcula o alvo operacional emitido pelo servidor", () => {
    expect(operationalTargetDisplay("102 g", "101 g")).toBe("102 g");
    expect(operationalTargetDisplay(undefined, "101 g")).toBe("101 g");
  });

  it("não inventa conversão de volume nem de contagem", () => {
    expect(projectedQuantityDisplay("700 ml")).toBe("700 ml");
    expect(projectedQuantityDisplay("12 un.")).toBe("12 un.");
  });

  it("formata a alternativa futura em kg com três casas exatas", () => {
    expect(projectedQuantityDisplay("1,25 kg")).toBe("1,250 kg");
    expect(projectedQuantityDisplay("2 kg")).toBe("2,000 kg");
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
        weight: "102 g",
        annotation: "(≈ 2 un.)",
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

describe("linhas da balança: mistura final e massa velha no teto", () => {
  const ticket = {
    output_sku: "MASSA-MF",
    ingredients: [
      {
        sku: "FARINHA-T55",
        name: "Farinha T55",
        target_display: "1000 g",
        quantity_display: "1000 g",
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
    old_dough: {
      old_dough_display: "344 g",
      lines: [
        { sku: "FARINHA-T55", target_display: "800 g" },
        { sku: "OVO", target_display: "280 g" },
      ],
    },
  };

  it("sem massa velha pesa a ficha do preparo, com a ajuda de contagem", () => {
    const rows = weighingRows(ticket, false);
    expect(rows.map((row) => [row.sku, row.target, row.annotation])).toEqual([
      ["FARINHA-T55", "1000 g", ""],
      ["OVO", "350 g", "≈ 7 ovos"],
    ]);
  });

  it("com massa velha pesa a mistura final no teto e põe a massa velha primeiro", () => {
    const rows = weighingRows(ticket, true);
    expect(rows.map((row) => [row.name, row.target, row.isOldDough])).toEqual([
      ["Massa velha", "344 g", true],
      ["Farinha T55", "800 g", false],
      ["Ovo", "280 g", false],
    ]);
    // A contagem era do peso cheio: no teto ela mentiria.
    expect(rows.every((row) => row.annotation === "")).toBe(true);
  });

  it("ficha sem teto ignora o pedido de massa velha", () => {
    const rows = weighingRows({ ...ticket, old_dough: null }, true);
    expect(rows.map((row) => row.target)).toEqual(["1000 g", "350 g"]);
  });
});

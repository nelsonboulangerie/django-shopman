import { describe, expect, it } from "vitest";

import {
  alertsReleased,
  batchConfirmLabel,
  cleanSummary,
  closersSummary,
  exceptionBadge,
  exceptionReference,
  exceptionSegments,
  lotQuantityLabel,
  quantityMeasure,
  qualityGate,
  reviewedSummary,
} from "../../app/presentation/qualityGate";
import type {
  QCDefectProjection,
  QCGradeProjection,
  QCOrderCardProjection,
} from "../../app/types/production";

const GRADES: QCGradeProjection[] = [
  { ref: "standard", label: "Padrão", rank: 30, markdown_percent: 0, is_default: true },
  { ref: "fair", label: "Regular", rank: 20, markdown_percent: 30, is_default: false },
];
const DEFECTS: QCDefectProjection[] = [
  { ref: "overbaked", label: "Assou demais", hint: "", forces_discard: true },
  { ref: "shape", label: "Formato irregular", hint: "", forces_discard: false },
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
    planned_qty: "60",
    started_qty: "60",
    started_at_display: "06:00",
    elapsed_minutes: 0,
    can_close: false,
    closed: true,
    can_correct: true,
    quality_reviewed: false,
    partition: [{ quantity: "60", quality_grade_ref: "standard", quality_defect_ref: "", loss: false }],
    correction_count: 0,
    last_correction_at_display: "",
    committed_qty: "",
    full_price_qty: "60",
    discounted_qty: "0",
    loss_qty: "0",
    quality_exception: false,
    closed_by: "Rafael",
    closed_at_display: "07:25",
    typical_loss_qty: "",
    alert_waiting_count: 0,
    output_unit: "un",
    ...overrides,
  };
}

describe("qualityGate", () => {
  it("separa sem exceção, exceções, confirmados e os que não fecharam", () => {
    const gate = qualityGate([
      card(1),
      card(2, { quality_exception: true }),
      card(3, { quality_reviewed: true }),
      card(4, { closed: false, status: "started" }),
      card(5, { quality_reviewed: true, quality_exception: true }),
    ]);

    expect(gate.clean.map((order) => order.pk)).toEqual([1]);
    expect(gate.exceptions.map((order) => order.pk)).toEqual([2]);
    expect(gate.reviewed.map((order) => order.pk)).toEqual([3, 5]);
    expect(gate.openCount).toBe(1);
  });

  it("soma as peças e escreve o ato com o fato", () => {
    expect(cleanSummary([card(1), card(2, { full_price_qty: "24" })])).toBe(
      "84 peças, todas no padrão · perda 0 · desconto 0",
    );
    expect(cleanSummary([card(1, { full_price_qty: "1" })])).toBe(
      "1 peça, todas no padrão · perda 0 · desconto 0",
    );
    expect(batchConfirmLabel(6)).toBe("6 lotes, nenhuma exceção · Confirmar");
    expect(batchConfirmLabel(1)).toBe("1 lote, nenhuma exceção · Confirmar");
  });

  it("diz quem fechou e a janela de horário", () => {
    expect(
      closersSummary([
        card(1, { closed_by: "Rafael", closed_at_display: "13:40" }),
        card(2, { closed_by: "Joana", closed_at_display: "06:10" }),
        card(3, { closed_by: "Rafael", closed_at_display: "09:00" }),
      ]),
    ).toEqual({ names: "Rafael · Joana", window: "entre 06:10 e 13:40" });
    expect(closersSummary([card(1)])).toEqual({ names: "Rafael", window: "às 07:25" });
  });

  it("soma o 'Me avise' por produto e cala quando a fila não foi lida", () => {
    expect(
      alertsReleased([
        card(1, { output_sku: "A", alert_waiting_count: 3 }),
        card(2, { output_sku: "A", alert_waiting_count: 3 }),
        card(3, { output_sku: "B", alert_waiting_count: 2 }),
        card(4, { output_sku: "C", alert_waiting_count: 0 }),
      ]),
    ).toEqual({ people: 5, products: 2 });
    expect(alertsReleased([card(1, { alert_waiting_count: null })])).toBeNull();
  });

  it("descreve a perda com o motivo e a referência para decidir", () => {
    const loss = card(1, {
      recipe_name: "Croissant",
      partition: [
        { quantity: "58", quality_grade_ref: "standard", quality_defect_ref: "", loss: false },
        { quantity: "2", quality_grade_ref: "", quality_defect_ref: "overbaked", loss: true },
      ],
      full_price_qty: "58",
      loss_qty: "2",
      quality_exception: true,
      typical_loss_qty: "1",
    });

    expect(exceptionSegments(loss, GRADES, DEFECTS)).toEqual([
      { kind: "standard", quantity: 58, label: "58 padrão" },
      { kind: "loss", quantity: 2, label: "2 perda · “Assou demais”" },
    ]);
    expect(exceptionBadge(loss)).toBe("Perda 2");
    expect(exceptionReference(loss)).toBe(
      "Entraram 60. Perda típica de Croissant: 1 por lote.",
    );
  });

  it("descreve o desconto com o grau, o percentual e o motivo", () => {
    const discounted = card(2, {
      partition: [
        { quantity: "18", quality_grade_ref: "standard", quality_defect_ref: "", loss: false },
        { quantity: "6", quality_grade_ref: "fair", quality_defect_ref: "shape", loss: false },
      ],
      started_qty: "24",
      full_price_qty: "18",
      discounted_qty: "6",
      quality_exception: true,
    });

    expect(exceptionSegments(discounted, GRADES, DEFECTS)[1]).toEqual({
      kind: "discount",
      quantity: 6,
      label: "6 regular (−30%) · “Formato irregular”",
    });
    expect(exceptionBadge(discounted)).toBe("Desconto 6");
    expect(exceptionReference(discounted)).toBe("Entraram 24.");
  });

  it("acusa contagem acima do que entrou", () => {
    expect(
      exceptionBadge(card(3, { full_price_qty: "62", quality_exception: true })),
    ).toBe("Contagem 62 de 60");
  });

  it("nunca soma gramas com peças: agrupa por grandeza (seed Nelson)", () => {
    const clean = [
      card(1, { recipe_name: "Yudane", output_unit: "g", full_price_qty: "3453.659" }),
      card(2, { recipe_name: "Pasta Autolizada", output_unit: "g", full_price_qty: "17073.914" }),
      card(3, { recipe_name: "Massa Tradição", output_unit: "g", full_price_qty: "18480" }),
      card(4, { recipe_name: "Baguette", full_price_qty: "120" }),
      card(5, { recipe_name: "Croissant", full_price_qty: "192" }),
    ];

    expect(cleanSummary(clean)).toBe(
      "312 peças e 39 kg, tudo no padrão · perda 0 · desconto 0",
    );
    expect(cleanSummary(clean.slice(0, 3))).toBe(
      "39 kg, tudo no padrão · perda 0 · desconto 0",
    );
    expect(
      cleanSummary([
        card(1, { output_unit: "kg", full_price_qty: "2.5" }),
        card(2, { output_unit: "g", full_price_qty: "400" }),
        card(3, { output_unit: "L", full_price_qty: "1.5" }),
        card(4, { full_price_qty: "10" }),
      ]),
    ).toBe("10 peças, 2,9 kg e 1,5 L, tudo no padrão · perda 0 · desconto 0");
  });

  it("escreve cada lote na sua unidade, com vírgula decimal", () => {
    expect(lotQuantityLabel("3453.659", "g")).toBe("3,454 kg");
    expect(lotQuantityLabel("1800", "g")).toBe("1,8 kg");
    expect(lotQuantityLabel("850", "g")).toBe("850 g");
    expect(lotQuantityLabel("21", "un")).toBe("21 peças");
    expect(lotQuantityLabel("1", "")).toBe("1 peça");
    expect(quantityMeasure("1.5", "un")).toBe("1,5");
    expect(quantityMeasure("0.75", "kg")).toBe("750 g");
    expect(quantityMeasure("2", "dz")).toBe("2 dz");
  });

  it("referência, selo e partição de lote em gramas usam a unidade e a vírgula", () => {
    const dough = card(9, {
      recipe_name: "Massa Tradição",
      output_unit: "g",
      started_qty: "18480",
      partition: [
        { quantity: "17980", quality_grade_ref: "standard", quality_defect_ref: "", loss: false },
        { quantity: "500", quality_grade_ref: "", quality_defect_ref: "overbaked", loss: true },
      ],
      full_price_qty: "17980",
      loss_qty: "500",
      quality_exception: true,
      typical_loss_qty: "250.5",
    });

    expect(exceptionBadge(dough)).toBe("Perda 500 g");
    expect(exceptionSegments(dough, GRADES, DEFECTS).map((s) => s.label)).toEqual([
      "17,98 kg padrão",
      "500 g perda · “Assou demais”",
    ]);
    expect(exceptionReference(dough)).toBe(
      "Entraram 18,48 kg. Perda típica de Massa Tradição: 250,5 g por lote.",
    );
    expect(reviewedSummary(dough)).toBe("17,98 kg no padrão · 500 g de perda");
    expect(exceptionReference(card(1, { typical_loss_qty: "1.5" }))).toBe(
      "Entraram 60. Perda típica de Receita 1: 1,5 por lote.",
    );
  });
});

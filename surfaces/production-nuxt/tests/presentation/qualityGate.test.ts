import { describe, expect, it } from "vitest";

import {
  alertsReleased,
  batchConfirmLabel,
  cleanPieces,
  closersSummary,
  exceptionBadge,
  exceptionReference,
  exceptionSegments,
  qualityGate,
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
    expect(cleanPieces([card(1), card(2, { full_price_qty: "24" })])).toBe(84);
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
});

import { describe, expect, it } from "vitest";

import {
  applyDiscountGrade,
  buildPartition,
  canSubmit,
  defaultGradeRef,
  discountDefault,
  discountGrades,
  finishedTotal,
  fullPriceGrades,
  gradeBandClass,
  initialState,
  lossQty,
  ovenAnchor,
  pendingQuestions,
  typeBackspace,
  typeDigit,
} from "../app/presentation/qc";
import type { QCGradeProjection } from "../app/types/production";

const GRADES: QCGradeProjection[] = [
  { ref: "excellent", label: "Ótima", rank: 40, markdown_percent: 0, is_default: false },
  { ref: "standard", label: "Normal", rank: 30, markdown_percent: 0, is_default: true },
  { ref: "fair", label: "Razoável", rank: 20, markdown_percent: 20, is_default: false },
  { ref: "minimal", label: "Mínima", rank: 10, markdown_percent: 50, is_default: false },
];

describe("a escala", () => {
  it("separa preço cheio de desconto pelo markdown, não pelo nome", () => {
    expect(fullPriceGrades(GRADES).map((g) => g.ref)).toEqual(["excellent", "standard"]);
    expect(discountGrades(GRADES).map((g) => g.ref)).toEqual(["fair", "minimal"]);
  });

  it("o padrão vem do catálogo", () => {
    expect(defaultGradeRef(GRADES)).toBe("standard");
  });

  it("a faixa de cor deriva da semântica (rank/markdown), nunca do rótulo", () => {
    expect(gradeBandClass(GRADES[0]!, GRADES)).toBe("bg-emerald-500");
    expect(gradeBandClass(GRADES[1]!, GRADES)).toBe("bg-zinc-400");
    expect(gradeBandClass(GRADES[2]!, GRADES)).toBe("bg-amber-500");
    expect(gradeBandClass(GRADES[3]!, GRADES)).toBe("bg-orange-600");
  });
});

describe("a âncora do fechamento (o que entrou no forno)", () => {
  it("sem started, o previsto ancora sozinho", () => {
    expect(ovenAnchor(10, null)).toEqual({ anchor: 10, planned: null });
  });

  it("started diverge do previsto: ele ancora e o previsto vira referência", () => {
    // Planejou 10, enfornou 11 — fechar ancorado em 10 gravaria 1 de perda
    // que nunca existiu.
    expect(ovenAnchor(10, 11)).toEqual({ anchor: 11, planned: 10 });
  });

  it("started igual ao previsto não fabrica referência", () => {
    expect(ovenAnchor(10, 10)).toEqual({ anchor: 10, planned: null });
  });

  it("fornada avulsa: sem previsto e sem started, sem âncora", () => {
    expect(ovenAnchor(null, null)).toEqual({ anchor: null, planned: null });
  });

  it("started sem previsto (avulsa iniciada) ancora sozinho", () => {
    expect(ovenAnchor(null, 12)).toEqual({ anchor: 12, planned: null });
  });
});

describe("a aritmética subtrativa (QC-FORNADA §4)", () => {
  it("a tela nasce com tudo a preço cheio", () => {
    const state = initialState(40, "standard");
    expect(state.fullQty).toBe(40);
    expect(lossQty(state)).toBe(0);
    expect(finishedTotal(state)).toBe(40);
  });

  it("38 boas + grau menor: quantas assim recebe o não contado", () => {
    let state = initialState(40, "standard");
    state = { ...state, fullQty: 38, fullTouched: true };
    expect(discountDefault(state)).toBe(2);
    state = applyDiscountGrade(state, "minimal");
    expect(state.discountQty).toBe(2);
    expect(state.fullQty).toBe(38);
    expect(lossQty(state)).toBe(0);
  });

  it("não mexeu em nada: o padrão vira a fornada inteira, e o preço cheio cede", () => {
    let state = initialState(40, "standard");
    state = applyDiscountGrade(state, "minimal");
    expect(state.discountQty).toBe(40);
    expect(state.fullQty).toBe(0);
    expect(lossQty(state)).toBe(0);
  });

  it("38 boas, 2 se perderam: a perda é derivada, nunca digitada", () => {
    let state = initialState(40, "standard");
    state = { ...state, fullQty: 38, fullTouched: true };
    expect(lossQty(state)).toBe(2);
  });

  it("fora do plano não há previsto, logo não há perda derivável", () => {
    const state = initialState(null, "standard");
    expect(lossQty(state)).toBe(0);
    expect(discountDefault(state)).toBe(0);
  });
});

describe("Confirmar sempre ativo: as perguntas que faltam", () => {
  it("fornada limpa não pergunta nada", () => {
    const state = initialState(40, "standard");
    expect(pendingQuestions(state)).toEqual([]);
  });

  it("perda sem motivo pergunta primeiro; sublote sem motivo em seguida", () => {
    let state = initialState(40, "standard");
    state = { ...state, fullQty: 30, fullTouched: true };
    state = applyDiscountGrade(state, "fair");
    state = { ...state, discountQty: 8 };
    expect(pendingQuestions(state)).toEqual(["loss_reason", "discount_reason"]);

    state = { ...state, lossDefectRef: "overbaked" };
    expect(pendingQuestions(state)).toEqual(["discount_reason"]);
    state = { ...state, discountDefectRef: "misshapen" };
    expect(pendingQuestions(state)).toEqual([]);
  });

  it("fornada sem grupo vendável não fecha (é void/waste, não conclusão)", () => {
    let state = initialState(40, "standard");
    state = { ...state, fullQty: 0, fullTouched: true };
    expect(canSubmit(state)).toBe(false);
  });

  it("acima do previsto pede confirmação ANTES de qualquer motivo", () => {
    let state = initialState(22, "standard");
    state = { ...state, fullQty: 222, fullTouched: true };
    expect(pendingQuestions(state)).toEqual(["overshoot"]);

    state = { ...state, overshootConfirmed: true };
    expect(pendingQuestions(state)).toEqual([]);
  });

  it("fornada avulsa não tem previsto, logo não há acima-do-previsto", () => {
    let state = initialState(null, "standard");
    state = { ...state, fullQty: 999, fullTouched: true };
    expect(pendingQuestions(state)).toEqual([]);
  });
});

describe("o payload da partição (contrato do finish)", () => {
  it("32 + 5 na mínima + 3 de perda: três grupos disjuntos", () => {
    let state = initialState(40, "standard");
    state = { ...state, fullQty: 32, fullTouched: true };
    state = applyDiscountGrade(state, "minimal");
    state = {
      ...state,
      discountQty: 5,
      discountDefectRef: "overbaked",
      lossDefectRef: "underproofed",
    };
    expect(buildPartition(state)).toEqual([
      { quantity: "32", quality_grade_ref: "standard" },
      { quantity: "5", quality_grade_ref: "minimal", quality_defect_ref: "overbaked" },
      { quantity: "3", quality_defect_ref: "underproofed", loss: true },
    ]);
    expect(finishedTotal(state)).toBe(37);
  });

  it("grupo zerado não entra no payload", () => {
    const state = initialState(40, "excellent");
    expect(buildPartition({ ...state, fullGradeRef: "excellent" })).toEqual([
      { quantity: "40", quality_grade_ref: "excellent" },
    ]);
  });
});

describe("entrada tipo calculadora", () => {
  it("primeiro dígito sobre valor pré-preenchido substitui", () => {
    expect(typeDigit(40, "3", true)).toBe(3);
    expect(typeDigit(3, "8", false)).toBe(38);
  });

  it("backspace apaga um dígito; o último vira zero", () => {
    expect(typeBackspace(38)).toBe(3);
    expect(typeBackspace(3)).toBe(0);
  });
});

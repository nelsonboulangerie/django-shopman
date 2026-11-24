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
  reportedTotal,
  backspaceQuantityText,
  formatQcQuantity,
  isCountUnit,
  parseQuantityText,
  quantityDecimals,
  quantityText,
  roundQuantity,
  typeQuantityKey,
  yieldReasons,
} from "../app/presentation/qc";
import type { QCGradeProjection } from "../app/types/production";

const GRADES: QCGradeProjection[] = [
  {
    ref: "excellent",
    label: "Ótima",
    rank: 40,
    markdown_percent: 0,
    is_default: false,
  },
  {
    ref: "standard",
    label: "Normal",
    rank: 30,
    markdown_percent: 0,
    is_default: true,
  },
  {
    ref: "fair",
    label: "Razoável",
    rank: 20,
    markdown_percent: 20,
    is_default: false,
  },
  {
    ref: "minimal",
    label: "Mínima",
    rank: 10,
    markdown_percent: 50,
    is_default: false,
  },
];

describe("a escala", () => {
  it("separa os graus por identidade, mesmo se o markdown mudar", () => {
    const gradesWithZeroFairMarkdown = GRADES.map((grade) =>
      grade.ref === "fair" ? { ...grade, markdown_percent: 0 } : grade,
    );
    expect(fullPriceGrades(gradesWithZeroFairMarkdown).map((g) => g.ref)).toEqual([
      "excellent",
      "standard",
    ]);
    expect(discountGrades(gradesWithZeroFairMarkdown).map((g) => g.ref)).toEqual([
      "fair",
      "minimal",
    ]);
  });

  it("o padrão vem do catálogo", () => {
    expect(defaultGradeRef(GRADES)).toBe("standard");
  });

  it("a faixa de cor deriva da identidade/rank, nunca do preço ou rótulo", () => {
    expect(gradeBandClass(GRADES[0]!, GRADES)).toBe("bg-emerald-500");
    expect(gradeBandClass(GRADES[1]!, GRADES)).toBe("bg-zinc-400");
    expect(gradeBandClass(GRADES[2]!, GRADES)).toBe("bg-amber-500");
    expect(gradeBandClass(GRADES[3]!, GRADES)).toBe("bg-orange-600");
  });
});

describe("a âncora da finalização (o que entrou no forno É o previsto daqui)", () => {
  it("sem started, o planejado ancora sozinho", () => {
    expect(ovenAnchor(10, null)).toEqual({ anchor: 10 });
  });

  it("com started, é ele o previsto — o plano não aparece mais", () => {
    // Planejou 10, enfornou 11: fechar ancorado em 10 gravaria 1 de perda
    // que nunca existiu. E o 10 não vira referência na tela: o que entrou
    // no forno é o que se espera que saia dele.
    expect(ovenAnchor(10, 11)).toEqual({ anchor: 11 });
  });

  it("started igual ao planejado dá no mesmo número", () => {
    expect(ovenAnchor(10, 10)).toEqual({ anchor: 10 });
  });

  it("lote avulso: sem previsto e sem started, sem âncora", () => {
    expect(ovenAnchor(null, null)).toEqual({ anchor: null });
  });

  it("started sem plano (avulsa iniciada) ancora sozinho", () => {
    expect(ovenAnchor(null, 12)).toEqual({ anchor: 12 });
  });
});

describe("a aritmética subtrativa do lote (§4 da nota de QC)", () => {
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

  it("não mexeu em nada: o padrão vira o lote inteiro, e o preço cheio cede", () => {
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
  it("lote limpo não pergunta nada", () => {
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

  it("perda total fecha como conclusão auditável", () => {
    let state = initialState(40, "standard");
    state = { ...state, fullQty: 0, fullTouched: true };
    expect(canSubmit(state)).toBe(true);
  });

  it("acima do previsto pede confirmação ANTES de qualquer motivo", () => {
    let state = initialState(22, "standard");
    state = { ...state, fullQty: 222, fullTouched: true };
    expect(pendingQuestions(state)).toEqual(["overshoot"]);

    state = {
      ...state,
      overshootConfirmed: true,
      overshootReason: "Contagem conferida",
    };
    expect(pendingQuestions(state)).toEqual([]);
  });

  it("lote avulso não tem previsto, logo não há acima-do-previsto", () => {
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
      {
        quantity: "5",
        quality_grade_ref: "minimal",
        quality_defect_ref: "overbaked",
      },
      { quantity: "3", quality_defect_ref: "underproofed", loss: true },
    ]);
    expect(finishedTotal(state)).toBe(37);
    expect(reportedTotal(state)).toBe(40);
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
    expect(typeQuantityKey("40", "3", true, 0)).toEqual({ ok: true, text: "3" });
    expect(typeQuantityKey("3", "8", false, 0)).toEqual({ ok: true, text: "38" });
    expect(typeQuantityKey("0", "5", false, 0)).toEqual({ ok: true, text: "5" });
  });

  it("backspace apaga um caractere; o último vira zero", () => {
    expect(backspaceQuantityText("38")).toBe("3");
    expect(backspaceQuantityText("3")).toBe("0");
    expect(backspaceQuantityText("2,5")).toBe("2,");
  });

  it("o teto não corta calado: devolve o motivo para a tela dizer", () => {
    expect(typeQuantityKey("999", "9", false, 0)).toEqual({ ok: true, text: "9999" });
    expect(typeQuantityKey("9999", "1", false, 0)).toEqual({ ok: false, reason: "max" });
  });
});

describe("a unidade do lote (P1-22)", () => {
  it("peça é inteira; peso aceita vírgula", () => {
    expect(isCountUnit("un")).toBe(true);
    expect(isCountUnit("")).toBe(true);
    expect(isCountUnit("kg")).toBe(false);
    expect(quantityDecimals("un")).toBe(0);
    expect(quantityDecimals("kg")).toBe(3);
  });

  it("digita 2,35 kg com vírgula, uma vez só e até três casas", () => {
    let text = "0";
    for (const key of ["2", ",", "3", "5"]) {
      const result = typeQuantityKey(text, key, text === "0", 3);
      expect(result.ok).toBe(true);
      if (result.ok) text = result.text;
    }
    expect(text).toBe("2,35");
    expect(parseQuantityText(text)).toBe(2.35);
    expect(typeQuantityKey("2,35", ",", false, 3)).toEqual({ ok: true, text: "2,35" });
    expect(typeQuantityKey("2,355", "1", false, 3)).toEqual({ ok: false, reason: "decimals" });
    expect(typeQuantityKey("0", ",", true, 3)).toEqual({ ok: true, text: "0," });
  });

  it("vírgula em lote de peça é recusada", () => {
    expect(typeQuantityKey("3", ",", false, 0)).toEqual({ ok: false, reason: "no_decimal" });
  });

  it("escreve a quantidade com a unidade, sem converter a escala", () => {
    expect(formatQcQuantity(26, "un")).toBe("26 un.");
    expect(formatQcQuantity(2.5, "kg")).toBe("2,5 kg");
    expect(formatQcQuantity(1230.77, "g")).toBe("1.230,77 g");
    expect(quantityText(2.5)).toBe("2,5");
    expect(roundQuantity(0.1 + 0.2)).toBe(0.3);
  });
});

describe("motivos de rendeu menos e rendeu mais (P1-07)", () => {
  it("cada lista diz uma causa, sem repetir e sem o Outro (que é da tela)", () => {
    for (const kind of ["shortfall", "overshoot"] as const) {
      for (const unit of ["un", "kg"]) {
        const list = yieldReasons(kind, unit);
        expect(list.length).toBe(3);
        expect(new Set(list).size).toBe(list.length);
        expect(list).not.toContain("Outro");
        // A causa nunca repete a pergunta ("rendeu menos/mais"), e não se chama
        // "perda": a folha já diz que a diferença é perda; o motivo diz a causa.
        for (const reason of list) expect(reason).not.toMatch(/rendeu|^perda/i);
      }
    }
  });

  it("lote pesado não fala em peça", () => {
    for (const kind of ["shortfall", "overshoot"] as const) {
      for (const reason of yieldReasons(kind, "kg")) {
        expect(reason).not.toMatch(/peça/i);
      }
    }
    expect(yieldReasons("shortfall", "un")).toContain("Peças maiores que o padrão");
    expect(yieldReasons("overshoot", "un")).toContain("Peças menores que o padrão");
  });
});

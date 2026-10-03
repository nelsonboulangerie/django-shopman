import { describe, expect, it } from "vitest";

import {
  fittingAlternative,
  shortageLine,
  suggestionBasisLine,
  suggestionHistory,
  suggestionMath,
  suggestionSignal,
} from "~/presentation/planningReason";
import type { ProductionSuggestionProjection } from "~/types/production";

// 2026-10-03 é sábado.
const SATURDAY = "2026-10-03";

function suggestion(
  over: Partial<ProductionSuggestionProjection> = {},
): ProductionSuggestionProjection {
  return {
    recipe_pk: 1,
    recipe_ref: "croissant",
    recipe_name: "Croissant",
    base_usages: [],
    output_sku: "CRO",
    quantity: "52",
    committed: "6",
    avg_demand: "44.0",
    confidence: "Média",
    sample_size: 4,
    high_demand_applied: false,
    projected: "44",
    margin: "2",
    safety_percent: 4,
    same_weekday: true,
    season_label: "",
    soldout_days: 0,
    waste_percent: 0,
    waste_discounted: false,
    material_shortages: [],
    fits_quantity: "",
    ...over,
  };
}

const butter = {
  sku: "MANTEIGA",
  name: "Manteiga",
  missing_display: "1200 g",
  fits_quantity: "40",
};

describe("suggestionSignal: um sinal só, com prioridade", () => {
  it("linha sem nada a notar não tem sinal", () => {
    expect(suggestionSignal(suggestion())).toBeNull();
    expect(suggestionSignal(null)).toBeNull();
  });

  it("falta insumo vence acabou cedo e sobra", () => {
    const signal = suggestionSignal(
      suggestion({
        material_shortages: [butter],
        soldout_days: 3,
        waste_discounted: true,
        waste_percent: 20,
      }),
    );
    expect(signal?.kind).toBe("material");
    expect(signal?.label).toBe("falta insumo");
    expect(signal?.icon).toBe("lucide:lock");
  });

  it("acabou cedo vence sobra, e é vermelho", () => {
    const signal = suggestionSignal(
      suggestion({
        soldout_days: 2,
        waste_discounted: true,
        waste_percent: 20,
      }),
    );
    expect(signal).toMatchObject({ kind: "soldout", tone: "danger" });
  });

  it("acabou cedo só quando esgotou em metade ou mais dos dias", () => {
    expect(suggestionSignal(suggestion({ soldout_days: 1 }))).toBeNull();
    expect(suggestionSignal(suggestion({ soldout_days: 2 }))?.kind).toBe(
      "soldout",
    );
  });

  it("sobra só quando passou do teto que a fórmula desconta", () => {
    expect(
      suggestionSignal(
        suggestion({ waste_percent: 8, waste_discounted: false }),
      ),
    ).toBeNull();
    expect(
      suggestionSignal(
        suggestion({ waste_percent: 18, waste_discounted: true }),
      ),
    ).toMatchObject({ kind: "leftover", label: "sobra", tone: "warning" });
  });
});

describe("suggestionMath: projeção + encomendas + margem = sugestão", () => {
  it("usa a média dos mesmos dias da semana quando a conta olha só eles", () => {
    const math = suggestionMath(suggestion(), SATURDAY);
    expect(math.terms).toEqual([
      { value: "44", label: "média dos sábados" },
      { value: "6", label: "encomendas" },
      { value: "2", label: "margem" },
    ]);
    expect(math.total).toEqual({ value: "52", label: "sugestão" });
    expect(math.marginNote).toBe("segurança 4%");
  });

  it("sem encomenda, a encomenda sai da conta; sem recorte, é média de venda", () => {
    const math = suggestionMath(
      suggestion({ committed: "0", same_weekday: false, margin: "8" }),
      SATURDAY,
    );
    expect(math.terms.map((t) => t.label)).toEqual([
      "média de venda",
      "margem",
    ]);
  });

  it("o reforço do dia aparece na nota da margem", () => {
    const math = suggestionMath(
      suggestion({ high_demand_applied: true, safety_percent: 10 }),
      SATURDAY,
    );
    expect(math.marginNote).toBe("segurança 10% + reforço de sábado");
  });
});

describe("suggestionHistory: o que a média sozinha não conta", () => {
  it("sem esgotamento, sobra ou estação, não há linha", () => {
    expect(suggestionHistory(suggestion(), SATURDAY)).toEqual([]);
  });

  it("esgotamento, sobra descontada e estação", () => {
    const lines = suggestionHistory(
      suggestion({
        soldout_days: 3,
        waste_percent: 18,
        waste_discounted: true,
        season_label: "estação quente",
      }),
      SATURDAY,
    );
    expect(lines.map((line) => line.text)).toEqual([
      "Acabou antes de fechar em 3 dos 4 sábados usados na conta",
      "Sobrou 18% do que vendeu",
      "Histórico só da estação quente",
    ]);
    expect(lines[1]!.note).toBe("a média já desconta essa sobra");
  });

  it("sobra abaixo do teto aparece sem dizer que foi descontada", () => {
    const [line] = suggestionHistory(
      suggestion({ waste_percent: 8 }),
      SATURDAY,
    );
    expect(line!.note).toBe("");
  });

  it("subtítulo com a confiança e a amostra", () => {
    expect(suggestionBasisLine(suggestion(), SATURDAY)).toBe(
      "confiança média · 4 sábados de histórico",
    );
    expect(
      suggestionBasisLine(
        suggestion({ sample_size: 1, same_weekday: false }),
        SATURDAY,
      ),
    ).toBe("confiança média · 1 dia de histórico");
  });
});

describe("falta de insumo e a alternativa que cabe", () => {
  it("diz para quanto o insumo dá e quanto falta", () => {
    expect(shortageLine(butter)).toBe("Manteiga: dá para 40; faltam 1200 g");
  });

  it("a alternativa é o que cabe, quando é maior que zero e menor que a sugestão", () => {
    expect(
      fittingAlternative(
        suggestion({ material_shortages: [butter], fits_quantity: "40" }),
      ),
    ).toBe("40");
    expect(
      fittingAlternative(
        suggestion({ material_shortages: [butter], fits_quantity: "0" }),
      ),
    ).toBeNull();
    expect(fittingAlternative(suggestion({ fits_quantity: "40" }))).toBeNull();
  });
});

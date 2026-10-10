import { describe, expect, it } from "vitest";

import {
  MATERIAL_ATTENTION_TONES,
  isAttentionRecorte,
  materialDimensions,
  matchesMaterialFilters,
} from "../app/presentation/purchaseUi";

// Base · Insumos no painel de filtros da suíte (fase 2): Situação e Categoria, com a
// contagem; o filtro rápido "Pedem atenção" é a Situação em Comprar ou Revisar.
const MATERIALS = [
  { tone: "urgent" as const, category: "Farinhas" },
  { tone: "watch" as const, category: "Laticínios" },
  { tone: "ok" as const, category: "Farinhas" },
  { tone: "ok" as const, category: "" },
];

describe("recortes de Base · Insumos", () => {
  it("dão Situação na ordem do que pede compra e Categoria em ordem alfabética, com contagem", () => {
    const [tone, category] = materialDimensions(MATERIALS);
    expect(tone!.options).toEqual([
      { value: "urgent", label: "Comprar", count: 1 },
      { value: "watch", label: "Revisar", count: 1 },
      { value: "ok", label: "Em ordem", count: 2 },
    ]);
    expect(category!.options).toEqual([
      { value: "Farinhas", label: "Farinhas", count: 2 },
      { value: "Laticínios", label: "Laticínios", count: 1 },
    ]);
    expect(MATERIAL_ATTENTION_TONES).toEqual(["urgent", "watch"]);
  });

  it("reconhecem o \"Pedem atenção\" só quando são as duas situações, e só elas", () => {
    expect(isAttentionRecorte({ tone: ["watch", "urgent"] })).toBe(true);
    expect(isAttentionRecorte({ tone: ["urgent"] })).toBe(false);
    expect(isAttentionRecorte({ tone: ["urgent", "watch", "ok"] })).toBe(false);
    expect(isAttentionRecorte({})).toBe(false);
  });

  it("somam dentro da dimensão e cruzam entre dimensões", () => {
    const attention = { tone: ["urgent", "watch"] };
    expect(MATERIALS.filter((material) => matchesMaterialFilters(material, attention))).toHaveLength(2);
    expect(
      MATERIALS.filter((material) => matchesMaterialFilters(material, { ...attention, category: ["Farinhas"] })),
    ).toEqual([{ tone: "urgent", category: "Farinhas" }]);
    expect(MATERIALS.filter((material) => matchesMaterialFilters(material, {}))).toHaveLength(4);
  });
});

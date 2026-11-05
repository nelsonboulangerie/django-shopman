import { describe, expect, it } from "vitest";

import {
  MATERIAL_PANEL_QUICK,
  SUPPLIER_PANEL_QUICK,
  materialDimensions,
  matchesMaterialFilters,
} from "../app/presentation/purchaseUi";

// Base · Insumos no painel de filtros da suíte (fase 2): Situação e Categoria, com a
// contagem; os filtros rápidos do próprio painel são a Situação em Comprar e em Revisar.
const MATERIALS = [
  { tone: "urgent" as const, category: "Farinhas" },
  { tone: "watch" as const, category: "Laticínios" },
  { tone: "ok" as const, category: "Farinhas" },
  { tone: "ok" as const, category: "" },
];

describe("recortes de Base · Insumos", () => {
  it("dão Situação na ordem do que pede compra e Categoria em ordem alfabética, com contagem", () => {
    const [archive, tone, category] = materialDimensions(MATERIALS);
    expect(archive).toEqual({
      id: "archive",
      label: "Cadastro",
      type: "single-select",
      options: [{ value: "archived", label: "Arquivados" }],
    });
    expect(tone!.options).toEqual([
      { value: "urgent", label: "Comprar", count: 1 },
      { value: "watch", label: "Revisar", count: 1 },
      { value: "ok", label: "Em ordem", count: 2 },
    ]);
    expect(category!.options).toEqual([
      { value: "Farinhas", label: "Farinhas", count: 2 },
      { value: "Laticínios", label: "Laticínios", count: 1 },
    ]);
  });

  it("os filtros rápidos moram no painel (filtro único da suíte): Comprar, Revisar e Sem contato comercial", () => {
    expect(MATERIAL_PANEL_QUICK).toEqual([
      { dimension: "tone", value: "urgent", label: "Comprar" },
      { dimension: "tone", value: "watch", label: "Revisar" },
    ]);
    expect(SUPPLIER_PANEL_QUICK).toEqual([{ dimension: "contact", value: "without", label: "Sem contato comercial" }]);
  });

  it("somam dentro da dimensão e cruzam entre dimensões", () => {
    const attention = { tone: ["urgent", "watch"] };
    expect(MATERIALS.filter((material) => matchesMaterialFilters(material, attention))).toHaveLength(2);
    expect(
      MATERIALS.filter((material) => matchesMaterialFilters(material, { ...attention, category: ["Farinhas"] })),
    ).toEqual([{ tone: "urgent", category: "Farinhas" }]);
    expect(MATERIALS.filter((material) => matchesMaterialFilters(material, {}))).toHaveLength(4);
  });

  it("mostra arquivados somente quando o filtro explícito está ligado", () => {
    const archived = { tone: "ok" as const, category: "Farinhas", isActive: false };
    expect(matchesMaterialFilters(archived, {})).toBe(false);
    expect(matchesMaterialFilters(archived, { archive: ["archived"] })).toBe(true);
    expect(matchesMaterialFilters({ ...archived, isActive: true }, { archive: ["archived"] })).toBe(false);
  });
});

import { describe, expect, it } from "vitest";

import { BI_SECTIONS, biSections } from "~/presentation/biSections";
import {
  quickBarLayout,
  quickBarProblems,
  withSectionShortcuts,
} from "../../operator-kit/app/presentation/suiteChrome";

// O modelo de navegação (dono, 31/10/2026; implementar autorizado em 02/11): cada seção
// declara a forma da tela. No B.I. o chão é a olhada do dia pelo celular, e é ela que vai
// para a barra de baixo ("as seções principais vão para a barra de baixo, em TODOS os
// apps", 03/11/2026).
describe("seções do B.I. no modelo de navegação", () => {
  it("a ordem de sempre, com Alt+1 a Alt+9 por posição (a forma não renumera tecla)", () => {
    expect(withSectionShortcuts(biSections("")).map((s) => [s.key, s.shortcut])).toEqual([
      ["production", "Alt+1"],
      ["sales", "Alt+2"],
      ["cash", "Alt+3"],
      ["customers", "Alt+4"],
      ["delivery", "Alt+5"],
      ["profiles", "Alt+6"],
      ["explore", "Alt+7"],
      ["forecast", "Alt+8"],
      ["scenarios", "Alt+9"],
    ]);
  });

  it("forma de cada seção: a olhada do dia é do chão, a leitura de tendência é do escritório", () => {
    expect(BI_SECTIONS.map((s) => [s.key, s.form, Boolean(s.quick)])).toEqual([
      ["production", "floor", true],
      ["sales", "floor", true],
      ["cash", "floor", true],
      ["customers", "office", false],
      ["delivery", "office", false],
      ["profiles", "office", false],
      ["explore", "office", false],
      ["forecast", "floor", true],
      ["scenarios", "office", false],
    ]);
  });

  it("a barra de baixo do chão: as quatro, sem Mais, dentro da regra do kit", () => {
    const floor = biSections("period=week").filter((s) => s.form === "floor");
    expect(quickBarProblems(floor)).toEqual([]);
    const layout = quickBarLayout(floor);
    expect(layout.items.map((s) => s.key)).toEqual(["production", "sales", "cash", "forecast"]);
    expect(layout.more).toBe(false);
  });

  it("a forma e a barra sobrevivem à janela de análise na query", () => {
    const sections = biSections("period=28d");
    expect(sections.map((s) => s.form)).toEqual(BI_SECTIONS.map((s) => s.form));
    expect(sections.find((s) => s.key === "forecast")?.to).toBe("/forecast?period=28d");
  });

  it("nenhum nome de forma aparece ao operador", () => {
    const forbidden = /ch[ãa]o|escrit[óo]rio|parede|no posto|na parede/i;
    for (const section of BI_SECTIONS) {
      expect(section.label).not.toMatch(forbidden);
      expect(section.shortLabel ?? "").not.toMatch(forbidden);
    }
  });
});

import { describe, expect, it } from "vitest";

import {
  BENCH_CUTS,
  productionSections,
} from "../../app/presentation/productionSections";
import { activeSectionKey } from "../../../operator-kit/app/presentation/appBar";
import { withSectionShortcuts } from "../../../operator-kit/app/presentation/suiteChrome";

// Modelo de navegação (dono, 31/10/2026): os lugares agrupados pela forma da tela, e as
// etapas do mesmo trabalho viram recorte na Bancada.
describe("seções da Produção", () => {
  it("a bancada primeiro, depois o escritório e o Letreiro, cada um com a forma", () => {
    const sections = productionSections({ canViewRecipes: true, canViewReports: true });
    expect(sections.map((s) => [s.key, s.form])).toEqual([
      ["bench", "floor"],
      ["timers", "floor"],
      ["quality", "floor"],
      ["plan", "office"],
      ["recipes", "office"],
      ["reports", "office"],
      ["board", "wall"],
    ]);
    expect(sections.some((section) => section.foot)).toBe(false);
    expect(sections.find((s) => s.key === "plan")?.divider).toBe(true);
  });

  it("Alt+1 a Alt+7 seguem a ordem da lista", () => {
    const shortcuts = withSectionShortcuts(
      productionSections({ canViewRecipes: true, canViewReports: true }),
    ).map((s) => [s.key, s.shortcut]);
    expect(shortcuts.slice(0, 4)).toEqual([
      ["bench", "Alt+1"],
      ["timers", "Alt+2"],
      ["quality", "Alt+3"],
      ["plan", "Alt+4"],
    ]);
  });

  it("Preparo, Produção e Finalização são recortes da Bancada, cada um com o seu endereço", () => {
    expect(BENCH_CUTS.map((cut) => [cut.label, cut.to])).toEqual([
      ["Preparo", "/mise-en-place"],
      ["Produção", "/"],
      ["Finalização", "/close"],
    ]);
    const sections = productionSections({});
    for (const path of ["/", "/mise-en-place", "/close/"]) {
      expect(activeSectionKey(path, sections)).toBe("bench");
    }
  });

  it("Receitas e Relatórios só para quem tem acesso", () => {
    const keys = productionSections({}).map((s) => s.key);
    expect(keys).not.toContain("recipes");
    expect(keys).not.toContain("reports");
    expect(keys).toContain("plan");
  });

  it("o selo de Timers conta os ativos e o ponto avisa quando um toca", () => {
    const idle = productionSections({}).find((s) => s.key === "timers")!;
    expect(idle.badge).toBeUndefined();
    expect(idle.attention).toBeUndefined();

    const busy = productionSections({ timersActive: 3, timersRinging: 1 }).find(
      (s) => s.key === "timers",
    )!;
    expect(busy.badge).toBe("3");
    expect(busy.attention).toBe("1 tocando");
  });

  it("a Qualidade ganha o selo dos lotes para confirmar, e só quando há", () => {
    expect(
      productionSections({ qualityPending: 0 }).find((s) => s.key === "quality")!
        .badge,
    ).toBeUndefined();
    const quality = productionSections({ qualityPending: 8 }).find(
      (s) => s.key === "quality",
    )!;
    expect(quality.badge).toBe("8");
  });

  it("a rota acende a seção direta correspondente", () => {
    const sections = productionSections({ canViewRecipes: true });
    expect(activeSectionKey("/plan", sections)).toBe("plan");
    expect(activeSectionKey("/recipes/PAO/edit", sections)).toBe("recipes");
    expect(activeSectionKey("/timers/", sections)).toBe("timers");
    expect(activeSectionKey("/board", sections)).toBe("board");
  });
});

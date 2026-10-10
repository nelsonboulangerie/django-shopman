import { describe, expect, it } from "vitest";

import {
  productionSections,
  stageSections,
} from "../../app/presentation/productionSections";
import { activeSectionKey } from "../../../operator-kit/app/presentation/appBar";
import { quickBarLayout, quickBarProblems } from "../../../operator-kit/app/presentation/suiteChrome";

// V4-PROD: as etapas do lote moram no rail da suíte (e na barra do polegar no
// celular). Era a fileira de abas do cabeçalho; o contrato (ordem, rótulo, rota,
// tecla) continua o mesmo, decidido no #1433.
describe("seções da Produção no rail", () => {
  it("o ciclo do lote, de Planejamento a Qualidade, com Alt+1 a Alt+5", () => {
    const stages = stageSections().map((section) => [
      section.to,
      section.label,
      section.shortcut,
    ]);
    expect(stages).toEqual([
      ["/plan", "Planejamento", "Alt+1"],
      ["/mise-en-place", "Preparação", "Alt+2"],
      ["/", "Abertura", "Alt+3"],
      ["/close", "Fechamento", "Alt+4"],
      ["/quality", "Qualidade", "Alt+5"],
    ]);
  });

  it("barra inferior do shell: as quatro primeiras etapas e o Mais, que abre a gaveta", () => {
    const sections = productionSections({ canViewRecipes: true, timersActive: 1 });
    expect(quickBarProblems(sections)).toEqual([]);
    const layout = quickBarLayout(sections);
    expect(layout.items.map((s) => s.key)).toEqual(["plan", "mise-en-place", "open", "close"]);
    expect(layout.more).toBe(true);
  });

  it("depois do ciclo, um traço, Timers e Ajustes (v4 plano-porque, R02); nada no pé", () => {
    const sections = productionSections({ canViewRecipes: true, canViewReports: true });
    expect(sections.map((section) => section.key)).toEqual(["plan", "mise-en-place", "open", "close", "quality", "timers", "settings"]);
    expect(sections.some((section) => section.foot)).toBe(false);
    expect(sections.find((s) => s.key === "timers")?.divider).toBe(true);
    // Receitas, Relatórios e o Letreiro moram em Ajustes: a seção acende lá.
    expect(activeSectionKey("/recipes/abc", sections)).toBe("settings");
    expect(activeSectionKey("/board", sections)).toBe("settings");
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

  it("a rota acende a seção certa; Receitas acende Ajustes, onde ela mora", () => {
    const sections = productionSections({ canViewRecipes: true });
    expect(activeSectionKey("/", sections)).toBe("open");
    expect(activeSectionKey("/close", sections)).toBe("close");
    expect(activeSectionKey("/recipes/PAO/edit", sections)).toBe("settings");
    expect(activeSectionKey("/timers/", sections)).toBe("timers");
  });
});

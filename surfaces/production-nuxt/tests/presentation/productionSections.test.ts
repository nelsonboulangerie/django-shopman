import { describe, expect, it } from "vitest";

import {
  phoneSections,
  productionSections,
} from "../../app/presentation/productionSections";
import { activeSectionKey } from "../../../operator-kit/app/presentation/appBar";

// V4-PROD: as etapas do lote moram no rail da suíte (e na barra do polegar no
// celular). Era a fileira de abas do cabeçalho; o contrato (ordem, rótulo, rota,
// tecla) continua o mesmo, decidido no #1433.
describe("seções da Produção no rail", () => {
  it("o ciclo do lote, de Planejamento a Qualidade, com Alt+1 a Alt+5", () => {
    const stages = phoneSections().map((section) => [
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

  it("Timers logo abaixo do ciclo; no pé, só as ferramentas que o operador pode abrir", () => {
    const keys = (input: Parameters<typeof productionSections>[0]) =>
      productionSections(input).map((section) => [section.key, !!section.foot]);

    expect(keys({})).toEqual([
      ["plan", false],
      ["mise-en-place", false],
      ["open", false],
      ["close", false],
      ["quality", false],
      ["timers", false],
      ["board", true],
    ]);
    expect(
      keys({ canViewRecipes: true, canViewReports: true }).slice(-3),
    ).toEqual([
      ["recipes", true],
      ["reports", true],
      ["board", true],
    ]);
  });

  it("o selo de Timers conta os ativos e o ponto avisa quando um toca", () => {
    const idle = productionSections({}).find((s) => s.key === "timers")!;
    expect(idle.badge).toBeUndefined();
    expect(idle.attention).toBeUndefined();

    const busy = productionSections({ timersActive: 3, timersRinging: 1 }).find(
      (s) => s.key === "timers",
    )!;
    expect(busy.badge).toBe("3");
    expect(busy.badgeLabel).toBe("3 timers ativos");
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
    expect(quality.badgeLabel).toBe("8 lotes para confirmar");
  });

  it("a rota acende a seção certa, inclusive dentro de Receitas", () => {
    const sections = productionSections({ canViewRecipes: true });
    expect(activeSectionKey("/", sections)).toBe("open");
    expect(activeSectionKey("/close", sections)).toBe("close");
    expect(activeSectionKey("/recipes/PAO/edit", sections)).toBe("recipes");
    expect(activeSectionKey("/timers/", sections)).toBe("timers");
  });
});

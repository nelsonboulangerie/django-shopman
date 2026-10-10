import { describe, expect, it } from "vitest";

import { activeSectionKey } from "../../operator-kit/app/presentation/appBar";
import { quickBarProblems } from "../../operator-kit/app/presentation/suiteChrome";
import { baseSectionOf, baseSectionPath, purchaseSections } from "../app/presentation/purchaseSections";

describe("seções do Compras no shell da suíte", () => {
  const sections = purchaseSections({ urgentMaterials: 2, receivePending: 3 });

  it("quatro seções com rota, todas na barra inferior, sem Mais", () => {
    expect(sections.map((section) => [section.key, section.to])).toEqual([
      ["panel", "/"],
      ["buy", "/buy"],
      ["receive", "/receive"],
      ["base", "/base/materials"],
    ]);
    expect(sections.every((section) => section.quick)).toBe(true);
    expect(quickBarProblems(sections)).toEqual([]);
  });

  it("a rota acende a seção, inclusive o registro aberto da Base", () => {
    expect(activeSectionKey("/", sections)).toBe("panel");
    expect(activeSectionKey("/receive", sections)).toBe("receive");
    expect(activeSectionKey("/base/suppliers/MOINHO", sections)).toBe("base");
    expect(activeSectionKey("/base/count", sections)).toBe("base");
  });

  it("sinais: ponto em Comprar, número em Receber; zero não é sinal", () => {
    expect(sections[1]?.attention).toBe("2 reposições urgentes");
    expect(sections[2]?.badge).toBe("3");
    const calm = purchaseSections({ urgentMaterials: 0, receivePending: 0 });
    expect(calm[1]?.attention).toBeUndefined();
    expect(calm[2]?.badge).toBeUndefined();
  });

  it("sub-seção da Base pela rota, e a rota de cada sub-seção", () => {
    expect(baseSectionOf("/base/costs")).toBe("costs");
    expect(baseSectionOf("/base/materials/FAR-T65")).toBe("materials");
    expect(baseSectionOf("/buy")).toBeNull();
    expect(baseSectionPath("count")).toBe("/base/count");
  });
});

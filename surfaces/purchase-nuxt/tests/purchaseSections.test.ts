import { describe, expect, it } from "vitest";

import { activeSectionKey } from "../../operator-kit/app/presentation/appBar";
import { quickBarProblems } from "../../operator-kit/app/presentation/suiteChrome";
import {
  COUNT_PATH,
  PURCHASE_BASE_RECORD_SECTIONS,
  PURCHASE_BASE_SECTIONS,
  baseSectionOf,
  baseSectionPath,
  purchaseSections,
} from "../app/presentation/purchaseSections";

describe("seções do Compras no shell da suíte", () => {
  const sections = purchaseSections({ urgentMaterials: 2, receivePending: 3 });

  it("cinco seções com rota, na ordem de antes, e Contar estoque no fim", () => {
    expect(sections.map((section) => [section.key, section.to])).toEqual([
      ["panel", "/"],
      ["buy", "/buy"],
      ["receive", "/receive"],
      ["base", "/base/materials"],
      ["count", COUNT_PATH],
    ]);
    expect(COUNT_PATH).toBe("/count");
  });

  it("as teclas Alt+1 a Alt+4 não mudam de lugar; Contar estoque é Alt+5", () => {
    expect(sections.map((section) => [section.label, section.shortcut])).toEqual([
      ["Painel", "Alt+1"],
      ["Comprar", "Alt+2"],
      ["Receber", "Alt+3"],
      ["Base", "Alt+4"],
      ["Contar estoque", "Alt+5"],
    ]);
  });

  it("chão: Painel, Comprar, Receber e Contar estoque, a barra de baixo; a Base é escritório", () => {
    expect(sections.map((section) => [section.key, section.form, Boolean(section.quick)])).toEqual([
      ["panel", "floor", true],
      ["buy", "floor", true],
      ["receive", "floor", true],
      ["base", "office", false],
      ["count", "floor", true],
    ]);
    const floor = sections.filter((section) => section.form === "floor");
    expect(quickBarProblems(floor)).toEqual([]);
    expect(quickBarProblems(sections)).toEqual([]);
  });

  it("nenhum nome de forma vira palavra na tela", () => {
    const words = sections.flatMap((section) => [section.label, section.shortLabel ?? "", section.attention ?? ""]);
    for (const word of words) {
      expect(word).not.toMatch(/chão|escritório|parede|no posto|na parede/i);
    }
  });

  it("a rota acende a seção, inclusive o registro aberto da Base e a contagem", () => {
    expect(activeSectionKey("/", sections)).toBe("panel");
    expect(activeSectionKey("/receive", sections)).toBe("receive");
    expect(activeSectionKey("/base/suppliers/MOINHO", sections)).toBe("base");
    expect(activeSectionKey("/count", sections)).toBe("count");
  });

  it("sinais: ponto em Comprar, número em Receber; zero não é sinal", () => {
    expect(sections[1]?.attention).toBe("2 reposições urgentes");
    expect(sections[2]?.badge).toBe("3");
    const calm = purchaseSections({ urgentMaterials: 0, receivePending: 0 });
    expect(calm[1]?.attention).toBeUndefined();
    expect(calm[2]?.badge).toBeUndefined();
  });

  it("sub-seção da Base pela rota, e a rota de cada sub-seção; a contagem saiu da Base", () => {
    expect(baseSectionOf("/base/costs")).toBe("costs");
    expect(baseSectionOf("/base/materials/FAR-T65")).toBe("materials");
    expect(baseSectionOf("/buy")).toBeNull();
    expect(baseSectionOf("/count")).toBeNull();
    expect(baseSectionPath("costs")).toBe("/base/costs");
    expect(PURCHASE_BASE_SECTIONS.map((section) => section.key)).toEqual(["materials", "suppliers", "costs"]);
  });

  it("a troca de cadastro contém só objetos estáveis; custos é tarefa", () => {
    expect(PURCHASE_BASE_RECORD_SECTIONS.map((section) => [section.key, section.label])).toEqual([
      ["materials", "Insumos"],
      ["suppliers", "Fornecedores"],
    ]);
  });
});

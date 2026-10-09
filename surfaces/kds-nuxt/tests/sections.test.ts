import { describe, expect, it } from "vitest";

import { KDS_BAR_SECTIONS, kdsSections, kdsShellSections } from "../app/presentation/sections";
import { quickBarLayout, quickBarProblems } from "../../operator-kit/app/presentation/suiteChrome";

// As seções da Cozinha (dono, 09/10/2026): cada estação da casa pelo NOME, levando à sua
// bancada; a Saída leva ao Gestor. Não existe estação chamada "Preparo".
const EXIT = "https://gestor.example/?columns=expedition";
const stations = [
  { ref: "cafes", name: "Cafés", type: "prep", count: 2 },
  { ref: "lanches", name: "Lanches", type: "prep", count: 0 },
  { ref: "encomendas", name: "Encomendas", type: "picking", count: 1 },
];
const base = { stations, priorityRef: "", exitUrl: EXIT, exitCount: 5 };

describe("seções da Cozinha", () => {
  it("barra lateral: as estações na ordem do cadastro, Saída, Painel de retirada; Ajustes no pé", () => {
    const sections = kdsSections({ ...base, priorityRef: "lanches", place: "rail" });
    expect(sections.map((s) => [s.label, s.to])).toEqual([
      ["Cafés", "/cafes"],
      ["Lanches", "/lanches"],
      ["Encomendas", "/encomendas"],
      ["Saída", EXIT],
      ["Painel de retirada", "/pickup"],
      ["Ajustes", undefined],
    ]);
    expect(sections.find((s) => s.key === "settings")?.foot).toBe(true);
  });

  it("nenhum item se chama Preparo, em lugar nenhum", () => {
    for (const place of ["rail", "bar"] as const) {
      expect(kdsSections({ ...base, priorityRef: "cafes", place }).some((s) => s.label === "Preparo")).toBe(false);
    }
  });

  it("cada estação leva o selo dos pedidos dela; zero não é selo", () => {
    const sections = kdsSections({ ...base, exitCount: 0, place: "rail" });
    expect(sections.find((s) => s.to === "/cafes")?.badge).toBe("2");
    expect(sections.find((s) => s.to === "/lanches")?.badge).toBeUndefined();
    expect(sections.find((s) => s.key === "exit")?.badge).toBeUndefined();
  });

  it("Saída é atalho para a coluna do Gestor, nunca uma tela da Cozinha (#1431)", () => {
    const exit = kdsSections({ ...base, place: "rail" }).find((s) => s.key === "exit")!;
    expect(exit.to).toBe(EXIT);
    expect(exit.badge).toBe("5");
    expect(kdsSections({ ...base, exitUrl: "", place: "rail" }).some((s) => s.key === "exit")).toBe(false);
  });

  it("barra inferior: a estação aberta à frente, as outras na ordem do cadastro, Saída à vista", () => {
    const sections = kdsSections({ ...base, priorityRef: "encomendas", place: "bar" });
    expect(sections.map((s) => s.label)).toEqual(["Encomendas", "Cafés", "Lanches", "Saída", "Ajustes"]);
    expect(sections.some((s) => s.key === "pickup")).toBe(false);
  });

  it("com mais estações do que cabem, a Saída fica entre as visíveis e o resto vai para o Mais", () => {
    const many = [
      ...stations,
      { ref: "forno", name: "Forno", type: "prep", count: 0 },
      { ref: "bar", name: "Bar", type: "prep", count: 0 },
    ];
    const sections = kdsSections({ ...base, stations: many, priorityRef: "bar", place: "bar" });
    const visible = sections.slice(0, KDS_BAR_SECTIONS).map((s) => s.label);
    expect(visible).toEqual(["Bar", "Cafés", "Lanches", "Saída"]);
    expect(sections.slice(KDS_BAR_SECTIONS).map((s) => s.label)).toEqual(["Encomendas", "Forno", "Ajustes"]);
  });

  it("sem a estação aberta nem lembrada, a barra segue a ordem do cadastro", () => {
    const sections = kdsSections({ ...base, place: "bar" });
    expect(sections.map((s) => s.label)).toEqual(["Cafés", "Lanches", "Encomendas", "Saída", "Ajustes"]);
  });
});

describe("seções da Cozinha no shell da suíte", () => {
  it("uma lista, as duas ordens: a lateral pelo cadastro, a inferior com a aberta à frente", () => {
    const sections = kdsShellSections({ ...base, priorityRef: "encomendas" });
    const rail = sections.filter((s) => s.where !== "bar" && !s.foot).map((s) => s.label);
    const quick = sections.filter((s) => s.where !== "rail");
    expect(rail).toEqual(["Cafés", "Lanches", "Encomendas", "Saída", "Painel de retirada"]);
    expect(quick.filter((s) => s.quick).map((s) => s.label)).toEqual(["Encomendas", "Cafés", "Lanches", "Saída"]);
    expect(quick.at(-1)?.key).toBe("settings");
    expect(sections.filter((s) => s.foot).map((s) => s.label)).toEqual(["Ajustes"]);
  });

  it("a barra inferior cabe na regra da suíte (4 seções e o Mais com Ajustes)", () => {
    const quick = kdsShellSections({ ...base, priorityRef: "" }).filter((s) => s.where !== "rail");
    expect(quickBarProblems(quick)).toEqual([]);
    expect(quickBarLayout(quick).more).toBe(true);
  });
});

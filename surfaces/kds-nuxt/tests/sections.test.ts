import { describe, expect, it } from "vitest";

import { kdsSections } from "../app/presentation/sections";

// As seções da Cozinha no rail da suíte e na barra do polegar (prévia v4).
const base = { stationRef: "forno", prepCount: 12, exitUrl: "https://gestor.example/?columns=expedition", exitCount: 5 };

describe("seções da Cozinha", () => {
  it("rail: Estações, Preparo, Saída, Painel de retirada; Ajustes no pé", () => {
    const sections = kdsSections({ ...base, place: "rail" });
    expect(sections.map((s) => s.key)).toEqual(["stations", "prep", "exit", "pickup", "settings"]);
    expect(sections.find((s) => s.key === "settings")?.foot).toBe(true);
    expect(sections.find((s) => s.key === "settings")?.to).toBeUndefined();
  });

  it("Preparo abre a estação deste dispositivo, com o selo dos pedidos dela", () => {
    const prep = kdsSections({ ...base, place: "rail" }).find((s) => s.key === "prep")!;
    expect(prep.to).toBe("/forno");
    expect(prep.badge).toBe("12");
  });

  it("Saída é atalho para a coluna do Gestor, nunca uma tela da Cozinha (#1431)", () => {
    const exit = kdsSections({ ...base, place: "rail" }).find((s) => s.key === "exit")!;
    expect(exit.to).toBe(base.exitUrl);
    expect(exit.badge).toBe("5");
    expect(kdsSections({ ...base, exitUrl: "", place: "rail" }).some((s) => s.key === "exit")).toBe(false);
  });

  it("zero não é selo", () => {
    const sections = kdsSections({ ...base, prepCount: 0, exitCount: 0, place: "rail" });
    expect(sections.find((s) => s.key === "prep")?.badge).toBeUndefined();
    expect(sections.find((s) => s.key === "exit")?.badge).toBeUndefined();
  });

  it("sem estação lembrada, não há Preparo", () => {
    expect(kdsSections({ ...base, stationRef: "", place: "rail" }).some((s) => s.key === "prep")).toBe(false);
  });

  it("barra do polegar (v4 cozinha-celular): Preparo, Saída, Estações; sem o Painel de retirada (é tela de TV)", () => {
    const keys = kdsSections({ ...base, place: "bar" }).map((s) => s.key);
    expect(keys).toEqual(["prep", "exit", "stations", "settings"]);
  });
});

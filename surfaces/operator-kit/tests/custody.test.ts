// A custódia do entregador (troco da gaveta, maquininha): uma forma só, no Gestor e no PDV.
import { describe, expect, it } from "vitest";

import { freeMachines, machinePhrase, moneyInput } from "../app/presentation/custody";

describe("custódia do entregador", () => {
  it("só as maquininhas livres saem", () => {
    const options = [
      { ref: "card_machine:A", label: "Maquininha 1", enabled: true },
      { ref: "card_machine:B", label: "Azul", enabled: false, reason: "Na rua com o pedido 1043" },
      { ref: "cash_bag", label: "Malote" },
    ];
    expect(freeMachines(options).map((opt) => opt.ref)).toEqual(["card_machine:A"]);
  });

  it("a maquininha na frase, sem repetir a palavra", () => {
    expect(machinePhrase("Azul")).toBe("maquininha Azul");
    expect(machinePhrase("Maquininha 1")).toBe("maquininha 1");
    expect(machinePhrase("  ")).toBe("maquininha");
  });

  it("centavos no formato do campo de dinheiro", () => {
    expect(moneyInput(2000)).toBe("20,00");
    expect(moneyInput(5)).toBe("0,05");
    expect(moneyInput(-30)).toBe("0,00");
  });
});

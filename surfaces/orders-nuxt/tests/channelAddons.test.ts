import { describe, expect, it } from "vitest";
import {
  addonStatusLabel,
  choiceRule,
  parsePriceQ,
} from "~/presentation/channelAddons";
import { homologationClock } from "~/presentation/homologationBand";

describe("parsePriceQ", () => {
  it.each([
    ["12,50", 1250],
    ["R$ 3", 300],
    ["1.234,56", 123456],
    ["2.5", 250],
    ["0", 0],
  ])("%s → %d centavos", (text, cents) => {
    expect(parsePriceQ(text)).toBe(cents);
  });
  it.each(["", "abc", "1,234", "-2", "12,5,0"])("%s não é preço", (text) => {
    expect(parsePriceQ(text)).toBeNull();
  });
});

describe("choiceRule", () => {
  it("diz se é opcional ou obrigatório e quantos", () => {
    expect(choiceRule(0, 1)).toBe("Opcional, escolhe 1");
    expect(choiceRule(0, 3)).toBe("Opcional, até 3");
    expect(choiceRule(1, 1)).toBe("Obrigatório, escolhe 1");
    expect(choiceRule(1, 3)).toBe("Obrigatório, de 1 a 3");
  });
  it("rotula o estado", () => {
    expect(addonStatusLabel(true)).toBe("Ativo");
    expect(addonStatusLabel(false)).toBe("Pausado");
  });
});

describe("homologationClock", () => {
  it("mostra Brasília com segundos e o UTC do log do iFood", () => {
    expect(homologationClock(new Date("2026-11-17T14:05:09Z"))).toBe(
      "17/11/2026 11:05:09 (Brasília) · 14:05:09 UTC",
    );
  });
});

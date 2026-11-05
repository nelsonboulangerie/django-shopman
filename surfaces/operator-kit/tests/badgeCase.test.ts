import { describe, expect, it } from "vitest";

import { badgeCase } from "../app/presentation/badgeCase";

// Selo leva iniciais maiúsculas na suíte inteira (dono, 03/11 e 04/11/2026).
describe("badgeCase", () => {
  it("cada palavra maiúscula, artigo e preposição no meio em minúscula", () => {
    expect(badgeCase("Loja online")).toBe("Loja Online");
    expect(badgeCase("a receber")).toBe("A Receber");
    expect(badgeCase("Pagar na retirada")).toBe("Pagar na Retirada");
    expect(badgeCase("Saiu para entrega")).toBe("Saiu para Entrega");
    expect(badgeCase("Turno aberto · parcial")).toBe("Turno Aberto · Parcial");
  });

  it("marca, sigla, número e unidade ficam como são", () => {
    expect(badgeCase("iFood")).toBe("iFood");
    expect(badgeCase("PDV")).toBe("PDV");
    expect(badgeCase("NB-1042")).toBe("NB-1042");
    expect(badgeCase("2 kg")).toBe("2 kg");
    expect(badgeCase("vendido por kg")).toBe("Vendido por kg");
  });
});

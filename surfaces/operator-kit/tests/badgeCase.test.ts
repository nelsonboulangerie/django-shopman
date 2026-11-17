import { describe, expect, it } from "vitest";

import { badgeCase } from "../app/presentation/badgeCase";

// Selo é sentença: só a primeira letra maiúscula (dono, 16/11/2026). Reverte as
// iniciais maiúsculas de 03/11 e 04/11/2026 ("Loja Online", "A Receber").
describe("badgeCase", () => {
  it("só a primeira letra da sentença maiúscula", () => {
    expect(badgeCase("procurando outro entregador")).toBe("Procurando outro entregador");
    expect(badgeCase("Procurando outro entregador")).toBe("Procurando outro entregador");
    expect(badgeCase("loja online")).toBe("Loja online");
    expect(badgeCase("a receber")).toBe("A receber");
    expect(badgeCase("Saiu para entrega")).toBe("Saiu para entrega");
    expect(badgeCase("Turno aberto · parcial")).toBe("Turno aberto · Parcial");
  });

  it("o resto fica como foi escrito: nome próprio e sigla no meio", () => {
    expect(badgeCase("Pronto pela Cozinha")).toBe("Pronto pela Cozinha");
    expect(badgeCase("pedido do iFood")).toBe("Pedido do iFood");
    expect(badgeCase("NFC-e não solicitada")).toBe("NFC-e não solicitada");
  });

  it("marca, sigla, número e unidade no começo ficam como são", () => {
    expect(badgeCase("iFood")).toBe("iFood");
    expect(badgeCase("PDV")).toBe("PDV");
    expect(badgeCase("NB-1042")).toBe("NB-1042");
    expect(badgeCase("2 kg")).toBe("2 kg");
    expect(badgeCase("vendido por kg")).toBe("Vendido por kg");
  });

  it("a regra de iniciais de 03/11 não volta", () => {
    for (const label of ["loja online", "a receber", "pagar na retirada", "saiu para entrega"]) {
      const rest = badgeCase(label).split(" ").slice(1);
      expect(rest.every((word) => word === word.toLowerCase())).toBe(true);
    }
  });
});

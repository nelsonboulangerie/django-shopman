import { describe, expect, it } from "vitest";

import { PICKUP_CAPACITY, pickupCode, pickupColumn, pickupDensity } from "~/presentation/pickup";

const refs = (n: number) => Array.from({ length: n }, (_, i) => `PDV-261105-${String(i + 1).padStart(3, "0")}`);

describe("Painel de retirada: a TV não rola (beta 05/11, KDS-09)", () => {
  it("seis pedidos em preparo cabem todos, sem nada abaixo da dobra", () => {
    const column = pickupColumn(refs(6));
    expect(column.shown).toHaveLength(6);
    expect(column.more).toBe(0);
    expect(column.density).toBe("compact");
  });

  it("a densidade sobe com a contagem", () => {
    expect(pickupDensity(3)).toBe("roomy");
    expect(pickupDensity(12)).toBe("dense");
  });

  it("no limite do servidor (24), o que não cabe vira +N no último lugar, sem cartão cortado", () => {
    const column = pickupColumn(refs(24));
    expect(column.density).toBe("dense");
    expect(column.shown.length + 1).toBe(PICKUP_CAPACITY.dense);
    expect(column.shown.length + column.more).toBe(24);
  });
});

describe("Painel de retirada: o cliente lê só o código (beta 05/11, KDS-16)", () => {
  it("tira o prefixo da casa", () => {
    expect(pickupCode("PDV-261105-R09")).toBe("R09");
    expect(pickupCode("R09")).toBe("R09");
  });
});

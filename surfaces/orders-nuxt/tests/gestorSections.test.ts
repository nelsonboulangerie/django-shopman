import { describe, expect, it } from "vitest";

import { gestorSections } from "../app/presentation/gestorSections";

describe("gestorSections", () => {
  it("Clientes aparece para quem pode gerir clientes, entre Catálogo e Canais", () => {
    const keys = gestorSections({ channelsAttention: "", canManageCustomers: true }).map((s) => s.key);
    expect(keys).toEqual(["orders", "catalog", "customers", "feeds"]);
  });

  it("sem a permissão (ou sem resposta ainda) a aba não existe", () => {
    const keys = gestorSections({ channelsAttention: "", canManageCustomers: false }).map((s) => s.key);
    expect(keys).toEqual(["orders", "catalog", "feeds"]);
  });

  it("a atenção de Canais só aparece quando há o que dizer", () => {
    const quiet = gestorSections({ channelsAttention: "", canManageCustomers: false }).find((s) => s.key === "feeds");
    const loud = gestorSections({ channelsAttention: "1 desligado", canManageCustomers: false }).find((s) => s.key === "feeds");
    expect(quiet?.attention).toBeUndefined();
    expect(loud?.attention).toBe("1 desligado");
  });
});

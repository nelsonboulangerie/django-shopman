import { describe, expect, it } from "vitest";

import { gestorLandingPath } from "../app/presentation/gestorAccess";

describe("gestorLandingPath", () => {
  it("leva a persona exclusiva de catálogo direto ao catálogo", () => {
    expect(gestorLandingPath("catalog", "/catalog")).toBe("/catalog");
  });

  it("falha fechado para path inventado e preserva as personas de pedidos", () => {
    expect(gestorLandingPath("catalog", "/customers")).toBe("/");
    expect(gestorLandingPath("orders", "/catalog")).toBe("/");
    expect(gestorLandingPath("expedition", "/catalog")).toBe("/");
  });
});

import { describe, expect, it } from "vitest";

import { lowerFirst, materialShortageLine } from "~/presentation/shortage";

describe("materialShortageLine (WP-F11)", () => {
  it("diz quanto falta de quê, na medida da bancada", () => {
    expect(materialShortageLine({ name: "Manteiga", sku: "INS-MANTEIGA", shortage_display: "300 g" })).toBe(
      "Falta 300 g de manteiga",
    );
  });

  it("sem nome, cai no SKU; sigla não vira minúscula", () => {
    expect(materialShortageLine({ name: "", sku: "INS-X", shortage_display: "2 un" })).toBe("Falta 2 un de INS-X");
    expect(lowerFirst("UHT integral")).toBe("UHT integral");
    expect(lowerFirst("Farinha T65")).toBe("farinha T65");
  });
});

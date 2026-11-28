import { describe, expect, it } from "vitest";
import { productSearchPlaceholder } from "~/presentation/catalog";

// Beta test de 05/11/2026 (PDV-16): em 1024 px o convite saía "Buscar produto, có".
describe("productSearchPlaceholder", () => {
  it("campo estreito ganha a frase curta, que cabe", () => {
    expect(productSearchPlaceholder({ coarse: false, customerSearch: true, width: 420 })).toBe("Buscar produto ou comanda");
  });
  it("campo largo diz tudo o que a busca acha", () => {
    expect(productSearchPlaceholder({ coarse: false, customerSearch: true, width: 800 })).toBe("Buscar produto, código, comanda ou cliente");
    expect(productSearchPlaceholder({ coarse: false, customerSearch: false, width: 800 })).toBe("Buscar produto, código ou comanda");
  });
  it("no toque e antes de medir, como antes", () => {
    expect(productSearchPlaceholder({ coarse: true, customerSearch: true, width: 900 })).toBe("Buscar produto ou comanda");
    expect(productSearchPlaceholder({ coarse: false, customerSearch: false, width: 0 })).toBe("Buscar produto, código ou comanda");
  });
});

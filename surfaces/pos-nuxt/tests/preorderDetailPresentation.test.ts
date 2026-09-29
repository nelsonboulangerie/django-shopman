// A volta do detalhe da encomenda: o recorte da lista vai no link (`?back=`), e
// só caminho da própria seção vale (o parâmetro nunca vira redirecionamento aberto).
import { describe, expect, it } from "vitest";

import { preorderBackTarget, preorderDetailPath } from "../app/presentation/preorderDetail";

describe("preorderDetailPath — o link leva a volta junto", () => {
  it("o recorte da lista vai em ?back=", () => {
    expect(preorderDetailPath("NB-7", "/preorders?mode=day&date=2026-10-02&print=pending"))
      .toBe("/preorders/NB-7?back=%2Fpreorders%3Fmode%3Dday%26date%3D2026-10-02%26print%3Dpending");
  });

  it("a casa da seção não vai na URL: a volta sem back já cai nela", () => {
    expect(preorderDetailPath("NB-7", "/preorders")).toBe("/preorders/NB-7");
    expect(preorderDetailPath("NB-7")).toBe("/preorders/NB-7");
  });

  it("recorte de fora da seção é ignorado", () => {
    expect(preorderDetailPath("NB-7", "https://example.com/preorders")).toBe("/preorders/NB-7");
    expect(preorderDetailPath("NB-7", "/preordersX")).toBe("/preorders/NB-7");
  });

  it("o ref é escapado", () => {
    expect(preorderDetailPath("A/B 1")).toBe("/preorders/A%2FB%201");
  });

  it("o que o link manda, a volta aceita (ida e volta)", () => {
    const from = "/preorders?mode=week&fulfillment=delivery&q=Ana";
    const link = new URL(preorderDetailPath("NB-7", from), "http://pdv.test");
    expect(preorderBackTarget(link.searchParams.get("back"))).toBe(from);
  });
});

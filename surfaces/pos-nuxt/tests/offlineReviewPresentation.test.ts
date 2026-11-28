import { describe, expect, it } from "vitest";

import type { POSOfflineReviewSaleProjection } from "../app/types/pos";
import { offlineReviewClosingNotice, offlineReviewLine } from "../app/presentation/cash";
import { MANAGER_ACTIONS, managerAuthTitle } from "../../operator-kit/app/presentation/managerAuth";

// Venda sem conexão cobrada por um preço que o catálogo não explica (dono,
// 03/11/2026): entrou, e o caixa só fecha com o gerente. O fechamento lista o
// que ele confere.

function sale(over: Partial<POSOfflineReviewSaleProjection> = {}): POSOfflineReviewSaleProjection {
  return {
    order_ref: "ORD-1",
    sku: "PAO",
    name: "Pão",
    qty_display: "1",
    catalog_price_display: "R$ 12,00",
    charged_price_display: "R$ 0,01",
    operator: "marina",
    captured_at_display: "14:32",
    ...over,
  };
}

describe("presentation/cash — venda sem conexão a conferir", () => {
  it("o aviso conta as vendas, não os itens", () => {
    expect(offlineReviewClosingNotice([])).toBe("");
    expect(offlineReviewClosingNotice([sale()])).toBe("1 venda sem conexão a conferir");
    expect(offlineReviewClosingNotice([sale(), sale({ sku: "BOLO" })])).toBe("1 venda sem conexão a conferir");
    expect(offlineReviewClosingNotice([sale(), sale({ order_ref: "ORD-2" })])).toBe("2 vendas sem conexão a conferir");
  });

  it("cada linha diz o item, o cobrado, o catálogo daquela hora e quem cobrou", () => {
    expect(offlineReviewLine(sale())).toBe("Pão (PAO): cobrado R$ 0,01, catálogo R$ 12,00. marina, 14:32.");
    expect(offlineReviewLine(sale({ qty_display: "2", catalog_price_display: "" }))).toBe(
      "2 × Pão (PAO): cobrado R$ 0,01, fora do catálogo. marina, 14:32.",
    );
    expect(offlineReviewLine(sale({ operator: "", captured_at_display: "" }))).toBe(
      "Pão (PAO): cobrado R$ 0,01, catálogo R$ 12,00.",
    );
  });

  it("nenhuma frase usa travessão", () => {
    const texts = [
      offlineReviewClosingNotice([sale()]),
      offlineReviewLine(sale()),
      MANAGER_ACTIONS.close_shift_review.title,
      MANAGER_ACTIONS.close_shift_review.reason,
    ];
    for (const text of texts) expect(text).not.toMatch(/[—–]/);
  });

  it("o gerente sabe o que assina", () => {
    expect(managerAuthTitle("close_shift_review")).toBe("Autorizar o fechamento");
    expect(MANAGER_ACTIONS.close_shift_review.reason).toBe("Há venda sem conexão a conferir.");
  });
});

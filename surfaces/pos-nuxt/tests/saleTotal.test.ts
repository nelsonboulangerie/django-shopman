// O total da tela de venda: do servidor, ou o estado sem número (regra do dono, 09/10).
import { describe, expect, it } from "vitest";

import { saleTotalText, saleTotalView, type SaleTotalInputs } from "~/presentation/saleTotal";
import type { POSSaleReviewProjection } from "~/types/pos";

const review = (display: string) => ({ total_q: 0, total_display: display }) as POSSaleReviewProjection;

function inputs(overrides: Partial<SaleTotalInputs> = {}): SaleTotalInputs {
  return {
    checkoutMode: false,
    checkoutReview: null,
    checkoutReviewFailed: false,
    saleReview: null,
    saleReviewFailed: false,
    paused: false,
    hasItems: true,
    ...overrides,
  };
}

describe("saleTotalView", () => {
  it("sem itens não há total", () => {
    expect(saleTotalView(inputs({ hasItems: false })).status).toBe("hidden");
  });

  it("na venda, a revisão silenciosa é a fonte; sem ela, calculando", () => {
    expect(saleTotalView(inputs())).toEqual({ status: "calculating", display: "" });
    expect(saleTotalView(inputs({ saleReview: review("R$ 9,90") }))).toEqual({ status: "confirmed", display: "R$ 9,90" });
    expect(saleTotalView(inputs({ saleReviewFailed: true }))).toEqual({ status: "failed", display: "" });
  });

  it("no pagamento, a fonte é a revisão do pagamento (a da venda não vale)", () => {
    expect(saleTotalView(inputs({ checkoutMode: true, saleReview: review("R$ 9,90") })).status).toBe("calculating");
    expect(saleTotalView(inputs({ checkoutMode: true, checkoutReview: review("R$ 8,00") })).display).toBe("R$ 8,00");
    expect(saleTotalView(inputs({ checkoutMode: true, checkoutReviewFailed: true })).status).toBe("failed");
  });

  it("edição de encomenda: escondido (a prévia do Salvar alterações é a fonte)", () => {
    expect(saleTotalView(inputs({ paused: true, saleReview: review("R$ 9,90") })).status).toBe("hidden");
  });
});

describe("saleTotalText", () => {
  it("só o confirmado tem número", () => {
    expect(saleTotalText({ status: "confirmed", display: "R$ 9,90" })).toBe("R$ 9,90");
    expect(saleTotalText({ status: "calculating", display: "" })).toBe("Calculando…");
    expect(saleTotalText({ status: "failed", display: "" })).toBe("Não calculado");
    expect(saleTotalText({ status: "hidden", display: "" })).toBe("");
  });
});

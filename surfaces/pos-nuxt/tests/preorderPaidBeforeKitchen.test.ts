// P1-7: encomenda cobra antes (política da casa, 28/08/2026), e o Pix da venda
// mista não liquida pela palavra do operador. O servidor é a trava
// (`preorder_unpaid`, `preorder_fired_unpaid`, `pix_mixed_unconfirmed`); estas
// são as gêmeas da tela e o que ela manda.
import { describe, expect, it } from "vitest";

import type { POSCartItem } from "../app/types/pos";
import { fireRefusalView, kitchenHandoffNote } from "../app/presentation/kitchen";
import {
  attestedPixLines,
  chargeWaitsForProvider,
  firedPreorderBlocksPendingCharge,
  paymentConfirmView,
  tenderLineView,
} from "../app/presentation/payment";
import { resolvePayment } from "../app/utils/posIntent";

const line = (method: string, amount_q = 1000) =>
  tenderLineView({ method, amount_q, collection: "terminal" }, []);

function item(overrides: Partial<POSCartItem> & { sku: string }): POSCartItem {
  return { line_id: `L-${overrides.sku}`, name: overrides.sku, price_q: 0, qty: 1, notes: "", ...overrides };
}

describe("Enviar à cozinha: encomenda ainda não paga", () => {
  it("a recusa do servidor vira aviso com a saída para o Pagamento", () => {
    const view = fireRefusalView({
      code: "preorder_unpaid",
      message: "Esta encomenda ainda não foi paga. Ela vai à cozinha sozinha quando o pagamento entrar.",
      recovery: "Cobre no Pagamento.",
    });
    expect(view?.title).toContain("ainda não foi paga");
    expect(view?.description).toBe("Cobre no Pagamento.");
    expect(view?.action).toEqual({ label: "Abrir Pagamento", opens: "payment" });
  });

  it("outra recusa segue pelo aviso de erro de sempre", () => {
    expect(fireRefusalView({ code: "preorder_not_due", message: "x" })).toBeNull();
    expect(fireRefusalView(null)).toBeNull();
  });

  it("a frase do Pagamento não promete a cozinha antes de o Pix ou o link entrarem", () => {
    expect(kitchenHandoffNote([item({ sku: "BOLO", qty: 2 })], { waitsPayment: true }))
      .toBe("Os 2 itens vão para a cozinha quando o pagamento entrar.");
    expect(kitchenHandoffNote([item({ sku: "BOLO" })], { waitsPayment: true }))
      .toBe("O item vai para a cozinha quando o pagamento entrar.");
  });
});

describe("cobrança que espera o provedor", () => {
  it("só Pix ou link da venda inteira, recebidos no balcão", () => {
    expect(chargeWaitsForProvider({ collection: "terminal", methods: ["pix"] })).toBe(true);
    expect(chargeWaitsForProvider({ collection: "terminal", methods: ["pix", "pix"] })).toBe(true);
    expect(chargeWaitsForProvider({ collection: "terminal", methods: ["link"] })).toBe(true);
    expect(chargeWaitsForProvider({ collection: "terminal", methods: ["cash", "pix"] })).toBe(false);
    expect(chargeWaitsForProvider({ collection: "terminal", methods: ["credit"] })).toBe(false);
    expect(chargeWaitsForProvider({ collection: "on_delivery", methods: ["cash"] })).toBe(false);
  });

  it("encomenda já na cozinha não valida com Pix ou link pendentes (gêmea de preorder_fired_unpaid)", () => {
    const base = { salesMode: "order" as const, anyFired: true, collection: "terminal" as const };
    expect(firedPreorderBlocksPendingCharge({ ...base, methods: ["pix"] })).toBe(true);
    expect(firedPreorderBlocksPendingCharge({ ...base, methods: ["link"] })).toBe(true);
    expect(firedPreorderBlocksPendingCharge({ ...base, methods: ["cash"] })).toBe(false);
    expect(firedPreorderBlocksPendingCharge({ ...base, anyFired: false, methods: ["pix"] })).toBe(false);
    expect(firedPreorderBlocksPendingCharge({ ...base, salesMode: "counter", methods: ["pix"] })).toBe(false);
  });
});

describe("Pix na venda mista: o gesto Recebi o Pix", () => {
  it("só o Pix da venda MISTA é atestado pelo operador", () => {
    expect(attestedPixLines([line("cash"), line("pix")]).map((l) => l.method)).toEqual(["pix"]);
    expect(attestedPixLines([line("pix"), line("pix")])).toEqual([]);
    expect(attestedPixLines([line("pix")])).toEqual([]);
    expect(attestedPixLines([line("cash"), line("credit")])).toEqual([]);
  });

  it("o botão diz exatamente o que afirma", () => {
    expect(paymentConfirmView({ machine: 1, pix: 0 }).cta).toBe("OK, cobrei na maquininha");
    expect(paymentConfirmView({ machine: 0, pix: 1 })).toEqual({
      title: "Confira o Pix",
      description: "Veja no app do banco ou na maquininha se o valor entrou.",
      cta: "Recebi o Pix",
    });
    expect(paymentConfirmView({ machine: 1, pix: 1 }).cta).toBe("Cobrei e recebi o Pix");
  });

  it("nenhuma frase usa travessão", () => {
    for (const view of [
      paymentConfirmView({ machine: 1, pix: 0 }),
      paymentConfirmView({ machine: 0, pix: 1 }),
      paymentConfirmView({ machine: 1, pix: 1 }),
    ]) {
      expect(`${view.title} ${view.description} ${view.cta}`).not.toMatch(/[—–]/);
    }
  });

  it("o intent leva a confirmação só na linha de Pix, e nunca quem ou quando", () => {
    const r = resolvePayment(
      [
        { method: "cash", amount_q: 200, collection: "terminal", pix_confirmed: true },
        { method: "pix", amount_q: 1000, collection: "terminal", pix_confirmed: true },
      ],
      1200,
    );
    expect(r.paymentTenders).toEqual([
      { method: "cash", amount_q: 200, collection: "terminal" },
      { method: "pix", amount_q: 1000, collection: "terminal", pix_confirmed: true },
    ]);
  });

  it("Pix sem o gesto sobe sem a marca (o servidor recusa)", () => {
    const r = resolvePayment(
      [
        { method: "cash", amount_q: 200, collection: "terminal" },
        { method: "pix", amount_q: 1000, collection: "terminal" },
      ],
      1200,
    );
    expect(r.paymentTenders[1]).toEqual({ method: "pix", amount_q: 1000, collection: "terminal" });
  });
});

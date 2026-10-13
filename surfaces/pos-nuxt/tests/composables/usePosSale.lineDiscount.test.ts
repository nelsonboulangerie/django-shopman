import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

import { cartNetTotalQ } from "~/presentation/receipt";
import { lineTotalQ } from "~/presentation/lineDiscounts";
import type { POSCartItem } from "~/types/pos";

import { makeProjection, makeSale } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }));

// Relato do dono (13/10/2026, no alpha): R$ 1,00 de desconto numa linha de 3
// cafés, e o total da linha só mudou quando ele recarregou a página. O total da
// linha lia `charged_price_q`, que só o servidor escrevia, e só ao reabrir a
// comanda. Agora o toque recalcula pela régua do kernel e o eco do salvar confirma.

function saleWithCafe(actionCall = vi.fn().mockResolvedValue({})) {
  const routed = vi.fn((path: string, options?: unknown) => (String(path).includes("/sale/review/")
    ? Promise.resolve({ review: { total_q: 0, total_display: "R$ 0,00" } })
    : actionCall(path, options)));
  const h = makeSale({
    projection: makeProjection({
      checkout: {
        intent_version: 1,
        capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
      } as ReturnType<typeof makeProjection>["checkout"],
    }),
    actionCall: routed,
  });
  h.sale.cart.tabRef = "M1";
  h.sale.cart.tabDisplay = "M1";
  h.sale.cart.tabSessionKey = "sess-1";
  h.sale.cart.expectedRevision = "v1:initial";
  const cafe: POSCartItem = {
    line_id: "L1",
    sku: "CAFE",
    name: "Café",
    qty: 3,
    price_q: 800,
    list_price_q: 800,
    charged_price_q: 800,
    pricing_discount: null,
    notes: "",
  };
  h.sale.cart.items.push(cafe);
  return h;
}

const line = (h: ReturnType<typeof saleWithCafe>) => h.sale.cart.items.find((item) => item.line_id === "L1")!;

describe("usePosSale — desconto na linha muda o total no mesmo toque", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("R$ 1,00 numa linha de 3: a linha e a comanda mostram R$ 21,00 antes de o servidor responder", async () => {
    const h = saleWithCafe();
    await nextTick();

    h.sale.setLineDiscount("L1", 1, "cortesia", "fixed");

    expect(lineTotalQ(line(h))).toBe(2100);
    expect(cartNetTotalQ(h.sale.cart.items)).toBe(2100);
    h.handles.dispose();
  });

  it("10% numa linha de 3: R$ 21,60, e tirar o desconto volta a R$ 24,00", async () => {
    const h = saleWithCafe();
    await nextTick();

    h.sale.setLineDiscount("L1", 10, "cortesia", "percent");
    expect(lineTotalQ(line(h))).toBe(2160);

    h.sale.setLineDiscount("L1", 0, "cortesia", "percent");
    expect(lineTotalQ(line(h))).toBe(2400);
    h.handles.dispose();
  });

  it("o automático maior continua valendo: o manual menor não baixa o preço", async () => {
    const h = saleWithCafe();
    Object.assign(line(h), {
      charged_price_q: 680,
      pricing_discount: { type: "promotion", label: "Semana do Café", amount_q: 120, percent: 15 },
    });
    await nextTick();

    h.sale.setLineDiscount("L1", 1, "cortesia", "fixed");

    expect(lineTotalQ(line(h))).toBe(2040);
    h.handles.dispose();
  });

  it("o eco do salvar manda no preço, e a gravação não se repete por causa dele", async () => {
    const actionCall = vi.fn().mockResolvedValue({
      revision: "v1:next",
      line_prices: { L1: { charged_price_q: 650, list_price_q: 800, pricing_discount: null } },
    });
    const h = saleWithCafe(actionCall);
    await nextTick();
    await vi.advanceTimersByTimeAsync(1200);
    actionCall.mockClear();

    h.sale.setLineDiscount("L1", 1, "cortesia", "fixed");
    await nextTick();
    await vi.advanceTimersByTimeAsync(1200);

    expect(actionCall).toHaveBeenCalledTimes(1);
    expect(line(h).charged_price_q).toBe(650);
    expect(lineTotalQ(line(h))).toBe(1950);

    await vi.advanceTimersByTimeAsync(10_000);
    expect(actionCall).toHaveBeenCalledTimes(1);
    h.handles.dispose();
  });
});

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { toast } from "vue-sonner";

import { lineTotalQ, type POSLinePrice } from "~/presentation/lineDiscounts";
import type { POSCartItem } from "~/types/pos";

import { makeProjection, makeSale } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }));

// Relato do dono (13/10/2026, no alpha): R$ 1,00 de desconto numa linha de 3
// cafés, e o total da linha só mudou quando ele recarregou a página. A correção de
// então fez a tela calcular o preço pela régua do kernel copiada; o laudo de
// soberania (18/10/2026) apagou a cópia. Agora o preço da linha e o descarte do
// desconto vêm do servidor: a prévia do editor (antes do Aplicar), a revisão e o
// eco do salvar. Entre o toque e a resposta, a linha diz "calculando".

type ReviewBody = { items?: Array<{ line_id: string; discount?: { type: string; value: number } }> };

function saleWithCafe(
  actionCall = vi.fn().mockResolvedValue({}),
  reviewLinePrices: (body: ReviewBody) => Record<string, POSLinePrice> = () => ({}),
) {
  const routed = vi.fn((path: string, options?: unknown) => (String(path).includes("/sale/review/")
    ? Promise.resolve({
        review: {
          total_q: 0,
          total_display: "R$ 0,00",
          line_prices: reviewLinePrices(((options as { body?: ReviewBody })?.body) || {}),
        },
      })
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

/** A revisão como o motor responderia: R$ 1,00 por unidade vence, 10% perde para
 *  a "Semana do Café" (−15%). */
function engine(body: ReviewBody): Record<string, POSLinePrice> {
  const discount = body.items?.find((item) => item.line_id === "L1")?.discount;
  if (!discount) return {};
  if (discount.type === "fixed") {
    return { L1: { charged_price_q: 700, list_price_q: 800, pricing_discount: null, manual_discount_discarded: false } };
  }
  return {
    L1: {
      charged_price_q: 680, list_price_q: 800, manual_discount_discarded: true,
      pricing_discount: { type: "promotion", label: "Semana do Café", amount_q: 120, percent: 15 },
    },
  };
}

describe("usePosSale — o desconto na linha: o motor decide, a tela espera", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(toast.info).mockClear();
  });
  afterEach(() => vi.useRealTimers());

  it("o toque não inventa número: a linha diz calculando até a revisão responder", async () => {
    const h = saleWithCafe(undefined, engine);
    await nextTick();

    h.sale.setLineDiscount("L1", 1, "cortesia", "fixed");

    expect(line(h).price_pending).toBe(true);
    expect(line(h).charged_price_q).toBe(800);
    await vi.advanceTimersByTimeAsync(450);
    expect(line(h).price_pending).toBe(false);
    expect(lineTotalQ(line(h))).toBe(2100);
    h.handles.dispose();
  });

  it("a prévia do editor pergunta à revisão com o desconto digitado, e o Aplicar usa a resposta", async () => {
    const h = saleWithCafe(undefined, engine);
    await nextTick();

    h.sale.previewLineDiscount("L1", "fixed", 1);
    expect(h.sale.discountPreview.value?.status).toBe("pending");
    await vi.advanceTimersByTimeAsync(250);

    const reviewCalls = vi.mocked(h.handles.actionCall).mock.calls.filter(([path]) => String(path).includes("/sale/review/"));
    const body = reviewCalls.at(-1)![1] as { body: ReviewBody };
    expect(body.body.items?.[0]?.discount).toMatchObject({ type: "fixed", value: 1 });
    // A prévia não mexe no carrinho: o desconto só vale no Aplicar.
    expect(line(h).discount).toBeUndefined();
    expect(h.sale.discountPreview.value).toMatchObject({ status: "ready", price: { charged_price_q: 700 } });

    h.sale.setLineDiscount("L1", 1, "cortesia", "fixed");
    expect(line(h).price_pending).toBeFalsy();
    expect(lineTotalQ(line(h))).toBe(2100);
    h.handles.dispose();
  });

  it("o descarte é o que o servidor disse, e se diz uma vez", async () => {
    const h = saleWithCafe(undefined, engine);
    await nextTick();

    h.sale.setLineDiscount("L1", 10, "cortesia", "percent");
    await vi.advanceTimersByTimeAsync(450);

    expect(lineTotalQ(line(h))).toBe(2040);
    expect(toast.info).toHaveBeenCalledTimes(1);
    expect(vi.mocked(toast.info).mock.calls[0]![0]).toContain("Semana do Café");

    // Outra revisão (qualquer mudança no carrinho) repete o eco: o aviso não volta.
    h.sale.setQty("L1", 4);
    await vi.advanceTimersByTimeAsync(450);
    expect(toast.info).toHaveBeenCalledTimes(1);
    h.handles.dispose();
  });

  it("o desconto que vence não vira aviso", async () => {
    const h = saleWithCafe(undefined, engine);
    await nextTick();

    h.sale.setLineDiscount("L1", 1, "cortesia", "fixed");
    await vi.advanceTimersByTimeAsync(450);

    expect(toast.info).not.toHaveBeenCalled();
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

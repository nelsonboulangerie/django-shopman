// Reenvio do link de pagamento — o gesto "não chegou" da tela de resultado.
// Arquivo próprio (e não no sale.test.ts) porque o harness `makeSale` injeta o
// transporte `action.call`: aqui não há `$fetch` a mockar.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "vue-sonner";

import { makeProjection, makeSale } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

function freeCartProjection() {
  return makeProjection({
    checkout: {
      intent_version: 1,
      capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
    } as ReturnType<typeof makeProjection>["checkout"],
  });
}

function saleRouter(closePayment: Record<string, unknown> | null = null) {
  return vi.fn().mockImplementation(async (path: string) => {
    if (String(path).includes("/sale/review/")) {
      return { review: { total_q: 1000, total_display: "R$ 10,00", subtotal_q: 1000 } };
    }
    if (String(path).includes("/sale/close/")) {
      return { ok: true, order_ref: "PED-1", payment: closePayment };
    }
    return {};
  });
}

function saleReadyForCheckout(actionCall: ReturnType<typeof vi.fn>) {
  const h = makeSale({ projection: freeCartProjection(), actionCall });
  const pao = h.handles.posValue.value!.products[0]!;
  h.sale.addProduct(pao);
  h.sale.addProduct(pao);
  return h;
}

describe("usePosSale — reenviar o link de pagamento", () => {
  const linkPayment = {
    method: "link",
    amount_q: 1000,
    amount_display: "R$ 10,00",
    status: "pending",
    message: "",
    checkout_url: "https://pay.example.com/abc",
  };

  beforeEach(() => {
    vi.mocked(toast.error).mockClear();
    vi.mocked(toast.success).mockClear();
  });

  async function closedLinkSale(actionCall: ReturnType<typeof vi.fn>) {
    const h = saleReadyForCheckout(actionCall);
    await h.sale.submitSale(); // prepara
    await h.sale.submitSale(); // fecha
    expect(h.sale.result.value?.payment?.isLink).toBe(true);
    return h;
  }

  it("posta em /pos/orders/{ref}/resend-payment-link/ e tosta sucesso", async () => {
    const actionCall = saleRouter(linkPayment);
    const h = await closedLinkSale(actionCall);

    expect(await h.sale.resendPaymentLink()).toBe(true);

    const resend = actionCall.mock.calls.filter((c) => String(c[0]).includes("/resend-payment-link/"));
    expect(resend).toHaveLength(1);
    expect(String(resend[0]![0])).toBe("/api/v1/backstage/pos/orders/PED-1/resend-payment-link/");
    expect(vi.mocked(toast.success)).toHaveBeenCalledWith("Link reenviado ao cliente");
    expect(h.sale.resendingLink.value).toBe(false);
    h.handles.dispose();
  });

  it("recusa do servidor vira toast com o MOTIVO — não o fallback genérico", async () => {
    const actionCall = saleRouter(linkPayment);
    const h = await closedLinkSale(actionCall);
    actionCall.mockImplementationOnce(async () => {
      throw { data: { detail: "Acabamos de enviar. Aguarde 42 s para reenviar.", error: { code: "payment_link_resend_too_soon" } } };
    });

    expect(await h.sale.resendPaymentLink()).toBe(false);

    expect(vi.mocked(toast.error)).toHaveBeenCalledWith("Acabamos de enviar. Aguarde 42 s para reenviar.");
    expect(vi.mocked(toast.success)).not.toHaveBeenCalled();
    h.handles.dispose();
  });

  it("em voo, o segundo clique é no-op — e sem resultado na tela não há o que reenviar", async () => {
    const actionCall = saleRouter(linkPayment);
    const h = await closedLinkSale(actionCall);
    let release!: () => void;
    actionCall.mockImplementationOnce(() => new Promise<void>((r) => { release = r; }));

    const first = h.sale.resendPaymentLink();
    expect(h.sale.resendingLink.value).toBe(true);
    expect(await h.sale.resendPaymentLink()).toBe(false);
    release();
    expect(await first).toBe(true);
    expect(actionCall.mock.calls.filter((c) => String(c[0]).includes("/resend-payment-link/"))).toHaveLength(1);

    h.sale.dismissResult();
    expect(await h.sale.resendPaymentLink()).toBe(false);
    h.handles.dispose();
  });
});

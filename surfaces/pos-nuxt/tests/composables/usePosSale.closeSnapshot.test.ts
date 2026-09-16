import { mockNuxtImport } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

import { makeProjection, makeSale } from "./_posSaleHarness";

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));
mockNuxtImport("$fetch", () => fetchMock);
vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

let storageValues: Map<string, string>;
beforeEach(() => {
  storageValues = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => storageValues.get(key) ?? null,
    setItem: (key: string, value: string) => storageValues.set(key, value),
    removeItem: (key: string) => storageValues.delete(key),
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

/** Projeção sem gate de comanda e com as DUAS coletas na entrega. */
function entregaProjection(overrides: Record<string, unknown> = {}) {
  const base = makeProjection();
  return makeProjection({
    checkout: {
      intent_version: 1,
      capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
    } as ReturnType<typeof makeProjection>["checkout"],
    payment_collections: [
      ...base.payment_collections,
      {
        ref: "on_delivery" as (typeof base.payment_collections)[number]["ref"],
        label: "Na entrega",
        description: "",
        fulfillment_types: ["delivery"],
        payment_method_refs: ["cash", "credit", "debit"],
      },
    ],
    ...overrides,
  });
}

/** Router de action.call: review devolve total R$ 10,00; close devolve o que o teste pedir. */
function saleRouter(close: Record<string, unknown> = {}) {
  return vi.fn().mockImplementation(async (path: string) => {
    if (String(path).includes("/sale/review/")) {
      return { review: { total_q: 1000, total_display: "R$ 10,00", subtotal_q: 1000 } };
    }
    if (String(path).includes("/sale/close/")) {
      return { ok: true, order_ref: "PED-1", payment: null, ...close };
    }
    return {};
  });
}

function cartWithTwoBreads(h: ReturnType<typeof makeSale>) {
  const pao = h.handles.posValue.value!.products[0]!;
  h.sale.addProduct(pao);
  h.sale.addProduct(pao);
}

describe("usePosSale — o troco congelado respeita ONDE o dinheiro entra", () => {
  // A tela de resultado anunciava "TROCO R$ 90 · Confira o troco" e travava
  // Enter e auto-avanço por um dinheiro que ainda não tinha entrado: o cliente
  // paga na porta, e o troco é o que o entregador vai LEVAR.
  it("cobrança na entrega: changeQ = 0 e o troco do entregador em courierChangeQ", async () => {
    const actionCall = saleRouter();
    const h = makeSale({ projection: entregaProjection(), actionCall });
    cartWithTwoBreads(h);
    h.sale.cart.fulfillmentType = "delivery";
    await nextTick();
    h.sale.cart.paymentCollection = "on_delivery";
    await nextTick();
    await h.sale.submitSale(); // prepara (review)
    h.sale.addTender("cash");
    h.sale.tenderAdd(10000); // o cliente vai pagar com R$ 100
    expect(h.sale.paymentChangeQ.value).toBe(9000);

    await h.sale.submitSale(); // fecha

    expect(h.sale.result.value?.orderRef).toBe("PED-1");
    expect(h.sale.result.value?.changeQ).toBe(0);
    expect(h.sale.result.value?.courierChangeQ).toBe(9000);
    // e o recibo do navegador sabe que o papel saiu antes do dinheiro
    expect(h.sale.result.value?.receipt.paymentPending).toBe(true);
    expect(h.sale.result.value?.receipt.changeQ).toBe(0);
    expect(h.sale.result.value?.receipt.tenderedQ).toBe(0);
    h.handles.dispose();
  });

  it("no caixa: o troco segue congelado como herói, e o recibo guarda Recebido/Troco", async () => {
    const actionCall = saleRouter();
    const h = makeSale({ projection: entregaProjection(), actionCall });
    cartWithTwoBreads(h);
    await h.sale.submitSale();
    h.sale.addTender("cash");
    h.sale.tenderAdd(10000);

    await h.sale.submitSale();

    expect(h.sale.result.value?.changeQ).toBe(9000);
    expect(h.sale.result.value?.courierChangeQ).toBe(0);
    expect(h.sale.result.value?.receipt.tenderedQ).toBe(10000);
    expect(h.sale.result.value?.receipt.changeQ).toBe(9000);
    expect(h.sale.result.value?.receipt.paymentPending).toBe(false);
    h.handles.dispose();
  });
});

describe("usePosSale — o estado da NFC-e no resultado", () => {
  async function closeWith(close: Record<string, unknown>) {
    const actionCall = saleRouter(close);
    const h = makeSale({ projection: entregaProjection(), actionCall });
    cartWithTwoBreads(h);
    await h.sale.submitSale();
    await h.sale.submitSale();
    return h;
  }

  it("`fiscal_state` do close vence; sem ele, deriva de `fiscal_expected`", async () => {
    const explicito = await closeWith({ fiscal_expected: true, fiscal_state: "awaiting_payment" });
    expect(explicito.sale.result.value?.fiscalState).toBe("awaiting_payment");
    explicito.handles.dispose();

    const esperada = await closeWith({ fiscal_expected: true });
    expect(esperada.sale.result.value?.fiscalState).toBe("queued");
    esperada.handles.dispose();

    const semNota = await closeWith({ fiscal_expected: false });
    expect(semNota.sale.result.value?.fiscalState).toBe("not_expected");
    semNota.handles.dispose();
  });

  it("markFiscalState promove só a venda que está na tela", async () => {
    const h = await closeWith({ fiscal_expected: true });
    expect(h.sale.result.value?.fiscalState).toBe("queued");
    h.sale.markFiscalState("OUTRO", "authorized");
    expect(h.sale.result.value?.fiscalState).toBe("queued");
    h.sale.markFiscalState("PED-1", "authorized");
    expect(h.sale.result.value?.fiscalState).toBe("authorized");
    // o snapshot é substituído (não mutado): quem observa `result` acorda
    h.sale.dismissResult();
    h.sale.markFiscalState("PED-1", "failed");
    expect(h.sale.result.value).toBeNull();
    h.handles.dispose();
  });

  it("Pix confirmado no polling: `awaiting_payment` vira `queued`", async () => {
    vi.useFakeTimers();
    fetchMock.mockResolvedValue({ is_paid: true });
    const actionCall = saleRouter({
      fiscal_expected: true,
      fiscal_state: "awaiting_payment",
      payment: { method: "pix", status: "pending", amount_q: 1000, amount_display: "R$ 10,00", qr_code_base64: "abc", copy_paste: "000201", expires_at: "" },
    });
    const h = makeSale({ projection: entregaProjection(), actionCall });
    cartWithTwoBreads(h);
    await h.sale.submitSale();
    h.sale.addTender("pix");
    await h.sale.submitSale();
    expect(h.sale.result.value?.payment?.isPix).toBe(true);
    expect(h.sale.result.value?.fiscalState).toBe("awaiting_payment");
    expect(h.sale.pixStatus.value).toBe("polling");

    await vi.advanceTimersByTimeAsync(2600);

    expect(h.sale.pixStatus.value).toBe("paid");
    expect(h.sale.result.value?.fiscalState).toBe("queued");
    h.handles.dispose();
  });
});

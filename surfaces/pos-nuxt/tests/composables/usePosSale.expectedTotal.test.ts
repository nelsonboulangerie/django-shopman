// D42: o fechamento leva o total que a tela mostrou, e a recusa "o total mudou"
// refaz a revisão para o operador conferir com o cliente e finalizar de novo.
import { mockNuxtImport } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "vue-sonner";

import { makeProjection, makeSale } from "./_posSaleHarness";

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));
mockNuxtImport("$fetch", () => fetchMock);
afterEach(() => vi.unstubAllGlobals());
vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

let storageValues: Map<string, string>;
beforeEach(() => {
  storageValues = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => storageValues.get(key) ?? null,
    setItem: (key: string, value: string) => storageValues.set(key, value),
    removeItem: (key: string) => storageValues.delete(key),
  });
  vi.mocked(toast.error).mockClear();
});

function freeCartProjection() {
  return makeProjection({
    checkout: {
      intent_version: 1,
      capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
    } as ReturnType<typeof makeProjection>["checkout"],
  });
}

const CHANGED = "O total mudou de R$ 10,00 para R$ 9,00. Confira com o cliente antes de cobrar.";

/** Revisões em sequência (R$ 10,00 e depois R$ 9,00); o fechamento responde por `closeReplies`. */
function router(closeReplies: Array<() => unknown>) {
  const reviews = [1000, 900];
  let reviewIdx = 0;
  let closeIdx = 0;
  return vi.fn().mockImplementation(async (path: string) => {
    if (String(path).includes("/sale/review/")) {
      const total = reviews[Math.min(reviewIdx++, reviews.length - 1)]!;
      return { review: { total_q: total, total_display: `R$ ${(total / 100).toFixed(2).replace(".", ",")}` } };
    }
    if (String(path).includes("/sale/close/")) return closeReplies[closeIdx++]!();
    return {};
  });
}

function closeBodies(actionCall: ReturnType<typeof vi.fn>) {
  return actionCall.mock.calls
    .filter((call) => String(call[0]).includes("/sale/close/"))
    .map((call) => (call[1] as { body: Record<string, unknown> }).body);
}

function readySale(actionCall: ReturnType<typeof vi.fn>) {
  const h = makeSale({ projection: freeCartProjection(), actionCall });
  const pao = h.handles.posValue.value!.products[0]!;
  h.sale.addProduct(pao);
  h.sale.addProduct(pao);
  return h;
}

describe("usePosSale — total esperado no fechamento (D42)", () => {
  it("o fechamento leva o total que a revisão mostrou, sem mexer nas linhas de pagamento", async () => {
    const actionCall = router([() => ({ ok: true, order_ref: "PED-1" })]);
    const h = readySale(actionCall);

    await h.sale.submitSale(); // prepara: revisão de R$ 10,00
    await h.sale.submitSale(); // fecha

    const [body] = closeBodies(actionCall);
    expect(body).toMatchObject({ expected_total_q: 1000 });
    // Lançamento único não-dinheiro segue mandando só o método: o total é campo à parte.
    expect(body).not.toHaveProperty("payment_tenders");
    expect(h.sale.result.value?.orderRef).toBe("PED-1");
    h.handles.dispose();
  });

  it("a recusa 'o total mudou' mostra os dois valores, refaz a revisão e o novo envio leva o total novo", async () => {
    const actionCall = router([
      () => {
        throw {
          status: 422,
          data: { detail: CHANGED, field: "expected_total_q", error: { code: "total_changed", message: CHANGED } },
        };
      },
      () => ({ ok: true, order_ref: "PED-2" }),
    ]);
    const h = readySale(actionCall);

    await h.sale.submitSale(); // revisão de R$ 10,00
    await h.sale.submitSale(); // recusa: o servidor diz R$ 9,00

    expect(h.sale.result.value).toBeNull();
    // A frase do servidor, com os dois valores, chega ao operador (toast do PDV).
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith(CHANGED);
    expect(h.sale.checkoutMode.value).toBe(true);
    // A revisão foi refeita: a tela agora mostra o total do servidor.
    expect(h.sale.review.value?.total_q).toBe(900);
    expect(h.sale.paymentTotalQ.value).toBe(900);
    expect(h.sale.cart.items).toHaveLength(1);
    // Recusa 4xx sem pedido: a trava local de cobrança fica livre para o novo envio.
    expect(storageValues.size).toBe(0);

    await h.sale.submitSale(); // o operador conferiu e finaliza de novo

    expect(closeBodies(actionCall).map((body) => body.expected_total_q)).toEqual([1000, 900]);
    expect(h.sale.result.value?.orderRef).toBe("PED-2");
    h.handles.dispose();
  });
});

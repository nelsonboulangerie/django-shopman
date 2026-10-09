// TOTAL QUE AINDA PODE MUDAR NÃO É O TOTAL (regra do dono). Enquanto a revisão
// do servidor não volta para o carrinho ATUAL, o total está "calculando": não há
// número confirmado, a forma de pagamento não lança linha e o Validar não fecha.
//
// A corrida que isto trava: o operador muda o desconto, a revisão sai; muda de
// novo com ela em voo. A resposta da PRIMEIRA mudança chegava depois e era
// gravada como o total confirmado: a tela mostrava o total sem o último
// desconto, o Validar liberava, e a maquininha era passada pelo valor errado
// (o fechamento só recusava depois, com o cartão já cobrado).
import { mockNuxtImport } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { toast } from "vue-sonner";

import { makeProjection, makeSale } from "./_posSaleHarness";

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));
mockNuxtImport("$fetch", () => fetchMock);
vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

let storageValues: Map<string, string>;
beforeEach(() => {
  vi.useFakeTimers();
  storageValues = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => storageValues.get(key) ?? null,
    setItem: (key: string, value: string) => storageValues.set(key, value),
    removeItem: (key: string) => storageValues.delete(key),
  });
  vi.mocked(toast.info).mockClear();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function freeCartProjection() {
  return makeProjection({
    checkout: {
      intent_version: 1,
      capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
    } as ReturnType<typeof makeProjection>["checkout"],
  });
}

type Deferred = { body: Record<string, unknown>; resolve: (value: unknown) => void; reject: (error: unknown) => void };

/** Cada revisão fica pendurada até o teste responder; o fechamento responde na hora. */
function controlledServer() {
  const reviews: Deferred[] = [];
  const closes: Array<Record<string, unknown>> = [];
  const actionCall = vi.fn().mockImplementation((path: string, options?: { body?: Record<string, unknown> }) => {
    if (String(path).includes("/sale/review/")) {
      return new Promise((resolve, reject) => reviews.push({ body: options?.body ?? {}, resolve, reject }));
    }
    if (String(path).includes("/sale/close/")) {
      closes.push(options?.body ?? {});
      return Promise.resolve({ ok: true, order_ref: `PED-${closes.length}` });
    }
    return Promise.resolve({});
  });
  return { actionCall, reviews, closes };
}

const totalOf = (q: number) => ({ review: { total_q: q, total_display: `R$ ${(q / 100).toFixed(2).replace(".", ",")}` } });

/** Dois pães (R$ 10,00), checkout aberto com a primeira revisão respondida. */
async function openCheckout() {
  const server = controlledServer();
  const h = makeSale({ projection: freeCartProjection(), actionCall: server.actionCall });
  const pao = h.handles.posValue.value!.products[0]!;
  h.sale.addProduct(pao);
  h.sale.addProduct(pao);
  const opening = h.sale.submitSale(); // abre o checkout e pede a revisão
  await vi.advanceTimersByTimeAsync(0);
  server.reviews[0]!.resolve(totalOf(1000));
  await opening;
  await vi.advanceTimersByTimeAsync(0);
  expect(h.sale.totalStatus.value).toBe("confirmed");
  return { h, server };
}

async function setDiscount(h: ReturnType<typeof makeSale>, percent: string) {
  h.sale.cart.discountType = "percent";
  h.sale.cart.discountValue = percent;
  await nextTick();
}

describe("usePosSale — total pendente nunca vira total confirmado", () => {
  it("mudou o desconto: o total fica 'calculando' até a revisão nova chegar", async () => {
    const { h, server } = await openCheckout();

    await setDiscount(h, "10");
    expect(h.sale.totalStatus.value).toBe("calculating");
    expect(h.sale.review.value).toBeNull();

    await vi.advanceTimersByTimeAsync(450);
    expect(server.reviews).toHaveLength(2);
    expect(h.sale.totalStatus.value).toBe("calculating");

    server.reviews[1]!.resolve(totalOf(900));
    await vi.advanceTimersByTimeAsync(0);
    expect(h.sale.totalStatus.value).toBe("confirmed");
    expect(h.sale.review.value?.total_q).toBe(900);
    h.handles.dispose();
  });

  it("a resposta de um desconto já trocado é descartada, e a do desconto atual é pedida", async () => {
    const { h, server } = await openCheckout();

    await setDiscount(h, "10");
    await vi.advanceTimersByTimeAsync(450); // revisão A (10%) em voo
    expect(server.reviews).toHaveLength(2);

    await setDiscount(h, "20"); // muda de novo com A em voo
    await vi.advanceTimersByTimeAsync(450); // a revisão B espera a vez (A em voo)
    expect(server.reviews).toHaveLength(2);

    server.reviews[1]!.resolve(totalOf(900)); // A volta: carrinho velho
    await vi.advanceTimersByTimeAsync(0);
    // O total de A NÃO aparece como confirmado.
    expect(h.sale.review.value).toBeNull();
    expect(h.sale.totalStatus.value).toBe("calculating");

    await vi.advanceTimersByTimeAsync(200);
    expect(server.reviews).toHaveLength(3); // B pedida com o desconto atual
    expect(server.reviews[2]!.body).toMatchObject({ manual_discount: { value: 20 } });

    server.reviews[2]!.resolve(totalOf(800));
    await vi.advanceTimersByTimeAsync(0);
    expect(h.sale.totalStatus.value).toBe("confirmed");
    expect(h.sale.review.value?.total_q).toBe(800);
    h.handles.dispose();
  });

  it("Validar durante o cálculo não fecha; o fechamento leva SEMPRE o total confirmado", async () => {
    const { h, server } = await openCheckout();

    await setDiscount(h, "10");
    await vi.advanceTimersByTimeAsync(450);

    // Enter/Validar com o total em cálculo: nada fecha.
    const early = h.sale.submitSale();
    await vi.advanceTimersByTimeAsync(0);
    expect(server.closes).toHaveLength(0);

    server.reviews[1]!.resolve(totalOf(900));
    await early;
    await vi.advanceTimersByTimeAsync(0);
    expect(server.closes).toHaveLength(0);
    expect(h.sale.totalStatus.value).toBe("confirmed");

    await h.sale.submitSale();
    expect(server.closes).toHaveLength(1);
    expect(server.closes[0]).toMatchObject({ expected_total_q: 900 });
    h.handles.dispose();
  });

  it("forma de pagamento e Exato não lançam pelo total em cálculo", async () => {
    const { h } = await openCheckout();
    h.sale.addTender("cash");
    expect(h.sale.cart.paymentTenders).toHaveLength(1);

    await setDiscount(h, "10");
    h.sale.addTender("card");
    h.sale.tenderExact();
    expect(h.sale.cart.paymentTenders).toHaveLength(1);
    expect(h.sale.cart.paymentTenders[0]!.amount_q).toBe(1000);
    expect(toast.info).toHaveBeenCalledWith("Calculando o total. A forma libera assim que ele chegar.");
    expect(h.sale.splitNote.value).toBe("");
    h.handles.dispose();
  });

  it("a revisão que falha guarda o motivo, e Tentar de novo refaz e confirma", async () => {
    const { h, server } = await openCheckout();

    await setDiscount(h, "10");
    await vi.advanceTimersByTimeAsync(450);
    server.reviews[1]!.reject({ status: 503, data: { detail: "O servidor está ocupado. Tente em instantes." } });
    await vi.advanceTimersByTimeAsync(0);

    expect(h.sale.totalStatus.value).toBe("failed");
    expect(h.sale.reviewFailureReason.value).toBe("O servidor está ocupado. Tente em instantes.");

    const retry = h.sale.submitSale(); // o botão "Tentar de novo"
    await vi.advanceTimersByTimeAsync(0);
    expect(server.closes).toHaveLength(0);
    server.reviews[2]!.resolve(totalOf(900));
    await retry;

    expect(h.sale.totalStatus.value).toBe("confirmed");
    expect(h.sale.reviewFailureReason.value).toBe("");
    expect(server.closes).toHaveLength(0);
    h.handles.dispose();
  });
});

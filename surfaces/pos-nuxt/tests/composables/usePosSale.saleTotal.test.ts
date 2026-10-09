// O TOTAL DA VENDA, ANTES DO PAGAMENTO, TAMBÉM É O DO SERVIDOR (regra do dono,
// 09/10/2026). O botão do Pagamento (F4) e o "Pagar" da folha da mesa
// mostravam a soma local do carrinho, que não sabe do desconto automático, da
// taxa de entrega nem do desconto manual que o servidor descarta. Agora a
// revisão é pedida em silêncio a cada mudança; até ela voltar para o carrinho
// ATUAL, o total é "calculando" e não tem número.
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
  vi.mocked(toast.error).mockClear();
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

function controlledServer() {
  const reviews: Deferred[] = [];
  const actionCall = vi.fn().mockImplementation((path: string, options?: { body?: Record<string, unknown> }) => {
    if (String(path).includes("/sale/review/")) {
      return new Promise((resolve, reject) => reviews.push({ body: options?.body ?? {}, resolve, reject }));
    }
    return Promise.resolve({});
  });
  return { actionCall, reviews };
}

const totalOf = (q: number) => ({ review: { total_q: q, total_display: `R$ ${(q / 100).toFixed(2).replace(".", ",")}` } });

function setup() {
  const server = controlledServer();
  const h = makeSale({ projection: freeCartProjection(), actionCall: server.actionCall });
  const pao = h.handles.posValue.value!.products[0]!;
  return { h, server, pao };
}

describe("usePosSale — o total da venda vem da revisão, não da soma local", () => {
  it("carrinho vazio: não há total a mostrar, e nada é pedido ao servidor", async () => {
    const { h, server } = setup();
    expect(h.sale.saleTotal.value.status).toBe("hidden");
    await vi.advanceTimersByTimeAsync(1000);
    expect(server.reviews).toHaveLength(0);
    h.handles.dispose();
  });

  it("lançou um item: calculando sem número até a revisão chegar; depois, o número do servidor", async () => {
    const { h, server, pao } = setup();
    h.sale.addProduct(pao);
    await nextTick();
    expect(h.sale.saleTotal.value).toEqual({ status: "calculating", display: "" });

    await vi.advanceTimersByTimeAsync(450);
    expect(server.reviews).toHaveLength(1);
    expect(h.sale.saleTotal.value.status).toBe("calculating");

    // O servidor diz 4,50 (um desconto automático que a soma local não vê).
    server.reviews[0]!.resolve(totalOf(450));
    await vi.advanceTimersByTimeAsync(0);
    expect(h.sale.saleTotal.value).toEqual({ status: "confirmed", display: "R$ 4,50" });
    h.handles.dispose();
  });

  it("lançamentos rápidos viram UMA revisão (debounce), e a resposta de um carrinho já trocado é descartada", async () => {
    const { h, server, pao } = setup();
    h.sale.addProduct(pao);
    await nextTick();
    await vi.advanceTimersByTimeAsync(200);
    h.sale.addProduct(pao);
    await nextTick();
    await vi.advanceTimersByTimeAsync(450);
    expect(server.reviews).toHaveLength(1);

    h.sale.addProduct(pao); // muda com a revisão em voo
    await nextTick();
    server.reviews[0]!.resolve(totalOf(1000)); // a resposta é do carrinho de 2 pães
    await vi.advanceTimersByTimeAsync(0);
    expect(h.sale.saleTotal.value.status).toBe("calculating");

    await vi.advanceTimersByTimeAsync(450);
    expect(server.reviews).toHaveLength(2);
    server.reviews[1]!.resolve(totalOf(1500));
    await vi.advanceTimersByTimeAsync(0);
    expect(h.sale.saleTotal.value).toEqual({ status: "confirmed", display: "R$ 15,00" });
    h.handles.dispose();
  });

  it("a revisão falhou: 'failed' sem número e sem toast (o Pagamento diz o motivo)", async () => {
    const { h, server, pao } = setup();
    h.sale.addProduct(pao);
    await nextTick();
    await vi.advanceTimersByTimeAsync(450);
    server.reviews[0]!.reject(new Error("rede"));
    await vi.advanceTimersByTimeAsync(0);
    expect(h.sale.saleTotal.value).toEqual({ status: "failed", display: "" });
    expect(toast.error).not.toHaveBeenCalled();

    // A próxima mudança tenta de novo.
    h.sale.addProduct(pao);
    await nextTick();
    expect(h.sale.saleTotal.value.status).toBe("calculating");
    await vi.advanceTimersByTimeAsync(450);
    expect(server.reviews).toHaveLength(2);
    h.handles.dispose();
  });

  it("a revisão silenciosa não mexe no clientRequestId do carrinho nem trava a tela", async () => {
    const { h, server, pao } = setup();
    h.sale.addProduct(pao);
    await nextTick();
    const before = h.sale.cart.clientRequestId;
    await vi.advanceTimersByTimeAsync(450);
    expect(server.reviews).toHaveLength(1);
    expect(h.sale.busy.value).toBe(false);
    expect(h.sale.cart.clientRequestId).toBe(before);
    server.reviews[0]!.resolve(totalOf(500));
    await vi.advanceTimersByTimeAsync(0);
    h.handles.dispose();
  });

  it("edição de encomenda: a revisão de venda fica parada e o total, escondido", async () => {
    const { h, server, pao } = setup();
    h.sale.saleTotalPaused.value = true;
    h.sale.addProduct(pao);
    await nextTick();
    await vi.advanceTimersByTimeAsync(1000);
    expect(server.reviews).toHaveLength(0);
    expect(h.sale.saleTotal.value.status).toBe("hidden");
    h.handles.dispose();
  });
});

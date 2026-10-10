// A venda de balcão SEM CONEXÃO (WP-PDV-SEM-CONEXAO): o total sai da última
// leitura, a venda vai para a fila com o mesmo `close_sale` e a tela de resultado
// diz que ela está guardada. A rede caindo NO MEIO do fechamento também vai para
// a fila, com a mesma chave, em vez de travar o balcão.
import { mockNuxtImport } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "vue-sonner";

import { makeProjection, makeSale } from "./_posSaleHarness";
import { usePosOfflineSales } from "~/composables/usePosOfflineSales";

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));
mockNuxtImport("$fetch", () => fetchMock);
vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

let online = true;
let storageValues: Map<string, string>;
beforeEach(() => {
  online = true;
  Object.defineProperty(globalThis.navigator, "onLine", { configurable: true, get: () => online });
  storageValues = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => storageValues.get(key) ?? null,
    setItem: (key: string, value: string) => storageValues.set(key, value),
    removeItem: (key: string) => storageValues.delete(key),
  });
  vi.mocked(toast.error).mockClear();
});
afterEach(() => vi.unstubAllGlobals());

function freeCartProjection() {
  return makeProjection({
    checkout: {
      intent_version: 1,
      capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
    } as ReturnType<typeof makeProjection>["checkout"],
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

describe("usePosSale — venda sem conexão", () => {
  it("sem conexão: total da última leitura, venda guardada, resultado diz que está no dispositivo", async () => {
    const actionCall = vi.fn().mockRejectedValue({ status: 0 });
    const h = readySale(actionCall);
    online = false;

    await h.sale.submitSale(); // abre o Pagamento: revisão local
    expect(h.sale.review.value?.total_q).toBe(1000);
    expect(h.sale.review.value?.offline?.prices_at).toBeTruthy();
    h.sale.addTender("cash");
    await h.sale.submitSale(); // finaliza: vai para a fila

    // Nada foi ao servidor: nem revisão nem fechamento.
    expect(closeBodies(actionCall)).toHaveLength(0);
    expect(h.sale.result.value?.offline?.capturedAt).toBeTruthy();
    expect(h.sale.result.value?.orderRef).toMatch(/^Sem conexão /);
    expect(h.sale.cart.items).toHaveLength(0);
    // Sem trava de cobrança incerta: a venda está na fila, não em dúvida.
    expect(storageValues.size).toBe(0);
    h.handles.dispose();
  });

  it("sem conexão, Pix não fecha: o motivo diz para receber em dinheiro ou na maquininha", async () => {
    const actionCall = vi.fn().mockRejectedValue({ status: 0 });
    const h = readySale(actionCall);
    online = false;

    await h.sale.submitSale();
    h.sale.addTender("pix");
    await h.sale.submitSale();

    expect(h.sale.result.value).toBeNull();
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith("Pix precisa de conexão. Receba em dinheiro ou na maquininha.");
    expect(h.sale.cart.items).toHaveLength(1);
    h.handles.dispose();
  });

  it("a rede cai no meio do fechamento: a venda vai para a fila com a MESMA chave", async () => {
    const actionCall = vi.fn().mockImplementation(async (path: string) => {
      if (String(path).includes("/sale/review/")) return { review: { total_q: 1000, total_display: "R$ 10,00" } };
      if (String(path).includes("/sale/close/")) {
        online = false; // o cabo saiu com o POST em voo
        throw { status: 0 };
      }
      return {};
    });
    const h = readySale(actionCall);

    await h.sale.submitSale(); // revisão do servidor
    h.sale.addTender("cash");
    await h.sale.submitSale(); // POST sai e a rede cai

    const [sentOnce] = closeBodies(actionCall);
    expect(sentOnce?.client_request_id).toBeTruthy();
    expect(h.sale.result.value?.offline).toBeTruthy();
    // O marcador de resultado incerto saiu: a fila reenvia a mesma chave, e o
    // servidor devolve a venda se ela tiver nascido.
    expect(storageValues.size).toBe(0);
    expect(h.sale.result.value?.orderRef).toContain(String(sentOnce?.client_request_id).replace(/[^a-zA-Z0-9]/g, "").slice(-4).toUpperCase());
    h.handles.dispose();
  });

  it("sem conexão, comanda livre abre só na tela e a venda sobe como balcão direto", async () => {
    const actionCall = vi.fn().mockRejectedValue({ status: 0 });
    const h = makeSale({ projection: freeCartProjection(), actionCall });
    h.handles.tabsValue.value = [
      { ref: "15", display_ref: "15", session_key: "", state: "empty" } as never,
      { ref: "12", display_ref: "12", session_key: "S-12", state: "in_use" } as never,
    ];
    online = false;

    await h.sale.openTab("12");
    expect(h.sale.inSaleView.value).toBe(false);
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith("Sem conexão, a comanda 12 não abre: ela está em uso. Escolha uma comanda livre.");

    await h.sale.openTab("15");
    expect(h.sale.inSaleView.value).toBe(true);
    expect(h.sale.cart.tabDisplay).toBe("15");
    // Nada foi pedido ao servidor para abrir.
    expect(actionCall.mock.calls.filter((call) => String(call[0]).includes("/tabs/"))).toHaveLength(0);

    h.sale.addProduct(h.handles.posValue.value!.products[0]!);
    await h.sale.submitSale();
    h.sale.addTender("cash");
    await h.sale.submitSale();

    expect(h.sale.result.value?.offline).toBeTruthy();
    expect(h.sale.result.value?.receipt.tabDisplay).toBe("15");
    // O corpo guardado é o de uma venda de balcão direta: sem comanda, com a hora.
    const queued = usePosOfflineSales().sales.value.at(-1)!;
    expect(queued.body.tab_ref).toBeFalsy();
    expect(queued.body.tab_session_key).toBeFalsy();
    expect(queued.body.offline_captured_at).toBe(queued.capturedAt);
    expect(queued.body.expected_total_q).toBe(500);
    h.handles.dispose();
  });
});

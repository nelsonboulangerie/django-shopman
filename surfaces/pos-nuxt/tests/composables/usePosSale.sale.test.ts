import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockNuxtImport } from "@nuxt/test-utils/runtime";
import { toast } from "vue-sonner";

import { makeProjection, makeSale, makeTabPayload } from "./_posSaleHarness";

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));
mockNuxtImport("$fetch", () => fetchMock);
vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

function freeCartProjection() {
  return makeProjection({
    checkout: {
      intent_version: 1,
      capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
    } as ReturnType<typeof makeProjection>["checkout"],
  });
}

// Router de action.call por caminho: review devolve um review; close devolve ok.
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

/** Carrinho pronto para checkout (2 pães = R$ 10,00, sem comanda). */
function saleReadyForCheckout(actionCall: ReturnType<typeof vi.fn>) {
  const h = makeSale({ projection: freeCartProjection(), actionCall });
  const pao = h.handles.posValue.value!.products[0]!;
  h.sale.addProduct(pao);
  h.sale.addProduct(pao);
  return h;
}

describe("usePosSale — submitSale (fluxo em etapas)", () => {
  beforeEach(() => {
    vi.mocked(toast.error).mockClear();
  });

  it("guarda de reentrância: não dispara nada enquanto busy", async () => {
    const actionCall = saleRouter();
    const h = saleReadyForCheckout(actionCall);
    h.sale.busy.value = true;
    await h.sale.submitSale();
    expect(actionCall).not.toHaveBeenCalled();
    h.handles.dispose();
  });

  it("primeiro clique prepara (review + checkoutMode), não fecha", async () => {
    const actionCall = saleRouter();
    const h = saleReadyForCheckout(actionCall);

    await h.sale.submitSale();

    expect(h.sale.checkoutMode.value).toBe(true);
    expect(h.sale.review.value?.total_q).toBe(1000);
    const closeCalls = actionCall.mock.calls.filter((c) => String(c[0]).includes("/sale/close/"));
    expect(closeCalls).toHaveLength(0);
    h.handles.dispose();
  });

  it("segundo clique fecha a venda, congela o recibo e limpa o carrinho", async () => {
    const actionCall = saleRouter(null);
    const h = saleReadyForCheckout(actionCall);

    await h.sale.submitSale(); // prepara
    await h.sale.submitSale(); // fecha

    expect(h.sale.result.value?.orderRef).toBe("PED-1");
    // Recibo congelado ANTES do reset: 1 linha (pão), total do review.
    expect(h.sale.result.value?.receipt.items).toHaveLength(1);
    expect(h.sale.result.value?.receipt.items[0]).toMatchObject({ qty: 2, price_q: 500 });
    expect(h.sale.result.value?.receipt.totalDisplay).toBe("R$ 10,00");
    // Carrinho zerado após finalizar.
    expect(h.sale.cart.items).toHaveLength(0);
    expect(h.handles.refresh).toHaveBeenCalled();
    h.handles.dispose();
  });

  it("review obsoleto (stale) volta a revisar em vez de fechar", async () => {
    const actionCall = saleRouter(null);
    const h = saleReadyForCheckout(actionCall);
    await h.sale.submitSale(); // checkoutMode + review
    h.sale.review.value = null; // simula dado de venda mudado → review invalidado

    await h.sale.submitSale();

    const closeCalls = actionCall.mock.calls.filter((c) => String(c[0]).includes("/sale/close/"));
    expect(closeCalls).toHaveLength(0); // re-revisou, não fechou
    h.handles.dispose();
  });

  it("falha no fechamento acende toast e preserva o carrinho", async () => {
    const actionCall = vi.fn().mockImplementation(async (path: string) => {
      if (String(path).includes("/sale/review/")) return { review: { total_q: 1000, total_display: "R$ 10,00" } };
      if (String(path).includes("/sale/close/")) throw { data: { detail: "Caixa fechado" } };
      return {};
    });
    const h = saleReadyForCheckout(actionCall);
    await h.sale.submitSale(); // prepara
    await h.sale.submitSale(); // tenta fechar → erro

    expect(h.sale.result.value).toBeNull();
    expect(h.sale.busy.value).toBe(false);
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith("Caixa fechado");
    expect(h.sale.cart.items).toHaveLength(1); // 1 linha (pão x2) — nada perdido
    expect(h.sale.cart.items[0]!.qty).toBe(2);
    h.handles.dispose();
  });

  it("venda fechada aponta 'Abrir no gestor' para o orders app (não o Django admin)", async () => {
    const actionCall = saleRouter(null);
    const h = saleReadyForCheckout(actionCall);
    await h.sale.submitSale(); // prepara
    await h.sale.submitSale(); // fecha
    expect(h.sale.result.value?.nextUrl).toBe("http://gestor.test/PED-1");
    h.handles.dispose();
  });

  it("congela o troco no result — o resetCart apagaria o troco computado", async () => {
    const actionCall = saleRouter(null);
    const h = saleReadyForCheckout(actionCall);
    await h.sale.submitSale(); // prepara (review R$ 10,00)
    h.sale.tenderAdd(2000); // cliente entregou R$ 20,00 em dinheiro
    expect(h.sale.paymentChangeQ.value).toBe(1000);

    await h.sale.submitSale(); // fecha

    expect(h.sale.result.value?.changeQ).toBe(1000); // congelado no commit
    expect(h.sale.paymentChangeQ.value).toBe(0); // o cart já resetou por baixo
    h.handles.dispose();
  });

  it("venda exata não inventa troco no result", async () => {
    const actionCall = saleRouter(null);
    const h = saleReadyForCheckout(actionCall);
    await h.sale.submitSale();
    h.sale.tenderAdd(1000); // exato
    await h.sale.submitSale();
    expect(h.sale.result.value?.changeQ).toBe(0);
    h.handles.dispose();
  });
});

describe("usePosSale — checkout otimista (sem flash)", () => {
  beforeEach(() => {
    vi.mocked(toast.error).mockClear();
  });

  it("o shell de pagamento abre ANTES da review resolver", async () => {
    let resolveReview!: (value: unknown) => void;
    const actionCall = vi.fn().mockImplementation((path: string) => {
      if (String(path).includes("/sale/review/")) {
        return new Promise((resolve) => { resolveReview = resolve; });
      }
      return Promise.resolve({});
    });
    const h = saleReadyForCheckout(actionCall);

    const pending = h.sale.submitSale();
    expect(h.sale.checkoutMode.value).toBe(true); // shell já aberto, review por baixo
    expect(h.sale.review.value).toBeNull();

    resolveReview({ review: { total_q: 1000, total_display: "R$ 10,00" } });
    await pending;
    expect(h.sale.review.value?.total_q).toBe(1000);
    h.handles.dispose();
  });

  it("falha na review devolve o operador à venda (sem shell órfão)", async () => {
    const actionCall = vi.fn().mockImplementation(async (path: string) => {
      if (String(path).includes("/sale/review/")) throw { data: { detail: "Sem preço" } };
      return {};
    });
    const h = saleReadyForCheckout(actionCall);

    await h.sale.submitSale();

    expect(h.sale.checkoutMode.value).toBe(false);
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith("Sem preço");
    h.handles.dispose();
  });

  it("entrada de pagamento digitada durante o load do checkout não é perdida", async () => {
    let resolveOpen!: (value: unknown) => void;
    const actionCall = vi.fn().mockImplementation((path: string) => {
      const p = String(path);
      if (p.includes("/tabs/save/")) return Promise.resolve({});
      if (p.includes("/open/")) return new Promise((resolve) => { resolveOpen = resolve; });
      if (p.includes("/sale/review/")) return Promise.resolve({ review: { total_q: 1000, total_display: "R$ 10,00" } });
      return Promise.resolve({});
    });
    const h = makeSale({ projection: freeCartProjection(), actionCall });
    Object.assign(h.sale.cart, { tabRef: "M1", tabDisplay: "M1", tabSessionKey: "sess-1" });
    const pao = h.handles.posValue.value!.products[0]!;
    h.sale.addProduct(pao);

    const pending = h.sale.submitSale(); // shell aberto, reload da comanda pendente
    expect(h.sale.checkoutMode.value).toBe(true);
    await vi.waitFor(() => {
      if (!resolveOpen) throw new Error("open_tab ainda não chamado");
    });
    // Operador já lança dinheiro + valor enquanto a comanda recarrega por baixo.
    h.sale.cart.paymentMethod = "cash";
    h.sale.cart.paymentTenders.push({ method: "cash", amount_q: 2000 });
    h.sale.cart.tenderedAmountInput = "20,00";

    resolveOpen(makeTabPayload({
      items: [{ sku: "PAO", name: "Pão", qty: 2, unit_price_q: 500, price_q: 500 }],
    }));
    await pending;

    expect(h.sale.cart.paymentTenders).toHaveLength(1); // entrada preservada
    expect(h.sale.cart.tenderedAmountInput).toBe("20,00");
    expect(h.sale.cart.paymentMethod).toBe("cash");
    h.handles.dispose();
  });

  it("com comanda aberta, o reload da comanda não derruba o checkout otimista", async () => {
    const actionCall = vi.fn().mockImplementation(async (path: string) => {
      const p = String(path);
      if (p.includes("/tabs/save/")) return {};
      if (p.includes("/open/")) {
        return makeTabPayload({
          items: [{ sku: "PAO", name: "Pão", qty: 2, unit_price_q: 500, price_q: 500 }],
        });
      }
      if (p.includes("/sale/review/")) return { review: { total_q: 1000, total_display: "R$ 10,00" } };
      return {};
    });
    const h = makeSale({ projection: freeCartProjection(), actionCall });
    Object.assign(h.sale.cart, { tabRef: "M1", tabDisplay: "M1", tabSessionKey: "sess-1" });
    const pao = h.handles.posValue.value!.products[0]!;
    h.sale.addProduct(pao);

    await h.sale.submitSale(); // prepara: persiste + recarrega + review, tudo por baixo

    expect(h.sale.checkoutMode.value).toBe(true);
    expect(h.sale.review.value?.total_q).toBe(1000);
    h.handles.dispose();
  });
});

describe("usePosSale — PIX polling pós-venda", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    fetchMock.mockReset();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  const pixProof = { method: "pix", amount_q: 1000, amount_display: "R$ 10,00", qr_code: "QRDATA", status: "pending" };

  it("polling → 'paid' quando o status vira is_paid, e então para", async () => {
    fetchMock.mockResolvedValue({ is_paid: true });
    const actionCall = saleRouter(pixProof);
    const h = saleReadyForCheckout(actionCall);

    await h.sale.submitSale(); // prepara
    await h.sale.submitSale(); // fecha → inicia polling
    expect(h.sale.pixStatus.value).toBe("polling");

    await vi.advanceTimersByTimeAsync(2500); // 1º poll
    expect(fetchMock).toHaveBeenCalled();
    expect(String(fetchMock.mock.calls[0]![0])).toContain("/pos/payment/PED-1/status/");
    expect(h.sale.pixStatus.value).toBe("paid");

    // Confirmado → o polling parou (não chama mais).
    const callsAfter = fetchMock.mock.calls.length;
    await vi.advanceTimersByTimeAsync(5000);
    expect(fetchMock.mock.calls.length).toBe(callsAfter);
    h.handles.dispose();
  });

  it("estado terminal (cancelado/expirado) vira 'expired' — não mente 'aguardando'", async () => {
    fetchMock.mockResolvedValue({ is_terminal: true });
    const actionCall = saleRouter(pixProof);
    const h = saleReadyForCheckout(actionCall);

    await h.sale.submitSale();
    await h.sale.submitSale();
    await vi.advanceTimersByTimeAsync(2500);

    expect(h.sale.pixStatus.value).toBe("expired");
    const calls = fetchMock.mock.calls.length;
    await vi.advanceTimersByTimeAsync(5000);
    expect(fetchMock.mock.calls.length).toBe(calls); // parou
    h.handles.dispose();
  });

  it("timeout (~10 min sem resolução) desiste com 'expired'", async () => {
    fetchMock.mockResolvedValue({}); // nunca is_paid/is_terminal
    const actionCall = saleRouter(pixProof);
    const h = saleReadyForCheckout(actionCall);

    await h.sale.submitSale();
    await h.sale.submitSale();
    expect(h.sale.pixStatus.value).toBe("polling");

    // 241 tentativas a 2,5s → passa do teto de 240 e desiste.
    await vi.advanceTimersByTimeAsync(241 * 2500);
    expect(h.sale.pixStatus.value).toBe("expired");
    h.handles.dispose();
  });

  it("sair da tela de resultado com PIX aguardando vira chip e o polling SEGUE", async () => {
    fetchMock.mockResolvedValue({}); // nunca resolve neste teste
    const actionCall = saleRouter(pixProof);
    const h = saleReadyForCheckout(actionCall);
    await h.sale.submitSale();
    await h.sale.submitSale();
    expect(h.sale.pixStatus.value).toBe("polling");

    h.sale.dismissResult(); // toque explícito no CTA

    expect(h.sale.result.value).toBeNull();
    expect(h.sale.pendingPixOrderRef.value).toBe("PED-1"); // prova não descartada
    const before = fetchMock.mock.calls.length;
    await vi.advanceTimersByTimeAsync(2500);
    expect(fetchMock.mock.calls.length).toBeGreaterThan(before); // polling vivo
    h.handles.dispose();
  });

  it("o chip pendente resolve em voz alta: confirmou → toast e chip sai", async () => {
    fetchMock.mockResolvedValue({ is_paid: true });
    const actionCall = saleRouter(pixProof);
    const h = saleReadyForCheckout(actionCall);
    await h.sale.submitSale();
    await h.sale.submitSale();
    h.sale.dismissResult();
    vi.mocked(toast.success).mockClear();

    await vi.advanceTimersByTimeAsync(2500);

    expect(h.sale.pixStatus.value).toBe("paid");
    expect(h.sale.pendingPixOrderRef.value).toBe("");
    expect(vi.mocked(toast.success)).toHaveBeenCalledWith("PIX do pedido PED-1 confirmado.");
    h.handles.dispose();
  });

  it("dismissResult sem PIX pendente encerra o polling e volta a 'idle'", async () => {
    fetchMock.mockResolvedValue({ is_paid: true });
    const actionCall = saleRouter(pixProof);
    const h = saleReadyForCheckout(actionCall);
    await h.sale.submitSale();
    await h.sale.submitSale();
    await vi.advanceTimersByTimeAsync(2500); // confirma antes de sair
    expect(h.sale.pixStatus.value).toBe("paid");

    h.sale.dismissResult();

    expect(h.sale.pendingPixOrderRef.value).toBe(""); // nada pendente
    expect(h.sale.pixStatus.value).toBe("idle");
    h.handles.dispose();
  });

  it("métodos sem prova (dinheiro) não iniciam polling → 'idle'", async () => {
    const actionCall = saleRouter(null); // sem payment proof
    const h = saleReadyForCheckout(actionCall);
    await h.sale.submitSale();
    await h.sale.submitSale();
    await vi.advanceTimersByTimeAsync(5000);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(h.sale.pixStatus.value).toBe("idle");
    h.handles.dispose();
  });
});

// ── Gaveta na venda em dinheiro ──────────────────────────────────────────

const AGENT_DRAWER = {
  adapter: "agent",
  can_kick: true,
  open_on_cash_sale: true,
  agent_url: "http://127.0.0.1:47811",
  token: "token-do-balcao",
  pulse: { pin: 0, on_ms: 50, off_ms: 500 },
};

/** Carrinho pronto para checkout num balcão com o agente local instalado. */
async function saleWithDrawer(actionCall: ReturnType<typeof vi.fn>, drawer = AGENT_DRAWER) {
  const projection = makeProjection({
    checkout: {
      intent_version: 1,
      capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
    } as ReturnType<typeof makeProjection>["checkout"],
    cash_drawer: drawer as ReturnType<typeof makeProjection>["cash_drawer"],
  });
  const h = makeSale({ projection, actionCall });
  const pao = h.handles.posValue.value!.products[0]!;
  // ⚠️ `await`: com agente no balcão, o PRIMEIRO item de uma venda sem comanda
  // passa pela trava da gaveta (é o "iniciar a venda" deste fluxo), e a leitura
  // do sensor é assíncrona. Sem esperar, o carrinho ainda está vazio aqui.
  h.sale.addProduct(pao);
  await flushDrawerRead();
  return h;
}

/** Dá tempo à leitura do sensor (loopback) antes de seguir. */
async function flushDrawerRead(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe("usePosSale — a gaveta na venda em dinheiro", () => {
  let kicks: string[];

  beforeEach(() => {
    kicks = [];
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
      // A leitura da gaveta (`GET /drawer`) atravessa o mesmo agente desde que a
      // trava passou a morder no primeiro item da venda sem comanda. Ela não é
      // um chute: responder aqui mantém `kicks` sendo só o que ABRE a gaveta.
      if (String(url).endsWith("/drawer")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ known: true, calibrated: true, open: false, raw: "0x16" }),
        });
      }
      kicks.push(JSON.parse(init!.body as string).reason);
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ok: true }) });
    }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("venda em dinheiro abre a gaveta — o momento mais comum de dar troco", async () => {
    const h = await saleWithDrawer(saleRouter());
    h.sale.cart.paymentMethod = "cash";
    h.sale.tenderAdd(1000);

    await h.sale.submitSale(); // prepara
    await h.sale.submitSale(); // fecha

    expect(kicks).toEqual(["cash_sale"]);
    h.handles.dispose();
  });

  it("venda sem dinheiro NÃO abre a gaveta", async () => {
    const h = await saleWithDrawer(saleRouter());
    h.sale.cart.paymentMethod = "pix";

    await h.sale.submitSale();
    await h.sale.submitSale();

    expect(kicks).toEqual([]);
    h.handles.dispose();
  });

  it("o dono pode desligar a abertura automática sem perder o botão manual", async () => {
    const h = await saleWithDrawer(saleRouter(), { ...AGENT_DRAWER, open_on_cash_sale: false });
    h.sale.cart.paymentMethod = "cash";
    h.sale.tenderAdd(1000);

    await h.sale.submitSale();
    await h.sale.submitSale();

    expect(kicks).toEqual([]);
    h.handles.dispose();
  });

  it("balcão de gaveta com chave não bate no agente", async () => {
    const h = await saleWithDrawer(saleRouter(), {
      adapter: "manual", can_kick: false, open_on_cash_sale: false,
    } as typeof AGENT_DRAWER);
    h.sale.cart.paymentMethod = "cash";
    h.sale.tenderAdd(1000);

    await h.sale.submitSale();
    await h.sale.submitSale();

    expect(kicks).toEqual([]);
    h.handles.dispose();
  });
});


// ── A trava tem que morder na venda que ESTE balcão faz ───────────────────
//
// A trava nasceu presa ao `openTab`, descrito como "o único portão de entrada
// na venda". Era verdade com comanda obrigatória e deixou de ser: este balcão
// roda `requires_open_tab_for_cart: false`, então a venda comum (toca o
// produto, cobra, entrega) nunca passa por `openTab`. A trava existia e não
// agia justamente na venda que mais acontece — deixar a gaveta aberta não
// custava nada. O trap certo é o PRIMEIRO item de uma venda nova sem comanda.

describe("usePosSale — a trava da gaveta na venda SEM comanda", () => {
  function drawerAnswering(open: boolean) {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (String(url).endsWith("/drawer")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ known: true, calibrated: true, open, raw: open ? "0x12" : "0x16" }),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ok: true }) });
    }));
  }

  function makeTabless() {
    const projection = makeProjection({
      checkout: {
        intent_version: 1,
        capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
      } as ReturnType<typeof makeProjection>["checkout"],
      cash_drawer: AGENT_DRAWER as ReturnType<typeof makeProjection>["cash_drawer"],
    });
    return makeSale({ projection, actionCall: saleRouter() });
  }

  afterEach(() => vi.unstubAllGlobals());

  it("gaveta ABERTA: o primeiro item não entra e o diálogo aparece", async () => {
    drawerAnswering(true);
    const h = makeTabless();

    h.sale.addProduct(h.handles.posValue.value!.products[0]!);
    await flushDrawerRead();

    expect(h.sale.cart.items).toHaveLength(0);
    expect(h.sale.drawerLock.open.value).toBe(true);
    h.handles.dispose();
  });

  it("gaveta FECHADA: o primeiro item entra normalmente", async () => {
    drawerAnswering(false);
    const h = makeTabless();

    h.sale.addProduct(h.handles.posValue.value!.products[0]!);
    await flushDrawerRead();

    expect(h.sale.cart.items).toHaveLength(1);
    expect(h.sale.drawerLock.open.value).toBe(false);
    h.handles.dispose();
  });

  it("venda JÁ começada não vira refém: o 2º item entra com a gaveta aberta", async () => {
    drawerAnswering(false);
    const h = makeTabless();
    h.sale.addProduct(h.handles.posValue.value!.products[0]!);
    await flushDrawerRead();

    drawerAnswering(true); // abriram a gaveta no meio da venda
    h.sale.addProduct(h.handles.posValue.value!.products[1]!);
    await flushDrawerRead();

    expect(h.sale.cart.items).toHaveLength(2);
    expect(h.sale.drawerLock.open.value).toBe(false);
    h.handles.dispose();
  });
});

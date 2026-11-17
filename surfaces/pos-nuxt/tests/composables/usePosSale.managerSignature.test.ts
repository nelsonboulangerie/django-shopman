// WP-E1 (P0-1 e P1-4): a assinatura do gerente vale para o retrato que ele viu
// (comanda, itens, desconto, forma) e nunca fica guardada no navegador.
//
// O defeito provado em 16/11/2026 (venda PDV-261116-U44): a Gerente assinou um
// desconto de R$ 6,00, a Caixa voltou da maquininha, trocou para R$ 30,00 e a
// venda fechou com `approved_by: "joyce"`. A tela guardava usuário e PIN no
// carrinho e os reenviava em todo fechamento; o mesmo corpo ia ao guarda do
// fechamento incerto, no `localStorage`.
import { mockNuxtImport } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

import { makeProjection, makeSale } from "./_posSaleHarness";
import { memoryOfflineSaleStore } from "~/utils/offlineSaleStore";

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));
mockNuxtImport("$fetch", () => fetchMock);
afterEach(() => vi.unstubAllGlobals());
vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

const GUARD_KEY = "shopman:pos:close-outcome-uncertain";
const PIN = "1234";

let storageValues: Map<string, string>;
/** Tudo o que a tela escreveu no `localStorage`, na ordem, inclusive o que já saiu. */
let storageWrites: string[];
beforeEach(() => {
  storageValues = new Map<string, string>();
  storageWrites = [];
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => storageValues.get(key) ?? null,
    setItem: (key: string, value: string) => {
      storageWrites.push(value);
      storageValues.set(key, value);
    },
    removeItem: (key: string) => storageValues.delete(key),
  });
});

function freeCartProjection() {
  return makeProjection({
    checkout: {
      intent_version: 1,
      capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
    } as ReturnType<typeof makeProjection>["checkout"],
  });
}

/** A revisão diz o desconto que o gerente vê; o fechamento responde por `closeReplies`. */
function router(closeReplies: Array<(body: Record<string, unknown>) => unknown>) {
  let closeIdx = 0;
  return vi.fn().mockImplementation(async (path: string, options?: { body?: Record<string, unknown> }) => {
    const body = options?.body || {};
    if (String(path).includes("/sale/review/")) {
      const discount = (body.manual_discount as { value?: number } | undefined)?.value || 0;
      const discountQ = Math.round(discount * 100);
      return {
        review: {
          total_q: 4335 - discountQ,
          total_display: "",
          order_discount_q: discountQ,
          line_discount_q: 0,
          requires_manager_approval: discountQ > 500,
          manager_approval_threshold_q: 500,
          approval_reasons: discountQ > 500 ? ["discount_over_threshold"] : [],
        },
      };
    }
    if (String(path).includes("/manager-approval/check/")) return { ok: true };
    if (String(path).includes("/sale/close/")) return closeReplies[closeIdx++]!(body);
    return {};
  });
}

function bodiesTo(actionCall: ReturnType<typeof vi.fn>, fragment: string) {
  return actionCall.mock.calls
    .filter((call) => String(call[0]).includes(fragment))
    .map((call) => (call[1] as { body: Record<string, unknown> }).body);
}

async function saleWithDiscount(actionCall: ReturnType<typeof vi.fn>, value: string) {
  const h = makeSale({ projection: freeCartProjection(), actionCall });
  const pao = h.handles.posValue.value!.products[0]!;
  h.sale.addProduct(pao);
  h.sale.addProduct(pao);
  h.sale.cart.discountType = "fixed";
  h.sale.cart.discountValue = value;
  h.sale.cart.discountReason = "cortesia";
  await h.sale.submitSale(); // prepara: revisão com o desconto
  return h;
}

describe("usePosSale — a assinatura do gerente vale para o retrato que ele viu (WP-E1)", () => {
  it("R$ 6 assinado, a Caixa troca para R$ 30: a assinatura cai e não volta ao desfazer", async () => {
    const actionCall = router([]);
    const h = await saleWithDiscount(actionCall, "6,00");
    expect(h.sale.review.value?.requires_manager_approval).toBe(true);

    expect(await h.sale.checkManagerApproval("joyce", PIN)).toBe(true);
    expect(h.sale.managerApproved.value).toBe(true);

    h.sale.cart.discountValue = "30,00";
    await nextTick();
    expect(h.sale.managerApproved.value).toBe(false);

    // Voltar a R$ 6 não ressuscita a assinatura: o PIN já saiu da memória.
    h.sale.cart.discountValue = "6,00";
    await nextTick();
    expect(h.sale.managerApproved.value).toBe(false);
    h.handles.dispose();
  });

  it("item, quantidade e forma de pagamento também apagam a assinatura", async () => {
    const actionCall = router([]);
    const h = await saleWithDiscount(actionCall, "6,00");
    const pao = h.handles.posValue.value!.products[0]!;

    await h.sale.checkManagerApproval("joyce", PIN);
    h.sale.addProduct(pao);
    await nextTick();
    expect(h.sale.managerApproved.value).toBe(false);

    await h.sale.checkManagerApproval("joyce", PIN);
    h.sale.cart.paymentTenders = [{ method: "credit", amount_q: 3735, collection: "terminal" }];
    await nextTick();
    expect(h.sale.managerApproved.value).toBe(false);
    h.handles.dispose();
  });

  it("a mudança feita enquanto o PIN era conferido não leva a assinatura", async () => {
    let release!: () => void;
    const actionCall = vi.fn().mockImplementation(async (path: string, options?: { body?: Record<string, unknown> }) => {
      if (String(path).includes("/manager-approval/check/")) {
        await new Promise<void>((resolve) => { release = resolve; });
        return { ok: true };
      }
      return router([])(path, options);
    });
    const h = await saleWithDiscount(actionCall, "6,00");

    const checking = h.sale.checkManagerApproval("joyce", PIN);
    await nextTick();
    h.sale.cart.discountValue = "30,00";
    release();
    expect(await checking).toBe(false);
    expect(h.sale.managerApproved.value).toBe(false);
    h.handles.dispose();
  });
});

describe("usePosSale — o PIN do gerente nunca fica no navegador (P1-4)", () => {
  it("só o POST do fechamento leva a assinatura; guarda, autosave e revisão nunca", async () => {
    let guardDuringClose = "";
    const actionCall = router([
      () => {
        guardDuringClose = storageValues.get(GUARD_KEY) || "";
        return { ok: true, order_ref: "PED-1" };
      },
    ]);
    const h = await saleWithDiscount(actionCall, "6,00");
    await h.sale.checkManagerApproval("joyce", PIN);
    await h.sale.saveTab();

    await h.sale.submitSale();

    const [close] = bodiesTo(actionCall, "/sale/close/");
    expect(close?.manager_approval).toEqual({ username: "joyce", pin: PIN });
    // O guarda estava gravado durante a cobrança, e sem o PIN.
    expect(guardDuringClose).toContain("client_request_id");
    expect(guardDuringClose).not.toContain(PIN);
    expect(guardDuringClose).not.toContain("manager_approval");
    // Ele guarda o VALOR que o gerente vê ao reconferir, nada que autorize.
    expect(JSON.parse(guardDuringClose).approval).toMatchObject({ discount_q: 600, threshold_q: 500 });
    for (const written of storageWrites) expect(written).not.toContain(PIN);
    for (const body of [...bodiesTo(actionCall, "/tabs/save/"), ...bodiesTo(actionCall, "/sale/review/")]) {
      expect(body).not.toHaveProperty("manager_approval");
    }
    h.handles.dispose();
  });

  it("a retentativa pede a assinatura de novo: a recusa gasta a que havia", async () => {
    const actionCall = router([
      () => {
        throw {
          status: 422,
          data: { detail: "Confira o cliente.", error: { code: "customer_required", message: "Confira o cliente." } },
        };
      },
      () => ({ ok: true, order_ref: "PED-2" }),
    ]);
    const h = await saleWithDiscount(actionCall, "6,00");
    await h.sale.checkManagerApproval("joyce", PIN);

    await h.sale.submitSale();
    expect(h.sale.managerApproved.value).toBe(false);

    await h.sale.submitSale();
    const [first, second] = bodiesTo(actionCall, "/sale/close/");
    expect(first?.manager_approval).toEqual({ username: "joyce", pin: PIN });
    expect(second).not.toHaveProperty("manager_approval");
    h.handles.dispose();
  });

  it("a recusa da assinatura reabre o diálogo e não deixa assinatura para reenviar", async () => {
    const actionCall = router([
      () => {
        throw {
          status: 422,
          data: {
            detail: "Esta venda exige aprovação gerencial.",
            error: { code: "manager_approval_invalid", message: "Aprovação gerencial inválida.", recovery: "Revise o gerente e o PIN." },
          },
        };
      },
    ]);
    const h = await saleWithDiscount(actionCall, "6,00");
    await h.sale.checkManagerApproval("joyce", PIN);

    await h.sale.submitSale();

    expect(h.sale.managerApprovalError.value).toBe("Revise o gerente e o PIN.");
    expect(h.sale.managerApproved.value).toBe(false);
    h.handles.dispose();
  });
});

describe("usePosSale — a conferência da venda sem resposta pede o gerente de novo", () => {
  function storeMarker(body: Record<string, unknown>, approval?: Record<string, unknown>) {
    storageValues.set(GUARD_KEY, JSON.stringify({
      client_request_id: "pos:incerta-1",
      owner_id: "o-1",
      state: "uncertain",
      recorded_at: "2026-11-16T15:00:00Z",
      body: { client_request_id: "pos:incerta-1", ...body },
      ...(approval ? { approval } : {}),
    }));
  }

  it("sem a assinatura, nem chama o servidor: devolve 'approval' com o valor que o gerente vai ver", async () => {
    storeMarker({ manual_discount: { type: "fixed", value: 30 } }, { discount_q: 3000, threshold_q: 500, reasons: ["discount_over_threshold"] });
    const actionCall = router([]);
    const h = makeSale({ projection: freeCartProjection(), actionCall });

    expect(await h.sale.recheckUncertainClose()).toBe("approval");
    expect(bodiesTo(actionCall, "/sale/close/")).toHaveLength(0);
    expect(h.sale.closeRecheckApproval.value).toMatchObject({ discount_q: 3000, threshold_q: 500 });
    h.handles.dispose();
  });

  it("com a assinatura nova, reenvia o mesmo corpo com ela, e ela não volta ao disco", async () => {
    storeMarker({ manual_discount: { type: "fixed", value: 30 } }, { discount_q: 3000, threshold_q: 500, reasons: [] });
    const actionCall = router([() => ({ ok: true, order_ref: "PED-3" })]);
    const h = makeSale({ projection: freeCartProjection(), actionCall });

    expect(await h.sale.recheckUncertainClose({ username: "joyce", pin: PIN })).toBe("resolved");
    const [replay] = bodiesTo(actionCall, "/sale/close/");
    expect(replay).toMatchObject({ client_request_id: "pos:incerta-1", manager_approval: { username: "joyce", pin: PIN } });
    expect(storageValues.get(GUARD_KEY)).toBeUndefined();
    for (const written of storageWrites) expect(written).not.toContain(PIN);
    expect(h.sale.closeRecheckApproval.value).toBeNull();
    h.handles.dispose();
  });

  it("o PIN recusado na conferência fica no diálogo, com a frase do servidor", async () => {
    storeMarker({}, { discount_q: 3000, threshold_q: 500, reasons: [] });
    const actionCall = router([
      () => {
        throw {
          status: 422,
          data: { error: { code: "manager_approval_invalid", message: "Aprovação gerencial inválida.", recovery: "Revise o gerente e o PIN." } },
        };
      },
    ]);
    const h = makeSale({ projection: freeCartProjection(), actionCall });

    expect(await h.sale.recheckUncertainClose({ username: "joyce", pin: "0000" })).toBe("approval");
    expect(h.sale.closeRecheckApprovalError.value).toBe("Revise o gerente e o PIN.");
    h.handles.dispose();
  });

  it("o marcador gravado antes, com o PIN no corpo, perde o PIN na primeira leitura", async () => {
    storeMarker({ manager_approval: { username: "joyce", pin: PIN } });
    const actionCall = router([]);
    const h = makeSale({ projection: freeCartProjection(), actionCall });

    await h.sale.restoreUncertainClose();

    expect(storageValues.get(GUARD_KEY)).not.toContain(PIN);
    expect(await h.sale.recheckUncertainClose()).toBe("approval");
    h.handles.dispose();
  });
});

describe("a fila sem conexão nunca grava a assinatura", () => {
  it("o corpo guardado sai sem `manager_approval`", async () => {
    const store = memoryOfflineSaleStore();
    await store.put({
      id: "pos:off-1",
      capturedAt: "2026-11-16T15:00:00Z",
      pricesAt: "2026-11-16T14:00:00Z",
      body: { client_request_id: "pos:off-1", manager_approval: { username: "joyce", pin: PIN } },
      totalQ: 1000,
      itemCount: 1,
      paymentLabel: "Dinheiro",
      status: "pending",
      attempts: 0,
    });
    const [saved] = await store.list();
    expect(saved?.body).toEqual({ client_request_id: "pos:off-1" });
  });
});

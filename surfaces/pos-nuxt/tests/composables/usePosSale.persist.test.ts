import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { toast } from "vue-sonner";

import { makeProjection, makeSale, makeTabPayload } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

function openProjection() {
  return makeProjection({
    checkout: {
      intent_version: 1,
      capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
    } as ReturnType<typeof makeProjection>["checkout"],
  });
}

/**
 * Instância com uma comanda "aberta": atribui a identidade da comanda direto no
 * `cart` reativo retornado (tabSessionKey não está na watch-list do autosave, então
 * não agenda por si) — evita depender do `openTab`/`setFromTabPayload` internos.
 */
function saleWithOpenTab(actionCall = vi.fn().mockResolvedValue({})) {
  const h = makeSale({ projection: openProjection(), actionCall });
  h.sale.cart.tabRef = "M1";
  h.sale.cart.tabDisplay = "M1";
  h.sale.cart.tabSessionKey = "sess-1";
  h.sale.cart.expectedRevision = "v1:initial";
  return h;
}

describe("usePosSale — autosave debounced (auto-persist estilo Odoo)", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("persiste (quiet) 1,2s após mudar o carrinho, sem refresh", async () => {
    const actionCall = vi.fn().mockResolvedValue({});
    const h = saleWithOpenTab(actionCall);

    const pao = h.handles.posValue.value!.products[0]!;
    h.sale.addProduct(pao);
    await nextTick();
    await vi.advanceTimersByTimeAsync(1200);

    expect(actionCall).toHaveBeenCalledTimes(1);
    expect(String(actionCall.mock.calls[0]![0])).toContain("/tabs/save/");
    expect(h.handles.refresh).not.toHaveBeenCalled(); // quiet: sem refresh de projeção
    expect(h.sale.unsaved.value).toBe(false);
    h.handles.dispose();
  });

  it("reutiliza a revisão retornada no próximo save", async () => {
    const actionCall = vi.fn().mockResolvedValue({ revision: "v1:next" });
    const h = saleWithOpenTab(actionCall);
    await h.sale.saveTab();
    await h.sale.saveTab();
    expect(actionCall.mock.calls[0]?.[1].body.expected_revision).toBe("v1:initial");
    expect(actionCall.mock.calls[1]?.[1].body.expected_revision).toBe("v1:next");
    h.handles.dispose();
  });

  it("conflito preserva o rascunho e não repete autosave até escolha explícita", async () => {
    const actionCall = vi.fn().mockRejectedValue({ status: 409, data: { detail: "Outra estação alterou a comanda." } });
    const h = saleWithOpenTab(actionCall);
    h.sale.addProduct(h.handles.posValue.value!.products[0]!);
    await nextTick();
    await vi.advanceTimersByTimeAsync(1200);
    expect(h.sale.tabConflict.value).toBe(true);
    expect(h.sale.cart.items).toHaveLength(1);
    expect(h.sale.cart.expectedRevision).toBe("v1:initial");
    await vi.advanceTimersByTimeAsync(10000);
    expect(actionCall).toHaveBeenCalledTimes(1);
    h.handles.dispose();
  });

  it("duas telas convergem somente após descarte explícito e salvam sobre a revisão atual", async () => {
    const remoteItem = {
      line_id: "L-shared",
      sku: "PAO",
      name: "Pão",
      qty: 3,
      unit_price_q: 500,
      notes: "",
    };
    const actionCall = vi
      .fn()
      .mockRejectedValueOnce({
        status: 409,
        data: { detail: "Outra estação alterou a comanda." },
      })
      .mockResolvedValueOnce(
        makeTabPayload({ revision: "v1:remote", items: [remoteItem] }),
      )
      .mockResolvedValueOnce({ revision: "v1:merged" });
    const h = saleWithOpenTab(actionCall);
    h.sale.addProduct(h.handles.posValue.value!.products[0]!);
    const localLineId = h.sale.cart.items[0]?.line_id;

    await h.sale.saveTab();
    expect(h.sale.tabConflict.value).toBe(true);
    expect(h.sale.cart.items[0]?.line_id).toBe(localLineId);
    expect(h.sale.cart.expectedRevision).toBe("v1:initial");

    await h.sale.reloadConflictingTab();
    expect(actionCall.mock.calls[1]?.[1]?.method).toBe("GET");
    expect(h.sale.tabConflict.value).toBe(false);
    expect(h.sale.cart.items[0]?.qty).toBe(3);
    expect(h.sale.cart.expectedRevision).toBe("v1:remote");

    h.sale.cart.items[0]!.qty = 4;
    await h.sale.saveTab();
    expect(actionCall.mock.calls[2]?.[1]?.body.expected_revision).toBe(
      "v1:remote",
    );
    expect(h.sale.cart.expectedRevision).toBe("v1:merged");
    h.handles.dispose();
  });

  it("atualiza somente a comanda original após descarte explícito", async () => {
    const actionCall = vi.fn().mockResolvedValue(makeTabPayload({ revision: "v1:remote" }));
    const h = saleWithOpenTab(actionCall);
    h.sale.tabConflict.value = true;
    await h.sale.reloadConflictingTab();
    expect(actionCall.mock.calls[0]?.[1].method).toBe("GET");
    expect(h.sale.cart.expectedRevision).toBe("v1:remote");
    expect(h.sale.tabConflict.value).toBe(false);
    h.sale.tabConflict.value = true;
    actionCall.mockResolvedValue(makeTabPayload({ session_key: "replacement", revision: "v1:other" }));
    await h.sale.reloadConflictingTab();
    expect(h.sale.cart.tabSessionKey).toBe("sess-1");
    expect(h.sale.cart.expectedRevision).toBe("v1:remote");
    expect(h.sale.tabConflict.value).toBe(true);
    h.handles.dispose();
  });

  it("agrupa lançamentos rápidos num único save (debounce)", async () => {
    const actionCall = vi.fn().mockResolvedValue({});
    const h = saleWithOpenTab(actionCall);
    const pao = h.handles.posValue.value!.products[0]!;

    h.sale.addProduct(pao);
    await nextTick();
    await vi.advanceTimersByTimeAsync(600); // ainda dentro da janela
    h.sale.addProduct(pao);
    await nextTick();
    await vi.advanceTimersByTimeAsync(1200);

    expect(actionCall).toHaveBeenCalledTimes(1);
    h.handles.dispose();
  });

  it("o guard tabLoading suprime autosave durante o load programático de comanda", async () => {
    const actionCall = vi
      .fn()
      .mockResolvedValue(
        makeTabPayload({ items: [{ line_id: "L-pao-1", sku: "PAO", name: "Pão", price_q: 500, qty: 1, notes: "" }] }),
      );
    const h = makeSale({ projection: openProjection(), actionCall });

    await h.sale.openTab("M1"); // carrega itens via setFromTabPayload (tabLoading)
    await vi.advanceTimersByTimeAsync(1200);

    // A carga não pode disparar um save — só houve a chamada de open_tab.
    const savedCalls = actionCall.mock.calls.filter((c) => String(c[0]).includes("/tabs/save/"));
    expect(savedCalls).toHaveLength(0);
    h.handles.dispose();
  });

  it("falha de autosave marca unsaved e reagenda o retry (rede instável)", async () => {
    const actionCall = vi.fn().mockRejectedValue(new Error("wifi caiu"));
    const h = saleWithOpenTab(actionCall);

    const pao = h.handles.posValue.value!.products[0]!;
    h.sale.addProduct(pao);
    await nextTick();
    await vi.advanceTimersByTimeAsync(1200); // autosave dispara e falha

    expect(actionCall).toHaveBeenCalledTimes(1);
    expect(h.sale.unsaved.value).toBe(true);

    await vi.advanceTimersByTimeAsync(5000); // retry agendado tenta de novo
    expect(actionCall).toHaveBeenCalledTimes(2);
    expect(h.sale.unsaved.value).toBe(true);
    h.handles.dispose();
  });

  it("um retry bem-sucedido limpa o chip unsaved", async () => {
    const actionCall = vi
      .fn()
      .mockRejectedValueOnce(new Error("wifi caiu"))
      .mockResolvedValue({});
    const h = saleWithOpenTab(actionCall);

    const pao = h.handles.posValue.value!.products[0]!;
    h.sale.addProduct(pao);
    await nextTick();
    await vi.advanceTimersByTimeAsync(1200); // falha → unsaved
    expect(h.sale.unsaved.value).toBe(true);

    await vi.advanceTimersByTimeAsync(5000); // retry → sucesso
    expect(h.sale.unsaved.value).toBe(false);
    h.handles.dispose();
  });
});

describe("usePosSale — persistQueue serializa gravações", () => {
  afterEach(() => vi.useRealTimers());

  it("saves concorrentes não correm em paralelo (fila)", async () => {
    let active = 0;
    let overlapped = false;
    const actionCall = vi.fn().mockImplementation(async () => {
      active += 1;
      if (active > 1) overlapped = true;
      await Promise.resolve();
      active -= 1;
      return {};
    });
    const h = saleWithOpenTab(actionCall);
    await nextTick();

    const a = h.sale.saveTab();
    const b = h.sale.saveTab();
    await Promise.all([a, b]);

    expect(overlapped).toBe(false);
    expect(actionCall.mock.calls.length).toBeGreaterThanOrEqual(2);
    h.handles.dispose();
  });
});

describe("cadastro em rascunho não é persistência autorizada", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); });
  it("não salva versões digitadas do cadastro; selecionar ref libera autosave", async () => {
    const h = saleWithOpenTab();
    h.sale.addProduct(h.handles.posValue.value!.products[0]!);
    await nextTick();
    h.sale.cart.customerName = "Br";
    await nextTick();
    await vi.advanceTimersByTimeAsync(6000);
    h.sale.cart.customerName = "Bruno";
    h.sale.cart.customerPhone = "43999990022";
    await nextTick();
    await vi.advanceTimersByTimeAsync(6000);
    expect(h.handles.actionCall).not.toHaveBeenCalled();
    expect(h.sale.unsaved.value).toBe(true);
    h.sale.cart.customerRef = "CUST-B";
    await nextTick();
    await vi.advanceTimersByTimeAsync(1200);
    expect(h.handles.actionCall).toHaveBeenCalledTimes(1);
    expect(h.sale.unsaved.value).toBe(false);
    h.handles.dispose();
  });
  it("checkout e fechamento pedem concluir cadastro, sem chamar API", async () => {
    const h = saleWithOpenTab();
    h.sale.addProduct(h.handles.posValue.value!.products[0]!);
    h.sale.cart.customerPhone = "43999990022";
    await nextTick();
    const focus = h.sale.customerFocusNonce.value;
    await h.sale.prepareCheckout();
    expect(h.sale.checkoutMode.value).toBe(false);
    expect(h.sale.customerFocusNonce.value).toBeGreaterThan(focus);
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("Conclua o cadastro ou remova os dados"));
    h.sale.checkoutMode.value = true;
    await h.sale.submitSale();
    expect(h.handles.actionCall).not.toHaveBeenCalled();
    h.handles.dispose();
  });
});

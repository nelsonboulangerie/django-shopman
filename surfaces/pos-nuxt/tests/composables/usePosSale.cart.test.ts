import { afterEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { toast } from "vue-sonner";

import { makeProjection, makeSale, makeTabPayload } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

function freeCartProjection() {
  return makeProjection({
    checkout: {
      intent_version: 1,
      capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
    } as ReturnType<typeof makeProjection>["checkout"],
  });
}

describe("usePosSale — mutações de carrinho", () => {
  it("addProduct deduplica na mesma linha e incrementa a quantidade", () => {
    const h = makeSale({ projection: freeCartProjection() });
    const pao = h.handles.posValue.value!.products[0]!;
    h.sale.addProduct(pao);
    h.sale.addProduct(pao);
    expect(h.sale.cart.items).toHaveLength(1);
    expect(h.sale.productQty("PAO")).toBe(2);
    expect(h.sale.itemCount.value).toBe(2);
    h.handles.dispose();
  });

  it("setQty(0) remove a linha; >0 ajusta", () => {
    const h = makeSale({ projection: freeCartProjection() });
    const pao = h.handles.posValue.value!.products[0]!;
    h.sale.addProduct(pao);
    h.sale.setQty("PAO", 5);
    expect(h.sale.productQty("PAO")).toBe(5);
    h.sale.setQty("PAO", 0);
    expect(h.sale.cart.items).toHaveLength(0);
    h.handles.dispose();
  });

  it("setLinePrice marca override só quando difere do catálogo", () => {
    const h = makeSale({ projection: freeCartProjection() });
    const pao = h.handles.posValue.value!.products[0]!; // catálogo 500
    h.sale.addProduct(pao);
    h.sale.setLinePrice("PAO", 700);
    expect(h.sale.cart.items[0]!.price_q).toBe(700);
    expect(h.sale.cart.items[0]!.price_overridden).toBe(true);
    h.sale.setLinePrice("PAO", 500); // volta ao catálogo → limpa override
    expect(h.sale.cart.items[0]!.price_overridden).toBe(false);
    h.handles.dispose();
  });

  it("setLineDiscount adiciona e remove o desconto da linha", () => {
    const h = makeSale({ projection: freeCartProjection() });
    const pao = h.handles.posValue.value!.products[0]!;
    h.sale.addProduct(pao);
    h.sale.setLineDiscount("PAO", 10, "cortesia");
    expect(h.sale.cart.items[0]!.discount).toEqual({ value: 10, reason: "cortesia" });
    h.sale.setLineDiscount("PAO", 0, "");
    expect(h.sale.cart.items[0]!.discount).toBeUndefined();
    h.handles.dispose();
  });

  it("clearCustomer solta TODOS os campos do cliente (não só o nome)", () => {
    const h = makeSale({ projection: freeCartProjection() });
    Object.assign(h.sale.cart, { customerRef: "C1", customerName: "Ana", customerPhone: "43999", customerEmail: "a@b.c", customerTaxId: "123" });
    h.sale.clearCustomer();
    expect(h.sale.cart.customerRef).toBe("");
    expect(h.sale.cart.customerName).toBe("");
    expect(h.sale.cart.customerPhone).toBe("");
    expect(h.sale.cart.customerEmail).toBe("");
    expect(h.sale.cart.customerTaxId).toBe("");
    h.handles.dispose();
  });
});

describe("usePosSale — gate de comanda para usar o carrinho", () => {
  it("com comanda obrigatória, addProduct pede associação em vez de lançar", () => {
    const h = makeSale(); // projeção default → requires_open_tab_for_cart
    const pao = h.handles.posValue.value!.products[0]!;
    expect(h.sale.canUseCart.value).toBe(false);
    h.sale.addProduct(pao);
    expect(h.sale.cart.items).toHaveLength(0);
    expect(h.sale.tabDialogOpen.value).toBe(true);
    expect(h.sale.tabDialogReason.value).toBe("cart");
    h.handles.dispose();
  });
});

describe("usePosSale — a trava da gaveta morde ao INICIAR a venda", () => {
  const AGENT_DRAWER = {
    adapter: "agent", can_kick: true, open_on_cash_sale: true,
    agent_url: "http://127.0.0.1:47811", token: "token-do-balcao",
  };
  function drawerProjection() {
    return makeProjection({
      checkout: {
        intent_version: 1,
        capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
      } as ReturnType<typeof makeProjection>["checkout"],
      cash_drawer: AGENT_DRAWER as ReturnType<typeof makeProjection>["cash_drawer"],
    });
  }
  function stubDrawer(body: Record<string, unknown>) {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) })));
  }
  afterEach(() => vi.unstubAllGlobals());

  it("gaveta sabidamente aberta: NÃO abre a comanda, sobe a trava", async () => {
    stubDrawer({ known: true, open: true, raw: "0x12" });
    const actionCall = vi.fn().mockResolvedValue(makeTabPayload());
    const h = makeSale({ projection: drawerProjection(), actionCall });

    await h.sale.openTab("M1");

    expect(actionCall).not.toHaveBeenCalled();
    expect(h.sale.drawerLock.open.value).toBe(true);
    expect(h.sale.hasOpenTab.value).toBe(false);
    h.handles.dispose();
  });

  it("gaveta fechada: a comanda abre normalmente", async () => {
    stubDrawer({ known: true, open: false, raw: "0x16" });
    const actionCall = vi.fn().mockResolvedValue(makeTabPayload());
    const h = makeSale({ projection: drawerProjection(), actionCall });

    await h.sale.openTab("M1");
    await nextTick();

    expect(actionCall).toHaveBeenCalledTimes(1);
    expect(h.sale.hasOpenTab.value).toBe(true);
    h.handles.dispose();
  });

  it("estado desconhecido NUNCA trava", async () => {
    stubDrawer({ known: false, reason: "esta estacao nunca mediu a gaveta." });
    const actionCall = vi.fn().mockResolvedValue(makeTabPayload());
    const h = makeSale({ projection: drawerProjection(), actionCall });

    await h.sale.openTab("M1");
    await nextTick();

    expect(actionCall).toHaveBeenCalledTimes(1);
    expect(h.sale.drawerLock.open.value).toBe(false);
    h.handles.dispose();
  });

  it("venda já começada escolhendo comanda (preserveDraft) não vira refém", async () => {
    stubDrawer({ known: true, open: true, raw: "0x12" });
    const actionCall = vi.fn().mockResolvedValue(makeTabPayload());
    const h = makeSale({ projection: drawerProjection(), actionCall });
    h.sale.addProduct(h.handles.posValue.value!.products[0]!);

    await h.sale.openTab("M1", { preserveDraft: true });

    expect(actionCall).toHaveBeenCalledTimes(1);
    expect(h.sale.drawerLock.open.value).toBe(false);
    h.handles.dispose();
  });

  it("'já fechei' com a gaveta fechada abre a comanda que esperava", async () => {
    stubDrawer({ known: true, open: true, raw: "0x12" });
    const actionCall = vi.fn().mockResolvedValue(makeTabPayload());
    const h = makeSale({ projection: drawerProjection(), actionCall });
    await h.sale.openTab("M1");
    expect(actionCall).not.toHaveBeenCalled();

    stubDrawer({ known: true, open: false, raw: "0x16" });
    await h.sale.drawerLock.recheck();
    await nextTick();

    expect(actionCall).toHaveBeenCalledTimes(1);
    expect(h.sale.hasOpenTab.value).toBe(true);
    expect(h.sale.drawerLock.open.value).toBe(false);
    h.handles.dispose();
  });
});

describe("usePosSale — openTab / preserveDraft", () => {
  it("rascunho sem comanda → openTab pede associação (não abre direto)", async () => {
    const actionCall = vi.fn().mockResolvedValue(makeTabPayload());
    const h = makeSale({ projection: freeCartProjection(), actionCall });
    const pao = h.handles.posValue.value!.products[0]!;
    h.sale.addProduct(pao); // rascunho sem comanda

    await h.sale.openTab("M1");

    expect(actionCall).not.toHaveBeenCalled(); // não abriu; abriu o diálogo
    expect(h.sale.tabDialogOpen.value).toBe(true);
    expect(h.sale.tabInput.value).toBe("M1");
    h.handles.dispose();
  });

  it("preserveDraft numa comanda já ocupada acusa erro (não sobrescreve)", async () => {
    const actionCall = vi.fn().mockResolvedValue(makeTabPayload({
      items: [{ sku: "CAFE", name: "Café", price_q: 300, qty: 1, notes: "" }],
    }));
    const h = makeSale({ projection: freeCartProjection(), actionCall });
    const pao = h.handles.posValue.value!.products[0]!;
    h.sale.addProduct(pao);

    await h.sale.openTab("M1", { preserveDraft: true });

    // A comanda tinha pedido → recusa, mantém o rascunho intacto, sem sessão.
    expect(h.sale.cart.tabSessionKey).toBe("");
    expect(h.sale.cart.items[0]!.sku).toBe("PAO");
    h.handles.dispose();
  });

  it("openTab de comanda livre carrega o payload no carrinho", async () => {
    const actionCall = vi.fn().mockResolvedValue(makeTabPayload({
      session_key: "sess-9",
      tab_session_key: "sess-9",
      tab_ref: "M9",
      tab_display: "M9",
      customer_name: "Bruno",
      items: [{ sku: "CAFE", name: "Café", price_q: 300, qty: 2, notes: "" }],
    }));
    const h = makeSale({ projection: freeCartProjection(), actionCall });

    await h.sale.openTab("M9");
    await nextTick();

    expect(h.sale.cart.tabSessionKey).toBe("sess-9");
    expect(h.sale.hasOpenTab.value).toBe(true);
    expect(h.sale.cart.customerName).toBe("Bruno");
    expect(h.sale.cart.items).toHaveLength(1);
    expect(h.sale.showTabs.value).toBe(false); // move p/ o workspace da venda
    h.handles.dispose();
  });
});

describe("usePosSale — intent (currentIntentState via saveTab)", () => {
  it("monta o intent com entrega, desconto manual e aprovação do gerente", async () => {
    const actionCall = vi.fn().mockResolvedValue({});
    const h = makeSale({ projection: freeCartProjection(), actionCall });
    const pao = h.handles.posValue.value!.products[0]!;
    h.sale.addProduct(pao);
    Object.assign(h.sale.cart, {
      tabRef: "M1",
      tabSessionKey: "sess-1",
      fulfillmentType: "delivery",
      deliveryAddress: "Rua A",
      deliveryStreetNumber: "100",
      deliveryFeeOverride: true,
      deliveryFeeOverrideInput: "5,00",
      discountType: "fixed",
      discountValue: "2,50",
      discountReason: "cliente fiel",
      managerUsername: "gerente",
      managerPin: "9999",
      customerName: "Ana",
      customerPhone: "(43) 99999-0000",
    });

    await h.sale.saveTab();

    const saveCall = actionCall.mock.calls.find((c) => String(c[0]).includes("/tabs/save/"))!;
    const body = saveCall[1]!.body as Record<string, any>;
    expect(body.fulfillment_type).toBe("delivery");
    // A taxa é resolvida no servidor; o que sobe é a EXCEÇÃO declarada.
    expect(body.delivery_fee_q).toBeUndefined();
    expect(body.delivery_fee_override_q).toBe(500);
    expect(body.manual_discount).toEqual({ type: "fixed", value: 2.5, reason: "cliente fiel" });
    expect(body.manager_approval).toEqual({ username: "gerente", pin: "9999" });
    expect(body.customer_name).toBe("Ana");
    expect(body.customer_phone).toBe("43999990000"); // só dígitos
    expect(typeof body.client_request_id).toBe("string");
    h.handles.dispose();
  });
});

describe("usePosSale — comandos de sessão (path + body + flags)", () => {
  let actionCall: ReturnType<typeof vi.fn>;

  function openTabSale() {
    actionCall = vi.fn().mockResolvedValue({ tab: null, source: null, source_closed: false });
    const h = makeSale({ projection: freeCartProjection(), actionCall });
    Object.assign(h.sale.cart, { tabRef: "M1", tabDisplay: "M1", tabSessionKey: "sess-1" });
    return h;
  }

  it("renameTab chama rename com session_key + new_tab_ref e liga renamingTab→false", async () => {
    const h = openTabSale();
    await h.sale.renameTab("M2");
    const call = actionCall.mock.calls.find((c) => String(c[0]).includes("/tabs/rename/"))!;
    expect(call[1]!.body).toMatchObject({ session_key: "sess-1", new_tab_ref: "M2" });
    expect(h.sale.renamingTab.value).toBe(false);
    h.handles.dispose();
  });

  it("submitMove(split) envia line_ids e reindexa a fonte", async () => {
    const h = openTabSale();
    await h.sale.submitMove({ mode: "split", lineIds: ["L1", "L2"], toTabRef: "M2", closeSource: true });
    const call = actionCall.mock.calls.find((c) => String(c[0]).includes("/tabs/move-lines/"))!;
    expect(call[1]!.body).toMatchObject({
      from_session_key: "sess-1",
      line_ids: ["L1", "L2"],
      to_tab_ref: "M2",
      close_source_when_empty: true,
    });
    expect(h.sale.moveDialogOpen.value).toBe(false);
    h.handles.dispose();
  });

  it("cancelRecentSale só age quando há resultado e envia order_ref + reason + manager_approval", async () => {
    const h = openTabSale();
    // sem result → no-op
    await h.sale.cancelRecentSale("gerente", "4321");
    expect(actionCall.mock.calls.some((c) => String(c[0]).includes("/recent/cancel/"))).toBe(false);

    h.sale.result.value = { orderRef: "PED-7", nextUrl: "", payment: null, receipt: {} as never, fiscalExpected: false, changeQ: 0 };
    h.sale.cancelSaleReason.value = "cliente desistiu";
    h.sale.cancelSaleDialogOpen.value = true;
    await h.sale.cancelRecentSale("gerente", "4321");
    const call = actionCall.mock.calls.find((c) => String(c[0]).includes("/recent/cancel/"))!;
    expect(call[1]!.body).toEqual({
      order_ref: "PED-7",
      reason: "cliente desistiu",
      manager_approval: { username: "gerente", pin: "4321" },
    });
    // O banner fixo morreu: a confirmação é um toast padrão de sucesso.
    expect(vi.mocked(toast.success)).toHaveBeenCalledWith("Venda cancelada", expect.anything());
    expect(h.sale.result.value).toBeNull();
    expect(h.sale.cancelSaleDialogOpen.value).toBe(false);
    h.handles.dispose();
  });

  it("cancelRecentSale com PIN recusado mantém o diálogo aberto com o motivo", async () => {
    const rejectingCall = vi.fn().mockImplementation(async (path: string) => {
      if (String(path).includes("/recent/cancel/")) {
        throw {
          data: {
            detail: "Aprovação gerencial inválida.",
            error: { code: "manager_approval_invalid", message: "Aprovação gerencial inválida.", recovery: "Revise o gerente e o PIN." },
          },
        };
      }
      return {};
    });
    const h = makeSale({ projection: freeCartProjection(), actionCall: rejectingCall });
    h.sale.result.value = { orderRef: "PED-8", nextUrl: "", payment: null, receipt: {} as never, fiscalExpected: false, changeQ: 0 };
    h.sale.cancelSaleDialogOpen.value = true;
    vi.mocked(toast.success).mockClear();

    await h.sale.cancelRecentSale("gerente", "0000");

    expect(h.sale.cancelSaleDialogOpen.value).toBe(true);
    expect(h.sale.cancelSaleError.value).toBe("Revise o gerente e o PIN.");
    expect(vi.mocked(toast.success)).not.toHaveBeenCalled();
    expect(h.sale.result.value?.orderRef).toBe("PED-8"); // venda continua de pé
    h.handles.dispose();
  });

  it("cancelRecentSale com erro de negócio também fica inline (diálogo aberto ≠ sucesso)", async () => {
    const rejectingCall = vi.fn().mockImplementation(async (path: string) => {
      if (String(path).includes("/recent/cancel/")) {
        throw { data: { detail: "Pedido PED-9 não pode ser cancelado (status: ready)" } };
      }
      return {};
    });
    const h = makeSale({ projection: freeCartProjection(), actionCall: rejectingCall });
    h.sale.result.value = { orderRef: "PED-9", nextUrl: "", payment: null, receipt: {} as never, fiscalExpected: false, changeQ: 0 };
    h.sale.cancelSaleDialogOpen.value = true;
    vi.mocked(toast.success).mockClear();

    await h.sale.cancelRecentSale("gerente", "4321");

    expect(h.sale.cancelSaleDialogOpen.value).toBe(true); // não fecha fingindo sucesso
    expect(h.sale.cancelSaleError.value).toContain("não pode ser cancelado");
    expect(vi.mocked(toast.success)).not.toHaveBeenCalled();
    h.handles.dispose();
  });

  it("clearCurrentTab sem sessão apenas reseta; com sessão chama clear", async () => {
    const noTabCall = vi.fn().mockResolvedValue({});
    const noTab = makeSale({ projection: freeCartProjection(), actionCall: noTabCall });
    const pao = noTab.handles.posValue.value!.products[0]!;
    noTab.sale.cart.items.push({ ...pao, qty: 1, notes: "" });
    await noTab.sale.clearCurrentTab();
    expect(noTabCall).not.toHaveBeenCalled(); // sem sessão → só reset local
    expect(noTab.sale.cart.items).toHaveLength(0);
    noTab.handles.dispose();

    const h = openTabSale();
    await h.sale.clearCurrentTab();
    const call = actionCall.mock.calls.find((c) => String(c[0]).includes("/clear/"))!;
    expect(call[1]).toMatchObject({ method: "DELETE" });
    expect(h.sale.cart.tabSessionKey).toBe("");
    h.handles.dispose();
  });
});

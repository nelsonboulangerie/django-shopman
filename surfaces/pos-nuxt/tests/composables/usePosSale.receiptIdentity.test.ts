import { mockNuxtImport } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick, watch } from "vue";
import { makeProjection, makeSale, makeTabPayload } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
const { dollarFetch } = vi.hoisted(() => ({ dollarFetch: vi.fn() }));
mockNuxtImport("$fetch", () => dollarFetch);
const CPF = "52998224725";
const EMAIL = "bia@example.org";
const owner = { ref: "CUST-B", name: "Bia Nunes", phone: "", email: EMAIL, tax_id: CPF, matched_by: ["cpf"], is_current: false };
type Body = Record<string, any>;
let instances: ReturnType<typeof makeSale>[] = [];
function identityError(body: Body, field: "tax_id" | "email") {
  return { data: { detail: "Escolha como usar este dado", error: {
    code: "receipt_identity_conflict", field: field === "tax_id" ? "fiscal_tax_id" : "receipt_email",
    value: field === "tax_id" ? CPF : EMAIL, customer_ref: body.customer_ref || "",
    client_request_id: body.client_request_id, candidates: [owner],
  } } };
}
function setup(checkAt: "review" | "close" = "review", batch = false, emailOwner = owner) {
  const bodies: Body[] = [];
  const actionCall = vi.fn(async (path: string, options?: { body?: Body }): Promise<any> => {
    const body = options?.body || {};
    bodies.push(body);
    if (path.includes(`/sale/${checkAt}/`)) {
      const conflicts: Body[] = [];
      for (const field of ["tax_id", "email"] as const) {
        const fieldOwner = field === "email" ? emailOwner : owner;
        const value = field === "tax_id" ? body.fiscal_tax_id : body.receipt_email?.trim().toLowerCase();
        if (value !== (field === "tax_id" ? CPF : EMAIL) || body.customer_ref === fieldOwner.ref) continue;
        const choice = body.receipt_identity_choices?.find((item: Body) => item.field === field
          && item.value === value && item.customer_ref === (body.customer_ref || "") && item.owner_ref === fieldOwner.ref
          && item.client_request_id === body.client_request_id && item.choice === "receipt_only");
        if (!choice) {
          if (!batch) throw identityError(body, field);
          conflicts.push({ field: field === "tax_id" ? "fiscal_tax_id" : "receipt_email", value, candidates: [fieldOwner] });
        }
      }
      if (conflicts.length) throw { data: { error: { ...identityError(body, "tax_id").data.error, ...conflicts[0], conflicts } } };
    }
    if (path.includes("/sale/close/")) return { ok: true, order_ref: "PED-1", payment: null };
    return { review: { total_q: 500, subtotal_q: 500, total_display: "R$ 5,00" } };
  });
  const h = makeSale({ actionCall, projection: makeProjection({ checkout: {
    intent_version: 1, capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
  } as ReturnType<typeof makeProjection>["checkout"] }) });
  instances.push(h);
  h.sale.addProduct(h.handles.posValue.value!.products[0]!);
  return { ...h, bodies };
}
beforeEach(() => {
  instances = []; vi.useFakeTimers();
  dollarFetch.mockReset().mockResolvedValue({ customer: { ...owner, fiscal_prefs: {}, saved_addresses: [] } });
});
afterEach(() => {
  instances.forEach((h) => h.handles.dispose());
  vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals();
});

describe("CPF/e-mail do documento têm decisão própria", () => {
  it.each(["tax_id", "email"] as const)("pergunta %s mesmo com salvar desmarcado e lembra apenas documento", async (field) => {
    const h = setup();
    if (field === "tax_id") { h.sale.cart.invoiceTaxId = CPF; h.sale.cart.wantsCpfOnInvoice = true; }
    else { h.sale.cart.receiptEmail = EMAIL; h.sale.cart.receiptChannels = ["email"]; }
    h.sale.cart.saveReceiptContact = false; h.sale.cart.saveReceiptTaxId = false;
    await nextTick(); await h.sale.prepareCheckout();
    expect(h.sale.customerDecision.value).toMatchObject({ kind: "receipt_identity", field, other: { name: "Bia Nunes" } });
    expect(h.sale.cart.customerRef).toBe("");
    await h.sale.cancelCustomerDecision();
    expect(h.sale.customerDecision.value).toBeNull();
    expect(h.sale.cart.customerRef).toBe("");
    expect(h.bodies.at(-1)?.receipt_identity_choices).toHaveLength(1);
    await h.sale.reviewCheckout();
    expect(h.sale.customerDecision.value).toBeNull();
    expect(h.bodies.at(-1)?.save_receipt_contact).toBeUndefined();
    expect(h.bodies.at(-1)?.save_receipt_tax_id).toBeUndefined();
  });
  it("pergunta CPF e e-mail em série sem perder decisão anterior", async () => {
    const h = setup();
    Object.assign(h.sale.cart, { invoiceTaxId: CPF, wantsCpfOnInvoice: true, receiptEmail: EMAIL, receiptChannels: ["email"] });
    await nextTick(); await h.sale.prepareCheckout();
    expect(h.sale.customerDecision.value?.field).toBe("tax_id");
    const transitions: unknown[] = [];
    const stop = watch(h.sale.customerDecision, (decision) => transitions.push(decision?.field || null), { flush: "sync" });
    const pending = h.sale.cancelCustomerDecision();
    expect(h.sale.lookupBusy.value).toBe(true);
    await h.sale.cancelCustomerDecision(); // duplo toque não aceita o próximo campo
    await pending;
    expect(h.sale.lookupBusy.value).toBe(false);
    expect(h.sale.customerDecision.value?.field).toBe("email");
    expect(transitions).not.toContain(null);
    stop();
    await h.sale.cancelCustomerDecision();
    expect(h.sale.customerDecision.value).toBeNull();
    expect(h.bodies.at(-1)?.receipt_identity_choices).toHaveLength(2);
    await h.sale.submitSale();
    expect(h.sale.result.value?.orderRef).toBe("PED-1");
  });
  it("associar é explícito e conserva os dados pedidos na nota", async () => {
    const h = setup();
    Object.assign(h.sale.cart, { invoiceTaxId: CPF, wantsCpfOnInvoice: true, receiptEmail: "contador@example.com", receiptChannels: ["email"], customerRef: "CUST-A", customerName: "Ana" });
    await nextTick(); await h.sale.prepareCheckout();
    expect(h.sale.cart.customerRef).toBe("CUST-A");
    dollarFetch.mockReset().mockResolvedValue({ customer: { ...owner, fiscal_prefs: {}, saved_addresses: [] } });
    await h.sale.confirmCustomerDecision();
    expect(h.sale.cart.customerRef).toBe(owner.ref);
    expect(h.sale.cart.customerName).toBe(owner.name);
    expect(h.sale.cart.invoiceTaxId).toBe(CPF);
    expect(h.sale.cart.receiptEmail).toBe("contador@example.com");
    expect(h.sale.cart.wantsCpfOnInvoice).toBe(true);
    expect(h.sale.cart.saveReceiptContact).toBe(false);
    expect(h.sale.cart.saveReceiptTaxId).toBe(false);
    expect(h.sale.result.value).toBeNull();
  });
  it("mudar valor ou cliente invalida decisão anterior", async () => {
    const h = setup();
    Object.assign(h.sale.cart, { invoiceTaxId: CPF, wantsCpfOnInvoice: true });
    await nextTick(); await h.sale.prepareCheckout(); await h.sale.cancelCustomerDecision();
    h.sale.cart.invoiceTaxId = "11144477735"; h.sale.cart.invoiceTaxId = CPF;
    await h.sale.reviewCheckout();
    expect(h.sale.customerDecision.value?.kind).toBe("receipt_identity");
    await h.sale.cancelCustomerDecision();
    h.sale.cart.customerRef = "CUST-A";
    await h.sale.reviewCheckout();
    expect(h.sale.customerDecision.value?.kind).toBe("receipt_identity");
    expect(h.bodies.at(-1)?.receipt_identity_choices).toBeUndefined();
  });
  it("resposta tardia não associa nem confirma o dado que já mudou", async () => {
    const h = setup(); let reject!: (error: unknown) => void; let body: Body = {};
    h.handles.actionCall.mockImplementationOnce((_path: string, options?: { body?: Body }) => {
      body = options?.body || {}; return new Promise((_resolve, fail) => { reject = fail; });
    });
    Object.assign(h.sale.cart, { invoiceTaxId: CPF, wantsCpfOnInvoice: true });
    await nextTick(); const loading = h.sale.prepareCheckout();
    h.sale.cart.invoiceTaxId = "11144477735"; reject(identityError(body, "tax_id")); await loading;
    expect(h.sale.customerDecision.value).toBeNull(); expect(h.sale.cart.customerRef).toBe("");
  });
  it("dono descoberto ao fechar pede decisão novamente em cada venda", async () => {
    const h = setup("close");
    Object.assign(h.sale.cart, { invoiceTaxId: CPF, wantsCpfOnInvoice: true });
    await nextTick(); await h.sale.prepareCheckout(); await h.sale.submitSale();
    expect(h.sale.customerDecision.value?.kind).toBe("receipt_identity");
    await h.sale.cancelCustomerDecision(); expect(h.sale.result.value?.orderRef).toBe("PED-1");
    h.sale.addProduct(h.handles.posValue.value!.products[0]!);
    Object.assign(h.sale.cart, { invoiceTaxId: CPF, wantsCpfOnInvoice: true });
    await nextTick(); await h.sale.prepareCheckout(); await h.sale.submitSale();
    expect(h.sale.customerDecision.value?.kind).toBe("receipt_identity");
  });
  it("e-mail desativado não viaja, não grava nem pergunta", async () => {
    const h = setup();
    Object.assign(h.sale.cart, { receiptEmail: EMAIL, saveReceiptContact: true, receiptChannels: [] });
    await nextTick(); await h.sale.prepareCheckout();
    expect(h.sale.customerDecision.value).toBeNull();
    expect(h.bodies.at(-1)?.receipt_email).toBeUndefined();
    expect(h.bodies.at(-1)?.save_receipt_contact).toBeUndefined();
  });
  it("recarga da mesma comanda conserva a decisão válida para a venda", async () => {
    const h = setup();
    const route = h.handles.actionCall.getMockImplementation()!;
    h.handles.actionCall.mockImplementation(async (path: string, options?: { body?: Body }) => {
      if (path.includes("/tabs/") && path.includes("/open/")) return makeTabPayload({
        tab_ref: "M1", tab_session_key: "sess-1", session_key: "sess-1",
        items: h.sale.cart.items.map((item) => ({ ...item })), fiscal_tax_id: CPF,
      });
      if (path.includes("/tabs/save/")) return {};
      return route(path, options);
    });
    Object.assign(h.sale.cart, { tabRef: "M1", tabSessionKey: "sess-1", invoiceTaxId: CPF, wantsCpfOnInvoice: true });
    await nextTick(); await h.sale.prepareCheckout(); await h.sale.cancelCustomerDecision();
    const requestId = h.sale.cart.clientRequestId;
    await h.sale.prepareCheckout();
    expect(h.sale.customerDecision.value).toBeNull();
    expect(h.sale.cart.clientRequestId).toBe(requestId);
    expect(h.bodies.at(-1)?.receipt_identity_choices).toHaveLength(1);
  });

  it("consolida os dois dados do mesmo dono numa decisão", async () => {
    const h = setup("review", true);
    Object.assign(h.sale.cart, { invoiceTaxId: CPF, wantsCpfOnInvoice: true, receiptEmail: EMAIL, receiptChannels: ["email"] });
    await nextTick(); await h.sale.prepareCheckout();
    expect(h.sale.customerDecision.value?.receiptFields).toHaveLength(2);
    await h.sale.cancelCustomerDecision();
    expect(h.sale.customerDecision.value).toBeNull();
    expect(h.bodies.at(-1)?.receipt_identity_choices).toHaveLength(2);
  });
  it("escolhe um dono e reconhece o outro só no documento sem nova pergunta", async () => {
    const second = { ...owner, ref: "CUST-C", name: "Carla" };
    const h = setup("review", true, second);
    Object.assign(h.sale.cart, { invoiceTaxId: CPF, wantsCpfOnInvoice: true, receiptEmail: EMAIL, receiptChannels: ["email"] });
    await nextTick(); await h.sale.prepareCheckout();
    await h.sale.confirmCustomerDecision();
    expect(h.sale.cart.customerRef).toBe("");
    dollarFetch.mockReset().mockResolvedValue({ customer: { ...owner, fiscal_prefs: {}, saved_addresses: [] } });
    await h.sale.confirmCustomerDecision(owner.ref);
    expect(h.sale.cart.customerRef).toBe(owner.ref);
    expect(h.sale.customerDecision.value).toBeNull();
    expect(h.bodies.at(-1)?.receipt_identity_choices).toEqual([expect.objectContaining({field: "email", owner_ref: second.ref, customer_ref: owner.ref})]);
    expect(h.sale.cart.invoiceTaxId).toBe(CPF);
    expect(h.sale.cart.receiptEmail).toBe(EMAIL);
  });
  it("lookup pendente ignora duplo clique e mudança de documento", async () => {
    const h = setup("review", true);
    Object.assign(h.sale.cart, { invoiceTaxId: CPF, wantsCpfOnInvoice: true, receiptEmail: EMAIL, receiptChannels: ["email"] });
    await nextTick(); await h.sale.prepareCheckout();
    let finish!: (value: unknown) => void;
    dollarFetch.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const pending = h.sale.confirmCustomerDecision(owner.ref);
    await h.sale.confirmCustomerDecision(owner.ref);
    await h.sale.cancelCustomerDecision();
    h.sale.cart.receiptEmail = "changed@example.org";
    finish({customer: {...owner, fiscal_prefs: {}, saved_addresses: []}});
    await pending;
    expect(h.sale.cart.customerRef).toBe("");
    expect(h.sale.cart.receiptEmail).toBe("changed@example.org");
    expect(h.sale.customerDecision.value).toBeNull();
  });

  it("preserva e-mail do documento vindo do cliente anterior", async () => {
    const h = setup("review", true);
    Object.assign(h.sale.cart, { customerRef: "CUST-A", customerName: "Ana", customerEmail: "contador@example.org", invoiceTaxId: CPF, wantsCpfOnInvoice: true, receiptEmail: "", receiptChannels: ["email"] });
    await nextTick(); await h.sale.prepareCheckout();
    dollarFetch.mockReset().mockResolvedValue({ customer: { ...owner, fiscal_prefs: {}, saved_addresses: [] } });
    await h.sale.confirmCustomerDecision(owner.ref);
    expect(h.sale.cart.customerEmail).toBe(EMAIL);
    expect(h.sale.cart.receiptEmail).toBe("contador@example.org");
    expect(h.bodies.at(-1)?.receipt_email).toBe("contador@example.org");
  });
  it.each(["reset", "failure"])("não confirma ao %s durante lookup", async (mode) => {
    const h = setup("review", true);
    Object.assign(h.sale.cart, { invoiceTaxId: CPF, wantsCpfOnInvoice: true, receiptEmail: EMAIL, receiptChannels: ["email"] });
    await nextTick(); await h.sale.prepareCheckout();
    let finish!: (value: unknown) => void;
    let fail!: (reason: unknown) => void;
    dollarFetch.mockImplementationOnce(() => new Promise((resolve, reject) => { finish = resolve; fail = reject; }));
    const pending = h.sale.confirmCustomerDecision(owner.ref);
    if (mode === "reset") {
      h.sale.cart.clientRequestId = "next-sale";
      finish({customer: {...owner, fiscal_prefs: {}, saved_addresses: []}});
    } else fail(new Error("offline"));
    await pending;
    expect(h.sale.cart.customerRef).toBe("");
    expect(h.bodies.at(-1)?.receipt_identity_choices).toBeUndefined();
    expect(h.sale.lookupBusy.value).toBe(false);
  });

});

// Sem o bloco "Nota e comprovante" na tela, a venda não carrega pedido fiscal.
//
// O toggle "Nota fiscal" do Admin só MOSTRA o formulário (a regra fiscal é
// soberana). Mas com ele desligado os padrões do cliente (CPF na nota, nota por
// e-mail) continuavam pré-marcando o carrinho e viajando no intent: nota com CPF
// e e-mail disparado sem o operador ver nem ter onde desmarcar. Medido em
// 17/09/2026. Os padrões seguem no CADASTRO; só não entram na venda.
import { mockNuxtImport } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeProjection, makeSale } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

const { dollarFetch } = vi.hoisted(() => ({ dollarFetch: vi.fn() }));
mockNuxtImport("$fetch", () => dollarFetch);

function projection(offered: boolean) {
  return makeProjection({
    checkout: {
      intent_version: 1,
      capabilities: {
        supports_fiscal_document: offered,
        tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false },
      },
    } as ReturnType<typeof makeProjection>["checkout"],
  });
}

function customer(overrides: Record<string, unknown> = {}) {
  return {
    ref: "CUST-1", name: "Ana Prado", phone: "+5543999990011", email: "ana@example.org",
    tax_id: "52998224725", fiscal_prefs: { cpf_na_nota: true, email_receipt: true },
    notes: "", dietary_restrictions: "", birthday_display: "", is_birthday_today: false,
    is_birthday_month: false, birthday_promo_label: "", price_tier: "", is_staff: false,
    default_address: null, saved_addresses: [],
    memory: { total_orders: 0, average_order_display: "", favorite_product: "", favorite_item: {}, last_order_items: [] },
    ...overrides,
  };
}

async function savedBody(offered: boolean, prepare: (sale: ReturnType<typeof makeSale>["sale"]) => void) {
  const actionCall = vi.fn().mockResolvedValue({});
  const h = makeSale({ projection: projection(offered), actionCall });
  const pao = h.handles.posValue.value!.products[0]!;
  h.sale.addProduct(pao);
  Object.assign(h.sale.cart, { tabRef: "M1", tabSessionKey: "sess-1" });
  prepare(h.sale);
  await h.sale.saveTab();
  const call = actionCall.mock.calls.find((c) => String(c[0]).includes("/tabs/save/"))!;
  h.handles.dispose();
  return call[1]!.body as Record<string, unknown>;
}

describe("bloco fiscal escondido — a venda não carrega pedido fiscal", () => {
  let disposers: Array<() => void>;
  beforeEach(() => { dollarFetch.mockReset(); disposers = []; });
  afterEach(() => { disposers.forEach((dispose) => dispose()); });

  it("associar cliente NÃO pré-marca CPF nem e-mail quando o bloco não existe", async () => {
    dollarFetch.mockResolvedValue({ customer: customer() });
    const { sale, handles } = makeSale({ projection: projection(false) });
    disposers.push(handles.dispose);
    sale.cart.customerRef = "CUST-1";
    sale.cart.customerPhone = "43999990011";

    await sale.lookupCustomer();

    expect(sale.cart.wantsCpfOnInvoice).toBe(false);
    expect(sale.cart.receiptChannels).toEqual([]);
  });

  it("controle: com o bloco na tela, os mesmos padrões pré-marcam como antes", async () => {
    dollarFetch.mockResolvedValue({ customer: customer() });
    const { sale, handles } = makeSale({ projection: projection(true) });
    disposers.push(handles.dispose);
    sale.cart.customerRef = "CUST-1";
    sale.cart.customerPhone = "43999990011";

    await sale.lookupCustomer();

    expect(sale.cart.wantsCpfOnInvoice).toBe(true);
    expect(sale.cart.invoiceTaxId).toBe("52998224725");
    expect(sale.cart.receiptChannels).toEqual(["email"]);
  });

  it("o interruptor do modal grava o rascunho do cadastro, mas não mexe na venda", () => {
    const { sale, handles } = makeSale({ projection: projection(false) });
    disposers.push(handles.dispose);
    sale.cart.customerTaxId = "52998224725";

    sale.applyCustomerPreference("cpf_na_nota", true);
    sale.applyCustomerPreference("email_receipt", true);

    expect(sale.pendingCustomerPrefs.value).toEqual({ cpf_na_nota: true, email_receipt: true });
    expect(sale.cart.wantsCpfOnInvoice).toBe(false);
    expect(sale.cart.receiptChannels).toEqual([]);
  });

  it("o intent não leva CPF nem canais — nem os que vieram de comanda reaberta", async () => {
    const body = await savedBody(false, (sale) => {
      Object.assign(sale.cart, {
        wantsCpfOnInvoice: true, invoiceTaxId: "52998224725",
        receiptChannels: ["print", "email"], receiptEmail: "ana@example.org",
      });
    });
    expect(body.fiscal_tax_id).toBeUndefined();
    expect(body.receipt_channels).toEqual([]);
    expect(body.receipt_email ?? "").toBe("");
  });

  it("controle: com o bloco na tela, o intent leva CPF e canais como antes", async () => {
    const body = await savedBody(true, (sale) => {
      Object.assign(sale.cart, {
        wantsCpfOnInvoice: true, invoiceTaxId: "52998224725",
        receiptChannels: ["print", "email"], receiptEmail: "ana@example.org",
      });
    });
    expect(body.fiscal_tax_id).toBe("52998224725");
    expect(body.receipt_channels).toEqual(["print", "email"]);
  });
});

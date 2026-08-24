// Cliente no write-side: o lookup agora é chaveado pelo REF (cliente sem
// telefone existe) e o resolve marca "criado agora" para a confirmação visual.
import { mockNuxtImport } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeSale } from "./_posSaleHarness";

// `$fetch` é auto-import do Nuxt (ofetch): stub de global não o alcança — o
// mock entra pelo registro de auto-imports, como o `useFetch` nos outros testes.
const { dollarFetch } = vi.hoisted(() => ({ dollarFetch: vi.fn() }));
mockNuxtImport("$fetch", () => dollarFetch);

function lookupProjection(overrides: Record<string, unknown> = {}) {
  return {
    ref: "CUST-9",
    name: "Noa Sem Telefone",
    phone: "",
    email: "",
    tax_id: "52998224725",
    fiscal_prefs: {},
    notes: "",
    dietary_restrictions: "",
    birthday_display: "",
    is_birthday_today: false,
    is_birthday_month: false,
    birthday_promo_label: "",
    price_tier: "",
    is_staff: false,
    default_address: null,
    saved_addresses: [],
    memory: { total_orders: 0, average_order_display: "", favorite_product: "", favorite_item: {}, last_order_items: [] },
    ...overrides,
  };
}

describe("usePosSale — cliente por ref e o flag de cadastro novo", () => {
  let disposers: Array<() => void>;

  beforeEach(() => {
    dollarFetch.mockReset().mockResolvedValue({ customer: lookupProjection() });
    disposers = [];
  });

  afterEach(() => {
    disposers.forEach((dispose) => dispose());
  });

  it("selecionar um resultado SEM telefone ainda carrega a memória (lookup por ref)", async () => {
    const { sale, handles } = makeSale();
    disposers.push(handles.dispose);

    await sale.selectCustomerResult({ ref: "CUST-9", name: "Noa Sem Telefone", phone: "", document: "52998224725", email: "" });

    expect(dollarFetch).toHaveBeenCalledTimes(1);
    const url = String(dollarFetch.mock.calls[0]?.[0]);
    expect(url).toContain("/pos/customer/lookup/");
    expect(url).toContain("ref=CUST-9");
    expect(sale.customerLookup.value?.ref).toBe("CUST-9");
    expect(sale.customerResolvedNew.value).toBe(false);
  });

  it("o resolve marca 'criado agora' quando o servidor diz created=true", async () => {
    const actionCall = vi.fn().mockResolvedValue({ customer: lookupProjection(), created: true });
    const { sale, handles } = makeSale({ actionCall });
    disposers.push(handles.dispose);

    sale.cart.customerTaxId = "52998224725";
    await sale.resolveCustomer();

    expect(sale.customerResolvedNew.value).toBe(true);
    expect(sale.cart.customerRef).toBe("CUST-9");

    // O mesmo CPF de novo: o servidor ACHOU (created=false) → o flag cai.
    actionCall.mockResolvedValue({ customer: lookupProjection(), created: false });
    await sale.resolveCustomer();
    expect(sale.customerResolvedNew.value).toBe(false);
  });

  it("remover o cliente zera também o flag de cadastro novo", async () => {
    const actionCall = vi.fn().mockResolvedValue({ customer: lookupProjection(), created: true });
    const { sale, handles } = makeSale({ actionCall });
    disposers.push(handles.dispose);

    sale.cart.customerTaxId = "52998224725";
    await sale.resolveCustomer();
    expect(sale.customerResolvedNew.value).toBe(true);

    sale.clearCustomer();
    expect(sale.customerResolvedNew.value).toBe(false);
    expect(sale.cart.customerRef).toBe("");
    expect(sale.customerLookup.value).toBeNull();
  });
});

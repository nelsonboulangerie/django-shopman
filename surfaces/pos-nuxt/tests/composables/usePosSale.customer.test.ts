// Cliente no write-side: o lookup agora é chaveado pelo REF (cliente sem
// telefone existe) e o resolve marca "criado agora" para a confirmação visual.
import { mockNuxtImport } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "vue-sonner";
import { injectableMethods } from "~/presentation/payment";
import { receiptSaveOffers } from "~/presentation/receiptContact";

import { makeSale, makeTabPayload } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

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

// UNIFICAR TEM VOLTA, E A VOLTA TEM PRAZO. O servidor devolve `undo_deadline`
// desde sempre; o PDV descartava. Quem unifica no balcão é o Caixa, que não
// tem `shop.manage_customers` — se o toast não contar, ninguém conta, e a
// janela de 24h fecha sozinha.
describe("usePosSale — o toast da unificação carrega o prazo do desfazer", () => {
  const disposers: Array<() => void> = [];

  beforeEach(() => {
    vi.mocked(toast.success).mockClear();
    dollarFetch.mockReset().mockResolvedValue({ customer: lookupProjection() });
  });

  afterEach(() => {
    disposers.forEach((dispose) => dispose());
    disposers.length = 0;
  });

  function armDecision(sale: ReturnType<typeof makeSale>["sale"]) {
    sale.customerDecision.value = {
      kind: "contact_conflict",
      field: "phone",
      typed: "(43) 99999-0011",
      current: { ref: "CUST-A", name: "Ana Prado", value: "" },
      other: { ref: "CUST-B", name: "Ana P.", value: "+5543999990011" },
    };
  }

  it("diz até quando dá para desfazer e a quem pedir", async () => {
    const deadline = new Date(Date.now() + 24 * 60 * 60 * 1000);
    const actionCall = vi.fn().mockResolvedValue({
      ok: true,
      customer: lookupProjection({ name: "Ana Prado" }),
      merge: {
        source_ref: "CUST-B",
        target_ref: "CUST-A",
        audit_id: "AUD-1",
        undo_deadline: deadline.toISOString(),
        migrated: { contact_points: 2, identifiers: 0, addresses: 0, orders: 3, loyalty: false },
      },
    });
    const { sale, handles } = makeSale({ actionCall });
    disposers.push(handles.dispose);

    armDecision(sale);
    await sale.mergeConflictCustomers();

    const [title, options] = vi.mocked(toast.success).mock.calls.at(-1) as [string, { description?: string }];
    expect(title).toBe("Cadastros unificados em Ana Prado.");
    expect(options.description).toContain("2 contatos e 3 pedidos passaram para este cadastro.");
    expect(options.description).toContain("Dá para desfazer até");
    expect(options.description).toContain("com o gerente, em Clientes → Unificações de cadastro");
  });

  it("sem prazo do servidor, o toast não promete um desfazer que não sabe datar", async () => {
    const actionCall = vi.fn().mockResolvedValue({
      ok: true,
      customer: lookupProjection({ name: "Ana Prado" }),
      merge: {
        source_ref: "CUST-B",
        target_ref: "CUST-A",
        audit_id: "AUD-2",
        undo_deadline: "",
        migrated: { contact_points: 1, identifiers: 0, addresses: 0, orders: 0, loyalty: false },
      },
    });
    const { sale, handles } = makeSale({ actionCall });
    disposers.push(handles.dispose);

    armDecision(sale);
    await sale.mergeConflictCustomers();

    const [, options] = vi.mocked(toast.success).mock.calls.at(-1) as [string, { description?: string }];
    expect(options.description).toBe("1 contato e 0 pedidos passaram para este cadastro.");
    expect(options.description).not.toContain("desfazer");
  });
});


describe("usePosSale — cadastro de comanda reaberta", () => {
  const disposers: Array<() => void> = [];
  afterEach(() => { disposers.splice(0).forEach(dispose => dispose()); });
  beforeEach(() => { dollarFetch.mockReset(); vi.mocked(toast.info).mockClear(); });

  it.each([["", "save"], ["52998224725", "none"], ["11144477735", "update"]])("restaura cadastro com CPF %s e oferta %s, sem reaplicar preferências", async (taxId, kind) => {
    const customer = lookupProjection({ tax_id: taxId, fiscal_prefs: { cpf_na_nota: true, email_receipt: true }, is_birthday_today: true, house_account: { enabled: true }, saved_addresses: [{ ref: "A1" }], memory: { favorite_item: { sku: "PAO" } } });
    dollarFetch.mockResolvedValue({ customer });
    const actionCall = vi.fn().mockResolvedValue(makeTabPayload({ customer_ref: customer.ref, customer_name: customer.name, fiscal_tax_id: "", fulfillment_type: "delivery", delivery_address: "Endereço desta venda" }));
    const { sale, handles } = makeSale({ actionCall }); disposers.push(handles.dispose);
    await sale.openTab("M1", { drawerChecked: true });
    expect(sale.customerLookup.value).toEqual(customer);
    expect(injectableMethods([], { houseAccount: Boolean(sale.customerLookup.value?.house_account) })).toHaveLength(1);
    expect(sale.cart.wantsCpfOnInvoice).toBe(false);
    expect(sale.cart.invoiceTaxId).toBe("");
    expect(sale.cart.receiptChannels).toEqual([]);
    expect(sale.cart.deliveryAddress).toBe("Endereço desta venda");
    expect(toast.info).not.toHaveBeenCalled();
    const offers = receiptSaveOffers({ customerRef: sale.cart.customerRef, customer: sale.customerLookup.value, receiptEmail: "", customerEmail: "", invoiceTaxId: "52998224725", wantsCpfOnInvoice: true, customerTaxId: "" });
    expect(offers.taxId.kind).toBe(kind);
    await sale.openTab("M1", { drawerChecked: true });
    expect(dollarFetch).toHaveBeenCalledTimes(1);
  });

  it("o CPF da nota acompanha cada comanda, sem vazar para a próxima", async () => {
    dollarFetch.mockResolvedValue({ customer: lookupProjection({ fiscal_prefs: { cpf_na_nota: false } }) });
    const actionCall = vi.fn().mockResolvedValueOnce(makeTabPayload({ customer_ref: "CUST-9", fiscal_tax_id: "52998224725" })).mockResolvedValueOnce(makeTabPayload({ tab_ref: "M2", tab_session_key: "sess-2", customer_ref: "CUST-9", fiscal_tax_id: "" }));
    const { sale, handles } = makeSale({ actionCall }); disposers.push(handles.dispose);
    await sale.openTab("M1", { drawerChecked: true });
    expect(sale.cart.wantsCpfOnInvoice).toBe(true);
    expect(sale.cart.invoiceTaxId).toBe("52998224725");
    await sale.openTab("M2", { drawerChecked: true });
    expect(sale.cart.wantsCpfOnInvoice).toBe(false);
    expect(sale.cart.invoiceTaxId).toBe("");
  });

  it("resposta atrasada não recoloca um cliente removido", async () => {
    let resolveLookup!: (value: unknown) => void;
    dollarFetch.mockImplementation(() => new Promise(resolve => { resolveLookup = resolve; }));
    const { sale, handles } = makeSale(); disposers.push(handles.dispose);
    sale.cart.customerRef = "CUST-9";
    const pending = sale.lookupCustomer();
    sale.clearCustomer();
    resolveLookup({ customer: lookupProjection() });
    await pending;
    expect(sale.customerLookup.value).toBeNull();
    expect(sale.cart.customerRef).toBe("");
    expect(sale.cart.invoiceTaxId).toBe("");
  });

  it("falha de rede mantém a comanda e não oferece criar outro cliente", async () => {
    dollarFetch.mockRejectedValue(new Error("offline"));
    const { sale, handles } = makeSale({ actionCall: vi.fn().mockResolvedValue(makeTabPayload({ customer_ref: "CUST-9", customer_name: "Noa" })) }); disposers.push(handles.dispose);
    await sale.openTab("M1", { drawerChecked: true });
    expect(sale.cart.tabRef).toBe("M1");
    expect(sale.cart.customerRef).toBe("CUST-9");
    expect(sale.customerLookup.value).toBeNull();
    const offers = receiptSaveOffers({ customerRef: sale.cart.customerRef, customer: null, receiptEmail: "", customerEmail: "", invoiceTaxId: "52998224725", wantsCpfOnInvoice: true, customerTaxId: "" });
    expect(offers.taxId.kind).toBe("none");
  });
});

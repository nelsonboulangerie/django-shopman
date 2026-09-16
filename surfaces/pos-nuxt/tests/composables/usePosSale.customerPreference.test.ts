// Virar um PADRÃO do cliente no modal vale NESTA venda, na hora — e nas
// próximas. "A venda de agora se decide no pagamento" não existe mais: o
// interruptor aplica ao carrinho aberto (CPF na nota / canal de e-mail) além de
// gravar no cadastro. Sem cadastro, o rascunho mora no shell e viaja no
// "Cadastrar cliente" como `fiscal_prefs` do resolve.
import { mockNuxtImport } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeSale } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

const { dollarFetch } = vi.hoisted(() => ({ dollarFetch: vi.fn() }));
mockNuxtImport("$fetch", () => dollarFetch);

function lookupProjection(overrides: Record<string, unknown> = {}) {
  return {
    ref: "CUST-NEW",
    name: "Outra Pessoa",
    phone: "+5543999990033",
    email: "",
    tax_id: "",
    fiscal_prefs: { cpf_na_nota: true },
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

describe("usePosSale.applyCustomerPreference — vale nesta venda, na hora", () => {
  let disposers: Array<() => void>;

  beforeEach(() => {
    dollarFetch.mockReset().mockResolvedValue({ customer: lookupProjection() });
    disposers = [];
  });

  afterEach(() => {
    disposers.forEach((dispose) => dispose());
  });

  it("cpf_na_nota LIGA o CPF na nota e copia o CPF do cadastro para o campo da nota vazio", () => {
    const { sale, handles } = makeSale();
    disposers.push(handles.dispose);
    sale.cart.customerTaxId = "52998224725";
    expect(sale.cart.wantsCpfOnInvoice).toBe(false);

    sale.applyCustomerPreference("cpf_na_nota", true);

    expect(sale.cart.wantsCpfOnInvoice).toBe(true);
    expect(sale.cart.invoiceTaxId).toBe("52998224725");
  });

  // A MESMA regra de `applyCustomerDefaults`: o CPF do cadastro é DEFAULT, não
  // sobrescreve o que o cliente pediu para esta nota.
  it("cpf_na_nota não passa por cima de um CPF já digitado na nota", () => {
    const { sale, handles } = makeSale();
    disposers.push(handles.dispose);
    sale.cart.customerTaxId = "52998224725";
    sale.cart.invoiceTaxId = "11144477735";

    sale.applyCustomerPreference("cpf_na_nota", true);

    expect(sale.cart.wantsCpfOnInvoice).toBe(true);
    expect(sale.cart.invoiceTaxId).toBe("11144477735");
  });

  it("cpf_na_nota DESLIGA o CPF na nota sem apagar o número (\"hoje não\" continua possível)", () => {
    const { sale, handles } = makeSale();
    disposers.push(handles.dispose);
    sale.cart.wantsCpfOnInvoice = true;
    sale.cart.invoiceTaxId = "52998224725";

    sale.applyCustomerPreference("cpf_na_nota", false);

    expect(sale.cart.wantsCpfOnInvoice).toBe(false);
    expect(sale.cart.invoiceTaxId).toBe("52998224725");
  });

  it("email_receipt LIGA o canal de e-mail uma vez só e DESLIGA removendo-o", () => {
    const { sale, handles } = makeSale();
    disposers.push(handles.dispose);
    sale.cart.receiptChannels = ["print"];

    sale.applyCustomerPreference("email_receipt", true);
    expect(sale.cart.receiptChannels).toEqual(["print", "email"]);
    sale.applyCustomerPreference("email_receipt", true);
    expect(sale.cart.receiptChannels).toEqual(["print", "email"]);

    sale.applyCustomerPreference("email_receipt", false);
    expect(sale.cart.receiptChannels).toEqual(["print"]);
  });

  it("sem cadastro o rascunho fica no shell e viaja no resolve como fiscal_prefs; depois zera", async () => {
    const actionCall = vi.fn().mockResolvedValue({ customer: lookupProjection(), created: true });
    const { sale, handles } = makeSale({ actionCall });
    disposers.push(handles.dispose);
    sale.cart.customerName = "Outra Pessoa";
    sale.cart.customerPhone = "43999990033";

    sale.applyCustomerPreference("cpf_na_nota", true);
    sale.applyCustomerPreference("email_receipt", false);
    expect(sale.pendingCustomerPrefs.value).toEqual({ cpf_na_nota: true, email_receipt: false });

    await sale.resolveCustomer();

    expect(actionCall.mock.calls[0]?.[1]?.body).toMatchObject({
      customer_name: "Outra Pessoa",
      fiscal_prefs: { cpf_na_nota: true, email_receipt: false },
    });
    expect(sale.cart.customerRef).toBe("CUST-NEW");
    expect(sale.pendingCustomerPrefs.value).toEqual({});
  });

  it("com nada ligado o resolve não manda fiscal_prefs", async () => {
    const actionCall = vi.fn().mockResolvedValue({ customer: lookupProjection(), created: true });
    const { sale, handles } = makeSale({ actionCall });
    disposers.push(handles.dispose);
    sale.cart.customerName = "Outra Pessoa";
    sale.applyCustomerPreference("cpf_na_nota", false);

    await sale.resolveCustomer();

    expect(actionCall.mock.calls[0]?.[1]?.body).not.toHaveProperty("fiscal_prefs");
  });

  // Com cadastro, o modal grava no perfil (POST parcial) — aqui só a venda de
  // agora muda, e o resolve não leva padrão nenhum.
  it("com cadastro não há rascunho: aplica à venda e o resolve segue sem fiscal_prefs", async () => {
    const actionCall = vi.fn().mockResolvedValue({ customer: lookupProjection({ ref: "CUST-A", name: "Ana Prado" }), created: false });
    const { sale, handles } = makeSale({ actionCall });
    disposers.push(handles.dispose);
    sale.cart.customerRef = "CUST-A";
    sale.cart.customerName = "Ana Prado";

    sale.applyCustomerPreference("email_receipt", true);
    expect(sale.cart.receiptChannels).toContain("email");
    expect(sale.pendingCustomerPrefs.value).toEqual({});

    await sale.resolveCustomer();
    expect(actionCall.mock.calls[0]?.[1]?.body).not.toHaveProperty("fiscal_prefs");
  });

  it("remover o cliente zera o rascunho", () => {
    const { sale, handles } = makeSale();
    disposers.push(handles.dispose);
    sale.applyCustomerPreference("cpf_na_nota", true);
    expect(sale.pendingCustomerPrefs.value).toEqual({ cpf_na_nota: true });

    sale.clearCustomer();
    expect(sale.pendingCustomerPrefs.value).toEqual({});
  });
});

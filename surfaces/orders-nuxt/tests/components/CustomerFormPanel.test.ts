import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import CustomerFormPanel from "../../app/components/CustomerFormPanel.vue";
import type { CustomerDetailProjection, CustomerFormOptionsProjection } from "../../app/generated/ordersContract";

const options: CustomerFormOptionsProjection = {
  customer_types: [
    { value: "individual", label: "Pessoa Física" },
    { value: "business", label: "Pessoa Jurídica" },
  ],
  price_tiers: [{ value: "varejo", label: "Varejo" }],
};

const customer = {
  ref: "CUST-ANA",
  name: "Ana Silva",
  is_active: true,
  revision: "2026-10-14T20:00:00+00:00",
  first_name: "Ana",
  last_name: "Silva",
  customer_type: "individual",
  document: "52998224725",
  birthday: "1990-05-10",
  phone: "+5543999991111",
  phone_display: "(43) 99999-1111",
  email: "ana@example.com",
  price_tier_ref: "varejo",
  price_tier_name: "Varejo",
  tags: ["vizinha"],
  notes: "Prefere retirada.",
  house_account: false,
  house_account_limit: "",
  fiscal_cpf_na_nota: false,
  fiscal_email_receipt: false,
  form: options,
  merged_into_ref: "",
  document_display: "529.982.247-25",
  birthday_display: "10/05",
  source_label: "Cadastro manual",
  is_ifood: false,
  created_display: "14/10/2026 às 20:00",
  orders_label: "Nenhum pedido",
  total_spent_display: "",
  last_order_display: "",
  identifiers: [],
  consents: [],
  addresses: [],
  recent_orders: [],
  candidates: [],
  actions: [],
} satisfies CustomerDetailProjection;

function panel(props: Record<string, unknown> = {}) {
  return mount(CustomerFormPanel, {
    props: { open: true, options, busy: false, error: "", ...props },
  });
}

describe("CustomerFormPanel", () => {
  it("explica que contato não concede consentimento", () => {
    const wrapper = panel();
    expect(wrapper.text()).toContain("Contato não é consentimento");
    expect(wrapper.text()).toContain("trilha LGPD");
  });

  it("cria com a fonte comercial e os campos normalizáveis", async () => {
    const wrapper = panel();
    await wrapper.get("[data-testid='customer-first-name']").setValue("Ana");
    await wrapper.get("[data-testid='customer-email']").setValue("ANA@EXAMPLE.COM");
    await wrapper.get("[data-testid='customer-submit']").trigger("click");

    expect(wrapper.emitted("save")?.[0]?.[0]).toEqual(expect.objectContaining({
      firstName: "Ana",
      email: "ANA@EXAMPLE.COM",
      priceTierRef: "varejo",
      tags: [],
    }));
  });

  it("edita com a revisão que protege contra outra aba", async () => {
    const wrapper = panel({ customer });
    await wrapper.get("[data-testid='customer-first-name']").setValue("Ana Clara");
    await wrapper.get("[data-testid='customer-submit']").trigger("click");

    expect(wrapper.emitted("save")?.[0]?.[0]).toEqual(expect.objectContaining({
      expectedRevision: customer.revision,
      firstName: "Ana Clara",
      tags: ["vizinha"],
    }));
  });

  it("não permite nota por e-mail sem endereço de e-mail", async () => {
    const wrapper = panel({ customer: { ...customer, email: "", fiscal_email_receipt: true } });
    expect(wrapper.text()).toContain("Informe o e-mail que receberá a nota.");
    expect(wrapper.get("[data-testid='customer-submit']").attributes("disabled")).toBeDefined();
  });

  it("não permite CPF na nota sem documento", () => {
    const wrapper = panel({ customer: { ...customer, document: "", fiscal_cpf_na_nota: true } });
    expect(wrapper.text()).toContain("Informe o CPF ou CNPJ usado na nota.");
    expect(wrapper.get("[data-testid='customer-submit']").attributes("disabled")).toBeDefined();
  });

  it("mostra a recusa no campo apontado pelo servidor", () => {
    const wrapper = panel({ fieldErrors: { document: "O CPF ou CNPJ não confere." } });
    expect(wrapper.text()).toContain("O CPF ou CNPJ não confere.");
  });
});

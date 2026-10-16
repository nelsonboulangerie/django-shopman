import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import CustomerDuplicatePanel from "../../app/components/CustomerDuplicatePanel.vue";
import type { CustomerDetailProjection, CustomerFormOptionsProjection } from "../../app/generated/ordersContract";

const options: CustomerFormOptionsProjection = {
  customer_types: [
    { value: "individual", label: "Pessoa Física" },
    { value: "business", label: "Pessoa Jurídica" },
  ],
  price_tiers: [{ value: "varejo", label: "Varejo" }],
};

const source = {
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
  price_tiers: [{ ref: "varejo", name: "Varejo", is_primary: true }],
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
  return mount(CustomerDuplicatePanel, {
    props: { open: true, source, busy: false, error: "", ...props },
  });
}

function inputValue(wrapper: ReturnType<typeof panel>, selector: string): string {
  return (wrapper.get(selector).element as HTMLInputElement).value;
}

describe("CustomerDuplicatePanel", () => {
  it("diz o que a cópia leva e o que não leva", () => {
    const wrapper = panel();
    expect(wrapper.text()).toContain("O que a cópia leva");
    expect(wrapper.text()).toContain("Não leva CPF/CNPJ, telefone nem e-mail");
  });

  it("nasce com o nome da cópia e envia a revisão do original", async () => {
    const wrapper = panel();
    expect(inputValue(wrapper, "[data-testid='customer-duplicate-first-name']")).toBe("Ana");
    expect(inputValue(wrapper, "[data-testid='customer-duplicate-last-name']")).toBe("Silva (cópia)");

    await wrapper.get("[data-testid='customer-duplicate-submit']").trigger("click");

    expect(wrapper.emitted("save")?.[0]?.[0]).toEqual({
      expectedRevision: source.revision,
      firstName: "Ana",
      lastName: "Silva (cópia)",
    });
  });

  it("não deixa duplicar sem nome", () => {
    const wrapper = panel({ source: { ...source, first_name: "" } });
    expect(wrapper.text()).toContain("Informe o nome da cópia.");
    expect(wrapper.get("[data-testid='customer-duplicate-submit']").attributes("disabled")).toBeDefined();
  });
});

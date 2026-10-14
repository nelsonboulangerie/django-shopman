// O cadastro do insumo e do fornecedor no casco. O casco de verdade já tem os
// testes dele no kit; aqui se cobra o que é DO APP: a validação que escreve o
// motivo, o payload que sai e o comportamento de cada modo (criar, editar,
// duplicar). A gaveta é substituída por um dublê que mostra o motivo e tem o
// botão de salvar, para o gesto poder ser disparado.
import { computed, defineComponent, h, reactive, ref, watch } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import PurchaseMaterialFormPanel from "../../app/components/PurchaseMaterialFormPanel.vue";
import PurchaseSupplierFormPanel from "../../app/components/PurchaseSupplierFormPanel.vue";
import type { Material, MaterialConversion, Supplier } from "../../app/types/purchase";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("reactive", reactive);
vi.stubGlobal("watch", watch);

const ShellStub = defineComponent({
  name: "OperatorFormShell",
  props: {
    open: Boolean,
    title: String,
    dirty: Boolean,
    dirtyCount: Number,
    saveLabel: String,
    saveDisabled: Boolean,
    saveDisabledReason: String,
    activeSection: String,
  },
  emits: ["update:open", "save"],
  setup(props, { emit, slots }) {
    return () =>
      h("div", { "data-shell": "" }, [
        h("p", { "data-testid": "shell-title" }, props.title),
        h("p", { "data-testid": "save-label" }, props.saveLabel),
        h("p", { "data-testid": "save-disabled" }, String(props.saveDisabled)),
        h("p", { "data-testid": "save-reason" }, props.saveDisabledReason),
        h("button", { "data-testid": "shell-save", onClick: () => emit("save") }, "salvar"),
        slots.default?.(),
      ]);
  },
});

const farinha: Material = {
  sku: "FAR-T65",
  name: "Farinha T65",
  unit: "kg",
  shelfLifeDays: 180,
  isActive: true,
  category: "Farinhas",
  stockOnHand: 40,
  dailyUse: 18,
  minStock: 90,
  recipes: ["Baguete"],
};

const saco: MaterialConversion = {
  id: "c1",
  materialSku: "FAR-T65",
  supplierRef: null,
  label: "saco 25 kg",
  toBaseFactor: 25,
  kind: "conventional",
  isActive: true,
};

const moinho: Supplier = {
  ref: "moinho-sp",
  name: "Moinho São Paulo",
  tradeName: "Moinho SP",
  displayName: "Moinho SP",
  document: "12.345.678/0001-90",
  email: "compras@moinho.example",
  phone: "(43) 3333-0000",
  contact: "compras@moinho.example",
  contacts: [
    {
      id: "7",
      name: "Cláudia Ramos",
      role: "sales",
      roleLabel: "Comercial",
      email: "claudia@moinho.example",
      phone: "",
      isPrimary: true,
      isActive: true,
      notes: "",
    },
  ],
  orderContactName: "Cláudia Ramos",
  leadTimeDays: 2,
  reliabilityPercent: 97,
  isActive: true,
  lastDeliveryAt: "2026-10-06",
  paymentTerm: "28 dias",
};

function mountMaterial(props: Record<string, unknown>) {
  return mount(PurchaseMaterialFormPanel, {
    props: { open: true, ...props },
    global: { stubs: { OperatorFormShell: ShellStub } },
  });
}

function mountSupplier(props: Record<string, unknown>) {
  return mount(PurchaseSupplierFormPanel, {
    props: { open: true, ...props },
    global: { stubs: { OperatorFormShell: ShellStub } },
  });
}

describe("PurchaseMaterialFormPanel", () => {
  it("criar: o SKU e o nome são obrigatórios, e o motivo fica escrito", async () => {
    const wrapper = mountMaterial({ mode: "create" });
    expect(wrapper.find('[data-testid="save-disabled"]').text()).toBe("true");
    expect(wrapper.find('[data-testid="save-reason"]').text()).toBe("Informe o SKU para salvar.");

    await wrapper.find('[data-testid="material-sku"]').setValue("NOVO-INSUMO");
    expect(wrapper.find('[data-testid="save-reason"]').text()).toBe("Informe o nome para salvar.");
  });

  it("criar: salvar emite o payload completo e converte a validade", async () => {
    const wrapper = mountMaterial({ mode: "create" });
    await wrapper.find('[data-testid="material-sku"]').setValue("NOVO-INSUMO");
    await wrapper.find('[data-testid="material-name"]').setValue("Novo insumo");
    await wrapper.find('[data-testid="material-category"]').setValue("Farinhas");
    await wrapper.find('[data-testid="material-shelf-life"]').setValue("90");
    await wrapper.find('[data-testid="shell-save"]').trigger("click");

    expect(wrapper.emitted("save")![0][0]).toEqual({
      sku: "NOVO-INSUMO",
      name: "Novo insumo",
      unit: "un",
      shelfLifeDays: 90,
      isActive: true,
      category: "Farinhas",
    });
  });

  it("duplicar: nasce sugerido e recusa repetir o SKU do original", async () => {
    const wrapper = mountMaterial({ mode: "duplicate", source: farinha });
    expect((wrapper.find('[data-testid="material-sku"]').element as HTMLInputElement).value).toBe("FAR-T65-COPIA");
    expect((wrapper.find('[data-testid="material-name"]').element as HTMLInputElement).value).toBe("Farinha T65 (cópia)");

    await wrapper.find('[data-testid="material-sku"]').setValue("FAR-T65");
    expect(wrapper.find('[data-testid="save-reason"]').text()).toBe("O SKU da cópia precisa ser diferente do original.");

    await wrapper.find('[data-testid="material-sku"]').setValue("FAR-T80");
    await wrapper.find('[data-testid="shell-save"]').trigger("click");
    expect(wrapper.emitted("save")![0][0]).toEqual({ sku: "FAR-T80", name: "Farinha T65 (cópia)" });
  });

  it("editar: adicionar conversão emite o payload da declaração", async () => {
    const wrapper = mountMaterial({ mode: "edit", source: farinha, conversions: [saco], costs: [], suppliers: [] });
    await wrapper.find('[data-testid="conversion-add"]').trigger("click");
    await wrapper.find('[data-testid="conversion-label"]').setValue("pacote 5 kg");
    await wrapper.find('[data-testid="conversion-factor"]').setValue("5");
    await wrapper.find('[data-testid="conversion-form"]').trigger("submit");

    expect(wrapper.emitted("save-conversion")![0][0]).toEqual({
      conversionId: null,
      label: "pacote 5 kg",
      factor: "5",
      kind: "conventional",
      supplierRef: null,
      isActive: true,
    });
  });

  it("editar: editar a conversão existente manda o id", async () => {
    const wrapper = mountMaterial({ mode: "edit", source: farinha, conversions: [saco], costs: [], suppliers: [] });
    // O Editar da linha da conversão é o botão com esse rótulo.
    const edit = wrapper.findAll("button").find((button) => button.text() === "Editar");
    await edit!.trigger("click");
    await wrapper.find('[data-testid="conversion-factor"]').setValue("20");
    await wrapper.find('[data-testid="conversion-form"]').trigger("submit");

    expect(wrapper.emitted("save-conversion")![0][0]).toMatchObject({ conversionId: "c1", factor: "20" });
  });
});

describe("PurchaseSupplierFormPanel", () => {
  it("criar: exige a razão social", async () => {
    const wrapper = mountSupplier({ mode: "create" });
    expect(wrapper.find('[data-testid="save-reason"]').text()).toBe("Informe a razão social para salvar.");

    await wrapper.find('[data-testid="supplier-name"]').setValue("Moinho Novo");
    await wrapper.find('[data-testid="shell-save"]').trigger("click");
    expect(wrapper.emitted("save")![0][0]).toEqual({
      ref: "",
      name: "Moinho Novo",
      tradeName: "",
      document: "",
      email: "",
      phone: "",
      isActive: true,
      leadTimeDays: 0,
      paymentTerm: "",
    });
  });

  it("duplicar: sugere ref e nome, e recusa repetir a referência", async () => {
    const wrapper = mountSupplier({ mode: "duplicate", source: moinho });
    expect((wrapper.find('[data-testid="supplier-ref"]').element as HTMLInputElement).value).toBe("moinho-sp-2");

    await wrapper.find('[data-testid="supplier-ref"]').setValue("moinho-sp");
    expect(wrapper.find('[data-testid="save-reason"]').text()).toBe("A referência da cópia precisa ser diferente da original.");

    await wrapper.find('[data-testid="supplier-ref"]').setValue("moinho-sp-filial");
    await wrapper.find('[data-testid="shell-save"]').trigger("click");
    expect(wrapper.emitted("save")![0][0]).toMatchObject({ ref: "moinho-sp-filial" });
  });

  it("editar: contato sem e-mail nem telefone fica bloqueado com o motivo", async () => {
    const wrapper = mountSupplier({ mode: "edit", source: moinho });
    await wrapper.find('[data-testid="contact-add"]').trigger("click");
    await wrapper.find('[data-testid="contact-name"]').setValue("Sem meio");
    expect(wrapper.find('[data-testid="contact-submit"]').attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("Informe e-mail ou telefone");

    await wrapper.find('[data-testid="contact-email"]').setValue("novo@moinho.example");
    await wrapper.find('[data-testid="contact-form"]').trigger("submit");
    expect(wrapper.emitted("save-contact")![0][0]).toMatchObject({
      contactId: null,
      name: "Sem meio",
      email: "novo@moinho.example",
    });
  });

  it("editar: editar contato existente manda o id", async () => {
    const wrapper = mountSupplier({ mode: "edit", source: moinho });
    const edit = wrapper.findAll("button").find((button) => button.text() === "Editar");
    await edit!.trigger("click");
    await wrapper.find('[data-testid="contact-email"]').setValue("outra@moinho.example");
    await wrapper.find('[data-testid="contact-form"]').trigger("submit");

    expect(wrapper.emitted("save-contact")![0][0]).toMatchObject({ contactId: "7", email: "outra@moinho.example" });
  });
});

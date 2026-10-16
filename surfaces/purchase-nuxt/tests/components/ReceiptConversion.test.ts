// "Como isto é contado": a escolha da embalagem do item.
//
// Contrato, não estilo: "Direto na unidade" é a AUSÊNCIA de embalagem. O
// `NuxtSelect` não aceita item de valor vazio, então ela tem um valor próprio na
// lista, e o que sai do componente é `null`, nunca esse valor nem a string "null":
// a linha não pode voltar com uma conversão que não existe.
import { computed, ref } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import ReceiptConversion from "../../app/components/ReceiptConversion.vue";
import ReceiptField from "../../app/components/ReceiptField.vue";
import { receiptLinePreview } from "../../app/presentation/purchase";
import type { Material, MaterialConversion, ReceiptLine } from "../../app/types/purchase";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);

const farinha: Material = {
  sku: "FAR-T1",
  name: "Farinha tipo 1",
  unit: "kg",
  shelfLifeDays: 180,
  isActive: true,
  category: "Secos",
  stockOnHand: 50,
  dailyUse: 10,
  minStock: 40,
  recipes: [],
};

const saco: MaterialConversion = {
  id: "saco", materialSku: "FAR-T1", supplierRef: null, label: "saco 25 kg", toBaseFactor: 25, kind: "conventional", isActive: true,
};

function mountConversion(patch: Partial<ReceiptLine> = {}) {
  const line: ReceiptLine = {
    id: "l1",
    materialSku: "FAR-T1",
    conversionId: "saco",
    purchaseQty: 4,
    costInput: "400,00",
    expiryDate: "",
    lineNote: "",
    checked: false,
    ...patch,
  };
  return mount(ReceiptConversion, {
    props: { preview: receiptLinePreview(line, "manual", [farinha], [saco])!, conversions: [saco] },
    global: { components: { ReceiptField }, stubs: { Icon: true } },
  });
}

describe("ReceiptConversion: como isto é contado", () => {
  it("a lista oferece 'Direto em kg' e as embalagens cadastradas", () => {
    const select = mountConversion().find("[data-receipt-conversion-select]");
    const options = select.findAll("option").map((option) => option.text());
    expect(options).toEqual(["Direto em kg", "saco 25 kg"]);
  });

  it("escolher 'Direto' sai como null; escolher a embalagem sai com o id dela", async () => {
    const wrapper = mountConversion();
    const select = wrapper.find("[data-receipt-conversion-select]");

    await select.setValue("__direct__");
    await select.setValue("saco");

    expect(wrapper.emitted("select")).toEqual([[null], ["saco"]]);
  });

  it("cadastrar embalagem só salva com nome e fator, e manda o fator com ponto", async () => {
    const wrapper = mountConversion();
    const declare = wrapper.findAll("button").find((button) => button.text().includes("Cadastrar embalagem"))!;
    await declare.trigger("click");

    const save = () => wrapper.findAll("button").find((button) => button.text().includes("Salvar"))!;
    expect(save().attributes("disabled")).toBeDefined();

    const inputs = wrapper.find("[data-receipt-conversion-declare]").findAll("input");
    await inputs[0]!.setValue("fardo 10 kg");
    await inputs[1]!.setValue("10,5");
    await save().trigger("click");

    expect(wrapper.emitted("declare")).toEqual([[{ label: "fardo 10 kg", factor: "10.5", kind: "conventional" }]]);
  });
});

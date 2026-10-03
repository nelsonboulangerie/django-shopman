// A conferência por exceção na doca (UX-C1): o ato físico, a validade com um
// toque, e "Trocar". Contrato, não estilo:
//
// 1. **"Contei N volumes" grava o número do stepper**, e mexer no número depois
//    desfaz a declaração (ela só vale para o número que o recebedor viu);
// 2. **um toque no atalho grava a validade** daquela linha;
// 3. **a contagem tem endereço** (`data-receipt-anchor="volumes"`): é para lá que
//    o "Confirmar entrada" leva quando falta contar.
import { computed, ref, watch } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import ReceiptExceptionFlow from "../../app/components/ReceiptExceptionFlow.vue";
import { receiptExceptionView, receiptLinePreview } from "../../app/presentation/purchase";
import type { Material, MaterialConversion, ReceiptLine } from "../../app/types/purchase";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);

const manteiga: Material = {
  sku: "MANT-SS",
  name: "Manteiga sem sal",
  unit: "kg",
  shelfLifeDays: 7,
  isActive: true,
  category: "Frescos",
  stockOnHand: 4,
  dailyUse: 2,
  minStock: 6,
  recipes: [],
};

const caixa: MaterialConversion = {
  id: "caixa", materialSku: "MANT-SS", supplierRef: null, label: "caixa 5 kg", toBaseFactor: 5, kind: "conventional", isActive: true,
};

function viewOf(counted: number | null, patch: Partial<ReceiptLine> = {}) {
  const line: ReceiptLine = {
    id: "l1",
    materialSku: "MANT-SS",
    conversionId: "caixa",
    purchaseQty: 4,
    invoicePurchaseQty: 4,
    invoiceUnit: "CX",
    costInput: "880,00",
    invoiceTotal: "880,00",
    expiryDate: "",
    lineNote: "",
    checked: false,
    ...patch,
  };
  const previews = [receiptLinePreview(line, "invoice", [manteiga], [caixa])!];
  return receiptExceptionView(previews, "invoice", 0, counted);
}

function mountFlow(counted: number | null = null) {
  return mount(ReceiptExceptionFlow, {
    props: { view: viewOf(counted), materials: [manteiga], lineCount: 1, totalCostQ: 88000, declaredVolumes: 0 },
    global: { stubs: { Icon: true, OperatorDayPicker: true } },
  });
}

function buttonWith(wrapper: ReturnType<typeof mountFlow>, text: string) {
  const button = wrapper.findAll("button").find((item) => item.text().includes(text));
  if (!button) throw new Error(`sem botão "${text}"`);
  return button;
}

describe("ReceiptExceptionFlow — a conferência por exceção", () => {
  it("o stepper nasce no esperado e 'Contei' declara esse número", async () => {
    const wrapper = mountFlow();
    expect(wrapper.find('[data-receipt-anchor="volumes"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("Tudo bate com a nota");

    await buttonWith(wrapper, "Contei 4 volumes").trigger("click");
    expect(wrapper.emitted("count")).toEqual([[4]]);
  });

  it("um volume a menos muda o que se declara", async () => {
    const wrapper = mountFlow();
    await wrapper.find('[aria-label="Um volume a menos"]').trigger("click");
    await buttonWith(wrapper, "Contei 3 volumes").trigger("click");
    expect(wrapper.emitted("count")).toEqual([[3]]);
  });

  it("mexer no número depois de declarar desfaz a declaração", async () => {
    const wrapper = mountFlow(4);
    expect(wrapper.text()).toContain("4 de 4 volumes contados");
    await wrapper.find('[aria-label="Um volume a mais"]').trigger("click");
    expect(wrapper.emitted("count")).toEqual([[null]]);
  });

  it("falta só a validade: um toque no atalho grava a data da linha", async () => {
    const wrapper = mountFlow(4);
    expect(wrapper.text()).toContain("Falta só a validade");
    await buttonWith(wrapper, "Típica: +7 dias").trigger("click");
    const [lineId, date] = wrapper.emitted("expiry")![0] as [string, string];
    expect(lineId).toBe("l1");
    expect(date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

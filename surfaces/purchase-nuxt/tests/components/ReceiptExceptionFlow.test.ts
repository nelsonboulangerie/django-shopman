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
import type { Material, MaterialConversion, ReceiptLine, ReceiptPriceCheck } from "../../app/types/purchase";

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

function mountFlow(counted: number | null = null, extra: { priceCheck?: ReceiptPriceCheck | null; lineCount?: number } = {}) {
  return mount(ReceiptExceptionFlow, {
    props: { view: viewOf(counted), materials: [manteiga], lineCount: 1, totalCostQ: 88000, declaredVolumes: 0, ...extra },
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

  it("contou e bateu: o cartão recolhe numa linha, e Recontar desfaz a declaração (v4 b)", async () => {
    const wrapper = mountFlow(4);
    expect(wrapper.text()).toContain("4 de 4 volumes contados");
    expect(wrapper.find('[aria-label="Um volume a mais"]').exists()).toBe(false);
    await buttonWith(wrapper, "Recontar").trigger("click");
    expect(wrapper.emitted("count")).toEqual([[null]]);
  });

  it("antes de contar: Bipar cada volume e o aviso do que vem depois (v4 a)", async () => {
    const wrapper = mountFlow(null);
    expect(wrapper.find("[data-scan-volumes]").text()).toContain("Bipar cada volume");
    await wrapper.find("[data-scan-volumes]").trigger("click");
    expect(wrapper.emitted("scan-volumes")).toHaveLength(1);
  });

  it("falta só a validade: um toque no atalho grava a data da linha", async () => {
    const wrapper = mountFlow(4);
    expect(wrapper.text()).toContain("Falta só a validade");
    await buttonWith(wrapper, "Típica: +7 dias").trigger("click");
    const [lineId, date] = wrapper.emitted("expiry")![0] as [string, string];
    expect(lineId).toBe("l1");
    expect(date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  // Nenhuma frase de "o sistema conferiu" sem o dado que a sustenta (DEV-2026-032).
  it("sem preço medido, o bloco do que o sistema conferiu não aparece", () => {
    const wrapper = mountFlow(null);
    expect(wrapper.text()).toContain("Tudo bate com a nota");
    expect(wrapper.find("[data-exception-facts]").exists()).toBe(false);
    for (const text of ["de-para", "reconhecidos", "Embalagens conferem", "último pago", "Preço"]) {
      expect(wrapper.text()).not.toContain(text);
    }
  });

  it("nenhum item com custo preferencial para comparar: nenhuma frase de preço", () => {
    const wrapper = mountFlow(null, { priceCheck: { compared: 0, same: 0 } });
    expect(wrapper.find("[data-exception-facts]").exists()).toBe(false);
  });

  it("o preço medido vira a frase, com o número da medida", () => {
    const wrapper = mountFlow(null, { priceCheck: { compared: 12, same: 11 }, lineCount: 12 });
    const facts = wrapper.findAll("[data-exception-facts] li").map((item) => item.text());
    expect(facts).toEqual(["Preço igual ao custo preferencial do fornecedor em 11 de 12 itens"]);
  });

  it("item sem custo para comparar é dito, para o denominador não mentir", () => {
    const wrapper = mountFlow(null, { priceCheck: { compared: 1, same: 1 }, lineCount: 3 });
    const facts = wrapper.findAll("[data-exception-facts] li").map((item) => item.text());
    expect(facts).toEqual([
      "Preço igual ao custo preferencial do fornecedor em 1 de 1 item (2 sem custo preferencial para comparar)",
    ]);
  });
});

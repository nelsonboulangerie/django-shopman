import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { Material, MaterialConversion, ReceiptLine, SupplierMaterialCost } from "~/types/purchase";
import { receiptLinePreview, receiptPreferredCostChanges } from "~/presentation/purchase";

// Beta test 05/11/2026, achado CMP-06; decisão do dono em 06/11.
// (a) No recebimento, fornecedor e item nascem vazios: o primeiro da ordem
//     alfabética entrava sozinho, como se alguém o tivesse escolhido.
// (b) Receber com preço diferente do custo preferencial não troca esse custo em
//     silêncio: a entrada pergunta "Atualizar" ou "Manter", com os dois valores.

const desk = readFileSync(resolve(__dirname, "../app/composables/usePurchaseDesk.ts"), "utf8");
const page = readFileSync(resolve(__dirname, "../app/pages/receive.vue"), "utf8");

const farinha: Material = {
  sku: "FAR-T65",
  name: "Farinha T65",
  unit: "kg",
  shelfLifeDays: null,
  isActive: true,
  category: "Farinhas",
  stockOnHand: 0,
  dailyUse: 0,
  minStock: 0,
  recipes: [],
};
const saco: MaterialConversion = {
  id: "c-saco",
  materialSku: "FAR-T65",
  supplierRef: "moinho",
  label: "saco 25 kg",
  toBaseFactor: 25,
  kind: "exact",
  isActive: true,
};
const pacote: MaterialConversion = { ...saco, id: "c-pacote", label: "pacote 1 kg", toBaseFactor: 1 };
const conversions = [saco, pacote];
const preferido: SupplierMaterialCost = {
  id: "1",
  materialSku: "FAR-T65",
  supplierRef: "moinho",
  conversionId: "c-saco",
  costQ: 18000,
  isPreferred: true,
  updatedAt: "",
};

function line(patch: Partial<ReceiptLine> = {}): ReceiptLine {
  return {
    id: "l1",
    materialSku: "FAR-T65",
    conversionId: "c-saco",
    purchaseQty: 1,
    costInput: "180,00",
    expiryDate: "",
    lineNote: "",
    checked: true,
    ...patch,
  };
}

function changes(lines: ReceiptLine[], costs = [preferido], supplierRef = "moinho") {
  const previews = lines
    .map((item) => receiptLinePreview(item, "manual", [farinha], conversions))
    .filter((preview) => preview !== null);
  return receiptPreferredCostChanges(previews, costs, supplierRef, conversions);
}

describe("item e fornecedor nascem vazios no recebimento (CMP-06 a)", () => {
  it("adicionar item não escolhe o primeiro insumo da lista", () => {
    const body = desk.slice(desk.indexOf("function addReceiptLine()"), desk.indexOf("function removeReceiptLine("));
    expect(body).toContain('const materialSku = "";');
    expect(body).not.toMatch(/materials\.value\[0\]/);
  });

  it("trocar entre Com NF e Sem NF zera o fornecedor em vez de pegar o primeiro", () => {
    const body = desk.slice(desk.indexOf("function setReceiptMode("), desk.indexOf("function setReceiptVolumesCounted("));
    expect(body).toContain('receiptSupplierRef.value = "";');
    expect(body).not.toMatch(/suppliers\.value\[0\]/);
  });
});

describe("preço diferente do custo preferencial pergunta antes (CMP-06 b)", () => {
  it("mesmo preço não pergunta nada", () => {
    expect(changes([line()])).toEqual([]);
    expect(changes([line({ purchaseQty: 2, costInput: "360,00" })])).toEqual([]);
  });

  it("mesmo preço em outra embalagem não pergunta", () => {
    expect(changes([line({ conversionId: "c-pacote", purchaseQty: 25, costInput: "180,00" })])).toEqual([]);
  });

  it("preço diferente mostra os dois valores na unidade do custo preferencial", () => {
    expect(changes([line({ costInput: "198,00" })])).toEqual([
      {
        lineId: "l1",
        materialName: "Farinha T65",
        unitLabel: "saco 25 kg",
        currentQ: 18000,
        incomingQ: 19800,
        decision: "",
      },
    ]);
    // Em pacote de 1 kg, o preço recebido é levado ao saco de 25 kg.
    expect(changes([line({ conversionId: "c-pacote", purchaseQty: 25, costInput: "200,00" })])[0]).toMatchObject({
      currentQ: 18000,
      incomingQ: 20000,
      unitLabel: "saco 25 kg",
    });
  });

  it("a resposta do operador acompanha o item", () => {
    expect(changes([line({ costInput: "198,00", preferredCost: "keep" })])[0]?.decision).toBe("keep");
  });

  it("preferencial de outro fornecedor ou insumo sem custo não pergunta", () => {
    expect(changes([line({ costInput: "198,00" })], [{ ...preferido, supplierRef: "outro" }])).toEqual([]);
    expect(changes([line({ costInput: "198,00" })], [])).toEqual([]);
    expect(changes([line({ costInput: "198,00" })], [{ ...preferido, isPreferred: false }])).toEqual([]);
    expect(changes([line({ costInput: "198,00" })], [preferido], "")).toEqual([]);
  });

  it("mexer em preço, quantidade, embalagem ou item desfaz a resposta", () => {
    expect(desk).toMatch(/PRICE_FIELDS[^=]*= \["costInput", "purchaseQty", "conversionId", "materialSku"\]/);
    expect(desk).toMatch(/repriced \? \{ preferredCost: "" as const \}/);
  });

  it("confirmar a entrada abre a pergunta enquanto algum item não respondeu", () => {
    const body = page.slice(page.indexOf("async function onConfirmReceipt()"), page.indexOf("async function onRejectReceipt()"));
    expect(body).toMatch(/if \(!preferredCostAnswered\.value\) \{\s*preferredCostOpen\.value = true;\s*return;/);
    expect(page).toContain("Atualizar para ${formatMoney(change.incomingQ)}");
    expect(page).toContain("Manter ${formatMoney(change.currentQ)}");
    expect(page).toMatch(/:disabled="!preferredCostAnswered"/);
  });
});

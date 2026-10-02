import { describe, expect, it } from "vitest";

import type { POSCartItemOption, POSProductOptionGroup } from "~/types/pos";
import { buildPosSaleIntent } from "~/utils/posIntent";
import { orderEditBody } from "~/presentation/orderEdit";
import { choiceGroup } from "~/presentation/catalog";
import {
  groupMissing,
  groupRuleLabel,
  hasOptionGroups,
  lineUnitPriceQ,
  optionLineName,
  optionPriceLabel,
  optionsIntent,
  optionsSignature,
  optionsSummary,
  selectedCartOptions,
  selectionValid,
  toggleOption,
} from "~/presentation/productOptions";

const sabor: POSProductOptionGroup = {
  ref: "sabor",
  label: "Sabor",
  min: 1,
  max: 1,
  options: [
    { ref: "cafe", label: "Café", price_q: 0, available: true },
    { ref: "chocolate", label: "Chocolate", price_q: 0, available: true },
    { ref: "frutas", label: "Frutas vermelhas", price_q: 0, available: false },
  ],
};

const adicionais: POSProductOptionGroup = {
  ref: "adicionais",
  label: "Adicionais",
  min: 0,
  max: 2,
  options: [
    { ref: "ovo", label: "Ovo frito", price_q: 400, available: true },
    { ref: "salada", label: "Salada", price_q: 300, available: true },
    { ref: "bacon", label: "Bacon", price_q: 500, available: true },
  ],
};

const ovo: POSCartItemOption = { group: "adicionais", ref: "ovo", group_label: "Adicionais", name: "Ovo frito", unit_price_q: 400 };
const salada: POSCartItemOption = { group: "adicionais", ref: "salada", group_label: "Adicionais", name: "Salada", unit_price_q: 300 };

describe("escolhas no produto · apresentação", () => {
  it("sabe quando o produto abre a escolha", () => {
    expect(hasOptionGroups({ option_groups: [adicionais] })).toBe(true);
    expect(hasOptionGroups({ option_groups: [] })).toBe(false);
    expect(hasOptionGroups({})).toBe(false);
  });

  it("assinatura: group:ref ordenados; vazio e ausente são o mesmo", () => {
    expect(optionsSignature([salada, ovo])).toBe("adicionais:ovo|adicionais:salada");
    expect(optionsSignature([ovo, salada])).toBe(optionsSignature([salada, ovo]));
    expect(optionsSignature([])).toBe("");
    expect(optionsSignature(undefined)).toBe("");
    expect(optionsSignature([ovo])).not.toBe(optionsSignature([salada]));
  });

  it("regra legível do grupo", () => {
    expect(groupRuleLabel({ min: 1, max: 1 })).toBe("Escolha 1");
    expect(groupRuleLabel({ min: 0, max: 1 })).toBe("Opcional");
    expect(groupRuleLabel({ min: 0, max: 2 })).toBe("Opcional, até 2");
    expect(groupRuleLabel({ min: 2, max: 2 })).toBe("Escolha 2");
    expect(groupRuleLabel({ min: 1, max: 3 })).toBe("Escolha de 1 a 3");
  });

  it("escolha única troca; indisponível não entra; obrigatória não desmarca", () => {
    let sel = toggleOption(sabor, {}, "cafe");
    expect(sel.sabor).toEqual(["cafe"]);
    sel = toggleOption(sabor, sel, "chocolate");
    expect(sel.sabor).toEqual(["chocolate"]);
    sel = toggleOption(sabor, sel, "frutas");
    expect(sel.sabor).toEqual(["chocolate"]);
    sel = toggleOption(sabor, sel, "chocolate");
    expect(sel.sabor).toEqual(["chocolate"]);
  });

  it("múltipla marca até o máximo e desmarca no segundo toque", () => {
    let sel = toggleOption(adicionais, {}, "ovo");
    sel = toggleOption(adicionais, sel, "salada");
    sel = toggleOption(adicionais, sel, "bacon");
    expect(sel.adicionais).toEqual(["ovo", "salada"]);
    sel = toggleOption(adicionais, sel, "ovo");
    expect(sel.adicionais).toEqual(["salada"]);
  });

  it("validade: só com os mínimos cumpridos", () => {
    expect(selectionValid([sabor, adicionais], {})).toBe(false);
    expect(groupMissing(sabor, {})).toBe(1);
    expect(selectionValid([sabor, adicionais], { sabor: ["cafe"] })).toBe(true);
    expect(selectionValid([adicionais], {})).toBe(true);
  });

  it("escolhas na ordem do catálogo, com preço e rótulo", () => {
    const options = selectedCartOptions([adicionais], { adicionais: ["salada", "ovo"] });
    expect(options).toEqual([ovo, salada]);
  });

  it("total, resumo e nome da linha", () => {
    expect(lineUnitPriceQ(2400, [ovo, salada])).toBe(3100);
    expect(lineUnitPriceQ(2400, [])).toBe(2400);
    expect(optionsSummary([ovo])).toBe("+ Ovo frito");
    const chocolate: POSCartItemOption = { group: "sabor", ref: "chocolate", group_label: "Sabor", name: "Chocolate", unit_price_q: 0 };
    expect(optionsSummary([chocolate, ovo])).toBe("Chocolate · + Ovo frito");
    expect(optionLineName("Croque Monsieur", [ovo])).toBe("Croque Monsieur (+ Ovo frito)");
    expect(optionLineName("Croque Monsieur", [])).toBe("Croque Monsieur");
    expect(optionPriceLabel(400)).toBe("+ R$ 4,00");
    expect(optionPriceLabel(0)).toBe("");
  });

  it("o que sobe é só {group, ref}", () => {
    expect(optionsIntent([ovo])).toEqual([{ group: "adicionais", ref: "ovo" }]);
  });

  it("o payload da venda leva options por item; sem escolha, não leva", () => {
    const payload = buildPosSaleIntent({
      tabRef: "", tabSessionKey: "", customerName: "", customerRef: "", customerPhone: "",
      customerTaxId: "", invoiceTaxId: "", customerEmail: "", customerMemoryAction: "",
      fulfillmentType: "pickup", deliveryAddress: "", deliveryAddressStructured: null as never,
      deliveryComplement: "", deliveryInstructions: "", deliveryDate: "", deliveryTimeSlot: "",
      deliveryFeeOverrideQ: null, orderNotes: "", paymentMethod: "cash", paymentCollection: "terminal",
      paymentTenders: [], tenderedQ: null, changeForQ: 0, receiptChannels: [], receiptEmail: "",
      saveReceiptContact: false, saveReceiptTaxId: false, saveReceiptTaxIdConfirmed: false,
      manualDiscount: null, managerApproval: null, clientRequestId: "pos:opcoes-1",
      items: [
        { line_id: "L-1", sku: "CQMO", name: "Croque Monsieur (+ Ovo frito)", price_q: 2800, qty: 1, notes: "", options: [ovo] },
        { line_id: "L-2", sku: "PAO", name: "Pão", price_q: 500, qty: 1, notes: "" },
      ],
    }) as { items: Array<Record<string, unknown>> };
    expect(payload.items[0]!.options).toEqual([{ group: "adicionais", ref: "ovo" }]);
    expect(payload.items[0]!.unit_price_q).toBe(2800);
    expect(payload.items[1]!).not.toHaveProperty("options");
  });

  it("a edição de encomenda reenvia as escolhas da linha", () => {
    const body = orderEditBody(
      {
        items: [{ line_id: "L1", sku: "CQMO", qty: 1, options: [{ group: "adicionais", ref: "ovo" }] }],
        fulfillment_type: "pickup",
      },
      {
        items: [], fulfillment_type: "pickup", delivery_address: "", delivery_address_structured: {},
        delivery_date: "", delivery_time_slot: "", order_notes: "", fiscal_tax_id: "",
      },
    );
    expect(body.items).toEqual([{ line_id: "L1", sku: "CQMO", qty: 1, options: [{ group: "adicionais", ref: "ovo" }] }]);
  });

  it("cartão de escolha mostra o rótulo do que se escolhe", () => {
    const base = { price_q: 1500, price_display: "R$ 15,00", collection_ref: "", collection_color: "", collection_icon: "", image_url: "" };
    const group = choiceGroup("Frappé", [
      { ...base, sku: "FR-CAFE", name: "Frappé café", choice_group: "Frappé", choice_group_label: "Sabor" },
      { ...base, sku: "FR-CHOC", name: "Frappé chocolate", choice_group: "Frappé", choice_group_label: "Sabor" },
    ]);
    expect(group.label).toBe("Sabor");
    expect(choiceGroup("Chás", [{ ...base, sku: "CHA", name: "Chá", choice_group: "Chás" }]).label).toBe("");
  });
});

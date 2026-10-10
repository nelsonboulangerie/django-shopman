// Cadastro sintético do Compras para a matriz visual e a prévia (padaria de exemplo).
// Nada aqui é dado real. Os nomes compridos são de propósito: a tela tem de quebrar o
// texto da casa, nunca cortar.

const SUPPLIERS = [
  ["MOINHO-PARANA", "Moinho Paraná Indústria de Alimentos Ltda.", "Moinho Paraná", 3, 97, "28 dias", "Cláudia Ramos"],
  ["LATICINIOS-SERRA", "Laticínios Serra Azul S.A.", "Serra Azul", 2, 92, "21 dias", "Marcos Lima"],
  ["GRANJA-BOA-VISTA", "Granja Boa Vista ME", "", 1, 99, "à vista", ""],
  ["DOCES-CENTRAL", "Central de Açúcares e Derivados Ltda.", "Central Açúcares", 4, 88, "30 dias", "Renata Souza"],
  ["EMBALA-SUL", "Embala Sul Comércio de Embalagens Ltda.", "Embala Sul", 5, 81, "30/60 dias", ""],
  ["HORTIFRUTI-VALE", "Hortifrúti do Vale Produtor Rural", "Hortifrúti do Vale", 1, 95, "à vista", "Seu Antônio"],
];

// sku, nome, unidade, categoria, estoque, consumo/dia, mínimo, declarado, receitas, fornecedor preferido
const MATERIALS = [
  ["FAR-T65", "Farinha de trigo tipo 65, moagem fina, saco de 25 kg", "kg", "Farinhas", 42, 18, 90, true, ["Baguete", "Pão de campanha", "Croissant"], "MOINHO-PARANA"],
  ["FAR-INTEGRAL", "Farinha de trigo integral orgânica", "kg", "Farinhas", 64, 4, 20, true, ["Pão integral"], "MOINHO-PARANA"],
  ["FAR-CENTEIO", "Farinha de centeio", "kg", "Farinhas", 9, 1.5, 6, false, ["Pão de centeio"], "MOINHO-PARANA"],
  ["MANTEIGA-82", "Manteiga sem sal extra, 82% de gordura, bloco de 5 kg para folhados", "kg", "Laticínios", 11, 6, 30, true, ["Croissant", "Pain au chocolat", "Brioche"], "LATICINIOS-SERRA"],
  ["LEITE-INTEGRAL", "Leite integral", "l", "Laticínios", 48, 12, 36, true, ["Brioche", "Pão de leite"], "LATICINIOS-SERRA"],
  ["CREME-35", "Creme de leite fresco 35%", "l", "Laticínios", 3, 2, 8, false, ["Éclair", "Quiche"], ""],
  ["OVO-GRANDE", "Ovos grandes, bandeja com 30", "un", "Ovos", 180, 90, 240, true, ["Brioche", "Éclair", "Quiche"], "GRANJA-BOA-VISTA"],
  ["ACUCAR-CRISTAL", "Açúcar cristal", "kg", "Açúcares", 35, 3, 15, true, ["Brioche", "Croissant"], "DOCES-CENTRAL"],
  ["ACUCAR-CONFEITEIRO", "Açúcar de confeiteiro impalpável", "kg", "Açúcares", 6, 0.8, 4, false, ["Éclair"], "DOCES-CENTRAL"],
  ["CHOC-70", "Chocolate amargo 70% em gotas para forno", "kg", "Açúcares", 2.5, 1.2, 6, true, ["Pain au chocolat"], ""],
  ["FERMENTO-SECO", "Fermento biológico seco instantâneo", "kg", "Fermentos", 1.8, 0.3, 1, true, ["Baguete", "Brioche"], "DOCES-CENTRAL"],
  ["SAL-REFINADO", "Sal refinado", "kg", "Temperos", 22, 1, 5, true, ["Baguete", "Pão de campanha"], "DOCES-CENTRAL"],
  ["SACO-KRAFT-M", "Saco kraft médio com visor, pacote com 500", "un", "Embalagens", 900, 140, 600, true, [], "EMBALA-SUL"],
  ["CAIXA-BOLO-20", "Caixa para bolo 20 cm", "un", "Embalagens", 40, 12, 60, false, [], "EMBALA-SUL"],
  ["MORANGO", "Morango fresco, bandeja de 250 g", "kg", "Frutas", 1, 1.5, 3, false, ["Tarte aux fraises"], "HORTIFRUTI-VALE"],
  ["LIMAO-SICILIANO", "Limão-siciliano", "kg", "Frutas", 4, 0.5, 2, true, ["Tarte au citron"], "HORTIFRUTI-VALE"],
  ["GELEIA-DAMASCO", "Geleia de damasco para brilho", "kg", "Açúcares", 3, 0.2, 1, true, ["Croissant"], ""],
  ["AMENDOA-LAMINADA", "Amêndoa laminada", "kg", "Oleaginosas", 0.4, 0.3, 2, true, ["Croissant de amêndoas"], ""],
];

const FACTORS = {
  "FAR-T65": [["Saco 25 kg", 25, "conventional"]],
  "FAR-INTEGRAL": [["Saco 5 kg", 5, "conventional"]],
  "MANTEIGA-82": [["Bloco 5 kg", 5, "conventional"]],
  "LEITE-INTEGRAL": [["Caixa 12 l", 12, "conventional"]],
  "OVO-GRANDE": [["Bandeja 30", 30, "conventional"]],
  "ACUCAR-CRISTAL": [["Fardo 30 kg", 30, "conventional"]],
  "SACO-KRAFT-M": [["Pacote 500", 500, "conventional"]],
  "MORANGO": [["Bandeja (≈ 250 g)", 0.25, "approximate"]],
};

// custo em centavos por unidade de compra (a conversão, se houver) ou por unidade-base
const COSTS = [
  ["FAR-T65", "MOINHO-PARANA", 11800, true],
  ["FAR-INTEGRAL", "MOINHO-PARANA", 4250, true],
  ["FAR-CENTEIO", "MOINHO-PARANA", 1190, true],
  ["MANTEIGA-82", "LATICINIOS-SERRA", 27900, true],
  ["LEITE-INTEGRAL", "LATICINIOS-SERRA", 6480, true],
  ["OVO-GRANDE", "GRANJA-BOA-VISTA", 2490, true],
  ["ACUCAR-CRISTAL", "DOCES-CENTRAL", 13500, true],
  ["ACUCAR-CONFEITEIRO", "DOCES-CENTRAL", 980, true],
  ["FERMENTO-SECO", "DOCES-CENTRAL", 6200, true],
  ["SAL-REFINADO", "DOCES-CENTRAL", 290, true],
  ["SACO-KRAFT-M", "EMBALA-SUL", 18900, true],
  ["CAIXA-BOLO-20", "EMBALA-SUL", 310, true],
  ["MORANGO", "HORTIFRUTI-VALE", 890, true],
  ["LIMAO-SICILIANO", "HORTIFRUTI-VALE", 1490, true],
  ["MANTEIGA-82", "DOCES-CENTRAL", 29500, false],
];

function suppliers() {
  return SUPPLIERS.map(([ref, name, tradeName, lead, reliability, term, contact], index) => ({
    ref,
    name,
    tradeName,
    displayName: tradeName || name,
    document: `12.345.${String(670 + index).padStart(3, "0")}/0001-${String(10 + index)}`,
    contact: index === 2 ? "" : "(43) 3333-0000",
    contacts: contact
      ? [{
          id: `${ref}-1`,
          name: contact,
          role: "sales",
          roleLabel: "Comercial",
          email: `${contact.split(" ")[0].toLowerCase()}@exemplo.com.br`,
          phone: "(43) 99999-0000",
          isPrimary: true,
          isActive: true,
          notes: "",
        }]
      : [],
    orderContactName: contact,
    leadTimeDays: lead,
    reliabilityPercent: reliability,
    isActive: index !== 4,
    lastDeliveryAt: "2026-10-06",
    paymentTerm: term,
  }));
}

function conversions() {
  return Object.entries(FACTORS).flatMap(([sku, list]) =>
    list.map(([label, factor, kind], index) => ({
      id: `${sku}-c${index + 1}`,
      materialSku: sku,
      supplierRef: null,
      label,
      toBaseFactor: factor,
      kind,
      isActive: true,
    })),
  );
}

function costs() {
  return COSTS.map(([sku, supplierRef, costQ, isPreferred], index) => ({
    id: `cost-${index + 1}`,
    materialSku: sku,
    supplierRef,
    conversionId: FACTORS[sku] ? `${sku}-c1` : null,
    costQ,
    isPreferred,
    updatedAt: "2026-10-01",
  }));
}

function materials() {
  return MATERIALS.map(([sku, name, unit, category, stock, dailyUse, minStock, declared, recipes]) => {
    const coverage = dailyUse ? stock / dailyUse : 99;
    const suggestedQty = coverage < 4 ? Math.max(Math.ceil(dailyUse * 7 - stock), 1) : 0;
    return {
      sku,
      name,
      unit,
      shelfLifeDays: category === "Frutas" ? 4 : category === "Laticínios" ? 20 : null,
      isActive: true,
      category,
      stockOnHand: stock,
      dailyUse,
      minStock,
      minStockDeclared: declared,
      recipes,
      leadTimeDays: 2,
      replenishAtDays: 4,
      suggestedQty,
      roles: {
        purchasable: true,
        sellable: sku === "GELEIA-DAMASCO",
        produced: false,
        usedInRecipe: recipes.length > 0,
      },
      salePriceQ: sku === "GELEIA-DAMASCO" ? 3900 : null,
      saleSuggestion: null,
      opensInto: null,
      netContentKg: "",
      lastDeliveryExpiry: "",
      eans: [],
    };
  });
}

function history() {
  return [
    { sourceRef: "41261012345670000112550010000128841000041700", mode: "invoice", supplierRef: "MOINHO-PARANA", supplierName: "Moinho Paraná", lines: 3, totalCostQ: 241680, operator: "Compras", receivedAtDisplay: "09/10 08:12", receivedAtTime: "08:12", receivedToday: true },
    { sourceRef: "manual-2026-10-09-1", mode: "manual", supplierRef: "HORTIFRUTI-VALE", supplierName: "Hortifrúti do Vale", lines: 2, totalCostQ: 8340, operator: "Compras", receivedAtDisplay: "09/10 07:40", receivedAtTime: "07:40", receivedToday: true },
    { sourceRef: "41261012345671000112550010000127991000039900", mode: "invoice", supplierRef: "LATICINIOS-SERRA", supplierName: "Serra Azul", lines: 4, totalCostQ: 182300, operator: "Compras", receivedAtDisplay: "08/10 15:03", receivedAtTime: "15:03", receivedToday: false },
  ];
}

const BLANK_RECEIPT = { mode: "invoice", supplierRef: "", invoiceInput: "", note: "", lines: [], invoiceVolumes: 0, volumesCounted: null };

export function purchaseFixture() {
  return {
    materials: materials(),
    suppliers: suppliers(),
    conversions: conversions(),
    costs: costs(),
    purchaseRequestStatuses: { "MANTEIGA-82": "approved" },
    activeReceipt: { ...BLANK_RECEIPT },
    receiptHistory: history(),
  };
}

function line(id, sku, description, qty, unit, total, extra = {}) {
  return {
    id,
    materialSku: sku,
    suggestedMaterialSku: sku,
    suggestionScore: 1,
    suggestionSource: "gtin",
    conversionId: FACTORS[sku] ? `${sku}-c1` : null,
    requiresConversion: false,
    conversionSuggestion: null,
    purchaseQty: qty,
    invoicePurchaseQty: qty,
    costInput: (total / qty / 100).toFixed(2).replace(".", ","),
    expiryDate: "",
    expiryFromInvoice: false,
    invoiceLot: "",
    lineNote: "",
    invoiceDescription: description,
    invoiceQty: qty,
    invoiceUnit: unit,
    invoiceTotal: (total / 100).toFixed(2),
    invoiceProductCode: id.toUpperCase(),
    invoiceEan: "",
    checked: false,
    ...extra,
  };
}

/** A base cheia e uma NF do Serra Azul lida, em conferência. */
export function receivingFixture() {
  const base = purchaseFixture();
  base.activeReceipt = {
    mode: "invoice",
    supplierRef: "LATICINIOS-SERRA",
    invoiceInput: "41261012345671000112550010000129121000041705",
    note: "",
    invoiceVolumes: 6,
    volumesCounted: null,
    lines: [
      line("l1", "MANTEIGA-82", "MANTEIGA S/SAL EXTRA 82% BLOCO 5KG", 4, "CX", 111600),
      line("l2", "LEITE-INTEGRAL", "LEITE INTEGRAL UHT CX 12X1L", 1, "CX", 6480),
      line("l3", "CREME-35", "CREME DE LEITE FRESCO 35% 1L", 6, "UN", 16200, { materialSku: "", suggestedMaterialSku: "CREME-35", suggestionSource: "name", suggestionScore: 0.82 }),
    ],
  };
  return base;
}

export function countFixture() {
  return {
    items: MATERIALS.slice(0, 12).map(([sku, name, unit, category, stock]) => ({
      sku,
      name,
      unit,
      category,
      isActive: true,
      systemQty: stock,
    })),
  };
}

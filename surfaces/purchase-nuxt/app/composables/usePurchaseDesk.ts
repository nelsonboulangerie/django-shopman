import type {
  PurchaseView,
  PurchaseBaseView,
  PurchaseRequestStatus,
  PurchaseActionResponse,
  PurchaseProjection,
  PurchaseResponse,
  ConversionKind,
  CountItem,
  Material,
  MaterialConversion,
  ReceiptLine,
  ReceiptLinePreview,
  ReceiptMode,
  Supplier,
  SupplierMaterialCost,
} from "~/types/purchase";
import { PURCHASE_API_ENDPOINTS, usePurchaseApi } from "~/composables/usePurchaseApi";
import {
  costPerBaseUnitQ,
  countConfirmPayload,
  countRows,
  countSummary,
  enrichMaterial,
  invoiceProbe,
  isApproximateCost,
  parseMoneyInput,
  quotePreview as buildQuotePreview,
  receiptLinePreview,
  supplierCostRows,
} from "~/presentation/purchase";

const MATERIALS: Material[] = [
  {
    sku: "FARINHA-T65",
    name: "Farinha T65",
    unit: "kg",
    shelfLifeDays: 180,
    isActive: true,
    category: "Farinhas",
    stockOnHand: 78,
    dailyUse: 18,
    minStock: 60,
    recipes: ["Baguete", "Croissant", "Pain de campagne"],
  },
  {
    sku: "MANTEIGA-TOURAGE",
    name: "Manteiga de tourage",
    unit: "kg",
    shelfLifeDays: 45,
    isActive: true,
    category: "Laticínios",
    stockOnHand: 22,
    dailyUse: 9,
    minStock: 30,
    recipes: ["Croissant", "Pain au chocolat"],
  },
  {
    // Comprado por cartela e contado em kg: a ponte e aproximada, e o saldo
    // carrega o "≈" por causa disso (ADR-024, R3).
    stockIsApproximate: true,
    sku: "OVOS",
    name: "Ovos",
    unit: "kg",
    shelfLifeDays: 21,
    isActive: true,
    category: "Frescos",
    stockOnHand: 16,
    dailyUse: 4,
    minStock: 12,
    recipes: ["Quiche", "Brioche", "Creme confeiteiro"],
  },
  {
    sku: "FERMENTO-NAT",
    name: "Fermento natural",
    unit: "kg",
    shelfLifeDays: 14,
    isActive: true,
    category: "Fermentação",
    stockOnHand: 7,
    dailyUse: 2.4,
    minStock: 8,
    recipes: ["Levain", "Pain de campagne"],
  },
  {
    // Pesado em kg e comprado em pacote, e sem conversao cadastrada: e o estado
    // que a linha do recebimento precisa saber mostrar, e o que o QA de 27/08
    // encontrou quebrado (10 unidades lidas como 10 kg).
    sku: "FERMENTO-BIO",
    name: "Fermento biológico",
    unit: "kg",
    shelfLifeDays: 45,
    isActive: true,
    category: "Fermentação",
    stockOnHand: 2.5,
    dailyUse: 0.6,
    minStock: 2,
    recipes: ["Brioche", "Croissant"],
  },
  {
    sku: "SAL",
    name: "Sal",
    unit: "kg",
    shelfLifeDays: null,
    isActive: true,
    category: "Secos",
    stockOnHand: 55,
    dailyUse: 1.1,
    minStock: 20,
    recipes: ["Todas as massas"],
  },
  {
    sku: "CANELA",
    name: "Canela",
    unit: "g",
    shelfLifeDays: 180,
    isActive: true,
    category: "Especiarias",
    stockOnHand: 750,
    dailyUse: 90,
    minStock: 600,
    recipes: ["Pain perdu", "Rabanada"],
  },
  {
    sku: "ALECRIM",
    name: "Alecrim fresco",
    unit: "g",
    shelfLifeDays: 14,
    isActive: true,
    category: "Frescos",
    stockOnHand: 260,
    dailyUse: 120,
    minStock: 400,
    recipes: ["Focaccia", "Pão de alecrim"],
  },
  {
    sku: "LEITE-INTEGRAL",
    name: "Leite integral",
    unit: "l",
    shelfLifeDays: 7,
    isActive: true,
    category: "Laticínios",
    stockOnHand: 14,
    dailyUse: 8,
    minStock: 30,
    recipes: ["Creme confeiteiro", "Chocolate quente"],
  },
  {
    sku: "QUEIJO-ARTESANAL",
    name: "Queijo artesanal",
    unit: "kg",
    shelfLifeDays: 18,
    isActive: true,
    category: "Frescos",
    stockOnHand: 5.5,
    dailyUse: 1.3,
    minStock: 8,
    recipes: ["Quiche", "Tartine", "Sanduíche de queijo"],
  },
];

const SUPPLIERS: Supplier[] = [
  {
    ref: "SUP-MOINHO-SP",
    name: "Moinho São Paulo",
    document: "12.345.678/0001-90",
    contact: "compras@moinhosp.example",
    leadTimeDays: 2,
    reliabilityPercent: 96,
    isActive: true,
    lastDeliveryAt: "2026-08-22",
    paymentTerm: "14 dias",
  },
  {
    ref: "SUP-COOP-NORTE",
    name: "Cooperativa Norte",
    document: "43.210.987/0001-12",
    contact: "pedidos@coopnorte.example",
    leadTimeDays: 3,
    reliabilityPercent: 91,
    isActive: true,
    lastDeliveryAt: "2026-08-20",
    paymentTerm: "7 dias",
  },
  {
    ref: "SUP-LATICINIOS",
    name: "Laticínios Aurora",
    document: "18.190.200/0001-05",
    contact: "aurora@laticinios.example",
    leadTimeDays: 1,
    reliabilityPercent: 98,
    isActive: true,
    lastDeliveryAt: "2026-08-24",
    paymentTerm: "à vista",
  },
  {
    ref: "SUP-CEASA-LONDRINA",
    name: "Ceasa Londrina",
    document: "09.001.002/0001-33",
    contact: "banca27@ceasa.example",
    leadTimeDays: 1,
    reliabilityPercent: 86,
    isActive: true,
    lastDeliveryAt: "2026-08-24",
    paymentTerm: "7 dias",
  },
  {
    ref: "SUP-DISTRIBUIDORA",
    name: "Distribuidora Paraná",
    document: "33.444.555/0001-44",
    contact: "industrial@parana.example",
    leadTimeDays: 4,
    reliabilityPercent: 89,
    isActive: true,
    lastDeliveryAt: "2026-08-18",
    paymentTerm: "21 dias",
  },
  {
    ref: "SUP-FAZENDA-BOA-VISTA",
    name: "Fazenda Boa Vista",
    document: "entrega informal",
    contact: "WhatsApp do produtor",
    leadTimeDays: 1,
    reliabilityPercent: 88,
    isActive: true,
    lastDeliveryAt: "2026-08-25",
    paymentTerm: "à vista",
  },
];

const CONVERSIONS: MaterialConversion[] = [
  { id: "conv-farinha-moinho-25", materialSku: "FARINHA-T65", supplierRef: "SUP-MOINHO-SP", label: "saco 25 kg", toBaseFactor: 25, kind: "conventional", isActive: true },
  { id: "conv-farinha-coop-20", materialSku: "FARINHA-T65", supplierRef: "SUP-COOP-NORTE", label: "saco 20 kg", toBaseFactor: 20, kind: "conventional", isActive: true },
  { id: "conv-manteiga-caixa-10", materialSku: "MANTEIGA-TOURAGE", supplierRef: "SUP-LATICINIOS", label: "caixa 10 kg", toBaseFactor: 10, kind: "conventional", isActive: true },
  { id: "conv-manteiga-pacote-5", materialSku: "MANTEIGA-TOURAGE", supplierRef: "SUP-DISTRIBUIDORA", label: "pacote 5 kg", toBaseFactor: 5, kind: "conventional", isActive: true },
  { id: "conv-ovos-cartela", materialSku: "OVOS", supplierRef: null, label: "cartela", toBaseFactor: 1.5, kind: "approximate", isActive: true },
  { id: "conv-ovos-caixa", materialSku: "OVOS", supplierRef: "SUP-DISTRIBUIDORA", label: "caixa 12 cartelas", toBaseFactor: 18, kind: "approximate", isActive: true },
  { id: "conv-canela-pacote", materialSku: "CANELA", supplierRef: "SUP-DISTRIBUIDORA", label: "pacote 500 g", toBaseFactor: 500, kind: "conventional", isActive: true },
  { id: "conv-leite-caixa", materialSku: "LEITE-INTEGRAL", supplierRef: "SUP-LATICINIOS", label: "caixa 12 l", toBaseFactor: 12, kind: "conventional", isActive: true },
  { id: "conv-alecrim-maco", materialSku: "ALECRIM", supplierRef: "SUP-CEASA-LONDRINA", label: "maço", toBaseFactor: 80, kind: "approximate", isActive: true },
  { id: "conv-queijo-peca", materialSku: "QUEIJO-ARTESANAL", supplierRef: "SUP-FAZENDA-BOA-VISTA", label: "peça", toBaseFactor: 0.9, kind: "approximate", isActive: true },
];

const COSTS: SupplierMaterialCost[] = [
  { id: "cost-farinha-moinho", materialSku: "FARINHA-T65", supplierRef: "SUP-MOINHO-SP", conversionId: "conv-farinha-moinho-25", costQ: 18000, isPreferred: true, updatedAt: "2026-08-22" },
  { id: "cost-farinha-coop", materialSku: "FARINHA-T65", supplierRef: "SUP-COOP-NORTE", conversionId: "conv-farinha-coop-20", costQ: 15200, isPreferred: false, updatedAt: "2026-08-20" },
  { id: "cost-manteiga-laticinios", materialSku: "MANTEIGA-TOURAGE", supplierRef: "SUP-LATICINIOS", conversionId: "conv-manteiga-caixa-10", costQ: 69000, isPreferred: true, updatedAt: "2026-08-24" },
  { id: "cost-manteiga-distribuidora", materialSku: "MANTEIGA-TOURAGE", supplierRef: "SUP-DISTRIBUIDORA", conversionId: "conv-manteiga-pacote-5", costQ: 36500, isPreferred: false, updatedAt: "2026-08-16" },
  { id: "cost-ovos-ceasa", materialSku: "OVOS", supplierRef: "SUP-CEASA-LONDRINA", conversionId: "conv-ovos-cartela", costQ: 2400, isPreferred: true, updatedAt: "2026-08-24" },
  { id: "cost-ovos-distribuidora", materialSku: "OVOS", supplierRef: "SUP-DISTRIBUIDORA", conversionId: "conv-ovos-caixa", costQ: 25200, isPreferred: false, updatedAt: "2026-08-18" },
  { id: "cost-sal-distribuidora", materialSku: "SAL", supplierRef: "SUP-DISTRIBUIDORA", conversionId: null, costQ: 290, isPreferred: true, updatedAt: "2026-08-12" },
  { id: "cost-canela-distribuidora", materialSku: "CANELA", supplierRef: "SUP-DISTRIBUIDORA", conversionId: "conv-canela-pacote", costQ: 2250, isPreferred: true, updatedAt: "2026-08-12" },
  { id: "cost-leite-laticinios", materialSku: "LEITE-INTEGRAL", supplierRef: "SUP-LATICINIOS", conversionId: "conv-leite-caixa", costQ: 10800, isPreferred: true, updatedAt: "2026-08-24" },
  { id: "cost-alecrim-ceasa", materialSku: "ALECRIM", supplierRef: "SUP-CEASA-LONDRINA", conversionId: "conv-alecrim-maco", costQ: 650, isPreferred: false, updatedAt: "2026-08-24" },
  { id: "cost-queijo-fazenda", materialSku: "QUEIJO-ARTESANAL", supplierRef: "SUP-FAZENDA-BOA-VISTA", conversionId: "conv-queijo-peca", costQ: 4200, isPreferred: true, updatedAt: "2026-08-25" },
];

const INVOICE_ACCESS_KEY = "41260812345678000190550010000012341000123459";

const INVOICE_RECEIPT_LINES: ReceiptLine[] = [
  {
    id: "receipt-farinha",
    materialSku: "FARINHA-T65",
    conversionId: "conv-farinha-moinho-25",
    purchaseQty: 2,
    costInput: "360,00",
    expiryDate: "2027-02-25",
    lineNote: "",
    checked: true,
  },
  {
    id: "receipt-ovos",
    materialSku: "OVOS",
    conversionId: "conv-ovos-cartela",
    purchaseQty: 4,
    costInput: "96,00",
    expiryDate: "2026-09-10",
    lineNote: "",
    checked: false,
  },
  {
    id: "receipt-fermento",
    materialSku: "FERMENTO-BIO",
    conversionId: null,
    requiresConversion: true,
    conversionSuggestion: {
      label: "un 500 g",
      factor: "0.5",
      kind: "conventional",
      source: "invoice-tax-pair",
      note: "A NF diz 10 UN = 5 KG (12,00 por KG), então 1 UN = 0,5 kg.",
    },
    purchaseQty: 10,
    costInput: "60,00",
    expiryDate: "2026-10-05",
    lineNote: "Confirmar a conversao sugerida (un 500 g). NF: FERM BIOL FRESCO MAURI 500G; unidade UN; tributavel 5 KG.",
    invoiceUnit: "UN",
    invoiceProductCode: "FERM-500",
    checked: false,
  },
];

const MANUAL_RECEIPT_LINES: ReceiptLine[] = [
  {
    id: "receipt-manual-ovos",
    materialSku: "OVOS",
    conversionId: "conv-ovos-cartela",
    purchaseQty: 2,
    costInput: "48,00",
    expiryDate: "2026-09-08",
    lineNote: "Produtor entregou romaneio em papel.",
    checked: false,
  },
  {
    id: "receipt-manual-queijo",
    materialSku: "QUEIJO-ARTESANAL",
    conversionId: "conv-queijo-peca",
    purchaseQty: 3,
    costInput: "126,00",
    expiryDate: "2026-09-06",
    lineNote: "",
    checked: false,
  },
];

function copy<T>(items: T[]): T[] {
  return items.map((item) => ({ ...item }));
}

function receiptLineCopy(lines: ReceiptLine[]): ReceiptLine[] {
  return lines.map((line) => ({
    ...line,
    conversionId: line.conversionId ?? null,
    suggestedMaterialSku: line.suggestedMaterialSku ?? "",
    suggestionScore: Number(line.suggestionScore) || 0,
    costInput: line.costInput ?? "",
    expiryDate: line.expiryDate ?? "",
    lineNote: line.lineNote ?? "",
    invoiceProductCode: line.invoiceProductCode ?? "",
    invoiceEan: line.invoiceEan ?? "",
    checked: Boolean(line.checked),
    purchaseQty: Number(line.purchaseQty) || 0,
  }));
}

function todayStamp(): string {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());
}

function centsInput(cents: number): string {
  return (cents / 100).toFixed(2).replace(".", ",");
}

export function usePurchaseDesk() {
  const view = useState<PurchaseView>("purchase-view", () => "panel");
  const baseView = useState<PurchaseBaseView>("purchase-base-view", () => "materials");
  const query = useState("purchase-query", () => "");
  const onlyAlerts = useState("purchase-only-alerts", () => false);
  const selectedMaterialSku = useState("purchase-selected-material", () => "FARINHA-T65");
  const selectedSupplierRef = useState("purchase-selected-supplier", () => "SUP-MOINHO-SP");
  const noteMaterialSku = useState("purchase-note-material", () => "FARINHA-T65");
  const noteSupplierRef = useState("purchase-note-supplier", () => "SUP-MOINHO-SP");
  const noteConversionId = useState("purchase-note-conversion", () => "conv-farinha-moinho-25");
  const noteCostInput = useState("purchase-note-cost", () => "180,00");
  const receiptMode = useState<ReceiptMode>("purchase-receipt-mode", () => "invoice");
  const invoiceInput = useState(
    "purchase-invoice-input",
    () => `https://www.fazenda.pr.gov.br/nfce/qrcode?p=${INVOICE_ACCESS_KEY}|2|1|1|A1B2C3D4E5`,
  );
  const receiptSupplierRef = useState("purchase-receipt-supplier", () => "SUP-MOINHO-SP");
  const receiptNote = useState("purchase-receipt-note", () => "");
  const receiptLines = useState<ReceiptLine[]>("purchase-receipt-lines", () => copy(INVOICE_RECEIPT_LINES));
  const receiptConfirmedAt = useState<string | null>("purchase-receipt-confirmed-at", () => null);
  const receiptRejectedAt = useState<string | null>("purchase-receipt-rejected-at", () => null);
  const receiptHydrated = useState("purchase-receipt-hydrated", () => false);
  const purchaseRequestStatuses = useState<Record<string, PurchaseRequestStatus>>(
    "purchase-request-statuses",
    () => ({}),
  );

  const materials = useState<Material[]>("purchase-materials", () => copy(MATERIALS));
  const suppliers = useState<Supplier[]>("purchase-suppliers", () => copy(SUPPLIERS));
  const conversions = useState<MaterialConversion[]>("purchase-conversions", () => copy(CONVERSIONS));
  const costs = useState<SupplierMaterialCost[]>("purchase-costs", () => copy(COSTS));
  // Contagem: a posição vem CRUA do ledger (endpoint próprio, restrito ao
  // gestor/dono) — o stockOnHand do board desconta hold e lote vencido e não
  // bateria com o ajuste lançado.
  const countItems = useState<CountItem[]>("purchase-count-items", () => []);
  const countInputs = useState<Record<string, string>>("purchase-count-inputs", () => ({}));
  const countReasons = useState<Record<string, string>>("purchase-count-reasons", () => ({}));
  const countLoaded = useState("purchase-count-loaded", () => false);
  const countForbidden = useState("purchase-count-forbidden", () => false);
  const countConfirmedAt = useState<string | null>("purchase-count-confirmed-at", () => null);
  const countPending = ref(false);
  const api = usePurchaseApi();
  const actionPending = ref(false);
  const actionError = ref("");
  const { flagIfStationLocked } = useStationLock();
  const { data, pending, error, refresh } = useFetch<PurchaseResponse>(PURCHASE_API_ENDPOINTS.projection, {
    key: "purchase-projection",
    server: false,
    onResponseError: operatorSessionOnError,
  });
  const backendReady = computed(() => Boolean(data.value?.purchase));
  const backendErrorStatus = computed(() => (error.value ? httpError(error.value).status : 0));
  const readonlyFallback = computed(() => !backendReady.value && !pending.value);
  const backendBlockTitle = computed(() => {
    if (backendErrorStatus.value === 403) return "Operador sem acesso a Compras";
    if (backendErrorStatus.value === 401) return "Sessão expirada";
    return "Compras sem conexão operacional";
  });
  const backendBlockMessage = computed(() => {
    if (backendErrorStatus.value === 403) {
      return "Entre com um operador habilitado para compras e recebimento, ou destrave a estação com PIN/crachá de gestor.";
    }
    if (backendErrorStatus.value === 401) {
      return "Entre novamente para carregar dados reais e registrar ações.";
    }
    return "A tela está em consulta com dados de exemplo. Ações como receber, enviar pedidos e definir custos ficam bloqueadas até reconectar ao Django.";
  });

  const enrichedMaterials = computed(() =>
    materials.value
      .map((material) => enrichMaterial(material, costs.value, conversions.value))
      .sort((a, b) => {
        const toneOrder = { urgent: 0, watch: 1, ok: 2 };
        return toneOrder[a.tone] - toneOrder[b.tone] || a.sku.localeCompare(b.sku);
      }),
  );

  const filteredMaterials = computed(() => {
    const term = query.value.trim().toLowerCase();
    return enrichedMaterials.value.filter((material) => {
      const matches =
        !term ||
        material.sku.toLowerCase().includes(term) ||
        material.name.toLowerCase().includes(term) ||
        material.category.toLowerCase().includes(term);
      const alertMatch = !onlyAlerts.value || material.tone !== "ok";
      return matches && alertMatch;
    });
  });

  const selectedMaterial = computed(() =>
    enrichedMaterials.value.find((material) => material.sku === selectedMaterialSku.value) ??
    enrichedMaterials.value[0] ??
    null,
  );

  const selectedSupplier = computed(() =>
    suppliers.value.find((supplier) => supplier.ref === selectedSupplierRef.value) ?? suppliers.value[0] ?? null,
  );

  const selectedCostRows = computed(() =>
    selectedMaterial.value ?
      supplierCostRows(selectedMaterial.value, costs.value, suppliers.value, conversions.value)
    : [],
  );

  const noteMaterial = computed(() => materials.value.find((material) => material.sku === noteMaterialSku.value));
  const noteSupplier = computed(() => suppliers.value.find((supplier) => supplier.ref === noteSupplierRef.value));
  const availableNoteConversions = computed(() =>
    conversions.value.filter(
      (conversion) =>
        conversion.isActive &&
        conversion.materialSku === noteMaterialSku.value &&
        (!conversion.supplierRef || conversion.supplierRef === noteSupplierRef.value),
    ),
  );
  const selectedNoteConversion = computed(
    () => availableNoteConversions.value.find((conversion) => conversion.id === noteConversionId.value) ?? null,
  );
  const notePreview = computed(() =>
    buildQuotePreview(noteCostInput.value, noteMaterial.value, selectedNoteConversion.value),
  );

  const receiptSupplier = computed(() =>
    suppliers.value.find((supplier) => supplier.ref === receiptSupplierRef.value) ?? null,
  );
  const invoiceStatus = computed(() => invoiceProbe(invoiceInput.value));
  const receiptLinePreviews = computed(() =>
    receiptLines.value
      .map((line) => receiptLinePreview(line, receiptMode.value, materials.value, conversions.value))
      .filter((preview): preview is ReceiptLinePreview => Boolean(preview)),
  );
  const receiptLineWarnings = computed(() => receiptLinePreviews.value.flatMap((preview) => preview.warnings));
  const receiptBlockers = computed(() => receiptLineWarnings.value.filter((warning) => warning.tone === "block"));
  const receiptWatchWarnings = computed(() => receiptLineWarnings.value.filter((warning) => warning.tone === "watch"));
  // O painel listava as pendências ACHATADAS — dez pílulas "Definir insumo"
  // iguais, sem dizer de qual item, e a lista ficava inútil justamente quando
  // era mais necessária (nota grande). Uma linha por item, com nome e gesto.
  const receiptPendingLines = computed(() =>
    receiptLinePreviews.value
      .filter((preview) => preview.nextStep)
      .map((preview) => ({
        id: preview.line.id,
        label: preview.line.invoiceDescription || preview.material.name || "Item sem descrição",
        step: preview.nextStep,
      })),
  );
  const receiptDocumentBlockers = computed(() =>
    receiptMode.value === "invoice" && !invoiceStatus.value.valid ? ["Ler QR, código de barras ou chave da NF"] : [],
  );
  const receiptSupplierBlockers = computed(() => (receiptSupplierRef.value ? [] : ["Definir fornecedor"]));
  const receiptCheckedCount = computed(() => receiptLinePreviews.value.filter((preview) => preview.line.checked).length);
  const receiptTotalCostQ = computed(() =>
    receiptLinePreviews.value.reduce((total, preview) => total + preview.totalCostQ, 0),
  );
  const receiptHasRejectionReason = computed(
    () => Boolean(receiptNote.value.trim()) || receiptLines.value.some((line) => Boolean(line.lineNote.trim())),
  );
  const receiptReady = computed(
    () =>
      receiptLinePreviews.value.length > 0 &&
      receiptDocumentBlockers.value.length === 0 &&
      receiptSupplierBlockers.value.length === 0 &&
      receiptBlockers.value.length === 0 &&
      receiptCheckedCount.value === receiptLinePreviews.value.length,
  );

  watch([noteMaterialSku, noteSupplierRef], () => {
    const first = availableNoteConversions.value[0];
    noteConversionId.value = first?.id ?? "";
  });

  const metrics = computed(() => {
    const missingPreferred = enrichedMaterials.value.filter((material) => !material.preferredCost).length;
    const urgentMaterials = enrichedMaterials.value.filter((material) => material.tone === "urgent").length;
    const approximatePreferred = enrichedMaterials.value.filter(
      (material) => material.preferredCost && isApproximateCost(material.preferredCost, conversions.value),
    ).length;
    const activeSuppliers = suppliers.value.filter((supplier) => supplier.isActive).length;
    return {
      activeMaterials: enrichedMaterials.value.filter((material) => material.isActive).length,
      urgentMaterials,
      missingPreferred,
      approximatePreferred,
      activeSuppliers,
    };
  });

  const integrityQueue = computed(() =>
    enrichedMaterials.value
      .flatMap((material) =>
        material.issues.map((issue) => ({
          material,
          issue,
        })),
      )
      .sort((a, b) => {
        const toneOrder = { urgent: 0, watch: 1, ok: 2 };
        return toneOrder[a.issue.tone] - toneOrder[b.issue.tone] || a.material.sku.localeCompare(b.material.sku);
      }),
  );

  const reorderRows = computed(() =>
    enrichedMaterials.value
      .filter((material) => material.stockOnHand < material.minStock || material.coverageDays <= 5)
      .map((material) => {
        const preferred = material.preferredCost;
        const supplier = preferred ? suppliers.value.find((item) => item.ref === preferred.supplierRef) : null;
        const target = Math.max(material.minStock * 2, material.dailyUse * 7);
        const suggestedQty = Math.max(0, Math.ceil(target - material.stockOnHand));
        const estimatedCostQ =
          preferred && material.preferredBaseCostQ ? Math.round(material.preferredBaseCostQ * suggestedQty) : null;
        return { material, supplier, suggestedQty, estimatedCostQ };
      })
      .sort((a, b) => a.material.coverageDays - b.material.coverageDays),
  );

  const supplierSummaries = computed(() =>
    suppliers.value.map((supplier) => {
      const supplierCosts = costs.value.filter((cost) => cost.supplierRef === supplier.ref);
      const preferredCount = supplierCosts.filter((cost) => cost.isPreferred).length;
      const materialsCovered = new Set(supplierCosts.map((cost) => cost.materialSku)).size;
      return {
        supplier,
        materialsCovered,
        preferredCount,
        approximateCount: supplierCosts.filter((cost) => isApproximateCost(cost, conversions.value)).length,
      };
    }),
  );

  const projection = computed<PurchaseProjection>(() => ({
    materials: materials.value,
    suppliers: suppliers.value,
    conversions: conversions.value,
    costs: costs.value,
    purchaseRequestStatuses: purchaseRequestStatuses.value,
    activeReceipt: {
      mode: receiptMode.value,
      supplierRef: receiptSupplierRef.value,
      invoiceInput: invoiceInput.value,
      note: receiptNote.value,
      lines: receiptLines.value,
    },
  }));

  function normalizeSelections() {
    const firstMaterialSku = materials.value[0]?.sku ?? "";
    const firstSupplierRef = suppliers.value[0]?.ref ?? "";
    if (!materials.value.some((material) => material.sku === selectedMaterialSku.value)) {
      selectedMaterialSku.value = firstMaterialSku;
    }
    if (!materials.value.some((material) => material.sku === noteMaterialSku.value)) {
      noteMaterialSku.value = firstMaterialSku;
    }
    if (!suppliers.value.some((supplier) => supplier.ref === selectedSupplierRef.value)) {
      selectedSupplierRef.value = firstSupplierRef;
    }
    if (!suppliers.value.some((supplier) => supplier.ref === noteSupplierRef.value)) {
      noteSupplierRef.value = firstSupplierRef;
    }
    if (receiptSupplierRef.value && !suppliers.value.some((supplier) => supplier.ref === receiptSupplierRef.value)) {
      receiptSupplierRef.value = firstSupplierRef;
    }
    if (
      noteConversionId.value &&
      !conversions.value.some(
        (conversion) =>
          conversion.id === noteConversionId.value &&
          conversion.materialSku === noteMaterialSku.value &&
          (!conversion.supplierRef || conversion.supplierRef === noteSupplierRef.value),
      )
    ) {
      noteConversionId.value =
        conversions.value.find(
          (conversion) =>
            conversion.isActive &&
            conversion.materialSku === noteMaterialSku.value &&
            (!conversion.supplierRef || conversion.supplierRef === noteSupplierRef.value),
        )?.id ?? "";
    }
    receiptLines.value = receiptLines.value.map((line) => {
      const materialSku = !line.materialSku || materials.value.some((material) => material.sku === line.materialSku) ?
        line.materialSku
      : firstMaterialSku;
      const conversionAllowed =
        line.conversionId &&
        conversions.value.some(
          (conversion) =>
            conversion.id === line.conversionId &&
            conversion.isActive &&
            conversion.materialSku === materialSku &&
            (!conversion.supplierRef || conversion.supplierRef === receiptSupplierRef.value),
        );
      return {
        ...line,
        materialSku,
        conversionId: conversionAllowed ? line.conversionId : defaultReceiptConversionId(materialSku),
      };
    });
  }

  // O rascunho do recibo é estado do cliente: o GET base devolve um
  // activeReceipt default (o servidor não persiste rascunho), então só o
  // primeiro carregamento e as ações que falam do recibo (scan/confirmar/
  // recusar) podem sobrescrevê-lo — senão qualquer refresh apaga as linhas
  // que o operador acabou de receber ou digitar.
  function applyProjection(next: PurchaseProjection, options: { receipt?: boolean } = {}) {
    materials.value = copy(next.materials);
    suppliers.value = copy(next.suppliers);
    conversions.value = copy(next.conversions);
    costs.value = copy(next.costs);
    purchaseRequestStatuses.value = { ...next.purchaseRequestStatuses };
    if (options.receipt) {
      receiptMode.value = next.activeReceipt.mode;
      receiptSupplierRef.value = next.activeReceipt.supplierRef || "";
      invoiceInput.value = next.activeReceipt.invoiceInput || "";
      receiptNote.value = next.activeReceipt.note || "";
      receiptLines.value = receiptLineCopy(next.activeReceipt.lines ?? []);
      receiptConfirmedAt.value = null;
      receiptRejectedAt.value = null;
      receiptHydrated.value = true;
    }
    normalizeSelections();
  }

  watch(
    () => data.value?.purchase,
    (next) => {
      if (next) applyProjection(next, { receipt: !receiptHydrated.value });
    },
    { immediate: true },
  );

  watch(error, (value) => {
    if (value) flagIfStationLocked(value);
  }, { immediate: true });

  function requireBackend(action: string): boolean {
    if (backendReady.value) return true;
    const message =
      backendErrorStatus.value === 403 ?
        "Este operador não tem permissão para Compras."
      : backendErrorStatus.value === 401 ?
        "Sua sessão expirou. Entre novamente para continuar."
      : `Conecte o backend para ${action}.`;
    actionError.value = message;
    useSonner.error(message);
    return false;
  }

  // Devolve a resposta em vez de um booleano porque uma das ações precisa de um
  // dado dela: declarar conversão volta com o `conversionId` que a linha travada
  // vai selecionar. `null` continua sendo o "não deu" dos usos que só testam.
  async function runBackendAction(
    request: () => Promise<PurchaseActionResponse>,
    options: { receipt?: boolean } = {},
  ): Promise<PurchaseActionResponse | null> {
    if (actionPending.value) return null;
    actionPending.value = true;
    actionError.value = "";
    try {
      const response = await request();
      if (response.purchase) applyProjection(response.purchase, options);
      if (response.message) useSonner.success(response.message);
      await refresh();
      return response;
    } catch (err) {
      const message = httpErrorMessage(err, "Falha na ação. Tente de novo.");
      actionError.value = message;
      useSonner.error(message);
      await refresh();
      return null;
    } finally {
      actionPending.value = false;
    }
  }

  function selectMaterial(sku: string) {
    selectedMaterialSku.value = sku;
    noteMaterialSku.value = sku;
    baseView.value = "materials";
  }

  function selectSupplier(ref: string) {
    selectedSupplierRef.value = ref;
    noteSupplierRef.value = ref;
    baseView.value = "suppliers";
  }

  function receiptConversionsFor(materialSku: string): MaterialConversion[] {
    return conversions.value
      .filter(
        (conversion) =>
          conversion.isActive &&
          conversion.materialSku === materialSku &&
          (!conversion.supplierRef || conversion.supplierRef === receiptSupplierRef.value),
      )
      .sort((a, b) => {
        const aScore = a.supplierRef === receiptSupplierRef.value ? 0 : 1;
        const bScore = b.supplierRef === receiptSupplierRef.value ? 0 : 1;
        return aScore - bScore || a.label.localeCompare(b.label);
      });
  }

  function defaultReceiptConversionId(materialSku: string): string | null {
    return receiptConversionsFor(materialSku)[0]?.id ?? null;
  }

  function setReceiptMode(mode: ReceiptMode) {
    receiptMode.value = mode;
    receiptConfirmedAt.value = null;
    receiptRejectedAt.value = null;
    if (backendReady.value) {
      receiptSupplierRef.value = suppliers.value[0]?.ref ?? "";
      receiptNote.value = mode === "manual" ? "Romaneio em papel conferido na entrega" : "";
      receiptLines.value = [];
      return;
    }
    if (mode === "manual") {
      receiptSupplierRef.value = "SUP-FAZENDA-BOA-VISTA";
      receiptNote.value = "Romaneio em papel conferido na entrega";
      receiptLines.value = copy(MANUAL_RECEIPT_LINES);
      return;
    }
    receiptSupplierRef.value = "SUP-MOINHO-SP";
    receiptNote.value = "";
    receiptLines.value = copy(INVOICE_RECEIPT_LINES);
  }

  function updateReceiptLine(lineId: string, patch: Partial<ReceiptLine>) {
    receiptConfirmedAt.value = null;
    receiptRejectedAt.value = null;
    receiptLines.value = receiptLines.value.map((line) => (line.id === lineId ? { ...line, ...patch } : line));
  }

  function setReceiptSupplier(ref: string) {
    receiptSupplierRef.value = ref;
    receiptConfirmedAt.value = null;
    receiptRejectedAt.value = null;
    receiptLines.value = receiptLines.value.map((line) => {
      const currentConversion =
        line.conversionId ? conversions.value.find((conversion) => conversion.id === line.conversionId) : null;
      const currentIsAllowed =
        currentConversion &&
        currentConversion.isActive &&
        currentConversion.materialSku === line.materialSku &&
        (!currentConversion.supplierRef || currentConversion.supplierRef === ref);
      return currentIsAllowed ? line : { ...line, conversionId: defaultReceiptConversionId(line.materialSku) };
    });
  }

  function setReceiptLineMaterial(lineId: string, materialSku: string) {
    updateReceiptLine(lineId, {
      materialSku,
      conversionId: defaultReceiptConversionId(materialSku),
      checked: false,
    });
  }

  function acceptReceiptLineSuggestion(lineId: string) {
    const line = receiptLines.value.find((item) => item.id === lineId);
    if (!line?.suggestedMaterialSku) return;
    setReceiptLineMaterial(lineId, line.suggestedMaterialSku);
  }

  /**
   * Declara a conversão e já a coloca na linha que estava travada.
   *
   * Um clique quando vem da sugestão da NF; o mesmo caminho quando o operador
   * digita a embalagem que a nota não soube contar. A conversão nasce no
   * servidor (com autor), volta na projection, e a linha passa a apontar para
   * ela — a entrada segue sem ninguém sair da tela para o Admin.
   */
  async function declareReceiptLineConversion(
    lineId: string,
    input: { label: string; factor: string; kind: ConversionKind },
  ): Promise<boolean> {
    const line = receiptLines.value.find((item) => item.id === lineId);
    if (!line?.materialSku) return false;
    if (!requireBackend("cadastrar a conversão")) return false;
    const response = await runBackendAction(() =>
      api.declareConversion({
        materialSku: line.materialSku,
        supplierRef: receiptSupplierRef.value,
        label: input.label.trim(),
        factor: input.factor,
        kind: input.kind,
      }),
    );
    if (!response?.conversionId) return false;
    updateReceiptLine(lineId, { conversionId: response.conversionId, requiresConversion: false });
    return true;
  }

  /**
   * Aceitar o par que a NF declara, deixando o servidor derivar o fator.
   *
   * É o caminho da nota real: o item chega como "MANTEIGA S/SAL CX 5 KG
   * PRESIDENT TEU", não casa com insumo nenhum, e por isso o scan não pôde
   * calcular a conversão — sem insumo não há unidade-base para converter PARA.
   * Escolhido o insumo, "7 CX = 35 KG" volta ao servidor e vira "1 caixa 5 kg".
   */
  async function acceptReceiptLineInvoiceAxes(lineId: string): Promise<boolean> {
    const line = receiptLines.value.find((item) => item.id === lineId);
    if (!line?.materialSku) return false;
    if (!requireBackend("cadastrar a conversão")) return false;
    const response = await runBackendAction(() =>
      api.declareConversion({
        materialSku: line.materialSku,
        supplierRef: receiptSupplierRef.value,
        invoiceQty: line.invoiceQty,
        invoiceUnit: line.invoiceUnit,
        invoiceTaxQty: line.invoiceTaxQty,
        invoiceTaxUnit: line.invoiceTaxUnit,
        invoiceDescription: line.invoiceDescription,
      }),
    );
    if (!response?.conversionId) return false;
    updateReceiptLine(lineId, { conversionId: response.conversionId, requiresConversion: false });
    return true;
  }

  /** Aceitar a conversão que a NF propôs, sem redigitar nada. */
  async function acceptReceiptLineConversion(lineId: string): Promise<boolean> {
    const suggestion = receiptLines.value.find((item) => item.id === lineId)?.conversionSuggestion;
    if (!suggestion) return false;
    return declareReceiptLineConversion(lineId, {
      label: suggestion.label,
      factor: suggestion.factor,
      kind: suggestion.kind,
    });
  }

  function addReceiptLine() {
    const materialSku = materials.value[0]?.sku ?? "";
    const conversionId = defaultReceiptConversionId(materialSku);
    receiptConfirmedAt.value = null;
    receiptRejectedAt.value = null;
    receiptLines.value = receiptLines.value.concat({
      id: `receipt-${Date.now()}`,
      materialSku,
      conversionId,
      purchaseQty: 1,
      costInput: "",
      expiryDate: "",
      lineNote: "",
      checked: false,
    });
  }

  function removeReceiptLine(lineId: string) {
    receiptConfirmedAt.value = null;
    receiptRejectedAt.value = null;
    receiptLines.value = receiptLines.value.filter((line) => line.id !== lineId);
  }

  async function readInvoice() {
    if (!requireBackend("traduzir a NF")) return;
    if (!invoiceInput.value.trim()) {
      actionError.value = "Escaneie QR, código de barras ou cole a chave da NF.";
      useSonner.error(actionError.value);
      return;
    }
    await runBackendAction(() => api.scanInvoice({ qrPayload: invoiceInput.value }), { receipt: true });
  }

  async function confirmReceipt() {
    if (!receiptReady.value) return;
    if (!requireBackend("confirmar a entrada no estoque")) return;
    const ok = await runBackendAction(
      () =>
        api.confirmReceipt({
          mode: receiptMode.value,
          supplierRef: receiptSupplierRef.value,
          invoiceAccessKey: invoiceStatus.value.accessKey,
          note: receiptNote.value,
          lines: receiptLines.value,
        }),
      { receipt: true },
    );
    if (ok) receiptConfirmedAt.value = todayStamp();
  }

  async function rejectReceipt() {
    if (!requireBackend("registrar a devolução")) return;
    if (!receiptHasRejectionReason.value) {
      actionError.value = "Descreva o motivo da recusa/devolução antes de registrar.";
      useSonner.error(actionError.value);
      return;
    }
    const ok = await runBackendAction(
      () =>
        api.rejectReceipt({
          mode: receiptMode.value,
          supplierRef: receiptSupplierRef.value,
          invoiceAccessKey: invoiceStatus.value.accessKey,
          note: receiptNote.value,
          lines: receiptLines.value,
        }),
      { receipt: true },
    );
    if (ok) receiptRejectedAt.value = todayStamp();
  }

  // ── Contagem de insumos (auditoria de estoque, gestor/dono) ──────────────

  const countBoardItems = computed<CountItem[]>(() => {
    if (countLoaded.value) return countItems.value;
    // Modo demonstração (sem backend): a lista dos insumos serve de amostra,
    // mas nada se lança — confirmar exige backend.
    if (readonlyFallback.value) {
      return materials.value.map((material) => ({
        sku: material.sku,
        name: material.name,
        unit: material.unit,
        category: material.category,
        isActive: material.isActive,
        systemQty: material.stockOnHand,
      }));
    }
    return [];
  });

  const countBoardRows = computed(() => countRows(countBoardItems.value, countInputs.value, countReasons.value));

  const countFilteredRows = computed(() => {
    const term = query.value.trim().toLowerCase();
    if (!term) return countBoardRows.value;
    return countBoardRows.value.filter(
      (row) =>
        row.item.name.toLowerCase().includes(term) ||
        row.item.sku.toLowerCase().includes(term) ||
        row.item.category.toLowerCase().includes(term),
    );
  });

  const countDivergentRows = computed(() => countBoardRows.value.filter((row) => row.divergent));
  const countTotals = computed(() => countSummary(countBoardRows.value));
  const countReady = computed(() => backendReady.value && !countForbidden.value && countTotals.value.ready);

  async function loadCount() {
    if (countPending.value) return;
    countPending.value = true;
    try {
      const response = await api.fetchCount();
      countItems.value = response.count.items.map((item) => ({ ...item }));
      countLoaded.value = true;
      countForbidden.value = false;
    } catch (err) {
      countForbidden.value = httpError(err).status === 403;
    } finally {
      countPending.value = false;
    }
  }

  watch(
    [view, baseView, backendReady],
    ([currentView, currentBase, ready]) => {
      if (currentView === "base" && currentBase === "count" && ready && !countLoaded.value) {
        void loadCount();
      }
    },
    { immediate: true },
  );

  function setCountInput(sku: string, value: string) {
    countConfirmedAt.value = null;
    countInputs.value = { ...countInputs.value, [sku]: value };
  }

  function setCountReason(sku: string, value: string) {
    countReasons.value = { ...countReasons.value, [sku]: value };
  }

  function resetCount() {
    countInputs.value = {};
    countReasons.value = {};
  }

  async function confirmCount(): Promise<boolean> {
    if (!countReady.value || actionPending.value) return false;
    if (!requireBackend("lançar os ajustes da contagem")) return false;
    actionPending.value = true;
    actionError.value = "";
    try {
      const response = await api.confirmCount(countConfirmPayload(countBoardRows.value));
      if (response.count) {
        countItems.value = response.count.items.map((item) => ({ ...item }));
        countLoaded.value = true;
      }
      if (response.message) useSonner.success(response.message);
      resetCount();
      countConfirmedAt.value = todayStamp();
      // O board também muda de figura: o estoque disponível acompanha o ajuste.
      await refresh();
      return true;
    } catch (err) {
      const message = httpErrorMessage(err, "Falha na ação. Tente de novo.");
      actionError.value = message;
      useSonner.error(message);
      return false;
    } finally {
      actionPending.value = false;
    }
  }

  function purchaseRequestStatus(sku: string): PurchaseRequestStatus {
    return purchaseRequestStatuses.value[sku] ?? "review";
  }

  async function sendPurchaseRequest(sku: string) {
    const status = purchaseRequestStatus(sku);
    if (status === "sent") return;
    if (!requireBackend("enviar o pedido ao fornecedor")) return;
    await runBackendAction(() => api.sendRequest({ materialSku: sku }));
  }

  async function setPreferredCost(costId: string) {
    const target = costs.value.find((cost) => cost.id === costId);
    if (!target) return;
    if (!requireBackend("definir o custo padrão")) return;
    await runBackendAction(() =>
      api.upsertCost({
        materialSku: target.materialSku,
        supplierRef: target.supplierRef,
        conversionId: target.conversionId,
        costInput: centsInput(target.costQ),
        makePreferred: true,
      }),
    );
  }

  async function saveQuote(makePreferred = false) {
    const costQ = parseMoneyInput(noteCostInput.value);
    if (!noteMaterial.value || !noteSupplier.value || costQ <= 0) return;
    if (!requireBackend("salvar o custo")) return;
    const ok = await runBackendAction(() =>
      api.upsertCost({
        materialSku: noteMaterialSku.value,
        supplierRef: noteSupplierRef.value,
        conversionId: noteConversionId.value || null,
        costInput: noteCostInput.value,
        makePreferred,
      }),
    );
    if (ok) {
      selectedMaterialSku.value = noteMaterialSku.value;
      selectedSupplierRef.value = noteSupplierRef.value;
    }
  }

  return {
    view,
    baseView,
    query,
    onlyAlerts,
    selectedMaterialSku,
    selectedSupplierRef,
    noteMaterialSku,
    noteSupplierRef,
    noteConversionId,
    noteCostInput,
    materials,
    suppliers,
    conversions,
    costs,
    enrichedMaterials,
    filteredMaterials,
    selectedMaterial,
    selectedSupplier,
    selectedCostRows,
    noteMaterial,
    noteSupplier,
    availableNoteConversions,
    selectedNoteConversion,
    notePreview,
    metrics,
    integrityQueue,
    reorderRows,
    supplierSummaries,
    projection,
    receiptMode,
    invoiceInput,
    receiptSupplierRef,
    receiptNote,
    receiptLines,
    receiptConfirmedAt,
    receiptRejectedAt,
    receiptSupplier,
    invoiceStatus,
    receiptLinePreviews,
    receiptBlockers,
    receiptWatchWarnings,
    receiptPendingLines,
    receiptDocumentBlockers,
    receiptSupplierBlockers,
    receiptCheckedCount,
    receiptTotalCostQ,
    receiptHasRejectionReason,
    receiptReady,
    purchaseRequestStatuses,
    pending,
    error,
    refresh,
    backendReady,
    backendErrorStatus,
    readonlyFallback,
    backendBlockTitle,
    backendBlockMessage,
    actionPending,
    actionError,
    selectMaterial,
    selectSupplier,
    receiptConversionsFor,
    setReceiptMode,
    setReceiptSupplier,
    setReceiptLineMaterial,
    acceptReceiptLineSuggestion,
    acceptReceiptLineConversion,
    acceptReceiptLineInvoiceAxes,
    declareReceiptLineConversion,
    updateReceiptLine,
    addReceiptLine,
    removeReceiptLine,
    readInvoice,
    confirmReceipt,
    rejectReceipt,
    countBoardRows,
    countFilteredRows,
    countDivergentRows,
    countTotals,
    countReady,
    countPending,
    countLoaded,
    countForbidden,
    countConfirmedAt,
    loadCount,
    setCountInput,
    setCountReason,
    resetCount,
    confirmCount,
    purchaseRequestStatus,
    sendPurchaseRequest,
    setPreferredCost,
    saveQuote,
    costPerBaseUnitQ,
  };
}

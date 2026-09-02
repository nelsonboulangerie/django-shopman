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
  ReceiptOutcome,
  Supplier,
  SupplierMaterialCost,
} from "~/types/purchase";
import { PURCHASE_API_ENDPOINTS, usePurchaseApi } from "~/composables/usePurchaseApi";
import {
  costBatchLineErrors as buildCostBatchLineErrors,
  costBatchPayload as buildCostBatchPayload,
  costPerBaseUnitQ,
  countConfirmPayload,
  countRows,
  countSummary,
  enrichMaterial,
  invoiceProbe,
  isApproximateCost,
  parseMoneyInput,
  quotePreview as buildQuotePreview,
  receiptFirstBlocker as receiptFirstReceiptBlocker,
  receiptIsBlank as receiptIsBlankDraft,
  receiptLinePreview,
  receiptPendingItems,
  reorderBlockers as buildReorderBlockers,
  reorderRows as buildReorderRows,
  supplierCostRows,
} from "~/presentation/purchase";

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
  const selectedMaterialSku = useState("purchase-selected-material", () => "");
  const selectedSupplierRef = useState("purchase-selected-supplier", () => "");
  const noteMaterialSku = useState("purchase-note-material", () => "");
  const noteSupplierRef = useState("purchase-note-supplier", () => "");
  const noteConversionId = useState("purchase-note-conversion", () => "");
  const noteCostInput = useState("purchase-note-cost", () => "");
  const receiptMode = useState<ReceiptMode>("purchase-receipt-mode", () => "invoice");
  const invoiceInput = useState("purchase-invoice-input", () => "");
  const receiptSupplierRef = useState("purchase-receipt-supplier", () => "");
  const receiptNote = useState("purchase-receipt-note", () => "");
  const receiptLines = useState<ReceiptLine[]>("purchase-receipt-lines", () => []);
  // Confirmar zera o rascunho, e um rascunho zerado nao sabe dizer o que acabou
  // de entrar. O resultado guarda o resumo capturado ANTES da limpeza — e o que
  // o aviso de sucesso mostra.
  const receiptOutcome = useState<ReceiptOutcome | null>("purchase-receipt-outcome", () => null);
  const receiptHydrated = useState("purchase-receipt-hydrated", () => false);
  const purchaseRequestStatuses = useState<Record<string, PurchaseRequestStatus>>(
    "purchase-request-statuses",
    () => ({}),
  );

  // A base nasce VAZIA e só o servidor a preenche.
  //
  // Estas quatro listas já nasceram com um catálogo de demonstração dentro
  // (farinha, manteiga, ovos, leite, alecrim...), e como a busca é client-side
  // (`server: false`) esse catálogo era o que a primeira pintura mostrava — em
  // número grande, sem nenhuma marca de que era exemplo. O painel anunciava
  // "Comprar 8 · R$ 4.293,97" com insumos que a padaria não tinha, e quando a
  // resposta real chegava o mesmo painel virava 0. Nada mudara nos dados: o
  // primeiro número nunca fora real. Dado inventado não é estado de partida.
  const materials = useState<Material[]>("purchase-materials", () => []);
  const suppliers = useState<Supplier[]>("purchase-suppliers", () => []);
  const conversions = useState<MaterialConversion[]>("purchase-conversions", () => []);
  const costs = useState<SupplierMaterialCost[]>("purchase-costs", () => []);
  // Contagem: a posição vem CRUA do ledger (endpoint próprio, restrito ao
  // gestor/dono) — o stockOnHand do board desconta hold e lote vencido e não
  // bateria com o ajuste lançado.
  const countItems = useState<CountItem[]>("purchase-count-items", () => []);
  const countInputs = useState<Record<string, string>>("purchase-count-inputs", () => ({}));
  const countReasons = useState<Record<string, string>>("purchase-count-reasons", () => ({}));
  const countLoaded = useState("purchase-count-loaded", () => false);
  const countForbidden = useState("purchase-count-forbidden", () => false);
  const countConfirmedAt = useState<string | null>("purchase-count-confirmed-at", () => null);
  // Lançamento em lote: uma tabela de preços do MESMO fornecedor. É o gesto que
  // tira 54 insumos do estado "sem custo preferencial" — e portanto fora de
  // qualquer pedido — sem passar pelo Django Admin.
  const batchSupplierRef = useState("purchase-batch-supplier", () => "");
  const batchInputs = useState<Record<string, string>>("purchase-batch-inputs", () => ({}));
  const batchConversionIds = useState<Record<string, string>>("purchase-batch-conversions", () => ({}));
  const batchOnlyMissing = useState("purchase-batch-only-missing", () => true);
  const batchQuery = useState("purchase-batch-query", () => "");
  const batchLineErrors = useState<Record<string, string>>("purchase-batch-line-errors", () => ({}));
  // Estoque mínimo declarado: sem consumo medido o alvo de reposição é zero e o
  // insumo nunca vira sugestão. Declarar o mínimo é o que o destrava.
  const minStockInputs = useState<Record<string, string>>("purchase-min-stock-inputs", () => ({}));
  const minStockLineErrors = useState<Record<string, string>>("purchase-min-stock-errors", () => ({}));
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
    return "A tela não conseguiu carregar a base de insumos, fornecedores e custos. Nada é exibido enquanto não houver dado real. Toque em Atualizar para tentar de novo.";
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
  // Um rascunho que ainda nao comecou nao tem pendencia — tem convite. Sem
  // isto, confirmar a entrada devolvia o rascunho zerado do servidor e a tela
  // acusava "Ler QR, codigo de barras ou chave da NF" em vermelho logo ACIMA do
  // "Entrada confirmada" em verde. O operador acertou tudo e levou uma bronca.
  const receiptIsBlank = computed(() =>
    receiptIsBlankDraft(receiptLines.value, invoiceInput.value, receiptNote.value),
  );

  // O painel listava as pendências ACHATADAS — dez pílulas "Definir insumo"
  // iguais, sem dizer de qual item, e a lista ficava inútil justamente quando
  // era mais necessária (nota grande). Uma linha por item, com nome e gesto.
  const receiptPendingLines = computed(() => receiptPendingItems(receiptLinePreviews.value));
  const receiptDocumentBlockers = computed(() =>
    receiptIsBlank.value ? []
    : receiptMode.value === "invoice" && !invoiceStatus.value.valid ? ["Ler QR, código de barras ou chave da NF"]
    : [],
  );
  const receiptSupplierBlockers = computed(() =>
    receiptIsBlank.value || receiptSupplierRef.value ? [] : ["Definir fornecedor"],
  );
  // O gesto que o botao `Confirmar entrada` responde quando ainda nao da.
  const receiptFirstBlocker = computed(() =>
    receiptFirstReceiptBlocker(
      receiptDocumentBlockers.value,
      receiptSupplierBlockers.value,
      receiptPendingLines.value,
      receiptLinePreviews.value.length > 0,
    ),
  );
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

  // A fila de compra vem inteira de `presentation/` e é a resposta do SERVIDOR
  // (`Material.suggestedQty`). Ver `reorderRows` lá: painel e tela Comprar
  // faziam duas contas diferentes para a mesma pergunta, e discordavam em voz
  // alta.
  const reorderRows = computed(() =>
    buildReorderRows(materials.value, suppliers.value, costs.value, conversions.value),
  );

  // Por que a fila está vazia. Só faz sentido depois que o servidor respondeu —
  // antes disso o vazio é "ainda não chegou", não "não há".
  const reorderBlockers = computed(() =>
    backendReady.value ? buildReorderBlockers(materials.value, costs.value) : [],
  );

  // As linhas da tabela de preços. O filtro nasce em "só os que faltam" porque
  // é essa a tarefa: fechar o buraco dos insumos sem custo preferencial.
  const batchRows = computed(() => {
    const term = batchQuery.value.trim().toLowerCase();
    return enrichedMaterials.value.filter((material) => {
      if (!material.isActive) return false;
      if (batchOnlyMissing.value && material.preferredCost) return false;
      if (!term) return true;
      return (
        material.name.toLowerCase().includes(term) ||
        material.sku.toLowerCase().includes(term) ||
        material.category.toLowerCase().includes(term)
      );
    });
  });

  // Conta as MESMAS linhas que o payload manda — as visíveis. Um botão que diz
  // "Salvar 10" e manda 3 é pior que um botão sem número.
  const batchFilledCount = computed(
    () => batchRows.value.filter((row) => Boolean((batchInputs.value[row.sku] ?? "").trim())).length,
  );

  // Trocar de fornecedor invalida a unidade de compra escolhida: a conversão é
  // do par (insumo, fornecedor). Sem limpar, o `<select>` fica em branco — a
  // opção sumiu da lista — enquanto o id antigo continua no estado e viaja no
  // payload, e o servidor recusa o lote inteiro com "conversão pertence a outro
  // fornecedor" numa linha que na tela diz "Unidade-base".
  watch(batchSupplierRef, () => {
    batchConversionIds.value = {};
    batchLineErrors.value = {};
  });

  const batchReady = computed(() => Boolean(batchSupplierRef.value) && batchFilledCount.value > 0);

  function batchConversionsFor(materialSku: string) {
    return conversions.value.filter(
      (conversion) =>
        conversion.isActive &&
        conversion.materialSku === materialSku &&
        (!conversion.supplierRef || conversion.supplierRef === batchSupplierRef.value),
    );
  }

  function setBatchInput(materialSku: string, value: string) {
    batchInputs.value = { ...batchInputs.value, [materialSku]: value };
    // Editar a linha apaga o erro dela: o aviso descreve o que foi enviado, e o
    // que está na tela já não é isso.
    if (batchLineErrors.value[materialSku]) {
      batchLineErrors.value = Object.fromEntries(
        Object.entries(batchLineErrors.value).filter(([sku]) => sku !== materialSku),
      );
    }
  }

  function setBatchConversion(materialSku: string, conversionId: string) {
    batchConversionIds.value = { ...batchConversionIds.value, [materialSku]: conversionId };
  }

  // Só as linhas visíveis, pelo mesmo motivo do lote de custos: a busca e o
  // filtro "Atenção" escondem linhas já digitadas, e o erro de uma linha
  // escondida não teria onde aparecer.
  const minStockRows = computed(() =>
    filteredMaterials.value.filter((material) => Boolean((minStockInputs.value[material.sku] ?? "").trim())),
  );

  const minStockFilledCount = computed(() => minStockRows.value.length);

  function setMinStockInput(materialSku: string, value: string) {
    minStockInputs.value = { ...minStockInputs.value, [materialSku]: value };
    if (minStockLineErrors.value[materialSku]) {
      minStockLineErrors.value = Object.fromEntries(
        Object.entries(minStockLineErrors.value).filter(([sku]) => sku !== materialSku),
      );
    }
  }

  function clearMinStock() {
    minStockInputs.value = {};
    minStockLineErrors.value = {};
  }

  /** Declara os mínimos digitados. Mesmo contrato do lote de custos. */
  async function saveMinStock() {
    if (!minStockFilledCount.value) return;
    if (!requireBackend("salvar os mínimos")) return;
    if (actionPending.value) return;

    actionPending.value = true;
    actionError.value = "";
    minStockLineErrors.value = {};
    try {
      const minimums = minStockRows.value.map((material) => ({
        materialSku: material.sku,
        minStock: (minStockInputs.value[material.sku] ?? "").trim(),
      }));
      const response = await api.setMinStock({ minimums });
      if (response.purchase) applyProjection(response.purchase);
      if (response.message) useSonner.success(response.message);
      clearMinStock();
      await refresh();
    } catch (err) {
      minStockLineErrors.value = buildCostBatchLineErrors(httpError(err).data);
      const message = httpErrorMessage(err, "Não foi possível salvar os mínimos.");
      actionError.value = message;
      useSonner.error(message);
    } finally {
      actionPending.value = false;
    }
  }

  function clearCostBatch() {
    batchInputs.value = {};
    batchConversionIds.value = {};
    batchLineErrors.value = {};
  }

  /**
   * Lança a tabela inteira num POST.
   *
   * O lote é tudo-ou-nada no servidor, então a recusa precisa dizer QUAL linha
   * errou — senão o operador recebe "corrija as linhas" olhando para quarenta
   * campos preenchidos. Os erros voltam em `error.lines` e vão para o campo.
   */
  async function saveCostBatch() {
    if (!batchReady.value) return;
    if (!requireBackend("salvar os custos")) return;
    if (actionPending.value) return;

    actionPending.value = true;
    actionError.value = "";
    batchLineErrors.value = {};
    try {
      const payload = buildCostBatchPayload(
        batchSupplierRef.value,
        batchInputs.value,
        batchConversionIds.value,
        batchRows.value.map((row) => row.sku),
      );
      const response = await api.upsertCostBatch(payload);
      if (response.purchase) applyProjection(response.purchase);
      if (response.message) useSonner.success(response.message);
      clearCostBatch();
      await refresh();
    } catch (err) {
      batchLineErrors.value = buildCostBatchLineErrors(httpError(err).data);
      const message = httpErrorMessage(err, "Não foi possível salvar os custos.");
      actionError.value = message;
      useSonner.error(message);
    } finally {
      actionPending.value = false;
    }
  }

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
      receiptOutcome.value = null;
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
    options: { receipt?: boolean; quiet?: boolean } = {},
  ): Promise<PurchaseActionResponse | null> {
    if (actionPending.value) return null;
    actionPending.value = true;
    actionError.value = "";
    try {
      const response = await request();
      if (response.purchase) applyProjection(response.purchase, options);
      // `quiet`: a própria tela já anuncia o que aconteceu, e em tamanho maior
      // que um toast. Repetir "Entrada confirmada no estoque" duas vezes na
      // mesma dobra não é reforço, é ruído.
      if (response.message && !options.quiet) useSonner.success(response.message);
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
    receiptOutcome.value = null;
    receiptSupplierRef.value = suppliers.value[0]?.ref ?? "";
    receiptNote.value = mode === "manual" ? "Romaneio em papel conferido na entrega" : "";
    receiptLines.value = [];
  }

  function updateReceiptLine(lineId: string, patch: Partial<ReceiptLine>) {
    receiptOutcome.value = null;
    receiptLines.value = receiptLines.value.map((line) => (line.id === lineId ? { ...line, ...patch } : line));
  }

  function setReceiptSupplier(ref: string) {
    receiptSupplierRef.value = ref;
    receiptOutcome.value = null;
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
    receiptOutcome.value = null;
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
    receiptOutcome.value = null;
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

  /**
   * O que a entrada foi, fotografado ANTES de o rascunho zerar.
   *
   * A resposta do servidor devolve o recibo em branco (o rascunho nao e
   * persistido), entao ler `receiptLinePreviews` depois de confirmar so acha
   * lista vazia. Quem quiser mostrar "7 itens, R$ 1.480,00" tem de guardar
   * antes.
   */
  function receiptSnapshot(kind: ReceiptOutcome["kind"]): ReceiptOutcome {
    return {
      kind,
      at: todayStamp(),
      mode: receiptMode.value,
      lineCount: receiptLinePreviews.value.length,
      totalCostQ: receiptTotalCostQ.value,
      supplierName: receiptSupplier.value?.name ?? "",
    };
  }

  async function confirmReceipt(): Promise<boolean> {
    if (!receiptReady.value) return false;
    if (!requireBackend("confirmar a entrada no estoque")) return false;
    const snapshot = receiptSnapshot("confirmed");
    const ok = await runBackendAction(
      () =>
        api.confirmReceipt({
          mode: receiptMode.value,
          supplierRef: receiptSupplierRef.value,
          invoiceAccessKey: invoiceStatus.value.accessKey,
          note: receiptNote.value,
          lines: receiptLines.value,
        }),
      { receipt: true, quiet: true },
    );
    if (ok) receiptOutcome.value = snapshot;
    return Boolean(ok);
  }

  async function rejectReceipt(): Promise<boolean> {
    if (!requireBackend("registrar a devolução")) return false;
    if (!receiptHasRejectionReason.value) {
      actionError.value = "Descreva o motivo da recusa/devolução antes de registrar.";
      useSonner.error(actionError.value);
      return false;
    }
    const snapshot = receiptSnapshot("rejected");
    const ok = await runBackendAction(
      () =>
        api.rejectReceipt({
          mode: receiptMode.value,
          supplierRef: receiptSupplierRef.value,
          invoiceAccessKey: invoiceStatus.value.accessKey,
          note: receiptNote.value,
          lines: receiptLines.value,
        }),
      { receipt: true, quiet: true },
    );
    if (ok) receiptOutcome.value = snapshot;
    return Boolean(ok);
  }

  /** Fecha o aviso de sucesso — o proximo recebimento comeca da tela limpa. */
  function dismissReceiptOutcome() {
    receiptOutcome.value = null;
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
    reorderBlockers,
    batchSupplierRef,
    batchInputs,
    batchConversionIds,
    batchOnlyMissing,
    batchQuery,
    batchLineErrors,
    batchRows,
    batchFilledCount,
    batchReady,
    batchConversionsFor,
    setBatchInput,
    setBatchConversion,
    clearCostBatch,
    saveCostBatch,
    minStockInputs,
    minStockLineErrors,
    minStockFilledCount,
    setMinStockInput,
    clearMinStock,
    saveMinStock,
    supplierSummaries,
    projection,
    receiptMode,
    invoiceInput,
    receiptSupplierRef,
    receiptNote,
    receiptLines,
    receiptOutcome,
    receiptIsBlank,
    receiptFirstBlocker,
    dismissReceiptOutcome,
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

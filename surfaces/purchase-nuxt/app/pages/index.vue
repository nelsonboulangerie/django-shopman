<script setup lang="ts">
import type {
  ConversionKind,
  EnrichedMaterial,
  Material,
  MaterialTone,
  PurchaseBaseView,
  PurchaseRequestStatus,
  ReceiptBlocker,
  ReceiptDocumentAnchor,
  ReceiptFieldAnchor,
  ReceiptLine,
  ReceiptMode,
  ReceiptWarningTone,
  SupplierMaterialCost,
} from "~/types/purchase";
import {
  costPerBaseUnitQ,
  coverageLabel,
  formatMoney,
  formatQty,
  formatQtyDiff,
  formatShortDate,
  formatStockOnHand,
  invoiceKeyTail,
  invoiceNumberLabel,
  receiptOutcomeSummary,
  isApproximateCost,
  purchaseUnitLabel,
  resaleCopy,
  resaleSuggestionView,
  openingView,
  purchaseSuggestionLabel,
  skuRoleBadges,
} from "~/presentation/purchase";
import { RECEIPT_LINE_STATUS_BADGE, RECEIPT_LINE_STATUS_ROW, RECEIPT_LINE_STATUS_TEXT } from "~/utils/receiptLineStatus";
import { FLASH_RING, receiptFieldSelector, waitForElement } from "~/utils/receiptFocus";

const {
  view,
  baseView,
  query,
  onlyAlerts,
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
  availableNoteConversions,
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
  setSale,
  setOpening,
  clearMinStock,
  saveMinStock,
  supplierSummaries,
  receiptMode,
  invoiceInput,
  receiptSupplierRef,
  receiptNote,
  receiptOutcome,
  receiptIsBlank,
  receiptFirstBlocker,
  dismissReceiptOutcome,
  receiptSupplier,
  invoiceStatus,
  receiptLinePreviews,
  receiptRows,
  receiptException,
  receiptInvoiceVolumes,
  receiptVolumesStep,
  setReceiptVolumesCounted,
  receiptWatchWarnings,
  receiptPendingLines,
  receiptDocumentBlockers,
  receiptSupplierBlockers,
  receiptConference,
  receiptTotalCostQ,
  receiptHasRejectionReason,
  receiptReady,
  pending,
  refresh,
  backendReady,
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
  countFilteredRows,
  countDivergentRows,
  countTotals,
  countReady,
  countPending,
  countForbidden,
  countConfirmedAt,
  setCountInput,
  setCountReason,
  resetCount,
  confirmCount,
  purchaseRequestStatus,
  sendPurchaseRequest,
  setPreferredCost,
  saveQuote,
} = usePurchaseDesk();

const toneClasses: Record<MaterialTone, string> = {
  ok: "border-success/25 bg-success/10 text-success",
  watch: "border-warning/30 bg-warning/10 text-warning",
  urgent: "border-destructive/30 bg-destructive/10 text-destructive",
};

const toneLabels: Record<MaterialTone, string> = {
  ok: "Em ordem",
  watch: "Revisar",
  urgent: "Comprar",
};

// A etiqueta cheia da suíte (pílula com ponto, prévias v3/v4): um estilo só para o
// estado do insumo em toda tela.
const tonePills: Record<MaterialTone, string> = {
  ok: "pill-success",
  watch: "pill-warning",
  urgent: "pill-destructive",
};

const receiptWarningClasses: Record<ReceiptWarningTone, string> = {
  ok: "border-success/25 bg-success/10 text-success",
  watch: "border-warning/30 bg-warning/10 text-warning",
  block: "border-destructive/30 bg-destructive/10 text-destructive",
};

const requestStatusClasses: Record<PurchaseRequestStatus, string> = {
  review: "border-warning/30 bg-warning/10 text-warning",
  approved: "border-info/30 bg-info/10 text-info",
  sent: "border-success/25 bg-success/10 text-success",
};

const requestStatusLabels: Record<PurchaseRequestStatus, string> = {
  review: "Revisar",
  approved: "Pronto",
  sent: "Enviado",
};

const baseTabs: { key: PurchaseBaseView; label: string; icon: string }[] = [
  { key: "materials", label: "Insumos", icon: "lucide:package-search" },
  { key: "suppliers", label: "Fornecedores", icon: "lucide:truck" },
  { key: "costs", label: "Custos", icon: "lucide:calculator" },
  { key: "count", label: "Contagem", icon: "lucide:clipboard-check" },
];

// "Permitir revenda" do item aberto: o campo de preço só existe depois do gesto,
// e volta fechado quando outro item é aberto.
const saleOpen = ref(false);
const salePriceInput = ref("");
watch(
  () => selectedMaterial.value?.sku,
  () => {
    saleOpen.value = false;
    salePriceInput.value = "";
  },
);

// O quadrado mostra o que o servidor diz (ou o formulário aberto): desligar
// uma revenda ativa é gesto na hora; ligar abre o campo de preço.
async function onResaleToggle(event: Event) {
  const input = event.target as HTMLInputElement;
  const material = selectedMaterial.value;
  if (!material) return;
  if (input.checked) {
    saleOpen.value = true;
    salePriceInput.value = resaleSuggestionView(material.saleSuggestion, material.unit)?.input ?? "";
    return;
  }
  if (saleOpen.value && !material.roles?.sellable) {
    saleOpen.value = false;
    salePriceInput.value = "";
    return;
  }
  input.checked = true;
  await setSale(material.sku, false);
}

// "Quando aberto, vira" do item aberto: rascunho local, reidratado a cada item.
const CREATE_OPENED = "__create__";
const openingDraft = reactive({ open: false, target: "", quantity: "", shelfLifeDays: "" });
watch(
  () => selectedMaterial.value?.sku,
  () => {
    const material = selectedMaterial.value;
    openingDraft.open = false;
    openingDraft.target = material?.opensInto?.sku ?? CREATE_OPENED;
    openingDraft.quantity = material?.opensInto?.quantity.replace(".", ",") ?? (material ? openingView(material, materials.value).suggestedQuantity : "");
    openingDraft.shelfLifeDays = material?.opensInto?.shelfLifeDays?.toString() ?? "";
  },
  { immediate: true },
);

async function saveOpening() {
  const material = selectedMaterial.value;
  if (!material) return;
  const creating = openingDraft.target === CREATE_OPENED;
  const ok = await setOpening(material.sku, {
    enabled: true,
    createOpened: creating,
    openedSku: creating ? "" : openingDraft.target,
    openedUnit: "kg",
    quantity: openingDraft.quantity,
    shelfLifeDays: openingDraft.shelfLifeDays,
  });
  if (ok) openingDraft.open = false;
}

async function confirmSale() {
  const material = selectedMaterial.value;
  if (!material) return;
  if (await setSale(material.sku, true, salePriceInput.value)) {
    saleOpen.value = false;
    salePriceInput.value = "";
  }
}

const countConfirmOpen = ref(false);

function openCountConfirm() {
  if (countReady.value) countConfirmOpen.value = true;
}

async function submitCount() {
  const ok = await confirmCount();
  if (ok) countConfirmOpen.value = false;
}

// O documento da entrada no cabeçalho de uma linha (prévias v3/v4): "Alto Alegre · NF
// 12.884", e o selo da chave lida ("Chave …4170").
const invoiceNumber = computed(() => invoiceNumberLabel(invoiceStatus.value.accessKey));
const invoiceKeyLabel = computed(() => invoiceKeyTail(invoiceStatus.value.accessKey));
const receiptDocumentTitle = computed(() =>
  [receiptSupplier.value?.displayName || receiptSupplier.value?.name || "", receiptMode.value === "invoice" ? invoiceNumber.value : "Sem NF"]
    .filter(Boolean)
    .join(" · "),
);

// Conta ITENS travados, não avisos: uma linha que precisa de insumo E de
// validade é um item para resolver, não dois bloqueios. O número tem de bater
// com o tamanho da lista logo abaixo dele, senão vira ruído — e com o que
// realmente segura o `Confirmar entrada`, inclusive a linha pronta que ninguém
// marcou como conferida.
const receiptTotalPending = computed(
  () =>
    receiptPendingLines.value.length +
    receiptDocumentBlockers.value.length +
    receiptSupplierBlockers.value.length +
    (receiptVolumesStep.value ? 1 : 0),
);
const purchaseTotalQ = computed(() =>
  reorderRows.value.reduce((total, row) => total + (row.estimatedCostQ ?? 0), 0),
);
const purchaseSupplierCount = computed(
  () => new Set(reorderRows.value.map((row) => row.supplier?.ref).filter(Boolean)).size,
);

type SupplierPortfolioRow = {
  cost: SupplierMaterialCost;
  material: Material;
  unitLabel: string;
  baseCostQ: number;
  approximate: boolean;
};

// Contato inativo continua no cadastro (historico), mas nao na tela de quem
// vai ligar hoje.
const activeSupplierContacts = computed(
  () => selectedSupplier.value?.contacts.filter((person) => person.isActive) ?? [],
);

const selectedSupplierPortfolio = computed(() => {
  if (!selectedSupplier.value) return [];
  return costs.value
    .filter((cost) => cost.supplierRef === selectedSupplier.value?.ref)
    .map((cost) => {
      const material = materials.value.find((item) => item.sku === cost.materialSku);
      if (!material) return null;
      return {
        cost,
        material,
        unitLabel: purchaseUnitLabel(cost, material, conversions.value),
        baseCostQ: costPerBaseUnitQ(cost, conversions.value),
        approximate: isApproximateCost(cost, conversions.value),
      };
    })
    .filter((row): row is SupplierPortfolioRow => Boolean(row));
});

const quoteDisabled = computed(() => !notePreview.value || !noteMaterialSku.value || !noteSupplierRef.value);
const scannerOpen = ref(false);
const scannerError = ref("");
const scannerHint = ref("");
const scannerCanTorch = ref(false);
const scannerTorchOn = ref(false);
const scannerVideo = ref<HTMLVideoElement | null>(null);
const scannerFileInput = ref<HTMLInputElement | null>(null);
let scannerControls: { stop: () => void; switchTorch?: (onOff: boolean) => Promise<void> } | null = null;
let scannerAccepted = false;

function openBase(tab: PurchaseBaseView) {
  baseView.value = tab;
  view.value = "base";
}

function openReceive(mode: ReceiptMode) {
  setReceiptMode(mode);
  view.value = "receive";
}

function selectMaterialAndView(material: EnrichedMaterial) {
  selectMaterial(material.sku);
  openBase("materials");
}

function openQuoteFor(material: EnrichedMaterial, supplierRef?: string) {
  selectMaterial(material.sku);
  noteMaterialSku.value = material.sku;
  if (supplierRef) noteSupplierRef.value = supplierRef;
  openBase("costs");
}

function onReceiptSupplierChange(event: Event) {
  setReceiptSupplier((event.target as HTMLSelectElement).value);
}

function stopInvoiceScanner(resetAccepted = true) {
  scannerControls?.stop();
  scannerControls = null;
  const source = scannerVideo.value?.srcObject;
  if (source && typeof (source as MediaStream).getTracks === "function") {
    (source as MediaStream).getTracks().forEach((track) => track.stop());
  }
  if (scannerVideo.value) scannerVideo.value.srcObject = null;
  scannerCanTorch.value = false;
  scannerTorchOn.value = false;
  if (resetAccepted) scannerAccepted = false;
  scannerOpen.value = false;
}

function invoiceVideoConstraints(): MediaStreamConstraints {
  return {
    audio: false,
    video: {
      facingMode: { ideal: "environment" },
      width: { ideal: 1920 },
      height: { ideal: 1080 },
    },
  };
}

async function createInvoiceCodeReader() {
  const [{ BrowserMultiFormatReader }, { BarcodeFormat, DecodeHintType }] = await Promise.all([
    import("@zxing/browser"),
    import("@zxing/library"),
  ]);
  const formats = [
    BarcodeFormat.QR_CODE,
    BarcodeFormat.CODE_128,
    BarcodeFormat.CODE_39,
    BarcodeFormat.CODE_93,
    BarcodeFormat.CODABAR,
    BarcodeFormat.EAN_13,
    BarcodeFormat.EAN_8,
    BarcodeFormat.ITF,
    BarcodeFormat.PDF_417,
    BarcodeFormat.DATA_MATRIX,
  ];
  const hints = new Map();
  hints.set(DecodeHintType.POSSIBLE_FORMATS, formats);
  hints.set(DecodeHintType.TRY_HARDER, true);
  return new BrowserMultiFormatReader(hints, {
    delayBetweenScanAttempts: 250,
    delayBetweenScanSuccess: 900,
    tryPlayVideoTimeout: 4500,
  });
}

async function acceptScannedInvoice(rawValue: string) {
  const value = rawValue.trim();
  if (!value || scannerAccepted) return;
  scannerAccepted = true;
  invoiceInput.value = value;
  stopInvoiceScanner(false);
  await readInvoice();
}

async function toggleScannerTorch() {
  if (!scannerControls?.switchTorch) return;
  const next = !scannerTorchOn.value;
  try {
    await scannerControls.switchTorch(next);
    scannerTorchOn.value = next;
  } catch {
    scannerCanTorch.value = false;
    scannerError.value = "Lanterna indisponível neste dispositivo. Use boa luz e mantenha o código inteiro no quadro.";
  }
}

async function openInvoiceScanner() {
  if (actionPending.value || scannerOpen.value) return;
  scannerError.value = "";
  scannerHint.value = "Abrindo câmera...";
  scannerAccepted = false;
  if (!import.meta.client || !navigator.mediaDevices?.getUserMedia) {
    scannerError.value = "Câmera indisponível neste navegador. Fotografe a nota, cole ou digite a chave da NF.";
    if (invoiceInput.value.trim()) await readInvoice();
    return;
  }
  scannerOpen.value = true;
  await nextTick();
  try {
    if (!scannerVideo.value) throw new Error("scanner_video_missing");
    const reader = await createInvoiceCodeReader();
    scannerHint.value = "Centralize o QR ou alinhe todo o código de barras dentro do quadro.";
    scannerControls = await reader.decodeFromConstraints(invoiceVideoConstraints(), scannerVideo.value, (result, _error, controls) => {
      scannerControls = controls;
      scannerCanTorch.value = Boolean(controls.switchTorch);
      const text = result?.getText();
      if (text) void acceptScannedInvoice(text);
    });
  } catch {
    scannerError.value = "Não consegui abrir a câmera para ler a NF. Fotografe a nota, cole ou digite a chave.";
    stopInvoiceScanner();
  }
}

function openInvoiceImagePicker() {
  scannerFileInput.value?.click();
}

async function readInvoiceImage(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file || actionPending.value) return;
  scannerError.value = "";
  try {
    const reader = await createInvoiceCodeReader();
    const url = URL.createObjectURL(file);
    try {
      const result = await reader.decodeFromImageUrl(url);
      await acceptScannedInvoice(result.getText());
    } finally {
      URL.revokeObjectURL(url);
    }
  } catch {
    scannerError.value = "Não consegui ler a foto. Use uma imagem nítida do QR/código de barras ou digite a chave.";
  }
}

// QUAL item está aberto na gaveta. Estado de TELA, e nao do recebimento — por
// isso vive aqui e nao na projection.
const openLineId = ref("");

const openPreview = computed(
  () => receiptLinePreviews.value.find((preview) => preview.line.id === openLineId.value) ?? null,
);

// A gaveta so esta aberta se o item ainda existe: apagar a linha de dentro dela
// deixaria uma gaveta vazia por cima da lista.
const lineSheetOpen = computed({
  get: () => Boolean(openPreview.value),
  set: (value: boolean) => {
    if (!value) openLineId.value = "";
  },
});

function openReceiptLine(lineId: string) {
  openLineId.value = lineId;
}

// Lançar um item à mão é pedir o formulário dele: a gaveta abre no item recém
// criado, e não numa linha vazia no fim da lista esperando um segundo toque.
async function addAndOpenReceiptLine() {
  addReceiptLine();
  await nextTick();
  const created = receiptRows.value.at(-1);
  if (created) openReceiptLine(created.id);
}

function removeOpenReceiptLine() {
  const lineId = openLineId.value;
  openLineId.value = "";
  removeReceiptLine(lineId);
}

function setReceiptLineChecked(lineId: string, checked: boolean) {
  updateReceiptLine(lineId, { checked });
}

// Os gestos da gaveta chegam sem o id: quem está aberto é estado da tela, e não
// da gaveta. Ela edita UM item — o que o operador tocou.
function onSheetUpdate(patch: Partial<ReceiptLine>) {
  if (openLineId.value) updateReceiptLine(openLineId.value, patch);
}

function onSheetSelectMaterial(sku: string) {
  if (openLineId.value) setReceiptLineMaterial(openLineId.value, sku);
}

function onSheetAcceptSuggestion() {
  if (openLineId.value) acceptReceiptLineSuggestion(openLineId.value);
}

function onSheetSelectConversion(conversionId: string | null) {
  if (openLineId.value) updateReceiptLine(openLineId.value, { conversionId });
}

function onSheetAcceptConversion() {
  if (openLineId.value) acceptReceiptLineConversion(openLineId.value);
}

function onSheetAcceptAxes() {
  if (openLineId.value) acceptReceiptLineInvoiceAxes(openLineId.value);
}

function onSheetDeclareConversion(input: { label: string; factor: string; kind: ConversionKind }) {
  if (openLineId.value) declareReceiptLineConversion(openLineId.value, input);
}

function onSheetCheck(checked: boolean) {
  if (openLineId.value) setReceiptLineChecked(openLineId.value, checked);
}

// Um aviso do MESMO tipo repetido em oito linhas vira oito pílulas iguais no
// painel: informação nenhuma, e afoga o que importa. Um por tipo basta.
const uniqueWatchWarnings = computed(() =>
  receiptWatchWarnings.value.filter(
    (warning, index, all) => all.findIndex((item) => item.key === warning.key) === index,
  ),
);

// O campo que a tela acabou de apontar, marcado por alguns segundos.
//
// Rolar até o campo resolve metade do problema: o operador chega lá e ainda
// precisa achar QUAL dos quatro campos do card é o que falta. O anel some
// sozinho — é um dedo apontando, não um estado do recebimento.
const flashedField = ref("");
let flashTimer: ReturnType<typeof setTimeout> | null = null;

function flashTarget(key: string) {
  flashedField.value = key;
  if (flashTimer) clearTimeout(flashTimer);
  flashTimer = setTimeout(() => {
    flashedField.value = "";
  }, 2600);
}

// O campo apontado dentro da gaveta que esta aberta AGORA. Se a tela apontou um
// campo de outro item, este nao pisca.
const sheetFlashField = computed<ReceiptFieldAnchor | null>(() => {
  const [lineId, field] = flashedField.value.split(":");
  if (!field || lineId !== openLineId.value) return null;
  return field as ReceiptFieldAnchor;
});

function anchorRing(anchor: ReceiptDocumentAnchor): string {
  return flashedField.value === anchor ? FLASH_RING : "";
}

// Salto, e não rolagem suave. O `behavior: "smooth"` é um PEDIDO: onde ele não
// roda — reduced-motion, webview, e o pane de automação onde isto foi medido —
// a chamada não faz nada e o campo continua fora da tela, que é exatamente a
// falha que esta frente veio corrigir. O anel âmbar dá a continuidade que a
// animação daria, e chega sempre.
const FOCUSABLE = "input:not([type=hidden]), select, textarea, button";

function revealTarget(target: HTMLElement, key: string, block: ScrollLogicalPosition = "center") {
  target.scrollIntoView({ behavior: "auto", block });
  // O alvo as vezes E o controle — o "Marcar como conferido" da gaveta e um
  // botao, e nao um card com um campo dentro. Procurar so para dentro deixava
  // justamente essa pendencia sem foco.
  const control = target.matches(FOCUSABLE) ? target : target.querySelector<HTMLElement>(FOCUSABLE);
  control?.focus({ preventScroll: true });
  flashTarget(key);
}

// Clicar na pendência leva ao item — numa nota de dez linhas, achar "aquele
// que falta a validade" rolando a lista é o trabalho que a tela devia poupar.
// Com a âncora do campo, leva ao CAMPO: a gaveta do item abre, a tela rola até
// ele e o cursor já pousa dentro.
//
// ⚠️ A espera não é decoração. A gaveta monta num portal, no fim do `<body>`,
// e um `nextTick` sozinho devolve `null`: quem clicasse na pendência não veria
// nada acontecer. `waitForElement` espera o campo existir, por poucos quadros.
async function focusReceiptLine(lineId: string, field: ReceiptFieldAnchor | null = null) {
  openReceiptLine(lineId);
  await nextTick();
  const target = await waitForElement(receiptFieldSelector(lineId, field));
  if (!target) return;
  revealTarget(target, field ? `${lineId}:${field}` : lineId);
}

// Recebimento por exceção: o que a conferência do topo pede, ela mesma grava.
function onExceptionCount(counted: number | null) {
  setReceiptVolumesCounted(counted);
}

function onExceptionExpiry(lineId: string, date: string) {
  updateReceiptLine(lineId, { expiryDate: date });
}

function focusReceiptAnchor(anchor: ReceiptDocumentAnchor) {
  const target = document.querySelector<HTMLElement>(`[data-receipt-anchor="${anchor}"]`);
  if (target) revealTarget(target, anchor);
}

/**
 * O que o `Confirmar entrada` responde quando ainda não dá para confirmar.
 *
 * O botão cinza era o pior aviso possível: o operador aperta, nada acontece, e
 * a explicação está no rodapé de uma página longa. Agora o botão sempre
 * responde — diz o gesto que falta, em cima da tela, e leva até o campo.
 */
function reportReceiptBlocker(blocker: ReceiptBlocker) {
  const goThere = () => {
    if (blocker.scope === "line") void focusReceiptLine(blocker.lineId, blocker.field);
    else if (blocker.anchor) focusReceiptAnchor(blocker.anchor);
  };
  // O aviso leva na hora; o botão do aviso continua levando depois, para quem
  // rolou para outro lugar antes de ler.
  useSonner.error(blocker.step, {
    description: blocker.label || undefined,
    action: { label: "Ir até lá", onClick: goThere },
  });
  goThere();
}

async function onConfirmReceipt() {
  const blocker = receiptFirstBlocker.value;
  if (blocker) {
    reportReceiptBlocker(blocker);
    return;
  }
  if (await confirmReceipt()) await revealReceiptOutcome();
}

async function onRejectReceipt() {
  if (await rejectReceipt()) await revealReceiptOutcome();
}

// Deu certo: a tela volta ao topo. O aviso de sucesso mora lá, e logo abaixo
// dele está o "Escanear NF" — quem acabou de dar entrada numa nota quase sempre
// tem a próxima na mão. Quem não tem, tem a navegação.
//
// Duas escolhas medidas, não superstição:
//
// - **Os dois quadros de espera.** Confirmar esvazia o rascunho, e a página
//   encolhe DEPOIS do render (de 3.855px para 1.677px na medição). Rolar antes
//   disso é rolar num documento que já não existe.
// - **Salto, não rolagem suave.** Enquanto a altura muda, a âncora de rolagem
//   do browser corrige o `scrollTop` para manter o que está à vista — e essa
//   correção atropela a animação: o `behavior: "smooth"` saía de 697px e
//   terminava em 818px, mais longe do topo do que começou.
async function revealReceiptOutcome() {
  await nextTick();
  await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
  window.scrollTo({ top: 0, behavior: "auto" });
}

// O convite fala da entrada que ACABOU de acontecer: quem deu baixa numa NF tem
// a próxima nota na mão; quem lançou sem NF tem o próximo romaneio. Oferecer
// "escanear NF" a quem acabou de conferir um romaneio de produtor é oferecer a
// ferramenta errada.
function startNextReceipt() {
  const manual = receiptOutcome.value?.mode === "manual";
  dismissReceiptOutcome();
  if (!manual) {
    void openInvoiceScanner();
    return;
  }
  setReceiptMode("manual");
  addReceiptLine();
}

onBeforeUnmount(() => {
  if (flashTimer) clearTimeout(flashTimer);
});

function stockAfterReceipt(sku: string): number {
  const material = materials.value.find((item) => item.sku === sku);
  const incomingQty = receiptLinePreviews.value
    .filter((item) => item.material.sku === sku && item.baseQtyKnown)
    .reduce((total, item) => total + item.baseQty, 0);
  return (material?.stockOnHand ?? 0) + incomingQty;
}

// ── Cabeçalho de uma linha (camada visual da suíte) ─────────────────────────
const isPhone = useMediaQuery("(max-width: 767.98px)");
const VIEW_TITLES = { panel: "Painel", buy: "Comprar", receive: "Receber", base: "Base" } as const;
// Celular com uma entrada aberta: a barra de 56px fala do documento, como a prévia v4
// ("Alto Alegre" e, acima, "NF 12.884 · R$ 2.416,80"). Sem entrada, o nome da seção.
const phoneReceiptHeader = computed(() => isPhone.value && view.value === "receive" && !receiptIsBlank.value && Boolean(receiptSupplier.value));
const pageTitle = computed(() =>
  phoneReceiptHeader.value ? receiptSupplier.value?.displayName || receiptSupplier.value?.name || VIEW_TITLES.receive : VIEW_TITLES[view.value],
);
const pageEyebrow = computed(() => {
  if (!phoneReceiptHeader.value) return "";
  return [receiptMode.value === "invoice" ? invoiceNumber.value : "Sem NF", formatMoney(receiptTotalCostQ.value)].filter(Boolean).join(" · ");
});

// Com a NF lida e o fornecedor certo, o bloco de leitura recolhe numa linha (prévias
// v3/v4: a conferência é a tela; o documento vira cabeçalho). "Trocar NF" reabre.
const docExpanded = ref(false);
const docCompact = computed(
  () =>
    receiptMode.value === "invoice" &&
    invoiceStatus.value.valid &&
    receiptLinePreviews.value.length > 0 &&
    Boolean(receiptSupplierRef.value) &&
    !docExpanded.value,
);
watch(
  () => invoiceStatus.value.accessKey,
  () => {
    docExpanded.value = false;
  },
);

// A hora da última leitura útil da base. O Compras não tem SSE: a leitura acontece ao
// abrir e em Atualizar, e o ponto diz isso sem fingir ao vivo quando a leitura falha.
const readAt = ref("");
watch(
  [pending, backendReady],
  ([isPending, ready]) => {
    if (!isPending && ready) {
      readAt.value = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    }
  },
  { immediate: true },
);
const liveTone = computed(() => (readonlyFallback.value ? "off" : pending.value ? "calm" : "live"));
const liveLabel = computed(() =>
  readonlyFallback.value ? "Sem leitura" : pending.value ? "Lendo" : "Lido",
);

// Base: a busca do cabeçalho filtra o cadastro aberto (insumos e contagem pelo nome ou
// SKU, custos na tabela do fornecedor). Fornecedores não têm busca.
const baseSearch = computed({
  get: () => (baseView.value === "costs" ? batchQuery.value : query.value),
  set: (value: string) => {
    if (baseView.value === "costs") batchQuery.value = value;
    else query.value = value;
  },
});
const baseSearchPlaceholder = computed(() =>
  baseView.value === "costs" ? "Buscar insumo na tabela" : "Buscar insumo ou SKU",
);
const attentionCount = computed(() => enrichedMaterials.value.filter((material) => material.tone !== "ok").length);
const baseTabCount = computed<Partial<Record<PurchaseBaseView, number>>>(() => ({
  materials: metrics.value.activeMaterials,
  suppliers: suppliers.value.length,
}));

const searchInput = ref<{ focus: () => void } | null>(null);
function onKeydown(event: KeyboardEvent) {
  if (event.key !== "/" || view.value !== "base" || baseView.value === "suppliers") return;
  const target = event.target as HTMLElement | null;
  if (target?.closest("input, textarea, select, [contenteditable=true]")) return;
  event.preventDefault();
  searchInput.value?.focus();
}
onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));

// Painel: "Precisa de você" mostra o que pede gesto agora; o resto vira contagem.
// "Digitar chave": abre o Receber com o cursor já no campo da chave.
function openReceiveTyping() {
  openReceive("invoice");
  void focusInvoiceField();
}

async function focusInvoiceField() {
  await nextTick();
  const field = await waitForElement('[data-receipt-anchor="invoice"] textarea');
  (field as HTMLTextAreaElement | null)?.focus();
}

function openCostsMissing() {
  batchOnlyMissing.value = true;
  openBase("costs");
}

onBeforeUnmount(stopInvoiceScanner);
</script>

<template>
  <main class="flex min-w-0 flex-1 flex-col">
    <!-- Cabeçalho de uma linha (kit, prévias v3/v4): título, leitura, busca e controles;
         recortes na segunda linha. No celular, a barra de 56px com o selo, a lupa e o
         sino. Fica preso no topo enquanto a tela rola. -->
    <div class="sticky top-0 z-30">
      <OperatorPageHeader :title="pageTitle" :eyebrow="pageEyebrow">
        <template #status>
          <OperatorLiveStatus
            :tone="liveTone"
            :time="readAt"
            :label="liveLabel"
            :detail="readonlyFallback ? backendBlockTitle : 'Última leitura da base de compras. Atualizar lê de novo.'"
          />
          <!-- Receber: o documento da entrada aberta, ao lado do título. -->
          <div
            v-if="view === 'receive' && !receiptIsBlank && !isPhone"
            class="flex min-w-0 items-center gap-3 border-l border-border pl-3"
            data-receipt-document
          >
            <div class="min-w-0">
              <p class="truncate op-title leading-tight">{{ receiptDocumentTitle || "Entrada em conferência" }}</p>
              <p class="truncate op-micro text-muted-foreground tnum">
                <template v-if="receiptSupplier?.document">{{ receiptSupplier.document }} · </template>{{ receiptSupplier?.paymentTerm || "prazo a combinar" }} · {{ formatMoney(receiptTotalCostQ) }}
              </p>
            </div>
          </div>
          <!-- Base: os quatro cadastros num controle segmentado (no celular, na linha
               dos recortes). -->
          <nav
            v-if="view === 'base' && !isPhone"
            class="inline-flex h-control shrink-0 items-center gap-1 rounded-md bg-secondary p-1"
            aria-label="Cadastros da Base"
          >
            <button
              v-for="tab in baseTabs"
              :key="tab.key"
              type="button"
              class="inline-flex h-full items-center gap-1.5 rounded px-3 op-label transition"
              :class="baseView === tab.key ? 'bg-card font-semibold shadow-sm' : 'text-muted-foreground hover:bg-card/60'"
              :aria-current="baseView === tab.key ? 'page' : undefined"
              @click="baseView = tab.key"
            >
              <Icon :name="tab.icon" class="size-4" />
              {{ tab.label }}
              <span v-if="baseTabCount[tab.key]" class="font-normal text-muted-foreground tnum">{{ baseTabCount[tab.key] }}</span>
            </button>
          </nav>
        </template>

        <template v-if="view === 'base' && baseView !== 'suppliers'" #search>
          <OperatorSuiteSearch
            ref="searchInput"
            v-model="baseSearch"
            screen-label="filtrando a base"
            :placeholder="baseSearchPlaceholder"
            :aria-label="baseSearchPlaceholder"
          />
        </template>

        <template #phone-actions>
          <button
            type="button"
            class="grid size-12 place-items-center rounded-md text-foreground"
            aria-label="Atualizar"
            @click="refresh()"
          >
            <Icon name="lucide:refresh-cw" class="size-5" :class="pending ? 'animate-spin' : ''" />
          </button>
          <PurchasePhoneBell />
        </template>

        <!-- No celular só o Receber tem controles na linha de baixo (Com NF / Sem NF);
             Atualizar sobe para a barra de 56px. -->
        <template v-if="!isPhone || view === 'receive'" #actions>
          <!-- Receber: o selo da chave lida e o par Com NF / Sem NF. -->
          <template v-if="view === 'receive'">
            <span
              v-if="receiptMode === 'invoice' && invoiceStatus.valid && !isPhone"
              class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full px-3 op-label font-semibold pill-success tnum"
            >
              <Icon name="lucide:check" class="size-4" />
              {{ invoiceKeyLabel }}
            </span>
            <div class="inline-flex h-control shrink-0 items-center gap-1 rounded-md bg-secondary p-1" role="group" aria-label="Origem da entrada">
              <button type="button" class="inline-flex h-full items-center gap-1.5 rounded px-3 op-label transition" :class="receiptMode === 'invoice' ? 'bg-card font-semibold shadow-sm' : 'text-muted-foreground hover:bg-card/60'" :aria-pressed="receiptMode === 'invoice'" @click="setReceiptMode('invoice')">
                <Icon name="lucide:scan-line" class="size-4" />
                Com NF
              </button>
              <button type="button" class="inline-flex h-full items-center gap-1.5 rounded px-3 op-label transition" :class="receiptMode === 'manual' ? 'bg-card font-semibold shadow-sm' : 'text-muted-foreground hover:bg-card/60'" :aria-pressed="receiptMode === 'manual'" @click="setReceiptMode('manual')">
                <Icon name="lucide:clipboard-pen-line" class="size-4" />
                Sem NF
              </button>
            </div>
          </template>
          <span v-if="view === 'buy'" class="inline-flex h-8 shrink-0 items-center rounded-full px-3 op-label pill-muted tnum">
            {{ purchaseSupplierCount }} {{ purchaseSupplierCount === 1 ? "fornecedor" : "fornecedores" }}
          </span>
          <UiIconButton v-if="!isPhone" icon="lucide:refresh-cw" label="Atualizar" :spinning="pending" @click="refresh()" />
        </template>

        <!-- Base: Atenção e as métricas de Compras hoje; cada uma leva ao recorte. -->
        <template v-if="view === 'base'" #filters>
          <nav
            v-if="isPhone"
            class="inline-flex h-control shrink-0 items-center gap-1 rounded-md bg-secondary p-1"
            aria-label="Cadastros da Base"
          >
            <button
              v-for="tab in baseTabs"
              :key="tab.key"
              type="button"
              class="inline-flex h-full shrink-0 items-center gap-1.5 rounded px-3 op-label transition"
              :class="baseView === tab.key ? 'bg-card font-semibold shadow-sm' : 'text-muted-foreground'"
              :aria-current="baseView === tab.key ? 'page' : undefined"
              @click="baseView = tab.key"
            >
              <Icon :name="tab.icon" class="size-4" />
              {{ tab.label }}
            </button>
          </nav>
          <template v-if="baseView === 'materials'">
            <UiFilterChip :active="onlyAlerts" :count="attentionCount" :aria-pressed="onlyAlerts" @click="onlyAlerts = !onlyAlerts">
              <template #icon><Icon name="lucide:triangle-alert" class="size-4 text-warning" /></template>
              Atenção
            </UiFilterChip>
            <span class="mx-1 h-6 w-px shrink-0 bg-border" aria-hidden="true" />
          </template>
          <span class="mr-1 shrink-0 op-eyebrow text-muted-foreground">Compras hoje</span>
          <UiFilterChip @click="view = 'buy'">
            <template #icon><Icon name="lucide:triangle-alert" class="size-4 text-warning" /></template>
            <span class="font-semibold tnum">{{ metrics.urgentMaterials }}</span>
            {{ metrics.urgentMaterials === 1 ? "reposição urgente" : "reposições urgentes" }}
          </UiFilterChip>
          <UiFilterChip :active="baseView === 'costs' && batchOnlyMissing" @click="openCostsMissing">
            <template #icon><Icon name="lucide:badge-alert" class="size-4 text-info" /></template>
            <span class="font-semibold tnum">{{ metrics.missingPreferred }}</span>
            sem fornecedor preferencial
          </UiFilterChip>
          <UiFilterChip @click="openBase('costs')">
            <template #icon><Icon name="lucide:equal-approximately" class="size-4 text-muted-foreground" /></template>
            <span class="font-semibold tnum">{{ metrics.approximatePreferred }}</span>
            {{ metrics.approximatePreferred === 1 ? "custo estimado" : "custos estimados" }}
          </UiFilterChip>
          <span class="ml-auto hidden shrink-0 op-micro text-muted-foreground 2xl:inline">Base: referências usadas pelos fluxos de comprar e receber.</span>
        </template>
      </OperatorPageHeader>
    </div>

    <div class="flex min-w-0 flex-1 flex-col gap-4 p-3 md:p-4" :class="view === 'base' && baseView === 'materials' ? 'xl:p-0' : ''">
      <section
        v-if="(pending && !backendReady) || readonlyFallback || actionError"
        class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card px-3 py-2 op-body"
        :class="view === 'base' && baseView === 'materials' ? 'xl:mx-4 xl:mt-3' : ''"
        aria-live="polite"
      >
        <span v-if="pending && !backendReady" class="inline-flex items-center gap-2 text-muted-foreground">
          <Icon name="lucide:loader-circle" class="size-4 animate-spin" />
          Conectando ao Core de compras
        </span>
        <span v-else-if="readonlyFallback" class="inline-flex items-center gap-2 text-warning">
          <Icon name="lucide:wifi-off" class="size-4" />
          {{ backendBlockTitle }}
        </span>
        <span v-else class="inline-flex items-center gap-2 text-destructive">
          <Icon name="lucide:triangle-alert" class="size-4" />
          {{ actionError }}
        </span>
        <button type="button" class="min-h-control rounded-md border border-border bg-card px-3 op-label hover:bg-accent" @click="refresh()">
          Atualizar
        </button>
      </section>

      <section
        v-if="readonlyFallback"
        class="rounded-lg border border-warning/35 bg-warning/10 p-4 text-warning"
        :class="view === 'base' && baseView === 'materials' ? 'xl:mx-4' : ''"
        aria-live="polite"
      >
        <div class="flex items-start gap-3">
          <Icon name="lucide:shield-alert" class="mt-0.5 size-5 shrink-0" />
          <div>
            <h2 class="op-title">{{ backendBlockTitle }}</h2>
            <p class="mt-1 op-body">{{ backendBlockMessage }}</p>
          </div>
        </div>
      </section>

      <!-- ══ PAINEL ══════════════════════════════════════════════════════════ -->
      <section v-if="view === 'panel'" class="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div class="min-w-0 space-y-4">
          <section class="grid grid-cols-2 gap-3 xl:grid-cols-4" aria-label="Painel de compras">
            <button type="button" class="rounded-xl border border-border bg-card p-4 text-left transition hover:bg-accent" @click="view = 'buy'">
              <p class="flex items-center gap-2 op-eyebrow text-muted-foreground">
                <Icon name="lucide:shopping-cart" class="size-4 text-warning" />
                Comprar
              </p>
              <p class="mt-2 op-display tnum">{{ reorderRows.length }}</p>
              <p class="op-micro text-muted-foreground">{{ formatMoney(purchaseTotalQ) }} estimados</p>
            </button>
            <button type="button" class="rounded-xl border border-border bg-card p-4 text-left transition hover:bg-accent" @click="view = 'receive'">
              <p class="flex items-center gap-2 op-eyebrow text-muted-foreground">
                <Icon name="lucide:package-check" class="size-4 text-success" />
                Receber
              </p>
              <p class="mt-2 op-display tnum">{{ receiptConference.ready }}/{{ receiptConference.total }}</p>
              <p class="op-micro text-muted-foreground">{{ receiptTotalPending }} {{ receiptTotalPending === 1 ? "pendência" : "pendências" }}</p>
            </button>
            <button type="button" class="rounded-xl border border-border bg-card p-4 text-left transition hover:bg-accent" @click="openBase('costs')">
              <p class="flex items-center gap-2 op-eyebrow text-muted-foreground">
                <Icon name="lucide:equal-approximately" class="size-4 text-info" />
                Conversões
              </p>
              <p class="mt-2 op-display tnum">{{ metrics.approximatePreferred }}</p>
              <p class="op-micro text-muted-foreground">custos estimados</p>
            </button>
            <button type="button" class="rounded-xl border border-border bg-card p-4 text-left transition hover:bg-accent" @click="openBase('materials')">
              <p class="flex items-center gap-2 op-eyebrow text-muted-foreground">
                <Icon name="lucide:database" class="size-4" />
                Base
              </p>
              <p class="mt-2 op-display tnum">{{ metrics.activeMaterials }}</p>
              <p class="op-micro text-muted-foreground">{{ metrics.missingPreferred }} sem custo preferencial</p>
            </button>
          </section>

          <section class="overflow-hidden rounded-xl border border-border bg-card">
            <div class="flex items-baseline justify-between gap-3 border-b border-border px-4 py-3">
              <h2 class="op-title">Precisa de você</h2>
              <p class="op-micro text-muted-foreground">Fila de decisão operacional</p>
            </div>
            <div class="divide-y divide-border">
              <!-- A fila de decisão vazia tem de dizer o motivo aqui, onde o
                   operador olha primeiro — não só na tela Comprar. -->
              <div
                v-for="blocker in (reorderRows.length ? [] : reorderBlockers)"
                :key="`panel-blocker-${blocker.key}`"
                class="flex items-start gap-3 p-4"
              >
                <Icon
                  :name="blocker.key === 'stocked' ? 'lucide:circle-check' : 'lucide:info'"
                  class="mt-0.5 size-5 shrink-0"
                  :class="blocker.key === 'stocked' ? 'text-success' : 'text-info'"
                />
                <div class="min-w-0">
                  <p class="op-title">{{ blocker.headline }}</p>
                  <p class="mt-0.5 op-body text-muted-foreground">{{ blocker.detail }}</p>
                  <button
                    v-if="blocker.action"
                    type="button"
                    class="mt-2 inline-flex min-h-control items-center gap-1.5 rounded-md border border-border bg-card px-3 op-label hover:bg-accent"
                    @click="openBase(blocker.action.baseView)"
                  >
                    <Icon name="lucide:arrow-right" class="size-4" />
                    {{ blocker.action.label }}
                  </button>
                </div>
              </div>
              <button
                v-for="row in reorderRows.slice(0, 5)"
                :key="`panel-buy-${row.material.sku}`"
                type="button"
                class="flex min-h-16 w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-accent"
                @click="view = 'buy'"
              >
                <span class="min-w-0">
                  <span class="block truncate op-title">{{ row.material.name }}</span>
                  <span class="block op-micro text-muted-foreground">
                    {{ coverageLabel(row.material.coverageDays) }} · sugerir {{ purchaseSuggestionLabel(row.material, row.suggestedQty) }}
                  </span>
                </span>
                <span class="inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full px-2 op-micro font-semibold pill-warning">
                  <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />
                  Comprar
                </span>
              </button>
              <button type="button" class="flex min-h-16 w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-accent" @click="view = 'receive'">
                <span class="min-w-0">
                  <span class="block op-title">Recebimento em conferência</span>
                  <span class="block truncate op-micro text-muted-foreground">{{ receiptConference.label }}</span>
                </span>
                <span class="inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full px-2 op-micro font-semibold" :class="receiptReady ? 'pill-success' : 'pill-warning'">
                  <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />
                  {{ receiptReady ? "Pronto" : "Revisar" }}
                </span>
              </button>
              <button
                v-for="item in integrityQueue.slice(0, 4)"
                :key="`panel-integrity-${item.material.sku}-${item.issue.key}`"
                type="button"
                class="flex min-h-16 w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-accent"
                @click="selectMaterialAndView(item.material)"
              >
                <span class="min-w-0">
                  <span class="block truncate op-title">{{ item.material.name }}</span>
                  <span class="block truncate op-micro text-muted-foreground">{{ item.issue.label }}</span>
                </span>
                <span class="inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full px-2 op-micro font-semibold" :class="tonePills[item.issue.tone]">
                  <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />
                  {{ toneLabels[item.issue.tone] }}
                </span>
              </button>
            </div>
          </section>
        </div>

        <!-- O que se FAZ, no alcance do polegar (prévia `purchase-receive-phone3.html`):
             Escanear NF grande; Digitar chave e Sem NF ao lado. -->
        <aside class="space-y-3">
          <button type="button" class="flex w-full flex-col items-center justify-center gap-2 rounded-2xl bg-primary px-4 py-6 text-center text-primary-foreground shadow-sm transition hover:opacity-95" @click="openReceive('invoice')">
            <span class="grid size-14 place-items-center rounded-full bg-primary-foreground/15">
              <Icon name="lucide:scan-line" class="size-7" />
            </span>
            <span class="text-[22px] leading-tight font-semibold">Escanear NF</span>
            <span class="op-label text-primary-foreground/80">QR ou código de barras do DANFE</span>
          </button>
          <div class="grid grid-cols-2 gap-3">
            <button type="button" class="flex h-14 items-center justify-center gap-2 rounded-xl border border-border bg-card px-3 op-title hover:bg-accent" @click="openReceiveTyping">
              <Icon name="lucide:keyboard" class="size-5" />
              Digitar chave
            </button>
            <button type="button" class="flex h-14 items-center justify-center gap-2 rounded-xl border border-border bg-card px-3 op-title hover:bg-accent" @click="openReceive('manual')">
              <Icon name="lucide:clipboard-pen-line" class="size-5" />
              Sem NF
            </button>
          </div>
          <button type="button" class="flex h-14 w-full items-center gap-3 rounded-xl border border-border bg-card px-4 text-left op-title hover:bg-accent" @click="view = 'buy'">
            <Icon name="lucide:shopping-cart" class="size-5" />
            Revisar compras
          </button>
          <button type="button" class="flex h-14 w-full items-center gap-3 rounded-xl border border-border bg-card px-4 text-left op-title hover:bg-accent" @click="openBase('materials')">
            <Icon name="lucide:database" class="size-5" />
            Consultar Base
          </button>
        </aside>
      </section>

      <!-- ══ COMPRAR ═════════════════════════════════════════════════════════ -->
      <section v-else-if="view === 'buy'" class="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <section class="min-w-0">
          <p class="mb-3 op-body text-muted-foreground">Solicitações consolidadas por estoque, produção e operação.</p>

          <!-- Zero explicado: sem isto, "não precisa comprar nada" e "o app não
               consegue calcular" são a mesma tela vazia. -->
          <div v-if="!reorderRows.length && reorderBlockers.length" class="space-y-3">
            <div
              v-for="blocker in reorderBlockers"
              :key="`buy-blocker-${blocker.key}`"
              class="rounded-xl border border-border bg-card p-4"
            >
              <div class="flex items-start gap-3">
                <Icon
                  :name="blocker.key === 'stocked' ? 'lucide:circle-check' : 'lucide:info'"
                  class="mt-0.5 size-5 shrink-0"
                  :class="blocker.key === 'stocked' ? 'text-success' : 'text-info'"
                />
                <div class="min-w-0">
                  <h2 class="op-title">{{ blocker.headline }}</h2>
                  <p class="mt-0.5 op-body text-muted-foreground">{{ blocker.detail }}</p>
                  <button
                    v-if="blocker.action"
                    type="button"
                    class="mt-3 inline-flex min-h-control items-center gap-1.5 rounded-md border border-border bg-card px-3 op-label hover:bg-accent"
                    @click="openBase(blocker.action.baseView)"
                  >
                    <Icon name="lucide:arrow-right" class="size-4" />
                    {{ blocker.action.label }}
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div v-else class="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
            <article v-for="row in reorderRows" :key="row.material.sku" class="flex flex-col rounded-xl border border-border bg-card p-4">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <h2 class="truncate op-title">{{ row.material.name }}</h2>
                  <p class="truncate op-micro text-muted-foreground"><span class="font-mono">{{ row.material.sku }}</span> · {{ row.material.category }}</p>
                </div>
                <span class="inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full border-0 px-2 op-micro font-semibold" :class="requestStatusClasses[purchaseRequestStatus(row.material.sku)]">
                  <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />
                  {{ requestStatusLabels[purchaseRequestStatus(row.material.sku)] }}
                </span>
              </div>
            <dl class="mt-4 grid grid-cols-2 gap-3 text-sm">
              <div class="col-span-2"><dt class="text-xs text-muted-foreground">Cobertura</dt><dd class="font-semibold tabular-nums">{{ coverageLabel(row.material.coverageDays) }}</dd></div>
              <div class="col-span-2"><dt class="text-xs text-muted-foreground">Sugestão</dt><dd class="font-semibold tabular-nums">{{ purchaseSuggestionLabel(row.material, row.suggestedQty) }}</dd></div>
              <div><dt class="text-xs text-muted-foreground">Fornecedor</dt><dd class="truncate font-semibold">{{ row.supplier?.name || "Definir" }}</dd></div>
              <div><dt class="text-xs text-muted-foreground">Estimado</dt><dd class="font-semibold tabular-nums">{{ formatMoney(row.estimatedCostQ) }}</dd></div>
            </dl>
            <div class="mt-4 grid grid-cols-2 gap-2">
              <button type="button" class="h-10 rounded-md border border-border px-3 text-sm font-medium hover:bg-accent" @click="openQuoteFor(row.material, row.supplier?.ref)">Lançar custo</button>
              <button type="button" class="h-10 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-50" :disabled="readonlyFallback || purchaseRequestStatus(row.material.sku) === 'sent' || actionPending" @click="sendPurchaseRequest(row.material.sku)">
                {{ purchaseRequestStatus(row.material.sku) === "sent" ? "Enviado" : "Enviar pedido" }}
              </button>
            </div>
            </article>
          </div>
        </section>

        <aside class="h-fit rounded-xl border border-border bg-card p-4">
          <p class="op-eyebrow text-muted-foreground">Consolidação</p>
          <dl class="mt-3 grid grid-cols-2 gap-3">
            <div><dt class="op-micro text-muted-foreground">Solicitações</dt><dd class="op-figure">{{ reorderRows.length }}</dd></div>
            <div><dt class="op-micro text-muted-foreground">Fornecedores</dt><dd class="op-figure">{{ purchaseSupplierCount }}</dd></div>
            <div class="col-span-2"><dt class="op-micro text-muted-foreground">Total previsto</dt><dd class="op-figure">{{ formatMoney(purchaseTotalQ) }}</dd></div>
          </dl>
          <div class="mt-4 space-y-2">
            <button type="button" class="flex min-h-control w-full items-center justify-center gap-2 rounded-md border border-border bg-card px-3 op-label hover:bg-accent" @click="openBase('suppliers')">
              <Icon name="lucide:truck" class="size-4" />
              Fornecedores
            </button>
            <button type="button" class="flex min-h-control w-full items-center justify-center gap-2 rounded-md border border-border bg-card px-3 op-label hover:bg-accent" @click="openBase('costs')">
              <Icon name="lucide:calculator" class="size-4" />
              Custos e conversões
            </button>
          </div>
        </aside>
      </section>

      <!-- ══ RECEBER ═════════════════════════════════════════════════════════ -->
      <section v-else-if="view === 'receive'" class="grid min-h-0 grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <div class="min-w-0 space-y-4">
          <!-- Deu certo, e a tela diz isso onde o olho está: no topo, do tamanho
               do que aconteceu, com o que entrou escrito por extenso. O gesto
               seguinte fica dentro do próprio aviso — quem deu entrada numa nota
               quase sempre tem a próxima na mão. -->
          <section
            v-if="receiptOutcome"
            data-receipt-outcome
            class="scroll-mt-4 rounded-2xl border p-4"
            :class="receiptOutcome.kind === 'confirmed' ? 'border-success/40 bg-success/10' : 'border-warning/40 bg-warning/10'"
            aria-live="polite"
          >
            <div class="flex items-start gap-3">
              <span
                class="grid size-11 shrink-0 place-items-center rounded-full text-white"
                :class="receiptOutcome.kind === 'confirmed' ? 'bg-success' : 'bg-warning'"
              >
                <Icon :name="receiptOutcome.kind === 'confirmed' ? 'lucide:check-check' : 'lucide:undo-2'" class="size-6" />
              </span>
              <div class="min-w-0 flex-1">
                <h2 class="text-[19px] leading-snug font-semibold" :class="receiptOutcome.kind === 'confirmed' ? 'text-success' : 'text-warning'">
                  {{ receiptOutcome.kind === "confirmed" ? "Entrada confirmada no estoque" : "Devolução registrada" }}
                </h2>
                <p class="mt-1 op-body text-foreground">{{ receiptOutcomeSummary(receiptOutcome) }}</p>
                <p class="mt-0.5 op-micro text-muted-foreground">{{ receiptOutcome.at }}</p>
                <div class="mt-3 flex flex-col gap-2 sm:flex-row">
                  <button type="button" class="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-primary px-4 op-title text-primary-foreground disabled:opacity-50" :disabled="readonlyFallback || actionPending" @click="startNextReceipt">
                    <Icon :name="receiptOutcome.mode === 'manual' ? 'lucide:clipboard-pen-line' : 'lucide:scan-line'" class="size-5" />
                    {{ receiptOutcome.mode === "manual" ? "Lançar outra entrada" : "Escanear outra NF" }}
                  </button>
                  <button type="button" class="inline-flex h-12 items-center justify-center gap-2 rounded-xl border border-border bg-card px-4 op-title hover:bg-accent" @click="dismissReceiptOutcome">
                    <Icon name="lucide:x" class="size-5" />
                    Fechar
                  </button>
                </div>
              </div>
            </div>
          </section>

          <section v-if="docCompact" class="flex items-center gap-3 rounded-xl border border-success/30 bg-card px-4 py-3" data-receipt-document-compact>
            <span class="grid size-10 shrink-0 place-items-center rounded-full pill-success">
              <Icon name="lucide:file-check-2" class="size-5" />
            </span>
            <div class="min-w-0 flex-1">
              <p class="truncate op-title">{{ receiptDocumentTitle }}</p>
              <p class="truncate op-micro text-muted-foreground tnum">
                <template v-if="receiptSupplier?.document">{{ receiptSupplier.document }} · </template>{{ invoiceKeyLabel }} · {{ receiptSupplier?.paymentTerm || "prazo a combinar" }}
              </p>
            </div>
            <button type="button" class="inline-flex min-h-control shrink-0 items-center gap-1.5 rounded-xl border border-border bg-card px-3 op-label font-semibold hover:bg-accent" @click="docExpanded = true">
              <Icon name="lucide:scan-line" class="size-4" />
              Trocar NF
            </button>
          </section>

          <section v-else class="rounded-xl border border-border bg-card p-4">
            <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
              <div class="space-y-3">
                <!-- Prévia v3 (celular): começar pela câmera. O que se faz é grande e
                     fica no polegar; digitar a chave e a foto ficam ao lado. -->
                <button v-if="receiptMode === 'invoice'" type="button" class="flex w-full items-center gap-4 rounded-2xl bg-primary px-4 py-4 text-left text-primary-foreground shadow-sm disabled:opacity-50" :disabled="readonlyFallback || actionPending || scannerOpen" @click="openInvoiceScanner">
                  <span class="grid size-12 shrink-0 place-items-center rounded-full bg-primary-foreground/15">
                    <Icon :name="actionPending ? 'lucide:loader-circle' : 'lucide:scan-line'" class="size-6" :class="actionPending ? 'animate-spin' : ''" />
                  </span>
                  <span class="min-w-0">
                    <span class="block text-[20px] leading-tight font-semibold">{{ actionPending ? "Lendo NF" : "Escanear NF" }}</span>
                    <span class="block op-label text-primary-foreground/80">QR ou código de barras do DANFE</span>
                  </span>
                </button>
                <p v-if="scannerError" class="rounded-lg border border-warning/35 bg-warning/10 p-3 op-body text-warning">
                  {{ scannerError }}
                </p>
                <label v-if="receiptMode === 'invoice'" data-receipt-anchor="invoice" class="block scroll-mt-4 rounded-md p-0.5 op-label transition-shadow" :class="anchorRing('invoice')">
                  QR, código de barras ou chave da NF
                  <textarea v-model="invoiceInput" rows="2" class="mt-1 w-full resize-none rounded-lg border border-input bg-card px-3 py-2 op-body tnum" placeholder="Escaneie, cole ou digite a chave de acesso" />
                </label>
                <div v-if="receiptMode === 'invoice'" class="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    class="inline-flex h-12 items-center justify-center gap-2 rounded-xl border border-border bg-card px-3 op-title hover:bg-accent disabled:opacity-50"
                    :disabled="readonlyFallback || actionPending || !invoiceInput.trim()"
                    @click="readInvoice"
                  >
                    <Icon :name="actionPending ? 'lucide:loader-circle' : 'lucide:file-check-2'" class="size-5" :class="actionPending ? 'animate-spin' : ''" />
                    {{ actionPending ? "Traduzindo" : "Traduzir NF" }}
                  </button>
                  <button
                    type="button"
                    class="inline-flex h-12 items-center justify-center gap-2 rounded-xl border border-border bg-card px-3 op-title hover:bg-accent disabled:opacity-50"
                    :disabled="readonlyFallback || actionPending"
                    @click="openInvoiceImagePicker"
                  >
                    <Icon name="lucide:image-up" class="size-5" />
                    Ler foto da NF
                  </button>
                </div>
                <input ref="scannerFileInput" class="sr-only" type="file" accept="image/*" capture="environment" @change="readInvoiceImage" />
                <label v-if="receiptMode !== 'invoice'" class="block op-label">
                  Referência em papel
                  <textarea v-model="receiptNote" rows="3" class="mt-1 w-full resize-none rounded-lg border border-input bg-card px-3 py-2 op-body" placeholder="Romaneio, produtor, observação" />
                </label>

                <div class="flex flex-wrap items-center gap-2">
                  <span v-if="receiptMode === 'invoice'" class="inline-flex h-8 items-center gap-1.5 rounded-full px-3 op-label font-semibold tnum" :class="invoiceStatus.valid ? 'pill-success' : 'pill-destructive'">
                    <Icon :name="invoiceStatus.valid ? 'lucide:check' : 'lucide:scan-line'" class="size-4" />
                    {{ invoiceStatus.valid ? [invoiceNumber, invoiceKeyLabel].filter(Boolean).join(" · ") : "Aguardando NF" }}
                  </span>
                  <span v-else class="inline-flex h-8 items-center gap-1.5 rounded-full px-3 op-label font-semibold pill-warning">
                    <Icon name="lucide:badge-alert" class="size-4" />
                    Sem documento fiscal
                  </span>
                </div>
              </div>

              <div class="space-y-3">
                <label data-receipt-anchor="supplier" class="block scroll-mt-4 rounded-md p-0.5 op-label transition-shadow" :class="anchorRing('supplier')">
                  Fornecedor
                  <UiNativeSelect :value="receiptSupplierRef" class="mt-1 w-full" @change="onReceiptSupplierChange">
                    <option value="">Definir fornecedor</option>
                    <option v-for="supplier in suppliers" :key="supplier.ref" :value="supplier.ref">{{ supplier.displayName }}</option>
                  </UiNativeSelect>
                </label>
                <div class="rounded-lg border border-border bg-background p-3">
                  <p class="op-eyebrow text-muted-foreground">Documento</p>
                  <p class="mt-1 op-title tnum">{{ receiptSupplier?.document || "Sem CNPJ no cadastro" }}</p>
                  <p class="op-micro text-muted-foreground">{{ receiptSupplier?.paymentTerm || "prazo a combinar" }} · {{ receiptSupplier?.leadTimeDays ?? 0 }} {{ (receiptSupplier?.leadTimeDays ?? 0) === 1 ? "dia" : "dias" }}</p>
                </div>
              </div>
            </div>
          </section>

          <!-- Recebimento por exceção (com NF): o que bate entra pela contagem de
               volumes; a validade é pedida uma linha por vez; só o que não bate
               pede atenção. A lista completa continua logo abaixo. -->
          <ReceiptExceptionFlow
            v-if="receiptMode === 'invoice' && receiptLinePreviews.length"
            :view="receiptException"
            :materials="materials"
            :line-count="receiptLinePreviews.length"
            :total-cost-q="receiptTotalCostQ"
            :declared-volumes="receiptInvoiceVolumes"
            :pending="readonlyFallback || actionPending"
            :volumes-ring="anchorRing('volumes')"
            @count="onExceptionCount"
            @expiry="onExceptionExpiry"
            @open="openReceiptLine"
          />

          <section class="rounded-xl border border-border bg-card">
            <div class="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
              <div class="min-w-0">
                <h2 class="op-title">Itens da entrada</h2>
                <p class="op-micro text-muted-foreground">{{ receiptConference.label }}</p>
              </div>
              <button type="button" class="inline-flex min-h-control items-center gap-2 rounded-xl border border-border bg-card px-4 op-label font-semibold hover:bg-accent" @click="addAndOpenReceiptLine">
                <Icon name="lucide:plus" class="size-4" />
                Item
              </button>
            </div>

            <!-- A LISTA da entrada: uma linha por item, e o que falta dito na
                 própria linha. Tocar na linha abre a gaveta daquele item.

                 `min-w-0` no item da lista: sem ele a coluna é dimensionada pelo
                 min-content do nome mais comprido e passa da largura do telefone. -->
            <ul v-if="receiptRows.length" class="grid min-w-0 grid-cols-1 gap-2 p-3">
              <li
                v-for="row in receiptRows"
                :key="row.id"
                :data-receipt-line="row.id"
                class="flex min-w-0 scroll-mt-4 items-stretch gap-1 rounded-xl border pr-1 transition-colors"
                :class="RECEIPT_LINE_STATUS_ROW[row.status]"
              >
                <button
                  type="button"
                  class="flex min-h-16 min-w-0 flex-1 items-center gap-3 rounded-xl py-3 pl-3 text-left"
                  :aria-label="`Abrir ${row.label}`"
                  @click="openReceiptLine(row.id)"
                >
                  <Icon :name="row.statusIcon" class="size-6 shrink-0" :class="RECEIPT_LINE_STATUS_TEXT[row.status]" />
                  <span class="min-w-0 flex-1">
                    <span class="block truncate op-title">{{ row.label }}</span>
                    <span v-if="row.digest" class="block truncate op-label font-normal text-muted-foreground tnum">{{ row.digest }}</span>
                    <!-- A pendência mora na LINHA. Era isto que obrigava a abrir
                         o item para descobrir que faltava a validade dele. -->
                    <span v-if="row.nextStep" class="block truncate op-label text-destructive">{{ row.nextStep }}</span>
                    <span v-else-if="row.note" class="block truncate op-label font-normal text-warning">{{ row.note }}</span>
                  </span>
                  <span class="flex shrink-0 flex-col items-end gap-1">
                    <span v-if="row.total" class="op-title tnum">{{ row.total }}</span>
                    <span
                      class="inline-flex h-6 items-center rounded-full px-2 op-micro font-semibold"
                      :class="RECEIPT_LINE_STATUS_BADGE[row.status]"
                    >
                      {{ row.statusLabel }}
                    </span>
                  </span>
                  <Icon name="lucide:chevron-right" class="size-4 shrink-0 text-muted-foreground" />
                </button>
                <button
                  type="button"
                  class="inline-flex w-11 shrink-0 items-center justify-center rounded-xl text-muted-foreground hover:bg-accent hover:text-destructive"
                  :aria-label="`Remover ${row.label}`"
                  @click="removeReceiptLine(row.id)"
                >
                  <Icon name="lucide:trash-2" class="size-4" />
                </button>
              </li>
            </ul>
            <p v-else class="px-4 py-8 text-center op-body text-muted-foreground">
              Nenhum item na entrada ainda. Escaneie a NF, ou toque em "Item" para lançar à mão.
            </p>
          </section>

          <!-- A gaveta do item: título fixo no topo, formulário rolando por
               baixo. Confirmar ali fecha a gaveta e a linha da lista muda de cor
               na frente do operador. -->
          <ReceiptLineSheet
            v-model:open="lineSheetOpen"
            :preview="openPreview"
            :materials="materials"
            :conversions="openPreview ? receiptConversionsFor(openPreview.line.materialSku) : []"
            :pending="actionPending"
            :stock-after="openPreview ? stockAfterReceipt(openPreview.material.sku) : 0"
            :flash-field="sheetFlashField"
            @update="onSheetUpdate"
            @select-material="onSheetSelectMaterial"
            @accept-suggestion="onSheetAcceptSuggestion"
            @select-conversion="onSheetSelectConversion"
            @accept-conversion="onSheetAcceptConversion"
            @accept-axes="onSheetAcceptAxes"
            @declare-conversion="onSheetDeclareConversion"
            @check="onSheetCheck"
            @remove="removeOpenReceiptLine"
          />
        </div>

        <aside class="h-fit min-w-0 rounded-xl border border-border bg-card p-4" data-receipt-conference>
          <!-- Prévia v3 (tablet): "4 de 7 conferidos · 2 pendências" com a barra. -->
          <div class="flex items-baseline justify-between gap-2">
            <p class="op-title tnum">{{ receiptConference.ready }} de {{ receiptConference.total }} {{ receiptConference.total === 1 ? "conferido" : "conferidos" }}</p>
            <p class="op-label tnum" :class="receiptTotalPending ? 'text-destructive' : 'text-success'">
              {{ receiptTotalPending ? `${receiptTotalPending} ${receiptTotalPending === 1 ? "pendência" : "pendências"}` : "sem pendência" }}
            </p>
          </div>
          <div class="mt-2 flex h-2 overflow-hidden rounded-full bg-muted" aria-hidden="true">
            <span class="h-full bg-success" :style="{ width: receiptConference.total ? `${(receiptConference.ready / receiptConference.total) * 100}%` : '0%' }" />
            <span class="h-full bg-destructive/70" :style="{ width: receiptConference.total ? `${(Math.min(receiptPendingLines.length, receiptConference.total - receiptConference.ready) / receiptConference.total) * 100}%` : '0%' }" />
          </div>

          <dl class="mt-4 grid grid-cols-3 gap-3">
            <div><dt class="op-micro text-muted-foreground">Origem</dt><dd class="op-title">{{ receiptMode === "invoice" ? "NF" : "Sem NF" }}</dd></div>
            <div><dt class="op-micro text-muted-foreground">Valor</dt><dd class="op-title tnum">{{ formatMoney(receiptTotalCostQ) }}</dd></div>
            <div><dt class="op-micro text-muted-foreground">Pendências</dt><dd class="op-title tnum" :class="receiptTotalPending ? 'text-destructive' : 'text-success'">{{ receiptTotalPending }}</dd></div>
          </dl>

          <div class="mt-4 rounded-lg border border-border bg-background p-3">
            <p class="op-eyebrow text-muted-foreground">{{ receiptMode === "invoice" ? "Chave NF" : "Fornecedor" }}</p>
            <p class="mt-1 break-words op-title tnum">
              <template v-if="receiptMode === 'invoice'">{{ invoiceStatus.valid ? [invoiceNumber, invoiceKeyLabel].filter(Boolean).join(" · ") : "Aguardando NF" }}</template>
              <template v-else>{{ receiptSupplier?.name || "Definir fornecedor" }}</template>
            </p>
          </div>

          <label v-if="receiptMode === 'invoice'" class="mt-4 block op-label">
            Ressalva geral
            <textarea v-model="receiptNote" rows="3" class="mt-1 w-full resize-none rounded-lg border border-input bg-card px-3 py-2 op-body" placeholder="Avaria, falta, devolução, observação na NF/CT-e" />
          </label>

          <!-- Rascunho em branco não tem pendência: tem convite. -->
          <div v-if="receiptIsBlank" class="mt-4 rounded-lg border border-dashed border-border p-3 op-body text-muted-foreground">
            Nada em conferência. Escaneie a NF da próxima entrega, ou lance sem NF.
          </div>

          <!-- Toda pendência é um GESTO: clicar leva ao campo que falta, não a
               uma acusação parada no rodapé. -->
          <div v-else-if="receiptDocumentBlockers.length || receiptSupplierBlockers.length || receiptVolumesStep || receiptPendingLines.length || uniqueWatchWarnings.length" class="mt-4 space-y-2">
            <button
              v-for="blocker in receiptDocumentBlockers"
              :key="blocker"
              type="button"
              class="block min-h-control w-full min-w-0 rounded-lg border px-3 py-2 text-left op-label"
              :class="receiptWarningClasses.block"
              @click="focusReceiptAnchor('invoice')"
            >
              {{ blocker }}
            </button>
            <button
              v-for="blocker in receiptSupplierBlockers"
              :key="blocker"
              type="button"
              class="block min-h-control w-full min-w-0 rounded-lg border px-3 py-2 text-left op-label"
              :class="receiptWarningClasses.block"
              @click="focusReceiptAnchor('supplier')"
            >
              {{ blocker }}
            </button>
            <button
              v-if="receiptVolumesStep"
              type="button"
              class="block min-h-control w-full min-w-0 rounded-lg border px-3 py-2 text-left op-label"
              :class="receiptWarningClasses.block"
              @click="focusReceiptAnchor('volumes')"
            >
              {{ receiptVolumesStep }}
            </button>
            <button
              v-for="item in receiptPendingLines"
              :key="`pending-${item.id}`"
              type="button"
              class="block min-h-control w-full min-w-0 rounded-lg border px-3 py-2 text-left"
              :class="receiptWarningClasses[item.tone]"
              @click="focusReceiptLine(item.id, item.field)"
            >
              <span class="block truncate op-label font-semibold">{{ item.label }}</span>
              <span class="block op-micro opacity-80">{{ item.step }}</span>
            </button>
            <div v-for="(warning, index) in uniqueWatchWarnings" :key="`watch-${warning.key}-${index}`" class="rounded-lg border px-3 py-2 op-label" :class="receiptWarningClasses[warning.tone]">{{ warning.label }}</div>
          </div>

          <div v-if="!receiptIsBlank" class="mt-4 border-t border-border pt-4" data-receipt-confirm-panel>
            <!-- O botão nunca fica mudo. Se ainda falta algo ele diz o quê, e ao
                 ser apertado leva até o campo. Com pendência ele é tracejado
                 (prévia v4): tocável, aponta para o que falta. -->
            <button
              type="button"
              class="hidden h-14 w-full items-center justify-center gap-2 rounded-xl px-3 op-action disabled:opacity-50 md:inline-flex"
              :class="receiptReady ? 'bg-primary text-primary-foreground' : 'border-2 border-dashed border-primary/50 bg-background text-foreground hover:bg-accent'"
              :disabled="readonlyFallback || actionPending"
              @click="onConfirmReceipt"
            >
              <Icon :name="actionPending ? 'lucide:loader-circle' : receiptReady ? 'lucide:package-check' : 'lucide:list-checks'" class="size-5" :class="actionPending ? 'animate-spin' : ''" />
              {{ actionPending ? "Confirmando" : "Confirmar entrada" }}
            </button>
            <p v-if="!receiptReady && receiptFirstBlocker" class="mt-2 hidden items-start justify-center gap-1.5 op-label font-normal text-muted-foreground md:flex">
              <Icon name="lucide:arrow-right" class="mt-0.5 size-3.5 shrink-0" />
              <span>
                {{ receiptFirstBlocker.step }}{{ receiptFirstBlocker.label ? ` em ${receiptFirstBlocker.label}` : "" }}<template v-if="receiptTotalPending > 1"> · e mais {{ receiptTotalPending - 1 }}</template>
              </span>
            </p>
            <button type="button" class="mt-2 inline-flex h-12 w-full items-center justify-center gap-2 rounded-xl border border-border bg-card px-3 op-title text-destructive hover:bg-destructive/10 disabled:opacity-50" :disabled="readonlyFallback || !receiptHasRejectionReason || actionPending" @click="onRejectReceipt">
              <Icon :name="actionPending ? 'lucide:loader-circle' : 'lucide:undo-2'" class="size-5" :class="actionPending ? 'animate-spin' : ''" />
              {{ actionPending ? "Registrando" : "Registrar devolução" }}
            </button>
          </div>
        </aside>

        <!-- Celular: "Confirmar entrada" fica no polegar, logo acima da barra das seções
             (prévias v3/v4 do celular). Mesmo gesto e mesma regra do painel. -->
        <div
          v-if="isPhone && !receiptIsBlank"
          class="sticky bottom-[calc(4rem+1px+env(safe-area-inset-bottom))] z-20 -mx-3 -mb-3 border-t border-border bg-card px-3 pt-2.5 pb-2 shadow-[0_-6px_14px_rgb(0_0_0/.06)]"
          data-focus-obstruction
          data-receipt-confirm-bar
        >
          <button
            type="button"
            class="inline-flex h-14 w-full items-center justify-center gap-2 rounded-xl px-3 op-action disabled:opacity-50"
            :class="receiptReady ? 'bg-primary text-primary-foreground' : 'border-2 border-dashed border-primary/50 bg-background text-foreground'"
            :disabled="readonlyFallback || actionPending"
            @click="onConfirmReceipt"
          >
            <Icon :name="actionPending ? 'lucide:loader-circle' : receiptReady ? 'lucide:check' : 'lucide:arrow-up'" class="size-5" :class="actionPending ? 'animate-spin' : ''" />
            {{ actionPending ? "Confirmando" : "Confirmar entrada" }}
          </button>
          <p v-if="!receiptReady && receiptFirstBlocker" class="mt-1.5 flex items-center justify-center gap-1.5 op-label font-normal text-muted-foreground">
            <Icon name="lucide:arrow-right" class="size-3.5 shrink-0" />
            <span class="truncate">{{ receiptFirstBlocker.step }}{{ receiptFirstBlocker.label ? ` em ${receiptFirstBlocker.label}` : "" }}<template v-if="receiptTotalPending > 1"> · e mais {{ receiptTotalPending - 1 }}</template></span>
          </p>
        </div>
      </section>

      <!-- ══ BASE ════════════════════════════════════════════════════════════ -->
      <section v-else class="flex min-w-0 flex-1 flex-col gap-4">
        <!-- Insumos: tabela e painel docado do item (prévia `purchase-base3.html`). -->
        <section v-if="baseView === 'materials'" class="flex min-w-0 flex-1 flex-col xl:flex-row">
          <div class="flex min-w-0 flex-1 flex-col xl:px-4 xl:pt-3">
            <!-- Celular: um cartão por insumo (a tabela de seis colunas não cabe em 390 px). -->
            <ul v-if="isPhone" class="grid grid-cols-1 gap-2" data-material-cards>
              <li
                v-for="material in filteredMaterials"
                :key="`card-${material.sku}`"
                class="rounded-xl border bg-card p-3"
                :class="selectedMaterial?.sku === material.sku ? 'border-primary/50 bg-primary/8' : 'border-border'"
              >
                <button type="button" class="block w-full min-w-0 text-left" @click="selectMaterial(material.sku)">
                  <span class="block truncate op-title">{{ material.name }}</span>
                  <span class="mt-0.5 flex min-w-0 items-center gap-1.5 overflow-hidden whitespace-nowrap">
                    <span class="shrink-0 font-mono op-micro text-muted-foreground">{{ material.sku }}</span>
                    <span v-for="badge in skuRoleBadges(material.roles)" :key="badge" class="inline-flex h-5 items-center rounded border border-border px-1.5 op-micro text-muted-foreground">{{ badge }}</span>
                  </span>
                </button>
                <div class="mt-2 flex items-end justify-between gap-3">
                  <div class="min-w-0">
                    <p class="op-micro text-muted-foreground">Estoque · {{ coverageLabel(material.coverageDays) }}</p>
                    <p class="op-title tnum">{{ formatStockOnHand(material) }}</p>
                  </div>
                  <label
                    class="inline-flex h-11 w-32 shrink-0 items-center gap-1.5 rounded-md bg-card px-2.5"
                    :class="minStockLineErrors[material.sku] ? 'border-2 border-destructive' : minStockInputs[material.sku] ? 'border-2 border-primary' : 'border border-input'"
                  >
                    <input
                      inputmode="decimal"
                      :placeholder="material.minStockDeclared ? material.minStock.toLocaleString('pt-BR') : 'sem mínimo'"
                      class="w-full min-w-0 border-0 bg-transparent p-0 text-right font-semibold tnum outline-none placeholder:op-micro placeholder:font-normal placeholder:text-muted-foreground focus:ring-0"
                      :aria-label="`Mínimo de ${material.name}`"
                      :value="minStockInputs[material.sku] ?? ''"
                      @input="setMinStockInput(material.sku, ($event.target as HTMLInputElement).value)"
                    />
                    <span class="op-micro text-muted-foreground">{{ material.unit }}</span>
                  </label>
                </div>
                <div class="mt-2 flex flex-wrap items-center justify-between gap-2">
                  <span class="inline-flex h-6 items-center gap-1.5 rounded-full px-2 op-micro font-semibold" :class="tonePills[material.tone]">
                    <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />
                    {{ toneLabels[material.tone] }}
                  </span>
                  <span class="op-micro text-muted-foreground tnum">
                    {{ material.preferredBaseCostQ ? `${formatMoney(material.preferredBaseCostQ)} / ${material.unit}` : "sem custo" }}
                  </span>
                </div>
                <p v-if="!material.minStockDeclared && material.minStock" class="mt-1 op-micro text-muted-foreground">
                  pelo consumo: {{ formatQty(material.minStock, material.unit) }}
                </p>
                <p v-if="minStockLineErrors[material.sku]" class="mt-1 op-micro font-semibold text-destructive">
                  {{ minStockLineErrors[material.sku] }}
                </p>
              </li>
              <li v-if="!filteredMaterials.length" class="rounded-xl border border-dashed border-border p-6 text-center op-body text-muted-foreground">
                <template v-if="!materials.length">Base de insumos ainda não carregada.</template>
                <template v-else-if="query.trim()">Nenhum insumo encontrado para “{{ query }}”.</template>
                <template v-else>Nenhum insumo pede atenção.</template>
              </li>
            </ul>
            <div v-else class="overflow-hidden rounded-lg border border-border bg-card">
              <div class="overflow-x-auto">
                <table class="w-full min-w-[56rem] table-fixed op-body">
                  <colgroup><col><col class="w-28"><col class="w-32"><col class="w-48"><col class="w-32"><col class="w-32"></colgroup>
                  <thead class="bg-muted/60 text-left text-muted-foreground">
                    <tr class="h-10">
                      <th class="pr-2 pl-4 op-eyebrow">Insumo</th>
                      <th class="px-3 text-right op-eyebrow">Estoque</th>
                      <th class="px-3 op-eyebrow">Cobertura</th>
                      <th class="px-3 op-eyebrow">Mínimo</th>
                      <th class="px-3 text-right op-eyebrow whitespace-nowrap">Custo-base</th>
                      <th class="px-3 op-eyebrow">Situação</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="material in filteredMaterials"
                      :key="material.sku"
                      class="h-16 border-t border-border transition-colors hover:bg-accent/60"
                      :class="selectedMaterial?.sku === material.sku ? 'bg-primary/8 shadow-[inset_3px_0_0_var(--primary)]' : ''"
                    >
                      <td class="max-w-0 py-2 pr-2 pl-4">
                        <button type="button" class="block max-w-full truncate text-left hover:underline" @click="selectMaterial(material.sku)">
                          <span class="font-semibold">{{ material.name }}</span>
                          <span class="op-micro text-muted-foreground"> · {{ material.category }}<template v-if="material.recipes.length"> · {{ material.recipes.length }} {{ material.recipes.length === 1 ? "receita" : "receitas" }}</template></span>
                        </button>
                        <div class="mt-1 flex min-w-0 items-center gap-1.5 overflow-hidden whitespace-nowrap">
                          <span class="mr-0.5 shrink-0 font-mono op-micro text-muted-foreground">{{ material.sku }}</span>
                          <span v-for="badge in skuRoleBadges(material.roles)" :key="badge" class="inline-flex h-5 items-center rounded border border-border px-1.5 op-micro text-muted-foreground">{{ badge }}</span>
                        </div>
                      </td>
                      <td class="px-3 text-right font-medium whitespace-nowrap tnum">{{ formatStockOnHand(material) }}</td>
                      <td class="px-3 whitespace-nowrap text-muted-foreground tnum">{{ coverageLabel(material.coverageDays) }}</td>
                      <!-- Sem consumo medido, o alvo de reposição é zero e o insumo
                           nunca vira sugestão. O mínimo declarado é o que destrava. -->
                      <td class="px-3 py-2">
                        <div class="flex items-center gap-1.5">
                          <label
                            class="inline-flex h-10 w-32 items-center gap-1.5 rounded-md bg-card px-2.5"
                            :class="minStockLineErrors[material.sku] ? 'border-2 border-destructive' : minStockInputs[material.sku] ? 'border-2 border-primary' : 'border border-input'"
                          >
                            <input
                              inputmode="decimal"
                              :placeholder="material.minStockDeclared ? material.minStock.toLocaleString('pt-BR') : 'sem mínimo'"
                              class="w-full min-w-0 border-0 bg-transparent p-0 text-right font-semibold tnum outline-none placeholder:op-micro placeholder:font-normal placeholder:text-muted-foreground focus:ring-0"
                              :aria-label="`Mínimo de ${material.name}`"
                              :value="minStockInputs[material.sku] ?? ''"
                              @input="setMinStockInput(material.sku, ($event.target as HTMLInputElement).value)"
                            />
                            <span class="op-micro text-muted-foreground">{{ material.unit }}</span>
                          </label>
                          <span class="size-1.5 shrink-0 rounded-full" :class="minStockInputs[material.sku] ? 'bg-primary' : ''" :title="minStockInputs[material.sku] ? 'Alterado' : undefined" />
                        </div>
                        <!-- Declarado × derivado do consumo. O derivado NÃO vai no
                             campo: pré-preenchido, ele convida a "confirmar"
                             digitando o mesmo número — e isso congela um mínimo que
                             era para acompanhar o consumo. -->
                        <p v-if="!material.minStockDeclared && material.minStock" class="mt-0.5 op-micro text-muted-foreground">
                          pelo consumo: {{ formatQty(material.minStock, material.unit) }}
                        </p>
                        <p v-if="minStockLineErrors[material.sku]" class="mt-0.5 op-micro font-semibold text-destructive">
                          {{ minStockLineErrors[material.sku] }}
                        </p>
                      </td>
                      <td class="px-3 text-right whitespace-nowrap tnum" :class="material.preferredBaseCostQ ? '' : 'text-muted-foreground'">
                        {{ material.preferredBaseCostQ ? `${formatMoney(material.preferredBaseCostQ)} / ${material.unit}` : "sem custo" }}
                      </td>
                      <td class="px-3">
                        <span class="inline-flex h-6 items-center gap-1.5 rounded-full px-2 op-micro font-semibold" :class="tonePills[material.tone]">
                          <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />
                          {{ toneLabels[material.tone] }}
                        </span>
                      </td>
                    </tr>
                    <tr v-if="!filteredMaterials.length">
                      <td colspan="6" class="px-4 py-8 text-center text-muted-foreground">
                        <template v-if="!materials.length">Base de insumos ainda não carregada.</template>
                        <template v-else-if="query.trim()">Nenhum insumo encontrado para “{{ query }}”.</template>
                        <template v-else>Nenhum insumo pede atenção.</template>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            <div class="flex-1" />

            <!-- Barra de ação no rodapé (prévia v3): os mínimos alterados e o salvar. -->
            <div
              v-if="minStockFilledCount"
              class="sticky bottom-0 z-10 mt-3 flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card px-4 py-3 max-md:bottom-[calc(4rem+1px+env(safe-area-inset-bottom))] xl:-mx-4 xl:mt-3 xl:rounded-none xl:border-x-0 xl:border-b-0"
              data-focus-obstruction
            >
              <span class="size-2 rounded-full bg-primary" aria-hidden="true" />
              <p class="op-label">
                <span class="font-semibold tnum">{{ minStockFilledCount }}</span>
                {{ minStockFilledCount === 1 ? "mínimo alterado" : "mínimos alterados" }}
              </p>
              <span class="op-micro text-muted-foreground">zero apaga o mínimo do insumo</span>
              <div class="flex-1" />
              <button
                type="button"
                class="min-h-control rounded-md border border-border bg-card px-4 op-label hover:bg-accent disabled:opacity-50"
                :disabled="actionPending"
                @click="clearMinStock()"
              >
                Limpar
              </button>
              <button
                type="button"
                class="inline-flex min-h-control items-center gap-2 rounded-md bg-primary px-5 op-label font-semibold text-primary-foreground disabled:opacity-50"
                :disabled="readonlyFallback || actionPending"
                @click="saveMinStock()"
              >
                <Icon name="lucide:check" class="size-4" />
                Salvar mínimos
              </button>
            </div>
          </div>

          <!-- Painel docado do item (prévia v3: 372 px, borda à esquerda). -->
          <aside
            v-if="selectedMaterial"
            class="mt-4 shrink-0 rounded-lg border border-border bg-card xl:mt-0 xl:w-[372px] xl:self-stretch xl:rounded-none xl:border-y-0 xl:border-r-0"
            data-material-panel
          >
            <div class="flex items-start gap-3 border-b border-border px-5 pt-4 pb-3">
              <div class="min-w-0 flex-1">
                <p class="op-eyebrow text-muted-foreground">Insumo</p>
                <h2 class="truncate text-lg leading-tight font-semibold">{{ selectedMaterial.name }}</h2>
                <p class="truncate op-micro text-muted-foreground"><span class="font-mono">{{ selectedMaterial.sku }}</span> · {{ selectedMaterial.category }}</p>
              </div>
            </div>
            <div class="flex flex-col gap-3.5 px-5 py-4">
              <div v-for="issue in selectedMaterial.issues" :key="issue.key" class="inline-flex items-center gap-2 rounded-md border px-3 py-2 op-label" :class="toneClasses[issue.tone]">
                <Icon name="lucide:triangle-alert" class="size-4 shrink-0" />
                {{ issue.label }}
              </div>
              <p v-if="!selectedMaterial.issues.length" class="inline-flex items-center gap-2 rounded-md border border-success/25 bg-success/10 px-3 py-2 op-label text-success">
                <Icon name="lucide:circle-check" class="size-4 shrink-0" />
                Sem pontos de atenção
              </p>
              <!-- Permitir revenda: um gesto, que pede só o preço. O cadastro de venda
                   nasce com o MESMO SKU (mesmo estoque) e entra no PDV; loja online
                   só com foto. Desligar tira da venda sem apagar nada. -->
              <div data-testid="sale-toggle">
                <div class="flex flex-wrap gap-1.5">
                  <span v-for="badge in skuRoleBadges(selectedMaterial.roles)" :key="badge" class="inline-flex h-6 items-center rounded border border-border px-2 op-micro text-muted-foreground">{{ badge }}</span>
                </div>
                <div class="mt-4 border-t border-border pt-4">
                  <p v-if="selectedMaterial.roles?.produced && !selectedMaterial.roles?.sellable" class="op-micro text-muted-foreground">
                    É produzido aqui: a venda dele é do Catálogo, não do Compras.
                  </p>
                  <template v-else>
                    <label class="flex items-center gap-2.5 op-label font-semibold">
                      <input
                        type="checkbox" class="form-checkbox size-5 rounded border-input text-primary"
                        :checked="Boolean(selectedMaterial.roles?.sellable) || saleOpen"
                        :disabled="readonlyFallback || actionPending"
                        @change="onResaleToggle"
                      />
                      Permitir revenda
                    </label>
                    <p v-if="selectedMaterial.roles?.sellable" class="mt-1 pl-7 op-body">
                      <template v-if="selectedMaterial.unit === 'kg'">Vendido só no balcão, por peso:</template>
                      <template v-else>À venda no PDV:</template>
                      <span class="font-semibold tnum">{{ formatMoney(selectedMaterial.salePriceQ ?? 0) }}</span> / {{ selectedMaterial.unit }}.
                    </p>
                    <p v-else-if="!saleOpen" class="mt-1 pl-7 op-micro text-muted-foreground">Pede só o preço. Entra no PDV com o mesmo SKU e o mesmo estoque.</p>
                    <form v-if="!selectedMaterial.roles?.sellable && saleOpen" class="mt-3 rounded-md border border-dashed border-border bg-background/60 p-3" @submit.prevent="confirmSale()">
                      <div class="flex items-end gap-2">
                        <label class="block min-w-0 flex-1">
                          <span class="block op-micro text-muted-foreground">{{ resaleCopy(selectedMaterial.unit, salePriceInput).priceLabel }}</span>
                          <input v-model="salePriceInput" inputmode="decimal" required placeholder="0,00" class="mt-1 h-10 w-full rounded-md border border-input bg-card px-3 op-body tnum" />
                        </label>
                        <button
                          type="submit"
                          class="h-10 shrink-0 rounded-md bg-primary px-3 op-label font-semibold text-primary-foreground disabled:opacity-50"
                          :disabled="readonlyFallback || actionPending || !resaleCopy(selectedMaterial.unit, salePriceInput).ready"
                        >
                          Colocar à venda
                        </button>
                      </div>
                      <p v-if="resaleSuggestionView(selectedMaterial.saleSuggestion, selectedMaterial.unit)" class="mt-1.5 op-micro text-muted-foreground">
                        Sugerido: {{ resaleSuggestionView(selectedMaterial.saleSuggestion, selectedMaterial.unit)?.basis }}
                      </p>
                      <p v-else class="mt-1.5 op-micro text-muted-foreground">Sem custo de compra registrado: informe o preço.</p>
                      <p class="mt-0.5 op-micro text-muted-foreground">{{ resaleCopy(selectedMaterial.unit, salePriceInput).reach }}</p>
                    </form>
                  </template>
                </div>
              </div>
              <!-- Quando aberto, vira: a embalagem por unidade que a produção usa em
                   gramas. A produção abre sozinha no fechamento da fornada; aqui só
                   se diz o que vem dentro. -->
              <div v-if="openingView(selectedMaterial, materials).canOpen" class="border-t border-border pt-4" data-testid="opening">
                <div class="flex items-baseline justify-between gap-2">
                  <p class="op-label font-semibold">Quando aberto, vira</p>
                  <button
                    v-if="!openingDraft.open"
                    type="button"
                    class="min-h-control px-1 op-label font-semibold text-primary hover:underline disabled:opacity-50"
                    :disabled="readonlyFallback || actionPending"
                    @click="openingDraft.open = true"
                  >
                    {{ selectedMaterial.opensInto ? "Alterar" : "Definir" }}
                  </button>
                </div>
                <p v-if="selectedMaterial.opensInto && !openingDraft.open" class="mt-1 op-body">{{ openingView(selectedMaterial, materials).summary }}</p>
                <p v-else-if="!openingDraft.open" class="mt-1 op-micro text-muted-foreground">
                  Só se a produção usa este item em peso. Ela abre uma embalagem quando precisa.
                </p>
                <form v-if="openingDraft.open" class="mt-2 space-y-2" @submit.prevent="saveOpening()">
                  <label class="block">
                    <span class="block op-micro text-muted-foreground">Insumo aberto</span>
                    <select v-model="openingDraft.target" class="mt-1 h-10 w-full rounded-md border border-input bg-card px-2 op-body">
                      <option :value="CREATE_OPENED">Criar a partir desta embalagem (em kg)</option>
                      <option v-for="option in openingView(selectedMaterial, materials).options" :key="option.value" :value="option.value">{{ option.label }}</option>
                    </select>
                  </label>
                  <div class="grid grid-cols-2 gap-2">
                    <label class="block">
                      <span class="block op-micro text-muted-foreground">Quanto vem em uma embalagem</span>
                      <input v-model="openingDraft.quantity" inputmode="decimal" required placeholder="0,200" class="mt-1 h-10 w-full rounded-md border border-input bg-card px-3 op-body tnum" />
                    </label>
                    <label class="block">
                      <span class="block op-micro text-muted-foreground">Validade depois de aberto (dias)</span>
                      <input v-model="openingDraft.shelfLifeDays" inputmode="numeric" placeholder="Sem prazo" class="mt-1 h-10 w-full rounded-md border border-input bg-card px-3 op-body tnum" />
                    </label>
                  </div>
                  <div class="flex flex-wrap gap-2">
                    <button type="submit" class="min-h-control rounded-md bg-primary px-4 op-label font-semibold text-primary-foreground disabled:opacity-50" :disabled="readonlyFallback || actionPending || !openingDraft.quantity.trim()">
                      Salvar
                    </button>
                    <button type="button" class="min-h-control rounded-md border border-border bg-card px-3 op-label hover:bg-accent" @click="openingDraft.open = false">Cancelar</button>
                    <button
                      v-if="selectedMaterial.opensInto"
                      type="button"
                      class="min-h-control rounded-md border border-border bg-card px-3 op-label hover:bg-accent disabled:opacity-50"
                      :disabled="readonlyFallback || actionPending"
                      @click="setOpening(selectedMaterial.sku, { enabled: false }).then((ok) => { if (ok) openingDraft.open = false; })"
                    >
                      Não abre mais
                    </button>
                  </div>
                </form>
              </div>
              <div class="border-t border-border pt-4">
                <p class="op-label font-semibold">Receitas que consomem <span class="font-normal text-muted-foreground tnum">{{ selectedMaterial.recipes.length }}</span></p>
                <div class="mt-2 flex flex-wrap gap-1.5">
                  <span v-for="recipe in selectedMaterial.recipes" :key="recipe" class="inline-flex h-7 items-center rounded-md border border-border px-2 op-micro">{{ recipe }}</span>
                </div>
              </div>
            </div>
          </aside>
        </section>

        <!-- Fornecedores -->
        <section v-else-if="baseView === 'suppliers'" class="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
          <div class="grid content-start gap-3 md:grid-cols-2 2xl:grid-cols-3">
            <button v-for="summary in supplierSummaries" :key="summary.supplier.ref" type="button" class="rounded-xl border p-4 text-left transition" :class="summary.supplier.ref === selectedSupplierRef ? 'border-primary bg-primary/8 shadow-[inset_3px_0_0_var(--primary)]' : 'border-border bg-card hover:bg-accent'" @click="selectSupplier(summary.supplier.ref)">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <h2 class="truncate op-title">{{ summary.supplier.displayName }}</h2>
                  <p class="truncate font-mono op-micro text-muted-foreground">{{ summary.supplier.ref }}</p>
                </div>
                <span class="inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full px-2 op-micro font-semibold" :class="summary.supplier.isActive ? 'pill-success' : 'pill-muted'">
                  <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />
                  {{ summary.supplier.isActive ? "Ativo" : "Inativo" }}
                </span>
              </div>
              <div class="mt-3 grid grid-cols-3 gap-2">
                <span><span class="block op-micro text-muted-foreground">Insumos</span><span class="op-title tnum">{{ summary.materialsCovered }}</span></span>
                <span><span class="block op-micro text-muted-foreground">Preferidos</span><span class="op-title tnum">{{ summary.preferredCount }}</span></span>
                <span><span class="block op-micro text-muted-foreground">Entrega</span><span class="op-title tnum">{{ summary.supplier.reliabilityPercent }}%</span></span>
              </div>
            </button>
            <p v-if="!supplierSummaries.length" class="rounded-xl border border-dashed border-border p-6 text-center op-body text-muted-foreground md:col-span-2 2xl:col-span-3">
              Nenhum fornecedor cadastrado ainda.
            </p>
          </div>

          <aside v-if="selectedSupplier" class="h-fit rounded-xl border border-border bg-card">
            <div class="border-b border-border px-5 pt-4 pb-3">
              <p class="op-eyebrow text-muted-foreground">Fornecedor</p>
              <h2 class="text-lg leading-tight font-semibold">{{ selectedSupplier.displayName }}</h2>
              <!-- A razao social so aparece quando difere do nome do dia a dia:
                   repeti-la nas duas linhas nao informa nada. -->
              <p v-if="selectedSupplier.tradeName && selectedSupplier.name !== selectedSupplier.displayName" class="op-micro text-muted-foreground">
                {{ selectedSupplier.name }}
              </p>
              <p v-if="selectedSupplier.document" class="op-micro text-muted-foreground tnum">{{ selectedSupplier.document }}</p>
            </div>
            <div class="px-5 py-4">
              <dl class="grid grid-cols-2 gap-3">
                <div><dt class="op-micro text-muted-foreground">Prazo</dt><dd class="op-title">{{ selectedSupplier.leadTimeDays }} {{ selectedSupplier.leadTimeDays === 1 ? "dia" : "dias" }}</dd></div>
                <div><dt class="op-micro text-muted-foreground">Entrega</dt><dd class="op-title tnum">{{ selectedSupplier.reliabilityPercent }}%</dd></div>
                <div><dt class="op-micro text-muted-foreground">Última</dt><dd class="op-title tnum">{{ formatShortDate(selectedSupplier.lastDeliveryAt) }}</dd></div>
                <div><dt class="op-micro text-muted-foreground">Pagamento</dt><dd class="op-title">{{ selectedSupplier.paymentTerm }}</dd></div>
              </dl>
              <div class="mt-4 border-t border-border pt-4">
                <div class="flex items-baseline justify-between gap-2">
                  <h3 class="op-label font-semibold">Contatos</h3>
                  <!-- O cadastro de pessoa e config, e config se edita no Admin.
                       A tela mostra para conferir antes de enviar, nao para editar. -->
                  <span class="op-micro text-muted-foreground">Cadastro no Admin</span>
                </div>

                <!-- A pergunta que o operador faz antes de apertar "enviar" e "vai
                     para quem?". Responder depois do envio nao serve. -->
                <p class="mt-2 op-micro" :class="selectedSupplier.orderContactName ? 'text-muted-foreground' : 'text-warning'">
                  <template v-if="selectedSupplier.orderContactName">
                    O pedido de compra vai para <span class="font-semibold">{{ selectedSupplier.orderContactName }}</span>.
                  </template>
                  <template v-else-if="selectedSupplier.contact">
                    Sem contato comercial: o pedido cai na central ({{ selectedSupplier.contact }}).
                  </template>
                  <template v-else>
                    Sem contato e sem central: o pedido de compra nao tem para onde ir.
                  </template>
                </p>

                <div v-if="activeSupplierContacts.length" class="mt-3 space-y-2">
                  <div v-for="person in activeSupplierContacts" :key="person.id" class="rounded-lg border border-border bg-background p-3">
                    <div class="flex items-start justify-between gap-2">
                      <p class="op-label font-semibold">{{ person.name }}</p>
                      <span class="inline-flex h-6 shrink-0 items-center rounded-full px-2 op-micro pill-muted">
                        {{ person.roleLabel }}<template v-if="person.isPrimary"> · principal</template>
                      </span>
                    </div>
                    <p v-if="person.email" class="op-micro text-muted-foreground">{{ person.email }}</p>
                    <p v-if="person.phone" class="op-micro text-muted-foreground tnum">{{ person.phone }}</p>
                    <p v-if="person.notes" class="mt-1 op-micro text-muted-foreground">{{ person.notes }}</p>
                  </div>
                </div>
              </div>

              <div class="mt-4 border-t border-border pt-4">
                <h3 class="op-label font-semibold">Carteira <span class="font-normal text-muted-foreground tnum">{{ selectedSupplierPortfolio.length }}</span></h3>
                <div class="mt-2 space-y-2">
                  <div v-for="row in selectedSupplierPortfolio" :key="row.cost.id" class="flex items-start justify-between gap-2 rounded-lg border border-border bg-background p-3">
                    <div class="min-w-0">
                      <p class="truncate op-label font-semibold">{{ row.material.name }}</p>
                      <p class="op-micro text-muted-foreground tnum">{{ formatMoney(row.cost.costQ) }} / {{ row.unitLabel }}</p>
                    </div>
                    <span class="shrink-0 op-label font-semibold tnum"><span v-if="row.approximate">≈ </span>{{ formatMoney(row.baseCostQ) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </aside>
        </section>

        <!-- Custos -->
        <section v-else-if="baseView === 'costs'" class="space-y-4">
          <!-- Tabela de preços do fornecedor: o gesto que tira dezenas de insumos
               do estado "sem custo preferencial" — e portanto fora de qualquer
               pedido — sem passar pelo Django Admin. -->
          <section class="overflow-hidden rounded-lg border border-border bg-card">
            <div class="flex flex-wrap items-end justify-between gap-3 border-b border-border px-4 py-3">
              <div class="min-w-0">
                <h2 class="op-title">Tabela do fornecedor</h2>
                <p class="op-micro text-muted-foreground">
                  Escolha o fornecedor e preencha os que você sabe. Quem ficar em branco não entra.
                </p>
              </div>
              <div class="flex flex-wrap items-end gap-2">
                <label class="block op-label">Fornecedor
                  <UiNativeSelect
                    v-model="batchSupplierRef"
                    class="mt-1 w-56"
                  >
                    <option value="">Escolher…</option>
                    <!-- Fornecedor inativo não pode receber custo preferencial; o
                         servidor recusa. Não oferecer é melhor que recusar. -->
                    <option
                      v-for="supplier in suppliers.filter((item) => item.isActive)"
                      :key="supplier.ref"
                      :value="supplier.ref"
                    >
                      {{ supplier.displayName }}
                    </option>
                  </UiNativeSelect>
                </label>
                <UiFilterChip :active="batchOnlyMissing" :aria-pressed="batchOnlyMissing" @click="batchOnlyMissing = !batchOnlyMissing">
                  <template #icon><Icon name="lucide:badge-alert" class="size-4 text-info" /></template>
                  Só os que faltam
                </UiFilterChip>
              </div>
            </div>

            <!-- "Nenhuma linha" tem três causas diferentes e a tela precisa dizer
                 qual: base não carregada, filtro fechando tudo, ou nada a fazer. -->
            <div v-if="!batchRows.length" class="p-6 text-center op-body text-muted-foreground">
              <template v-if="!materials.length">Base de insumos ainda não carregada.</template>
              <template v-else-if="batchQuery.trim()">Nenhum insumo encontrado para “{{ batchQuery }}”.</template>
              <template v-else-if="batchOnlyMissing">Todo insumo ativo já tem custo preferencial.</template>
              <template v-else>Nenhum insumo ativo na base.</template>
            </div>

            <div v-else class="max-h-[28rem] overflow-auto">
              <table class="w-full min-w-[36rem] op-body">
                <thead class="sticky top-0 z-10 bg-muted text-left text-muted-foreground">
                  <tr class="h-10">
                    <th class="pr-2 pl-4 op-eyebrow">Insumo</th>
                    <th class="px-3 op-eyebrow">Unidade de compra</th>
                    <th class="w-40 px-3 op-eyebrow">Valor</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in batchRows" :key="`batch-${row.sku}`" class="h-14 border-t border-border hover:bg-accent/60">
                    <td class="py-2 pr-2 pl-4">
                      <span class="font-semibold">{{ row.name }}</span>
                      <span class="ml-1 op-micro text-muted-foreground"><span class="font-mono">{{ row.sku }}</span> · {{ row.unit }}</span>
                      <p v-if="batchLineErrors[row.sku]" class="mt-0.5 op-micro font-semibold text-destructive">
                        {{ batchLineErrors[row.sku] }}
                      </p>
                    </td>
                    <td class="px-3 py-2">
                      <UiNativeSelect
                        class="w-full"
                        :value="batchConversionIds[row.sku] ?? ''"
                        @change="setBatchConversion(row.sku, ($event.target as HTMLSelectElement).value)"
                      >
                        <option value="">Unidade-base ({{ row.unit }})</option>
                        <option
                          v-for="conversion in batchConversionsFor(row.sku)"
                          :key="conversion.id"
                          :value="conversion.id"
                        >
                          {{ conversion.label }}
                        </option>
                      </UiNativeSelect>
                    </td>
                    <td class="px-3 py-2">
                      <input
                        inputmode="decimal"
                        placeholder="0,00"
                        :aria-label="`Valor de ${row.name}`"
                        class="h-10 w-full rounded-md bg-card px-2.5 text-right font-semibold tnum"
                        :class="batchLineErrors[row.sku] ? 'border-2 border-destructive' : batchInputs[row.sku] ? 'border-2 border-primary' : 'border border-input'"
                        :value="batchInputs[row.sku] ?? ''"
                        @input="setBatchInput(row.sku, ($event.target as HTMLInputElement).value)"
                      />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3">
              <p class="flex items-center gap-2 op-label">
                <span class="size-2 rounded-full" :class="batchFilledCount ? 'bg-primary' : 'bg-muted-foreground/40'" aria-hidden="true" />
                <template v-if="!batchSupplierRef">Escolha o fornecedor para lançar.</template>
                <template v-else><span class="font-semibold tnum">{{ batchFilledCount }}</span> {{ batchFilledCount === 1 ? "valor preenchido" : "valores preenchidos" }}</template>
              </p>
              <div class="flex gap-2">
                <button
                  type="button"
                  class="min-h-control rounded-md border border-border bg-card px-4 op-label hover:bg-accent disabled:opacity-50"
                  :disabled="!batchFilledCount || actionPending"
                  @click="clearCostBatch()"
                >
                  Limpar
                </button>
                <button
                  type="button"
                  class="inline-flex min-h-control items-center gap-2 rounded-md bg-primary px-5 op-label font-semibold text-primary-foreground disabled:opacity-50"
                  :disabled="readonlyFallback || !batchReady || actionPending"
                  @click="saveCostBatch()"
                >
                  <Icon name="lucide:check" class="size-4" />
                  Salvar {{ batchFilledCount || "" }} como padrão
                </button>
              </div>
            </div>
          </section>

          <div class="grid grid-cols-1 gap-4 xl:grid-cols-[24rem_minmax(0,1fr)]">
            <aside class="h-fit rounded-xl border border-border bg-card p-4">
              <h2 class="op-title">Lançar custo</h2>
              <div class="mt-3 space-y-3">
                <label class="block op-label">Insumo
                  <UiNativeSelect v-model="noteMaterialSku" class="mt-1 w-full">
                    <option v-for="material in materials" :key="material.sku" :value="material.sku">{{ material.name }}</option>
                  </UiNativeSelect>
                </label>
                <label class="block op-label">Fornecedor
                  <UiNativeSelect v-model="noteSupplierRef" class="mt-1 w-full">
                    <option v-for="supplier in suppliers" :key="supplier.ref" :value="supplier.ref">{{ supplier.displayName }}</option>
                  </UiNativeSelect>
                </label>
                <label class="block op-label">Unidade de compra
                  <UiNativeSelect v-model="noteConversionId" class="mt-1 w-full">
                    <option value="">Unidade-base</option>
                    <option v-for="conversion in availableNoteConversions" :key="conversion.id" :value="conversion.id">{{ conversion.label }}</option>
                  </UiNativeSelect>
                </label>
                <label class="block op-label">Valor da unidade de compra
                  <input v-model="noteCostInput" inputmode="decimal" class="mt-1 h-10 w-full rounded-md border border-input bg-card px-3 op-body tnum" placeholder="180,00" />
                </label>
                <div class="rounded-lg border border-border bg-background p-3">
                  <p class="op-eyebrow text-muted-foreground">Custo derivado</p>
                  <p class="mt-1 op-display tnum">
                    <template v-if="notePreview"><span v-if="notePreview.approximate">≈ </span>{{ formatMoney(notePreview.baseCostQ) }}</template>
                    <template v-else>R$ 0,00</template>
                  </p>
                </div>
                <div class="grid grid-cols-2 gap-2">
                  <button type="button" class="min-h-control rounded-md border border-border bg-card px-3 op-label hover:bg-accent disabled:opacity-50" :disabled="readonlyFallback || quoteDisabled || actionPending" @click="saveQuote(false)">Salvar custo</button>
                  <button type="button" class="min-h-control rounded-md bg-primary px-3 op-label font-semibold text-primary-foreground disabled:opacity-50" :disabled="readonlyFallback || quoteDisabled || actionPending" @click="saveQuote(true)">Salvar como padrão</button>
                </div>
              </div>
            </aside>

            <div class="overflow-hidden rounded-lg border border-border bg-card">
              <div class="border-b border-border px-4 py-3">
                <h2 class="op-title">Custos por fornecedor</h2>
              </div>
              <div class="overflow-x-auto">
                <table class="w-full min-w-[40rem] op-body">
                  <thead class="bg-muted/60 text-left text-muted-foreground">
                    <tr class="h-10"><th class="pr-2 pl-4 op-eyebrow">Insumo</th><th class="px-3 op-eyebrow">Fornecedor</th><th class="px-3 op-eyebrow">Compra</th><th class="px-3 text-right op-eyebrow">Base</th><th class="px-3 op-eyebrow">Padrão</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="cost in costs" :key="cost.id" class="h-14 border-t border-border hover:bg-accent/60">
                      <td class="pr-2 pl-4 font-semibold">{{ materials.find((material) => material.sku === cost.materialSku)?.name }}</td>
                      <td class="px-3">{{ suppliers.find((supplier) => supplier.ref === cost.supplierRef)?.displayName }}</td>
                      <td class="px-3 whitespace-nowrap tnum">{{ formatMoney(cost.costQ) }} / {{ purchaseUnitLabel(cost, materials.find((material) => material.sku === cost.materialSku), conversions) }}</td>
                      <td class="px-3 text-right font-semibold whitespace-nowrap tnum"><span v-if="isApproximateCost(cost, conversions)">≈ </span>{{ formatMoney(costPerBaseUnitQ(cost, conversions)) }}</td>
                      <td class="px-3">
                        <button type="button" class="inline-flex min-h-control items-center gap-1.5 rounded-full px-3 op-label disabled:opacity-100" :class="cost.isPreferred ? 'pill-success font-semibold' : 'border border-border bg-card hover:bg-accent'" :disabled="readonlyFallback || actionPending || cost.isPreferred" @click="setPreferredCost(cost.id)">
                          <Icon v-if="cost.isPreferred" name="lucide:check" class="size-4" />
                          {{ cost.isPreferred ? "Padrão" : "Usar padrão" }}
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>

        <!-- Contagem -->
        <section v-else class="space-y-4">
          <div v-if="countForbidden" class="rounded-xl border border-border bg-card p-8 text-center">
            <Icon name="lucide:lock" class="mx-auto size-6 text-muted-foreground" />
            <h2 class="mt-3 op-title">Contagem restrita ao gestor</h2>
            <p class="mx-auto mt-1 max-w-md op-body text-muted-foreground">
              Auditar e ajustar o estoque de insumos pede a permissão de auditoria. Entre com o operador do gestor para contar.
            </p>
          </div>

          <div v-else class="overflow-hidden rounded-lg border border-border bg-card">
            <p class="border-b border-border px-4 py-3 op-label font-normal text-muted-foreground">Informe o que contou no físico. Divergência pede motivo e vira ajuste no estoque.</p>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[48rem] op-body">
                <thead class="bg-muted/60 text-left text-muted-foreground">
                  <tr class="h-10"><th class="pr-2 pl-4 op-eyebrow">Insumo</th><th class="px-3 text-right op-eyebrow">Sistema</th><th class="px-3 op-eyebrow">Contado</th><th class="px-3 op-eyebrow">Diferença</th><th class="px-3 op-eyebrow">Motivo</th></tr>
                </thead>
                <tbody>
                  <tr v-for="row in countFilteredRows" :key="row.item.sku" class="h-16 border-t border-border hover:bg-accent/60">
                    <td class="py-2 pr-2 pl-4">
                      <p class="font-semibold">{{ row.item.name }}</p>
                      <p class="op-micro text-muted-foreground"><span class="font-mono">{{ row.item.sku }}</span> · {{ row.item.category }}</p>
                    </td>
                    <td class="px-3 text-right whitespace-nowrap tnum">{{ formatQty(row.item.systemQty, row.item.unit) }}</td>
                    <td class="px-3">
                      <input
                        :value="row.input"
                        type="text"
                        inputmode="decimal"
                        :placeholder="`0 ${row.item.unit}`"
                        :aria-label="`Quantidade contada de ${row.item.name}`"
                        class="h-10 w-28 rounded-md bg-card px-3 text-right font-semibold tnum"
                        :class="row.input ? 'border-2 border-primary' : 'border border-input'"
                        @input="setCountInput(row.item.sku, ($event.target as HTMLInputElement).value)"
                      />
                    </td>
                    <td class="px-3">
                      <span
                        v-if="row.counted !== null"
                        class="inline-flex h-6 items-center gap-1.5 rounded-full px-2 op-micro font-semibold tnum"
                        :class="row.divergent ? (row.diff < 0 ? 'pill-destructive' : 'pill-warning') : 'pill-success'"
                      >
                        <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />
                        {{ row.divergent ? formatQtyDiff(row.diff, row.item.unit) : "Confere" }}
                      </span>
                      <span v-else class="op-micro text-muted-foreground">não contado</span>
                    </td>
                    <td class="px-3">
                      <input
                        v-if="row.divergent"
                        :value="row.reason"
                        type="text"
                        placeholder="Por que divergiu?"
                        :aria-label="`Motivo da divergência de ${row.item.name}`"
                        class="h-10 w-56 rounded-md border bg-card px-3 op-body"
                        :class="row.missingReason ? 'border-destructive/50' : 'border-input'"
                        @input="setCountReason(row.item.sku, ($event.target as HTMLInputElement).value)"
                      />
                      <span v-else class="op-micro text-muted-foreground">sem divergência</span>
                    </td>
                  </tr>
                  <tr v-if="!countFilteredRows.length">
                    <td colspan="5" class="px-4 py-8 text-center text-muted-foreground">
                      {{ countPending ? "Carregando posições do estoque..." : "Nenhum insumo para contar." }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3">
              <div class="op-label font-normal text-muted-foreground">
                <span class="font-semibold text-foreground tnum">{{ countTotals.filled }}</span> {{ countTotals.filled === 1 ? "contado" : "contados" }} ·
                <span class="font-semibold text-foreground tnum">{{ countTotals.divergent }}</span> {{ countTotals.divergent === 1 ? "divergência" : "divergências" }}
                <span v-if="countTotals.missingReason" class="text-destructive"> · {{ countTotals.missingReason }} sem motivo</span>
                <span v-if="countConfirmedAt" class="text-success"> · Última contagem lançada {{ countConfirmedAt }}</span>
              </div>
              <div class="flex items-center gap-2">
                <button type="button" class="min-h-control rounded-md border border-border bg-card px-4 op-label hover:bg-accent disabled:opacity-50" :disabled="actionPending || !countTotals.filled" @click="resetCount">
                  Limpar
                </button>
                <button type="button" class="inline-flex min-h-control items-center gap-2 rounded-md bg-primary px-5 op-label font-semibold text-primary-foreground disabled:opacity-50" :disabled="actionPending || countPending || !countReady" @click="openCountConfirm">
                  <Icon name="lucide:clipboard-check" class="size-4" />
                  Lançar contagem
                </button>
              </div>
            </div>
          </div>
        </section>
      </section>
    </div>

    <div v-if="countConfirmOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-label="Confirmar contagem">
      <div class="w-full max-w-lg rounded-xl border border-border bg-card p-5 shadow-lg">
        <div class="flex items-start gap-3">
          <Icon name="lucide:clipboard-check" class="mt-0.5 size-5 text-muted-foreground" />
          <div>
            <h2 class="op-title">Lançar a contagem no estoque?</h2>
            <p class="mt-1 op-body text-muted-foreground">
              Cada divergência vira um ajuste definitivo no livro de estoque, registrado com o seu usuário e o motivo informado.
            </p>
          </div>
        </div>
        <div v-if="countDivergentRows.length" class="mt-4 max-h-64 space-y-2 overflow-y-auto">
          <div v-for="row in countDivergentRows" :key="row.item.sku" class="rounded-lg border border-border bg-background p-3">
            <div class="flex items-center justify-between gap-2">
              <p class="op-label font-semibold">{{ row.item.name }}</p>
              <span class="op-label font-semibold tnum" :class="row.diff < 0 ? 'text-destructive' : 'text-warning'">{{ formatQtyDiff(row.diff, row.item.unit) }}</span>
            </div>
            <p class="op-micro text-muted-foreground tnum">{{ formatQty(row.item.systemQty, row.item.unit) }} no sistema · {{ formatQty(row.counted ?? 0, row.item.unit) }} contado</p>
            <p class="mt-1 op-micro">{{ row.reason }}</p>
          </div>
        </div>
        <p v-else class="mt-4 rounded-lg border border-success/25 bg-success/10 p-3 op-body text-success">
          Sem divergência: a contagem confirma o saldo do sistema e nenhum ajuste será lançado.
        </p>
        <div class="mt-4 flex items-center justify-end gap-2">
          <button type="button" class="min-h-control rounded-md border border-border bg-card px-4 op-label hover:bg-accent" :disabled="actionPending" @click="countConfirmOpen = false">
            Voltar
          </button>
          <button
            type="button"
            class="inline-flex min-h-control items-center gap-2 rounded-md px-4 op-label font-semibold disabled:opacity-50"
            :class="countDivergentRows.length ? 'border border-destructive/30 text-destructive hover:bg-destructive/10' : 'bg-primary text-primary-foreground'"
            :disabled="actionPending"
            @click="submitCount"
          >
            <Icon :name="actionPending ? 'lucide:loader-circle' : 'lucide:check'" class="size-4" :class="actionPending ? 'animate-spin' : ''" />
            Confirmar ajustes
          </button>
        </div>
      </div>
    </div>

    <div v-if="scannerOpen" class="fixed inset-0 z-50 flex flex-col bg-black p-3 text-white md:p-6" role="dialog" aria-modal="true" aria-label="Escanear NF">
      <div class="flex items-center justify-between gap-3 pb-3">
        <button type="button" class="inline-flex size-12 items-center justify-center rounded-full bg-white/10" aria-label="Fechar câmera" @click="() => stopInvoiceScanner()">
          <Icon name="lucide:x" class="size-6" />
        </button>
        <div class="text-center">
          <p class="op-eyebrow text-white/60">Receber</p>
          <h2 class="op-title">Escanear NF</h2>
        </div>
        <button v-if="scannerCanTorch" type="button" class="inline-flex size-12 items-center justify-center rounded-full" :class="scannerTorchOn ? 'bg-suite-badge text-suite-badge-foreground' : 'bg-white/10'" :aria-label="scannerTorchOn ? 'Desligar lanterna' : 'Ligar lanterna'" @click="toggleScannerTorch">
          <Icon :name="scannerTorchOn ? 'lucide:flashlight-off' : 'lucide:flashlight'" class="size-6" />
        </button>
        <span v-else class="size-12" aria-hidden="true" />
      </div>
      <div class="relative min-h-0 flex-1 overflow-hidden rounded-2xl bg-zinc-950">
        <video ref="scannerVideo" muted playsinline class="h-full w-full object-cover" />
        <div class="pointer-events-none absolute inset-x-8 top-1/2 h-40 -translate-y-1/2 rounded-xl border-4 border-success/90 shadow-[0_0_0_999px_rgba(0,0,0,0.35)]" />
      </div>
      <p class="mx-auto mt-3 flex max-w-xl items-start gap-2 rounded-xl bg-white/10 px-4 py-3 op-body text-white/90">
        <Icon name="lucide:smartphone" class="mt-0.5 size-5 shrink-0" />
        <span>
          {{ scannerHint || "Aponte para o QR ou código de barras da nota." }}
          Para barras, deixe a linha inteira visível, na horizontal, sem cortar as laterais.
        </span>
      </p>
      <div class="mx-auto mt-3 grid w-full max-w-xl grid-cols-1 gap-2">
        <button type="button" class="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-white/10 op-title" @click="() => { stopInvoiceScanner(); openInvoiceImagePicker(); }">
          <Icon name="lucide:image-up" class="size-5" />
          Ler foto da NF
        </button>
      </div>
    </div>
  </main>
</template>

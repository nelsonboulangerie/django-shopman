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
  receiptOutcomeSummary,
  isApproximateCost,
  purchaseUnitLabel,
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
  receiptWatchWarnings,
  receiptPendingLines,
  receiptDocumentBlockers,
  receiptSupplierBlockers,
  receiptCheckedCount,
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

const countConfirmOpen = ref(false);

function openCountConfirm() {
  if (countReady.value) countConfirmOpen.value = true;
}

async function submitCount() {
  const ok = await confirmCount();
  if (ok) countConfirmOpen.value = false;
}

const invoiceShortKey = computed(() =>
  invoiceStatus.value.accessKey ?
    `${invoiceStatus.value.accessKey.slice(0, 4)} ${invoiceStatus.value.accessKey.slice(4, 8)} ... ${invoiceStatus.value.accessKey.slice(-6)}`
  : "—",
);

// Conta ITENS travados, não avisos: uma linha que precisa de insumo E de
// validade é um item para resolver, não dois bloqueios. O número tem de bater
// com o tamanho da lista logo abaixo dele, senão vira ruído — e com o que
// realmente segura o `Confirmar entrada`, inclusive a linha pronta que ninguém
// marcou como conferida.
const receiptTotalPending = computed(
  () => receiptPendingLines.value.length + receiptDocumentBlockers.value.length + receiptSupplierBlockers.value.length,
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
    scannerError.value = "Lanterna indisponível neste aparelho. Use boa luz e mantenha o código inteiro no quadro.";
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

onBeforeUnmount(stopInvoiceScanner);
</script>

<template>
  <main class="flex flex-1 flex-col gap-4 overflow-x-hidden p-3 pb-24 md:p-4 md:pb-4">
    <section
      v-if="(pending && !backendReady) || readonlyFallback || actionError"
      class="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-card px-3 py-2 text-sm"
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
      <button type="button" class="h-8 rounded-md border border-border px-2.5 text-xs font-medium hover:bg-accent" @click="refresh()">
        Atualizar
      </button>
    </section>

    <section
      v-if="readonlyFallback"
      class="rounded-md border border-warning/30 bg-warning/10 p-4 text-warning"
      aria-live="polite"
    >
      <div class="flex items-start gap-3">
        <Icon name="lucide:shield-alert" class="mt-0.5 size-5 shrink-0" />
        <div>
          <h2 class="font-semibold">{{ backendBlockTitle }}</h2>
          <p class="mt-1 text-sm">{{ backendBlockMessage }}</p>
        </div>
      </div>
    </section>

    <section v-if="view === 'panel'" class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <div class="space-y-4">
        <section class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Painel de compras">
          <button type="button" class="rounded-md border border-border bg-card p-4 text-left transition hover:bg-accent" @click="view = 'buy'">
            <p class="flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <Icon name="lucide:shopping-cart" class="size-4 text-warning" />
              Comprar
            </p>
            <p class="mt-2 text-3xl font-bold tabular-nums">{{ reorderRows.length }}</p>
            <p class="mt-1 text-xs text-muted-foreground">{{ formatMoney(purchaseTotalQ) }} estimados</p>
          </button>
          <button type="button" class="rounded-md border border-border bg-card p-4 text-left transition hover:bg-accent" @click="view = 'receive'">
            <p class="flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <Icon name="lucide:package-check" class="size-4 text-success" />
              Receber
            </p>
            <p class="mt-2 text-3xl font-bold tabular-nums">{{ receiptCheckedCount }}/{{ receiptLinePreviews.length }}</p>
            <p class="mt-1 text-xs text-muted-foreground">{{ receiptTotalPending }} pendências</p>
          </button>
          <button type="button" class="rounded-md border border-border bg-card p-4 text-left transition hover:bg-accent" @click="openBase('costs')">
            <p class="flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <Icon name="lucide:equal-approximately" class="size-4 text-info" />
              Conversões
            </p>
            <p class="mt-2 text-3xl font-bold tabular-nums">{{ metrics.approximatePreferred }}</p>
            <p class="mt-1 text-xs text-muted-foreground">custos estimados</p>
          </button>
          <button type="button" class="rounded-md border border-border bg-card p-4 text-left transition hover:bg-accent" @click="openBase('materials')">
            <p class="flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <Icon name="lucide:database" class="size-4" />
              Base
            </p>
            <p class="mt-2 text-3xl font-bold tabular-nums">{{ metrics.activeMaterials }}</p>
            <p class="mt-1 text-xs text-muted-foreground">{{ metrics.missingPreferred }} sem custo preferencial</p>
          </button>
        </section>

        <section class="rounded-md border border-border bg-card">
          <div class="border-b border-border p-4">
            <h1 class="text-xl font-semibold">Painel do Compras</h1>
            <p class="mt-1 text-sm text-muted-foreground">Fila de decisão operacional.</p>
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
                <p class="font-semibold">{{ blocker.headline }}</p>
                <p class="mt-1 text-sm text-muted-foreground">{{ blocker.detail }}</p>
                <button
                  v-if="blocker.action"
                  type="button"
                  class="mt-2 inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-sm font-medium hover:bg-accent"
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
              class="flex w-full items-center justify-between gap-3 p-4 text-left transition hover:bg-accent"
              @click="view = 'buy'"
            >
              <span class="min-w-0">
                <span class="block font-semibold">{{ row.material.name }}</span>
                <span class="mt-0.5 block text-sm text-muted-foreground">
                  {{ coverageLabel(row.material.coverageDays) }} · sugerir {{ formatQty(row.suggestedQty, row.material.unit) }}
                </span>
              </span>
              <span class="shrink-0 rounded-md border border-warning/30 bg-warning/10 px-2 py-1 text-xs font-medium text-warning">
                Comprar
              </span>
            </button>
            <button type="button" class="flex w-full items-center justify-between gap-3 p-4 text-left transition hover:bg-accent" @click="view = 'receive'">
              <span class="min-w-0">
                <span class="block font-semibold">Recebimento em conferência</span>
                <span class="mt-0.5 block text-sm text-muted-foreground">{{ receiptCheckedCount }} de {{ receiptLinePreviews.length }} itens conferidos</span>
              </span>
              <span class="shrink-0 rounded-md border px-2 py-1 text-xs font-medium" :class="receiptReady ? 'border-success/25 bg-success/10 text-success' : 'border-warning/30 bg-warning/10 text-warning'">
                {{ receiptReady ? "Pronto" : "Revisar" }}
              </span>
            </button>
            <button
              v-for="item in integrityQueue.slice(0, 4)"
              :key="`panel-integrity-${item.material.sku}-${item.issue.key}`"
              type="button"
              class="flex w-full items-center justify-between gap-3 p-4 text-left transition hover:bg-accent"
              @click="selectMaterialAndView(item.material)"
            >
              <span class="min-w-0">
                <span class="block font-semibold">{{ item.material.name }}</span>
                <span class="mt-0.5 block text-sm text-muted-foreground">{{ item.issue.label }}</span>
              </span>
              <span class="shrink-0 rounded-md border px-2 py-1 text-xs font-medium" :class="toneClasses[item.issue.tone]">
                {{ toneLabels[item.issue.tone] }}
              </span>
            </button>
          </div>
        </section>
      </div>

      <aside class="space-y-3">
        <button type="button" class="flex h-16 w-full items-center gap-3 rounded-md bg-primary px-4 text-left font-semibold text-primary-foreground" @click="openReceive('invoice')">
          <Icon name="lucide:scan-line" class="size-5" />
          Escanear NF
        </button>
        <button type="button" class="flex h-14 w-full items-center gap-3 rounded-md border border-border bg-card px-4 text-left font-semibold hover:bg-accent" @click="view = 'buy'">
          <Icon name="lucide:shopping-cart" class="size-5" />
          Revisar compras
        </button>
        <button type="button" class="flex h-14 w-full items-center gap-3 rounded-md border border-border bg-card px-4 text-left font-semibold hover:bg-accent" @click="openReceive('manual')">
          <Icon name="lucide:clipboard-pen-line" class="size-5" />
          Entrada sem NF
        </button>
        <button type="button" class="flex h-14 w-full items-center gap-3 rounded-md border border-border bg-card px-4 text-left font-semibold hover:bg-accent" @click="openBase('materials')">
          <Icon name="lucide:database" class="size-5" />
          Consultar Base
        </button>
      </aside>
    </section>

    <section v-else-if="view === 'buy'" class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <section class="rounded-md border border-border bg-card">
        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-border p-4">
          <div>
            <h1 class="text-xl font-semibold">Comprar</h1>
            <p class="mt-1 text-sm text-muted-foreground">Solicitações consolidadas por estoque, produção e operação.</p>
          </div>
          <span class="rounded-md border border-border bg-background px-2.5 py-1 text-xs font-medium">
            {{ purchaseSupplierCount }} fornecedor(es)
          </span>
        </div>

        <!-- Zero explicado: sem isto, "não precisa comprar nada" e "o app não
             consegue calcular" são a mesma tela vazia. -->
        <div v-if="!reorderRows.length && reorderBlockers.length" class="space-y-3 p-4">
          <div
            v-for="blocker in reorderBlockers"
            :key="`buy-blocker-${blocker.key}`"
            class="rounded-md border border-border bg-background p-4"
          >
            <div class="flex items-start gap-3">
              <Icon
                :name="blocker.key === 'stocked' ? 'lucide:circle-check' : 'lucide:info'"
                class="mt-0.5 size-5 shrink-0"
                :class="blocker.key === 'stocked' ? 'text-success' : 'text-info'"
              />
              <div class="min-w-0">
                <h2 class="font-semibold">{{ blocker.headline }}</h2>
                <p class="mt-1 text-sm text-muted-foreground">{{ blocker.detail }}</p>
                <button
                  v-if="blocker.action"
                  type="button"
                  class="mt-3 inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-sm font-medium hover:bg-accent"
                  @click="openBase(blocker.action.baseView)"
                >
                  <Icon name="lucide:arrow-right" class="size-4" />
                  {{ blocker.action.label }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="grid gap-3 p-3 md:grid-cols-2 2xl:grid-cols-3">
          <article v-for="row in reorderRows" :key="row.material.sku" class="rounded-md border border-border bg-background p-3">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <h2 class="truncate font-semibold">{{ row.material.name }}</h2>
                <p class="mt-0.5 text-xs text-muted-foreground">{{ row.material.sku }} · {{ row.material.category }}</p>
              </div>
              <span class="shrink-0 rounded-md border px-2 py-1 text-xs font-medium" :class="requestStatusClasses[purchaseRequestStatus(row.material.sku)]">
                {{ requestStatusLabels[purchaseRequestStatus(row.material.sku)] }}
              </span>
            </div>
            <dl class="mt-4 grid grid-cols-2 gap-3 text-sm">
              <div><dt class="text-xs text-muted-foreground">Cobertura</dt><dd class="font-semibold tabular-nums">{{ coverageLabel(row.material.coverageDays) }}</dd></div>
              <div><dt class="text-xs text-muted-foreground">Sugestão</dt><dd class="font-semibold tabular-nums">{{ formatQty(row.suggestedQty, row.material.unit) }}</dd></div>
              <div><dt class="text-xs text-muted-foreground">Fornecedor</dt><dd class="truncate font-semibold">{{ row.supplier?.name || "Definir" }}</dd></div>
              <div><dt class="text-xs text-muted-foreground">Estimado</dt><dd class="font-semibold tabular-nums">{{ formatMoney(row.estimatedCostQ) }}</dd></div>
            </dl>
            <div class="mt-4 grid grid-cols-2 gap-2">
              <button type="button" class="h-10 rounded-md border border-border px-3 text-sm font-medium hover:bg-accent" @click="openQuoteFor(row.material, row.supplier?.ref)">Ajustar</button>
              <button type="button" class="h-10 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-50" :disabled="readonlyFallback || purchaseRequestStatus(row.material.sku) === 'sent' || actionPending" @click="sendPurchaseRequest(row.material.sku)">
                {{ purchaseRequestStatus(row.material.sku) === "sent" ? "Enviado" : "Enviar pedido" }}
              </button>
            </div>
          </article>
        </div>
      </section>

      <aside class="rounded-md border border-border bg-card p-4">
        <h2 class="text-lg font-semibold">Consolidação</h2>
        <dl class="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div><dt class="text-xs text-muted-foreground">Solicitações</dt><dd class="font-semibold tabular-nums">{{ reorderRows.length }}</dd></div>
          <div><dt class="text-xs text-muted-foreground">Fornecedores</dt><dd class="font-semibold tabular-nums">{{ purchaseSupplierCount }}</dd></div>
          <div class="col-span-2"><dt class="text-xs text-muted-foreground">Total previsto</dt><dd class="font-semibold tabular-nums">{{ formatMoney(purchaseTotalQ) }}</dd></div>
        </dl>
        <div class="mt-4 space-y-2">
          <button type="button" class="h-10 w-full rounded-md border border-border px-3 text-sm font-medium hover:bg-accent" @click="openBase('suppliers')">Fornecedores</button>
          <button type="button" class="h-10 w-full rounded-md border border-border px-3 text-sm font-medium hover:bg-accent" @click="openBase('costs')">Custos e conversões</button>
        </div>
      </aside>
    </section>

    <section v-else-if="view === 'receive'" class="grid min-h-0 gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
      <div class="min-w-0 space-y-4">
        <!-- Deu certo, e a tela diz isso onde o olho está: no topo, do tamanho
             do que aconteceu, com o que entrou escrito por extenso. O gesto
             seguinte fica dentro do próprio aviso — quem deu entrada numa nota
             quase sempre tem a próxima na mão. -->
        <section
          v-if="receiptOutcome"
          data-receipt-outcome
          class="scroll-mt-4 rounded-md border p-4"
          :class="receiptOutcome.kind === 'confirmed' ? 'border-success/40 bg-success/10' : 'border-warning/40 bg-warning/10'"
          aria-live="polite"
        >
          <div class="flex items-start gap-3">
            <Icon
              :name="receiptOutcome.kind === 'confirmed' ? 'lucide:circle-check-big' : 'lucide:undo-2'"
              class="mt-0.5 size-6 shrink-0"
              :class="receiptOutcome.kind === 'confirmed' ? 'text-success' : 'text-warning'"
            />
            <div class="min-w-0 flex-1">
              <h2 class="text-lg font-semibold" :class="receiptOutcome.kind === 'confirmed' ? 'text-success' : 'text-warning'">
                {{ receiptOutcome.kind === "confirmed" ? "Entrada confirmada no estoque" : "Devolução registrada" }}
              </h2>
              <p class="mt-1 text-sm text-foreground">{{ receiptOutcomeSummary(receiptOutcome) }}</p>
              <p class="mt-0.5 text-xs text-muted-foreground">{{ receiptOutcome.at }}</p>
              <div class="mt-3 flex flex-col gap-2 sm:flex-row">
                <button type="button" class="inline-flex h-12 items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground disabled:opacity-50" :disabled="readonlyFallback || actionPending" @click="startNextReceipt">
                  <Icon :name="receiptOutcome.mode === 'manual' ? 'lucide:clipboard-pen-line' : 'lucide:scan-line'" class="size-4" />
                  {{ receiptOutcome.mode === "manual" ? "Lançar outra entrada" : "Escanear outra NF" }}
                </button>
                <button type="button" class="inline-flex h-12 items-center justify-center gap-2 rounded-md border border-border bg-card px-4 text-sm font-semibold hover:bg-accent" @click="dismissReceiptOutcome">
                  <Icon name="lucide:x" class="size-4" />
                  Fechar
                </button>
              </div>
            </div>
          </div>
        </section>

        <section class="rounded-md border border-border bg-card">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-border p-4">
            <div>
              <p class="text-xs font-medium text-muted-foreground">Compras</p>
              <h1 class="mt-1 text-xl font-semibold">Receber materiais</h1>
            </div>
            <!-- No celular o par ocupa a linha inteira: dois botões encolhidos
                 num canto ficam pequenos para o dedo e desalinhados com o resto. -->
            <div class="flex w-full rounded-md bg-muted p-1 sm:inline-flex sm:w-auto">
              <button type="button" class="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-md px-3 text-sm transition sm:flex-none" :class="receiptMode === 'invoice' ? 'bg-card font-semibold shadow-sm' : 'text-muted-foreground hover:bg-card/60'" @click="setReceiptMode('invoice')">
                <Icon name="lucide:scan-line" class="size-4" />
                Com NF
              </button>
              <button type="button" class="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-md px-3 text-sm transition sm:flex-none" :class="receiptMode === 'manual' ? 'bg-card font-semibold shadow-sm' : 'text-muted-foreground hover:bg-card/60'" @click="setReceiptMode('manual')">
                <Icon name="lucide:clipboard-pen-line" class="size-4" />
                Sem NF
              </button>
            </div>
          </div>

          <div class="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
            <div class="space-y-3">
              <button v-if="receiptMode === 'invoice'" type="button" class="flex h-14 w-full items-center justify-center gap-2 rounded-md bg-primary px-4 font-semibold text-primary-foreground disabled:opacity-50" :disabled="readonlyFallback || actionPending || scannerOpen" @click="openInvoiceScanner">
                <Icon :name="actionPending ? 'lucide:loader-circle' : 'lucide:camera'" class="size-5" :class="actionPending ? 'animate-spin' : ''" />
                {{ actionPending ? "Lendo NF" : "Escanear NF" }}
              </button>
              <p v-if="scannerError" class="rounded-md border border-warning/30 bg-warning/10 p-2 text-sm text-warning">
                {{ scannerError }}
              </p>
              <label v-if="receiptMode === 'invoice'" data-receipt-anchor="invoice" class="block scroll-mt-4 p-0.5 text-sm font-medium transition-shadow" :class="anchorRing('invoice')">
                QR, código de barras ou chave da NF
                <textarea v-model="invoiceInput" rows="3" class="mt-1 w-full resize-none rounded-md border border-border bg-background px-3 py-2 text-sm" placeholder="Escaneie, cole ou digite a chave de acesso" />
              </label>
              <button
                v-if="receiptMode === 'invoice'"
                type="button"
                class="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md border border-border px-3 text-sm font-semibold hover:bg-accent disabled:opacity-50"
                :disabled="readonlyFallback || actionPending || !invoiceInput.trim()"
                @click="readInvoice"
              >
                <Icon :name="actionPending ? 'lucide:loader-circle' : 'lucide:file-check-2'" class="size-4" :class="actionPending ? 'animate-spin' : ''" />
                {{ actionPending ? "Traduzindo" : "Traduzir NF" }}
              </button>
              <button
                v-if="receiptMode === 'invoice'"
                type="button"
                class="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md border border-border px-3 text-sm font-semibold hover:bg-accent disabled:opacity-50"
                :disabled="readonlyFallback || actionPending"
                @click="openInvoiceImagePicker"
              >
                <Icon name="lucide:image-up" class="size-4" />
                Ler foto da NF
              </button>
              <input ref="scannerFileInput" class="sr-only" type="file" accept="image/*" capture="environment" @change="readInvoiceImage" />
              <label v-if="receiptMode !== 'invoice'" class="block text-sm font-medium">
                Referência em papel
                <textarea v-model="receiptNote" rows="3" class="mt-1 w-full resize-none rounded-md border border-border bg-background px-3 py-2 text-sm" placeholder="Romaneio, produtor, observação" />
              </label>

              <div class="flex flex-wrap items-center gap-2">
                <span v-if="receiptMode === 'invoice'" class="inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium" :class="invoiceStatus.valid ? 'border-success/25 bg-success/10 text-success' : 'border-destructive/30 bg-destructive/10 text-destructive'">
                  <Icon :name="invoiceStatus.valid ? 'lucide:check' : 'lucide:scan-line'" class="size-3.5" />
                  {{ invoiceStatus.valid ? `Chave ${invoiceShortKey}` : "Aguardando NF" }}
                </span>
                <span v-else class="inline-flex h-8 items-center gap-1.5 rounded-md border border-warning/30 bg-warning/10 px-2.5 text-xs font-medium text-warning">
                  <Icon name="lucide:badge-alert" class="size-3.5" />
                  Sem documento fiscal
                </span>
              </div>
            </div>

            <div class="space-y-3">
              <label data-receipt-anchor="supplier" class="block scroll-mt-4 p-0.5 text-sm font-medium transition-shadow" :class="anchorRing('supplier')">
                Fornecedor
                <select :value="receiptSupplierRef" class="mt-1 h-10 w-full rounded-md border border-border bg-background px-3 text-sm" @change="onReceiptSupplierChange">
                  <option value="">Definir fornecedor</option>
                  <option v-for="supplier in suppliers" :key="supplier.ref" :value="supplier.ref">{{ supplier.displayName }}</option>
                </select>
              </label>
              <div class="rounded-md border border-border bg-background p-3 text-sm">
                <p class="text-xs font-medium text-muted-foreground">Documento</p>
                <p class="mt-1 font-semibold">{{ receiptSupplier?.document || "—" }}</p>
                <p class="mt-1 text-xs text-muted-foreground">{{ receiptSupplier?.paymentTerm || "—" }} · {{ receiptSupplier?.leadTimeDays ?? 0 }} dia(s)</p>
              </div>
            </div>
          </div>
        </section>

        <section class="rounded-md border border-border bg-card">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-border p-4">
            <div>
              <h2 class="text-lg font-semibold">Itens da entrada</h2>
              <p class="text-sm text-muted-foreground">{{ receiptCheckedCount }} de {{ receiptLinePreviews.length }} conferidos</p>
            </div>
            <button type="button" class="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-sm font-medium hover:bg-accent" @click="addAndOpenReceiptLine">
              <Icon name="lucide:plus" class="size-4" />
              Item
            </button>
          </div>

          <!-- A LISTA da entrada: uma linha por item, e o que falta dito na
               própria linha. Eram formulários abertos empilhados — para saber
               como estava uma nota de dez itens, o operador rolava dez cards.
               Tocar na linha abre a gaveta daquele item.

               `min-w-0` no item da lista: sem ele a coluna é dimensionada pelo
               min-content do nome mais comprido e passa da largura do telefone.
               O corte ficava invisível atrás do `overflow-x-hidden` do main. -->
          <ul v-if="receiptRows.length" class="grid min-w-0 gap-2 p-3">
            <li
              v-for="row in receiptRows"
              :key="row.id"
              :data-receipt-line="row.id"
              class="flex min-w-0 scroll-mt-4 items-stretch gap-1 rounded-md border pr-1 transition-colors"
              :class="RECEIPT_LINE_STATUS_ROW[row.status]"
            >
              <button
                type="button"
                class="flex min-w-0 flex-1 items-center gap-3 rounded-md py-2.5 pl-3 text-left"
                :aria-label="`Abrir ${row.label}`"
                @click="openReceiptLine(row.id)"
              >
                <Icon :name="row.statusIcon" class="size-5 shrink-0" :class="RECEIPT_LINE_STATUS_TEXT[row.status]" />
                <span class="min-w-0 flex-1">
                  <span class="block truncate text-sm font-medium">{{ row.label }}</span>
                  <span v-if="row.digest" class="block truncate text-xs text-muted-foreground">{{ row.digest }}</span>
                  <!-- A pendência mora na LINHA. Era isto que obrigava a abrir
                       o item para descobrir que faltava a validade dele. -->
                  <span v-if="row.nextStep" class="block truncate text-xs font-medium text-destructive">{{ row.nextStep }}</span>
                  <span v-else-if="row.note" class="block truncate text-xs text-warning">{{ row.note }}</span>
                </span>
                <span class="flex shrink-0 flex-col items-end gap-1">
                  <span v-if="row.total" class="text-sm font-semibold tabular-nums">{{ row.total }}</span>
                  <span
                    class="inline-flex h-6 items-center rounded-md border px-1.5 text-xs font-medium"
                    :class="RECEIPT_LINE_STATUS_BADGE[row.status]"
                  >
                    {{ row.statusLabel }}
                  </span>
                </span>
                <Icon name="lucide:chevron-right" class="size-4 shrink-0 text-muted-foreground" />
              </button>
              <button
                type="button"
                class="inline-flex w-11 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-destructive"
                :aria-label="`Remover ${row.label}`"
                @click="removeReceiptLine(row.id)"
              >
                <Icon name="lucide:trash-2" class="size-4" />
              </button>
            </li>
          </ul>
          <p v-else class="px-4 py-6 text-center text-sm text-muted-foreground">
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

      <aside class="min-w-0 rounded-md border border-border bg-card p-4">
        <h2 class="text-lg font-semibold">Conferência</h2>
        <dl class="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div><dt class="text-xs text-muted-foreground">Origem</dt><dd class="font-semibold">{{ receiptMode === "invoice" ? "NF" : "Sem NF" }}</dd></div>
          <div><dt class="text-xs text-muted-foreground">Itens</dt><dd class="font-semibold tabular-nums">{{ receiptCheckedCount }}/{{ receiptLinePreviews.length }}</dd></div>
          <div><dt class="text-xs text-muted-foreground">Valor</dt><dd class="font-semibold tabular-nums">{{ formatMoney(receiptTotalCostQ) }}</dd></div>
          <div><dt class="text-xs text-muted-foreground">Pendências</dt><dd class="font-semibold tabular-nums" :class="receiptTotalPending ? 'text-destructive' : 'text-success'">{{ receiptTotalPending }}</dd></div>
        </dl>

        <div class="mt-4 rounded-md border border-border bg-background p-3">
          <p class="text-xs font-medium text-muted-foreground">{{ receiptMode === "invoice" ? "Chave NF" : "Fornecedor" }}</p>
          <p class="mt-1 break-words text-sm font-semibold">{{ receiptMode === "invoice" ? invoiceShortKey : receiptSupplier?.name }}</p>
        </div>

        <label v-if="receiptMode === 'invoice'" class="mt-4 block text-sm font-medium">
          Ressalva geral
          <textarea v-model="receiptNote" rows="3" class="mt-1 w-full resize-none rounded-md border border-border bg-background px-3 py-2 text-sm" placeholder="Avaria, falta, devolução, observação na NF/CT-e" />
        </label>

        <!-- Rascunho em branco não tem pendência: tem convite. Era daqui que
             saía o vermelho "Ler QR, código de barras ou chave da NF" logo
             depois de uma entrada dar certo — o rascunho zerava e a tela
             cobrava do zero. -->
        <div v-if="receiptIsBlank" class="mt-4 rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">
          Nada em conferência. Escaneie a NF da próxima entrega, ou lance sem NF.
        </div>

        <!-- Toda pendência é um GESTO: clicar leva ao campo que falta, não a
             uma acusação parada no rodapé. -->
        <div v-else-if="receiptDocumentBlockers.length || receiptSupplierBlockers.length || receiptPendingLines.length || uniqueWatchWarnings.length" class="mt-4 space-y-2">
          <button
            v-for="blocker in receiptDocumentBlockers"
            :key="blocker"
            type="button"
            class="block w-full min-w-0 rounded-md border p-2 text-left text-sm"
            :class="receiptWarningClasses.block"
            @click="focusReceiptAnchor('invoice')"
          >
            {{ blocker }}
          </button>
          <button
            v-for="blocker in receiptSupplierBlockers"
            :key="blocker"
            type="button"
            class="block w-full min-w-0 rounded-md border p-2 text-left text-sm"
            :class="receiptWarningClasses.block"
            @click="focusReceiptAnchor('supplier')"
          >
            {{ blocker }}
          </button>
          <button
            v-for="item in receiptPendingLines"
            :key="`pending-${item.id}`"
            type="button"
            class="block w-full min-w-0 rounded-md border p-2 text-left text-sm"
            :class="receiptWarningClasses[item.tone]"
            @click="focusReceiptLine(item.id, item.field)"
          >
            <span class="block truncate font-medium">{{ item.label }}</span>
            <span class="block text-xs opacity-80">{{ item.step }}</span>
          </button>
          <div v-for="(warning, index) in uniqueWatchWarnings" :key="`watch-${warning.key}-${index}`" class="rounded-md border p-2 text-sm" :class="receiptWarningClasses[warning.tone]">{{ warning.label }}</div>
        </div>

        <div v-if="!receiptIsBlank" class="mt-4 border-t border-border pt-4">
          <!-- O botão nunca fica mudo. Se ainda falta algo ele diz o quê, e ao
               ser apertado leva até o campo — botão cinza que não explica nada
               é o pior aviso que um formulário pode dar. -->
          <button type="button" class="inline-flex h-12 w-full items-center justify-center gap-2 rounded-md px-3 text-sm font-semibold disabled:opacity-50" :class="receiptReady ? 'bg-primary text-primary-foreground' : 'border border-border bg-card text-muted-foreground hover:bg-accent'" :disabled="readonlyFallback || actionPending" @click="onConfirmReceipt">
            <Icon :name="actionPending ? 'lucide:loader-circle' : receiptReady ? 'lucide:package-check' : 'lucide:list-checks'" class="size-4" :class="actionPending ? 'animate-spin' : ''" />
            {{ actionPending ? "Confirmando" : "Confirmar entrada" }}
          </button>
          <p v-if="!receiptReady && receiptFirstBlocker" class="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground">
            <Icon name="lucide:arrow-right" class="mt-0.5 size-3.5 shrink-0" />
            <span>
              {{ receiptFirstBlocker.step }}{{ receiptFirstBlocker.label ? ` em ${receiptFirstBlocker.label}` : "" }}<template v-if="receiptTotalPending > 1"> · e mais {{ receiptTotalPending - 1 }}</template>
            </span>
          </p>
          <button type="button" class="mt-2 inline-flex h-11 w-full items-center justify-center gap-2 rounded-md border border-destructive/30 px-3 text-sm font-semibold text-destructive hover:bg-destructive/10 disabled:opacity-50" :disabled="readonlyFallback || !receiptHasRejectionReason || actionPending" @click="onRejectReceipt">
            <Icon :name="actionPending ? 'lucide:loader-circle' : 'lucide:undo-2'" class="size-4" :class="actionPending ? 'animate-spin' : ''" />
            {{ actionPending ? "Registrando" : "Registrar devolução" }}
          </button>
        </div>
      </aside>
    </section>

    <section v-else class="space-y-4">
      <section class="rounded-md border border-border bg-card p-3">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 class="text-xl font-semibold">Base</h1>
            <p class="mt-1 text-sm text-muted-foreground">Referências usadas pelos fluxos de comprar e receber.</p>
          </div>
          <nav class="inline-flex overflow-x-auto rounded-md bg-muted p-1" aria-label="Base do compras">
            <button v-for="tab in baseTabs" :key="tab.key" type="button" class="inline-flex h-9 shrink-0 items-center gap-2 rounded-md px-3 text-sm transition" :class="baseView === tab.key ? 'bg-card font-semibold shadow-sm' : 'text-muted-foreground hover:bg-card/60'" @click="baseView = tab.key">
              <Icon :name="tab.icon" class="size-4" />
              {{ tab.label }}
            </button>
          </nav>
        </div>
      </section>

      <section v-if="baseView === 'materials'" class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <div class="rounded-md border border-border bg-card">
          <div class="flex flex-wrap items-center gap-3 border-b border-border p-3">
            <label class="relative min-w-64 flex-1">
              <Icon name="lucide:search" class="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <input v-model="query" type="search" placeholder="Buscar insumo" class="h-10 w-full rounded-md border border-border bg-background pl-9 pr-3 text-sm" />
            </label>
            <label class="flex h-10 items-center gap-2 rounded-md border border-border px-3 text-sm">
              <input v-model="onlyAlerts" type="checkbox" class="form-checkbox rounded border-border text-primary" />
              Atenção
            </label>
          </div>
          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-border text-sm">
              <thead class="bg-muted text-left text-xs font-medium text-muted-foreground">
                <tr><th class="px-3 py-2">SKU</th><th class="px-3 py-2">Insumo</th><th class="px-3 py-2">Estoque</th><th class="px-3 py-2">Cobertura</th><th class="px-3 py-2 w-32">Mínimo</th><th class="px-3 py-2">Custo-base</th><th class="px-3 py-2">Status</th></tr>
              </thead>
              <tbody class="divide-y divide-border">
                <tr v-for="material in filteredMaterials" :key="material.sku" class="hover:bg-accent/70">
                  <td class="px-3 py-2 font-mono text-xs">{{ material.sku }}</td>
                  <td class="px-3 py-2">
                    <button type="button" class="text-left font-semibold hover:underline" @click="selectMaterial(material.sku)">{{ material.name }}</button>
                    <p class="text-xs text-muted-foreground">{{ material.category }} · {{ material.recipes.join(", ") }}</p>
                  </td>
                  <td class="px-3 py-2 tabular-nums">{{ formatStockOnHand(material) }}</td>
                  <td class="px-3 py-2 tabular-nums">{{ coverageLabel(material.coverageDays) }}</td>
                  <!-- Sem consumo medido, o alvo de reposição é zero e o insumo
                       nunca vira sugestão. O mínimo declarado é o que destrava. -->
                  <td class="px-3 py-2">
                    <input
                      inputmode="decimal"
                      :placeholder="material.unit"
                      class="h-9 w-full rounded-md border bg-background px-2 text-sm tabular-nums"
                      :class="minStockLineErrors[material.sku] ? 'border-destructive' : 'border-border'"
                      :value="minStockInputs[material.sku] ?? ''"
                      @input="setMinStockInput(material.sku, ($event.target as HTMLInputElement).value)"
                    />
                    <!-- Declarado × derivado do consumo. O derivado NÃO vai no
                         placeholder: pré-preenchido, ele convida a "confirmar"
                         digitando o mesmo número — e isso congela um mínimo que
                         era para acompanhar o consumo. -->
                    <p class="mt-0.5 text-xs text-muted-foreground">
                      <template v-if="material.minStockDeclared">
                        definido: {{ formatQty(material.minStock, material.unit) }}
                      </template>
                      <template v-else-if="material.minStock">
                        pelo consumo: {{ formatQty(material.minStock, material.unit) }}
                      </template>
                      <template v-else>sem mínimo</template>
                    </p>
                    <p v-if="minStockLineErrors[material.sku]" class="mt-0.5 text-xs font-medium text-destructive">
                      {{ minStockLineErrors[material.sku] }}
                    </p>
                  </td>
                  <td class="px-3 py-2 tabular-nums">{{ formatMoney(material.preferredBaseCostQ) }} / {{ material.unit }}</td>
                  <td class="px-3 py-2">
                    <span class="rounded-md border px-2 py-1 text-xs font-medium" :class="toneClasses[material.tone]">{{ toneLabels[material.tone] }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div
            v-if="minStockFilledCount"
            class="flex flex-wrap items-center justify-between gap-3 border-t border-border p-3"
          >
            <p class="text-sm text-muted-foreground">
              {{ minStockFilledCount }} mínimo(s) para salvar · zero apaga o mínimo do insumo
            </p>
            <div class="flex gap-2">
              <button
                type="button"
                class="h-10 rounded-md border border-border px-3 text-sm font-medium hover:bg-accent disabled:opacity-50"
                :disabled="actionPending"
                @click="clearMinStock()"
              >
                Limpar
              </button>
              <button
                type="button"
                class="h-10 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground disabled:opacity-50"
                :disabled="readonlyFallback || actionPending"
                @click="saveMinStock()"
              >
                Salvar mínimos
              </button>
            </div>
          </div>
        </div>

        <aside v-if="selectedMaterial" class="rounded-md border border-border bg-card p-4">
          <h2 class="text-lg font-semibold">{{ selectedMaterial.name }}</h2>
          <p class="text-sm text-muted-foreground">{{ selectedMaterial.sku }} · {{ selectedMaterial.category }}</p>
          <div class="mt-4 space-y-2">
            <div v-for="issue in selectedMaterial.issues" :key="issue.key" class="rounded-md border p-2 text-sm" :class="toneClasses[issue.tone]">{{ issue.label }}</div>
            <p v-if="!selectedMaterial.issues.length" class="rounded-md border border-success/25 bg-success/10 p-2 text-sm text-success">Sem pontos de atenção</p>
          </div>
          <div class="mt-4 border-t border-border pt-4">
            <p class="text-xs font-medium text-muted-foreground">Receitas que consomem</p>
            <div class="mt-2 flex flex-wrap gap-2">
              <span v-for="recipe in selectedMaterial.recipes" :key="recipe" class="rounded-md border border-border px-2 py-1 text-xs">{{ recipe }}</span>
            </div>
          </div>
        </aside>
      </section>

      <section v-else-if="baseView === 'suppliers'" class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <div class="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
          <button v-for="summary in supplierSummaries" :key="summary.supplier.ref" type="button" class="rounded-md border p-3 text-left transition" :class="summary.supplier.ref === selectedSupplierRef ? 'border-primary bg-primary/5' : 'border-border bg-card hover:bg-accent'" @click="selectSupplier(summary.supplier.ref)">
            <div class="flex items-start justify-between gap-3">
              <div>
                <h2 class="font-semibold">{{ summary.supplier.displayName }}</h2>
                <p class="text-xs text-muted-foreground">{{ summary.supplier.ref }}</p>
              </div>
              <span class="rounded-md border px-2 py-1 text-xs font-medium" :class="summary.supplier.isActive ? 'border-success/25 bg-success/10 text-success' : 'border-border text-muted-foreground'">{{ summary.supplier.isActive ? "Ativo" : "Inativo" }}</span>
            </div>
            <div class="mt-3 grid grid-cols-3 gap-2 text-xs">
              <span><span class="block text-muted-foreground">Insumos</span><span class="font-semibold">{{ summary.materialsCovered }}</span></span>
              <span><span class="block text-muted-foreground">Prefer.</span><span class="font-semibold">{{ summary.preferredCount }}</span></span>
              <span><span class="block text-muted-foreground">SLA</span><span class="font-semibold">{{ summary.supplier.reliabilityPercent }}%</span></span>
            </div>
          </button>
        </div>

        <aside v-if="selectedSupplier" class="rounded-md border border-border bg-card p-4">
          <h2 class="text-lg font-semibold">{{ selectedSupplier.displayName }}</h2>
          <!-- A razao social so aparece quando difere do nome do dia a dia:
               repeti-la nas duas linhas nao informa nada. -->
          <p v-if="selectedSupplier.tradeName && selectedSupplier.name !== selectedSupplier.displayName" class="text-sm text-muted-foreground">
            {{ selectedSupplier.name }}
          </p>
          <p v-if="selectedSupplier.document" class="text-sm text-muted-foreground">{{ selectedSupplier.document }}</p>
          <dl class="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div><dt class="text-xs text-muted-foreground">Prazo</dt><dd class="font-semibold">{{ selectedSupplier.leadTimeDays }} dia(s)</dd></div>
            <div><dt class="text-xs text-muted-foreground">Entrega</dt><dd class="font-semibold">{{ selectedSupplier.reliabilityPercent }}%</dd></div>
            <div><dt class="text-xs text-muted-foreground">Última</dt><dd class="font-semibold">{{ formatShortDate(selectedSupplier.lastDeliveryAt) }}</dd></div>
            <div><dt class="text-xs text-muted-foreground">Pagamento</dt><dd class="font-semibold">{{ selectedSupplier.paymentTerm }}</dd></div>
          </dl>
          <div class="mt-4 border-t border-border pt-4">
            <div class="flex items-baseline justify-between gap-2">
              <h3 class="font-semibold">Contatos</h3>
              <!-- O cadastro de pessoa e config, e config se edita no Admin.
                   A tela mostra para conferir antes de enviar, nao para editar. -->
              <span class="text-xs text-muted-foreground">Cadastro no Admin</span>
            </div>

            <!-- A pergunta que o operador faz antes de apertar "enviar" e "vai
                 para quem?". Responder depois do envio nao serve. -->
            <p class="mt-2 text-xs" :class="selectedSupplier.orderContactName ? 'text-muted-foreground' : 'text-warning'">
              <template v-if="selectedSupplier.orderContactName">
                O pedido de compra vai para <span class="font-medium">{{ selectedSupplier.orderContactName }}</span>.
              </template>
              <template v-else-if="selectedSupplier.contact">
                Sem contato comercial — o pedido cai na central ({{ selectedSupplier.contact }}).
              </template>
              <template v-else>
                Sem contato e sem central: o pedido de compra nao tem para onde ir.
              </template>
            </p>

            <div v-if="activeSupplierContacts.length" class="mt-3 space-y-2">
              <div v-for="person in activeSupplierContacts" :key="person.id" class="rounded-md border border-border bg-background p-2">
                <div class="flex items-start justify-between gap-2">
                  <p class="font-medium">{{ person.name }}</p>
                  <span class="rounded-md border border-border px-2 py-0.5 text-xs text-muted-foreground">
                    {{ person.roleLabel }}<template v-if="person.isPrimary"> · principal</template>
                  </span>
                </div>
                <p v-if="person.email" class="text-xs text-muted-foreground">{{ person.email }}</p>
                <p v-if="person.phone" class="text-xs text-muted-foreground">{{ person.phone }}</p>
                <p v-if="person.notes" class="mt-1 text-xs text-muted-foreground">{{ person.notes }}</p>
              </div>
            </div>
          </div>

          <div class="mt-4 border-t border-border pt-4">
            <h3 class="font-semibold">Carteira</h3>
            <div class="mt-2 space-y-2">
              <div v-for="row in selectedSupplierPortfolio" :key="row.cost.id" class="rounded-md border border-border bg-background p-2">
                <div class="flex items-start justify-between gap-2">
                  <div>
                    <p class="font-medium">{{ row.material.name }}</p>
                    <p class="text-xs text-muted-foreground">{{ formatMoney(row.cost.costQ) }} / {{ row.unitLabel }}</p>
                  </div>
                  <span class="text-sm font-semibold tabular-nums"><span v-if="row.approximate">≈ </span>{{ formatMoney(row.baseCostQ) }}</span>
                </div>
              </div>
            </div>
          </div>
        </aside>
      </section>

      <section v-else-if="baseView === 'costs'" class="space-y-4">
        <!-- Tabela de preços do fornecedor: o gesto que tira dezenas de insumos
             do estado "sem custo preferencial" — e portanto fora de qualquer
             pedido — sem passar pelo Django Admin. -->
        <section class="rounded-md border border-border bg-card">
          <div class="flex flex-wrap items-end justify-between gap-3 border-b border-border p-4">
            <div>
              <h1 class="text-lg font-semibold">Tabela do fornecedor</h1>
              <p class="mt-1 text-sm text-muted-foreground">
                Escolha o fornecedor e preencha os que você sabe. Quem ficar em branco não entra.
              </p>
            </div>
            <div class="flex flex-wrap items-end gap-2">
              <label class="block text-sm font-medium">Fornecedor
                <select
                  v-model="batchSupplierRef"
                  class="mt-1 h-10 w-56 rounded-md border border-border bg-background px-3 text-sm"
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
                </select>
              </label>
              <input
                v-model="batchQuery"
                type="search"
                placeholder="Buscar insumo"
                class="h-10 w-48 rounded-md border border-border bg-background px-3 text-sm"
              />
              <label class="inline-flex h-10 items-center gap-2 text-sm">
                <input v-model="batchOnlyMissing" type="checkbox" class="size-4 rounded border-border" />
                Só os que faltam
              </label>
            </div>
          </div>

          <!-- "Nenhuma linha" tem três causas diferentes e a tela precisa dizer
               qual: base não carregada, filtro fechando tudo, ou nada a fazer. -->
          <div v-if="!batchRows.length" class="p-6 text-center text-sm text-muted-foreground">
            <template v-if="!materials.length">Base de insumos ainda não carregada.</template>
            <template v-else-if="batchQuery.trim()">Nenhum insumo encontrado para “{{ batchQuery }}”.</template>
            <template v-else-if="batchOnlyMissing">Todo insumo ativo já tem custo preferencial.</template>
            <template v-else>Nenhum insumo ativo na base.</template>
          </div>

          <div v-else class="max-h-[28rem] overflow-y-auto">
            <table class="min-w-full divide-y divide-border text-sm">
              <thead class="sticky top-0 bg-muted text-left text-xs font-medium text-muted-foreground">
                <tr>
                  <th class="px-3 py-2">Insumo</th>
                  <th class="px-3 py-2">Unidade de compra</th>
                  <th class="px-3 py-2 w-40">Valor</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-border">
                <tr v-for="row in batchRows" :key="`batch-${row.sku}`" class="hover:bg-accent/70">
                  <td class="px-3 py-2">
                    <span class="font-medium">{{ row.name }}</span>
                    <span class="ml-1 text-xs text-muted-foreground">{{ row.sku }} · {{ row.unit }}</span>
                    <p v-if="batchLineErrors[row.sku]" class="mt-0.5 text-xs font-medium text-destructive">
                      {{ batchLineErrors[row.sku] }}
                    </p>
                  </td>
                  <td class="px-3 py-2">
                    <select
                      class="h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
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
                    </select>
                  </td>
                  <td class="px-3 py-2">
                    <input
                      inputmode="decimal"
                      placeholder="0,00"
                      class="h-9 w-full rounded-md border bg-background px-2 text-sm tabular-nums"
                      :class="batchLineErrors[row.sku] ? 'border-destructive' : 'border-border'"
                      :value="batchInputs[row.sku] ?? ''"
                      @input="setBatchInput(row.sku, ($event.target as HTMLInputElement).value)"
                    />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="flex flex-wrap items-center justify-between gap-3 border-t border-border p-3">
            <p class="text-sm text-muted-foreground">
              <template v-if="!batchSupplierRef">Escolha o fornecedor para lançar.</template>
              <template v-else>{{ batchFilledCount }} valor(es) preenchido(s)</template>
            </p>
            <div class="flex gap-2">
              <button
                type="button"
                class="h-10 rounded-md border border-border px-3 text-sm font-medium hover:bg-accent disabled:opacity-50"
                :disabled="!batchFilledCount || actionPending"
                @click="clearCostBatch()"
              >
                Limpar
              </button>
              <button
                type="button"
                class="h-10 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground disabled:opacity-50"
                :disabled="readonlyFallback || !batchReady || actionPending"
                @click="saveCostBatch()"
              >
                Salvar {{ batchFilledCount || "" }} como padrão
              </button>
            </div>
          </div>
        </section>

        <div class="grid gap-4 xl:grid-cols-[24rem_minmax(0,1fr)]">
        <aside class="rounded-md border border-border bg-card p-4">
          <h1 class="text-lg font-semibold">Lançar custo</h1>
          <div class="mt-3 space-y-3">
            <label class="block text-sm font-medium">Insumo
              <select v-model="noteMaterialSku" class="mt-1 h-10 w-full rounded-md border border-border bg-background px-3 text-sm">
                <option v-for="material in materials" :key="material.sku" :value="material.sku">{{ material.name }}</option>
              </select>
            </label>
            <label class="block text-sm font-medium">Fornecedor
              <select v-model="noteSupplierRef" class="mt-1 h-10 w-full rounded-md border border-border bg-background px-3 text-sm">
                <option v-for="supplier in suppliers" :key="supplier.ref" :value="supplier.ref">{{ supplier.displayName }}</option>
              </select>
            </label>
            <label class="block text-sm font-medium">Unidade de compra
              <select v-model="noteConversionId" class="mt-1 h-10 w-full rounded-md border border-border bg-background px-3 text-sm">
                <option value="">Unidade-base</option>
                <option v-for="conversion in availableNoteConversions" :key="conversion.id" :value="conversion.id">{{ conversion.label }}</option>
              </select>
            </label>
            <label class="block text-sm font-medium">Valor da unidade de compra
              <input v-model="noteCostInput" inputmode="decimal" class="mt-1 h-10 w-full rounded-md border border-border bg-background px-3 text-sm" placeholder="180,00" />
            </label>
            <div class="rounded-md border border-border bg-background p-3">
              <p class="text-xs font-medium text-muted-foreground">Custo derivado</p>
              <p class="mt-1 text-3xl font-bold tabular-nums">
                <template v-if="notePreview"><span v-if="notePreview.approximate">≈ </span>{{ formatMoney(notePreview.baseCostQ) }}</template>
                <template v-else>—</template>
              </p>
            </div>
            <div class="grid grid-cols-2 gap-2">
              <button type="button" class="h-10 rounded-md border border-border px-3 text-sm font-medium hover:bg-accent disabled:opacity-50" :disabled="readonlyFallback || quoteDisabled || actionPending" @click="saveQuote(false)">Salvar</button>
              <button type="button" class="h-10 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-50" :disabled="readonlyFallback || quoteDisabled || actionPending" @click="saveQuote(true)">Salvar padrão</button>
            </div>
          </div>
        </aside>

        <div class="rounded-md border border-border bg-card">
          <div class="border-b border-border p-3">
            <h2 class="text-lg font-semibold">Custos por fornecedor</h2>
          </div>
          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-border text-sm">
              <thead class="bg-muted text-left text-xs font-medium text-muted-foreground">
                <tr><th class="px-3 py-2">Insumo</th><th class="px-3 py-2">Fornecedor</th><th class="px-3 py-2">Compra</th><th class="px-3 py-2">Base</th><th class="px-3 py-2">Padrão</th></tr>
              </thead>
              <tbody class="divide-y divide-border">
                <tr v-for="cost in costs" :key="cost.id" class="hover:bg-accent/70">
                  <td class="px-3 py-2 font-medium">{{ materials.find((material) => material.sku === cost.materialSku)?.name }}</td>
                  <td class="px-3 py-2">{{ suppliers.find((supplier) => supplier.ref === cost.supplierRef)?.displayName }}</td>
                  <td class="px-3 py-2 tabular-nums">{{ formatMoney(cost.costQ) }} / {{ purchaseUnitLabel(cost, materials.find((material) => material.sku === cost.materialSku), conversions) }}</td>
                  <td class="px-3 py-2 font-semibold tabular-nums"><span v-if="isApproximateCost(cost, conversions)">≈ </span>{{ formatMoney(costPerBaseUnitQ(cost, conversions)) }}</td>
                  <td class="px-3 py-2">
                    <button type="button" class="h-8 rounded-md border px-2.5 text-xs font-medium disabled:opacity-50" :class="cost.isPreferred ? 'border-success/30 bg-success/10 text-success' : 'border-border hover:bg-accent'" :disabled="readonlyFallback || actionPending || cost.isPreferred" @click="setPreferredCost(cost.id)">
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

      <section v-else class="space-y-4">
        <div v-if="countForbidden" class="rounded-md border border-border bg-card p-8 text-center">
          <Icon name="lucide:lock" class="mx-auto size-6 text-muted-foreground" />
          <h2 class="mt-3 text-lg font-semibold">Contagem restrita ao gestor</h2>
          <p class="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Auditar e ajustar o estoque de insumos pede a permissão de auditoria. Entre com o operador do gestor para contar.
          </p>
        </div>

        <div v-else class="rounded-md border border-border bg-card">
          <div class="flex flex-wrap items-center gap-3 border-b border-border p-3">
            <label class="relative min-w-64 flex-1">
              <Icon name="lucide:search" class="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <input v-model="query" type="search" placeholder="Buscar insumo" class="h-10 w-full rounded-md border border-border bg-background pl-9 pr-3 text-sm" />
            </label>
            <p class="text-sm text-muted-foreground">Informe o que contou no físico. Divergência pede motivo e vira ajuste no estoque.</p>
          </div>
          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-border text-sm">
              <thead class="bg-muted text-left text-xs font-medium text-muted-foreground">
                <tr><th class="px-3 py-2">Insumo</th><th class="px-3 py-2">Sistema</th><th class="px-3 py-2">Contado</th><th class="px-3 py-2">Diferença</th><th class="px-3 py-2">Motivo</th></tr>
              </thead>
              <tbody class="divide-y divide-border">
                <tr v-for="row in countFilteredRows" :key="row.item.sku" class="hover:bg-accent/70">
                  <td class="px-3 py-2">
                    <p class="font-semibold">{{ row.item.name }}</p>
                    <p class="font-mono text-xs text-muted-foreground">{{ row.item.sku }} · {{ row.item.category }}</p>
                  </td>
                  <td class="px-3 py-2 tabular-nums">{{ formatQty(row.item.systemQty, row.item.unit) }}</td>
                  <td class="px-3 py-2">
                    <input
                      :value="row.input"
                      type="text"
                      inputmode="decimal"
                      :placeholder="`0 ${row.item.unit}`"
                      :aria-label="`Quantidade contada de ${row.item.name}`"
                      class="h-10 w-28 rounded-md border border-border bg-background px-3 text-sm tabular-nums"
                      @input="setCountInput(row.item.sku, ($event.target as HTMLInputElement).value)"
                    />
                  </td>
                  <td class="px-3 py-2">
                    <span
                      v-if="row.counted !== null"
                      class="rounded-md border px-2 py-1 text-xs font-medium tabular-nums"
                      :class="
                        row.divergent ?
                          (row.diff < 0 ? 'border-destructive/30 bg-destructive/10 text-destructive' : 'border-warning/30 bg-warning/10 text-warning')
                        : 'border-success/25 bg-success/10 text-success'
                      "
                    >
                      {{ row.divergent ? formatQtyDiff(row.diff, row.item.unit) : "Confere" }}
                    </span>
                    <span v-else class="text-xs text-muted-foreground">—</span>
                  </td>
                  <td class="px-3 py-2">
                    <input
                      v-if="row.divergent"
                      :value="row.reason"
                      type="text"
                      placeholder="Por que divergiu?"
                      :aria-label="`Motivo da divergência de ${row.item.name}`"
                      class="h-10 w-56 rounded-md border bg-background px-3 text-sm"
                      :class="row.missingReason ? 'border-destructive/50' : 'border-border'"
                      @input="setCountReason(row.item.sku, ($event.target as HTMLInputElement).value)"
                    />
                    <span v-else class="text-xs text-muted-foreground">—</span>
                  </td>
                </tr>
                <tr v-if="!countFilteredRows.length">
                  <td colspan="5" class="px-3 py-8 text-center text-sm text-muted-foreground">
                    {{ countPending ? "Carregando posições do estoque..." : "Nenhum insumo para contar." }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="flex flex-wrap items-center justify-between gap-3 border-t border-border p-3">
            <div class="text-sm text-muted-foreground">
              <span class="tabular-nums">{{ countTotals.filled }}</span> contado(s) ·
              <span class="tabular-nums">{{ countTotals.divergent }}</span> divergência(s)
              <span v-if="countTotals.missingReason" class="text-destructive"> · {{ countTotals.missingReason }} sem motivo</span>
              <span v-if="countConfirmedAt" class="text-success"> · Última contagem lançada {{ countConfirmedAt }}</span>
            </div>
            <div class="flex items-center gap-2">
              <button type="button" class="h-10 rounded-md border border-border px-3 text-sm font-medium hover:bg-accent disabled:opacity-50" :disabled="actionPending || !countTotals.filled" @click="resetCount">
                Limpar
              </button>
              <button type="button" class="h-10 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-50" :disabled="actionPending || countPending || !countReady" @click="openCountConfirm">
                Lançar contagem
              </button>
            </div>
          </div>
        </div>
      </section>
    </section>

    <div v-if="countConfirmOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-label="Confirmar contagem">
      <div class="w-full max-w-lg rounded-md border border-border bg-card p-4 shadow-lg">
        <div class="flex items-start gap-3">
          <Icon name="lucide:clipboard-check" class="mt-0.5 size-5 text-muted-foreground" />
          <div>
            <h2 class="text-lg font-semibold">Lançar a contagem no estoque?</h2>
            <p class="mt-1 text-sm text-muted-foreground">
              Cada divergência vira um ajuste definitivo no livro de estoque, registrado com o seu usuário e o motivo informado.
            </p>
          </div>
        </div>
        <div v-if="countDivergentRows.length" class="mt-4 max-h-64 space-y-2 overflow-y-auto">
          <div v-for="row in countDivergentRows" :key="row.item.sku" class="rounded-md border border-border bg-background p-2 text-sm">
            <div class="flex items-center justify-between gap-2">
              <p class="font-medium">{{ row.item.name }}</p>
              <span class="font-semibold tabular-nums" :class="row.diff < 0 ? 'text-destructive' : 'text-warning'">{{ formatQtyDiff(row.diff, row.item.unit) }}</span>
            </div>
            <p class="text-xs text-muted-foreground tabular-nums">{{ formatQty(row.item.systemQty, row.item.unit) }} no sistema · {{ formatQty(row.counted ?? 0, row.item.unit) }} contado</p>
            <p class="mt-1 text-xs">{{ row.reason }}</p>
          </div>
        </div>
        <p v-else class="mt-4 rounded-md border border-success/25 bg-success/10 p-2 text-sm text-success">
          Sem divergência: a contagem confirma o saldo do sistema e nenhum ajuste será lançado.
        </p>
        <div class="mt-4 flex items-center justify-end gap-2">
          <button type="button" class="h-10 rounded-md border border-border px-3 text-sm font-medium hover:bg-accent" :disabled="actionPending" @click="countConfirmOpen = false">
            Voltar
          </button>
          <button
            type="button"
            class="inline-flex h-10 items-center gap-2 rounded-md px-3 text-sm font-medium disabled:opacity-50"
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
        <div>
          <p class="text-xs font-medium uppercase tracking-wide text-white/60">Receber</p>
          <h2 class="text-lg font-semibold">Escanear NF</h2>
        </div>
        <div class="flex items-center gap-2">
          <button v-if="scannerCanTorch" type="button" class="inline-flex size-11 items-center justify-center rounded-md border border-white/20 bg-white/10" :aria-label="scannerTorchOn ? 'Desligar lanterna' : 'Ligar lanterna'" @click="toggleScannerTorch">
            <Icon :name="scannerTorchOn ? 'lucide:flashlight-off' : 'lucide:flashlight'" class="size-5" />
          </button>
          <button type="button" class="inline-flex size-11 items-center justify-center rounded-md border border-white/20 bg-white/10" aria-label="Fechar câmera" @click="() => stopInvoiceScanner()">
            <Icon name="lucide:x" class="size-5" />
          </button>
        </div>
      </div>
      <div class="relative min-h-0 flex-1 overflow-hidden rounded-md border border-white/20 bg-zinc-950">
        <video ref="scannerVideo" muted playsinline class="h-full w-full object-cover" />
        <div class="pointer-events-none absolute inset-x-8 top-1/2 h-40 -translate-y-1/2 rounded-md border-2 border-white/80 shadow-[0_0_0_999px_rgba(0,0,0,0.35)]" />
      </div>
      <p class="pt-3 text-sm text-white/80">
        {{ scannerHint || "Aponte para o QR ou código de barras da nota." }}
        Para barras, deixe a linha inteira visível, na horizontal, sem cortar as laterais.
      </p>
    </div>
  </main>
</template>

<script setup lang="ts">
import type {
  EnrichedMaterial,
  Material,
  MaterialTone,
  PurchaseBaseView,
  PurchaseRequestStatus,
  ReceiptMode,
  ReceiptWarningTone,
  SupplierMaterialCost,
} from "~/types/purchase";
import {
  costPerBaseUnitQ,
  coverageLabel,
  formatMoney,
  formatQty,
  formatStockOnHand,
  isApproximateCost,
  purchaseUnitLabel,
} from "~/presentation/purchase";

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
  supplierSummaries,
  receiptMode,
  invoiceInput,
  receiptSupplierRef,
  receiptNote,
  receiptConfirmedAt,
  receiptRejectedAt,
  receiptSupplier,
  invoiceStatus,
  receiptLinePreviews,
  receiptBlockers,
  receiptWatchWarnings,
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
  declareReceiptLineConversion,
  updateReceiptLine,
  addReceiptLine,
  removeReceiptLine,
  readInvoice,
  confirmReceipt,
  rejectReceipt,
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
];

const invoiceShortKey = computed(() =>
  invoiceStatus.value.accessKey ?
    `${invoiceStatus.value.accessKey.slice(0, 4)} ${invoiceStatus.value.accessKey.slice(4, 8)} ... ${invoiceStatus.value.accessKey.slice(-6)}`
  : "—",
);

const receiptTotalBlockers = computed(
  () => receiptBlockers.value.length + receiptDocumentBlockers.value.length + receiptSupplierBlockers.value.length,
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

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit" }).format(new Date(`${value}T12:00:00`));
}

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

function onReceiptMaterialChange(lineId: string, event: Event) {
  setReceiptLineMaterial(lineId, (event.target as HTMLSelectElement).value);
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
            <p class="mt-1 text-xs text-muted-foreground">{{ receiptTotalBlockers }} bloqueios</p>
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

        <div class="grid gap-3 p-3 md:grid-cols-2 2xl:grid-cols-3">
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
        <section class="rounded-md border border-border bg-card">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-border p-4">
            <div>
              <p class="text-xs font-medium text-muted-foreground">Compras</p>
              <h1 class="mt-1 text-xl font-semibold">Receber materiais</h1>
            </div>
            <div class="inline-flex rounded-md bg-muted p-1">
              <button type="button" class="inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm transition" :class="receiptMode === 'invoice' ? 'bg-card font-semibold shadow-sm' : 'text-muted-foreground hover:bg-card/60'" @click="setReceiptMode('invoice')">
                <Icon name="lucide:scan-line" class="size-4" />
                Com NF
              </button>
              <button type="button" class="inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm transition" :class="receiptMode === 'manual' ? 'bg-card font-semibold shadow-sm' : 'text-muted-foreground hover:bg-card/60'" @click="setReceiptMode('manual')">
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
              <label v-if="receiptMode === 'invoice'" class="block text-sm font-medium">
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
              <label class="block text-sm font-medium">
                Fornecedor
                <select :value="receiptSupplierRef" class="mt-1 h-10 w-full rounded-md border border-border bg-background px-3 text-sm" @change="onReceiptSupplierChange">
                  <option value="">Definir fornecedor</option>
                  <option v-for="supplier in suppliers" :key="supplier.ref" :value="supplier.ref">{{ supplier.name }}</option>
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
            <button type="button" class="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-sm font-medium hover:bg-accent" @click="addReceiptLine">
              <Icon name="lucide:plus" class="size-4" />
              Item
            </button>
          </div>

          <div class="grid gap-3 p-3 lg:hidden">
            <article v-for="preview in receiptLinePreviews" :key="`card-${preview.line.id}`" class="rounded-md border border-border bg-background p-3">
              <select :value="preview.line.materialSku" class="h-11 w-full rounded-md border border-border bg-card px-3 text-sm font-medium" @change="onReceiptMaterialChange(preview.line.id, $event)">
                <option value="">Definir insumo</option>
                <option v-for="material in materials" :key="material.sku" :value="material.sku">{{ material.name }}</option>
              </select>
              <div v-if="preview.suggestion" class="mt-2 rounded-md border border-warning/30 bg-warning/10 p-2">
                <p class="flex items-center gap-1.5 text-xs font-medium text-warning">
                  <Icon name="lucide:sparkles" class="size-3.5" />
                  Sugestão: {{ preview.suggestion.name }} ({{ preview.suggestion.scorePercent }}% parecido)
                </p>
                <div class="mt-2 flex flex-wrap items-center gap-2">
                  <button type="button" class="inline-flex h-9 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-semibold text-primary-foreground" @click="acceptReceiptLineSuggestion(preview.line.id)">
                    <Icon name="lucide:check" class="size-3.5" />
                    Usar sugestão
                  </button>
                  <span class="text-xs text-muted-foreground">ou escolha outro insumo acima</span>
                </div>
              </div>
              <div class="mt-3">
                <ReceiptConversion
                  :preview="preview"
                  :conversions="receiptConversionsFor(preview.line.materialSku)"
                  :pending="actionPending"
                  @select="updateReceiptLine(preview.line.id, { conversionId: $event })"
                  @accept="acceptReceiptLineConversion(preview.line.id)"
                  @declare="declareReceiptLineConversion(preview.line.id, $event)"
                />
              </div>
              <div class="mt-3 grid grid-cols-2 gap-2">
                <input v-model.number="preview.line.purchaseQty" type="number" min="0" step="0.01" class="h-11 rounded-md border border-border bg-card px-3 text-sm tabular-nums" />
                <input v-model="preview.line.expiryDate" type="date" class="h-11 rounded-md border border-border bg-card px-3 text-sm" />
                <input v-model="preview.line.costInput" inputmode="decimal" class="h-11 rounded-md border border-border bg-card px-3 text-sm tabular-nums" placeholder="0,00" />
              </div>
              <div class="mt-3 rounded-md border border-border bg-card p-2 text-sm">
                <p v-if="preview.baseQtyKnown" class="font-semibold tabular-nums">{{ formatQty(preview.baseQty, preview.material.unit) }}</p>
                <p v-else class="font-semibold text-muted-foreground">Aguardando a conversão</p>
                <p v-if="preview.baseQtyKnown" class="text-xs text-muted-foreground">{{ formatMoney(preview.baseCostQ) }} / {{ preview.material.unit }} · após {{ formatQty(stockAfterReceipt(preview.material.sku), preview.material.unit) }}</p>
              </div>
              <textarea v-model="preview.line.lineNote" rows="2" class="mt-3 w-full resize-none rounded-md border border-border bg-card px-3 py-2 text-sm" placeholder="Ocorrência: parcial, avaria, ressalva" />
              <div class="mt-3 flex items-center justify-between gap-2">
                <label class="inline-flex h-10 items-center gap-2 rounded-md border border-border px-3 text-sm font-medium">
                  <input v-model="preview.line.checked" type="checkbox" class="form-checkbox rounded border-border text-primary" />
                  Conferido
                </label>
                <button type="button" class="inline-flex size-10 items-center justify-center rounded-md border border-border hover:bg-accent" @click="removeReceiptLine(preview.line.id)">
                  <Icon name="lucide:trash-2" class="size-4" />
                </button>
              </div>
              <div v-if="preview.warnings.length" class="mt-3 flex flex-wrap gap-1.5">
                <span v-for="warning in preview.warnings" :key="`${preview.line.id}-${warning.key}`" class="rounded-md border px-2 py-0.5 text-xs font-medium" :class="receiptWarningClasses[warning.tone]">
                  {{ warning.label }}
                </span>
              </div>
            </article>
          </div>

          <div class="hidden overflow-x-auto lg:block">
            <table class="min-w-full divide-y divide-border text-sm">
              <thead class="bg-muted text-left text-xs font-medium text-muted-foreground">
                <tr><th class="px-3 py-2">Insumo</th><th class="px-3 py-2">Entrega</th><th class="px-3 py-2">Qtd.</th><th class="px-3 py-2">Validade</th><th class="px-3 py-2">Valor</th><th class="px-3 py-2">Entrada</th><th class="px-3 py-2">Conferência</th><th class="px-3 py-2"></th></tr>
              </thead>
              <tbody class="divide-y divide-border">
                <tr v-for="preview in receiptLinePreviews" :key="preview.line.id" class="align-top hover:bg-accent/60">
                  <td class="min-w-56 px-3 py-3">
                    <select :value="preview.line.materialSku" class="h-10 w-full rounded-md border border-border bg-background px-2 text-sm font-medium" @change="onReceiptMaterialChange(preview.line.id, $event)">
                      <option value="">Definir insumo</option>
                      <option v-for="material in materials" :key="material.sku" :value="material.sku">{{ material.name }}</option>
                    </select>
                    <div v-if="preview.suggestion" class="mt-2 rounded-md border border-warning/30 bg-warning/10 p-2">
                      <p class="flex items-center gap-1.5 text-xs font-medium text-warning">
                        <Icon name="lucide:sparkles" class="size-3.5" />
                        Sugestão: {{ preview.suggestion.name }} ({{ preview.suggestion.scorePercent }}% parecido)
                      </p>
                      <div class="mt-2 flex flex-wrap items-center gap-2">
                        <button type="button" class="inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-2.5 text-xs font-semibold text-primary-foreground" @click="acceptReceiptLineSuggestion(preview.line.id)">
                          <Icon name="lucide:check" class="size-3.5" />
                          Usar sugestão
                        </button>
                        <span class="text-xs text-muted-foreground">ou escolha outro insumo acima</span>
                      </div>
                    </div>
                    <p class="mt-1 text-xs text-muted-foreground">{{ preview.material.sku }} · base {{ preview.material.unit }}</p>
                  </td>
                  <td class="min-w-56 px-3 py-3">
                    <ReceiptConversion
                      :preview="preview"
                      :conversions="receiptConversionsFor(preview.line.materialSku)"
                      :pending="actionPending"
                      @select="updateReceiptLine(preview.line.id, { conversionId: $event })"
                      @accept="acceptReceiptLineConversion(preview.line.id)"
                      @declare="declareReceiptLineConversion(preview.line.id, $event)"
                    />
                  </td>
                  <td class="min-w-28 px-3 py-3"><input v-model.number="preview.line.purchaseQty" type="number" min="0" step="0.01" class="h-10 w-full rounded-md border border-border bg-background px-2 text-sm tabular-nums" /></td>
                  <td class="min-w-40 px-3 py-3"><input v-model="preview.line.expiryDate" type="date" class="h-10 w-full rounded-md border border-border bg-background px-2 text-sm" /></td>
                  <td class="min-w-32 px-3 py-3"><input v-model="preview.line.costInput" inputmode="decimal" class="h-10 w-full rounded-md border border-border bg-background px-2 text-sm tabular-nums" placeholder="0,00" /></td>
                  <td class="min-w-44 px-3 py-3">
                    <template v-if="preview.baseQtyKnown">
                      <p class="font-semibold tabular-nums">{{ formatQty(preview.baseQty, preview.material.unit) }}</p>
                      <p class="text-xs text-muted-foreground">{{ formatMoney(preview.baseCostQ) }} / {{ preview.material.unit }}</p>
                      <p class="text-xs text-muted-foreground">Após: {{ formatQty(stockAfterReceipt(preview.material.sku), preview.material.unit) }}</p>
                    </template>
                    <p v-else class="font-semibold text-muted-foreground">Aguardando a conversão</p>
                  </td>
                  <td class="min-w-52 px-3 py-3">
                    <label class="inline-flex h-9 items-center gap-2 rounded-md border border-border px-2.5 text-sm font-medium">
                      <input v-model="preview.line.checked" type="checkbox" class="form-checkbox rounded border-border text-primary" />
                      Conferido
                    </label>
                    <textarea v-model="preview.line.lineNote" rows="2" class="mt-2 w-full resize-none rounded-md border border-border bg-background px-2 py-1.5 text-sm" placeholder="Ocorrência" />
                    <div v-if="preview.warnings.length" class="mt-2 flex flex-wrap gap-1.5">
                      <span v-for="warning in preview.warnings" :key="`${preview.line.id}-${warning.key}`" class="rounded-md border px-2 py-0.5 text-xs font-medium" :class="receiptWarningClasses[warning.tone]">{{ warning.label }}</span>
                    </div>
                  </td>
                  <td class="px-3 py-3 text-right">
                    <button type="button" class="inline-flex size-9 items-center justify-center rounded-md border border-border hover:bg-accent" @click="removeReceiptLine(preview.line.id)">
                      <Icon name="lucide:trash-2" class="size-4" />
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <aside class="rounded-md border border-border bg-card p-4">
        <h2 class="text-lg font-semibold">Conferência</h2>
        <dl class="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div><dt class="text-xs text-muted-foreground">Origem</dt><dd class="font-semibold">{{ receiptMode === "invoice" ? "NF" : "Sem NF" }}</dd></div>
          <div><dt class="text-xs text-muted-foreground">Itens</dt><dd class="font-semibold tabular-nums">{{ receiptCheckedCount }}/{{ receiptLinePreviews.length }}</dd></div>
          <div><dt class="text-xs text-muted-foreground">Valor</dt><dd class="font-semibold tabular-nums">{{ formatMoney(receiptTotalCostQ) }}</dd></div>
          <div><dt class="text-xs text-muted-foreground">Bloqueios</dt><dd class="font-semibold tabular-nums" :class="receiptTotalBlockers ? 'text-destructive' : 'text-success'">{{ receiptTotalBlockers }}</dd></div>
        </dl>

        <div class="mt-4 rounded-md border border-border bg-background p-3">
          <p class="text-xs font-medium text-muted-foreground">{{ receiptMode === "invoice" ? "Chave NF" : "Fornecedor" }}</p>
          <p class="mt-1 break-words text-sm font-semibold">{{ receiptMode === "invoice" ? invoiceShortKey : receiptSupplier?.name }}</p>
        </div>

        <label v-if="receiptMode === 'invoice'" class="mt-4 block text-sm font-medium">
          Ressalva geral
          <textarea v-model="receiptNote" rows="3" class="mt-1 w-full resize-none rounded-md border border-border bg-background px-3 py-2 text-sm" placeholder="Avaria, falta, devolução, observação na NF/CT-e" />
        </label>

        <div v-if="receiptDocumentBlockers.length || receiptSupplierBlockers.length || receiptBlockers.length || receiptWatchWarnings.length" class="mt-4 space-y-2">
          <div v-for="blocker in receiptDocumentBlockers" :key="blocker" class="rounded-md border border-destructive/30 bg-destructive/10 p-2 text-sm text-destructive">{{ blocker }}</div>
          <div v-for="blocker in receiptSupplierBlockers" :key="blocker" class="rounded-md border border-destructive/30 bg-destructive/10 p-2 text-sm text-destructive">{{ blocker }}</div>
          <div v-for="(warning, index) in receiptBlockers" :key="`block-${warning.key}-${index}`" class="rounded-md border p-2 text-sm" :class="receiptWarningClasses[warning.tone]">{{ warning.label }}</div>
          <div v-for="(warning, index) in receiptWatchWarnings" :key="`watch-${warning.key}-${index}`" class="rounded-md border p-2 text-sm" :class="receiptWarningClasses[warning.tone]">{{ warning.label }}</div>
        </div>

        <div class="mt-4 border-t border-border pt-4">
          <button type="button" class="inline-flex h-12 w-full items-center justify-center gap-2 rounded-md bg-primary px-3 text-sm font-semibold text-primary-foreground disabled:opacity-50" :disabled="readonlyFallback || !receiptReady || actionPending" @click="confirmReceipt">
            <Icon :name="actionPending ? 'lucide:loader-circle' : 'lucide:package-check'" class="size-4" :class="actionPending ? 'animate-spin' : ''" />
            {{ actionPending ? "Confirmando" : "Confirmar entrada" }}
          </button>
          <p v-if="receiptConfirmedAt" class="mt-3 rounded-md border border-success/25 bg-success/10 p-2 text-sm font-medium text-success">
            Entrada confirmada em {{ receiptConfirmedAt }}
          </p>
          <button type="button" class="mt-2 inline-flex h-11 w-full items-center justify-center gap-2 rounded-md border border-destructive/30 px-3 text-sm font-semibold text-destructive hover:bg-destructive/10 disabled:opacity-50" :disabled="readonlyFallback || !receiptHasRejectionReason || actionPending" @click="rejectReceipt">
            <Icon :name="actionPending ? 'lucide:loader-circle' : 'lucide:undo-2'" class="size-4" :class="actionPending ? 'animate-spin' : ''" />
            {{ actionPending ? "Registrando" : "Registrar devolução" }}
          </button>
          <p v-if="receiptRejectedAt" class="mt-3 rounded-md border border-warning/30 bg-warning/10 p-2 text-sm font-medium text-warning">
            Devolução registrada em {{ receiptRejectedAt }}
          </p>
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
                <tr><th class="px-3 py-2">SKU</th><th class="px-3 py-2">Insumo</th><th class="px-3 py-2">Estoque</th><th class="px-3 py-2">Cobertura</th><th class="px-3 py-2">Custo-base</th><th class="px-3 py-2">Status</th></tr>
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
                  <td class="px-3 py-2 tabular-nums">{{ formatMoney(material.preferredBaseCostQ) }} / {{ material.unit }}</td>
                  <td class="px-3 py-2">
                    <span class="rounded-md border px-2 py-1 text-xs font-medium" :class="toneClasses[material.tone]">{{ toneLabels[material.tone] }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
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
                <h2 class="font-semibold">{{ summary.supplier.name }}</h2>
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
          <h2 class="text-lg font-semibold">{{ selectedSupplier.name }}</h2>
          <p class="text-sm text-muted-foreground">{{ selectedSupplier.document }}</p>
          <dl class="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div><dt class="text-xs text-muted-foreground">Prazo</dt><dd class="font-semibold">{{ selectedSupplier.leadTimeDays }} dia(s)</dd></div>
            <div><dt class="text-xs text-muted-foreground">Entrega</dt><dd class="font-semibold">{{ selectedSupplier.reliabilityPercent }}%</dd></div>
            <div><dt class="text-xs text-muted-foreground">Última</dt><dd class="font-semibold">{{ formatDate(selectedSupplier.lastDeliveryAt) }}</dd></div>
            <div><dt class="text-xs text-muted-foreground">Pagamento</dt><dd class="font-semibold">{{ selectedSupplier.paymentTerm }}</dd></div>
          </dl>
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

      <section v-else class="grid gap-4 xl:grid-cols-[24rem_minmax(0,1fr)]">
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
                <option v-for="supplier in suppliers" :key="supplier.ref" :value="supplier.ref">{{ supplier.name }}</option>
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
                  <td class="px-3 py-2">{{ suppliers.find((supplier) => supplier.ref === cost.supplierRef)?.name }}</td>
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
      </section>
    </section>

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

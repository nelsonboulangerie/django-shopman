<script setup lang="ts">
// Receber: a NF (ou o romaneio sem NF) entra no estoque. Começo: escanear a NF, digitar
// a chave ou lançar sem NF, e as entradas de hoje. Conferência: o que bate entra pela
// contagem de volumes; só o que não bate pede atenção, item a item.
//
// O item aberto tem endereço (`/receive?line=<id>`): "‹ 3 de 7 ›" (`OperatorRecordNav`)
// anda pelos itens na ordem da lista. No celular, a ação do momento mora na base
// (`OperatorActionBar`): Escanear NF, Contei N volumes ou Confirmar entrada. Na mesa
// ela está no painel da conferência, ao lado da lista.
import type {
  ConversionKind,
  ReceiptBlocker,
  ReceiptDocumentAnchor,
  ReceiptFieldAnchor,
  ReceiptHistoryEntry,
  ReceiptLine,
} from "~/types/purchase";
import {
  formatMoney,
  formatShortDate,
  invoiceKeyTail,
  invoiceNumberLabel,
  receiptOutcomeSummary,
} from "~/presentation/purchase";
import { materialForEan, parseGs1, receiptLineForEan } from "~/presentation/scanning";
import { RECEIPT_LINES_TRAIL } from "~/presentation/purchaseSections";
import { plural } from "~/presentation/purchaseUi";
import { RECEIPT_LINE_STATUS_COLOR, RECEIPT_LINE_STATUS_ROW, RECEIPT_LINE_STATUS_TEXT } from "~/utils/receiptLineStatus";
import { FLASH_RING, receiptFieldSelector, waitForElement } from "~/utils/receiptFocus";

const route = useRoute();
const router = useRouter();
const screen = useScreen();
const {
  materials,
  suppliers,
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
  receiptLines,
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
  receiptTotalPending,
  readonlyFallback,
  actionPending,
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
  rejectReceiptLine,
  receiptHistory,
  refresh,
} = usePurchaseDesk();

const touch = useCoarsePointer();
const supplierItems = computed(() => suppliers.value.map((supplier) => ({ label: supplier.displayName, value: supplier.ref })));

// O documento da entrada: "Serra Azul · NF 12.912" e o selo da chave lida ("Chave …4170").
const invoiceNumber = computed(() => invoiceNumberLabel(invoiceStatus.value.accessKey));
const invoiceKeyLabel = computed(() => invoiceKeyTail(invoiceStatus.value.accessKey));
const receiptDocumentTitle = computed(() =>
  [receiptSupplier.value?.displayName || receiptSupplier.value?.name || "", receiptMode.value === "invoice" ? invoiceNumber.value : "Sem NF"]
    .filter(Boolean)
    .join(" · "),
);

// ── Estado da tela ──────────────────────────────────────────────────────────
// O celular volta ao começo do Receber com a conferência guardada ("‹" da barra:
// "Em conferência · Continuar").
const receiptParked = ref(false);
const keyEntryOpen = ref(false);
const ressalvaOpen = ref(false);
const matchedOpen = ref(false);
const volumesDraft = ref(0);
const receiveQuery = ref("");
const phone = computed(() => screen.belowMd.value);
// O começo fica na tela enquanto a NF não trouxe itens (digitar a chave não pode sumir
// com o campo em que se digita).
const receiveStart = computed(
  () => (receiptMode.value === "invoice" && receiptRows.value.length === 0) || (phone.value && receiptParked.value),
);
const exceptionFlowOn = computed(() => receiptMode.value === "invoice" && receiptLinePreviews.value.length > 0);
// Tablet (768 a 1279 px): a lista à esquerda e o item encaixado à direita. Celular e
// mesa larga: o item numa folha por cima. A régua é a do kit; muda a árvore, por isso
// lê `useScreen()`.
const splitDrawer = computed(() => !screen.belowMd.value && screen.belowXl.value && !receiptIsBlank.value);
const thumbCount = computed(
  () => phone.value && exceptionFlowOn.value && receiptException.value.available && receiptException.value.countedVolumes === null,
);
const visibleReceiptRows = computed(() => {
  const term = receiveQuery.value.trim().toLowerCase();
  if (!term) return receiptRows.value;
  return receiptRows.value.filter((row) => row.label.toLowerCase().includes(term));
});
watch(
  () => invoiceStatus.value.accessKey,
  () => {
    matchedOpen.value = false;
    volumesDraft.value = 0;
  },
);
// A hora em que a NF foi lida: "NF 12.912 · lida 22:02" sob o título no celular.
const invoiceReadAt = ref("");
watch(
  () => [invoiceStatus.value.accessKey, receiptLinePreviews.value.length] as const,
  ([key, count]) => {
    if (key && count && !invoiceReadAt.value) {
      invoiceReadAt.value = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    }
    if (!key) invoiceReadAt.value = "";
  },
  { immediate: true },
);
const conferenceOpen = computed(() => !receiveStart.value && Boolean(receiptSupplier.value));
const phoneTitle = computed(() =>
  conferenceOpen.value ? receiptSupplier.value?.displayName || receiptSupplier.value?.name || "Receber" : "",
);
const documentLine = computed(() => {
  if (receiptMode.value !== "invoice") return ["Sem NF", formatMoney(receiptTotalCostQ.value)].join(" · ");
  return [invoiceNumber.value, invoiceReadAt.value ? `lida ${invoiceReadAt.value}` : ""].filter(Boolean).join(" · ");
});
const volumesBadge = computed(() => {
  const view = receiptException.value;
  if (!view.available || view.countedVolumes === null) return "";
  return `${view.countedVolumes} de ${view.expectedVolumes} volumes`;
});

// ── O item aberto (endereço próprio) ────────────────────────────────────────
const openLineId = computed(() => (typeof route.query.line === "string" ? route.query.line : ""));
const openPreview = computed(
  () => receiptLinePreviews.value.find((preview) => preview.line.id === openLineId.value) ?? null,
);
function lineLocation(lineId: string) {
  const query = { ...route.query, line: lineId };
  if (!lineId) delete (query as Record<string, unknown>).line;
  return { path: "/receive", query };
}
function openReceiptLine(lineId: string) {
  if (lineId === openLineId.value) return;
  void router.replace(lineLocation(lineId));
}
function closeReceiptLine() {
  if (openLineId.value) void router.replace(lineLocation(""));
}
// A folha só está aberta se o item ainda existe: apagar a linha de dentro dela deixaria
// uma folha vazia por cima da lista.
const lineSheetOpen = computed({
  get: () => Boolean(openPreview.value),
  set: (value: boolean) => {
    if (!value) closeReceiptLine();
  },
});
const { remember } = useRecordTrail(RECEIPT_LINES_TRAIL);
watch(
  visibleReceiptRows,
  (rows) => remember(rows.map((row) => row.id), { from: "/receive", label: "Itens da entrada" }),
  { immediate: true },
);
// No tablet, o item encaixado nunca fica vazio: abre o primeiro pendente.
watch(
  () => [splitDrawer.value, receiptRows.value.length] as const,
  ([split]) => {
    if (!split || openPreview.value) return;
    const first = receiptRows.value.find((row) => row.nextStep) ?? receiptRows.value[0];
    if (first) openReceiptLine(first.id);
  },
  { immediate: true },
);

// Lançar um item à mão é pedir o formulário dele: a folha abre no item recém-criado.
function addAndOpenReceiptLine() {
  addReceiptLine();
  void nextTick(() => {
    const created = receiptRows.value.at(-1);
    if (created) openReceiptLine(created.id);
  });
}
function removeOpenReceiptLine() {
  const lineId = openLineId.value;
  closeReceiptLine();
  removeReceiptLine(lineId);
}

// Os gestos da folha chegam sem o id: quem está aberto é estado da tela.
function onSheetUpdate(patch: Partial<ReceiptLine>) {
  if (openLineId.value) updateReceiptLine(openLineId.value, patch);
}
function onSheetSelectMaterial(sku: string) {
  if (openLineId.value) setReceiptLineMaterial(openLineId.value, sku);
}
function onSheetDeclareConversion(input: { label: string; factor: string; kind: ConversionKind }) {
  if (openLineId.value) declareReceiptLineConversion(openLineId.value, input);
}

// Um aviso do MESMO tipo repetido em oito linhas vira oito avisos iguais: um por tipo.
const uniqueWatchWarnings = computed(() =>
  receiptWatchWarnings.value.filter((warning, index, all) => all.findIndex((item) => item.key === warning.key) === index),
);

// ── Levar até o que falta ───────────────────────────────────────────────────
// O campo que a tela acabou de apontar ganha o anel âmbar por alguns segundos: rolar até
// ele resolve metade; a outra metade é achar QUAL campo do item é o que falta.
const flashedField = ref("");
let flashTimer: ReturnType<typeof setTimeout> | null = null;
function flashTarget(key: string) {
  flashedField.value = key;
  if (flashTimer) clearTimeout(flashTimer);
  flashTimer = setTimeout(() => {
    flashedField.value = "";
  }, 2600);
}
const sheetFlashField = computed<ReceiptFieldAnchor | null>(() => {
  const [lineId, field] = flashedField.value.split(":");
  if (!field || lineId !== openLineId.value) return null;
  return field as ReceiptFieldAnchor;
});
function anchorRing(anchor: ReceiptDocumentAnchor): string {
  return flashedField.value === anchor ? FLASH_RING : "";
}
// Salto, e não rolagem suave: onde o `smooth` não roda (reduced-motion, webview) o campo
// continuaria fora da tela. O anel dá a continuidade que a animação daria.
const FOCUSABLE = "input:not([type=hidden]), select, textarea, button";
function revealTarget(target: HTMLElement, key: string, block: ScrollLogicalPosition = "center") {
  target.scrollIntoView({ behavior: "auto", block });
  const control = target.matches(FOCUSABLE) ? target : target.querySelector<HTMLElement>(FOCUSABLE);
  control?.focus({ preventScroll: true });
  flashTarget(key);
}
// A folha monta num portal: `waitForElement` espera o campo existir, por poucos quadros.
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

// "Confirmar entrada" sempre responde: diz o gesto que falta e leva até o campo.
function reportReceiptBlocker(blocker: ReceiptBlocker) {
  const goThere = () => {
    if (blocker.scope === "line") void focusReceiptLine(blocker.lineId, blocker.field);
    else if (blocker.anchor) focusReceiptAnchor(blocker.anchor);
  };
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
// Deu certo: a tela volta ao topo, onde mora o aviso do que entrou. Dois quadros de
// espera: confirmar esvazia o rascunho e a página encolhe DEPOIS do render.
async function revealReceiptOutcome() {
  await nextTick();
  await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
  document.querySelector("[data-receive-scroll]")?.scrollTo({ top: 0, behavior: "auto" });
}
// O convite fala da entrada que ACABOU de acontecer: quem deu baixa numa NF tem a
// próxima nota na mão; quem lançou sem NF tem o próximo romaneio.
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

// Recebimento por exceção: o que a conferência do topo pede, ela mesma grava.
function onExceptionCount(counted: number | null) {
  setReceiptVolumesCounted(counted);
}
function onExceptionExpiry(lineId: string, date: string) {
  updateReceiptLine(lineId, { expiryDate: date });
}
function onSomethingOff() {
  matchedOpen.value = true;
  void nextTick(() => document.querySelector("[data-exception-see-items], [data-exception-matched]")?.scrollIntoView({ block: "start" }));
}
async function onRejectLine(lineId: string) {
  if ((await rejectReceiptLine(lineId)) && openLineId.value === lineId) closeReceiptLine();
}

function stockAfterReceipt(sku: string): number {
  const material = materials.value.find((item) => item.sku === sku);
  const incomingQty = receiptLinePreviews.value
    .filter((item) => item.material.sku === sku && item.baseQtyKnown)
    .reduce((total, item) => total + item.baseQty, 0);
  return (material?.stockOnHand ?? 0) + incomingQty;
}

// ── Começo ──────────────────────────────────────────────────────────────────
async function focusInvoiceField() {
  await nextTick();
  const field = await waitForElement('[data-receipt-anchor="invoice"] textarea');
  (field as HTMLTextAreaElement | null)?.focus();
}
function openKeyEntry() {
  keyEntryOpen.value = true;
  void focusInvoiceField();
}
function startManualReceipt() {
  receiptParked.value = false;
  setReceiptMode("manual");
  addAndOpenReceiptLine();
}
async function onReadInvoice() {
  await readInvoice();
  if (receiptRows.value.length) {
    receiptParked.value = false;
    keyEntryOpen.value = false;
  }
}

// ── A câmera da NF ──────────────────────────────────────────────────────────
const scannerOpen = ref(false);
const scannerError = ref("");
const scannerHint = ref("");
const scannerCanTorch = ref(false);
const scannerTorchOn = ref(false);
const scannerVideo = ref<HTMLVideoElement | null>(null);
const scannerFileInput = ref<HTMLInputElement | null>(null);
let scannerControls: { stop: () => void; switchTorch?: (onOff: boolean) => Promise<void> } | null = null;
let scannerAccepted = false;

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

async function createInvoiceCodeReader() {
  const [{ BrowserMultiFormatReader }, { BarcodeFormat, DecodeHintType }] = await Promise.all([
    import("@zxing/browser"),
    import("@zxing/library"),
  ]);
  const hints = new Map();
  hints.set(DecodeHintType.POSSIBLE_FORMATS, [
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
  ]);
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
  await onReadInvoice();
}

const torchSwitching = ref(false);
async function toggleScannerTorch() {
  if (!scannerControls?.switchTorch) return;
  const next = !scannerTorchOn.value;
  torchSwitching.value = true;
  try {
    await scannerControls.switchTorch(next);
    scannerTorchOn.value = next;
  } catch {
    scannerCanTorch.value = false;
    scannerError.value = "Lanterna indisponível neste dispositivo. Use boa luz e mantenha o código inteiro no quadro.";
  } finally {
    torchSwitching.value = false;
  }
}

async function openInvoiceScanner() {
  if (actionPending.value || scannerOpen.value) return;
  scannerError.value = "";
  scannerHint.value = "Abrindo a câmera…";
  scannerAccepted = false;
  if (!import.meta.client || !navigator.mediaDevices?.getUserMedia) {
    scannerError.value = "Câmera indisponível neste navegador. Fotografe a nota, cole ou digite a chave da NF.";
    keyEntryOpen.value = true;
    if (invoiceInput.value.trim()) await onReadInvoice();
    return;
  }
  scannerOpen.value = true;
  await nextTick();
  try {
    const video = await waitForElement("[data-invoice-scanner-video]");
    if (!video) throw new Error("scanner_video_missing");
    scannerVideo.value = video as HTMLVideoElement;
    const reader = await createInvoiceCodeReader();
    scannerHint.value = "Centralize o QR ou alinhe todo o código de barras dentro do quadro.";
    scannerControls = await reader.decodeFromConstraints(
      { audio: false, video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } } },
      scannerVideo.value,
      (result, _error, controls) => {
        scannerControls = controls;
        scannerCanTorch.value = Boolean(controls.switchTorch);
        const text = result?.getText();
        if (text) void acceptScannedInvoice(text);
      },
    );
  } catch {
    scannerError.value = "Não consegui abrir a câmera para ler a NF. Fotografe a nota, cole ou digite a chave.";
    keyEntryOpen.value = true;
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
    scannerError.value = "Não consegui ler a foto. Use uma imagem nítida do QR ou do código de barras, ou digite a chave.";
  }
}

// Os atalhos do Painel chegam por query (`?scan=1`, `?key=1`, `?manual=1`): faz o gesto
// e limpa o endereço.
onMounted(() => {
  const { scan, key, manual, ...rest } = route.query;
  if (!scan && !key && !manual) return;
  void router.replace({ path: "/receive", query: rest });
  if (manual) setReceiptMode("manual");
  else if (key) {
    setReceiptMode("invoice");
    openKeyEntry();
  } else if (scan) {
    setReceiptMode("invoice");
    void openInvoiceScanner();
  }
});

onBeforeUnmount(() => {
  stopInvoiceScanner();
  if (flashTimer) clearTimeout(flashTimer);
});

// ── O ⋯ do Receber ──────────────────────────────────────────────────────────
const headerActions = computed(() => {
  const items = [];
  if (!receiptIsBlank.value) items.push({ label: "Lançar item", icon: "i-lucide-plus", onSelect: () => addAndOpenReceiptLine() });
  if (receiptMode.value === "invoice") {
    items.push({
      label: "Trocar a NF",
      icon: "i-lucide-scan-line",
      onSelect: () => {
        receiptParked.value = true;
        keyEntryOpen.value = true;
        if (!phone.value) setReceiptMode("invoice");
      },
    });
    items.push({ label: "Lançar sem NF", icon: "i-lucide-clipboard-pen-line", onSelect: () => setReceiptMode("manual") });
  } else {
    items.push({ label: "Lançar com NF", icon: "i-lucide-scan-line", onSelect: () => setReceiptMode("invoice") });
  }
  if (!receiptIsBlank.value) items.push({ label: "Ressalva geral", icon: "i-lucide-notebook-pen", onSelect: () => (ressalvaOpen.value = true) });
  items.push({ label: "Atualizar", icon: "i-lucide-refresh-cw", kbds: ["R"], onSelect: () => void refresh() });
  if (!receiptIsBlank.value) {
    items.push({
      label: "Registrar devolução",
      icon: "i-lucide-undo-2",
      color: "error" as const,
      onSelect: () => {
        if (!receiptHasRejectionReason.value) ressalvaOpen.value = true;
        else void onRejectReceipt();
      },
    });
  }
  return items;
});

// O painel da conferência, nos dois lugares (coluna da direita / pé da lista).
const conferencePanelProps = computed(() => ({
  ready: receiptConference.value.ready,
  total: receiptConference.value.total,
  totalPending: receiptTotalPending.value,
  pendingLineCount: receiptPendingLines.value.length,
  mode: receiptMode.value,
  totalCostQ: receiptTotalCostQ.value,
  documentLabel: receiptDocumentTitle.value,
  blank: receiptIsBlank.value,
  documentBlockers: receiptDocumentBlockers.value,
  supplierBlockers: receiptSupplierBlockers.value,
  volumesStep: exceptionFlowOn.value ? "" : receiptVolumesStep.value,
  // Com a conferência por exceção, as pendências de linha moram no fluxo.
  pendingLines: exceptionFlowOn.value ? [] : receiptPendingLines.value,
  watchWarnings: uniqueWatchWarnings.value,
  receiptReady: receiptReady.value,
  firstBlocker: receiptFirstBlocker.value,
  busy: readonlyFallback.value || actionPending.value,
  canReject: receiptHasRejectionReason.value,
  note: receiptNote.value,
}));

// ── Entradas de hoje e o comprovante ────────────────────────────────────────
const todayReceipts = computed(() => (receiptHistory.value ?? []).filter((entry) => entry.receivedToday));
const receiptSheetEntry = ref<ReceiptHistoryEntry | null>(null);
function receiptVoucherDocument(entry: ReceiptHistoryEntry): string {
  return entry.mode === "manual" ? "Sem NF" : invoiceNumberLabel(entry.sourceRef) || entry.sourceRef;
}
function receiptHistoryLine(entry: ReceiptHistoryEntry): string {
  return [receiptVoucherDocument(entry), entry.receivedAtTime, plural(entry.lines, "item", "itens")].filter(Boolean).join(" · ");
}
const sharingReceipt = ref(false);
async function shareReceipt(entry: ReceiptHistoryEntry) {
  if (sharingReceipt.value) return;
  const text = [
    `Entrada no estoque: ${entry.supplierName || entry.supplierRef}`,
    `${receiptVoucherDocument(entry)} · ${entry.receivedAtDisplay}`,
    `${plural(entry.lines, "item", "itens")} · ${formatMoney(entry.totalCostQ)}`,
    entry.operator ? `Recebido por ${entry.operator}` : "",
  ]
    .filter(Boolean)
    .join("\n");
  sharingReceipt.value = true;
  try {
    if (navigator.share) {
      await navigator.share({ title: "Comprovante de entrada", text });
      return;
    }
    await navigator.clipboard.writeText(text);
    useSonner.success("Comprovante copiado. Cole onde quiser compartilhar.");
  } catch (error) {
    // silêncio-deliberado: AbortError é o operador fechando a folha de compartilhar.
    if (error instanceof DOMException && error.name === "AbortError") return;
    useSonner.error("Não consegui compartilhar nem copiar o comprovante. Tente de novo.");
  } finally {
    sharingReceipt.value = false;
  }
}

// ── As câmeras do item ──────────────────────────────────────────────────────
const eanScanOpen = ref(false);
const eanTarget = ref<"find" | "line">("find");
function openEanScanner(target: "find" | "line") {
  eanTarget.value = target;
  eanScanOpen.value = true;
}
function onEanCode(code: string) {
  if (eanTarget.value === "line" && openLineId.value) {
    // Na folha: o EAN identifica o item; vira EAN do cadastro ao confirmar.
    const material = materialForEan(code, materials.value);
    updateReceiptLine(openLineId.value, { scannedEan: code });
    if (material) {
      onSheetSelectMaterial(material.sku);
      useSonner.success(`EAN de ${material.name}.`);
    } else {
      useSonner.success("EAN guardado. Escolha o item: o código passa a identificá-lo.");
    }
    return;
  }
  const line = receiptLineForEan(code, receiptLines.value, materials.value);
  if (line) {
    openReceiptLine(line.id);
    return;
  }
  useSonner.error("Nenhum item desta entrada com este código. Toque em Item para lançar.");
}

const volumeScanOpen = ref(false);
const volumeScanCodes = ref<string[]>([]);
const volumeScanCount = computed(() => volumeScanCodes.value.length);
function openVolumeScanner() {
  volumeScanCodes.value = [];
  volumeScanOpen.value = true;
}
function onVolumeCode(code: string) {
  // Cada leitura é um volume.
  volumeScanCodes.value = [...volumeScanCodes.value, code];
  volumesDraft.value = volumeScanCodes.value.length;
}
function finishVolumeScan() {
  volumeScanOpen.value = false;
  if (volumeScanCount.value > 0) {
    volumesDraft.value = volumeScanCount.value;
    onExceptionCount(volumeScanCount.value);
  }
}

const packageScanOpen = ref(false);
const packageLineId = ref("");
function openPackageScanner(lineId: string) {
  packageLineId.value = lineId;
  packageScanOpen.value = true;
}
function onPackageCode(code: string) {
  const reading = parseGs1(code);
  if (!reading || (!reading.expiry && !reading.lot)) {
    useSonner.error("Este código não traz validade nem lote. Escolha a data à mão.");
    return;
  }
  const patch: Partial<ReceiptLine> = {};
  if (reading.expiry) patch.expiryDate = reading.expiry;
  if (reading.lot) patch.invoiceLot = reading.lot;
  updateReceiptLine(packageLineId.value, patch);
  useSonner.success(
    [reading.expiry ? `Vence ${formatShortDate(reading.expiry)}` : "", reading.lot ? `lote ${reading.lot}` : ""].filter(Boolean).join(" · "),
  );
}

// ── A ação do momento no celular ────────────────────────────────────────────
const firstBlockerLabel = computed(() => {
  const blocker = receiptFirstBlocker.value;
  if (!blocker) return "";
  const where = blocker.label ? ` em ${blocker.label}` : "";
  const more = receiptTotalPending.value > 1 ? ` · e mais ${receiptTotalPending.value - 1}` : "";
  return `${blocker.step}${where}${more}`;
});
const thumbAction = computed(() => {
  if (receiveStart.value) {
    return {
      action: {
        label: actionPending.value ? "Lendo a NF" : "Escanear NF",
        icon: "i-lucide-scan-line",
        loading: actionPending.value,
        disabled: readonlyFallback.value || scannerOpen.value,
        onSelect: () => void openInvoiceScanner(),
      },
      secondary: { label: "Sem NF", icon: "i-lucide-clipboard-pen-line", onSelect: () => startManualReceipt() },
      contextLabel: "QR ou código de barras do DANFE",
      contextValue: "",
    };
  }
  if (thumbCount.value) {
    return {
      action: {
        label: `Contei ${plural(volumesDraft.value, "volume", "volumes")}`,
        icon: "i-lucide-check",
        disabled: readonlyFallback.value || actionPending.value || volumesDraft.value <= 0,
        reason: volumesDraft.value <= 0 ? "Conte os volumes que chegaram antes de seguir." : "",
        onSelect: () => onExceptionCount(volumesDraft.value),
      },
      secondary: { label: "Algo não bate", icon: "i-lucide-circle-help", onSelect: () => onSomethingOff() },
      contextLabel: `A NF declara ${plural(receiptInvoiceVolumes.value, "volume", "volumes")}`,
      contextValue: formatMoney(receiptTotalCostQ.value),
    };
  }
  return {
    action: {
      label: actionPending.value ? "Confirmando a entrada" : "Confirmar entrada",
      icon: receiptReady.value ? "i-lucide-check" : "i-lucide-arrow-up",
      loading: actionPending.value,
      disabled: readonlyFallback.value,
      onSelect: () => void onConfirmReceipt(),
    },
    secondary: undefined,
    contextLabel: firstBlockerLabel.value || receiptDocumentTitle.value || "Entrada em conferência",
    contextValue: formatMoney(receiptTotalCostQ.value),
  };
});
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Receber" :phone-title="phoneTitle" :actions="headerActions" actions-label="Mais ações do Receber">
      <!-- Celular com a entrada aberta: "‹" volta ao começo, com a conferência guardada
           em "Em conferência · Continuar". -->
      <template v-if="conferenceOpen" #lead>
        <NuxtButton
          icon="i-lucide-chevron-left"
          color="neutral"
          variant="ghost"
          square
          class="md:hidden"
          aria-label="Voltar ao começo do Receber"
          data-receipt-back
          @click="receiptParked = true"
        />
      </template>
      <template v-if="conferenceOpen" #subtitle>
        <p class="text-xs text-muted tabular-nums md:hidden" data-receipt-subtitle>{{ documentLine }}</p>
      </template>
      <template #status>
        <PurchaseReadStatus />
        <NuxtBadge v-if="volumesBadge" color="success" icon="i-lucide-package-check" :label="volumesBadge" data-receipt-volumes-badge />
        <NuxtBadge
          v-if="receiptMode === 'invoice' && invoiceStatus.valid"
          color="success"
          icon="i-lucide-check"
          :label="invoiceKeyLabel"
          class="max-md:hidden"
          data-receipt-key-badge
        />
        <!-- O documento da entrada aberta, ao lado do título (na mesa). -->
        <span v-if="!receiptIsBlank" class="min-w-0 text-sm max-md:hidden" data-receipt-document>
          <span class="font-semibold">{{ receiptDocumentTitle || "Entrada em conferência" }}</span>
          <span class="text-muted tabular-nums">
            · {{ receiptSupplier?.paymentTerm || "prazo a combinar" }} · {{ formatMoney(receiptTotalCostQ) }}
          </span>
        </span>
      </template>
      <!-- Com a conferência aberta, a busca acha o item da entrada. -->
      <template v-if="!receiveStart" #search>
        <OperatorSuiteSearch
          v-model="receiveQuery"
          screen-label="filtrando a entrada"
          placeholder="Buscar item da entrada"
          aria-label="Buscar item da entrada"
        />
      </template>
      <!-- Origem da entrada (só no começo): com NF ou sem NF. -->
      <template v-if="receiptIsBlank" #filters-primary>
        <div class="flex gap-1" role="group" aria-label="Origem da entrada" data-receipt-origin>
          <NuxtButton
            icon="i-lucide-scan-line"
            label="Com NF"
            color="neutral"
            variant="ghost"
            :active="receiptMode === 'invoice'"
            active-variant="soft"
            active-color="primary"
            :aria-pressed="receiptMode === 'invoice'"
            @click="setReceiptMode('invoice')"
          />
          <NuxtButton
            icon="i-lucide-clipboard-pen-line"
            label="Sem NF"
            color="neutral"
            variant="ghost"
            :active="receiptMode === 'manual'"
            active-variant="soft"
            active-color="primary"
            :aria-pressed="receiptMode === 'manual'"
            @click="setReceiptMode('manual')"
          />
        </div>
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 overflow-auto p-4 sm:p-6" data-receive-scroll>
      <PurchaseLoadState>
        <div
          class="grid min-h-0 grid-cols-1 gap-4"
          :class="splitDrawer ? 'md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] md:items-start' : 'xl:grid-cols-[minmax(0,1fr)_24rem]'"
          data-receive
        >
          <div class="min-w-0 space-y-4">
            <!-- Deu certo: a tela diz isso no topo, com o que entrou por extenso e o
                 gesto seguinte dentro do próprio aviso. -->
            <NuxtAlert
              v-if="receiptOutcome"
              variant="subtle"
              :color="receiptOutcome.kind === 'confirmed' ? 'success' : 'warning'"
              :icon="receiptOutcome.kind === 'confirmed' ? 'i-lucide-check-check' : 'i-lucide-undo-2'"
              :title="receiptOutcome.kind === 'confirmed' ? 'Entrada confirmada no estoque' : 'Devolução registrada'"
              :description="`${receiptOutcomeSummary(receiptOutcome)} · ${receiptOutcome.at}`"
              :actions="[
                {
                  label: receiptOutcome.mode === 'manual' ? 'Lançar outra entrada' : 'Escanear outra NF',
                  icon: receiptOutcome.mode === 'manual' ? 'i-lucide-clipboard-pen-line' : 'i-lucide-scan-line',
                  color: receiptOutcome.kind === 'confirmed' ? 'success' : 'warning',
                  variant: 'outline',
                  disabled: readonlyFallback || actionPending,
                  onClick: startNextReceipt,
                },
              ]"
              close
              data-receipt-outcome
              aria-live="polite"
              @update:open="(open: boolean) => { if (!open) dismissReceiptOutcome(); }"
            />

            <!-- ── Começo: o que se LÊ no alto (a conferência aberta e as entradas de
                 hoje); o que se FAZ no polegar (Escanear NF, Sem NF). -->
            <template v-if="receiveStart">
              <NuxtCard v-if="receiptRows.length" data-receipt-in-progress>
                <div class="flex items-center gap-3">
                  <div class="min-w-0 flex-1">
                    <p class="text-xs text-muted">Em conferência</p>
                    <p class="text-base font-semibold">{{ receiptDocumentTitle || "Entrada aberta" }}</p>
                    <p class="text-xs text-muted tabular-nums">
                      {{ receiptConference.ready }} de {{ plural(receiptConference.total, "conferido", "conferidos") }}<template v-if="receiptTotalPending"> · {{ plural(receiptTotalPending, "pendência", "pendências") }}</template>
                    </p>
                  </div>
                  <NuxtButton label="Continuar" data-receipt-continue @click="receiptParked = false" />
                </div>
              </NuxtCard>

              <!-- Celular: a chave se digita sob demanda (o polegar é da câmera). -->
              <NuxtButton
                v-if="!keyEntryOpen"
                icon="i-lucide-keyboard"
                label="Digitar a chave da NF"
                color="neutral"
                variant="outline"
                block
                class="md:hidden"
                data-receipt-type-key
                @click="openKeyEntry()"
              />
              <NuxtCard :class="keyEntryOpen ? '' : 'max-md:hidden'" data-receipt-key-entry>
                <NuxtFormField
                  label="QR, código de barras ou chave da NF"
                  data-receipt-anchor="invoice"
                  class="scroll-mt-4"
                  :class="anchorRing('invoice')"
                >
                  <NuxtTextarea
                    v-model="invoiceInput"
                    :rows="2"
                    autoresize
                    placeholder="Escaneie, cole ou digite a chave de acesso"
                    class="w-full [&_textarea]:tabular-nums"
                  />
                </NuxtFormField>
                <div class="mt-2 grid grid-cols-2 gap-2">
                  <NuxtButton
                    icon="i-lucide-file-check-2"
                    :label="actionPending ? 'Lendo a NF' : 'Ler a chave'"
                    color="neutral"
                    variant="outline"
                    block
                    :loading="actionPending"
                    :disabled="readonlyFallback || !invoiceInput.trim()"
                    @click="onReadInvoice()"
                  />
                  <NuxtButton
                    icon="i-lucide-image-up"
                    label="Ler foto da NF"
                    color="neutral"
                    variant="outline"
                    block
                    :disabled="readonlyFallback || actionPending"
                    @click="openInvoiceImagePicker()"
                  />
                </div>
                <NuxtAlert v-if="scannerError" class="mt-2" variant="subtle" color="warning" :title="scannerError" />
              </NuxtCard>
              <input ref="scannerFileInput" class="sr-only" type="file" accept="image/*" capture="environment" @change="readInvoiceImage" />

              <!-- Mesa e tablet: o "Escanear NF" grande no começo (no celular, na base). -->
              <NuxtButton
                size="xl"
                icon="i-lucide-scan-line"
                :label="actionPending ? 'Lendo a NF' : 'Escanear NF'"
                block
                class="max-md:hidden"
                :loading="actionPending"
                :disabled="readonlyFallback || scannerOpen"
                data-receipt-scan
                @click="openInvoiceScanner()"
              />

              <section v-if="todayReceipts.length" aria-labelledby="today-title" data-receipts-today>
                <div class="flex items-baseline justify-between">
                  <h2 id="today-title" class="text-sm font-semibold">Entradas de hoje</h2>
                  <span class="text-xs text-muted tabular-nums">{{ todayReceipts.length }}</span>
                </div>
                <NuxtCard class="mt-2">
                  <ul class="divide-y divide-default">
                    <li v-for="entry in todayReceipts" :key="entry.sourceRef">
                      <NuxtButton
                        color="neutral"
                        variant="ghost"
                        block
                        class="justify-start py-2 text-start"
                        :aria-label="`Comprovante de ${entry.supplierName || entry.supplierRef}`"
                        @click="receiptSheetEntry = entry"
                      >
                        <span class="min-w-0 flex-1">
                          <span class="block text-sm font-semibold">{{ entry.supplierName || entry.supplierRef }}</span>
                          <span class="block text-xs text-muted tabular-nums">{{ receiptHistoryLine(entry) }}</span>
                        </span>
                        <span class="shrink-0 text-sm font-semibold tabular-nums">{{ formatMoney(entry.totalCostQ) }}</span>
                      </NuxtButton>
                    </li>
                  </ul>
                </NuxtCard>
                <p class="mt-2 text-xs text-muted">Toque numa entrada para ver o comprovante e compartilhar.</p>
              </section>
            </template>

            <!-- ── Conferência aberta ─────────────────────────────────────────── -->
            <template v-else>
              <!-- Sem NF: o fornecedor e a referência em papel (com NF eles vêm da nota). -->
              <NuxtCard v-if="receiptMode !== 'invoice'" data-receipt-manual-doc>
                <div class="grid gap-3 lg:grid-cols-2">
                  <NuxtFormField label="Fornecedor" data-receipt-anchor="supplier" class="scroll-mt-4" :class="anchorRing('supplier')">
                    <NuxtSelectMenu
                      :model-value="receiptSupplierRef || undefined"
                      :items="supplierItems"
                      value-key="value"
                      placeholder="Escolher o fornecedor"
                      :search-input="{ autofocus: !touch, placeholder: 'Buscar fornecedor' }"
                      class="w-full"
                      @update:model-value="(value: unknown) => setReceiptSupplier(String(value ?? ''))"
                    />
                  </NuxtFormField>
                  <NuxtFormField label="Referência em papel">
                    <NuxtTextarea v-model="receiptNote" :rows="2" autoresize placeholder="Romaneio, produtor, observação" class="w-full" />
                  </NuxtFormField>
                </div>
              </NuxtCard>
              <!-- Com NF lida mas sem fornecedor certo: o vínculo antes de tudo. -->
              <NuxtCard v-else-if="!receiptSupplierRef || receiptSupplierBlockers.length" data-receipt-supplier-link>
                <NuxtFormField
                  label="Fornecedor da nota"
                  description="A NF não casou com um fornecedor da Base. Escolha quem é."
                  data-receipt-anchor="supplier"
                  class="scroll-mt-4"
                  :class="anchorRing('supplier')"
                >
                  <NuxtSelectMenu
                    :model-value="receiptSupplierRef || undefined"
                    :items="supplierItems"
                    value-key="value"
                    placeholder="Escolher o fornecedor"
                    :search-input="{ autofocus: !touch, placeholder: 'Buscar fornecedor' }"
                    class="w-full"
                    @update:model-value="(value: unknown) => setReceiptSupplier(String(value ?? ''))"
                  />
                </NuxtFormField>
              </NuxtCard>

              <!-- Recebimento por exceção (com NF): o que bate entra pela contagem de
                   volumes; a validade é pedida uma linha por vez; só o que não bate pede
                   atenção. -->
              <ReceiptExceptionFlow
                v-if="exceptionFlowOn"
                v-model:draft="volumesDraft"
                v-model:matched-open="matchedOpen"
                :view="receiptException"
                :materials="materials"
                :line-count="receiptLinePreviews.length"
                :total-cost-q="receiptTotalCostQ"
                :declared-volumes="receiptInvoiceVolumes"
                :pending="readonlyFallback || actionPending"
                :volumes-ring="anchorRing('volumes')"
                :count-in-thumb="phone"
                @count="onExceptionCount"
                @expiry="onExceptionExpiry"
                @open="openReceiptLine"
                @scan-volumes="openVolumeScanner"
                @read-package="openPackageScanner"
                @qty="(lineId: string, qty: number) => updateReceiptLine(lineId, { purchaseQty: qty })"
                @reason="(lineId: string, reason: string) => updateReceiptLine(lineId, { lineNote: reason })"
                @reject-line="onRejectLine"
              />

              <!-- A lista da entrada. No celular com a conferência por exceção ela vive
                   recolhida no "Ver os N itens" do fluxo. -->
              <NuxtCard :class="exceptionFlowOn ? 'max-md:hidden' : ''" data-receipt-list>
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <div class="min-w-0">
                    <h2 class="text-base font-semibold">Itens da entrada</h2>
                    <p class="text-xs text-muted">{{ receiptConference.label }}</p>
                  </div>
                  <div class="flex gap-2">
                    <NuxtButton icon="i-lucide-plus" label="Item" color="neutral" variant="outline" @click="addAndOpenReceiptLine()" />
                    <NuxtButton icon="i-lucide-scan-barcode" label="Ler EAN" color="neutral" variant="outline" data-scan-ean @click="openEanScanner('find')" />
                  </div>
                </div>
                <ul v-if="visibleReceiptRows.length" class="mt-3 grid min-w-0 grid-cols-1 gap-2">
                  <li
                    v-for="row in visibleReceiptRows"
                    :key="row.id"
                    :data-receipt-line="row.id"
                    class="flex min-w-0 scroll-mt-4 items-stretch gap-1 rounded-md border pr-1"
                    :class="[RECEIPT_LINE_STATUS_ROW[row.status], openLineId === row.id ? 'outline-2 -outline-offset-2 outline-primary' : '']"
                  >
                    <NuxtLink
                      :to="lineLocation(row.id)"
                      replace
                      class="flex min-h-14 min-w-0 flex-1 items-center gap-3 py-2 pl-3"
                      :aria-label="`Abrir ${row.label}`"
                    >
                      <Icon :name="row.statusIcon" class="size-5 shrink-0" :class="RECEIPT_LINE_STATUS_TEXT[row.status]" />
                      <span class="min-w-0 flex-1">
                        <span class="block text-sm font-semibold">{{ row.label }}</span>
                        <span v-if="row.digest" class="block text-xs text-muted tabular-nums">{{ row.digest }}</span>
                        <span v-if="row.nextStep" class="block text-xs font-medium text-error">{{ row.nextStep }}</span>
                        <span v-else-if="row.note" class="block text-xs text-warning">{{ row.note }}</span>
                      </span>
                      <span class="flex shrink-0 flex-col items-end gap-1">
                        <span v-if="row.total && !splitDrawer" class="text-sm font-semibold tabular-nums">{{ row.total }}</span>
                        <NuxtBadge :color="RECEIPT_LINE_STATUS_COLOR[row.status]" :label="row.statusLabel" />
                      </span>
                    </NuxtLink>
                    <NuxtButton
                      v-if="!splitDrawer"
                      icon="i-lucide-trash-2"
                      color="error"
                      variant="ghost"
                      square
                      class="self-center"
                      :aria-label="`Remover ${row.label}`"
                      @click="removeReceiptLine(row.id)"
                    />
                  </li>
                </ul>
                <OperatorScreenState
                  v-else
                  state="empty"
                  in-card
                  icon="i-lucide-list-checks"
                  :title="receiveQuery.trim() ? `Nenhum item da entrada com “${receiveQuery.trim()}”.` : 'Nenhum item na entrada ainda.'"
                  :description="receiveQuery.trim() ? '' : 'Escaneie a NF, ou toque em Item para lançar à mão.'"
                />
              </NuxtCard>

              <!-- Tablet: o resumo, Confirmar entrada e Registrar devolução no pé da coluna
                   da esquerda. -->
              <ReceiptConferencePanel
                v-if="splitDrawer"
                v-bind="conferencePanelProps"
                @confirm="onConfirmReceipt"
                @reject="onRejectReceipt"
                @anchor="focusReceiptAnchor"
                @line="(id: string) => focusReceiptLine(id)"
                @ressalva="ressalvaOpen = true"
              />
            </template>
          </div>

          <!-- O item aberto. Tablet: encaixado ao lado da lista. Celular e mesa larga: a
               folha por cima. -->
          <ReceiptLineSheet
            v-if="!receiveStart"
            v-model:open="lineSheetOpen"
            :docked="splitDrawer"
            :preview="openPreview"
            :materials="materials"
            :conversions="openPreview ? receiptConversionsFor(openPreview.line.materialSku) : []"
            :pending="actionPending"
            :stock-after="openPreview ? stockAfterReceipt(openPreview.material.sku) : 0"
            :flash-field="sheetFlashField"
            @update="onSheetUpdate"
            @select-material="onSheetSelectMaterial"
            @accept-suggestion="openLineId && acceptReceiptLineSuggestion(openLineId)"
            @select-conversion="(conversionId: string | null) => onSheetUpdate({ conversionId })"
            @accept-conversion="openLineId && acceptReceiptLineConversion(openLineId)"
            @accept-axes="openLineId && acceptReceiptLineInvoiceAxes(openLineId)"
            @declare-conversion="onSheetDeclareConversion"
            @check="(checked: boolean) => onSheetUpdate({ checked })"
            @remove="removeOpenReceiptLine"
            @scan-ean="openEanScanner('line')"
            @read-package="openLineId && openPackageScanner(openLineId)"
            @reject-line="openLineId && onRejectLine(openLineId)"
          >
            <template #nav>
              <OperatorRecordNav
                v-if="openLineId"
                :trail="RECEIPT_LINES_TRAIL"
                :current="openLineId"
                :to="lineLocation"
                previous-label="Item anterior"
                next-label="Próximo item"
              />
            </template>
          </ReceiptLineSheet>

          <!-- Mesa larga: a conferência ao lado da lista. -->
          <aside v-if="!receiveStart && !splitDrawer" class="h-fit min-w-0 max-md:hidden" data-receipt-conference>
            <ReceiptConferencePanel
              v-bind="conferencePanelProps"
              @confirm="onConfirmReceipt"
              @reject="onRejectReceipt"
              @anchor="focusReceiptAnchor"
              @line="(id: string) => focusReceiptLine(id)"
              @ressalva="ressalvaOpen = true"
            />
          </aside>
        </div>
      </PurchaseLoadState>
    </section>

    <!-- Celular: a ação do momento na base (Escanear NF · Contei N volumes · Confirmar
         entrada). Do tablet para cima ela está no painel da conferência. -->
    <OperatorActionBar
      class="md:hidden"
      :action="thumbAction.action"
      :secondary="thumbAction.secondary"
      :context-label="thumbAction.contextLabel"
      :context-value="thumbAction.contextValue"
      label="Ação do Receber"
      data-receipt-thumb
    />

    <!-- As câmeras do item. -->
    <CodeScannerSheet
      v-model:open="eanScanOpen"
      title="Ler EAN"
      hint="Enquadre o código de barras da caixa ou da embalagem."
      @code="onEanCode"
    />
    <CodeScannerSheet
      v-model:open="volumeScanOpen"
      title="Bipar cada volume"
      hint="Passe a câmera no código de cada caixa, saco ou fardo. Cada leitura conta um volume."
      continuous
      :progress="`${volumeScanCount} de ${plural(receiptException.expectedVolumes ?? 0, 'volume', 'volumes')}`"
      @code="onVolumeCode"
    >
      <div class="flex gap-2">
        <NuxtButton label="Zerar" color="neutral" variant="outline" size="xl" class="flex-1 justify-center" @click="volumeScanCodes = []" />
        <NuxtButton icon="i-lucide-check" :label="`Usar ${volumeScanCount}`" size="xl" class="flex-[1.4] justify-center" @click="finishVolumeScan()" />
      </div>
    </CodeScannerSheet>
    <CodeScannerSheet
      v-model:open="packageScanOpen"
      title="Ler da embalagem"
      hint="Enquadre o código GS1 da caixa (o de barras longo ou o quadradinho): ele traz a validade e o lote."
      @code="onPackageCode"
    />

    <!-- O comprovante de uma entrada de hoje, com Compartilhar. -->
    <NuxtDrawer
      :open="receiptSheetEntry != null"
      title="Comprovante de entrada"
      :description="receiptSheetEntry ? receiptSheetEntry.supplierName || receiptSheetEntry.supplierRef : ''"
      @update:open="(open: boolean) => { if (!open) receiptSheetEntry = null; }"
    >
      <template #body>
        <div v-if="receiptSheetEntry" data-receipt-voucher>
          <dl class="grid grid-cols-2 gap-3">
            <div><dt class="text-xs text-muted">Documento</dt><dd class="text-sm font-semibold tabular-nums">{{ receiptVoucherDocument(receiptSheetEntry) }}</dd></div>
            <div><dt class="text-xs text-muted">Quando</dt><dd class="text-sm font-semibold tabular-nums">{{ receiptSheetEntry.receivedAtDisplay }}</dd></div>
            <div><dt class="text-xs text-muted">Itens</dt><dd class="text-sm font-semibold tabular-nums">{{ receiptSheetEntry.lines }}</dd></div>
            <div><dt class="text-xs text-muted">Valor</dt><dd class="text-sm font-semibold tabular-nums">{{ formatMoney(receiptSheetEntry.totalCostQ) }}</dd></div>
            <div class="col-span-2"><dt class="text-xs text-muted">Recebido por</dt><dd class="text-sm font-semibold">{{ receiptSheetEntry.operator || "não registrado" }}</dd></div>
          </dl>
          <NuxtButton
            class="mt-4"
            icon="i-lucide-share-2"
            label="Compartilhar"
            size="xl"
            block
            :loading="sharingReceipt"
            data-receipt-share
            @click="shareReceipt(receiptSheetEntry)"
          />
        </div>
      </template>
    </NuxtDrawer>

    <!-- Ressalva geral: abre pelo ⋯ ou pelo painel da conferência. -->
    <NuxtModal
      v-model:open="ressalvaOpen"
      title="Ressalva geral"
      description="Avaria, falta, devolução, observação na NF ou no CT-e. Vale para a entrada inteira."
    >
      <template #body>
        <div data-receipt-ressalva>
          <NuxtTextarea v-model="receiptNote" :rows="4" autoresize placeholder="Avaria, falta, devolução, observação na NF ou no CT-e" class="w-full" />
          <NuxtButton class="mt-3" label="Pronto" block @click="ressalvaOpen = false" />
        </div>
      </template>
    </NuxtModal>

    <!-- A câmera da NF, em tela cheia. -->
    <NuxtModal
      :open="scannerOpen"
      fullscreen
      :close="false"
      title="Escanear NF"
      description="Aponte para o QR ou para o código de barras do DANFE."
      @update:open="(open: boolean) => { if (!open) stopInvoiceScanner(); }"
    >
      <template #content>
        <div class="flex h-full flex-col bg-inverted p-3 text-inverted md:p-6" data-invoice-scanner>
          <div class="flex items-center justify-between gap-3 pb-3">
            <NuxtButton
              icon="i-lucide-x"
              color="neutral"
              variant="ghost"
              square
              size="xl"
              class="text-inverted"
              aria-label="Fechar a câmera"
              @click="stopInvoiceScanner()"
            />
            <p class="text-base font-semibold">Escanear NF</p>
            <NuxtButton
              v-if="scannerCanTorch"
              :icon="scannerTorchOn ? 'i-lucide-flashlight-off' : 'i-lucide-flashlight'"
              color="neutral"
              variant="ghost"
              square
              size="xl"
              class="text-inverted"
              :aria-label="scannerTorchOn ? 'Desligar a lanterna' : 'Ligar a lanterna'"
              :loading="torchSwitching"
              @click="toggleScannerTorch()"
            />
            <span v-else class="size-12" aria-hidden="true" />
          </div>
          <div class="relative min-h-0 flex-1 overflow-hidden rounded-lg bg-black">
            <video ref="scannerVideo" muted playsinline class="h-full w-full object-cover" data-invoice-scanner-video />
            <div class="pointer-events-none absolute inset-x-8 top-1/2 h-40 -translate-y-1/2 rounded-md border-4 border-success shadow-[0_0_0_999px_rgba(0,0,0,0.35)]" />
          </div>
          <p class="mx-auto mt-3 max-w-xl text-sm">
            {{ scannerHint || "Aponte para o QR ou para o código de barras da nota." }}
            Para barras, deixe a linha inteira visível, na horizontal, sem cortar as laterais.
          </p>
          <NuxtButton
            class="mx-auto mt-3 w-full max-w-xl"
            icon="i-lucide-image-up"
            label="Ler foto da NF"
            color="neutral"
            variant="outline"
            size="xl"
            block
            @click="() => { stopInvoiceScanner(); openInvoiceImagePicker(); }"
          />
        </div>
      </template>
    </NuxtModal>
  </main>
</template>

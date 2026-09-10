<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import type { WeighingTicketProjection } from "~/types/production";
import type {
  ProductionBlindLabel,
  ProductionPreparationLabelTicket,
  ProductionPrintingSourceProjection,
} from "~/types/productionPrinting";
import {
  blindLabelsFromPrintDocument,
  operationalTargetDisplay,
  preparationLabelsFromPrintDocument,
} from "~/presentation/weighing";
import {
  isProvenPrintFailure,
  isReprintState,
} from "~/composables/useProductionLabelPrinting";
import {
  callLocalDeviceAgent,
  localDeviceAgentErrorMessage,
  printWithLocalDeviceAgent,
} from "../../../operator-kit/app/utils/localDeviceAgent";
const props = defineProps<{
  open: boolean;
  printMode: "pesagem" | "preparo";
  labels: ProductionBlindLabel[];
  tickets: WeighingTicketProjection[];
  selectedDate: string;
  dateDisplay: string;
  projection: ProductionPrintingSourceProjection | null;
  refreshProjection: () => unknown;
}>();

const emit = defineEmits<{
  "update:open": [open: boolean];
}>();

const printing = useProductionLabelPrinting({
  projection: computed(() => props.projection),
  selectedDate: computed(() => props.selectedDate),
  refreshProjection: props.refreshProjection,
});

const labelMode = computed(() =>
  props.printMode === "pesagem" ? ("blind" as const) : ("explicit" as const),
);
const ticketRefs = computed(() => [
  ...new Set(
    props.tickets.map(
      (ticket) => ticket.ticket_ref?.trim() || ticket.recipe_ref,
    ),
  ),
]);
const frozenDocument = computed(
  () => printing.job.value?.print_document ?? null,
);
const effectivePrintMode = computed<"pesagem" | "preparo">(() => {
  const document = frozenDocument.value;
  if (!document) return props.printMode;
  return document.mode === "blind" ? "pesagem" : "preparo";
});
const effectiveLabels = computed<ProductionBlindLabel[]>(() => {
  const document = frozenDocument.value;
  return document ? blindLabelsFromPrintDocument(document) : props.labels;
});
const effectiveTickets = computed<ProductionPreparationLabelTicket[]>(() => {
  const document = frozenDocument.value;
  return document
    ? preparationLabelsFromPrintDocument(document)
    : props.tickets;
});
const labelCount = computed(() =>
  effectivePrintMode.value === "pesagem"
    ? effectiveLabels.value.length
    : effectiveTickets.value.length,
);
const title = computed(() =>
  effectivePrintMode.value === "pesagem"
    ? "Etiquetas de pesagem"
    : "Identificação interna do preparo",
);
const effectiveDateDisplay = computed(
  () =>
    frozenDocument.value?.tickets[0]?.made_display ||
    frozenDocument.value?.selected_date ||
    props.dateDisplay ||
    props.selectedDate,
);
const summary = computed(
  () =>
    `${labelCount.value} ${labelCount.value === 1 ? "etiqueta" : "etiquetas"} · ${effectiveDateDisplay.value}`,
);
const confirmationQuestion = computed(() =>
  labelCount.value === 1
    ? "A etiqueta saiu corretamente?"
    : `As ${labelCount.value} etiquetas saíram corretamente?`,
);
const scaleRoundingNote = computed(
  () =>
    frozenDocument.value?.scale_rounding_note ||
    props.projection?.scale_rounding_note ||
    "",
);
const previewLabels = computed(() => effectiveLabels.value.slice(0, 3));
const previewTickets = computed(() => effectiveTickets.value.slice(0, 3));
const remainingCount = computed(() =>
  Math.max(
    0,
    labelCount.value -
      (effectivePrintMode.value === "pesagem"
        ? previewLabels.value.length
        : previewTickets.value.length),
  ),
);
const showConfirm = computed(
  () =>
    !!printing.job.value?.can_confirm ||
    ["spooled", "accepted", "awaiting_confirmation", "uncertain"].includes(
      printing.job.value?.status.toLowerCase() ?? "",
    ),
);
const showRetry = computed(
  () =>
    !!printing.job.value?.can_retry && isProvenPrintFailure(printing.job.value),
);
const showReprint = computed(
  () => !!printing.job.value?.can_reprint && isReprintState(printing.job.value),
);
const isConfirmed = computed(
  () => printing.job.value?.status.toLowerCase() === "confirmed",
);
const copyNumber = computed(() => printing.job.value?.copy_number ?? 0);
const blockedReason = computed(() => printing.block.value?.detail ?? "");
const validityBlockReason = computed(() => {
  if (effectivePrintMode.value !== "preparo" || frozenDocument.value) return "";
  const missing = effectiveTickets.value
    .filter(
      (ticket) =>
        ticket.validity_configured === false || !ticket.expiry_display,
    )
    .map((ticket) => ticket.name)
    .filter(Boolean);
  if (!missing.length) return "";
  const names = missing.slice(0, 3).join(", ");
  return `Validade não configurada na ficha técnica de: ${names}${missing.length > 3 ? "…" : ""}. O gestor define uma vez; o sistema não presume D+1.`;
});
const preflightBlockReason = computed(
  () => blockedReason.value || validityBlockReason.value,
);
const relayUnavailableReason = computed(() => {
  const destination = props.projection?.print_destination;
  if (!destination || destination.available !== false) return "";
  return (
    destination.status_label || "A estação de impressão não está disponível."
  );
});
const printDestination = computed(() => props.projection?.print_destination);
const labelWidthMm = computed(
  () => printDestination.value?.label_width_mm || 60,
);
const labelHeightMm = computed(
  () => printDestination.value?.label_height_mm || 40,
);
const printableWidthMm = computed(
  () => printDestination.value?.printable_width_mm || labelWidthMm.value - 8,
);
const previewStyle = computed(() => ({
  width: `${labelWidthMm.value}mm`,
  minHeight: `${labelHeightMm.value}mm`,
}));
const localAgentAvailable = computed(
  () => printDestination.value?.local_agent_available === true,
);
const activeTransport = ref<"relay" | "browser" | null>(null);
const usedLocalAgent = ref(false);
const localPrintNote = ref("");
const deviceProbeBusy = ref(false);
const browserBusy = ref(false);
const actionBusy = computed(
  () => printing.busy.value || browserBusy.value || deviceProbeBusy.value,
);
let wasOpen = false;

watch(
  () => props.open,
  (open) => {
    // Um job aberto é um documento imutável. Mudanças da projeção viva não o
    // substituem; uma nova seleção só começa ao reabrir o fluxo.
    if (open && !wasOpen) {
      activeTransport.value = null;
      usedLocalAgent.value = false;
      localPrintNote.value = "";
      printing.reset();
    }
    wasOpen = open;
  },
  { immediate: true },
);

function selection() {
  return { mode: labelMode.value, ticketRefs: ticketRefs.value };
}

async function createRelay() {
  if (actionBusy.value) return;
  activeTransport.value = "relay";
  await printing.create(selection(), "relay");
}

async function sendPreparedJobToLocalAgent(): Promise<boolean> {
  const destination = printDestination.value;
  const job = printing.job.value;
  if (
    !destination?.local_agent_available ||
    !destination.local_agent_url ||
    !destination.local_agent_token ||
    !job?.payload_b64
  )
    return false;
  try {
    const payload = await printWithLocalDeviceAgent(
      {
        agent_url: destination.local_agent_url,
        token: destination.local_agent_token,
      },
      job.payload_b64,
      job.print_title || "Etiquetas de preparação",
    );
    usedLocalAgent.value = true;
    localPrintNote.value = "Enviado à impressora configurada neste PC.";
    await printing.recordBrowserResult(
      "agent_spooled",
      `Fila ${String(payload?.queue || "local")} · job ${String(payload?.job_id || "aceito")}`,
    );
    return true;
  } catch (error) {
    const reason = localDeviceAgentErrorMessage(error);
    usedLocalAgent.value = false;
    localPrintNote.value = `${reason} Abrimos a impressão do navegador como alternativa.`;
    await printing.recordBrowserResult("agent_failed", reason);
    return false;
  }
}

const PRINT_EVENT_PROBE_MS = 220;
const NATIVE_PAGE_STYLE_ID = "production-label-page-size";

function installNativePageStyle(): HTMLStyleElement | null {
  if (typeof document === "undefined") return null;
  document.getElementById(NATIVE_PAGE_STYLE_ID)?.remove();
  const style = document.createElement("style");
  style.id = NATIVE_PAGE_STYLE_ID;
  // Valores vêm da projeção validada pelo backend. O driver ainda precisa usar
  // o mesmo papel, mas o navegador deixa de presumir A4 no fallback.
  style.textContent = `@media print { @page { size: ${labelWidthMm.value}mm ${labelHeightMm.value}mm; margin: 0; } }`;
  document.head.appendChild(style);
  return style;
}

async function openNativePrintDialog(): Promise<void> {
  if (browserBusy.value) return;
  if (!frozenDocument.value) {
    printing.errorCode.value = "print_document_missing";
    printing.errorMessage.value =
      "O documento congelado não veio do servidor. Atualize antes de imprimir.";
    return;
  }
  browserBusy.value = true;
  await nextTick();
  const pageStyle = installNativePageStyle();
  let dialogOpened = false;
  const markDialog = () => {
    dialogOpened = true;
  };
  if (typeof window === "undefined" || typeof window.print !== "function") {
    await printing.recordBrowserResult("dialog_unavailable");
    pageStyle?.remove();
    browserBusy.value = false;
    return;
  }
  window.addEventListener("beforeprint", markDialog, { once: true });
  window.addEventListener("afterprint", markDialog, { once: true });
  try {
    window.print();
  } catch {
    window.removeEventListener("beforeprint", markDialog);
    window.removeEventListener("afterprint", markDialog);
    await printing.recordBrowserResult("dialog_unavailable");
    pageStyle?.remove();
    browserBusy.value = false;
    return;
  }
  await new Promise((resolve) =>
    window.setTimeout(resolve, PRINT_EVENT_PROBE_MS),
  );
  window.removeEventListener("beforeprint", markDialog);
  window.removeEventListener("afterprint", markDialog);
  await printing.recordBrowserResult(
    dialogOpened ? "dialog_opened" : "dialog_unavailable",
  );
  pageStyle?.remove();
  browserBusy.value = false;
}

async function createBrowserPrint() {
  if (actionBusy.value) return;
  activeTransport.value = "browser";
  const created = await printing.create(selection(), "browser");
  if (created) await openNativePrintDialog();
}

async function createLocalAgentPrint() {
  if (actionBusy.value) return;
  activeTransport.value = "browser";
  const created = await printing.create(selection(), "browser");
  if (!created) return;
  if (!(await sendPreparedJobToLocalAgent())) await openNativePrintDialog();
}

async function localAgentIsReachable(): Promise<boolean> {
  const destination = printDestination.value;
  if (
    !destination?.local_agent_available ||
    !destination.local_agent_url ||
    !destination.local_agent_token
  )
    return false;
  try {
    const health = await callLocalDeviceAgent(
      {
        agent_url: destination.local_agent_url,
        token: destination.local_agent_token,
      },
      "/health",
      undefined,
      1_200,
    );
    return health.ok !== false;
  } catch {
    // Em tablet, a loopback naturalmente não contém o agente do PC. Isso não
    // é erro para o operador: a próxima rota é o relay já projetado.
    return false;
  }
}

async function printBestAvailable() {
  if (actionBusy.value) return;
  deviceProbeBusy.value = true;
  const localReachable = await localAgentIsReachable();
  deviceProbeBusy.value = false;
  if (localReachable) {
    await createLocalAgentPrint();
    return;
  }
  if (!relayUnavailableReason.value) {
    await createRelay();
    return;
  }
  await createBrowserPrint();
}

async function retry() {
  if (actionBusy.value) return;
  const retried = await printing.retry();
  if (retried && activeTransport.value === "browser")
    await openNativePrintDialog();
}

async function reprint() {
  if (actionBusy.value) return;
  const transport = activeTransport.value ?? "relay";
  const registered = await printing.reprint(transport);
  if (registered && transport === "browser") {
    if (usedLocalAgent.value && (await sendPreparedJobToLocalAgent())) return;
    await openNativePrintDialog();
  }
}

async function reconcileCreate() {
  if (actionBusy.value) return;
  await printing.create(selection(), activeTransport.value ?? "relay");
}

function close() {
  emit("update:open", false);
}
</script>

<template>
  <UiDialog :open="open" @update:open="emit('update:open', Boolean($event))">
    <UiDialogContent
      hide-close
      class="print:hidden sm:max-w-3xl"
      data-testid="production-label-print-dialog"
    >
      <UiDialogHeader>
        <UiDialogTitle>{{ title }}</UiDialogTitle>
        <UiDialogDescription>
          Confira o conteúdo e o destino antes de enviar. A confirmação final
          registra somente o que realmente saiu no papel.
        </UiDialogDescription>
      </UiDialogHeader>

      <UiAlert
        variant="info"
        icon="lucide:info"
        description="Estas etiquetas apoiam a preparação interna e não substituem o rótulo de venda."
      />

      <div class="grid min-h-0 gap-4 md:grid-cols-[minmax(0,1fr)_18rem]">
        <section aria-labelledby="label-preview-title" class="min-w-0">
          <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 id="label-preview-title" class="text-sm font-semibold">
                Prévia · etiqueta {{ labelWidthMm }} × {{ labelHeightMm }} mm
              </h3>
              <p class="text-xs text-muted-foreground">{{ summary }}</p>
              <p
                v-if="scaleRoundingNote"
                class="mt-1 text-xs text-muted-foreground"
              >
                {{ scaleRoundingNote }}
              </p>
            </div>
            <UiBadge variant="outline">{{ printableWidthMm }} mm úteis</UiBadge>
          </div>

          <div
            class="max-h-[46vh] overflow-auto rounded-lg border bg-muted/30 p-3"
          >
            <div
              class="label-roll-preview mx-auto flex max-w-full flex-col gap-2 bg-white p-[4mm] text-black shadow-sm"
              :style="previewStyle"
              aria-label="Conteúdo das etiquetas"
            >
              <template v-if="effectivePrintMode === 'pesagem'">
                <article
                  v-for="label in previewLabels"
                  :key="label.key"
                  class="rounded border border-black p-2"
                >
                  <p class="text-xs font-bold uppercase">Pesagem interna</p>
                  <div class="flex items-baseline justify-between gap-2">
                    <strong class="font-mono text-xl tracking-widest">{{
                      label.code
                    }}</strong>
                    <span class="text-xs">{{ label.date }}</span>
                  </div>
                  <p class="font-semibold">{{ label.ingredient }}</p>
                  <p class="font-mono text-xs">{{ label.sku }}</p>
                  <p class="text-lg font-bold tabular-nums">
                    {{ label.weight }}
                  </p>
                  <p
                    v-if="label.annotation"
                    class="text-sm text-muted-foreground"
                  >
                    {{ label.annotation }}
                  </p>
                </article>
              </template>
              <template v-else>
                <article
                  v-for="ticket in previewTickets"
                  :key="ticket.ticket_ref || ticket.output_sku"
                  class="rounded border border-black p-2"
                >
                  <span class="block text-xs font-bold uppercase">Preparo interno</span>
                  <strong class="block uppercase leading-tight">{{
                    ticket.name
                  }}</strong>
                  <span class="block font-mono text-xs">{{
                    ticket.output_sku
                  }}</span>
                  <span
                    v-if="
                      ticket.total_weight_display || ticket.dough_weight_display
                    "
                    class="block font-bold tabular-nums"
                  >
                    Alvo total:
                    {{
                      operationalTargetDisplay(
                        ticket.total_weight_display,
                        ticket.dough_weight_display,
                      )
                    }}
                  </span>
                  <span class="block text-xs">
                    Preparo {{ ticket.made_display }} · Validade
                    {{ ticket.expiry_display || "não configurada" }}
                  </span>
                </article>
              </template>
              <p
                v-if="remainingCount"
                class="rounded border border-dashed p-2 text-center text-xs font-medium"
              >
                + {{ remainingCount }}
                {{ remainingCount === 1 ? "etiqueta" : "etiquetas" }}
              </p>
            </div>
          </div>
        </section>

        <section
          class="flex min-w-0 flex-col gap-3"
          aria-label="Envio da impressão"
        >
          <div class="rounded-lg border p-3" data-testid="print-destination">
            <div class="flex items-start gap-2">
              <Icon name="lucide:printer" class="mt-0.5 size-5 shrink-0" />
              <div class="min-w-0">
                <p class="truncate text-sm font-semibold">
                  {{ printing.destinationLabel.value }}
                </p>
                <p class="text-xs text-muted-foreground">
                  {{ printing.destinationStatusLabel.value }}
                </p>
              </div>
            </div>
          </div>

          <div
            v-if="printing.job.value || printing.operation.value === 'create'"
            role="status"
            aria-live="polite"
            class="rounded-lg border p-3"
            data-testid="print-job-status"
          >
            <div class="flex items-start gap-2">
              <Icon
                :name="
                  actionBusy
                    ? 'line-md:loading-loop'
                    : isConfirmed
                      ? 'lucide:circle-check'
                      : 'lucide:info'
                "
                class="mt-0.5 size-5 shrink-0"
              />
              <div>
                <p class="font-semibold">{{ printing.statusLabel.value }}</p>
                <p
                  v-if="printing.job.value?.message"
                  class="mt-1 text-sm text-muted-foreground"
                >
                  {{ printing.job.value.message }}
                </p>
                <p v-if="copyNumber > 1" class="mt-1 text-xs font-medium">
                  Reimpressão {{ copyNumber }}
                </p>
              </div>
            </div>
          </div>

          <p
            v-if="printing.pollingMessage.value"
            role="status"
            aria-live="polite"
            class="text-sm text-amber-700"
          >
            {{ printing.pollingMessage.value }}
          </p>

          <p
            v-if="localPrintNote"
            role="status"
            aria-live="polite"
            class="text-sm text-muted-foreground"
          >
            {{ localPrintNote }}
          </p>

          <div
            v-if="printing.errorMessage.value"
            role="alert"
            class="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
            data-testid="print-error"
          >
            <p>{{ printing.errorMessage.value }}</p>
            <UiButton
              v-if="printing.errorCode.value === 'stale_projection'"
              type="button"
              variant="outline"
              class="mt-3 min-h-11"
              @click="printing.refreshSource()"
            >
              Atualizar etiquetas
            </UiButton>
            <UiButton
              v-else-if="printing.createUncertain.value"
              type="button"
              variant="outline"
              class="mt-3 min-h-11"
              :loading="actionBusy"
              @click="reconcileCreate"
            >
              Verificar envio
            </UiButton>
          </div>

          <p
            v-if="!printing.job.value && preflightBlockReason"
            role="alert"
            class="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-sm text-amber-800 dark:text-amber-200"
          >
            {{ preflightBlockReason }}
          </p>
          <p
            v-if="
              !printing.job.value &&
              !preflightBlockReason &&
              relayUnavailableReason
            "
            class="text-sm text-muted-foreground"
          >
            {{ relayUnavailableReason }} Você ainda pode imprimir neste
            dispositivo.
          </p>

          <div
            v-if="showConfirm"
            class="rounded-lg border border-primary/30 bg-primary/5 p-3"
          >
            <p class="mb-3 text-sm font-semibold">{{ confirmationQuestion }}</p>
            <div class="grid gap-2">
              <UiButton
                type="button"
                class="min-h-11"
                :loading="printing.operation.value === 'confirm'"
                :disabled="!printing.isOnline.value"
                @click="printing.confirm(true)"
              >
                Sim, saíram
              </UiButton>
              <UiButton
                type="button"
                variant="outline"
                class="min-h-11 whitespace-normal"
                :disabled="actionBusy || !printing.isOnline.value"
                @click="printing.confirm(false)"
              >
                Não saíram ou saiu incompleto
              </UiButton>
            </div>
          </div>

          <div
            v-if="!printing.job.value && !printing.createUncertain.value"
            class="grid gap-2"
          >
            <UiButton
              type="button"
              class="min-h-11 whitespace-normal"
              :loading="
                printing.operation.value === 'create' &&
                activeTransport === 'relay'
              "
              :disabled="
                !!preflightBlockReason || browserBusy
              "
              @click="printBestAvailable"
            >
              Imprimir {{ labelCount }}
              {{ labelCount === 1 ? "etiqueta" : "etiquetas" }}
            </UiButton>
            <UiButton
              v-if="localAgentAvailable || !relayUnavailableReason"
              type="button"
              variant="outline"
              class="min-h-11 whitespace-normal"
              :loading="browserBusy"
              :disabled="!!preflightBlockReason || printing.busy.value"
              @click="createBrowserPrint"
            >
              Abrir impressão do navegador
            </UiButton>
          </div>

          <UiButton
            v-if="showRetry"
            type="button"
            class="min-h-11"
            :loading="printing.operation.value === 'retry' || browserBusy"
            :disabled="!printing.isOnline.value"
            @click="retry"
          >
            Tentar novamente
          </UiButton>
          <UiButton
            v-if="showReprint"
            type="button"
            variant="outline"
            class="min-h-11"
            :loading="printing.operation.value === 'reprint' || browserBusy"
            :disabled="!printing.isOnline.value"
            @click="reprint"
          >
            Reimprimir {{ labelCount }}
            {{ labelCount === 1 ? "etiqueta" : "etiquetas" }}
          </UiButton>
        </section>
      </div>

      <UiDialogFooter>
        <UiButton type="button" variant="ghost" class="min-h-11" @click="close">
          Fechar
        </UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>

  <!-- O papel usa a projeção antes do POST e, obrigatoriamente, o documento
       congelado/hashado do PrintJob assim que ele existe. -->
  <div
    v-if="open"
    data-testid="frozen-print-payload"
    :data-document-sha256="printing.job.value?.document_sha256 || ''"
    :data-label-count="labelCount"
    :data-copy-number="copyNumber || 1"
  >
    <WeighingLabels
      :print-mode="effectivePrintMode"
      :labels="effectiveLabels"
      :tickets="effectiveTickets"
      :copy-number="copyNumber || 1"
      :label-width-mm="labelWidthMm"
      :label-height-mm="labelHeightMm"
    />
  </div>
</template>

<style scoped>
.label-roll-preview { box-sizing: border-box; }

@media (prefers-reduced-motion: reduce) {
  .label-roll-preview {
    scroll-behavior: auto;
  }
}

@media print {
  :global([data-slot="dialog-overlay"]) {
    display: none !important;
  }
}
</style>

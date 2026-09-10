import {
  computed,
  onScopeDispose,
  ref,
  toValue,
  watch,
  type MaybeRefOrGetter,
} from "vue";
import type {
  ProductionBrowserPrintResult,
  ProductionLabelMode,
  ProductionLabelTransport,
  ProductionPrintJobCreateRequest,
  ProductionLabelPrintDocument,
  ProductionPrintJobProjection,
  ProductionPrintJobResponse,
  ProductionPrintingSourceProjection,
} from "~/types/productionPrinting";
import { newProductionMutationKey } from "~/utils/api";
import {
  useProductionMutationGuard,
  type ProductionMutationBlock,
} from "~/composables/useProductionMutationGuard";

const PRINT_JOBS_ENDPOINT = "/api/v1/backstage/production/weighing/print-jobs/";
const MIN_POLL_MS = 750;
const MAX_POLL_MS = 5_000;

type PrintOperation =
  "create" | "poll" | "confirm" | "retry" | "reprint" | "browser_result";

export interface ProductionLabelSelection {
  mode: ProductionLabelMode;
  ticketRefs: string[];
}

export interface ProductionLabelPrintingOptions {
  projection: MaybeRefOrGetter<ProductionPrintingSourceProjection | null>;
  selectedDate: MaybeRefOrGetter<string>;
  refreshProjection: () => unknown;
  now?: () => number;
}

function normalizedStatus(job: ProductionPrintJobProjection | null): string {
  return job?.status.trim().toLowerCase() ?? "";
}

export function printJobStatusLabel(
  job: ProductionPrintJobProjection | null,
): string {
  if (!job) return "Pronta para enviar";
  const status = normalizedStatus(job);
  if (["queued", "awaiting_station", "pending", "claimed"].includes(status))
    return "Aguardando estação";
  if (["accepted", "spooled"].includes(status)) return "Enviado à fila";
  if (status === "prepared") return "Pronta para abrir a impressão";
  if (["dispatching", "leased"].includes(status)) return "Enviando";
  if (status === "awaiting_confirmation") return "Aguardando confirmação";
  if (status === "confirmed") return "Saída confirmada";
  if (["failed", "expired"].includes(status)) return "Falha confirmada";
  if (["unknown", "uncertain"].includes(status)) return "Envio sem confirmação";
  if (status === "cancelled") return "Cancelada";
  // Contrato evolutivo: nunca transformar um rótulo novo do backend em uma
  // alegação física que o frontend não mediu.
  if (/impress[ao]/i.test(job.status_label)) return "Estado da fila atualizado";
  return job.status_label || "Estado atualizado";
}

export function isProvenPrintFailure(
  job: ProductionPrintJobProjection | null,
): boolean {
  return ["failed", "expired"].includes(normalizedStatus(job));
}

export function isReprintState(
  job: ProductionPrintJobProjection | null,
): boolean {
  const status = normalizedStatus(job);
  if (status === "failed" && job?.can_reprint && !job.can_retry) return true;
  return [
    "accepted",
    "spooled",
    "awaiting_confirmation",
    "unknown",
    "uncertain",
    "confirmed",
  ].includes(status);
}

function shouldPoll(job: ProductionPrintJobProjection): boolean {
  return ["queued", "leased", "dispatching", "awaiting_station"].includes(
    normalizedStatus(job),
  );
}

function pollDelay(job: ProductionPrintJobProjection): number {
  const requested = Number(job.poll_after_ms);
  if (!Number.isFinite(requested)) return 1_500;
  return Math.min(MAX_POLL_MS, Math.max(MIN_POLL_MS, requested));
}

function clonePrintDocument(
  document: ProductionLabelPrintDocument,
): ProductionLabelPrintDocument {
  // O contrato é JSON puro. A cópia impede que uma projection/fixture reativa
  // altere o papel depois que o servidor congelou e hasheou o documento.
  return JSON.parse(JSON.stringify(document)) as ProductionLabelPrintDocument;
}

/**
 * Máquina de estados do trabalho de etiquetas. A resposta do spooler nunca é
 * promovida a verdade física: somente `/confirm/` pode terminar em confirmed.
 */
export function useProductionLabelPrinting(
  options: ProductionLabelPrintingOptions,
) {
  const { isOnline } = useConnectivity();
  const guard = useProductionMutationGuard(
    options.projection,
    options.refreshProjection,
    options.now,
  );
  const job = ref<ProductionPrintJobProjection | null>(null);
  const operation = ref<PrintOperation | null>(null);
  const errorMessage = ref("");
  const errorCode = ref("");
  const createUncertain = ref(false);
  const pollingMessage = ref("");
  let timer: ReturnType<typeof setTimeout> | null = null;
  let createPayload: ProductionPrintJobCreateRequest | null = null;

  const busy = computed(
    () => operation.value !== null && operation.value !== "poll",
  );
  const printAction = computed(() =>
    toValue(options.projection)?.actions.find(
      (action) => (action.kind as string) === "print_labels",
    ),
  );
  const block = computed<ProductionMutationBlock | null>(() => {
    const freshness = guard.currentBlock();
    if (freshness) return freshness;
    const action = printAction.value;
    if (!action)
      return {
        code: "action_not_projected",
        detail:
          "A autorização para imprimir não veio nesta tela. Atualize os dados.",
        recovery: { action: "refresh", label: "Atualizar dados" },
      };
    if (!action.enabled)
      return {
        code: "action_disabled",
        detail:
          action.reason || "A impressão está indisponível neste contexto.",
        recovery: { action: "refresh", label: "Atualizar dados" },
      };
    if (!action.proof.trim())
      return {
        code: "action_not_projected",
        detail: "A prova para imprimir não veio nesta tela. Atualize os dados.",
        recovery: { action: "refresh", label: "Atualizar dados" },
      };
    return null;
  });
  const statusLabel = computed(() =>
    operation.value === "create" ? "Enviando" : printJobStatusLabel(job.value),
  );
  const destinationLabel = computed(
    () =>
      job.value?.target_label ||
      toValue(options.projection)?.print_destination?.label ||
      "Estação da Preparação",
  );
  const destinationStatusLabel = computed(() => {
    if (job.value) return statusLabel.value;
    const destination = toValue(options.projection)?.print_destination;
    return (
      destination?.status_label || "Destino definido automaticamente ao enviar"
    );
  });

  function stopPolling() {
    if (timer !== null) clearTimeout(timer);
    timer = null;
  }

  function schedulePolling() {
    stopPolling();
    const current = job.value;
    if (!current || !shouldPoll(current)) return;
    timer = setTimeout(() => void poll(), pollDelay(current));
  }

  function acceptResponse(response: ProductionPrintJobResponse) {
    job.value = {
      ...response.print_job,
      print_document: clonePrintDocument(response.print_job.print_document),
    };
    errorMessage.value = "";
    errorCode.value = "";
    createUncertain.value = false;
    pollingMessage.value = "";
    schedulePolling();
  }

  function setRequestError(
    error: unknown,
    fallback: string,
    { uncertain = false }: { uncertain?: boolean } = {},
  ) {
    const status = httpError(error).status;
    if (status === 401 || status === 403)
      operatorSessionOnError({ response: { status } });
    errorCode.value = httpErrorCode(error);
    errorMessage.value = httpErrorMessage(error, fallback);
    createUncertain.value = uncertain;
  }

  async function poll() {
    const current = job.value;
    if (!current || operation.value || !isOnline.value) return;
    operation.value = "poll";
    try {
      const response = await $fetch<ProductionPrintJobResponse>(
        `${PRINT_JOBS_ENDPOINT}${encodeURIComponent(current.ref)}/`,
      );
      acceptResponse(response);
    } catch (error) {
      const status = httpError(error).status;
      if (status === 401 || status === 403)
        operatorSessionOnError({ response: { status } });
      pollingMessage.value =
        "Não foi possível atualizar o estado agora. A estação pode continuar trabalhando.";
      schedulePolling();
    } finally {
      operation.value = null;
    }
  }

  async function create(
    selection: ProductionLabelSelection,
    transport: ProductionLabelTransport,
  ): Promise<boolean> {
    // O lock é erguido antes do primeiro await: dois taps no mesmo frame
    // compartilham uma única tentativa e uma única idempotency_key.
    if (operation.value || job.value) return false;
    const currentBlock = block.value;
    if (currentBlock) {
      errorCode.value = currentBlock.code;
      errorMessage.value = currentBlock.detail;
      return false;
    }
    const source = toValue(options.projection);
    if (!source) return false;
    operation.value = "create";
    errorMessage.value = "";
    errorCode.value = "";
    const action = printAction.value;
    if (!action) {
      operation.value = null;
      return false;
    }
    if (!createPayload) {
      createPayload = {
        mode: selection.mode,
        selected_date: source.selected_date || toValue(options.selectedDate),
        position: source.selected_position_ref || "",
        base_recipe: source.selected_base_recipe || "",
        ticket_refs: [...selection.ticketRefs],
        transport,
        idempotency_key: newProductionMutationKey(),
        projection_generated_at: source.generated_at,
        source_revision: source.source_revision,
        fresh_until: source.fresh_until,
        contract_version: source.contract_version,
        action_ref: action.ref,
        action_proof: action.proof,
      };
    }
    try {
      const response = await $fetch<ProductionPrintJobResponse>(
        action.href || PRINT_JOBS_ENDPOINT,
        { method: "POST", body: createPayload },
      );
      acceptResponse(response);
      return true;
    } catch (error) {
      const status = httpError(error).status;
      const uncertain = status === 0 || status >= 500;
      setRequestError(
        error,
        uncertain
          ? "Não recebemos resposta. O trabalho pode ter sido criado; verifique o envio antes de tentar de novo."
          : "Não foi possível preparar as etiquetas. Revise e tente novamente.",
        { uncertain },
      );
      return false;
    } finally {
      operation.value = null;
    }
  }

  async function postAction(
    action: Exclude<PrintOperation, "create" | "poll">,
    suffix: "confirm" | "retry" | "reprint" | "browser-result",
    body: Record<string, unknown>,
    fallback: string,
  ): Promise<boolean> {
    if (operation.value || !job.value) return false;
    if (!isOnline.value) {
      errorCode.value = "offline";
      errorMessage.value =
        "Sem conexão. O resultado foi preservado nesta tela; registre ao reconectar.";
      return false;
    }
    operation.value = action;
    errorMessage.value = "";
    errorCode.value = "";
    const ref = job.value.ref;
    try {
      const response = await $fetch<ProductionPrintJobResponse>(
        `${PRINT_JOBS_ENDPOINT}${encodeURIComponent(ref)}/${suffix}/`,
        { method: "POST", body },
      );
      acceptResponse(response);
      return true;
    } catch (error) {
      setRequestError(error, fallback);
      return false;
    } finally {
      operation.value = null;
    }
  }

  function confirm(outputWasComplete: boolean): Promise<boolean> {
    if (!job.value?.can_confirm) return Promise.resolve(false);
    return postAction(
      "confirm",
      "confirm",
      {
        result: outputWasComplete ? "confirmed" : "incomplete",
        idempotency_key: newProductionMutationKey(),
      },
      "Não foi possível registrar a confirmação. Tente novamente.",
    );
  }

  function retry(): Promise<boolean> {
    if (!job.value?.can_retry || !isProvenPrintFailure(job.value))
      return Promise.resolve(false);
    return postAction(
      "retry",
      "retry",
      { idempotency_key: newProductionMutationKey() },
      "Não foi possível tentar novamente. Verifique a estação.",
    );
  }

  function reprint(
    transport: ProductionLabelTransport = "relay",
  ): Promise<boolean> {
    if (!job.value?.can_reprint || !isReprintState(job.value))
      return Promise.resolve(false);
    return postAction(
      "reprint",
      "reprint",
      { idempotency_key: newProductionMutationKey(), transport },
      "Não foi possível registrar a reimpressão. Verifique a estação.",
    );
  }

  function recordBrowserResult(result: ProductionBrowserPrintResult) {
    if (!job.value) return Promise.resolve(false);
    return postAction(
      "browser_result",
      "browser-result",
      { result, idempotency_key: newProductionMutationKey() },
      result === "dialog_opened"
        ? "O diálogo abriu, mas não foi possível registrar o resultado. Confirme antes de reimprimir."
        : "A impressão deste dispositivo não respondeu. Use Chrome, Safari ou envie à estação.",
    );
  }

  async function refreshSource() {
    await guard.refreshSafely();
    if (!block.value) {
      errorMessage.value = "";
      errorCode.value = "";
    }
  }

  function reset() {
    stopPolling();
    job.value = null;
    operation.value = null;
    errorMessage.value = "";
    errorCode.value = "";
    createUncertain.value = false;
    pollingMessage.value = "";
    createPayload = null;
  }

  watch(isOnline, (online) => {
    if (!online) {
      stopPolling();
      if (job.value && shouldPoll(job.value))
        pollingMessage.value =
          "Sem conexão. O trabalho continua registrado e será atualizado ao reconectar.";
      return;
    }
    if (pollingMessage.value.startsWith("Sem conexão"))
      pollingMessage.value = "";
    schedulePolling();
  });

  onScopeDispose(stopPolling);

  return {
    job,
    isOnline,
    busy,
    operation,
    block,
    statusLabel,
    destinationLabel,
    destinationStatusLabel,
    errorMessage,
    errorCode,
    createUncertain,
    pollingMessage,
    create,
    poll,
    confirm,
    retry,
    reprint,
    recordBrowserResult,
    refreshSource,
    reset,
  };
}

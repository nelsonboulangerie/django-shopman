// Painel do Marketing — leitura do board + as decisões do card.
//
// ADR-016 (SSE-first): o push do canal pessoal (`/sse/notifications`) só avisa
// que chegou coisa nova; a VERDADE é sempre o refetch do board. O poll fica
// como rede de segurança em cadência calma.
import type {
  BoardResponse,
  Announcement,
  AnnouncementEdits,
  MarketingCommandResponse,
  PublishMode,
  ReachLimit,
} from "~/types/campaign";
import { NOTIFICATION_REVISION_STATE } from "~/composables/useUserNotifications";

const POLL_MS = 60_000;

export function buildApprovalCommand(
  edits: AnnouncementEdits,
  baseVersion: number,
  publishMode: PublishMode,
  publishTimezone: string,
) {
  const { publish_at: publishAt, ...contentEdits } = edits;
  if (publishMode !== "now" && publishMode !== "scheduled") {
    throw new Error("approval requires an explicit publish mode");
  }
  if (!publishTimezone.trim()) {
    throw new Error("approval requires the shop timezone");
  }
  if (publishMode === "scheduled") {
    if (!publishAt) throw new Error("scheduled approval requires publish_at");
    return {
      ...contentEdits,
      publish_at: publishAt,
      publish_timezone: publishTimezone,
      base_version: baseVersion,
      publish_mode: publishMode,
    };
  }
  // Clicking "Publicar agora" wins even if the scheduling panel still holds a
  // value.  The timestamp is omitted, rather than relying on the API to guess.
  return {
    ...contentEdits,
    publish_timezone: publishTimezone,
    base_version: baseVersion,
    publish_mode: publishMode,
  };
}

export function useCampaignBoard() {
  const decisionCommand = useMarketingDecisionCommand();
  const decisionError = ref("");
  const { data, refresh, pending, error } = useFetch<BoardResponse>(
    "/api/v1/backstage/marketing/",
    {
      key: "marketing-board",
      server: true,
      onResponseError: operatorSessionOnError,
    },
  );

  const board = computed(() => data.value?.board);
  const pendingPosts = computed<Announcement[]>(
    () => board.value?.pending ?? [],
  );
  const recentPosts = computed<Announcement[]>(() => board.value?.recent ?? []);
  const stats = computed(() => board.value?.stats);
  /** Limites de alcance: aparecem no topo do painel, antes de qualquer disparo. */
  const reachLimits = computed<ReachLimit[]>(
    () => board.value?.reach_limits ?? [],
  );
  const aiAssistAvailable = computed(
    () => board.value?.ai_assist_available ?? false,
  );
  const shopTimezone = computed(() => board.value?.shop_timezone ?? "UTC");
  // Keep one key for the same visible version + consequence. If the response is
  // lost and the operator taps again, the backend returns the original receipt
  // instead of creating a second command.
  const approvalKeys = new Map<string, string>();

  let pollTimer: ReturnType<typeof setInterval> | null = null;
  onMounted(() => {
    pollTimer = setInterval(() => refresh(), POLL_MS);
  });
  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer);
  });

  // A caixa pessoal possui uma única conexão SSE. Ela publica somente uma
  // revisão local; o board continua buscando sua própria verdade canônica.
  const notificationRevision = useState<number>(
    NOTIFICATION_REVISION_STATE,
    () => 0,
  );
  watch(notificationRevision, () => void refresh());

  async function approve(
    pk: number,
    edits: AnnouncementEdits,
    publishMode: PublishMode,
  ): Promise<MarketingCommandResponse | null> {
    const announcement = pendingPosts.value.find((item) => item.pk === pk);
    if (!announcement) {
      useSonner.error(
        "Este anúncio mudou ou saiu da fila. Atualizamos o painel.",
      );
      await refresh();
      return null;
    }
    let command: ReturnType<typeof buildApprovalCommand>;
    try {
      command = buildApprovalCommand(
        edits,
        announcement.version,
        publishMode,
        shopTimezone.value,
      );
    } catch {
      useSonner.error("Escolha a data e a hora para agendar.");
      return null;
    }
    const fingerprint = `approve:${pk}:${JSON.stringify(command)}`;
    let idempotencyKey = approvalKeys.get(fingerprint);
    if (!idempotencyKey) {
      idempotencyKey = globalThis.crypto.randomUUID();
      approvalKeys.set(fingerprint, idempotencyKey);
    }
    return decide(
      pk,
      "approve",
      command,
      publishMode === "scheduled"
        ? "Anúncio agendado."
        : "Anúncio preparado para publicação.",
      idempotencyKey,
    );
  }

  // O motivo é opcional: exigir justificativa só ensina o gestor a digitar "não".
  async function reject(
    pk: number,
    reason = "",
  ): Promise<MarketingCommandResponse | null> {
    const announcement = pendingPosts.value.find((item) => item.pk === pk);
    if (!announcement) {
      useSonner.error(
        "Este anúncio mudou ou saiu da fila. Atualizamos o painel.",
      );
      await refresh();
      return null;
    }
    const command = { base_version: announcement.version, reason };
    const fingerprint = `reject:${pk}:${JSON.stringify(command)}`;
    let idempotencyKey = approvalKeys.get(fingerprint);
    if (!idempotencyKey) {
      idempotencyKey = globalThis.crypto.randomUUID();
      approvalKeys.set(fingerprint, idempotencyKey);
    }
    return decide(pk, "reject", command, "Anúncio recusado.", idempotencyKey);
  }

  async function decide(
    pk: number,
    action: "approve" | "reject",
    // Aprovar manda edições; recusar manda o motivo. Não é o mesmo corpo, e fingir
    // que é obrigaria um cast que esconde exatamente essa diferença.
    body: AnnouncementEdits | { reason: string },
    okMessage: string,
    idempotencyKey: string,
  ): Promise<MarketingCommandResponse | null> {
    decisionError.value = "";
    try {
      const response = await decisionCommand.begin({
        announcementId: pk,
        action,
        body: body as Record<string, unknown>,
        idempotencyKey,
      });
      if (!response) return null;
      useSonner.success(okMessage);
      await refresh();
      return response;
    } catch (err) {
      useSonner.error(
        httpErrorMessage(err, "Não foi possível concluir. Tente de novo."),
      );
      // Refetch mesmo no erro: quem falhou por expiração precisa sumir do painel.
      await refresh();
      return null;
    }
  }

  async function confirmDecision(value: {
    credential: string;
    typedConfirmation: string;
  }): Promise<MarketingCommandResponse | null> {
    const command = decisionCommand.pendingDecision.value;
    if (!command) return null;
    decisionError.value = "";
    try {
      const response = await decisionCommand.confirm(value);
      const message =
        command.action === "reject"
          ? "Anúncio recusado."
          : command.body.publish_mode === "scheduled"
            ? "Anúncio agendado."
            : "Anúncio preparado para publicação.";
      useSonner.success(message);
      await refresh();
      return response;
    } catch (err) {
      decisionError.value = httpErrorMessage(
        err,
        "Não foi possível confirmar. O anúncio continua sem nova decisão.",
      );
      return null;
    }
  }

  function cancelDecision() {
    decisionError.value = "";
    decisionCommand.cancel();
  }

  async function resumeDecision(): Promise<MarketingCommandResponse | null> {
    const command = decisionCommand.pendingReauthentication.value;
    if (!command) return null;
    decisionError.value = "";
    try {
      const response = await decisionCommand.resumeAfterReauthentication();
      // `null` significa que o servidor devolveu um challenge novo; o diálogo
      // normal fará a reconfirmação, sem reaproveitar o token anterior.
      if (!response) return null;
      useSonner.success(
        command.action === "reject"
          ? "Anúncio recusado."
          : command.body.publish_mode === "scheduled"
            ? "Anúncio agendado."
            : "Anúncio preparado para publicação.",
      );
      await refresh();
      return response;
    } catch (err) {
      decisionError.value = httpErrorMessage(
        err,
        "Não foi possível retomar. Sua decisão continua preservada.",
      );
      return null;
    }
  }

  async function saveDraft(
    pk: number,
    edits: AnnouncementEdits,
  ): Promise<boolean> {
    try {
      await $fetch(`/api/v1/backstage/marketing/announcements/${pk}/`, {
        method: "PATCH",
        body: edits,
      });
      useSonner.success("Rascunho salvo.");
      await refresh();
      return true;
    } catch (err) {
      flagMarketingSessionError(err);
      useSonner.error(httpErrorMessage(err, "Não foi possível salvar."));
      return false;
    }
  }

  return {
    board,
    reachLimits,
    aiAssistAvailable,
    shopTimezone,
    pendingPosts,
    recentPosts,
    stats,
    loading: pending,
    error,
    refresh,
    approve,
    reject,
    pendingDecision: decisionCommand.pendingDecision,
    pendingReauthentication: decisionCommand.pendingReauthentication,
    decisionError,
    confirmDecision,
    resumeDecision,
    cancelDecision,
    saveDraft,
  };
}

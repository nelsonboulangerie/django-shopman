// Painel do Marketing — leitura do board + as decisões do card.
//
// ADR-016 (SSE-first): o push do canal pessoal (`/sse/notifications`) só avisa
// que chegou coisa nova; a VERDADE é sempre o refetch do board. O poll fica
// como rede de segurança em cadência calma.
import type { BoardResponse, Announcement, AnnouncementEdits, ReachLimit } from "~/types/campaign";

const POLL_MS = 60_000;

export function useCampaignBoard() {
  const { data, refresh, pending, error } = useFetch<BoardResponse>(
    "/api/v1/backstage/marketing/",
    { key: "marketing-board", server: true },
  );

  const board = computed(() => data.value?.board);
  const pendingPosts = computed<Announcement[]>(() => board.value?.pending ?? []);
  const recentPosts = computed<Announcement[]>(() => board.value?.recent ?? []);
  const stats = computed(() => board.value?.stats);
  /** Limites de alcance: aparecem no topo do painel, antes de qualquer disparo. */
  const reachLimits = computed<ReachLimit[]>(() => board.value?.reach_limits ?? []);
  const aiAssistAvailable = computed(() => board.value?.ai_assist_available ?? false);
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

  // Push pessoal: announcement novo pedindo revisão chega aqui antes do poll.
  useUserNotifications(() => refresh());

  async function approve(pk: number, edits: AnnouncementEdits = {}): Promise<boolean> {
    const announcement = pendingPosts.value.find(item => item.pk === pk);
    if (!announcement) {
      useSonner.error("Este anúncio mudou ou saiu da fila. Atualizamos o painel.");
      await refresh();
      return false;
    }
    const command = {
      ...edits,
      base_version: announcement.version,
      publish_mode: edits.publish_at ? "scheduled" : "now",
    };
    const fingerprint = `${pk}:${JSON.stringify(command)}`;
    let idempotencyKey = approvalKeys.get(fingerprint);
    if (!idempotencyKey) {
      idempotencyKey = globalThis.crypto.randomUUID();
      approvalKeys.set(fingerprint, idempotencyKey);
    }
    return decide(
      pk,
      "approve",
      command,
      edits.publish_at ? "Anúncio agendado." : "Anúncio preparado para publicação.",
      { "Idempotency-Key": idempotencyKey },
    );
  }

  // O motivo é opcional: exigir justificativa só ensina o gestor a digitar "não".
  async function reject(pk: number, reason = ""): Promise<boolean> {
    return decide(pk, "reject", { reason }, "Anúncio recusado.");
  }

  async function decide(
    pk: number,
    action: "approve" | "reject",
    // Aprovar manda edições; recusar manda o motivo. Não é o mesmo corpo, e fingir
    // que é obrigaria um cast que esconde exatamente essa diferença.
    body: AnnouncementEdits | { reason: string },
    okMessage: string,
    headers: Record<string, string> = {},
  ): Promise<boolean> {
    try {
      await $fetch(`/api/v1/backstage/marketing/announcements/${pk}/${action}/`, {
        method: "POST",
        body,
        headers,
      });
      useSonner.success(okMessage);
      await refresh();
      return true;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não foi possível concluir. Tente de novo."));
      // Refetch mesmo no erro: quem falhou por expiração precisa sumir do painel.
      await refresh();
      return false;
    }
  }

  async function saveDraft(pk: number, edits: AnnouncementEdits): Promise<boolean> {
    try {
      await $fetch(`/api/v1/backstage/marketing/announcements/${pk}/`, { method: "PATCH", body: edits });
      useSonner.success("Rascunho salvo.");
      await refresh();
      return true;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não foi possível salvar."));
      return false;
    }
  }

  return {
    board,
    reachLimits,
    aiAssistAvailable,
    pendingPosts,
    recentPosts,
    stats,
    loading: pending,
    error,
    refresh,
    approve,
    reject,
    saveDraft,
  };
}

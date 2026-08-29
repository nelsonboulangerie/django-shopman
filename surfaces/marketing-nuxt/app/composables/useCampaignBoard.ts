// Painel do Marketing — leitura do board + as decisões do card.
//
// ADR-016 (SSE-first): o push do canal pessoal (`/sse/notifications`) só avisa
// que chegou coisa nova; a VERDADE é sempre o refetch do board. O poll fica
// como rede de segurança em cadência calma.
import { approvalBody, approvalMessage } from "~/presentation/campaign";
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

  let pollTimer: ReturnType<typeof setInterval> | null = null;
  onMounted(() => {
    pollTimer = setInterval(() => refresh(), POLL_MS);
  });
  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer);
  });

  // Push pessoal: announcement novo pedindo revisão chega aqui antes do poll.
  useUserNotifications(() => refresh());

  // ⚠️ Duas mentiras moravam nesta linha — "Publicar" que não publicava e toast que
  // dizia "publicado" quando o servidor agendou. As duas decisões viraram função pura
  // em `~/presentation/campaign`, onde o motivo está escrito e provado por teste.
  async function approve(pk: number, edits: AnnouncementEdits = {}): Promise<boolean> {
    return decide(pk, "approve", approvalBody(edits));
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
    // Vazio no approve: o texto sai da RESPOSTA (ver `approvalMessage`).
    okMessage = "",
  ): Promise<boolean> {
    try {
      const resposta = await $fetch<{ scheduled?: boolean }>(
        `/api/v1/backstage/marketing/announcements/${pk}/${action}/`,
        { method: "POST", body },
      );
      useSonner.success(okMessage || approvalMessage(resposta));
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

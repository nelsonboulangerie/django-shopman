import { useReadMetadata } from "./useReadMetadata";
import { useBackstageEvents } from "./useBackstageEvents";
import { coalesceRefresh } from "../utils/coalesceRefresh";
import { useOrderIntention } from "./useOrderIntention";
import { useOperatorResourceKey } from "./useOperatorResourceKey";
// Aba Canais — lê o board, liga/desliga qualquer canal (toggle "Ativo", com período,
// motivo e gerente) e, nos feeds, escolhe coleções, rotação e modo automático.
import type { ChannelSwitchProjection, FeedBoardProjection, FeedBoardResponse } from "~/types/feeds";

/** O que o modal do toggle manda: o estado pedido, o período e o motivo. */
export interface ChannelSwitchRequest {
  is_active: boolean;
  period: string;
  reason: string;
  starts_at?: string;
  ends_at?: string;
}

/** Desfecho do toggle: ``code`` distingue "falta gerente" de "PIN errado" sem ler a frase. */
export interface ChannelSwitchOutcome {
  ok: boolean;
  code: string;
  message: string;
}

const MANAGER_CODES = new Set(["manager_approval_required", "manager_approval_invalid"]);

export function useFeedBoard() {
  const path = "/api/v1/backstage/feeds/";
  const { data, pending, error, refresh: fetchBoard } = useFetch<FeedBoardResponse>(path, {
    key: useOperatorResourceKey("feed-board"),
    server: true,
    dedupe: "defer",
    onResponseError: operatorSessionOnError,
  });
  const refresh = coalesceRefresh(() => fetchBoard());
  const { realtime } = useBackstageEvents("catalog", refresh);
  const readMetadata = useReadMetadata(data, error);
  const lastConfirmed = shallowRef<FeedBoardProjection | null>(data.value?.board ?? null);
  watch([data, error], ([value, failure]) => {
    if (value?.board && !failure) lastConfirmed.value = value.board;
  }, { flush: "sync" });
  // Session ownership is provided by the page instance/resource cache key.
  // A transient failure is not a successful empty board.
  const board = computed<FeedBoardProjection | null>(() => data.value?.board ?? lastConfirmed.value);

  const intentions = useOrderIntention();
  const busy = ref<Set<string>>(new Set());
  const isBusy = (ref_: string) => busy.value.has(ref_);
  const errorMsg = ref("");

  async function run(ref_: string, body: Record<string, unknown>, url: string): Promise<boolean> {
    if (busy.value.has(ref_)) return false;
    if (error.value) {
      errorMsg.value = "A leitura está desatualizada. Atualize antes de aplicar; seu rascunho foi mantido.";
      return false;
    }
    errorMsg.value = "";
    busy.value = new Set(busy.value).add(ref_);
    try {
      const operation = url.split("/").filter(Boolean).at(-1)!;
      const action = board.value?.feeds.find((feed) => feed.ref === ref_)?.actions.find((item) => item.ref === operation);
      await intentions.executePath(`feed:${ref_}:${operation}`, url, action, body);
      try { await refresh(); }
      catch { errorMsg.value = "Alteração confirmada. A leitura atualizada falhou; atualize antes da próxima edição."; }
      if (error.value) errorMsg.value = "Alteração confirmada. A leitura atualizada falhou; atualize antes da próxima edição.";
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, error instanceof Error ? error.message : "Falha ao atualizar o feed.");
      useSonner.error(errorMsg.value);
      if (httpError(error).status === 409) {
        try { await refresh(); }
        catch { errorMsg.value += " A leitura atualizada também falhou; o rascunho foi mantido."; }
      }
      return false;
    } finally {
      const next = new Set(busy.value);
      next.delete(ref_);
      busy.value = next;
    }
  }

  const switchFor = (ref_: string): ChannelSwitchProjection | null =>
    board.value?.feeds.find((feed) => feed.ref === ref_)?.switch
    ?? board.value?.catalog_channels.find((channel) => channel.ref === ref_)?.switch
    ?? null;

  /**
   * O toggle "Ativo": uma intenção por canal, com a MESMA chave entre a recusa por
   * falta de gerente e a nova tentativa assinada — a assinatura não entra nos
   * insumos, então o PIN errado não prende o rascunho.
   */
  async function switchChannel(
    ref_: string,
    request: ChannelSwitchRequest,
    approval?: Record<string, string>,
  ): Promise<ChannelSwitchOutcome> {
    if (busy.value.has(ref_)) return { ok: false, code: "busy", message: "" };
    const current = switchFor(ref_);
    const action = current
      ? { enabled: current.enabled, reason: current.disabled_reason,
          payload_schema: { base_revision: current.base_revision, expected_actor_id: current.expected_actor_id } }
      : undefined;
    errorMsg.value = "";
    busy.value = new Set(busy.value).add(ref_);
    try {
      await intentions.executePath(
        `feed:${ref_}:switch`, "/api/v1/backstage/feeds/switch/", action,
        { ref: ref_, ...request }, approval,
      );
      try { await refresh(); } catch { /* a leitura seguinte acerta; o gesto já foi confirmado */ }
      return { ok: true, code: "", message: "" };
    } catch (error) {
      const code = httpErrorCode(error);
      const message = httpErrorMessage(error, error instanceof Error ? error.message : "Não foi possível mudar o canal.");
      // Falta de gerente é o próximo passo do modal, não erro para o toast.
      if (!MANAGER_CODES.has(code)) useSonner.error(message);
      if (httpError(error).status === 409) {
        try { await refresh(); } catch { /* o conflito já foi dito */ }
      }
      return { ok: false, code, message };
    } finally {
      const next = new Set(busy.value);
      next.delete(ref_);
      busy.value = next;
    }
  }
  const setCollections = (ref_: string, collections: string[], baseRevision?: string) =>
    run(ref_, { ref: ref_, collections, ...(baseRevision ? { base_revision: baseRevision } : {}) }, "/api/v1/backstage/feeds/collections/");
  const setRotation = (ref_: string, rotateSeconds: number, itemsPerPage: number, baseRevision?: string) =>
    run(
      ref_,
      { ref: ref_, rotate_seconds: rotateSeconds, items_per_page: itemsPerPage, ...(baseRevision ? { base_revision: baseRevision } : {}) },
      "/api/v1/backstage/feeds/rotation/",
    );
  const setAutomatic = (ref_: string, enabled: boolean, idleMessages: string[], baseRevision?: string) =>
    run(
      ref_,
      { ref: ref_, enabled, idle_messages: idleMessages, ...(baseRevision ? { base_revision: baseRevision } : {}) },
      "/api/v1/backstage/feeds/automatic/",
    );

  return { readMetadata, realtime, board, pending, error, refresh, isBusy, errorMsg, switchChannel, setCollections, setRotation, setAutomatic };
}

import { useOperatorResourceKey } from "./useOperatorResourceKey";
import { coalesceRefresh } from "../utils/coalesceRefresh";
// O checklist vivo de cada canal (aba Canais). Leitura só; o ritmo é o do board de
// canais: quando ele relê (SSE do catálogo, poll de fallback, botão Atualizar), o
// checklist relê junto — sem abrir uma segunda conexão por card.
import type { ChannelHealthProjection, ChannelHealthResponse } from "~/types/channelHealth";

export function useChannelHealth() {
  const { data, refresh: fetchHealth } = useFetch<ChannelHealthResponse>("/api/v1/backstage/channels/health/", {
    key: useOperatorResourceKey("channel-health"),
    server: true,
    dedupe: "defer",
    onResponseError: operatorSessionOnError,
  });
  const refresh = coalesceRefresh(() => fetchHealth());
  const board = useNuxtData(useOperatorResourceKey("feed-board"));
  watch(() => board.data.value, (value, previous) => { if (value && previous) refresh(); });

  const byRef = computed(() => new Map((data.value?.health.channels ?? []).map((c) => [c.ref, c])));
  const healthOf = (ref_: string): ChannelHealthProjection | null => byRef.value.get(ref_) ?? null;
  return { healthOf, refresh };
}

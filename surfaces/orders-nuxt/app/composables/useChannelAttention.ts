import { useOperatorResourceKey } from "./useOperatorResourceKey";
import { useBackstageEvents } from "./useBackstageEvents";
// Canais desligados, pausados ou divergentes — o ponto na navegação ("Canais") e o
// aviso da fila de Pedidos. O fetch REST é a fonte da verdade; o SSE de catálogo
// (o toggle emite nele) só pede a releitura, e o poll calmo cobre o fim de um
// período, que acontece pelo relógio, sem evento.
import type { ChannelAttentionProjection } from "~/types/channelAttention";

const POLL_MS = 60_000;

export function useChannelAttention() {
  const { data, refresh } = useFetch<{ attention: ChannelAttentionProjection }>("/api/v1/backstage/channels/attention/", {
    key: useOperatorResourceKey("channel-attention"),
    server: false,
  });
  useBackstageEvents("catalog", () => refresh());
  const attention = computed<ChannelAttentionProjection | null>(() => data.value?.attention ?? null);

  let timer: ReturnType<typeof setInterval> | null = null;
  onMounted(() => { timer = setInterval(() => { void refresh(); }, POLL_MS); });
  onBeforeUnmount(() => { if (timer) clearInterval(timer); timer = null; });

  return { attention, refresh };
}

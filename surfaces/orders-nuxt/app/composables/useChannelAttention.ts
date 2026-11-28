import { useOperatorResourceKey } from "./useOperatorResourceKey";
import { useSharedLive } from "../../../operator-kit/app/composables/useSharedLive";
import { coalesceRefresh } from "../../../operator-kit/app/utils/coalesceRefresh";
import { subscribeSharedEventSource } from "../../../operator-kit/app/utils/sharedEventSource";
// Canais desligados, pausados ou divergentes — o ponto na navegação ("Canais") e o
// aviso da fila de Pedidos. O fetch REST é a fonte da verdade; o SSE de catálogo
// (o toggle emite nele) só pede a releitura, e o poll calmo cobre o fim de um
// período, que acontece pelo relógio, sem evento.
//
// UMA leitura por app e por pessoa (`useSharedLive`): o app.vue (pelas seções), a fila
// e o sinal da fila chamavam isto, e cada chamada abria o próprio `/sse/catalog` e o
// próprio poll. Medido no beta de 05/11 (GES-01): `/channels/attention/` 51 vezes em
// 6,5 min, e as conexões longas tomando o teto de seis do HTTP/1.1.
import type { ChannelAttentionProjection } from "~/types/channelAttention";

const POLL_MS = 60_000;

export function useChannelAttention() {
  const config = useRuntimeConfig();
  return useSharedLive(
    useOperatorResourceKey("channel-attention"),
    () => {
      const data = ref<{ attention: ChannelAttentionProjection } | null>(null);
      const refresh = coalesceRefresh(async () => {
        try {
          data.value = await $fetch<{ attention: ChannelAttentionProjection }>(
            "/api/v1/backstage/channels/attention/",
          );
        } catch {
          // O ponto de atenção é sinal, não tela: a leitura que falha mantém a última.
        }
      });
      const attention = computed<ChannelAttentionProjection | null>(
        () => data.value?.attention ?? null,
      );
      return { attention, refresh };
    },
    ({ refresh }) => {
      void refresh();
      const timer = setInterval(() => void refresh(), POLL_MS);
      const stream = subscribeSharedEventSource({
        url: ssePath("/sse/catalog", config.app.baseURL),
        events: ["backstage-catalog-update"],
        onEvent: () => void refresh(),
        onOpen: (reconnected) => {
          if (reconnected) void refresh();
        },
      });
      return () => {
        clearInterval(timer);
        stream.close();
      };
    },
  );
}

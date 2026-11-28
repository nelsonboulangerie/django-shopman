// O tempo real das telas de lote da Produção (ADR-016, WP-F15).
//
// Uma conexão só por app no canal `backstage-production` (BFF `/sse/production`),
// compartilhada por toda tela e composable que a pede (`useSharedLive` do kit): a
// Preparação lê a lista e as marcas, a grade lê o quadro e a cozinha, e cada uma
// abrindo o próprio stream gastava as seis conexões por host do HTTP/1.1.
//
// Cada consumidor entrega a SUA leitura canônica (`refresh`): o aviso do canal só diz
// "um lote mudou", e a tela refaz o GET, que continua sendo a fonte da verdade. O poll
// da tela fica de reserva: com o canal aberto, a reserva calma de 60 s; com o canal
// caído (ou ainda conectando), a cadência própria da tela, que é o que o selo anuncia.
//
// `realtime` diz HONESTAMENTE o que a tela tem: "live" só com o canal aberto. O
// cabeçalho (`ProductionHeader`) só escreve "Ao vivo" nesse caso.
import {
  openResilientEventSource,
  type ResilientEventSource,
} from "../../../operator-kit/app/utils/resilientEventSource";
import { useSharedLive } from "../../../operator-kit/app/composables/useSharedLive";

/** Eventos do canal `backstage-production` (shop/handlers/_sse_emitters.py). */
export const PRODUCTION_LIVE_EVENTS = ["backstage-production-update"] as const;
/** Com o canal aberto, o poll é só a reserva (stream que morreu calado, deploy). */
export const PRODUCTION_LIVE_RESERVE_POLL_MS = 60_000;

export type ProductionRealtime = "connecting" | "live" | "polling";

interface ProductionLiveChannel {
  realtime: Ref<ProductionRealtime>;
  listeners: Set<() => void>;
}

function useProductionLiveChannel(): ProductionLiveChannel {
  const config = useRuntimeConfig();
  return useSharedLive<ProductionLiveChannel>(
    "production-live",
    () => ({ realtime: ref<ProductionRealtime>("polling"), listeners: new Set() }),
    (channel) => {
      const notify = () => {
        for (const listener of [...channel.listeners]) listener();
      };
      channel.realtime.value = "connecting";
      let source: ResilientEventSource | null = openResilientEventSource({
        url: ssePath("/sse/production", config.app.baseURL),
        events: PRODUCTION_LIVE_EVENTS,
        onEvent: notify,
        onOpen: (reconnected) => {
          channel.realtime.value = "live";
          // Reabriu depois de uma queda: cobre o que passou no meio.
          if (reconnected) notify();
        },
        onDown: () => {
          channel.realtime.value = "polling";
        },
      });
      return () => {
        source?.close();
        source = null;
        channel.realtime.value = "polling";
      };
    },
  );
}

/** Rajada de avisos (plano em massa) vira UMA releitura em voo e uma depois dela. */
function coalesce(refresh: () => unknown): () => void {
  let inFlight: Promise<unknown> | null = null;
  let queued = false;
  return () => {
    queued = true;
    if (inFlight) return;
    inFlight = (async () => {
      while (queued) {
        queued = false;
        await refresh();
      }
    })()
      .catch(() => {})
      .finally(() => {
        inFlight = null;
      });
  };
}

/**
 * Liga a leitura canônica de uma tela de lote ao canal da Produção.
 *
 * @param refresh  o GET canônico da tela (o `refresh` do `useFetch`).
 * @param pollMs   a cadência própria da tela, usada enquanto o canal não está aberto.
 */
export function useProductionLive(
  refresh: () => unknown,
  pollMs: () => number,
): { realtime: Ref<ProductionRealtime>; fallbackPollMs: ComputedRef<number> } {
  const channel = useProductionLiveChannel();
  const onPush = coalesce(refresh);

  const fallbackPollMs = computed(() => pollMs());
  useAdaptivePoll(refresh, () =>
    channel.realtime.value === "live"
      ? Math.max(PRODUCTION_LIVE_RESERVE_POLL_MS, fallbackPollMs.value)
      : fallbackPollMs.value,
  );

  onMounted(() => {
    channel.listeners.add(onPush);
  });
  onBeforeUnmount(() => {
    channel.listeners.delete(onPush);
  });

  return { realtime: channel.realtime, fallbackPollMs };
}

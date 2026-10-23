import { toValue } from "vue";

import { shouldConnectSse, shouldPollTick, type PosRealtimeState } from "~/presentation/events";
import {
  openResilientEventSource,
  type ResilientEventSource,
} from "../../../operator-kit/app/utils/resilientEventSource";

export interface PosEventChannel {
  /** Rota SSE same-origin do BFF (`server/routes/sse/*`). */
  path: string;
  /** O evento nomeado que o django-eventstream empurra naquele canal. */
  event: string;
}

/** Os canais que o balcão assina, e o evento nomeado de cada um. Dois streams
 *  porque são duas PERMISSÕES e dois assuntos — não porque a tela precise
 *  distinguir: os dois desembocam no mesmo refetch. */
export const POS_TERMINAL_CHANNELS: readonly PosEventChannel[] = [
  { path: "/sse/cash", event: "backstage-cash-update" },
  // A cozinha mexeu numa comanda deste balcão: o selo "Na cozinha" da linha
  // vira "Pronto" ou "Cancelado" sem ninguém apertar "Atualizar".
  { path: "/sse/tabs", event: "backstage-tabs-update" },
];

/** O canal dos PEDIDOS (o mesmo do Gestor, `shop.manage_orders`): as Encomendas
 *  refazem a leitura quando um pedido nasce, muda de status ou é pago. */
export const POS_ORDER_CHANNELS: readonly PosEventChannel[] = [
  { path: "/sse/orders", event: "backstage-orders-update" },
];

/**
 * Tempo real entre estações do PDV: SSE push + poll de fallback + wake.
 *
 * EventSource same-origin no BFF: /sse/cash (canal `backstage-cash-main`) e
 * /sse/tabs (canal `backstage-tabs-main`, a cozinha mexendo numa comanda). O canal anuncia o que OUTRA estação fez e esta
 * precisa ver sem F5: pedido de troco (pedido/atendido/cancelado), devolução
 * pendente/entregue, turno aberto/fechado. Todo evento dispara o MESMO
 * `onPush` — o refetch da Projection do terminal, que é o fetch canônico onde
 * pendências, turno e comandas já vivem (ADR-016: o push é sinal, o fetch é a
 * verdade).
 *
 * `channels` troca os streams (padrão: cash + tabs). As Encomendas assinam o
 * canal dos pedidos (`POS_ORDER_CHANNELS`) com a mesma mecânica.
 *
 * Fallback: poll calmo (60s) só enquanto o SSE não está vivo — se o stream
 * conecta, o tick não refaz nada. Cada stream se recria sozinho com backoff
 * (`openResilientEventSource`): o 502 de todo deploy deixava o EventSource cru
 * CLOSED e a estação no poll até alguém recarregar. Ao REABRIR, o canal refaz o
 * fetch canônico (o que mudou enquanto o push esteve fora não chegou por ele).
 * Tablet que dormiu/voltou à aba refaz na hora e tenta reconectar sem esperar
 * o backoff.
 */
export function usePosEvents(
  /** `channel` diz qual stream avisou; sem ele (poll, volta à aba) é a releitura inteira. */
  onPush: (channel?: PosEventChannel) => void,
  opts?: { pollMs?: number; enabled?: () => boolean; channels?: readonly PosEventChannel[] },
) {
  /** O stream so conecta com a estacao identificada: no gate os canais sao
   *  negados e o EventSource entraria no ciclo de reconexao com 400. */
  const isEnabled = () => shouldConnectSse(opts?.enabled ? toValue(opts.enabled()) : undefined);
  const config = useRuntimeConfig();
  const realtime = ref<PosRealtimeState>("polling");
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let sources: ResilientEventSource[] = [];
  /** Quais canais estão de pé agora. Um stream vivo já tira a tela do poll; o
   *  outro caindo não a devolve para lá, senão o canal saudável passaria a
   *  refazer fetch de graça. */
  const live = new Set<string>();

  const channels = opts?.channels ?? POS_TERMINAL_CHANNELS;

  function connectSse() {
    if (!isEnabled() || sources.length) return;
    realtime.value = "connecting";
    for (const channel of channels) {
      sources.push(
        openResilientEventSource({
          url: ssePath(channel.path, config.app.baseURL),
          // django-eventstream empurra eventos nomeados; qualquer um = refetch.
          events: [channel.event],
          onEvent: () => onPush(channel),
          onOpen: (reconnected) => {
            live.add(channel.path);
            realtime.value = "live";
            if (reconnected) onPush(channel);
          },
          onDown: () => {
            live.delete(channel.path);
            if (!live.size) realtime.value = "polling";
          },
        }),
      );
    }
  }

  function closeSse() {
    sources.forEach((source) => source.close());
    sources = [];
    live.clear();
    // Sem stream de pe, o tick de poll volta a ser o dono do refresh.
    realtime.value = "polling";
  }

  const onVisible = () => {
    if (!isEnabled()) {
      closeSse();
      return;
    }
    if (document.visibilityState !== "visible") return;
    onPush();
    // Stream esperando o backoff (ex.: recusado antes do login)? Tenta já: a
    // sessão pode ter nascido desde então.
    if (sources.length) sources.forEach((source) => source.reconnectNow());
    else connectSse();
  };

  onMounted(() => {
    pollTimer = setInterval(() => {
      if (shouldPollTick(realtime.value)) onPush();
    }, opts?.pollMs ?? 60_000);
    connectSse();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
  });
  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer);
    closeSse();
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", onVisible);
  });

  // Liga/desliga junto com a identificacao da estacao: destravar reconecta,
  // travar derruba os streams (o ciclo de 400 do gate nao volta a ocorrer).
  watch(isEnabled, (on) => {
    if (on) connectSse();
    else closeSse();
  });

  return { realtime };
}

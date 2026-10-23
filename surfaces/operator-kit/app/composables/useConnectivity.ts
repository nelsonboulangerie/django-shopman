import { computed, onScopeDispose, ref } from "vue";
import { useOnline } from "@vueuse/core";
import { useReachability } from "./useReachability";

type ReconnectHandler = () => void | Promise<void>;

/**
 * Sinal de conexão do operador (omotenashi de rede: uma padaria tem wi-fi instável).
 *
 * Expõe `isOnline` reativo e `onReconnect(handler)` para reconciliar dado stale ao
 * voltar a rede OU ao reganhar foco da aba (`visibilitychange`) — o tablet do balcão
 * que dormiu não deve esperar o próximo tick com dados velhos. O `<OfflineBanner>`
 * consome `isOnline` para um aviso calmo, nunca no vácuo ([[feedback_transparent_timeouts]]).
 *
 * `isOnline` são as duas metades: o navegador na rede (`navigator.onLine`) E o
 * servidor respondendo (`useReachability`). Wi-fi de pé com o link caído é "sem
 * conexão" também, desde que a tela relate a falha de transporte; e a sonda leve
 * do `useReachability` é o que faz a volta do link contar como reconexão.
 */
export function useConnectivity() {
  const browserOnline = useOnline();
  const reachability = useReachability();
  const online = computed(() => browserOnline.value !== false && reachability.reachable.value);
  const handlers = new Set<ReconnectHandler>();
  // A tela que JÁ ABRE sem rede (o casco sem conexão do PDV, `offlineShellPaths`)
  // nunca vê a transição online→offline: sem isto, a volta da rede não contava
  // como reconexão e a fila de vendas guardadas esperava o próximo ciclo de 30 s.
  const wasOffline = ref(online.value === false);

  const runHandlers = () => {
    for (const handler of handlers) {
      try {
        void handler();
      } catch {
        // reconciliação best-effort; nunca propaga
      }
    }
  };

  if (import.meta.client) {
    watch(online, (value) => {
      if (!value) {
        wasOffline.value = true;
      } else if (wasOffline.value) {
        wasOffline.value = false;
        runHandlers();
      }
    });

    const onVisible = () => {
      if (document.visibilityState === "visible" && online.value) runHandlers();
    };
    document.addEventListener("visibilitychange", onVisible);
    onScopeDispose(() => document.removeEventListener("visibilitychange", onVisible));
  }

  /** Registra um reconciliador chamado ao reconectar / reganhar foco. Retorna o unregister. */
  const onReconnect = (handler: ReconnectHandler) => {
    handlers.add(handler);
    onScopeDispose(() => handlers.delete(handler));
    return () => handlers.delete(handler);
  };

  return { isOnline: online, onReconnect, reachability };
}

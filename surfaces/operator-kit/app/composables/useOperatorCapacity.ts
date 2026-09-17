// Leitura de capacidade do serviço para o indicador do rail.
//
// Cadência CALMA de propósito: quem responde é o próprio processo que está sendo
// medido, então a leitura não pode virar carga. Uma a cada 45 s, pausada com a
// aba em segundo plano (e retomada na volta se a última já envelheceu). Não há
// SSE aqui: o dado nasce no Nitro, não no Django, e o aviso ao gestor já viaja
// pelo canal de alertas quando a regra dispara.
import type { CapacityResponse } from "../types/capacity";
import { httpError } from "../utils/httpError";
import { ssePath } from "../utils/ssePath";
import { coalesceRefresh } from "../utils/coalesceRefresh";

export const CAPACITY_POLL_MS = 45_000;
export const CAPACITY_ROUTE = "/health/capacity";

export function useOperatorCapacity() {
  const reading = ref<CapacityResponse | null>(null);
  /** O servidor respondeu 200 para este operador — só então há o que mostrar. */
  const authorized = ref(false);
  /** A última tentativa falhou por rede/servidor; a leitura anterior fica, marcada como velha. */
  const stale = ref(false);
  const lastFetchedAt = ref(0);
  let disposed = false;

  const path = ssePath(CAPACITY_ROUTE, useRuntimeConfig().app.baseURL);

  const hidden = () => typeof document !== "undefined" && document.visibilityState === "hidden";

  const refresh = coalesceRefresh(async () => {
    if (disposed || hidden()) return;
    try {
      const res = await $fetch<CapacityResponse>(path, { headers: { accept: "application/json" } });
      if (disposed) return;
      reading.value = res;
      authorized.value = true;
      stale.value = false;
      lastFetchedAt.value = Date.now();
    } catch (failure) {
      if (disposed) return;
      const { status } = httpError(failure);
      if (status === 401 || status === 403) {
        // Sessão caída ou sem permissão: o indicador some em vez de mentir.
        reading.value = null;
        authorized.value = false;
        return;
      }
      stale.value = true;
    }
  });

  function onVisibility() {
    if (!hidden() && Date.now() - lastFetchedAt.value >= CAPACITY_POLL_MS) void refresh();
  }

  let timer: ReturnType<typeof setInterval> | null = null;
  onMounted(() => {
    void refresh();
    timer = setInterval(() => void refresh(), CAPACITY_POLL_MS);
    document.addEventListener("visibilitychange", onVisibility);
  });
  onBeforeUnmount(() => {
    disposed = true;
    if (timer) clearInterval(timer);
    timer = null;
    document.removeEventListener("visibilitychange", onVisibility);
  });

  return { reading, authorized, stale, refresh };
}

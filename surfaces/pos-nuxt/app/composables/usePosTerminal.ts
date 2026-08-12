import type { Action, POSOperatorProjection, POSProjection, POSResponse, POSShiftSummaryProjection, POSTabProjection } from "~/types/pos";

/**
 * Read-side of the POS terminal: the single fetch of the serialized Projection
 * (`{ pos, shift, tabs, operator }`) plus the slices screens consume.
 *
 * This is the surface's window onto the orchestrator's data — `pos.actions`
 * carries the command contract; screens render affordances over it (see
 * `presentation/actions`). Awaiting it (in the shell's `<script setup>`) keeps
 * SSR data ready so a reload stays on the right screen. The operator-lock
 * identity layer lives in the shell setup, where Vue lifecycle hooks survive
 * the await — this composable stays a pure read window.
 */
export async function usePosTerminal() {
  const apiPath = usePosApiPath();
  const requestHeaders = import.meta.server ? useRequestHeaders(["cookie"]) : undefined;
  // A leitura é o primeiro lugar onde a estação travada aparece — antes de o
  // operador tentar qualquer comando. Sem isto o 403 ficava só no `error`, a
  // Projection ficava nula e a tela desenhava um PDV sem barra e sem comandas,
  // como se a loja não tivesse nada aberto. Agora o servidor decide o cadeado.
  // Resolvido ANTES do await: depois dele o contexto do Nuxt já não existe.
  const { flagIfStationLocked } = useStationLock();

  const { data, pending, error, refresh } = await useFetch<POSResponse>(
    () => apiPath("/api/v1/backstage/pos/"),
    { credentials: "include", headers: requestHeaders },
  );

  watch(error, (value) => { if (value) flagIfStationLocked(value); }, { immediate: true });

  const pos = computed<POSProjection | null>(() => data.value?.pos ?? null);
  const shift = computed<POSShiftSummaryProjection | null>(() => data.value?.shift ?? null);
  const tabs = computed<POSTabProjection[]>(() => data.value?.tabs ?? []);
  const operators = computed<POSOperatorProjection[]>(() => pos.value?.operators ?? []);
  const actions = computed<Action[]>(() => pos.value?.actions ?? []);

  return { data, pos, shift, tabs, operators, actions, pending, error, refresh };
}

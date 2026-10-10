import type { Action, POSOperatorProjection, POSProjection, POSResponse, POSShiftSummaryProjection, POSTabProjection } from "~/types/pos";

/** As comandas da última leitura da Projection, para o selo das Comandas no shell. */
export function usePosTabsState() {
  return useState<POSTabProjection[]>("pos-tabs", () => []);
}

/**
 * Uma releitura inteira da Projection por vez, e no máximo uma na fila.
 *
 * A leitura inteira (catálogo com disponibilidade, turno, operadores) custa
 * segundos de CPU no servidor do alpha (1 vCPU). O `useFetch` deduplica do lado
 * do navegador cancelando o pedido anterior, mas o servidor calcula os dois: no
 * alpha (10/10/2026) três releituras seguidas depois de abrir a comanda e de
 * fechar a venda disputavam a CPU com a revisão e o fechamento. Quem pede durante
 * uma leitura em voo ganha UMA leitura nova logo depois dela (que enxerga o que
 * ele acabou de gravar), dividida com todos que pedirem até ela começar.
 *
 * Só no navegador: no servidor o módulo é compartilhado entre requests.
 */
let refreshInFlight: Promise<void> | null = null;
let refreshQueued: Promise<void> | null = null;
export function coalescePosRefresh(run: () => Promise<void>): Promise<void> {
  if (!import.meta.client) return run();
  if (!refreshInFlight) {
    refreshInFlight = Promise.resolve(run()).finally(() => {
      refreshInFlight = null;
    });
    return refreshInFlight;
  }
  if (!refreshQueued) {
    refreshQueued = refreshInFlight
      .catch(() => {})
      .then(() => {
        refreshQueued = null;
        return coalescePosRefresh(run);
      });
  }
  return refreshQueued;
}

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
  const apiPath = useApiPath();
  const requestHeaders = import.meta.server ? useRequestHeaders(["cookie"]) : undefined;
  // A leitura é o primeiro lugar onde a estação travada aparece — antes de o
  // operador tentar qualquer comando. Sem isto o 403 ficava só no `error`, a
  // Projection ficava nula e a tela desenhava um PDV sem barra e sem comandas,
  // como se a loja não tivesse nada aberto. Agora o servidor decide o cadeado.
  // Resolvido ANTES do await: depois dele o contexto do Nuxt já não existe.
  const { flagIfStationLocked } = useStationLock();
  // Antes do `await`: depois dele o contexto do Nuxt já não está garantido.
  const sharedTabs = usePosTabsState();

  const { data, pending, error, refresh: fetchAgain } = await useFetch<POSResponse>(
    () => apiPath("/api/v1/backstage/pos/"),
    { credentials: "include", headers: requestHeaders },
  );
  const refresh = () => coalescePosRefresh(() => fetchAgain());

  watch(error, (value) => { if (value) flagIfStationLocked(value); }, { immediate: true });

  const pos = computed<POSProjection | null>(() => data.value?.pos ?? null);
  const shift = computed<POSShiftSummaryProjection | null>(() => data.value?.shift ?? null);
  const tabs = computed<POSTabProjection[]>(() => data.value?.tabs ?? []);
  // O selo das Comandas no rail (camada da suíte) conta as em uso em qualquer tela
  // do PDV; o rail lê daqui, sem uma segunda leitura.
  watch(tabs, (value) => { sharedTabs.value = value; }, { immediate: true });
  const operators = computed<POSOperatorProjection[]>(() => pos.value?.operators ?? []);
  const actions = computed<Action[]>(() => pos.value?.actions ?? []);

  /**
   * Relê SÓ o quadro de comandas (`?only=tabs`) e o encaixa na leitura atual.
   * É a resposta ao aviso de comanda (SSE `/sse/tabs`): cada salvar de qualquer
   * balcão avisa todas as estações, e reler a projeção inteira a cada aviso
   * (catálogo com disponibilidade, turno, operadores) enchia o servidor nas
   * pausas de quem está vendendo. Falhou, ou ainda não há leitura: a inteira.
   */
  async function refreshTabs() {
    if (!data.value) return refresh();
    try {
      const response = await $fetch<{ tabs: POSTabProjection[] }>(
        apiPath("/api/v1/backstage/pos/?only=tabs"),
        { credentials: "include", headers: requestHeaders },
      );
      if (data.value && Array.isArray(response?.tabs)) data.value = { ...data.value, tabs: response.tabs };
    } catch (failure) {
      flagIfStationLocked(failure);
      await refresh();
    }
  }

  return { data, pos, shift, tabs, operators, actions, pending, error, refresh, refreshTabs };
}

import type { Ref } from "vue";

import { railBadge } from "~/presentation/preorders";
import type { PreorderDetailResponse, PreorderListResponse, PreorderSearchResponse } from "~/types/preorders";

/** A leitura padrão da rota (hoje + 6): o selo da barra lateral. */
const AHEAD_KEY = "pos-preorders-ahead";
/** O período da tela das Encomendas (o dia ou a semana escolhidos). */
const PERIOD_KEY = "pos-preorders-period";
/** O resultado da busca "Cliente veio buscar". */
const SEARCH_KEY = "pos-preorders-search";

/**
 * As leituras que o evento de pedido refaz: o selo, o período e a busca que
 * estão na tela. A busca entra: quem acabou de pagar online ou de ser entregue
 * muda de seção (em aberto → concluída) sem o operador redigitar.
 */
export const PREORDERS_LIVE_KEYS = [AHEAD_KEY, PERIOD_KEY, SEARCH_KEY];

/**
 * O período da tela: `?week=` (modo Semana) ou `?date_from=&date_to=` (modo
 * Dia) → a lista por dia.
 *
 * O corte, o saldo e a situação são do servidor
 * (`backstage/projections/preorders.py`). Leitura client-side (`server: false`):
 * a permissão é do operador identificado na estação, e o SSR não tem quem seja.
 */
export function usePosPreorders(params: Ref<Record<string, string>>) {
  const apiPath = useApiPath();
  const { data, pending, error, refresh } = useFetch<PreorderListResponse>(
    () => apiPath("/api/v1/backstage/pos/preorders/"),
    { key: PERIOD_KEY, query: params, credentials: "include", server: false, lazy: true },
  );
  return { list: data, pending, error, refresh };
}

/**
 * A leitura que o selo da barra lateral JÁ faz (hoje e os seis dias seguintes),
 * para a linha "Hoje" quando o período na tela não contém hoje. Só lê o que está
 * guardado: não pergunta nada ao servidor (a leitura é do rail, que mora na
 * mesma moldura).
 */
export function usePosPreordersAhead() {
  return useNuxtData<PreorderListResponse>(AHEAD_KEY).data;
}

/**
 * "Cliente veio buscar": sem período, em aberto de qualquer data e, com
 * `includeCompleted`, as concluídas numa seção à parte.
 *
 * `enabled` segura a requisição — a busca não pergunta nada ao servidor antes
 * de haver o que procurar. Com `enabled` falso o resultado volta vazio, nunca a
 * resposta da busca anterior.
 */
export function usePosPreorderSearch(options: { query: Ref<string>; includeCompleted: Ref<boolean>; enabled: Ref<boolean> }) {
  const apiPath = useApiPath();
  const params = computed(() => ({
    q: options.query.value.trim(),
    ...(options.includeCompleted.value ? { include_completed: "1" } : {}),
  }));

  const { data, pending, error, refresh } = useFetch<PreorderSearchResponse>(
    () => apiPath("/api/v1/backstage/pos/preorders/search/"),
    {
      key: SEARCH_KEY,
      query: params,
      credentials: "include",
      server: false,
      lazy: true,
      immediate: options.enabled.value,
      watch: false,
    },
  );

  // Um watcher só, que respeita o `enabled`: o `watch` embutido do useFetch
  // perguntaria ao servidor a cada letra, inclusive antes do mínimo da busca.
  watch([params, options.enabled], () => {
    if (options.enabled.value) void refresh();
  }, { deep: true });

  return {
    result: computed(() => (options.enabled.value ? data.value : null)),
    pending,
    error,
    refresh,
  };
}

/**
 * Uma encomenda, para o detalhe. 404 = não é encomenda (ou não existe).
 *
 * A resposta é o detalhe do pedido do Gestor no contexto do balcão (envelope
 * `read_data`, `{order: …}`): as seções comuns e, em `order.counter`, os gestos.
 */
export function usePosPreorderDetail(ref: Ref<string>) {
  const apiPath = useApiPath();
  const { data, pending, error, refresh } = useFetch<PreorderDetailResponse>(
    () => apiPath(`/api/v1/backstage/pos/preorders/${encodeURIComponent(ref.value)}/`),
    { key: `pos-preorder:${ref.value}`, credentials: "include", server: false, lazy: true },
  );
  return { detail: computed(() => data.value?.order ?? null), pending, error, refresh };
}

function isDenied(error: unknown): boolean {
  const status = (error as { statusCode?: number } | null)?.statusCode;
  return status === 401 || status === 403;
}

/**
 * O item "Encomendas" da barra lateral: se aparece, e o selo (as de hoje por
 * entregar, lidas da semana que começa hoje — a resposta padrão da rota).
 *
 * - **Permissão por sondagem**: a rota exige `shop.manage_orders`; 401/403 = o item
 *   some (a tela não oferece porta que vai bater na cara). A resposta boa fica
 *   lembrada em `useState`, para o item não piscar a cada troca de tela.
 * - **SSE primeiro** (ADR-016): o canal dos pedidos (`/sse/orders`, o mesmo do
 *   Gestor) avisa que um pedido nasceu, mudou ou foi pago, e o aviso refaz as
 *   leituras canônicas das Encomendas que estão na tela (`PREORDERS_LIVE_KEYS`).
 *   Sem stream de pé, o fallback é calmo: a cada 2 minutos, e ao voltar à aba.
 */
export function usePosPreordersRail() {
  const apiPath = useApiPath();
  const { data: list, error, refresh } = useFetch<PreorderListResponse>(
    () => apiPath("/api/v1/backstage/pos/preorders/"),
    { key: AHEAD_KEY, credentials: "include", server: false, lazy: true },
  );
  const allowed = useState<boolean>("pos-preorders-allowed", () => false);

  watch(list, (value) => { if (value) allowed.value = true; }, { immediate: true });
  watch(error, (value) => { if (isDenied(value)) allowed.value = false; }, { immediate: true });

  usePosEvents(
    () => {
      if (allowed.value) void refreshNuxtData(PREORDERS_LIVE_KEYS);
      // Sem resposta boa ainda (rede caiu na primeira leitura): tenta de novo no
      // tick calmo. Recusa de permissão não se repete.
      else if (!isDenied(error.value)) void refresh();
    },
    { channels: POS_ORDER_CHANNELS, pollMs: 120_000, enabled: () => allowed.value },
  );

  const badge = computed(() => railBadge(list.value));
  return { allowed, badge };
}
